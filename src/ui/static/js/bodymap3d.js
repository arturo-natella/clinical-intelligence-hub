/* ══════════════════════════════════════════════════════════
   BodyMap3D — Three.js 3D Anatomy Viewer Controller
   Clinical Intelligence Hub

   Security: All user-facing text rendered via escapeHtml()
   before insertion into DOM. innerHTML usage is intentional
   and safe — all dynamic content is sanitized.
   ══════════════════════════════════════════════════════════ */

// eslint-disable-next-line no-unused-vars
var BodyMap3D = {

    // ── State ──────────────────────────────────────────────
    scene: null,
    camera: null,
    renderer: null,
    controls: null,
    clock: null,
    animationId: null,

    currentModel: null,
    currentGender: null,
    currentLayer: "skin",
    layers: {},
    pins: [],
    pinGroup: null,
    deformedMeshes: [],

    // ── Before/After + Translation state ───────────────────
    showingHealthy: false,
    cachedOrganFindings: null,
    cachedRegionFindings: null,

    raycaster: null,
    mouse: null,

    webglSupported: true,
    initialized: false,
    modelLoaded: false,

    // ── Region keyword mapping (from existing BodyMap) ──
    regionMapping: {
        head: ["neurology", "brain", "head", "neurological", "mental", "cognitive", "headache", "migraine", "seizure", "eye", "ear", "sinus", "thyroid"],
        chest: ["cardiac", "heart", "lung", "pulmonary", "respiratory", "chest", "cardio", "coronary", "thorax", "rib", "breast"],
        abdomen: ["gastro", "liver", "hepat", "pancrea", "stomach", "intestin", "colon", "abdom", "gallbladder", "spleen", "kidney", "renal"],
        pelvis: ["pelvic", "bladder", "uterus", "prostate", "reproduct", "urinary", "urological"],
        "left-arm": ["arm", "upper extremity", "shoulder", "elbow", "wrist", "hand"],
        "right-arm": ["arm", "upper extremity", "shoulder", "elbow", "wrist", "hand"],
        "left-leg": ["leg", "lower extremity", "hip", "knee", "ankle", "foot", "femur", "tibia"],
        "right-leg": ["leg", "lower extremity", "hip", "knee", "ankle", "foot", "femur", "tibia"],
    },

    // ── Mesh name → region mapping ──
    meshToRegion: {
        head: ["head", "brain", "skull", "cranium", "face", "jaw", "mandible", "eye", "ear", "nose", "thyroid"],
        chest: ["heart", "lung", "thorax", "rib", "ribcage", "sternum", "breast", "pectoral", "chest", "diaphragm"],
        abdomen: ["liver", "stomach", "intestin", "colon", "kidney", "renal", "spleen", "pancrea", "gallbladder", "abdomen"],
        pelvis: ["pelvis", "pelvic", "bladder", "uterus", "ovary", "ovaries", "fallopian", "prostate", "rectum", "sacrum"],
        "left-arm": ["left_arm", "left_shoulder", "left_elbow", "left_wrist", "left_hand", "left_humerus", "left_bicep"],
        "right-arm": ["right_arm", "right_shoulder", "right_elbow", "right_wrist", "right_hand", "right_humerus", "right_bicep"],
        "left-leg": ["left_leg", "left_hip", "left_knee", "left_ankle", "left_foot", "left_femur", "left_tibia"],
        "right-leg": ["right_leg", "right_hip", "right_knee", "right_ankle", "right_foot", "right_femur", "right_tibia"],
    },

    // ── 3D positions for pin placement ──
    regionPositions: null, // initialized in init()

    // ── Camera presets ──
    cameraPresets: null, // initialized in init()

    // ── Severity colors ──
    severityColors: {
        critical: 0xf05545,
        high:     0xf97316,
        moderate: 0xf0c550,
        low:      0x5a8ffc,
        info:     0x888888,
    },

    // ── Organ damage visual settings ──
    damageColors: {
        critical: { color: 0x8b0000, emissive: 0x440000, emissiveIntensity: 0.5 },
        high:     { color: 0xa04020, emissive: 0x331000, emissiveIntensity: 0.3 },
        moderate: { color: 0xb08040, emissive: 0x221100, emissiveIntensity: 0.15 },
        low:      { color: null, emissive: 0x001133, emissiveIntensity: 0.1 },
    },

    // ── Procedural deformation profiles ──────────────────
    // Maps condition keywords → physical geometry parameters:
    //   scale: [x,y,z] factors (1.0 = healthy baseline)
    //   noise: amplitude of surface displacement (0 = smooth)
    //   freq:  noise frequency (higher = finer bumps/scarring)
    //   pulse: animated pulsing amplitude (0 = static)
    deformationProfiles: {
        // ── Enlargement ──
        "enlarged":         { scale: [1.30, 1.30, 1.30], noise: 0.003, freq: 3.0, pulse: 0 },
        "cardiomegaly":     { scale: [1.40, 1.35, 1.40], noise: 0.003, freq: 3.0, pulse: 0.04 },
        "hepatomegaly":     { scale: [1.30, 1.20, 1.30], noise: 0.003, freq: 4.0, pulse: 0 },
        "splenomegaly":     { scale: [1.35, 1.30, 1.35], noise: 0.002, freq: 3.0, pulse: 0 },
        "hypertrophy":      { scale: [1.25, 1.25, 1.25], noise: 0.002, freq: 4.0, pulse: 0.02 },
        "dilated":          { scale: [1.30, 1.25, 1.30], noise: 0.002, freq: 3.0, pulse: 0.03 },
        "distended":        { scale: [1.25, 1.20, 1.25], noise: 0.003, freq: 3.5, pulse: 0 },
        "megaly":           { scale: [1.25, 1.25, 1.25], noise: 0.002, freq: 3.0, pulse: 0 },
        // ── Surface Roughness / Scarring ──
        "cirrhosis":        { scale: [1.10, 0.95, 1.10], noise: 0.020, freq: 8.0, pulse: 0 },
        "fibrosis":         { scale: [1.00, 1.00, 1.00], noise: 0.015, freq: 6.0, pulse: 0 },
        "scarring":         { scale: [1.00, 1.00, 1.00], noise: 0.012, freq: 7.0, pulse: 0 },
        "sclerosis":        { scale: [0.95, 0.95, 0.95], noise: 0.010, freq: 8.0, pulse: 0 },
        "calcification":    { scale: [1.00, 1.00, 1.00], noise: 0.015, freq: 10.0, pulse: 0 },
        "necrosis":         { scale: [0.90, 0.90, 0.90], noise: 0.020, freq: 8.0, pulse: 0 },
        // ── Shrinkage / Deflation ──
        "atelectasis":      { scale: [0.70, 0.60, 0.70], noise: 0.008, freq: 5.0, pulse: 0 },
        "collapse":         { scale: [0.65, 0.55, 0.65], noise: 0.010, freq: 4.0, pulse: 0 },
        "atrophy":          { scale: [0.75, 0.75, 0.75], noise: 0.005, freq: 6.0, pulse: 0 },
        "shrunk":           { scale: [0.80, 0.80, 0.80], noise: 0.003, freq: 5.0, pulse: 0 },
        "infarction":       { scale: [0.95, 0.95, 0.95], noise: 0.015, freq: 7.0, pulse: 0 },
        "ischemia":         { scale: [0.95, 0.95, 0.95], noise: 0.008, freq: 6.0, pulse: 0 },
        // ── Nodules / Masses ──
        "nodule":           { scale: [1.00, 1.00, 1.00], noise: 0.012, freq: 12.0, pulse: 0 },
        "mass":             { scale: [1.15, 1.15, 1.15], noise: 0.020, freq: 4.0, pulse: 0.01 },
        "tumor":            { scale: [1.20, 1.20, 1.20], noise: 0.025, freq: 3.5, pulse: 0.015 },
        "cancer":           { scale: [1.15, 1.15, 1.15], noise: 0.020, freq: 4.0, pulse: 0.015 },
        "malignant":        { scale: [1.15, 1.15, 1.15], noise: 0.022, freq: 4.5, pulse: 0.015 },
        "cyst":             { scale: [1.10, 1.10, 1.10], noise: 0.005, freq: 2.0, pulse: 0 },
        "polyp":            { scale: [1.05, 1.05, 1.05], noise: 0.010, freq: 10.0, pulse: 0 },
        "lesion":           { scale: [1.05, 1.05, 1.05], noise: 0.012, freq: 8.0, pulse: 0 },
        "metastas":         { scale: [1.10, 1.10, 1.10], noise: 0.020, freq: 6.0, pulse: 0.01 },
        // ── Inflammation / Swelling ──
        "inflammation":     { scale: [1.12, 1.12, 1.12], noise: 0.006, freq: 5.0, pulse: 0.03 },
        "inflamed":         { scale: [1.12, 1.12, 1.12], noise: 0.006, freq: 5.0, pulse: 0.03 },
        "edema":            { scale: [1.20, 1.20, 1.20], noise: 0.004, freq: 3.0, pulse: 0.02 },
        "swollen":          { scale: [1.15, 1.15, 1.15], noise: 0.005, freq: 4.0, pulse: 0.025 },
        "nephritis":        { scale: [1.15, 1.15, 1.15], noise: 0.010, freq: 6.0, pulse: 0.02 },
        "hepatitis":        { scale: [1.15, 1.10, 1.15], noise: 0.008, freq: 5.0, pulse: 0.02 },
        "pancreatitis":     { scale: [1.15, 1.10, 1.15], noise: 0.008, freq: 5.0, pulse: 0.025 },
        "pericarditis":     { scale: [1.10, 1.10, 1.10], noise: 0.006, freq: 5.0, pulse: 0.03 },
        "myocarditis":      { scale: [1.15, 1.15, 1.15], noise: 0.008, freq: 5.0, pulse: 0.04 },
        "colitis":          { scale: [1.10, 1.10, 1.10], noise: 0.008, freq: 6.0, pulse: 0.02 },
        "gastritis":        { scale: [1.10, 1.10, 1.10], noise: 0.006, freq: 5.0, pulse: 0.02 },
        // ── Respiratory ──
        "copd":             { scale: [1.15, 1.10, 1.15], noise: 0.008, freq: 5.0, pulse: 0 },
        "emphysema":        { scale: [1.20, 1.15, 1.20], noise: 0.010, freq: 4.0, pulse: 0 },
        "pneumonia":        { scale: [1.05, 1.00, 1.05], noise: 0.012, freq: 7.0, pulse: 0.02 },
        "effusion":         { scale: [1.10, 1.05, 1.10], noise: 0.003, freq: 3.0, pulse: 0 },
        "pneumothorax":     { scale: [0.70, 0.65, 0.70], noise: 0.005, freq: 4.0, pulse: 0 },
        "consolidation":    { scale: [1.05, 1.00, 1.05], noise: 0.010, freq: 6.0, pulse: 0 },
        // ── Cardiac ──
        "heart failure":    { scale: [1.30, 1.25, 1.30], noise: 0.005, freq: 3.0, pulse: 0.04 },
        "cardiomyopathy":   { scale: [1.30, 1.25, 1.30], noise: 0.008, freq: 4.0, pulse: 0.035 },
        "valvular":         { scale: [1.10, 1.10, 1.10], noise: 0.005, freq: 5.0, pulse: 0.025 },
        "stenosis":         { scale: [0.85, 0.85, 0.85], noise: 0.008, freq: 8.0, pulse: 0 },
        "aneurysm":         { scale: [1.35, 1.25, 1.35], noise: 0.010, freq: 3.0, pulse: 0.03 },
        // ── Renal ──
        "kidney disease":   { scale: [0.90, 0.90, 0.90], noise: 0.012, freq: 7.0, pulse: 0 },
        "polycystic":       { scale: [1.40, 1.35, 1.40], noise: 0.025, freq: 5.0, pulse: 0 },
        "hydronephrosis":   { scale: [1.30, 1.30, 1.30], noise: 0.005, freq: 3.0, pulse: 0 },
        "kidney stones":    { scale: [1.05, 1.05, 1.05], noise: 0.015, freq: 10.0, pulse: 0 },
        "nephrotic":        { scale: [1.15, 1.15, 1.15], noise: 0.008, freq: 5.0, pulse: 0.015 },
        // ── Hepatic ──
        "fatty liver":      { scale: [1.15, 1.10, 1.15], noise: 0.005, freq: 4.0, pulse: 0 },
        "steatosis":        { scale: [1.15, 1.10, 1.15], noise: 0.005, freq: 4.0, pulse: 0 },
        // ── Neurological ──
        "hydrocephalus":    { scale: [1.25, 1.30, 1.25], noise: 0.003, freq: 2.0, pulse: 0 },
        "cerebral edema":   { scale: [1.15, 1.15, 1.15], noise: 0.005, freq: 3.0, pulse: 0.02 },
        "brain atrophy":    { scale: [0.85, 0.85, 0.85], noise: 0.008, freq: 6.0, pulse: 0 },
    },


    // ═══════════════════════════════════════════════════════
    //  INITIALIZATION
    // ═══════════════════════════════════════════════════════

    init: function(containerId) {
        // Initialize Vector3 objects (requires THREE to be loaded)
        this.regionPositions = {
            head:        new THREE.Vector3(0, 1.55, 0.15),
            chest:       new THREE.Vector3(0, 0.85, 0.25),
            abdomen:     new THREE.Vector3(0, 0.25, 0.25),
            pelvis:      new THREE.Vector3(0, -0.15, 0.15),
            "left-arm":  new THREE.Vector3(0.45, 0.65, 0),
            "right-arm": new THREE.Vector3(-0.45, 0.65, 0),
            "left-leg":  new THREE.Vector3(0.18, -0.85, 0),
            "right-leg": new THREE.Vector3(-0.18, -0.85, 0),
        };

        this.cameraPresets = {
            head:        { position: new THREE.Vector3(0, 1.8, 1.2), target: new THREE.Vector3(0, 1.5, 0) },
            chest:       { position: new THREE.Vector3(0, 1.0, 1.5), target: new THREE.Vector3(0, 0.85, 0) },
            abdomen:     { position: new THREE.Vector3(0, 0.4, 1.5), target: new THREE.Vector3(0, 0.25, 0) },
            pelvis:      { position: new THREE.Vector3(0, -0.1, 1.5), target: new THREE.Vector3(0, -0.15, 0) },
            "left-arm":  { position: new THREE.Vector3(1.0, 0.7, 1.2), target: new THREE.Vector3(0.45, 0.65, 0) },
            "right-arm": { position: new THREE.Vector3(-1.0, 0.7, 1.2), target: new THREE.Vector3(-0.45, 0.65, 0) },
            "left-leg":  { position: new THREE.Vector3(0.5, -0.6, 1.5), target: new THREE.Vector3(0.18, -0.85, 0) },
            "right-leg": { position: new THREE.Vector3(-0.5, -0.6, 1.5), target: new THREE.Vector3(-0.18, -0.85, 0) },
            default:     { position: new THREE.Vector3(0, 0.5, 3.0), target: new THREE.Vector3(0, 0.5, 0) },
        };

        var container = document.getElementById(containerId);
        if (!container) return;

        // WebGL check
        try {
            var tc = document.createElement("canvas");
            if (!(tc.getContext("webgl2") || tc.getContext("webgl"))) throw new Error("No WebGL");
        } catch (e) {
            this.webglSupported = false;
            this.fallbackTo2D();
            return;
        }

        var canvas = document.getElementById("bodymap-canvas");
        if (!canvas) {
            canvas = document.createElement("canvas");
            canvas.id = "bodymap-canvas";
            container.appendChild(canvas);
        }

        var w = container.clientWidth;
        var h = container.clientHeight || 700;

        // Scene
        this.scene = new THREE.Scene();

        // Camera
        this.camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000);
        this.camera.position.copy(this.cameraPresets.default.position);

        // Renderer
        this.renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
        this.renderer.setSize(w, h);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.2;

        // Controls
        this.controls = new THREE.OrbitControls(this.camera, canvas);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.minDistance = 1.0;
        this.controls.maxDistance = 8.0;
        this.controls.target.copy(this.cameraPresets.default.target);
        this.controls.panSpeed = 0.5;
        this.controls.rotateSpeed = 0.8;

        // Lights
        this.scene.add(new THREE.AmbientLight(0xffffff, 0.6));
        var key = new THREE.DirectionalLight(0xffffff, 0.8);
        key.position.set(2, 3, 4);
        this.scene.add(key);
        var fill = new THREE.DirectionalLight(0xffffff, 0.3);
        fill.position.set(-2, 1, -2);
        this.scene.add(fill);

        // Raycaster
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();

        // Pin group
        this.pinGroup = new THREE.Group();
        this.scene.add(this.pinGroup);

        // Clock
        this.clock = new THREE.Clock();

        // Events
        var self = this;
        canvas.addEventListener("mousemove", function(e) { self.onMouseMove(e); });
        canvas.addEventListener("click", function(e) { self.onClick(e); });
        window.addEventListener("resize", function() { self.onWindowResize(containerId); });

        this.initialized = true;
        this.animate();
        this.autoLoadModel();
    },

    animate: function() {
        var self = this;
        this.animationId = requestAnimationFrame(function() { self.animate(); });
        if (this.controls) this.controls.update();

        // Animate pin pulse
        var t = this.clock ? this.clock.getElapsedTime() : 0;
        for (var i = 0; i < this.pins.length; i++) {
            var p = this.pins[i];
            if (p.sprite) {
                var s = 1.0 + 0.15 * Math.sin(t * 2 + i * 0.5);
                p.sprite.scale.set(0.06 * s, 0.06 * s, 1);
            }
        }

        // Animate deformed organs (pulsing for inflamed/damaged tissue)
        for (var j = 0; j < this.deformedMeshes.length; j++) {
            var dm = this.deformedMeshes[j];
            if (dm.pulse > 0 && dm.mesh) {
                var ps = 1.0 + dm.pulse * Math.sin(t * 1.5 + j * 0.7);
                dm.mesh.scale.set(ps, ps, ps);
            }
            
            // Update custom shader time if present
            if (dm.mesh.material && dm.mesh.material.userData && dm.mesh.material.userData.shader) {
                dm.mesh.material.userData.shader.uniforms.uTime.value = t;
            }
        }

        if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
    },

    destroy: function() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.renderer) this.renderer.dispose();
    },


    // ═══════════════════════════════════════════════════════
    //  MODEL LOADING
    // ═══════════════════════════════════════════════════════

    autoLoadModel: function() {
        var self = this;
        fetch("/api/demographics")
            .then(function(r) {
                if (!r.ok) throw new Error("No profile");
                return r.json();
            })
            .then(function(data) {
                var gender = "male";
                if (data && data.biological_sex) {
                    var sex = data.biological_sex.toLowerCase();
                    if (sex === "female" || sex === "f") gender = "female";
                }
                self.loadModel(gender);
            })
            .catch(function() {
                // Always load male model as default — don't block on missing data
                self.loadModel("male");
            });
    },

    loadModel: function(gender) {
        this.currentGender = gender;

        var toggle = document.getElementById("gender-toggle");
        if (toggle) {
            toggle.textContent = gender === "male" ? "\u2642" : "\u2640";
            toggle.title = "Currently: " + gender + " \u2014 Click to switch";
        }

        var loading = document.getElementById("bodymap-loading");
        if (loading) loading.style.display = "flex";

        var modelPath = "/models/" + gender + "_anatomy.glb";
        var self = this;

        fetch(modelPath, { method: "HEAD" })
            .then(function(r) {
                if (!r.ok) {
                    self.loadPlaceholderModel(gender);
                    return;
                }
                self._loadGLB(modelPath, gender);
            })
            .catch(function() { self.loadPlaceholderModel(gender); });
    },

    _loadGLB: function(path, gender) {
        var self = this;
        var loader = new THREE.GLTFLoader();

        try {
            var draco = new THREE.DRACOLoader();
            draco.setDecoderPath("https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/");
            loader.setDRACOLoader(draco);
        } catch (e) { /* Draco optional */ }

        loader.load(path, function(gltf) {
            self._onModelReady(gltf.scene, gender);
        }, null, function() {
            self.loadPlaceholderModel(gender);
        });
    },

    _onModelReady: function(modelScene, gender) {
        if (this.currentModel) this.scene.remove(this.currentModel);

        // Wrap in group so we can rotate + scale without affecting child transforms
        var wrapper = new THREE.Group();
        wrapper.add(modelScene);

        // Normalize model: scale to fit ~2 units tall, center at origin
        var box = new THREE.Box3().setFromObject(wrapper);
        var size = box.getSize(new THREE.Vector3());
        var maxDim = Math.max(size.x, size.y, size.z);
        var targetHeight = 2.0;
        var scale = targetHeight / maxDim;
        wrapper.scale.setScalar(scale);

        // GLB model has height along Z — rotate to stand upright (Y-up)
        if (size.z > size.y * 1.5) {
            wrapper.rotation.x = -Math.PI / 2;
        }

        // Force matrix update, then re-center
        wrapper.updateMatrixWorld(true);
        box.setFromObject(wrapper);
        var center = box.getCenter(new THREE.Vector3());
        wrapper.position.sub(center);
        // Lift so feet sit near y=0
        var halfH = (box.max.y - box.min.y) / 2;
        wrapper.position.y += halfH * 0.05;

        this.currentModel = wrapper;
        this.scene.add(wrapper);

        // Parse layers
        this.layers = { skin: [], muscle: [], skeleton: [], organs: [] };
        var self = this;

        modelScene.traverse(function(child) {
            var n = (child.name || "").toLowerCase();
            if (n.indexOf("layer_skin") >= 0 || n.indexOf("skin") === 0) self.layers.skin.push(child);
            else if (n.indexOf("layer_muscle") >= 0 || n.indexOf("muscle") === 0) self.layers.muscle.push(child);
            else if (n.indexOf("layer_skeleton") >= 0 || n.indexOf("skeleton") === 0 || n.indexOf("bone") === 0) self.layers.skeleton.push(child);
            else if (n.indexOf("layer_organs") >= 0 || n.indexOf("organ") === 0) self.layers.organs.push(child);

            // Store original material colors + geometry for damage visualization & deformation
            if (child.isMesh && child.material) {
                child.userData.originalColor = child.material.color ? child.material.color.getHex() : 0xcccccc;
                child.userData.originalEmissive = child.material.emissive ? child.material.emissive.getHex() : 0x000000;
            }
            if (child.isMesh && child.geometry && child.geometry.attributes.position) {
                child.userData.originalPositions = child.geometry.attributes.position.array.slice();
            }

            if (child.isMesh) child.userData.region = self._meshNameToRegion(n);
        });

        this.setLayer(this.currentLayer);

        var loading = document.getElementById("bodymap-loading");
        if (loading) loading.style.display = "none";

        this.modelLoaded = true;
        this.loadFindings();
    },

    _meshNameToRegion: function(name) {
        var regions = Object.keys(this.meshToRegion);
        for (var i = 0; i < regions.length; i++) {
            var kw = this.meshToRegion[regions[i]];
            for (var j = 0; j < kw.length; j++) {
                if (name.indexOf(kw[j]) >= 0) return regions[i];
            }
        }
        return null;
    },


    // ═══════════════════════════════════════════════════════
    //  PLACEHOLDER MODEL
    // ═══════════════════════════════════════════════════════

    loadPlaceholderModel: function(gender) {
        var group = new THREE.Group();

        var skinMat = new THREE.MeshPhongMaterial({ color: 0x8d6e63, transparent: true, opacity: 0.85, side: THREE.DoubleSide });
        var organMat = new THREE.MeshPhongMaterial({ color: 0xc62828, transparent: true, opacity: 0.7 });
        var skeleMat = new THREE.MeshPhongMaterial({ color: 0xefebe9, transparent: true, opacity: 0.7 });
        var muscleMat = new THREE.MeshPhongMaterial({ color: 0xb71c1c, transparent: true, opacity: 0.7 });

        // ── Skin layer ──
        var skinG = new THREE.Group(); skinG.name = "layer_skin";
        this._addMesh(skinG, new THREE.SphereGeometry(0.18, 24, 24), skinMat, "skin_head", "head", [0, 1.55, 0]);
        this._addMesh(skinG, new THREE.CylinderGeometry(0.28, 0.22, 1.0, 16), skinMat, "skin_torso", "chest", [0, 0.85, 0]);
        this._addMesh(skinG, new THREE.CylinderGeometry(0.22, 0.2, 0.5, 16), skinMat, "skin_abdomen", "abdomen", [0, 0.1, 0]);
        this._addMesh(skinG, new THREE.CylinderGeometry(0.2, 0.18, 0.3, 16), skinMat, "skin_pelvis", "pelvis", [0, -0.25, 0]);

        var armGeo = new THREE.CylinderGeometry(0.06, 0.05, 0.8, 8);
        var la = this._addMesh(skinG, armGeo, skinMat, "skin_left_arm", "left-arm", [0.38, 0.75, 0]);
        la.rotation.z = -0.2;
        var ra = this._addMesh(skinG, armGeo, skinMat, "skin_right_arm", "right-arm", [-0.38, 0.75, 0]);
        ra.rotation.z = 0.2;

        var legGeo = new THREE.CylinderGeometry(0.08, 0.06, 1.0, 8);
        this._addMesh(skinG, legGeo, skinMat, "skin_left_leg", "left-leg", [0.12, -0.9, 0]);
        this._addMesh(skinG, legGeo, skinMat, "skin_right_leg", "right-leg", [-0.12, -0.9, 0]);
        group.add(skinG);

        // ── Skeleton layer ──
        var skeleG = new THREE.Group(); skeleG.name = "layer_skeleton";
        this._addMesh(skeleG, new THREE.CylinderGeometry(0.03, 0.03, 1.4, 6), skeleMat, "skeleton_spine", "chest", [0, 0.6, -0.05]);
        this._addMesh(skeleG, new THREE.SphereGeometry(0.14, 16, 16), skeleMat, "skeleton_skull", "head", [0, 1.55, 0]);
        var ribGeo = new THREE.TorusGeometry(0.2, 0.02, 4, 12, Math.PI);
        var ribs = this._addMesh(skeleG, ribGeo, skeleMat, "skeleton_ribcage", "chest", [0, 0.9, 0.05]);
        ribs.rotation.x = Math.PI / 2;
        group.add(skeleG);

        // ── Organs layer ──
        var orgG = new THREE.Group(); orgG.name = "layer_organs";
        this._addMesh(orgG, new THREE.SphereGeometry(0.06, 12, 12), organMat, "organ_heart", "chest", [0.05, 0.95, 0.1]);

        var lungMat = organMat.clone(); lungMat.color.setHex(0xef9a9a);
        var lungGeo = new THREE.SphereGeometry(0.1, 12, 12);
        this._addMesh(orgG, lungGeo, lungMat, "organ_lung_left", "chest", [0.15, 0.9, 0.05]);
        this._addMesh(orgG, lungGeo, lungMat.clone(), "organ_lung_right", "chest", [-0.15, 0.9, 0.05]);

        var liverMat = organMat.clone(); liverMat.color.setHex(0x8d6e63);
        this._addMesh(orgG, new THREE.SphereGeometry(0.1, 12, 12), liverMat, "organ_liver", "abdomen", [-0.1, 0.55, 0.1]);

        var kidneyMat = organMat.clone(); kidneyMat.color.setHex(0x795548);
        this._addMesh(orgG, new THREE.SphereGeometry(0.04, 8, 8), kidneyMat, "organ_kidney_left", "abdomen", [0.12, 0.45, -0.05]);
        this._addMesh(orgG, new THREE.SphereGeometry(0.04, 8, 8), kidneyMat.clone(), "organ_kidney_right", "abdomen", [-0.12, 0.45, -0.05]);

        if (gender === "female") {
            var fMat = organMat.clone(); fMat.color.setHex(0xe91e63);
            this._addMesh(orgG, new THREE.SphereGeometry(0.05, 12, 12), fMat, "organ_uterus", "pelvis", [0, -0.1, 0.05]);
            this._addMesh(orgG, new THREE.SphereGeometry(0.02, 8, 8), fMat.clone(), "organ_ovary_left", "pelvis", [0.06, -0.08, 0.05]);
            this._addMesh(orgG, new THREE.SphereGeometry(0.02, 8, 8), fMat.clone(), "organ_ovary_right", "pelvis", [-0.06, -0.08, 0.05]);
        } else {
            var pMat = organMat.clone(); pMat.color.setHex(0x7986cb);
            this._addMesh(orgG, new THREE.SphereGeometry(0.03, 8, 8), pMat, "organ_prostate", "pelvis", [0, -0.15, -0.02]);
        }
        group.add(orgG);

        // ── Muscle layer ──
        var muscG = new THREE.Group(); muscG.name = "layer_muscle";
        this._addMesh(muscG, new THREE.CylinderGeometry(0.26, 0.2, 0.9, 16), muscleMat, "muscle_torso", "chest", [0, 0.85, 0]);
        group.add(muscG);

        this._onModelReady(group, gender);
    },

    _addMesh: function(parent, geo, mat, name, region, pos) {
        var mesh = new THREE.Mesh(geo, mat.clone());
        mesh.position.set(pos[0], pos[1], pos[2]);
        mesh.name = name;
        mesh.userData.region = region;
        mesh.userData.originalColor = mat.color.getHex();
        mesh.userData.originalEmissive = 0x000000;
        parent.add(mesh);
        return mesh;
    },


    // ═══════════════════════════════════════════════════════
    //  LAYER CONTROL
    // ═══════════════════════════════════════════════════════

    setLayer: function(layer) {
        this.currentLayer = layer;
        var layerNames = ["skin", "muscle", "skeleton", "organs"];
        if (!this.currentModel) return;

        this.currentModel.traverse(function(child) {
            var n = (child.name || "").toLowerCase();
            for (var i = 0; i < layerNames.length; i++) {
                var ln = layerNames[i];
                if (n.indexOf("layer_" + ln) >= 0 || n === ln) {
                    if (ln === layer) {
                        child.visible = true;
                        if (child.isMesh && child.material) {
                            child.material.opacity = 1.0;
                            child.material.transparent = false;
                        }
                    } else if (ln === "skin" && layer !== "skin") {
                        // Ghost the skin outline
                        child.visible = true;
                        if (child.isMesh && child.material) {
                            child.material.transparent = true;
                            child.material.opacity = 0.08;
                        }
                    } else {
                        child.visible = false;
                    }
                }
            }
        });

        // Update buttons
        var btns = document.querySelectorAll(".bodymap-layer");
        for (var b = 0; b < btns.length; b++) {
            if (btns[b].dataset.layer === layer) btns[b].classList.add("active");
            else btns[b].classList.remove("active");
        }
    },


    // ═══════════════════════════════════════════════════════
    //  NAVIGATION
    // ═══════════════════════════════════════════════════════

    focusRegion: function(region) {
        var preset = this.cameraPresets[region] || this.cameraPresets.default;
        this._animateCamera(preset.position, preset.target);
    },

    resetView: function() {
        this._animateCamera(this.cameraPresets.default.position, this.cameraPresets.default.target);
    },

    _animateCamera: function(endPos, endTarget) {
        if (!this.camera || !this.controls) return;
        var self = this;
        var startPos = this.camera.position.clone();
        var startTarget = this.controls.target.clone();
        var dur = 800;
        var start = performance.now();

        function step(now) {
            var raw = Math.min((now - start) / dur, 1);
            var t = raw < 0.5 ? 4 * raw * raw * raw : 1 - Math.pow(-2 * raw + 2, 3) / 2;
            self.camera.position.lerpVectors(startPos, endPos, t);
            self.controls.target.lerpVectors(startTarget, endTarget, t);
            if (raw < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    },


    // ═══════════════════════════════════════════════════════
    //  CLINICAL DATA + ORGAN DAMAGE VISUALIZATION
    // ═══════════════════════════════════════════════════════

    loadFindings: function() {
        var self = this;
        Promise.all([
            fetch("/api/diagnoses").then(function(r) { return r.ok ? r.json() : []; }).catch(function() { return []; }),
            fetch("/api/imaging").then(function(r) { return r.ok ? r.json() : []; }).catch(function() { return []; }),
            fetch("/api/labs").then(function(r) { return r.ok ? r.json() : []; }).catch(function() { return []; }),
            fetch("/api/flags").then(function(r) { return r.ok ? r.json() : []; }).catch(function() { return []; }),
        ]).then(function(results) {
            self.clearPins();
            self._resetOrganColors();

            var regionFindings = {};
            var organFindings = {}; // mesh-level findings for damage vis

            // Diagnoses
            var dx = results[0];
            for (var a = 0; a < dx.length; a++) {
                var txt = ((dx[a].name || "") + " " + (dx[a].status || "")).toLowerCase();
                var reg = self._textToRegion(txt);
                if (reg) {
                    if (!regionFindings[reg]) regionFindings[reg] = [];
                    regionFindings[reg].push({ type: "diagnosis", name: dx[a].name || "", severity: dx[a].severity || "moderate", source: dx[a].source_file || "", page: dx[a].source_page || "", date: dx[a].date_extracted || "" });

                    // Map to specific organ meshes for damage vis
                    self._mapToOrganMeshes(txt, dx[a].severity || "moderate", organFindings);
                }
            }

            // Imaging
            var img = results[1];
            for (var b = 0; b < img.length; b++) {
                var itxt = ((img[b].study_type || "") + " " + (img[b].description || "")).toLowerCase();
                var ir = self._textToRegion(itxt);
                if (ir) {
                    if (!regionFindings[ir]) regionFindings[ir] = [];
                    regionFindings[ir].push({ type: "imaging", name: img[b].study_type || "Imaging", severity: img[b].severity || "info", source: img[b].source_file || "", page: img[b].source_page || "", date: img[b].study_date || "" });
                    self._mapToOrganMeshes(itxt, img[b].severity || "info", organFindings);
                }
            }

            // Flags
            var fl = results[3];
            for (var c = 0; c < fl.length; c++) {
                var ftxt = ((fl[c].description || "") + " " + (fl[c].category || "")).toLowerCase();
                var fr = self._textToRegion(ftxt);
                if (fr) {
                    if (!regionFindings[fr]) regionFindings[fr] = [];
                    regionFindings[fr].push({ type: "flag", name: fl[c].description || "Flag", severity: fl[c].severity || "high", source: fl[c].source_file || "", page: fl[c].source_page || "", date: fl[c].date || "" });
                    self._mapToOrganMeshes(ftxt, fl[c].severity || "high", organFindings);
                }
            }

            // Cache findings for Before/After toggle
            self.cachedRegionFindings = regionFindings;
            self.cachedOrganFindings = organFindings;

            // Place pins
            var regions = Object.keys(regionFindings);
            for (var d = 0; d < regions.length; d++) {
                var r = regions[d];
                var findings = regionFindings[r];
                var highest = self._highestSeverity(findings);
                self._placePin(r, findings.length, highest, findings);
            }

            // Apply damage visualization to organ meshes
            if (!self.showingHealthy) {
                self._applyOrganDamage(organFindings);
            }

            // Reset toggle button state
            var btn = document.getElementById("bodymap-healthy-toggle");
            if (btn) {
                self.showingHealthy = false;
                btn.textContent = "Show Healthy";
                btn.classList.remove("active");
            }
        });
    },

    _mapToOrganMeshes: function(text, severity, organFindings) {
        // Map finding text to specific organ mesh keywords for visual damage
        var organKeywords = {
            "organ_heart": ["heart", "cardiac", "cardio", "coronary", "atrial", "ventricular"],
            "organ_lung": ["lung", "pulmonary", "respiratory", "bronch", "pleural"],
            "organ_liver": ["liver", "hepat", "hepatic", "cirrhosis", "hepatitis"],
            "organ_kidney": ["kidney", "renal", "nephro", "creatinine"],
            "organ_stomach": ["stomach", "gastric", "peptic"],
            "organ_pancrea": ["pancrea", "insulin"],
            "organ_brain": ["brain", "cerebr", "neurolog"],
            "organ_uterus": ["uterus", "uterine", "endometri"],
            "organ_ovary": ["ovary", "ovarian"],
            "organ_prostate": ["prostate", "prostatic"],
        };

        var organs = Object.keys(organKeywords);
        for (var i = 0; i < organs.length; i++) {
            var kws = organKeywords[organs[i]];
            for (var j = 0; j < kws.length; j++) {
                if (text.indexOf(kws[j]) >= 0) {
                    var key = organs[i];
                    if (!organFindings[key]) organFindings[key] = [];
                    organFindings[key].push({ severity: severity, text: text });
                    break;
                }
            }
        }
    },

    _applyOrganDamage: function(organFindings) {
        // Visually alter organ mesh materials AND geometry based on findings
        if (!this.currentModel) return;
        var self = this;

        this.currentModel.traverse(function(child) {
            if (!child.isMesh || !child.material) return;
            var n = (child.name || "").toLowerCase();

            // Check if this mesh has findings mapped to it
            var matchedKey = null;
            var organs = Object.keys(organFindings);
            for (var i = 0; i < organs.length; i++) {
                if (n.indexOf(organs[i]) >= 0) {
                    matchedKey = organs[i];
                    break;
                }
            }

            if (matchedKey) {
                var entries = organFindings[matchedKey];
                var worst = self._highestSeverity(entries);

                // 1) Procedural deformation (CPU-side base scale/pulse)
                var deformation = self._conditionToDeformation(entries);
                if (deformation) {
                    self._applyMeshDeformation(child, deformation);
                }

                // 2) Overkill Procedural Shader (GPU-side bumps, scarring, discoloration)
                // We clone the material so we don't accidentally infect healthy organs that share it
                if (!child.userData.hasCustomShader) {
                    child.material = child.material.clone();
                    child.userData.hasCustomShader = true;
                    
                    var severityMap = { "critical": 1.0, "high": 0.7, "moderate": 0.4, "low": 0.2, "info": 0.0 };
                    var damageFloat = severityMap[worst] || 0.0;
                    
                    // Determine disease type for the shader
                    // 1: Hypertrophy/Enlarged/Swollen (Red, throbbing, bulging)
                    // 2: Cirrhosis/Scarring/Necrosis (Bumpy, yellow/brown, rough)
                    // 3: Deflation/Atrophy/Collapse (Shrunken, grey/blue, dense)
                    var diseaseType = 0;
                    var keys = Object.keys(self.deformationProfiles);
                    var combinedText = entries.map(function(e) { return e.text; }).join(" ").toLowerCase();
                    
                    if (combinedText.indexOf("cirrhosis") >= 0 || combinedText.indexOf("fibrosis") >= 0 || combinedText.indexOf("scarring") >= 0 || combinedText.indexOf("necrosis") >= 0) {
                        diseaseType = 2;
                    } else if (combinedText.indexOf("collapse") >= 0 || combinedText.indexOf("atrophy") >= 0 || combinedText.indexOf("atelectasis") >= 0) {
                        diseaseType = 3;
                    } else if (damageFloat > 0) {
                        diseaseType = 1; // Default to inflamed/swollen
                    }

                    child.material.onBeforeCompile = function(shader) {
                        shader.uniforms.uDamage = { value: damageFloat };
                        shader.uniforms.uTime = { value: 0 };
                        shader.uniforms.uDiseaseType = { value: diseaseType };
                        child.material.userData.shader = shader; // Save ref for animation loop

                        // Inject Uniforms
                        shader.vertexShader = `
                            uniform float uDamage;
                            uniform float uTime;
                            uniform int uDiseaseType;
                            
                            // 3D Noise function for procedural bumps
                            vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
                            vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
                            vec4 permute(vec4 x) { return mod289(((x*34.0)+1.0)*x); }
                            vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
                            float snoise(vec3 v) {
                                const vec2  C = vec2(1.0/6.0, 1.0/3.0) ;
                                const vec4  D = vec4(0.0, 0.5, 1.0, 2.0);
                                vec3 i  = floor(v + dot(v, C.yyy) );
                                vec3 x0 = v - i + dot(i, C.xxx) ;
                                vec3 g = step(x0.yzx, x0.xyz);
                                vec3 l = 1.0 - g;
                                vec3 i1 = min( g.xyz, l.zxy );
                                vec3 i2 = max( g.xyz, l.zxy );
                                vec3 x1 = x0 - i1 + C.xxx;
                                vec3 x2 = x0 - i2 + C.yyy;
                                vec3 x3 = x0 - D.yyy;
                                i = mod289(i);
                                vec4 p = permute( permute( permute(
                                            i.z + vec4(0.0, i1.z, i2.z, 1.0 ))
                                        + i.y + vec4(0.0, i1.y, i2.y, 1.0 ))
                                        + i.x + vec4(0.0, i1.x, i2.x, 1.0 ));
                                float n_ = 0.142857142857;
                                vec3  ns = n_ * D.wyz - D.xzx;
                                vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
                                vec4 x_ = floor(j * ns.z);
                                vec4 y_ = floor(j - 7.0 * x_ );
                                vec4 x = x_ *ns.x + ns.yyyy;
                                vec4 y = y_ *ns.x + ns.yyyy;
                                vec4 h = 1.0 - abs(x) - abs(y);
                                vec4 b0 = vec4( x.xy, y.xy );
                                vec4 b1 = vec4( x.zw, y.zw );
                                vec4 s0 = floor(b0)*2.0 + 1.0;
                                vec4 s1 = floor(b1)*2.0 + 1.0;
                                vec4 sh = -step(h, vec4(0.0));
                                vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy ;
                                vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww ;
                                vec3 p0 = vec3(a0.xy,h.x);
                                vec3 p1 = vec3(a0.zw,h.y);
                                vec3 p2 = vec3(a1.xy,h.z);
                                vec3 p3 = vec3(a1.zw,h.w);
                                vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
                                p0 *= norm.x;
                                p1 *= norm.y;
                                p2 *= norm.z;
                                p3 *= norm.w;
                                vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
                                m = m * m;
                                return 42.0 * dot( m*m, vec4( dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3) ) );
                            }
                            
                            varying float vDamageOutput;
                            varying vec3 vWorldPos;
                        ` + shader.vertexShader;

                        // Inject Vertex Displacement
                        shader.vertexShader = shader.vertexShader.replace(
                            '#include <begin_vertex>',
                            `
                            vec3 transformed = vec3( position );
                            vWorldPos = (modelMatrix * vec4(position, 1.0)).xyz;
                            vDamageOutput = 0.0;
                            
                            if (uDamage > 0.0) {
                                // Hypertrophy/Swelling - smoothly balloon out
                                if (uDiseaseType == 1) {
                                    float pulse = sin(uTime * 3.0) * 0.5 + 0.5;
                                    transformed += normal * (uDamage * 0.08 * (1.0 + pulse * 0.2));
                                    vDamageOutput = uDamage * (0.8 + pulse * 0.2);
                                } 
                                // Cirrhosis/Scarring - procedural bumpy displacement
                                else if (uDiseaseType == 2) {
                                    // High frequency noise for rough scarred texture
                                    float bump = snoise(vWorldPos * 60.0);
                                    // Low frequency noise for larger lumps (macronodular)
                                    float lump = snoise(vWorldPos * 15.0);
                                    
                                    float totalDisplacement = (bump * 0.3 + lump * 0.7) * uDamage * 0.02;
                                    transformed += normal * totalDisplacement;
                                    
                                    // Pass noise value to fragment shader to color the bumps
                                    vDamageOutput = max(0.0, totalDisplacement) * 50.0;
                                }
                                // Atrophy/Collapse - shrivel
                                else if (uDiseaseType == 3) {
                                    // Deflate geometry along normals inward
                                    float noise = snoise(vWorldPos * 20.0) * 0.5 + 0.5;
                                    transformed -= normal * (uDamage * 0.05 * noise);
                                    vDamageOutput = uDamage * noise;
                                }
                            }
                            `
                        );

                        // Inject Fragment Uniforms
                        shader.fragmentShader = `
                            uniform float uDamage;
                            uniform int uDiseaseType;
                            varying float vDamageOutput;
                            varying vec3 vWorldPos;
                        ` + shader.fragmentShader;

                        // Inject Fragment Colors
                        shader.fragmentShader = shader.fragmentShader.replace(
                            '#include <color_fragment>',
                            `
                            #include <color_fragment>
                            
                            if (uDamage > 0.0) {
                                vec3 diseaseColor = diffuseColor.rgb;
                                
                                // 1: Hypertrophy/Inflammation -> Angry Red / Glowing
                                if (uDiseaseType == 1) {
                                    diseaseColor = vec3(0.6, 0.0, 0.0);
                                    // Add fiery glowing edges based on vertex output
                                    diffuseColor.rgb = mix(diffuseColor.rgb, diseaseColor, vDamageOutput);
                                    diffuseColor.rgb += vec3(0.3, 0.0, 0.0) * vDamageOutput * 0.5;
                                }
                                // 2: Cirrhosis/Fibrosis -> Yellowish/Brown necrotic tissue
                                else if (uDiseaseType == 2) {
                                    // Base sick color
                                    vec3 sickBase = mix(diffuseColor.rgb, vec3(0.5, 0.4, 0.2), uDamage);
                                    // Scars are lighter/yellower
                                    vec3 scarColor = vec3(0.8, 0.7, 0.4);
                                    diffuseColor.rgb = mix(sickBase, scarColor, clamp(vDamageOutput * uDamage, 0.0, 1.0));
                                }
                                // 3: Ischemia/Atrophy/Collapse -> Pale, cyanotic (blue/grey)
                                else if (uDiseaseType == 3) {
                                    diseaseColor = vec3(0.3, 0.3, 0.4); // Dead/oxygen deprived
                                    diffuseColor.rgb = mix(diffuseColor.rgb, diseaseColor, clamp(uDamage + vDamageOutput, 0.0, 1.0));
                                }
                            }
                            `
                        );
                    };
                    
                    // Force material recompile
                    child.material.needsUpdate = true;
                }
            }
        });
    },

    _resetOrganColors: function() {
        this._clearDeformations();
        if (!this.currentModel) return;
        this.currentModel.traverse(function(child) {
            if (!child.isMesh || !child.material) return;
            if (child.userData.originalColor !== undefined) {
                child.material.color.setHex(child.userData.originalColor);
            }
            if (child.material.emissive && child.userData.originalEmissive !== undefined) {
                child.material.emissive.setHex(child.userData.originalEmissive);
                child.material.emissiveIntensity = 0;
            }
            
            // Reset custom GLSL shader damage if present
            if (child.material.userData && child.material.userData.shader) {
                child.material.userData.shader.uniforms.uDamage.value = 0.0;
            }
        });
    },

    // ═══════════════════════════════════════════════════════
    //  PROCEDURAL DEFORMATION ENGINE
    // ═══════════════════════════════════════════════════════

    /**
     * 3D value noise — smooth pseudo-random values in [0,1]
     * for any 3D coordinate. Used to generate organic surface
     * displacement on organ meshes.
     */
    _noise3d: function(x, y, z) {
        function hash(n) { var s = Math.sin(n) * 43758.5453123; return s - Math.floor(s); }
        var ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
        var fx = x - ix, fy = y - iy, fz = z - iz;
        // Smoothstep interpolation for organic blending
        var ux = fx * fx * (3.0 - 2.0 * fx);
        var uy = fy * fy * (3.0 - 2.0 * fy);
        var uz = fz * fz * (3.0 - 2.0 * fz);
        // 8-corner hash for trilinear interpolation
        var n = ix + iy * 157 + iz * 113;
        var a  = hash(n);
        var b  = hash(n + 1);
        var c  = hash(n + 157);
        var d  = hash(n + 158);
        var e  = hash(n + 113);
        var f  = hash(n + 114);
        var g  = hash(n + 270);
        var hh = hash(n + 271);
        var l1 = a + ux * (b - a) + uy * (c - a) + ux * uy * (a - b - c + d);
        var l2 = e + ux * (f - e) + uy * (g - e) + ux * uy * (e - f - g + hh);
        return l1 + uz * (l2 - l1);
    },

    /**
     * Fractal Brownian Motion — layers multiple octaves of noise
     * at increasing frequencies for richer, more organic surface
     * detail (bumps within bumps, like real tissue scarring).
     */
    _fbm3d: function(x, y, z, octaves) {
        var value = 0, amplitude = 0.5, frequency = 1.0, total = 0;
        for (var i = 0; i < (octaves || 4); i++) {
            value += amplitude * this._noise3d(x * frequency, y * frequency, z * frequency);
            total += amplitude;
            amplitude *= 0.5;
            frequency *= 2.0;
        }
        return value / total;
    },

    /**
     * Analyze all finding entries for a mesh and select the most
     * visually dramatic deformation profile. If no specific
     * condition keyword matches, falls back to severity-based
     * generic deformation.
     */
    _conditionToDeformation: function(entries) {
        if (!entries || entries.length === 0) return null;
        var profiles = this.deformationProfiles;
        var keys = Object.keys(profiles);
        var bestMatch = null;
        var bestPriority = -1;

        for (var i = 0; i < entries.length; i++) {
            var text = (entries[i].text || "").toLowerCase();
            for (var j = 0; j < keys.length; j++) {
                if (text.indexOf(keys[j]) >= 0) {
                    var prof = profiles[keys[j]];
                    // Prioritize by visual impact: noise amplitude + scale deviation from 1.0
                    var impact = prof.noise + Math.abs(prof.scale[0] - 1.0) * 0.1;
                    if (impact > bestPriority) {
                        bestPriority = impact;
                        bestMatch = prof;
                    }
                }
            }
        }

        // Severity-based fallback when no specific condition matched
        if (!bestMatch) {
            var worst = this._highestSeverity(entries);
            if (worst === "critical") bestMatch = { scale: [1.15, 1.15, 1.15], noise: 0.015, freq: 6.0, pulse: 0.03 };
            else if (worst === "high") bestMatch = { scale: [1.08, 1.08, 1.08], noise: 0.008, freq: 5.0, pulse: 0.015 };
            else if (worst === "moderate") bestMatch = { scale: [1.0, 1.0, 1.0], noise: 0.004, freq: 4.0, pulse: 0 };
        }

        return bestMatch;
    },

    /**
     * Apply procedural vertex displacement to a mesh.
     * Clones geometry (safety for shared buffers), displaces
     * each vertex along its normal using fBm noise, and applies
     * non-uniform scaling. Stores original positions for reset.
     */
    _applyMeshDeformation: function(mesh, deformation) {
        if (!mesh.geometry || !mesh.geometry.attributes.position) return;

        // Clone geometry if shared (prevents corrupting other meshes)
        if (!mesh.userData._geometryCloned) {
            mesh.geometry = mesh.geometry.clone();
            mesh.userData._geometryCloned = true;
        }

        // Store original vertex positions for reset
        if (!mesh.userData.originalPositions) {
            mesh.userData.originalPositions = mesh.geometry.attributes.position.array.slice();
        }

        var positions = mesh.geometry.attributes.position;
        var originals = mesh.userData.originalPositions;

        // Compute normals if missing (displacement direction)
        var normals = mesh.geometry.attributes.normal;
        if (!normals) {
            mesh.geometry.computeVertexNormals();
            normals = mesh.geometry.attributes.normal;
        }
        if (!normals) return;

        var noiseAmp = deformation.noise || 0;
        var noiseFreq = deformation.freq || 5.0;
        var sx = deformation.scale ? deformation.scale[0] : 1.0;
        var sy = deformation.scale ? deformation.scale[1] : 1.0;
        var sz = deformation.scale ? deformation.scale[2] : 1.0;

        for (var i = 0; i < positions.count; i++) {
            var ox = originals[i * 3];
            var oy = originals[i * 3 + 1];
            var oz = originals[i * 3 + 2];

            // Noise-based displacement along surface normal
            var displacement = 0;
            if (noiseAmp > 0) {
                var n = this._fbm3d(ox * noiseFreq, oy * noiseFreq, oz * noiseFreq, 4);
                displacement = (n - 0.5) * 2.0 * noiseAmp;
            }

            var nx = normals.getX(i);
            var ny = normals.getY(i);
            var nz = normals.getZ(i);

            // Apply: scaled position + noise displacement along normal
            positions.setXYZ(i,
                ox * sx + nx * displacement,
                oy * sy + ny * displacement,
                oz * sz + nz * displacement
            );
        }

        positions.needsUpdate = true;
        mesh.geometry.computeVertexNormals();
        mesh.geometry.computeBoundingSphere();

        // Track for animation + reset
        this.deformedMeshes.push({
            mesh: mesh,
            pulse: deformation.pulse || 0,
        });
    },

    /**
     * Restore a mesh to its pre-deformation geometry.
     */
    _restoreOriginalGeometry: function(mesh) {
        if (!mesh.userData.originalPositions || !mesh.geometry) return;
        var positions = mesh.geometry.attributes.position;
        var originals = mesh.userData.originalPositions;

        for (var i = 0; i < positions.count; i++) {
            positions.setXYZ(i, originals[i * 3], originals[i * 3 + 1], originals[i * 3 + 2]);
        }

        positions.needsUpdate = true;
        mesh.geometry.computeVertexNormals();
        mesh.geometry.computeBoundingSphere();
        mesh.scale.set(1, 1, 1);
    },

    /**
     * Clear all active deformations, restoring every organ
     * to its healthy baseline geometry.
     */
    _clearDeformations: function() {
        for (var i = 0; i < this.deformedMeshes.length; i++) {
            this._restoreOriginalGeometry(this.deformedMeshes[i].mesh);
        }
        this.deformedMeshes = [];
    },


    // ═══════════════════════════════════════════════════════
    //  BEFORE / AFTER TOGGLE
    // ═══════════════════════════════════════════════════════

    toggleHealthyView: function() {
        this.showingHealthy = !this.showingHealthy;
        var btn = document.getElementById("bodymap-healthy-toggle");

        if (this.showingHealthy) {
            // Show healthy baseline — clear all damage
            this._clearDeformations();
            this._resetOrganColors();
            this.clearPins();
            if (btn) {
                btn.textContent = "Show My State";
                btn.classList.add("active");
            }
        } else {
            // Restore patient's actual state
            if (this.cachedOrganFindings) {
                this._applyOrganDamage(this.cachedOrganFindings);
            }
            // Re-place pins from cached region findings
            if (this.cachedRegionFindings) {
                this.clearPins();
                var self = this;
                var regions = Object.keys(this.cachedRegionFindings);
                for (var i = 0; i < regions.length; i++) {
                    var r = regions[i];
                    var findings = self.cachedRegionFindings[r];
                    var highest = self._highestSeverity(findings);
                    self._placePin(r, findings.length, highest, findings);
                }
            }
            if (btn) {
                btn.textContent = "Show Healthy";
                btn.classList.remove("active");
            }
        }
    },


    // ═══════════════════════════════════════════════════════
    //  SYMPTOM MAPPING — "Why Does This Hurt?"
    // ═══════════════════════════════════════════════════════

    // Maps organ conditions → common patient-experienced symptoms.
    // Used to bridge clinical findings with what the patient actually feels.
    symptomMapping: {
        // Cardiac
        "cardiomegaly":     ["shortness of breath", "fatigue", "swollen ankles", "chest tightness"],
        "heart failure":    ["shortness of breath at rest or lying down", "leg swelling", "persistent cough", "fatigue", "rapid weight gain"],
        "cardiomyopathy":   ["breathlessness", "dizziness", "fainting", "irregular heartbeat", "swollen legs"],
        "pericarditis":     ["sharp chest pain (worse lying down)", "pain radiating to shoulder", "fever", "fatigue"],
        "myocarditis":      ["chest pain", "rapid or irregular heartbeat", "shortness of breath", "fatigue", "flu-like symptoms"],
        "aneurysm":         ["deep throbbing pain", "pulsating sensation", "sudden severe pain if rupturing"],
        "valvular":         ["heart murmur", "breathlessness", "dizziness", "chest pain during exertion", "fatigue"],
        "stenosis":         ["chest pain during activity", "fainting", "shortness of breath", "fatigue"],
        "atrial fibrillation": ["heart palpitations", "dizziness", "shortness of breath", "fatigue", "chest discomfort"],
        // Pulmonary
        "copd":             ["chronic cough", "shortness of breath (especially during activity)", "wheezing", "chest tightness", "frequent respiratory infections"],
        "emphysema":        ["shortness of breath (gradual worsening)", "barrel chest appearance", "chronic cough", "reduced exercise tolerance"],
        "pneumonia":        ["cough with mucus", "fever and chills", "sharp chest pain when breathing", "shortness of breath", "fatigue"],
        "pneumothorax":     ["sudden sharp chest pain", "shortness of breath", "rapid heart rate", "dry cough"],
        "effusion":         ["shortness of breath", "chest pain (pleuritic)", "dry cough", "difficulty breathing when lying flat"],
        "atelectasis":      ["shortness of breath", "rapid shallow breathing", "cough"],
        // Hepatic
        "cirrhosis":        ["fatigue", "easy bruising", "itchy skin", "yellowing of skin/eyes", "swollen abdomen", "confusion"],
        "hepatomegaly":     ["abdominal fullness", "discomfort in upper right abdomen", "nausea", "fatigue"],
        "hepatitis":        ["fatigue", "nausea", "abdominal pain", "dark urine", "yellowing of skin", "joint pain"],
        "fatty liver":      ["usually no symptoms", "fatigue", "discomfort in upper right abdomen"],
        "steatosis":        ["usually no symptoms", "fatigue", "vague upper abdominal discomfort"],
        // Renal
        "kidney disease":   ["fatigue", "swollen ankles/feet", "poor appetite", "trouble sleeping", "muscle cramps", "frequent urination at night"],
        "polycystic":       ["back or side pain", "headaches", "blood in urine", "frequent urination", "high blood pressure"],
        "hydronephrosis":   ["flank pain", "nausea/vomiting", "urinary urgency", "fever if infected"],
        "kidney stones":    ["severe flank pain radiating to groin", "blood in urine", "nausea/vomiting", "painful urination"],
        "nephritis":        ["blood in urine", "foamy urine", "high blood pressure", "swelling in face/legs"],
        // GI
        "pancreatitis":     ["severe upper abdominal pain radiating to back", "nausea/vomiting", "fever", "rapid pulse", "tenderness when touching abdomen"],
        "colitis":          ["abdominal pain and cramping", "bloody diarrhea", "urgency to defecate", "weight loss", "fatigue"],
        "gastritis":        ["burning upper abdominal pain", "nausea", "bloating", "loss of appetite", "vomiting"],
        // Neurological
        "hydrocephalus":    ["headache", "blurred/double vision", "nausea/vomiting", "balance problems", "cognitive decline"],
        "cerebral edema":   ["headache", "nausea/vomiting", "vision changes", "confusion", "weakness"],
        "brain atrophy":    ["memory loss", "difficulty with thinking/reasoning", "personality changes", "difficulty with coordination"],
        "brain tumor":      ["persistent headaches (worse in morning)", "seizures", "vision/speech changes", "personality changes", "nausea"],
        // General
        "inflammation":     ["pain", "swelling", "redness", "warmth at affected area", "loss of function"],
        "edema":            ["swelling", "stretched/shiny skin", "puffiness", "difficulty moving affected area"],
        "fibrosis":         ["stiffness", "reduced organ function", "fatigue", "shortness of breath (if lung)"],
        "tumor":            ["lump or mass", "unexplained weight loss", "fatigue", "pain at site", "night sweats"],
        "cancer":           ["unexplained weight loss", "fatigue", "pain", "skin changes", "persistent cough or hoarseness"],
    },

    _getMatchingSymptoms: function(findings) {
        var matched = [];
        var seen = {};
        for (var i = 0; i < findings.length; i++) {
            var text = ((findings[i].name || "") + " " + (findings[i].text || "")).toLowerCase();
            var keys = Object.keys(this.symptomMapping);
            for (var j = 0; j < keys.length; j++) {
                if (text.indexOf(keys[j]) >= 0) {
                    var symptoms = this.symptomMapping[keys[j]];
                    for (var k = 0; k < symptoms.length; k++) {
                        if (!seen[symptoms[k]]) {
                            seen[symptoms[k]] = true;
                            matched.push({ symptom: symptoms[k], cause: keys[j] });
                        }
                    }
                }
            }
        }
        return matched;
    },


    _textToRegion: function(text) {
        var regions = Object.keys(this.regionMapping);
        for (var i = 0; i < regions.length; i++) {
            var kw = this.regionMapping[regions[i]];
            for (var j = 0; j < kw.length; j++) {
                if (text.indexOf(kw[j]) >= 0) return regions[i];
            }
        }
        return null;
    },

    _highestSeverity: function(findings) {
        var order = ["critical", "high", "moderate", "low", "info"];
        var best = "info";
        for (var i = 0; i < findings.length; i++) {
            var s = (findings[i].severity || "info").toLowerCase();
            if (order.indexOf(s) >= 0 && order.indexOf(s) < order.indexOf(best)) best = s;
        }
        return best;
    },

    _placePin: function(region, count, severity, findings) {
        var pos = this.regionPositions[region];
        if (!pos) return;

        // Create pin texture
        var cv = document.createElement("canvas");
        cv.width = 64; cv.height = 64;
        var ctx = cv.getContext("2d");
        var hex = this.severityColors[severity] || this.severityColors.info;
        var cr = (hex >> 16) & 0xff, cg = (hex >> 8) & 0xff, cb = hex & 0xff;

        ctx.beginPath();
        ctx.arc(32, 32, 28, 0, Math.PI * 2);
        ctx.fillStyle = "rgb(" + cr + "," + cg + "," + cb + ")";
        ctx.fill();
        ctx.lineWidth = 3;
        ctx.strokeStyle = "rgba(255,255,255,0.8)";
        ctx.stroke();

        if (count > 1) {
            ctx.fillStyle = "white";
            ctx.font = "bold 24px Inter, sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(String(count), 32, 33);
        }

        var tex = new THREE.CanvasTexture(cv);
        var sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
        sprite.position.copy(pos);
        sprite.scale.set(0.06, 0.06, 1);
        sprite.userData = { isPin: true, region: region, severity: severity, count: count, findings: findings };

        this.pinGroup.add(sprite);
        this.pins.push({ sprite: sprite, region: region, findings: findings, severity: severity });
    },

    clearPins: function() {
        for (var i = 0; i < this.pins.length; i++) {
            var p = this.pins[i];
            if (p.sprite) {
                this.pinGroup.remove(p.sprite);
                if (p.sprite.material) {
                    if (p.sprite.material.map) p.sprite.material.map.dispose();
                    p.sprite.material.dispose();
                }
            }
        }
        this.pins = [];
    },


    // ═══════════════════════════════════════════════════════
    //  INTERACTION
    // ═══════════════════════════════════════════════════════

    onMouseMove: function(event) {
        if (!this.renderer || !this.camera) return;
        var canvas = this.renderer.domElement;
        var rect = canvas.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        this.raycaster.setFromCamera(this.mouse, this.camera);

        var tooltip = document.getElementById("bodymap-tooltip");

        // Check pins
        var pinHits = this.raycaster.intersectObjects(this.pinGroup.children);
        if (pinHits.length > 0 && pinHits[0].object.userData.isPin) {
            canvas.style.cursor = "pointer";
            this._showPinTooltip(event, pinHits[0].object.userData);
            return;
        }

        // Check model meshes
        if (this.currentModel) {
            var meshes = [];
            this.currentModel.traverse(function(c) {
                if (c.isMesh && c.visible && c.material && c.material.opacity > 0.1) meshes.push(c);
            });
            var hits = this.raycaster.intersectObjects(meshes);
            if (hits.length > 0 && hits[0].object.userData.region) {
                canvas.style.cursor = "pointer";
                this._showRegionTooltip(event, hits[0].object.userData.region);
                return;
            }
        }

        canvas.style.cursor = "grab";
        if (tooltip) tooltip.style.display = "none";
    },

    onClick: function(event) {
        if (!this.renderer || !this.camera) return;
        var canvas = this.renderer.domElement;
        var rect = canvas.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        this.raycaster.setFromCamera(this.mouse, this.camera);

        // Pins
        var pinHits = this.raycaster.intersectObjects(this.pinGroup.children);
        if (pinHits.length > 0 && pinHits[0].object.userData.isPin) {
            var pd = pinHits[0].object.userData;
            this._showFindingsPanel(pd.region, pd.findings);
            this.focusRegion(pd.region);
            return;
        }

        // Meshes
        if (this.currentModel) {
            var meshes = [];
            this.currentModel.traverse(function(c) {
                if (c.isMesh && c.visible && c.material && c.material.opacity > 0.1) meshes.push(c);
            });
            var hits = this.raycaster.intersectObjects(meshes);
            if (hits.length > 0 && hits[0].object.userData.region) {
                this._selectRegion(hits[0].object.userData.region);
            }
        }
    },

    _showPinTooltip: function(event, data) {
        var tooltip = document.getElementById("bodymap-tooltip");
        if (!tooltip) return;
        var f = data.findings[0];
        var icon = data.severity === "critical" ? "\ud83d\udd34" : data.severity === "high" ? "\ud83d\udfe0" : data.severity === "moderate" ? "\ud83d\udfe1" : "\ud83d\udd35";

        var el = document.createElement("div");

        var titleDiv = document.createElement("div");
        titleDiv.className = "tooltip-title";
        titleDiv.textContent = icon + " " + (f.name || "Finding");
        el.appendChild(titleDiv);

        if (data.count > 1) {
            var countDiv = document.createElement("div");
            countDiv.style.cssText = "font-size:12px;color:rgba(255,255,255,0.7);margin-bottom:4px;";
            countDiv.textContent = data.count + " findings in this region";
            el.appendChild(countDiv);
        }

        if (f.source) {
            var srcDiv = document.createElement("div");
            srcDiv.className = "tooltip-source";
            srcDiv.textContent = "Source: " + f.source;
            el.appendChild(srcDiv);
        }

        if (f.date) {
            var dateDiv = document.createElement("div");
            dateDiv.className = "tooltip-source";
            dateDiv.textContent = "Date: " + f.date;
            el.appendChild(dateDiv);
        }

        var ctaDiv = document.createElement("div");
        ctaDiv.style.cssText = "font-size:11px;color:var(--heat);margin-top:4px;";
        ctaDiv.textContent = "Click to explore \u2192";
        el.appendChild(ctaDiv);

        tooltip.textContent = "";
        tooltip.appendChild(el);
        tooltip.style.display = "block";

        var container = document.getElementById("bodymap-canvas-container");
        var cr = container.getBoundingClientRect();
        tooltip.style.left = (event.clientX - cr.left + 16) + "px";
        tooltip.style.top = (event.clientY - cr.top - 8) + "px";
    },

    _showRegionTooltip: function(event, region) {
        var tooltip = document.getElementById("bodymap-tooltip");
        if (!tooltip) return;
        var name = region.replace("-", " ");
        name = name.charAt(0).toUpperCase() + name.slice(1);

        tooltip.textContent = "";
        var titleDiv = document.createElement("div");
        titleDiv.className = "tooltip-title";
        titleDiv.textContent = name;
        tooltip.appendChild(titleDiv);

        var hintDiv = document.createElement("div");
        hintDiv.style.cssText = "font-size:11px;color:var(--text-muted);";
        hintDiv.textContent = "Click to see findings";
        tooltip.appendChild(hintDiv);

        tooltip.style.display = "block";
        var container = document.getElementById("bodymap-canvas-container");
        var cr = container.getBoundingClientRect();
        tooltip.style.left = (event.clientX - cr.left + 16) + "px";
        tooltip.style.top = (event.clientY - cr.top - 8) + "px";
    },

    _selectRegion: function(region) {
        var findings = [];
        for (var i = 0; i < this.pins.length; i++) {
            if (this.pins[i].region === region) findings = findings.concat(this.pins[i].findings);
        }
        this._showFindingsPanel(region, findings);
        this.focusRegion(region);
    },

    _showFindingsPanel: function(region, findings) {
        var panel = document.getElementById("bodymap-findings-list");
        if (!panel) return;

        var title = document.querySelector(".findings-title");
        var name = region.replace("-", " ");
        name = name.charAt(0).toUpperCase() + name.slice(1);
        if (title) title.textContent = name + " \u2014 " + findings.length + " finding" + (findings.length !== 1 ? "s" : "");

        // Clear panel using DOM methods
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        if (findings.length === 0) {
            var emptyDiv = document.createElement("div");
            emptyDiv.style.cssText = "color:var(--text-muted);font-size:14px;padding:24px 0;text-align:center;";
            emptyDiv.textContent = "No clinical findings for this region";
            panel.appendChild(emptyDiv);
            return;
        }

        // ── AI Body Translation button ──
        var self = this;
        var translateBtn = document.createElement("button");
        translateBtn.className = "btn btn-sm btn-outline bodymap-translate-btn";
        translateBtn.textContent = "What does this mean?";
        translateBtn.title = "Get a plain-English explanation of these findings";
        translateBtn.onclick = function() { self._requestBodyTranslation(region, findings); };
        panel.appendChild(translateBtn);

        // ── AI Translation output area ──
        var translationArea = document.createElement("div");
        translationArea.id = "bodymap-translation-" + region;
        translationArea.className = "bodymap-translation";
        translationArea.style.display = "none";
        panel.appendChild(translationArea);

        // ── Symptom mapping section ──
        var symptoms = this._getMatchingSymptoms(findings);
        if (symptoms.length > 0) {
            var symptomSection = document.createElement("div");
            symptomSection.className = "bodymap-symptom-section";

            var symptomTitle = document.createElement("div");
            symptomTitle.className = "symptom-section-title";
            symptomTitle.textContent = "Why might this hurt?";
            symptomSection.appendChild(symptomTitle);

            var symptomList = document.createElement("div");
            symptomList.className = "symptom-list";
            // Show up to 8 symptoms to avoid overwhelming
            var displayCount = Math.min(symptoms.length, 8);
            for (var s = 0; s < displayCount; s++) {
                var symptomItem = document.createElement("div");
                symptomItem.className = "symptom-item";

                var symptomText = document.createElement("span");
                symptomText.className = "symptom-text";
                symptomText.textContent = symptoms[s].symptom;
                symptomItem.appendChild(symptomText);

                var symptomCause = document.createElement("span");
                symptomCause.className = "symptom-cause";
                symptomCause.textContent = symptoms[s].cause;
                symptomItem.appendChild(symptomCause);

                symptomList.appendChild(symptomItem);
            }
            if (symptoms.length > 8) {
                var moreDiv = document.createElement("div");
                moreDiv.className = "symptom-more";
                moreDiv.textContent = "+" + (symptoms.length - 8) + " more possible symptoms";
                symptomList.appendChild(moreDiv);
            }
            symptomSection.appendChild(symptomList);

            var disclaimer = document.createElement("div");
            disclaimer.className = "symptom-disclaimer";
            disclaimer.textContent = "These are common associations, not a diagnosis. Discuss with your doctor.";
            symptomSection.appendChild(disclaimer);

            panel.appendChild(symptomSection);
        }

        // ── Individual finding cards ──
        for (var i = 0; i < findings.length; i++) {
            var f = findings[i];
            var sev = (f.severity || "info").toLowerCase();

            var card = document.createElement("div");
            card.className = "finding-card";
            card.setAttribute("data-severity", sev);

            var nameEl = document.createElement("div");
            nameEl.className = "finding-name";
            nameEl.textContent = f.name || "Finding";
            card.appendChild(nameEl);

            var badge = document.createElement("span");
            badge.className = "badge badge-" + sev;
            badge.textContent = f.type || "finding";
            card.appendChild(badge);

            if (f.source) {
                var src = document.createElement("div");
                src.className = "finding-source";
                src.textContent = f.source + (f.page ? ", p." + f.page : "");
                card.appendChild(src);
            }

            if (f.date) {
                var dateEl = document.createElement("div");
                dateEl.className = "finding-date";
                dateEl.textContent = f.date;
                card.appendChild(dateEl);
            }

            panel.appendChild(card);
        }
    },


    // ═══════════════════════════════════════════════════════
    //  AI BODY TRANSLATION
    // ═══════════════════════════════════════════════════════

    _requestBodyTranslation: function(region, findings) {
        var areaId = "bodymap-translation-" + region;
        var area = document.getElementById(areaId);
        if (!area) return;

        // Show loading state
        area.style.display = "block";
        area.textContent = "";
        var loadingDiv = document.createElement("div");
        loadingDiv.className = "translation-loading";
        loadingDiv.textContent = "Generating plain-English explanation...";
        area.appendChild(loadingDiv);

        // Build context for the API
        var findingDescriptions = [];
        for (var i = 0; i < findings.length; i++) {
            findingDescriptions.push(findings[i].name || findings[i].type || "finding");
        }

        fetch("/api/body-translation", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                region: region,
                findings: findingDescriptions,
            }),
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            area.textContent = "";
            if (data.error) {
                var errDiv = document.createElement("div");
                errDiv.className = "translation-error";
                errDiv.textContent = "Could not generate explanation: " + data.error;
                area.appendChild(errDiv);
                return;
            }

            var explDiv = document.createElement("div");
            explDiv.className = "translation-content";

            var explTitle = document.createElement("div");
            explTitle.className = "translation-title";
            explTitle.textContent = "In Plain English";
            explDiv.appendChild(explTitle);

            var explText = document.createElement("div");
            explText.className = "translation-text";
            explText.textContent = data.explanation || "No explanation available.";
            explDiv.appendChild(explText);

            if (data.action_items && data.action_items.length > 0) {
                var actionTitle = document.createElement("div");
                actionTitle.className = "translation-action-title";
                actionTitle.textContent = "Questions for Your Doctor";
                explDiv.appendChild(actionTitle);

                var actionList = document.createElement("ul");
                actionList.className = "translation-actions";
                for (var j = 0; j < data.action_items.length; j++) {
                    var li = document.createElement("li");
                    li.textContent = data.action_items[j];
                    actionList.appendChild(li);
                }
                explDiv.appendChild(actionList);
            }

            area.appendChild(explDiv);
        })
        .catch(function() {
            area.textContent = "";
            var errDiv = document.createElement("div");
            errDiv.className = "translation-error";
            errDiv.textContent = "Could not connect to explanation service.";
            area.appendChild(errDiv);
        });
    },


    // ═══════════════════════════════════════════════════════
    //  GENDER SWITCHING
    // ═══════════════════════════════════════════════════════

    toggleGender: function() {
        this.loadModel(this.currentGender === "male" ? "female" : "male");
    },


    // ═══════════════════════════════════════════════════════
    //  FALLBACK + RESIZE
    // ═══════════════════════════════════════════════════════

    fallbackTo2D: function() {
        var c = document.getElementById("bodymap-canvas-container");
        var f = document.getElementById("bodymap-2d-fallback");
        if (c) c.style.display = "none";
        if (f) f.style.display = "block";
    },

    onWindowResize: function(containerId) {
        var c = document.getElementById(containerId || "bodymap-canvas-container");
        if (!c || !this.camera || !this.renderer) return;
        var w = c.clientWidth, h = c.clientHeight || 700;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    },
};
