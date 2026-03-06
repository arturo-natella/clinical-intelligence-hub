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
    composer: null,
    ssaoPass: null,
    bloomPass: null,
    controls: null,
    clock: null,
    animationId: null,

    currentModel: null,
    currentGender: null,
    currentLayer: "skin",
    currentOrganCategory: "all",
    layers: {},
    pins: [],
    pinGroup: null,
    deformedMeshes: [],

    // Detailed organs (BodyParts3D high-detail overlay)
    detailedOrgansModel: null,     // wrapper Group for the detailed organs GLB
    detailedOrgans: {},            // category → [mesh, mesh, ...] for drill-down
    detailedOrgansLoaded: false,

    // Organ sub-category keyword mapping for mesh name classification
    organCategories: {
        heart: ["heart", "ventricle", "atrium", "aorta", "coronary", "pericardium",
                "papillary_muscle", "leaflet", "valve", "pulmonary_trunk",
                "mitral", "tricuspid", "semilunar", "chordae", "endocardium", "myocardium"],
        lungs: ["lung", "bronch", "alveol", "pleura", "trachea", "diaphragm", "lobe_"],
        brain: ["brain", "cerebr", "cerebel", "hippocampus", "thalamus", "hypothalamus",
                "amygdala", "pons", "medulla_oblongata", "midbrain", "corpus_callosum",
                "frontal_lobe", "parietal_lobe", "temporal_lobe", "occipital_lobe",
                "brainstem", "spinal_cord", "meninges", "dura_mater", "pia_mater"],
        liver: ["liver", "hepat", "gallbladder", "bile", "hepatic"],
        kidneys: ["kidney", "renal", "ureter", "adrenal", "suprarenal"],
        gi_tract: ["stomach", "intestin", "colon", "rectum", "esophag", "duodenum",
                   "jejunum", "ileum", "appendix", "cecum", "sigmoid", "pylor", "fundus"],
        reproductive: ["uterus", "ovary", "testi", "prostate", "penis", "vagina",
                       "scrotum", "fallopian", "epididym", "seminal"],
        other: ["spleen", "pancrea", "bladder", "thyroid", "pharynx", "larynx",
                "tongue", "tonsil", "salivary", "pituitary", "pineal", "uvula",
                "thymus", "parathyroid"]
    },

    // ── NIH HRA on-demand organ loading ────────────────────
    // Maps organ sub-categories → GLB filenames by gender.
    // Loaded on-demand when user drills into a category.
    nihOrganRegistry: {
        heart: {
            male:   ["VH_M_Heart.glb"],
            female: ["VH_F_Heart.glb"]
        },
        lungs: {
            male:   ["3d-vh-m-main-bronchus.glb", "3d-vh-m-trachea.glb", "3d-vh-m-larynx.glb"],
            female: ["3d-vh-f-lung.glb", "3d-vh-f-main-bronchus.glb", "3d-vh-f-trachea.glb", "3d-vh-f-larynx.glb"]
        },
        brain: {
            male:   ["3d-vh-m-allen-brain.glb", "3d-vh-m-eye-l.glb", "3d-vh-m-eye-r.glb"],
            female: ["3d-vh-f-allen-brain.glb", "3d-vh-f-eye-l.glb", "3d-vh-f-eye-r.glb"]
        },
        liver: {
            male:   ["VH_M_Liver.glb"],
            female: ["VH_F_Liver.glb"]
        },
        kidneys: {
            male:   ["VH_M_Kidney_L.glb", "VH_M_Kidney_R.glb", "VH_M_Ureter_L.glb", "VH_M_Ureter_R.glb",
                     "3d-vh-m-renal-pelvis-l.glb", "3d-vh-m-renal-pelvis-r.glb"],
            female: ["VH_F_Kidney_L.glb", "VH_F_Kidney_R.glb", "VH_F_Ureter_L.glb", "VH_F_Ureter_R.glb",
                     "3d-vh-f-renal-pelvis-l.glb", "3d-vh-f-renal-pelvis-r.glb"]
        },
        gi_tract: {
            male:   ["VH_M_Small_Intestine.glb", "SBU_M_Intestine_Large.glb",
                     "3d-vh-m-pancreas.glb", "3d-vh-m-mouth.glb"],
            female: ["VH_F_Small_Intestine.glb", "SBU_F_Intestine_Large.glb",
                     "3d-vh-f-pancreas.glb", "3d-vh-f-mouth.glb"]
        },
        reproductive: {
            male:   ["VH_M_Prostate.glb"],
            female: ["VH_F_Uterus.glb", "VH_F_Ovary_L.glb", "VH_F_Ovary_R.glb",
                     "VH_F_Fallopian_Tube_L.glb", "VH_F_Fallopian_Tube_R.glb"]
        },
        other: {
            male:   ["VH_M_Spleen.glb", "VH_M_Thymus.glb", "VH_M_Urinary_Bladder.glb",
                     "NIH_M_Lymph_Node.glb", "VH_M_Spinal_Cord.glb",
                     "3d-vh-m-palatine-tonsil-l.glb", "3d-vh-m-palatine-tonsil-r.glb"],
            female: ["VH_F_Spleen.glb", "VH_F_Thymus.glb", "VH_F_Urinary_Bladder.glb",
                     "NIH_F_Lymph_Node.glb", "VH_F_Spinal_Cord.glb",
                     "3d-vh-f-palatine-tonsil-l.glb", "3d-vh-f-palatine-tonsil-r.glb"]
        }
    },
    nihOrgansBasePath: "/models/nih_hra/",
    nihOrgansCache: {},        // "male_heart" → { group: THREE.Group, meshes: [...] }
    _nihOrganLoading: null,    // category currently being loaded (prevents duplicate loads)

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

        // Scene — explicit dark background so SSAO pass doesn't grey-wash empty space
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x141414);

        // Camera
        this.camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000);
        this.camera.position.copy(this.cameraPresets.default.position);

        // Renderer — dark background so skin-toned model is visible
        this.renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: false });
        this.renderer.setClearColor(0x141414, 1.0);
        this.renderer.setSize(w, h);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.0;

        // Post-processing + HDR environment
        this._setupEnvironment();
        this._setupPostProcessing();

        // Controls — left-drag = full 360 rotation, scroll = zoom.
        // Pan is DISABLED so the body always stays centered (like Zygote Body).
        // Use Focus dropdown to reposition the view to a specific body region.
        this.controls = new THREE.OrbitControls(this.camera, canvas);
        this.controls.mouseButtons = {
            LEFT: THREE.MOUSE.ROTATE,
            MIDDLE: THREE.MOUSE.DOLLY,
            RIGHT: THREE.MOUSE.ROTATE   // Both mouse buttons rotate
        };
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.enablePan = false;
        this.controls.minDistance = 0.3;
        this.controls.maxDistance = 8.0;
        this.controls.target.copy(this.cameraPresets.default.target);
        this.controls.rotateSpeed = 1.0;
        // Allow full vertical orbit (small margin prevents gimbal lock at poles)
        this.controls.minPolarAngle = 0.05;
        this.controls.maxPolarAngle = Math.PI - 0.05;

        // Lights — balanced studio setup: enough to reveal surface detail
        // without washing out dark anatomical colors (crimson muscle, dark liver).
        // Hemisphere light: warm from above (sky), cool from below (ground bounce)
        var hemi = new THREE.HemisphereLight(0xffeedd, 0x445566, 0.6);
        this.scene.add(hemi);

        // Key light — warm, moderate, front-right
        var key = new THREE.DirectionalLight(0xfff5ee, 0.9);
        key.position.set(3, 4, 5);
        this.scene.add(key);

        // Fill light — cooler, softer, front-left
        var fill = new THREE.DirectionalLight(0xe8eef5, 0.45);
        fill.position.set(-3, 2, 3);
        this.scene.add(fill);

        // Rim/back light — edge definition for depth perception
        var rim = new THREE.DirectionalLight(0xffffff, 0.35);
        rim.position.set(0, 2, -4);
        this.scene.add(rim);

        // Under light — illuminates abdominal and pelvic cavity detail
        var under = new THREE.DirectionalLight(0xdde8ff, 0.25);
        under.position.set(0, -3, 2);
        this.scene.add(under);

        // Side light — brings out surface contours on muscles and vessels
        var side = new THREE.DirectionalLight(0xfff0e0, 0.3);
        side.position.set(-5, 1, -1);
        this.scene.add(side);

        // Ambient — subtle shadow fill, low to preserve color saturation
        this.scene.add(new THREE.AmbientLight(0xffffff, 0.12));

        // Raycaster
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();

        // Pin group
        this.pinGroup = new THREE.Group();
        this.scene.add(this.pinGroup);

        // Clock
        this.clock = new THREE.Clock();

        // Events — OrbitControls handles all rotation/pan/zoom natively.
        // We only need click detection (distinguishing click from drag).
        var self = this;
        this._mouseDownPos = { x: 0, y: 0 };

        canvas.addEventListener("mousedown", function(e) {
            self._mouseDownPos.x = e.clientX;
            self._mouseDownPos.y = e.clientY;
        });
        canvas.addEventListener("mousemove", function(e) {
            self.onMouseMove(e);
        });
        canvas.addEventListener("click", function(e) {
            var ddx = e.clientX - self._mouseDownPos.x;
            var ddy = e.clientY - self._mouseDownPos.y;
            if (ddx * ddx + ddy * ddy > 25) return; // >5px = drag, not click
            self.onClick(e);
        });
        window.addEventListener("resize", function() { self.onWindowResize(containerId); });

        // ResizeObserver catches SPA visibility changes (container goes from 0 → visible width)
        // which window.resize misses
        if (typeof ResizeObserver !== "undefined") {
            new ResizeObserver(function() { self.onWindowResize(containerId); }).observe(container);
        }

        // ── Wire up toolbar buttons ──
        var layerBtns = document.querySelectorAll(".bodymap-layer");
        for (var lb = 0; lb < layerBtns.length; lb++) {
            layerBtns[lb].addEventListener("click", function(e) {
                var layer = e.currentTarget.dataset.layer;
                // Organs button has its own dropdown handler
                if (layer === "organs") return;
                if (layer) self.setLayer(layer);
            });
        }

        var resetBtn = document.getElementById("bodymap-reset-btn");
        if (resetBtn) resetBtn.addEventListener("click", function() { self.resetView(); });

        var genderBtn = document.getElementById("gender-toggle");
        if (genderBtn) genderBtn.addEventListener("click", function() {
            self.loadModel(self.currentGender === "male" ? "female" : "male");
        });

        var zoomInBtn = document.getElementById("bodymap-zoom-in");
        if (zoomInBtn) zoomInBtn.addEventListener("click", function() { self.zoom(0.8); });

        var zoomOutBtn = document.getElementById("bodymap-zoom-out");
        if (zoomOutBtn) zoomOutBtn.addEventListener("click", function() { self.zoom(1.25); });

        // ── Region zoom dropdown ──
        var regionBtn = document.getElementById("bodymap-region-btn");
        var regionDropdown = document.getElementById("bodymap-region-dropdown");
        if (regionBtn && regionDropdown) {
            regionBtn.addEventListener("click", function(e) {
                e.stopPropagation();
                regionDropdown.classList.toggle("open");
                // Close organ dropdown if open
                var od = document.getElementById("bodymap-organ-dropdown");
                if (od) od.classList.remove("open");
            });
            var regionBtns = regionDropdown.querySelectorAll(".bodymap-region-btn");
            for (var ri = 0; ri < regionBtns.length; ri++) {
                regionBtns[ri].addEventListener("click", function(e) {
                    var region = e.currentTarget.dataset.region;
                    if (region && self.cameraPresets[region]) {
                        self._animateCamera(
                            self.cameraPresets[region].position,
                            self.cameraPresets[region].target
                        );
                    }
                    regionDropdown.classList.remove("open");
                });
            }
        }

        // ── Organs sub-category dropdown ──
        var organsBtn = document.getElementById("bodymap-organs-btn");
        var organDropdown = document.getElementById("bodymap-organ-dropdown");
        if (organsBtn && organDropdown) {
            organsBtn.addEventListener("click", function(e) {
                // First click: activate organs layer
                self.setLayer("organs");
                // Toggle dropdown
                e.stopPropagation();
                organDropdown.classList.toggle("open");
                // Close region dropdown if open
                if (regionDropdown) regionDropdown.classList.remove("open");
            });
            var organBtns = organDropdown.querySelectorAll(".bodymap-organ-btn");
            for (var oi = 0; oi < organBtns.length; oi++) {
                organBtns[oi].addEventListener("click", function(e) {
                    var cat = e.currentTarget.dataset.organ;
                    // Update active state on organ sub-buttons
                    for (var ob = 0; ob < organBtns.length; ob++) {
                        organBtns[ob].classList.remove("active");
                    }
                    e.currentTarget.classList.add("active");
                    self.setLayer("organs");
                    self.setOrganCategory(cat);
                    organDropdown.classList.remove("open");
                });
            }
        }

        // Close dropdowns on outside click
        document.addEventListener("click", function() {
            if (organDropdown) organDropdown.classList.remove("open");
            if (regionDropdown) regionDropdown.classList.remove("open");
        });

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

        if (this.composer) {
            this.composer.render();
        } else if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
    },

    destroy: function() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.composer) this.composer.dispose();
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

        // Remove cached NIH organ groups from scene before loading new model
        for (var key in this.nihOrgansCache) {
            var cached = this.nihOrgansCache[key];
            if (cached.group && cached.group.parent) {
                cached.group.parent.remove(cached.group);
            }
        }
        this.nihOrgansCache = {};
        this._nihOrganLoading = null;

        var toggle = document.getElementById("gender-toggle");
        if (toggle) {
            toggle.textContent = gender === "male" ? "\u2642" : "\u2640";
            toggle.title = "Currently: " + gender + " \u2014 Click to switch";
        }

        var loading = document.getElementById("bodymap-loading");
        if (loading) loading.style.display = "flex";

        // Try Z-Anatomy full model first, then NIH HRA united, then basic fallbacks.
        // Note: Z-Anatomy has 0 image textures — materials are Principled BSDF
        // node colors (roughness, metallic) already exported as glTF PBR properties.
        // Rendering quality improvements come from lighting setup, not model files.
        var fullPath = "/models/" + gender + "_anatomy_full.glb";
        var basicPath = "/models/" + gender + "_anatomy.glb";
        var maleFull = "/models/male_anatomy_full.glb";
        var maleBasic = "/models/male_anatomy.glb";
        var self = this;

        // Cascade: Z-Anatomy full → NIH HRA united → basic → male fallbacks → placeholder
        var candidates = [fullPath];
        if (gender === "female") {
            candidates.push("/models/nih_hra/3d-vh-f-united.glb");
        }
        candidates.push(basicPath);
        if (gender === "female") candidates.push(maleFull, maleBasic);

        function tryNext(idx) {
            if (idx >= candidates.length) {
                self.loadPlaceholderModel(gender);
                return;
            }
            fetch(candidates[idx], { method: "HEAD" })
                .then(function(r) {
                    if (r.ok) {
                        self._loadGLB(candidates[idx], gender);
                    } else {
                        tryNext(idx + 1);
                    }
                })
                .catch(function() { tryNext(idx + 1); });
        }
        tryNext(0);
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
            self._hideLoadingProgress();
            self._onModelReady(gltf.scene, gender);
        }, function(event) {
            // Show loading progress for large files (NIH HRA united = 208MB)
            if (event.total > 0) {
                var pct = Math.round(event.loaded / event.total * 100);
                self._showLoadingProgress(pct);
            }
        }, function() {
            self._hideLoadingProgress();
            self.loadPlaceholderModel(gender);
        });
    },

    _onModelReady: function(modelScene, gender) {
        if (this.currentModel) this.scene.remove(this.currentModel);

        // Wrap in group so we can rotate + scale without affecting child transforms
        var wrapper = new THREE.Group();
        wrapper.add(modelScene);

        // Pre-pass: remove instructional/non-anatomy meshes BEFORE computing
        // the bounding box. Z-Anatomy includes text label meshes (HOW_TO guides,
        // Navigation labels, collection headers like "SKELETAL SYSTEM") that extend
        // 1.5-4+ units on X and inflate the bounding box, shifting the computed
        // center far from the actual visible anatomy.
        var toRemove = [];
        wrapper.traverse(function(child) {
            // Only remove Mesh nodes — removing Group/Empty nodes would also
            // remove all their children (the actual anatomy meshes).
            if (!child.isMesh) return;
            var n = (child.name || "");
            var nl = n.toLowerCase();
            // Strip layer prefix for glyph detection
            var stripped = nl.replace(/^(?:skel|musc|orgn|vasc|nerv|skin)__/, "");
            if (/^(how_to|navigation)/i.test(nl) ||
                // Collection header glyphs: "Skeletal_systemg", "Jointsg",
                // "Muscular_systemg", "Regions_of_human_bodyg", etc.
                /(?:systemg|organsg|jointsg|bodyg|insertionsg|systemsg)$/.test(stripped)) {
                toRemove.push(child);
            }
        });
        for (var ri = 0; ri < toRemove.length; ri++) {
            if (toRemove[ri].parent) toRemove[ri].parent.remove(toRemove[ri]);
        }

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

        // Force matrix update, then center model at camera default target
        wrapper.updateMatrixWorld(true);
        box.setFromObject(wrapper);
        var center = box.getCenter(new THREE.Vector3());
        wrapper.position.sub(center);
        // Position model center at camera's default look-at point (y=0.5)
        wrapper.position.y += this.cameraPresets.default.target.y;

        this.currentModel = wrapper;
        this.scene.add(wrapper);

        // Parse layers using name-prefix system from export pipeline.
        // Each mesh name is prefixed: SKEL__, MUSC__, ORGN__, VASC__, NERV__, SKIN__
        // Fallback: hierarchy-based parsing for older GLBs, then raw name matching.
        this.layers = { skin: [], muscle: [], skeleton: [], organs: [], vasculature: [], nervous: [] };
        var self = this;

        // Prefix→layer mapping (from Blender export pipeline)
        var prefixMap = {
            "skel__": "skeleton", "musc__": "muscle", "orgn__": "organs",
            "vasc__": "vasculature", "nerv__": "nervous", "skin__": "skin"
        };

        // Also support hierarchy-based parsing (layer_* parent empties)
        var layerParents = {};
        var layerNameMap = {
            "layer_skin": "skin", "layer_muscle": "muscle", "layer_skeleton": "skeleton",
            "layer_organs": "organs", "layer_vasculature": "vasculature", "layer_nervous": "nervous"
        };
        modelScene.traverse(function(child) {
            var n = (child.name || "").toLowerCase();
            if (layerNameMap[n]) {
                layerParents[child.uuid] = layerNameMap[n];
            }
        });

        // Z-Anatomy 3D text glyph filter — collection/category header meshes
        // that should never appear in anatomy layers (e.g., "SKELETAL SYSTEM" text)
        var glyphRe = /(?:_g|systemg|organsg|glandsg|musclesg|girdleg|genitaliag|abdomeng|termsg|movementsg|linesg|planesg)$/;

        modelScene.traverse(function(child) {
            var n = (child.name || "").toLowerCase();
            var layerName = null;

            // Remove Z-Anatomy instructional text meshes (HOW_TO guides, Navigation labels).
            // These must be REMOVED from the scene, not just hidden — their geometry
            // extends 4+ units on X, inflating Box3.setFromObject() and shifting the
            // computed center far from the actual visible anatomy.
            if (/^(how_to|navigation)/i.test(n)) {
                if (child.parent) child.parent.remove(child);
                return;
            }

            // Skip Z-Anatomy text label glyphs (collection headers, reference labels)
            var stripped = n.replace(/^(?:skel|musc|orgn|vasc|nerv|skin)__(?:(?:skel|musc|orgn|vasc|nerv|skin)_)*/g, "");
            if (glyphRe.test(stripped)) return;

            // Method 1: Name prefix (most reliable — set by export pipeline)
            for (var pfx in prefixMap) {
                if (n.indexOf(pfx) === 0) {
                    layerName = prefixMap[pfx];
                    break;
                }
            }

            // Method 2: Ancestor hierarchy — walk up the parent chain looking for
            // either a layer_* empty (legacy GLBs) or a prefix-tagged ancestor
            // (current pipeline: tagged empties parent untagged geometry meshes).
            if (!layerName) {
                var p = child.parent;
                while (p && !layerName) {
                    if (layerParents[p.uuid]) {
                        layerName = layerParents[p.uuid];
                    } else {
                        // Check if this ancestor has a prefix tag
                        var pn = (p.name || "").toLowerCase();
                        for (var apfx in prefixMap) {
                            if (pn.indexOf(apfx) === 0) {
                                layerName = prefixMap[apfx];
                                break;
                            }
                        }
                    }
                    p = p.parent;
                }
            }

            // Method 3: Keyword-based classification (fallback for NIH HRA models
            // that lack SKEL__/MUSC__ prefixes and layer_* hierarchy)
            if (!layerName && child.isMesh) {
                var keywordLayerMap = {
                    skeleton: ["bone", "skeletal", "pelvis", "rib", "vertebr", "skull", "sternum",
                               "clavicle", "scapula", "humerus", "femur", "tibia", "fibula",
                               "radius", "ulna", "patella", "sacrum", "mandible", "cartilage",
                               "maxilla", "sphenoid", "temporal_bone", "occipital_bone",
                               "metacarpal", "metatarsal", "phalang", "carpal", "tarsal",
                               "hyoid", "coccyx", "ilium", "ischium", "pubis", "calcaneus",
                               "talus", "navicular", "cuneiform", "cuboid", "pisiform",
                               "triquetrum", "lunate", "scaphoid", "capitate", "hamate",
                               "trapezoid", "trapezium",
                               // Bony landmarks (NIH HRA detail)
                               "epicondyl", "enthesis", "condyle", "tubercle", "tuberosity",
                               "trochle", "fossa", "groove", "foramen", "olecranon",
                               "malleolus", "acetabul", "glenoid", "labrum",
                               "annulus", "disc_", "meniscus", "sesamoid"],
                    muscle: ["muscle", "musc_", "tendon", "ligament", "diaphragm",
                             "bicep", "tricep", "deltoid", "pectoral", "trapezius",
                             "quadricep", "hamstring", "gluteus", "abdomin", "oblique",
                             "soleus", "gastrocnemius", "sartorius", "latissimus",
                             "rotator_cuff", "masseter", "temporalis",
                             // Connective tissue
                             "fascia", "aponeurosis", "retinaculum"],
                    organs: ["heart", "lung", "liver", "kidney", "brain", "stomach", "intestin",
                             "spleen", "pancrea", "bladder", "uterus", "ovary", "prostate",
                             "thyroid", "thymus", "trachea", "bronch", "larynx", "esophag",
                             "colon", "rectum", "appendix", "duodenum", "jejunum", "ileum",
                             "gallbladder", "adrenal", "pituitary", "pineal", "tonsil",
                             "mammary", "placenta", "fallopian", "epididym",
                             // Eye anatomy
                             "retina", "fovea", "macula", "sclera", "pupil", "iris",
                             "cornea", "conjunctiva", "eyelid", "lens", "vitreous",
                             "aqueous", "ciliary", "humor", "ora_serrata",
                             // Kidney detail
                             "calyx", "renal_papilla", "renal_pyramid", "renal_column",
                             "renal_pelvis", "nephron",
                             // Heart chambers
                             "atrium", "cardiac", "ventricle", "septum",
                             "papillary", "chordae", "valve",
                             // GI detail
                             "bile_duct", "hepatic_duct", "cystic_duct", "ampulla",
                             "pylor", "fundus", "cardia",
                             // Reproductive detail
                             "mesovarium", "mesosalpinx", "endometrium", "myometrium",
                             "cervix", "vagina", "vulva", "labia",
                             // Breast tissue
                             "areol", "nipple", "lactiferous"],
                    vasculature: ["artery", "arter", "vein", "venous", "vessel", "blood",
                                  "aorta", "aortic", "coronary", "vascular", "capillar",
                                  "jugular", "carotid", "subclavian",
                                  "pulmonary_artery", "pulmonary_vein",
                                  "hepatic_artery", "hepatic_vein",
                                  "renal_artery", "renal_vein",
                                  "iliac", "femoral_artery", "femoral_vein",
                                  "vena_cava", "azygos", "portal",
                                  "mesenteric", "celiac", "splenic_artery", "splenic_vein"],
                    nervous: ["nerve", "nerv", "gangli", "plexus", "cerebr", "cerebel",
                              "spinal_cord", "brainstem", "optic", "vagus", "sciatic",
                              "brachial_plexus", "lumbar_plexus", "sacral_plexus",
                              // Allen Brain Atlas regions (NIH HRA)
                              "allen_", "gyrus", "nucleus", "putamen", "caudate",
                              "globus_pallidus", "colliculus", "substantia_nigra",
                              "hippocamp", "amygdal", "thalamus", "hypothalamus",
                              "claustrum", "habenul", "pretect", "tegment",
                              "cingulate", "precuneus", "cuneus", "sulcus"],
                    skin: ["skin", "dermis", "epidermis", "integument", "subcutaneous",
                           "fat_l", "fat_r", "adipose"]
                };
                for (var kwLayer in keywordLayerMap) {
                    var kws = keywordLayerMap[kwLayer];
                    for (var kwi = 0; kwi < kws.length; kwi++) {
                        if (n.indexOf(kws[kwi]) >= 0) {
                            layerName = kwLayer;
                            break;
                        }
                    }
                    if (layerName) break;
                }
            }

            if (layerName && self.layers[layerName]) {
                self.layers[layerName].push(child);
            }

            // Cross-list organs that live in system layers (heart, brain, etc.)
            if (child.isMesh && layerName && layerName !== "organs") {
                var organKeywords = [
                    "heart", "ventricle", "atrium", "aorta", "pulmonary_trunk", "coronary",
                    "pericardium", "papillary_muscle", "leaflet", "valve",
                    "brain", "cerebr", "cerebel", "hippocampus", "thalamus", "hypothalamus",
                    "amygdala", "pons", "medulla_oblongata", "midbrain", "corpus_callosum",
                    "frontal_lobe", "parietal_lobe", "temporal_lobe", "occipital_lobe",
                    "spinal_cord", "brainstem",
                    "adrenal", "esophag", "pharynx", "larynx", "tongue", "uvula",
                    "tonsil", "salivary", "pituitary", "pineal"
                ];
                for (var oi = 0; oi < organKeywords.length; oi++) {
                    if (n.indexOf(organKeywords[oi]) >= 0) {
                        self.layers.organs.push(child);
                        break;
                    }
                }
            }

            // Tag organ meshes with sub-category for filtering
            if (child.isMesh && layerName === "organs") {
                child.userData._organCategory = self._classifyOrgan(n);
            }

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

        // Tag cross-listed organ meshes that came from other layers
        var organMeshes = this.layers.organs || [];
        for (var omi = 0; omi < organMeshes.length; omi++) {
            var om = organMeshes[omi];
            if (om.isMesh && !om.userData._organCategory) {
                om.userData._organCategory = this._classifyOrgan((om.name || "").toLowerCase());
            }
        }

        // Diagnostic: hand-related meshes in muscle layer
        var handMuscleCount = 0;
        var handRe = /hand|finger|digit|phalang|metacarp|thenar|carpal|lumbrical|inteross|hypothenar/;
        var muscleMeshes = this.layers.muscle || [];
        for (var hmi = 0; hmi < muscleMeshes.length; hmi++) {
            var hm = muscleMeshes[hmi];
            if (hm.isMesh && handRe.test((hm.name || "").toLowerCase())) {
                handMuscleCount++;
                console.log("[BodyMap3D] Hand muscle mesh: " + hm.name);
            }
        }
        if (handMuscleCount === 0) {
            // Search ALL meshes for hand-related names to find if they exist but are in wrong layer
            var handAnywhere = 0;
            modelScene.traverse(function(child) {
                if (child.isMesh && handRe.test((child.name || "").toLowerCase())) {
                    handAnywhere++;
                    console.log("[BodyMap3D] Hand mesh (any layer): " + child.name);
                }
            });
            console.warn("[BodyMap3D] No hand muscles found in muscle layer. " +
                handAnywhere + " hand-related meshes found across all layers.");
        } else {
            console.log("[BodyMap3D] Hand muscles in muscle layer: " + handMuscleCount);
        }

        // Force-hide Z-Anatomy 3D text label meshes — these were excluded from
        // layers by glyphRe but still have visible geometry. Use material swap
        // (not visible=false) to avoid hiding their anatomy mesh children.
        modelScene.traverse(function(child) {
            if (!child.isMesh || !child.material) return;
            var cn = (child.name || "").toLowerCase();
            var cstripped = cn.replace(/^(?:skel|musc|orgn|vasc|nerv|skin)__(?:(?:skel|musc|orgn|vasc|nerv|skin)_)*/g, "");
            if (glyphRe.test(cstripped)) {
                child.userData._isGlyph = true;
                child.userData._origMat = child.material;
                child.userData._hiddenMat = new THREE.MeshBasicMaterial({
                    visible: false, transparent: true, opacity: 0
                });
                child.material = child.userData._hiddenMat;
            }
        });

        // Filter out Z-Anatomy 3D text labels (FONT objects converted to mesh
        // during GLB export). These are flat (2D bounding box) AND lack a layer
        // prefix (export script only tags Blender MESH objects, not FONTs).
        // Prefixed flat meshes (thin ligaments, fascia) are real anatomy — keep them.
        for (var tlk in this.layers) {
            var tlarr = this.layers[tlk];
            for (var tli = tlarr.length - 1; tli >= 0; tli--) {
                var tlm = tlarr[tli];
                if (!tlm.isMesh || !tlm.geometry || tlm.userData._isGlyph) continue;
                // Skip meshes that have a layer prefix — they're real anatomy
                var tln = (tlm.name || "").toLowerCase();
                var tlHasPrefix = false;
                for (var tlp in prefixMap) {
                    if (tln.indexOf(tlp) === 0) { tlHasPrefix = true; break; }
                }
                if (tlHasPrefix) continue;
                // Unprefixed mesh in a layer (got here via ancestor inheritance).
                // Check geometric flatness to confirm it's a text label.
                if (!tlm.geometry.boundingBox) tlm.geometry.computeBoundingBox();
                var tlbb = tlm.geometry.boundingBox;
                var tld = [
                    tlbb.max.x - tlbb.min.x,
                    tlbb.max.y - tlbb.min.y,
                    tlbb.max.z - tlbb.min.z
                ];
                var tlMax = Math.max(tld[0], tld[1], tld[2]);
                var tlMin = Math.min(tld[0], tld[1], tld[2]);
                if (tlMax > 0.001 && tlMin / tlMax < 0.05) {
                    tlm.userData._isGlyph = true;
                    if (!tlm.userData._hiddenMat) {
                        tlm.userData._origMat = tlm.material;
                        tlm.userData._hiddenMat = new THREE.MeshBasicMaterial({
                            visible: false, transparent: true, opacity: 0
                        });
                    }
                    tlm.material = tlm.userData._hiddenMat;
                    tlarr.splice(tli, 1);
                }
            }
        }

        // Hide anomalously large meshes from curve conversion artifacts
        // (e.g., brain sulcus curves that produce giant tubes, ciliary body rings)
        // Uses world-space radius to account for model scaling
        for (var lk in this.layers) {
            var layerArr = this.layers[lk];
            for (var li = layerArr.length - 1; li >= 0; li--) {
                var m = layerArr[li];
                if (m.isMesh && m.geometry) {
                    m.geometry.computeBoundingSphere();
                    var ws = m.getWorldScale(new THREE.Vector3());
                    var worldRadius = m.geometry.boundingSphere.radius * Math.max(ws.x, ws.y, ws.z);
                    // Body is normalized to ~2 units; anything > 0.6 world radius is suspect
                    // (legitimate organs like lungs are ~0.3, limbs ~0.4)
                    var isCurveArtifact = m.name.toLowerCase().indexOf("-curve") >= 0 && worldRadius > 0.6;
                    var isGiantMesh = m.geometry.boundingSphere.radius > 20;
                    if (isCurveArtifact || isGiantMesh) {
                        m.visible = false;
                        m.userData.oversized = true;
                        layerArr.splice(li, 1);
                    }
                }
            }
        }

        // Re-fit: the initial normalization used maxDim from ALL meshes (including
        // text labels that inflate the bounding box). Compute the anatomy-only
        // bounding box and apply a scale correction so the body fills the viewport.
        //
        // CRITICAL: reset wrapper position to origin BEFORE computing the anatomy
        // box. The initial centering (line ~470) baked an offset into wrapper.position.
        // If we compute the anatomy box with that offset in matrixWorld, then try to
        // re-center by subtracting the world-space center, we double-count the offset.
        wrapper.position.set(0, 0, 0);
        wrapper.updateMatrixWorld(true);

        var anatomyBox = new THREE.Box3();
        for (var rk in this.layers) {
            var rarr = this.layers[rk];
            for (var ri = 0; ri < rarr.length; ri++) {
                var rm = rarr[ri];
                if (rm.isMesh && rm.geometry && rm.geometry.attributes.position
                    && rm.geometry.attributes.position.count > 10) {
                    if (!rm.geometry.boundingBox) rm.geometry.computeBoundingBox();
                    var geoBB = rm.geometry.boundingBox.clone();
                    geoBB.applyMatrix4(rm.matrixWorld);
                    anatomyBox.expandByPoint(geoBB.min);
                    anatomyBox.expandByPoint(geoBB.max);
                }
            }
        }
        if (!anatomyBox.isEmpty()) {
            var aSize = anatomyBox.getSize(new THREE.Vector3());
            var aMaxDim = Math.max(aSize.x, aSize.y, aSize.z);

            // Scale correction: if anatomy is smaller than target, scale up
            if (aMaxDim > 0.01 && aMaxDim < targetHeight * 0.95) {
                var correction = targetHeight / aMaxDim;
                wrapper.scale.multiplyScalar(correction);
                wrapper.position.set(0, 0, 0);
                wrapper.updateMatrixWorld(true);

                // Recompute anatomy box at new scale (clean position)
                anatomyBox = new THREE.Box3();
                for (var rk2 in this.layers) {
                    var rarr2 = this.layers[rk2];
                    for (var ri2 = 0; ri2 < rarr2.length; ri2++) {
                        var rm2 = rarr2[ri2];
                        if (rm2.isMesh && rm2.geometry && rm2.geometry.attributes.position
                            && rm2.geometry.attributes.position.count > 10) {
                            if (!rm2.geometry.boundingBox) rm2.geometry.computeBoundingBox();
                            var geoBB2 = rm2.geometry.boundingBox.clone();
                            geoBB2.applyMatrix4(rm2.matrixWorld);
                            anatomyBox.expandByPoint(geoBB2.min);
                            anatomyBox.expandByPoint(geoBB2.max);
                        }
                    }
                }
            }

            // Center anatomy at camera target — position is clean (no prior offset)
            var aCenter = anatomyBox.getCenter(new THREE.Vector3());
            wrapper.position.set(-aCenter.x, -aCenter.y + this.cameraPresets.default.target.y, -aCenter.z);
        }

        // Apply realistic anatomical materials to all layers
        this._applySkinMaterial(gender);
        this._applyMuscleMaterial();
        this._applySkeletonMaterial();
        this._applyVasculatureMaterial();
        this._applyNervousMaterial();
        this._applyOrganMaterial();

        // Gender-specific organ filtering (male GLB used as base for both)
        this._filterOrgansForGender(gender);

        this.setLayer(this.currentLayer);

        var loading = document.getElementById("bodymap-loading");
        if (loading) loading.style.display = "none";

        this.modelLoaded = true;
        this.loadFindings();

        // Load supplementary muscle GLBs (deep muscles, insertions) to fill
        // coverage gaps in the base Z-Anatomy model.
        this._loadSupplementaryMuscles();

        // NIH HRA organs are loaded on-demand when user drills into a category.
        // No eager loading needed — see _loadNIHOrgan().
    },

    // ── Supplementary Muscle GLBs ───────────────────────────────
    // Loads additional muscle data from Z-Anatomy HQ exports that aren't
    // in the base male_anatomy_full.glb. These fill torso, neck, and deep
    // muscle gaps visible when compared to Zygote Body reference.
    //
    // Files:
    //   z-anatomy-hq/muscular-system.glb  — 579 NEW meshes (deep abdominals,
    //       neck muscles, intercostals, rotators, etc.)
    //   z-anatomy-hq/muscular-insertions.glb — 705 NEW meshes (origin/insertion
    //       attachment point meshes for each muscle)
    //
    // Both share Z-Anatomy coordinate space so alignment is automatic when
    // added to the same wrapper group.

    _loadSupplementaryMuscles: function() {
        var self = this;
        var wrapper = this.currentModel;
        if (!wrapper) return;

        // Build a set of existing mesh names for fast deduplication
        var existingNames = {};
        wrapper.traverse(function(child) {
            if (child.isMesh) {
                existingNames[(child.name || "").toLowerCase()] = true;
            }
        });

        var glbPaths = [
            "/models/z-anatomy-hq/muscular-system.glb",
            "/models/z-anatomy-hq/muscular-insertions.glb"
        ];

        var loader = new THREE.GLTFLoader();
        try {
            var draco = new THREE.DRACOLoader();
            draco.setDecoderPath("https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/");
            loader.setDRACOLoader(draco);
        } catch (e) { /* Draco optional */ }

        var totalNew = 0, totalDups = 0, totalGlyphs = 0;
        var pending = glbPaths.length;

        // Z-Anatomy 3D text glyph filter
        var glyphRe = /(?:_g|systemg|organsg|glandsg|musclesg|girdleg|genitaliag|abdomeng|termsg|movementsg|linesg|planesg)$/;
        var instructionalRe = /^(how_to|navigation)/i;

        function onAllLoaded() {
            if (--pending > 0) return;
            console.log("[BodyMap3D] Supplementary muscles loaded: " + totalNew +
                " new, " + totalDups + " duplicates skipped, " + totalGlyphs + " glyphs skipped");

            // Apply muscle material to newly added meshes, then re-apply layer
            if (totalNew > 0) {
                self._applyMuscleMaterial();
                self.setLayer(self.currentLayer);
            }
        }

        for (var gi = 0; gi < glbPaths.length; gi++) {
            (function(glbPath) {
                fetch(glbPath, { method: "HEAD" }).then(function(r) {
                    if (!r.ok) {
                        console.warn("[BodyMap3D] Supplementary muscle GLB not found: " + glbPath);
                        onAllLoaded();
                        return;
                    }
                    loader.load(glbPath, function(gltf) {
                        var scene = gltf.scene;
                        var newMeshes = [];

                        scene.traverse(function(child) {
                            if (!child.isMesh) return;
                            var n = (child.name || "").toLowerCase();

                            // Skip instructional text
                            if (instructionalRe.test(n)) { totalGlyphs++; return; }

                            // Skip glyph/label meshes
                            var stripped = n.replace(/^(?:skel|musc|orgn|vasc|nerv|skin)__(?:(?:skel|musc|orgn|vasc|nerv|skin)_)*/g, "");
                            if (glyphRe.test(stripped)) { totalGlyphs++; return; }

                            // Skip duplicates (same name already in base model)
                            if (existingNames[n]) { totalDups++; return; }

                            // Skip flat text labels (2D geometry)
                            if (child.geometry) {
                                if (!child.geometry.boundingBox) child.geometry.computeBoundingBox();
                                var bb = child.geometry.boundingBox;
                                var dims = [
                                    bb.max.x - bb.min.x,
                                    bb.max.y - bb.min.y,
                                    bb.max.z - bb.min.z
                                ];
                                var dMax = Math.max(dims[0], dims[1], dims[2]);
                                var dMin = Math.min(dims[0], dims[1], dims[2]);
                                if (dMax > 0.001 && dMin / dMax < 0.05) {
                                    totalGlyphs++;
                                    return;
                                }
                            }

                            newMeshes.push(child);
                            existingNames[n] = true; // prevent cross-GLB duplicates
                        });

                        // Add the supplementary scene as a child of the wrapper
                        // (NOT of modelScene). Both the base model scene and
                        // supplementary scenes share the same Z-Anatomy coordinate
                        // system. The GLTFLoader applies its own Y-up conversion
                        // per scene, so each scene must be a direct wrapper child
                        // to get the same scale/rotation/position pipeline.
                        // DO NOT bake matrixWorld onto individual meshes — that
                        // double-applies the GLTF coordinate conversion.
                        wrapper.add(scene);

                        for (var mi = 0; mi < newMeshes.length; mi++) {
                            var mesh = newMeshes[mi];
                            self.layers.muscle.push(mesh);

                            // Tag for region mapping
                            mesh.userData.region = self._meshNameToRegion(
                                (mesh.name || "").toLowerCase()
                            );
                        }

                        totalNew += newMeshes.length;
                        console.log("[BodyMap3D] " + glbPath.split("/").pop() + ": " +
                            newMeshes.length + " new meshes added");
                        onAllLoaded();
                    }, null, function(err) {
                        console.warn("[BodyMap3D] Failed to load " + glbPath + ":", err);
                        onAllLoaded();
                    });
                }).catch(function() {
                    console.warn("[BodyMap3D] Cannot reach " + glbPath);
                    onAllLoaded();
                });
            })(glbPaths[gi]);
        }
    },

    // ── Detailed Organs (BodyParts3D) ──────────────────────────
    // Loads organs_detailed.glb as a secondary model. When the user
    // drills into a specific organ sub-category (Heart, Brain, etc.),
    // the detailed meshes replace Z-Anatomy's basic organ layer.
    // On "All Organs" the overview (Z-Anatomy) is restored.

    _loadDetailedOrgans: function() {
        var self = this;
        var path = "/models/organs_detailed.glb";

        fetch(path, { method: "HEAD" }).then(function(r) {
            if (!r.ok) {
                console.log("[BodyMap3D] No detailed organs model at " + path);
                return;
            }

            var loader = new THREE.GLTFLoader();
            try {
                var draco = new THREE.DRACOLoader();
                draco.setDecoderPath("https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/");
                loader.setDRACOLoader(draco);
            } catch (e) { /* Draco optional */ }

            loader.load(path, function(gltf) {
                self._onDetailedOrgansReady(gltf.scene);
            }, null, function(err) {
                console.warn("[BodyMap3D] Failed to load detailed organs:", err);
            });
        }).catch(function() {
            console.log("[BodyMap3D] Detailed organs model not available");
        });
    },

    _onDetailedOrgansReady: function(organsScene) {
        if (!this.currentModel) return;

        // Both Z-Anatomy and BodyParts3D export to GLB in meters, Y-up.
        // Add detailed organs directly INTO the main model's wrapper so they
        // share the exact same normalization transform (scale + position).
        // No separate normalization needed — coordinates should overlap.
        this.currentModel.children[0].add(organsScene);
        this.detailedOrgansModel = organsScene;

        // Parse categories from organ_* parent empties
        this.detailedOrgans = {};
        var self = this;

        organsScene.traverse(function(child) {
            if (!child.isMesh) return;

            // Walk up to find organ_* parent
            var category = null;
            var p = child.parent;
            while (p) {
                var pn = (p.name || "").toLowerCase();
                if (pn.indexOf("organ_") === 0) {
                    category = pn.replace("organ_", "");
                    break;
                }
                p = p.parent;
            }

            // Fallback: classify by mesh name
            if (!category) {
                category = self._classifyOrgan((child.name || "").toLowerCase());
            }

            if (category) {
                if (!self.detailedOrgans[category]) {
                    self.detailedOrgans[category] = [];
                }
                self.detailedOrgans[category].push(child);
            }

            // All detailed organs start hidden
            child.visible = false;
        });

        this.detailedOrgansLoaded = true;

        var catCounts = [];
        for (var cat in this.detailedOrgans) {
            catCounts.push(cat + ":" + this.detailedOrgans[cat].length);
        }
        console.log("[BodyMap3D] Detailed organs loaded: " + catCounts.join(", "));
    },

    // ── NIH HRA On-Demand Organ Loading ─────────────────────
    // Loads individual NIH HRA GLBs when user drills into an organ category.
    // Caches loaded groups for instant re-access. Files are added into the
    // main model wrapper to share normalization transform.

    _loadNIHOrgan: function(category) {
        var gender = this.currentGender || "male";
        var cacheKey = gender + "_" + category;

        // Already cached — just show it
        if (this.nihOrgansCache[cacheKey]) {
            this._showNIHOrgan(cacheKey);
            return;
        }

        // Already loading this category — don't duplicate
        if (this._nihOrganLoading === cacheKey) return;

        // Check registry
        var entry = this.nihOrganRegistry[category];
        if (!entry || !entry[gender] || entry[gender].length === 0) {
            console.warn("[BodyMap3D] No NIH HRA files for " + category + " (" + gender + ")");
            return;
        }

        this._nihOrganLoading = cacheKey;
        var files = entry[gender];
        var basePath = this.nihOrgansBasePath;
        var self = this;
        var loaded = 0;
        var group = new THREE.Group();
        group.name = "nih_" + cacheKey;
        var allMeshes = [];

        // Show loading indicator
        this._showNIHLoadingIndicator(category, true);

        console.log("[BodyMap3D] Loading NIH HRA " + category + " (" + gender + "): " +
            files.length + " file(s)");

        var loader = new THREE.GLTFLoader();
        try {
            var draco = new THREE.DRACOLoader();
            draco.setDecoderPath("https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/");
            loader.setDRACOLoader(draco);
        } catch (e) { /* Draco optional */ }

        files.forEach(function(file) {
            var url = basePath + file;
            loader.load(url, function(gltf) {
                var scene = gltf.scene;
                scene.name = file.replace(".glb", "");

                // Collect all meshes for visibility control
                scene.traverse(function(child) {
                    if (child.isMesh) {
                        allMeshes.push(child);
                        child.visible = true;
                    }
                });

                group.add(scene);
                loaded++;

                if (loaded === files.length) {
                    self._onNIHOrganReady(cacheKey, category, group, allMeshes);
                }
            }, function(event) {
                // Progress — could update indicator per-file
            }, function(err) {
                console.warn("[BodyMap3D] Failed to load " + url + ":", err);
                loaded++;
                if (loaded === files.length) {
                    self._onNIHOrganReady(cacheKey, category, group, allMeshes);
                }
            });
        });
    },

    _onNIHOrganReady: function(cacheKey, category, group, meshes) {
        this._nihOrganLoading = null;
        this._showNIHLoadingIndicator(category, false);

        if (meshes.length === 0) {
            console.warn("[BodyMap3D] NIH HRA " + cacheKey + " loaded 0 meshes");
            return;
        }

        // Add into main model wrapper to share normalization transform
        if (this.currentModel && this.currentModel.children[0]) {
            this.currentModel.children[0].add(group);
        }

        this.nihOrgansCache[cacheKey] = { group: group, meshes: meshes };

        console.log("[BodyMap3D] NIH HRA " + cacheKey + " ready: " +
            meshes.length + " meshes from " + group.children.length + " files");

        // If the user is still on this category, show it
        if (this.currentOrganCategory === category && this.currentLayer === "organs") {
            this._showNIHOrgan(cacheKey);
        }
    },

    _showNIHOrgan: function(cacheKey) {
        // Hide all cached NIH organs first
        for (var key in this.nihOrgansCache) {
            var entry = this.nihOrgansCache[key];
            for (var i = 0; i < entry.meshes.length; i++) {
                entry.meshes[i].visible = false;
            }
        }
        // Show requested
        var organ = this.nihOrgansCache[cacheKey];
        if (organ) {
            for (var j = 0; j < organ.meshes.length; j++) {
                organ.meshes[j].visible = true;
            }
        }
    },

    _hideAllNIHOrgans: function() {
        for (var key in this.nihOrgansCache) {
            var entry = this.nihOrgansCache[key];
            for (var i = 0; i < entry.meshes.length; i++) {
                entry.meshes[i].visible = false;
            }
        }
    },

    _showNIHLoadingIndicator: function(category, show) {
        var indicator = document.getElementById("nih-organ-loading");
        if (!indicator) {
            // Create floating indicator on canvas
            var canvas = document.getElementById("bodymap3d-canvas");
            if (!canvas || !canvas.parentElement) return;
            indicator = document.createElement("div");
            indicator.id = "nih-organ-loading";
            indicator.style.cssText = "position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);" +
                "background:rgba(0,0,0,0.7);color:#fff;padding:12px 24px;border-radius:8px;" +
                "font-size:14px;z-index:100;pointer-events:none;display:none;";
            canvas.parentElement.style.position = "relative";
            canvas.parentElement.appendChild(indicator);
        }
        if (show) {
            var label = category.replace("_", " ");
            label = label.charAt(0).toUpperCase() + label.slice(1);
            indicator.textContent = "Loading " + label + "…";
            indicator.style.display = "block";
        } else {
            indicator.style.display = "none";
        }
    },

    _showLoadingProgress: function(pct) {
        var bar = document.getElementById("glb-loading-progress");
        if (!bar) {
            var canvas = document.getElementById("bodymap3d-canvas");
            if (!canvas || !canvas.parentElement) return;
            bar = document.createElement("div");
            bar.id = "glb-loading-progress";
            bar.style.cssText = "position:absolute;bottom:20px;left:50%;transform:translateX(-50%);" +
                "background:rgba(0,0,0,0.8);padding:10px 20px;border-radius:8px;z-index:100;" +
                "display:flex;align-items:center;gap:12px;pointer-events:none;";
            // Build DOM elements safely (no innerHTML)
            var labelEl = document.createElement("span");
            labelEl.id = "glb-progress-label";
            labelEl.style.cssText = "color:#fff;font-size:13px;";
            labelEl.textContent = "Loading\u2026";
            var trackEl = document.createElement("div");
            trackEl.style.cssText = "width:160px;height:6px;background:rgba(255,255,255,0.2);border-radius:3px;overflow:hidden;";
            var fillEl = document.createElement("div");
            fillEl.id = "glb-progress-fill";
            fillEl.style.cssText = "width:0%;height:100%;background:#ef4444;border-radius:3px;transition:width 0.2s;";
            trackEl.appendChild(fillEl);
            bar.appendChild(labelEl);
            bar.appendChild(trackEl);
            canvas.parentElement.appendChild(bar);
        }
        bar.style.display = "flex";
        var fill = document.getElementById("glb-progress-fill");
        var label = document.getElementById("glb-progress-label");
        if (fill) fill.style.width = pct + "%";
        if (label) label.textContent = "Loading model\u2026 " + pct + "%";
    },

    _hideLoadingProgress: function() {
        var bar = document.getElementById("glb-loading-progress");
        if (bar) bar.style.display = "none";
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

    _classifyOrgan: function(meshName) {
        var cats = Object.keys(this.organCategories);
        for (var i = 0; i < cats.length; i++) {
            var keywords = this.organCategories[cats[i]];
            for (var j = 0; j < keywords.length; j++) {
                if (meshName.indexOf(keywords[j]) >= 0) return cats[i];
            }
        }
        return "other";
    },

    setOrganCategory: function(category) {
        this.currentOrganCategory = category;
        if (!this.currentModel || this.currentLayer !== "organs") return;

        var gender = this.currentGender || "male";
        var cacheKey = gender + "_" + category;

        // Check if NIH HRA high-detail organs are available/cached for this category
        var hasNIH = category !== "all" &&
            this.nihOrganRegistry[category] &&
            this.nihOrgansCache[cacheKey];

        // Check if NIH HRA files exist for this category (even if not yet loaded)
        var canLoadNIH = category !== "all" &&
            this.nihOrganRegistry[category] &&
            this.nihOrganRegistry[category][gender] &&
            this.nihOrganRegistry[category][gender].length > 0;

        // ── Companion layers: show for "all", hide for specific organ ──
        // When drilling into a specific organ (e.g. Liver), the vasculature +
        // nervous companions clutter the view. Hide them so only the organ shows.
        var companionLayers = ["vasculature", "nervous"];
        var self = this;
        if (category === "all") {
            // Restore companions at their normal opacity
            this.currentModel.traverse(function(child) {
                if (!child.isMesh) return;
                for (var ci = 0; ci < companionLayers.length; ci++) {
                    var compArr = self.layers[companionLayers[ci]] || [];
                    for (var cj = 0; cj < compArr.length; cj++) {
                        if (compArr[cj].uuid === child.uuid || (compArr[cj].traverse && child.uuid)) {
                            // Let setLayer handle visibility — just re-run it
                        }
                    }
                }
            });
            // Re-run setLayer to restore companion visibility properly
            this._restoreCompanions = true;
        } else {
            // Hide all companion layer meshes
            for (var ci = 0; ci < companionLayers.length; ci++) {
                var compMeshes = this.layers[companionLayers[ci]] || [];
                for (var cj = 0; cj < compMeshes.length; cj++) {
                    var cm = compMeshes[cj];
                    if (cm.isMesh) {
                        cm.visible = false;
                    } else if (cm.traverse) {
                        cm.traverse(function(d) { if (d.isMesh) d.visible = false; });
                    }
                }
            }
        }

        // ── Z-Anatomy (base) organ layer ──
        var organMeshes = this.layers.organs || [];
        var shown = 0, hidden = 0;
        for (var i = 0; i < organMeshes.length; i++) {
            var mesh = organMeshes[i];
            if (!mesh.isMesh) {
                // Handle group nodes — set visibility on all child meshes
                if (mesh.traverse) {
                    mesh.traverse(function(d) {
                        if (!d.isMesh) return;
                        if (category === "all") {
                            d.visible = true;
                            if (d.material) { d.material.opacity = 1.0; d.material.transparent = false; }
                            shown++;
                        } else if (hasNIH || canLoadNIH) {
                            d.visible = false; hidden++;
                        } else {
                            var meshCat = d.userData._organCategory || "other";
                            if (meshCat === category) {
                                d.visible = true;
                                if (d.material) { d.material.opacity = 1.0; d.material.transparent = false; }
                                shown++;
                            } else { d.visible = false; hidden++; }
                        }
                    });
                }
                continue;
            }
            if (category === "all") {
                mesh.visible = true;
                if (mesh.material) {
                    mesh.material.opacity = 1.0;
                    mesh.material.transparent = false;
                }
                shown++;
            } else if (hasNIH || canLoadNIH) {
                // Hide Z-Anatomy organs — NIH HRA meshes replace them
                mesh.visible = false;
                hidden++;
            } else {
                // No NIH HRA available — filter Z-Anatomy organs by category
                var meshCat = mesh.userData._organCategory || "other";
                if (meshCat === category) {
                    mesh.visible = true;
                    if (mesh.material) {
                        mesh.material.opacity = 1.0;
                        mesh.material.transparent = false;
                    }
                    shown++;
                } else {
                    mesh.visible = false;
                    hidden++;
                }
            }
        }

        if (category === "all") {
            this._hideAllNIHOrgans();
            // Re-run setLayer to restore companion visibility
            this.setLayer("organs");
        }

        // ── NIH HRA organ overlay ──
        if (hasNIH) {
            // Already cached — show immediately
            this._showNIHOrgan(cacheKey);
            console.log("[BodyMap3D] setOrganCategory('" + category + "') — NIH HRA cached, showing");
        } else if (canLoadNIH && category !== "all") {
            // Not yet loaded — trigger on-demand load
            this._loadNIHOrgan(category);
        } else if (category !== "all") {
            this._hideAllNIHOrgans();
        }

        // Legacy BodyParts3D overlay — hide all
        if (this.detailedOrgansLoaded) {
            for (var cat in this.detailedOrgans) {
                var meshes = this.detailedOrgans[cat];
                for (var di = 0; di < meshes.length; di++) {
                    meshes[di].visible = false;
                }
            }
        }

        console.log("[BodyMap3D] setOrganCategory('" + category + "') — base shown: " + shown + ", hidden: " + hidden);
    },

    _showFasciaLayer: function() {
        if (!this.currentModel) return;
        var layerNames = ["skin", "muscle", "skeleton", "organs", "vasculature", "nervous"];

        // Build layer UUID sets
        var layerSets = {};
        for (var i = 0; i < layerNames.length; i++) {
            var ln = layerNames[i];
            layerSets[ln] = {};
            var arr = this.layers[ln] || [];
            for (var j = 0; j < arr.length; j++) {
                layerSets[ln][arr[j].uuid] = true;
            }
        }

        var fasciaCount = 0;
        var self = this;
        this.currentModel.traverse(function(child) {
            if (child.userData._isGlyph) {
                if (child.userData._hiddenMat) child.material = child.userData._hiddenMat;
                return;
            }

            // Show fascia meshes with semi-translucent tan material
            if (child.userData._isFascia && child.isMesh) {
                child.visible = true;
                var fasciaColor = new THREE.Color();
                fasciaColor.setRGB(0.65, 0.52, 0.38, THREE.SRGBColorSpace);
                child.material = new THREE.MeshStandardMaterial({
                    color: fasciaColor,
                    roughness: 0.5,
                    metalness: 0.0,
                    transparent: true,
                    opacity: 0.75,
                    side: THREE.DoubleSide,
                    toneMapped: false,
                    depthWrite: false,
                    envMapIntensity: 0.0,
                });
                fasciaCount++;
                return;
            }

            // Show skeleton as companion at reduced opacity for context
            var childLayer = null;
            for (var k = 0; k < layerNames.length; k++) {
                if (layerSets[layerNames[k]][child.uuid]) {
                    childLayer = layerNames[k];
                    break;
                }
            }

            if (childLayer === "skeleton") {
                child.visible = true;
                if (child.isMesh && child.material) {
                    if (!child.userData._origLayerMat) {
                        child.userData._origLayerMat = child.material;
                    }
                    var baseMat = child.userData._origLayerMat;
                    var compMat = baseMat.clone();
                    compMat.transparent = true;
                    compMat.opacity = 0.4;
                    compMat.depthWrite = false;
                    child.material = compMat;
                }
            } else if (childLayer) {
                child.visible = false;
            } else if (child.isMesh && child.material) {
                if (!child.userData._hiddenMat) {
                    child.userData._origMat = child.material;
                    child.userData._hiddenMat = new THREE.MeshBasicMaterial({
                        visible: false, transparent: true, opacity: 0
                    });
                }
                child.material = child.userData._hiddenMat;
            }
        });
        console.log("[BodyMap3D] Fascia layer: " + fasciaCount + " fascia meshes shown");
    },

    // ═══════════════════════════════════════════════════════
    //  ENVIRONMENT MAP — HDR studio for PBR reflections
    // ═══════════════════════════════════════════════════════

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

    // ═══════════════════════════════════════════════════════
    //  POST-PROCESSING — EffectComposer pipeline
    // ═══════════════════════════════════════════════════════

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

        // Pass 3: Bloom — specular highlight glow
        this.bloomPass = new THREE.UnrealBloomPass(
            new THREE.Vector2(w, h),
            0.15,     // strength
            0.4,      // radius
            0.85      // threshold — only brightest highlights
        );
        this.composer.addPass(this.bloomPass);

        // Pass 4: Output — color space conversion (required final pass)
        var outputPass = new THREE.OutputPass();
        this.composer.addPass(outputPass);

        console.log("[BodyMap3D] Post-processing pipeline: RenderPass → SSAO → Bloom → Output");
    },

    // ═══════════════════════════════════════════════════════
    //  SKIN MATERIAL — PBR with subsurface scattering
    // ═══════════════════════════════════════════════════════

    _applySkinMaterial: function(gender) {
        var skinMeshes = this.layers.skin || [];

        // MeshPhysicalMaterial with transmission/thickness gives subsurface scattering
        var skinMat = new THREE.MeshPhysicalMaterial({
            color: new THREE.Color(0.72, 0.52, 0.40),        // warm skin tone
            roughness: 0.75,
            metalness: 0.0,
            clearcoat: 0.05,
            clearcoatRoughness: 0.4,
            sheen: 0.4,
            sheenRoughness: 0.5,
            sheenColor: new THREE.Color(0.6, 0.35, 0.25),    // warm sheen for skin depth
            envMapIntensity: 0.5,                              // HDR studio reflections
            side: THREE.DoubleSide,
        });

        // Collect all meshes — including children of Group nodes.
        // When traversing groups, skip meshes whose name prefix belongs to a
        // different layer (e.g. MUSC__ children under SKIN__ groups).
        var _otherPrefixes = ["musc__", "skel__", "orgn__", "vasc__", "nerv__"];
        var allMeshes = [];
        for (var i = 0; i < skinMeshes.length; i++) {
            var entry = skinMeshes[i];
            if (entry.isMesh) { allMeshes.push(entry); }
            else if (entry.traverse) { entry.traverse(function(d) {
                if (!d.isMesh) return;
                var dn = (d.name || "").toLowerCase();
                for (var p = 0; p < _otherPrefixes.length; p++) {
                    if (dn.indexOf(_otherPrefixes[p]) === 0) return;
                }
                allMeshes.push(d);
            }); }
        }
        for (var i = 0; i < allMeshes.length; i++) {
            var child = allMeshes[i];
            child.material = skinMat.clone();
            child.userData.originalColor = skinMat.color.getHex();
            child.userData.originalEmissive = 0x000000;
            if (child.geometry && !child.geometry.attributes.normal) {
                child.geometry.computeVertexNormals();
            }
        }
    },

    _applyMuscleMaterial: function() {
        var meshes = this.layers.muscle || [];

        // Simple string hash → 0..1 float for per-muscle color variation
        function hashName(str) {
            var h = 0;
            for (var i = 0; i < str.length; i++) {
                h = ((h << 5) - h + str.charCodeAt(i)) | 0;
            }
            return (((h >>> 0) % 10000) / 10000);
        }

        // Muscle palette — deep crimson red, specified in sRGB space.
        // Bumped ~10% from previous values to compensate for ACES Filmic tone mapping
        // which slightly darkens midtones. MeshPhysicalMaterial (lit) + clearcoat
        // gives wet muscle appearance with HDR env reflections.
        var baseR = 0.50, baseG = 0.09, baseB = 0.07;   // sRGB deep crimson (ACES-compensated)
        var rangeR = 0.15, rangeG = 0.04, rangeB = 0.03;

        var muscleCount = 0, fasciaCount = 0, tendonCount = 0;

        // Collect all meshes — including children of Group nodes.
        // Z-Anatomy packs some muscles as Group → child Mesh(es).
        // When traversing groups, skip meshes whose name prefix belongs to a
        // different layer (e.g. SKEL__ children under MUSC__ groups).
        var _otherPrefixes = ["skel__", "skin__", "orgn__", "vasc__", "nerv__"];
        var allMeshes = [];
        for (var i = 0; i < meshes.length; i++) {
            var entry = meshes[i];
            if (entry.isMesh) {
                allMeshes.push(entry);
            } else if (entry.traverse) {
                entry.traverse(function(desc) {
                    if (!desc.isMesh) return;
                    var dn = (desc.name || "").toLowerCase();
                    for (var p = 0; p < _otherPrefixes.length; p++) {
                        if (dn.indexOf(_otherPrefixes[p]) === 0) return;
                    }
                    allMeshes.push(desc);
                });
            }
        }

        for (var i = 0; i < allMeshes.length; i++) {
            var child = allMeshes[i];

            var n = (child.name || "muscle_" + i).toLowerCase();
            var h = hashName(n);

            // Per-muscle color: base + variation seeded by name hash (sRGB values)
            var r = baseR + h * rangeR;
            var g = baseG + ((h * 1.7) % 1) * rangeG;
            var b = baseB + ((h * 2.3) % 1) * rangeB;

            // Tendons/aponeuroses — actual cord/band connective tissue
            var isTendon = n.indexOf("tendon") >= 0 || n.indexOf("aponeuros") >= 0
                        || n.indexOf("retinacul") >= 0 || n.indexOf("ligament") >= 0;
            // Fascia — connective tissue sheaths. Hide them (user preference)
            // but NOT muscles whose name contains "fasciae" (e.g. Tensor fasciae
            // latae is a real hip muscle, not connective tissue).
            var isFascia = !isTendon && n.indexOf("fascia") >= 0
                        && n.indexOf("fasciae_latae") < 0;

            if (isFascia) {
                child.visible = false;
                child.userData._isFascia = true;
                fasciaCount++;
                continue;
            }

            if (isTendon) {
                r = 0.55; g = 0.42; b = 0.34;
                tendonCount++;
            }

            // MeshPhysicalMaterial with clearcoat + sheen for wet muscle appearance.
            // Lighting reveals surface contours: each muscle mesh catches light
            // differently based on surface normal orientation, making individual
            // muscles visually distinct. HDR env reflections add realistic ambient.
            var color = new THREE.Color();
            color.setRGB(r, g, b, THREE.SRGBColorSpace);
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

            child.material = mat;
            child.userData.originalColor = mat.color.getHex();
            child.userData.originalEmissive = 0x000000;
            if (child.geometry && !child.geometry.attributes.normal) {
                child.geometry.computeVertexNormals();
            }
            muscleCount++;
        }
        console.log("[BodyMap3D] Muscle material applied: " + muscleCount + " total (" +
            (muscleCount - fasciaCount - tendonCount) + " muscles, " + fasciaCount + " fascia, " + tendonCount + " tendons)");
    },

    _applySkeletonMaterial: function() {
        var meshes = this.layers.skeleton || [];
        var boneMat = new THREE.MeshPhysicalMaterial({
            color: new THREE.Color(0.92, 0.88, 0.78),   // warm ivory bone
            roughness: 0.5,
            metalness: 0.0,
            clearcoat: 0.12,
            clearcoatRoughness: 0.35,
            sheen: 0.2,
            sheenRoughness: 0.6,
            sheenColor: new THREE.Color(0.85, 0.80, 0.65),
            envMapIntensity: 0.35,                        // waxy porcelain-like surface
            side: THREE.DoubleSide,
        });
        // Collect all meshes — including children of Group nodes.
        // When traversing groups, skip meshes whose name prefix belongs to a
        // different layer (e.g. MUSC__ muscles parented under SKEL__ bone groups).
        var _otherPrefixes = ["musc__", "skin__", "orgn__", "vasc__", "nerv__"];
        var allMeshes = [];
        for (var i = 0; i < meshes.length; i++) {
            var entry = meshes[i];
            if (entry.isMesh) { allMeshes.push(entry); }
            else if (entry.traverse) { entry.traverse(function(d) {
                if (!d.isMesh) return;
                var dn = (d.name || "").toLowerCase();
                for (var p = 0; p < _otherPrefixes.length; p++) {
                    if (dn.indexOf(_otherPrefixes[p]) === 0) return;
                }
                allMeshes.push(d);
            }); }
        }
        for (var i = 0; i < allMeshes.length; i++) {
            var child = allMeshes[i];
            child.material = boneMat.clone();
            child.userData.originalColor = boneMat.color.getHex();
            child.userData.originalEmissive = 0x000000;
            if (child.geometry && !child.geometry.attributes.normal) {
                child.geometry.computeVertexNormals();
            }
        }
    },

    _applyVasculatureMaterial: function() {
        var meshes = this.layers.vasculature || [];
        var arteryMat = new THREE.MeshPhysicalMaterial({
            color: new THREE.Color(0.78, 0.12, 0.10),   // arterial red
            roughness: 0.35,
            metalness: 0.0,
            clearcoat: 0.2,
            clearcoatRoughness: 0.25,
            sheen: 0.35,
            sheenRoughness: 0.35,
            sheenColor: new THREE.Color(0.6, 0.08, 0.06),
            envMapIntensity: 0.6,                         // glossiest tissue — wet taut membrane
            side: THREE.DoubleSide,
        });
        var veinMat = new THREE.MeshPhysicalMaterial({
            color: new THREE.Color(0.20, 0.25, 0.60),   // venous blue
            roughness: 0.4,
            metalness: 0.0,
            clearcoat: 0.15,
            clearcoatRoughness: 0.3,
            sheen: 0.3,
            sheenRoughness: 0.4,
            sheenColor: new THREE.Color(0.15, 0.18, 0.45),
            envMapIntensity: 0.6,                         // glossiest tissue — wet taut membrane
            side: THREE.DoubleSide,
        });
        var veinKeywords = ["vein", "venous", "vena", "jugular", "saphenous", "portal", "azygos", "hemiazygos", "sinus"];
        // Collect all meshes — including children of Group nodes.
        // Skip meshes whose name prefix belongs to a different layer.
        var _otherPrefixes = ["musc__", "skel__", "skin__", "orgn__", "nerv__"];
        var allMeshes = [];
        for (var i = 0; i < meshes.length; i++) {
            var entry = meshes[i];
            if (entry.isMesh) { allMeshes.push(entry); }
            else if (entry.traverse) { entry.traverse(function(d) {
                if (!d.isMesh) return;
                var dn = (d.name || "").toLowerCase();
                for (var p = 0; p < _otherPrefixes.length; p++) {
                    if (dn.indexOf(_otherPrefixes[p]) === 0) return;
                }
                allMeshes.push(d);
            }); }
        }
        for (var i = 0; i < allMeshes.length; i++) {
            var child = allMeshes[i];
            var n = (child.name || "").toLowerCase();
            var isVein = false;
            for (var j = 0; j < veinKeywords.length; j++) {
                if (n.indexOf(veinKeywords[j]) >= 0) { isVein = true; break; }
            }
            var mat = isVein ? veinMat : arteryMat;
            child.material = mat.clone();
            child.userData.originalColor = mat.color.getHex();
            child.userData.originalEmissive = 0x000000;
            if (child.geometry && !child.geometry.attributes.normal) {
                child.geometry.computeVertexNormals();
            }
        }
    },

    _applyNervousMaterial: function() {
        var meshes = this.layers.nervous || [];
        var nerveMat = new THREE.MeshPhysicalMaterial({
            color: new THREE.Color(0.95, 0.85, 0.35),   // bright neural yellow
            roughness: 0.45,
            metalness: 0.0,
            clearcoat: 0.1,
            clearcoatRoughness: 0.45,
            sheen: 0.35,
            sheenRoughness: 0.35,
            sheenColor: new THREE.Color(0.80, 0.65, 0.20),
            envMapIntensity: 0.3,                         // myelin sheath subtle sheen
            side: THREE.DoubleSide,
        });
        // Collect all meshes — including children of Group nodes.
        // Skip meshes whose name prefix belongs to a different layer.
        var _otherPrefixes = ["musc__", "skel__", "skin__", "orgn__", "vasc__"];
        var allMeshes = [];
        for (var i = 0; i < meshes.length; i++) {
            var entry = meshes[i];
            if (entry.isMesh) { allMeshes.push(entry); }
            else if (entry.traverse) { entry.traverse(function(d) {
                if (!d.isMesh) return;
                var dn = (d.name || "").toLowerCase();
                for (var p = 0; p < _otherPrefixes.length; p++) {
                    if (dn.indexOf(_otherPrefixes[p]) === 0) return;
                }
                allMeshes.push(d);
            }); }
        }
        for (var i = 0; i < allMeshes.length; i++) {
            var child = allMeshes[i];
            // Keep existing colors for meshes that already have non-white/non-black colors
            var existing = child.material && child.material.color ?
                child.material.color.getHexString() : "ffffff";
            if (existing === "ffffff" || existing === "000000") {
                child.material = nerveMat.clone();
                child.userData.originalColor = nerveMat.color.getHex();
                child.userData.originalEmissive = 0x000000;
            }
            if (child.geometry && !child.geometry.attributes.normal) {
                child.geometry.computeVertexNormals();
            }
        }
    },

    _applyOrganMaterial: function() {
        var meshes = this.layers.organs || [];
        var seen = {};  // deduplicate cross-listed meshes

        // Anatomically accurate organ colors (sRGB) with per-mesh variation
        // Each organ system gets a distinct hue so they're visually separable
        var organColors = [
            // Cardiac — deep crimson-red
            { keywords: ["heart", "ventricle", "atrium", "coronary", "pericardium",
                         "papillary_muscle", "leaflet", "valve", "pulmonary_trunk",
                         "mitral", "tricuspid", "semilunar", "chordae", "endocardium", "myocardium"],
              base: [0.65, 0.14, 0.12], range: [0.08, 0.04, 0.03] },
            // Lungs — soft mauve-pink
            { keywords: ["lung", "bronch", "alveol", "pleura", "lobe_"],
              base: [0.72, 0.48, 0.52], range: [0.06, 0.04, 0.04] },
            // Trachea/airway — pale cartilage
            { keywords: ["trachea", "larynx", "pharynx", "epiglott"],
              base: [0.75, 0.62, 0.55], range: [0.04, 0.03, 0.03] },
            // Diaphragm — muscular red-brown
            { keywords: ["diaphragm"],
              base: [0.58, 0.25, 0.20], range: [0.05, 0.03, 0.02] },
            // Brain — pinkish-grey cortex
            { keywords: ["brain", "cerebr", "cerebel", "hippocampus", "thalamus",
                         "hypothalamus", "amygdala", "pons", "medulla_oblongata",
                         "midbrain", "corpus_callosum", "frontal_lobe", "parietal_lobe",
                         "temporal_lobe", "occipital_lobe", "brainstem", "meninges",
                         "dura_mater", "pia_mater"],
              base: [0.78, 0.68, 0.65], range: [0.05, 0.04, 0.04] },
            // Spinal cord — off-white neural
            { keywords: ["spinal_cord"],
              base: [0.82, 0.78, 0.72], range: [0.03, 0.03, 0.03] },
            // Liver — dark reddish-brown
            { keywords: ["liver", "hepat", "gallbladder", "bile"],
              base: [0.50, 0.18, 0.14], range: [0.06, 0.03, 0.02] },
            // Kidneys — dark bean-brown
            { keywords: ["kidney", "renal", "adrenal", "suprarenal", "ureter"],
              base: [0.55, 0.25, 0.20], range: [0.05, 0.03, 0.02] },
            // Stomach — warm pink-tan
            { keywords: ["stomach", "gastric", "pylor", "fundus"],
              base: [0.78, 0.55, 0.48], range: [0.05, 0.04, 0.03] },
            // Intestines — warm tan-pink
            { keywords: ["intestin", "colon", "rectum", "cecum", "appendix",
                         "duoden", "jejun", "ileum", "sigmoid"],
              base: [0.80, 0.60, 0.48], range: [0.06, 0.05, 0.04] },
            // Esophagus — pinkish tube
            { keywords: ["esophag"],
              base: [0.75, 0.52, 0.48], range: [0.04, 0.03, 0.03] },
            // Spleen — deep purple-red
            { keywords: ["spleen"],
              base: [0.45, 0.15, 0.20], range: [0.04, 0.02, 0.03] },
            // Pancreas — yellowish-tan
            { keywords: ["pancrea"],
              base: [0.82, 0.70, 0.48], range: [0.04, 0.04, 0.03] },
            // Bladder — pale yellowish
            { keywords: ["bladder"],
              base: [0.78, 0.68, 0.50], range: [0.04, 0.03, 0.03] },
            // Reproductive — warm pink
            { keywords: ["uterus", "ovary", "testi", "prostate", "penis",
                         "vagina", "scrotum", "fallopian", "epididym", "seminal"],
              base: [0.72, 0.42, 0.42], range: [0.06, 0.04, 0.04] },
            // Endocrine glands — warm amber
            { keywords: ["thyroid", "pituitary", "pineal", "parathyroid", "thymus"],
              base: [0.72, 0.48, 0.35], range: [0.05, 0.04, 0.03] },
            // Eye
            { keywords: ["eye", "retina", "lens", "cornea", "sclera"],
              base: [0.88, 0.85, 0.82], range: [0.03, 0.03, 0.03] },
            // Oral — tongue, tonsil, salivary
            { keywords: ["tongue", "tonsil", "salivary", "uvula"],
              base: [0.72, 0.45, 0.42], range: [0.05, 0.04, 0.03] },
        ];

        // Default: soft pinkish tissue for unmatched organs
        var defaultBase = [0.75, 0.52, 0.48];
        var defaultRange = [0.06, 0.04, 0.04];

        function hashName(str) {
            var h = 0;
            for (var c = 0; c < str.length; c++) {
                h = ((h << 5) - h + str.charCodeAt(c)) | 0;
            }
            return (((h >>> 0) % 10000) / 10000);
        }

        // Collect all meshes — including children of Group nodes.
        // Skip meshes whose name prefix belongs to a different layer.
        var _otherPrefixes = ["musc__", "skel__", "skin__", "vasc__", "nerv__"];
        var allMeshes = [];
        for (var i = 0; i < meshes.length; i++) {
            var entry = meshes[i];
            if (entry.isMesh) { allMeshes.push(entry); }
            else if (entry.traverse) { entry.traverse(function(d) {
                if (!d.isMesh) return;
                var dn = (d.name || "").toLowerCase();
                for (var p = 0; p < _otherPrefixes.length; p++) {
                    if (dn.indexOf(_otherPrefixes[p]) === 0) return;
                }
                allMeshes.push(d);
            }); }
        }

        var applied = 0;
        for (var i = 0; i < allMeshes.length; i++) {
            var child = allMeshes[i];
            if (seen[child.uuid]) continue;
            seen[child.uuid] = true;

            var n = (child.name || "organ_" + i).toLowerCase();
            var h = hashName(n);

            // Find organ-specific color
            var base = defaultBase, range = defaultRange;
            for (var j = 0; j < organColors.length; j++) {
                var kws = organColors[j].keywords;
                var found = false;
                for (var k = 0; k < kws.length; k++) {
                    if (n.indexOf(kws[k]) >= 0) { found = true; break; }
                }
                if (found) {
                    base = organColors[j].base;
                    range = organColors[j].range;
                    break;
                }
            }

            // Per-mesh color variation (same technique as muscle)
            var r = base[0] + h * range[0];
            var g = base[1] + ((h * 1.7) % 1) * range[1];
            var b = base[2] + ((h * 2.3) % 1) * range[2];

            var color = new THREE.Color();
            color.setRGB(r, g, b, THREE.SRGBColorSpace);

            var mat = new THREE.MeshPhysicalMaterial({
                color: color,
                roughness: 0.5,
                metalness: 0.0,
                clearcoat: 0.08,
                clearcoatRoughness: 0.4,
                sheen: 0.2,
                sheenRoughness: 0.5,
                envMapIntensity: 0.45,                    // moist organ surfaces
                side: THREE.DoubleSide,
            });

            child.material = mat;
            child.userData.originalColor = mat.color.getHex();
            child.userData.originalEmissive = 0x000000;
            if (child.geometry && !child.geometry.attributes.normal) {
                child.geometry.computeVertexNormals();
            }
            applied++;
        }
        console.log("[BodyMap3D] Organ material applied: " + applied + " unique meshes colored");
    },

    _filterOrgansForGender: function(gender) {
        // Male-specific organs to hide when viewing as female
        var maleOnly = ["prostate", "seminal", "testis", "testes", "epididymis", "vas_deferens"];
        // Female-specific organs to hide when viewing as male
        var femaleOnly = ["uterus", "ovary", "ovaries", "fallopian"];

        var hideList = gender === "female" ? maleOnly : femaleOnly;
        var organMeshes = this.layers.organs || [];

        for (var i = 0; i < organMeshes.length; i++) {
            var mesh = organMeshes[i];
            var n = (mesh.name || "").toLowerCase();
            var shouldHide = false;
            for (var j = 0; j < hideList.length; j++) {
                if (n.indexOf(hideList[j]) >= 0) { shouldHide = true; break; }
            }
            if (shouldHide) mesh.visible = false;
        }
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

    // Map layer names to mesh prefixes (handles singular/plural mismatch)
    _layerMeshPrefixes: {
        skin: "skin_",
        muscle: "muscle_",
        skeleton: "skeleton_",
        organs: "organ_",       // meshes use singular "organ_heart", not "organs_heart"
        vasculature: "artery_", // also matches "vein_" — checked separately below
        nervous: "nerve_",
    },

    setLayer: function(layer) {
        this.currentLayer = layer;
        var layerNames = ["skin", "muscle", "skeleton", "organs", "vasculature", "nervous"];
        if (!this.currentModel) return;

        // Update toolbar active state
        var allBtns = document.querySelectorAll(".bodymap-layer");
        for (var bi = 0; bi < allBtns.length; bi++) {
            var btnLayer = allBtns[bi].dataset.layer;
            if (btnLayer === layer) {
                allBtns[bi].classList.add("active");
            } else {
                allBtns[bi].classList.remove("active");
            }
        }

        // Hide detailed organs when switching away from organs layer
        this._hideAllNIHOrgans();
        if (this.detailedOrgansLoaded) {
            for (var dcat in this.detailedOrgans) {
                var dmeshes = this.detailedOrgans[dcat];
                for (var dmi = 0; dmi < dmeshes.length; dmi++) {
                    dmeshes[dmi].visible = false;
                }
            }
        }

        // Handle fascia as a pseudo-layer: show only fascia-tagged muscle meshes
        if (layer === "fascia") {
            this._showFasciaLayer();
            return;
        }

        // Reset organ category when switching to organs
        if (layer === "organs") {
            this.currentOrganCategory = "all";
            var organBtns = document.querySelectorAll(".bodymap-organ-btn");
            for (var obi = 0; obi < organBtns.length; obi++) {
                organBtns[obi].classList.toggle("active", organBtns[obi].dataset.organ === "all");
            }
        }

        // Each filter shows its own system at full detail.
        // Anatomically intertwined systems appear as companions where they add
        // genuine detail (vessels through organs, nerves along bones).
        // Muscle stays clean — those 1,951 meshes speak for themselves.
        var companions = {
            skin:         [],
            muscle:       [],
            skeleton:     [{layer: "nervous", opacity: 0.5}],
            organs:       [{layer: "vasculature", opacity: 0.7}, {layer: "nervous", opacity: 0.45}],
            vasculature:  [{layer: "nervous", opacity: 0.35}],
            nervous:      [{layer: "vasculature", opacity: 0.35}]
        };

        // Build companion opacity lookup: companionOf[layerName] = opacity (0 = not a companion)
        var companionOf = {};
        var comps = companions[layer] || [];
        for (var ci = 0; ci < comps.length; ci++) {
            companionOf[comps[ci].layer] = comps[ci].opacity;
        }

        // Build a Set of UUIDs for each layer from the parsed this.layers dict.
        // Include descendant meshes of group nodes — Z-Anatomy packs some
        // muscles as Group → child Mesh, and those children need layer tagging
        // or setLayer hides them as "untagged".
        // IMPORTANT: When traversing groups, skip descendants whose name prefix
        // belongs to a different layer (e.g. MUSC__ children of SKEL__ groups).
        var prefixToLayer = {
            "skel__": "skeleton", "musc__": "muscle", "orgn__": "organs",
            "vasc__": "vasculature", "nerv__": "nervous", "skin__": "skin"
        };
        var layerSets = {};
        for (var i = 0; i < layerNames.length; i++) {
            var ln = layerNames[i];
            layerSets[ln] = {};
            var arr = this.layers[ln] || [];
            for (var j = 0; j < arr.length; j++) {
                var node = arr[j];
                layerSets[ln][node.uuid] = true;
                // Tag descendant meshes — but only if they don't belong to another layer
                if (!node.isMesh && node.traverse) {
                    node.traverse(function(desc) {
                        var dn = (desc.name || "").toLowerCase();
                        var descPrefix = dn.substring(0, 6);
                        // Check if first 4-6 chars match a known prefix from another layer
                        for (var pfx in prefixToLayer) {
                            if (dn.indexOf(pfx) === 0 && prefixToLayer[pfx] !== ln) {
                                return; // belongs to a different layer — skip
                            }
                        }
                        layerSets[ln][desc.uuid] = true;
                    });
                }
            }
        }

        this.currentModel.traverse(function(child) {
            // Determine which layer this child belongs to
            var childLayer = null;
            for (var k = 0; k < layerNames.length; k++) {
                if (layerSets[layerNames[k]][child.uuid]) {
                    childLayer = layerNames[k];
                    break;
                }
            }
            // Always keep glyph text meshes hidden regardless of active layer
            if (child.userData._isGlyph) {
                if (child.userData._hiddenMat) child.material = child.userData._hiddenMat;
                return;
            }
            // Keep fascia hidden in muscle view — 44 stacked fascia meshes
            // create an opaque veil that hides muscle fiber detail
            if (child.userData._isFascia && layer === "muscle") {
                child.visible = false;
                return;
            }

            if (!childLayer) {
                // Hide untagged meshes' own rendering (text labels, reference lines)
                // but do NOT set visible=false — that would hide children too
                // (Z-Anatomy glyph nodes are parents of real anatomy meshes).
                if (child.isMesh && child.material) {
                    if (!child.userData._hiddenMat) {
                        child.userData._origMat = child.material;
                        child.userData._hiddenMat = new THREE.MeshBasicMaterial({
                            visible: false, transparent: true, opacity: 0
                        });
                    }
                    child.material = child.userData._hiddenMat;
                }
                return;
            }

            if (childLayer === layer) {
                // Active layer: fully visible
                child.visible = true;
                if (child.isMesh) {
                    // Restore original skin material if switching back to skin layer
                    if (childLayer === "skin" && child.userData.skinMaterial) {
                        child.material = child.userData.skinMaterial;
                    }
                    // Restore original material if it was swapped to hidden
                    if (child.userData._origMat && child.material === child.userData._hiddenMat) {
                        child.material = child.userData._origMat;
                    }
                    if (child.material) {
                        child.material.opacity = 1.0;
                        child.material.transparent = false;
                    }
                }
            } else if (companionOf[childLayer]) {
                // Companion layer: show at reduced opacity for anatomical context
                child.visible = true;
                if (child.isMesh && child.material) {
                    // Save original material if needed
                    if (!child.userData._origLayerMat) {
                        child.userData._origLayerMat = child.material;
                    }
                    // Restore original first (in case it was previously ghosted)
                    var baseMat = child.userData._origLayerMat;
                    var compMat = baseMat.clone();
                    compMat.transparent = true;
                    compMat.opacity = companionOf[childLayer];
                    compMat.depthWrite = companionOf[childLayer] > 0.4;
                    child.material = compMat;
                }
            } else {
                // Inactive layer — hide this node.
                // CRITICAL: Only set visible=false on MESH nodes, not groups.
                // In Three.js, parent.visible=false cascades to ALL children,
                // which would hide muscles parented under skeleton groups (e.g.
                // pectoralis_major is a child of the humerus bone group).
                // For non-mesh nodes, keep visible=true so children can render.
                if (child.isMesh) {
                    if (child.material) {
                        if (!child.userData._hiddenMat) {
                            child.userData._origMat = child.material;
                            child.userData._hiddenMat = new THREE.MeshBasicMaterial({
                                visible: false, transparent: true, opacity: 0
                            });
                        }
                        child.material = child.userData._hiddenMat;
                    }
                }
                // Non-mesh group nodes: keep visible=true (children may be in active layer)
            }
        });

        // Diagnostic: count visible meshes by layer and material type
        var diag = {active: 0, companion: 0, hidden: 0, untagged: 0, skinVisible: 0};
        var self2 = this;
        this.currentModel.traverse(function(child) {
            if (!child.isMesh) return;
            if (!child.visible) { diag.hidden++; return; }
            if (child.material && child.material.visible === false) { diag.hidden++; return; }
            var cl = null;
            for (var k = 0; k < layerNames.length; k++) {
                if (layerSets[layerNames[k]][child.uuid]) { cl = layerNames[k]; break; }
            }
            if (!cl) { diag.untagged++; return; }
            if (cl === layer) diag.active++;
            else if (cl === "skin") diag.skinVisible++;
            else diag.companion++;
        });
        console.log("[BodyMap3D] setLayer('" + layer + "') — visible: active=" + diag.active +
            " companion=" + diag.companion + " skinVisible=" + diag.skinVisible +
            " untagged=" + diag.untagged + " hidden=" + diag.hidden);

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

    zoom: function(factor) {
        if (!this.camera || !this.controls) return;
        var dir = new THREE.Vector3().subVectors(this.camera.position, this.controls.target);
        dir.multiplyScalar(factor);
        var newPos = new THREE.Vector3().addVectors(this.controls.target, dir);
        // Clamp to min/max distance
        var dist = newPos.distanceTo(this.controls.target);
        if (dist < this.controls.minDistance || dist > this.controls.maxDistance) return;
        this._animateCamera(newPos, this.controls.target.clone());
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
        if (this.composer) this.composer.setSize(w, h);
    },
};
