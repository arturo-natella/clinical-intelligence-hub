# Three.js Renderer Upgrade — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the 3D anatomy viewer to production-level rendering with HDR environment lighting, SSAO, bloom, and corrected materials.

**Architecture:** Replace direct `renderer.render()` with an EffectComposer pipeline (RenderPass → SSAOPass → UnrealBloomPass → OutputPass). Load a real HDR studio environment via RGBELoader + PMREMGenerator. Fix material inconsistencies (tone mapping bypass, disabled env map). All changes in 2 files + 1 new asset.

**Tech Stack:** Three.js r170 (CDN), EffectComposer post-processing addons, Poly Haven CC0 HDR

**Design doc:** `docs/plans/2026-03-06-renderer-upgrade-design.md`

---

### Task 1: Download HDR Environment File

**Files:**
- Create: `src/ui/static/models/studio_small_08_2k.hdr`

**Step 1: Download the HDR from Poly Haven**

```bash
curl -L -o "/Users/owner/Desktop/Tech Tools/MedPrep/src/ui/static/models/studio_small_08_2k.hdr" \
  "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/studio_small_08_2k.hdr"
```

**Step 2: Verify the file**

```bash
ls -lh "/Users/owner/Desktop/Tech Tools/MedPrep/src/ui/static/models/studio_small_08_2k.hdr"
```

Expected: ~6-7 MB file.

**Step 3: Add MIME type for .hdr in Flask**

The Flask `send_from_directory` must serve `.hdr` files with the correct MIME type. Check `src/ui/app.py` — Flask's built-in static file serving handles unknown extensions as `application/octet-stream`, which is fine for binary download. No change needed unless the browser rejects it (verify in Task 5).

**Step 4: Commit**

```bash
git add src/ui/static/models/studio_small_08_2k.hdr
git commit -m "asset: add Poly Haven studio HDR environment (CC0, 2K)"
```

---

### Task 2: Add CDN Imports for Post-Processing + RGBELoader

**Files:**
- Modify: `src/ui/static/index.html:18-33`

**Step 1: Add the new addon imports**

In the `<script type="module">` block (lines 18-34), add imports for EffectComposer, RenderPass, SSAOPass, UnrealBloomPass, OutputPass, and RGBELoader. These follow the exact same pattern as the existing OrbitControls and GLTFLoader imports.

Replace lines 18-34 with:

```html
<script type="module">
    import * as _THREE from "three";
    const base = "https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm";
    const { OrbitControls } = await import(base + "/controls/OrbitControls.js");
    const { GLTFLoader } = await import(base + "/loaders/GLTFLoader.js");
    // Post-processing pipeline
    const { EffectComposer } = await import(base + "/postprocessing/EffectComposer.js");
    const { RenderPass } = await import(base + "/postprocessing/RenderPass.js");
    const { SSAOPass } = await import(base + "/postprocessing/SSAOPass.js");
    const { UnrealBloomPass } = await import(base + "/postprocessing/UnrealBloomPass.js");
    const { OutputPass } = await import(base + "/postprocessing/OutputPass.js");
    // HDR environment loader
    const { RGBELoader } = await import(base + "/loaders/RGBELoader.js");
    // Module namespace is immutable — copy to mutable object
    const THREE = {};
    Object.getOwnPropertyNames(_THREE).forEach(k => { THREE[k] = _THREE[k]; });
    THREE.OrbitControls = OrbitControls;
    THREE.GLTFLoader = GLTFLoader;
    THREE.EffectComposer = EffectComposer;
    THREE.RenderPass = RenderPass;
    THREE.SSAOPass = SSAOPass;
    THREE.UnrealBloomPass = UnrealBloomPass;
    THREE.OutputPass = OutputPass;
    THREE.RGBELoader = RGBELoader;
    try {
        const { DRACOLoader } = await import(base + "/loaders/DRACOLoader.js");
        THREE.DRACOLoader = DRACOLoader;
    } catch (e) { /* DRACO not required */ }
    window.THREE = THREE;
    window.dispatchEvent(new Event("three-ready"));
</script>
```

**Step 2: Bump cache version**

Find the `bodymap3d.js` script tag and bump `?v=7.0` → `?v=8.0`:

```html
<script src="/js/bodymap3d.js?v=8.0"></script>
```

**Step 3: Start the preview server and verify imports load without errors**

Start: `preview_start` (name: "hub")
Check: `preview_console_logs` — should show no import errors.

**Step 4: Commit**

```bash
git add src/ui/static/index.html
git commit -m "feat: add Three.js post-processing + RGBELoader CDN imports"
```

---

### Task 3: Add State Properties + Setup Post-Processing Pipeline

**Files:**
- Modify: `src/ui/static/js/bodymap3d.js:13-19` (state properties)
- Modify: `src/ui/static/js/bodymap3d.js:1557-1588` (replace `_setupEnvironment`)

**Step 1: Add composer state to BodyMap3D object**

At line 17, after `animationId: null,` add:

```javascript
    composer: null,
    ssaoPass: null,
    bloomPass: null,
```

**Step 2: Replace `_setupEnvironment` with HDR loader + post-processing setup**

Replace the entire `_setupEnvironment` function (lines 1561-1588) with two new functions:

```javascript
    _setupEnvironment: function() {
        // Load real HDR studio environment (Poly Haven studio_small_08, CC0)
        // Provides realistic ambient lighting + reflections for all PBR materials
        var self = this;
        var loader = new THREE.RGBELoader();
        loader.load("/models/studio_small_08_2k.hdr", function(texture) {
            texture.mapping = THREE.EquirectangularReflectionMapping;
            var pmremGenerator = new THREE.PMREMGenerator(self.renderer);
            pmremGenerator.compileEquirectangularShader();
            self.scene.environment = pmremGenerator.fromEquirectangular(texture).texture;
            texture.dispose();
            pmremGenerator.dispose();
            console.log("[BodyMap3D] HDR environment loaded — studio_small_08_2k");
        }, undefined, function(err) {
            // Fallback: procedural gradient if HDR fails to load
            console.warn("[BodyMap3D] HDR env failed to load, using procedural fallback:", err);
            var size = 256;
            var canvas = document.createElement("canvas");
            canvas.width = size;
            canvas.height = size;
            var ctx = canvas.getContext("2d");
            var grad = ctx.createLinearGradient(0, 0, 0, size);
            grad.addColorStop(0.0, "#d4c8bb");
            grad.addColorStop(0.3, "#c0b8b0");
            grad.addColorStop(0.5, "#a8a4a0");
            grad.addColorStop(0.7, "#8890a0");
            grad.addColorStop(1.0, "#607088");
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, size, size);
            var tex = new THREE.CanvasTexture(canvas);
            tex.mapping = THREE.EquirectangularReflectionMapping;
            var pmremGenerator = new THREE.PMREMGenerator(self.renderer);
            pmremGenerator.compileEquirectangularShader();
            self.scene.environment = pmremGenerator.fromEquirectangular(tex).texture;
            tex.dispose();
            pmremGenerator.dispose();
        });
    },

    _setupPostProcessing: function() {
        // EffectComposer pipeline: RenderPass → SSAOPass → UnrealBloomPass → OutputPass
        var canvas = this.renderer.domElement;
        var w = canvas.width;
        var h = canvas.height;

        this.composer = new THREE.EffectComposer(this.renderer);

        // Pass 1: Render the scene
        var renderPass = new THREE.RenderPass(this.scene, this.camera);
        this.composer.addPass(renderPass);

        // Pass 2: SSAO — contact shadows where anatomy meets anatomy
        this.ssaoPass = new THREE.SSAOPass(this.scene, this.camera, w, h);
        this.ssaoPass.kernelRadius = 0.5;     // tight — crevice shadows, not broad haze
        this.ssaoPass.minDistance = 0.001;
        this.ssaoPass.maxDistance = 0.05;
        this.composer.addPass(this.ssaoPass);

        // Pass 3: Bloom — subtle specular highlight glow
        this.bloomPass = new THREE.UnrealBloomPass(
            new THREE.Vector2(w, h),
            0.15,     // strength — subtle, not sci-fi
            0.4,      // radius
            0.85      // threshold — only brightest highlights
        );
        this.composer.addPass(this.bloomPass);

        // Pass 4: Output — color space conversion (required final pass)
        var outputPass = new THREE.OutputPass();
        this.composer.addPass(outputPass);

        console.log("[BodyMap3D] Post-processing pipeline: RenderPass → SSAO → Bloom → Output");
    },
```

**Step 3: Call both setup functions in `init()`**

Find where the renderer is created (around line 306-312). After the renderer setup and before `this.controls = new THREE.OrbitControls(...)`, add:

```javascript
        // Post-processing + HDR environment
        this._setupEnvironment();
        this._setupPostProcessing();
```

Specifically, insert after line 312 (`this.renderer.toneMappingExposure = 1.0;`) and before line 314 (`this.controls = new THREE.OrbitControls(...)`).

**Step 4: Commit**

```bash
git add src/ui/static/js/bodymap3d.js
git commit -m "feat: add HDR environment + EffectComposer post-processing pipeline"
```

---

### Task 4: Switch Animation Loop to Composer

**Files:**
- Modify: `src/ui/static/js/bodymap3d.js:525-527` (animate loop)
- Modify: `src/ui/static/js/bodymap3d.js:530-533` (destroy)
- Modify: `src/ui/static/js/bodymap3d.js:3383-3390` (resize)

**Step 1: Replace renderer.render() with composer.render() in _animate**

Replace lines 525-527:

```javascript
        // Old: this.renderer.render(this.scene, this.camera);
        if (this.composer) {
            this.composer.render();
        } else if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
```

**Step 2: Update destroy() to dispose composer**

Replace lines 530-533:

```javascript
    destroy: function() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.composer) this.composer.dispose();
        if (this.renderer) this.renderer.dispose();
    },
```

**Step 3: Update onWindowResize() to resize composer**

Replace lines 3383-3390:

```javascript
    onWindowResize: function(containerId) {
        var c = document.getElementById(containerId || "bodymap-canvas-container");
        if (!c || !this.camera || !this.renderer) return;
        var w = c.clientWidth, h = c.clientHeight || 700;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
        if (this.composer) this.composer.setSize(w, h);
    },
```

**Step 4: Commit**

```bash
git add src/ui/static/js/bodymap3d.js
git commit -m "feat: switch animation loop to EffectComposer pipeline"
```

---

### Task 5: Verify Post-Processing Pipeline Renders

**Step 1: Start preview server**

`preview_start` (name: "hub")

**Step 2: Navigate to Body Map section and check console**

`preview_console_logs` — Look for:
- `[BodyMap3D] HDR environment loaded — studio_small_08_2k`
- `[BodyMap3D] Post-processing pipeline: RenderPass → SSAO → Bloom → Output`
- No errors about missing imports or failed HDR load

**Step 3: Take screenshot**

`preview_screenshot` — the scene should now render (though materials still have envMapIntensity: 0.0 at this point, so SSAO is the main visible difference).

**Step 4: If HDR fails to load (MIME type issue)**

Check `preview_network` for the HDR request. If 404 or wrong MIME type, add to Flask app.py:

```python
@app.after_request
def add_mime_types(response):
    if request.path.endswith('.hdr'):
        response.headers['Content-Type'] = 'application/octet-stream'
    return response
```

This is likely unnecessary — Flask serves static files fine — but verify.

---

### Task 6: Fix Material — Skin

**Files:**
- Modify: `src/ui/static/js/bodymap3d.js:1594-1623` (`_applySkinMaterial`)

**Step 1: Enable env map + keep MeshPhysicalMaterial**

Replace the skin material definition (around line 1598-1609):

```javascript
        var skinMat = new THREE.MeshPhysicalMaterial({
            color: new THREE.Color(0.72, 0.52, 0.40),
            roughness: 0.75,
            metalness: 0.0,
            clearcoat: 0.05,
            clearcoatRoughness: 0.4,
            sheen: 0.4,
            sheenRoughness: 0.5,
            sheenColor: new THREE.Color(0.6, 0.35, 0.25),
            envMapIntensity: 0.5,
            side: THREE.DoubleSide,
        });
```

Key changes from current:
- `envMapIntensity`: 0.0 → 0.5 (enable HDR reflections)
- `roughness`: 0.8 → 0.75 (slightly glossier for visible specular)
- `sheen`: 0.3 → 0.4 (richer subsurface appearance)
- `clearcoat`: 0.02 → 0.05 (subtle skin sheen)

**Step 2: Commit**

```bash
git add src/ui/static/js/bodymap3d.js
git commit -m "feat: enable HDR env reflections on skin material"
```

---

### Task 7: Fix Material — Muscles

**Files:**
- Modify: `src/ui/static/js/bodymap3d.js:1625-1705` (`_applyMuscleMaterial`)

**Step 1: Upgrade to MeshPhysicalMaterial + enable env map + fix tone mapping**

Replace the material creation block (around lines 1686-1693):

```javascript
            var mat = new THREE.MeshPhysicalMaterial({
                color: color,
                roughness: 0.5,
                metalness: 0.0,
                clearcoat: 0.08,
                clearcoatRoughness: 0.3,
                sheen: 0.25,
                sheenRoughness: 0.5,
                sheenColor: new THREE.Color(0.4, 0.06, 0.04),
                envMapIntensity: 0.4,
                side: THREE.DoubleSide,
            });
```

Key changes:
- `MeshStandardMaterial` → `MeshPhysicalMaterial` (adds clearcoat + sheen)
- Removed `toneMapped: false` (all materials now go through ACES consistently)
- Removed `envMapIntensity: 0.0` → set to 0.4
- Added `clearcoat` + `sheen` for wet muscle appearance
- `roughness`: 0.6 → 0.5 (wetter, glossier exposed muscle)

The sRGB base colors (`baseR = 0.45, baseG = 0.08, baseB = 0.06`) may need slight adjustment if ACES darkens them too much. Tune visually. Bump by ~10% if needed:

```javascript
        var baseR = 0.50, baseG = 0.09, baseB = 0.07;
```

Also update the tendon color assignment (around line 1676) — tendons keep their silvery-white appearance but with env map:

```javascript
            if (isTendon) {
                r = 0.55; g = 0.42; b = 0.34;
                tendonCount++;
            }
```

**Step 2: Commit**

```bash
git add src/ui/static/js/bodymap3d.js
git commit -m "feat: upgrade muscle to MeshPhysicalMaterial + enable env map + fix tone mapping"
```

---

### Task 8: Fix Material — Skeleton

**Files:**
- Modify: `src/ui/static/js/bodymap3d.js:1707-1731` (`_applySkeletonMaterial`)

**Step 1: Enable env map on bone material**

Replace the bone material (around lines 1709-1719):

```javascript
        var boneMat = new THREE.MeshPhysicalMaterial({
            color: new THREE.Color(0.92, 0.88, 0.78),
            roughness: 0.5,
            metalness: 0.0,
            clearcoat: 0.12,
            clearcoatRoughness: 0.35,
            sheen: 0.2,
            sheenRoughness: 0.6,
            sheenColor: new THREE.Color(0.85, 0.80, 0.65),
            envMapIntensity: 0.35,
            side: THREE.DoubleSide,
        });
```

Key changes:
- `envMapIntensity`: not set (defaulted 0) → 0.35
- `roughness`: 0.55 → 0.5 (slightly glossier waxy bone)
- `clearcoat`: 0.1 → 0.12

**Step 2: Commit**

```bash
git add src/ui/static/js/bodymap3d.js
git commit -m "feat: enable HDR env reflections on skeleton material"
```

---

### Task 9: Fix Material — Vasculature

**Files:**
- Modify: `src/ui/static/js/bodymap3d.js:1733-1775` (`_applyVasculatureMaterial`)

**Step 1: Enable env map on artery + vein materials**

Replace artery material (around lines 1735-1745):

```javascript
        var arteryMat = new THREE.MeshPhysicalMaterial({
            color: new THREE.Color(0.78, 0.12, 0.10),
            roughness: 0.35,
            metalness: 0.0,
            clearcoat: 0.2,
            clearcoatRoughness: 0.25,
            sheen: 0.35,
            sheenRoughness: 0.35,
            sheenColor: new THREE.Color(0.6, 0.08, 0.06),
            envMapIntensity: 0.6,
            side: THREE.DoubleSide,
        });
```

Replace vein material (around lines 1746-1755):

```javascript
        var veinMat = new THREE.MeshPhysicalMaterial({
            color: new THREE.Color(0.20, 0.25, 0.60),
            roughness: 0.4,
            metalness: 0.0,
            clearcoat: 0.15,
            clearcoatRoughness: 0.3,
            sheen: 0.3,
            sheenRoughness: 0.4,
            sheenColor: new THREE.Color(0.15, 0.18, 0.45),
            envMapIntensity: 0.6,
            side: THREE.DoubleSide,
        });
```

Key changes:
- `envMapIntensity` → 0.6 (blood vessels are the glossiest tissue)
- `roughness` lowered (wetter surface)
- `clearcoat` raised (wet membrane shine)

**Step 2: Commit**

```bash
git add src/ui/static/js/bodymap3d.js
git commit -m "feat: enable HDR env reflections on vasculature materials"
```

---

### Task 10: Fix Material — Nervous + Organs

**Files:**
- Modify: `src/ui/static/js/bodymap3d.js:1777-1806` (`_applyNervousMaterial`)
- Modify: `src/ui/static/js/bodymap3d.js:1808-1930+` (`_applyOrganMaterial`)

**Step 1: Enable env map on nerve material**

In `_applyNervousMaterial`, replace the nerveMat (around lines 1779-1789):

```javascript
        var nerveMat = new THREE.MeshPhysicalMaterial({
            color: new THREE.Color(0.95, 0.85, 0.35),
            roughness: 0.45,
            metalness: 0.0,
            clearcoat: 0.1,
            clearcoatRoughness: 0.45,
            sheen: 0.35,
            sheenRoughness: 0.35,
            sheenColor: new THREE.Color(0.80, 0.65, 0.20),
            envMapIntensity: 0.3,
            side: THREE.DoubleSide,
        });
```

**Step 2: Enable env map on organ materials**

In `_applyOrganMaterial`, find the material creation for each organ mesh. The organ material is created dynamically per-mesh (around line 1920-1931). Find where the `MeshStandardMaterial` or `MeshPhysicalMaterial` is created for organs and:

1. Ensure it's `MeshPhysicalMaterial` (not `MeshStandardMaterial`)
2. Add `envMapIntensity: 0.45`
3. Remove any `toneMapped: false` or `envMapIntensity: 0.0`
4. Add `clearcoat: 0.08`, `clearcoatRoughness: 0.4`, `sheen: 0.2`, `sheenRoughness: 0.5`

Read the full organ material section to find the exact location — the organ material creation involves per-organ-system color matching via keyword lookup.

**Step 3: Commit**

```bash
git add src/ui/static/js/bodymap3d.js
git commit -m "feat: enable HDR env reflections on nerve + organ materials"
```

---

### Task 11: Visual Verification + Tuning

**Step 1: Start preview server and navigate to Body Map**

`preview_start` (name: "hub")

**Step 2: Check console for all success messages**

Expected:
```
[BodyMap3D] HDR environment loaded — studio_small_08_2k
[BodyMap3D] Post-processing pipeline: RenderPass → SSAO → Bloom → Output
[BodyMap3D] Skin material applied...
[BodyMap3D] Muscle material applied...
```
No errors, no warnings.

**Step 3: Cycle through all layers and take screenshots**

For each layer (Skin, Muscle, Fascia, Skeleton, Organs, Vessels, Nerves):
1. Click the layer button
2. `preview_screenshot`
3. Verify: contact shadows visible at mesh boundaries (SSAO), subtle specular reflections from HDR env, consistent tone mapping

**Step 4: Tune if needed**

If muscles look too dark under ACES (they were bypassing it before), bump the base sRGB values ~10%.
If SSAO is too strong/weak, adjust `kernelRadius` and `maxDistance`.
If bloom is invisible or too bright, adjust `strength` and `threshold`.
If env reflections wash out colors, reduce per-material `envMapIntensity`.

**Step 5: Final commit**

```bash
git add src/ui/static/js/bodymap3d.js
git commit -m "fix: tune material parameters for production-level rendering"
```

---

### Task 12: Update Documentation

**Files:**
- Modify: `docs/3d-anatomy-journey.md`
- Modify: `CHANGELOG.md`

**Step 1: Update journey doc**

Add a new section under "Where We Are Now" documenting:
- HDR environment: studio_small_08_2k.hdr (Poly Haven, CC0)
- Post-processing pipeline: RenderPass → SSAOPass → UnrealBloomPass → OutputPass
- Material upgrades: all layers now MeshPhysicalMaterial with env map reflections
- Tone mapping fix: muscles no longer bypass ACES Filmic

**Step 2: Update CHANGELOG.md**

Add entry:
```markdown
## 2026-03-06

### Renderer Upgrade — Production-Level 3D Rendering
- Added HDR studio environment (Poly Haven studio_small_08, CC0) via RGBELoader + PMREMGenerator
- Added EffectComposer post-processing: SSAO (contact shadows) + UnrealBloom (specular highlights) + OutputPass
- Upgraded all tissue materials to MeshPhysicalMaterial with HDR env map reflections
- Fixed muscle tone mapping inconsistency (removed `toneMapped: false` bypass)
- Per-tissue env map intensity tuned for realism: skin 0.5, muscle 0.4, vasculature 0.6, bone 0.35, nerves 0.3, organs 0.45
```

**Step 3: Commit**

```bash
git add docs/3d-anatomy-journey.md CHANGELOG.md
git commit -m "docs: renderer upgrade — HDR env + SSAO + bloom pipeline"
```
