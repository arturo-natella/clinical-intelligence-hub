#!/bin/bash
# Clinical Intelligence Hub — Install Monitoring Schedules
#
# Installs launchd plists so macOS runs monitoring automatically:
#   • API monitors  — daily at 6:00 AM (PubMed, OpenFDA, ClinVar, RxNorm, CT.gov, PharmGKB)
#   • Playwright monitors — weekly Sunday 3:00 AM (ADA, AHA, USPSTF guidelines)
#
# Usage: chmod +x install_monitors.sh && ./install_monitors.sh

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "╔══════════════════════════════════════════════════╗"
echo "║   Install Monitoring Schedules                   ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Paths
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
VENV_PYTHON="$DIR/venv/bin/python"
DATA_DIR="$DIR/data"
LOG_DIR="$DIR/data/logs"
PROJECT_DIR="$DIR"

# Verify venv exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "✗ Virtual environment not found at $VENV_PYTHON"
    echo "  Run setup.sh first."
    exit 1
fi

# Create directories
mkdir -p "$LAUNCH_AGENTS" "$LOG_DIR"

# Vault passphrase for monitoring
echo "Monitoring needs your vault passphrase to read the patient profile."
echo "It will be stored in the macOS Keychain (encrypted)."
echo ""
read -s -p "Enter vault passphrase: " PASSPHRASE
echo ""

# Store in Keychain
security add-generic-password \
    -a "$USER" \
    -s "com.medprep.vault" \
    -w "$PASSPHRASE" \
    -U 2>/dev/null || true
echo "  ✓ Passphrase stored in macOS Keychain"

# ── Install API Monitor Plist ─────────────────────────────
echo ""
echo "▸ Installing daily API monitor schedule..."

API_PLIST="$LAUNCH_AGENTS/com.medprep.api-monitor.plist"

# Create plist from template with actual paths
sed \
    -e "s|VENV_PYTHON|$VENV_PYTHON|g" \
    -e "s|DATA_DIR|$DATA_DIR|g" \
    -e "s|PROJECT_DIR|$PROJECT_DIR|g" \
    -e "s|LOG_DIR|$LOG_DIR|g" \
    "$DIR/com.medprep.api-monitor.plist" > "$API_PLIST"

# Unload if already loaded, then load
launchctl unload "$API_PLIST" 2>/dev/null || true
launchctl load "$API_PLIST"
echo "  ✓ API monitors scheduled (daily at 6:00 AM)"

# ── Install Playwright Monitor Plist ──────────────────────
echo ""
echo "▸ Installing weekly Playwright monitor schedule..."

PW_PLIST="$LAUNCH_AGENTS/com.medprep.playwright-monitor.plist"

sed \
    -e "s|VENV_PYTHON|$VENV_PYTHON|g" \
    -e "s|DATA_DIR|$DATA_DIR|g" \
    -e "s|PROJECT_DIR|$PROJECT_DIR|g" \
    -e "s|LOG_DIR|$LOG_DIR|g" \
    "$DIR/com.medprep.playwright-monitor.plist" > "$PW_PLIST"

launchctl unload "$PW_PLIST" 2>/dev/null || true
launchctl load "$PW_PLIST"
echo "  ✓ Playwright monitors scheduled (weekly Sunday 3:00 AM)"

# ── Verify ────────────────────────────────────────────────
echo ""
echo "▸ Verifying installation..."
if launchctl list | grep -q "com.medprep.api-monitor"; then
    echo "  ✓ com.medprep.api-monitor is loaded"
else
    echo "  ⚠ com.medprep.api-monitor may not be loaded (check launchctl list)"
fi

if launchctl list | grep -q "com.medprep.playwright-monitor"; then
    echo "  ✓ com.medprep.playwright-monitor is loaded"
else
    echo "  ⚠ com.medprep.playwright-monitor may not be loaded (check launchctl list)"
fi

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Monitoring Installed                           ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║   API monitors:       daily at 6:00 AM          ║"
echo "║   Playwright monitors: Sunday at 3:00 AM        ║"
echo "║                                                  ║"
echo "║   Logs: data/logs/                               ║"
echo "║                                                  ║"
echo "║   To uninstall:                                  ║"
echo "║     launchctl unload ~/Library/LaunchAgents/     ║"
echo "║       com.medprep.api-monitor.plist              ║"
echo "║     launchctl unload ~/Library/LaunchAgents/     ║"
echo "║       com.medprep.playwright-monitor.plist       ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
