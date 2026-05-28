from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx


@dataclass
class ProbeResult:
    ok: bool
    status_code: int | None
    error: str | None


@dataclass
class BambuddyPrintJob:
    source_event_id: str
    printer_id: str
    printer_name: str | None
    file_name: str | None
    started_at: str | None
    eta_end_at: str | None
    est_duration_sec: int | None
    filament_estimated_g: float | None


@dataclass
class BambuddyPrinter:
    printer_id: str
    name: str | None
    serial_number: str | None
    ip_address: str | None


def _to_iso8601(value: str | int | float | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC).isoformat()
    text = str(value).strip()
    if not text:
        return None
    # Keep incoming ISO-like strings unchanged.
    return text


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class BambuddyClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout_seconds: float,
        auth_mode: str = "bearer",
        auth_header_name: str = "X-API-Key",
        jobs_endpoint: str = "/api/v1/print-log/",
        printers_endpoint: str = "/api/v1/printers/",
        printer_status_endpoint_template: str = "/api/v1/printers/{printer_id}/status",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._timeout_seconds = timeout_seconds
        self._auth_mode = auth_mode.lower().strip()
        self._auth_header_name = auth_header_name
        self._jobs_endpoint = jobs_endpoint
        self._printers_endpoint = printers_endpoint
        self._printer_status_endpoint_template = printer_status_endpoint_template

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._auth_mode == "api_key_header":
            headers[self._auth_header_name] = self._api_token
        elif self._auth_mode == "none":
            return headers
        else:
            headers["Authorization"] = f"Bearer {self._api_token}"
        return headers

    async def probe(self) -> ProbeResult:
        # We intentionally probe the root endpoint because concrete Bambuddy API paths
        # will be finalized in the next milestone after endpoint discovery.
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(f"{self._base_url}/", headers=headers)
            return ProbeResult(ok=response.status_code < 500, status_code=response.status_code, error=None)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(ok=False, status_code=None, error=str(exc))

    def _parse_jobs(self, data: object) -> list[BambuddyPrintJob]:
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ("items", "prints", "jobs", "data", "results"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
            else:
                items = []
        else:
            items = []

        jobs: list[BambuddyPrintJob] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            source_event_id = str(
                item.get("id")
                or item.get("job_id")
                or item.get("print_id")
                or item.get("uuid")
                or ""
            ).strip()
            if not source_event_id:
                continue

            printer_id = str(item.get("printer_id") or item.get("device_id") or item.get("serial") or "unknown").strip()
            printer_name = item.get("printer_name") or item.get("device_name")
            # Bambuddy PrintLogEntrySchema uses "print_name"; keep legacy fallbacks for other sources
            file_name = (
                item.get("print_name")
                or item.get("filename")
                or item.get("file_name")
                or item.get("job_name")
            )
            started_at = _to_iso8601(item.get("started_at") or item.get("start_time") or item.get("created_at"))
            remaining_sec = _to_int(item.get("remaining_seconds") or item.get("eta_seconds") or item.get("time_left"))
            # Prefer explicit duration; compute from timestamps if available; never fall back to remaining_sec alone
            raw_duration = _to_int(item.get("duration_seconds") or item.get("estimated_duration"))
            if raw_duration is None:
                completed_at_raw = item.get("completed_at")
                if completed_at_raw and started_at:
                    try:
                        dt_start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
                        dt_end = datetime.fromisoformat(str(completed_at_raw).replace("Z", "+00:00"))
                        computed = int((dt_end - dt_start).total_seconds())
                        raw_duration = computed if computed > 0 else None
                    except ValueError:
                        pass
            est_duration_sec = raw_duration
            # Bambuddy PrintLogEntrySchema uses "filament_used_grams"; keep legacy fallbacks for other sources
            filament_estimated_g = _to_float(
                item.get("filament_used_grams")
                or item.get("filament_grams")
                or item.get("filament_estimated_g")
            )

            eta_end_at: str | None = _to_iso8601(
                item.get("completed_at")
                or item.get("eta_end_at")
                or item.get("estimated_end_time")
            )
            if eta_end_at is None and started_at is not None and remaining_sec is not None:
                try:
                    dt_start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    eta_end_at = (dt_start + timedelta(seconds=remaining_sec)).astimezone(UTC).isoformat()
                except ValueError:
                    eta_end_at = None

            jobs.append(
                BambuddyPrintJob(
                    source_event_id=source_event_id,
                    printer_id=printer_id,
                    printer_name=str(printer_name) if printer_name is not None else None,
                    file_name=str(file_name) if file_name is not None else None,
                    started_at=started_at,
                    eta_end_at=eta_end_at,
                    est_duration_sec=est_duration_sec,
                    filament_estimated_g=filament_estimated_g,
                )
            )
        return jobs

    async def list_print_jobs(self) -> list[BambuddyPrintJob]:
        headers = self._headers()
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.get(f"{self._base_url}{self._jobs_endpoint}", headers=headers)
            response.raise_for_status()
        return self._parse_jobs(response.json())

    async def list_running_jobs(self) -> list[BambuddyPrintJob]:
        jobs = await self.list_print_jobs()
        return [job for job in jobs if job.source_event_id]

    async def list_printers(self) -> list[BambuddyPrinter]:
        headers = self._headers()
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.get(f"{self._base_url}{self._printers_endpoint}", headers=headers)
            response.raise_for_status()

        data = response.json()
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items") if isinstance(data.get("items"), list) else []
        else:
            items = []

        printers: list[BambuddyPrinter] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id") or item.get("printer_id")
            if raw_id is None:
                continue
            printers.append(
                BambuddyPrinter(
                    printer_id=str(raw_id),
                    name=str(item.get("name")) if item.get("name") is not None else None,
                    serial_number=(
                        str(item.get("serial_number")) if item.get("serial_number") is not None else None
                    ),
                    ip_address=str(item.get("ip_address")) if item.get("ip_address") is not None else None,
                )
            )
        return printers

    async def get_printer_status(self, printer_id: str) -> dict[str, Any]:
        headers = self._headers()
        endpoint = self._printer_status_endpoint_template.format(printer_id=printer_id)
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.get(f"{self._base_url}{endpoint}", headers=headers)
            response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data
        return {}
