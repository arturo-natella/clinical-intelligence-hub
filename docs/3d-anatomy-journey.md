# 3D Anatomy Viewer — Where We Started, Where We're Going

**Project:** MedPrep Clinical Intelligence Hub
**Date:** 2026-03-03

---

## Where We Started

### The Vision
Build a ZygoteBody-level 3D interactive anatomy viewer inside MedPrep — a Clinical Intelligence Hub designed for a non-technical ~60-year-old friend to visually explore their medical conditions. Not a simplified diagram. Real anatomy. Real detail. Clinically meaningful.

### Phase 11 Baseline (Feb 28)
We had a working Three.js viewer (`bodymap3d.js`, ~950 lines) with:

- **4 layers:** skin, muscle, skeleton, organs
- **BodyParts3D source:** 1,258 OBJ files, but only **92 meshes** (7%) actually exported into the GLB
- **5 MB GLB** — missing arteries, veins, nerves, most muscles, many organs
- **Procedural deformation engine:** 65+ medical conditions mapped to geometry changes (fBm noise displacement, scaling, pulsing)
- **Clinical pin system:** Severity-colored sprites at body regions
- **White skin bug:** Overexposed from tone mapping
- **Dead toolbar buttons:** Click handlers not wired up
- **No zoom controls**
- **Female model:** Fell back to placeholder primitive shapes (spheres/cylinders)
- **No vasculature or nervous system** at all

### The Problem
BodyParts3D v4.0 had 1,258 files but was missing critical systems. Only 9 muscles (out of 600+). Zero nerves. Zero labeled arteries/veins. The 92-mesh GLB looked like a medical school reject compared to ZygoteBody's thousands of structures.

---

## What We Built

### Infrastructure Fixes
| Fix | What Changed |
|-----|-------------|
| White skin | Switched to `MeshPhysicalMaterial` with subsurface scattering, disabled env map washout |
| Toolbar buttons | Wired click handlers for all layer buttons, gender toggle, reset view |
| Zoom controls | Added zoom in/out buttons with clamped distance animation |
| Female fallback | Implemented `_filterOrgansForGender()` — hides male-specific organs on female view |

### The Z-Anatomy Breakthrough
Discovered **Z-Anatomy** — an open-source anatomical atlas built on BodyParts3D but massively expanded:

| Metric | BodyParts3D (old) | Z-Anatomy (new) |
|--------|-------------------|------------------|
| Structures | 1,258 | **7,000+** |
| Meshes | 92 exported | **3,805 exported** |
| Arteries/Veins | 0 | **947 (curve-based)** |
| Nerves | 0 | **Hundreds** |
| Muscles | 9 | **898** |
| Bones | ~30 | **984** |
| Pre-colored | No | **Yes — 38 anatomical material types** |
| License | CC BY-SA 2.1 JP | CC BY-SA 4.0 |

### Blender Export Pipeline (`export_zanatomy.py`)
Built a custom Blender 5.0.1 headless pipeline that:

1. Opens the 307MB Z-Anatomy `.blend` file
2. Maps 8 Z-Anatomy collections → 6 viewer layers (skin, skeleton, muscle, organs, vasculature, nervous)
3. Converts 947 curves (blood vessels, nerves) → tube meshes using depsgraph evaluation
4. Assigns anatomically-correct colors from Principled BSDF shader nodes
5. Builds layer hierarchy with named parent empties
6. Exports Draco-compressed GLB

**Challenges solved:**
- `bpy.ops.object.convert()` doesn't work in Blender background mode → used `depsgraph` evaluation
- Deleted curve objects left stale `StructRNA` references → added `live_objects()` filter
- `export_colors` parameter removed in Blender 5.0.1 → removed (materials carry the colors)
- Curve-converted meshes not tracked in layer lists → fixed list aliasing bug

### 6-Layer Viewer System
Expanded from 4 layers to 6:

```
layer_skin          — Body surface regions (494 meshes)
layer_muscle        — All skeletal muscles, tendons, fascia (898 meshes)
layer_skeleton      — All bones, ligaments, joint capsules (984 meshes)
layer_organs        — Visceral organs, glands, GI tract (251 meshes)
layer_vasculature   — Arteries + veins (curve→mesh converted)
layer_nervous       — Nerves + sense organs
```

**Viewer JS updates:**
- Hierarchy-based layer parsing (Z-Anatomy uses parent empties, not name prefixes)
- UUID-based `setLayer()` using pre-parsed layer dictionaries
- Model loading cascade: `full → basic → male_full → male_basic → placeholder`
- Ghosted skin at 8% opacity on deeper layers for spatial context

---

## Where We Are Now (March 3)

### Working
- **Skin layer**: 494 meshes with realistic PBR skin material — renders beautifully
- **Skeleton layer**: 984 bones — skull, ribcage, pelvis, every finger bone visible
- **Muscle layer**: 898 muscles showing through ghosted skin
- **Organs layer**: Lungs (pink), liver (amber), trachea, stomach, intestines — color-coded
- **Vessels layer**: Heart chambers visible, but arteries/veins sparse (bug fix in progress)
- **Nerves layer**: 459 meshes present (untested visually yet)
- **All 6 toolbar buttons** wired and working with active state highlighting
- **OrbitControls**: Rotate, zoom, pan all functional
- **9.4 MB GLB** with Draco compression (was 5 MB with 92 meshes, now 3,805 meshes)

### In Progress
- **Re-exporting GLB** with vasculature fix — curve-converted vessels weren't being tracked in layer assignments (list aliasing bug). Fix applied, Blender re-running now.

### Known Issues
- Nerves button visible but not yet visually verified
- Skin ghost overlay on muscle layer creates a blueish tint (cosmetic, functional)
- Button active state CSS could be more prominent for some layers

---

## Where We're Going

### Immediate Next Steps
1. **Verify vasculature** — After re-export, confirm arteries (red) and veins (blue) render throughout the body
2. **Verify nervous system** — Click Nerves, confirm nerve pathways (yellow) visible
3. **Demo data toggle** — Add a button to load sample clinical findings so non-technical users can see the viewer with conditions visualized (colored pins, organ deformations, damage tinting)

### Future Enhancements
| Feature | Description |
|---------|-------------|
| **Female model** | Z-Anatomy has female .blend files — run same pipeline for `female_anatomy_full.glb` |
| **Organ hover tooltips** | Hover any mesh → show anatomical name + any clinical findings |
| **Click-to-inspect** | Click an organ → side panel shows related diagnoses, labs, imaging |
| **Condition deformations** | The 65+ deformation profiles (cardiomegaly, cirrhosis, etc.) need testing with the new high-res meshes |
| **Before/After toggle** | Show healthy vs. current state side-by-side |
| **Search** | Type "liver" → camera zooms to liver, highlights it |
| **Cross-section mode** | Clip plane to see internal structures in context |
| **Annotations** | Doctor or patient can pin notes to specific anatomy |

### The Big Picture
This is a **personal medical intelligence system**. The 3D body map isn't just a pretty visualization — it's the spatial anchor for all clinical data. Every diagnosis, lab result, imaging finding, and medication maps to a region of the body. When you click on the liver, you see hepatic findings. When you hover over the heart, you see cardiac history.

The goal: A 60-year-old opens this app before a doctor visit and **understands their body** — what's wrong, where it is, how it connects. Not through medical jargon, but through a visual, interactive, anatomically-accurate model of themselves.

---

## File Map

| File | Lines | Purpose |
|------|-------|---------|
| `src/ui/static/js/bodymap3d.js` | ~1,050 | Three.js viewer + deformation engine |
| `src/ui/static/models/export_zanatomy.py` | ~510 | Z-Anatomy → GLB pipeline (Blender 5.0.1) |
| `src/ui/static/models/male_anatomy_full.glb` | 9.4 MB | Full Z-Anatomy export (3,805 meshes) |
| `src/ui/static/models/male_anatomy.glb` | 5 MB | Original BodyParts3D export (92 meshes) |
| `src/ui/static/models/z_anatomy/` | 307 MB | Z-Anatomy source .blend file |
| `src/ui/static/index.html` | — | 3D canvas + 6-button toolbar |
| `src/ui/static/app.js` | — | BodyMap3D integration |
| `src/ui/app.py` | — | Flask backend, /api/demographics, /models/ |
| `docs/phase11-3d-anatomy-handoff.md` | — | Original Phase 11 handoff document |

---

## Data Sources & Licenses

| Source | License | What We Use |
|--------|---------|-------------|
| [Z-Anatomy](https://github.com/LluisV/Z-Anatomy) | CC BY-SA 4.0 | 7,000+ structures, pre-colored .blend |
| [BodyParts3D v4.0](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html) | CC BY-SA 2.1 JP | Foundation dataset (Z-Anatomy builds on this) |
| [Three.js](https://threejs.org/) | MIT | WebGL renderer |

**Attribution:** "Z-Anatomy, based on BodyParts3D (c) The Database Center for Life Science, licensed under CC BY-SA 4.0"
