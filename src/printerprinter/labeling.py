from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from brother_ql.devicedependent import label_type_specs
from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class DymoMediaSpec:
    code: str
    ppd_page_size: str
    dots_printable: tuple[int, int]
    description: str


# Printable pixel dimensions at 300 DPI derived directly from lw400t.ppd ImageableArea
# in Debian's printer-driver-dymo package.
DYMO_MEDIA_SPECS: dict[str, DymoMediaSpec] = {
    "30336": DymoMediaSpec(
        code="30336",
        ppd_page_size="w72h154.1",
        dots_printable=(271, 593),
        description='30336 Small Multipurpose (1" x 2-1/8" / 25x54mm)',
    ),
    "11352": DymoMediaSpec(
        code="11352",
        ppd_page_size="w72h154",
        dots_printable=(271, 593),
        description="11352 Return Address Int (25x54mm)",
    ),
    "30252": DymoMediaSpec(
        code="30252",
        ppd_page_size="w79h252",
        dots_printable=(299, 963),
        description='30252 Standard Address (1-1/8" x 3-1/2" / 28x89mm)',
    ),
    "30320": DymoMediaSpec(
        code="30320",
        ppd_page_size="w79h252.1",
        dots_printable=(299, 963),
        description='30320 Address (1-1/8" x 3-1/2")',
    ),
    "99010": DymoMediaSpec(
        code="99010",
        ppd_page_size="w79h252.2",
        dots_printable=(299, 963),
        description="99010 Standard Address (28x89mm)",
    ),
    "30321": DymoMediaSpec(
        code="30321",
        ppd_page_size="w102h252",
        dots_printable=(392, 961),
        description='30321 Large Address (1-4/10" x 3-1/2" / 36x89mm)',
    ),
    "99012": DymoMediaSpec(
        code="99012",
        ppd_page_size="w102h252.1",
        dots_printable=(392, 961),
        description="99012 Large Address (36x89mm)",
    ),
    "30256": DymoMediaSpec(
        code="30256",
        ppd_page_size="w167h288",
        dots_printable=(665, 1112),
        description='30256 Shipping (2-5/16" x 4" / 59x102mm)',
    ),
    "30323": DymoMediaSpec(
        code="30323",
        ppd_page_size="w154h286",
        dots_printable=(608, 1109),
        description='30323 Shipping (2-1/8" x 4" / 54x101mm)',
    ),
    "99014": DymoMediaSpec(
        code="99014",
        ppd_page_size="w154h286.2",
        dots_printable=(608, 1109),
        description="99014 Shipping (54x101mm)",
    ),
    "30364": DymoMediaSpec(
        code="30364",
        ppd_page_size="w167h288.1",
        dots_printable=(665, 1112),
        description='30364 Name Badge (2-5/16" x 4")',
    ),
    "30857": DymoMediaSpec(
        code="30857",
        ppd_page_size="w167h288.2",
        dots_printable=(665, 1112),
        description='30857 Badge Label (2-5/16" x 4")',
    ),
    "11356": DymoMediaSpec(
        code="11356",
        ppd_page_size="w118h252",
        dots_printable=(459, 963),
        description="11356 White Name Badge (89x41mm)",
    ),
    "30334": DymoMediaSpec(
        code="30334",
        ppd_page_size="w162h90.1",
        dots_printable=(651, 339),
        description='30334 Multi-Purpose (2-1/4" x 1-1/4" / 57x32mm)',
    ),
    "11354": DymoMediaSpec(
        code="11354",
        ppd_page_size="w162h90",
        dots_printable=(651, 339),
        description="11354 Multi-Purpose (57x32mm)",
    ),
    "99019": DymoMediaSpec(
        code="99019",
        ppd_page_size="w167h539",
        dots_printable=(665, 2160),
        description="99019 Large Lever Arch (59x190mm)",
    ),
    "1744907": DymoMediaSpec(
        code="1744907",
        ppd_page_size="w288h432",
        dots_printable=(1160, 1740),
        description='1744907 4XL Extra Large Shipping (4" x 6")',
    ),
}

_PPD_PAGE_SIZE_RE = re.compile(r"^w(\d+)h(\d+)(?:\.\d+)?$")


def resolve_dymo_media(label_size: str) -> DymoMediaSpec | None:
    key = label_size.strip()
    if not key:
        return None

    if key in DYMO_MEDIA_SPECS:
        return DYMO_MEDIA_SPECS[key]

    lower_key = key.lower()
    for spec in DYMO_MEDIA_SPECS.values():
        if spec.ppd_page_size.lower() == lower_key:
            return spec

    match = _PPD_PAGE_SIZE_RE.match(key)
    if match:
        width_pt = int(match.group(1))
        height_pt = int(match.group(2))
        if width_pt > 0 and height_pt > 0:
            dots_w = max(100, round(width_pt * 300 / 72))
            dots_h = max(100, round(height_pt * 300 / 72))
            return DymoMediaSpec(
                code=key,
                ppd_page_size=key,
                dots_printable=(dots_w, dots_h),
                description=f"Custom PPD PageSize ({key})",
            )

    return None


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
        return "Unknown"

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


def _parse_local_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    candidate = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone()


def _format_datetime(value: object | None) -> str:
    dt = _parse_local_datetime(value)
    if dt is None:
        return _safe_text(value)

    # Example: Wed May 28, 10:05 AM
    return dt.strftime("%a %b %d, %I:%M %p")


def _format_compact_datetime(value: object | None) -> str:
    dt = _parse_local_datetime(value)
    if dt is None:
        return _safe_text(value)

    time_part = dt.strftime("%I:%M %p").lstrip("0")
    return f"{dt.strftime('%a')} {dt.month}/{dt.day} {time_part}"


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
    dymo_spec = resolve_dymo_media(label_size)
    if dymo_spec is not None:
        return dymo_spec.dots_printable

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
            return ImageFont.truetype(name, size=max(8, size))
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
    effective_start = max(10, start_size)
    effective_min = max(10, min(effective_start, min_size))
    for size in range(effective_start, effective_min - 1, -2):
        font = _load_font(size, bold=bold)
        if draw.textbbox((0, 0), value, font=font)[2] <= max_width:
            return value, font

    font = _load_font(effective_min, bold=bold)
    if draw.textbbox((0, 0), value, font=font)[2] <= max_width:
        return value, font

    # Truncate if no font size can fit.
    while len(value) > 4 and draw.textbbox((0, 0), value + "...", font=font)[2] > max_width:
        value = value[:-1]
    return value + "...", font


def _render_compact_label(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    event: dict[str, object],
    *,
    width: int,
    height: int,
    show_price: bool,
    price_per_gram: float,
) -> None:
    """High-density layout tailored for small/narrow labels like Dymo 30336 (1" x 2-1/8") and 30252."""
    margin = max(6, int(width * 0.014))
    bottom_margin = max(4, int(height * 0.015))
    header_h = max(30, int(height * 0.125))

    # Top banner puts Printer on the left and Filament/Price on the right instead of a static title.
    draw.rectangle((0, 0, width, header_h), fill="black")
    printer_raw = _safe_text(event.get("printer_name") or event.get("printer_id"))
    filament_raw = _format_filament_with_optional_price(
        event.get("filament_estimated_g"),
        show_price=show_price,
        price_per_gram=price_per_gram,
    )
    badge_text = filament_raw if filament_raw != "Unknown" else ""

    header_target_size = max(15, int(header_h * 0.66))
    header_min_size = max(12, int(header_h * 0.45))
    badge_w = 0
    if badge_text:
        badge_fitted, badge_font = _fit_text(
            draw,
            badge_text,
            max_width=max(80, int(width * 0.44)),
            start_size=header_target_size,
            min_size=header_min_size,
            bold=True,
        )
        badge_box = draw.textbbox((0, 0), badge_fitted, font=badge_font)
        badge_w = badge_box[2] - badge_box[0]
        badge_h = badge_box[3] - badge_box[1]
        draw.text(
            (width - margin - badge_w, max(0, (header_h - badge_h) // 2 - badge_box[1] // 2)),
            badge_fitted,
            fill="white",
            font=badge_font,
        )

    printer_max_w = max(80, width - (margin * 2) - (badge_w + 12 if badge_w else 0))
    printer_fitted, printer_font = _fit_text(
        draw,
        printer_raw,
        max_width=printer_max_w,
        start_size=header_target_size,
        min_size=header_min_size,
        bold=True,
    )
    p_box = draw.textbbox((0, 0), printer_fitted, font=printer_font)
    p_h = p_box[3] - p_box[1]
    draw.text(
        (margin, max(0, (header_h - p_h) // 2 - p_box[1] // 2)),
        printer_fitted,
        fill="white",
        font=printer_font,
    )

    y = header_h + max(4, int(height * 0.018))
    line_h = max(22, int(height * 0.098))
    body_size = max(15, int(height * 0.076))
    body_min_size = max(12, int(height * 0.052))

    duration_str = _format_duration(event.get("est_duration_sec"))
    start_str = _format_compact_datetime(event.get("started_at"))
    start_and_dur = f"Start: {start_str}  ({duration_str})" if duration_str != "Unknown" else f"Start: {start_str}"
    eta_str = f"ETA: {_format_datetime(event.get('eta_end_at'))}"
    file_str = f"File: {_safe_text(event.get('file_name'))}"

    compact_rows = [
        (file_str, False),
        (start_and_dur, False),
        (eta_str, True),
    ]
    for row_text, is_bold in compact_rows:
        fitted, font = _fit_text(
            draw,
            row_text,
            max_width=width - (margin * 2),
            start_size=body_size + (1 if is_bold else 0),
            min_size=body_min_size,
            bold=is_bold,
        )
        draw.text((margin, y), fitted, fill="black", font=font)
        y += line_h

    y += max(4, int(height * 0.018))
    fields = ("Name", "Contact")
    field_gap = max(5, int(height * 0.02))
    available = max(64, height - bottom_margin - y)
    field_h = max(28, (available - field_gap * (len(fields) - 1)) // len(fields))
    field_font = _load_font(max(13, int(height * 0.068)), bold=True)

    for index, field in enumerate(fields):
        field_top = y + index * (field_h + field_gap)
        field_bottom = min(height - bottom_margin, field_top + field_h)
        draw.rectangle((margin, field_top, width - margin, field_bottom), outline="black", width=2)
        draw.text((margin + 6, field_top + max(3, int(field_h * 0.09))), f"{field}:", fill="black", font=field_font)


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

    if height < 450:
        _render_compact_label(
            image,
            draw,
            event,
            width=width,
            height=height,
            show_price=show_price,
            price_per_gram=price_per_gram,
        )
        if rotate_back:
            return image.rotate(90, expand=True)
        return image

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
