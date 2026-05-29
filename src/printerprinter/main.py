from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException

from printerprinter.bambuddy_client import BambuddyClient
from printerprinter.config import get_settings
from printerprinter.logging_config import configure_logging
from printerprinter.printing import BrotherPrintService
from printerprinter.storage import (
    get_print_start_event,
    init_db,
    list_recent_print_start_events,
    record_label_job_attempt,
    update_print_start_event,
    upsert_print_start_event,
)


LOGGER = logging.getLogger(__name__)


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
    return False


def _normalize_name(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    # Normalize common filename delimiters to improve matching across API sources.
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
        if normalized_file_name and job_file_name and job_file_name != normalized_file_name:
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


def _job_matches_event(job, event: dict[str, object]) -> bool:
    job_printer_id = _normalize_name(getattr(job, "printer_id", None))
    event_printer_id = _normalize_name(event.get("printer_id"))
    if job_printer_id != event_printer_id:
        return False

    event_file_name = _normalize_name(event.get("file_name"))
    job_file_name = _normalize_name(getattr(job, "file_name", None))
    if event_file_name:
        return event_file_name == job_file_name

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
            start_dt = _parse_datetime(new_started_at)
            if start_dt is not None and normalized_duration is not None and normalized_duration > 0:
                new_eta_end_at = (start_dt + timedelta(seconds=normalized_duration)).isoformat()

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
) -> dict[str, int]:
    printers = await client.list_printers()
    allowed_ids = _resolve_allowed_printer_ids(printers, monitored_ids, monitored_identifiers)
    seen = 0
    inserted = 0

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
            print_result = await asyncio.to_thread(print_service.print_event, result["event"])
            status = "printed" if print_result.ok else "failed"
            record_label_job_attempt(
                db_path,
                event_id=int(result["event"]["id"]),
                status=status,
                attempts=1,
                error_message=print_result.error,
            )

    return {"seen": seen, "inserted": inserted}


async def poller_loop(
    client: BambuddyClient,
    db_path: str,
    interval_seconds: float,
    monitored_ids: set[str],
    monitored_identifiers: set[str],
    last_states: dict[str, str],
    print_service: BrotherPrintService,
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
            )
            reconciled = await reconcile_recent_events(client, db_path)
            LOGGER.info("poll iteration complete: seen=%s inserted=%s", outcome["seen"], outcome["inserted"])
            if reconciled:
                LOGGER.info("event reconciliation complete: updated=%s", reconciled)
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
