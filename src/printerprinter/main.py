from __future__ import annotations

import asyncio
import io
import logging
import re
import shlex
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from printerprinter.admin_ui import render_admin_ui_html
from printerprinter.bambuddy_client import BambuddyClient
from printerprinter.config import get_settings
from printerprinter.labeling import render_label_image
from printerprinter.logging_config import configure_logging
from printerprinter.printing import BrotherPrintService
from printerprinter.storage import (
    get_print_start_event,
    has_label_job_attempt,
    init_db,
    list_recent_print_start_events,
    record_label_job_attempt,
    update_print_start_event,
    upsert_print_start_event,
)


LOGGER = logging.getLogger(__name__)


EDITABLE_CONFIG_KEYS: tuple[str, ...] = (
    "BAMBUDDY_BASE_URL",
    "BAMBUDDY_API_TOKEN",
    "BAMBUDDY_TIMEOUT_SECONDS",
    "BAMBUDDY_AUTH_MODE",
    "BAMBUDDY_AUTH_HEADER_NAME",
    "BAMBUDDY_JOBS_ENDPOINT",
    "BAMBUDDY_PRINTERS_ENDPOINT",
    "BAMBUDDY_PRINTER_STATUS_ENDPOINT_TEMPLATE",
    "PRINTERPRINTER_MONITORED_PRINTER_IDS",
    "PRINTERPRINTER_MONITORED_PRINTER_IDENTIFIERS",
    "PRINTERPRINTER_POLL_INTERVAL_SECONDS",
    "PRINTERPRINTER_LABEL_WAIT_SECONDS",
    "PRINTERPRINTER_LABEL_WAIT_POLL_SECONDS",
    "PRINTERPRINTER_PENDING_LABEL_MAX_AGE_SECONDS",
    "BROTHER_ENABLED",
    "BROTHER_MODEL",
    "BROTHER_PRINTER_URI",
    "BROTHER_LABEL_SIZE",
    "BROTHER_CUT",
    "SHOW_PRICE_ON_LABEL",
    "FILAMENT_PRICE_PER_GRAM",
)


class ConfigUpdateRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


def _resolve_env_file_path() -> Path:
    settings = get_settings()
    env_path = Path(settings.env_file_path)
    if env_path.is_absolute():
        return env_path
    cwd_candidate = Path.cwd() / env_path
    if cwd_candidate.exists():
        return cwd_candidate
    return Path(settings.install_dir) / env_path


def _read_env_lines(env_path: Path) -> list[str]:
    if not env_path.exists():
        return []
    return env_path.read_text(encoding="utf-8").splitlines()


def _parse_env_map(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        values[key.strip()] = raw_value.strip()
    return values


def _write_env_updates(env_path: Path, updates: dict[str, str]) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = _read_env_lines(env_path)
    touched_keys: set[str] = set()
    output_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output_lines.append(line)
            continue

        key, _ = stripped.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in updates:
            output_lines.append(f"{normalized_key}={updates[normalized_key]}")
            touched_keys.add(normalized_key)
        else:
            output_lines.append(line)

    missing_keys = [key for key in updates if key not in touched_keys]
    if missing_keys and output_lines and output_lines[-1].strip():
        output_lines.append("")
    for key in missing_keys:
        output_lines.append(f"{key}={updates[key]}")

    content = "\n".join(output_lines).rstrip() + "\n"
    env_path.write_text(content, encoding="utf-8")


async def _run_exec_command(command: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


def _shell_join(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _tail_text(value: str, max_lines: int = 20) -> str:
    lines = [line for line in value.splitlines() if line.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[-max_lines:])


def _exc_message(exc: Exception) -> str:
    detail = str(exc).strip()
    if detail:
        return detail
    return exc.__class__.__name__


def _is_running_state(state: str) -> bool:
    return state.upper() in {"RUNNING", "PRINTING", "IN_PROGRESS", "STARTED"}


def _parse_monitored_ids(raw: str) -> set[str]:
    if not raw.strip():
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _parse_monitored_identifiers(raw: str) -> set[str]:
    if not raw.strip():
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _coerce_int(value: object | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: object | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_iso8601(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC).isoformat()

    text = str(value).strip()
    if not text:
        return None

    try:
        numeric = float(text)
        return datetime.fromtimestamp(numeric, tz=UTC).isoformat()
    except ValueError:
        pass

    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _parse_datetime(value: object | None) -> datetime | None:
    iso = _to_iso8601(value)
    if iso is None:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _eta_mismatch(started_at: object | None, eta_end_at: object | None, est_duration_sec: object | None) -> bool:
    start_dt = _parse_datetime(started_at)
    eta_dt = _parse_datetime(eta_end_at)
    duration = _coerce_int(est_duration_sec)
    if start_dt is None or eta_dt is None or duration is None or duration <= 0:
        return False

    expected_eta = start_dt + timedelta(seconds=duration)
    delta_seconds = abs((eta_dt - expected_eta).total_seconds())
    # Allow small drift from polling/rounding but flag obviously inconsistent ETA.
    return delta_seconds > 120


def _eta_from_start_and_duration(started_at: object | None, est_duration_sec: object | None) -> str | None:
    start_dt = _parse_datetime(started_at)
    duration = _coerce_int(est_duration_sec)
    if start_dt is None or duration is None or duration <= 0:
        return None
    return (start_dt + timedelta(seconds=duration)).isoformat()


def _get_status_value(status: dict[str, object], keys: tuple[str, ...]) -> object | None:
    for key in keys:
        value = status.get(key)
        if value not in (None, ""):
            return value

    for container_key in ("job", "print", "data"):
        nested = status.get(container_key)
        if not isinstance(nested, dict):
            continue
        for key in keys:
            value = nested.get(key)
            if value not in (None, ""):
                return value

    return None


def _extract_event_fields_from_status(status: dict[str, object], now: datetime) -> dict[str, object | None]:
    started_at = _to_iso8601(
        _get_status_value(
            status,
            ("started_at", "start_time", "gcode_start_time", "print_start_time", "job_started_at"),
        )
    )
    if started_at is None:
        started_at = now.isoformat()

    remaining_seconds = _coerce_int(
        _get_status_value(
            status,
            ("remaining_time", "remaining_seconds", "eta_seconds", "time_left", "mc_remaining_time"),
        )
    )

    duration_seconds = _coerce_int(
        _get_status_value(
            status,
            (
                "est_duration_sec",
                "estimated_duration",
                "duration_seconds",
                "total_duration",
                "estimated_total_time",
            ),
        )
    )
    elapsed_seconds = _coerce_int(
        _get_status_value(status, ("elapsed_time", "print_time", "mc_print_time", "elapsed_seconds"))
    )
    if duration_seconds is None and remaining_seconds is not None and elapsed_seconds is not None:
        duration_seconds = remaining_seconds + elapsed_seconds
    if duration_seconds is not None and duration_seconds <= 0:
        duration_seconds = None

    filament_grams = _coerce_float(
        _get_status_value(
            status,
            (
                "filament_estimated_g",
                "filament_grams",
                "filament_used_g",
                "total_filament_g",
                "weight",
            ),
        )
    )
    if filament_grams is not None and filament_grams < 0:
        filament_grams = None

    eta_end_at = _to_iso8601(
        _get_status_value(
            status,
            (
                "eta_end_at",
                "estimated_end_time",
                "eta",
                "end_time",
                "estimated_finish_time",
            ),
        )
    )
    if remaining_seconds is not None and remaining_seconds <= 0:
        remaining_seconds = None
    if eta_end_at is None and remaining_seconds is not None:
        eta_end_at = (now + timedelta(seconds=remaining_seconds)).isoformat()

    return {
        "started_at": started_at,
        "eta_end_at": eta_end_at,
        "est_duration_sec": duration_seconds,
        "filament_estimated_g": filament_grams,
    }


def _needs_enrichment(fields: dict[str, object | None]) -> bool:
    eta_end_at = fields.get("eta_end_at")
    started_at = fields.get("started_at")
    est_duration_sec = _coerce_int(fields.get("est_duration_sec"))
    filament_estimated_g = _coerce_float(fields.get("filament_estimated_g"))

    if eta_end_at is None or (started_at is not None and eta_end_at == started_at):
        return True
    if est_duration_sec is None or est_duration_sec <= 0:
        return True
    if filament_estimated_g is None:
        return True
    if _eta_mismatch(started_at, eta_end_at, est_duration_sec):
        return True
    return False


def _normalize_name(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    # Normalize common filename delimiters to improve matching across API sources.
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _name_tokens(value: object | None) -> set[str]:
    normalized = _normalize_name(value)
    if not normalized:
        return set()
    return {token for token in normalized.split(" ") if token}


def _names_compatible(expected: object | None, candidate: object | None) -> bool:
    expected_normalized = _normalize_name(expected)
    candidate_normalized = _normalize_name(candidate)

    if not expected_normalized and not candidate_normalized:
        return True
    if not expected_normalized or not candidate_normalized:
        return False
    if expected_normalized == candidate_normalized:
        return True

    expected_tokens = _name_tokens(expected)
    candidate_tokens = _name_tokens(candidate)

    if not expected_tokens or not candidate_tokens:
        return False

    if expected_tokens == candidate_tokens:
        return True

    ignored_suffix_tokens = {"gcode", "3mf", "stl"}
    expected_core = expected_tokens - ignored_suffix_tokens
    candidate_core = candidate_tokens - ignored_suffix_tokens
    if not expected_core or not candidate_core:
        return False

    smaller, larger = (
        (expected_core, candidate_core)
        if len(expected_core) <= len(candidate_core)
        else (candidate_core, expected_core)
    )
    # Accept subset matches when at least three meaningful words align.
    return len(smaller) >= 3 and smaller.issubset(larger)


def _job_enrichment_score(job: object) -> tuple[int, int]:
    duration = _coerce_int(getattr(job, "est_duration_sec", None))
    filament = _coerce_float(getattr(job, "filament_estimated_g", None))
    eta_end_at = getattr(job, "eta_end_at", None)
    started_at = getattr(job, "started_at", None)

    score = 0
    if duration is not None and duration > 0:
        score += 4
    if filament is not None and filament >= 0:
        score += 4
    if eta_end_at:
        score += 2
    if started_at:
        score += 1

    # Very short durations with no filament are often transient "time remaining" values.
    if duration is not None and duration < 600 and filament is None:
        score -= 2

    source_event_id = _coerce_int(getattr(job, "source_event_id", None)) or -1
    return (score, source_event_id)


def _pick_running_job_fields(
    jobs: list,
    *,
    printer_id: str,
    file_name: object | None,
) -> dict[str, object | None]:
    normalized_printer_id = _normalize_name(printer_id)
    normalized_file_name = _normalize_name(file_name)
    candidates: list[object] = []

    for job in jobs:
        job_printer_id = _normalize_name(getattr(job, "printer_id", None))
        if job_printer_id != normalized_printer_id:
            continue

        job_file_name = _normalize_name(getattr(job, "file_name", None))
        if normalized_file_name and job_file_name and not _names_compatible(normalized_file_name, job_file_name):
            continue

        candidates.append(job)

    if not candidates:
        return {}

    best_job = max(candidates, key=_job_enrichment_score)

    return {
        "started_at": getattr(best_job, "started_at", None),
        "eta_end_at": getattr(best_job, "eta_end_at", None),
        "est_duration_sec": getattr(best_job, "est_duration_sec", None),
        "filament_estimated_g": getattr(best_job, "filament_estimated_g", None),
    }


async def _build_event_fields(
    client: BambuddyClient,
    *,
    printer_id: str,
    file_name: object | None,
    initial_status: dict[str, object],
    now: datetime,
) -> dict[str, object | None]:
    fields = _extract_event_fields_from_status(initial_status, now)

    for _ in range(3):
        if not _needs_enrichment(fields):
            break
        await asyncio.sleep(1.5)
        refreshed_status = await client.get_printer_status(printer_id)
        refreshed_fields = _extract_event_fields_from_status(refreshed_status, now)
        for key, value in refreshed_fields.items():
            if fields.get(key) is None and value is not None:
                fields[key] = value

    if _needs_enrichment(fields):
        try:
            jobs = await client.list_print_jobs()
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("running-jobs enrichment failed: %s", _exc_message(exc))
        else:
            job_fields = _pick_running_job_fields(jobs, printer_id=printer_id, file_name=file_name)
            for key, value in job_fields.items():
                if fields.get(key) is None and value is not None:
                    fields[key] = value

            # If status supplied a short-term ETA snapshot but jobs gave a durable duration,
            # force ETA to align with started_at + duration for label correctness.
            if _eta_mismatch(fields.get("started_at"), fields.get("eta_end_at"), fields.get("est_duration_sec")):
                rebuilt_eta = _eta_from_start_and_duration(fields.get("started_at"), fields.get("est_duration_sec"))
                if rebuilt_eta is not None:
                    fields["eta_end_at"] = rebuilt_eta

    if _eta_mismatch(fields.get("started_at"), fields.get("eta_end_at"), fields.get("est_duration_sec")):
        rebuilt_eta = _eta_from_start_and_duration(fields.get("started_at"), fields.get("est_duration_sec"))
        if rebuilt_eta is not None:
            fields["eta_end_at"] = rebuilt_eta

    return fields


def _event_needs_backfill(event: dict[str, object]) -> bool:
    if any(
        event.get(key) in (None, "") or (key == "est_duration_sec" and _coerce_int(event.get(key)) in (None, 0))
        for key in ("eta_end_at", "est_duration_sec", "filament_estimated_g")
    ):
        return True

    return _eta_mismatch(
        event.get("started_at"),
        event.get("eta_end_at"),
        event.get("est_duration_sec"),
    )


def _parse_created_at(value: object | None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace(" ", "T").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _job_matches_event(job, event: dict[str, object]) -> bool:
    job_printer_id = _normalize_name(getattr(job, "printer_id", None))
    event_printer_id = _normalize_name(event.get("printer_id"))
    if job_printer_id != event_printer_id:
        return False

    event_file_name = _normalize_name(event.get("file_name"))
    job_file_name = _normalize_name(getattr(job, "file_name", None))
    if event_file_name:
        return _names_compatible(event_file_name, job_file_name)

    if job_file_name:
        return False

    return True


async def reconcile_recent_events(client: BambuddyClient, db_path: str) -> int:
    try:
        recent_events = list_recent_print_start_events(db_path, limit=25)
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("recent event lookup failed: %s", _exc_message(exc))
        return 0

    targets = [event for event in recent_events if _event_needs_backfill(event)]
    if not targets:
        return 0

    try:
        jobs = await client.list_print_jobs()
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("event reconciliation job lookup failed: %s", _exc_message(exc))
        return 0

    updates = 0
    for event in targets:
        matched_jobs = [job for job in jobs if _job_matches_event(job, event)]
        if not matched_jobs:
            continue

        matched_job = max(matched_jobs, key=_job_enrichment_score)

        new_started_at = getattr(matched_job, "started_at", None) or event.get("started_at")
        new_eta_end_at = getattr(matched_job, "eta_end_at", None) or event.get("eta_end_at")
        new_duration = getattr(matched_job, "est_duration_sec", None)
        new_filament = getattr(matched_job, "filament_estimated_g", None)

        normalized_duration = _coerce_int(new_duration)
        if _eta_mismatch(new_started_at, new_eta_end_at, normalized_duration):
            rebuilt_eta = _eta_from_start_and_duration(new_started_at, normalized_duration)
            if rebuilt_eta is not None:
                new_eta_end_at = rebuilt_eta

        if _coerce_int(event.get("est_duration_sec")) in (None, 0) and normalized_duration in (None, 0):
            new_duration = None

        if update_print_start_event(
            db_path,
            event_id=int(event["id"]),
            started_at=str(new_started_at) if new_started_at is not None else None,
            eta_end_at=str(new_eta_end_at) if new_eta_end_at is not None else None,
            est_duration_sec=normalized_duration,
            filament_estimated_g=_coerce_float(new_filament),
        ):
            updates += 1

    return updates


async def _attempt_print_for_event(
    db_path: str,
    print_service: BrotherPrintService,
    event: dict[str, object],
) -> bool:
    print_result = await asyncio.to_thread(print_service.print_event, event)
    status = "printed" if print_result.ok else "failed"
    record_label_job_attempt(
        db_path,
        event_id=int(event["id"]),
        status=status,
        attempts=1,
        error_message=print_result.error,
    )
    return print_result.ok


async def _wait_for_event_data(
    client: BambuddyClient,
    db_path: str,
    *,
    event_id: int,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, object] | None:
    event = get_print_start_event(db_path, event_id)
    if event is None:
        return None
    if not _event_needs_backfill(event):
        return event

    timeout = max(0.0, float(timeout_seconds))
    interval = max(1.0, float(poll_interval_seconds))
    if timeout == 0:
        return event

    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(interval)
        await reconcile_recent_events(client, db_path)
        event = get_print_start_event(db_path, event_id)
        if event is None:
            return None
        if not _event_needs_backfill(event):
            return event

    return event


async def process_pending_labels(
    db_path: str,
    print_service: BrotherPrintService,
    *,
    max_age_seconds: float,
    limit: int = 50,
) -> int:
    recent_events = list_recent_print_start_events(db_path, limit=limit)
    now = datetime.now(UTC)
    attempts = 0

    for event in sorted(recent_events, key=lambda item: int(item["id"])):
        event_id = int(event["id"])
        if has_label_job_attempt(db_path, event_id):
            continue

        if _event_needs_backfill(event):
            continue

        created_at = _parse_created_at(event.get("created_at"))
        if created_at is None:
            continue
        if (now - created_at).total_seconds() > max(0.0, float(max_age_seconds)):
            continue

        await _attempt_print_for_event(db_path, print_service, event)
        attempts += 1

    return attempts


def _resolve_allowed_printer_ids(
    printers: list,
    monitored_ids: set[str],
    monitored_identifiers: set[str],
) -> set[str]:
    allowed = set(monitored_ids)
    if not monitored_identifiers:
        return allowed

    for printer in printers:
        candidates = {printer.printer_id.lower()}
        if printer.name:
            candidates.add(printer.name.lower())
        if printer.serial_number:
            candidates.add(printer.serial_number.lower())
        if printer.ip_address:
            candidates.add(printer.ip_address.lower())

        if candidates.intersection(monitored_identifiers):
            allowed.add(printer.printer_id)

    return allowed


async def run_poll_iteration(
    client: BambuddyClient,
    db_path: str,
    monitored_ids: set[str],
    monitored_identifiers: set[str],
    last_states: dict[str, str],
    print_service: BrotherPrintService,
    label_wait_seconds: float,
    label_wait_poll_seconds: float,
) -> dict[str, int]:
    printers = await client.list_printers()
    allowed_ids = _resolve_allowed_printer_ids(printers, monitored_ids, monitored_identifiers)
    seen = 0
    inserted = 0
    printed = 0
    deferred = 0

    for printer in printers:
        if allowed_ids and printer.printer_id not in allowed_ids:
            continue

        status = await client.get_printer_status(printer.printer_id)
        state = str(status.get("state") or "").upper()
        previous = last_states.get(printer.printer_id, "")
        last_states[printer.printer_id] = state
        seen += 1

        if not _is_running_state(state) or _is_running_state(previous):
            continue

        now = datetime.now(UTC)
        file_name = status.get("subtask_name") or status.get("current_print") or status.get("gcode_file")
        event_fields = await _build_event_fields(
            client,
            printer_id=printer.printer_id,
            file_name=file_name,
            initial_status=status,
            now=now,
        )

        source_event_id = f"{printer.printer_id}:{file_name or 'unknown'}:{int(now.timestamp())}"
        result = upsert_print_start_event(
            db_path,
            source="bambuddy",
            source_event_id=source_event_id,
            printer_id=printer.printer_id,
            printer_name=printer.name,
            file_name=str(file_name) if file_name is not None else None,
            started_at=(
                str(event_fields.get("started_at")) if event_fields.get("started_at") is not None else now.isoformat()
            ),
            eta_end_at=(str(event_fields.get("eta_end_at")) if event_fields.get("eta_end_at") is not None else None),
            est_duration_sec=_coerce_int(event_fields.get("est_duration_sec")),
            filament_estimated_g=_coerce_float(event_fields.get("filament_estimated_g")),
        )
        if result["inserted"]:
            inserted += 1
            event_row: dict[str, object] | None = result["event"]
            if _event_needs_backfill(event_row):
                deferred += 1
                event_row = await _wait_for_event_data(
                    client,
                    db_path,
                    event_id=int(result["event"]["id"]),
                    timeout_seconds=label_wait_seconds,
                    poll_interval_seconds=label_wait_poll_seconds,
                )

            if event_row is None:
                continue

            if _event_needs_backfill(event_row):
                LOGGER.info(
                    "label deferred: event_id=%s waiting for duration/filament",
                    event_row.get("id"),
                )
                continue

            if await _attempt_print_for_event(db_path, print_service, event_row):
                printed += 1

    return {"seen": seen, "inserted": inserted, "printed": printed, "deferred": deferred}


async def poller_loop(
    client: BambuddyClient,
    db_path: str,
    interval_seconds: float,
    monitored_ids: set[str],
    monitored_identifiers: set[str],
    last_states: dict[str, str],
    print_service: BrotherPrintService,
    label_wait_seconds: float,
    label_wait_poll_seconds: float,
    pending_label_max_age_seconds: float,
) -> None:
    while True:
        try:
            outcome = await run_poll_iteration(
                client,
                db_path,
                monitored_ids,
                monitored_identifiers,
                last_states,
                print_service,
                label_wait_seconds,
                label_wait_poll_seconds,
            )
            reconciled = await reconcile_recent_events(client, db_path)
            pending_attempts = await process_pending_labels(
                db_path,
                print_service,
                max_age_seconds=pending_label_max_age_seconds,
            )
            LOGGER.info(
                "poll iteration complete: seen=%s inserted=%s printed=%s deferred=%s",
                outcome["seen"],
                outcome["inserted"],
                outcome.get("printed", 0),
                outcome.get("deferred", 0),
            )
            if reconciled:
                LOGGER.info("event reconciliation complete: updated=%s", reconciled)
            if pending_attempts:
                LOGGER.info("pending label processing complete: attempted=%s", pending_attempts)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("poll iteration failed: %s", _exc_message(exc))
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db(settings.db_path)

    client = BambuddyClient(
        base_url=str(settings.bambuddy_base_url),
        api_token=settings.bambuddy_api_token,
        timeout_seconds=settings.bambuddy_timeout_seconds,
        auth_mode=settings.bambuddy_auth_mode,
        auth_header_name=settings.bambuddy_auth_header_name,
        jobs_endpoint=settings.bambuddy_jobs_endpoint,
        printers_endpoint=settings.bambuddy_printers_endpoint,
        printer_status_endpoint_template=settings.printer_status_endpoint_template,
    )
    monitored_ids = _parse_monitored_ids(settings.monitored_printer_ids)
    monitored_identifiers = _parse_monitored_identifiers(settings.monitored_printer_identifiers)
    last_states: dict[str, str] = {}
    print_service = BrotherPrintService(
        enabled=settings.brother_enabled,
        model=settings.brother_model,
        printer_uri=settings.brother_printer_uri,
        label_size=settings.brother_label_size,
        cut=settings.brother_cut,
        show_price=settings.show_price_on_label,
        price_per_gram=settings.filament_price_per_gram,
    )

    app.state.print_service = print_service
    app.state.db_path = settings.db_path

    poller_task = asyncio.create_task(
        poller_loop(
            client,
            settings.db_path,
            settings.poll_interval_seconds,
            monitored_ids,
            monitored_identifiers,
            last_states,
            print_service,
            settings.label_wait_seconds,
            settings.label_wait_poll_seconds,
            settings.pending_label_max_age_seconds,
        ),
        name="bambuddy-poller",
    )
    yield
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="PrinterPrinter", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/probes/bambuddy")
async def probe_bambuddy() -> dict[str, object]:
    settings = get_settings()
    client = BambuddyClient(
        base_url=str(settings.bambuddy_base_url),
        api_token=settings.bambuddy_api_token,
        timeout_seconds=settings.bambuddy_timeout_seconds,
        auth_mode=settings.bambuddy_auth_mode,
        auth_header_name=settings.bambuddy_auth_header_name,
        jobs_endpoint=settings.bambuddy_jobs_endpoint,
        printers_endpoint=settings.bambuddy_printers_endpoint,
        printer_status_endpoint_template=settings.printer_status_endpoint_template,
    )
    result = await client.probe()
    return asdict(result)


@app.post("/admin/poll-once")
async def admin_poll_once() -> dict[str, int]:
    settings = get_settings()
    client = BambuddyClient(
        base_url=str(settings.bambuddy_base_url),
        api_token=settings.bambuddy_api_token,
        timeout_seconds=settings.bambuddy_timeout_seconds,
        auth_mode=settings.bambuddy_auth_mode,
        auth_header_name=settings.bambuddy_auth_header_name,
        jobs_endpoint=settings.bambuddy_jobs_endpoint,
        printers_endpoint=settings.bambuddy_printers_endpoint,
        printer_status_endpoint_template=settings.printer_status_endpoint_template,
    )
    monitored_ids = _parse_monitored_ids(settings.monitored_printer_ids)
    monitored_identifiers = _parse_monitored_identifiers(settings.monitored_printer_identifiers)
    state_cache: dict[str, str] = {}
    print_service = BrotherPrintService(
        enabled=settings.brother_enabled,
        model=settings.brother_model,
        printer_uri=settings.brother_printer_uri,
        label_size=settings.brother_label_size,
        cut=settings.brother_cut,
        show_price=settings.show_price_on_label,
        price_per_gram=settings.filament_price_per_gram,
    )
    try:
        return await run_poll_iteration(
            client,
            settings.db_path,
            monitored_ids,
            monitored_identifiers,
            state_cache,
            print_service,
            settings.label_wait_seconds,
            settings.label_wait_poll_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        msg = _exc_message(exc)
        LOGGER.warning("manual poll failed: %s", msg)
        raise HTTPException(status_code=502, detail=f"Bambuddy poll failed: {msg}") from exc


@app.get("/admin/printers")
async def admin_printers() -> dict[str, object]:
    settings = get_settings()
    client = BambuddyClient(
        base_url=str(settings.bambuddy_base_url),
        api_token=settings.bambuddy_api_token,
        timeout_seconds=settings.bambuddy_timeout_seconds,
        auth_mode=settings.bambuddy_auth_mode,
        auth_header_name=settings.bambuddy_auth_header_name,
        jobs_endpoint=settings.bambuddy_jobs_endpoint,
        printers_endpoint=settings.bambuddy_printers_endpoint,
        printer_status_endpoint_template=settings.printer_status_endpoint_template,
    )
    try:
        printers = await client.list_printers()
    except Exception as exc:  # noqa: BLE001
        msg = _exc_message(exc)
        LOGGER.warning("list printers failed: %s", msg)
        raise HTTPException(status_code=502, detail=f"Bambuddy printers lookup failed: {msg}") from exc
    return {
        "count": len(printers),
        "items": [asdict(printer) for printer in printers],
    }


@app.get("/admin/events")
async def admin_events(limit: int = 50) -> dict[str, object]:
    settings = get_settings()
    items = list_recent_print_start_events(settings.db_path, limit=limit)
    return {"count": len(items), "items": items}


@app.get("/admin/ui", response_class=HTMLResponse)
async def admin_ui() -> HTMLResponse:
    return HTMLResponse(content=render_admin_ui_html())


@app.get("/admin", response_class=HTMLResponse)
async def admin_ui_shortcut() -> HTMLResponse:
    return HTMLResponse(content=render_admin_ui_html())


@app.get("/admin/config")
async def admin_get_config() -> dict[str, object]:
    env_path = _resolve_env_file_path()
    lines = _read_env_lines(env_path)
    values = _parse_env_map(lines)
    filtered_values = {key: values.get(key, "") for key in EDITABLE_CONFIG_KEYS}
    missing = [key for key, value in filtered_values.items() if not value]
    return {
        "env_file_path": str(env_path),
        "editable_keys": list(EDITABLE_CONFIG_KEYS),
        "values": filtered_values,
        "missing": missing,
    }


@app.post("/admin/config")
async def admin_update_config(payload: ConfigUpdateRequest) -> dict[str, object]:
    unknown_keys = [key for key in payload.values if key not in EDITABLE_CONFIG_KEYS]
    if unknown_keys:
        raise HTTPException(status_code=400, detail=f"Unsupported config keys: {', '.join(unknown_keys)}")

    updates = {key: str(value).strip() for key, value in payload.values.items()}
    env_path = _resolve_env_file_path()
    _write_env_updates(env_path, updates)
    get_settings.cache_clear()
    return {
        "ok": True,
        "updated": sorted(updates.keys()),
        "env_file_path": str(env_path),
        "detail": "Saved. Restart service to apply runtime polling/printing changes.",
    }


@app.post("/admin/actions/restart")
async def admin_action_restart() -> dict[str, object]:
    settings = get_settings()
    command = ["systemctl", "restart", settings.service_name]
    code, stdout, stderr = await _run_exec_command(command)
    if code != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Command failed ({_shell_join(command)}): {_tail_text(stderr) or _tail_text(stdout)}",
        )
    return {
        "ok": True,
        "command": _shell_join(command),
        "detail": f"Service {settings.service_name} restarted.",
    }


@app.post("/admin/actions/update")
async def admin_action_update() -> dict[str, object]:
    settings = get_settings()
    install_dir = settings.install_dir
    branch = settings.update_branch
    service_name = settings.service_name
    pip_path = Path(settings.venv_path) / "bin" / "pip"

    commands: list[tuple[list[str], str | None, str]] = [
        (["git", "fetch", "origin", branch], install_dir, "fetch"),
        (["git", "pull", "--ff-only", "origin", branch], install_dir, "pull"),
    ]
    if pip_path.exists():
        commands.append(([str(pip_path), "install", "-e", install_dir], install_dir, "pip_install"))
    else:
        commands.append((["python3", "-m", "pip", "install", "-e", install_dir], install_dir, "pip_install"))
    commands.append((["systemctl", "restart", service_name], None, "restart"))

    completed_steps: list[str] = []
    logs: list[dict[str, str]] = []
    for command, cwd, step in commands:
        code, stdout, stderr = await _run_exec_command(command, cwd=cwd)
        logs.append(
            {
                "step": step,
                "command": _shell_join(command),
                "stdout": _tail_text(stdout),
                "stderr": _tail_text(stderr),
            }
        )
        if code != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Update failed during {step}: {_tail_text(stderr) or _tail_text(stdout)}",
            )
        completed_steps.append(step)

    return {
        "ok": True,
        "steps": completed_steps,
        "logs": logs,
        "detail": f"Updated from {branch} and restarted {service_name}.",
    }


@app.get("/admin/label-preview/{event_id}.png")
async def admin_label_preview(event_id: int) -> Response:
    settings = get_settings()
    event = get_print_start_event(settings.db_path, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    image = render_label_image(
        event,
        settings.brother_label_size,
        show_price=settings.show_price_on_label,
        price_per_gram=settings.filament_price_per_gram,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")


@app.post("/admin/print-event/{event_id}")
async def admin_print_event(event_id: int) -> dict[str, object]:
    settings = get_settings()
    event = get_print_start_event(settings.db_path, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    print_service = BrotherPrintService(
        enabled=settings.brother_enabled,
        model=settings.brother_model,
        printer_uri=settings.brother_printer_uri,
        label_size=settings.brother_label_size,
        cut=settings.brother_cut,
        show_price=settings.show_price_on_label,
        price_per_gram=settings.filament_price_per_gram,
    )
    result = await asyncio.to_thread(print_service.print_event, event)
    status = "printed" if result.ok else "failed"
    job_id = record_label_job_attempt(
        settings.db_path,
        event_id=event_id,
        status=status,
        attempts=1,
        error_message=result.error,
    )
    return {"ok": result.ok, "error": result.error, "label_job_id": job_id}
