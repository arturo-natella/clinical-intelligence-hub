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


// ══════════════════════════════════════════════════════════
//  App — Main Application Controller
// ══════════════════════════════════════════════════════════

var App = {
    uploadedFiles: [],

    // ── Initialization ────────────────────────────────

    init: async function() {
        // Setup nav tab click handlers
        var tabs = document.querySelectorAll(".nav-tab");
        for (var i = 0; i < tabs.length; i++) {
            (function(tab) {
                tab.addEventListener("click", function() {
                    App.navigateTo(tab.dataset.view);
                });
            })(tabs[i]);
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
                $("main-nav").style.display = "flex";
                $("main-container").style.display = "block";
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
            $("main-nav").style.display = "flex";
            $("main-container").style.display = "block";

            if (result.has_profile) {
                App.loadAllData();
            }
        } catch (e) {
            $("passphrase-error").textContent = e.message || "Failed to unlock vault";
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

        // Update nav tabs
        var tabs = document.querySelectorAll(".nav-tab");
        for (var j = 0; j < tabs.length; j++) {
            if (tabs[j].dataset.view === view) {
                tabs[j].classList.add("active");
            } else {
                tabs[j].classList.remove("active");
            }
        }

        // Load data for the view if needed
        var loaders = {
            dashboard: function() { App.loadDashboard(); },
            medications: function() { App.loadMedications(); },
            labs: function() { App.loadLabs(); },
            imaging: function() { App.loadImaging(); },
            genetics: function() { App.loadGenetics(); },
            flags: function() { App.loadFlags(); },
            crossdisc: function() { App.loadCrossDisciplinary(); },
            community: function() { App.loadCommunity(); },
            timeline: function() { Timeline.load(); },
            alerts: function() { App.loadAlerts(); },
            report: function() { App.loadQuestions(); },
        };
        if (loaders[view]) loaders[view]();
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
            html += '<div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--border-glass); font-size:14px;">'
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

    listenProgress: function() {
        var evtSource = new EventSource("/api/progress");

        evtSource.onmessage = function(event) {
            var data = JSON.parse(event.data);

            if (data.pass === "heartbeat") return;

            if (data.percent >= 0) {
                $("progress-fill").style.width = data.percent + "%";
                $("progress-text").textContent = data.message;
            }

            if (data.pass === "complete") {
                evtSource.close();
                $("progress-card").style.display = "none";
                $("actions-card").style.display = "block";
                App.loadAllData();
            }

            if (data.pass === "error") {
                evtSource.close();
                $("progress-text").textContent = data.message;
                $("progress-fill").style.background = "var(--accent-red)";
            }
        };

        evtSource.onerror = function() {
            evtSource.close();
        };
    },

    // ── Load All Data ─────────────────────────────────

    loadAllData: async function() {
        App.loadDashboard();
        // Other views load on demand when navigated to
    },

    // ── Dashboard ─────────────────────────────────────

    loadDashboard: async function() {
        try {
            var results = await Promise.all([
                api("/api/medications"),
                api("/api/labs"),
                api("/api/diagnoses"),
                api("/api/flags"),
            ]);
            var meds = results[0];
            var labs = results[1];
            var diags = results[2];
            var flags = results[3];

            var activeMeds = meds.filter(function(m) {
                return ["active", "prn"].indexOf((m.status || "").toLowerCase()) >= 0;
            });
            var activeDx = diags.filter(function(d) {
                return ["active", "chronic"].indexOf((d.status || "").toLowerCase()) >= 0;
            });

            $("stat-conditions").textContent = activeDx.length || "0";
            $("stat-meds").textContent = activeMeds.length || "0";
            $("stat-labs").textContent = labs.length || "0";
            $("stat-flags").textContent = flags.length || "0";

            // Show actions if we have data
            if (meds.length > 0 || labs.length > 0) {
                $("actions-card").style.display = "block";
                $("upload-card").style.display = "none";
                $("files-card").style.display = "none";
            }
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

                    iHtml += '<div style="padding:12px 0; border-bottom:1px solid var(--border-glass);">'
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

            if (!labs.length) {
                safeSetHtml(tbody, '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No lab results found</td></tr>');
                return;
            }

            // Sort: flagged first, then by date
            var sorted = labs.slice().sort(function(a, b) {
                var aFlag = (a.flag && a.flag.toLowerCase() !== "normal") ? 0 : 1;
                var bFlag = (b.flag && b.flag.toLowerCase() !== "normal") ? 0 : 1;
                if (aFlag !== bFlag) return aFlag - bFlag;
                return (b.test_date || "").localeCompare(a.test_date || "");
            });

            var html = "";
            for (var i = 0; i < sorted.length; i++) {
                var l = sorted[i];
                var flag = (l.flag || "").toLowerCase();
                var flagBadge;
                if (flag === "high" || flag === "critical high") {
                    flagBadge = '<span class="badge badge-high">HIGH</span>';
                } else if (flag === "low" || flag === "critical low") {
                    flagBadge = '<span class="badge badge-moderate">LOW</span>';
                } else if (flag && flag !== "normal") {
                    flagBadge = '<span class="badge badge-warning">' + escapeHtml(l.flag) + "</span>";
                } else {
                    flagBadge = '<span class="badge badge-active">Normal</span>';
                }

                var value = l.value != null ? l.value : (l.value_text || "\u2014");
                html += "<tr>"
                    + "<td><strong>" + escapeHtml(l.name) + "</strong></td>"
                    + "<td>" + escapeHtml(String(value)) + "</td>"
                    + "<td>" + escapeHtml(l.unit || "") + "</td>"
                    + "<td>" + flagBadge + "</td>"
                    + "<td>" + formatDate(l.test_date) + "</td>"
                    + '<td style="font-size:12px; color:var(--text-muted);">' + formatProvenance(l.provenance) + "</td>"
                    + "</tr>";
            }
            safeSetHtml(tbody, html);
        } catch (e) { /* no data */ }
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
                    findingsHtml += '<div style="padding:8px 12px; background:var(--bg-glass); border-radius:8px; margin-top:8px;">'
                        + '<div style="font-size:14px;">' + escapeHtml(f.description || "") + "</div>"
                        + (f.body_region ? '<div style="font-size:12px; color:var(--text-muted); margin-top:4px;">Region: ' + escapeHtml(f.body_region) + "</div>" : "")
                        + (f.confidence ? '<div style="font-size:12px; color:var(--text-muted);">Confidence: ' + Math.round(f.confidence * 100) + "%</div>" : "")
                        + "</div>";
                }

                html += '<div style="padding:16px 0; border-bottom:1px solid var(--border-glass);">'
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

                html += '<div style="padding:16px 0; border-bottom:1px solid var(--border-glass);">'
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
            var container = $("crossdisc-list");

            if (!connections.length) {
                safeSetHtml(container, '<div style="color:var(--text-muted); text-align:center; padding:40px;">No cross-disciplinary connections found</div>');
                return;
            }

            var html = "";
            for (var i = 0; i < connections.length; i++) {
                var c = connections[i];

                var specHtml = "";
                if (c.specialties && c.specialties.length) {
                    specHtml = '<div style="margin-bottom:8px;"><span style="font-size:12px; color:var(--text-muted);">Specialties: </span>';
                    for (var j = 0; j < c.specialties.length; j++) {
                        specHtml += '<span class="badge badge-info" style="margin-right:4px;">' + escapeHtml(c.specialties[j]) + "</span>";
                    }
                    specHtml += "</div>";
                }

                var dataHtml = "";
                if (c.patient_data_points && c.patient_data_points.length) {
                    dataHtml = '<div style="margin-bottom:8px;"><span style="font-size:12px; color:var(--text-muted);">Your data: </span>';
                    for (var k = 0; k < c.patient_data_points.length; k++) {
                        dataHtml += '<span style="font-size:13px; color:var(--accent-teal); margin-right:12px;">' + escapeHtml(c.patient_data_points[k]) + "</span>";
                    }
                    dataHtml += "</div>";
                }

                var questionHtml = "";
                if (c.question_for_doctor) {
                    questionHtml = '<div style="background:var(--bg-glass); padding:12px; border-radius:8px; margin-top:8px;">'
                        + '<div style="font-size:12px; color:var(--accent-amber); margin-bottom:4px;">Ask your doctor:</div>'
                        + '<div style="font-size:14px;">' + escapeHtml(c.question_for_doctor) + "</div>"
                        + "</div>";
                }

                html += '<div class="card" style="border-left:3px solid var(--accent-purple); margin-bottom:12px;">'
                    + '<div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">'
                    + severityBadge(c.severity)
                    + '<strong style="font-size:15px;">' + escapeHtml(c.title || "") + "</strong>"
                    + "</div>"
                    + '<div style="color:var(--text-secondary); font-size:14px; line-height:1.6; margin-bottom:12px;">'
                    + escapeHtml(c.description || "") + "</div>"
                    + specHtml
                    + dataHtml
                    + questionHtml
                    + "</div>";
            }
            safeSetHtml(container, html);
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
                html += '<div style="padding:16px 0; border-bottom:1px solid var(--border-glass);">'
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
                html += '<div style="padding:16px 0; border-bottom:1px solid var(--border-glass);">'
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

    // ── Questions for Doctor ──────────────────────────

    loadQuestions: async function() {
        try {
            var questions = await api("/api/questions");
            var container = $("questions-list");

            if (questions.length) {
                $("questions-card").style.display = "block";
                var html = "";
                for (var i = 0; i < questions.length; i++) {
                    html += '<div style="padding:12px 0; border-bottom:1px solid var(--border-glass); display:flex; gap:12px; align-items:flex-start;">'
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
        if (!confirm("Start a new session? This will clear all patient data. API keys and model downloads are kept.")) {
            return;
        }

        try {
            await api("/api/session/clear", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });

            // Reset UI
            App.uploadedFiles = [];
            $("stat-conditions").textContent = "\u2014";
            $("stat-meds").textContent = "\u2014";
            $("stat-labs").textContent = "\u2014";
            $("stat-flags").textContent = "\u2014";
            safeSetHtml("file-list", "");
            $("upload-card").style.display = "block";
            $("files-card").style.display = "none";
            $("progress-card").style.display = "none";
            $("actions-card").style.display = "none";
            $("interactions-card").style.display = "none";
            $("questions-card").style.display = "none";
            $("report-download-btn").style.display = "none";
            $("report-status").textContent = "No report generated yet.";
            App.navigateTo("dashboard");
        } catch (e) {
            alert("Failed to clear session: " + e.message);
        }
    },

    // ── Settings ──────────────────────────────────────

    showSettings: async function() {
        $("settings-overlay").style.display = "flex";

        // Load current key status
        try {
            var status = await api("/api/keys/status");
            var geminiStatus = $("gemini-key-status");
            geminiStatus.textContent = status.gemini ? "Configured" : "Not set";
            geminiStatus.style.color = status.gemini ? "var(--accent-green)" : "var(--accent-amber)";
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

        App.hideSettings();
    },
};


// ══════════════════════════════════════════════════════════
//  BodyMap — 3D Anatomy Viewer Controller
// ══════════════════════════════════════════════════════════

var BodyMap = {
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

    // Body region to clinical keyword mapping
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
        BodyMap.currentLayer = layer;
        var key = layer + "-" + BodyMap.currentSide;
        $("bodymap-img").src = BodyMap.layerImages[key] || BodyMap.layerImages["skin-front"];

        // Update active button
        var btns = document.querySelectorAll(".bodymap-layer");
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].dataset.layer === layer) {
                btns[i].classList.add("active");
            } else {
                btns[i].classList.remove("active");
            }
        }
    },

    toggleSide: function() {
        BodyMap.currentSide = BodyMap.currentSide === "front" ? "back" : "front";
        $("bodymap-side-btn").textContent = BodyMap.currentSide === "front" ? "Show Back" : "Show Front";
        BodyMap.setLayer(BodyMap.currentLayer);
    },

    selectRegion: async function(region) {
        // Highlight selected zone
        var zones = document.querySelectorAll(".bodymap-zone");
        for (var i = 0; i < zones.length; i++) {
            var isSelected = zones[i].dataset.region === region;
            zones[i].style.fill = isSelected ? "rgba(59, 130, 246, 0.2)" : "transparent";
            zones[i].style.stroke = isSelected ? "#3b82f6" : "none";
            zones[i].style.strokeWidth = isSelected ? "2" : "0";
        }

        var regionName = region.replace(/-/g, " ").replace(/\b\w/g, function(c) { return c.toUpperCase(); });
        $("bodymap-region-title").textContent = regionName;

        // Search for relevant findings
        var keywords = BodyMap.regionMapping[region] || [];
        var findings = [];

        try {
            var results = await Promise.all([
                api("/api/diagnoses"),
                api("/api/imaging"),
                api("/api/labs"),
                api("/api/flags"),
            ]);
            var diagnoses = results[0];
            var imaging = results[1];
            var labs = results[2];
            var flags = results[3];

            // Search diagnoses
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

            // Search imaging
            for (var c = 0; c < imaging.length; c++) {
                var study = imaging[c];
                var studyText = ((study.body_region || "") + " " + (study.description || "")).toLowerCase();
                var matched = false;
                for (var d = 0; d < keywords.length; d++) {
                    if (studyText.indexOf(keywords[d]) >= 0) { matched = true; break; }
                }
                if (matched) {
                    var studyFindings = study.findings || [];
                    if (studyFindings.length) {
                        for (var e = 0; e < studyFindings.length; e++) {
                            findings.push({ type: "Imaging", text: studyFindings[e].description, detail: study.modality + " " + formatDate(study.study_date) });
                        }
                    } else {
                        findings.push({ type: "Imaging", text: study.description || study.modality, detail: formatDate(study.study_date) });
                    }
                }
            }

            // Search flags
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

        // Render findings
        var container = $("bodymap-findings");
        if (findings.length === 0) {
            container.textContent = "No findings related to this region in your records.";
            container.style.color = "var(--text-muted)";
        } else {
            var html = "";
            for (var m = 0; m < findings.length; m++) {
                var fn = findings[m];
                html += '<div style="padding:8px 0; border-bottom:1px solid var(--border-glass);">'
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
//  Timeline — Health Timeline Controller
// ══════════════════════════════════════════════════════════

var Timeline = {
    events: [],
    currentFilter: "all",

    load: async function() {
        try {
            Timeline.events = await api("/api/timeline");
            Timeline.render();
        } catch (e) { /* no data */ }
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
        var container = $("timeline-list");
        var events = Timeline.events;

        if (Timeline.currentFilter !== "all") {
            events = events.filter(function(e) {
                return e.type === Timeline.currentFilter;
            });
        }

        if (!events.length) {
            safeSetHtml(container, '<div style="color:var(--text-muted); text-align:center; padding:40px;">No events to display.</div>');
            return;
        }

        var html = "";
        for (var i = 0; i < events.length; i++) {
            var e = events[i];
            html += '<div class="timeline-item">'
                + '<div class="timeline-dot ' + escapeHtml(e.type) + '"></div>'
                + '<div class="timeline-date">' + formatDate(e.date) + "</div>"
                + '<div style="flex:1;">'
                + '<div class="timeline-title">' + escapeHtml(e.title) + "</div>"
                + '<div class="timeline-detail">' + escapeHtml(e.detail || "") + "</div>"
                + "</div>"
                + '<span class="badge badge-info" style="align-self:flex-start;">' + escapeHtml(e.type) + "</span>"
                + "</div>";
        }
        safeSetHtml(container, html);
    },
};


// ══════════════════════════════════════════════════════════
//  Boot — Initialize on DOM ready
// ══════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", function() { App.init(); });
