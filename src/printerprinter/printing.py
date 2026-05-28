from __future__ import annotations

from dataclasses import dataclass

from brother_ql.backends import backend_factory
from brother_ql.conversion import convert
from brother_ql.raster import BrotherQLRaster

from printerprinter.labeling import render_label_image


@dataclass
class PrintResult:
    ok: bool
    error: str | None


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
