#!/bin/bash
# Clinical Intelligence Hub — Launch Script
# Double-click this file to start the application.

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "╔══════════════════════════════════════════════════╗"
echo "║   Clinical Intelligence Hub                      ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Prevent macOS from sleeping during analysis
caffeinate -i -w $$ &
CAFFEINATE_PID=$!
trap "kill $CAFFEINATE_PID 2>/dev/null" EXIT

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "⚠ Virtual environment not found. Run setup.sh first."
    echo "  chmod +x setup.sh && ./setup.sh"
    read -p "Press Enter to exit..."
    exit 1
fi

# Vault passphrase prompt
echo "Enter your vault passphrase to decrypt patient data:"
read -s VAULT_PASSPHRASE
export VAULT_PASSPHRASE
echo "  ✓ Vault unlocked"
echo ""

# Launch browser after short delay
(sleep 2 && open "http://127.0.0.1:5050") &

# Start the Flask server
echo "Starting Clinical Intelligence Hub on http://127.0.0.1:5050..."
python -m src.ui.app
