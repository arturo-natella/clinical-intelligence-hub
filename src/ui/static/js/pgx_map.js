/**
 * Pharmacogenomic Collision Map — D3 Bipartite Graph
 *
 * Shows gene-drug collisions: gene nodes on the left, drug nodes on
 * the right, edges colored by severity (critical/high/moderate).
 *
 * Red edges = critical collision (avoid drug or major dose change).
 * Orange edges = high severity.
 * Yellow edges = moderate.
 * Grey nodes with no edges = tested/active but no collision (safe).
 *
 * Click an edge or node for: collision details, recommended action.
 *
 * Overlay pattern matches Snowball / Cascades.
 */

/* global d3 */

var PgxMap = {
    _overlay: null,
    _isOpen: false,
    _data: null,

    open: function() {
        if (this._isOpen) return;

        fetch("/api/pgx-collisions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            PgxMap._data = data;
            PgxMap._buildOverlay(data);
        })
        .catch(function(err) {
            console.error("PGx fetch failed:", err);
        });
    },

    close: function() {
        if (this._overlay && this._overlay.parentNode) {
            this._overlay.parentNode.removeChild(this._overlay);
        }
        this._overlay = null;
        this._isOpen = false;
    },

    _buildOverlay: function(data) {
        var self = this;

        var overlay = document.createElement("div");
        overlay.className = "pgx-overlay";
        this._overlay = overlay;
        this._isOpen = true;

        // Header
        var header = document.createElement("div");
        header.className = "pgx-header";

        var titleWrap = document.createElement("div");
        var title = document.createElement("div");
        title.className = "pgx-title";
        title.textContent = "Pharmacogenomic Collision Map";
        titleWrap.appendChild(title);

        var subtitle = document.createElement("div");
        subtitle.className = "pgx-subtitle";
        subtitle.textContent = "How your genes affect the way your body processes medications";
        titleWrap.appendChild(subtitle);

        var closeBtn = document.createElement("button");
        closeBtn.className = "pgx-close";
        closeBtn.textContent = "\u00d7";
        closeBtn.addEventListener("click", function() { self.close(); });

        header.appendChild(titleWrap);
        header.appendChild(closeBtn);
        overlay.appendChild(header);

        // Summary bar
        var summary = data.summary || {};
        if (summary.total_genes_tested > 0 || summary.total_collisions > 0) {
            var summaryBar = document.createElement("div");
            summaryBar.className = "pgx-summary-bar";

            var genesStat = document.createElement("span");
            genesStat.className = "pgx-summary-stat";
            genesStat.textContent = (summary.total_genes_tested || 0) + " genes tested";
            summaryBar.appendChild(genesStat);

            if (summary.total_collisions > 0) {
                var collStat = document.createElement("span");
                collStat.className = "pgx-summary-stat pgx-stat-warn";
                collStat.textContent = summary.total_collisions + " collision" + (summary.total_collisions > 1 ? "s" : "") + " found";
                summaryBar.appendChild(collStat);

                if (summary.critical_count > 0) {
                    var critStat = document.createElement("span");
                    critStat.className = "pgx-summary-badge pgx-badge-critical";
                    critStat.textContent = summary.critical_count + " critical";
                    summaryBar.appendChild(critStat);
                }
                if (summary.high_count > 0) {
                    var highStat = document.createElement("span");
                    highStat.className = "pgx-summary-badge pgx-badge-high";
                    highStat.textContent = summary.high_count + " high";
                    summaryBar.appendChild(highStat);
                }
            } else {
                var safeStat = document.createElement("span");
                safeStat.className = "pgx-summary-stat pgx-stat-safe";
                safeStat.textContent = "No collisions detected";
                summaryBar.appendChild(safeStat);
            }

            overlay.appendChild(summaryBar);
        }

        // Main content
        var content = document.createElement("div");
        content.className = "pgx-content";

        var hasGenes = data.gene_nodes && data.gene_nodes.length > 0;
        var hasDrugs = data.drug_nodes && data.drug_nodes.length > 0;

        if (!hasGenes && !hasDrugs) {
            var empty = document.createElement("div");
            empty.className = "pgx-empty";
            empty.textContent = "No genetic data or medications found in your records. This map will show gene-drug interactions when both are present.";
            content.appendChild(empty);
            overlay.appendChild(content);
            document.body.appendChild(overlay);
            return;
        }

        // Graph panel
        var graphPanel = document.createElement("div");
        graphPanel.className = "pgx-graph-panel";
        graphPanel.id = "pgx-graph";
        content.appendChild(graphPanel);

        // Detail panel (bottom)
        var detailPanel = document.createElement("div");
        detailPanel.className = "pgx-detail-panel";
        detailPanel.id = "pgx-detail";

        var detailEmpty = document.createElement("div");
        detailEmpty.className = "pgx-detail-empty";
        detailEmpty.textContent = "Click a connection line or node to see collision details";
        detailPanel.appendChild(detailEmpty);

        content.appendChild(detailPanel);
        overlay.appendChild(content);

        // Partner note
        var partnerNote = document.createElement("div");
        partnerNote.className = "pgx-partner-note";

        var headline = document.createElement("div");
        headline.className = "pgx-partner-headline";
        headline.textContent = "Your genes are part of the picture.";
        partnerNote.appendChild(headline);

        var body = document.createElement("div");
        body.className = "pgx-partner-body";
        body.textContent = "This map shows where your genetic makeup may change how medications work in your body. Red connections mean a medication may be dangerous or ineffective based on your genes. Your doctor visit printout will include these findings so you can discuss them together.";
        partnerNote.appendChild(body);

        overlay.appendChild(partnerNote);
        document.body.appendChild(overlay);

        // Render D3
        this._renderGraph(data);
    },

    _renderGraph: function(data) {
        var self = this;
        var container = document.getElementById("pgx-graph");
        if (!container) return;

        var width = container.clientWidth || 800;
        var height = container.clientHeight || 500;

        while (container.firstChild) container.removeChild(container.firstChild);

        var svg = d3.select(container)
            .append("svg")
            .attr("width", width)
            .attr("height", height);

        // Layout: genes on left (x=20%), drugs on right (x=80%)
        var geneX = width * 0.2;
        var drugX = width * 0.8;

        var geneNodes = (data.gene_nodes || []).slice();
        var drugNodes = (data.drug_nodes || []).slice();
        var edges = (data.edges || []).slice();

        // Assign y positions evenly
        var geneSpacing = height / (geneNodes.length + 1);
        for (var i = 0; i < geneNodes.length; i++) {
            geneNodes[i].x = geneX;
            geneNodes[i].y = geneSpacing * (i + 1);
        }

        var drugSpacing = height / (drugNodes.length + 1);
        for (var j = 0; j < drugNodes.length; j++) {
            drugNodes[j].x = drugX;
            drugNodes[j].y = drugSpacing * (j + 1);
        }

        // Build lookup
        var nodeLookup = {};
        for (var gi = 0; gi < geneNodes.length; gi++) {
            nodeLookup[geneNodes[gi].id] = geneNodes[gi];
        }
        for (var di = 0; di < drugNodes.length; di++) {
            nodeLookup[drugNodes[di].id] = drugNodes[di];
        }

        // Severity colors
        var sevColor = {
            "critical": "#ef4444",
            "high": "#f97316",
            "moderate": "#eab308",
        };

        // Draw edges (curved paths)
        var edgeGroup = svg.append("g");
        var edgePaths = edgeGroup.selectAll("path")
            .data(edges)
            .enter()
            .append("path")
            .attr("class", "pgx-edge")
            .attr("d", function(d) {
                var src = nodeLookup[d.source];
                var tgt = nodeLookup[d.target];
                if (!src || !tgt) return "";
                var mx = (src.x + tgt.x) / 2;
                return "M" + src.x + "," + src.y +
                       " C" + mx + "," + src.y +
                       " " + mx + "," + tgt.y +
                       " " + tgt.x + "," + tgt.y;
            })
            .attr("fill", "none")
            .attr("stroke", function(d) { return sevColor[d.severity] || "#666"; })
            .attr("stroke-width", function(d) {
                return d.severity === "critical" ? 3 : d.severity === "high" ? 2.5 : 2;
            })
            .attr("stroke-opacity", 0.7)
            .style("cursor", "pointer");

        // Click on edge for detail
        edgePaths.on("click", function(event, d) {
            self._showEdgeDetail(d, nodeLookup);
        });

        // Draw gene nodes (left side)
        var geneGroup = svg.append("g").selectAll("g")
            .data(geneNodes)
            .enter()
            .append("g")
            .attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; })
            .style("cursor", "pointer");

        geneGroup.append("circle")
            .attr("r", 16)
            .attr("fill", function(d) {
                return d.no_collisions ? "#374151" : "#7c3aed";
            })
            .attr("stroke", function(d) {
                return d.no_collisions ? "#4b5563" : "#a78bfa";
            })
            .attr("stroke-width", 2)
            .attr("class", "pgx-node");

        // Gene icon (DNA helix symbol: ⧬)
        geneGroup.append("text")
            .text("\u29EC")
            .attr("text-anchor", "middle")
            .attr("dy", 5)
            .attr("font-size", "14px")
            .attr("fill", "#fff");

        // Gene label (to the left)
        geneGroup.append("text")
            .text(function(d) { return d.label; })
            .attr("dx", -24)
            .attr("dy", -4)
            .attr("text-anchor", "end")
            .attr("font-size", "12px")
            .attr("font-weight", "600")
            .attr("fill", function(d) { return d.no_collisions ? "#6b7280" : "#a78bfa"; });

        // Phenotype label under gene name
        geneGroup.append("text")
            .text(function(d) { return d.phenotype || ""; })
            .attr("dx", -24)
            .attr("dy", 10)
            .attr("text-anchor", "end")
            .attr("font-size", "10px")
            .attr("fill", "#6b7280");

        geneGroup.on("click", function(event, d) {
            self._showGeneDetail(d, edges, nodeLookup);
        });

        // Draw drug nodes (right side)
        var drugGroup = svg.append("g").selectAll("g")
            .data(drugNodes)
            .enter()
            .append("g")
            .attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; })
            .style("cursor", "pointer");

        drugGroup.append("rect")
            .attr("x", -14)
            .attr("y", -14)
            .attr("width", 28)
            .attr("height", 28)
            .attr("rx", 6)
            .attr("fill", function(d) {
                return d.no_collisions ? "#374151" : "#1e40af";
            })
            .attr("stroke", function(d) {
                return d.no_collisions ? "#4b5563" : "#60a5fa";
            })
            .attr("stroke-width", 2)
            .attr("class", "pgx-node");

        // Drug icon (pill: 💊 as text)
        drugGroup.append("text")
            .text("\u2695")
            .attr("text-anchor", "middle")
            .attr("dy", 5)
            .attr("font-size", "13px")
            .attr("fill", "#fff");

        // Drug label (to the right)
        drugGroup.append("text")
            .text(function(d) { return d.label; })
            .attr("dx", 22)
            .attr("dy", -2)
            .attr("text-anchor", "start")
            .attr("font-size", "12px")
            .attr("font-weight", "500")
            .attr("fill", function(d) { return d.no_collisions ? "#6b7280" : "#93c5fd"; });

        // "Active" label
        drugGroup.append("text")
            .text(function(d) { return d.is_active ? "active" : ""; })
            .attr("dx", 22)
            .attr("dy", 12)
            .attr("text-anchor", "start")
            .attr("font-size", "9px")
            .attr("fill", "#4b5563");

        drugGroup.on("click", function(event, d) {
            self._showDrugDetail(d, edges, nodeLookup);
        });

        // Column headers
        svg.append("text")
            .text("Your Genes")
            .attr("x", geneX)
            .attr("y", 20)
            .attr("text-anchor", "middle")
            .attr("font-size", "11px")
            .attr("font-weight", "600")
            .attr("fill", "#6b7280")
            .attr("text-transform", "uppercase")
            .attr("letter-spacing", "1px");

        svg.append("text")
            .text("Your Medications")
            .attr("x", drugX)
            .attr("y", 20)
            .attr("text-anchor", "middle")
            .attr("font-size", "11px")
            .attr("font-weight", "600")
            .attr("fill", "#6b7280")
            .attr("text-transform", "uppercase")
            .attr("letter-spacing", "1px");
    },

    _showEdgeDetail: function(edge, nodeLookup) {
        var panel = document.getElementById("pgx-detail");
        if (!panel) return;
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        var src = nodeLookup[edge.source] || {};
        var tgt = nodeLookup[edge.target] || {};

        // Header
        var header = document.createElement("div");
        header.className = "pgx-detail-header";

        var sevBadge = document.createElement("span");
        sevBadge.className = "pgx-sev-badge pgx-sev-" + edge.severity;
        sevBadge.textContent = edge.severity.toUpperCase();
        header.appendChild(sevBadge);

        var titleEl = document.createElement("strong");
        titleEl.textContent = (src.label || "?") + " \u00d7 " + (tgt.label || "?");
        header.appendChild(titleEl);

        panel.appendChild(header);

        // Phenotype
        if (src.phenotype) {
            var phenoEl = document.createElement("div");
            phenoEl.className = "pgx-detail-pheno";
            phenoEl.textContent = "Your genetic profile: " + src.label + " \u2014 " + src.phenotype;
            panel.appendChild(phenoEl);
        }

        // Risk
        var riskEl = document.createElement("div");
        riskEl.className = "pgx-detail-section";
        riskEl.textContent = "Risk: " + edge.risk;
        panel.appendChild(riskEl);

        // Action
        var actionEl = document.createElement("div");
        actionEl.className = "pgx-detail-action";
        actionEl.textContent = "Recommended action: " + edge.action;
        panel.appendChild(actionEl);

        // Reassurance
        var reassure = document.createElement("div");
        reassure.className = "pgx-reassure";
        reassure.textContent = "This finding will be included in your doctor visit printout with the full context your doctor needs.";
        panel.appendChild(reassure);
    },

    _showGeneDetail: function(gene, edges, nodeLookup) {
        var panel = document.getElementById("pgx-detail");
        if (!panel) return;
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        var header = document.createElement("div");
        header.className = "pgx-detail-header";

        var iconSpan = document.createElement("span");
        iconSpan.className = "pgx-gene-icon";
        iconSpan.textContent = "\u29EC";
        header.appendChild(iconSpan);

        var nameEl = document.createElement("strong");
        nameEl.textContent = gene.label;
        header.appendChild(nameEl);

        if (gene.phenotype) {
            var phenoSpan = document.createElement("span");
            phenoSpan.className = "pgx-detail-pheno-inline";
            phenoSpan.textContent = " \u2014 " + gene.phenotype;
            header.appendChild(phenoSpan);
        }

        panel.appendChild(header);

        // Find edges for this gene
        var geneEdges = [];
        for (var i = 0; i < edges.length; i++) {
            if (edges[i].source === gene.id) {
                geneEdges.push(edges[i]);
            }
        }

        if (geneEdges.length === 0) {
            var safeMsg = document.createElement("div");
            safeMsg.className = "pgx-detail-safe";
            safeMsg.textContent = "No collisions with your current medications. This gene was tested and your medications are compatible.";
            panel.appendChild(safeMsg);
        } else {
            var collTitle = document.createElement("div");
            collTitle.className = "pgx-detail-section-title";
            collTitle.textContent = "Affected medications:";
            panel.appendChild(collTitle);

            for (var j = 0; j < geneEdges.length; j++) {
                var e = geneEdges[j];
                var drugNode = nodeLookup[e.target] || {};
                var item = document.createElement("div");
                item.className = "pgx-detail-collision-item";

                var badge = document.createElement("span");
                badge.className = "pgx-sev-badge pgx-sev-" + e.severity;
                badge.textContent = e.severity.toUpperCase();
                item.appendChild(badge);

                var drugName = document.createElement("span");
                drugName.textContent = " " + (drugNode.label || "?") + " \u2014 " + e.risk;
                item.appendChild(drugName);

                panel.appendChild(item);
            }
        }
    },

    _showDrugDetail: function(drug, edges, nodeLookup) {
        var panel = document.getElementById("pgx-detail");
        if (!panel) return;
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        var header = document.createElement("div");
        header.className = "pgx-detail-header";

        var nameEl = document.createElement("strong");
        nameEl.textContent = drug.label;
        header.appendChild(nameEl);

        if (drug.is_active) {
            var activeTag = document.createElement("span");
            activeTag.className = "pgx-active-tag";
            activeTag.textContent = "Active Medication";
            header.appendChild(activeTag);
        }

        panel.appendChild(header);

        // Find edges targeting this drug
        var drugEdges = [];
        for (var i = 0; i < edges.length; i++) {
            if (edges[i].target === drug.id) {
                drugEdges.push(edges[i]);
            }
        }

        if (drugEdges.length === 0) {
            var safeMsg = document.createElement("div");
            safeMsg.className = "pgx-detail-safe";
            safeMsg.textContent = "No genetic interactions detected for this medication based on your tested genes.";
            panel.appendChild(safeMsg);
        } else {
            var collTitle = document.createElement("div");
            collTitle.className = "pgx-detail-section-title";
            collTitle.textContent = "Genetic interactions:";
            panel.appendChild(collTitle);

            for (var j = 0; j < drugEdges.length; j++) {
                var e = drugEdges[j];
                var geneNode = nodeLookup[e.source] || {};
                var item = document.createElement("div");
                item.className = "pgx-detail-collision-item";

                var badge = document.createElement("span");
                badge.className = "pgx-sev-badge pgx-sev-" + e.severity;
                badge.textContent = e.severity.toUpperCase();
                item.appendChild(badge);

                var geneName = document.createElement("span");
                geneName.textContent = " " + (geneNode.label || "?");
                if (geneNode.phenotype) {
                    geneName.textContent += " (" + geneNode.phenotype + ")";
                }
                geneName.textContent += " \u2014 " + e.action;
                item.appendChild(geneName);

                panel.appendChild(item);
            }
        }
    },
};
