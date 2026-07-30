#!/usr/bin/env python3
"""
Z-Anatomy → GLB Export Pipeline
================================
Converts Z-Anatomy Blender template into a multi-layered, color-coded GLB
for the MedPrep 3D anatomy viewer (Three.js).

Usage:
    blender --background \
        /path/to/Z-Anatomy/Startup.blend \
        --python export_zanatomy.py -- \
        --output /path/to/output/male_anatomy_full.glb \
        --max-tris 1500000

Output GLB structure:
    Root
    ├── layer_skin          (body surface — from BodyParts3D skin or Regions)
    ├── layer_skeleton      (all bones)
    ├── layer_muscle        (all skeletal muscles, tendons, fascia)
    ├── layer_organs        (visceral organs, glands, GI tract)
    ├── layer_vasculature   (arteries + veins, curve→mesh converted)
    └── layer_nervous       (nerves + sense organs, curve→mesh converted)
"""

import bpy
import bmesh
import sys
import os
import math
from collections import defaultdict

# Force unbuffered stdout so print() shows in real-time
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

# ═══════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════

# Map Z-Anatomy collection names → our layer names
COLLECTION_TO_LAYER = {
    "1: Skeletal system":                    "layer_skeleton",
    "2: Muscular insertions":                "layer_muscle",      # muscle attachment points on bone
    "3: Joints":                             "layer_skeleton",    # ligaments, capsules → skeleton
    "4: Muscular system":                    "layer_muscle",
    "5: Cardiovascular system":              "layer_vasculature",
    "6: Lymphoid organs":                    "layer_organs",      # spleen, thymus, etc.
    "7: Nervous system & Sense organs":      "layer_nervous",
    "8: Visceral systems":                   "layer_organs",
    "9: Regions of human body":              "layer_skin",        # body surface regions
}

# Skip these collections (reference-only, not visual anatomy)
SKIP_COLLECTIONS = {
    "Reference lines, reference planes, movements",
    "Cross section planes",
    # NOTE: "Bonus collection" and "Muscular insertions" both included
    # for maximum anatomical detail (user has powerful local Mac rendering)
}

# Heart-related mesh names → should go to organs layer even though they're
# under Cardiovascular system. Matched case-insensitively.
HEART_ORGAN_KEYWORDS = [
    "heart", "ventricle", "atrium", "aorta", "pulmonary_trunk", "coronary",
    "pericardium", "papillary", "leaflet", "valve", "septum",
]

# Brain-related mesh names → should go to organs layer even though they're
# under Nervous system. Matched case-insensitively.
BRAIN_ORGAN_KEYWORDS = [
    "brain", "cerebr", "cerebel", "hippocampus", "thalamus", "hypothalamus",
    "amygdala", "pons", "medulla_oblongata", "midbrain", "corpus_callosum",
    "frontal_lobe", "parietal_lobe", "temporal_lobe", "occipital_lobe",
    "brainstem", "pineal", "pituitary",
]

# Anatomically-correct material colors (from Z-Anatomy's shader nodes)
# We'll read these from the .blend file directly, but have fallbacks
MATERIAL_COLORS = {
    "Artery":           (0.784, 0.158, 0.158),  # red
    "Vein":             (0.189, 0.172, 0.785),  # blue
    "Pulmonary artery": (0.388, 0.228, 0.785),  # purple
    "Pulmonary vein":   (0.784, 0.234, 0.308),  # pink-red
    "Heart":            (0.800, 0.155, 0.095),  # deep red
    "Brain":            (0.800, 0.279, 0.195),  # salmon
    "Brain-Inner":      (0.898, 0.598, 0.439),  # light salmon
    "Cerebellum":       (0.345, 0.166, 0.089),  # dark brown
    "Bone":             (0.900, 0.880, 0.850),  # off-white bone
    "Cartilage":        (0.696, 0.615, 0.568),  # warm tan
    "Ligament":         (0.797, 0.997, 0.973),  # white-green
    "Tendon":           (0.926, 0.804, 0.801),  # pale pink
    "Fascia":           (0.477, 0.720, 0.800),  # light blue
    "Intestine":        (0.800, 0.261, 0.261),  # pink-red
    "Lung-base":        (0.800, 0.367, 0.337),  # pink
    "Skin":             (0.588, 0.307, 0.190),  # brown
    "Mucosa":           (0.639, 0.191, 0.251),  # dark pink
    "Gland":            (0.800, 0.264, 0.132),  # orange-red
    "Gallbladder":      (0.153, 0.315, 0.076),  # dark green
    "Biliary system":   (0.094, 0.166, 0.050),  # dark green
    "Fat":              (0.648, 0.413, 0.100),  # yellow-brown
    "Peritoneum":       (0.800, 0.345, 0.077),  # orange
    "Nucleus":          (0.499, 0.161, 0.037),  # dark brown
    "Teeth":            (0.758, 0.605, 0.566),  # off-white
    "Articular capsule":(0.561, 0.463, 0.800),  # lavender
    "Bursa":            (0.017, 0.494, 0.614),  # teal
    "LCR":              (0.440, 0.800, 0.737),  # light teal
    "White matter":     (0.513, 0.513, 0.513),  # gray
    "Eye":              (0.519, 0.519, 0.519),  # gray
    "Nail":             (0.854, 0.590, 0.480),  # peach
}

# Default colors per layer (fallback when material has no color)
LAYER_DEFAULT_COLORS = {
    "layer_skeleton":    (0.900, 0.880, 0.850),  # bone white
    "layer_muscle":      (0.690, 0.220, 0.180),  # muscle red
    "layer_organs":      (0.750, 0.300, 0.250),  # organ pink-red
    "layer_vasculature": (0.784, 0.158, 0.158),  # artery red
    "layer_nervous":     (0.850, 0.800, 0.350),  # nerve yellow
    "layer_skin":        (0.720, 0.520, 0.400),  # skin tone
}

# Muscle material names → muscle red color override
MUSCLE_MATERIALS = {
    "Abductor", "Adductor", "Biarticular", "Depressor",
    "Diaphragm", "Elevator", "External rotator", "Flexion",
    "Flexion fingers", "Flexion hand-foot", "Internal rotator",
    "Lateral flexor", "Mastication", "Plantarflexion", "Pronation",
    "Rotator", "Supination", "Trapezius",
}


def parse_args():
    """Parse arguments after Blender's '--' separator."""
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    import argparse
    parser = argparse.ArgumentParser(description="Export Z-Anatomy to GLB")
    parser.add_argument("--output", default="male_anatomy_full.glb",
                        help="Output GLB file path")
    parser.add_argument("--max-tris", type=int, default=4_000_000,
                        help="Target max triangle count (default: 4M, local rendering)")
    parser.add_argument("--gender", default="male", choices=["male", "female"],
                        help="Gender variant to export (filters sex-specific organs)")
    parser.add_argument("--skin-glb", default=None,
                        help="Path to existing GLB with skin mesh to merge")
    return parser.parse_args(argv)


def get_material_color(mat):
    """Extract base color from material's Principled BSDF node."""
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None

    for node in mat.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            bc = node.inputs.get('Base Color')
            if bc and bc.default_value:
                c = bc.default_value[:3]
                # Skip default gray
                if 0.79 < c[0] < 0.81 and 0.79 < c[1] < 0.81 and 0.79 < c[2] < 0.81:
                    return None
                return tuple(c)
    return None


def create_simple_material(name, color):
    """Create a simple material with the given RGB color."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    bsdf = tree.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.7
    bsdf.inputs['Metallic'].default_value = 0.0
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    return mat


def assign_color_to_mesh(obj, layer_name):
    """Ensure mesh has a properly colored material for GLB export."""
    if not obj.data.materials:
        # No material — assign layer default
        color = LAYER_DEFAULT_COLORS.get(layer_name, (0.7, 0.7, 0.7))
        mat = create_simple_material(f"default_{layer_name}", color)
        obj.data.materials.append(mat)
        return

    for i, mat in enumerate(obj.data.materials):
        if not mat:
            continue

        # Check material name against our color map
        base_name = mat.name.split('.')[0]
        node_color = get_material_color(mat)

        if node_color:
            # Material already has a real color from Z-Anatomy nodes
            continue

        # Check if it's a known material type
        if base_name in MATERIAL_COLORS:
            color = MATERIAL_COLORS[base_name]
        elif base_name in MUSCLE_MATERIALS:
            color = (0.690, 0.220, 0.180)  # muscle red
        else:
            color = LAYER_DEFAULT_COLORS.get(layer_name, (0.7, 0.7, 0.7))

        # Update the Principled BSDF node color
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    node.inputs['Base Color'].default_value = (*color, 1.0)
                    break


def convert_curves_to_meshes(objects):
    """Convert curve objects to mesh objects for GLB export.

    Curves are used for blood vessels and nerves in Z-Anatomy.
    They need to be converted to tube meshes for Three.js.
    Uses depsgraph evaluation (works in background mode, unlike bpy.ops).

    Handles stale references: Blender can cascade-delete related objects
    when we remove curves, so every access must be guarded.
    """
    converted = []
    skipped = 0
    depsgraph = bpy.context.evaluated_depsgraph_get()

    # Snapshot curve references with their names (for safe iteration)
    curve_refs = []
    for obj in list(objects):
        try:
            if obj.type == 'CURVE':
                curve_refs.append(obj)
        except ReferenceError:
            continue

    for obj in curve_refs:
        # Guard: check if this object is still alive
        try:
            obj_name = obj.name
            obj_type = obj.type
        except ReferenceError:
            skipped += 1
            continue

        if obj_type != 'CURVE':
            continue

        try:
            curve_data = obj.data

            # If curve has no bevel (zero-width), give it a small tube radius
            if curve_data.bevel_depth == 0 and not curve_data.bevel_object:
                curve_data.bevel_depth = 0.001  # 1mm tube radius
                curve_data.bevel_resolution = 3  # low-poly tube cross-section

            # Evaluate and convert using depsgraph (background-safe)
            depsgraph.update()
            obj_eval = obj.evaluated_get(depsgraph)
            mesh_data = bpy.data.meshes.new_from_object(obj_eval)

            if mesh_data and len(mesh_data.vertices) > 0:
                # Create a NEW mesh object (can't change curve obj type in-place)
                mesh_obj = bpy.data.objects.new(obj_name + "_mesh", mesh_data)
                mesh_obj.matrix_world = obj.matrix_world.copy()

                # Copy materials from original curve
                if curve_data.materials:
                    for mat in curve_data.materials:
                        if mat:
                            mesh_obj.data.materials.append(mat)

                # Link to same collections as original
                for col in list(obj.users_collection):
                    try:
                        col.objects.link(mesh_obj)
                    except Exception:
                        pass

                converted.append(mesh_obj)

                # Unlink and remove original curve
                for col in list(obj.users_collection):
                    try:
                        col.objects.unlink(obj)
                    except Exception:
                        pass
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception:
                    pass
            else:
                skipped += 1
        except ReferenceError:
            skipped += 1
        except Exception as e:
            print(f"  [WARN] Could not convert curve '{obj_name}': {e}")
            skipped += 1

    if skipped:
        print(f"    Skipped {skipped} curves (stale refs or no geometry)")
    print(f"    Converted {len(converted)} curves to meshes")
    return converted


def collect_objects_recursive(collection):
    """Recursively collect all objects from a collection and its children."""
    objects = list(collection.objects)
    for child in collection.children:
        objects.extend(collect_objects_recursive(child))
    return objects


def decimate_mesh(obj, ratio):
    """Apply decimation to reduce triangle count."""
    if ratio >= 1.0:
        return

    mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
    mod.ratio = ratio

    # Apply modifier
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.modifier_apply(modifier="Decimate")
    except Exception:
        # If apply fails, remove the modifier
        obj.modifiers.remove(mod)


def count_tris(obj):
    """Count triangles in a mesh object."""
    if obj.type != 'MESH' or not obj.data:
        return 0
    # Each polygon with N vertices = N-2 triangles
    return sum(max(0, len(p.vertices) - 2) for p in obj.data.polygons)


def make_name_safe(name):
    """Make object name safe for GLB/Three.js (no dots, no special chars)."""
    # Replace .l .r suffixes with _left _right
    name = name.replace('.l', '_left').replace('.r', '_right')
    name = name.replace('.L', '_left').replace('.R', '_right')
    # Replace remaining dots and spaces
    name = name.replace('.', '_').replace(' ', '_')
    # Remove consecutive underscores
    while '__' in name:
        name = name.replace('__', '_')
    return name.strip('_')


# ═══════════════════════════════════════════════════════════
#  MAIN EXPORT
# ═══════════════════════════════════════════════════════════

def main():
    args = parse_args()
    scene = bpy.context.scene

    print("=" * 60)
    print("Z-Anatomy → GLB Export Pipeline")
    print("=" * 60)

    # ── Step 1: Build layer groups ──
    print("\n[1/6] Mapping collections to layers...")

    layer_objects = defaultdict(list)
    skipped_count = 0

    for col in scene.collection.children:
        if col.name in SKIP_COLLECTIONS:
            skipped_count += len(collect_objects_recursive(col))
            print(f"  SKIP: {col.name}")
            continue

        layer_name = COLLECTION_TO_LAYER.get(col.name)
        if not layer_name:
            # For unmapped collections (like Bonus collection), classify by name patterns
            if "Bonus" in col.name or "bonus" in col.name:
                layer_name = None  # Will be classified per-object below
                print(f"  {col.name} → per-object classification (bonus detail)")
            else:
                print(f"  SKIP (unmapped): {col.name}")
                skipped_count += len(collect_objects_recursive(col))
                continue

        objects = collect_objects_recursive(col)
        meshes = [o for o in objects if o.type == 'MESH']
        curves = [o for o in objects if o.type == 'CURVE']

        # Bonus collection: classify by SUB-COLLECTION HIERARCHY, not name keywords
        if layer_name is None:
            # Map Bonus sub-collection names to layers
            BONUS_SUBCOL_MAP = {
                "Skeletal system":          "layer_skeleton",
                "Arthrology":               "layer_skeleton",
                "Muscular system":          "layer_muscle",
                "Muscular insertions":      "layer_muscle",
                "Cardiovascular system":    "layer_vasculature",
                "Nervous system":           "layer_nervous",
                "Visceral systems":         "layer_organs",
                "Regions of human body":    "layer_skin",
            }
            BONUS_SKIP = {"Reference lines, planes & movements'"}

            classified = defaultdict(int)
            # First: classify objects from named sub-collections
            for subcol in col.children:
                subcol_layer = BONUS_SUBCOL_MAP.get(subcol.name)
                if subcol.name in BONUS_SKIP or (not subcol_layer and "reference" in subcol.name.lower()):
                    continue
                if not subcol_layer:
                    # Unknown sub-collection → default to organs
                    subcol_layer = "layer_organs"
                sub_objects = collect_objects_recursive(subcol)
                for obj in sub_objects:
                    layer_objects[subcol_layer].append(obj)
                    classified[subcol_layer] += 1

            # Then: classify any DIRECT objects in Bonus (not in a sub-collection)
            for obj in col.objects:
                # Use name-based fallback for direct objects only
                name_lower = obj.name.lower()
                assigned = False
                bone_kw = ["bone", "vertebr", "rib", "scapul", "clavicl", "femur", "tibia", "fibula", "humer", "radius", "ulna", "phalanx", "skull"]
                muscle_kw = ["muscle", "muscul", "tendon", "fascia", "ligament"]
                vessel_kw = ["artery", "arter", "vein", "venous"]
                nerve_kw = ["nerve", "nerv", "gangli", "plexus"]
                organ_kw = ["liver", "lung", "kidney", "heart", "stomach", "intestin", "brain", "cerebr"]
                for kws, lyr in [(bone_kw, "layer_skeleton"), (muscle_kw, "layer_muscle"), (vessel_kw, "layer_vasculature"), (nerve_kw, "layer_nervous"), (organ_kw, "layer_organs")]:
                    if any(kw in name_lower for kw in kws):
                        layer_objects[lyr].append(obj)
                        classified[lyr] += 1
                        assigned = True
                        break
                if not assigned:
                    layer_objects["layer_organs"].append(obj)
                    classified["layer_organs (default)"] += 1

            for lyr, cnt in sorted(classified.items()):
                print(f"    → {lyr}: {cnt}")
            print(f"  {col.name}: {len(meshes)} meshes, {len(curves)} curves → classified by sub-collection")
            continue

        print(f"  {col.name} → {layer_name} ({len(meshes)} meshes, {len(curves)} curves)")

        # Reclassify heart/brain structures to organs layer
        reclassified = 0
        if layer_name == "layer_vasculature":
            for obj in list(objects):
                name_lower = obj.name.lower()
                if any(kw in name_lower for kw in HEART_ORGAN_KEYWORDS):
                    layer_objects["layer_organs"].append(obj)
                    reclassified += 1
                else:
                    layer_objects[layer_name].append(obj)
            if reclassified:
                print(f"    → Reclassified {reclassified} heart structures to layer_organs")
        elif layer_name == "layer_nervous":
            for obj in list(objects):
                name_lower = obj.name.lower()
                if any(kw in name_lower for kw in BRAIN_ORGAN_KEYWORDS):
                    layer_objects["layer_organs"].append(obj)
                    reclassified += 1
                else:
                    layer_objects[layer_name].append(obj)
            if reclassified:
                print(f"    → Reclassified {reclassified} brain structures to layer_organs")
        else:
            layer_objects[layer_name].extend(objects)

    print(f"  Skipped {skipped_count} objects from excluded collections")

    # ── Step 2: Convert curves to meshes ──
    print("\n[2/6] Converting curves to tube meshes...")

    for layer_name, objects in layer_objects.items():
        curves = []
        for o in objects:
            try:
                if o.type == 'CURVE':
                    curves.append(o)
            except ReferenceError:
                continue
        if curves:
            print(f"  {layer_name}: converting {len(curves)} curves...")
            new_meshes = convert_curves_to_meshes(curves)
            # Add converted mesh objects back into layer_objects
            # (curves list is a copy, so replacements don't propagate)
            layer_objects[layer_name].extend(new_meshes)

    # Helper to filter out deleted Blender objects (stale references from curve conversion)
    def live_objects(objs):
        result = []
        for o in objs:
            try:
                _ = o.name  # Accessing .name on a deleted object raises ReferenceError
                result.append(o)
            except ReferenceError:
                pass
        return result

    # Clean up stale references in all layers (original curves now deleted)
    for layer_name in layer_objects:
        layer_objects[layer_name] = live_objects(layer_objects[layer_name])

    # ── Step 3: Assign colors ──
    print("\n[3/6] Assigning anatomical colors...")

    for layer_name, objects in layer_objects.items():
        meshes = [o for o in objects if o.type == 'MESH']
        colored = 0
        for obj in meshes:
            assign_color_to_mesh(obj, layer_name)
            colored += 1
        print(f"  {layer_name}: {colored} meshes colored")

    # ── Step 4: Count triangles and decimate if needed ──
    print("\n[4/6] Counting triangles and optimizing...")

    total_tris = 0
    layer_tris = {}
    for layer_name, objects in layer_objects.items():
        meshes = [o for o in objects if o.type == 'MESH']
        tris = sum(count_tris(o) for o in meshes)
        layer_tris[layer_name] = tris
        total_tris += tris
        print(f"  {layer_name}: {tris:,} triangles ({len(meshes)} meshes)")

    print(f"  TOTAL: {total_tris:,} triangles")

    if total_tris > args.max_tris:
        ratio = args.max_tris / total_tris
        print(f"\n  Decimating to ~{args.max_tris:,} triangles (ratio: {ratio:.3f})...")

        for layer_name, objects in layer_objects.items():
            meshes = [o for o in objects if o.type == 'MESH']
            for obj in meshes:
                if count_tris(obj) > 100:  # Only decimate non-trivial meshes
                    decimate_mesh(obj, ratio)

        # Recount
        new_total = 0
        for layer_name, objects in layer_objects.items():
            meshes = [o for o in objects if o.type == 'MESH']
            tris = sum(count_tris(o) for o in meshes)
            new_total += tris
        print(f"  After decimation: {new_total:,} triangles")

    # ── Step 5: Tag meshes with layer prefix in name ──
    # Instead of re-parenting (which fails for deeply nested Bonus objects),
    # prefix each mesh name with its layer. JS parser splits on the prefix.
    #
    # CRITICAL: Process layers in priority order and DEDUPLICATE.
    # The same Blender object can appear in multiple layers (main collection
    # + Bonus sub-collection). Without dedup, cascading renames produce
    # garbage like SKIN__SKEL_SKEL_SKEL_Incus.
    print("\n[5/6] Tagging meshes with layer names...")

    # Priority order: most anatomically specific first.
    # If an object is in both skeleton and skin (Bonus), skeleton wins.
    LAYER_PRIORITY = [
        "layer_skeleton",
        "layer_muscle",
        "layer_vasculature",
        "layer_nervous",
        "layer_organs",
        "layer_skin",
    ]

    PREFIX_MAP = {
        "layer_skeleton":    "SKEL__",
        "layer_muscle":      "MUSC__",
        "layer_organs":      "ORGN__",
        "layer_vasculature": "VASC__",
        "layer_nervous":     "NERV__",
        "layer_skin":        "SKIN__",
    }

    total_exported = 0
    tagged_objects = []
    seen_names = set()
    tagged_ids = set()   # Track by Python id() — each object tagged ONCE

    for layer_name in LAYER_PRIORITY:
        if layer_name not in layer_objects:
            continue
        objects = layer_objects[layer_name]
        # Filter: real mesh, has geometry, NOT already tagged by a higher-priority layer
        meshes = [o for o in objects
                  if o.type == 'MESH' and o.data and len(o.data.vertices) > 0
                  and id(o) not in tagged_ids]

        if not meshes:
            print(f"  {layer_name}: 0 unique meshes (skipping)")
            continue

        prefix = PREFIX_MAP.get(layer_name, "UNKN__")

        for obj in meshes:
            tagged_ids.add(id(obj))
            safe_name = make_name_safe(obj.name)
            tagged_name = prefix + safe_name
            # Ensure uniqueness (Blender requires unique names)
            if tagged_name in seen_names:
                tagged_name = tagged_name + "_" + str(total_exported)
            seen_names.add(tagged_name)
            obj.name = tagged_name
            tagged_objects.append(obj)
            total_exported += 1

        print(f"  {layer_name}: {len(meshes)} unique meshes (prefix: {prefix})")

    print(f"  Total unique meshes tagged: {total_exported}")

    # ── Step 6: Export GLB ──
    print(f"\n[6/6] Exporting GLB to {args.output}...")

    # Export ENTIRE scene (use_selection=False) to avoid Blender's selection
    # limitations with deeply nested collection hierarchies. Our name prefixes
    # (SKEL__, MUSC__, etc.) let the JS parser identify each mesh's layer.
    # Untagged objects (reference lines, etc.) are ignored by JS.

    # Ensure output directory exists
    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)

    bpy.ops.export_scene.gltf(
        filepath=args.output,
        use_selection=False,
        export_format='GLB',
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=6,
        export_draco_position_quantization=14,
        export_draco_normal_quantization=10,
        export_materials='EXPORT',
        export_normals=True,
        export_yup=True,            # Y-up for Three.js
    )

    file_size = os.path.getsize(args.output)
    print(f"\n{'=' * 60}")
    print(f"SUCCESS! Exported {total_exported} meshes")
    print(f"File: {args.output}")
    print(f"Size: {file_size / 1024 / 1024:.1f} MB")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
