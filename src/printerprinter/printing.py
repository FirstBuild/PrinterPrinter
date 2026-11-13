from __future__ import annotations

import os
import re
import select
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from brother_ql.backends import backend_factory
from brother_ql.conversion import convert
from brother_ql.raster import BrotherQLRaster

from printerprinter.config import Settings
from printerprinter.labeling import DYMO_MEDIA_SPECS, DymoMediaSpec, render_label_image, resolve_dymo_media


DYMO_USB_VENDOR_ID = "0922"
DYMO_KNOWN_USB_PRODUCTS: dict[str, str] = {
    "0019": "DYMO LabelWriter 400",
    "001a": "DYMO LabelWriter 400 Turbo",
    "001b": "DYMO LabelWriter 400 Twin Turbo",
    "001c": "DYMO LabelWriter 400 Duo",
    "0020": "DYMO LabelWriter 450",
    "0021": "DYMO LabelWriter 450 Turbo",
    "0022": "DYMO LabelWriter 450 Twin Turbo",
    "0023": "DYMO LabelWriter 4XL",
    "0028": "DYMO LabelWriter Wireless",
}

_SAFE_QUEUE_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
_LPSTAT_DEVICE_RE = re.compile(r"^device for\s+([^\s:]+):\s+(\S+)", re.IGNORECASE)
_LSUSB_DYMO_RE = re.compile(r"ID\s+0922:([0-9a-fA-F]{4})\s*(.*)")

_DYMO_QUALITY_MAP: dict[str, str] = {
    "graphics": "Graphics",
    "text": "Text",
}
_DYMO_DENSITY_MAP: dict[str, str] = {
    "light": "Light",
    "medium": "Medium",
    "normal": "Normal",
    "dark": "Dark",
}


@dataclass
class PrintResult:
    ok: bool
    error: str | None


class PrintService(Protocol):
    def print_event(self, event: dict[str, object]) -> PrintResult:
        ...


def _read_sysfs_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def detect_dymo_usb_devices(sysfs_root: Path | None = None) -> list[dict[str, str]]:
    root = sysfs_root if sysfs_root is not None else Path("/sys/bus/usb/devices")
    devices: list[dict[str, str]] = []

    if root.exists():
        try:
            entries = sorted(root.iterdir(), key=lambda p: p.name)
        except OSError:
            entries = []

        for entry in entries:
            vendor = _read_sysfs_text(entry / "idVendor").lower()
            if vendor != DYMO_USB_VENDOR_ID:
                continue
            product_id = _read_sysfs_text(entry / "idProduct").lower()
            product_name = (
                _read_sysfs_text(entry / "product")
                or DYMO_KNOWN_USB_PRODUCTS.get(product_id, f"DYMO USB Device ({product_id or 'unknown'})")
            )
            manufacturer = _read_sysfs_text(entry / "manufacturer") or "DYMO"
            serial = _read_sysfs_text(entry / "serial")
            devices.append(
                {
                    "vendor_id": vendor,
                    "product_id": product_id,
                    "manufacturer": manufacturer,
                    "product": product_name,
                    "serial": serial,
                }
            )
        return devices

    lsusb_path = shutil.which("lsusb")
    if lsusb_path:
        try:
            proc = subprocess.run([lsusb_path], capture_output=True, text=True, check=False, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return devices
        for line in proc.stdout.splitlines():
            match = _LSUSB_DYMO_RE.search(line)
            if match:
                pid = match.group(1).lower()
                desc = match.group(2).strip() or DYMO_KNOWN_USB_PRODUCTS.get(pid, "DYMO USB Printer")
                devices.append(
                    {
                        "vendor_id": DYMO_USB_VENDOR_ID,
                        "product_id": pid,
                        "manufacturer": "DYMO",
                        "product": desc,
                        "serial": "",
                    }
                )

    return devices


def _find_dymo_usblp_devices(sysfs_usbmisc: Path | None = None) -> list[Path]:
    class_dirs = (
        [sysfs_usbmisc]
        if sysfs_usbmisc is not None
        else [Path("/sys/class/usbmisc"), Path("/sys/class/usb")]
    )
    matched: list[Path] = []

    for class_dir in class_dirs:
        if not class_dir.exists():
            continue
        try:
            entries = sorted(class_dir.glob("lp*"))
        except OSError:
            continue

        for entry in entries:
            try:
                dev_dir = (entry / "device").resolve()
            except OSError:
                continue

            is_dymo = False
            cursor = dev_dir
            for _ in range(5):
                if _read_sysfs_text(cursor / "idVendor").lower() == DYMO_USB_VENDOR_ID:
                    is_dymo = True
                    break
                if cursor.parent == cursor:
                    break
                cursor = cursor.parent

            if not is_dymo:
                continue

            dev_node = Path("/dev/usb") / entry.name
            if dev_node.exists() and dev_node not in matched:
                matched.append(dev_node)

    return matched


def parse_dymo_status_byte(status_byte: int) -> dict[str, object]:
    ready_bit = bool(status_byte & 0x01)
    top_of_form = bool(status_byte & 0x02)
    paper_out = bool(status_byte & 0x20)
    paper_jam = bool(status_byte & 0x40)
    printer_error = bool(status_byte & 0x80)
    ready = ready_bit and not (paper_out or paper_jam or printer_error)
    return {
        "raw_byte": status_byte,
        "ready": ready,
        "top_of_form": top_of_form,
        "paper_out": paper_out,
        "paper_jam": paper_jam,
        "printer_error": printer_error,
    }


def query_dymo_usb_hardware_status(
    device_path: Path | None = None,
    timeout_sec: float = 0.4,
) -> dict[str, object] | None:
    """Query Dymo LabelWriter ESC A status byte via usblp if accessible without blocking."""
    candidates = [device_path] if device_path is not None else _find_dymo_usblp_devices()
    for candidate in candidates:
        if candidate is None or not candidate.exists():
            continue
        fd: int | None = None
        try:
            fd = os.open(str(candidate), os.O_RDWR | os.O_NONBLOCK)
            os.write(fd, b"\x1bA")
            readable, _, _ = select.select([fd], [], [], max(0.05, timeout_sec))
            if not readable:
                continue
            data = os.read(fd, 8)
            if not data:
                continue
            parsed = parse_dymo_status_byte(data[0])
            parsed["device_path"] = str(candidate)
            return parsed
        except OSError:
            continue
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
    return None


def is_dymo_cups_driver_installed() -> bool:
    driver_paths = (
        Path("/usr/lib/cups/filter/raster2dymolw"),
        Path("/usr/local/lib/cups/filter/raster2dymolw"),
        Path("/Library/Printers/DYMO/CUPS/Filter/raster2dymolw"),
    )
    return any(p.exists() for p in driver_paths)


def discover_dymo_cups_queues() -> list[dict[str, object]]:
    lpstat_path = shutil.which("lpstat")
    if lpstat_path is None:
        return []

    try:
        proc = subprocess.run(
            [lpstat_path, "-v"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    queues: list[dict[str, object]] = []
    for line in proc.stdout.splitlines():
        match = _LPSTAT_DEVICE_RE.match(line.strip())
        if not match:
            continue
        queue_name, uri = match.group(1), match.group(2)
        haystack = f"{queue_name} {uri}".lower()
        if any(token in haystack for token in ("dymo", "labelwriter", "lw400", "lw450", "lw550")):
            queues.append(
                {
                    "queue": queue_name,
                    "uri": uri,
                    "is_usb": uri.lower().startswith("usb:"),
                }
            )
    return queues


def get_cups_queue_state(queue_name: str) -> dict[str, object]:
    if not queue_name or not _SAFE_QUEUE_NAME_RE.match(queue_name):
        return {
            "exists": False,
            "enabled": False,
            "out_of_paper": False,
            "queued_jobs": 0,
            "summary": "Invalid or empty queue name",
        }

    lpstat_path = shutil.which("lpstat")
    if lpstat_path is None:
        return {
            "exists": False,
            "enabled": False,
            "out_of_paper": False,
            "queued_jobs": 0,
            "summary": "CUPS lpstat command not found",
        }

    try:
        status_proc = subprocess.run(
            [lpstat_path, "-l", "-p", queue_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        jobs_proc = subprocess.run(
            [lpstat_path, "-o", queue_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return {
            "exists": False,
            "enabled": False,
            "out_of_paper": False,
            "queued_jobs": 0,
            "summary": "Failed to query CUPS status",
        }

    combined = (status_proc.stdout or status_proc.stderr or "").strip()
    if status_proc.returncode != 0:
        return {
            "exists": False,
            "enabled": False,
            "out_of_paper": False,
            "queued_jobs": 0,
            "summary": combined or f"Queue '{queue_name}' does not exist",
        }

    lower_out = combined.lower()
    enabled = "disabled" not in lower_out
    out_of_paper = "out-of-paper" in lower_out or "out of labels" in lower_out or "out of paper" in lower_out
    job_lines = [ln for ln in (jobs_proc.stdout or "").splitlines() if ln.strip()]
    first_line = combined.splitlines()[0].strip() if combined else f"printer {queue_name} ready"
    return {
        "exists": True,
        "enabled": enabled,
        "out_of_paper": out_of_paper,
        "queued_jobs": len(job_lines),
        "summary": first_line,
    }


class BrotherPrintService:
    def __init__(
        self,
        enabled: bool,
        model: str,
        printer_uri: str,
        label_size: str,
        cut: bool,
        show_price: bool,
        price_per_gram: float,
    ) -> None:
        self._enabled = enabled
        self._model = model
        self._printer_uri = printer_uri
        self._label_size = label_size
        self._cut = cut
        self._show_price = show_price
        self._price_per_gram = price_per_gram

    def print_event(self, event: dict[str, object]) -> PrintResult:
        if not self._enabled:
            return PrintResult(ok=False, error="Brother printing disabled by config")

        if not self._printer_uri.strip():
            return PrintResult(ok=False, error="BROTHER_PRINTER_URI is not configured")

        try:
            image = render_label_image(
                event,
                self._label_size,
                show_price=self._show_price,
                price_per_gram=self._price_per_gram,
            )
            qlr = BrotherQLRaster(self._model)

            instructions = convert(
                qlr,
                [image],
                self._label_size,
                rotate="auto",
                cut=self._cut,
                threshold=70,
                dither=False,
                compress=False,
                red=False,
                dpi_600=False,
                hq=True,
            )

            backend_class = backend_factory("network")["backend_class"]
            backend = backend_class(self._printer_uri)
            backend.write(instructions)
            backend.dispose()
            return PrintResult(ok=True, error=None)
        except Exception as exc:  # noqa: BLE001
            return PrintResult(ok=False, error=str(exc))


class DymoPrintService:
    def __init__(
        self,
        enabled: bool,
        model: str,
        interface: str,
        usb_queue_name: str,
        wifi_queue_name: str,
        label_size: str,
        show_price: bool,
        price_per_gram: float,
        print_quality: str = "Graphics",
        print_density: str = "Normal",
        job_expire_seconds: int = 300,
    ) -> None:
        self._enabled = enabled
        self._model = model.strip() or "LabelWriter-400-Turbo"
        self._interface = interface.strip().lower() or "usb"
        self._usb_queue_name = usb_queue_name.strip()
        self._wifi_queue_name = wifi_queue_name.strip()
        self._label_size = label_size.strip() or "30336"
        self._show_price = show_price
        self._price_per_gram = price_per_gram
        self._print_quality = _DYMO_QUALITY_MAP.get(print_quality.strip().lower(), "Graphics")
        self._print_density = _DYMO_DENSITY_MAP.get(print_density.strip().lower(), "Normal")
        self._job_expire_seconds = max(0, int(job_expire_seconds))

    def _validate_media(self) -> tuple[DymoMediaSpec | None, str | None]:
        if self._interface not in {"usb", "wifi", "auto"}:
            return None, f"Invalid PRINTER_INTERFACE '{self._interface}'; expected usb, wifi, or auto"

        spec = resolve_dymo_media(self._label_size)
        if spec is None:
            supported = ", ".join(DYMO_MEDIA_SPECS.keys())
            return (
                None,
                f"Unsupported Dymo label size '{self._label_size}'. "
                f"Expected a Dymo SKU ({supported}) or CUPS PageSize (e.g. w72h154.1).",
            )

        is_xl_model = "4xl" in self._model.lower() or "5xl" in self._model.lower()
        min_dim = min(spec.dots_printable)
        if not is_xl_model and min_dim > 700:
            return (
                None,
                f"Label size '{self._label_size}' exceeds the 62mm print head width of {self._model}.",
            )

        return spec, None

    def resolve_queue_name(self) -> tuple[str | None, bool, str | None]:
        """Return (queue_name, is_usb_target, error_message)."""
        for configured_name in (self._usb_queue_name, self._wifi_queue_name):
            if configured_name and not _SAFE_QUEUE_NAME_RE.match(configured_name):
                return None, False, f"Invalid characters in CUPS queue name '{configured_name}'"

        if self._interface == "usb":
            if self._usb_queue_name:
                return self._usb_queue_name, True, None
            discovered = discover_dymo_cups_queues()
            for item in discovered:
                if item["is_usb"]:
                    return str(item["queue"]), True, None
            if len(discovered) == 1:
                return str(discovered[0]["queue"]), bool(discovered[0]["is_usb"]), None
            return (
                None,
                True,
                "No Dymo USB CUPS queue configured or auto-discovered. "
                "Connect/power on the Dymo printer and run setup-dymo-cups (or set DYMO_USB_QUEUE_NAME).",
            )

        if self._interface == "wifi":
            if self._wifi_queue_name:
                return self._wifi_queue_name, False, None
            discovered = discover_dymo_cups_queues()
            for item in discovered:
                if not item["is_usb"]:
                    return str(item["queue"]), False, None
            return (
                None,
                False,
                "No Dymo WiFi/network CUPS queue configured. Set DYMO_WIFI_QUEUE_NAME.",
            )

        # auto mode: prefer USB when USB queue is configured or USB hardware is attached
        usb_attached = bool(detect_dymo_usb_devices())
        if usb_attached and self._usb_queue_name:
            return self._usb_queue_name, True, None
        if self._wifi_queue_name and not usb_attached:
            return self._wifi_queue_name, False, None
        if self._usb_queue_name:
            return self._usb_queue_name, True, None
        if self._wifi_queue_name:
            return self._wifi_queue_name, False, None

        discovered = discover_dymo_cups_queues()
        if discovered:
            first = discovered[0]
            return str(first["queue"]), bool(first["is_usb"]), None

        return (
            None,
            True,
            "No Dymo CUPS queue found. Connect the printer and run setup-dymo-cups, "
            "or set DYMO_USB_QUEUE_NAME / DYMO_WIFI_QUEUE_NAME.",
        )

    def print_event(self, event: dict[str, object]) -> PrintResult:
        if not self._enabled:
            return PrintResult(ok=False, error="Printing disabled by config")

        spec, media_error = self._validate_media()
        if spec is None or media_error is not None:
            return PrintResult(ok=False, error=media_error)

        lp_path = shutil.which("lp")
        if lp_path is None:
            return PrintResult(ok=False, error="CUPS 'lp' command not found on host")

        queue_name, is_usb_target, queue_error = self.resolve_queue_name()
        if queue_name is None or queue_error is not None:
            return PrintResult(ok=False, error=queue_error)

        if is_usb_target and Path("/sys/bus/usb/devices").exists():
            if not detect_dymo_usb_devices():
                return PrintResult(
                    ok=False,
                    error=(
                        "Dymo USB printer not detected on USB bus "
                        "(check 24V power adapter and USB cable connection)"
                    ),
                )

        queue_state = get_cups_queue_state(queue_name)
        if not queue_state["exists"]:
            return PrintResult(
                ok=False,
                error=f"CUPS queue '{queue_name}' not found ({queue_state['summary']})",
            )
        if not queue_state["enabled"]:
            return PrintResult(
                ok=False,
                error=f"CUPS queue '{queue_name}' is disabled ({queue_state['summary']})",
            )
        if queue_state["out_of_paper"]:
            return PrintResult(ok=False, error="Dymo printer reports out of paper in CUPS")

        if is_usb_target and int(queue_state.get("queued_jobs", 0)) == 0:
            hw_status = query_dymo_usb_hardware_status()
            if hw_status is not None:
                if hw_status.get("paper_out"):
                    return PrintResult(ok=False, error="Dymo printer is out of paper")
                if hw_status.get("paper_jam"):
                    return PrintResult(ok=False, error="Dymo printer reports a label jam")

        try:
            image = render_label_image(
                event,
                self._label_size,
                show_price=self._show_price,
                price_per_gram=self._price_per_gram,
            )

            with tempfile.TemporaryDirectory(prefix="printerprinter-dymo-") as tmpdir:
                tmp_image_path = Path(tmpdir) / "label.png"
                image.save(tmp_image_path, format="PNG", dpi=(300, 300))

                cmd = [
                    lp_path,
                    "-d",
                    queue_name,
                    "-o",
                    f"PageSize={spec.ppd_page_size}",
                    "-o",
                    "fit-to-page",
                    "-o",
                    f"DymoPrintQuality={self._print_quality}",
                    "-o",
                    f"DymoPrintDensity={self._print_density}",
                ]
                if self._job_expire_seconds > 0:
                    cmd.extend(["-o", f"job-cancel-after={self._job_expire_seconds}"])
                cmd.append(str(tmp_image_path))

                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=15,
                )
                if completed.returncode != 0:
                    detail = (completed.stderr or completed.stdout or "unknown CUPS error").strip()
                    return PrintResult(ok=False, error=f"CUPS print failed: {detail}")

            return PrintResult(ok=True, error=None)
        except subprocess.TimeoutExpired:
            return PrintResult(ok=False, error="CUPS 'lp' command timed out after 15s")
        except Exception as exc:  # noqa: BLE001
            return PrintResult(ok=False, error=str(exc))


def create_print_service(settings: Settings) -> PrintService:
    backend = settings.printer_backend.strip().lower()

    if backend == "dymo":
        return DymoPrintService(
            enabled=settings.printer_enabled,
            model=settings.dymo_model,
            interface=settings.printer_interface,
            usb_queue_name=settings.dymo_usb_queue_name,
            wifi_queue_name=settings.dymo_wifi_queue_name,
            label_size=settings.label_size,
            show_price=settings.show_price_on_label,
            price_per_gram=settings.filament_price_per_gram,
            print_quality=settings.dymo_print_quality,
            print_density=settings.dymo_print_density,
            job_expire_seconds=settings.dymo_job_expire_seconds,
        )

    if backend == "brother":
        return BrotherPrintService(
            enabled=settings.printer_enabled,
            model=settings.brother_model,
            printer_uri=settings.brother_printer_uri,
            label_size=settings.label_size,
            cut=settings.brother_cut,
            show_price=settings.show_price_on_label,
            price_per_gram=settings.filament_price_per_gram,
        )

    raise ValueError(f"Unsupported PRINTER_BACKEND '{settings.printer_backend}'; expected brother or dymo")


def probe_printer_status(settings: Settings) -> dict[str, object]:
    backend = settings.printer_backend.strip().lower()
    base: dict[str, object] = {
        "backend": backend,
        "enabled": settings.printer_enabled,
        "label_size": settings.label_size,
    }

    if backend == "brother":
        uri_ok = bool(settings.brother_printer_uri.strip())
        base.update(
            {
                "ok": settings.printer_enabled and uri_ok,
                "model": settings.brother_model,
                "printer_uri": settings.brother_printer_uri,
                "detail": (
                    f"Brother {settings.brother_model} configured at {settings.brother_printer_uri}"
                    if uri_ok
                    else "BROTHER_PRINTER_URI is empty"
                ),
            }
        )
        return base

    if backend != "dymo":
        base.update({"ok": False, "detail": f"Unsupported backend '{backend}'"})
        return base

    media_spec = resolve_dymo_media(settings.label_size)
    usb_devices = detect_dymo_usb_devices()
    driver_installed = is_dymo_cups_driver_installed()
    discovered_queues = discover_dymo_cups_queues()

    dymo_service = DymoPrintService(
        enabled=settings.printer_enabled,
        model=settings.dymo_model,
        interface=settings.printer_interface,
        usb_queue_name=settings.dymo_usb_queue_name,
        wifi_queue_name=settings.dymo_wifi_queue_name,
        label_size=settings.label_size,
        show_price=settings.show_price_on_label,
        price_per_gram=settings.filament_price_per_gram,
        print_quality=settings.dymo_print_quality,
        print_density=settings.dymo_print_density,
        job_expire_seconds=settings.dymo_job_expire_seconds,
    )
    resolved_queue, is_usb_target, queue_err = dymo_service.resolve_queue_name()
    queue_state = get_cups_queue_state(resolved_queue) if resolved_queue else None
    hw_status = (
        query_dymo_usb_hardware_status()
        if is_usb_target and usb_devices and (queue_state is None or int(queue_state.get("queued_jobs", 0)) == 0)
        else None
    )

    issues: list[str] = []
    if not settings.printer_enabled:
        issues.append("Printing disabled (PRINTER_ENABLED=false)")
    if media_spec is None:
        issues.append(f"Unsupported Dymo label size '{settings.label_size}'")
    if not driver_installed:
        issues.append("printer-driver-dymo is not installed")
    if is_usb_target and Path("/sys/bus/usb/devices").exists() and not usb_devices:
        issues.append("No Dymo USB device detected (check 24V power brick & USB cable)")
    if queue_err:
        issues.append(queue_err)
    elif queue_state and not queue_state["exists"]:
        issues.append(f"CUPS queue '{resolved_queue}' does not exist")
    elif queue_state and not queue_state["enabled"]:
        issues.append(f"CUPS queue '{resolved_queue}' is disabled")

    paper_out = bool((queue_state and queue_state.get("out_of_paper")) or (hw_status and hw_status.get("paper_out")))
    if paper_out:
        issues.append("Printer is out of paper")
    if hw_status and hw_status.get("paper_jam"):
        issues.append("Printer reports label jam")

    ok = len(issues) == 0
    detail = (
        f"Ready on CUPS queue '{resolved_queue}' ({media_spec.description if media_spec else settings.label_size})"
        if ok
        else "; ".join(issues)
    )

    base.update(
        {
            "ok": ok,
            "model": settings.dymo_model,
            "interface": settings.printer_interface,
            "ppd_page_size": media_spec.ppd_page_size if media_spec else None,
            "media_description": media_spec.description if media_spec else None,
            "dots_printable": list(media_spec.dots_printable) if media_spec else None,
            "driver_installed": driver_installed,
            "usb_devices": usb_devices,
            "discovered_queues": discovered_queues,
            "resolved_queue": resolved_queue,
            "queue_state": queue_state,
            "hardware_status": hw_status,
            "paper_out": paper_out,
            "detail": detail,
        }
    )
    return base


def _select_dymo_ppd_uri(model: str, usb_product_name: str) -> str:
    lpinfo_path = shutil.which("lpinfo")
    candidates: list[tuple[str, str]] = []
    if lpinfo_path:
        try:
            proc = subprocess.run([lpinfo_path, "-m"], capture_output=True, text=True, check=False, timeout=10)
            for line in proc.stdout.splitlines():
                if "dymo" not in line.lower():
                    continue
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    candidates.append((parts[0], parts[1]))
        except (OSError, subprocess.SubprocessError):
            pass

    target = f"{usb_product_name} {model}".lower()
    if "400" in target and "turbo" in target and "twin" not in target:
        preferred_ppd = "lw400t.ppd"
    elif "400" in target and "twin" in target:
        preferred_ppd = "lw400tt.ppd"
    elif "400" in target:
        preferred_ppd = "lw400.ppd"
    elif "450" in target and "twin" in target:
        preferred_ppd = "lw450tt.ppd"
    elif "450" in target and "turbo" in target:
        preferred_ppd = "lw450t.ppd"
    elif "450" in target:
        preferred_ppd = "lw450.ppd"
    elif "4xl" in target:
        preferred_ppd = "lw4xl.ppd"
    else:
        preferred_ppd = "lw400t.ppd"

    for uri, _ in candidates:
        if uri.lower().endswith(f"/{preferred_ppd}"):
            return uri

    return f"dymo:0/cups/model/{preferred_ppd}"


def setup_dymo_usb_cups_queue(
    *,
    preferred_queue_name: str = "",
    model: str = "LabelWriter-400-Turbo",
    label_size: str = "30336",
) -> dict[str, object]:
    """Install printer-driver-dymo if needed (on Debian/RPi root) and register the USB CUPS queue."""
    steps: list[str] = []
    queue_name = preferred_queue_name.strip() or "DYMO_LabelWriter_400_Turbo"
    if not _SAFE_QUEUE_NAME_RE.match(queue_name):
        raise ValueError(f"Invalid queue name '{queue_name}'")

    if not is_dymo_cups_driver_installed():
        apt_get = shutil.which("apt-get")
        if apt_get and hasattr(os, "geteuid") and os.geteuid() == 0:
            env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
            subprocess.run([apt_get, "update"], capture_output=True, text=True, check=False, timeout=120, env=env)
            install_proc = subprocess.run(
                [apt_get, "install", "-y", "cups", "printer-driver-dymo"],
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
                env=env,
            )
            if install_proc.returncode != 0 or not is_dymo_cups_driver_installed():
                detail = (install_proc.stderr or install_proc.stdout or "apt-get install failed").strip()
                raise RuntimeError(f"Failed to install printer-driver-dymo: {detail}")
            steps.append("installed_printer_driver_dymo")
        else:
            raise RuntimeError(
                "printer-driver-dymo is not installed. Run: sudo apt-get update && sudo apt-get install -y cups printer-driver-dymo"
            )

    lpinfo_path = shutil.which("lpinfo")
    lpadmin_path = shutil.which("lpadmin")
    if not lpinfo_path or not lpadmin_path:
        raise RuntimeError("CUPS admin utilities (lpinfo/lpadmin) not found. Ensure 'cups' is installed.")

    usb_devices = detect_dymo_usb_devices()
    lpinfo_proc = subprocess.run([lpinfo_path, "-v"], capture_output=True, text=True, check=False, timeout=10)
    device_uri = ""
    for line in lpinfo_proc.stdout.splitlines():
        for token in line.strip().split():
            if token.lower().startswith("usb://") and ("dymo" in token.lower() or "labelwriter" in token.lower()):
                device_uri = token
                break
        if device_uri:
            break

    if not device_uri:
        if not usb_devices:
            raise RuntimeError(
                "No Dymo USB printer detected on USB bus. Verify the Dymo 24V power adapter is plugged in "
                "(front LED lit/flashing) and the USB cable is firmly seated underneath the printer."
            )
        raise RuntimeError(
            f"Dymo USB device ({usb_devices[0].get('product')}) seen on USB bus, "
            "but CUPS lpinfo -v did not report a usb://DYMO URI (check permissions / CUPS daemon)."
        )
    steps.append("detected_usb_uri")

    usb_product = usb_devices[0].get("product", "") if usb_devices else ""
    ppd_uri = _select_dymo_ppd_uri(model, usb_product)
    spec = resolve_dymo_media(label_size) or DYMO_MEDIA_SPECS["30336"]

    admin_cmd = [
        lpadmin_path,
        "-p",
        queue_name,
        "-E",
        "-v",
        device_uri,
        "-m",
        ppd_uri,
        "-o",
        f"PageSize={spec.ppd_page_size}",
        "-o",
        "DymoPrintQuality=Graphics",
        "-o",
        "printer-is-shared=false",
        "-o",
        "printer-error-policy=abort-job",
    ]
    admin_proc = subprocess.run(admin_cmd, capture_output=True, text=True, check=False, timeout=20)
    if admin_proc.returncode != 0:
        detail = (admin_proc.stderr or admin_proc.stdout or "lpadmin failed").strip()
        raise RuntimeError(f"lpadmin failed: {detail}")
    steps.append("configured_cups_queue")

    for enable_bin in ("cupsenable", "cupsaccept"):
        bin_path = shutil.which(enable_bin)
        if bin_path:
            subprocess.run([bin_path, queue_name], capture_output=True, text=True, check=False, timeout=10)

    return {
        "ok": True,
        "queue_name": queue_name,
        "device_uri": device_uri,
        "ppd_uri": ppd_uri,
        "page_size": spec.ppd_page_size,
        "steps": steps,
        "detail": f"Configured CUPS queue '{queue_name}' -> {device_uri} ({ppd_uri})",
    }
