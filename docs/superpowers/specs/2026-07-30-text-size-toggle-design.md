# Text Size Toggle — Design

**Date:** 2026-07-30 · **Origin:** P8 (HANDOFF). For the target reader (the
user's friend: non-technical, ~60), an in-app control beats teaching browser zoom.

## Mechanism

The stylesheet is px-based throughout (~180 font-size rules), so `rem` scaling
cannot work without rewriting every rule. Instead: CSS `zoom` on the root
element — standardized (Interop 2024), scales text, charts (vector SVG), and
click targets together, which serves this reader better than text-only scaling.

- Steps: **Standard 1.0 · Large 1.15 · Extra large 1.3** (cycle).
- Persistence: `localStorage["medprep_text_scale"]` — a preference, no PHI.
- Pre-paint application: tiny inline `<script>` in `<head>` reads localStorage
  and sets `document.documentElement.style.zoom` before first render (no flash
  of small text). Values outside the whitelist fall back to 1.0.

## Control

A `sidebar-item` button in the sidebar's bottom section (its own bordered row
above Settings), matching the Collapse/Settings pattern: SVG icon + label
`Text Size: Standard|Large|Extra large`. Click cycles to the next step,
applies zoom immediately, persists, and updates both the label and
`aria-label` ("Text size: Large — press to change"). Collapsed sidebar hides
the label like every other item; the aria-label keeps the button named.

## Code

- `index.html`: head pre-paint script + sidebar button.
- `app.js`: `TEXT_SCALE_STEPS`, `App.applyTextScale(scale)`,
  `App.cycleTextSize()`; init syncs the label to the stored value.
- No backend. No new endpoint.

## Tests

`tests/test_text_scale.py` — static contract (repo pattern: grep static
assets): index.html has the pre-paint script guarding with the whitelist and
the button; app.js defines the storage key, the three steps, and cycle/apply
functions. Runtime behavior (cycle, persist across reload, layout at 1.3)
verified live in the browser.
