/* ══════════════════════════════════════════════════════════
   Cross-Disciplinary Node Graph — D3 Force-Directed

   Reframed to follow the Snowball interaction model:
     - Header with quick summary + orientation
     - Split graph/detail layout
     - Dedicated legend + partner note
     - Clearer detail hierarchy when a node is selected
   ══════════════════════════════════════════════════════════ */

var CrossDiscGraph = {

    _svg: null,
    _simulation: null,
    _activePatternId: null,

    // Specialty color palette — 28 specialties, distinct hues
    _specColors: {
        "Cardiology":            "#C87850",
        "Neurology":             "#9B8BE0",
        "Pulmonology":           "#8BA8E8",
        "Nephrology":            "#5ED4C8",
        "Gastroenterology":      "#7AB0F0",
        "Hepatology":            "#6BD4A8",
        "Endocrinology":         "#6B9BF7",
        "Hematology":            "#C8A848",
        "Rheumatology":          "#68C8D8",
        "Dermatology":           "#E088B0",
        "Ophthalmology":         "#7EC4E8",
        "Allergy/Immunology":    "#D4A06B",
        "Nutrition":             "#8BD470",
        "Psychiatry":            "#C888D8",
        "Sleep Medicine":        "#7070C8",
        "Oncology":              "#D85858",
        "Genetics":              "#A0D0F0",
        "Vascular Medicine":     "#D87080",
        "Infectious Disease":    "#88C888",
        "Toxicology":            "#B8B868",
        "ENT":                   "#B09870",
        "Pain Medicine":         "#D8A088",
        "Geriatrics":            "#A8A8C8",
        "Clinical Pharmacology": "#90B8A0",
        "Orthopedics":           "#C0A080",
        "Obstetrics/Gynecology": "#D898C0",
        "Dentistry":             "#80C0B0",
        "Urology":               "#A0B8D8",
    },

    _sevRadius: { high: 28, moderate: 22, low: 16 },
    _sevColor: { high: "#C84040", moderate: "#C8A848", low: "#58B888" },

    render: function(containerId, connections) {
        var container = document.getElementById(containerId);
        if (!container) return;

        while (container.firstChild) container.removeChild(container.firstChild);
        this._activePatternId = null;

        if (!connections || connections.length === 0) {
            container.appendChild(this._buildEmptyState(
                "No cross-disciplinary connections found.",
                "Analyze your records to discover patterns that span specialties and deserve a closer look."
            ));
            return;
        }

        var specialties = this._getUniqueSpecialties(connections);
        var shell = document.createElement("div");
        shell.className = "crossdisc-shell";

        var header = document.createElement("div");
        header.className = "crossdisc-header";

        var headerCopy = document.createElement("div");
        var title = document.createElement("h3");
        title.textContent = "Connection Map";
        headerCopy.appendChild(title);

        var subtitle = document.createElement("div");
        subtitle.className = "crossdisc-subtitle";
        subtitle.textContent = "Patterns that cut across specialties and adjacent health domains. Click a pattern node to see the evidence, why it matters, and a question to save for your next visit.";
        headerCopy.appendChild(subtitle);
        header.appendChild(headerCopy);

        var summary = document.createElement("div");
        summary.className = "crossdisc-summary";
        summary.appendChild(this._summaryChip(connections.length + " pattern" + (connections.length === 1 ? "" : "s")));
        summary.appendChild(this._summaryChip(specialties.length + " specialties"));

        var questionsReady = connections.filter(function(c) { return !!c.question_for_doctor; }).length;
        if (questionsReady > 0) {
            summary.appendChild(this._summaryChip(questionsReady + " visit question" + (questionsReady === 1 ? "" : "s")));
        }

        var verifiedCount = connections.filter(function(c) { return !!c.pubmed_verified; }).length;
        if (verifiedCount > 0) {
            summary.appendChild(this._summaryChip(verifiedCount + " PubMed-verified"));
        }
        header.appendChild(summary);
        shell.appendChild(header);

        var body = document.createElement("div");
        body.className = "crossdisc-body";

        var graphPane = document.createElement("div");
        graphPane.className = "crossdisc-graph-pane";

        var graphHint = document.createElement("div");
        graphHint.className = "crossdisc-graph-hint";
        graphHint.textContent = "Drag nodes to rearrange the map. Scroll to zoom. Click a pattern to load the detail rail.";
        graphPane.appendChild(graphHint);

        var graphDiv = document.createElement("div");
        graphDiv.id = "crossdisc-graph-svg";
        graphDiv.className = "crossdisc-graph";
        graphPane.appendChild(graphDiv);
        body.appendChild(graphPane);

        var detailDiv = document.createElement("div");
        detailDiv.id = "crossdisc-detail";
        detailDiv.className = "crossdisc-detail";
        this._renderDetailEmpty(detailDiv);
        body.appendChild(detailDiv);

        shell.appendChild(body);
        shell.appendChild(this._buildLegend(connections));

        var note = document.createElement("div");
        note.className = "crossdisc-partner-note";

        var noteHeadline = document.createElement("div");
        noteHeadline.className = "crossdisc-partner-headline";
        noteHeadline.textContent = "Why this view exists";
        note.appendChild(noteHeadline);

        var noteBody = document.createElement("div");
        noteBody.className = "crossdisc-partner-body";
        noteBody.textContent = "We look across labs, medications, diagnoses, imaging, and symptoms to surface patterns that siloed specialists can miss. These are discussion prompts for your next visit, not diagnoses.";
        note.appendChild(noteBody);
        shell.appendChild(note);

        container.appendChild(shell);

        var graphData = this._buildGraphData(connections);
        var self = this;
        requestAnimationFrame(function() {
            self._renderD3(graphDiv, graphData, connections);
        });
    },

    _buildEmptyState: function(titleText, bodyText) {
        var wrapper = document.createElement("div");
        wrapper.className = "crossdisc-empty";

        var title = document.createElement("div");
        title.className = "crossdisc-empty-title";
        title.textContent = titleText;
        wrapper.appendChild(title);

        var body = document.createElement("div");
        body.className = "crossdisc-empty-copy";
        body.textContent = bodyText;
        wrapper.appendChild(body);

        return wrapper;
    },

    _summaryChip: function(text) {
        var chip = document.createElement("div");
        chip.className = "crossdisc-summary-chip";
        chip.textContent = text;
        return chip;
    },

    _getUniqueSpecialties: function(connections) {
        var seen = {};
        for (var i = 0; i < connections.length; i++) {
            var specs = connections[i].specialties || [];
            for (var j = 0; j < specs.length; j++) {
                seen[specs[j]] = true;
            }
        }
        return Object.keys(seen).sort();
    },

    _buildGraphData: function(connections) {
        var nodes = [];
        var edges = [];
        var specMap = {};

        for (var i = 0; i < connections.length; i++) {
            var c = connections[i];
            nodes.push({
                id: "pattern-" + i,
                type: "pattern",
                label: c.title || "Pattern " + (i + 1),
                severity: c.severity || "moderate",
                dataIndex: i,
            });
        }

        for (var pi = 0; pi < connections.length; pi++) {
            var specs = connections[pi].specialties || [];
            for (var si = 0; si < specs.length; si++) {
                var specName = specs[si];
                if (!specMap[specName]) {
                    specMap[specName] = {
                        id: "spec-" + specName,
                        type: "specialty",
                        label: specName,
                        count: 0,
                    };
                    nodes.push(specMap[specName]);
                }
                specMap[specName].count += 1;
                edges.push({
                    source: "pattern-" + pi,
                    target: "spec-" + specName,
                });
            }
        }

        return { nodes: nodes, edges: edges };
    },

    _renderD3: function(container, data, connections) {
        var self = this;
        var width = container.clientWidth || 500;
        var height = container.clientHeight || 440;

        if (this._simulation) this._simulation.stop();

        var svg = d3.select(container)
            .append("svg")
            .attr("width", width)
            .attr("height", height)
            .attr("viewBox", [0, 0, width, height]);

        this._svg = svg;

        var defs = svg.append("defs");
        ["high", "moderate", "low"].forEach(function(sev) {
            var grad = defs.append("linearGradient")
                .attr("id", "crossdisc-sev-" + sev)
                .attr("x1", "0%").attr("y1", "0%")
                .attr("x2", "0%").attr("y2", "100%");
            grad.append("stop")
                .attr("offset", "0%")
                .attr("stop-color", self._sevColor[sev] || "#888")
                .attr("stop-opacity", 0.92);
            grad.append("stop")
                .attr("offset", "100%")
                .attr("stop-color", self._sevColor[sev] || "#888")
                .attr("stop-opacity", 0.55);
        });

        var g = svg.append("g");

        svg.call(d3.zoom()
            .scaleExtent([0.55, 3])
            .on("zoom", function(event) {
                g.attr("transform", event.transform);
            }));

        var simulation = d3.forceSimulation(data.nodes)
            .force("link", d3.forceLink(data.edges)
                .id(function(d) { return d.id; })
                .distance(92))
            .force("charge", d3.forceManyBody().strength(-240))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide().radius(function(d) {
                return d.type === "pattern" ? 40 : 24;
            }));

        this._simulation = simulation;

        var link = g.selectAll(".crossdisc-link")
            .data(data.edges)
            .join("line")
            .attr("class", "crossdisc-link")
            .attr("stroke", "var(--border-faint)")
            .attr("stroke-width", 1.5)
            .attr("stroke-dasharray", "4,3")
            .attr("stroke-opacity", 0.55);

        var node = g.selectAll(".crossdisc-node")
            .data(data.nodes)
            .join("g")
            .attr("class", function(d) {
                return "crossdisc-node crossdisc-node--" + d.type;
            })
            .style("cursor", function(d) { return d.type === "pattern" ? "pointer" : "default"; })
            .call(d3.drag()
                .on("start", function(event, d) {
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    d.fx = d.x;
                    d.fy = d.y;
                })
                .on("drag", function(event, d) {
                    d.fx = event.x;
                    d.fy = event.y;
                })
                .on("end", function(event, d) {
                    if (!event.active) simulation.alphaTarget(0);
                    d.fx = null;
                    d.fy = null;
                }));

        var patternNodes = node.filter(function(d) { return d.type === "pattern"; })
            .attr("tabindex", 0)
            .attr("role", "button")
            .attr("aria-label", function(d) { return "Open details for " + d.label; });

        patternNodes.append("circle")
            .attr("r", function(d) { return self._sevRadius[d.severity] || 22; })
            .attr("fill", function(d) { return "url(#crossdisc-sev-" + d.severity + ")"; })
            .attr("stroke", function(d) { return self._sevColor[d.severity] || "#888"; })
            .attr("stroke-width", 2.5);

        patternNodes.append("text")
            .attr("class", "crossdisc-pattern-label")
            .attr("text-anchor", "middle")
            .attr("dy", "0.35em")
            .attr("pointer-events", "none")
            .text(function(d) {
                return self._shortPatternLabel(d.label);
            });

        var specialtyNodes = node.filter(function(d) { return d.type === "specialty"; });

        specialtyNodes.append("circle")
            .attr("r", function(d) { return 10 + (d.count || 1) * 3; })
            .attr("fill", function(d) { return self._specColors[d.label] || "#7AB0F0"; })
            .attr("fill-opacity", 0.7)
            .attr("stroke", function(d) { return self._specColors[d.label] || "#7AB0F0"; })
            .attr("stroke-width", 1.5);

        specialtyNodes.append("text")
            .attr("class", "crossdisc-specialty-label")
            .attr("text-anchor", "middle")
            .attr("dy", function(d) { return (12 + (d.count || 1) * 3) + 13; })
            .attr("pointer-events", "none")
            .text(function(d) { return d.label; });

        function selectPattern(d) {
            self._activePatternId = d.id;
            self._showDetail(connections[d.dataIndex]);
            updateSelection();
        }

        patternNodes
            .on("click", function(event, d) {
                event.stopPropagation();
                selectPattern(d);
            })
            .on("keydown", function(event, d) {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    selectPattern(d);
                }
            });

        function updateSelection() {
            patternNodes.select("circle")
                .attr("stroke", function(d) {
                    return d.id === self._activePatternId
                        ? "rgba(255,255,255,0.96)"
                        : (self._sevColor[d.severity] || "#888");
                })
                .attr("stroke-width", function(d) {
                    return d.id === self._activePatternId ? 4 : 2.5;
                });

            specialtyNodes.select("circle")
                .attr("stroke-width", 1.5)
                .attr("fill-opacity", function(d) {
                    return self._activePatternId ? 0.58 : 0.7;
                });
        }

        updateSelection();

        simulation.on("tick", function() {
            link
                .attr("x1", function(d) { return d.source.x; })
                .attr("y1", function(d) { return d.source.y; })
                .attr("x2", function(d) { return d.target.x; })
                .attr("y2", function(d) { return d.target.y; });

            node.attr("transform", function(d) {
                return "translate(" + d.x + "," + d.y + ")";
            });
        });
    },

    _shortPatternLabel: function(label) {
        if (!label) return "";
        var words = label.split(/[\s\-]+/).filter(Boolean);
        if (words.length === 1) return label.length > 14 ? label.substring(0, 13) + "…" : label;
        if (words.length === 2) return (words[0] + " " + words[1]).substring(0, 16);
        return words[0].substring(0, 7) + "…";
    },

    _renderDetailEmpty: function(panel) {
        var target = panel || document.getElementById("crossdisc-detail");
        if (!target) return;
        while (target.firstChild) target.removeChild(target.firstChild);

        var empty = document.createElement("div");
        empty.className = "crossdisc-detail-empty";

        var title = document.createElement("div");
        title.className = "crossdisc-detail-empty-title";
        title.textContent = "Select a connection";
        empty.appendChild(title);

        var copy = document.createElement("div");
        copy.className = "crossdisc-detail-empty-copy";
        copy.textContent = "Choose a pattern node to review the supporting evidence, the specialties involved, and a question you can save for your next visit.";
        empty.appendChild(copy);

        target.appendChild(empty);
    },

    _showDetail: function(connection) {
        var panel = document.getElementById("crossdisc-detail");
        if (!panel) return;
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        var card = document.createElement("div");
        card.className = "crossdisc-detail-card";

        var title = document.createElement("div");
        title.className = "crossdisc-detail-title";
        title.textContent = connection.title || connection.disease || "Cross-disciplinary pattern";
        card.appendChild(title);

        var badges = document.createElement("div");
        badges.className = "crossdisc-detail-badges";

        var sevMap = { high: "badge-critical", moderate: "badge-moderate", low: "badge-low" };
        var severityBadge = document.createElement("span");
        severityBadge.className = "badge " + (sevMap[connection.severity] || "badge-info");
        severityBadge.textContent = (connection.severity || "moderate").toUpperCase();
        badges.appendChild(severityBadge);

        var specialtyChip = document.createElement("span");
        specialtyChip.className = "crossdisc-meta-chip";
        specialtyChip.textContent = (connection.specialties || []).length + " specialties";
        badges.appendChild(specialtyChip);

        if (connection.type === "ai_discovered_correlation") {
            var aiChip = document.createElement("span");
            aiChip.className = "crossdisc-meta-chip " + (connection.pubmed_verified ? "is-verified" : "is-ai");
            aiChip.textContent = connection.pubmed_verified ? "PubMed verified" : "AI suggested";
            badges.appendChild(aiChip);
        } else if (connection.total_hits && connection.total_possible) {
            var indicatorChip = document.createElement("span");
            indicatorChip.className = "crossdisc-meta-chip";
            indicatorChip.textContent = connection.total_hits + "/" + connection.total_possible + " indicators";
            badges.appendChild(indicatorChip);
        }

        card.appendChild(badges);

        var dataPoints = connection.patient_data_points || connection.matched_symptoms || [];
        if (dataPoints.length > 0) {
            card.appendChild(this._sectionLabel("What we found in your records"));
            card.appendChild(this._buildList(dataPoints, "crossdisc-list"));
        }

        var matchedLabs = connection.matched_labs || [];
        if (matchedLabs.length > 0) {
            card.appendChild(this._sectionLabel("Matched lab markers"));
            card.appendChild(this._buildList(matchedLabs, "crossdisc-list crossdisc-list--labs"));
        }

        var desc = connection.description || connection.pattern || "";
        if (desc) {
            card.appendChild(this._sectionLabel("Why this might matter"));
            var descDiv = document.createElement("div");
            descDiv.className = "crossdisc-body-copy";
            descDiv.textContent = desc;
            card.appendChild(descDiv);
        }

        var specs = connection.specialties || [];
        if (specs.length > 0) {
            card.appendChild(this._sectionLabel("The connection"));

            var connNote = document.createElement("div");
            connNote.className = "crossdisc-note";
            connNote.textContent = specs.length > 1
                ? "These findings span specialties that do not always communicate directly:"
                : "This pattern is anchored in one specialty but has broader implications:";
            card.appendChild(connNote);

            card.appendChild(this._buildSpecialtyRow(specs));
        }

        card.appendChild(this._sectionLabel("How we identified this"));
        card.appendChild(this._buildSourceBlock(connection));

        var question = connection.question_for_doctor;
        if (question) {
            var visitBox = document.createElement("div");
            visitBox.className = "crossdisc-visit-box";

            var visitLabel = document.createElement("div");
            visitLabel.className = "crossdisc-visit-label";
            visitLabel.textContent = "Noted for your next visit";
            visitBox.appendChild(visitLabel);

            var qText = document.createElement("div");
            qText.className = "crossdisc-visit-question";
            qText.textContent = question;
            visitBox.appendChild(qText);

            var addBtn = document.createElement("button");
            addBtn.className = "btn btn-sm crossdisc-visit-btn";
            addBtn.type = "button";
            addBtn.textContent = "Add to Visit Prep";
            addBtn.onclick = this._addToVisitPrep.bind(this, connection, addBtn);
            visitBox.appendChild(addBtn);

            card.appendChild(visitBox);
        }

        var disclaimer = document.createElement("div");
        disclaimer.className = "crossdisc-disclaimer";
        disclaimer.textContent = "This is a pattern worth exploring, not a diagnosis. Your doctor can decide whether it changes testing, monitoring, or treatment.";
        card.appendChild(disclaimer);

        panel.appendChild(card);
    },

    _sectionLabel: function(text) {
        var el = document.createElement("div");
        el.className = "crossdisc-section-title";
        el.textContent = text;
        return el;
    },

    _buildList: function(items, className) {
        var list = document.createElement("ul");
        list.className = className || "crossdisc-list";
        for (var i = 0; i < items.length; i++) {
            var li = document.createElement("li");
            li.textContent = items[i];
            list.appendChild(li);
        }
        return list;
    },

    _buildSpecialtyRow: function(specs) {
        var row = document.createElement("div");
        row.className = "crossdisc-chip-row";

        for (var i = 0; i < specs.length; i++) {
            var chip = document.createElement("span");
            chip.className = "crossdisc-chip";
            var color = this._specColors[specs[i]] || "#7AB0F0";
            chip.style.color = color;
            chip.style.borderColor = color;
            chip.textContent = specs[i];
            row.appendChild(chip);
        }

        return row;
    },

    _buildSourceBlock: function(connection) {
        var box = document.createElement("div");
        box.className = "crossdisc-source-box";

        var hits = connection.total_hits;
        var possible = connection.total_possible;
        var sourceType = connection.type || "";
        var evidenceSource = connection.evidence_source || "";
        var diagnosticSource = connection.diagnostic_source || "";

        if (sourceType === "ai_discovered_correlation") {
            var status = document.createElement("div");
            status.className = "crossdisc-source-status " + (connection.pubmed_verified ? "is-verified" : "is-unverified");
            status.textContent = connection.pubmed_verified ? "PubMed verified" : "AI suggestion only";
            box.appendChild(status);

            var aiLead = document.createElement("div");
            aiLead.className = "crossdisc-source-copy";
            aiLead.textContent = "Gemini identified this pattern from your records and surfaced supporting rationale where available.";
            box.appendChild(aiLead);

            if (evidenceSource) {
                var cites = document.createElement("div");
                cites.className = "crossdisc-source-copy";
                cites.textContent = "Gemini cites: " + evidenceSource;
                box.appendChild(cites);
            }

            var pmCitations = connection.pubmed_citations || [];
            if (pmCitations.length > 0) {
                var pmLabel = document.createElement("div");
                pmLabel.className = "crossdisc-source-label";
                pmLabel.textContent = "Supporting literature";
                box.appendChild(pmLabel);

                var citeItems = [];
                for (var ci = 0; ci < pmCitations.length; ci++) {
                    var cite = pmCitations[ci];
                    var citeText = cite.title || "";
                    if (cite.journal) citeText += " — " + cite.journal;
                    if (cite.year) citeText += " (" + cite.year + ")";
                    if (cite.pmid) citeText += " [PMID:" + cite.pmid + "]";
                    citeItems.push(citeText);
                }
                box.appendChild(this._buildList(citeItems, "crossdisc-list crossdisc-list--compact"));
            }
            return box;
        }

        if (hits && possible) {
            var matchLead = document.createElement("div");
            matchLead.className = "crossdisc-source-copy";
            matchLead.textContent = hits + " of " + possible + " known clinical indicators matched in your records.";
            box.appendChild(matchLead);

            if (diagnosticSource) {
                var criteria = document.createElement("div");
                criteria.className = "crossdisc-source-criteria";

                var criteriaLabel = document.createElement("div");
                criteriaLabel.className = "crossdisc-source-criteria-label";
                criteriaLabel.textContent = "Diagnostic criteria source";
                criteria.appendChild(criteriaLabel);

                var criteriaText = document.createElement("div");
                criteriaText.className = "crossdisc-source-criteria-copy";
                criteriaText.textContent = diagnosticSource;
                criteria.appendChild(criteriaText);

                box.appendChild(criteria);
            }
            return box;
        }

        if (evidenceSource || diagnosticSource) {
            if (evidenceSource) {
                var evidence = document.createElement("div");
                evidence.className = "crossdisc-source-copy";
                evidence.textContent = "Based on: " + evidenceSource;
                box.appendChild(evidence);
            }

            if (diagnosticSource) {
                var source = document.createElement("div");
                source.className = "crossdisc-source-copy";
                source.textContent = "Source: " + diagnosticSource;
                box.appendChild(source);
            }
            return box;
        }

        var fallback = document.createElement("div");
        fallback.className = "crossdisc-source-copy";
        fallback.textContent = "Identified by cross-referencing your medical records across specialties.";
        box.appendChild(fallback);
        return box;
    },

    _addToVisitPrep: function(connection, btn) {
        var question = connection.question_for_doctor || "";
        var titleText = connection.title || connection.disease || "";
        if (!question) return;

        btn.disabled = true;
        btn.textContent = "Adding...";

        fetch("/api/questions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: question,
                context: "Cross-disciplinary finding: " + titleText + ". " + (connection.description || connection.pattern || ""),
                priority: connection.severity === "high" ? "high" : "moderate",
                source: "cross_disciplinary",
            }),
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.error) {
                btn.textContent = "Failed";
                btn.style.background = "var(--accent-red, #C84040)";
                setTimeout(function() {
                    btn.textContent = "Add to Visit Prep";
                    btn.style.background = "";
                    btn.disabled = false;
                }, 2000);
                return;
            }

            btn.textContent = "Added to Visit Prep";
            btn.style.background = "var(--accent-green, #58B888)";
        })
        .catch(function() {
            btn.textContent = "Failed";
            btn.style.background = "var(--accent-red, #C84040)";
            setTimeout(function() {
                btn.textContent = "Add to Visit Prep";
                btn.style.background = "";
                btn.disabled = false;
            }, 2000);
        });
    },

    _buildLegend: function(connections) {
        var specialties = this._getUniqueSpecialties(connections);
        var legend = document.createElement("div");
        legend.className = "crossdisc-legend";

        var nodeGroup = document.createElement("div");
        nodeGroup.className = "crossdisc-legend-group";
        nodeGroup.appendChild(this._legendTitle("How to read the map"));

        var nodeItems = document.createElement("div");
        nodeItems.className = "crossdisc-legend-items";
        nodeItems.appendChild(this._legendItem("Pattern node", "var(--accent-bluetron)"));
        nodeItems.appendChild(this._legendItem("Specialty node", "var(--text-muted)"));
        nodeItems.appendChild(this._legendItem("High severity", this._sevColor.high));
        nodeItems.appendChild(this._legendItem("Moderate", this._sevColor.moderate));
        nodeItems.appendChild(this._legendItem("Low", this._sevColor.low));
        nodeGroup.appendChild(nodeItems);
        legend.appendChild(nodeGroup);

        var specialtyGroup = document.createElement("div");
        specialtyGroup.className = "crossdisc-legend-group crossdisc-legend-group--wide";
        specialtyGroup.appendChild(this._legendTitle("Specialties in this map"));

        var specItems = document.createElement("div");
        specItems.className = "crossdisc-legend-items";
        for (var i = 0; i < specialties.length; i++) {
            specItems.appendChild(this._legendItem(
                specialties[i],
                this._specColors[specialties[i]] || "#7AB0F0"
            ));
        }
        specialtyGroup.appendChild(specItems);
        legend.appendChild(specialtyGroup);

        return legend;
    },

    _legendTitle: function(text) {
        var title = document.createElement("div");
        title.className = "crossdisc-legend-title";
        title.textContent = text;
        return title;
    },

    _legendItem: function(labelText, color) {
        var item = document.createElement("div");
        item.className = "crossdisc-legend-item";

        var dot = document.createElement("span");
        dot.className = "crossdisc-dot";
        dot.style.background = color;
        item.appendChild(dot);

        var label = document.createElement("span");
        label.textContent = labelText;
        item.appendChild(label);

        return item;
    },
};
