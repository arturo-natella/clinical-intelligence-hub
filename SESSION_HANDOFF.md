# MedPrep 3D Anatomy Viewer — Session Handoff

## Project Location
`/Users/owner/Desktop/Tech Tools/MedPrep`

## What This Is
A **Clinical Intelligence Hub** — a medical dashboard for a non-technical ~60-year-old friend to explore their health data. The **3D Interactive Anatomy Viewer** (Body Map) uses Z-Anatomy data (CC BY-SA 4.0) rendered with Three.js to achieve ZygoteBody-level fidelity.

## Architecture Overview

### Stack
- **Backend**: Python/Flask (`src/ui/app.py`), serves on port 5050
- **Frontend**: Vanilla JS + Three.js (no framework), SPA with sidebar navigation
- **3D Model**: `src/ui/static/models/male_anatomy_full.glb` (28.5MB, Draco compressed, 11,356 meshes)
- **Export Pipeline**: Blender + `export_zanatomy.py` converts Z-Anatomy `.blend` → tagged GLB

### Key Files
| File | Purpose |
|------|---------|
| `src/ui/static/js/bodymap3d.js` | Main 3D viewer controller (all layer/model/render logic) |
| `src/ui/static/models/export_zanatomy.py` | Blender export script: Z-Anatomy → multi-layer GLB |
| `src/ui/static/models/z_anatomy/Z-Anatomy/Startup.blend` | Z-Anatomy Blender source (306MB) |
| `src/ui/static/index.html` | SPA shell with Body Map section |
| `src/ui/static/styles.css` | All styling |
| `src/ui/app.py` | Flask backend with `/api/demographics` endpoint |
| `.claude/launch.json` | Preview server config (name "medprep", port 5050) |

### 3D Model Layer System
The GLB contains meshes tagged with name prefixes by the export script:
- `SKEL__` → skeleton (2,260 meshes)
- `MUSC__` → muscle (1,951 meshes)
- `ORGN__` → organs (803 meshes)
- `VASC__` → vasculature (696 meshes)
- `NERV__` → nervous (989 meshes)
- `SKIN__` → skin (669 meshes)

The JS parser reads these prefixes to assign meshes to layers. Fallback: ancestor hierarchy inheritance for untagged geometry.

### Layer Rendering
- **Active layer**: fully opaque
- **Skin on non-skin layers**: ghost overlay (MeshBasicMaterial, opacity 0.06)
- **Other inactive layers**: hidden
- **Text labels**: hidden via `_isGlyph` flag + invisible material swap

---

## What Was Done This Session

### 1. Fixed Text Labels (Region/Category Headers)
**Problem**: Z-Anatomy 3D text labels ("REGIONS OF HEAD", "BRACHIAL REGION", "MUSCLES OF THORAX") were visible floating around the body on Skin and Muscle layers.

**Root Cause**: Z-Anatomy FONT objects get converted to meshes by the GLTF exporter. They end up in layers via ancestor inheritance but lack export prefixes (export script only tags Blender MESH objects, not FONT objects).

**Fix** (bodymap3d.js, after line ~597): Geometric flatness filter — meshes that are:
1. In a layer but have NO layer prefix (unprefixed = FONT-converted text)
2. Geometrically flat (bounding box min/max dimension ratio < 5%)

These get flagged `_isGlyph = true`, hidden with invisible material, and removed from the layer array. The `setLayer()` function has a guard that keeps `_isGlyph` meshes hidden on all layer switches.

**Important**: The filter ONLY applies to unprefixed meshes. Prefixed flat meshes (thin ligaments, tendons, fascia with ratios of 0.01–0.03) are real anatomy and are preserved.

### 2. Fixed Model Centering
**Problem**: Body was offset to the right (wrapper x=0.66) instead of centered in viewport.

**Root Cause**: Double-counting bug. The refit code computed the anatomy bounding box using `matrixWorld` which already included the initial centering offset from line ~470. Then it subtracted this world-space center from the wrapper position, double-counting the offset.

**Fix** (bodymap3d.js, line ~662): Reset `wrapper.position` to `(0,0,0)` and call `updateMatrixWorld(true)` BEFORE computing the anatomy bounding box. This gives a clean local-space center that can be correctly negated for centering.

### 3. Earlier Fixes (From Previous Session)
- **Refit bounding box**: Uses per-mesh `geometry.computeBoundingBox()` instead of `expandByObject()` to exclude text glyph children
- **Glyph regex filter** (`glyphRe`): Catches individual character glyphs ending in `_g` and compound suffixes like `systemg`, `organsg`
- **Glyph-hiding pass**: After layer building, traverses scene and swaps materials to invisible on glyphRe-matching meshes
- **Glyph guard in setLayer()**: Keeps `_isGlyph` meshes hidden regardless of active layer
- **ResizeObserver**: Catches SPA visibility changes (container goes from 0 → visible width)
- **Scale correction**: If anatomy-only maxDim < target height, scales up with correction factor

---

## Current State
- Preview server running on port 5050 (`medprep` in `.claude/launch.json`)
- All 6 layers render correctly, centered, no text labels
- Gender toggle UI exists (♂/♀ button), JS infrastructure for female model loading is complete
- Fallback chain: tries `{gender}_anatomy_full.glb` → `{gender}_anatomy.glb` → male variants → procedural placeholder

---

## Pending Tasks

### 1. Female Model (User Requested)
**Status**: Infrastructure 100% complete, only needs the GLB file generated.

**What exists**:
- Gender toggle button in UI (`#gender-toggle`, line 369 of index.html)
- `loadModel(gender)` with fallback chain (bodymap3d.js lines 388-427)
- `_filterOrgansForGender()` hides male/female-specific organs (lines 816-830)
- Procedural placeholder with gender-specific anatomy as ultimate fallback
- `/api/demographics` endpoint returns `biological_sex` for auto-detection

**What's needed**:
1. Add `--gender` parameter to `export_zanatomy.py` with organ filtering (male-only: prostate, testes, seminal vesicles, epididymis, vas deferens; female-only: uterus, ovaries, fallopian tubes)
2. Run: `blender --background "src/ui/static/models/z_anatomy/Z-Anatomy/Startup.blend" --python export_zanatomy.py -- --output "src/ui/static/models/female_anatomy_full.glb" --gender female`
3. Test gender toggle in browser

**Note**: Z-Anatomy's `Startup.blend` contains BOTH male and female anatomy. The export script needs to filter by gender. The existing `prepare_models.py` already has gender filtering logic that can be referenced (lines 622-711).

### 2. Demo Data Toggle (User Requested)
For previewing the app with other people — toggles between real patient data and demo/sample data.

---

## Technical Gotchas

### SPA Timing
Body Map is a SPA section. The canvas container has `width: 0` when not visible. The `init()` function runs when the section becomes visible via sidebar click. A `ResizeObserver` catches the container becoming visible and triggers resize.

### WebGL Capture
The Three.js renderer uses `alpha: true` and `preserveDrawingBuffer: false`. The `preview_screenshot` tool can't capture the WebGL canvas (shows blank). Must test in actual Chrome browser or use the Chrome MCP extension.

### Text Label Detection
Two layers of defense:
1. `glyphRe` regex catches individual glyph meshes (character-level: `_g` suffix, compound: `systemg`, etc.)
2. Flatness filter catches FONT-converted text labels (no prefix + flat bounding box)

Both mark meshes as `_isGlyph` and use invisible material swap (not `visible=false`, which would hide children).

### Centering Math
The wrapper position must be reset to `(0,0,0)` before computing the anatomy bounding box for centering. Otherwise the world-space center includes the prior offset, and subtracting it double-counts.

---

## Z-Anatomy Export Command (Reference)
```bash
/Applications/Blender.app/Contents/MacOS/Blender --background \
    "/Users/owner/Desktop/Tech Tools/MedPrep/src/ui/static/models/z_anatomy/Z-Anatomy/Startup.blend" \
    --python "/Users/owner/Desktop/Tech Tools/MedPrep/src/ui/static/models/export_zanatomy.py" -- \
    --output "/Users/owner/Desktop/Tech Tools/MedPrep/src/ui/static/models/male_anatomy_full.glb" \
    --max-tris 4000000
```

## User Preferences
- Bold, no hedging. Default to action.
- Never defer identified work.
- Non-technical end user — the friend exploring their medical records is ~60 years old.
- Values working software over perfect plans.
