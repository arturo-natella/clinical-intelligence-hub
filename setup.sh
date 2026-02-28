#!/bin/bash
# Clinical Intelligence Hub — One-Command Setup
# Usage: chmod +x setup.sh && ./setup.sh

set -e

echo "╔══════════════════════════════════════════════════╗"
echo "║   Clinical Intelligence Hub — Setup              ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# ── 1. Python Virtual Environment ──────────────────────
echo "▸ Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  ✓ Created venv"
else
    echo "  ✓ venv already exists"
fi
source venv/bin/activate

echo "▸ Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  ✓ Dependencies installed"

# ── 2. Playwright Browser ──────────────────────────────
echo "▸ Installing Playwright Chromium..."
python -m playwright install chromium --quiet 2>/dev/null || {
    echo "  ⚠ Playwright browser install failed (will retry on first use)"
}
echo "  ✓ Playwright ready"

# ── 3. Ollama Check ───────────────────────────────────
echo ""
echo "▸ Checking Ollama..."
if command -v ollama &> /dev/null; then
    echo "  ✓ Ollama found at $(which ollama)"
else
    echo "  ✗ Ollama not found."
    echo "    Install from: https://ollama.com"
    echo "    Then run: ollama pull medgemma:27b-q8_0"
    echo "              ollama pull medgemma:4b"
fi

# ── 4. Model Downloads ────────────────────────────────
echo ""
echo "▸ Checking local AI models..."

# MedGemma 27B (Q8 quantization — ~28GB)
if ollama list 2>/dev/null | grep -q "medgemma.*27b"; then
    echo "  ✓ MedGemma 27B already downloaded"
else
    echo "  ⚠ MedGemma 27B not found."
    echo "    Run: ollama pull medgemma:27b-q8_0"
    echo "    (This is ~28GB and will take a while)"
fi

# MedGemma 4B
if ollama list 2>/dev/null | grep -q "medgemma.*4b"; then
    echo "  ✓ MedGemma 4B already downloaded"
else
    echo "  ⚠ MedGemma 4B not found."
    echo "    Run: ollama pull medgemma:4b"
fi

# ── 5. Data Directories ──────────────────────────────
echo ""
echo "▸ Creating data directories..."
mkdir -p data/uploads data/processed data/databases models
echo "  ✓ Data directories ready"

# ── 6. Tesseract OCR Check ────────────────────────────
echo ""
echo "▸ Checking Tesseract OCR (fallback)..."
if command -v tesseract &> /dev/null; then
    echo "  ✓ Tesseract found at $(which tesseract)"
else
    echo "  ⚠ Tesseract not found (optional — Apple Vision is primary OCR)"
    echo "    Install: brew install tesseract"
fi

# ── 7. NIH Database Downloads ─────────────────────────
echo ""
echo "▸ Standardization databases (LOINC, SNOMED CT, RxNorm)..."
echo "  These require free registration at https://uts.nlm.nih.gov/uts/"
echo "  After registration:"
echo "    • LOINC: https://loinc.org/downloads/ → place in data/databases/"
echo "    • SNOMED CT (US): https://www.nlm.nih.gov/healthit/snomedct/ → place in data/databases/"
echo "    • RxNorm: https://www.nlm.nih.gov/research/umls/rxnorm/ → place in data/databases/"
echo "  (The tool will use curated seed databases as fallback until full databases are installed)"

# ── 8. Summary ────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Setup Complete                                 ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║   To start:  double-click start.command          ║"
echo "║   Or run:    ./start.command                     ║"
echo "║                                                  ║"
echo "║   First run will prompt for a vault passphrase   ║"
echo "║   to encrypt your API keys and patient data.     ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
