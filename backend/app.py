from flask import Flask, jsonify, send_from_directory, request, send_file
import json
from pathlib import Path
import os
import subprocess
from google import genai
from google.genai import types
import sys

# Absolute paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / "backend" / "utils"))
sys.path.append(str(BASE_DIR / "backend" / "processors"))

from encryption import SecurityManager
from rag_chat import RAGEngine

app = Flask(__name__)

# Absolute paths
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"
PROFILE_PATH = DATA_DIR / "patient_profile.json"
RAW_UPLOADS_DIR = DATA_DIR / "raw_uploads"
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSORS_DIR = BASE_DIR / "backend" / "processors"

# Ensure upload directory exists
RAW_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

@app.route('/')
def index():
    """Serve the main dashboard UI."""
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(FRONTEND_DIR / 'css', filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(FRONTEND_DIR / 'js', filename)

# Simple local config storage for API Keys
CONFIG_PATH = DATA_DIR / "config.json"

@app.route('/api/config', methods=['GET', 'POST'])
def manage_config():
    """Allows the dashboard to save and retrieve API Keys securely to the local machine."""
    if request.method == 'POST':
        data = request.json
        with open(CONFIG_PATH, 'w') as f:
            json.dump(data, f)
        return jsonify({"status": "success"})
    else:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r') as f:
                return jsonify(json.load(f))
        return jsonify({"gemini_api_key": ""})

@app.route('/api/profile')
def get_profile():
    """Serve the centralized Patient Profile JSON to the frontend."""
    if PROFILE_PATH.exists():
        sm = SecurityManager(DATA_DIR)
        profile = sm.load_profile(PROFILE_PATH)
        if profile:
            return jsonify(profile)
    return jsonify({"error": "No patient profile found. Have you dropped files yet?"}), 404

@app.route('/api/analyze', methods=['POST'])
def run_analysis():
    """Orchestrates the offline data ingestion and deep research pipelines."""
    try:
        # 1. Document Ingestion & Vision API execution
        subprocess.run(["python", "ingest.py"], cwd=PROCESSORS_DIR, check=True)
        
        # 2. FDA / CPIC / Reddit Community Research execution
        subprocess.run(["python", "deep_research.py"], cwd=PROCESSORS_DIR, check=True)
        
        # 3. Embed the final profile into ChromaDB for live RAG Chat
        if PROFILE_PATH.exists():
            sm = SecurityManager(DATA_DIR)
            profile = sm.load_profile(PROFILE_PATH)
            if profile:
                rag = RAGEngine(DATA_DIR)
                rag.embed_profile(profile)
        
        return jsonify({"status": "success", "message": "Analysis & Embedding complete."})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Pipeline execution failed: {str(e)}"}), 500

@app.route('/api/upload', methods=['POST'])
def handle_upload():
    """Receives files from the frontend and saves them to the raw_uploads directory."""
    if 'files' not in request.files:
        return jsonify({"error": "No files provided."}), 400
        
    uploaded_files = request.files.getlist('files')
    saved_count = 0
    
    for file in uploaded_files:
        if file.filename:
            # Secure the filename simply by grabbing the basename
            filename = os.path.basename(file.filename)
            save_path = RAW_UPLOADS_DIR / filename
            file.save(save_path)
            saved_count += 1
            
    return jsonify({"status": "success", "message": f"{saved_count} files uploaded securely."})

@app.route('/api/export', methods=['GET'])
def export_doc():
    """Generates the Word document and returns it for download."""
    try:
        # Construct the latest DOCX
        subprocess.run(["python", "report_builder.py"], cwd=PROCESSORS_DIR, check=True)
        
        # Find the latest generated document in the processed directory
        import glob
        list_of_files = glob.glob(str(PROCESSED_DIR / "MedPrep_Report_*.docx"))
        if not list_of_files:
            return jsonify({"error": "Failed to generate report"}), 500
            
        latest_file = max(list_of_files, key=os.path.getctime)
        return send_file(latest_file, as_attachment=True)
    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    """Endpoint for the RAG AI Agent using Gemini Pro."""
    data = request.json
    user_message = data.get('message', '')
    
    # Load API Key
    api_key = None
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r') as f:
            api_key = json.load(f).get('gemini_api_key')
            
    if not api_key:
        return jsonify({"response": "Please configure your Gemini API Key in the settings first."})
        
    # Load Patient Context via ChromaDB RAG Vector Search
    context = "No patient data found."
    if PROFILE_PATH.exists():
        rag = RAGEngine(DATA_DIR)
        context = rag.query(user_message, n_results=10) # Find the 10 most relevant events
            
    try:
        client = genai.Client(api_key=api_key)
        
        system_instruction = f"""
        You are the MedPrep Clinical Assistant. Answer the user's questions utilizing ONLY the semantically relevant patient records retrieved from the local database below. If the answer is not in the context, say "I cannot explicitly confirm that in your records."
        
        \n<RETRIEVED_RECORDS>\n{context}\n</RETRIEVED_RECORDS>
        """
        
        response = client.models.generate_content(
            model="gemini-1.5-pro",
            contents=[system_instruction, user_message],
            config=types.GenerateContentConfig(temperature=0.2)
        )
        
        return jsonify({"response": response.text})
        
    except Exception as e:
        return jsonify({"response": f"API Error: {str(e)}"})

if __name__ == '__main__':
    # Run securely bound to localhost only
    app.run(host='127.0.0.1', port=5050, debug=True)
