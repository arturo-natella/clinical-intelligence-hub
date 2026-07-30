# System Health Panel — Design

**Date:** 2026-07-30 · **Approved:** dashboard-card placement, six checks, plain language.
**Origin:** P8 (HANDOFF). The 2026-04-15 incident — 1,593 silent MedGemma 404s because the
model wasn't installed — must never be invisible again.

## Endpoint

`GET /api/system-health` in `src/ui/app.py`. Returns:

```json
{
  "checked_at": "<iso>",
  "overall": "ok" | "warn" | "fail",
  "checks": [
    {"id": "ollama",          "label": "AI engine (Ollama)",        "status": "ok|fail",      "detail": "...", "hint": "..."},
    {"id": "medgemma_text",   "label": "Text model (MedGemma 27B)", "status": "ok|fail|unknown", ...},
    {"id": "medgemma_vision", "label": "Image model (MedGemma 4B)", "status": "ok|warn|unknown", ...},
    {"id": "disk",            "label": "Disk space",                "status": "ok|warn|fail", ...},
    {"id": "privacy",         "label": "Privacy shield (Presidio)", "status": "ok|warn",      ...},
    {"id": "vault",           "label": "Records vault",             "status": "ok|warn",      ...}
  ]
}
```

Rules:
- Every check individually try/excepted → `unknown` status with a generic hint; the
  endpoint never raises. No patient data is read anywhere in the handler.
- Ollama daemon + model checks share one bounded `ollama.list()` call (≈2 s timeout).
  Daemon down ⇒ ollama `fail`, both model checks `unknown` ("Can't check until the
  AI engine is running").
- Model matching mirrors `text_extractor._check_ollama`: accept exact, `:latest`,
  and bare-name variants.
- Disk: `shutil.disk_usage(DATA_DIR)`; warn < 50 GB free, fail < 10 GB.
- Privacy: `importlib.util.find_spec("presidio_analyzer")` — missing ⇒ `warn`
  ("Cloud analysis stays off until it's installed"), never blocks local work.
- Vault: locked (no in-memory passphrase) ⇒ `warn` "Locked — unlock to restore
  your saved profile"; unlocked ⇒ `ok`.
- Missing vision model is `warn` (image passes skip gracefully); missing text
  model is `fail` (analysis is pointless without it).
- `overall` = worst status across checks (fail > warn > ok; `unknown` counts as warn).
- Results cached in-process for 15 s (`time.monotonic`), bypassed with `?refresh=1`.

## Card

`System Status` `.dash-card` appended to the dashboard charts grid in
`index.html` (`id="dash-system-health"`), rendered by `App.renderSystemHealth`:

- One row per check: colored dot (forest `ok` / honey `warn`+`unknown` / crimson
  `fail`) + label + short detail ("Running", "Installed", "512 GB free", "Locked").
- Hint line in muted text under the row only when status ≠ ok, phrased for a
  non-technical reader ("Start the Ollama app, then press Refresh").
- Header row: overall dot + "All systems ready" / "Needs attention", a Refresh
  button (`?refresh=1` refetch), and "Checked just now" stamp.
- Fetch failure renders "Couldn't check your system — press Refresh to try again."
- Red appears only for analysis-blocking states, honoring the accent discipline.

## Wiring

Fetched inside `App.loadDashboard()` alongside existing dashboard calls; no polling.

## Tests (`tests/test_system_health.py`)

1. Contract: six known ids, statuses within enum, endpoint 200 and never raises
   (all dependencies monkeypatched to explode → every check `unknown`/`fail`, still 200).
2. Disk thresholds: injected byte values hit ok/warn/fail boundaries.
3. Model detection: monkeypatched `ollama.list` — present, absent, `:latest` variant.
4. Daemon down: ollama check `fail`, model checks `unknown`, overall `fail`.
5. Vault: locked vs unlocked statuses.
6. Cache: second call within window returns cached `checked_at`; `?refresh=1` busts.
