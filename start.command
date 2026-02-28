#!/bin/bash

# MedPrep Launch Command
# This script sets up the local server and opens the patient dashboard.

echo "========================================================"
echo " Starting MedPrep: Patient Medical Records Analyzer..."
echo "========================================================"

# Get the directory of where this script is physically located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR" || { echo "Failed to navigate to project directory"; exit 1; }

# Activate the Python virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "⚠️ Warning: Python virtual environment not found in 'venv/'."
    echo "Please ensure the project dependencies are installed."
fi

# Wait 2 seconds for the Flask server to spin up, then launch the default browser
(sleep 2 && open "http://127.0.0.1:5050") &

# Start the local backend Flask server
echo "Starting local Python server on port 5050..."
python backend/app.py
