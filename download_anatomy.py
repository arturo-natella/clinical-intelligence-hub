import os
import urllib.request
import zipfile
import sys

# Target directories
BASE_DIR = os.path.abspath("MedPrep/src/ui/static/models")
TEMP_DIR = os.path.join(BASE_DIR, "tmp_download")
OBJ_DIR = os.path.join(BASE_DIR, "bodyparts3d_raw")

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(OBJ_DIR, exist_ok=True)

url = "https://dbarchive.biosciencedbc.jp/data/bodyparts3d/LATEST/isa_BP3D_4.0_obj_99.zip"
zip_path = os.path.join(TEMP_DIR, "isa_BP3D_4.0_obj_99.zip")

print(f"Downloading Complete Human Anatomy from BodyParts3D (approx 1.5GB)...")
print(f"URL: {url}")

def progress_hook(count, block_size, total_size):
    percent = int(count * block_size * 100 / total_size)
    sys.stdout.write(f"Downloading: {percent}%")
    sys.stdout.flush()

try:
    if not os.path.exists(zip_path):
        urllib.request.urlretrieve(url, zip_path, reporthook=progress_hook)
        print("
Download complete!")
    else:
        print("
Zip file already exists, skipping download.")
        
    print("Extracting 4,000+ organs and body parts. This will take a few minutes...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(OBJ_DIR)
    
    print(f"
Success! All raw .obj files are extracted to: {OBJ_DIR}")
    print("Cleaning up temporary zip file...")
    os.remove(zip_path)
    os.rmdir(TEMP_DIR)
    print("Done.")

except Exception as e:
    print(f"
Error occurred: {e}")
