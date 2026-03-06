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

## Milestone: March 3 — 6-Layer Viewer Working

- All 6 layers (skin, muscle, skeleton, organs, vasculature, nervous) rendering
- 3,805 meshes in 9.4 MB Draco-compressed GLB
- OrbitControls working with rotate, zoom, pan
- Vasculature bug fix in progress (curve-converted vessels not tracked in layer assignments)

---

## What We Built: March 5 — Materials, Navigation, Organ Sub-Categories

### Rendering Overhaul
| Change | Before | After |
|--------|--------|-------|
| **Muscle material** | Default GLB colors, washed out | Deep crimson `MeshStandardMaterial` with per-fiber color variation, `toneMapped: false` + sRGB color space |
| **Muscle torso** | Pale/washed out from tone mapping | Fixed — ACES Filmic tone mapping + sRGB output color space properly configured |
| **Fascia rendering** | Hidden (lumped with muscle) | Semi-translucent tan `MeshStandardMaterial` at 75% opacity, skeleton visible through |
| **Organ materials** | Default GLB white/grey | 18 anatomically-accurate color categories (dark crimson heart, mauve-pink lungs, dark reddish-brown liver, pinkish-grey brain, etc.) |
| **Per-mesh variation** | Flat uniform color | `hashName()` function produces deterministic HSL variation so adjacent meshes look distinct |

### Navigation Controls
| Control | Action |
|---------|--------|
| **Left-drag** | Pan (move around the body — up to head, down to feet) |
| **Right-drag** | Rotate (spin the body front-to-back) |
| **Scroll** | Zoom in/out |
| **Click-after-drag fix** | Tracks mousedown position; only fires onClick if displacement < 5px (prevents camera snap on drag) |
| **Focus dropdown** | 8 body region presets (Head, Chest, Abdomen, Pelvis, Arms, Hands, Legs, Feet) with animated camera |

### Organ Sub-Categories
Replaced single "Organs" button with expandable dropdown — 8 categories:

| Category | Keywords | Color |
|----------|----------|-------|
| Heart | heart, ventricle, atrium, aorta, coronary, pericardium, valve... | Deep crimson |
| Lungs | lung, bronch, alveol, pleura, trachea, diaphragm | Mauve-pink |
| Brain | brain, cerebr, cerebel, hippocampus, thalamus, brainstem... | Pinkish-grey |
| Liver | liver, hepat, gallbladder, bile | Dark reddish-brown |
| Kidneys | kidney, renal, ureter, adrenal | Bean-brown |
| GI Tract | stomach, intestin, colon, rectum, esophag, duodenum... | Warm tan-pink |
| Reproductive | uterus, ovary, testi, prostate, penis, vagina... | Warm pink |
| Other | spleen, pancrea, bladder, thyroid, pharynx, larynx, tongue... | Various |

Each sub-category shows only its meshes + hides everything else. "All Organs" restores full view.

### Fascia as Independent Layer
- 44 fascia meshes tagged with `userData._isFascia` during model load
- New "Fascia" button in toolbar (between Muscle and Skeleton)
- Translucent tan material over skeleton companion at 40% opacity

### Hand Muscle Diagnostics
- 195 hand muscle meshes confirmed present in the muscle layer
- Names include: thenar, hypothenar, lumbrical, interosseous, flexor/extensor digitorum
- Model has good hand muscle coverage — no gaps found

### Current Mesh Counts (6,322 total)

| Layer | Active Meshes | Notes |
|-------|--------------|-------|
| Skin | 493 | Body surface regions |
| Muscle | 1,559 | 1,439 muscles + 44 fascia + 76 tendons |
| Skeleton | 984 | Bones, ligaments, cartilage |
| Organs | 388 unique | 306 pure organ + 82 cross-listed from vasculature/nervous |
| Vasculature | ~600 | Arteries (red) + veins (blue) |
| Nervous | ~459 | Nerves (yellow) + sense organs |
| Fascia | 44 | Connective tissue sheaths (semi-transparent) |

---

## Where We Are Now (March 6)

### Working
- **All 7 layer/pseudo-layer buttons** functional (Skin, Muscle, Fascia, Skeleton, Organs, Vessels, Nerves)
- **Organ sub-category dropdown** with 8 categories — click Heart to see only heart, etc.
- **NIH HRA on-demand organ drill-down** — click a category, expert-reviewed NIH organs load on-demand with caching
- **74 NIH HRA organ GLBs** integrated (769MB across male + female, loaded per-category)
- **Focus dropdown** — 8 body region camera presets with smooth animation
- **Anatomically-accurate materials** — organs color-coded, muscles deep crimson, fascia translucent tan
- **360 rotation** — Left/right-drag rotates body in all directions, body stays centered (pan disabled)
- **Scroll zoom** — with clamped distance limits
- **29 MB base GLB** with 6,322 meshes (Draco compressed) + 769MB on-demand organ detail
- **Zero console errors**

### What Changed Since March 5
| Change | Before | After |
|--------|--------|-------|
| **Rotation** | Horizontal only (polar angle locked), vertical drag panned camera | Full 360 orbit in all directions |
| **Centering** | Body could drift off-center via pan | Body always centered (pan disabled, Zygote Body style) |
| **Organ drill-down** | BodyParts3D overlay (rough MRI meshes) | NIH HRA expert-reviewed organs (Visible Human, sex-specific) |
| **Organ loading** | Eager (loaded everything on page load) | On-demand with caching (0.1ms re-show after first load) |
| **Female organs** | None | NIH HRA has sex-specific organ GLBs for all 8 categories |
| **Brain detail** | Z-Anatomy single mesh | Allen Brain Atlas (329 meshes) with eyes |
| **Heart detail** | Z-Anatomy single mesh | NIH HRA heart (14 detailed meshes with PBR materials) |
| **Kidney detail** | Z-Anatomy single mesh | 6 GLBs (kidneys + ureters + renal pelvis, 75 meshes) |
| **Instructional meshes** | HOW_TO / Navigation text rendered as circles | Filtered out (hidden) |

### Renderer Upgrade (March 6)
- **HDR environment**: `studio_small_08_2k.hdr` (Poly Haven, CC0) via RGBELoader + PMREMGenerator
- **Post-processing pipeline**: EffectComposer → RenderPass → SSAOPass → UnrealBloomPass → OutputPass
- **SSAO**: kernelRadius 0.5, tight contact shadows at mesh boundaries (ribs, organ surfaces)
- **Bloom**: strength 0.15, threshold 0.85 — subtle specular highlight glow
- **Material upgrades**: all 6 layers now MeshPhysicalMaterial with per-tissue envMapIntensity:
  - Skin 0.5, Muscle 0.4, Skeleton 0.35, Vasculature 0.6, Nerves 0.3, Organs 0.45
- **Tone mapping fix**: muscles + organs no longer bypass ACES Filmic (removed `toneMapped: false`)
- **Muscle upgrade**: MeshStandardMaterial → MeshPhysicalMaterial with clearcoat + sheen (wet muscle appearance)
- **Organ upgrade**: MeshStandardMaterial → MeshPhysicalMaterial with clearcoat (moist organ surfaces)

### Known Limitations — What's Left

**Rendering quality gap** — RESOLVED (March 6). See Renderer Upgrade section above.

**Female body model**:
- NIH HRA `3d-vh-f-united.glb` (208MB) complete female body — **working**
- Keyword-based layer classification implemented and verified (skin:70, muscle:119, skeleton:374, organs:732, vasculature:365, nervous:365)
- All 6 layers render correctly on the female model

**AnatomyTool skeleton/muscles**:
- 5 of 11 models downloaded (20MB total): overview-skeleton, upper-limb, lower-limb, hand, colored-skull-base
- 6 models don't have GLB exports yet (returned error pages — OBJ/FBX only)
- Not yet integrated into viewer — next step

---

## Where We're Going

### Immediate Priorities

| Priority | Feature | Impact | Effort |
|----------|---------|--------|--------|
| ~~1~~ | ~~**Three.js renderer upgrade**~~ | **DONE** — HDR env + SSAO + bloom + MeshPhysicalMaterial on all layers. Production-level rendering achieved. | Completed March 6 |
| 1 | **AnatomyTool integration** | Wire downloaded skeleton/muscle GLBs into viewer as higher-quality alternatives for bones and muscles | Low — 5 GLBs ready, need layer assignment + toggle |
| 2 | **Organ hover tooltips** | Hover mesh → show anatomical name; builds toward clinical data overlay | Medium — raycasting + HTML overlay |

### Completed (Since March 5)

| Feature | Status |
|---------|--------|
| **Female body model** | Working — NIH HRA united body loads, all 6 layers classified via keywords |
| **360 rotation** | Working — full orbit, body stays centered |
| **NIH HRA organ drill-down** | Working — 8 categories, on-demand loading, sex-specific |
| **Instructional mesh removal** | Working — HOW_TO + Navigation + collection header glyphs removed |
| **Centering fix** | Working — removed instructional meshes from scene before bounding box calc |
| **Z-Anatomy PBR investigation** | Complete — confirmed 0 textures, quality gap is renderer settings |
| **AnatomyTool downloads** | 5 of 11 GLBs downloaded (20MB) |

### Future Enhancements

| Feature | Description |
|---------|-------------|
| **Click-to-inspect** | Click organ → side panel with related diagnoses, labs, imaging |
| **Condition deformations** | 65+ deformation profiles for the high-res meshes |
| **Cross-section mode** | Clip plane to see internal structures in context |
| **Search** | Type "liver" → camera zooms to liver, highlights it |
| **Annotations** | Doctor or patient can pin notes to specific anatomy |
| **Animated systems** | Beating heart, breathing lungs, blood flow visualization |

### The Big Picture
This is a **personal medical intelligence system**. The 3D body map is the spatial anchor for all clinical data. Every diagnosis, lab result, imaging finding, and medication maps to a region of the body. When you click on the liver, you see hepatic findings. When you hover over the heart, you see cardiac history.

The goal: A 60-year-old opens this app before a doctor visit and **understands their body** — what's wrong, where it is, how it connects. Not through medical jargon, but through a visual, interactive, anatomically-accurate model of themselves.

We went from a 92-mesh BodyParts3D reject to a **multi-atlas hybrid** pulling from 3 of the world's best open anatomy datasets. The NIH's own expert-reviewed organs load on-demand when you drill in. The body rotates 360 degrees and stays centered. The only thing standing between us and Zygote Body-quality rendering is **renderer improvements** — environment maps, SSAO, and subsurface scattering in our Three.js pipeline.

---

## March 6 — Multi-Atlas Integration: NIH HRA + Z-Anatomy + AnatomyTool

This was a breakthrough session. We discovered three major open anatomy atlases, evaluated six potential data sources, built a hybrid integration architecture, and solved the long-standing rotation problem.

### The Research: Evaluating Every Open 3D Anatomy Source

We systematically evaluated every freely-licensed 3D human anatomy dataset available:

| Source | License | Strengths | Weaknesses | Verdict |
|--------|---------|-----------|------------|---------|
| **Z-Anatomy** | CC BY-SA 4.0 | 7,000+ structures, 6 system layers, named mesh prefixes (`SKEL__`, `MUSC__`), excellent musculoskeletal/vasculature/nervous | Organs are shallow (single meshes), our GLB export stripped PBR materials | **Keep as base model** |
| **NIH HRA** (3d.nih.gov) | CC BY 4.0 | 74 expert-reviewed organ GLBs, sex-specific (male + female), complete female united body (208MB), derived from Visible Human Project | Individual organs only, no musculoskeletal/vasculature/nervous | **Integrated — organ drill-down** |
| **AnatomyTool** (Open3DModel) | CC BY-SA 4.0 | 70% of Z-Anatomy meshes remeshed by anatomists for correctness, better topology | No internal organs (planned 2025-2026), SSL cert issues on download server | **Planned — skeleton/muscles upgrade** |
| **Zygote Body** | Proprietary | Beautiful PBR rendering, complete male + female | Commercial license ($4-98/mo viewer, $1000s+ for 3D data), no downloads allowed | **Cannot use** |
| **BlueLink** (U Michigan) | CC BY-NC-ND + NoAI | Excellent organ detail, medical school quality | Non-commercial, no derivatives — prohibits our use entirely | **Cannot use** |
| **BodyParts3D** (DBCLS Japan) | CC BY 4.0 | 1,523 FMA-mapped structures, heart chambers, liver lobes | 2013 vintage, rough MRI-derived meshes, male only, no maintenance | **Superseded by NIH HRA** |

### Key Discovery: The Zygote Connection

Zygote is the company that originally commercialized the Visible Human Project data. NIH HRA models are derived from the same Visible Human cadaver datasets — they're effectively the open-access version of what Zygote sells for thousands of dollars. We have the same source data, just without Zygote's proprietary PBR materials.

### The Rendering Quality Gap (Corrected Understanding)

Side-by-side comparison of Z-Anatomy on Sketchfab vs our viewer suggested the gap was materials. **Investigation proved this wrong.**

**Key finding: Z-Anatomy has 0 image textures.** We downloaded the full 307MB Z-Anatomy `.blend` file from GitHub and ran a Blender headless inspection (`inspect_materials.py`). Result:
- 188 materials, ALL using Principled BSDF nodes (solid color + roughness + metallic)
- **0 TEX_IMAGE nodes** — no textures, no normal maps, no skin textures
- The "PBR quality" visible on Sketchfab comes from **Sketchfab's renderer settings**, not from the model files

| Property | What We Assumed | What We Found |
|----------|-----------------|---------------|
| **Image textures** | Normal maps, skin textures | **Zero** — 0 TEX_IMAGE nodes across all 188 materials |
| **Materials** | Complex PBR with baked textures | Principled BSDF: base color + roughness + metallic (no textures) |
| **Sketchfab quality** | Comes from model files | Comes from **renderer settings** (environment maps, SSAO, post-processing) |
| **Our GLB export** | "Stripped PBR materials" | Actually exported the same data — there was nothing extra to strip |

**Corrected fix path**: The rendering quality gap is about **renderer improvements** in our Three.js viewer, not about downloading different model files. Both our GLB and Sketchfab use the same Principled BSDF material data. To match Sketchfab quality we need:
- **Environment maps** (HDR lighting that creates realistic reflections/ambient)
- **SSAO** (Screen-Space Ambient Occlusion for depth and contact shadows)
- **Subsurface scattering** (translucency for skin, lungs, organs)
- **Post-processing** (bloom, tone mapping refinement, depth of field)

### The Hybrid Architecture

Rather than replacing one atlas with another, we built a best-of-breed hybrid:

```
┌─────────────────────────────────────────────────────┐
│                  3D Anatomy Viewer                    │
├─────────────────────────────────────────────────────┤
│                                                       │
│  BASE MODEL (always loaded):                         │
│  └── Z-Anatomy male_anatomy_full.glb (29MB)          │
│      ├── Skin layer        (493 meshes)              │
│      ├── Muscle layer      (1,559 meshes)            │
│      ├── Skeleton layer    (984 meshes)              │
│      ├── Organs layer      (388 meshes) ← overview   │
│      ├── Vasculature layer (~600 meshes)             │
│      └── Nervous layer     (~459 meshes)             │
│                                                       │
│  ON-DEMAND ORGAN DRILL-DOWN (loaded when clicked):   │
│  └── NIH HRA GLBs (74 files, 769MB total)            │
│      ├── Heart      → VH_M_Heart.glb (14 meshes)    │
│      ├── Brain      → Allen Brain + eyes (329 mesh)  │
│      ├── Kidneys    → 6 GLBs (75 meshes)             │
│      ├── Lungs      → bronchus+trachea+larynx        │
│      ├── Liver      → VH_M_Liver.glb                 │
│      ├── GI Tract   → intestines+pancreas+mouth      │
│      ├── Reproductive → sex-specific organs           │
│      └── Other      → spleen, thymus, bladder, etc.  │
│                                                       │
│  FEMALE BODY (loaded on gender toggle):              │
│  └── NIH HRA 3d-vh-f-united.glb (208MB)             │
│      └── Keyword-based layer classification           │
│                                                       │
│  PLANNED UPGRADES:                                    │
│  ├── Three.js renderer → env maps + SSAO + SSS       │
│  └── AnatomyTool GLBs → better skeleton/muscles      │
│                                                       │
└─────────────────────────────────────────────────────┘
```

### What We Built: On-Demand Organ Loading System

The NIH HRA integration uses a registry + cache + on-demand loading pattern:

**1. Organ Registry** (`nihOrganRegistry` in bodymap3d.js):
Maps 8 organ categories to GLB filenames, sex-specific:
```javascript
heart:        { male: ["VH_M_Heart.glb"],     female: ["VH_F_Heart.glb"] }
brain:        { male: ["3d-vh-m-allen-brain.glb", "3d-vh-m-eye-l.glb", ...] }
kidneys:      { male: ["VH_M_Kidney_L.glb", "VH_M_Kidney_R.glb", ...] }
// ... 8 categories total, 74 GLBs mapped
```

**2. On-Demand Loading** (`_loadNIHOrgan(category)`):
- User clicks organ category (e.g., "Heart")
- Z-Anatomy base organs hidden for that category
- GLBs loaded in parallel via `GLTFLoader`
- Loaded meshes added INTO main model wrapper (shares normalization transform)
- Loading indicator overlay shown during download
- All meshes cached for instant re-access

**3. Cache System** (`nihOrgansCache`):
- Key: `"male_heart"`, `"female_brain"`, etc.
- Value: `{ group: THREE.Group, meshes: [Mesh, ...] }`
- First load: downloads GLB(s) from `/models/nih_hra/`
- Subsequent access: instant (0.1ms) visibility toggle
- Cache cleared on gender switch (male/female organs differ)

**4. Coordinate Alignment**:
NIH HRA organs use the same Visible Human coordinate space as Z-Anatomy's base model. By adding the loaded organ group INTO the main model's wrapper (`currentModel.children[0].add(group)`), they share the normalization transform (scale to ~2 units tall, center at camera target). No manual offsets needed.

### 360 Rotation Fix

**Problem**: Camera was locked to horizontal rotation only.

**Root causes found**:
1. `minPolarAngle = maxPolarAngle = Math.PI/2` — locked to equator
2. Custom `mousemove` handler intercepted left-drag Y and shifted `camera.position.y` + `controls.target.y` together — faking vertical pan instead of orbit

**Fix**: Unlocked polar angle (`0.05` to `PI - 0.05`), removed custom vertical pan handler entirely. OrbitControls now handles full 360 orbit natively. Left-drag = rotate (full 360), right-drag = pan, scroll = zoom.

### Z-Anatomy Instructional Mesh Filter + Centering Fix

Z-Anatomy contains `HOW_TO_*`, `Navigationst*`, and collection header glyphs (`Skeletal_systemg`, `Jointsg`, etc.) that render as unwanted circles and — critically — **inflate the bounding box calculation, shifting the model center 1.77 units off-axis**.

**Root cause of centering bug**: `Box3.setFromObject()` includes ALL descendants, even hidden meshes. The HOW_TO text meshes extended from X=-0.06 to X=4.32, pulling the computed center far right of the actual anatomy.

**Fix**: Two-phase removal:
1. **Pre-pass** (before bounding box centering): Traverse and REMOVE (not just hide) instructional meshes from the scene graph. Only removes `isMesh` nodes to avoid cascading removal of Group parents.
2. **Traversal filter**: Catches any remaining matches during layer classification.

```javascript
// Pre-pass: remove instructional meshes BEFORE bounding box centering
var toRemove = [];
wrapper.traverse(function(child) {
    if (!child.isMesh) return;  // Only Mesh nodes — removing Groups cascades to children
    var n = (child.name || "").toLowerCase();
    var stripped = n.replace(/^(?:skel|musc|orgn|vasc|nerv|skin)__/, "");
    if (/^(how_to|navigation)/.test(n) ||
        /(?:systemg|organsg|jointsg|bodyg|insertionsg|systemsg)$/.test(stripped)) {
        toRemove.push(child);
    }
});
toRemove.forEach(c => c.parent && c.parent.remove(c));
```

**Result**: Male model center X went from **1.769 to 0.027** — body stays centered at all rotation angles.

### Verified Results

| Test | Result |
|------|--------|
| Heart drill-down | 14 meshes load on-demand, correct chest position, PBR materials |
| Brain drill-down | 329 meshes (Allen Brain Atlas + eyes), detailed gyri visible |
| Kidneys drill-down | 75 meshes from 6 GLBs (kidneys + ureters + renal pelvis) |
| Cache re-show | 0.1ms (instant) after first load |
| "All" reset | NIH organs hidden (0 visible), Z-Anatomy base restored |
| Layer cycling | Skin → Muscle → Skeleton → back: no leftover NIH organ visibility |
| 360 rotation | Full vertical orbit, minPolar=0.05, maxPolar=3.09 |
| Console errors | Zero |

---

## NIH HRA Model Inventory

74 GLBs downloaded from https://3d.nih.gov/collections/hra (768.9 MB total):

### Male Models
| File | Size | Category |
|------|------|----------|
| VH_M_Heart.glb | 4.0 MB | Heart |
| 3d-vh-m-allen-brain.glb | 11.9 MB | Brain |
| 3d-vh-m-eye-l/r.glb | 0.4 MB each | Brain (eyes) |
| VH_M_Liver.glb | 0.8 MB | Liver |
| VH_M_Kidney_L/R.glb | 0.3 MB each | Kidneys |
| VH_M_Ureter_L/R.glb | 0.1 MB each | Kidneys |
| 3d-vh-m-renal-pelvis-l/r.glb | 0.1 MB each | Kidneys |
| VH_M_Small_Intestine.glb | 2.1 MB | GI Tract |
| SBU_M_Intestine_Large.glb | 3.2 MB | GI Tract |
| 3d-vh-m-pancreas.glb | 0.4 MB | GI Tract |
| 3d-vh-m-main-bronchus.glb | 0.5 MB | Lungs |
| 3d-vh-m-trachea.glb | 0.2 MB | Lungs |
| 3d-vh-m-larynx.glb | 0.5 MB | Lungs |
| VH_M_Prostate.glb | 0.2 MB | Reproductive |
| VH_M_Spleen.glb | 0.3 MB | Other |
| VH_M_Thymus.glb | 0.1 MB | Other |
| VH_M_Urinary_Bladder.glb | 0.2 MB | Other |
| VH_M_Spinal_Cord.glb | 1.0 MB | Other |
| NIH_M_Lymph_Node.glb | 0.1 MB | Other |
| VH_M_Blood_Vasculature.glb | 26.3 MB | Vasculature (layer) |
| VH_M_Skin.glb | 27.8 MB | Skin (layer) |
| VH_M_Knee_L/R.glb | 4.3 MB each | Skeletal |
| VH_M_Pelvis.glb | 7.2 MB | Skeletal |
| 3d-vh-m-united.glb | 153 MB | Complete body |

### Female Models
| File | Size | Category |
|------|------|----------|
| VH_F_Heart.glb | 1.7 MB | Heart |
| 3d-vh-f-allen-brain.glb | 11.9 MB | Brain |
| 3d-vh-f-lung.glb | 23 MB | Lungs |
| VH_F_Liver.glb | 0.7 MB | Liver |
| VH_F_Kidney_L/R.glb | 0.3 MB each | Kidneys |
| VH_F_Uterus.glb | 0.3 MB | Reproductive |
| VH_F_Ovary_L/R.glb | 0.1 MB each | Reproductive |
| VH_F_Fallopian_Tube_L/R.glb | 0.1 MB each | Reproductive |
| VH_F_Placenta.glb | 0.6 MB | Reproductive |
| 3d-vh-f-mammary-gland-l/r.glb | 0.4 MB each | Reproductive |
| 3d-vh-f-united.glb | 208 MB | Complete female body |
| VH_F_Blood_Vasculature.glb | 17 MB | Vasculature (layer) |
| *(+ ureters, spleen, thymus, bladder, spinal cord, lymph, skin, sternum, manubrium, mouth, pancreas, tonsils, trachea, larynx, bronchus, renal pelvis, eyes, knee, pelvis)* | | |

---

## Data Sources & Licenses (Updated March 6)

| Source | License | What We Use | Status |
|--------|---------|-------------|--------|
| [Z-Anatomy](https://www.z-anatomy.com/) ([GitHub](https://github.com/LluisV/Z-Anatomy), [Sketchfab](https://sketchfab.com/Z-Anatomy)) | CC BY-SA 4.0 | 6,322 meshes — base model for all 6 layers | **Active** |
| [NIH HRA](https://3d.nih.gov/collections/hra) | CC BY 4.0 | 74 GLBs — on-demand organ drill-down + female united body | **Integrated** |
| [AnatomyTool Open3DModel](https://anatomytool.org/open3dmodel) ([downloads](https://caskanatomy.info/open3dmodelfiles/)) | CC BY-SA 4.0 | Skeleton + muscle upgrade (70% remeshed for correctness) | **Planned** |
| [Three.js r170](https://threejs.org/) | MIT | WebGL renderer + OrbitControls + GLTFLoader | **Active** |

**Cannot use** (evaluated and rejected):
- **Zygote Body** — Proprietary, commercial ($4-98/mo viewer, model licensing $1000s+)
- **BlueLink** (U Michigan) — CC BY-NC-ND + NoAI, prohibits derivatives
- **BodyParts3D** — Superseded by NIH HRA (same Visible Human source, better quality, sex-specific)

**Attribution requirements:**
- Z-Anatomy: "Z-Anatomy, based on BodyParts3D, licensed under CC BY-SA 4.0"
- NIH HRA: "3D models from the NIH 3D Print Exchange Human Reference Atlas, licensed under CC BY 4.0"
- AnatomyTool: "Open3DModel by AnatomyTool, licensed under CC BY-SA 4.0"

---

## Lessons Learned

### Diagnose Before Prescribe (Bug Pattern #10)

**The incident**: Z-Anatomy looked flat in our Three.js viewer compared to Sketchfab. The AI assistant pattern-matched to "must need better model data" — the most common cause of 3D rendering quality issues. Hours were spent downloading the 307MB Blender file, writing export scripts with collection-based layer prefixes, debugging Group node cascading deletion, and re-exporting. Then an inspection script (`inspect_materials.py`) revealed: **0 image textures across all 188 materials.** Every material was a Principled BSDF node with solid color + roughness + metallic — no textures, no normal maps, no skin textures. The existing GLB already contained the same material data. The entire download/export detour was unnecessary.

**Root cause of the mistake**: Pattern-matching instead of investigating. The assistant jumped to solutions before confirming the problem. It should have asked: *"What do I already know vs. what am I assuming?"* — and couldn't have cleanly answered that, which means it needed to investigate first.

**Self-check prompts that would have caught this**:
- "Show the evidence before suggesting a fix."
- "What does the current code/data actually say?"
- "Diagnose first, then prescribe."

**The actual fix**: Three.js renderer upgrade — environment maps (PMREMGenerator), SSAO (SSAOPass), subsurface scattering, post-processing (EffectComposer). No new model files needed.

**Applies broadly**: Not just code. Anywhere someone is pattern-matching instead of actually looking — whether debugging, data analysis, or any recommendation — refuse to let the process jump to solutions before the problem is confirmed. Separate known facts from assumptions first.

---

## File Map (Updated March 6)

| File | Size/Lines | Purpose |
|------|-----------|---------|
| `src/ui/static/js/bodymap3d.js` | ~3,200 lines | Three.js viewer + materials + organ categories + NIH HRA on-demand loading + deformation engine |
| `src/ui/static/models/export_zanatomy.py` | ~510 lines | Z-Anatomy → GLB pipeline (Blender 5.0.1) |
| `src/ui/static/models/male_anatomy_full.glb` | 29 MB | Full Z-Anatomy export (6,322 meshes, Draco compressed) |
| `src/ui/static/models/male_anatomy.glb` | 5 MB | Original BodyParts3D export (92 meshes, legacy) |
| `src/ui/static/models/z_anatomy/` | 307 MB | Z-Anatomy source .blend file |
| `src/ui/static/models/nih_hra/` | 769 MB (74 GLBs) | NIH HRA organ models (male + female, on-demand loaded) |
| `src/ui/static/models/nih_hra/download_hra.sh` | — | Download script for all 77 NIH HRA entries |
| `src/ui/static/models/nih_hra/download_hra.py` | — | Python download script with API integration |
| `src/ui/static/models/anatomytool/` | 20 MB (5 GLBs) | AnatomyTool skeleton/muscle models (not yet integrated) |
| `models/anatomytool/download_anatomytool.sh` | — | Download script for caskanatomy.info GLBs |
| `models/z-anatomy-src/` | 307 MB | Z-Anatomy .blend file + Blender inspection/export scripts |
| `models/z-anatomy-src/inspect_materials.py` | — | Blender script that confirmed 0 image textures |
| `models/z-anatomy-src/export_layers.py` | — | Blender export script with collection-based layer prefixes |
| `src/ui/static/index.html` | ~920 lines | 3D canvas + toolbar with dropdowns |
| `src/ui/static/styles.css` | — | Dropdown CSS, dark theme |
| `src/ui/static/app.js` | — | BodyMap3D integration |
| `src/ui/app.py` | — | Flask backend, /api/demographics, /models/ |
| `docs/3d-anatomy-journey.md` | — | This document — full research + architecture log |
| `docs/phase11-3d-anatomy-handoff.md` | — | Original Phase 11 handoff document |
