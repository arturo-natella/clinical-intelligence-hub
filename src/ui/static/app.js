/* ══════════════════════════════════════════════════════════
   Clinical Intelligence Hub — Application JavaScript
   Handles view switching, API calls, SSE progress,
   file upload, chat, body map, timeline, and data rendering.

   Security: All dynamic content from APIs is sanitized via
   escapeHtml() before DOM insertion to prevent XSS.
   ══════════════════════════════════════════════════════════ */

// ── Helper Functions ──────────────────────────────────────

function $(id) { return document.getElementById(id); }

/**
 * Escapes HTML entities in a string to prevent XSS.
 * Uses DOM-based escaping (textContent → innerHTML).
 */
function escapeHtml(text) {
    if (text == null) return "";
    const div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
}

function severityBadge(severity) {
    const s = escapeHtml((severity || "info").toLowerCase());
    const map = {
        critical: "badge-critical",
        high: "badge-high",
        moderate: "badge-moderate",
        low: "badge-low",
        info: "badge-info",
    };
    const cls = map[s] || "badge-info";
    return '<span class="badge ' + cls + '">' + s.toUpperCase() + "</span>";
}

function formatDate(dateStr) {
    if (!dateStr) return "\u2014";
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
    } catch (e) { return escapeHtml(dateStr); }
}

function formatProvenance(prov) {
    if (!prov) return "";
    const parts = [];
    if (prov.source_file) parts.push(prov.source_file);
    if (prov.source_page) parts.push("p." + prov.source_page);
    if (prov.extraction_model) parts.push(prov.extraction_model);
    return escapeHtml(parts.join(", "));
}

const LAB_GLOSSARY = {
    "hba1c": {
        fullName: "Hemoglobin A1c",
        summary: "Estimates average blood sugar exposure over roughly the past 2 to 3 months.",
    },
    "fasting glucose": {
        fullName: "Fasting Glucose",
        summary: "Measures blood sugar after fasting and helps track day-to-day glucose control.",
    },
    "ldl cholesterol": {
        fullName: "Low-Density Lipoprotein Cholesterol",
        summary: "Often called LDL or 'bad' cholesterol. Higher levels are associated with plaque buildup in arteries.",
    },
    "hdl cholesterol": {
        fullName: "High-Density Lipoprotein Cholesterol",
        summary: "Often called HDL or 'good' cholesterol. It helps carry cholesterol away from the bloodstream.",
    },
    "total cholesterol": {
        fullName: "Total Cholesterol",
        summary: "Overall cholesterol measurement that includes multiple cholesterol fractions.",
    },
    "triglycerides": {
        fullName: "Triglycerides",
        summary: "A type of blood fat that often rises with insulin resistance, diet, and metabolic syndrome.",
    },
    "creatinine": {
        fullName: "Creatinine",
        summary: "A waste product used to help assess kidney filtration and overall kidney function.",
    },
    "bun": {
        fullName: "Blood Urea Nitrogen",
        summary: "A waste marker influenced by kidney function, hydration, and protein metabolism.",
    },
    "egfr": {
        fullName: "Estimated Glomerular Filtration Rate",
        summary: "An estimate of how well the kidneys are filtering blood.",
    },
    "tsh": {
        fullName: "Thyroid-Stimulating Hormone",
        summary: "A screening marker used to evaluate thyroid function.",
    },
    "alt": {
        fullName: "Alanine Aminotransferase",
        summary: "A liver enzyme that can rise when liver cells are irritated or injured.",
    },
    "ast": {
        fullName: "Aspartate Aminotransferase",
        summary: "An enzyme found in the liver and other tissues that can rise with cell injury.",
    },
    "wbc": {
        fullName: "White Blood Cell Count",
        summary: "Measures the cells involved in infection defense and inflammatory response.",
    },
    "white blood cell count": {
        fullName: "White Blood Cell Count",
        summary: "Measures the cells involved in infection defense and inflammatory response.",
    },
    "hemoglobin": {
        fullName: "Hemoglobin",
        summary: "The oxygen-carrying protein inside red blood cells.",
    },
    "platelets": {
        fullName: "Platelets",
        summary: "Cell fragments that help blood clot and stop bleeding.",
    },
    "vitamin d": {
        fullName: "Vitamin D",
        summary: "Helps reflect vitamin D status, which affects bone health and other body systems.",
    },
    "crp hs": {
        fullName: "High-Sensitivity C-Reactive Protein",
        summary: "A marker of low-grade inflammation often used in cardiovascular risk assessment.",
    },
    "crp": {
        fullName: "C-Reactive Protein",
        summary: "A marker of inflammation in the body.",
    },
    "blood pressure systolic": {
        fullName: "Systolic Blood Pressure",
        summary: "The top blood pressure number, showing pressure when the heart contracts.",
    },
};

function normalizeLabGlossaryKey(name) {
    return String(name || "")
        .toLowerCase()
        .replace(/[()]/g, " ")
        .replace(/[^a-z0-9]+/g, " ")
        .trim();
}

function getLabGlossaryEntry(name) {
    if (!name) return null;

    var normalized = normalizeLabGlossaryKey(name);
    if (LAB_GLOSSARY[normalized]) {
        return LAB_GLOSSARY[normalized];
    }

    if (normalized.indexOf("crp") !== -1) return LAB_GLOSSARY["crp hs"];
    if (normalized.indexOf("white blood cell") !== -1) return LAB_GLOSSARY["wbc"];
    if (normalized.indexOf("blood pressure") !== -1 && normalized.indexOf("systolic") !== -1) {
        return LAB_GLOSSARY["blood pressure systolic"];
    }

    return null;
}

function labelizeKey(key) {
    return String(key || "")
        .replace(/_/g, " ")
        .replace(/([a-z])([A-Z])/g, "$1 $2")
        .replace(/\b\w/g, function(ch) { return ch.toUpperCase(); });
}

async function api(path, options) {
    options = options || {};
    try {
        var res = await fetch(path, options);
        if (!res.ok) {
            var err = {};
            try { err = await res.json(); } catch (e2) { /* ignore */ }
            throw new Error(err.error || "HTTP " + res.status);
        }
        return res.json();
    } catch (e) {
        console.error("API " + path + ":", e);
        throw e;
    }
}

/**
 * Safely set innerHTML on an element. All dynamic values MUST be
 * pre-escaped with escapeHtml() before being included in the html string.
 */
function safeSetHtml(element, html) {
    if (typeof element === "string") element = $(element);
    if (element) element.innerHTML = html;
}

function updateSettingStatus(elementId, configured, configuredLabel) {
    var el = $(elementId);
    if (!el) return;
    el.textContent = configured ? (configuredLabel || "Configured") : "Not set";
    el.style.color = configured ? "var(--accent-green)" : "var(--accent-amber)";
}


// ══════════════════════════════════════════════════════════
//  App — Main Application Controller
// ══════════════════════════════════════════════════════════

var App = {
    uploadedFiles: [],

    // ── Initialization ────────────────────────────────

    init: async function() {
        // Setup sidebar nav click handlers
        var sidebarItems = document.querySelectorAll(".sidebar-item[data-view]");
        for (var i = 0; i < sidebarItems.length; i++) {
            (function(item) {
                item.addEventListener("click", function() {
                    App.navigateTo(item.dataset.view);
                });
            })(sidebarItems[i]);
        }

        // Enter key on passphrase input
        $("passphrase-input").addEventListener("keydown", function(e) {
            if (e.key === "Enter") App.unlock();
        });

        // Check if already unlocked (page refresh)
        try {
            var status = await api("/api/session/status");
            if (status.unlocked) {
                $("passphrase-modal").style.display = "none";
                $("sidebar").style.display = "flex";
                $("main-content").style.display = "block";
                if (status.has_profile) {
                    App.loadAllData();
                }
            }
        } catch (e) {
            // Server not ready yet, show passphrase modal
        }
    },

    // ── Vault Unlock ──────────────────────────────────

    unlock: async function() {
        var passphrase = $("passphrase-input").value;
        if (!passphrase) {
            $("passphrase-error").textContent = "Please enter a passphrase";
            $("passphrase-error").style.display = "block";
            return;
        }

        try {
            var result = await api("/api/unlock", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ passphrase: passphrase }),
            });

            $("passphrase-modal").style.display = "none";
            $("sidebar").style.display = "flex";
            $("main-content").style.display = "block";

            if (result.has_profile) {
                App.loadAllData();
            }
        } catch (e) {
            $("passphrase-error").textContent = e.message || "Failed to unlock vault";
            $("passphrase-error").style.display = "block";
        }
    },

    resetVault: async function() {
        if (!confirm("This will delete all encrypted patient data and let you start fresh with a new passphrase. Continue?")) {
            return;
        }
        try {
            await api("/api/vault/reset", { method: "POST" });
            $("passphrase-error").textContent = "";
            $("passphrase-error").style.display = "none";
            $("passphrase-input").value = "";
            $("passphrase-input").placeholder = "Choose a new passphrase";
            alert("Vault reset. Enter a new passphrase to create a fresh vault.");
        } catch (e) {
            $("passphrase-error").textContent = e.message || "Failed to reset vault";
            $("passphrase-error").style.display = "block";
        }
    },

    // ── View Navigation ───────────────────────────────

    navigateTo: function(view) {
        // Hide all views
        var views = document.querySelectorAll(".view");
        for (var i = 0; i < views.length; i++) views[i].classList.remove("active");

        // Show target view
        var target = $("view-" + view);
        if (target) target.classList.add("active");

        // Update active sidebar item
        var items = document.querySelectorAll(".sidebar-item[data-view]");
        for (var j = 0; j < items.length; j++) {
            items[j].classList.toggle("active", items[j].dataset.view === view);
        }

        // Load data for the view if needed
        var loaders = {
            dashboard: function() { App.loadDashboard(); },
            bodymap: function() { App.initBodyMap3D(); },
            medications: function() { App.loadMedications(); },
            labs: function() { App.loadLabs(); },
            imaging: function() { App.loadImaging(); },
            genetics: function() { App.loadGenetics(); },
            flags: function() { App.loadFlags(); },
            crossdisc: function() { App.loadCrossDisciplinary(); },
            community: function() { App.loadCommunity(); },
            timeline: function() { Timeline.load(); },
            symptoms: function() { Symptoms.load(); },
            alerts: function() { App.loadAlerts(); },
            report: function() { App.loadQuestions(); },
            environmental: function() { App.loadEnvironmental(); },
            tracker: function() { App.loadTracker(); },
        };
        if (loaders[view]) loaders[view]();
    },

    // ── Sidebar Toggle ───────────────────────────────

    toggleSidebar: function() {
        var sidebar = $("sidebar");
        var icon = $("sidebar-collapse-icon");
        sidebar.classList.toggle("collapsed");
        if (sidebar.classList.contains("collapsed")) {
            icon.style.transform = "rotate(180deg)";
        } else {
            icon.style.transform = "";
        }
    },

    // ── Dashboard Chat Toggle ─────────────────────────

    toggleDashboardChat: function() {
        var panel = $("dashboard-chat");
        if (!panel) return;
        var isOpen = panel.style.transform === "translateX(0px)" || panel.style.transform === "translateX(0%)";
        panel.style.transform = isOpen ? "translateX(100%)" : "translateX(0px)";
    },

    // ── 3D Body Map Initialization ───────────────────

    initBodyMap3D: function() {
        if (typeof THREE === "undefined") {
            // Three.js module still loading — wait for it
            window.addEventListener("three-ready", function() { App.initBodyMap3D(); }, { once: true });
            return;
        }
        if (typeof BodyMap3D !== "undefined" && !BodyMap3D.initialized) {
            BodyMap3D.init("bodymap-canvas-container");
        } else if (typeof BodyMap3D !== "undefined" && BodyMap3D.initialized) {
            // Already initialized — just refresh findings if profile loaded
            BodyMap3D.loadFindings();
        }
    },

    // ── Demo Data ──────────────────────────────────────

    loadDemoData: async function() {
        try {
            await api("/api/demo-data", { method: "POST" });
            App.loadDashboard();
            // Reload whichever view is active
            var active = document.querySelector(".nav-link.active");
            if (active) {
                var view = active.getAttribute("data-view");
                if (view && App.viewLoaders[view]) App.viewLoaders[view]();
            }
        } catch (e) {
            // Silent fail
        }
    },

    // ── File Upload ───────────────────────────────────

    handleDrop: function(event) {
        event.preventDefault();
        $("drop-zone").classList.remove("drag-over");
        var files = event.dataTransfer.files;
        if (files.length) App.handleFiles(files);
    },

    handleFiles: async function(files) {
        var formData = new FormData();
        for (var i = 0; i < files.length; i++) {
            formData.append("files", files[i]);
        }

        try {
            var result = await api("/api/upload", {
                method: "POST",
                body: formData,
            });

            for (var j = 0; j < result.files.length; j++) {
                App.uploadedFiles.push(result.files[j]);
            }
            App.renderFileList();
            $("files-card").style.display = "block";
        } catch (e) {
            alert("Upload failed: " + e.message);
        }
    },

    renderFileList: function() {
        var html = "";
        for (var i = 0; i < App.uploadedFiles.length; i++) {
            var f = App.uploadedFiles[i];
            var size = (f.size / 1024).toFixed(1);
            html += '<div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--border-faint); font-size:14px;">'
                + "<span>" + escapeHtml(f.name) + "</span>"
                + '<span style="color:var(--text-muted);">' + escapeHtml(size) + " KB</span>"
                + "</div>";
        }
        safeSetHtml("file-list", html);
    },

    // ── Analysis Pipeline ─────────────────────────────

    startAnalysis: async function() {
        try {
            await api("/api/analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });

            $("upload-card").style.display = "none";
            $("files-card").style.display = "none";
            $("progress-card").style.display = "block";
            $("actions-card").style.display = "none";

            App.listenProgress();
        } catch (e) {
            alert("Failed to start analysis: " + e.message);
        }
    },

    _evtSource: null,

    _appendTerminalLine: function(timeStr, message, color) {
        var terminal = $("pipeline-terminal");
        if (!terminal) return;
        var line = document.createElement("div");
        var tsSpan = document.createElement("span");
        tsSpan.style.color = "#484f58";
        tsSpan.textContent = timeStr + " ";
        var msgSpan = document.createElement("span");
        msgSpan.style.color = color;
        msgSpan.textContent = message;
        line.appendChild(tsSpan);
        line.appendChild(msgSpan);
        terminal.appendChild(line);
        terminal.scrollTop = terminal.scrollHeight;
    },

    listenProgress: function() {
        App._evtSource = new EventSource("/api/progress");
        var terminal = $("pipeline-terminal");
        if (terminal) terminal.textContent = "";

        App._evtSource.onmessage = function(event) {
            var data = JSON.parse(event.data);

            if (data.pass === "heartbeat") return;

            // Update progress bar
            if (data.percent >= 0) {
                $("progress-fill").style.width = data.percent + "%";
                $("progress-text").textContent = data.message;
            }

            // Append to terminal
            var ts = new Date(data.timestamp * 1000);
            var timeStr = ts.toLocaleTimeString("en-US", {hour12:false, hour:"2-digit", minute:"2-digit", second:"2-digit"});
            var color = "#8b949e";
            if (data.pass === "error") color = "#f85149";
            else if (data.pass === "complete") color = "#3fb950";
            else if (data.pass === "log") color = "#7d8590";
            else if (data.pass && data.pass.startsWith("pass_")) color = "#58a6ff";
            App._appendTerminalLine(timeStr, data.message, color);

            if (data.pass === "paused") {
                $("pause-btn").textContent = "Resume";
                $("pause-btn").style.background = "var(--accent-green, #3fb950)";
                $("progress-text").textContent = "Paused \u2014 safe to close laptop";
            }

            if (data.pass === "complete") {
                App._evtSource.close();
                $("progress-card").style.display = "none";
                $("actions-card").style.display = "block";
                App.loadAllData();
            }

            if (data.pass === "error") {
                App._evtSource.close();
                $("progress-text").textContent = data.message;
                $("progress-fill").style.background = "var(--accent-red)";
            }
        };

        App._evtSource.onerror = function() {
            App._evtSource.close();
        };
    },

    togglePause: async function() {
        try {
            var resp = await fetch("/api/pipeline/pause", {method: "POST"});
            var data = await resp.json();
            var btn = $("pause-btn");
            if (data.state === "paused") {
                btn.textContent = "Resume";
                btn.style.background = "var(--accent-green, #3fb950)";
            } else {
                btn.textContent = "Pause";
                btn.style.background = "var(--accent-amber, #f59e0b)";
            }
        } catch (e) {
            console.error("Pause toggle failed:", e);
        }
    },

    // ── Load All Data ─────────────────────────────────

    loadAllData: async function() {
        App.loadDashboard();
        // Other views load on demand when navigated to
    },

    // ── Dashboard ─────────────────────────────────────

    loadDashboard: async function() {
        try {
            var data = await api("/api/dashboard");
            if (!data.has_data) return;

            var hasDC = typeof DashboardCharts !== "undefined";

            // ── KPI Cards ─────────────────────────────────────
            var kpiMed = $("kpi-med-count");
            if (kpiMed) kpiMed.textContent = data.active_medications || 0;

            var kpiDx = $("kpi-dx-count");
            if (kpiDx) kpiDx.textContent = data.diagnoses_count || 0;

            var kpiFlags = $("kpi-flags-count");
            if (kpiFlags) kpiFlags.textContent = data.flags_count || 0;

            var kpiSym = $("kpi-symptom-count");
            if (kpiSym) kpiSym.textContent = data.symptoms_count || 0;

            var kpiLab = $("kpi-lab-count");
            if (kpiLab) kpiLab.textContent = (data.latest_labs || []).length;

            // PGx badge on KPI card
            if (data.pgx_collisions > 0) {
                var pgxBadge = $("kpi-pgx-badge");
                if (pgxBadge) {
                    pgxBadge.textContent = data.pgx_collisions + " PGx alert" + (data.pgx_collisions > 1 ? "s" : "");
                    pgxBadge.style.display = "inline-block";
                }
            }

            // Risk score — gauge or number
            var riskScore = data.risk_score || 0;
            var riskEl = $("dash-risk-score");
            if (riskEl) {
                riskEl.textContent = riskScore;
                if (riskScore <= 25) riskEl.style.color = "#5cd47f";
                else if (riskScore <= 50) riskEl.style.color = "#f0c550";
                else if (riskScore <= 75) riskEl.style.color = "#f05545";
                else riskEl.style.color = "#dc2626";
            }
            if (hasDC && riskScore > 0) {
                DashboardCharts.renderRiskGauge("dash-risk-gauge", riskScore, 100);
            }

            // ── Blood Panel — D3 range bars ───────────────────
            if (data.latest_labs && data.latest_labs.length > 0 && hasDC) {
                DashboardCharts.renderLabRangeBars("dash-blood-panel", data.latest_labs, { maxItems: 10 });
            }

            // ── Medications — donut by route/category ─────────
            if (data.medications_breakdown && data.medications_breakdown.length > 0 && hasDC) {
                DashboardCharts.renderDonut("dash-med-chart", data.medications_breakdown, {
                    size: 130, thickness: 22,
                    centerText: data.active_medications,
                    centerLabel: "active",
                });
            }
            // PGx alert below donut
            if (data.pgx_collisions > 0) {
                var pgxEl = $("dash-pgx-alert");
                if (pgxEl) {
                    pgxEl.textContent = data.pgx_collisions + " drug-gene interaction" + (data.pgx_collisions > 1 ? "s" : "") + " detected";
                    pgxEl.style.display = "block";
                }
            }

            // ── Lab Trends — full line chart ──────────────────
            if (data.lab_trends && Object.keys(data.lab_trends).length > 0 && hasDC) {
                var trendNames = Object.keys(data.lab_trends);
                var trendSeries = [];
                var linePal = DashboardCharts.linePalette || DashboardCharts.palette;
                for (var t = 0; t < Math.min(trendNames.length, 8); t++) {
                    var tn = trendNames[t];
                    trendSeries.push({
                        name: tn,
                        color: linePal[t % linePal.length],
                        points: data.lab_trends[tn].map(function(p) {
                            return { date: p.date, value: p.value };
                        }),
                    });
                }
                DashboardCharts.renderLineChart("dash-lab-trends", trendSeries, {
                    height: 200,
                    label: trendNames.length === 1 ? trendNames[0] : "",
                });
            } else if (data.lab_trends && Object.keys(data.lab_trends).length > 0) {
                // Fallback to sparklines
                var trendsEl = $("dash-lab-trends");
                if (trendsEl) {
                    while (trendsEl.firstChild) trendsEl.removeChild(trendsEl.firstChild);
                    var sparkNames = Object.keys(data.lab_trends);
                    for (var s = 0; s < Math.min(sparkNames.length, 4); s++) {
                        var sn = sparkNames[s];
                        var trendRow = document.createElement("div");
                        trendRow.style.cssText = "display:flex; align-items:center; gap:8px; margin-bottom:8px;";
                        var label = document.createElement("span");
                        label.textContent = sn;
                        label.style.cssText = "font-size:12px; color:var(--text-muted); width:80px; flex-shrink:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;";
                        trendRow.appendChild(label);
                        var sparkC = document.createElement("div");
                        sparkC.id = "spark-" + sn.replace(/[^a-zA-Z0-9]/g, "-");
                        sparkC.style.cssText = "flex:1; height:24px;";
                        trendRow.appendChild(sparkC);
                        trendsEl.appendChild(trendRow);
                        if (typeof Sparkline !== "undefined") Sparkline.render(sparkC.id, data.lab_trends[sn]);
                    }
                }
            }

            // ── Conditions — horizontal bar chart ─────────────
            if (data.diagnoses_list && data.diagnoses_list.length > 0 && hasDC) {
                var sevScore = { critical: 4, high: 3, moderate: 2, low: 1, info: 0 };
                var dxItems = data.diagnoses_list.map(function(dx, i) {
                    return {
                        label: dx.name,
                        value: sevScore[dx.severity] || 1,
                        color: { critical: "#dc2626", high: "#f05545", moderate: "#f0c550", low: "#5cd47f", info: "#5a8ffc" }[dx.severity] || "#5a8ffc",
                    };
                });
                DashboardCharts.renderHBars("dash-dx-chart", dxItems, { maxItems: 8 });
            }

            // ── Flags — donut by severity + stacked bar ───────
            if (data.flags_by_severity && hasDC) {
                var sevSegs = [];
                var sevColors = {
                    critical: { color: "#C84040", colorDark: "#8B1A1A" },
                    high:     { color: "#C87850", colorDark: "#984828" },
                    moderate: { color: "#C8A848", colorDark: "#987820" },
                    low:      { color: "#58B888", colorDark: "#308860" },
                };
                var sevOrder = ["critical", "high", "moderate", "low"];
                for (var sv = 0; sv < sevOrder.length; sv++) {
                    var key = sevOrder[sv];
                    if (data.flags_by_severity[key] > 0) {
                        sevSegs.push({
                            label: key.charAt(0).toUpperCase() + key.slice(1),
                            value: data.flags_by_severity[key],
                            color: sevColors[key].color,
                            colorDark: sevColors[key].colorDark,
                        });
                    }
                }
                if (sevSegs.length > 0) {
                    DashboardCharts.renderDonut("dash-flags-chart", sevSegs, {
                        size: 120, thickness: 18,
                        centerText: data.flags_count,
                        centerLabel: "flags",
                        centerColor: "#C87850",
                    });
                    DashboardCharts.renderSeverityBar("dash-flags-severity-bar", data.flags_by_severity);
                }
            }

            // ── Symptoms — vertical bar chart ─────────────────
            if (data.symptoms_list && data.symptoms_list.length > 0 && hasDC) {
                var symItems = data.symptoms_list.slice(0, 8).map(function(s) {
                    return { label: s.name, value: s.episodes };
                });
                DashboardCharts.renderBarChart("dash-symptom-chart", symItems, { height: 160 });
            }

            // ── Cross-Specialty Patterns ──────────────────────
            if (data.cross_specialty_list && data.cross_specialty_list.length > 0) {
                var csEl = $("dash-cross-spec");
                if (csEl) {
                    while (csEl.firstChild) csEl.removeChild(csEl.firstChild);
                    for (var c = 0; c < data.cross_specialty_list.length; c++) {
                        var pat = data.cross_specialty_list[c];
                        var patDiv = document.createElement("div");
                        patDiv.style.cssText = "padding:8px 12px; margin-bottom:8px; border-radius:8px; background:rgba(240,197,80,0.08); border-left:3px solid var(--honey);";
                        var patTitle = document.createElement("div");
                        patTitle.textContent = pat.title;
                        patTitle.style.cssText = "font-size:13px; font-weight:600; color:var(--text-primary); margin-bottom:4px;";
                        patDiv.appendChild(patTitle);
                        if (pat.specialties && pat.specialties.length > 0) {
                            var specSpan = document.createElement("div");
                            specSpan.textContent = pat.specialties.join(" · ");
                            specSpan.style.cssText = "font-size:11px; color:var(--honey);";
                            patDiv.appendChild(specSpan);
                        }
                        csEl.appendChild(patDiv);
                    }
                }
            }

            // ── Overdue / Missing Tests — table-style ─────────
            if (data.missing_tests && data.missing_tests.length > 0) {
                var overdueEl = $("dash-overdue");
                if (overdueEl) {
                    while (overdueEl.firstChild) overdueEl.removeChild(overdueEl.firstChild);
                    // Table header
                    var hdr = document.createElement("div");
                    hdr.style.cssText = "display:grid; grid-template-columns:1fr auto; gap:16px; padding:6px 0; border-bottom:1px solid var(--border-faint); font-size:11px; font-weight:600; color:var(--text-muted);";
                    var h1 = document.createElement("span"); h1.textContent = "TEST";
                    var h2 = document.createElement("span"); h2.textContent = "STATUS";
                    hdr.appendChild(h1); hdr.appendChild(h2);
                    overdueEl.appendChild(hdr);
                    for (var m = 0; m < data.missing_tests.length; m++) {
                        var test = data.missing_tests[m];
                        var testRow = document.createElement("div");
                        testRow.style.cssText = "display:grid; grid-template-columns:1fr auto; gap:16px; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.03); font-size:13px;";
                        var nameCell = document.createElement("span");
                        nameCell.textContent = test.title || test.missing_test || "—";
                        nameCell.style.color = "var(--text-primary)";
                        var statusCell = document.createElement("span");
                        statusCell.textContent = "OVERDUE";
                        statusCell.style.cssText = "font-size:11px; font-weight:600; padding:2px 8px; border-radius:4px; background:rgba(240,197,80,0.15); color:#f0c550;";
                        testRow.appendChild(nameCell); testRow.appendChild(statusCell);
                        overdueEl.appendChild(testRow);
                    }
                }
            }

            // Show actions, hide upload
            $("actions-card").style.display = "block";
            $("upload-card").style.display = "none";
            $("files-card").style.display = "none";
        } catch (e) {
            // No data yet, keep defaults
        }
    },

    // ── Medications ───────────────────────────────────

    loadMedications: async function() {
        try {
            var results = await Promise.all([
                api("/api/medications"),
                api("/api/interactions"),
            ]);
            var meds = results[0];
            var interactions = results[1];

            var tbody = $("meds-active-body");
            if (!meds.length) {
                safeSetHtml(tbody, '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No medications found</td></tr>');
                return;
            }

            var html = "";
            for (var i = 0; i < meds.length; i++) {
                var m = meds[i];
                var statusBadge = m.status === "active"
                    ? ' <span class="badge badge-active">Active</span>'
                    : "";
                html += "<tr>"
                    + "<td><strong>" + escapeHtml(m.name) + "</strong>" + statusBadge + "</td>"
                    + "<td>" + escapeHtml(m.dosage || "\u2014") + "</td>"
                    + "<td>" + escapeHtml(m.frequency || "\u2014") + "</td>"
                    + "<td>" + escapeHtml(m.reason || "\u2014") + "</td>"
                    + "<td>" + formatDate(m.start_date) + "</td>"
                    + '<td style="font-size:12px; color:var(--text-muted);">' + formatProvenance(m.provenance) + "</td>"
                    + "</tr>";
            }
            safeSetHtml(tbody, html);

            // Drug interactions
            if (interactions.length) {
                $("interactions-card").style.display = "block";
                var iHtml = "";
                for (var j = 0; j < interactions.length; j++) {
                    var ix = interactions[j];
                    var drugPair = escapeHtml(ix.drug_a);
                    if (ix.drug_b) drugPair += " + " + escapeHtml(ix.drug_b);
                    if (ix.gene) drugPair += " / " + escapeHtml(ix.gene);

                    iHtml += '<div style="padding:12px 0; border-bottom:1px solid var(--border-faint);">'
                        + '<div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">'
                        + severityBadge(ix.severity)
                        + "<strong>" + drugPair + "</strong>"
                        + "</div>"
                        + '<div style="color:var(--text-secondary); font-size:13px;">' + escapeHtml(ix.description || "") + "</div>"
                        + '<div style="color:var(--text-muted); font-size:12px; margin-top:4px;">' + escapeHtml(ix.source || "") + "</div>"
                        + "</div>";
                }
                safeSetHtml("interactions-list", iHtml);
            }
        } catch (e) { /* no data */ }
    },

    // ── Labs ──────────────────────────────────────────

    loadLabs: async function() {
        try {
            var labs = await api("/api/labs");
            var tbody = $("labs-body");
            while (tbody && tbody.firstChild) tbody.removeChild(tbody.firstChild);

            if (!labs.length) {
                var emptyRow = document.createElement("tr");
                var emptyCell = document.createElement("td");
                emptyCell.colSpan = 6;
                emptyCell.style.textAlign = "center";
                emptyCell.style.color = "var(--text-muted)";
                emptyCell.textContent = "No lab results found";
                emptyRow.appendChild(emptyCell);
                tbody.appendChild(emptyRow);
                return;
            }

            var normalizedLabs = labs.map(function(lab, index) {
                return App._normalizeLabRecord(lab, index);
            });

            // Sort: flagged first, then by date
            var sorted = normalizedLabs.slice().sort(function(a, b) {
                var aFlag = App._isFlaggedLab(a.flag) ? 0 : 1;
                var bFlag = App._isFlaggedLab(b.flag) ? 0 : 1;
                if (aFlag !== bFlag) return aFlag - bFlag;
                return (b.test_date || "").localeCompare(a.test_date || "");
            });

            for (var i = 0; i < sorted.length; i++) {
                App._appendLabRows(tbody, sorted[i], normalizedLabs);
            }
        } catch (e) { /* no data */ }
    },

    _normalizeLabRecord: function(lab, index) {
        var knownKeys = {
            name: true,
            test_name: true,
            value: true,
            value_text: true,
            unit: true,
            flag: true,
            test_date: true,
            date: true,
            reference_low: true,
            reference_high: true,
            ordering_provider: true,
            provider: true,
            lab_facility: true,
            facility: true,
            loinc_code: true,
            provenance: true,
            panel_name: true,
            description: true,
            summary: true,
            interpretation: true,
            note: true,
            notes: true,
            raw_text: true,
            source_file: true,
            source_page: true,
            confidence: true,
        };

        var normalized = {
            _labKey: "lab:" + index,
            _original: lab,
            name: lab.name || lab.test_name || "Lab Result",
            value: lab.value,
            value_text: lab.value_text,
            unit: lab.unit || "",
            flag: lab.flag || "",
            test_date: lab.test_date || lab.date || "",
            reference_low: lab.reference_low,
            reference_high: lab.reference_high,
            provider: lab.ordering_provider || lab.provider || "",
            facility: lab.lab_facility || lab.facility || "",
            loinc_code: lab.loinc_code || "",
            panel_name: lab.panel_name || "",
            description: lab.description || lab.summary || "",
            interpretation: lab.interpretation || lab.note || lab.notes || "",
            provenance: lab.provenance || null,
            extra_fields: [],
        };

        for (var key in lab) {
            if (!Object.prototype.hasOwnProperty.call(lab, key) || knownKeys[key]) continue;
            if (lab[key] == null || String(lab[key]).trim() === "") continue;
            normalized.extra_fields.push({
                key: key,
                label: labelizeKey(key),
                value: lab[key],
            });
        }

        return normalized;
    },

    _appendLabRows: function(tbody, lab, allLabs) {
        var mainRow = document.createElement("tr");
        mainRow.className = "lab-row-main";
        mainRow.tabIndex = 0;
        mainRow.setAttribute("role", "button");
        mainRow.setAttribute("aria-expanded", "false");

        var detailRow = document.createElement("tr");
        detailRow.className = "lab-row-detail";
        detailRow.style.display = "none";

        var detailCell = document.createElement("td");
        detailCell.colSpan = 6;
        detailRow.appendChild(detailCell);

        var testCell = document.createElement("td");
        var testWrap = document.createElement("div");
        testWrap.className = "lab-test-cell";

        var nameEl = document.createElement("strong");
        nameEl.className = "lab-test-name";
        nameEl.textContent = lab.name;
        testWrap.appendChild(nameEl);

        var glossary = getLabGlossaryEntry(lab.name);
        if (glossary) {
            var tooltip = document.createElement("span");
            tooltip.className = "info-tooltip lab-info-tooltip";

            var trigger = document.createElement("button");
            trigger.type = "button";
            trigger.className = "lab-info-trigger";
            trigger.setAttribute("aria-label", "About " + lab.name);
            trigger.textContent = "i";
            trigger.addEventListener("click", function(event) {
                event.stopPropagation();
            });
            tooltip.appendChild(trigger);

            var tooltipText = document.createElement("span");
            tooltipText.className = "tooltip-text";
            tooltipText.textContent = glossary.fullName + ". " + glossary.summary;
            tooltip.appendChild(tooltipText);

            testWrap.appendChild(tooltip);
        }
        testCell.appendChild(testWrap);
        mainRow.appendChild(testCell);

        var valueCell = document.createElement("td");
        var value = lab.value != null ? lab.value : (lab.value_text || "\u2014");
        valueCell.textContent = String(value);
        mainRow.appendChild(valueCell);

        var unitCell = document.createElement("td");
        unitCell.textContent = lab.unit || "";
        mainRow.appendChild(unitCell);

        var flagCell = document.createElement("td");
        flagCell.appendChild(App._buildLabFlagBadge(lab.flag));
        mainRow.appendChild(flagCell);

        var dateCell = document.createElement("td");
        dateCell.textContent = formatDate(lab.test_date);
        mainRow.appendChild(dateCell);

        var sourceCell = document.createElement("td");
        sourceCell.className = "lab-source-cell";
        sourceCell.textContent = App._labSourceText(lab);
        mainRow.appendChild(sourceCell);

        App._populateLabDetail(detailCell, lab, allLabs);

        function toggleRow() {
            var isOpen = detailRow.style.display !== "none";
            detailRow.style.display = isOpen ? "none" : "";
            mainRow.classList.toggle("is-open", !isOpen);
            mainRow.setAttribute("aria-expanded", isOpen ? "false" : "true");
        }

        mainRow.addEventListener("click", toggleRow);
        mainRow.addEventListener("keydown", function(event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                toggleRow();
            }
        });

        tbody.appendChild(mainRow);
        tbody.appendChild(detailRow);
    },

    _populateLabDetail: function(container, lab, allLabs) {
        var panel = document.createElement("div");
        panel.className = "lab-detail-panel";

        var header = document.createElement("div");
        header.className = "lab-detail-header";

        var titleBlock = document.createElement("div");
        var title = document.createElement("div");
        title.className = "lab-detail-title";
        title.textContent = lab.name;
        titleBlock.appendChild(title);

        var glossary = getLabGlossaryEntry(lab.name);
        if (glossary) {
            var subtitle = document.createElement("div");
            subtitle.className = "lab-detail-subtitle";
            subtitle.textContent = glossary.fullName + ". " + glossary.summary;
            titleBlock.appendChild(subtitle);
        }
        header.appendChild(titleBlock);

        var currentValue = document.createElement("div");
        currentValue.className = "lab-detail-current";
        currentValue.textContent = App._compactLabParts([
            lab.value != null ? lab.value : lab.value_text,
            lab.unit,
            App._normalizedFlagLabel(lab.flag),
        ]) || "No value available";
        header.appendChild(currentValue);
        panel.appendChild(header);

        var grid = document.createElement("div");
        grid.className = "lab-detail-grid";
        App._appendLabDetailField(grid, "Date", formatDate(lab.test_date));
        App._appendLabDetailField(grid, "Reference Range", App._formatLabReferenceRange(lab.reference_low, lab.reference_high, lab.unit));
        App._appendLabDetailField(grid, "Provider", lab.provider);
        App._appendLabDetailField(grid, "Facility", lab.facility);
        App._appendLabDetailField(grid, "LOINC", lab.loinc_code);
        App._appendLabDetailField(grid, "Panel", lab.panel_name);
        if (grid.childNodes.length) {
            panel.appendChild(grid);
        }

        App._appendLabDetailBody(panel, "Description", lab.description);
        App._appendLabDetailBody(panel, "Interpretation", lab.interpretation);

        if (lab.extra_fields && lab.extra_fields.length) {
            var extraTitle = document.createElement("div");
            extraTitle.className = "lab-detail-section-title";
            extraTitle.textContent = "Additional Details";
            panel.appendChild(extraTitle);

            var extraGrid = document.createElement("div");
            extraGrid.className = "lab-detail-grid";
            for (var i = 0; i < lab.extra_fields.length; i++) {
                App._appendLabDetailField(extraGrid, lab.extra_fields[i].label, lab.extra_fields[i].value);
            }
            if (extraGrid.childNodes.length) {
                panel.appendChild(extraGrid);
            }
        }

        var history = allLabs
            .filter(function(other) { return normalizeLabGlossaryKey(other.name) === normalizeLabGlossaryKey(lab.name); })
            .sort(function(a, b) { return (b.test_date || "").localeCompare(a.test_date || ""); });

        if (history.length > 1) {
            var historyTitle = document.createElement("div");
            historyTitle.className = "lab-detail-section-title";
            historyTitle.textContent = "Recent History";
            panel.appendChild(historyTitle);

            var historyWrap = document.createElement("div");
            historyWrap.className = "lab-history-chips";

            for (var hi = 0; hi < Math.min(history.length, 6); hi++) {
                var chip = document.createElement("div");
                chip.className = "lab-history-chip";

                var chipValue = document.createElement("div");
                chipValue.className = "lab-history-value";
                chipValue.textContent = App._compactLabParts([
                    history[hi].value != null ? history[hi].value : history[hi].value_text,
                    history[hi].unit,
                ]) || "No value";
                chip.appendChild(chipValue);

                var chipMeta = document.createElement("div");
                chipMeta.className = "lab-history-meta";
                chipMeta.textContent = formatDate(history[hi].test_date) + (
                    App._normalizedFlagLabel(history[hi].flag) ? " • " + App._normalizedFlagLabel(history[hi].flag) : ""
                );
                chip.appendChild(chipMeta);

                historyWrap.appendChild(chip);
            }

            panel.appendChild(historyWrap);
        }

        var sourceText = App._labSourceText(lab);
        if (sourceText || (lab.provenance && lab.provenance.raw_text)) {
            var sourceTitle = document.createElement("div");
            sourceTitle.className = "lab-detail-section-title";
            sourceTitle.textContent = "Source";
            panel.appendChild(sourceTitle);

            var sourceBox = document.createElement("div");
            sourceBox.className = "lab-detail-source";
            if (sourceText) {
                var sourceMeta = document.createElement("div");
                sourceMeta.className = "lab-detail-source-meta";
                sourceMeta.textContent = sourceText;
                sourceBox.appendChild(sourceMeta);
            }

            if (lab.provenance && lab.provenance.raw_text) {
                var raw = document.createElement("div");
                raw.className = "lab-detail-source-copy";
                raw.textContent = lab.provenance.raw_text;
                sourceBox.appendChild(raw);
            }
            panel.appendChild(sourceBox);
        }

        container.appendChild(panel);
    },

    _appendLabDetailField: function(container, label, value) {
        if (!value && value !== 0) return;

        var field = document.createElement("div");
        field.className = "lab-detail-field";

        var labelEl = document.createElement("div");
        labelEl.className = "lab-detail-field-label";
        labelEl.textContent = label;
        field.appendChild(labelEl);

        var valueEl = document.createElement("div");
        valueEl.className = "lab-detail-field-value";
        valueEl.textContent = App._labDisplayValue(value);
        field.appendChild(valueEl);

        container.appendChild(field);
    },

    _appendLabDetailBody: function(container, label, value) {
        if (!value && value !== 0) return;

        var block = document.createElement("div");
        block.className = "lab-detail-body-block";

        var labelEl = document.createElement("div");
        labelEl.className = "lab-detail-field-label";
        labelEl.textContent = label;
        block.appendChild(labelEl);

        var valueEl = document.createElement("div");
        valueEl.className = "lab-detail-body-copy";
        valueEl.textContent = App._labDisplayValue(value);
        block.appendChild(valueEl);

        container.appendChild(block);
    },

    _buildLabFlagBadge: function(flag) {
        var wrapper = document.createElement("span");
        var normalized = String(flag || "").trim().toLowerCase();

        if (normalized === "high" || normalized === "critical high" || normalized === "h") {
            wrapper.className = "badge badge-high";
            wrapper.textContent = "HIGH";
        } else if (normalized === "low" || normalized === "critical low" || normalized === "l") {
            wrapper.className = "badge badge-moderate";
            wrapper.textContent = "LOW";
        } else if (normalized && normalized !== "normal") {
            wrapper.className = "badge badge-warning";
            wrapper.textContent = String(flag);
        } else {
            wrapper.className = "badge badge-active";
            wrapper.textContent = "Normal";
        }

        return wrapper;
    },

    _normalizedFlagLabel: function(flag) {
        var normalized = String(flag || "").trim().toLowerCase();
        if (!normalized || normalized === "normal") return "";
        if (normalized === "h" || normalized === "high" || normalized === "critical high") return "High";
        if (normalized === "l" || normalized === "low" || normalized === "critical low") return "Low";
        return String(flag);
    },

    _isFlaggedLab: function(flag) {
        var normalized = String(flag || "").trim().toLowerCase();
        return !!normalized && normalized !== "normal";
    },

    _formatLabReferenceRange: function(low, high, unit) {
        if (low == null && high == null) return "";
        var range = "";
        if (low != null && high != null) {
            range = low + " to " + high;
        } else if (low != null) {
            range = ">= " + low;
        } else {
            range = "<= " + high;
        }
        if (unit) range += " " + unit;
        return range;
    },

    _compactLabParts: function(parts) {
        return parts
            .filter(function(part) {
                return part !== null && part !== undefined && String(part).trim() !== "";
            })
            .join(" ");
    },

    _labSourceText: function(lab) {
        var parts = [];
        var provenance = lab.provenance || {};
        if (provenance.source_file) parts.push(provenance.source_file);
        if (provenance.source_page) parts.push("p." + provenance.source_page);
        if (provenance.extraction_model) parts.push(provenance.extraction_model);
        if (parts.length) return parts.join(", ");

        return [lab.provider, lab.facility]
            .filter(function(part) { return !!part; })
            .join(", ");
    },

    _labDisplayValue: function(value) {
        if (value == null) return "";
        if (Array.isArray(value)) {
            return value.map(function(item) { return App._labDisplayValue(item); }).join(", ");
        }
        if (typeof value === "object") {
            try {
                return JSON.stringify(value);
            } catch (e) {
                return String(value);
            }
        }
        return String(value);
    },

    // ── Imaging ───────────────────────────────────────

    loadImaging: async function() {
        try {
            var studies = await api("/api/imaging");
            var container = $("imaging-list");

            if (!studies.length) {
                safeSetHtml(container, '<div style="color:var(--text-muted); text-align:center; padding:40px;">No imaging studies found</div>');
                return;
            }

            var html = "";
            for (var i = 0; i < studies.length; i++) {
                var s = studies[i];
                var findingsHtml = "";
                var findings = s.findings || [];
                for (var j = 0; j < findings.length; j++) {
                    var f = findings[j];
                    findingsHtml += '<div style="padding:8px 12px; background:var(--bg-raised); border-radius:8px; margin-top:8px;">'
                        + '<div style="font-size:14px;">' + escapeHtml(f.description || "") + "</div>"
                        + (f.body_region ? '<div style="font-size:12px; color:var(--text-muted); margin-top:4px;">Region: ' + escapeHtml(f.body_region) + "</div>" : "")
                        + (f.confidence ? '<div style="font-size:12px; color:var(--text-muted);">Confidence: ' + Math.round(f.confidence * 100) + "%</div>" : "")
                        + "</div>";
                }

                html += '<div style="padding:16px 0; border-bottom:1px solid var(--border-faint);">'
                    + '<div style="display:flex; justify-content:space-between; align-items:center;">'
                    + "<div>"
                    + "<strong>" + escapeHtml(s.modality || "Study") + " \u2014 " + escapeHtml(s.body_region || "") + "</strong>"
                    + '<div style="color:var(--text-secondary); font-size:13px; margin-top:4px;">' + escapeHtml(s.description || "") + "</div>"
                    + "</div>"
                    + '<div style="font-size:13px; color:var(--text-muted);">' + formatDate(s.study_date) + "</div>"
                    + "</div>"
                    + (findingsHtml ? '<div style="margin-top:8px;"><div style="font-size:12px; color:var(--text-secondary); margin-bottom:4px;">Findings:</div>' + findingsHtml + "</div>" : "")
                    + '<div style="font-size:12px; color:var(--text-muted); margin-top:8px;">' + formatProvenance(s.provenance) + "</div>"
                    + "</div>";
            }
            safeSetHtml(container, html);
        } catch (e) { /* no data */ }
    },

    // ── Genetics ──────────────────────────────────────

    loadGenetics: async function() {
        try {
            var variants = await api("/api/genetics");
            var tbody = $("genetics-body");

            if (!variants.length) {
                safeSetHtml(tbody, '<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">No genetic data found</td></tr>');
                return;
            }

            var html = "";
            for (var i = 0; i < variants.length; i++) {
                var g = variants[i];
                var sigBadge = (g.clinical_significance || "").toLowerCase() === "actionable"
                    ? '<span class="badge badge-high">Actionable</span>'
                    : '<span class="badge badge-info">' + escapeHtml(g.clinical_significance || "Unknown") + "</span>";

                html += "<tr>"
                    + "<td><strong>" + escapeHtml(g.gene || "\u2014") + "</strong></td>"
                    + "<td>" + escapeHtml(g.variant || "\u2014") + "</td>"
                    + "<td>" + escapeHtml(g.phenotype || "\u2014") + "</td>"
                    + "<td>" + sigBadge + "</td>"
                    + '<td style="font-size:13px;">' + escapeHtml(g.implications || "\u2014") + "</td>"
                    + "</tr>";
            }
            safeSetHtml(tbody, html);
        } catch (e) { /* no data */ }
    },

    // ── Flags & Patterns ──────────────────────────────

    loadFlags: async function() {
        try {
            var flags = await api("/api/flags");
            var container = $("flags-list");

            if (!flags.length) {
                safeSetHtml(container, '<div style="color:var(--text-muted); text-align:center; padding:40px;">No flags detected</div>');
                return;
            }

            // Sort by severity
            var order = { critical: 0, high: 1, moderate: 2, low: 3, info: 4 };
            var sorted = flags.slice().sort(function(a, b) {
                return (order[(a.severity || "info").toLowerCase()] || 4) -
                       (order[(b.severity || "info").toLowerCase()] || 4);
            });

            var html = "";
            for (var i = 0; i < sorted.length; i++) {
                var f = sorted[i];
                var evidenceHtml = "";
                if (f.evidence && f.evidence.length) {
                    for (var j = 0; j < f.evidence.length; j++) {
                        evidenceHtml += '<div style="font-size:12px; color:var(--text-muted); padding:2px 0;">'
                            + escapeHtml(f.evidence[j]) + "</div>";
                    }
                    evidenceHtml = '<div style="margin-top:8px;">' + evidenceHtml + "</div>";
                }

                html += '<div style="padding:16px 0; border-bottom:1px solid var(--border-faint);">'
                    + '<div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">'
                    + severityBadge(f.severity)
                    + '<span class="badge badge-info">' + escapeHtml(f.category || "") + "</span>"
                    + '<strong style="font-size:15px;">' + escapeHtml(f.title || "") + "</strong>"
                    + "</div>"
                    + '<div style="color:var(--text-secondary); font-size:14px; line-height:1.6;">'
                    + escapeHtml(f.description || "") + "</div>"
                    + evidenceHtml
                    + "</div>";
            }
            safeSetHtml(container, html);
        } catch (e) { /* no data */ }
    },

    // ── Cross-Disciplinary ────────────────────────────

    loadCrossDisciplinary: async function() {
        try {
            var connections = await api("/api/cross-disciplinary");
            // Normalise: demo data uses "pattern" field, API adds "description"
            for (var i = 0; i < connections.length; i++) {
                if (!connections[i].description && connections[i].pattern) {
                    connections[i].description = connections[i].pattern;
                }
            }
            CrossDiscGraph.render("crossdisc-list", connections);
        } catch (e) { /* no data */ }
    },

    // ── Community Insights ────────────────────────────

    loadCommunity: async function() {
        try {
            var insights = await api("/api/community");
            var container = $("community-list");

            if (!insights.length) {
                safeSetHtml(container, '<div style="color:var(--text-muted); text-align:center; padding:40px;">No community insights found</div>');
                return;
            }

            var html = "";
            for (var i = 0; i < insights.length; i++) {
                var ci = insights[i];
                html += '<div style="padding:16px 0; border-bottom:1px solid var(--border-faint);">'
                    + '<div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">'
                    + "<strong>" + escapeHtml(ci.title || "Community Report") + "</strong>"
                    + '<span class="badge badge-warning">Unverified</span>'
                    + "</div>"
                    + '<div style="color:var(--text-secondary); font-size:14px; margin-bottom:8px;">'
                    + escapeHtml(ci.summary || ci.description || "") + "</div>"
                    + (ci.subreddit ? '<div style="font-size:12px; color:var(--text-muted);">r/' + escapeHtml(ci.subreddit) + " | " + escapeHtml(ci.upvotes || 0) + " upvotes</div>" : "")
                    + "</div>";
            }
            safeSetHtml(container, html);
        } catch (e) { /* no data */ }
    },

    // ── Alerts ────────────────────────────────────────

    loadAlerts: async function() {
        try {
            var alerts = await api("/api/alerts");
            var container = $("alerts-list");

            if (!alerts.length) {
                safeSetHtml(container, '<div style="color:var(--text-muted); text-align:center; padding:40px;">No alerts. Monitoring will check for new findings relevant to your profile.</div>');
                return;
            }

            var html = "";
            for (var i = 0; i < alerts.length; i++) {
                var a = alerts[i];
                html += '<div style="padding:16px 0; border-bottom:1px solid var(--border-faint);">'
                    + '<div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">'
                    + severityBadge(a.severity)
                    + "<strong>" + escapeHtml(a.title || "Alert") + "</strong>"
                    + '<span style="font-size:12px; color:var(--text-muted); margin-left:auto;">' + escapeHtml(a.source || "") + "</span>"
                    + "</div>"
                    + '<div style="color:var(--text-secondary); font-size:14px; margin-bottom:4px;">' + escapeHtml(a.description || "") + "</div>"
                    + (a.relevance_explanation ? '<div style="font-size:13px; color:var(--accent-amber); margin-top:8px;">Why this matters: ' + escapeHtml(a.relevance_explanation) + "</div>" : "")
                    + "</div>";
            }
            safeSetHtml(container, html);
        } catch (e) { /* no data */ }
    },

    // ── Environmental ──────────────────────────────────

    loadEnvironmental: async function() {
        try {
            var data = await api("/api/environmental");
            var locBadge = $("env-location-badge");
            var personalizedList = $("env-personalized-list");
            var regionalList = $("env-regional-list");
            var emptyState = $("env-empty");
            var personalizedSection = $("env-personalized");
            var regionalSection = $("env-regional");
            var focusBox = $("env-analysis-focus");
            var focusText = $("env-analysis-focus-text");
            var focusDomains = $("env-analysis-domains");
            var sourceSummary = $("env-source-summary");
            var sourceList = $("env-source-list");
            var syncStatus = $("env-sync-status");

            while (personalizedList.firstChild) personalizedList.removeChild(personalizedList.firstChild);
            while (regionalList.firstChild) regionalList.removeChild(regionalList.firstChild);
            while (focusDomains && focusDomains.firstChild) focusDomains.removeChild(focusDomains.firstChild);
            while (sourceSummary && sourceSummary.firstChild) sourceSummary.removeChild(sourceSummary.firstChild);
            while (sourceList && sourceList.firstChild) sourceList.removeChild(sourceList.firstChild);

            if (focusBox) focusBox.style.display = data && data.analysis_focus ? "block" : "none";
            if (focusText) {
                focusText.textContent = data && data.analysis_focus
                    ? (data.analysis_focus.goal || "")
                    : "";
            }
            if (focusDomains && data && data.analysis_focus && data.analysis_focus.domains) {
                for (var d = 0; d < data.analysis_focus.domains.length; d++) {
                    var domainBadge = document.createElement("div");
                    domainBadge.style.cssText = "font-size:12px; color:var(--text-primary); padding:6px 10px; border-radius:999px; border:1px solid var(--border-muted); background:rgba(255,255,255,0.03);";
                    domainBadge.textContent = data.analysis_focus.domains[d];
                    focusDomains.appendChild(domainBadge);
                }
            }

            App._renderEnvironmentalSourceCoverage(sourceSummary, sourceList, data);

            if (syncStatus) {
                var syncSettings = data && data.sync_settings ? data.sync_settings : null;
                var updatedAt = syncSettings && syncSettings.last_run_at ? syncSettings.last_run_at : "";
                var nextRun = syncSettings && syncSettings.next_run_at ? syncSettings.next_run_at : "";
                var statusBits = [];
                if (updatedAt) statusBits.push("Last sync: " + formatDate(updatedAt));
                if (syncSettings && syncSettings.enabled && nextRun) statusBits.push("Next auto-sync: " + formatDate(nextRun));
                syncStatus.style.display = statusBits.length ? "block" : "none";
                syncStatus.textContent = statusBits.join(" • ");
            }

            if (locBadge) locBadge.textContent = data && data.location ? data.location : "Location not set";

            if (!data || !data.risks || !data.risks.length) {
                emptyState.style.display = "block";
                personalizedSection.style.display = "none";
                regionalSection.style.display = "none";
                return;
            }
            emptyState.style.display = "none";
            personalizedSection.style.display = "block";
            regionalSection.style.display = "block";

            if (data.location) locBadge.textContent = data.location;

            var hasPersonalized = false, hasRegional = false;
            for (var i = 0; i < data.risks.length; i++) {
                var risk = data.risks[i];
                var card = document.createElement("div");
                var personalized = Boolean(risk.personalized || (risk.relevance_score && risk.relevance_score > 0));
                card.style.cssText = "background:var(--bg-raised); border-radius:12px; padding:16px; margin-bottom:12px; border-left:3px solid " + (personalized ? "var(--heat)" : "var(--border-muted)") + ";";

                var header = document.createElement("div");
                header.style.cssText = "display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:4px;";

                var title = document.createElement("div");
                title.style.cssText = "font-weight:500; color:var(--text-primary);";
                title.textContent = risk.name || risk.title || "Risk";
                header.appendChild(title);

                var badges = document.createElement("div");
                badges.style.cssText = "display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end;";
                badges.appendChild(App._buildEnvironmentalBadge(risk.severity || "info", "severity"));
                if (risk.category) badges.appendChild(App._buildEnvironmentalBadge(risk.category, "category"));
                header.appendChild(badges);
                card.appendChild(header);

                var desc = document.createElement("div");
                desc.style.cssText = "font-size:14px; color:var(--text-secondary); margin-bottom:8px;";
                desc.textContent = risk.description || "";
                card.appendChild(desc);

                if (risk.relevance_reasons && risk.relevance_reasons.length) {
                    var reasons = document.createElement("div");
                    reasons.style.cssText = "font-size:13px; color:var(--accent-amber); margin-bottom:8px;";
                    reasons.textContent = "Why this may matter for you: " + risk.relevance_reasons.join(" ");
                    card.appendChild(reasons);
                }

                if (risk.symptoms_to_watch && risk.symptoms_to_watch.length) {
                    var symptoms = document.createElement("div");
                    symptoms.style.cssText = "font-size:13px; color:var(--text-muted); margin-bottom:8px;";
                    symptoms.textContent = "Symptoms to watch: " + risk.symptoms_to_watch.join(", ");
                    card.appendChild(symptoms);
                }

                if (risk.action) {
                    var action = document.createElement("div");
                    action.style.cssText = "font-size:14px; color:var(--accent-teal);";
                    action.textContent = risk.action;
                    card.appendChild(action);
                }

                if (personalized) {
                    personalizedList.appendChild(card);
                    hasPersonalized = true;
                } else {
                    regionalList.appendChild(card);
                    hasRegional = true;
                }
            }
            if (!hasPersonalized) personalizedSection.style.display = "none";
            if (!hasRegional) regionalSection.style.display = "none";
        } catch (e) {
            $("env-empty").style.display = "block";
            $("env-personalized").style.display = "none";
            $("env-regional").style.display = "none";
        }
    },

    syncEnvironmentalData: async function() {
        var btn = $("env-sync-btn");
        var status = $("env-sync-status");
        if (btn) {
            btn.disabled = true;
            btn.textContent = "Syncing…";
        }
        if (status) {
            status.style.display = "block";
            status.style.color = "var(--text-secondary)";
            status.textContent = "Fetching environmental source snapshots for your saved location…";
        }

        try {
            var result = await api("/api/environmental/sync", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}",
            });

            if (status) {
                status.style.display = "block";
                status.style.color = "var(--accent-green)";
                status.textContent =
                    "Environmental sync complete. "
                    + result.summary.downloaded + " downloaded, "
                    + (result.summary.cached || 0) + " reused from cache, "
                    + result.summary.skipped + " skipped, "
                    + result.summary.errors + " errors.";
            }
            await App.loadEnvironmental();
        } catch (e) {
            if (status) {
                status.style.display = "block";
                status.style.color = "var(--accent-red)";
                status.textContent = "Environmental sync failed: " + e.message;
            }
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = "Sync Data";
            }
        }
    },

    _renderEnvironmentalSettings: function(payload) {
        var settings = payload && payload.settings ? payload.settings : {};
        var sources = payload && payload.source_catalog ? payload.source_catalog : [];
        var automatedIds = payload && payload.automated_source_ids ? payload.automated_source_ids : [];

        var enabledCheckbox = $("setting-environmental-auto-enabled");
        var intervalSelect = $("setting-environmental-auto-interval");
        var autoSources = $("settings-environmental-auto-sources");
        var autoStatus = $("settings-environmental-auto-status");
        var inventory = $("settings-environmental-sources");

        if (enabledCheckbox) enabledCheckbox.checked = Boolean(settings.enabled);
        if (intervalSelect) intervalSelect.value = String(settings.interval_hours || 24);
        if (autoSources) while (autoSources.firstChild) autoSources.removeChild(autoSources.firstChild);
        if (inventory) while (inventory.firstChild) inventory.removeChild(inventory.firstChild);

        var selectedIds = settings.source_ids || automatedIds;
        for (var i = 0; i < sources.length; i++) {
            var source = sources[i];
            if (automatedIds.indexOf(source.id) !== -1 && autoSources) {
                var option = document.createElement("label");
                option.style.cssText = "display:flex; align-items:flex-start; gap:10px; padding:10px 12px; border-radius:10px; border:1px solid var(--border-faint); background:rgba(255,255,255,0.02);";

                var input = document.createElement("input");
                input.type = "checkbox";
                input.value = source.id;
                input.checked = selectedIds.indexOf(source.id) !== -1;
                input.setAttribute("data-environmental-source-check", "1");
                option.appendChild(input);

                var text = document.createElement("div");
                text.innerHTML =
                    '<div style="font-size:13px; color:var(--text-primary); margin-bottom:3px;">' + escapeHtml(source.name || source.id) + "</div>"
                    + '<div style="font-size:12px; color:var(--text-muted); line-height:1.4;">' + escapeHtml(source.purpose || "") + "</div>";
                option.appendChild(text);
                autoSources.appendChild(option);
            }

            if (!inventory) continue;

            var card = document.createElement("div");
            card.style.cssText = "padding:12px 14px; border-radius:12px; border:1px solid var(--border-faint); background:rgba(255,255,255,0.02);";

            var header = document.createElement("div");
            header.style.cssText = "display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:6px;";
            header.innerHTML =
                '<div>'
                + '<div style="font-size:14px; color:var(--text-primary); margin-bottom:2px;">' + escapeHtml(source.name || source.id) + "</div>"
                + '<div style="font-size:12px; color:var(--text-muted);">' + escapeHtml((source.provider || "") + " • " + (source.category || "")) + "</div>"
                + "</div>";

            var right = document.createElement("div");
            right.style.cssText = "text-align:right; font-size:11px; color:var(--text-muted);";
            right.innerHTML =
                '<div style="margin-bottom:4px;">' + escapeHtml(source.auth || "") + "</div>"
                + '<div>' + escapeHtml(source.status || "") + "</div>";
            header.appendChild(right);
            card.appendChild(header);

            var details = document.createElement("div");
            details.style.cssText = "display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:8px; font-size:12px;";
            var detailFields = [
                { label: "Layer", value: source.layer },
                { label: "Cadence", value: source.cadence },
                { label: "Endpoint", value: source.endpoint },
                { label: "Last Updated", value: source.last_updated || "Not synced yet" },
                { label: "Local Data", value: source.local_path || "Not staged yet" },
            ];
            for (var d = 0; d < detailFields.length; d++) {
                var field = document.createElement("div");
                field.style.cssText = "padding:8px 10px; border-radius:10px; background:rgba(0,0,0,0.18);";
                field.innerHTML =
                    '<div style="font-size:10px; text-transform:uppercase; letter-spacing:0.08em; color:var(--text-muted); margin-bottom:4px;">'
                    + escapeHtml(detailFields[d].label)
                    + "</div>"
                    + '<div style="color:var(--text-secondary); line-height:1.5; word-break:break-word;">'
                    + escapeHtml(detailFields[d].value || "\u2014")
                    + "</div>";
                details.appendChild(field);
            }
            card.appendChild(details);

            if (source.purpose) {
                var purpose = document.createElement("div");
                purpose.style.cssText = "font-size:12px; color:var(--text-secondary); line-height:1.6; margin-top:8px;";
                purpose.textContent = source.purpose;
                card.appendChild(purpose);
            }

            if (source.coverage_notes) {
                var notes = document.createElement("div");
                notes.style.cssText = "margin-top:8px; font-size:12px; color:var(--accent-teal);";
                notes.textContent = source.coverage_notes;
                card.appendChild(notes);
            }

            inventory.appendChild(card);
        }

        if (autoStatus) {
            var statusText = [];
            statusText.push(settings.enabled ? "Automatic sync is enabled." : "Automatic sync is off.");
            if (settings.last_run_at) statusText.push("Last run: " + formatDate(settings.last_run_at));
            if (settings.next_run_at && settings.enabled) statusText.push("Next run: " + formatDate(settings.next_run_at));
            if (settings.last_error) statusText.push("Last error: " + settings.last_error);
            autoStatus.textContent = statusText.join(" ");
        }
    },

    _buildEnvironmentalBadge: function(text, kind) {
        var badge = document.createElement("div");
        var normalizedKind = String(kind || "").toLowerCase();
        var color = "var(--text-muted)";
        var border = "var(--border-muted)";

        if (normalizedKind === "severity") {
            var severity = String(text || "").toLowerCase();
            if (severity === "high") {
                color = "var(--accent-red)";
                border = "rgba(255,79,79,0.35)";
            } else if (severity === "moderate") {
                color = "var(--accent-amber)";
                border = "rgba(248,181,52,0.35)";
            } else if (severity === "low") {
                color = "var(--accent-green)";
                border = "rgba(52,211,153,0.35)";
            }
        } else if (normalizedKind === "status") {
            var status = String(text || "").toLowerCase();
            if (status.indexOf("active") !== -1) {
                color = "var(--accent-green)";
                border = "rgba(52,211,153,0.35)";
            } else if (status.indexOf("planned") !== -1) {
                color = "var(--accent-bluetron)";
                border = "rgba(80,128,176,0.35)";
            } else if (status.indexOf("candidate") !== -1) {
                color = "var(--accent-amber)";
                border = "rgba(248,181,52,0.35)";
            } else if (status.indexOf("reference") !== -1) {
                color = "var(--accent-teal)";
                border = "rgba(56,189,248,0.35)";
            }
        } else if (normalizedKind === "download") {
            var downloaded = String(text || "").toLowerCase().indexOf("downloaded") !== -1
                && String(text || "").toLowerCase().indexOf("not") === -1;
            color = downloaded ? "var(--accent-green)" : "var(--text-muted)";
            border = downloaded ? "rgba(52,211,153,0.35)" : "var(--border-muted)";
        }

        badge.style.cssText = "font-size:11px; color:" + color + "; padding:4px 8px; border-radius:999px; border:1px solid " + border + "; background:rgba(255,255,255,0.02);";
        badge.textContent = text;
        return badge;
    },

    _renderEnvironmentalSourceCoverage: function(summaryContainer, listContainer, data) {
        if (!summaryContainer || !listContainer || !data) return;

        var summary = data.source_summary || {};
        var cards = [
            {
                label: "Total Sources",
                value: summary.total_sources != null ? String(summary.total_sources) : "\u2014",
            },
            {
                label: "Downloaded Locally",
                value: summary.downloaded_sources != null ? String(summary.downloaded_sources) : "0",
            },
            {
                label: "Active Now",
                value: String((summary.status_counts || {})["active-now"] || 0),
            },
            {
                label: "Planned / Candidate",
                value: String(((summary.status_counts || {}).planned || 0) + ((summary.status_counts || {}).candidate || 0) + ((summary.status_counts || {}).reference || 0)),
            },
        ];

        for (var i = 0; i < cards.length; i++) {
            var card = document.createElement("div");
            card.style.cssText = "padding:12px 14px; border-radius:12px; border:1px solid var(--border-faint); background:rgba(255,255,255,0.02);";

            var label = document.createElement("div");
            label.style.cssText = "font-size:11px; text-transform:uppercase; letter-spacing:0.08em; color:var(--text-muted); margin-bottom:6px;";
            label.textContent = cards[i].label;
            card.appendChild(label);

            var value = document.createElement("div");
            value.style.cssText = "font-size:22px; font-weight:600; color:var(--text-primary);";
            value.textContent = cards[i].value;
            card.appendChild(value);

            summaryContainer.appendChild(card);
        }

        var sources = data.source_catalog || [];
        for (var j = 0; j < sources.length; j++) {
            var source = sources[j];
            var sourceCard = document.createElement("div");
            sourceCard.style.cssText = "padding:14px 16px; border-radius:12px; border:1px solid var(--border-faint); background:rgba(255,255,255,0.02); margin-bottom:10px;";

            var header = document.createElement("div");
            header.style.cssText = "display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:6px;";

            var titleWrap = document.createElement("div");
            var title = document.createElement("div");
            title.style.cssText = "font-size:15px; font-weight:500; color:var(--text-primary); margin-bottom:2px;";
            title.textContent = source.name;
            titleWrap.appendChild(title);

            var provider = document.createElement("div");
            provider.style.cssText = "font-size:12px; color:var(--text-muted);";
            provider.textContent = source.provider + " • " + source.category;
            titleWrap.appendChild(provider);
            header.appendChild(titleWrap);

            var badgeRow = document.createElement("div");
            badgeRow.style.cssText = "display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end;";
            badgeRow.appendChild(App._buildEnvironmentalBadge(source.status || "planned", "status"));
            badgeRow.appendChild(App._buildEnvironmentalBadge(source.layer || "", "category"));
            badgeRow.appendChild(App._buildEnvironmentalBadge(source.downloaded ? "Downloaded" : "Not downloaded", "download"));
            header.appendChild(badgeRow);
            sourceCard.appendChild(header);

            var purpose = document.createElement("div");
            purpose.style.cssText = "font-size:13px; color:var(--text-secondary); line-height:1.6; margin-bottom:8px;";
            purpose.textContent = source.purpose || "";
            sourceCard.appendChild(purpose);

            var meta = document.createElement("div");
            meta.style.cssText = "display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:8px; font-size:12px; color:var(--text-muted);";

            var metaFields = [
                { label: "Horizon", value: source.time_horizon },
                { label: "Geography", value: source.geography },
                { label: "Cadence", value: source.cadence },
                { label: "Auth", value: source.auth },
                { label: "Last Updated", value: source.last_updated || "Not synced yet" },
                { label: "Endpoint", value: source.endpoint },
                { label: "Local Data", value: source.local_path || "Not staged yet" },
                { label: "Snapshot Count", value: source.snapshot_count != null ? String(source.snapshot_count) : "0" },
            ];

            for (var m = 0; m < metaFields.length; m++) {
                var field = document.createElement("div");
                field.style.cssText = "padding:8px 10px; border-radius:10px; background:rgba(0,0,0,0.18);";

                var fieldLabel = document.createElement("div");
                fieldLabel.style.cssText = "font-size:10px; text-transform:uppercase; letter-spacing:0.08em; color:var(--text-muted); margin-bottom:4px;";
                fieldLabel.textContent = metaFields[m].label;
                field.appendChild(fieldLabel);

                var fieldValue = document.createElement("div");
                fieldValue.style.cssText = "color:var(--text-secondary); line-height:1.5; word-break:break-word;";
                fieldValue.textContent = metaFields[m].value || "\u2014";
                field.appendChild(fieldValue);

                meta.appendChild(field);
            }

            if (source.coverage_notes) {
                var notes = document.createElement("div");
                notes.style.cssText = "margin-top:8px; font-size:12px; color:var(--accent-teal);";
                notes.textContent = source.coverage_notes;
                sourceCard.appendChild(notes);
            }

            sourceCard.appendChild(meta);
            listContainer.appendChild(sourceCard);
        }
    },

    // ── Health Tracker (stub — implemented in Phase I) ──

    loadTracker: async function() {
        Tracker.load();
    },

    // ── PubMed Sweep ────────────────────────────────────

    sweepNow: async function() {
        var btn = document.getElementById("sweep-now-btn");
        var statusDiv = document.getElementById("sweep-status");
        if (!btn || !statusDiv) return;

        // Show loading state
        btn.disabled = true;
        btn.textContent = "Sweeping\u2026";
        statusDiv.style.display = "block";
        safeSetHtml(statusDiv,
            '<div style="padding:16px; text-align:center; color:var(--accent-teal);">'
            + '<div style="font-size:14px; margin-bottom:4px;">'
            + 'Searching PubMed for research relevant to your profile\u2026</div>'
            + '<div style="font-size:12px; color:var(--text-muted);">'
            + 'This may take a moment \u2014 checking symptoms, medications, genetics, and more.</div>'
            + '</div>'
        );

        try {
            var result = await api("/api/sweep-now", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: "{}",
            });

            var alerts = result.alerts || [];
            var summary = result.query_summary || {};

            // Show query summary
            var catParts = [];
            var cats = summary.categories || {};
            if (cats.symptom_research) catParts.push(cats.symptom_research + " symptom");
            if (cats.medication_safety) catParts.push(cats.medication_safety + " medication safety");
            if (cats.medication_combination) catParts.push(cats.medication_combination + " drug combo");
            if (cats.diagnosis_treatment) catParts.push(cats.diagnosis_treatment + " diagnosis");
            if (cats.genetic_variant) catParts.push(cats.genetic_variant + " genetics");

            var summaryText = "Searched " + (summary.total_queries || 0)
                + " queries (" + (catParts.join(", ") || "none") + "). "
                + "Found " + alerts.length + " result" + (alerts.length !== 1 ? "s" : "") + ".";

            safeSetHtml(statusDiv,
                '<div style="padding:12px 16px; background:var(--bg-secondary); '
                + 'border-radius:8px; margin-bottom:16px; border-left:3px solid var(--accent-teal);">'
                + '<div style="font-size:13px; color:var(--text-secondary);">'
                + escapeHtml(summaryText) + '</div></div>'
            );

            // Render results into alerts-list
            if (alerts.length) {
                var container = $("alerts-list");
                var html = "";
                for (var i = 0; i < alerts.length; i++) {
                    var a = alerts[i];
                    html += '<div style="padding:16px 0; border-bottom:1px solid var(--border-faint);">'
                        + '<div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">'
                        + severityBadge(a.severity)
                        + "<strong>" + escapeHtml(a.title || "Alert") + "</strong>"
                        + '<span style="font-size:12px; color:var(--text-muted); margin-left:auto;">'
                        + escapeHtml(a.source || "") + "</span>"
                        + "</div>"
                        + '<div style="color:var(--text-secondary); font-size:14px; margin-bottom:4px;">'
                        + escapeHtml(a.description || "") + "</div>"
                        + (a.relevance
                            ? '<div style="font-size:13px; color:var(--accent-amber); margin-top:8px;">'
                              + 'Why this matters: ' + escapeHtml(a.relevance) + "</div>"
                            : "")
                        + (a.url
                            ? '<div style="margin-top:8px;">'
                              + '<a href="' + escapeHtml(a.url) + '" target="_blank" rel="noopener" '
                              + 'style="font-size:13px; color:var(--accent-teal); text-decoration:none;">'
                              + 'View on PubMed \u2192</a></div>'
                            : "")
                        + "</div>";
                }
                safeSetHtml(container, html);
            } else {
                safeSetHtml($("alerts-list"),
                    '<div style="color:var(--text-muted); text-align:center; padding:40px;">'
                    + 'No new publications found in the past 30 days. '
                    + 'This is good \u2014 no urgent updates for your profile.</div>'
                );
            }

        } catch (e) {
            safeSetHtml(statusDiv,
                '<div style="padding:12px 16px; background:var(--bg-secondary); '
                + 'border-radius:8px; margin-bottom:16px; border-left:3px solid var(--accent-crimson);">'
                + '<div style="font-size:13px; color:var(--accent-crimson);">'
                + 'Sweep failed: ' + escapeHtml(e.message || "Unknown error")
                + '. This may be due to network issues or PubMed rate limits.</div></div>'
            );
        } finally {
            btn.disabled = false;
            btn.textContent = "Sweep Now";
        }
    },

    // ── Questions for Doctor ──────────────────────────

    loadQuestions: async function() {
        try {
            var questions = await api("/api/questions");
            var container = $("questions-list");

            if (questions.length) {
                $("questions-card").style.display = "block";
                var html = "";
                for (var i = 0; i < questions.length; i++) {
                    html += '<div style="padding:12px 0; border-bottom:1px solid var(--border-faint); display:flex; gap:12px; align-items:flex-start;">'
                        + '<span style="color:var(--accent-teal); font-weight:600; font-size:16px;">' + (i + 1) + ".</span>"
                        + '<span style="font-size:14px; line-height:1.6;">' + escapeHtml(questions[i]) + "</span>"
                        + "</div>";
                }
                safeSetHtml(container, html);
            }
        } catch (e) { /* no data */ }
    },

    // ── Chat ──────────────────────────────────────────

    sendChat: async function() {
        var input = $("chat-input");
        var message = input.value.trim();
        if (!message) return;

        input.value = "";
        var container = $("chat-messages");

        // Add user message
        var userDiv = document.createElement("div");
        userDiv.className = "chat-message user";
        var userBubble = document.createElement("div");
        userBubble.className = "chat-bubble";
        userBubble.textContent = message;
        userDiv.appendChild(userBubble);
        container.appendChild(userDiv);
        container.scrollTop = container.scrollHeight;

        try {
            var result = await api("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: message }),
            });

            // Add assistant response using safe DOM methods
            var asstDiv = document.createElement("div");
            asstDiv.className = "chat-message assistant";
            var asstBubble = document.createElement("div");
            asstBubble.className = "chat-bubble";
            // Split on newlines to create line breaks safely
            var lines = result.response.split("\n");
            for (var i = 0; i < lines.length; i++) {
                if (i > 0) asstBubble.appendChild(document.createElement("br"));
                asstBubble.appendChild(document.createTextNode(lines[i]));
            }
            asstDiv.appendChild(asstBubble);
            container.appendChild(asstDiv);
        } catch (e) {
            var errDiv = document.createElement("div");
            errDiv.className = "chat-message assistant";
            var errBubble = document.createElement("div");
            errBubble.className = "chat-bubble";
            errBubble.style.borderColor = "var(--accent-red)";
            errBubble.textContent = "Sorry, I couldn't process that request. " + e.message;
            errDiv.appendChild(errBubble);
            container.appendChild(errDiv);
        }
        container.scrollTop = container.scrollHeight;
    },

    // ── Report ────────────────────────────────────────

    generateReport: async function() {
        try {
            $("report-status").textContent = "Generating report...";
            await api("/api/report/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });
            $("report-status").textContent = "Report generated successfully.";
            $("report-download-btn").style.display = "inline-flex";
        } catch (e) {
            $("report-status").textContent = "Failed to generate report: " + e.message;
        }
    },

    downloadReport: function() {
        window.location.href = "/api/report/download";
    },

    // ── Session ───────────────────────────────────────

    clearSession: async function() {
        if (!confirm(
            "Delete all local patient data from MedPrep?\n\n"
            + "This removes uploaded files, derived findings, the encrypted patient profile, the local SQLite database, and generated reports from this Mac.\n\n"
            + "API keys and downloaded anatomy/model assets are kept."
        )) {
            return;
        }

        try {
            await api("/api/session/clear", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });
            App.uploadedFiles = [];
            App.hideSettings();
            alert("Local patient data deleted from MedPrep. API keys and downloaded models were kept.");
            window.location.reload();
        } catch (e) {
            alert("Failed to delete local patient data: " + e.message);
        }
    },

    deleteLocalPatientData: async function() {
        await App.clearSession();
    },

    // ── Settings ──────────────────────────────────────

    showSettings: async function() {
        $("settings-overlay").style.display = "flex";

        // Load current key status
        try {
            var status = await api("/api/keys/status");
            updateSettingStatus("gemini-key-status", Boolean(status.gemini));
            updateSettingStatus("ncbi-key-status", Boolean(status.ncbi));
            updateSettingStatus("openfda-key-status", Boolean(status.openfda));
            updateSettingStatus("airnow-key-status", Boolean(status.airnow));
            updateSettingStatus("nws-contact-status", Boolean(status.nws_contact), "Saved");
        } catch (e) { /* ignore */ }

        // Load current location
        try {
            var locData = await api("/api/location");
            var locInput = $("setting-location");
            if (locInput && locData.location) {
                locInput.value = locData.location;
            }
        } catch (e) { /* ignore */ }

        try {
            var environmentalSettings = await api("/api/environmental/settings");
            App._renderEnvironmentalSettings(environmentalSettings);
        } catch (e) { /* ignore */ }
    },

    hideSettings: function() {
        $("settings-overlay").style.display = "none";
    },

    saveSettings: async function() {
        var keys = [
            { id: "setting-gemini-key", service: "gemini" },
            { id: "setting-ncbi-key", service: "ncbi" },
            { id: "setting-openfda-key", service: "openfda" },
            { id: "setting-airnow-key", service: "airnow" },
            { id: "setting-nws-contact", service: "nws_contact" },
        ];

        for (var i = 0; i < keys.length; i++) {
            var value = $(keys[i].id).value.trim();
            if (value) {
                try {
                    await api("/api/keys", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ service: keys[i].service, key: value }),
                    });
                } catch (e) {
                    alert("Failed to save " + keys[i].service + " key: " + e.message);
                    return;
                }
            }
        }

        // Save location separately (not an API key)
        var locationVal = $("setting-location").value.trim();
        try {
            await api("/api/location", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ location: locationVal }),
            });
        } catch (e) {
            alert("Failed to save location: " + e.message);
            return;
        }

        try {
            updateSettingStatus("gemini-key-status", Boolean($("setting-gemini-key").value.trim()));
            updateSettingStatus("ncbi-key-status", Boolean($("setting-ncbi-key").value.trim()));
            updateSettingStatus("openfda-key-status", Boolean($("setting-openfda-key").value.trim()));
            updateSettingStatus("airnow-key-status", Boolean($("setting-airnow-key").value.trim()));
            updateSettingStatus("nws-contact-status", Boolean($("setting-nws-contact").value.trim()), "Saved");
        } catch (e) { /* ignore */ }

        try {
            var selectedSourceIds = [];
            var sourceChecks = document.querySelectorAll("[data-environmental-source-check='1']");
            for (var s = 0; s < sourceChecks.length; s++) {
                if (sourceChecks[s].checked) {
                    selectedSourceIds.push(sourceChecks[s].value);
                }
            }

            await api("/api/environmental/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    enabled: Boolean($("setting-environmental-auto-enabled") && $("setting-environmental-auto-enabled").checked),
                    interval_hours: parseInt(($("setting-environmental-auto-interval") || {}).value || "24", 10),
                    source_ids: selectedSourceIds,
                }),
            });
        } catch (e) {
            alert("Failed to save environmental sync settings: " + e.message);
            return;
        }

        App.hideSettings();
    },

    // ── Visit Prep ──────────────────────────────────────

    prepareForVisit: async function() {
        var overlay = $("visit-prep-overlay");
        var content = $("visit-prep-content");
        if (!overlay || !content) return;

        overlay.style.display = "flex";
        while (content.firstChild) content.removeChild(content.firstChild);
        var loading = document.createElement("div");
        loading.style.cssText = "text-align:center; padding:40px; color:var(--text-muted);";
        loading.textContent = "Generating your visit prep...";
        content.appendChild(loading);

        try {
            var data = await api("/api/visit-prep", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}",
            });
            while (content.firstChild) content.removeChild(content.firstChild);
            App._renderVisitPrep(content, data);
        } catch (e) {
            while (content.firstChild) content.removeChild(content.firstChild);
            var err = document.createElement("div");
            err.style.cssText = "text-align:center; padding:40px; color:var(--accent-crimson);";
            err.textContent = "Failed to generate visit prep: " + e.message;
            content.appendChild(err);
        }
    },

    closeVisitPrep: function() {
        var overlay = $("visit-prep-overlay");
        if (overlay) overlay.style.display = "none";
    },

    downloadVisitPrep: function() {
        window.open("/api/visit-prep/download", "_blank");
    },

    _renderVisitPrep: function(container, data) {
        var self = this;

        // Narrative summary (if Gemini generated one)
        if (data.narrative) {
            var narCard = document.createElement("div");
            narCard.className = "visit-prep-section";
            var narTitle = document.createElement("h3");
            narTitle.textContent = "Summary";
            narCard.appendChild(narTitle);
            var narText = document.createElement("p");
            narText.textContent = data.narrative;
            narCard.appendChild(narText);
            container.appendChild(narCard);
        }

        // Section: Counter-Evidence Summary (THE STAR)
        var evidence = data.counter_evidence || [];
        if (evidence.length > 0) {
            var evCard = document.createElement("div");
            evCard.className = "visit-prep-section visit-prep-evidence";
            var evTitle = document.createElement("h3");
            evTitle.textContent = "Counter-Evidence Summary";
            evCard.appendChild(evTitle);
            var evDesc = document.createElement("p");
            evDesc.className = "visit-prep-section-desc";
            evDesc.textContent = "Data that challenges your doctor\u2019s claims about symptom causes.";
            evCard.appendChild(evDesc);

            for (var ei = 0; ei < evidence.length; ei++) {
                evCard.appendChild(self._vpEvidenceRow(evidence[ei]));
            }
            container.appendChild(evCard);
        }

        // Section: Active Conditions
        var conditions = data.conditions || [];
        if (conditions.length > 0) {
            container.appendChild(
                self._vpTable("Active Conditions", ["Condition", "Status", "Since"],
                    conditions.map(function(c) { return [c.name, c.status, c.date_diagnosed || "\u2014"]; }))
            );
        }

        // Section: Recent Symptoms
        var symptoms = data.recent_symptoms || [];
        if (symptoms.length > 0) {
            container.appendChild(self._vpSymptoms(symptoms));
        }

        // Section: Flagged Labs
        var labs = data.flagged_labs || [];
        if (labs.length > 0) {
            container.appendChild(
                self._vpTable("Flagged Lab Results", ["Test", "Value", "Flag", "Trend", "Date"],
                    labs.map(function(l) { return [l.name, (l.value || "") + " " + (l.unit || ""), l.flag, l.trend, l.test_date || "\u2014"]; }))
            );
        }

        // Section: Medications
        var meds = data.medications || [];
        if (meds.length > 0) {
            container.appendChild(self._vpMeds(meds));
        }

        // Section: Questions
        var questions = data.questions || [];
        if (questions.length > 0) {
            container.appendChild(self._vpQuestions(questions));
        }

        // Section: Patterns
        var patterns = data.patterns || [];
        if (patterns.length > 0) {
            var tl = {"worsening": "\u2191 Worsening", "improving": "\u2193 Improving", "stable": "\u2192 Stable", "insufficient_data": "\u2014 Too few"};
            container.appendChild(
                self._vpTable("Symptom Patterns", ["Symptom", "Frequency", "Trend", "Peak Time"],
                    patterns.map(function(p) { return [p.name, p.freq_per_week + "/week", tl[p.severity_trend] || "\u2014", (p.peak_time_of_day || "\u2014")]; }))
            );
        }

        // Empty state
        if (!conditions.length && !symptoms.length && !labs.length && !meds.length && !evidence.length) {
            var empty = document.createElement("div");
            empty.style.cssText = "text-align:center; padding:40px; color:var(--text-muted);";
            empty.textContent = "No data available yet. Upload medical records or start tracking symptoms to generate a visit prep.";
            container.appendChild(empty);
        }
    },

    _vpEvidenceRow: function(ev) {
        var row = document.createElement("div");
        row.className = "visit-prep-evidence-row" + (ev.archived ? " archived" : "");
        var claim = document.createElement("div");
        claim.className = "visit-prep-claim";
        claim.textContent = ev.symptom + " \u2014 Doctor says: " + ev.doctor_claim;
        row.appendChild(claim);
        var d = document.createElement("div");
        d.className = "visit-prep-data";
        d.textContent = "Your data: " + (ev.summary || "No data yet");
        row.appendChild(d);
        if (ev.verdict) {
            var badge = document.createElement("span");
            badge.className = "verdict-badge verdict-" + ev.verdict.toLowerCase().replace(/\s+/g, "-");
            badge.textContent = ev.verdict;
            row.appendChild(badge);
        }
        return row;
    },

    _vpSymptoms: function(symptoms) {
        var card = document.createElement("div");
        card.className = "visit-prep-section";
        var t = document.createElement("h3");
        t.textContent = "Recent Symptoms (Last 30 Days)";
        card.appendChild(t);
        for (var i = 0; i < symptoms.length; i++) {
            var s = symptoms[i];
            var row = document.createElement("div");
            row.className = "visit-prep-symptom-row";
            var n = document.createElement("strong");
            n.textContent = s.name;
            row.appendChild(n);
            var info = document.createElement("span");
            info.textContent = " \u2014 " + s.episode_count + " episodes, " + s.dominant_severity.toUpperCase();
            row.appendChild(info);
            card.appendChild(row);
            var cs = s.counter_stats || [];
            for (var j = 0; j < cs.length; j++) {
                var c = document.createElement("div");
                c.className = "visit-prep-counter-inline";
                c.textContent = "Doctor says: " + cs[j].doctor_claim + " \u2192 " + (cs[j].summary || "");
                card.appendChild(c);
            }
        }
        return card;
    },

    _vpMeds: function(meds) {
        var card = this._vpTable("Current Medications", ["Medication", "Dosage", "Frequency", "For"],
            meds.map(function(m) { return [m.name, m.dosage, m.frequency, m.reason]; }));
        for (var i = 0; i < meds.length; i++) {
            var ix = meds[i].interactions || [];
            for (var j = 0; j < ix.length; j++) {
                var w = document.createElement("div");
                w.className = "visit-prep-warning";
                w.textContent = "\u26a0 " + meds[i].name + ": " + ix[j].description;
                card.appendChild(w);
            }
        }
        return card;
    },

    _vpQuestions: function(questions) {
        var card = document.createElement("div");
        card.className = "visit-prep-section";
        var t = document.createElement("h3");
        t.textContent = "Questions to Ask Your Doctor";
        card.appendChild(t);
        var ol = document.createElement("ol");
        ol.className = "visit-prep-questions";
        var srcLabels = {counter_evidence: "Based on your tracked data", interaction: "Drug interaction", flag: "Flagged finding", analysis: "From analysis"};
        for (var i = 0; i < questions.length; i++) {
            var li = document.createElement("li");
            li.textContent = questions[i].question;
            var label = srcLabels[questions[i].source] || "";
            if (label) {
                var sp = document.createElement("span");
                sp.className = "visit-prep-q-source";
                sp.textContent = " (" + label + ")";
                li.appendChild(sp);
            }
            ol.appendChild(li);
        }
        card.appendChild(ol);
        return card;
    },

    _vpTable: function(title, headers, rows) {
        var section = document.createElement("div");
        section.className = "visit-prep-section";
        var h3 = document.createElement("h3");
        h3.textContent = title;
        section.appendChild(h3);
        var table = document.createElement("table");
        table.className = "visit-prep-table";
        var thead = document.createElement("thead");
        var tr = document.createElement("tr");
        for (var h = 0; h < headers.length; h++) {
            var th = document.createElement("th");
            th.textContent = headers[h];
            tr.appendChild(th);
        }
        thead.appendChild(tr);
        table.appendChild(thead);
        var tbody = document.createElement("tbody");
        for (var r = 0; r < rows.length; r++) {
            var row = document.createElement("tr");
            for (var c = 0; c < rows[r].length; c++) {
                var td = document.createElement("td");
                td.textContent = rows[r][c] || "\u2014";
                row.appendChild(td);
            }
            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        section.appendChild(table);
        return section;
    },
};


// ══════════════════════════════════════════════════════════
//  BodyMap2DFallback — 2D Fallback (used when WebGL unavailable)
//  Primary 3D viewer is in bodymap3d.js (BodyMap3D)
// ══════════════════════════════════════════════════════════

var BodyMap2DFallback = {
    currentLayer: "skin",
    currentSide: "front",

    layerImages: {
        "skin-front": "/assets/anatomy.png",
        "skin-back": "/assets/anatomy_back.png",
        "muscle-front": "/assets/anatomy_muscle.png",
        "muscle-back": "/assets/anatomy_muscle.png",
        "skeleton-front": "/assets/anatomy_skeleton.png",
        "skeleton-back": "/assets/anatomy_skeleton.png",
        "organs-front": "/assets/anatomy_organs.png",
        "organs-back": "/assets/anatomy_organs.png",
    },

    regionMapping: {
        head: ["neurology", "brain", "head", "neurological", "mental", "cognitive", "headache", "migraine", "seizure", "eye", "ear", "sinus", "thyroid"],
        chest: ["cardiac", "heart", "lung", "pulmonary", "respiratory", "chest", "cardio", "coronary", "thorax", "rib", "breast"],
        abdomen: ["gastro", "liver", "hepat", "pancrea", "stomach", "intestin", "colon", "abdom", "gallbladder", "spleen", "kidney", "renal"],
        pelvis: ["pelvic", "bladder", "uterus", "prostate", "reproduct", "urinary", "urological"],
        "left-arm": ["arm", "upper extremity", "shoulder", "elbow", "wrist", "hand"],
        "right-arm": ["arm", "upper extremity", "shoulder", "elbow", "wrist", "hand"],
        "left-leg": ["leg", "lower extremity", "hip", "knee", "ankle", "foot", "femur", "tibia"],
        "right-leg": ["leg", "lower extremity", "hip", "knee", "ankle", "foot", "femur", "tibia"],
    },

    setLayer: function(layer) {
        BodyMap2DFallback.currentLayer = layer;
        var key = layer + "-" + BodyMap2DFallback.currentSide;
        var img = $("bodymap-img");
        if (img) img.src = BodyMap2DFallback.layerImages[key] || BodyMap2DFallback.layerImages["skin-front"];
    },

    selectRegion: async function(region) {
        var zones = document.querySelectorAll(".bodymap-zone");
        for (var i = 0; i < zones.length; i++) {
            var isSelected = zones[i].dataset.region === region;
            zones[i].style.fill = isSelected ? "rgba(220, 38, 38, 0.15)" : "transparent";
            zones[i].style.stroke = isSelected ? "var(--heat)" : "none";
            zones[i].style.strokeWidth = isSelected ? "2" : "0";
        }

        var regionName = region.replace(/-/g, " ").replace(/\b\w/g, function(c) { return c.toUpperCase(); });
        $("bodymap-region-title").textContent = regionName;

        var keywords = BodyMap2DFallback.regionMapping[region] || [];
        var findings = [];

        try {
            var results = await Promise.all([
                api("/api/diagnoses"),
                api("/api/imaging"),
                api("/api/flags"),
            ]);
            var diagnoses = results[0];
            var imaging = results[1];
            var flags = results[2];

            for (var a = 0; a < diagnoses.length; a++) {
                var dx = diagnoses[a];
                var dxText = (dx.name + " " + (dx.status || "")).toLowerCase();
                for (var b = 0; b < keywords.length; b++) {
                    if (dxText.indexOf(keywords[b]) >= 0) {
                        findings.push({ type: "Diagnosis", text: dx.name, detail: dx.status || "" });
                        break;
                    }
                }
            }

            for (var c = 0; c < imaging.length; c++) {
                var study = imaging[c];
                var studyText = ((study.body_region || "") + " " + (study.description || "")).toLowerCase();
                var matched = false;
                for (var d = 0; d < keywords.length; d++) {
                    if (studyText.indexOf(keywords[d]) >= 0) { matched = true; break; }
                }
                if (matched) {
                    findings.push({ type: "Imaging", text: study.description || study.modality, detail: formatDate(study.study_date) });
                }
            }

            for (var g = 0; g < flags.length; g++) {
                var fl = flags[g];
                var flText = ((fl.title || "") + " " + (fl.description || "")).toLowerCase();
                for (var h = 0; h < keywords.length; h++) {
                    if (flText.indexOf(keywords[h]) >= 0) {
                        findings.push({ type: "Flag", text: fl.title, detail: fl.description || "" });
                        break;
                    }
                }
            }
        } catch (ex) { /* no data */ }

        var container = $("bodymap-findings-list");
        if (!container) return;
        if (findings.length === 0) {
            container.textContent = "No findings related to this region in your records.";
            container.style.color = "var(--text-muted)";
        } else {
            var html = "";
            for (var m = 0; m < findings.length; m++) {
                var fn = findings[m];
                html += '<div style="padding:8px 0; border-bottom:1px solid var(--border-faint);">'
                    + '<span class="badge badge-info" style="margin-right:8px;">' + escapeHtml(fn.type) + "</span>"
                    + "<strong>" + escapeHtml(fn.text) + "</strong>"
                    + '<div style="font-size:12px; color:var(--text-muted); margin-top:2px;">' + escapeHtml(fn.detail) + "</div>"
                    + "</div>";
            }
            safeSetHtml(container, html);
            container.style.color = "";
        }
    },
};


// ══════════════════════════════════════════════════════════
//  Health Tracker — Vitals Logging + Trends + Risk Score
// ══════════════════════════════════════════════════════════

var Tracker = {
    formVisible: false,

    load: async function() {
        try {
            await Promise.all([
                Tracker.loadTrends(),
                Tracker.loadEntries(),
                Tracker.loadRiskBreakdown(),
            ]);
        } catch (e) { /* partial load is fine */ }
    },

    toggleForm: function() {
        Tracker.formVisible = !Tracker.formVisible;
        var form = $("tracker-form");
        var btn = $("tracker-form-toggle");
        if (form) form.style.display = Tracker.formVisible ? "" : "none";
        if (btn) btn.textContent = Tracker.formVisible ? "Cancel" : "+ New Entry";
    },

    logEntry: async function() {
        var vtype = $("tracker-type").value;
        var value = $("tracker-value").value;
        var notes = $("tracker-notes").value;
        var errEl = $("tracker-form-error");

        if (!value) {
            if (errEl) { errEl.textContent = "Value is required"; errEl.style.display = "block"; }
            return;
        }
        if (errEl) errEl.style.display = "none";

        try {
            var result = await api("/api/tracker/log", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    vital_type: vtype,
                    value: parseFloat(value),
                    notes: notes,
                }),
            });

            if (result.error) {
                if (errEl) { errEl.textContent = result.error; errEl.style.display = "block"; }
                return;
            }

            // Clear form
            $("tracker-value").value = "";
            $("tracker-notes").value = "";

            // Refresh data
            Tracker.load();
        } catch (e) {
            if (errEl) { errEl.textContent = "Failed to log entry"; errEl.style.display = "block"; }
        }
    },

    deleteEntry: async function(id) {
        try {
            await api("/api/tracker/delete", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ id: id }),
            });
            Tracker.load();
        } catch (e) { /* silent */ }
    },

    loadTrends: async function() {
        var container = $("tracker-trends");
        if (!container) return;

        try {
            var trends = await api("/api/tracker/trends");
            if (!trends || !Object.keys(trends).length) {
                safeSetHtml(container, '<div style="grid-column:1/-1; color:var(--text-muted); text-align:center; padding:20px;">Log vitals above to see trends.</div>');
                return;
            }

            var cards = [];
            var order = ["blood_pressure_sys", "blood_pressure_dia", "heart_rate",
                         "blood_glucose", "a1c", "weight", "temperature", "oxygen_sat"];

            for (var i = 0; i < order.length; i++) {
                var key = order[i];
                var t = trends[key];
                if (!t) continue;

                var trendDir = "";
                if (t.values.length >= 2) {
                    var last = t.values[t.values.length - 1];
                    var prev = t.values[t.values.length - 2];
                    if (last > prev) trendDir = ' <span style="color:#f05545;">\u25b2</span>';
                    else if (last < prev) trendDir = ' <span style="color:#5cd47f;">\u25bc</span>';
                    else trendDir = ' <span style="color:var(--text-muted);">\u2192</span>';
                }

                var sparkId = "spark-" + key;
                cards.push(
                    '<div style="background:var(--bg-card); border-radius:var(--radius-sm); padding:14px; border:1px solid var(--border-faint);">'
                    + '<div style="font-size:10px; font-weight:600; letter-spacing:0.08em; color:var(--text-muted); margin-bottom:6px;">'
                    + escapeHtml(t.label.toUpperCase())
                    + '</div>'
                    + '<div style="display:flex; align-items:baseline; gap:4px; margin-bottom:8px;">'
                    + '<div style="font-size:22px; font-weight:700; color:#fff;">' + escapeHtml(String(t.latest)) + '</div>'
                    + '<div style="font-size:11px; color:var(--text-muted);">' + escapeHtml(t.unit) + '</div>'
                    + trendDir
                    + '</div>'
                    + '<div id="' + escapeHtml(sparkId) + '" style="height:30px;"></div>'
                    + '<div style="display:flex; justify-content:space-between; margin-top:4px;">'
                    + '<span style="font-size:10px; color:var(--text-muted);">Avg: ' + escapeHtml(String(t.average)) + '</span>'
                    + '<span style="font-size:10px; color:var(--text-muted);">' + escapeHtml(String(t.count)) + ' entries</span>'
                    + '</div>'
                    + '</div>'
                );
            }

            safeSetHtml(container, cards.join(""));

            // Render sparklines after DOM update
            for (var j = 0; j < order.length; j++) {
                var k = order[j];
                var tr = trends[k];
                if (tr && tr.values.length > 1 && typeof Sparklines !== "undefined") {
                    var color = k === "blood_glucose" || k === "a1c" ? "#dc2626" :
                                k === "heart_rate" ? "#f05545" :
                                k.startsWith("blood_pressure") ? "#5a8ffc" :
                                k === "oxygen_sat" ? "#5cd47f" : "#f0c550";
                    Sparklines.render("spark-" + k, tr.values, { color: color, height: 30 });
                }
            }
        } catch (e) {
            safeSetHtml(container, '<div style="grid-column:1/-1; color:var(--text-muted); text-align:center; padding:20px;">Could not load trends.</div>');
        }
    },

    loadEntries: async function() {
        var container = $("tracker-entries");
        if (!container) return;

        try {
            var entries = await api("/api/tracker/entries?limit=30");
            if (!entries || !entries.length) {
                safeSetHtml(container, '<div style="color:var(--text-muted); text-align:center; padding:40px;">No entries yet. Log your first vital sign above.</div>');
                return;
            }

            var html = '<table style="width:100%; border-collapse:collapse;">'
                + '<tr style="border-bottom:1px solid var(--border-faint);">'
                + '<th style="text-align:left; padding:8px; font-size:11px; color:var(--text-muted); font-weight:600;">Date</th>'
                + '<th style="text-align:left; padding:8px; font-size:11px; color:var(--text-muted); font-weight:600;">Type</th>'
                + '<th style="text-align:right; padding:8px; font-size:11px; color:var(--text-muted); font-weight:600;">Value</th>'
                + '<th style="text-align:left; padding:8px; font-size:11px; color:var(--text-muted); font-weight:600;">Notes</th>'
                + '<th style="width:40px;"></th>'
                + '</tr>';

            for (var i = 0; i < entries.length; i++) {
                var e = entries[i];
                var dateStr = e.timestamp ? formatDate(e.timestamp.substring(0, 10)) : "";
                var timeStr = e.timestamp ? e.timestamp.substring(11, 16) : "";

                html += '<tr style="border-bottom:1px solid var(--border-faint);">'
                    + '<td style="padding:8px; font-size:13px;">'
                    + escapeHtml(dateStr) + ' <span style="color:var(--text-muted); font-size:11px;">' + escapeHtml(timeStr) + '</span></td>'
                    + '<td style="padding:8px; font-size:13px;">' + escapeHtml(e.vital_type || "").replace(/_/g, " ") + '</td>'
                    + '<td style="padding:8px; font-size:13px; text-align:right; font-weight:600;">'
                    + escapeHtml(String(e.value)) + ' <span style="color:var(--text-muted); font-size:11px;">' + escapeHtml(e.unit || "") + '</span></td>'
                    + '<td style="padding:8px; font-size:12px; color:var(--text-secondary);">' + escapeHtml(e.notes || "") + '</td>'
                    + '<td style="padding:8px;">'
                    + '<button onclick="Tracker.deleteEntry(\'' + escapeHtml(e.id) + '\');" '
                    + 'style="background:none; border:none; cursor:pointer; color:var(--text-muted); font-size:14px;" title="Delete">\u00d7</button>'
                    + '</td>'
                    + '</tr>';
            }
            html += '</table>';
            safeSetHtml(container, html);
        } catch (e) {
            safeSetHtml(container, '<div style="color:var(--text-muted); text-align:center; padding:40px;">Could not load entries.</div>');
        }
    },

    loadRiskBreakdown: async function() {
        var container = $("risk-breakdown-content");
        if (!container) return;

        try {
            var data = await api("/api/tracker/risk-breakdown");
            if (!data || !data.factors || !data.factors.length) {
                safeSetHtml(container, '<div style="text-align:center; padding:20px;">'
                    + '<div style="font-size:32px; font-weight:700; color:#5cd47f; margin-bottom:8px;">0</div>'
                    + '<div style="color:var(--text-muted); font-size:12px;">No risk factors identified</div>'
                    + '</div>');
                return;
            }

            var scoreColor = data.score <= 25 ? "#5cd47f" :
                             data.score <= 50 ? "#f0c550" :
                             data.score <= 75 ? "#f05545" : "#dc2626";

            var html = '<div style="display:flex; gap:24px; align-items:flex-start;">'
                + '<div style="text-align:center; min-width:100px;">'
                + '<div style="font-size:42px; font-weight:700; color:' + scoreColor + ';">' + escapeHtml(String(data.score)) + '</div>'
                + '<div style="font-size:11px; color:var(--text-muted);">/100 Risk Score</div>'
                + '</div>'
                + '<div style="flex:1;">';

            for (var i = 0; i < data.factors.length; i++) {
                var f = data.factors[i];
                var pct = Math.min(f.points / 100 * 100, 100);
                html += '<div style="margin-bottom:10px;">'
                    + '<div style="display:flex; justify-content:space-between; margin-bottom:3px;">'
                    + '<span style="font-size:12px; font-weight:500;">' + escapeHtml(f.category) + '</span>'
                    + '<span style="font-size:12px; color:var(--text-muted);">+' + escapeHtml(String(f.points)) + ' pts \u2014 ' + escapeHtml(f.detail) + '</span>'
                    + '</div>'
                    + '<div style="height:6px; background:var(--bg-raised); border-radius:3px; overflow:hidden;">'
                    + '<div style="height:100%; width:' + pct + '%; background:' + escapeHtml(f.color) + '; border-radius:3px;"></div>'
                    + '</div>'
                    + '</div>';
            }

            html += '</div></div>';
            safeSetHtml(container, html);
        } catch (e) {
            safeSetHtml(container, '<div style="color:var(--text-muted); text-align:center; padding:20px;">Could not load risk breakdown.</div>');
        }
    },
};


// ══════════════════════════════════════════════════════════
//  Timeline — Health Timeline Controller
// ══════════════════════════════════════════════════════════

var Timeline = {
    events: [],
    currentFilter: "all",
    currentView: "flow", // "flow" (D3 swim-lane) or "list" (legacy)

    load: async function() {
        try {
            Timeline.events = await api("/api/timeline");
            for (var i = 0; i < Timeline.events.length; i++) {
                Timeline.events[i]._timelineKey = Timeline.events[i].event_key || (
                    (Timeline.events[i].type || "event") + ":" + (Timeline.events[i].date || "") + ":" + i
                );
            }
            Timeline.render();
        } catch (e) { /* no data */ }
    },

    setView: function(view) {
        Timeline.currentView = view;

        // Update toggle buttons
        var btns = document.querySelectorAll(".tl-view-btn");
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].dataset.tlView === view) {
                btns[i].classList.add("active");
            } else {
                btns[i].classList.remove("active");
            }
        }

        // Toggle container visibility
        var flowEl = $("timeline-flow-container");
        var detailEl = $("timeline-detail-panel");
        var listEl = $("timeline-list");
        if (flowEl) flowEl.style.display = view === "flow" ? "" : "none";
        if (detailEl) detailEl.style.display = view === "flow" ? "" : "none";
        if (listEl) listEl.style.display = view === "list" ? "" : "none";

        Timeline.render();
    },

    filter: function(type) {
        Timeline.currentFilter = type;

        // Update active button
        var btns = document.querySelectorAll(".timeline-filter");
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].dataset.type === type) {
                btns[i].classList.add("active");
            } else {
                btns[i].classList.remove("active");
            }
        }

        Timeline.render();
    },

    render: function() {
        if (Timeline.currentView === "flow") {
            Timeline._renderFlow();
        } else {
            Timeline._renderList();
        }
    },

    _renderFlow: function() {
        if (typeof TimelineFlow !== "undefined" && Timeline.events.length) {
            TimelineFlow.init(Timeline.events, Timeline.currentFilter);
        }
    },

    _renderList: function() {
        var container = $("timeline-list");
        var events = Timeline._getFilteredEvents();
        while (container && container.firstChild) container.removeChild(container.firstChild);

        if (!container) {
            return;
        }

        if (!events.length) {
            var empty = document.createElement("div");
            empty.style.cssText = "color:var(--text-muted); text-align:center; padding:40px;";
            empty.textContent = "No events to display.";
            container.appendChild(empty);
            return;
        }

        var list = document.createElement("div");
        list.className = "timeline-list-view";

        for (var i = 0; i < events.length; i++) {
            list.appendChild(Timeline._buildListItem(events[i]));
        }
        container.appendChild(list);
    },

    _getFilteredEvents: function() {
        if (Timeline.currentFilter === "all") {
            return Timeline.events.slice();
        }

        return Timeline.events.filter(function(e) {
            return e.type === Timeline.currentFilter;
        });
    },

    _buildListItem: function(event) {
        var item = document.createElement("details");
        item.className = "timeline-item timeline-item--expandable";

        var summary = document.createElement("summary");
        summary.className = "timeline-item-summary";

        var dot = document.createElement("div");
        dot.className = "timeline-dot " + (event.type || "");
        summary.appendChild(dot);

        var dateEl = document.createElement("div");
        dateEl.className = "timeline-date";
        dateEl.textContent = formatDate(event.date);
        summary.appendChild(dateEl);

        var body = document.createElement("div");
        body.className = "timeline-item-main";

        var title = document.createElement("div");
        title.className = "timeline-title";
        title.textContent = event.title || "Timeline event";
        body.appendChild(title);

        var detail = document.createElement("div");
        detail.className = "timeline-detail";
        detail.textContent = event.detail || "Open for more context.";
        body.appendChild(detail);

        summary.appendChild(body);

        var badge = document.createElement("span");
        badge.className = "badge badge-info timeline-item-badge";
        badge.textContent = (event.type || "event").toUpperCase();
        summary.appendChild(badge);

        item.appendChild(summary);

        var content = document.createElement("div");
        content.className = "timeline-item-content";
        Timeline._appendListEventDetails(content, event);
        item.appendChild(content);

        return item;
    },

    _appendListEventDetails: function(container, event) {
        var hasContent = false;
        var grid = document.createElement("div");
        grid.className = "timeline-item-grid";

        if (event.type === "medication") {
            Timeline._appendListField(grid, "Dose", event.dosage);
            Timeline._appendListField(grid, "Frequency", event.frequency);
            Timeline._appendListField(grid, "Route", event.route);
            Timeline._appendListField(grid, "Prescriber", event.prescriber || event.provider);
            Timeline._appendListField(grid, "Status", event.status);
        } else if (event.type === "lab") {
            Timeline._appendListField(grid, "Result", Timeline._compactParts([event.value, event.value_text, event.unit]));
            Timeline._appendListField(grid, "Flag", event.flag);
            Timeline._appendListField(grid, "Reference Range", Timeline._formatReferenceRange(event.reference_low, event.reference_high, event.unit));
            Timeline._appendListField(grid, "Provider", event.provider);
            Timeline._appendListField(grid, "Facility", event.facility);
        } else if (event.type === "diagnosis") {
            Timeline._appendListField(grid, "Status", event.status);
            Timeline._appendListField(grid, "ICD-10", event.icd10);
            Timeline._appendListField(grid, "Provider", event.provider);
        } else if (event.type === "procedure") {
            Timeline._appendListField(grid, "Provider", event.provider);
            Timeline._appendListField(grid, "Facility", event.facility);
            Timeline._appendListField(grid, "Outcome", event.outcome);
        } else if (event.type === "imaging") {
            Timeline._appendListField(grid, "Modality", event.modality);
            Timeline._appendListField(grid, "Region", event.body_region);
            Timeline._appendListField(grid, "Provider", event.provider);
            Timeline._appendListField(grid, "Facility", event.facility);
        } else if (event.type === "symptom") {
            Timeline._appendListField(grid, "Severity", event.severity);
            Timeline._appendListField(grid, "Time of Day", event.time_of_day);
            Timeline._appendListField(grid, "Duration", event.duration);
            Timeline._appendListField(grid, "Triggers", event.triggers);
        }

        if (grid.childNodes.length) {
            container.appendChild(Timeline._buildListSectionTitle("Entry Details"));
            container.appendChild(grid);
            hasContent = true;
        }

        if (event.type === "medication") {
            hasContent = Timeline._appendListBody(container, "Reason", event.reason) || hasContent;
        } else if (event.type === "procedure") {
            hasContent = Timeline._appendListBody(container, "Procedure Notes", event.notes || event.detail) || hasContent;
        } else if (event.type === "imaging") {
            hasContent = Timeline._appendListBody(container, "Study Summary", event.description) || hasContent;
            hasContent = Timeline._appendListBody(container, "Findings", event.findings || event.detail) || hasContent;
        } else if (event.type === "symptom") {
            hasContent = Timeline._appendListBody(container, "Episode Description", event.description || event.detail) || hasContent;
        } else if (event.detail) {
            hasContent = Timeline._appendListBody(container, "Details", event.detail) || hasContent;
        }

        if (event.related_notes && event.related_notes.length) {
            container.appendChild(Timeline._buildListSectionTitle("Doctor Notes"));
            container.appendChild(Timeline._buildTimelineNotes(event.related_notes));
            hasContent = true;
        }

        if (event.related_labs && event.related_labs.length) {
            container.appendChild(Timeline._buildListSectionTitle("Related Labs"));
            container.appendChild(Timeline._buildTimelineContextList(event.related_labs));
            hasContent = true;
        }

        if (event.related_events && event.related_events.length) {
            container.appendChild(Timeline._buildListSectionTitle("Nearby Context"));
            container.appendChild(Timeline._buildTimelineContextList(event.related_events));
            hasContent = true;
        }

        if (event.source_file || event.source_page || event.confidence || event.raw_text) {
            container.appendChild(Timeline._buildListSectionTitle("Source"));
            container.appendChild(Timeline._buildTimelineSource(event));
            hasContent = true;
        }

        if (!hasContent) {
            var empty = document.createElement("div");
            empty.className = "timeline-item-empty";
            empty.textContent = "No additional context was attached to this entry.";
            container.appendChild(empty);
        }
    },

    _appendListField: function(container, label, value) {
        if (!value && value !== 0) return;

        var field = document.createElement("div");
        field.className = "timeline-item-field";

        var labelEl = document.createElement("div");
        labelEl.className = "timeline-item-field-label";
        labelEl.textContent = label;
        field.appendChild(labelEl);

        var valueEl = document.createElement("div");
        valueEl.className = "timeline-item-field-value";
        valueEl.textContent = String(value);
        field.appendChild(valueEl);

        container.appendChild(field);
    },

    _appendListBody: function(container, label, value) {
        if (!value && value !== 0) return false;

        var block = document.createElement("div");
        block.className = "timeline-item-body-block";

        var labelEl = document.createElement("div");
        labelEl.className = "timeline-item-field-label";
        labelEl.textContent = label;
        block.appendChild(labelEl);

        var valueEl = document.createElement("div");
        valueEl.className = "timeline-item-body-copy";
        valueEl.textContent = String(value);
        block.appendChild(valueEl);

        container.appendChild(block);
        return true;
    },

    _buildListSectionTitle: function(text) {
        var title = document.createElement("div");
        title.className = "timeline-item-section-title";
        title.textContent = text;
        return title;
    },

    _buildTimelineNotes: function(notes) {
        var list = document.createElement("div");
        list.className = "timeline-context-list";

        for (var i = 0; i < notes.length; i++) {
            var note = notes[i];
            var card = document.createElement("div");
            card.className = "timeline-context-card";

            var top = document.createElement("div");
            top.className = "timeline-context-top";

            var title = document.createElement("div");
            title.className = "timeline-context-title";
            title.textContent = note.note_type || "Clinical note";
            top.appendChild(title);

            var meta = document.createElement("div");
            meta.className = "timeline-context-date";
            meta.textContent = formatDate(note.date);
            top.appendChild(meta);
            card.appendChild(top);

            var providerParts = [];
            if (note.provider) providerParts.push(note.provider);
            if (note.facility) providerParts.push(note.facility);
            if (providerParts.length) {
                var provider = document.createElement("div");
                provider.className = "timeline-context-meta";
                provider.textContent = providerParts.join(" • ");
                card.appendChild(provider);
            }

            var summary = document.createElement("div");
            summary.className = "timeline-context-body";
            summary.textContent = note.summary || "Clinical note attached to this time period.";
            card.appendChild(summary);

            list.appendChild(card);
        }

        return list;
    },

    _buildTimelineContextList: function(items) {
        var list = document.createElement("div");
        list.className = "timeline-context-list";

        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var card = document.createElement("div");
            card.className = "timeline-context-card";

            var top = document.createElement("div");
            top.className = "timeline-context-top";

            var title = document.createElement("div");
            title.className = "timeline-context-title";
            title.textContent = item.title || "Related entry";
            top.appendChild(title);

            var date = document.createElement("div");
            date.className = "timeline-context-date";
            date.textContent = formatDate(item.date);
            top.appendChild(date);
            card.appendChild(top);

            var type = document.createElement("div");
            type.className = "timeline-context-meta";
            type.textContent = (item.type || "event").toUpperCase();
            card.appendChild(type);

            if (item.detail) {
                var body = document.createElement("div");
                body.className = "timeline-context-body";
                body.textContent = item.detail;
                card.appendChild(body);
            }

            list.appendChild(card);
        }

        return list;
    },

    _buildTimelineSource: function(event) {
        var box = document.createElement("div");
        box.className = "timeline-source-box";

        var metaParts = [];
        var confidence = Number(event.confidence);
        if (event.source_file) metaParts.push(event.source_file);
        if (event.source_page) metaParts.push("Page " + event.source_page);
        if (event.confidence != null && !isNaN(confidence)) {
            metaParts.push("Confidence " + Math.round(confidence * 100) + "%");
        }

        if (metaParts.length) {
            var meta = document.createElement("div");
            meta.className = "timeline-context-meta";
            meta.textContent = metaParts.join(" • ");
            box.appendChild(meta);
        }

        if (event.raw_text) {
            var raw = document.createElement("div");
            raw.className = "timeline-context-body";
            raw.textContent = event.raw_text;
            box.appendChild(raw);
        }

        return box;
    },

    _compactParts: function(parts) {
        return parts
            .filter(function(part) {
                return part !== null && part !== undefined && String(part).trim() !== "";
            })
            .join(" ");
    },

    _formatReferenceRange: function(low, high, unit) {
        if (low == null && high == null) return "";

        var range = "";
        if (low != null && high != null) {
            range = low + " to " + high;
        } else if (low != null) {
            range = ">= " + low;
        } else {
            range = "<= " + high;
        }

        if (unit) range += " " + unit;
        return range;
    },
};


// ══════════════════════════════════════════════════════════
//  Boot — Initialize on DOM ready
// ══════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", function() { App.init(); });

// Resize handler for responsive D3 visualizations
window.addEventListener("resize", (function() {
    var timer;
    return function() {
        clearTimeout(timer);
        timer = setTimeout(function() {
            if (typeof TimelineFlow !== "undefined") TimelineFlow.resize();
        }, 250);
    };
})());
