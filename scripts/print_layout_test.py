import argparse

from printerprinter.config import get_settings
from printerprinter.labeling import render_label_image
from printerprinter.printing import create_print_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Render (and optionally print) a test label.")
    parser.add_argument("--backend", choices=["brother", "dymo"], help="Override PRINTER_BACKEND")
    parser.add_argument("--label-size", help="Override PRINTER_LABEL_SIZE (e.g. 30336, 30256, 62x100)")
    parser.add_argument("--output", help="Optional path to save rendered PNG preview")
    parser.add_argument("--preview-only", action="store_true", help="Render image without sending to printer")
    args = parser.parse_args()

    s = get_settings()
    overrides = {}
    if args.backend:
        overrides["printer_backend"] = args.backend
        if not args.label_size:
            overrides["label_size"] = "30336" if args.backend == "dymo" else "62x100"
    if args.label_size:
        overrides["label_size"] = args.label_size
    if overrides:
        s = s.model_copy(update=overrides)

    event = {
        "printer_name": "TEST-PRINTER",
        "printer_id": "test-id",
        "file_name": "Landscape large-text verification",
        "started_at": "2026-05-28T09:45:00Z",
        "eta_end_at": "2026-05-28T10:15:00Z",
        "est_duration_sec": 1800,
        "filament_estimated_g": 15.2,
    }

    img = render_label_image(
        event,
        s.label_size,
        show_price=s.show_price_on_label,
        price_per_gram=s.filament_price_per_gram,
    )
    print("image_size", img.size)
    if args.output:
        dpi = (300, 300) if s.printer_backend == "dymo" else None
        if dpi:
            img.save(args.output, format="PNG", dpi=dpi)
        else:
            img.save(args.output, format="PNG")
        print("saved_preview", args.output)

    if args.preview_only:
        return

    service = create_print_service(s)
    result = service.print_event(event)
    print(
        {
            "ok": result.ok,
            "error": result.error,
            "backend": s.printer_backend,
            "label_size": s.label_size,
        }
    )


if __name__ == "__main__":
    main()
