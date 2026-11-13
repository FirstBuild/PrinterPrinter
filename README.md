# PrinterPrinter

PrinterPrinter is a local daemon that runs alongside Bambuddy, watches configured Bambu printers for print starts, and auto-prints job labels to a USB-connected **Dymo LabelWriter** (such as the LabelWriter 400 Turbo via CUPS) or a network **Brother QL-820NWB**.

## Architecture

```mermaid
flowchart LR
	A["Bambu P1S Printers"] -->|"Status + Print State"| B["Bambuddy API"]
	B -->|"Poll every N seconds"| C["PrinterPrinter Daemon"]
	C --> D[("SQLite Event Store")]
	C --> E["Dymo LabelWriter 400 Turbo (USB/CUPS)\nor Brother QL-820NWB (TCP)"]
	C --> F["Admin UI & Endpoints\n/admin /probes/printer /admin/print-event/{id}"]
```

## Example Output

Dymo 30336 compact label (`1" x 2-1/8"` / `25x54mm`):

![Dymo 30336 compact label preview](data/label_preview_dymo_30336.png)

Brother DK-1202 / Dymo 30256 full shipping label (`62x100mm` / `59x102mm`):

![Latest label preview](data/label_preview_latest.png)

## Features

- Bambuddy connectivity check and printer discovery
- Print-start detection from printer state transitions
- Event persistence in SQLite
- Automatic label print on new start events
- Manual reprint endpoint
- Configurable price-per-gram and optional price display
- User-friendly date/time and duration formatting

## API Endpoints

- `GET /health`
- `GET /probes/bambuddy`
- `GET /probes/printer`
- `POST /admin/poll-once`
- `GET /admin/printers`
- `GET /admin/events`
- `GET /admin/ui`
- `GET /admin`
- `GET /admin/config`
- `POST /admin/config`
- `POST /admin/actions/setup-dymo`
- `POST /admin/actions/restart`
- `POST /admin/actions/update`
- `GET /admin/label-preview/{event_id}.png`
- `POST /admin/print-event/{event_id}`

## Configuration

Copy `.env.example` to `.env` and update values.

### Core

- `PRINTERPRINTER_HOST` (default `0.0.0.0`)
- `PRINTERPRINTER_PORT` (default `8080`)
- `PRINTERPRINTER_LOG_LEVEL` (default `INFO`)
- `PRINTERPRINTER_DB_PATH` (default `./data/printerprinter.sqlite3`)
- `PRINTERPRINTER_POLL_INTERVAL_SECONDS` (default `5`)
- `PRINTERPRINTER_LABEL_WAIT_SECONDS` (default `60`; wait window for missing duration/filament before deferring print)
- `PRINTERPRINTER_LABEL_WAIT_POLL_SECONDS` (default `5`; refresh interval during wait window)
- `PRINTERPRINTER_PENDING_LABEL_MAX_AGE_SECONDS` (default `900`; only auto-print deferred events younger than this)
- `PRINTERPRINTER_ENV_FILE_PATH` (default `.env`; config file used by admin UI save flow)
- `PRINTERPRINTER_SERVICE_NAME` (default `printerprinter`; systemd service name for restart/update actions)
- `PRINTERPRINTER_INSTALL_DIR` (default `/opt/printerprinter`; repository path used by update action)
- `PRINTERPRINTER_UPDATE_BRANCH` (default `main`; branch used by update action)
- `PRINTERPRINTER_VENV_PATH` (default `/opt/printerprinter/venv`; virtualenv used for update install)
- `PRINTERPRINTER_MONITORED_PRINTER_IDS` (comma-separated Bambuddy numeric IDs, empty means all)
- `PRINTERPRINTER_MONITORED_PRINTER_IDENTIFIERS` (comma-separated IDs, names, serials, or IPs to auto-resolve)

### Bambuddy

- `BAMBUDDY_BASE_URL` (example `http://10.206.50.172:8000`)
- `BAMBUDDY_API_TOKEN`
- `BAMBUDDY_TIMEOUT_SECONDS` (default `15`)
- `BAMBUDDY_AUTH_MODE` (`bearer`, `api_key_header`, `none`)
- `BAMBUDDY_AUTH_HEADER_NAME` (default `X-API-Key`)
- `BAMBUDDY_JOBS_ENDPOINT` (default `/api/v1/print-log/`)
- `BAMBUDDY_PRINTERS_ENDPOINT` (default `/api/v1/printers/`)
- `BAMBUDDY_PRINTER_STATUS_ENDPOINT_TEMPLATE` (default `/api/v1/printers/{printer_id}/status`)

### Label Printer Selection (Dymo USB or Brother Network)

- `PRINTER_BACKEND` (`dymo` or `brother`, default `brother`)
- `PRINTER_ENABLED` (`true`/`false`, fallback alias `BROTHER_ENABLED`)
- `PRINTER_INTERFACE` (`usb`, `auto`, `wifi`; default `usb` for Dymo)
- `PRINTER_LABEL_SIZE` (media SKU, fallback aliases `DYMO_LABEL_SIZE` / `BROTHER_LABEL_SIZE`)

#### Dymo LabelWriter 400 Turbo (Raspberry Pi / Linux via CUPS)

- `DYMO_MODEL` (default `LabelWriter-400-Turbo`)
- `DYMO_USB_QUEUE_NAME` (optional; auto-discovers USB Dymo CUPS queue when blank, or set e.g. `DYMO_LabelWriter_400_Turbo`)
- `DYMO_WIFI_QUEUE_NAME` (required only when `PRINTER_INTERFACE=wifi`)
- `DYMO_PRINT_QUALITY` (`Graphics` or `Text`, default `Graphics`)
- `DYMO_PRINT_DENSITY` (`Light`, `Medium`, `Normal`, `Dark`, default `Normal`)
- `DYMO_JOB_EXPIRE_SECONDS` (default `300`; auto-cancels unprinted CUPS jobs after 5 minutes if out of paper so old jobs never pile up)

Supported Dymo media SKUs (automatically mapped to exact 300 DPI `lw400t.ppd` `PageSize` dimensions and compact/full layouts):
- `30336` (`1" x 2-1/8"` / `25x54mm` Small Multipurpose — uses high-density compact layout)
- `30252` / `30320` / `99010` (`1-1/8" x 3-1/2"` / `28x89mm` Standard Address)
- `30321` / `99012` (`1-4/10" x 3-1/2"` / `36x89mm` Large Address)
- `30256` (`2-5/16" x 4"` / `59x102mm` Shipping — full layout)
- `30323` / `99014` (`2-1/8" x 4"` / `54x101mm` Shipping — full layout)
- `30334` / `11354` (`2-1/4" x 1-1/4"` / `57x32mm` Multi-Purpose)

Quick Dymo USB setup on an existing Raspberry Pi installation:

```bash
sudo bash /opt/printerprinter/scripts/setup-dymo-cups.sh DYMO_LabelWriter_400_Turbo 30336
```

Or click **Setup Dymo USB** directly in the Admin UI (`http://<pi-host>:8080/admin`).

#### Brother QL-820NWB

- `BROTHER_MODEL` (default `QL-820NWB`)
- `BROTHER_PRINTER_URI` (example `tcp://10.206.58.111:9100`)
- `BROTHER_CUT` (`true`/`false`)
- `PRINTER_LABEL_SIZE=62x100` (DK-1202)

### Pricing

- `SHOW_PRICE_ON_LABEL` (`true`/`false`)
- `FILAMENT_PRICE_PER_GRAM` (default `0.10`)

If price display is enabled, filament is shown as:

- `Filament: 42g ($4.20)`

Mass is rounded to the nearest gram before both display and price calculation.

## Local Development

1. Create and activate a virtual environment.
2. Install dependencies.
3. Configure `.env`.
4. Run the daemon.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
uvicorn printerprinter.main:app --host 0.0.0.0 --port 8080
```

Quick checks:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/probes/bambuddy
curl http://localhost:8080/admin/printers
curl -X POST http://localhost:8080/admin/poll-once
curl http://localhost:8080/admin/events
```

## Raspberry Pi Setup (Recommended for always-on deployment)

### Automated Setup (Recommended)

Run the setup script to fully set up PrinterPrinter with interactive configuration prompts. Choose one of the methods below:

If an existing `.env` is present, the installer will show the current values first and let you keep them to skip the prompts.

**Method 1: Pipe directly to bash (requires bash 4.1+, use Method 2 if this fails)**

```bash
curl -fsSL https://raw.githubusercontent.com/firstbuild/PrinterPrinter/main/scripts/setup-rpi.sh | sudo bash
```

**Method 2: Download then run (most reliable, recommended if Method 1 fails)**

```bash
curl -fsSL https://raw.githubusercontent.com/firstbuild/PrinterPrinter/main/scripts/setup-rpi.sh -o /tmp/setup.sh
sudo bash /tmp/setup.sh
```

**Method 3: Clone repo locally (manual)**

```bash
cd /tmp
git clone -b main https://github.com/firstbuild/PrinterPrinter.git
cd PrinterPrinter
sudo bash scripts/setup-rpi.sh
```

Specify a different branch by passing it as an argument (Methods 2 & 3):

```bash
sudo bash /tmp/setup.sh develop
```

The setup script will:
- Check and install system dependencies
- Clone or update the repository
- Create a Python virtual environment
- Install dependencies
- Prompt you for all configuration values (Bambuddy address, API key, printer IPs, pricing, etc.)
- Create a systemd service file
- Enable and start the daemon

After setup completes, monitor logs with:

```bash
journalctl -u printerprinter -f
```

### Manual Setup (Alternative)

If you prefer to set up manually, follow these steps:

These instructions assume Raspberry Pi OS 64-bit and Python 3.11+.

1. Install system packages.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

2. Clone and install.

```bash
git clone <your-repo-url> PrinterPrinter
cd PrinterPrinter
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
```

3. Edit `.env` for your network:

- `BAMBUDDY_BASE_URL=http://<bambuddy-ip>:8000`
- `BROTHER_PRINTER_URI=tcp://<brother-ip>:9100`
- `BAMBUDDY_API_TOKEN=<token>`

4. Create systemd service.

`/etc/systemd/system/printerprinter.service`

```ini
[Unit]
Description=PrinterPrinter Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/PrinterPrinter
EnvironmentFile=/home/pi/PrinterPrinter/.env
ExecStart=/home/pi/PrinterPrinter/.venv/bin/uvicorn printerprinter.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

5. Enable and start.

```bash
sudo systemctl daemon-reload
sudo systemctl enable printerprinter
sudo systemctl start printerprinter
sudo systemctl status printerprinter
```

6. View logs.

```bash
journalctl -u printerprinter -f
```

## Docker Setup (Sidecar with Bambuddy)

This repository includes:

- `Dockerfile`
- `docker-compose.example.yml`

### Option A: PrinterPrinter container, Bambuddy external

1. Set `.env` with Bambuddy LAN URL, for example:

- `BAMBUDDY_BASE_URL=http://bambuddy.local:8000`

2. Build and run:

```bash
docker compose -f docker-compose.example.yml up -d --build
```

### Option B: PrinterPrinter + Bambuddy in same Compose project

If your Bambuddy service is named `bambuddy` in compose, set:

- `BAMBUDDY_BASE_URL=http://bambuddy.local:8000`

Use shared compose network (default) so service DNS works.

### Docker networking notes

- On Linux, `network_mode: host` may simplify LAN printer discovery/access.
- On macOS/Windows Docker Desktop, host networking differs; prefer direct IP routing where possible.
- Ensure container can reach TCP `9100` on Brother printer.

## Operational Tips

- Keep API tokens out of git; do not commit `.env`.
- Use `PRINTERPRINTER_MONITORED_PRINTER_IDS` to limit label scope.
- If labels fail, test printer reachability:

```bash
ping <brother-ip>
nc -vz <brother-ip> 9100
```

- Trigger manual reprint by event ID:

```bash
curl -X POST http://localhost:8080/admin/print-event/123
```

## Troubleshooting

- **Dymo USB not appearing in `lsusb`**: The Dymo LabelWriter 400 Turbo is **not** USB-bus-powered. Confirm its 24V DC power adapter is plugged into live AC power (front blue feed LED lit or flashing) and both the barrel plug and USB-B plug are firmly seated in the recessed channel underneath the base.
- **Dymo out of paper**: When out of labels, the front LED flashes and PrinterPrinter detects the out-of-paper state via USB/CUPS (`GET /probes/printer`), failing cleanly (and expiring any queued CUPS job after `DYMO_JOB_EXPIRE_SECONDS`) so stale jobs will not mass-print when a new roll is loaded.
- `Wrong roll type` / clipped print: verify `PRINTER_LABEL_SIZE` matches the physical roll (`30336` for `1" x 2-1/8"`, `30256` for `2-5/16" x 4"`, `62x100` for Brother DK-1202).
- No prints: verify `PRINTER_ENABLED=true` and check `/probes/printer` or `/admin`.
- Bambuddy timeout/DNS issues: use direct IP in `BAMBUDDY_BASE_URL`.
- Price hidden unexpectedly: verify `SHOW_PRICE_ON_LABEL=true`.
