from __future__ import annotations


def render_admin_ui_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PrinterPrinter Admin</title>
  <style>
    :root {
      --bg: #f0f4f8;
      --surface: #ffffff;
      --ink: #1a2b3c;
      --muted: #526275;
      --line: #cbd5e1;
      --input-border: #757575;
      --accent: #3B73B9;
      --accent-2: #2a5da8;
      --warn: #b9380c;
      --ok: #0d7a52;
      --radius: 14px;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 20%, #eef5ff 0, transparent 36%),
        radial-gradient(circle at 90% 0%, #f0faff 0, transparent 34%),
        var(--bg);
      font-family: 'Avenir Next', 'Segoe UI', sans-serif;
      line-height: 1.45;
    }

    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 1.25rem;
      display: grid;
      gap: 1rem;
    }

    .hero {
      background: linear-gradient(135deg, #1a2b3c, #3B73B9);
      color: #fff;
      border-radius: var(--radius);
      padding: 1.25rem;
      box-shadow: 0 12px 28px rgba(26, 43, 60, 0.24);
    }

    .hero h1 {
      margin: 0;
      font-size: clamp(1.3rem, 2.4vw, 2rem);
      letter-spacing: 0.02em;
    }

    .hero p {
      margin: 0.5rem 0 0;
      color: #e2e8f0;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 1rem;
    }

    .card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 1rem;
      box-shadow: 0 6px 20px rgba(20, 40, 30, 0.08);
    }

    .controls { grid-column: span 12; }
    .config { grid-column: span 12; }
    .events { grid-column: span 12; }
    .logs { grid-column: span 12; }

    @media (min-width: 1000px) {
      .controls { grid-column: span 4; }
      .config { grid-column: span 8; }
      .events { grid-column: span 12; }
    }

    h2 {
      margin: 0 0 0.75rem;
      font-size: 1.08rem;
    }

    fieldset {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 0.85rem;
      margin: 0 0 0.85rem;
    }

    fieldset[hidden] {
      display: none;
    }

    legend {
      padding: 0 0.4rem;
      font-size: 0.88rem;
      font-weight: 700;
      color: var(--ink);
    }

    .row {
      display: grid;
      gap: 0.75rem;
      margin-block-end: 0.85rem;
    }

    .row:last-child {
      margin-block-end: 0;
    }

    .row.two {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    @media (max-width: 640px) {
      .row.two {
        grid-template-columns: 1fr;
      }
    }

    label {
      display: block;
      font-size: 0.86rem;
      color: var(--muted);
      margin-block-end: 0.25rem;
      font-weight: 600;
    }

    .hint {
      display: block;
      font-size: 0.78rem;
      color: var(--muted);
      margin-block-start: 0.2rem;
    }

    input:not([type="radio"]):not([type="checkbox"]), textarea, select {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--input-border);
      border-radius: 10px;
      background: #fff;
      color: var(--ink);
      padding: 0.55rem 0.7rem;
      min-height: 42px;
      font: inherit;
      font-size: max(1rem, 1em);
    }

    input[type="radio"], input[type="checkbox"] {
      accent-color: var(--accent);
      width: 1.15rem;
      height: 1.15rem;
      margin: 0;
    }

    .choice-group {
      display: flex;
      flex-wrap: wrap;
      gap: 0.9rem;
      align-items: center;
      min-height: 42px;
    }

    .choice-item {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }

    .choice-item label {
      display: inline;
      margin: 0;
      color: var(--ink);
      font-weight: 500;
      cursor: pointer;
    }

    input:focus-visible, textarea:focus-visible, select:focus-visible, button:focus-visible {
      outline: 3px solid var(--accent);
      outline-offset: 2px;
    }

    textarea {
      min-height: 80px;
      resize: vertical;
    }

    .btns {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-block-start: 0.5rem;
    }

    button {
      border: none;
      border-radius: 10px;
      padding: 0.55rem 0.8rem;
      min-height: 42px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      transition: transform 90ms ease, opacity 130ms ease;
    }

    button:hover:not(:disabled) { transform: translateY(-1px); }
    button:active:not(:disabled) { transform: translateY(0); }
    button:disabled { opacity: 0.6; cursor: not-allowed; }

    .primary { background: var(--accent); color: #fff; }
    .primary:hover:not(:disabled) { background: var(--accent-2); }
    .secondary { background: #e6eef6; color: var(--ink); }
    .danger { background: #fce8e5; color: var(--warn); }

    .status {
      font-size: 0.86rem;
      margin-block-start: 0.5rem;
      min-height: 1.2em;
      color: var(--muted);
    }

    .status.ok { color: var(--ok); }
    .status.error { color: var(--warn); }

    .printer-probe {
      margin-block-start: 0.85rem;
      padding: 0.75rem;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #f8fafc;
      font-size: 0.85rem;
    }

    .printer-probe strong {
      display: block;
      margin-block-end: 0.25rem;
    }

    .chip {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      background: #e7f4ec;
      color: #0f6f45;
      font-size: 0.75rem;
      font-weight: 700;
    }

    .chip.warn {
      background: #fce8e5;
      color: var(--warn);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
    }

    th, td {
      border-bottom: 1px solid var(--line);
      text-align: left;
      padding: 8px 6px;
      vertical-align: top;
    }

    th {
      color: var(--muted);
      font-size: 0.8rem;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }

    .mono { font-family: 'Menlo', 'Consolas', monospace; }
    .logs-output {
      background: #f8f8f8;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 12px;
      font-size: 0.8rem;
      line-height: 1.4;
      overflow: auto;
      max-height: 500px;
      white-space: pre;
    }

    .preview-box {
      padding: 1rem;
      display: flex;
      justify-content: center;
      align-items: center;
      overflow: auto;
    }

    .preview {
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      display: block;
    }

    .preview-row td {
      padding: 0;
      text-align: center;
      background: #fafafa;
      overflow: hidden;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>PrinterPrinter Admin</h1>
      <p>Configure Dymo or Brother label printing, preview &amp; reprint labels, and manage the daemon.</p>
    </section>

    <section class="grid">
      <article class="card controls">
        <h2>Instance Controls</h2>
        <div class="btns">
          <button type="button" class="secondary" id="refresh-all">Refresh All</button>
          <button type="button" class="secondary" id="poll-once">Poll Once</button>
          <button type="button" class="secondary" id="view-logs">View Logs</button>
          <button type="button" class="secondary" id="setup-dymo">Setup Dymo USB</button>
          <button type="button" class="primary" id="restart-service">Restart Service</button>
          <button type="button" class="danger" id="update-service">Update + Restart</button>
        </div>
        <div class="status" id="ops-status" role="status" aria-live="polite"></div>

        <div class="printer-probe" id="printer-probe" role="status" aria-live="polite">
          <strong>Label Printer Status</strong>
          <span id="printer-probe-text">Checking printer status...</span>
        </div>
      </article>

      <article class="card config">
        <h2 id="config-heading">Configuration</h2>
        <form id="config-form" action="/admin/config" method="POST" aria-labelledby="config-heading">
          <fieldset>
            <legend>Label Printer</legend>
            <div class="row two">
              <div>
                <label>Printer Backend</label>
                <div class="choice-group">
                  <span class="choice-item">
                    <input type="radio" id="backend-dymo" name="PRINTER_BACKEND" value="dymo" />
                    <label for="backend-dymo">Dymo (USB / CUPS)</label>
                  </span>
                  <span class="choice-item">
                    <input type="radio" id="backend-brother" name="PRINTER_BACKEND" value="brother" />
                    <label for="backend-brother">Brother (Network)</label>
                  </span>
                </div>
              </div>
              <div>
                <label>Printing State</label>
                <div class="choice-group">
                  <span class="choice-item">
                    <input type="checkbox" id="printer-enabled" name="PRINTER_ENABLED" checked />
                    <label for="printer-enabled">Enable automatic label printing</label>
                  </span>
                </div>
              </div>
            </div>

            <div class="row two">
              <div>
                <label for="label-size">Label Size / Media Code</label>
                <input
                  id="label-size"
                  name="PRINTER_LABEL_SIZE"
                  list="label-size-options"
                  autocorrect="off"
                  autocapitalize="none"
                  spellcheck="false"
                  aria-describedby="label-size-hint"
                />
                <datalist id="label-size-options">
                  <option value="30336">Dymo 30336 Small Multipurpose (1" x 2-1/8" / 25x54mm)</option>
                  <option value="30252">Dymo 30252 Standard Address (1-1/8" x 3-1/2")</option>
                  <option value="30321">Dymo 30321 Large Address (1-4/10" x 3-1/2")</option>
                  <option value="30256">Dymo 30256 Shipping (2-5/16" x 4" / 59x102mm)</option>
                  <option value="30323">Dymo 30323 Shipping (2-1/8" x 4" / 54x101mm)</option>
                  <option value="30334">Dymo 30334 Multi-Purpose (2-1/4" x 1-1/4")</option>
                  <option value="99010">Dymo 99010 Standard Address (28x89mm)</option>
                  <option value="99012">Dymo 99012 Large Address (36x89mm)</option>
                  <option value="99014">Dymo 99014 Shipping (54x101mm)</option>
                  <option value="62x100">Brother DK-1202 (62x100mm)</option>
                  <option value="62x29">Brother DK-1209 (62x29mm)</option>
                </datalist>
                <span id="label-size-hint" class="hint">Initial small roll: 30336 (1&quot; x 2-1/8&quot;). Shipping roll: 30256.</span>
              </div>
              <div>
                <label for="price-per-gram">Filament Price per Gram (USD)</label>
                <input id="price-per-gram" name="FILAMENT_PRICE_PER_GRAM" inputmode="decimal" autocorrect="off" autocapitalize="none" spellcheck="false" />
              </div>
            </div>
          </fieldset>

          <fieldset id="dymo-fieldset">
            <legend>Dymo LabelWriter Settings</legend>
            <div class="row two">
              <div>
                <label>Dymo Interface</label>
                <div class="choice-group">
                  <span class="choice-item">
                    <input type="radio" id="dymo-if-usb" name="PRINTER_INTERFACE" value="usb" checked />
                    <label for="dymo-if-usb">USB</label>
                  </span>
                  <span class="choice-item">
                    <input type="radio" id="dymo-if-auto" name="PRINTER_INTERFACE" value="auto" />
                    <label for="dymo-if-auto">Auto</label>
                  </span>
                  <span class="choice-item">
                    <input type="radio" id="dymo-if-wifi" name="PRINTER_INTERFACE" value="wifi" />
                    <label for="dymo-if-wifi">WiFi</label>
                  </span>
                </div>
              </div>
              <div>
                <label for="dymo-model">Dymo Model</label>
                <input id="dymo-model" name="DYMO_MODEL" autocorrect="off" autocapitalize="none" spellcheck="false" />
              </div>
            </div>
            <div class="row two">
              <div>
                <label for="dymo-usb-queue">Dymo USB CUPS Queue Name</label>
                <input
                  id="dymo-usb-queue"
                  name="DYMO_USB_QUEUE_NAME"
                  autocorrect="off"
                  autocapitalize="none"
                  spellcheck="false"
                  aria-describedby="dymo-usb-hint"
                />
                <span id="dymo-usb-hint" class="hint">Leave blank to auto-discover USB queue, or click Setup Dymo USB.</span>
              </div>
              <div>
                <label for="dymo-wifi-queue">Dymo WiFi CUPS Queue Name</label>
                <input
                  id="dymo-wifi-queue"
                  name="DYMO_WIFI_QUEUE_NAME"
                  autocorrect="off"
                  autocapitalize="none"
                  spellcheck="false"
                />
              </div>
            </div>
          </fieldset>

          <fieldset id="brother-fieldset" hidden inert>
            <legend>Brother QL Settings</legend>
            <div class="row two">
              <div>
                <label for="printer-uri">Brother Printer URI</label>
                <input id="printer-uri" name="BROTHER_PRINTER_URI" autocorrect="off" autocapitalize="none" spellcheck="false" />
              </div>
              <div>
                <label for="brother-model">Brother Model</label>
                <input id="brother-model" name="BROTHER_MODEL" autocorrect="off" autocapitalize="none" spellcheck="false" />
              </div>
            </div>
          </fieldset>

          <fieldset>
            <legend>Bambuddy &amp; Polling</legend>
            <div class="row two">
              <div>
                <label for="base-url">Bambuddy Base URL</label>
                <input id="base-url" name="BAMBUDDY_BASE_URL" autocorrect="off" autocapitalize="none" spellcheck="false" />
              </div>
              <div>
                <label for="api-token">Bambuddy API Token</label>
                <input id="api-token" name="BAMBUDDY_API_TOKEN" autocorrect="off" autocapitalize="none" spellcheck="false" />
              </div>
            </div>
            <div class="row two">
              <div>
                <label for="monitor-identifiers">Monitored Printer Identifiers</label>
                <textarea id="monitor-identifiers" name="PRINTERPRINTER_MONITORED_PRINTER_IDENTIFIERS" autocorrect="off" autocapitalize="none" spellcheck="false"></textarea>
                <span class="hint">Comma-separated serials, IPs, or names.</span>
              </div>
              <div>
                <label for="monitor-ids">Monitored Printer IDs</label>
                <textarea id="monitor-ids" name="PRINTERPRINTER_MONITORED_PRINTER_IDS" autocorrect="off" autocapitalize="none" spellcheck="false"></textarea>
                <span class="hint">Comma-separated numeric Bambuddy IDs (blank = all).</span>
              </div>
            </div>
            <div class="row two">
              <div>
                <label for="poll-seconds">Poll Interval Seconds</label>
                <input id="poll-seconds" name="PRINTERPRINTER_POLL_INTERVAL_SECONDS" inputmode="decimal" />
              </div>
              <div>
                <label for="wait-seconds">Label Wait Seconds</label>
                <input id="wait-seconds" name="PRINTERPRINTER_LABEL_WAIT_SECONDS" inputmode="decimal" />
              </div>
            </div>
          </fieldset>

          <div class="btns">
            <button type="submit" class="primary" id="save-config">Save Config</button>
          </div>
          <div class="status" id="config-status" role="status" aria-live="polite"></div>
        </form>
      </article>

      <article class="card events">
        <h2>Recent Labels</h2>
        <div class="status" id="events-status" role="status" aria-live="polite"></div>
        <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px;">
          <label for="events-limit" style="margin: 0;">Show Recent Labels:</label>
          <select id="events-limit" name="events_limit" style="width: auto;">
            <option value="5">5</option>
            <option value="10">10</option>
            <option value="25" selected>25</option>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="all">All</option>
          </select>
        </div>
        <div style="overflow:auto;">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Printer</th>
                <th>File</th>
                <th>Start</th>
                <th>Duration</th>
                <th>Filament</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody id="events-body"></tbody>
          </table>
        </div>
      </article>

      <article class="card logs">
        <h2>System Logs</h2>
        <div class="status" id="logs-status" role="status" aria-live="polite"></div>
        <pre id="logs-output" class="mono logs-output"></pre>
        <div class="btns">
          <button type="button" class="secondary" id="refresh-logs">Refresh Logs</button>
        </div>
      </article>
    </section>
  </div>

  <script>
    const ids = {
      configForm: document.getElementById('config-form'),
      saveBtn: document.getElementById('save-config'),
      backendDymo: document.getElementById('backend-dymo'),
      backendBrother: document.getElementById('backend-brother'),
      printerEnabled: document.getElementById('printer-enabled'),
      dymoFieldset: document.getElementById('dymo-fieldset'),
      brotherFieldset: document.getElementById('brother-fieldset'),
      dymoModel: document.getElementById('dymo-model'),
      dymoUsbQueue: document.getElementById('dymo-usb-queue'),
      dymoWifiQueue: document.getElementById('dymo-wifi-queue'),
      printerUri: document.getElementById('printer-uri'),
      brotherModel: document.getElementById('brother-model'),
      labelSize: document.getElementById('label-size'),
      pricePerGram: document.getElementById('price-per-gram'),
      baseUrl: document.getElementById('base-url'),
      apiToken: document.getElementById('api-token'),
      monitorIdentifiers: document.getElementById('monitor-identifiers'),
      monitorIds: document.getElementById('monitor-ids'),
      pollSeconds: document.getElementById('poll-seconds'),
      waitSeconds: document.getElementById('wait-seconds'),
      eventsBody: document.getElementById('events-body'),
      eventsLimit: document.getElementById('events-limit'),
      opsStatus: document.getElementById('ops-status'),
      printerProbeText: document.getElementById('printer-probe-text'),
      configStatus: document.getElementById('config-status'),
      eventsStatus: document.getElementById('events-status'),
      logsOutput: document.getElementById('logs-output'),
      logsStatus: document.getElementById('logs-status'),
    };

    function setStatus(el, message, level = '') {
      el.textContent = message;
      el.className = 'status' + (level ? ` ${level}` : '');
    }

    function escapeHTML(str) {
      if (str === null || str === undefined) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    async function api(url, options) {
      const response = await fetch(url, options);
      const text = await response.text();
      let data = null;
      try { data = text ? JSON.parse(text) : null; } catch (_) {}
      if (!response.ok) {
        const detail = data && data.detail ? data.detail : `${response.status} ${response.statusText}`;
        throw new Error(detail);
      }
      return data;
    }

    function fmt(v) { return (v === null || v === undefined || v === '') ? 'Unknown' : String(v); }

    function getSelectedBackend() {
      return ids.backendDymo.checked ? 'dymo' : 'brother';
    }

    function getSelectedInterface() {
      const checked = document.querySelector('input[name="PRINTER_INTERFACE"]:checked');
      return checked ? checked.value : 'usb';
    }

    function syncBackendVisibility(autoAdjustSize = false) {
      const isDymo = getSelectedBackend() === 'dymo';
      ids.dymoFieldset.hidden = !isDymo;
      ids.dymoFieldset.inert = !isDymo;
      ids.brotherFieldset.hidden = isDymo;
      ids.brotherFieldset.inert = isDymo;

      if (autoAdjustSize) {
        const cur = ids.labelSize.value.trim();
        if (isDymo && (!cur || cur === '62x100' || cur === '62x29')) {
          ids.labelSize.value = '30336';
        } else if (!isDymo && (!cur || cur === '30336' || cur === '30256' || cur === '30252')) {
          ids.labelSize.value = '62x100';
        }
      }
    }

    ids.backendDymo.addEventListener('change', () => syncBackendVisibility(true));
    ids.backendBrother.addEventListener('change', () => syncBackendVisibility(true));

    async function loadPrinterStatus() {
      try {
        const st = await api('/probes/printer');
        const badgeClass = st.ok ? 'chip' : 'chip warn';
        const badgeLabel = st.ok ? 'READY' : (st.paper_out ? 'OUT OF PAPER' : 'ATTENTION');
        const backendName = String(st.backend || 'unknown').toUpperCase();
        ids.printerProbeText.innerHTML = `
          <span class="${badgeClass}">${escapeHTML(badgeLabel)}</span>
          <span class="mono">${escapeHTML(backendName)}</span> &mdash;
          ${escapeHTML(st.detail || '')}
        `;
      } catch (err) {
        ids.printerProbeText.textContent = `Status check failed: ${err.message}`;
      }
    }

    async function loadLogs(lines = 100) {
      try {
        setStatus(ids.logsStatus, 'Fetching logs...', '');
        const payload = await api(`/admin/logs?lines=${lines}`);
        ids.logsOutput.textContent = payload.logs;
        ids.logsOutput.scrollTop = ids.logsOutput.scrollHeight;
        setStatus(ids.logsStatus, 'Logs updated', 'ok');
      } catch (err) {
        setStatus(ids.logsStatus, err.message, 'error');
      }
    }

    async function loadConfig() {
      const payload = await api('/admin/config');
      const v = payload.values || {};
      const backend = (v.PRINTER_BACKEND || 'brother').toLowerCase();
      ids.backendDymo.checked = backend === 'dymo';
      ids.backendBrother.checked = backend !== 'dymo';

      const enabledRaw = (v.PRINTER_ENABLED || v.BROTHER_ENABLED || 'true').toLowerCase();
      ids.printerEnabled.checked = !['false', '0', 'no'].includes(enabledRaw);

      const iface = (v.PRINTER_INTERFACE || 'usb').toLowerCase();
      const ifaceRadio = document.querySelector(`input[name="PRINTER_INTERFACE"][value="${iface}"]`);
      if (ifaceRadio) ifaceRadio.checked = true;

      ids.labelSize.value = v.PRINTER_LABEL_SIZE || v.BROTHER_LABEL_SIZE || (backend === 'dymo' ? '30336' : '62x100');
      ids.pricePerGram.value = v.FILAMENT_PRICE_PER_GRAM || '0.10';
      ids.dymoModel.value = v.DYMO_MODEL || 'LabelWriter-400-Turbo';
      ids.dymoUsbQueue.value = v.DYMO_USB_QUEUE_NAME || '';
      ids.dymoWifiQueue.value = v.DYMO_WIFI_QUEUE_NAME || '';
      ids.printerUri.value = v.BROTHER_PRINTER_URI || '';
      ids.brotherModel.value = v.BROTHER_MODEL || 'QL-820NWB';

      ids.baseUrl.value = v.BAMBUDDY_BASE_URL || '';
      ids.apiToken.value = v.BAMBUDDY_API_TOKEN || '';
      ids.monitorIdentifiers.value = v.PRINTERPRINTER_MONITORED_PRINTER_IDENTIFIERS || '';
      ids.monitorIds.value = v.PRINTERPRINTER_MONITORED_PRINTER_IDS || '';
      ids.pollSeconds.value = v.PRINTERPRINTER_POLL_INTERVAL_SECONDS || '';
      ids.waitSeconds.value = v.PRINTERPRINTER_LABEL_WAIT_SECONDS || '';

      syncBackendVisibility(false);
      setStatus(ids.configStatus, `Loaded ${payload.env_file_path}`, 'ok');
    }

    async function saveConfig() {
      const backend = getSelectedBackend();
      const enabledStr = ids.printerEnabled.checked ? 'true' : 'false';
      const labelSize = ids.labelSize.value.trim();

      const values = {
        PRINTER_BACKEND: backend,
        PRINTER_ENABLED: enabledStr,
        BROTHER_ENABLED: enabledStr,
        PRINTER_INTERFACE: getSelectedInterface(),
        PRINTER_LABEL_SIZE: labelSize,
        DYMO_MODEL: ids.dymoModel.value.trim() || 'LabelWriter-400-Turbo',
        DYMO_USB_QUEUE_NAME: ids.dymoUsbQueue.value.trim(),
        DYMO_WIFI_QUEUE_NAME: ids.dymoWifiQueue.value.trim(),
        BROTHER_PRINTER_URI: ids.printerUri.value.trim(),
        BROTHER_MODEL: ids.brotherModel.value.trim() || 'QL-820NWB',
        FILAMENT_PRICE_PER_GRAM: ids.pricePerGram.value.trim() || '0.10',
        BAMBUDDY_BASE_URL: ids.baseUrl.value.trim(),
        BAMBUDDY_API_TOKEN: ids.apiToken.value.trim(),
        PRINTERPRINTER_MONITORED_PRINTER_IDENTIFIERS: ids.monitorIdentifiers.value.trim(),
        PRINTERPRINTER_MONITORED_PRINTER_IDS: ids.monitorIds.value.trim(),
        PRINTERPRINTER_POLL_INTERVAL_SECONDS: ids.pollSeconds.value.trim(),
        PRINTERPRINTER_LABEL_WAIT_SECONDS: ids.waitSeconds.value.trim(),
      };
      if (backend === 'brother' && labelSize) {
        values.BROTHER_LABEL_SIZE = labelSize;
      }

      ids.saveBtn.disabled = true;
      try {
        await api('/admin/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ values }),
        });
        setStatus(ids.configStatus, 'Configuration saved. Restart service to apply runtime polling changes.', 'ok');
        await loadPrinterStatus();
      } finally {
        ids.saveBtn.disabled = false;
      }
    }

    async function loadEvents() {
      const limit = ids.eventsLimit.value;
      const url = limit === 'all' ? '/admin/events' : `/admin/events?limit=${limit}`;
      try {
        const payload = await api(url);
        ids.eventsBody.innerHTML = '';
        for (const event of (payload.items || [])) {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td class="mono">${escapeHTML(event.id)}</td>
            <td>${escapeHTML(fmt(event.printer_name || event.printer_id))}</td>
            <td>${escapeHTML(fmt(event.file_name))}</td>
            <td>${escapeHTML(fmt(event.started_at))}</td>
            <td>${escapeHTML(fmt(event.est_duration_sec))}</td>
            <td>${escapeHTML(fmt(event.filament_estimated_g))}</td>
            <td>
              <div class="btns">
                <button type="button" class="secondary" data-preview="${escapeHTML(event.id)}">Preview</button>
                <button type="button" class="primary" data-reprint="${escapeHTML(event.id)}">Reprint</button>
              </div>
            </td>
          `;
          ids.eventsBody.appendChild(tr);
        }
        setStatus(ids.eventsStatus, `Loaded ${payload.count} events`, 'ok');
      } catch (err) {
        setStatus(ids.eventsStatus, err.message, 'error');
      }
    }

    async function runAction(path, statusElement, okMessage, body = null) {
      const opts = { method: 'POST' };
      if (body !== null) {
        opts.headers = { 'Content-Type': 'application/json' };
        opts.body = JSON.stringify(body);
      }
      const payload = await api(path, opts);
      const suffix = payload && payload.detail ? ` (${payload.detail})` : '';
      setStatus(statusElement, okMessage + suffix, 'ok');
      return payload;
    }

    document.getElementById('refresh-all').addEventListener('click', async () => {
      try {
        await Promise.all([loadConfig(), loadEvents(), loadPrinterStatus()]);
        setStatus(ids.opsStatus, 'Refreshed.', 'ok');
      } catch (err) {
        setStatus(ids.opsStatus, err.message, 'error');
      }
    });

    ids.eventsLimit.addEventListener('change', () => {
      loadEvents();
    });

    document.getElementById('poll-once').addEventListener('click', async () => {
      try {
        const payload = await runAction('/admin/poll-once', ids.opsStatus, 'Poll complete');
        setStatus(ids.opsStatus, `Poll complete: inserted=${payload.inserted}, printed=${payload.printed}, deferred=${payload.deferred}`, 'ok');
        await loadEvents();
      } catch (err) {
        setStatus(ids.opsStatus, err.message, 'error');
      }
    });

    document.getElementById('view-logs').addEventListener('click', async () => {
      await loadLogs();
    });

    document.getElementById('setup-dymo').addEventListener('click', async () => {
      try {
        setStatus(ids.opsStatus, 'Detecting Dymo USB printer and configuring CUPS queue...');
        const sizeCandidate = ids.backendDymo.checked && ids.labelSize.value.trim()
          ? ids.labelSize.value.trim()
          : '30336';
        const payload = await runAction('/admin/actions/setup-dymo', ids.opsStatus, 'Dymo USB ready', {
          queue_name: ids.dymoUsbQueue.value.trim(),
          model: ids.dymoModel.value.trim() || 'LabelWriter-400-Turbo',
          label_size: sizeCandidate,
          save_to_env: true,
        });
        await Promise.all([loadConfig(), loadPrinterStatus()]);
        if (payload && payload.detail) {
          setStatus(ids.opsStatus, `${payload.detail}. Restart service to use updated runtime settings.`, 'ok');
        }
      } catch (err) {
        setStatus(ids.opsStatus, err.message, 'error');
        await loadPrinterStatus();
      }
    });

    document.getElementById('restart-service').addEventListener('click', async () => {
      try {
        await runAction('/admin/actions/restart', ids.opsStatus, 'Service restarted');
      } catch (err) {
        setStatus(ids.opsStatus, err.message, 'error');
      }
    });

    document.getElementById('update-service').addEventListener('click', async () => {
      if (!confirm('Run update + restart now?')) return;
      try {
        setStatus(ids.opsStatus, 'Running update... this can take a minute.');
        const payload = await runAction('/admin/actions/update', ids.opsStatus, 'Update completed');
        if (payload && payload.steps) {
          setStatus(ids.opsStatus, `Update completed: ${payload.steps.join(' -> ')}`, 'ok');
        }
      } catch (err) {
        setStatus(ids.opsStatus, err.message, 'error');
      }
    });

    document.getElementById('refresh-logs').addEventListener('click', async () => {
      await loadLogs();
    });

    ids.configForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        await saveConfig();
      } catch (err) {
        setStatus(ids.configStatus, err.message, 'error');
      }
    });

    ids.eventsBody.addEventListener('click', async (event) => {
      const btn = event.target.closest('button');
      if (!btn) return;
      const previewId = btn.getAttribute('data-preview');
      const reprintId = btn.getAttribute('data-reprint');

      if (previewId) {
        const row = btn.closest('tr');
        const existingPreview = row.nextElementSibling;

        if (existingPreview && existingPreview.classList.contains('preview-row')) {
          existingPreview.remove();
          return;
        }

        document.querySelectorAll('.preview-row').forEach(r => r.remove());

        const sizeParam = encodeURIComponent(ids.labelSize.value.trim());
        const previewRow = document.createElement('tr');
        previewRow.className = 'preview-row';
        const td = document.createElement('td');
        td.colSpan = 7;
        const box = document.createElement('div');
        box.className = 'preview-box';
        const img = document.createElement('img');
        img.className = 'preview';
        img.alt = 'Label preview';
        img.addEventListener('load', () => {
          if (img.naturalHeight > img.naturalWidth) {
            const margin = Math.max(0, Math.round((img.naturalHeight - img.naturalWidth) / 2));
            img.style.transform = 'rotate(90deg)';
            box.style.minHeight = `${img.naturalWidth + 32}px`;
            img.style.margin = `${-margin + 16}px auto`;
          }
        });
        img.src = `/admin/label-preview/${encodeURIComponent(previewId)}.png?label_size=${sizeParam}&ts=${Date.now()}`;
        box.appendChild(img);
        td.appendChild(box);
        previewRow.appendChild(td);
        row.after(previewRow);
        previewRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }

      if (reprintId) {
        try {
          const res = await api(`/admin/print-event/${encodeURIComponent(reprintId)}`, { method: 'POST' });
          if (res && res.ok === false) {
            setStatus(ids.eventsStatus, `Reprint failed for event ${reprintId}: ${res.error || 'unknown error'}`, 'error');
          } else {
            setStatus(ids.eventsStatus, `Reprint sent for event ${reprintId}`, 'ok');
          }
          await loadPrinterStatus();
        } catch (err) {
          setStatus(ids.eventsStatus, err.message, 'error');
        }
      }
    });

    (async () => {
      try {
        await Promise.all([loadConfig(), loadEvents(), loadPrinterStatus()]);
      } catch (err) {
        setStatus(ids.opsStatus, err.message, 'error');
      }
    })();
  </script>
</body>
</html>"""
