/* ══════════════════════════════════════════════════════════
   Symptom Logger — Setup Wizard, Episode Logging, Counter-Evidence

   Parent-child model:
     Symptom (named category) → Episodes (occurrences) + CounterDefinitions (doctor claims)

   Security: All dynamic content escaped via escapeHtml() / createElement.
   Uses safeSetHtml() for pre-escaped HTML strings (same pattern as app.js, snowball.js).
   ══════════════════════════════════════════════════════════ */

var Symptoms = {

    _data: [],          // array of symptom objects from API
    _activeFilter: null, // severity filter: null | "high" | "mid" | "low"

    // ── Load & Render ────────────────────────────────────

    load: async function() {
        try {
            this._data = await api("/api/symptoms");
        } catch (e) {
            this._data = [];
        }
        this.render();
    },

    render: function() {
        var container = $("symptoms-list");
        if (!container) return;

        while (container.firstChild) container.removeChild(container.firstChild);

        // Split into active and archived
        var active = [];
        var archived = [];
        for (var a = 0; a < this._data.length; a++) {
            if (this._data[a].archived) {
                archived.push(this._data[a]);
            } else {
                active.push(this._data[a]);
            }
        }

        var filtered = active;
        if (this._activeFilter) {
            var f = this._activeFilter;
            filtered = active.filter(function(s) {
                return s.episodes && s.episodes.some(function(ep) {
                    return (ep.severity || "mid") === f;
                });
            });
        }

        if (filtered.length === 0 && archived.length === 0) {
            var empty = document.createElement("div");
            empty.className = "empty-state";
            var p = document.createElement("p");
            p.style.cssText = "color:var(--text-muted); text-align:center; padding:40px 20px;";
            p.textContent = "No symptoms tracked yet. Click + Track Symptom to start.";
            empty.appendChild(p);
            container.appendChild(empty);
            return;
        }

        if (filtered.length === 0 && active.length > 0) {
            var noMatch = document.createElement("div");
            noMatch.style.cssText = "color:var(--text-muted); text-align:center; padding:20px;";
            noMatch.textContent = "No symptoms match this filter.";
            container.appendChild(noMatch);
        }

        for (var i = 0; i < filtered.length; i++) {
            container.appendChild(this._renderSymptomCard(filtered[i]));
        }

        // Archived section
        if (archived.length > 0) {
            var archSection = document.createElement("div");
            archSection.style.cssText = "margin-top:24px; border-top:1px solid var(--border-faint); padding-top:16px;";

            var archToggle = document.createElement("button");
            archToggle.className = "btn btn-sm btn-outline";
            archToggle.style.cssText = "color:var(--text-muted); border-color:var(--border-faint); margin-bottom:12px;";
            archToggle.textContent = "Archived (" + archived.length + ")";
            archToggle.onclick = function() {
                var list = archSection.querySelector(".archived-list");
                var showing = list.style.display !== "none";
                list.style.display = showing ? "none" : "block";
                archToggle.textContent = showing
                    ? "Archived (" + archived.length + ")"
                    : "Hide Archived";
            };
            archSection.appendChild(archToggle);

            var archList = document.createElement("div");
            archList.className = "archived-list";
            archList.style.display = "none";

            for (var ai = 0; ai < archived.length; ai++) {
                archList.appendChild(this._renderSymptomCard(archived[ai]));
            }
            archSection.appendChild(archList);
            container.appendChild(archSection);
        }
    },

    // ── Severity Filter ──────────────────────────────────

    filter: function(severity) {
        if (severity === "all" || this._activeFilter === severity) {
            this._activeFilter = null;
        } else {
            this._activeFilter = severity;
        }

        var btns = document.querySelectorAll(".symptom-filter");
        for (var i = 0; i < btns.length; i++) {
            var sev = btns[i].dataset.severity;
            if (this._activeFilter === null) {
                btns[i].classList.toggle("active", sev === "all");
            } else {
                btns[i].classList.toggle("active", sev === this._activeFilter);
            }
        }
        this.render();
    },

    // ── Symptom Card ─────────────────────────────────────

    _renderSymptomCard: function(symptom) {
        var isArchived = !!symptom.archived;
        var card = document.createElement("div");
        card.className = "symptom-card";
        if (isArchived) card.style.opacity = "0.55";

        // Header
        var header = document.createElement("div");
        header.className = "symptom-card-header";

        var title = document.createElement("span");
        title.className = "symptom-card-title";
        title.textContent = symptom.symptom_name;

        var badge = document.createElement("span");
        badge.className = "badge badge-info";
        badge.textContent = (symptom.episode_count || 0) + " episodes";

        var actions = document.createElement("div");
        actions.className = "symptom-card-actions";

        if (!isArchived) {
            var logBtn = document.createElement("button");
            logBtn.className = "btn btn-sm btn-primary";
            logBtn.textContent = "Log Episode";
            logBtn.onclick = function() { Symptoms.openAddEpisode(symptom.symptom_id); };
            actions.appendChild(logBtn);

            var counterBtn = document.createElement("button");
            counterBtn.className = "btn btn-sm btn-outline";
            counterBtn.textContent = "+ Counter";
            counterBtn.title = "Track what your doctor says causes this symptom \u2014 build evidence over time";
            counterBtn.onclick = function() { Symptoms.openAddCounter(symptom.symptom_id); };
            actions.appendChild(counterBtn);
        }

        var archiveBtn = document.createElement("button");
        archiveBtn.className = "btn btn-sm btn-outline";
        archiveBtn.style.cssText = isArchived
            ? "color:var(--accent-teal); border-color:var(--accent-teal);"
            : "color:var(--text-muted); border-color:var(--border-faint);";
        archiveBtn.textContent = isArchived ? "Restore" : "Archive";
        archiveBtn.title = isArchived ? "Restore this symptom to active tracking" : "Hide from main view (data is kept)";
        archiveBtn.onclick = function() { Symptoms.toggleArchive(symptom.symptom_id); };
        actions.appendChild(archiveBtn);

        header.appendChild(title);
        header.appendChild(badge);
        header.appendChild(actions);
        card.appendChild(header);

        // Counter-evidence stats (the killer stat)
        var stats = symptom.counter_stats || [];
        var activeCounters = stats.filter(function(c) { return !c.archived; });
        var archivedCounters = stats.filter(function(c) { return c.archived; });

        if (activeCounters.length > 0) {
            var counterSection = document.createElement("div");
            counterSection.className = "counter-evidence-section";

            for (var ci = 0; ci < activeCounters.length; ci++) {
                counterSection.appendChild(this._renderCounterStat(activeCounters[ci], symptom.symptom_id));
            }
            card.appendChild(counterSection);
        }

        // Archived counters (collapsible)
        if (archivedCounters.length > 0) {
            var archivedSection = document.createElement("div");
            archivedSection.className = "counter-archived-section";

            var archivedToggle = document.createElement("button");
            archivedToggle.className = "btn btn-sm btn-outline counter-archived-toggle";
            archivedToggle.textContent = "Resolved (" + archivedCounters.length + ")";
            var archSid = symptom.symptom_id;
            archivedToggle.onclick = function() {
                var list = this.parentElement.querySelector(".counter-archived-list");
                list.style.display = list.style.display === "none" ? "block" : "none";
                this.classList.toggle("expanded");
            };
            archivedSection.appendChild(archivedToggle);

            var archivedList = document.createElement("div");
            archivedList.className = "counter-archived-list";
            archivedList.style.display = "none";

            for (var ai = 0; ai < archivedCounters.length; ai++) {
                archivedList.appendChild(this._renderCounterStat(archivedCounters[ai], symptom.symptom_id));
            }
            archivedSection.appendChild(archivedList);
            card.appendChild(archivedSection);
        }

        // Episodes table (expandable)
        var episodes = symptom.episodes || [];
        if (episodes.length > 0) {
            var epSection = document.createElement("div");
            epSection.className = "symptom-episodes-section";

            var epCount = episodes.length;
            var epToggle = document.createElement("button");
            epToggle.className = "btn btn-sm btn-outline symptom-episodes-toggle";
            epToggle.textContent = "Show Episodes (" + epCount + ")";
            epToggle.onclick = function() {
                var tbl = this.parentElement.querySelector(".symptom-episodes-table");
                var showing = tbl.style.display !== "none";
                tbl.style.display = showing ? "none" : "table";
                this.textContent = showing
                    ? "Show Episodes (" + epCount + ")"
                    : "Hide Episodes";
            };
            epSection.appendChild(epToggle);

            var table = document.createElement("table");
            table.className = "symptom-episodes-table data-table";
            table.style.display = "none";

            var thead = document.createElement("thead");
            var headRow = document.createElement("tr");
            var headers = ["Date", "Time", "Severity", "Description", "Triggers", ""];
            for (var hi = 0; hi < headers.length; hi++) {
                var th = document.createElement("th");
                th.textContent = headers[hi];
                headRow.appendChild(th);
            }
            thead.appendChild(headRow);
            table.appendChild(thead);

            var tbody = document.createElement("tbody");
            // Most recent first
            var sorted = episodes.slice().sort(function(a, b) {
                return (b.episode_date || "").localeCompare(a.episode_date || "");
            });

            for (var ei = 0; ei < sorted.length; ei++) {
                tbody.appendChild(this._renderEpisodeRow(sorted[ei], symptom.symptom_id));
            }
            table.appendChild(tbody);
            epSection.appendChild(table);
            card.appendChild(epSection);
        }

        return card;
    },

    _renderEpisodeRow: function(ep, symptomId) {
        var row = document.createElement("tr");

        var dateCell = document.createElement("td");
        dateCell.textContent = formatDate(ep.episode_date);
        row.appendChild(dateCell);

        var timeCell = document.createElement("td");
        timeCell.textContent = ep.time_of_day || "\u2014";
        row.appendChild(timeCell);

        var sevCell = document.createElement("td");
        var sevMap = {high: "badge-critical", mid: "badge-moderate", low: "badge-low"};
        var sevSpan = document.createElement("span");
        sevSpan.className = "badge " + (sevMap[ep.severity] || "badge-info");
        sevSpan.textContent = (ep.severity || "mid").toUpperCase();
        sevCell.appendChild(sevSpan);
        row.appendChild(sevCell);

        var descCell = document.createElement("td");
        var desc = ep.description || "";
        descCell.textContent = desc.length > 80 ? desc.substring(0, 80) + "\u2026" : desc;
        row.appendChild(descCell);

        var trigCell = document.createElement("td");
        trigCell.textContent = ep.triggers || "\u2014";
        row.appendChild(trigCell);

        var actCell = document.createElement("td");
        var delBtn = document.createElement("button");
        delBtn.className = "btn btn-sm btn-outline";
        delBtn.style.cssText = "color:var(--accent-red); border-color:var(--accent-red); padding:2px 6px;";
        delBtn.textContent = "\u2715";
        var eid = ep.episode_id;
        var sid = symptomId;
        delBtn.onclick = function() {
            Symptoms.deleteEpisode(sid, eid);
        };
        actCell.appendChild(delBtn);
        row.appendChild(actCell);

        return row;
    },

    // ── Counter Stat Display ─────────────────────────────

    _renderCounterStat: function(stat, symptomId) {
        var div = document.createElement("div");
        div.className = "counter-stat" + (stat.archived ? " counter-archived" : "");

        var label = document.createElement("div");
        label.className = "counter-stat-label";

        var claimSpan = document.createElement("span");
        claimSpan.className = "counter-claim";
        claimSpan.textContent = "Doctor says: " + stat.doctor_claim;
        label.appendChild(claimSpan);

        // Archive/Unarchive button
        var archiveBtn = document.createElement("button");
        archiveBtn.className = "btn btn-sm btn-outline counter-archive-btn";
        archiveBtn.textContent = stat.archived ? "Reactivate" : "Resolve";
        var cid = stat.counter_id;
        var archSid = symptomId;
        archiveBtn.onclick = function() {
            Symptoms.archiveCounter(archSid, cid);
        };
        label.appendChild(archiveBtn);
        div.appendChild(label);

        // Data display
        var dataDiv = document.createElement("div");
        dataDiv.className = "counter-stat-data";

        if (stat.episodes_tracked === 0) {
            dataDiv.textContent = "No data yet \u2014 log episodes to build evidence.";
            dataDiv.style.color = "var(--text-muted)";
        } else if (stat.measure_type === "scale") {
            var avg = stat.average || 0;
            var dataLabel = document.createElement("span");
            dataLabel.textContent = "Your data: Average " + (stat.measure_label || stat.doctor_claim) + " ";
            var strong = document.createElement("strong");
            strong.textContent = avg + "/5";
            var suffix = document.createTextNode(" across " + stat.episodes_tracked + " episodes");
            dataDiv.appendChild(dataLabel);
            dataDiv.appendChild(strong);
            dataDiv.appendChild(suffix);
        } else if (stat.measure_type === "yes_no") {
            var noPct = 100 - (stat.yes_percent || 0);
            var yLabel = document.createElement("span");
            yLabel.textContent = "Your data: " + stat.doctor_claim + " \u2014 ";
            var yStrong = document.createElement("strong");
            yStrong.textContent = "No " + noPct + "%";
            var ySuffix = document.createTextNode(" of " + stat.episodes_tracked + " episodes");
            dataDiv.appendChild(yLabel);
            dataDiv.appendChild(yStrong);
            dataDiv.appendChild(ySuffix);
        } else {
            dataDiv.textContent = stat.episodes_tracked + " episodes tracked with notes.";
        }

        div.appendChild(dataDiv);
        return div;
    },

    // ── Setup Wizard (3-Card Flow) ───────────────────────

    openAddSymptom: function() {
        this._wizardState = { step: 1, name: "", counter: null };
        this._showWizardStep(1);
        var overlay = $("symptom-wizard-overlay");
        if (overlay) overlay.style.display = "flex";
    },

    _wizardState: { step: 1, name: "", counter: null },

    _showWizardStep: function(step) {
        this._wizardState.step = step;
        var content = $("symptom-wizard-modal");
        if (!content) return;

        content.innerHTML = "";

        if (step === 1) {
            this._buildWizardCard1(content);
        } else if (step === 2) {
            this._buildWizardCard2(content);
        } else if (step === 3) {
            this._buildWizardCard3(content);
        }
    },

    _buildWizardCard1: function(container) {
        var self = this;
        var card = document.createElement("div");
        card.className = "wizard-card";

        var h3 = document.createElement("h3");
        h3.className = "wizard-title";
        h3.textContent = "Log a symptom";
        card.appendChild(h3);

        // Existing symptoms — quick-pick grid (active only)
        var existing = (this._data || []).filter(function(s) { return !s.archived; });
        if (existing.length > 0) {
            var subExisting = document.createElement("p");
            subExisting.style.cssText = "font-size:13px; color:var(--text-muted); margin:0 0 10px 0;";
            subExisting.textContent = "Quick log to an existing symptom:";
            card.appendChild(subExisting);

            var grid = document.createElement("div");
            grid.id = "wizard-existing-grid";
            grid.style.cssText = "display:flex; flex-wrap:wrap; gap:8px; margin-bottom:20px;";

            for (var i = 0; i < existing.length; i++) {
                (function(sym) {
                    var btn = document.createElement("button");
                    btn.className = "btn btn-outline wizard-existing-btn";
                    btn.style.cssText = "font-size:13px; padding:6px 14px; border-radius:6px; white-space:nowrap;";
                    btn.textContent = sym.symptom_name;
                    btn.dataset.name = (sym.symptom_name || "").toLowerCase();
                    btn.onclick = function() {
                        // Go straight to episode logging for this symptom
                        self.closeWizard();
                        self.openAddEpisode(sym.symptom_id);
                    };
                    grid.appendChild(btn);
                })(existing[i]);
            }
            card.appendChild(grid);

            // Divider
            var divider = document.createElement("div");
            divider.style.cssText = "display:flex; align-items:center; gap:12px; margin:8px 0 16px 0;";
            var line1 = document.createElement("div");
            line1.style.cssText = "flex:1; height:1px; background:var(--border-faint);";
            var orText = document.createElement("span");
            orText.style.cssText = "font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.08em;";
            orText.textContent = "or";
            var line2 = document.createElement("div");
            line2.style.cssText = "flex:1; height:1px; background:var(--border-faint);";
            divider.appendChild(line1);
            divider.appendChild(orText);
            divider.appendChild(line2);
            card.appendChild(divider);
        }

        // New symptom input with search filtering
        var newLabel = document.createElement("p");
        newLabel.style.cssText = "font-size:13px; color:var(--text-muted); margin:0 0 8px 0;";
        newLabel.textContent = existing.length > 0
            ? "Track something new:"
            : "What symptom do you want to track?";
        card.appendChild(newLabel);

        var inputRow = document.createElement("div");
        inputRow.style.cssText = "display:flex; gap:8px; align-items:center;";

        var input = document.createElement("input");
        input.type = "text";
        input.id = "wizard-symptom-name";
        input.className = "form-input";
        input.placeholder = "e.g. Headaches, Nerve pain on left leg";
        input.style.flex = "1";

        // Archived match hint container
        var archiveHint = document.createElement("div");
        archiveHint.id = "wizard-archive-hint";
        archiveHint.style.cssText = "display:none; margin-top:10px; padding:10px 14px; border-radius:8px; "
            + "background:rgba(78,154,241,0.10); border:1px solid var(--accent-blue); font-size:13px;";

        var _archiveCheckTimer = null;

        // Filter existing buttons + check archived matches as user types
        input.addEventListener("input", function() {
            var val = input.value.trim().toLowerCase();
            var grid = document.getElementById("wizard-existing-grid");
            if (grid) {
                var btns = grid.querySelectorAll(".wizard-existing-btn");
                for (var b = 0; b < btns.length; b++) {
                    var match = !val || btns[b].dataset.name.indexOf(val) !== -1;
                    btns[b].style.display = match ? "" : "none";
                }
            }

            // Debounced check for archived fuzzy match
            clearTimeout(_archiveCheckTimer);
            var hint = document.getElementById("wizard-archive-hint");
            if (val.length < 3) {
                if (hint) hint.style.display = "none";
                return;
            }
            _archiveCheckTimer = setTimeout(function() {
                api("/api/symptoms/check-archived", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: val }),
                }).then(function(res) {
                    var hint = document.getElementById("wizard-archive-hint");
                    if (!hint) return;
                    if (res && res.match) {
                        var m = res.match;
                        while (hint.firstChild) hint.removeChild(hint.firstChild);

                        var icon = document.createElement("span");
                        icon.textContent = "\uD83D\uDCE6 ";
                        hint.appendChild(icon);

                        var msg = document.createElement("span");
                        msg.textContent = "Found archived: \"" + m.symptom_name + "\" (" + m.episode_count + " episodes). ";
                        hint.appendChild(msg);

                        var restoreBtn = document.createElement("button");
                        restoreBtn.className = "btn btn-sm btn-primary";
                        restoreBtn.style.cssText = "margin-left:8px; padding:3px 12px; font-size:12px;";
                        restoreBtn.textContent = "Restore & Continue";
                        restoreBtn.onclick = function() {
                            api("/api/symptoms/" + m.symptom_id + "/archive", { method: "PATCH" }).then(function() {
                                Symptoms.closeWizard();
                                Symptoms.load();
                            });
                        };
                        hint.appendChild(restoreBtn);
                        hint.style.display = "block";
                    } else {
                        hint.style.display = "none";
                    }
                }).catch(function() {});
            }, 300);
        });

        // Enter key advances to next step
        input.addEventListener("keydown", function(e) {
            if (e.key === "Enter") Symptoms._wizardNext();
        });

        inputRow.appendChild(input);
        card.appendChild(inputRow);
        card.appendChild(archiveHint);

        var actions = document.createElement("div");
        actions.className = "wizard-actions";

        var cancelBtn = document.createElement("button");
        cancelBtn.className = "btn btn-outline";
        cancelBtn.textContent = "Cancel";
        cancelBtn.onclick = function() { Symptoms.closeWizard(); };

        var nextBtn = document.createElement("button");
        nextBtn.className = "btn btn-primary";
        nextBtn.textContent = "+ Add New Symptom";
        nextBtn.onclick = function() { Symptoms._wizardNext(); };

        actions.appendChild(cancelBtn);
        actions.appendChild(nextBtn);
        card.appendChild(actions);

        container.appendChild(card);

        setTimeout(function() { input.focus(); }, 100);
    },

    _buildWizardCard2: function(container) {
        var card = document.createElement("div");
        card.className = "wizard-card";

        var h3 = document.createElement("h3");
        h3.className = "wizard-title";
        h3.textContent = "Does your doctor say your " + this._wizardState.name + " are caused by something, but you know it\u2019s not?";
        card.appendChild(h3);

        var sub = document.createElement("p");
        sub.className = "wizard-subtext";
        sub.textContent = "You know your body. Let\u2019s track the evidence.";
        card.appendChild(sub);

        var choiceGroup = document.createElement("div");
        choiceGroup.id = "wizard-counter-choice";
        choiceGroup.className = "wizard-choice-group";

        var yesBtn = document.createElement("button");
        yesBtn.className = "btn btn-primary wizard-choice-btn";
        yesBtn.textContent = "Yes, they say it\u2019s...";
        yesBtn.onclick = function() { Symptoms._wizardShowCounterInput(); };

        var skipBtn = document.createElement("button");
        skipBtn.className = "btn btn-outline wizard-choice-btn";
        skipBtn.textContent = "Skip \u2014 no counter needed";
        skipBtn.onclick = function() { Symptoms._wizardSkipCounter(); };

        choiceGroup.appendChild(yesBtn);
        choiceGroup.appendChild(skipBtn);
        card.appendChild(choiceGroup);

        var inputSection = document.createElement("div");
        inputSection.id = "wizard-counter-input";
        inputSection.style.display = "none";
        inputSection.style.marginTop = "16px";

        var lbl = document.createElement("label");
        lbl.className = "form-label";
        lbl.textContent = "What do they say causes it?";
        inputSection.appendChild(lbl);

        var claimInput = document.createElement("input");
        claimInput.type = "text";
        claimInput.id = "wizard-doctor-claim";
        claimInput.className = "form-input";
        claimInput.placeholder = "e.g. stress, anxiety, sitting weird";
        inputSection.appendChild(claimInput);

        var actions2 = document.createElement("div");
        actions2.className = "wizard-actions";
        actions2.style.marginTop = "16px";

        var backBtn = document.createElement("button");
        backBtn.className = "btn btn-outline";
        backBtn.textContent = "\u2190 Back";
        backBtn.onclick = function() { Symptoms._showWizardStep(1); };

        var nextBtn2 = document.createElement("button");
        nextBtn2.className = "btn btn-primary";
        nextBtn2.textContent = "Next \u2192";
        nextBtn2.onclick = function() { Symptoms._wizardNext(); };

        actions2.appendChild(backBtn);
        actions2.appendChild(nextBtn2);
        inputSection.appendChild(actions2);

        card.appendChild(inputSection);
        container.appendChild(card);
    },

    _buildWizardCard3: function(container) {
        var card = document.createElement("div");
        card.className = "wizard-card";

        var h3 = document.createElement("h3");
        h3.className = "wizard-title";
        h3.textContent = "How should we measure \u2018" + this._wizardState.counter.doctor_claim + "\u2019 each time?";
        card.appendChild(h3);

        var sub = document.createElement("p");
        sub.className = "wizard-subtext";
        sub.textContent = "Each time you log an episode, we\u2019ll ask about this so you can build evidence over time.";
        card.appendChild(sub);

        var options = document.createElement("div");
        options.className = "wizard-measure-options";

        var types = [
            { value: "scale", label: "Scale 1\u20135 (low to high)" },
            { value: "yes_no", label: "Yes or No" },
            { value: "free_text", label: "Free text" }
        ];

        for (var i = 0; i < types.length; i++) {
            var opt = document.createElement("label");
            opt.className = "wizard-measure-option";

            var radio = document.createElement("input");
            radio.type = "radio";
            radio.name = "measure-type";
            radio.value = types[i].value;
            if (i === 0) radio.checked = true;

            opt.appendChild(radio);
            opt.appendChild(document.createTextNode(" " + types[i].label));
            options.appendChild(opt);
        }
        card.appendChild(options);

        var actions = document.createElement("div");
        actions.className = "wizard-actions";

        var backBtn = document.createElement("button");
        backBtn.className = "btn btn-outline";
        backBtn.textContent = "\u2190 Back";
        backBtn.onclick = function() { Symptoms._showWizardStep(2); };

        var createBtn = document.createElement("button");
        createBtn.className = "btn btn-primary";
        createBtn.textContent = "Create Tracker";
        createBtn.onclick = function() { Symptoms._wizardCreate(); };

        actions.appendChild(backBtn);
        actions.appendChild(createBtn);
        card.appendChild(actions);

        container.appendChild(card);
    },

    _wizardShowCounterInput: function() {
        var choice = $("wizard-counter-choice");
        var input = $("wizard-counter-input");
        if (choice) choice.style.display = "none";
        if (input) input.style.display = "block";
        var inp = $("wizard-doctor-claim");
        if (inp) inp.focus();
    },

    _wizardSkipCounter: function() {
        this._wizardState.counter = null;
        this._wizardCreate();
    },

    _wizardNext: function() {
        var step = this._wizardState.step;

        if (step === 1) {
            var nameInput = $("wizard-symptom-name");
            var name = nameInput ? nameInput.value.trim() : "";
            if (!name) return;
            this._wizardState.name = name;
            this._showWizardStep(2);

        } else if (step === 2) {
            var claimInput = $("wizard-doctor-claim");
            var claim = claimInput ? claimInput.value.trim() : "";
            if (!claim) return;
            this._wizardState.counter = { doctor_claim: claim, measure_type: "scale" };
            this._showWizardStep(3);
        }
    },

    _wizardCreate: async function() {
        var state = this._wizardState;
        var body = { symptom_name: state.name };

        if (state.counter) {
            var radios = document.querySelectorAll('input[name="measure-type"]');
            var mtype = "scale";
            for (var i = 0; i < radios.length; i++) {
                if (radios[i].checked) { mtype = radios[i].value; break; }
            }
            state.counter.measure_type = mtype;
            body.counter = state.counter;
        }

        try {
            var result = await api("/api/symptoms", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            this.closeWizard();
            if (result && result.restored) {
                alert("Restored archived symptom: " + result.restored_name);
            }
            this.load();
        } catch (e) {
            if (e.message && e.message.indexOf("already exists") !== -1) {
                alert("That symptom already exists in your active list.");
            } else {
                alert("Failed to create symptom: " + e.message);
            }
        }
    },

    closeWizard: function() {
        var overlay = $("symptom-wizard-overlay");
        if (overlay) overlay.style.display = "none";
    },

    // ── Episode Logging Modal ────────────────────────────

    openAddEpisode: function(symptomId) {
        var symptom = null;
        for (var i = 0; i < this._data.length; i++) {
            if (this._data[i].symptom_id === symptomId) {
                symptom = this._data[i];
                break;
            }
        }
        if (!symptom) return;

        this._currentEpisodeSymptom = symptom;

        var modal = $("episode-modal-overlay");
        var content = $("episode-modal");
        if (!modal || !content) return;

        content.innerHTML = "";
        this._buildEpisodeForm(content, symptom);
        modal.style.display = "flex";
    },

    _buildEpisodeForm: function(container, symptom, overrideDate) {
        var card = document.createElement("div");
        card.className = "wizard-card";

        var h3 = document.createElement("h3");
        h3.className = "wizard-title";
        h3.textContent = "Log Episode: " + symptom.symptom_name;
        card.appendChild(h3);

        var today = new Date().toISOString().split("T")[0];
        var dateValue = overrideDate || today;
        var isCatchUp = !!overrideDate;

        // Catch-up mode banner
        if (isCatchUp) {
            var banner = document.createElement("div");
            banner.className = "catchup-banner";
            banner.textContent = "\u23f3 Catch-up mode \u2014 logging past episodes. Date auto-advances backward.";
            card.appendChild(banner);
        }

        // Form grid
        var grid = document.createElement("div");
        grid.className = "form-grid";

        // Date — defaults to today with hint
        var dateGroup = this._formGroup("Date", "date", "ep-date", dateValue);
        var dateHint = document.createElement("span");
        dateHint.className = "form-hint";
        dateHint.textContent = "Defaults to today \u2014 change if logging a past episode";
        dateGroup.appendChild(dateHint);
        grid.appendChild(dateGroup);

        // Time of day
        var timeGroup = document.createElement("div");
        timeGroup.className = "form-group";
        var timeLbl = document.createElement("label");
        timeLbl.className = "form-label";
        timeLbl.textContent = "Time of Day";
        timeGroup.appendChild(timeLbl);
        var timeSelect = document.createElement("select");
        timeSelect.id = "ep-time";
        timeSelect.className = "form-input";
        var timeOpts = [["", "\u2014"], ["morning", "Morning"], ["afternoon", "Afternoon"], ["evening", "Evening"], ["night", "Night"]];
        for (var ti = 0; ti < timeOpts.length; ti++) {
            var opt = document.createElement("option");
            opt.value = timeOpts[ti][0];
            opt.textContent = timeOpts[ti][1];
            timeSelect.appendChild(opt);
        }
        timeGroup.appendChild(timeSelect);
        grid.appendChild(timeGroup);

        // Severity
        var sevGroup = document.createElement("div");
        sevGroup.className = "form-group";
        var sevLbl = document.createElement("label");
        sevLbl.className = "form-label";
        sevLbl.textContent = "Severity";
        sevGroup.appendChild(sevLbl);
        var sevSelect = document.createElement("select");
        sevSelect.id = "ep-severity";
        sevSelect.className = "form-input";
        var sevOpts = [["high", "High"], ["mid", "Mid"], ["low", "Low"]];
        for (var si = 0; si < sevOpts.length; si++) {
            var sopt = document.createElement("option");
            sopt.value = sevOpts[si][0];
            sopt.textContent = sevOpts[si][1];
            if (sevOpts[si][0] === "mid") sopt.selected = true;
            sevSelect.appendChild(sopt);
        }
        sevGroup.appendChild(sevSelect);
        grid.appendChild(sevGroup);

        // Duration
        var durGroup = this._formGroup("Duration", "text", "ep-duration", "", "e.g. 2 hours, all day");
        grid.appendChild(durGroup);

        card.appendChild(grid);

        // Description
        var descGroup = document.createElement("div");
        descGroup.className = "form-group";
        var descLbl = document.createElement("label");
        descLbl.className = "form-label";
        descLbl.textContent = "What happened?";
        descGroup.appendChild(descLbl);
        var descArea = document.createElement("textarea");
        descArea.id = "ep-description";
        descArea.className = "form-input form-textarea";
        descArea.placeholder = "Describe what you experienced...";
        descGroup.appendChild(descArea);
        card.appendChild(descGroup);

        // Triggers
        var trigGroup = this._formGroup("Triggers", "text", "ep-triggers", "", "e.g. after skipping lunch, stress at work");
        card.appendChild(trigGroup);

        // Counter prompts (prompted but skippable)
        var counters = (symptom.counter_definitions || []).filter(function(c) { return !c.archived; });
        if (counters.length > 0) {
            var counterDiv = document.createElement("div");
            counterDiv.className = "episode-counters-section";

            var counterLabel = document.createElement("p");
            counterLabel.className = "form-label";
            counterLabel.style.cssText = "margin-top:16px; border-top:1px solid var(--border-faint); padding-top:12px;";
            counterLabel.textContent = "Counter-Evidence Tracking";
            counterDiv.appendChild(counterLabel);

            for (var ci = 0; ci < counters.length; ci++) {
                counterDiv.appendChild(this._buildCounterInput(counters[ci]));
            }
            card.appendChild(counterDiv);
        }

        // Actions
        var actions = document.createElement("div");
        actions.className = "wizard-actions";

        var cancelBtn = document.createElement("button");
        cancelBtn.className = "btn btn-outline";
        cancelBtn.textContent = "Cancel";
        cancelBtn.onclick = function() { Symptoms.closeEpisodeModal(); };

        var saveAnotherBtn = document.createElement("button");
        saveAnotherBtn.className = "btn btn-secondary";
        saveAnotherBtn.textContent = "Save & Log Another";
        saveAnotherBtn.title = "Save this episode and immediately log another (great for catching up on past days)";
        saveAnotherBtn.onclick = function() { Symptoms._saveEpisode(true); };

        var saveBtn = document.createElement("button");
        saveBtn.className = "btn btn-primary";
        saveBtn.textContent = "Save Episode";
        saveBtn.onclick = function() { Symptoms._saveEpisode(false); };

        actions.appendChild(cancelBtn);
        actions.appendChild(saveAnotherBtn);
        actions.appendChild(saveBtn);
        card.appendChild(actions);

        container.appendChild(card);
    },

    _formGroup: function(labelText, inputType, id, value, placeholder) {
        var group = document.createElement("div");
        group.className = "form-group";
        var lbl = document.createElement("label");
        lbl.className = "form-label";
        lbl.textContent = labelText;
        group.appendChild(lbl);
        var input = document.createElement("input");
        input.type = inputType;
        input.id = id;
        input.className = "form-input";
        if (value) input.value = value;
        if (placeholder) input.placeholder = placeholder;
        group.appendChild(input);
        return group;
    },

    _buildCounterInput: function(counter) {
        var div = document.createElement("div");
        div.className = "episode-counter-prompt";

        var lbl = document.createElement("label");
        lbl.className = "form-label";
        lbl.textContent = (counter.measure_label || counter.doctor_claim);

        var skip = document.createElement("span");
        skip.className = "counter-skip-link";
        skip.textContent = " (skip)";
        lbl.appendChild(skip);
        div.appendChild(lbl);

        if (counter.measure_type === "scale") {
            var range = document.createElement("input");
            range.type = "range";
            range.min = "1";
            range.max = "5";
            range.value = "3";
            range.className = "counter-scale-input";
            range.dataset.cid = counter.counter_id;

            var valSpan = document.createElement("span");
            valSpan.className = "counter-scale-value";
            valSpan.textContent = "3";

            range.oninput = function() { valSpan.textContent = this.value; };

            div.appendChild(range);
            div.appendChild(valSpan);

        } else if (counter.measure_type === "yes_no") {
            var sel = document.createElement("select");
            sel.className = "form-input counter-yesno-input";
            sel.dataset.cid = counter.counter_id;
            var opts = [["", "\u2014 Skip \u2014"], ["yes", "Yes"], ["no", "No"]];
            for (var i = 0; i < opts.length; i++) {
                var o = document.createElement("option");
                o.value = opts[i][0];
                o.textContent = opts[i][1];
                sel.appendChild(o);
            }
            div.appendChild(sel);

        } else {
            var txt = document.createElement("input");
            txt.type = "text";
            txt.className = "form-input counter-text-input";
            txt.dataset.cid = counter.counter_id;
            txt.placeholder = "Notes...";
            div.appendChild(txt);
        }

        return div;
    },

    _saveEpisode: async function(keepOpen) {
        var symptom = this._currentEpisodeSymptom;
        if (!symptom) return;

        var currentDate = ($("ep-date") || {}).value || null;

        var body = {
            episode_date: currentDate,
            time_of_day: ($("ep-time") || {}).value || null,
            severity: ($("ep-severity") || {}).value || "mid",
            description: ($("ep-description") || {}).value || null,
            duration: ($("ep-duration") || {}).value || null,
            triggers: ($("ep-triggers") || {}).value || null,
            counter_values: {},
        };

        // Collect counter values
        var scales = document.querySelectorAll(".counter-scale-input");
        for (var i = 0; i < scales.length; i++) {
            body.counter_values[scales[i].dataset.cid] = parseInt(scales[i].value);
        }

        var yesnos = document.querySelectorAll(".counter-yesno-input");
        for (var j = 0; j < yesnos.length; j++) {
            var val = yesnos[j].value;
            if (val === "yes") body.counter_values[yesnos[j].dataset.cid] = true;
            else if (val === "no") body.counter_values[yesnos[j].dataset.cid] = false;
        }

        var texts = document.querySelectorAll(".counter-text-input");
        for (var k = 0; k < texts.length; k++) {
            var txt = texts[k].value.trim();
            if (txt) body.counter_values[texts[k].dataset.cid] = txt;
        }

        try {
            await api("/api/symptoms/" + symptom.symptom_id + "/episodes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });

            if (keepOpen) {
                // Catch-up mode: rebuild form with date bumped back 1 day
                var nextDate = this._bumpDateBack(currentDate);
                var content = $("episode-modal");
                if (content) {
                    content.innerHTML = "";
                    this._buildEpisodeForm(content, symptom, nextDate);
                }
                // Refresh data in background so card updates
                this.load();
            } else {
                this.closeEpisodeModal();
                this.load();
            }
        } catch (e) {
            alert("Failed to save episode: " + e.message);
        }
    },

    _bumpDateBack: function(dateStr) {
        if (!dateStr) return new Date().toISOString().split("T")[0];
        var d = new Date(dateStr + "T12:00:00"); // noon to avoid timezone edge cases
        d.setDate(d.getDate() - 1);
        return d.toISOString().split("T")[0];
    },

    closeEpisodeModal: function() {
        var modal = $("episode-modal-overlay");
        if (modal) modal.style.display = "none";
    },

    // ── Add Counter (2-card mini-wizard) ─────────────────

    openAddCounter: function(symptomId) {
        this._counterWizardState = { symptomId: symptomId, step: 1, claim: "" };
        this._showCounterWizardStep(1);
        var overlay = $("counter-wizard-overlay");
        if (overlay) overlay.style.display = "flex";
    },

    _counterWizardState: { symptomId: null, step: 1, claim: "" },

    _showCounterWizardStep: function(step) {
        this._counterWizardState.step = step;
        var content = $("counter-wizard-modal");
        if (!content) return;

        content.innerHTML = "";

        if (step === 1) {
            this._buildCounterWizardCard1(content);
        } else if (step === 2) {
            this._buildCounterWizardCard2(content);
        }
    },

    _buildCounterWizardCard1: function(container) {
        var card = document.createElement("div");
        card.className = "wizard-card";

        var h3 = document.createElement("h3");
        h3.className = "wizard-title";
        h3.textContent = "What does your doctor say causes this?";
        card.appendChild(h3);

        var sub = document.createElement("p");
        sub.className = "wizard-subtext";
        sub.textContent = "You know your body. Let\u2019s track whether they\u2019re right.";
        card.appendChild(sub);

        var input = document.createElement("input");
        input.type = "text";
        input.id = "counter-claim-input";
        input.className = "form-input";
        input.placeholder = "e.g. stress, anxiety, posture";
        card.appendChild(input);

        var actions = document.createElement("div");
        actions.className = "wizard-actions";

        var cancelBtn = document.createElement("button");
        cancelBtn.className = "btn btn-outline";
        cancelBtn.textContent = "Cancel";
        cancelBtn.onclick = function() { Symptoms.closeCounterWizard(); };

        var nextBtn = document.createElement("button");
        nextBtn.className = "btn btn-primary";
        nextBtn.textContent = "Next \u2192";
        nextBtn.onclick = function() { Symptoms._counterWizardNext(); };

        actions.appendChild(cancelBtn);
        actions.appendChild(nextBtn);
        card.appendChild(actions);

        container.appendChild(card);
        setTimeout(function() { input.focus(); }, 100);
    },

    _buildCounterWizardCard2: function(container) {
        var card = document.createElement("div");
        card.className = "wizard-card";

        var h3 = document.createElement("h3");
        h3.className = "wizard-title";
        h3.textContent = "How should we measure \u2018" + this._counterWizardState.claim + "\u2019 each time?";
        card.appendChild(h3);

        var sub = document.createElement("p");
        sub.className = "wizard-subtext";
        sub.textContent = "Each time you log an episode, we\u2019ll ask about this.";
        card.appendChild(sub);

        var options = document.createElement("div");
        options.className = "wizard-measure-options";

        var types = [
            { value: "scale", label: "Scale 1\u20135 (low to high)" },
            { value: "yes_no", label: "Yes or No" },
            { value: "free_text", label: "Free text" }
        ];

        for (var i = 0; i < types.length; i++) {
            var opt = document.createElement("label");
            opt.className = "wizard-measure-option";
            var radio = document.createElement("input");
            radio.type = "radio";
            radio.name = "counter-measure-type";
            radio.value = types[i].value;
            if (i === 0) radio.checked = true;
            opt.appendChild(radio);
            opt.appendChild(document.createTextNode(" " + types[i].label));
            options.appendChild(opt);
        }
        card.appendChild(options);

        var actions = document.createElement("div");
        actions.className = "wizard-actions";

        var backBtn = document.createElement("button");
        backBtn.className = "btn btn-outline";
        backBtn.textContent = "\u2190 Back";
        backBtn.onclick = function() { Symptoms._showCounterWizardStep(1); };

        var addBtn = document.createElement("button");
        addBtn.className = "btn btn-primary";
        addBtn.textContent = "Add Counter";
        addBtn.onclick = function() { Symptoms._saveCounter(); };

        actions.appendChild(backBtn);
        actions.appendChild(addBtn);
        card.appendChild(actions);

        container.appendChild(card);
    },

    _counterWizardNext: function() {
        var claimInput = $("counter-claim-input");
        var claim = claimInput ? claimInput.value.trim() : "";
        if (!claim) return;
        this._counterWizardState.claim = claim;
        this._showCounterWizardStep(2);
    },

    _saveCounter: async function() {
        var state = this._counterWizardState;
        var radios = document.querySelectorAll('input[name="counter-measure-type"]');
        var mtype = "scale";
        for (var i = 0; i < radios.length; i++) {
            if (radios[i].checked) { mtype = radios[i].value; break; }
        }

        try {
            await api("/api/symptoms/" + state.symptomId + "/counter", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    doctor_claim: state.claim,
                    measure_type: mtype,
                }),
            });
            this.closeCounterWizard();
            this.load();
        } catch (e) {
            alert("Failed to add counter: " + e.message);
        }
    },

    closeCounterWizard: function() {
        var overlay = $("counter-wizard-overlay");
        if (overlay) overlay.style.display = "none";
    },

    // ── Delete / Archive ─────────────────────────────────

    toggleArchive: async function(symptomId) {
        try {
            await api("/api/symptoms/" + symptomId + "/archive", { method: "PATCH" });
            this.load();
        } catch (e) {
            alert("Failed to update: " + e.message);
        }
    },

    deleteSymptom: async function(symptomId) {
        if (!confirm("Remove this symptom tracker and all its episodes?")) return;
        try {
            await api("/api/symptoms/" + symptomId, { method: "DELETE" });
            this.load();
        } catch (e) {
            alert("Failed to delete: " + e.message);
        }
    },

    deleteEpisode: async function(symptomId, episodeId) {
        if (!confirm("Remove this episode?")) return;
        try {
            await api("/api/symptoms/" + symptomId + "/episodes/" + episodeId, { method: "DELETE" });
            this.load();
        } catch (e) {
            alert("Failed to delete: " + e.message);
        }
    },

    archiveCounter: async function(symptomId, counterId) {
        try {
            await api("/api/symptoms/" + symptomId + "/counter/" + counterId, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({}),
            });
            this.load();
        } catch (e) {
            alert("Failed to update counter: " + e.message);
        }
    },

    // ── Sub-tab Switching ───────────────────────────────

    switchTab: function(tab) {
        var tabs = document.querySelectorAll(".symptom-subtab");
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].classList.toggle("active", tabs[i].dataset.subtab === tab);
        }
        var tracker = $("symptom-tab-tracker");
        var patterns = $("symptom-tab-patterns");
        var analytics = $("symptom-tab-analytics");
        if (tracker) tracker.style.display = tab === "tracker" ? "" : "none";
        if (patterns) patterns.style.display = tab === "patterns" ? "" : "none";
        if (analytics) analytics.style.display = tab === "analytics" ? "" : "none";

        if (tab === "patterns") {
            this.loadPatterns();
        }
        if (tab === "analytics" && typeof SymptomAnalytics !== "undefined") {
            SymptomAnalytics.load("analytics-content");
        }
    },

    // ── Patterns Tab ────────────────────────────────────

    loadPatterns: async function() {
        var container = $("patterns-content");
        if (!container) return;

        while (container.firstChild) container.removeChild(container.firstChild);
        var loading = document.createElement("div");
        loading.style.cssText = "text-align:center; padding:40px; color:var(--text-muted);";
        loading.textContent = "Analyzing symptom patterns...";
        container.appendChild(loading);

        try {
            var data = await api("/api/symptom-patterns");
            while (container.firstChild) container.removeChild(container.firstChild);
            this._renderPatterns(container, data);
        } catch (e) {
            while (container.firstChild) container.removeChild(container.firstChild);
            var err = document.createElement("div");
            err.style.cssText = "text-align:center; padding:40px; color:var(--accent-crimson);";
            err.textContent = "Failed to load patterns: " + e.message;
            container.appendChild(err);
        }
    },

    _renderPatterns: function(container, data) {
        var perSymptom = data.per_symptom || [];
        var clusters = data.clusters || [];
        var summary = data.summary || {};

        // Per-symptom pattern cards
        for (var i = 0; i < perSymptom.length; i++) {
            container.appendChild(this._renderPatternCard(perSymptom[i]));
        }

        // Cluster detection
        if (clusters.length > 0) {
            var clusterCard = document.createElement("div");
            clusterCard.className = "pattern-card";
            var clTitle = document.createElement("div");
            clTitle.className = "pattern-card-title";
            clTitle.textContent = "\ud83d\udd17 Symptom Clusters";
            clusterCard.appendChild(clTitle);

            for (var ci = 0; ci < clusters.length; ci++) {
                var cl = clusters[ci];
                var row = document.createElement("div");
                row.className = "pattern-cluster-row";
                row.textContent = cl.description;
                clusterCard.appendChild(row);
            }
            container.appendChild(clusterCard);
        }

        // Empty state
        if (perSymptom.length === 0) {
            var empty = document.createElement("div");
            empty.style.cssText = "text-align:center; padding:40px; color:var(--text-muted);";
            empty.textContent = "No symptoms tracked yet. Start logging to see patterns.";
            container.appendChild(empty);
        }
    },

    _renderPatternCard: function(sym) {
        var card = document.createElement("div");
        card.className = "pattern-card";

        // Header row: name + badges
        var header = document.createElement("div");
        header.className = "pattern-card-header";

        var name = document.createElement("div");
        name.className = "pattern-card-title";
        name.textContent = sym.name;
        header.appendChild(name);

        var badges = document.createElement("div");
        badges.className = "pattern-badges";

        // Plain frequency badge (just the number, no trend judgment)
        var freq = sym.frequency || {};
        if (freq.per_week_4w > 0) {
            var fBadge = document.createElement("span");
            fBadge.className = "pattern-badge pattern-badge-stable";
            fBadge.textContent = freq.per_week_4w + "/wk";
            badges.appendChild(fBadge);
        }

        header.appendChild(badges);
        card.appendChild(header);

        // Stats row
        var stats = document.createElement("div");
        stats.className = "pattern-stats-row";

        // Total episodes
        var epStat = document.createElement("div");
        epStat.className = "pattern-stat";
        var epVal = document.createElement("div");
        epVal.className = "pattern-stat-value";
        epVal.textContent = sym.total_episodes;
        epStat.appendChild(epVal);
        var epLbl = document.createElement("div");
        epLbl.className = "pattern-stat-label";
        epLbl.textContent = "Episodes";
        epStat.appendChild(epLbl);
        stats.appendChild(epStat);

        // Frequency
        var freqStat = document.createElement("div");
        freqStat.className = "pattern-stat";
        var freqVal = document.createElement("div");
        freqVal.className = "pattern-stat-value";
        freqVal.textContent = freq.per_week_4w || "0";
        freqStat.appendChild(freqVal);
        var freqLbl = document.createElement("div");
        freqLbl.className = "pattern-stat-label";
        freqLbl.textContent = "Per week (4w)";
        freqStat.appendChild(freqLbl);
        stats.appendChild(freqStat);

        // Peak time
        var timePat = sym.time_patterns || {};
        if (timePat.peak) {
            var timeStat = document.createElement("div");
            timeStat.className = "pattern-stat";
            var timeVal = document.createElement("div");
            timeVal.className = "pattern-stat-value";
            timeVal.textContent = timePat.peak_pct + "%";
            timeStat.appendChild(timeVal);
            var timeLbl = document.createElement("div");
            timeLbl.className = "pattern-stat-label";
            timeLbl.textContent = timePat.peak.charAt(0).toUpperCase() + timePat.peak.slice(1);
            timeStat.appendChild(timeLbl);
            stats.appendChild(timeStat);
        }

        card.appendChild(stats);

        // Sparkline (12-week episodes)
        var sparkline = sym.weekly_sparkline || [];
        if (sparkline.length > 0 && sparkline.some(function(v) { return v > 0; })) {
            card.appendChild(this._renderSparkline(sparkline));
        }

        // Medication correlations
        var medCorrs = sym.medication_correlations || [];
        if (medCorrs.length > 0) {
            var medDiv = document.createElement("div");
            medDiv.className = "pattern-med-correlations";
            for (var mi = 0; mi < medCorrs.length; mi++) {
                var mb = document.createElement("div");
                mb.className = "pattern-med-badge";
                mb.textContent = "\ud83d\udc8a " + medCorrs[mi].description;
                medDiv.appendChild(mb);
            }
            card.appendChild(medDiv);
        }

        // Gentle insight nudge (only when there's something worth mentioning)
        var insight = this._generateInsight(sym);
        if (insight) {
            var nudge = document.createElement("div");
            nudge.className = "pattern-insight";
            var nudgeText = document.createElement("p");
            nudgeText.textContent = insight;
            nudge.appendChild(nudgeText);
            var nudgeNote = document.createElement("p");
            nudgeNote.className = "pattern-insight-note";
            nudgeNote.textContent = "Please keep logging these symptoms as time goes on \u2014 the more data, the clearer the picture.";
            nudge.appendChild(nudgeNote);
            card.appendChild(nudge);
        }

        return card;
    },

    _generateInsight: function(sym) {
        var name = sym.name || "this symptom";
        var sevDir = (sym.severity_trend || {}).direction || "";
        var freqDir = (sym.frequency || {}).direction || "";
        var perWeek = (sym.frequency || {}).per_week_4w || 0;
        var timePeak = (sym.time_patterns || {}).peak || "";
        var timePct = (sym.time_patterns || {}).peak_pct || 0;
        var medCorrs = sym.medication_correlations || [];

        // Friendly, conversational nudges — like a friend who's been paying attention
        // Priority: severity rising + frequent > severity rising > high frequency >
        //           increasing frequency > med correlation > time pattern

        var ln = name.toLowerCase();

        if (sevDir === "worsening" && perWeek >= 2) {
            return "Hey friend \u2014 your " + ln + " have been getting more intense lately, and they\u2019re happening pretty often. I\u2019m going to log this so you can bring it up with your doctor next time you visit them.";
        }
        if (sevDir === "worsening") {
            return "Hey friend \u2014 your " + ln + " seem to be getting a bit more intense over time. I\u2019m going to log this so you can bring it up with your doctor next time you visit them.";
        }
        if (perWeek >= 5) {
            return "Hey friend \u2014 you\u2019ve been dealing with " + ln + " a lot lately, about " + perWeek + " times a week. I\u2019m going to log this so you can bring it up with your doctor next time you visit them.";
        }
        if (freqDir === "increasing") {
            return "Hey friend \u2014 your " + ln + " have been happening more often recently. I\u2019m going to log this so you can bring it up with your doctor next time you visit them.";
        }
        if (medCorrs.length > 0) {
            return "Hey friend \u2014 we noticed a possible connection between your " + ln + " and a medication you started. I\u2019m going to log this so you can bring it up with your doctor next time you visit them.";
        }
        if (timePeak && timePct >= 70 && sym.total_episodes >= 3) {
            return "Hey friend \u2014 your " + ln + " tend to happen in the " + timePeak + " (" + timePct + "% of the time). I\u2019m going to log this so you can bring it up with your doctor next time you visit them.";
        }

        // No insight needed — things look steady
        return null;
    },

    _renderSparkline: function(data) {
        var div = document.createElement("div");
        div.className = "pattern-sparkline";

        var maxVal = Math.max.apply(null, data) || 1;
        var barWidth = Math.floor(100 / data.length);

        for (var i = 0; i < data.length; i++) {
            var bar = document.createElement("div");
            bar.className = "sparkline-bar";
            var height = Math.max(2, Math.round((data[i] / maxVal) * 28));
            bar.style.height = height + "px";
            bar.style.width = barWidth + "%";
            if (data[i] > 0) {
                bar.title = data[i] + " episode" + (data[i] > 1 ? "s" : "");
            }
            div.appendChild(bar);
        }

        var label = document.createElement("div");
        label.className = "sparkline-label";
        label.textContent = "12-week activity";
        div.appendChild(label);

        return div;
    },
};
