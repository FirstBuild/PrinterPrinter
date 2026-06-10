from __future__ import annotations


def render_admin_ui_html() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>PrinterPrinter Admin</title>
  <style>
    :root {
      --bg: #f4f7f4;
      --surface: #ffffff;
      --ink: #13201a;
      --muted: #5a6b61;
      --line: #d2ddd6;
      --accent: #0d7a4e;
      --accent-2: #0a5f3d;
      --warn: #a63a2d;
      --ok: #0b7f40;
      --radius: 14px;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 20%, #dbeee2 0, transparent 36%),
        radial-gradient(circle at 90% 0%, #e5f0ff 0, transparent 34%),
        var(--bg);
      font-family: 'Avenir Next', 'Segoe UI', sans-serif;
    }

    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px;
      display: grid;
      gap: 16px;
    }

    .hero {
      background: linear-gradient(135deg, #0c3d2a, #1e6e45);
      color: #fff;
      border-radius: var(--radius);
      padding: 20px;
      box-shadow: 0 12px 28px rgba(18, 58, 40, 0.24);
    }

    .hero h1 {
      margin: 0;
      font-size: clamp(1.3rem, 2.4vw, 2rem);
      letter-spacing: 0.02em;
    }

    .hero p {
      margin: 8px 0 0;
      color: #d6f4e4;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 16px;
    }

    .card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px;
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
      margin: 0 0 10px;
      font-size: 1.08rem;
    }

    .row {
      display: grid;
      gap: 10px;
      margin-bottom: 10px;
    }

    .row.two {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    label {
      display: block;
      font-size: 0.84rem;
      color: var(--muted);
      margin-bottom: 4px;
      font-weight: 600;
    }

    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
      color: var(--ink);
      padding: 9px 11px;
      font: inherit;
    }

    textarea {
      min-height: 84px;
      resize: vertical;
    }

    .btns {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }

    button {
      border: none;
      border-radius: 10px;
      padding: 9px 12px;
      font: inherit;
      cursor: pointer;
      transition: transform 90ms ease, opacity 130ms ease;
    }

    button:hover { transform: translateY(-1px); }
    button:active { transform: translateY(0); }

    .primary { background: var(--accent); color: #fff; }
    .primary:hover { background: var(--accent-2); }
    .secondary { background: #e9f0eb; color: var(--ink); }
    .danger { background: #fce8e5; color: var(--warn); }

    .status {
      font-size: 0.86rem;
      margin-top: 8px;
      min-height: 1.2em;
      color: var(--muted);
    }

    .status.ok { color: var(--ok); }
    .status.error { color: var(--warn); }

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

    .chip {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      background: #e7f4ec;
      color: #0f6f45;
      font-size: 0.75rem;
      font-weight: 700;
    }

    .preview {
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      margin: 0 auto;
      background: #fff;
      display: block;
      transform: rotate(90deg);
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
  <div class=\"wrap\">
    <section class=\"hero\">
      <h1>PrinterPrinter Admin</h1>
      <p>Configure settings, reprint labels, restart service, and run updates.</p>
    </section>

    <section class=\"grid\">
      <article class=\"card controls\">
        <h2>Instance Controls</h2>
        <div class=\"btns\">
          <button class=\"secondary\" id=\"refresh-all\">Refresh All</button>
          <button class=\"secondary\" id=\"poll-once\">Poll Once</button>
          <button class=\"secondary\" id=\"view-logs\">View Logs</button>
          <button class=\"primary\" id=\"restart-service\">Restart Service</button>
          <button class=\"danger\" id=\"update-service\">Update + Restart</button>
        </div>
        <div class=\"status\" id=\"ops-status\"></div>
      </article>

      <article class=\"card config\">
        <h2>Configuration</h2>
        <div class=\"row two\">
          <div>
            <label for=\"base-url\">Bambuddy Base URL</label>
            <input id=\"base-url\" />
          </div>
          <div>
            <label for=\"api-token\">Bambuddy API Token</label>
            <input id=\"api-token\" />
          </div>
        </div>
        <div class=\"row two\">
          <div>
            <label for=\"printer-uri\">Brother Printer URI</label>
            <input id=\"printer-uri\" />
          </div>
          <div>
            <label for=\"label-size\">Label Size</label>
            <input id=\"label-size\" />
          </div>
        </div>
        <div class=\"row two\">
          <div>
            <label for=\"monitor-identifiers\">Monitored Printer Identifiers</label>
            <textarea id=\"monitor-identifiers\" placeholder=\"comma-separated\"></textarea>
          </div>
          <div>
            <label for=\"monitor-ids\">Monitored Printer IDs</label>
            <textarea id=\"monitor-ids\" placeholder=\"comma-separated\"></textarea>
          </div>
        </div>
        <div class=\"row two\">
          <div>
            <label for=\"poll-seconds\">Poll Interval Seconds</label>
            <input id=\"poll-seconds\" />
          </div>
          <div>
            <label for=\"wait-seconds\">Label Wait Seconds</label>
            <input id=\"wait-seconds\" />
          </div>
        </div>
        <div class=\"btns\">
          <button class=\"primary\" id=\"save-config\">Save Config</button>
        </div>
        <div class=\"status\" id=\"config-status\"></div>
      </article>

      <article class=\"card events\">
        <h2>Recent Labels</h2>
        <div class=\"status\" id=\"events-status\"></div>
        <div style=\"overflow:auto;\">
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
            <tbody id=\"events-body\"></tbody>
          </table>
        </div>
      </article>
      <article class=\"card logs\">
        <h2>System Logs</h2>
        <div class=\"status\" id=\"logs-status\"></div>
        <pre id=\"logs-output\" class=\"mono logs-output\"></pre>
        <div class=\"btns\">
          <button class=\"secondary\" id=\"refresh-logs\">Refresh Logs</button>
        </div>
      </article>
    </section>
  </div>

  <script>
    const ids = {
      baseUrl: document.getElementById('base-url'),
      apiToken: document.getElementById('api-token'),
      printerUri: document.getElementById('printer-uri'),
      labelSize: document.getElementById('label-size'),
      monitorIdentifiers: document.getElementById('monitor-identifiers'),
      monitorIds: document.getElementById('monitor-ids'),
      pollSeconds: document.getElementById('poll-seconds'),
      waitSeconds: document.getElementById('wait-seconds'),
      eventsBody: document.getElementById('events-body'),
      opsStatus: document.getElementById('ops-status'),
      configStatus: document.getElementById('config-status'),
      eventsStatus: document.getElementById('events-status'),
      logsOutput: document.getElementById('logs-output'),
      logsStatus: document.getElementById('logs-status'),
    };

    function setStatus(el, message, level='') {
      el.textContent = message;
      el.className = 'status' + (level ? ` ${level}` : '');
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
      ids.baseUrl.value = v.BAMBUDDY_BASE_URL || '';
      ids.apiToken.value = v.BAMBUDDY_API_TOKEN || '';
      ids.printerUri.value = v.BROTHER_PRINTER_URI || '';
      ids.labelSize.value = v.BROTHER_LABEL_SIZE || '';
      ids.monitorIdentifiers.value = v.PRINTERPRINTER_MONITORED_PRINTER_IDENTIFIERS || '';
      ids.monitorIds.value = v.PRINTERPRINTER_MONITORED_PRINTER_IDS || '';
      ids.pollSeconds.value = v.PRINTERPRINTER_POLL_INTERVAL_SECONDS || '';
      ids.waitSeconds.value = v.PRINTERPRINTER_LABEL_WAIT_SECONDS || '';
      setStatus(ids.configStatus, `Loaded ${payload.env_file_path}`, 'ok');
    }

    async function saveConfig() {
      const values = {
        BAMBUDDY_BASE_URL: ids.baseUrl.value.trim(),
        BAMBUDDY_API_TOKEN: ids.apiToken.value.trim(),
        BROTHER_PRINTER_URI: ids.printerUri.value.trim(),
        BROTHER_LABEL_SIZE: ids.labelSize.value.trim(),
        PRINTERPRINTER_MONITORED_PRINTER_IDENTIFIERS: ids.monitorIdentifiers.value.trim(),
        PRINTERPRINTER_MONITORED_PRINTER_IDS: ids.monitorIds.value.trim(),
        PRINTERPRINTER_POLL_INTERVAL_SECONDS: ids.pollSeconds.value.trim(),
        PRINTERPRINTER_LABEL_WAIT_SECONDS: ids.waitSeconds.value.trim(),
      };

      await api('/admin/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values }),
      });
      setStatus(ids.configStatus, 'Configuration saved. Restart service to apply.', 'ok');
    }

    async function loadEvents() {
      const payload = await api('/admin/events?limit=50');
      ids.eventsBody.innerHTML = '';
      for (const event of payload.items || []) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class=\"mono\">${event.id}</td>
          <td>${fmt(event.printer_name || event.printer_id)}</td>
          <td>${fmt(event.file_name)}</td>
          <td>${fmt(event.started_at)}</td>
          <td>${fmt(event.est_duration_sec)}</td>
          <td>${fmt(event.filament_estimated_g)}</td>
          <td>
            <div class=\"btns\">
              <button class=\"secondary\" data-preview=\"${event.id}\">Preview</button>
              <button class=\"primary\" data-reprint=\"${event.id}\">Reprint</button>
            </div>
          </td>
        `;
        ids.eventsBody.appendChild(tr);
      }
      setStatus(ids.eventsStatus, `Loaded ${payload.count} events`, 'ok');
    }

    async function runAction(path, statusElement, okMessage) {
      const payload = await api(path, { method: 'POST' });
      const suffix = payload && payload.detail ? ` (${payload.detail})` : '';
      setStatus(statusElement, okMessage + suffix, 'ok');
      return payload;
    }

    document.getElementById('refresh-all').addEventListener('click', async () => {
      try {
        await Promise.all([loadConfig(), loadEvents()]);
        setStatus(ids.opsStatus, 'Refreshed.', 'ok');
      } catch (err) {
        setStatus(ids.opsStatus, err.message, 'error');
      }
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
      try {
        await loadLogs();
      } catch (err) {
        setStatus(ids.logsStatus, err.message, 'error');
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
      try {
        await loadLogs();
      } catch (err) {
        setStatus(ids.logsStatus, err.message, 'error');
      }
    });

    document.getElementById('save-config').addEventListener('click', async () => {
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

        const previewRow = document.createElement('tr');
        previewRow.className = 'preview-row';
        previewRow.innerHTML = `<td colspan=\"7\"><img src=\"/admin/label-preview/${previewId}.png?ts=${Date.now()}\" class=\"preview\" alt=\"Label preview\"></td>`;
        row.after(previewRow);
        previewRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }

      if (reprintId) {
        try {
          await api(`/admin/print-event/${reprintId}`, { method: 'POST' });
          setStatus(ids.eventsStatus, `Reprint sent for event ${reprintId}`, 'ok');
        } catch (err) {
          setStatus(ids.eventsStatus, err.message, 'error');
        }
      }
    });

    (async () => {
      try {
        await Promise.all([loadConfig(), loadEvents()]);
      } catch (err) {
        setStatus(ids.opsStatus, err.message, 'error');
      }
    })();
  </script>
</body>
</html>
"""
