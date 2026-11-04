/* Complete condition list and source-linked notes. Uses only existing local
   read endpoints; opening this view never starts analysis or a cloud call. */
var Conditions = {
    records: [],
    notes: [],
    notesByPage: {},
    mode: "conditions",
    requestId: 0,
    ready: false,
    loadedFor: null,
    loadedData: null,
    renderedDetails: [],

    node: function(tag, className, text) {
        var el = document.createElement(tag);
        if (className) el.className = className;
        if (text != null) el.textContent = text;
        return el;
    },

    sources: function(record) {
        var prov = record.provenance;
        return (Array.isArray(prov) ? prov : [prov || record]).filter(function(p) {
            return p && typeof p === "object";
        });
    },

    pageKey: function(p) {
        return p.source_file && p.source_page != null ? p.source_file + "\u0000" + p.source_page : null;
    },

    // Same file and page: one document can hold years of visits, so sharing
    // a file alone says nothing about which condition a note discusses.
    indexNotes: function() {
        Conditions.notesByPage = {};
        Conditions.notes.forEach(function(note) {
            var keys = {};
            Conditions.sources(note).forEach(function(p) {
                var key = Conditions.pageKey(p);
                if (key) keys[key] = true;
            });
            Object.keys(keys).forEach(function(key) {
                (Conditions.notesByPage[key] || (Conditions.notesByPage[key] = [])).push(note);
            });
        });
    },

    // Shared lists are returned as they are; callers only read them.
    notesFor: function(record) {
        var keys = Conditions.sources(record).map(Conditions.pageKey).filter(Boolean);
        if (keys.length === 1) return Conditions.notesByPage[keys[0]] || [];
        var seen = new Set(), linked = [];
        keys.forEach(function(key) {
            (Conditions.notesByPage[key] || []).forEach(function(note) {
                if (!seen.has(note)) { seen.add(note); linked.push(note); }
            });
        });
        return linked;
    },

    hasPage: function(record) {
        return Conditions.sources(record).some(function(p) { return Conditions.pageKey(p) !== null; });
    },

    // What the card shows, not raw stored strings: the note type as its title
    // reads, and no file names, which would match words in a document's name.
    searchText: function(record) {
        var text = [record.name, record.condition, record.status, record.date_diagnosed,
            record.date, record.note_date, record.diagnosing_provider, record.provider,
            record.facility, record.icd10_code, record.icd10, record.snomed_code,
            record.note_type ? String(record.note_type).replace(/_/g, " ") : "", record.summary];
        Conditions.sources(record).forEach(function(p) { text.push(p.raw_text); });
        return text.filter(Boolean).join(" ").toLowerCase();
    },

    queryWords: function() {
        return String($("conditions-search").value || "").toLowerCase().match(/[a-z0-9]+/g) || [];
    },

    // Every word of the search starts a word on the card, so "active" never
    // finds "Inactive". A single letter or a number must be a whole word:
    // "hepatitis c" is not Hepatitis B, and "stage 3" matches "3" or "3a", not "30".
    matches: function(record, words) {
        if (!words.length) return true;
        var have = Conditions.searchText(record).match(/[a-z0-9]+/g) || [];
        return words.every(function(word) {
            var number = /^\d+$/.test(word);
            return have.some(function(found) {
                if (found.indexOf(word) !== 0) return false;
                if (number) return found === word || /^[a-z]+$/.test(found.slice(word.length));
                return word.length > 1 || found === word;
            });
        });
    },

    loadKey: function(profileId, demo) {
        return String(profileId) + "\u0000" + String(demo);
    },

    recordKey: function(record) {
        var page = Conditions.sources(record).map(Conditions.pageKey).filter(Boolean)[0] || "";
        return [record.name || record.condition || "", record.date_diagnosed || record.date || "", page,
            record.status || ""].join("\u0000");
    },

    openKeys: function() {
        var open = {};
        Conditions.renderedDetails.forEach(function(item) { if (item.el.open) open[item.key] = true; });
        return open;
    },

    // The open notes that hold keyboard focus, so a reload can put it back.
    focusedKey: function() {
        var active = typeof document !== "undefined" ? document.activeElement : null;
        if (!active) return null;
        var hit = Conditions.renderedDetails.filter(function(item) {
            return item.el === active || item.summary === active || (item.el.contains && item.el.contains(active));
        })[0];
        return hit ? hit.key : null;
    },

    // From the dashboard: the full condition list, not the last tab or search.
    showAll: function() {
        Conditions.mode = "conditions";
        $("conditions-search").value = "";
        App.navigateTo("conditions");
    },

    reset: function() {
        Conditions.requestId++;
        Conditions.ready = false;
        Conditions.loadedFor = null;
        Conditions.loadedData = null;
        Conditions.renderedDetails = [];
        Conditions.records = [];
        Conditions.notes = [];
        Conditions.notesByPage = {};
        Conditions.mode = "conditions";
        $("conditions-search").value = "";
        $("conditions-list").replaceChildren();
        $("conditions-count").textContent = "";
        $("conditions-notes-status").textContent = "";
        $("conditions-list").setAttribute("aria-busy", "false");
        Conditions.renderPreviewMessage("Loading conditions…");
        Conditions.render();  // tab labels and pressed state
    },

    load: async function() {
        var requestId = ++Conditions.requestId;
        var profileId = App._activeProfileId;
        var demo = App._demoMode;
        // A reload of the same records (a run saves after every chunk) keeps
        // the list on screen, with any open notes, until the new answer arrives.
        var refresh = Conditions.ready && Conditions.loadedFor === Conditions.loadKey(profileId, demo);
        if (!refresh) {
            Conditions.ready = false;
            Conditions.records = [];
            Conditions.notes = [];
            $("conditions-list").replaceChildren();
            Conditions.render();  // tab labels without counts
            $("conditions-count").textContent = "Loading conditions and available notes…";
            $("conditions-notes-status").textContent = "";
        }
        $("conditions-list").setAttribute("aria-busy", "true");
        var data;
        try {
            data = await api("/api/conditions");
        } catch (e) { /* Show the retry state below, without retaining old data. */ }
        if (requestId !== Conditions.requestId || profileId !== App._activeProfileId || demo !== App._demoMode) return;
        $("conditions-list").setAttribute("aria-busy", "false");
        if (!data || !Array.isArray(data.conditions) || !Array.isArray(data.notes)) {
            Conditions.ready = false;
            Conditions.records = [];
            Conditions.notes = [];
            $("conditions-list").replaceChildren();
            Conditions.render();
            $("conditions-count").textContent = "Could not load conditions. Select Refresh list to try again.";
            return;
        }
        // The same answer again (a chunk saved nothing new here): leave the
        // page as it is, with its open notes and focus.
        var answer = JSON.stringify([data.conditions, data.notes]);
        if (refresh && answer === Conditions.loadedData) return;
        var open = refresh ? Conditions.openKeys() : {};
        var focus = refresh ? Conditions.focusedKey() : null;
        Conditions.loadedData = answer;
        Conditions.records = data.conditions.slice().sort(function(a, b) {
            return String(a.name || a.condition || "").localeCompare(String(b.name || b.condition || ""));
        });
        Conditions.notes = data.notes.slice().sort(function(a, b) {
            return String(b.note_date || b.date || "").localeCompare(String(a.note_date || a.date || ""));
        });
        Conditions.indexNotes();
        $("conditions-notes-status").textContent = "Includes all saved record notes, even those without dates. Saved summaries are labeled separately from source excerpts; full original notes may remain in your documents.";
        Conditions.loadedFor = Conditions.loadKey(profileId, demo);
        Conditions.ready = true;
        Conditions.render(open);
        if (focus) {
            var again = Conditions.renderedDetails.filter(function(item) { return item.key === focus; })[0];
            if (again && again.summary.focus) again.summary.focus();
        }
    },

    setMode: function(mode) {
        Conditions.mode = mode;
        Conditions.render();
    },

    clearSearch: function() {
        $("conditions-search").value = "";
        Conditions.render();
        $("conditions-search").focus();
    },

    // Open notes stay open only across a reload; a search shows a fresh list.
    render: function(open) {
        var isNotes = Conditions.mode === "notes";
        var keep = open || {};
        $("conditions-tab").setAttribute("aria-pressed", String(!isNotes));
        $("condition-notes-tab").setAttribute("aria-pressed", String(isNotes));
        // A count only for a list that loaded: "(0)" would say the record is empty.
        $("conditions-tab").textContent = Conditions.ready
            ? "Conditions (" + Conditions.records.length + ")" : "Conditions";
        $("condition-notes-tab").textContent = Conditions.ready
            ? "Available record notes (" + Conditions.notes.length + ")" : "Available record notes";
        $("conditions-search").placeholder = isNotes
            ? "Search notes by text, doctor, or date"
            : "Search conditions by name, doctor, or code";
        if (!Conditions.ready) return;
        var words = Conditions.queryWords();
        var matches = function(row) { return Conditions.matches(row, words); };
        var all = isNotes ? Conditions.notes : Conditions.records;
        var rows = all.filter(matches);
        var noun = isNotes ? "record notes" : "condition entries";
        var count = words.length
            ? "Showing " + rows.length + " of " + all.length + " " + noun
            : "Showing all " + all.length + " " + noun;
        var list = $("conditions-list");
        list.replaceChildren();
        Conditions.renderedDetails = [];
        if (!rows.length) {
            // A dead end says where the match is, in both directions.
            var other = words.length ? (isNotes ? Conditions.records : Conditions.notes).filter(matches).length : 0;
            var pointer = !other ? "" : isNotes
                ? other + (other === 1 ? " condition matches" : " conditions match")
                    + ". Select Conditions to see " + (other === 1 ? "it." : "them.")
                : other + (other === 1 ? " record note matches" : " record notes match")
                    + ". Select Available record notes to see " + (other === 1 ? "it." : "them.");
            list.appendChild(Conditions.node("p", "card conditions-muted", pointer
                ? (isNotes ? "No notes match. " : "No conditions match. ") + pointer
                : words.length
                ? "No matches. Clear your search to see the complete list."
                : (isNotes ? "No record notes have been extracted yet." : "No conditions have been extracted from your records yet.")));
            if (pointer) count += ". " + pointer;  // read out with the count
        }
        $("conditions-count").textContent = count;
        var seen = {};
        rows.forEach(function(row) {
            if (isNotes) {
                list.appendChild(Conditions.noteCard(row));
                return;
            }
            // Two entries alike in name, date, page and status still open on their own.
            var key = Conditions.recordKey(row);
            seen[key] = (seen[key] || 0) + 1;
            key += "\u0000" + seen[key];
            list.appendChild(Conditions.conditionCard(row, keep[key], key));
        });
    },

    addField: function(parent, label, value) {
        if (value == null || value === "") return;
        var line = Conditions.node("div", "condition-field");
        line.appendChild(Conditions.node("span", "conditions-muted", label + ": "));
        line.appendChild(Conditions.node("span", "", value));
        parent.appendChild(line);
    },

    addSources: function(parent, record) {
        var sources = Conditions.sources(record);
        var hasSource = false;
        sources.forEach(function(p) {
            if (!p.source_file && !p.raw_text) return;
            hasSource = true;
            var source = Conditions.node("div", "condition-source");
            Conditions.addField(source, "Source", p.source_file || "Not recorded");
            // Records are stored by the first page of the part of the file they came from.
            Conditions.addField(source, "Section starts on page", p.source_page);
            Conditions.addField(source, "Extracted", p.date_extracted);
            Conditions.addField(source, "Extraction confidence", p.confidence == null ? null : formatConfidence(p.confidence));
            if (p.raw_text) {
                source.appendChild(Conditions.node("div", "condition-note-label", "Saved source excerpt"));
                source.appendChild(Conditions.node("blockquote", "condition-note-text", p.raw_text));
            }
            parent.appendChild(source);
        });
        if (!hasSource) parent.appendChild(Conditions.node("p", "conditions-muted", "Source not recorded."));
    },

    noteCard: function(note) {
        var card = Conditions.node("article", "condition-note");
        var type = String(note.note_type || "Record note").replace(/_/g, " ");
        card.appendChild(Conditions.node("h3", "condition-note-title", type));
        Conditions.addField(card, "Date", note.note_date || note.date || "Not recorded");
        Conditions.addField(card, "Provider", note.provider || "Not recorded");
        Conditions.addField(card, "Facility", note.facility);
        if (note.summary) {
            card.appendChild(Conditions.node("div", "condition-note-label", "Saved summary · not a verbatim doctor's note"));
            card.appendChild(Conditions.node("p", "condition-note-text", note.summary));
        }
        Conditions.addSources(card, note);
        return card;
    },

    conditionCard: function(record, opened, key) {
        var card = Conditions.node("article", "card condition-card");
        card.appendChild(Conditions.node("h2", "condition-name", record.name || record.condition || "Unnamed condition"));
        var fields = Conditions.node("div", "condition-fields");
        Conditions.addField(fields, "Status", record.status || "Not recorded");
        Conditions.addField(fields, "Diagnosis date", record.date_diagnosed || record.date || "Not recorded");
        Conditions.addField(fields, "Provider", record.diagnosing_provider || record.provider || "Not recorded");
        Conditions.addField(fields, "ICD-10", record.icd10_code || record.icd10);
        Conditions.addField(fields, "SNOMED CT", record.snomed_code);
        card.appendChild(fields);
        Conditions.addSources(card, record);
        var notes = Conditions.notesFor(record);
        if (notes.length) {
            var details = Conditions.node("details", "condition-notes");
            var summary = Conditions.node("summary", "", "View notes from the same part of the record (" + notes.length + ")");
            details.appendChild(summary);
            details.appendChild(Conditions.node("p", "conditions-muted", "Matched by file and starting page. A file without page numbers counts as a single page. These notes may also discuss other conditions."));
            // Note cards are built on first open, so a long list stays light.
            var filled = false;
            var fill = function() {
                if (filled) return;
                filled = true;
                notes.forEach(function(note) { details.appendChild(Conditions.noteCard(note)); });
            };
            details.addEventListener("toggle", function() { if (details.open) fill(); });
            if (opened) {
                details.open = true;
                fill();
            }
            Conditions.renderedDetails.push({key: key || Conditions.recordKey(record), el: details, summary: summary});
            card.appendChild(details);
        } else {
            card.appendChild(Conditions.node("p", "conditions-muted condition-no-notes", Conditions.hasPage(record)
                ? "No saved notes come from the same part of the record as this condition. Browse Available record notes to see all notes."
                : "This condition's page in the record was not saved, so notes can't be matched to it. Browse Available record notes to see all notes."));
        }
        return card;
    },

    // ruledOut: entries the record rules out, which the card leaves out.
    renderPreview: function(records, ruledOut) {
        var preview = $("dash-dx-chart");
        if (!preview) return;
        preview.replaceChildren();
        ruledOut = ruledOut || 0;
        var ruledOutText = ruledOut + (ruledOut === 1 ? " ruled-out entry" : " ruled-out entries");
        // Current conditions first, each with the status the record gives it.
        var current = function(record) {
            return ["active", "chronic"].indexOf(String(record.status || "").trim().toLowerCase()) !== -1;
        };
        var ordered = records.filter(current).concat(records.filter(function(r) { return !current(r); }));
        var shown = ordered.slice(0, 5);
        var list = Conditions.node("ul", "conditions-preview");
        shown.forEach(function(record) {
            var name = record.name || record.condition || "Unnamed condition";
            var status = String(record.status || "").trim();
            list.appendChild(Conditions.node("li", "", status ? name + " · " + status : name));
        });
        preview.appendChild(records.length ? list : Conditions.node("p", "conditions-muted", ruledOut
            ? "No current conditions. " + ruledOutText + (ruledOut === 1 ? " is" : " are") + " listed on the Conditions page."
            : "No conditions recorded yet."));
        $("dash-dx-preview-count").textContent = records.length
            ? "Showing " + shown.length + " of " + records.length + " condition entries"
                + (ruledOut ? " · " + ruledOutText + " not shown" : "")
            : "";
    },

    // Loading or a failed request: never "No conditions recorded yet."
    renderPreviewMessage: function(text) {
        var preview = $("dash-dx-chart");
        if (!preview) return;
        preview.replaceChildren();
        preview.appendChild(Conditions.node("p", "conditions-muted", text));
        $("dash-dx-preview-count").textContent = "";
    }
};
