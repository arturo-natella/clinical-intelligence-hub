# Body Map Removal — Design

**Date:** 2026-07-30
**Status:** Implemented
**Decision:** Remove the 3D anatomy viewer entirely.

---

## Why

The body map was built to let a non-technical patient *see* their conditions on a
body. Roughly four months went into it: a Blender export pipeline, a multi-atlas
hybrid (Z-Anatomy 6,322 meshes + 74 NIH Human Reference Atlas organ GLBs), HDR
environment lighting, SSAO, and a 4,893-line Three.js viewer.

It was removed for one reason that no amount of further work could fix, plus two
defects that made it actively misleading.

### 1. The goal was unreachable by construction

No open atlas is *this patient's* anatomy. Z-Anatomy and NIH HRA are both derived
from Visible Human cadaver data — a stranger's body. Producing a map of the actual
patient would require medical-grade volumetric imaging of that patient, segmented
per-organ. That imaging does not exist for this user and is not obtainable.

Every hour spent on render fidelity therefore bought a more beautiful picture of
someone else. The fidelity chase had no finish line because the target was
mis-specified, not because the models were poor.

### 2. The deformation engine fabricated clinical content

`deformationProfiles` mapped 65+ condition keywords to geometry changes, and
`_conditionToDeformation()` selected among matches **by visual drama**:

```javascript
var impact = prof.noise + Math.abs(prof.scale[0] - 1.0) * 0.1;
if (impact > bestPriority) { bestPriority = impact; bestMatch = prof; }
```

When no keyword matched, it deformed anyway on severity alone. A record reading
"hepatomegaly" rendered a generic liver at 1.30x with fBm noise plus a GPU shader
adding bumps and discoloration. Nothing in the patient's chart stated that size or
texture — the numbers were chosen because they read dramatically.

The UI labelled this output "Current State" with a "Show Healthy" toggle, framing
procedurally generated fiction as a picture of the patient's body, with no
disclaimer anywhere in the view.

This directly violated the project's first principle (CLAUDE.md): *"Clinical
provenance on everything."* The body map was the only surface in the tool that
asserted clinical facts with no source, and the most emotionally persuasive one.

### 3. Region mapping was substring matching without word boundaries

`_textToRegion()` returned the first region whose keyword appeared anywhere in the
finding text. Verified behaviour against real clinical phrases:

| Finding | Pinned to | Should be | Cause |
|---|---|---|---|
| heart failure | head | chest | "h**ear**t" contains `ear` |
| right knee osteoarthritis | left-leg | right leg | `left-leg` key precedes `right-leg` |
| right shoulder rotator cuff tear | head | right arm | "t**ear**" contains `ear` |
| clear cell renal carcinoma | head | abdomen | "cl**ear**" contains `ear` |
| linear atelectasis | head | chest | "lin**ear**" contains `ear` |

`left-arm` and `right-arm` carried identical keyword lists (likewise the legs), so
`Object.keys` iteration order silently decided laterality — every right-sided
finding landed on the left. A heart-failure marker on the skull is not a rough
approximation; it is misinformation shown to a patient before a cardiology visit.

### 4. It could not ship

`.gitignore` ignores `models/`. The 1.4 GB of anatomy assets existed only on the
author's machine — `git ls-files` showed zero tracked GLBs. Any clone of this
BSD-licensed repository fell through the load cascade to placeholder primitives.
The flagship visual feature was a local-only artifact.

---

## Alternatives considered

**Reframe as a navigation surface (rejected by user).** Keep the atlas, delete the
deformation engine, replace keyword matching with the existing SNOMED/LOINC coding,
relabel from "Current State" to "Reference anatomy". The body becomes a spatial
index into cited findings rather than a portrait. Rejected because it still ships
1.4 GB to render a stranger, for navigation the sidebar already provides.

**Continue enhancing fidelity (rejected).** Wire in AnatomyTool GLBs, add hover
tooltips, chase Zygote-quality rendering. Rejected: most expensive option, touches
neither correctness defect, and a prettier wrong answer is worse than a plain one.

---

## What was removed

| Item | Detail |
|---|---|
| `src/ui/static/js/bodymap3d.js` | 4,893 lines |
| `src/imaging/volumetric_renderer.py` | DICOM→GLB pipeline, zero consumers |
| `tests/test_phase11.py` | 39 tests, ~35 body-map specific |
| `tests/test_bodymap_loading.py` | whole file |
| `src/ui/static/assets/*.png` | 5 anatomy images (2D fallback), directory now gone |
| `src/ui/static/models/studio_small_08_2k.hdr` | 5.9 MB HDR env map, the only tracked model asset |
| `docs/phase11-3d-anatomy-handoff.md` | superseded February handoff |
| `index.html` | sidebar entry, `#view-bodymap` block, script tag, **Three.js importmap + loader** |
| `app.js` | `bodymap` view loader, `initBodyMap3D()`, `BodyMap2DFallback` (120 lines) |
| `styles.css` | 420 lines |
| `app.py` | `/models/<path:filename>` and `/assets/<path:filename>` routes |
| Local disk | 1.4 GB of atlas data (NIH HRA 769 MB, Z-Anatomy 376 MB, BodyParts3D 210 MB, z-anatomy-hq 37 MB, AnatomyTool 20 MB) |

### Removing Three.js was a side benefit

`bodymap3d.js` was the sole consumer of Three.js, which `index.html` loaded from
the jsdelivr CDN on every page load. For a local-first tool whose premise is that
nothing leaves the machine, the dashboard was making an external network request
every time it opened. The UI is now free of that dependency.

---

## What was preserved

- **Differential Dx entry point.** The `SnowballDx.toggle()` button lived *inside*
  the body map toolbar and was its only entry point app-wide. Relocated to the
  dashboard Quick Actions card. Guarded by a test.
- **Blender pipeline scripts** → `docs/archive/body-map-pipeline/` (104 KB:
  `prepare_models.py`, `export_zanatomy.py`, `convert_bodyparts3d.py`,
  `download_hra.py`, `download_hra.sh`). These were the only non-re-downloadable
  content in the 1.4 GB tree.
- **`docs/3d-anatomy-journey.md`** — the research log, including the licensing
  survey of every open 3D anatomy atlas and the "diagnose before prescribe"
  lesson. Kept with a closing header.
- **`/api/demographics`** — generic profile endpoint, not body-map specific.
- **`test_js_route_exists` / `test_css_has_amaru_tokens`** — moved from
  `test_phase11.py` into `tests/test_static_ui_contract.py`.

### Verified as unaffected

- Plain-English translation: `CLINICAL_GLOSSARY`, `getClinicalGlossaryEntry()`,
  `plainLanguageHtml()` all live in `app.js`. The body map was a consumer.
- Cross-disciplinary findings: still surfaced by `crossdisc_graph.js`, which has
  its own contract test.
- Symptom Landscape: independent file, view, endpoint, and report section.
- Word report: had no body map section.

---

## Regression guard

`tests/test_static_ui_contract.py` asserts no `bodymap` reference survives in
`index.html`, `app.js`, or `styles.css`; that `bodymap3d.js` does not exist; that
the Three.js CDN import is gone; and that the Differential Dx entry point is still
reachable.
