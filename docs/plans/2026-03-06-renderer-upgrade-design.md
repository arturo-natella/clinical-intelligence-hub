# Three.js Renderer Upgrade — Design Document

**Date:** 2026-03-06
**Goal:** Upgrade the 3D anatomy viewer from flat direct rendering to production-level post-processed output with HDR environment lighting, SSAO, and bloom.

---

## Problem

The Z-Anatomy model has 0 image textures — all 188 materials are Principled BSDF with solid color + roughness + metallic. Sketchfab renders the same data beautifully because of renderer settings: environment maps, SSAO, post-processing. Our viewer renders directly via `renderer.render()` with no post-processing pipeline, and the existing PMREMGenerator env map is disabled on every material (`envMapIntensity: 0.0`).

Three specific issues:
1. Environment map built but disabled on all materials
2. Muscles bypass ACES tone mapping (`toneMapped: false`), creating inconsistent look
3. No EffectComposer — no SSAO, no bloom, no output pass

## Solution

Full post-processing pipeline with real HDR studio environment.

---

## 1. HDR Environment Map

**File:** `studio_small_08_2k.hdr` from Poly Haven (CC0, ~6.7MB)
- Soft wraparound studio lighting with octabox highlights
- Neutral, professional — medical photography studio quality
- Download: `https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/studio_small_08_2k.hdr`
- Host at: `src/ui/static/models/studio_small_08_2k.hdr`

**Loading chain:**
```
RGBELoader → PMREMGenerator.fromEquirectangular() → scene.environment
```

- `scene.environment` = HDR (affects all PBR materials)
- `scene.background` = unchanged (`0x141414` dark background stays)
- Replaces current canvas gradient in `_setupEnvironment()`

**Env map intensity per tissue type:**

| Layer | envMapIntensity | Rationale |
|-------|----------------|-----------|
| Skin | 0.5 | Visible specular from ambient light |
| Muscle | 0.4 | Wet, glossy exposed tissue |
| Skeleton | 0.35 | Waxy, porcelain-like bone surface |
| Vasculature | 0.6 | Glossiest tissue — wet taut membrane |
| Nervous | 0.3 | Myelin sheath subtle sheen |
| Organs | 0.45 | Moist organ surfaces |

Starting values — tune visually after implementation.

## 2. Post-Processing Pipeline

**New CDN imports** (same `examples/jsm` pattern as OrbitControls):
- `EffectComposer` from `postprocessing/EffectComposer.js`
- `RenderPass` from `postprocessing/RenderPass.js`
- `SSAOPass` from `postprocessing/SSAOPass.js`
- `UnrealBloomPass` from `postprocessing/UnrealBloomPass.js`
- `OutputPass` from `postprocessing/OutputPass.js`
- `RGBELoader` from `loaders/RGBELoader.js`

**Pass chain:**
```
RenderPass → SSAOPass → UnrealBloomPass → OutputPass
```

**SSAO parameters (tuned for anatomy):**
- `kernelRadius`: 0.5 — tight contact shadows (ribs meeting intercostals, organ surfaces touching)
- `minDistance`: 0.001
- `maxDistance`: 0.05 — short range, darkens crevices without halos

**Bloom parameters:**
- `strength`: 0.15 — specular highlight glow, not sci-fi
- `radius`: 0.4
- `threshold`: 0.85 — only brightest highlights bloom

**Animation loop:**
```javascript
// Before:  this.renderer.render(this.scene, this.camera);
// After:   this.composer.render();
```

## 3. Material Fixes

### Remove toneMapped: false from muscles
All materials go through ACES Filmic consistently. Muscle sRGB color values may need slight bump to compensate for ACES darkening.

### Upgrade muscle material to MeshPhysicalMaterial
Currently `MeshStandardMaterial`. Upgrading gives muscles clearcoat + sheen — physically accurate wet muscle surface. Same material class as skin and bones for consistency.

### Enable env map on all materials
Remove all `envMapIntensity: 0.0` overrides. Set per-tissue values from table above.

## 4. Resize Handling

EffectComposer and SSAOPass need explicit size updates. Extend existing `_onResize()`:
```javascript
if (this.composer) this.composer.setSize(w, h);
```

## 5. Fallback Safety

- If WebGL context lost or framerate drops: log WARNING (iron rule — no silent degradation)
- SSAO and bloom toggleable at runtime: `ssaoPass.enabled = false`
- If composer fails entirely, fall back to direct `renderer.render()`

## Implementation Files

| File | Changes |
|------|---------|
| `src/ui/static/index.html` | Add CDN imports for EffectComposer, RenderPass, SSAOPass, UnrealBloomPass, OutputPass, RGBELoader |
| `src/ui/static/js/bodymap3d.js` | Replace `_setupEnvironment()`, add `_setupPostProcessing()`, update `_animate()`, update all material functions, update `_onResize()` |
| `src/ui/static/models/studio_small_08_2k.hdr` | New file — HDR environment (6.7MB, CC0) |

## Attribution

Studio Small 08 HDRI by Sergej Majboroda, from Poly Haven. CC0 — no attribution required, but credit in source comments.
