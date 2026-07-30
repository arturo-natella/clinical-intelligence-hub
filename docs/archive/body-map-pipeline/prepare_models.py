#!/usr/bin/env python3
"""
Blender Headless Model Processing Pipeline
===========================================
Clinical Intelligence Hub — Phase 11

Converts free anatomical models into our 4-layer GLB convention for Three.js.
Supports BodyParts3D (FJ-numbered OBJs), Z-Anatomy (.blend), and generic models.

Usage (BodyParts3D — primary workflow):
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python prepare_models.py -- \
        --source ./bodyparts3d_raw_partof/partof_BP3D_4.0_obj_99 \
        --gender male \
        --mapping ./partof_element_parts.txt

Usage (Z-Anatomy .blend):
    blender --background --python prepare_models.py -- \
        --source /path/to/z_anatomy.blend --gender male

Arguments after '--':
    --source   Path to source directory (FJ*.obj files) or single file
    --gender   'male' or 'female' (determines output filename + organ filtering)
    --output   Output directory (default: same directory as this script)
    --quality  Draco compression quality 1-10 (default: 7)
    --mapping  Path to partof_element_parts.txt (BodyParts3D FJ→name mapping)

Output:
    male_anatomy.glb   or   female_anatomy.glb
    With named mesh groups: layer_skin, layer_muscle, layer_skeleton, layer_organs

Model Sources (all free, open-source):
    - BodyParts3D v4.0 (CC BY-SA 2.1 JP) — 1,258 OBJ meshes, male anatomy
      https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html
    - Z-Anatomy (CC BY-SA 4.0) — Blender files, male + female
      https://github.com/LluisV/Z-Anatomy
    - NIH 3D Print Exchange (Public Domain) — individual organs
      https://3dprint.nih.gov/
"""

import bpy
import os
import sys
import math
import re
from pathlib import Path
from collections import defaultdict


# ═══════════════════════════════════════════════════════════
#  BODYPARTS3D FJ ID → ORGAN NAME MAPPING
# ═══════════════════════════════════════════════════════════
#
# BodyParts3D uses FJ-prefixed IDs for mesh files (e.g., FJ2417.obj).
# These map to FMA (Foundational Model of Anatomy) concepts via the
# partof_element_parts.txt file from DBCLS.
#
# This table provides direct FJ→target name mapping for key organs.
# For FJ IDs not in this table, we fall back to the element_parts
# mapping file (parsed at runtime) + pattern-based classification.
#
# Format: "FJ_ID": ("target_name", "layer")
# The "M" suffix on FJ IDs indicates mirrored/left-side geometry.

FJ_DIRECT_MAP = {
    # ─── HEART (FMA7088) ───────────────────────────────
    "FJ2417": ("organ_heart", "organs"),
    "FJ2418": ("organ_heart", "organs"),
    "FJ2419": ("organ_heart", "organs"),
    "FJ2420": ("organ_heart", "organs"),
    "FJ2421": ("organ_heart", "organs"),
    "FJ2422": ("organ_heart", "organs"),
    "FJ2423": ("organ_heart", "organs"),
    "FJ2424": ("organ_heart", "organs"),
    "FJ2425": ("organ_heart", "organs"),
    "FJ2426": ("organ_heart", "organs"),
    "FJ2427": ("organ_heart", "organs"),
    "FJ2428": ("organ_heart", "organs"),
    "FJ2429": ("organ_heart", "organs"),
    "FJ2430": ("organ_heart", "organs"),
    "FJ2431": ("organ_heart", "organs"),
    "FJ2432": ("organ_heart", "organs"),
    "FJ2433": ("organ_heart", "organs"),
    "FJ2434": ("organ_heart", "organs"),
    "FJ2435": ("organ_heart", "organs"),
    "FJ2436": ("organ_heart", "organs"),
    "FJ2437": ("organ_heart", "organs"),
    "FJ2438": ("organ_heart", "organs"),
    "FJ2439": ("organ_heart", "organs"),
    "FJ2440": ("organ_heart", "organs"),

    # ─── LEFT LUNG (FMA7310) ──────────────────────────
    "FJ2441": ("organ_lung_left", "organs"),
    "FJ2442": ("organ_lung_left", "organs"),
    "FJ2443": ("organ_lung_left", "organs"),
    "FJ2444": ("organ_lung_left", "organs"),
    "FJ2445": ("organ_lung_left", "organs"),
    "FJ2446": ("organ_lung_left", "organs"),
    "FJ2447": ("organ_lung_left", "organs"),
    "FJ2448": ("organ_lung_left", "organs"),
    "FJ2460": ("organ_lung_left", "organs"),
    "FJ2461": ("organ_lung_left", "organs"),

    # ─── RIGHT LUNG (FMA7309) ─────────────────────────
    "FJ2041": ("organ_lung_right", "organs"),
    "FJ2044": ("organ_lung_right", "organs"),
    "FJ2449": ("organ_lung_right", "organs"),
    "FJ2451": ("organ_lung_right", "organs"),
    "FJ2452": ("organ_lung_right", "organs"),
    "FJ2453": ("organ_lung_right", "organs"),
    "FJ2454": ("organ_lung_right", "organs"),
    "FJ2455": ("organ_lung_right", "organs"),
    "FJ2456": ("organ_lung_right", "organs"),
    "FJ2457": ("organ_lung_right", "organs"),
    "FJ2458": ("organ_lung_right", "organs"),
    "FJ2459": ("organ_lung_right", "organs"),

    # ─── LIVER (FMA7197) ──────────────────────────────
    "FJ1883": ("organ_liver", "organs"),
    "FJ1893": ("organ_liver", "organs"),
    "FJ1913": ("organ_liver", "organs"),
    "FJ1914": ("organ_liver", "organs"),
    "FJ1916": ("organ_liver", "organs"),

    # ─── KIDNEYS ──────────────────────────────────────
    "FJ3145": ("organ_kidney_left", "organs"),   # FMA7205
    "FJ3147": ("organ_kidney_right", "organs"),  # FMA7204

    # ─── BRAIN (FMA50801) ─────────────────────────────
    "FJ1730": ("organ_brain", "organs"),
    "FJ1731": ("organ_brain", "organs"),
    "FJ1732": ("organ_brain", "organs"),
    "FJ1733": ("organ_brain", "organs"),
    "FJ1738": ("organ_brain", "organs"),
    "FJ1739": ("organ_brain", "organs"),
    "FJ1740": ("organ_brain", "organs"),
    "FJ1743": ("organ_brain", "organs"),
    "FJ1744": ("organ_brain", "organs"),
    "FJ1745": ("organ_brain", "organs"),

    # ─── CEREBELLUM (FMA67944) ────────────────────────
    "FJ1781": ("organ_cerebellum", "organs"),
    "FJ1830": ("organ_cerebellum", "organs"),

    # ─── SPINAL CORD (FMA7647) ────────────────────────
    "FJ1737": ("organ_spinal_cord", "organs"),

    # ─── STOMACH (FMA7148) ────────────────────────────
    "FJ2564": ("organ_stomach", "organs"),

    # ─── PANCREAS (FMA7198) ───────────────────────────
    "FJ1895": ("organ_pancreas", "organs"),
    "FJ1896": ("organ_pancreas", "organs"),
    "FJ2629": ("organ_pancreas", "organs"),
    "FJ2630": ("organ_pancreas", "organs"),

    # ─── ESOPHAGUS (FMA7131) ──────────────────────────
    "FJ2563": ("organ_esophagus", "organs"),

    # ─── TRACHEA (FMA7394) ────────────────────────────
    "FJ2541": ("organ_trachea", "organs"),

    # ─── GALLBLADDER (FMA7202) ────────────────────────
    "FJ2817": ("organ_gallbladder", "organs"),

    # ─── URINARY BLADDER (FMA15900) ───────────────────
    "FJ3149": ("organ_bladder", "organs"),

    # ─── PROSTATE (FMA9600, male only) ────────────────
    "FJ3139": ("organ_prostate", "organs"),

    # ─── ADRENAL GLANDS ──────────────────────────────
    "FJ3129": ("organ_adrenal_left", "organs"),   # FMA15630
    "FJ3130": ("organ_adrenal_right", "organs"),  # FMA15629

    # ─── SMALL INTESTINE (FMA7200) ────────────────────
    "FJ2573": ("organ_small_intestine", "organs"),
    "FJ2574": ("organ_small_intestine", "organs"),
    "FJ2575": ("organ_small_intestine", "organs"),
    "FJ2576": ("organ_small_intestine", "organs"),
    "FJ2577": ("organ_small_intestine", "organs"),
    "FJ2578": ("organ_small_intestine", "organs"),
    "FJ2579": ("organ_small_intestine", "organs"),
    "FJ2580": ("organ_small_intestine", "organs"),
    "FJ2581": ("organ_small_intestine", "organs"),
    "FJ2582": ("organ_small_intestine", "organs"),

    # ─── LARGE INTESTINE / COLON ──────────────────────
    "FJ2565": ("organ_appendix", "organs"),       # FMA14542
    "FJ2566": ("organ_large_intestine", "organs"), # ascending colon
    "FJ2567": ("organ_large_intestine", "organs"), # descending colon
    "FJ2568": ("organ_large_intestine", "organs"), # muscle layer
    "FJ2569": ("organ_large_intestine", "organs"),
    "FJ2570": ("organ_large_intestine", "organs"),
    "FJ2571": ("organ_large_intestine", "organs"), # rectum
    "FJ2572": ("organ_large_intestine", "organs"), # transverse colon
    "FJ2599": ("organ_large_intestine", "organs"), # cecum

    # ─── AORTA (FMA3734) ─────────────────────────────
    "FJ1931": ("organ_aorta", "organs"),
    "FJ1932": ("organ_aorta", "organs"),
    "FJ3411": ("organ_aorta", "organs"),
    "FJ3413": ("organ_aorta", "organs"),
    "FJ3427": ("organ_aorta", "organs"),

    # ─── SKIN (FMA7163) ──────────────────────────────
    "FJ2810": ("skin_body", "skin"),

    # ─── SKULL (FMA46565) ─────────────────────────────
    "FJ1282": ("skeleton_skull", "skeleton"),
    "FJ1285": ("skeleton_skull", "skeleton"),
    "FJ1286": ("skeleton_skull", "skeleton"),
    "FJ1289": ("skeleton_skull", "skeleton"),
    "FJ1294": ("skeleton_skull", "skeleton"),
    "FJ1295": ("skeleton_skull", "skeleton"),
    "FJ1297": ("skeleton_skull", "skeleton"),

    # ─── THORACIC VERTEBRAL COLUMN (FMA9140) ──────────
    "FJ3154": ("skeleton_spine_thoracic", "skeleton"),
    "FJ3155": ("skeleton_spine_thoracic", "skeleton"),
    "FJ3156": ("skeleton_spine_thoracic", "skeleton"),
    "FJ3158": ("skeleton_spine_thoracic", "skeleton"),
    "FJ3160": ("skeleton_spine_thoracic", "skeleton"),
    "FJ3163": ("skeleton_spine_thoracic", "skeleton"),
    "FJ3166": ("skeleton_spine_thoracic", "skeleton"),
    "FJ3169": ("skeleton_spine_thoracic", "skeleton"),
    "FJ3171": ("skeleton_spine_thoracic", "skeleton"),
    "FJ3173": ("skeleton_spine_thoracic", "skeleton"),

    # ─── CERVICAL VERTEBRAL COLUMN (FMA24138) ─────────
    "FJ3161": ("skeleton_spine_cervical", "skeleton"),
    "FJ3164": ("skeleton_spine_cervical", "skeleton"),
    "FJ3167": ("skeleton_spine_cervical", "skeleton"),
    "FJ3170": ("skeleton_spine_cervical", "skeleton"),
    "FJ3172": ("skeleton_spine_cervical", "skeleton"),

    # ─── LUMBAR VERTEBRAL COLUMN (FMA16203) ───────────
    "FJ3157": ("skeleton_spine_lumbar", "skeleton"),
    "FJ3159": ("skeleton_spine_lumbar", "skeleton"),
    "FJ3162": ("skeleton_spine_lumbar", "skeleton"),
    "FJ3165": ("skeleton_spine_lumbar", "skeleton"),
    "FJ3168": ("skeleton_spine_lumbar", "skeleton"),

    # ─── SACRUM (FMA16202) ────────────────────────────
    "FJ3393": ("skeleton_sacrum", "skeleton"),

    # ─── RIB CAGE (FMA7480) ───────────────────────────
    "FJ3153": ("skeleton_ribcage", "skeleton"),
    "FJ3178": ("skeleton_ribcage", "skeleton"),
    "FJ3225": ("skeleton_ribcage", "skeleton"),
    "FJ3226": ("skeleton_ribcage", "skeleton"),
    "FJ3227": ("skeleton_ribcage", "skeleton"),
    "FJ3228": ("skeleton_ribcage", "skeleton"),
    "FJ3229": ("skeleton_ribcage", "skeleton"),
    "FJ3230": ("skeleton_ribcage", "skeleton"),
    "FJ3231": ("skeleton_ribcage", "skeleton"),
    "FJ3232": ("skeleton_ribcage", "skeleton"),
    "FJ3233": ("skeleton_ribcage", "skeleton"),
    "FJ3234": ("skeleton_ribcage", "skeleton"),
    "FJ3235": ("skeleton_ribcage", "skeleton"),
    "FJ3236": ("skeleton_ribcage", "skeleton"),

    # ─── STERNUM (FMA7485) ────────────────────────────
    "FJ3290": ("skeleton_sternum", "skeleton"),

    # ─── PELVIS (FMA9578) ─────────────────────────────
    "FJ2815": ("skeleton_pelvis", "skeleton"),

    # ─── RIGHT FEMUR (FMA24474) ───────────────────────
    "FJ3365": ("skeleton_femur_right", "skeleton"),
    # ─── LEFT FEMUR (FMA24475) ────────────────────────
    "FJ3259": ("skeleton_femur_left", "skeleton"),

    # ─── RIGHT TIBIA (FMA24477) ───────────────────────
    "FJ3387": ("skeleton_tibia_right", "skeleton"),
    # ─── LEFT TIBIA (FMA24478) ────────────────────────
    "FJ3282": ("skeleton_tibia_left", "skeleton"),

    # ─── RIGHT FIBULA (FMA24480) ──────────────────────
    "FJ3366": ("skeleton_fibula_right", "skeleton"),
    # ─── LEFT FIBULA (FMA24481) ───────────────────────
    "FJ3260": ("skeleton_fibula_left", "skeleton"),

    # ─── RIGHT HUMERUS (FMA23130) ─────────────────────
    "FJ3368": ("skeleton_humerus_right", "skeleton"),
    # ─── LEFT HUMERUS (FMA23131) ──────────────────────
    "FJ3262": ("skeleton_humerus_left", "skeleton"),

    # ─── RIGHT RADIUS (FMA23464) ──────────────────────
    "FJ3349": ("skeleton_radius_right", "skeleton"),
    # ─── LEFT RADIUS (FMA23465) ───────────────────────
    "FJ3277": ("skeleton_radius_left", "skeleton"),

    # ─── RIGHT ULNA (FMA23467) ────────────────────────
    "FJ3391": ("skeleton_ulna_right", "skeleton"),
    # ─── LEFT ULNA (FMA23468) ─────────────────────────
    "FJ3286": ("skeleton_ulna_left", "skeleton"),

    # ─── RIGHT SCAPULA (FMA13395) ─────────────────────
    "FJ3384": ("skeleton_scapula_right", "skeleton"),
    # ─── LEFT SCAPULA (FMA13396) ──────────────────────
    "FJ3279": ("skeleton_scapula_left", "skeleton"),

    # ─── RIGHT CLAVICLE (FMA13322) ────────────────────
    "FJ3362": ("skeleton_clavicle_right", "skeleton"),
    # ─── LEFT CLAVICLE (FMA13323) ─────────────────────
    "FJ3237": ("skeleton_clavicle_left", "skeleton"),

    # ─── RIGHT PATELLA (FMA24486) ─────────────────────
    "FJ3381": ("skeleton_patella_right", "skeleton"),
    # ─── LEFT PATELLA (FMA24487) ──────────────────────
    "FJ3275": ("skeleton_patella_left", "skeleton"),

    # ─── MUSCLES (mapped from M-suffix and specific IDs) ──
    # Pectoralis major (right + left mirror)
    "FJ1446":  ("muscle_pectoralis_major_right", "muscle"),
    "FJ1446M": ("muscle_pectoralis_major_left", "muscle"),
    "FJ1464":  ("muscle_pectoralis_major_right", "muscle"),
    "FJ1464M": ("muscle_pectoralis_major_left", "muscle"),
    # Pectoralis minor
    "FJ1456":  ("muscle_pectoralis_minor_right", "muscle"),
    "FJ1456M": ("muscle_pectoralis_minor_left", "muscle"),
    # External oblique
    "FJ1452":  ("muscle_external_oblique_right", "muscle"),
    "FJ1452M": ("muscle_external_oblique_left", "muscle"),
    # Serratus anterior
    "FJ1459":  ("muscle_serratus_anterior_right", "muscle"),
    "FJ1459M": ("muscle_serratus_anterior_left", "muscle"),
    # Psoas major
    "FJ1431":  ("muscle_psoas_major_right", "muscle"),
    "FJ1431M": ("muscle_psoas_major_left", "muscle"),
    # Piriformis
    "FJ1428":  ("muscle_piriformis_right", "muscle"),
    "FJ1428M": ("muscle_piriformis_left", "muscle"),
    # Obturator internus
    "FJ1426":  ("muscle_obturator_internus_right", "muscle"),
    "FJ1426M": ("muscle_obturator_internus_left", "muscle"),
    # Subclavius
    "FJ1460":  ("muscle_subclavius_right", "muscle"),
    "FJ1460M": ("muscle_subclavius_left", "muscle"),
    # Transversus thoracis
    "FJ1461":  ("muscle_transversus_thoracis_right", "muscle"),
    "FJ1461M": ("muscle_transversus_thoracis_left", "muscle"),
    # Levator scapulae
    "FJ1532":  ("muscle_levator_scapulae_right", "muscle"),
    # Anal sphincter
    "FJ1450":  ("muscle_anal_sphincter", "muscle"),
    "FJ1450M": ("muscle_anal_sphincter", "muscle"),
    # Iliotibial tract (fascia, classify as muscle layer)
    "FJ1423":  ("muscle_iliotibial_tract_right", "muscle"),
    "FJ1423M": ("muscle_iliotibial_tract_left", "muscle"),
    # Arm muscles
    "FJ1485":  ("muscle_anconeus_right", "muscle"),
    "FJ1485M": ("muscle_anconeus_left", "muscle"),
    "FJ1486M": ("muscle_brachialis_left", "muscle"),
    "FJ1488M": ("muscle_coracobrachialis_left", "muscle"),
    # Flexor retinaculum
    "FJ1471":  ("muscle_flexor_retinaculum_right", "muscle"),
    "FJ1471M": ("muscle_flexor_retinaculum_left", "muscle"),
}

# Keywords in anatomical concept names → layer classification
# Used for FJ IDs not in the direct map (parsed from element_parts.txt)
CONCEPT_LAYER_RULES = [
    # Skin — check first (most specific)
    (r"\bskin\b", "skin"),
    (r"\bintegument", "skin"),

    # Skeleton
    (r"\bskull\b", "skeleton"),
    (r"\bcranium\b", "skeleton"),
    (r"\bmandible\b", "skeleton"),
    (r"\bvertebr", "skeleton"),
    (r"\bsacr", "skeleton"),
    (r"\bcoccyx\b", "skeleton"),
    (r"\brib\b", "skeleton"),
    (r"\bsternum\b", "skeleton"),
    (r"\bclavicle\b", "skeleton"),
    (r"\bscapula\b", "skeleton"),
    (r"\bhumerus\b", "skeleton"),
    (r"\bradius\b", "skeleton"),
    (r"\bulna\b", "skeleton"),
    (r"\bfemur\b", "skeleton"),
    (r"\bpatella\b", "skeleton"),
    (r"\btibia\b", "skeleton"),
    (r"\bfibula\b", "skeleton"),
    (r"\bcalcaneus\b", "skeleton"),
    (r"\bphalanx\b", "skeleton"),
    (r"\bphalang", "skeleton"),
    (r"\bcarpal\b", "skeleton"),
    (r"\btarsal\b", "skeleton"),
    (r"\bbone\b", "skeleton"),
    (r"\bskeletal\b", "skeleton"),
    (r"\bskeleton\b", "skeleton"),
    (r"\bhyoid\b", "skeleton"),
    (r"\bcartilage\b", "skeleton"),
    (r"\btooth\b", "skeleton"),
    (r"\bteeth\b", "skeleton"),

    # Muscle
    (r"\bmuscle\b", "muscle"),
    (r"\bmuscular\b", "muscle"),
    (r"\bpectoralis\b", "muscle"),
    (r"\bdeltoid\b", "muscle"),
    (r"\bbiceps\b", "muscle"),
    (r"\btriceps\b", "muscle"),
    (r"\brectus\b", "muscle"),
    (r"\boblique\b", "muscle"),
    (r"\bgluteus\b", "muscle"),
    (r"\btrapezius\b", "muscle"),
    (r"\blatissimus\b", "muscle"),
    (r"\bdiaphragm\b", "muscle"),
    (r"\btendon\b", "muscle"),
    (r"\bligament\b", "muscle"),
    (r"\bfascia\b", "muscle"),
    (r"\bretinaculum\b", "muscle"),
    (r"\bsphincter\b", "muscle"),

    # Organs — catch-all for viscera, nervous, vascular
    (r"\bheart\b", "organs"),
    (r"\bventricle\b", "organs"),
    (r"\batrium\b", "organs"),
    (r"\baort", "organs"),
    (r"\bartery\b", "organs"),
    (r"\bvein\b", "organs"),
    (r"\blung\b", "organs"),
    (r"\bbronch", "organs"),
    (r"\btrachea\b", "organs"),
    (r"\bliver\b", "organs"),
    (r"\bstomach\b", "organs"),
    (r"\bpancreas\b", "organs"),
    (r"\bkidney\b", "organs"),
    (r"\bbladder\b", "organs"),
    (r"\bintestin", "organs"),
    (r"\bcolon\b", "organs"),
    (r"\brectum\b", "organs"),
    (r"\bappendix\b", "organs"),
    (r"\besophagus\b", "organs"),
    (r"\bgallbladder\b", "organs"),
    (r"\bbrain\b", "organs"),
    (r"\bcerebr", "organs"),
    (r"\bcerebellum\b", "organs"),
    (r"\bspinal cord\b", "organs"),
    (r"\bnerve\b", "organs"),
    (r"\bneural\b", "organs"),
    (r"\bprostate\b", "organs"),
    (r"\buterus\b", "organs"),
    (r"\bovary\b", "organs"),
    (r"\badrenal\b", "organs"),
    (r"\bthyroid\b", "organs"),
    (r"\beye\b", "organs"),
    (r"\beyeball\b", "organs"),
    (r"\bearli", "organs"),
    (r"\bcochlea\b", "organs"),
    (r"\blymph\b", "organs"),
    (r"\btonsil\b", "organs"),
    (r"\btongue\b", "organs"),
]

# Name patterns → our naming convention (for element_parts-derived names)
CONCEPT_NAME_MAP = [
    # Specific before general (order matters!)
    (r"\bleft lung\b", "organ_lung_left"),
    (r"\bright lung\b", "organ_lung_right"),
    (r"\bleft kidney\b", "organ_kidney_left"),
    (r"\bright kidney\b", "organ_kidney_right"),
    (r"\bleft adrenal\b", "organ_adrenal_left"),
    (r"\bright adrenal\b", "organ_adrenal_right"),
    (r"\bleft eyeball\b", "organ_eye_left"),
    (r"\bright eyeball\b", "organ_eye_right"),
    (r"\bleft femur\b", "skeleton_femur_left"),
    (r"\bright femur\b", "skeleton_femur_right"),
    (r"\bleft tibia\b", "skeleton_tibia_left"),
    (r"\bright tibia\b", "skeleton_tibia_right"),
    (r"\bleft fibula\b", "skeleton_fibula_left"),
    (r"\bright fibula\b", "skeleton_fibula_right"),
    (r"\bleft humerus\b", "skeleton_humerus_left"),
    (r"\bright humerus\b", "skeleton_humerus_right"),
    (r"\bleft radius\b", "skeleton_radius_left"),
    (r"\bright radius\b", "skeleton_radius_right"),
    (r"\bleft ulna\b", "skeleton_ulna_left"),
    (r"\bright ulna\b", "skeleton_ulna_right"),
    (r"\bleft scapula\b", "skeleton_scapula_left"),
    (r"\bright scapula\b", "skeleton_scapula_right"),
    (r"\bleft clavicle\b", "skeleton_clavicle_left"),
    (r"\bright clavicle\b", "skeleton_clavicle_right"),
    (r"\bleft patella\b", "skeleton_patella_left"),
    (r"\bright patella\b", "skeleton_patella_right"),
    # General organs
    (r"\bheart\b", "organ_heart"),
    (r"\bliver\b", "organ_liver"),
    (r"\bstomach\b", "organ_stomach"),
    (r"\bpancreas\b", "organ_pancreas"),
    (r"\besophagus\b", "organ_esophagus"),
    (r"\btrachea\b", "organ_trachea"),
    (r"\bgallbladder\b", "organ_gallbladder"),
    (r"\burinary bladder\b", "organ_bladder"),
    (r"\bprostate\b", "organ_prostate"),
    (r"\bbrain\b", "organ_brain"),
    (r"\bcerebellum\b", "organ_cerebellum"),
    (r"\bspinal cord\b", "organ_spinal_cord"),
    (r"\bsmall intestine\b", "organ_small_intestine"),
    (r"\blarge intestine\b", "organ_large_intestine"),
    (r"\bascending colon\b", "organ_large_intestine"),
    (r"\btransverse colon\b", "organ_large_intestine"),
    (r"\bdescending colon\b", "organ_large_intestine"),
    (r"\bcecum\b", "organ_large_intestine"),
    (r"\brectum\b", "organ_large_intestine"),
    (r"\bappendix\b", "organ_appendix"),
    (r"\baorta\b", "organ_aorta"),
    (r"\bskin\b", "skin_body"),
    # General skeleton
    (r"\bskull\b", "skeleton_skull"),
    (r"\brib cage\b", "skeleton_ribcage"),
    (r"\bsternum\b", "skeleton_sternum"),
    (r"\bsacrum\b", "skeleton_sacrum"),
    (r"\bpelvis\b", "skeleton_pelvis"),
    (r"\bthoracic vertebral\b", "skeleton_spine_thoracic"),
    (r"\bcervical vertebral\b", "skeleton_spine_cervical"),
    (r"\blumbar vertebral\b", "skeleton_spine_lumbar"),
]

# Mesh name patterns → layer assignment (for generic/Z-Anatomy files)
LAYER_PATTERNS = {
    "skin": [
        r"skin", r"dermis", r"epidermis", r"integument",
        r"body_surface", r"surface", r"outer",
    ],
    "muscle": [
        r"muscle", r"muscl", r"musc\b", r"bicep", r"tricep",
        r"deltoid", r"pectoral", r"abdominal", r"rectus",
        r"oblique", r"gluteus", r"quadricep", r"hamstring",
        r"gastrocnemius", r"soleus", r"trapezius", r"latissimus",
        r"tendon", r"ligament", r"fascia", r"diaphragm_muscle",
    ],
    "skeleton": [
        r"bone", r"skeleton", r"skeletal", r"skelet",
        r"skull", r"cranium", r"mandible", r"maxilla",
        r"vertebr", r"spine", r"spinal", r"cervical",
        r"thoracic", r"lumbar", r"sacr", r"coccyx",
        r"rib\b", r"sternum", r"clavicle", r"scapula",
        r"humerus", r"radius\b", r"ulna", r"carpal",
        r"metacarpal", r"phalanx", r"phalang",
        r"pelvis", r"ilium", r"ischium", r"pubis",
        r"femur", r"patella", r"tibia", r"fibula",
        r"tarsal", r"metatarsal", r"calcaneus",
        r"tooth", r"teeth", r"dental",
        r"cartilage", r"hyoid",
    ],
    "organs": [
        r"organ", r"heart", r"cardiac", r"ventricle", r"atrium", r"atria",
        r"aorta", r"artery", r"arter", r"vein", r"venous", r"vascular",
        r"lung", r"pulmon", r"bronch", r"trachea", r"larynx", r"pharynx",
        r"liver", r"hepat", r"gallbladder", r"bile",
        r"stomach", r"gastric", r"esophag", r"oesophag",
        r"intestin", r"colon", r"rectum", r"cecum", r"appendix",
        r"duodenum", r"jejunum", r"ileum",
        r"kidney", r"renal", r"ureter", r"bladder", r"urethra",
        r"spleen", r"splenic",
        r"pancrea",
        r"adrenal", r"thyroid", r"thymus", r"pituitary", r"pineal",
        r"brain", r"cerebr", r"cerebellum", r"brainstem",
        r"hippocampus", r"thalamus", r"hypothalamus",
        r"eye\b", r"ocular", r"retina", r"lens\b",
        r"ear\b", r"cochlea", r"tympan",
        r"tongue", r"salivary", r"tonsil",
        r"lymph", r"node",
        r"nerve", r"neural", r"spinal_cord",
        r"uterus", r"uterine", r"ovary", r"ovaries", r"fallopian",
        r"vagina", r"cervix",
        r"prostate", r"prostatic", r"testicl", r"testes",
        r"seminal", r"epididymis", r"scrotum",
        r"breast", r"mammary",
        r"penis", r"glans",
    ],
}

# Mesh name → our naming convention (for generic/Z-Anatomy)
ORGAN_RENAME_MAP = {
    r"heart|cardiac|coeur": "organ_heart",
    r"left.*lung|poumon.*gauche": "organ_lung_left",
    r"right.*lung|poumon.*droit": "organ_lung_right",
    r"lung|poumon": "organ_lungs",
    r"trachea|trach": "organ_trachea",
    r"liver|foie|hepat": "organ_liver",
    r"stomach|estomac|gastric": "organ_stomach",
    r"gallbladder|vesicule": "organ_gallbladder",
    r"pancrea": "organ_pancreas",
    r"spleen|rate": "organ_spleen",
    r"small.*intestin|intestin.*grele": "organ_small_intestine",
    r"large.*intestin|colon|gros.*intestin": "organ_large_intestine",
    r"appendix": "organ_appendix",
    r"esophag|oesophag": "organ_esophagus",
    r"left.*kidney|rein.*gauche": "organ_kidney_left",
    r"right.*kidney|rein.*droit": "organ_kidney_right",
    r"kidney|rein": "organ_kidneys",
    r"bladder|vessie": "organ_bladder",
    r"brain|cerveau|encephale": "organ_brain",
    r"cerebellum": "organ_cerebellum",
    r"brainstem": "organ_brainstem",
    r"thyroid|thyroide": "organ_thyroid",
    r"adrenal|surrenal": "organ_adrenal",
    r"pituitary|hypophyse": "organ_pituitary",
    r"uterus|uterine": "organ_uterus",
    r"ovary|ovaries|ovaire": "organ_ovaries",
    r"fallopian": "organ_fallopian_tubes",
    r"prostate|prostatic": "organ_prostate",
    r"testicl|testes": "organ_testes",
    r"skull|crane|cranium": "skeleton_skull",
    r"spine|colonne|vertebr": "skeleton_spine",
    r"rib|cote\b": "skeleton_ribcage",
    r"pelvis|bassin": "skeleton_pelvis",
    r"femur": "skeleton_femur",
    r"tibia": "skeleton_tibia",
    r"humerus": "skeleton_humerus",
    r"scapula": "skeleton_scapula",
    r"clavicle": "skeleton_clavicle",
    r"sternum": "skeleton_sternum",
}

# Female-only organs (exclude from male model)
FEMALE_ONLY = {"organ_uterus", "organ_ovaries", "organ_fallopian_tubes"}

# Male-only organs (exclude from female model)
MALE_ONLY = {"organ_prostate", "organ_testes"}


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def log(msg):
    """Print with prefix for visibility in Blender output."""
    print(f"[MedPrep] {msg}")


def parse_args():
    """Parse arguments after '--' separator."""
    args = {
        "source": None,
        "gender": "male",
        "output": None,
        "quality": 7,
        "mapping": None,
    }

    argv = sys.argv
    if "--" in argv:
        custom_args = argv[argv.index("--") + 1:]
    else:
        custom_args = []

    i = 0
    while i < len(custom_args):
        if custom_args[i] == "--source" and i + 1 < len(custom_args):
            args["source"] = custom_args[i + 1]
            i += 2
        elif custom_args[i] == "--gender" and i + 1 < len(custom_args):
            args["gender"] = custom_args[i + 1].lower()
            i += 2
        elif custom_args[i] == "--output" and i + 1 < len(custom_args):
            args["output"] = custom_args[i + 1]
            i += 2
        elif custom_args[i] == "--quality" and i + 1 < len(custom_args):
            args["quality"] = int(custom_args[i + 1])
            i += 2
        elif custom_args[i] == "--mapping" and i + 1 < len(custom_args):
            args["mapping"] = custom_args[i + 1]
            i += 2
        else:
            i += 1

    return args


def clear_scene():
    """Remove all objects from the Blender scene."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def classify_mesh(name):
    """Determine which layer a mesh belongs to based on its name."""
    name_lower = name.lower().replace(" ", "_").replace("-", "_")

    for layer, patterns in LAYER_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, name_lower):
                return layer

    return None


def rename_mesh(name):
    """Rename a mesh to our convention if it matches a known organ."""
    name_lower = name.lower().replace(" ", "_").replace("-", "_")

    for pattern, new_name in ORGAN_RENAME_MAP.items():
        if re.search(pattern, name_lower):
            return new_name

    return None


def should_include_organ(target_name, gender):
    """Check if an organ should be included based on gender."""
    if gender == "male" and target_name in FEMALE_ONLY:
        return False
    if gender == "female" and target_name in MALE_ONLY:
        return False
    return True


# ═══════════════════════════════════════════════════════════
#  BODYPARTS3D PROCESSING
# ═══════════════════════════════════════════════════════════

def load_element_parts_mapping(mapping_path):
    """
    Parse partof_element_parts.txt to build FJ→(name, layer) mapping.

    File format (tab-separated):
        concept_id    name    element_file_id
        FMA7088       heart   FJ2417

    One FJ ID can map to multiple concepts (it belongs to multiple
    anatomical hierarchies). We pick the most specific useful one.
    """
    fj_map = {}  # FJ_ID → (target_name, layer)
    fj_concepts = defaultdict(list)  # FJ_ID → [(name, fma_id), ...]

    log(f"Loading element parts mapping from: {mapping_path}")

    with open(mapping_path, "r", encoding="utf-8") as f:
        header = f.readline()  # skip header
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 3:
                continue
            fma_id, name, fj_id = parts[0].strip(), parts[1].strip(), parts[2].strip()
            fj_concepts[fj_id].append((name.lower(), fma_id))

    log(f"  Loaded {len(fj_concepts)} unique FJ IDs from mapping file")

    # For each FJ ID, determine best target name and layer
    for fj_id, concepts in fj_concepts.items():
        # Skip if already in direct map
        if fj_id in FJ_DIRECT_MAP:
            continue

        # Try to find a matching concept name
        target_name = None
        layer = None

        # First pass: match against our concept name rules (most specific)
        for concept_name, _ in concepts:
            for pattern, mapped_name in CONCEPT_NAME_MAP:
                if re.search(pattern, concept_name):
                    target_name = mapped_name
                    break
            if target_name:
                break

        # Second pass: determine layer from concept names
        if not layer:
            for concept_name, _ in concepts:
                for pattern, found_layer in CONCEPT_LAYER_RULES:
                    if re.search(pattern, concept_name):
                        layer = found_layer
                        break
                if layer:
                    break

        # If we found a layer but no specific name, use a generic name
        if layer and not target_name:
            # Use the shortest concept name as a generic identifier
            shortest = min(concepts, key=lambda x: len(x[0]))
            safe_name = shortest[0].replace(" ", "_").replace("-", "_")
            safe_name = re.sub(r"[^a-z0-9_]", "", safe_name)
            if layer == "organs":
                target_name = f"organ_{safe_name}"
            elif layer == "skeleton":
                target_name = f"skeleton_{safe_name}"
            elif layer == "muscle":
                target_name = f"muscle_{safe_name}"
            elif layer == "skin":
                target_name = f"skin_{safe_name}"

        if target_name and layer:
            fj_map[fj_id] = (target_name, layer)

    log(f"  Resolved {len(fj_map)} additional FJ IDs from mapping file")
    return fj_map


def detect_bodyparts3d(source_dir):
    """Check if a directory contains BodyParts3D FJ-named OBJ files."""
    fj_count = 0
    for f in Path(source_dir).iterdir():
        if f.suffix.lower() == ".obj" and f.stem.startswith("FJ"):
            fj_count += 1
    return fj_count > 50  # Threshold: more than 50 FJ files = BodyParts3D


def process_bodyparts3d(source_dir, gender, mapping_path=None):
    """
    Process a BodyParts3D directory of FJ*.obj files.

    1. Build FJ→(target_name, layer) mapping from direct map + element_parts
    2. Import each OBJ file
    3. Assign to layer and rename
    4. Return layers dict
    """
    log("Processing BodyParts3D format...")
    log(f"  Source directory: {source_dir}")

    # Build complete FJ mapping
    fj_map = dict(FJ_DIRECT_MAP)  # Start with hard-coded mappings

    if mapping_path and Path(mapping_path).exists():
        extra = load_element_parts_mapping(mapping_path)
        # Only add entries not already in direct map
        for fj_id, value in extra.items():
            if fj_id not in fj_map:
                fj_map[fj_id] = value
    else:
        log("  WARNING: No mapping file provided — using direct map only")
        log("  (Pass --mapping partof_element_parts.txt for full coverage)")

    # Collect OBJ files
    obj_files = sorted([
        f for f in Path(source_dir).iterdir()
        if f.suffix.lower() == ".obj" and f.stem.startswith("FJ")
    ])
    log(f"  Found {len(obj_files)} FJ*.obj files")

    # Classify each file
    layers = {"skin": [], "muscle": [], "skeleton": [], "organs": []}
    target_groups = defaultdict(list)  # target_name → [filepath, ...]
    unmatched = []

    for obj_file in obj_files:
        fj_id = obj_file.stem  # e.g., "FJ2417" or "FJ1446M"

        if fj_id in fj_map:
            target_name, layer = fj_map[fj_id]

            # Gender filter
            if not should_include_organ(target_name, gender):
                continue

            target_groups[(target_name, layer)].append(str(obj_file))
        else:
            unmatched.append(fj_id)

    # Report
    log(f"  Classified into {len(target_groups)} named groups")
    if unmatched:
        log(f"  WARNING: {len(unmatched)} FJ IDs not in mapping:")
        for fj_id in unmatched[:15]:
            log(f"    - {fj_id}")
        if len(unmatched) > 15:
            log(f"    ... and {len(unmatched) - 15} more")

    # Import and group
    for (target_name, layer), filepaths in sorted(target_groups.items()):
        log(f"  Importing {target_name} ({len(filepaths)} meshes)...")

        imported_objs = []
        for filepath in filepaths:
            # Track objects before import
            before = set(obj.name for obj in bpy.context.scene.objects)
            bpy.ops.wm.obj_import(filepath=filepath)
            after = set(obj.name for obj in bpy.context.scene.objects)

            new_names = after - before
            for name in new_names:
                obj = bpy.context.scene.objects.get(name)
                if obj and obj.type == "MESH":
                    imported_objs.append(obj)

        # If multiple meshes for the same organ, join them
        if len(imported_objs) > 1:
            # Deselect all
            bpy.ops.object.select_all(action="DESELECT")

            # Select all parts of this organ
            for obj in imported_objs:
                obj.select_set(True)

            # Make first one active and join
            bpy.context.view_layer.objects.active = imported_objs[0]
            bpy.ops.object.join()

            # The joined result is the active object
            joined = bpy.context.view_layer.objects.active
            joined.name = target_name
            layers[layer].append(joined)
        elif len(imported_objs) == 1:
            imported_objs[0].name = target_name
            layers[layer].append(imported_objs[0])

    # Report layer counts
    for layer_name, objs in layers.items():
        log(f"  layer_{layer_name}: {len(objs)} named groups")

    return layers


# ═══════════════════════════════════════════════════════════
#  GENERIC / Z-ANATOMY PROCESSING
# ═══════════════════════════════════════════════════════════

def import_file(filepath):
    """Import a model file into Blender based on extension."""
    ext = Path(filepath).suffix.lower()
    log(f"Importing {ext} file: {filepath}")

    if ext == ".blend":
        with bpy.data.libraries.load(filepath) as (data_from, data_to):
            data_to.objects = data_from.objects
        for obj in data_to.objects:
            if obj is not None:
                bpy.context.collection.objects.link(obj)

    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=filepath)

    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=filepath)

    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)

    elif ext in (".gltf", ".glb"):
        bpy.ops.import_scene.gltf(filepath=filepath)

    else:
        log(f"WARNING: Unsupported format {ext}")
        return False

    log(f"Imported {len(bpy.context.scene.objects)} objects total")
    return True


def import_directory(dirpath):
    """Import all supported model files from a directory."""
    supported = {".obj", ".stl", ".fbx", ".gltf", ".glb"}
    imported = 0

    for f in sorted(Path(dirpath).iterdir()):
        if f.suffix.lower() in supported:
            if import_file(str(f)):
                imported += 1

    log(f"Imported {imported} files from directory")
    return imported > 0


def process_z_anatomy(gender):
    """Process a Z-Anatomy .blend file."""
    log("Processing Z-Anatomy format...")

    collections_found = False
    for collection in bpy.data.collections:
        cname = collection.name.lower()
        if any(kw in cname for kw in ["skeleton", "muscle", "organ", "skin",
                                       "squelette", "muscl", "organe", "peau"]):
            collections_found = True
            break

    if collections_found:
        log("Found Z-Anatomy collections — using collection-based grouping")
        return process_by_collections(gender)
    else:
        log("No collections found — falling back to name-based grouping")
        return process_by_names(gender)


def process_by_collections(gender):
    """Group meshes using Blender collection hierarchy."""
    layers = {"skin": [], "muscle": [], "skeleton": [], "organs": []}

    for collection in bpy.data.collections:
        cname = collection.name.lower()

        layer = None
        if any(kw in cname for kw in ["skin", "peau", "integument", "surface"]):
            layer = "skin"
        elif any(kw in cname for kw in ["muscle", "muscl", "musc", "tendon"]):
            layer = "muscle"
        elif any(kw in cname for kw in ["skeleton", "squelette", "bone", "os ",
                                         "skeletal", "cartilage"]):
            layer = "skeleton"
        elif any(kw in cname for kw in ["organ", "organe", "viscera", "viscere",
                                         "nervous", "nerveux", "vascular",
                                         "vasculaire", "digestif", "respirat",
                                         "urinair", "endocrin"]):
            layer = "organs"

        if layer:
            for obj in collection.objects:
                if obj.type == "MESH":
                    target = rename_mesh(obj.name)
                    if target and not should_include_organ(target, gender):
                        continue
                    layers[layer].append(obj)

    assigned = set()
    for layer_objs in layers.values():
        for obj in layer_objs:
            assigned.add(obj.name)

    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.name not in assigned:
            layer = classify_mesh(obj.name)
            target = rename_mesh(obj.name)
            if target and not should_include_organ(target, gender):
                continue
            if layer:
                layers[layer].append(obj)

    return layers


def process_by_names(gender):
    """Group meshes by analyzing their names against pattern dictionaries."""
    layers = {"skin": [], "muscle": [], "skeleton": [], "organs": []}
    unclassified = []

    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue

        target = rename_mesh(obj.name)
        if target and not should_include_organ(target, gender):
            continue

        layer = classify_mesh(obj.name)
        if layer:
            layers[layer].append(obj)
        else:
            unclassified.append(obj)

    if unclassified:
        log(f"WARNING: {len(unclassified)} meshes couldn't be classified:")
        for obj in unclassified[:20]:
            log(f"  - {obj.name}")
        if len(unclassified) > 20:
            log(f"  ... and {len(unclassified) - 20} more")
        for obj in unclassified:
            layers["organs"].append(obj)

    return layers


# ═══════════════════════════════════════════════════════════
#  BUILD OUTPUT
# ═══════════════════════════════════════════════════════════

def build_output(layers, gender):
    """Create the final scene structure with named layer groups."""
    log("Building output scene...")

    # For BodyParts3D mode, objects are already named — just need hierarchy
    # For generic mode, we rename during build

    root = bpy.data.objects.new("Root", None)
    bpy.context.collection.objects.link(root)

    total_meshes = 0

    for layer_name in ["skin", "muscle", "skeleton", "organs"]:
        layer_empty = bpy.data.objects.new(f"layer_{layer_name}", None)
        bpy.context.collection.objects.link(layer_empty)
        layer_empty.parent = root

        objs = layers.get(layer_name, [])
        log(f"  layer_{layer_name}: {len(objs)} meshes")

        for obj in objs:
            if obj.name not in bpy.context.scene.objects:
                bpy.context.collection.objects.link(obj)

            # For generic mode, try to rename
            if not obj.name.startswith(("organ_", "skeleton_", "muscle_", "skin_")):
                new_name = rename_mesh(obj.name)
                if new_name:
                    obj.name = new_name

            obj.parent = layer_empty
            total_meshes += 1

    log(f"Total meshes in output: {total_meshes}")
    return total_meshes


def optimize_meshes():
    """Reduce polygon count for web delivery."""
    log("Optimizing meshes for web...")

    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue

        vertex_count = len(obj.data.vertices)
        if vertex_count > 50000:
            ratio = min(10000 / vertex_count, 0.8)
            log(f"  Decimating {obj.name}: {vertex_count} -> ~{int(vertex_count * ratio)} verts")

            bpy.context.view_layer.objects.active = obj
            modifier = obj.modifiers.new("Decimate", "DECIMATE")
            modifier.ratio = ratio
            bpy.ops.object.modifier_apply(modifier="Decimate")


def export_glb(output_path, quality=7):
    """Export scene as Draco-compressed GLB."""
    log(f"Exporting to {output_path} (Draco quality: {quality})...")

    bpy.ops.object.select_all(action="SELECT")

    export_settings = {
        "filepath": str(output_path),
        "export_format": "GLB",
        "use_selection": False,
        "export_apply": True,
        "export_draco_mesh_compression_enable": True,
        "export_draco_mesh_compression_level": quality,
        "export_draco_position_quantization": 14,
        "export_draco_normal_quantization": 10,
        "export_draco_texcoord_quantization": 12,
        "export_materials": "EXPORT",
        "export_yup": True,
    }

    # Blender 5.0+ renamed export_colors to export_vertex_color
    blender_version = bpy.app.version
    if blender_version >= (5, 0, 0):
        export_settings["export_vertex_color"] = "MATERIAL"
    elif blender_version >= (4, 0, 0):
        export_settings["export_colors"] = True

    bpy.ops.export_scene.gltf(**export_settings)

    file_size = Path(output_path).stat().st_size / (1024 * 1024)
    log(f"Exported: {output_path} ({file_size:.1f} MB)")


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main():
    args = parse_args()

    if not args["source"]:
        log("ERROR: --source argument required")
        log("")
        log("Usage (BodyParts3D):")
        log("  blender --background --python prepare_models.py -- \\")
        log("    --source ./bodyparts3d_raw_partof/partof_BP3D_4.0_obj_99 \\")
        log("    --gender male \\")
        log("    --mapping ./partof_element_parts.txt")
        log("")
        log("Usage (Z-Anatomy .blend):")
        log("  blender --background --python prepare_models.py -- \\")
        log("    --source /path/to/z_anatomy.blend --gender male")
        sys.exit(1)

    source = Path(args["source"])
    gender = args["gender"]
    output_dir = Path(args["output"]) if args["output"] else Path(__file__).parent
    quality = args["quality"]
    mapping = args["mapping"]

    log("=" * 60)
    log("Clinical Intelligence Hub — Model Processing Pipeline")
    log("=" * 60)
    log(f"Source:  {source}")
    log(f"Gender:  {gender}")
    log(f"Output:  {output_dir}")
    log(f"Quality: {quality}")
    if mapping:
        log(f"Mapping: {mapping}")
    log("")

    # Clear default scene
    clear_scene()

    # Determine processing mode
    is_bodyparts3d = False

    if source.is_dir():
        is_bodyparts3d = detect_bodyparts3d(str(source))

        if is_bodyparts3d:
            log("Detected BodyParts3D format (FJ-named OBJ files)")

            # Auto-detect mapping file if not specified
            if not mapping:
                # Look in common locations
                candidates = [
                    source.parent / "partof_element_parts.txt",
                    source.parent.parent / "partof_element_parts.txt",
                    Path(__file__).parent / "partof_element_parts.txt",
                ]
                for candidate in candidates:
                    if candidate.exists():
                        mapping = str(candidate)
                        log(f"Auto-detected mapping file: {mapping}")
                        break

            layers = process_bodyparts3d(str(source), gender, mapping)
        else:
            if not import_directory(str(source)):
                log("ERROR: No supported files found in directory")
                sys.exit(1)
            layers = process_by_names(gender)

    elif source.suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(source))
        log(f"Opened .blend file: {len(bpy.context.scene.objects)} objects")
        layers = process_z_anatomy(gender)

    else:
        if not import_file(str(source)):
            log("ERROR: Failed to import source file")
            sys.exit(1)
        layers = process_by_names(gender)

    # Report layer counts
    for layer_name, objs in layers.items():
        log(f"  {layer_name}: {len(objs)} meshes")

    # Build output structure (for non-BodyParts3D, clears scene and rebuilds)
    if not is_bodyparts3d:
        total = build_output(layers, gender)
    else:
        # BodyParts3D already has properly named + joined meshes in scene
        # Just need to add layer hierarchy
        root = bpy.data.objects.new("Root", None)
        bpy.context.collection.objects.link(root)

        total = 0
        for layer_name in ["skin", "muscle", "skeleton", "organs"]:
            layer_empty = bpy.data.objects.new(f"layer_{layer_name}", None)
            bpy.context.collection.objects.link(layer_empty)
            layer_empty.parent = root

            for obj in layers.get(layer_name, []):
                obj.parent = layer_empty
                total += 1

        log(f"Total meshes in output: {total}")

    if total == 0:
        log("ERROR: No meshes in output — check source file naming")
        sys.exit(1)

    # Optimize for web
    optimize_meshes()

    # Export
    output_file = output_dir / f"{gender}_anatomy.glb"
    export_glb(output_file, quality)

    log("")
    log("=" * 60)
    log(f"SUCCESS: {gender}_anatomy.glb ready for Three.js")
    log("=" * 60)
    log("")
    log("Layer structure:")
    log("  Root")
    for layer_name in ["skin", "muscle", "skeleton", "organs"]:
        objs = layers.get(layer_name, [])
        log(f"  └── layer_{layer_name} ({len(objs)} meshes)")
        for obj in objs[:5]:
            log(f"      └── {obj.name}")
        if len(objs) > 5:
            log(f"      └── ... and {len(objs) - 5} more")


if __name__ == "__main__":
    main()
