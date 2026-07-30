#!/usr/bin/env python3
"""
Download all NIH HRA 3D Reference Organ GLB files.

The Human Reference Atlas (HRA) 3D Reference Object Library provides
anatomically correct reference organs, CC BY licensed.
Source: https://3d.nih.gov/collections/hra

Usage:
    python3 download_hra.py
"""

import json
import os
import sys
import urllib.request
import time

# All 77 HRA model entry IDs from the collection
# Format: 3DPX-0XXXXX → numeric ID XXXXX
ENTRY_IDS = [
    # Female organs
    20959,  # Brain, Female
    20961,  # Blood Vasculature, Female
    20962,  # Eye, Female, Left
    20963,  # Eye, Female, Right
    20964,  # Fallopian Tube, Female, Left
    20965,  # Fallopian Tube, Female, Right
    20966,  # Heart, Female
    20967,  # Kidney, Female, Left
    20968,  # Kidney, Female, Right
    20969,  # Knee, Female, Left
    20970,  # Knee, Female, Right
    20971,  # Large Intestine, Female
    20972,  # Larynx, Female
    20973,  # Liver, Female
    20974,  # Lung, Female
    20976,  # Main Bronchus, Female
    20977,  # Breast (mammary gland), Female left
    20978,  # Breast (mammary gland), Female right
    20979,  # Ovary, Female, Left
    20980,  # Ovary, Female, Right
    20983,  # Pancreas, Female
    20984,  # Pelvis, Female
    20985,  # Placenta, Full Term, Female
    20987,  # Small Intestine, Female
    20988,  # Spinal Cord, Female
    20989,  # Spleen, Female
    20990,  # Thymus, Female
    20991,  # Trachea, Female
    20992,  # Body, Female
    20993,  # Ureter, Female, Left
    20994,  # Ureter, Female, Right
    20995,  # Urinary Bladder, Female
    # Male organs
    20960,  # Brain, Male
    20997,  # Blood Vasculature, Male
    20998,  # Eye, Male, Left
    20999,  # Eye, Male, Right
    21000,  # Heart, Male
    21001,  # Kidney, Male, Left
    21002,  # Kidney, Male, Right
    21003,  # Knee, Male, Left
    21004,  # Knee, Male, Right
    21005,  # Large Intestine, Male
    21006,  # Larynx, Male
    21007,  # Liver, Male
    21008,  # Lung, Male
    21010,  # Main Bronchus, Male
    21013,  # Pancreas, Male
    21014,  # Pelvis, Male
    21015,  # Prostate, Male
    21017,  # Small Intestine, Male
    21018,  # Spinal Cord, Male
    21019,  # Spleen, Male
    21020,  # Thymus, Male
    21021,  # Trachea, Male
    21022,  # Body, Male
    21023,  # Ureter, Male, Left
    21024,  # Ureter, Male, Right
    21025,  # Urinary Bladder, Male
    20975,  # Lymph Node, Female
    21009,  # Lymph Node, Male
    21619,  # Manubrium, Female
    20996,  # Uterus, Female
    21621,  # Renal Pelvis, Female, Left
    21622,  # Renal Pelvis, Female, Right
    21623,  # Renal Pelvis, Male, Left
    21624,  # Renal Pelvis, Male, Right
    21626,  # Body, Male (v2)
    21627,  # Body, Female (v2)
    22826,  # Mouth, Female
    21016,  # Skin, Male
    20986,  # Skin, Female
    20982,  # Palatine Tonsil, Female, Right
    20981,  # Palatine Tonsil, Female, Left
    21011,  # Palatine Tonsil, Male, Left
    21012,  # Palatine Tonsil, Male, Right
    22831,  # Mouth, Male
    21620,  # Sternum, Female
]

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
API_BASE = "https://3d.nih.gov/api/entries/3DPX-{:06d}"


def download_entry(entry_id):
    """Fetch entry metadata and download the GLB file."""
    url = API_BASE.format(entry_id)
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  ERROR fetching metadata for {entry_id}: {e}")
        return None

    title = data.get("submissions", [{}])[0].get("metadata", {}).get("title", f"Unknown-{entry_id}")
    submissions = data.get("submissions", [])
    if not submissions:
        print(f"  WARN: No submissions for {entry_id}")
        return None

    sub = submissions[0]
    input_files = sub.get("inputFiles", [])

    glb_files = [f for f in input_files if f.get("fileFormat", "").upper() == "GLB"]
    if not glb_files:
        print(f"  WARN: No GLB file for {entry_id} ({title})")
        return None

    for glb in glb_files:
        s3_url = glb["s3Location"]
        filename = glb["name"]
        file_size = glb.get("fileSize", 0)
        out_path = os.path.join(OUTPUT_DIR, filename)

        if os.path.exists(out_path) and os.path.getsize(out_path) == file_size:
            print(f"  SKIP (exists): {filename} ({file_size / 1024:.0f} KB)")
            return filename

        print(f"  Downloading: {filename} ({file_size / 1024:.0f} KB) ...")
        try:
            urllib.request.urlretrieve(s3_url, out_path)
            print(f"  OK: {filename}")
            return filename
        except Exception as e:
            print(f"  ERROR downloading {filename}: {e}")
            return None


def main():
    print(f"NIH HRA 3D Model Downloader")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Entries: {len(ENTRY_IDS)}")
    print()

    downloaded = 0
    skipped = 0
    failed = 0

    for i, eid in enumerate(ENTRY_IDS, 1):
        print(f"[{i}/{len(ENTRY_IDS)}] 3DPX-{eid:06d}")
        result = download_entry(eid)
        if result:
            downloaded += 1
        else:
            failed += 1
        # Be polite to the server
        time.sleep(0.5)

    print(f"\nDone: {downloaded} downloaded, {failed} failed")

    # List all GLB files
    glbs = sorted(f for f in os.listdir(OUTPUT_DIR) if f.endswith('.glb'))
    total_size = sum(os.path.getsize(os.path.join(OUTPUT_DIR, f)) for f in glbs)
    print(f"Total: {len(glbs)} GLB files, {total_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
