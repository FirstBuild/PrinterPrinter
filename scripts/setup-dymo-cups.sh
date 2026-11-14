#!/bin/bash
# Configure a USB-connected Dymo LabelWriter (400/450/4XL series) in CUPS on Raspberry Pi / Debian.
# Usage: sudo bash scripts/setup-dymo-cups.sh [QUEUE_NAME] [LABEL_SIZE]

set -euo pipefail

QUEUE_NAME="${1:-}"
LABEL_SIZE="${2:-30336}"
ENV_FILE="${ENV_FILE:-/opt/printerprinter/.env}"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "Please run as root: sudo bash scripts/setup-dymo-cups.sh"
    exit 1
fi

case "$LABEL_SIZE" in
    30336) PPD_PAGE_SIZE="w72h154.1" ;;
    11352) PPD_PAGE_SIZE="w72h154" ;;
    30252) PPD_PAGE_SIZE="w79h252" ;;
    30321) PPD_PAGE_SIZE="w102h252" ;;
    30256) PPD_PAGE_SIZE="w167h288" ;;
    30323) PPD_PAGE_SIZE="w154h286" ;;
    30334) PPD_PAGE_SIZE="w162h90.1" ;;
    w*h*)  PPD_PAGE_SIZE="$LABEL_SIZE" ;;
    *)     PPD_PAGE_SIZE="w72h154.1" ;;
esac

echo "[1/4] Checking CUPS and printer-driver-dymo..."
if [ ! -x /usr/lib/cups/filter/raster2dymolw ] || ! command -v lpadmin >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y cups printer-driver-dymo
fi
systemctl enable --now cups

echo "[2/4] Scanning USB bus and CUPS backends for Dymo printer..."
if command -v lsusb >/dev/null 2>&1; then
    lsusb | grep -i 0922 || echo "Warning: No USB device with Dymo Vendor ID 0922 seen in lsusb."
fi

DEVICE_URI="$(lpinfo -v | awk '{for(i=1;i<=NF;i++) if (tolower($i) ~ /^usb:\/\/.*(dymo|labelwriter)/) {print $i; exit}}')"
if [ -z "$DEVICE_URI" ]; then
    echo ""
    echo "ERROR: No Dymo USB printer was detected by CUPS (lpinfo -v)."
    echo "Checklist for Dymo LabelWriter 400 Turbo:"
    echo "  1. Ensure the 24V DC power brick is plugged in underneath the base (front blue LED lit or flashing)."
    echo "     The LabelWriter 400 Turbo is NOT USB-bus-powered and is invisible on USB without AC power."
    echo "  2. Ensure the USB-B cable is firmly seated in the recessed jack underneath the printer and plugged into a Pi USB-A port."
    echo "  3. Run 'lsusb' to confirm '0922:001a Dymo-CoStar Corp. LabelWriter 400 Turbo' appears, then re-run this script."
    exit 2
fi
echo "Found Dymo USB URI: $DEVICE_URI"

DECODED_URI="$(printf '%s' "$DEVICE_URI" | sed 's/%20/ /g' | tr '[:upper:]' '[:lower:]')"
if [[ "$DECODED_URI" == *"450"* && "$DECODED_URI" == *"twin"* ]]; then
    TARGET_PPD="lw450tt.ppd"
    DETECTED_MODEL="LabelWriter-450-Twin-Turbo"
    DEFAULT_QUEUE="DYMO_LabelWriter_450_Twin_Turbo"
elif [[ "$DECODED_URI" == *"450"* && "$DECODED_URI" == *"duo"* ]]; then
    TARGET_PPD="lw450dl.ppd"
    DETECTED_MODEL="LabelWriter-450-DUO"
    DEFAULT_QUEUE="DYMO_LabelWriter_450_DUO"
elif [[ "$DECODED_URI" == *"450"* && "$DECODED_URI" == *"turbo"* ]]; then
    TARGET_PPD="lw450t.ppd"
    DETECTED_MODEL="LabelWriter-450-Turbo"
    DEFAULT_QUEUE="DYMO_LabelWriter_450_Turbo"
elif [[ "$DECODED_URI" == *"450"* ]]; then
    TARGET_PPD="lw450.ppd"
    DETECTED_MODEL="LabelWriter-450"
    DEFAULT_QUEUE="DYMO_LabelWriter_450"
elif [[ "$DECODED_URI" == *"400"* && "$DECODED_URI" == *"twin"* ]]; then
    TARGET_PPD="lwtt.ppd"
    DETECTED_MODEL="LabelWriter-400-Twin-Turbo"
    DEFAULT_QUEUE="DYMO_LabelWriter_400_Twin_Turbo"
elif [[ "$DECODED_URI" == *"400"* && "$DECODED_URI" == *"turbo"* ]]; then
    TARGET_PPD="lw400t.ppd"
    DETECTED_MODEL="LabelWriter-400-Turbo"
    DEFAULT_QUEUE="DYMO_LabelWriter_400_Turbo"
elif [[ "$DECODED_URI" == *"400"* ]]; then
    TARGET_PPD="lw400.ppd"
    DETECTED_MODEL="LabelWriter-400"
    DEFAULT_QUEUE="DYMO_LabelWriter_400"
elif [[ "$DECODED_URI" == *"4xl"* ]]; then
    TARGET_PPD="lw4xl.ppd"
    DETECTED_MODEL="LabelWriter-4XL"
    DEFAULT_QUEUE="DYMO_LabelWriter_4XL"
else
    TARGET_PPD="lw450t.ppd"
    DETECTED_MODEL="LabelWriter-450-Turbo"
    DEFAULT_QUEUE="DYMO_LabelWriter"
fi

QUEUE_NAME="${QUEUE_NAME:-$DEFAULT_QUEUE}"

echo "[3/4] Registering CUPS queue '$QUEUE_NAME' ($TARGET_PPD)..."
PPD_URI="$(lpinfo -m | awk -v ppd="$TARGET_PPD" '$1 ~ ("/" ppd "$") {print $1; exit}')"
PPD_URI="${PPD_URI:-dymo:0/cups/model/$TARGET_PPD}"

lpadmin -p "$QUEUE_NAME" -E \
    -v "$DEVICE_URI" \
    -m "$PPD_URI" \
    -o "PageSize=$PPD_PAGE_SIZE" \
    -o "DymoHalftoning=Default" \
    -o "Resolution=300dpi" \
    -o "DymoPrintQuality=Text" \
    -o "printer-is-shared=false" \
    -o "printer-error-policy=abort-job"

cupsenable "$QUEUE_NAME" 2>/dev/null || true
cupsaccept "$QUEUE_NAME" 2>/dev/null || true

echo "[4/4] Verifying queue status..."
lpstat -p "$QUEUE_NAME" -v "$QUEUE_NAME"

if [ -f "$ENV_FILE" ]; then
    python3 - "$ENV_FILE" "$QUEUE_NAME" "$LABEL_SIZE" "$DETECTED_MODEL" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
queue_name = sys.argv[2]
label_size = sys.argv[3]
detected_model = sys.argv[4]
updates = {
    "PRINTER_BACKEND": "dymo",
    "PRINTER_ENABLED": "true",
    "PRINTER_INTERFACE": "usb",
    "PRINTER_LABEL_SIZE": label_size,
    "DYMO_MODEL": detected_model,
    "DYMO_USB_QUEUE_NAME": queue_name,
}

lines = env_path.read_text(encoding="utf-8").splitlines()
seen = set()
out = []
for line in lines:
    s = line.strip()
    if s and not s.startswith("#") and "=" in s:
        k = s.split("=", 1)[0].strip()
        if k in updates:
            out.append(f"{k}={updates[k]}")
            seen.add(k)
            continue
    out.append(line)

missing = [k for k in updates if k not in seen]
if missing:
    if out and out[-1].strip():
        out.append("")
    out.append("# Dymo LabelWriter Configuration")
    for k in missing:
        out.append(f"{k}={updates[k]}")

env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
print(f"Updated {env_path} for Dymo USB queue '{queue_name}' (label size {label_size}).")
PY
fi

echo "Done! Load labels and start the service when ready: sudo systemctl start printerprinter"

