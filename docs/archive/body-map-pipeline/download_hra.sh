#!/bin/bash
# Download all NIH HRA 3D Reference Organ GLB files via curl
# Source: https://3d.nih.gov/collections/hra (CC BY)
# Each model: fetch API → extract S3 URL → download GLB

set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# All 77 entry IDs
ENTRIES=(
  20959 20961 20962 20963 20964 20965 20966 20967 20968 20969
  20970 20971 20972 20973 20974 20976 20977 20978 20979 20980
  20983 20984 20985 20987 20988 20989 20990 20991 20992 20993
  20994 20995 20960 20997 20998 20999 21000 21001 21002 21003
  21004 21005 21006 21007 21008 21010 21013 21014 21015 21017
  21018 21019 21020 21021 21022 21023 21024 21025 20975 21009
  21619 20996 21621 21622 21623 21624 21626 21627 22826 21016
  20986 20982 20981 21011 21012 22831 21620
)

TOTAL=${#ENTRIES[@]}
OK=0
FAIL=0
SKIP=0

echo "NIH HRA 3D Model Downloader (curl)"
echo "Output: $DIR"
echo "Entries: $TOTAL"
echo ""

for i in "${!ENTRIES[@]}"; do
  EID="${ENTRIES[$i]}"
  NUM=$((i + 1))
  DPXID=$(printf "3DPX-%06d" "$EID")
  echo "[$NUM/$TOTAL] $DPXID"

  # Fetch entry metadata from API
  API_URL="https://3d.nih.gov/api/entries/$DPXID"
  META=$(curl -sf "$API_URL" 2>/dev/null) || { echo "  ERROR: API fetch failed"; FAIL=$((FAIL+1)); continue; }

  # Extract submissionId, fileId, and filename from JSON
  DOWNLOAD_INFO=$(echo "$META" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for sub in data.get('submissions', []):
    sid = sub.get('submissionId', '')
    for f in sub.get('inputFiles', []):
        if f.get('fileFormat','').upper() == 'GLB':
            print(f'{sid}|{f[\"fileId\"]}|{f[\"name\"]}')
            sys.exit(0)
print('')
" 2>/dev/null)

  SUBMISSION_ID=$(echo "$DOWNLOAD_INFO" | cut -d'|' -f1)
  FILE_ID=$(echo "$DOWNLOAD_INFO" | cut -d'|' -f2)
  FILENAME=$(echo "$DOWNLOAD_INFO" | cut -d'|' -f3)

  if [ -z "$SUBMISSION_ID" ] || [ -z "$FILE_ID" ] || [ -z "$FILENAME" ]; then
    echo "  WARN: No GLB file found"
    FAIL=$((FAIL+1))
    continue
  fi

  # Skip if already downloaded
  if [ -f "$DIR/$FILENAME" ]; then
    echo "  SKIP: $FILENAME (exists)"
    SKIP=$((SKIP+1))
    continue
  fi

  # Download via NIH API (S3 direct links are restricted)
  DOWNLOAD_URL="https://3d.nih.gov/api/download?submissionId=${SUBMISSION_ID}&fileIds=${FILE_ID}"
  echo "  Downloading: $FILENAME ..."
  if curl -sf -o "$DIR/$FILENAME" "$DOWNLOAD_URL"; then
    SIZE=$(stat -f%z "$DIR/$FILENAME" 2>/dev/null || stat --printf="%s" "$DIR/$FILENAME" 2>/dev/null)
    echo "  OK: $FILENAME ($(( SIZE / 1024 )) KB)"
    OK=$((OK+1))
  else
    echo "  ERROR: Download failed"
    rm -f "$DIR/$FILENAME"
    FAIL=$((FAIL+1))
  fi

  sleep 0.3
done

echo ""
echo "Done: $OK downloaded, $SKIP skipped, $FAIL failed"
GLBS=$(ls -1 "$DIR"/*.glb 2>/dev/null | wc -l | tr -d ' ')
TOTAL_SIZE=$(ls -l "$DIR"/*.glb 2>/dev/null | awk '{s+=$5} END {printf "%.1f", s/1024/1024}')
echo "Total: $GLBS GLB files, ${TOTAL_SIZE} MB"
