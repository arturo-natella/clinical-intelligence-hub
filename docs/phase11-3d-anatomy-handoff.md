# Phase 11: Three.js 3D Anatomy Viewer — Handoff Document

**Date:** 2026-02-28
**Status:** Core JS complete, model pipeline ready, pending Blender run + browser verification

---

## What's Done

### 1. `bodymap3d.js` (~950 lines) — COMPLETE
**Path:** `src/ui/static/js/bodymap3d.js`

The full Three.js viewer controller with:

- **Scene setup:** WebGLRenderer (transparent bg), PerspectiveCamera, OrbitControls with damping
- **Model loading:** GLTFLoader + DracoLoader from CDN, parses `layer_*` named groups
- **4 dissection layers:** skin, muscle, skeleton, organs — toggle visibility with ghosted skin outline
- **Clinical findings as pins:** Severity-colored sprites (red/orange/yellow/blue), positioned at body regions via raycasting
- **Procedural deformation engine:** 65+ medical conditions mapped to physical geometry changes:
  - `_noise3d()` — 3D value noise with smoothstep
  - `_fbm3d()` — Fractal Brownian Motion (layered noise octaves)
  - `_conditionToDeformation()` — maps finding text to deformation profiles
  - `_applyMeshDeformation()` — vertex displacement along normals using fBm
  - `_restoreOriginalGeometry()` / `_clearDeformations()` — reset system
- **Organ damage visualization:** Color tinting + emissive glow based on severity
- **Pulsing animation:** Organs with cardiac/respiratory conditions pulse in render loop
- **Gender model switching:** `/api/demographics` auto-detect, manual ♂/♀ toggle
- **WebGL fallback:** Degrades to 2D viewer (BodyMap2DFallback) if WebGL unavailable
- **Region mapping:** Same keyword-based `regionMapping` from original prototype for data filtering

### 2. `prepare_models.py` (~650 lines) — COMPLETE
**Path:** `src/ui/static/models/prepare_models.py`

Blender headless processing script with two modes:

**BodyParts3D mode** (primary):
- Detects FJ-prefixed OBJ files automatically
- Hard-coded FJ→target name map for ~200 critical structures (heart, lungs, liver, kidneys, brain, skeleton, etc.)
- Parses `partof_element_parts.txt` for remaining ~1,000 FJ IDs
- Joins multiple FJ meshes into single named organs (e.g., 24 heart meshes → 1 `organ_heart`)
- Gender filtering (prostate for male, uterus/ovaries for female)
- Decimation for high-poly meshes, Draco-compressed GLB export

**Z-Anatomy mode** (secondary):
- Opens .blend files, uses collection hierarchy for layer assignment
- French + English name support
- Pattern-based fallback classification

**Usage:**
```bash
# Install Blender first
brew install --cask blender

# Run pipeline
/Applications/Blender.app/Contents/MacOS/Blender --background \
    --python src/ui/static/models/prepare_models.py -- \
    --source src/ui/static/models/bodyparts3d_raw_partof/partof_BP3D_4.0_obj_99 \
    --gender male \
    --mapping src/ui/static/models/partof_element_parts.txt
```

### 3. HTML/CSS Updates — COMPLETE
**Path:** `src/ui/static/index.html`, `src/ui/static/styles.css`

- Three.js import map (three, OrbitControls, GLTFLoader, DracoLoader from unpkg CDN)
- 3D canvas container with toolbar (layer buttons, gender toggle, reset view)
- 2D fallback section (hidden when WebGL works)
- Tooltip overlay, loading spinner, pin pulse animation CSS

### 4. `app.js` Integration — COMPLETE
**Path:** `src/ui/static/app.js`

- Old `BodyMap` renamed to `BodyMap2DFallback` (preserved for fallback)
- `BodyMap3D.init('bodymap-canvas-container')` called on Body Map view activation
- Layer button event handlers wired to `BodyMap3D.setLayer()`
- Gender toggle calls `BodyMap3D.setGender()`

### 5. `app.py` Endpoint — COMPLETE
**Path:** `src/ui/app.py`

- `/api/demographics` endpoint returns `biological_sex` and `birth_year`
- `/models/<path>` static file serving for GLB models

### 6. Tests — COMPLETE
**Path:** `tests/test_phase11.py` (27 tests, all passing)

Covers: file existence, Three.js imports, BodyMap3D controller structure, API integration, deformation engine, deformation profiles, animation loop, WebGL fallback, layer controls, pin system.

---

## What's Downloaded

### BodyParts3D v4.0 (PART-OF tree)
**Path:** `src/ui/static/models/bodyparts3d_raw_partof/partof_BP3D_4.0_obj_99/`
- 1,258 OBJ files named with FJ-prefix IDs (e.g., FJ2417.obj = heart mesh)
- Male anatomy only (BodyParts3D v4.0 is male-only)
- CC BY-SA 2.1 Japan license

### Element Parts Mapping
**Path:** `src/ui/static/models/partof_element_parts.txt`
- 17,944 rows mapping FJ IDs → FMA concepts → English anatomical names
- Downloaded from: `https://dbarchive.biosciencedbc.jp/data/bodyparts3d/LATEST/partof_element_parts.txt`

---

## What's NOT Done (Next Steps)

### Step 1: Install Blender
```bash
brew install --cask blender
```
Blender is NOT currently installed on this Mac.

### Step 2: Run the Blender Pipeline
```bash
cd /Users/owner/Desktop/Tech\ Tools/MedPrep/src/ui/static/models

/Applications/Blender.app/Contents/MacOS/Blender --background \
    --python prepare_models.py -- \
    --source ./bodyparts3d_raw_partof/partof_BP3D_4.0_obj_99 \
    --gender male \
    --mapping ./partof_element_parts.txt
```

This will produce `male_anatomy.glb` in the models directory.

**Expected output structure in the GLB:**
```
Root
├── layer_skin (1 mesh: skin_body)
├── layer_muscle (~15 meshes: pectoralis, obliques, etc.)
├── layer_skeleton (~30 meshes: skull, spine, ribs, limb bones)
└── layer_organs (~40 meshes: heart, lungs, liver, kidneys, brain, etc.)
```

### Step 3: Verify in Browser
```bash
cd /Users/owner/Desktop/Tech\ Tools/MedPrep
python -m src.ui.app
# Open http://localhost:5000 → Body Map tab
```

**Verify:**
- [ ] 3D canvas renders with loaded model
- [ ] OrbitControls: orbit, zoom, pan work
- [ ] Layer buttons toggle visibility
- [ ] Gender toggle button works
- [ ] Clinical findings appear as colored pins
- [ ] Hovering a pin shows tooltip
- [ ] Clicking a mesh region opens findings panel
- [ ] Reset View animates camera back
- [ ] 2D fallback works if WebGL is disabled

### Step 4: Female Model (Future)
BodyParts3D v4.0 is male-only. For a female model:
- Option A: Z-Anatomy has female .blend files (download from Google Drive, run in Z-Anatomy mode)
- Option B: Clone male model, remove prostate, add placeholder uterus/ovaries meshes
- Option C: Wait for BodyParts3D to release female model data

---

## Key File Map

| File | Lines | Purpose |
|------|-------|---------|
| `src/ui/static/js/bodymap3d.js` | ~950 | Three.js viewer + deformation engine |
| `src/ui/static/models/prepare_models.py` | ~650 | Blender pipeline (FJ→GLB) |
| `src/ui/static/models/partof_element_parts.txt` | 17,944 | FJ ID → anatomical name mapping |
| `src/ui/static/index.html` | - | 3D canvas + toolbar HTML |
| `src/ui/static/styles.css` | - | Canvas + tooltip + animation CSS |
| `src/ui/static/app.js` | - | BodyMap3D integration |
| `src/ui/app.py` | - | /api/demographics + /models/ |
| `tests/test_phase11.py` | 27 tests | Phase 11 test coverage |

---

## Deformation Profiles Reference

The `deformationProfiles` object in bodymap3d.js maps 65+ medical conditions to physical geometry parameters:

| Category | Conditions | Effect |
|----------|-----------|--------|
| Enlargement | cardiomegaly, hepatomegaly, splenomegaly, goiter | Scale up 1.2-1.6x |
| Surface Roughness | cirrhosis, fibrosis, interstitial lung disease | fBm noise displacement |
| Shrinkage | atelectasis, renal atrophy, cerebral atrophy | Scale down 0.5-0.8x |
| Nodules/Masses | lung nodule, thyroid nodule, renal mass, liver mass | Localized bulge with noise |
| Inflammation | pericarditis, hepatitis, nephritis, pancreatitis | Slight scale + fine noise |
| Cardiac | heart failure, afib, cardiomyopathy | Scale + pulse animation |
| Respiratory | COPD, emphysema, pneumothorax, pneumonia | Over-inflation or collapse |
| Renal | polycystic kidney, hydronephrosis, chronic kidney | Scale + cyst-like noise |
| Hepatic | fatty liver, hepatocellular carcinoma, portal hypertension | Scale + surface texture |
| Neurological | brain tumor, hydrocephalus, meningioma | Localized mass + pressure |

Each profile has: `scale: [x,y,z]`, `noise: amplitude`, `freq: noise_frequency`, `pulse: animation_intensity`

---

## Architecture Notes

### How Deformation Works
1. Findings loaded from `/api/diagnoses`, `/api/imaging`, `/api/labs`, `/api/flags`
2. Each finding's text scanned against `regionMapping` keywords → mapped to body region
3. Region → organ mesh name lookup
4. Finding text → `_conditionToDeformation()` → deformation profile
5. `_applyMeshDeformation()` displaces vertices along normals using fBm noise + scaling
6. Original positions stored in `mesh.userData.originalPositions` for reset
7. Cardiac/respiratory profiles get `pulse > 0` → animated via render loop

### How Layers Work
GLB contains named groups: `layer_skin`, `layer_muscle`, `layer_skeleton`, `layer_organs`
- Active layer: fully visible
- Skin layer on deeper views: ghosted at 15% opacity (spatial context)
- Switching layers clears deformations and re-applies for the new layer

### Three.js CDN Strategy
```
unpkg.com/three@0.170.0/build/three.module.js
unpkg.com/three@0.170.0/examples/jsm/controls/OrbitControls.js
unpkg.com/three@0.170.0/examples/jsm/loaders/GLTFLoader.js
unpkg.com/three@0.170.0/examples/jsm/loaders/DRACOLoader.js
```
~160KB gzipped total. DracoLoader decoder also from CDN.

---

## Data Sources & Licenses

| Source | License | What we use |
|--------|---------|-------------|
| [BodyParts3D v4.0](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html) | CC BY-SA 2.1 JP | 1,258 OBJ meshes (male) |
| [Z-Anatomy](https://github.com/LluisV/Z-Anatomy) | CC BY-SA 4.0 | Future: male + female .blend |
| [NIH 3D Print Exchange](https://3dprint.nih.gov/) | Public Domain | Future: supplementary organs |
| [Three.js](https://threejs.org/) | MIT | WebGL renderer |

Attribution required: "BodyParts3D, (c) The Database Center for Life Science licensed under CC Attribution-Share Alike 2.1 Japan"
