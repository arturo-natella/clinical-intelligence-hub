/*!
 * main.js
 * Master orchestrator for the dashboard frontend.
 * Fetches the medical JSON profile from the local Flask server 
 * and distributes it to the BodyMap, Timeline, and Chat controllers.
 */

document.addEventListener('DOMContentLoaded', async () => {

    // Initialize Tabbed Navigation
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active from all
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            // Add active to clicked
            btn.classList.add('active');
            const targetId = btn.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });

    // Initialize component controllers
    const bodyMap = new BodyMapController('body-map-container');
    const timeline = new TimelineController('timeline-container');
    const chat = new ChatController('chat-container');

    // UI Elements for Config & Actions
    const btnSettings = document.getElementById('btn-settings');
    const btnAnalyze = document.getElementById('btn-analyze');
    const btnExport = document.getElementById('btn-export');
    const btnUpload = document.getElementById('btn-upload');

    // Modals
    const modalConfig = document.getElementById('config-modal');
    const modalUpload = document.getElementById('upload-modal');

    // Config Elements
    const btnCancel = document.getElementById('btn-cancel-config');
    const btnSave = document.getElementById('btn-save-config');
    const inputGemini = document.getElementById('input-gemini-key');
    const inputOpenFda = document.getElementById('input-openfda-key');
    const inputReddit = document.getElementById('input-reddit-key');

    // Upload Elements
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const dropText = document.getElementById('drop-text');
    const fileListPreview = document.getElementById('file-list-preview');
    const btnCancelUpload = document.getElementById('btn-cancel-upload');
    const btnConfirmUpload = document.getElementById('btn-confirm-upload');

    let selectedFiles = [];

    // Upload Logic
    btnUpload.addEventListener('click', () => {
        modalUpload.style.display = 'flex';
        selectedFiles = [];
        updateFilePreview();
    });

    btnCancelUpload.addEventListener('click', () => {
        modalUpload.style.display = 'none';
    });

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.background = 'rgba(255,255,255,0.1)';
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.style.background = 'rgba(0,0,0,0.2)';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.background = 'rgba(0,0,0,0.2)';
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });

    function handleFiles(files) {
        for (const f of files) {
            if (f.name.toLowerCase().endsWith('.pdf') || f.name.toLowerCase().endsWith('.dcm')) {
                selectedFiles.push(f);
            }
        }
        updateFilePreview();
    }

    function updateFilePreview() {
        if (selectedFiles.length === 0) {
            fileListPreview.textContent = '';
            dropText.textContent = "Click to browse or Drag & Drop files here";
            btnConfirmUpload.disabled = true;
        } else {
            dropText.textContent = "Ready to upload";
            fileListPreview.textContent = `${selectedFiles.length} file(s) selected:\n` + selectedFiles.map(f => f.name).join(', ');
            btnConfirmUpload.disabled = false;
        }
    }

    btnConfirmUpload.addEventListener('click', async () => {
        if (selectedFiles.length === 0) return;

        btnConfirmUpload.textContent = "Uploading...";
        btnConfirmUpload.disabled = true;

        const formData = new FormData();
        selectedFiles.forEach(f => formData.append('files', f));

        try {
            const resp = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (resp.ok) {
                const result = await resp.json();
                alert(result.message + " You can now Run the Analysis Pipeline.");
                modalUpload.style.display = 'none';
            } else {
                const err = await resp.json();
                alert(`Upload failed: ${err.error}`);
            }
        } catch (e) {
            alert(`Network error during upload: ${e.message}`);
        } finally {
            btnConfirmUpload.textContent = "Upload & Save";
            btnConfirmUpload.disabled = false;
        }
    });

    // Pipeline Execution Logic
    btnAnalyze.addEventListener('click', async () => {
        btnAnalyze.textContent = "Analyzing... (This may take a few minutes)";
        btnAnalyze.disabled = true;

        try {
            const resp = await fetch('/api/analyze', { method: 'POST' });
            if (resp.ok) {
                alert("Deep Research & Analysis Complete. Reloading Dashboard.");
                window.location.reload();
            } else {
                const err = await resp.json();
                alert(`Analysis Failed: ${err.error || "Unknown Error"}`);
            }
        } catch (e) {
            alert(`Error triggering analysis pipeline: ${e.message}`);
        } finally {
            btnAnalyze.textContent = "🔄 Analyze New Records";
            btnAnalyze.disabled = false;
        }
    });

    btnExport.addEventListener('click', () => {
        // Automatically triggers the download of the Word DOCX
        window.open('/api/export', '_blank');
    });

    // Configuration Logic
    btnSettings.addEventListener('click', async () => {
        const resp = await fetch('/api/config');
        if (resp.ok) {
            const keys = await resp.json();
            inputGemini.value = keys.gemini_api_key || "";
            inputOpenFda.value = keys.openfda_api_key || "";
            inputReddit.value = keys.reddit_api_key || "";
        }
        modalConfig.style.display = 'flex';
    });

    btnCancel.addEventListener('click', () => {
        modalConfig.style.display = 'none';
    });

    btnSave.addEventListener('click', async () => {
        const keyData = {
            gemini_api_key: inputGemini.value.trim(),
            openfda_api_key: inputOpenFda.value.trim(),
            reddit_api_key: inputReddit.value.trim()
        };
        await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(keyData)
        });
        modalConfig.style.display = 'none';
        alert("API Keys saved securely to local configuration.");
    });

    try {
        // Fetch the living patient profile from the local Python backend
        const response = await fetch('/api/profile');

        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        const patientData = await response.json();

        // Feed the data into the visualizations
        bodyMap.initialize(patientData);
        timeline.initialize(patientData);

        console.log("MedPrep Dashboard successfully initialized with patient data.");

    } catch (error) {
        console.error("Failed to load Patient Profile:", error);

        // In a real app, this would render a user-friendly empty state 
        // asking them to drop files into the app to start the pipeline.
        alert("MedPrep Error: Unable to load patient profile data. Have you parsed any records yet?");
    }
});
