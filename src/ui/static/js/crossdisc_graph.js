/* ══════════════════════════════════════════════════════════
   Cross-Disciplinary Node Graph — D3 Force-Directed

   Visualizes cross-specialty medical connections as a network:
     - Coloured circles = systemic patterns (sized by severity)
     - Small circles = specialties (shared ones pull clusters together)
     - Edges = which specialties relate to which pattern
     - Click pattern node → detail panel
   ══════════════════════════════════════════════════════════ */

var CrossDiscGraph = {

    _svg: null,
    _simulation: null,

    // Specialty color palette — 28 specialties, distinct hues
    _specColors: {
        // Core organ systems
        "Cardiology":           "#C87850",
        "Neurology":            "#9B8BE0",
        "Pulmonology":          "#8BA8E8",
        "Nephrology":           "#5ED4C8",
        "Gastroenterology":     "#7AB0F0",
        "Hepatology":           "#6BD4A8",
        "Endocrinology":        "#6B9BF7",
        "Hematology":           "#C8A848",
        // Autoimmune / Connective tissue
        "Rheumatology":         "#68C8D8",
        "Dermatology":          "#E088B0",
        "Ophthalmology":        "#7EC4E8",
        "Allergy/Immunology":   "#D4A06B",
        // Specialties added in v3.1
        "Nutrition":            "#8BD470",
        "Psychiatry":           "#C888D8",
        "Sleep Medicine":       "#7070C8",
        "Oncology":             "#D85858",
        "Genetics":             "#A0D0F0",
        "Vascular Medicine":    "#D87080",
        "Infectious Disease":   "#88C888",
        "Toxicology":           "#B8B868",
        "ENT":                  "#B09870",
        "Pain Medicine":        "#D8A088",
        "Geriatrics":           "#A8A8C8",
        "Clinical Pharmacology":"#90B8A0",
        "Orthopedics":          "#C0A080",
        "Obstetrics/Gynecology":"#D898C0",
        "Dentistry":            "#80C0B0",
        "Urology":              "#A0B8D8",
    },

    _sevRadius: { high: 28, moderate: 22, low: 16 },
    _sevColor:  { high: "#C84040", moderate: "#C8A848", low: "#58B888" },

    /**
     * Render into a container element. Called by loadCrossDisciplinary.
     * @param {string} containerId - DOM element id
     * @param {Array} connections - array of cross-disciplinary connection objects
     */
    render: function(containerId, connections) {
        var container = document.getElementById(containerId);
        if (!container) return;

        // Clear previous
        while (container.firstChild) container.removeChild(container.firstChild);

        if (!connections || connections.length === 0) {
            var empty = document.createElement("div");
            empty.style.cssText = "color:var(--text-muted); text-align:center; padding:40px;";
            empty.textContent = "No cross-disciplinary connections found.";
            container.appendChild(empty);
            return;
        }

        // Build layout: graph on left, detail on right
        var wrapper = document.createElement("div");
        wrapper.style.cssText = "display:flex; gap:20px; min-height:420px;";

        var graphDiv = document.createElement("div");
        graphDiv.id = "crossdisc-graph-svg";
        graphDiv.style.cssText = "flex:2; min-width:300px; background:var(--bg-sunken); border-radius:8px; position:relative; overflow:hidden; height:420px;";
        wrapper.appendChild(graphDiv);

        var detailDiv = document.createElement("div");
        detailDiv.id = "crossdisc-detail";
        detailDiv.style.cssText = "flex:1; min-width:260px; max-width:340px; overflow-y:auto; max-height:420px;";
        var detailEmpty = document.createElement("div");
        detailEmpty.style.cssText = "color:var(--text-muted); text-align:center; padding:40px 20px; font-size:13px;";
        detailEmpty.textContent = "Click a pattern node to see what we found and why it matters";
        detailDiv.appendChild(detailEmpty);
        wrapper.appendChild(detailDiv);

        container.appendChild(wrapper);

        // Legend
        var legend = this._buildLegend(connections);
        container.appendChild(legend);

        // Partner note
        var note = document.createElement("div");
        note.style.cssText = "margin-top:16px; padding:12px 16px; background:var(--bg-raised); border-radius:8px; font-size:12px; color:var(--text-muted); line-height:1.5;";
        note.textContent = "We look across all your medical records \u2014 labs, medications, diagnoses, symptoms \u2014 and connect findings that individual specialists might miss. When something stands out, we note it for your next visit.";
        container.appendChild(note);

        // Build graph data — defer D3 one frame so flexbox layout settles
        var graphData = this._buildGraphData(connections);
        var self = this;
        requestAnimationFrame(function() {
            self._renderD3(graphDiv, graphData, connections);
        });
    },

    _buildGraphData: function(connections) {
        var nodes = [];
        var edges = [];
        var specMap = {}; // name → node index

        // Add pattern nodes
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

        // Add specialty nodes (deduplicated)
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
                specMap[specName].count++;

                // Edge from pattern to specialty
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
        var height = 400;

        // Stop previous simulation
        if (this._simulation) this._simulation.stop();

        var svg = d3.select(container)
            .append("svg")
            .attr("width", width)
            .attr("height", height)
            .attr("viewBox", [0, 0, width, height]);

        this._svg = svg;

        // Defs for gradients
        var defs = svg.append("defs");

        // Pattern node gradients (by severity)
        var sevKeys = ["high", "moderate", "low"];
        for (var si = 0; si < sevKeys.length; si++) {
            var sev = sevKeys[si];
            var grad = defs.append("linearGradient")
                .attr("id", "crossdisc-sev-" + sev)
                .attr("x1", "0%").attr("y1", "0%")
                .attr("x2", "0%").attr("y2", "100%");
            grad.append("stop").attr("offset", "0%").attr("stop-color", this._sevColor[sev]).attr("stop-opacity", 0.9);
            grad.append("stop").attr("offset", "100%").attr("stop-color", this._sevColor[sev]).attr("stop-opacity", 0.5);
        }

        var g = svg.append("g");

        // Zoom
        svg.call(d3.zoom()
            .scaleExtent([0.5, 3])
            .on("zoom", function(event) {
                g.attr("transform", event.transform);
            }));

        // Force simulation
        var simulation = d3.forceSimulation(data.nodes)
            .force("link", d3.forceLink(data.edges)
                .id(function(d) { return d.id; })
                .distance(80))
            .force("charge", d3.forceManyBody().strength(-200))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide().radius(function(d) {
                return d.type === "pattern" ? 35 : 22;
            }));

        this._simulation = simulation;

        // Edges
        var link = g.selectAll(".crossdisc-link")
            .data(data.edges)
            .join("line")
            .attr("class", "crossdisc-link")
            .attr("stroke", "var(--border-faint)")
            .attr("stroke-width", 1.5)
            .attr("stroke-dasharray", "4,3")
            .attr("stroke-opacity", 0.5);

        // Nodes
        var node = g.selectAll(".crossdisc-node")
            .data(data.nodes)
            .join("g")
            .attr("class", "crossdisc-node")
            .style("cursor", function(d) { return d.type === "pattern" ? "pointer" : "default"; })
            .call(d3.drag()
                .on("start", function(event, d) {
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    d.fx = d.x; d.fy = d.y;
                })
                .on("drag", function(event, d) {
                    d.fx = event.x; d.fy = event.y;
                })
                .on("end", function(event, d) {
                    if (!event.active) simulation.alphaTarget(0);
                    d.fx = null; d.fy = null;
                }));

        // Pattern circles
        node.filter(function(d) { return d.type === "pattern"; })
            .append("circle")
            .attr("r", function(d) { return self._sevRadius[d.severity] || 22; })
            .attr("fill", function(d) { return "url(#crossdisc-sev-" + d.severity + ")"; })
            .attr("stroke", function(d) { return self._sevColor[d.severity] || "#888"; })
            .attr("stroke-width", 2);

        // Pattern labels (abbreviated)
        node.filter(function(d) { return d.type === "pattern"; })
            .append("text")
            .attr("text-anchor", "middle")
            .attr("dy", "0.35em")
            .attr("fill", "#fff")
            .attr("font-size", "9px")
            .attr("font-weight", "600")
            .attr("pointer-events", "none")
            .text(function(d) {
                var words = d.label.split(/[\s\-]+/);
                if (words.length <= 2) return d.label.substring(0, 12);
                return words[0].substring(0, 5) + "…";
            });

        // Specialty circles
        node.filter(function(d) { return d.type === "specialty"; })
            .append("circle")
            .attr("r", function(d) { return 10 + (d.count || 1) * 3; })
            .attr("fill", function(d) { return self._specColors[d.label] || "#7AB0F0"; })
            .attr("fill-opacity", 0.7)
            .attr("stroke", function(d) { return self._specColors[d.label] || "#7AB0F0"; })
            .attr("stroke-width", 1.5);

        // Specialty labels
        node.filter(function(d) { return d.type === "specialty"; })
            .append("text")
            .attr("text-anchor", "middle")
            .attr("dy", function(d) { return (12 + (d.count || 1) * 3) + 12; })
            .attr("fill", "var(--text-secondary)")
            .attr("font-size", "10px")
            .attr("pointer-events", "none")
            .text(function(d) { return d.label; });

        // Click handler for pattern nodes
        node.filter(function(d) { return d.type === "pattern"; })
            .on("click", function(event, d) {
                self._showDetail(connections[d.dataIndex]);

                // Highlight selection
                node.selectAll("circle").attr("stroke-width", function(nd) {
                    return nd.id === d.id ? 4 : (nd.type === "pattern" ? 2 : 1.5);
                });
            });

        // Tick
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

    _showDetail: function(connection) {
        var self = this;
        var panel = document.getElementById("crossdisc-detail");
        if (!panel) return;
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        // ── Header: title + severity ──
        var title = document.createElement("div");
        title.style.cssText = "font-size:15px; font-weight:600; margin-bottom:6px; line-height:1.3;";
        title.textContent = connection.title || connection.disease || "";
        panel.appendChild(title);

        var sevMap = { high: "badge-critical", moderate: "badge-moderate", low: "badge-low" };
        var badge = document.createElement("span");
        badge.className = "badge " + (sevMap[connection.severity] || "badge-info");
        badge.textContent = (connection.severity || "moderate").toUpperCase();
        badge.style.cssText = "margin-bottom:16px; display:inline-block;";
        panel.appendChild(badge);

        // ── Section 1: What we found in your records ──
        var dataPoints = connection.patient_data_points || connection.matched_symptoms || [];
        if (dataPoints.length > 0) {
            panel.appendChild(this._sectionLabel("What we found in your records"));

            var dpList = document.createElement("div");
            dpList.style.cssText = "margin-bottom:14px; padding:10px 12px; background:var(--bg-sunken); border-radius:8px;";
            for (var i = 0; i < dataPoints.length; i++) {
                var dp = document.createElement("div");
                dp.style.cssText = "font-size:12px; color:var(--text-primary); padding:3px 0; line-height:1.5;";
                var dot = document.createElement("span");
                dot.style.cssText = "color:var(--accent-teal); margin-right:6px;";
                dot.textContent = "\u25cf";
                dp.appendChild(dot);
                dp.appendChild(document.createTextNode(dataPoints[i]));
                dpList.appendChild(dp);
            }
            panel.appendChild(dpList);
        }

        // Also show matched labs if present and different from data points
        var matchedLabs = connection.matched_labs || [];
        if (matchedLabs.length > 0 && dataPoints.length > 0) {
            var labList = document.createElement("div");
            labList.style.cssText = "margin-bottom:14px; padding:8px 12px; background:var(--bg-sunken); border-radius:8px;";
            var labNote = document.createElement("div");
            labNote.style.cssText = "font-size:11px; color:var(--text-muted); margin-bottom:4px;";
            labNote.textContent = "Lab markers matched:";
            labList.appendChild(labNote);
            for (var li = 0; li < matchedLabs.length; li++) {
                var lp = document.createElement("div");
                lp.style.cssText = "font-size:12px; color:var(--accent-amber); padding:2px 0;";
                lp.textContent = "\u25cf " + matchedLabs[li];
                labList.appendChild(lp);
            }
            panel.appendChild(labList);
        }

        // ── Section 2: Why this might matter ──
        var desc = connection.description || connection.pattern || "";
        if (desc) {
            panel.appendChild(this._sectionLabel("Why this might matter"));
            var descDiv = document.createElement("div");
            descDiv.style.cssText = "font-size:13px; color:var(--text-secondary); line-height:1.6; margin-bottom:14px;";
            descDiv.textContent = desc;
            panel.appendChild(descDiv);
        }

        // ── Section 3: The connection (specialties) ──
        var specs = connection.specialties || [];
        if (specs.length > 1) {
            panel.appendChild(this._sectionLabel("The connection"));
            var connNote = document.createElement("div");
            connNote.style.cssText = "font-size:12px; color:var(--text-secondary); line-height:1.5; margin-bottom:8px;";
            connNote.textContent = "These findings span " + specs.length + " specialties that don\u2019t always communicate:";
            panel.appendChild(connNote);

            var specRow = document.createElement("div");
            specRow.style.cssText = "display:flex; flex-wrap:wrap; gap:4px; margin-bottom:14px;";
            for (var si = 0; si < specs.length; si++) {
                var sb = document.createElement("span");
                sb.className = "badge badge-info";
                sb.style.cssText = "background:" + (this._specColors[specs[si]] || "#7AB0F0") + "; color:#fff; font-size:11px;";
                sb.textContent = specs[si];
                specRow.appendChild(sb);
            }
            panel.appendChild(specRow);
        }

        // ── Section 4: How we identified this ──
        panel.appendChild(this._sectionLabel("How we identified this"));
        var sourceDiv = document.createElement("div");
        sourceDiv.style.cssText = "font-size:12px; color:var(--text-muted); line-height:1.5; margin-bottom:14px;";

        var hits = connection.total_hits;
        var possible = connection.total_possible;
        var sourceType = connection.type || "";
        var evidenceSource = connection.evidence_source || "";
        var diagnosticSource = connection.diagnostic_source || "";

        if (sourceType === "ai_discovered_correlation") {
            // ── AI-discovered: show PubMed verification status ──
            var verified = connection.pubmed_verified;
            var pmCitations = connection.pubmed_citations || [];

            var verifyBadge = document.createElement("span");
            if (verified) {
                verifyBadge.style.cssText = "display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; margin-bottom:6px; background:rgba(88,184,136,0.15); color:var(--accent-green, #58B888); border:1px solid rgba(88,184,136,0.3);";
                verifyBadge.textContent = "\u2713 Verified against PubMed";
            } else {
                verifyBadge.style.cssText = "display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; margin-bottom:6px; background:rgba(200,168,72,0.15); color:var(--accent-amber); border:1px solid rgba(200,168,72,0.3);";
                verifyBadge.textContent = "\u26a0 Unverified \u2014 AI suggestion only";
            }
            sourceDiv.appendChild(verifyBadge);

            var aiExplain = document.createElement("div");
            aiExplain.style.cssText = "margin-top:6px;";
            var aiLabel = document.createElement("span");
            aiLabel.style.color = "var(--accent-blue)";
            aiLabel.textContent = "AI Analysis";
            aiExplain.appendChild(aiLabel);
            aiExplain.appendChild(document.createTextNode(" \u2014 Gemini identified this pattern from your records."));
            sourceDiv.appendChild(aiExplain);

            if (evidenceSource) {
                var srcLine = document.createElement("div");
                srcLine.style.cssText = "margin-top:4px; color:var(--text-secondary); font-size:11px;";
                srcLine.textContent = "Gemini cites: " + evidenceSource;
                sourceDiv.appendChild(srcLine);
            }

            // Show actual PubMed citations if verified
            if (pmCitations.length > 0) {
                var pmLabel = document.createElement("div");
                pmLabel.style.cssText = "margin-top:8px; font-size:11px; color:var(--accent-green, #58B888); font-weight:600;";
                pmLabel.textContent = "PubMed supporting literature:";
                sourceDiv.appendChild(pmLabel);
                for (var ci = 0; ci < pmCitations.length; ci++) {
                    var cite = pmCitations[ci];
                    var citeDiv = document.createElement("div");
                    citeDiv.style.cssText = "font-size:11px; color:var(--text-secondary); padding:2px 0; line-height:1.4;";
                    var citeText = cite.title || "";
                    if (cite.journal) citeText += " \u2014 " + cite.journal;
                    if (cite.year) citeText += " (" + cite.year + ")";
                    if (cite.pmid) citeText += " [PMID:" + cite.pmid + "]";
                    citeDiv.textContent = citeText;
                    sourceDiv.appendChild(citeDiv);
                }
            }
        } else if (hits && possible) {
            // ── Triad-based: show indicator match + diagnostic source ──
            sourceDiv.textContent = hits + " of " + possible + " known clinical indicators matched in your records.";

            if (diagnosticSource) {
                var diagBox = document.createElement("div");
                diagBox.style.cssText = "margin-top:8px; padding:8px 10px; background:var(--bg-sunken); border-radius:6px; border-left:3px solid var(--accent-teal);";

                var diagLabel = document.createElement("div");
                diagLabel.style.cssText = "font-size:10px; color:var(--accent-teal); font-weight:600; margin-bottom:3px; text-transform:uppercase; letter-spacing:0.05em;";
                diagLabel.textContent = "Diagnostic criteria source";
                diagBox.appendChild(diagLabel);

                var diagText = document.createElement("div");
                diagText.style.cssText = "font-size:11px; color:var(--text-secondary); line-height:1.4;";
                diagText.textContent = diagnosticSource;
                diagBox.appendChild(diagText);

                sourceDiv.appendChild(diagBox);
            }
        } else if (evidenceSource) {
            sourceDiv.textContent = "Based on: " + evidenceSource;
            if (diagnosticSource) {
                var diagLine = document.createElement("div");
                diagLine.style.cssText = "margin-top:4px; font-size:11px; color:var(--text-secondary);";
                diagLine.textContent = "Source: " + diagnosticSource;
                sourceDiv.appendChild(diagLine);
            }
        } else {
            sourceDiv.textContent = "Identified by cross-referencing your medical records across specialties.";
        }
        panel.appendChild(sourceDiv);

        // ── Section 5: Noted for your next visit ──
        var question = connection.question_for_doctor;
        if (question) {
            var visitBox = document.createElement("div");
            visitBox.style.cssText = "background:rgba(78,154,241,0.08); border:1px solid var(--accent-blue); padding:14px; border-radius:10px; margin-top:12px;";

            var visitLabel = document.createElement("div");
            visitLabel.style.cssText = "font-size:11px; color:var(--accent-blue); font-weight:600; margin-bottom:6px; text-transform:uppercase; letter-spacing:0.05em;";
            visitLabel.textContent = "Noted for your next visit";
            visitBox.appendChild(visitLabel);

            var qText = document.createElement("div");
            qText.style.cssText = "font-size:13px; line-height:1.5; margin-bottom:10px; color:var(--text-primary);";
            qText.textContent = question;
            visitBox.appendChild(qText);

            var addBtn = document.createElement("button");
            addBtn.className = "btn btn-sm";
            addBtn.style.cssText = "background:var(--accent-blue); color:#fff; border:none; padding:6px 14px; border-radius:6px; cursor:pointer; font-size:12px; font-weight:500;";
            addBtn.textContent = "Add to Visit Prep";
            addBtn.onclick = function() {
                self._addToVisitPrep(connection, addBtn);
            };
            visitBox.appendChild(addBtn);

            panel.appendChild(visitBox);
        }

        // ── Disclaimer ──
        var disc = document.createElement("div");
        disc.style.cssText = "font-size:11px; color:var(--text-muted); margin-top:14px; line-height:1.4; font-style:italic;";
        disc.textContent = "This is a pattern worth exploring, not a diagnosis. Your doctor can determine if further evaluation is needed.";
        panel.appendChild(disc);
    },

    _sectionLabel: function(text) {
        var el = document.createElement("div");
        el.style.cssText = "font-size:11px; color:var(--accent-amber); font-weight:600; margin:12px 0 6px; text-transform:uppercase; letter-spacing:0.05em;";
        el.textContent = text;
        return el;
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
                    btn.style.background = "var(--accent-blue)";
                    btn.disabled = false;
                }, 2000);
            } else {
                btn.textContent = "\u2713 Added to Visit Prep";
                btn.style.background = "var(--accent-green, #58B888)";
            }
        })
        .catch(function() {
            btn.textContent = "Failed";
            btn.style.background = "var(--accent-red, #C84040)";
            setTimeout(function() {
                btn.textContent = "Add to Visit Prep";
                btn.style.background = "var(--accent-blue)";
                btn.disabled = false;
            }, 2000);
        });
    },

    _buildLegend: function(connections) {
        var self = this;
        var legend = document.createElement("div");
        legend.style.cssText = "display:flex; flex-wrap:wrap; gap:16px; margin-top:16px; padding:12px; background:var(--bg-raised); border-radius:8px;";

        // Collect unique specialties
        var specsSeen = {};
        for (var i = 0; i < connections.length; i++) {
            var specs = connections[i].specialties || [];
            for (var j = 0; j < specs.length; j++) {
                specsSeen[specs[j]] = true;
            }
        }

        var specNames = Object.keys(specsSeen).sort();
        for (var k = 0; k < specNames.length; k++) {
            var item = document.createElement("div");
            item.style.cssText = "display:flex; align-items:center; gap:6px;";

            var dot = document.createElement("div");
            var color = self._specColors[specNames[k]] || "#7AB0F0";
            dot.style.cssText = "width:10px; height:10px; border-radius:50%; background:" + color + ";";
            item.appendChild(dot);

            var label = document.createElement("span");
            label.style.cssText = "font-size:12px; color:var(--text-secondary);";
            label.textContent = specNames[k];
            item.appendChild(label);

            legend.appendChild(item);
        }

        // Severity legend
        var sevs = [
            { key: "high", label: "High Severity" },
            { key: "moderate", label: "Moderate" },
            { key: "low", label: "Low" },
        ];

        for (var s = 0; s < sevs.length; s++) {
            var sItem = document.createElement("div");
            sItem.style.cssText = "display:flex; align-items:center; gap:6px;";

            var sDot = document.createElement("div");
            sDot.style.cssText = "width:10px; height:10px; border-radius:50%; background:" + self._sevColor[sevs[s].key] + ";";
            sItem.appendChild(sDot);

            var sLabel = document.createElement("span");
            sLabel.style.cssText = "font-size:12px; color:var(--text-muted);";
            sLabel.textContent = sevs[s].label;
            sItem.appendChild(sLabel);

            legend.appendChild(sItem);
        }

        return legend;
    },
};
