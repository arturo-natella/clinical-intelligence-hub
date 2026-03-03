import os
import urllib.request

# Target directory
BASE_DIR = os.path.abspath("MedPrep/src/ui/static/models")
os.makedirs(BASE_DIR, exist_ok=True)

# The concept file maps FMA IDs to English anatomical names
url = "https://dbarchive.biosciencedbc.jp/data/bodyparts3d/LATEST/FMA_BTO_mapping.txt"
file_path = os.path.join(BASE_DIR, "FMA_mapping.txt")

print(f"Downloading FMA Anatomy Mapping Dictionary...")
try:
    urllib.request.urlretrieve(url, file_path)
    print(f"Success! Mapping file saved to: {file_path}")
    print("Give this text file to Claude so it knows which FMA.obj file is which organ.")
except Exception as e:
    print(f"Error occurred: {e}")
