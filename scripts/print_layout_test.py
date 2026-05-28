from printerprinter.config import get_settings
from printerprinter.labeling import render_label_image
from printerprinter.printing import BrotherPrintService


def main() -> None:
    s = get_settings()
    event = {
        "printer_name": "TEST-PRINTER",
        "printer_id": "test-id",
        "file_name": "Landscape large-text verification",
        "started_at": "2026-05-28T09:45:00Z",
        "eta_end_at": "2026-05-28T10:15:00Z",
        "est_duration_sec": 1800,
        "filament_estimated_g": 15.2,
    }

    img = render_label_image(event, s.brother_label_size)
    print("image_size", img.size)

    service = BrotherPrintService(
        enabled=True,
        model=s.brother_model,
        printer_uri=s.brother_printer_uri,
        label_size=s.brother_label_size,
        cut=s.brother_cut,
        show_price=s.show_price_on_label,
        price_per_gram=s.filament_price_per_gram,
    )
    result = service.print_event(event)
    print({"ok": result.ok, "error": result.error, "label_size": s.brother_label_size})


if __name__ == "__main__":
    main()
