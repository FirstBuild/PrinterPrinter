from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from printerprinter.admin_ui import render_admin_ui_html
from printerprinter.config import Settings, get_settings
from printerprinter.labeling import render_label_image, resolve_dymo_media
from printerprinter.main import app
from printerprinter.printing import (
    BrotherPrintService,
    DymoPrintService,
    _default_dymo_queue_name,
    _select_dymo_ppd_uri,
    create_print_service,
    detect_dymo_usb_devices,
    parse_dymo_status_byte,
    probe_printer_status,
)
from printerprinter.storage import init_db, upsert_print_start_event


SAMPLE_EVENT: dict[str, object] = {
    "id": 1,
    "printer_name": "Bam Bam",
    "printer_id": "11",
    "file_name": "dragon-scale-planter-v4.3mf",
    "started_at": "2026-05-28T14:20:00Z",
    "eta_end_at": "2026-05-29T16:50:00Z",
    "est_duration_sec": 95400,
    "filament_estimated_g": 42.1,
}


class DymoLabelingAndMediaTests(unittest.TestCase):
    def test_resolve_dymo_media_skus_and_ppd_codes(self) -> None:
        spec_30336 = resolve_dymo_media("30336")
        self.assertIsNotNone(spec_30336)
        assert spec_30336 is not None
        self.assertEqual(spec_30336.ppd_page_size, "w72h154.1")
        self.assertEqual(spec_30336.dots_printable, (271, 593))

        spec_30256 = resolve_dymo_media("30256")
        assert spec_30256 is not None
        self.assertEqual(spec_30256.ppd_page_size, "w167h288")
        self.assertEqual(spec_30256.dots_printable, (665, 1112))

        by_ppd = resolve_dymo_media("w79h252")
        assert by_ppd is not None
        self.assertEqual(by_ppd.code, "30252")

        custom_ppd = resolve_dymo_media("w80h144")
        assert custom_ppd is not None
        self.assertEqual(custom_ppd.ppd_page_size, "w80h144")

        self.assertIsNone(resolve_dymo_media("62x100"))

    def test_render_compact_and_full_labels(self) -> None:
        img_30336 = render_label_image(SAMPLE_EVENT, "30336", show_price=True, price_per_gram=0.10)
        self.assertEqual(img_30336.size, (271, 593))

        img_30252 = render_label_image(SAMPLE_EVENT, "30252", show_price=True, price_per_gram=0.10)
        self.assertEqual(img_30252.size, (299, 963))

        img_30334 = render_label_image(SAMPLE_EVENT, "30334", show_price=True, price_per_gram=0.10)
        self.assertEqual(img_30334.size, (651, 339))

        img_30256 = render_label_image(SAMPLE_EVENT, "30256", show_price=True, price_per_gram=0.10)
        self.assertEqual(img_30256.size, (665, 1112))

        img_brother = render_label_image(SAMPLE_EVENT, "62x100", show_price=True, price_per_gram=0.10)
        self.assertEqual(img_brother.size, (696, 1109))


class SettingsTests(unittest.TestCase):
    def test_legacy_brother_env_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "BAMBUDDY_BASE_URL=http://bambuddy.local:8000",
                        "BAMBUDDY_API_TOKEN=secret",
                        "BROTHER_ENABLED=false",
                        "BROTHER_LABEL_SIZE=62x29",
                        "EXTRA_FUTURE_KEY=ignored",
                    ]
                ),
                encoding="utf-8",
            )
            s = Settings(_env_file=str(env_file))
            self.assertEqual(s.printer_backend, "brother")
            self.assertFalse(s.printer_enabled)
            self.assertFalse(s.brother_enabled)
            self.assertEqual(s.label_size, "62x29")
            self.assertEqual(s.brother_label_size, "62x29")

    def test_dymo_default_label_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "BAMBUDDY_BASE_URL=http://bambuddy.local:8000",
                        "BAMBUDDY_API_TOKEN=secret",
                        "PRINTER_BACKEND=dymo",
                    ]
                ),
                encoding="utf-8",
            )
            s = Settings(_env_file=str(env_file))
            self.assertEqual(s.printer_backend, "dymo")
            self.assertEqual(s.printer_interface, "usb")
            self.assertEqual(s.label_size, "30336")
            self.assertIsInstance(create_print_service(s), DymoPrintService)


class DymoPrintServiceTests(unittest.TestCase):
    def test_status_byte_parsing(self) -> None:
        ready = parse_dymo_status_byte(0x03)
        self.assertTrue(ready["ready"])
        self.assertTrue(ready["top_of_form"])
        self.assertFalse(ready["paper_out"])

        out_of_paper = parse_dymo_status_byte(0xA1)
        self.assertFalse(out_of_paper["ready"])
        self.assertTrue(out_of_paper["paper_out"])

    def test_sysfs_usb_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hub = root / "1-0"
            hub.mkdir()
            (hub / "idVendor").write_text("1d6b\n", encoding="utf-8")
            (hub / "idProduct").write_text("0002\n", encoding="utf-8")

            dymo = root / "1-1"
            dymo.mkdir()
            (dymo / "idVendor").write_text("0922\n", encoding="utf-8")
            (dymo / "idProduct").write_text("001a\n", encoding="utf-8")
            (dymo / "product").write_text("LabelWriter 400 Turbo\n", encoding="utf-8")
            (dymo / "serial").write_text("070111\n", encoding="utf-8")

            devices = detect_dymo_usb_devices(sysfs_root=root)
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["product_id"], "001a")
            self.assertEqual(devices[0]["product"], "LabelWriter 400 Turbo")

    @patch("printerprinter.printing.shutil.which", return_value=None)
    def test_ppd_selection_prefers_live_usb_model_over_fallback(self, _mock_which: MagicMock) -> None:
        ppd_450t = _select_dymo_ppd_uri("LabelWriter-400-Turbo", "DYMO LabelWriter 450  Turbo")
        self.assertEqual(ppd_450t, "dymo:0/cups/model/lw450t.ppd")
        self.assertEqual(
            _default_dymo_queue_name("DYMO LabelWriter 450  Turbo", "LabelWriter-400-Turbo"),
            "DYMO_LabelWriter_450_Turbo",
        )

        ppd_400t = _select_dymo_ppd_uri("LabelWriter-450-Turbo", "LabelWriter 400 Turbo")
        self.assertEqual(ppd_400t, "dymo:0/cups/model/lw400t.ppd")

    @patch("printerprinter.printing.query_dymo_usb_hardware_status", return_value={"paper_out": False, "paper_jam": False, "ready": True})
    @patch(
        "printerprinter.printing.get_cups_queue_state",
        return_value={"exists": True, "enabled": True, "out_of_paper": False, "queued_jobs": 0, "summary": "idle"},
    )
    @patch("printerprinter.printing.detect_dymo_usb_devices", return_value=[{"vendor_id": "0922", "product_id": "001a"}])
    @patch("printerprinter.printing.discover_dymo_cups_queues", return_value=[{"queue": "DYMO_LW400T", "uri": "usb://DYMO/LabelWriter%20400%20Turbo", "is_usb": True}])
    @patch("printerprinter.printing.shutil.which", return_value="/usr/bin/lp")
    def test_print_event_auto_discovers_usb_queue_and_passes_ppd_options(
        self,
        _mock_which: MagicMock,
        _mock_discover: MagicMock,
        _mock_usb: MagicMock,
        _mock_state: MagicMock,
        _mock_hw: MagicMock,
    ) -> None:
        captured_cmd: list[str] = []
        captured_dpi: tuple[float, float] | None = None

        def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal captured_cmd, captured_dpi
            captured_cmd = list(cmd)
            with Image.open(cmd[-1]) as saved_img:
                captured_dpi = saved_img.info.get("dpi")
            return subprocess.CompletedProcess(cmd, 0, stdout="request id is DYMO_LW400T-1\n", stderr="")

        service = DymoPrintService(
            enabled=True,
            model="LabelWriter-400-Turbo",
            interface="usb",
            usb_queue_name="",
            wifi_queue_name="",
            label_size="30336",
            show_price=True,
            price_per_gram=0.10,
            print_quality="Graphics",
            print_density="Normal",
            job_expire_seconds=300,
        )
        with patch("printerprinter.printing.subprocess.run", side_effect=fake_run):
            res = service.print_event(SAMPLE_EVENT)

        self.assertTrue(res.ok, res.error)
        self.assertIn("DYMO_LW400T", captured_cmd)
        self.assertIn("PageSize=w72h154.1", captured_cmd)
        self.assertIn("fit-to-page", captured_cmd)
        self.assertIn("DymoPrintQuality=Graphics", captured_cmd)
        self.assertIn("DymoPrintDensity=Normal", captured_cmd)
        self.assertIn("job-cancel-after=300", captured_cmd)
        self.assertIsNotNone(captured_dpi)
        assert captured_dpi is not None
        self.assertAlmostEqual(captured_dpi[0], 300, delta=1)
        self.assertAlmostEqual(captured_dpi[1], 300, delta=1)

    @patch("printerprinter.printing.query_dymo_usb_hardware_status", return_value={"paper_out": True, "paper_jam": False, "ready": False})
    @patch(
        "printerprinter.printing.get_cups_queue_state",
        return_value={"exists": True, "enabled": True, "out_of_paper": False, "queued_jobs": 0, "summary": "idle"},
    )
    @patch("printerprinter.printing.detect_dymo_usb_devices", return_value=[{"vendor_id": "0922", "product_id": "001a"}])
    @patch("printerprinter.printing.shutil.which", return_value="/usr/bin/lp")
    def test_print_event_fails_cleanly_when_out_of_paper(
        self,
        _mock_which: MagicMock,
        _mock_usb: MagicMock,
        _mock_state: MagicMock,
        _mock_hw: MagicMock,
    ) -> None:
        service = DymoPrintService(
            enabled=True,
            model="LabelWriter-400-Turbo",
            interface="usb",
            usb_queue_name="DYMO_LW400T",
            wifi_queue_name="",
            label_size="30336",
            show_price=True,
            price_per_gram=0.10,
        )
        res = service.print_event(SAMPLE_EVENT)
        self.assertFalse(res.ok)
        self.assertIn("out of paper", (res.error or "").lower())

    def test_rejects_oversized_4xl_media_on_400_turbo(self) -> None:
        service = DymoPrintService(
            enabled=True,
            model="LabelWriter-400-Turbo",
            interface="usb",
            usb_queue_name="DYMO_LW400T",
            wifi_queue_name="",
            label_size="1744907",
            show_price=True,
            price_per_gram=0.10,
        )
        res = service.print_event(SAMPLE_EVENT)
        self.assertFalse(res.ok)
        self.assertIn("exceeds", (res.error or "").lower())


class AdminApiAndUiTests(unittest.TestCase):
    def test_admin_endpoints_and_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.sqlite3"
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "BAMBUDDY_BASE_URL=http://bambuddy.local:8000",
                        "BAMBUDDY_API_TOKEN=testtoken",
                        f"PRINTERPRINTER_DB_PATH={db_path}",
                        f"PRINTERPRINTER_ENV_FILE_PATH={env_path}",
                        "PRINTER_BACKEND=dymo",
                        "PRINTER_INTERFACE=usb",
                        "PRINTER_LABEL_SIZE=30336",
                    ]
                ),
                encoding="utf-8",
            )
            init_db(str(db_path))
            ins = upsert_print_start_event(
                str(db_path),
                source="bambuddy",
                source_event_id="11:test:1",
                printer_id="11",
                printer_name="Bam Bam",
                file_name="benchy.3mf",
                started_at="2026-11-13T18:00:00Z",
                eta_end_at="2026-11-13T19:00:00Z",
                est_duration_sec=3600,
                filament_estimated_g=12.4,
            )
            event_id = int(ins["event"]["id"])

            test_settings = Settings(_env_file=str(env_path))
            with patch("printerprinter.main.get_settings", return_value=test_settings):
                client = TestClient(app, raise_server_exceptions=True)

                r_health = client.get("/health")
                self.assertEqual(r_health.status_code, 200)

                r_probe = client.get("/probes/printer")
                self.assertEqual(r_probe.status_code, 200)
                self.assertEqual(r_probe.json()["backend"], "dymo")
                self.assertEqual(r_probe.json()["ppd_page_size"], "w72h154.1")

                r_cfg = client.get("/admin/config")
                self.assertEqual(r_cfg.status_code, 200)
                self.assertEqual(r_cfg.json()["values"]["PRINTER_BACKEND"], "dymo")

                r_save = client.post(
                    "/admin/config",
                    json={"values": {"DYMO_USB_QUEUE_NAME": "", "BROTHER_PRINTER_URI": ""}},
                )
                self.assertEqual(r_save.status_code, 200)

                r_prev = client.get(f"/admin/label-preview/{event_id}.png?label_size=30336")
                self.assertEqual(r_prev.status_code, 200)
                self.assertEqual(r_prev.headers["content-type"], "image/png")

                r_ui = client.get("/admin")
                self.assertEqual(r_ui.status_code, 200)
                self.assertIn("Setup Dymo USB", r_ui.text)

    def test_admin_ui_html_has_no_broken_template_interpolations(self) -> None:
        html = render_admin_ui_html()
        self.assertNotIn("event.started_at})", html)
        self.assertNotIn("escapeHTML(fmt(event.filament_estimated_g)}", html)
        self.assertIn('id="config-form"', html)
        self.assertIn('name="PRINTER_BACKEND"', html)


if __name__ == "__main__":
    unittest.main()

