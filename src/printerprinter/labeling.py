from __future__ import annotations

from datetime import datetime

from brother_ql.devicedependent import label_type_specs
from PIL import Image, ImageDraw, ImageFont


def _safe_text(value: object | None) -> str:
    if value is None:
        return "Unknown"
    text = str(value).strip()
    return text if text else "Unknown"


def _format_duration(value: object | None) -> str:
    try:
        total_seconds = int(float(value))
    except (TypeError, ValueError):
        return "Unknown"

    if total_seconds <= 0:
        return "0m"

    days = total_seconds // 86400
    remaining = total_seconds % 86400
    hours = remaining // 3600
    minutes = (remaining % 3600) // 60

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")

    # For very short durations (< 60s), keep output predictable.
    if not parts:
        parts.append("0m")
    return " ".join(parts)


def _format_datetime(value: object | None) -> str:
    if value is None:
        return "Unknown"

    text = str(value).strip()
    if not text:
        return "Unknown"

    candidate = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return text

    # Use a compact friendly format that still includes month/day and time.
    # Example: Wed May 28, 10:05 AM
    return dt.strftime("%a %b %d, %I:%M %p")


def _format_filament_grams(value: object | None) -> str:
    try:
        grams = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    rounded = int(round(grams))
    return f"{rounded}g"


def _format_price(value: object | None, price_per_gram: float) -> str:
    try:
        grams = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    if grams < 0:
        return "Unknown"
    rounded = int(round(grams))
    return f"${rounded * price_per_gram:.2f}"


def _format_filament_with_optional_price(value: object | None, show_price: bool, price_per_gram: float) -> str:
    grams_text = _format_filament_grams(value)
    if grams_text == "Unknown":
        return "Unknown"

    if not show_price:
        return grams_text

    price_text = _format_price(value, price_per_gram)
    if price_text == "Unknown":
        return grams_text
    return f"{grams_text} ({price_text})"


def _dimensions_for_label(label_size: str) -> tuple[int, int]:
    spec = label_type_specs.get(label_size)
    if spec is None:
        return (696, 1109)

    width, height = spec["dots_printable"]
    if int(height) <= 0:
        # Endless rolls do not have a fixed printable height.
        return (int(width), 600)

    return (int(width), int(height))


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["DejaVuSans.ttf", "Arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
    min_size: int,
    bold: bool = False,
) -> tuple[str, ImageFont.ImageFont]:
    value = text
    for size in range(start_size, min_size - 1, -2):
        font = _load_font(size, bold=bold)
        if draw.textbbox((0, 0), value, font=font)[2] <= max_width:
            return value, font

    # Truncate if no font size can fit.
    font = _load_font(min_size, bold=bold)
    while len(value) > 4 and draw.textbbox((0, 0), value + "...", font=font)[2] > max_width:
        value = value[:-1]
    return value + "...", font


def render_label_image(
    event: dict[str, object],
    label_size: str,
    *,
    show_price: bool,
    price_per_gram: float,
) -> Image.Image:
    native_width, native_height = _dimensions_for_label(label_size)

    # Build in landscape design space, then rotate back to native dimensions.
    rotate_back = native_height > native_width
    if rotate_back:
        width, height = native_height, native_width
    else:
        width, height = native_width, native_height

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    margin = int(width * 0.02)
    bottom_margin = int(height * 0.02)
    header_h = int(height * 0.16)
    section_gap = max(8, int(height * 0.012))

    # Header bar
    draw.rectangle((0, 0, width, header_h), fill="black")
    header_text = "3D PRINT JOB"
    header_label, header_font = _fit_text(
        draw,
        header_text,
        max_width=width - (margin * 2),
        start_size=int(header_h * 0.55),
        min_size=26,
        bold=True,
    )
    text_box = draw.textbbox((0, 0), header_label, font=header_font)
    text_w = text_box[2] - text_box[0]
    text_h = text_box[3] - text_box[1]
    draw.text(((width - text_w) // 2, (header_h - text_h) // 2), header_label, fill="white", font=header_font)

    y = header_h + section_gap
    line_h = int(height * 0.085)
    body_size = int(height * 0.057)

    lines = [
        ("Printer", _safe_text(event.get("printer_name") or event.get("printer_id"))),
        ("File", _safe_text(event.get("file_name"))),
        ("Start", _format_datetime(event.get("started_at"))),
        ("ETA End", _format_datetime(event.get("eta_end_at"))),
        ("Duration", _format_duration(event.get("est_duration_sec"))),
        (
            "Filament",
            _format_filament_with_optional_price(
                event.get("filament_estimated_g"),
                show_price=show_price,
                price_per_gram=price_per_gram,
            ),
        ),
    ]

    for label, value in lines:
        line_text = f"{label}: {value}"
        fitted, font = _fit_text(
            draw,
            line_text,
            max_width=width - (margin * 2),
            start_size=body_size,
            min_size=22,
            bold=False,
        )
        draw.text((margin, y), fitted, fill="black", font=font)
        y += line_h

    y += section_gap
    field_gap = max(8, int(height * 0.012))
    fields = ("Name", "Phone/E-Mail")
    available_for_fields = max(120, height - bottom_margin - y)
    field_h = max(70, int((available_for_fields - (field_gap * (len(fields) - 1))) / len(fields)))
    field_font = _load_font(int(height * 0.05), bold=True)

    for index, field in enumerate(fields):
        field_top = y + index * (field_h + field_gap)
        field_bottom = min(height - bottom_margin, field_top + field_h)
        draw.rectangle((margin, field_top, width - margin, field_bottom), outline="black", width=3)
        draw.text((margin + 12, field_top + 8), f"{field}:", fill="black", font=field_font)

    if rotate_back:
        return image.rotate(90, expand=True)
    return image
