#!/usr/bin/env python3
"""
BodyParts3D OBJ → GLB Conversion Pipeline
==========================================
Imports BodyParts3D OBJ files, groups by organ category,
assigns anatomically-correct colors, and exports as GLB.

Usage:
    blender --background --python convert_bodyparts3d.py -- \
        --input /path/to/partof_BP3D_4.0_obj_99/ \
        --mapping /path/to/partof_element_parts.txt \
        --output /path/to/output/organs_detailed.glb

BodyParts3D uses millimeters with Z-up. GLTF uses meters with Y-up.
Blender handles the coordinate conversion during export.
"""

import bpy
import os
import sys
import math
from collections import defaultdict

# ── Parse CLI args ──────────────────────────────────────────────────
argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

input_dir = None
mapping_file = None
output_file = None

i = 0
while i < len(argv):
    if argv[i] == "--input" and i + 1 < len(argv):
        input_dir = argv[i + 1]; i += 2
    elif argv[i] == "--mapping" and i + 1 < len(argv):
        mapping_file = argv[i + 1]; i += 2
    elif argv[i] == "--output" and i + 1 < len(argv):
        output_file = argv[i + 1]; i += 2
    else:
        i += 1

if not all([input_dir, mapping_file, output_file]):
    print("ERROR: --input, --mapping, and --output are required")
    sys.exit(1)

# ── Organ categories with FMA-name keyword matching ─────────────────
ORGAN_CATEGORIES = {
    "heart": {
        "keywords": [
            "heart", "ventricle", "atrium", "aorta", "coronary",
            "pericardium", "valve", "papillary", "myocardium",
            "interventricular", "interatrial", "cardiac",
            "pulmonary trunk", "pulmonary valve", "aortic valve",
            "mitral", "tricuspid", "chordae", "cusp",
        ],
        "color": (0.55, 0.08, 0.08),  # deep crimson
    },
    "brain": {
        "keywords": [
            "brain", "cerebr", "cerebel", "hippocampus", "thalamus",
            "hypothalamus", "amygdala", "pons", "medulla oblongata",
            "midbrain", "corpus callosum", "frontal lobe", "parietal lobe",
            "temporal lobe", "occipital lobe", "brainstem", "basal ganglia",
            "caudate", "putamen", "globus pallidus", "substantia nigra",
            "red nucleus", "fornix", "cingulate", "insula",
            "choroid plexus", "pineal", "pituitary",
        ],
        "color": (0.72, 0.62, 0.65),  # pinkish-grey
    },
    "lungs": {
        "keywords": [
            "lung", "bronch", "alveol", "pleura", "trachea",
            "diaphragm", "pulmonary", "lingula",
            "bronchopulmonary", "segmental",
        ],
        "color": (0.75, 0.55, 0.62),  # mauve-pink
    },
    "liver": {
        "keywords": [
            "liver", "hepat", "gallbladder", "bile", "portal",
            "caudate lobe", "quadrate lobe",
        ],
        "color": (0.45, 0.15, 0.12),  # dark reddish-brown
    },
    "kidneys": {
        "keywords": [
            "kidney", "renal", "ureter", "adrenal", "suprarenal",
            "nephron", "calyx", "renal pelvis",
        ],
        "color": (0.55, 0.30, 0.20),  # bean-brown
    },
    "gi_tract": {
        "keywords": [
            "stomach", "intestin", "colon", "rectum", "esophag",
            "duodenum", "jejunum", "ileum", "appendix", "cecum",
            "sigmoid", "ascending colon", "descending colon",
            "transverse colon", "gastric", "pylor",
        ],
        "color": (0.78, 0.60, 0.52),  # warm tan-pink
    },
    "reproductive": {
        "keywords": [
            "uterus", "ovary", "testi", "prostate", "penis",
            "vagina", "scrotum", "fallopian", "epididym",
            "seminal", "vas deferens", "spermatic",
        ],
        "color": (0.82, 0.55, 0.60),  # warm pink
    },
    "other_organs": {
        "keywords": [
            "spleen", "pancrea", "bladder", "thyroid", "pharynx",
            "larynx", "tongue", "tonsil", "salivary", "thymus",
            "parathyroid", "parotid", "submandibular", "sublingual",
        ],
        "color": (0.65, 0.45, 0.40),  # muted brown-pink
    },
}

# ── Parse FMA mapping ──────────────────────────────────────────────
print("Reading FMA mapping...")
fma_map = {}  # file_id → (concept_id, name)
file_to_names = defaultdict(list)  # file_id → [name1, name2, ...]

with open(mapping_file, "r") as f:
    header = f.readline()  # skip header
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) >= 3:
            concept_id, name, file_id = parts[0], parts[1], parts[2]
            fma_map[file_id] = (concept_id, name)
            file_to_names[file_id].append(name)

print(f"  Loaded {len(fma_map)} mappings for {len(file_to_names)} unique files")

# ── Classify files by organ category ───────────────────────────────
def classify_file(file_id):
    """Return the organ category for a file based on its FMA names."""
    names = file_to_names.get(file_id, [])
    name_str = " ".join(names).lower()

    for category, config in ORGAN_CATEGORIES.items():
        for keyword in config["keywords"]:
            if keyword.lower() in name_str:
                return category
    return None

# Build category → [file_ids] mapping
category_files = defaultdict(set)
for file_id in file_to_names:
    cat = classify_file(file_id)
    if cat:
        obj_path = os.path.join(input_dir, f"{file_id}.obj")
        if os.path.exists(obj_path):
            category_files[cat].add(file_id)

print("\nOrgan categories:")
total_files = 0
for cat in sorted(category_files.keys()):
    count = len(category_files[cat])
    total_files += count
    print(f"  {cat}: {count} OBJ files")
print(f"  TOTAL: {total_files} files to import")

# ── Clear Blender scene ───────────────────────────────────────────
print("\nClearing scene...")
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
for col in list(bpy.data.collections):
    bpy.data.collections.remove(col)

# ── Import and organize ──────────────────────────────────────────
print("\nImporting OBJ files...")

imported_count = 0
failed_count = 0

for category, file_ids in sorted(category_files.items()):
    config = ORGAN_CATEGORIES[category]
    color = config["color"]

    # Create collection for this category
    col = bpy.data.collections.new(f"organ_{category}")
    bpy.context.scene.collection.children.link(col)

    # Create parent empty for the category
    parent_empty = bpy.data.objects.new(f"organ_{category}", None)
    col.objects.link(parent_empty)

    for file_id in sorted(file_ids):
        obj_path = os.path.join(input_dir, f"{file_id}.obj")
        names = file_to_names.get(file_id, [file_id])
        primary_name = names[0] if names else file_id

        try:
            # Import OBJ
            bpy.ops.wm.obj_import(
                filepath=obj_path,
                forward_axis='NEGATIVE_Z',
                up_axis='Y',
            )

            # Get the newly imported objects
            new_objects = [o for o in bpy.context.selected_objects if o.type == 'MESH']

            for obj in new_objects:
                # Rename with anatomical name
                obj.name = f"{primary_name} [{file_id}]"

                # Scale from mm to m (BodyParts3D uses mm)
                obj.scale = (0.001, 0.001, 0.001)

                # Apply scale
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

                # Create material with organ color
                mat = bpy.data.materials.new(name=f"mat_{category}_{file_id}")
                mat.use_nodes = True
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    # Add slight variation per mesh for visual distinction
                    h = hash(file_id) % 1000 / 1000.0
                    r = min(1.0, color[0] + (h - 0.5) * 0.06)
                    g = min(1.0, color[1] + (h - 0.5) * 0.04)
                    b = min(1.0, color[2] + (h - 0.5) * 0.04)
                    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
                    bsdf.inputs["Roughness"].default_value = 0.7
                    if hasattr(bsdf.inputs, "Subsurface Weight"):
                        bsdf.inputs["Subsurface Weight"].default_value = 0.1

                obj.data.materials.clear()
                obj.data.materials.append(mat)

                # Move to category collection
                for c in obj.users_collection:
                    c.objects.unlink(obj)
                col.objects.link(obj)

                # Parent to category empty
                obj.parent = parent_empty

                # Store metadata
                obj["fma_id"] = fma_map.get(file_id, ("", ""))[0]
                obj["fma_name"] = primary_name
                obj["organ_category"] = category

                imported_count += 1

        except Exception as e:
            print(f"  WARNING: Failed to import {file_id}: {e}")
            failed_count += 1

print(f"\nImported: {imported_count} meshes ({failed_count} failed)")

# ── Compute total stats ──────────────────────────────────────────
total_verts = 0
total_faces = 0
for obj in bpy.data.objects:
    if obj.type == 'MESH' and obj.data:
        total_verts += len(obj.data.vertices)
        total_faces += len(obj.data.polygons)

print(f"Total geometry: {total_verts:,} vertices, {total_faces:,} faces")

# ── Export GLB ───────────────────────────────────────────────────
print(f"\nExporting to {output_file}...")

bpy.ops.export_scene.gltf(
    filepath=output_file,
    export_format='GLB',
    export_draco_mesh_compression_enable=True,
    export_draco_mesh_compression_level=6,
    export_materials='EXPORT',
    export_apply=True,
    use_selection=False,
)

# Check output size
size = os.path.getsize(output_file)
print(f"Output: {output_file} ({size / 1024 / 1024:.1f} MB)")
print("Done!")
