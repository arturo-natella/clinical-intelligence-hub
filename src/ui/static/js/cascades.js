/**
 * Biomarker Cascade Graphs — D3 Force-Directed Visualization
 *
 * Shows how abnormal biomarkers cascade into downstream effects.
 * Red nodes = patient has this abnormality.
 * Grey nodes = predictive / not yet present.
 * Click a node to see: current value, normal range, downstream effects.
 *
 * Overlay pattern matches Snowball.
 */

/* global d3 */

var BiomarkerCascades = {
    _overlay: null,
    _isOpen: false,
    _data: null,
    _simulation: null,

    open: function() {
        if (this._isOpen) return;

        // Fetch cascade data
        fetch("/api/biomarker-cascades", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            BiomarkerCascades._data = data;
            BiomarkerCascades._buildOverlay(data);
        })
        .catch(function(err) {
            console.error("Cascade fetch failed:", err);
        });
    },

    close: function() {
        if (this._overlay && this._overlay.parentNode) {
            this._overlay.parentNode.removeChild(this._overlay);
        }
        if (this._simulation) {
            this._simulation.stop();
            this._simulation = null;
        }
        this._overlay = null;
        this._isOpen = false;
    },

    _buildOverlay: function(data) {
        var self = this;

        // Create overlay
        var overlay = document.createElement("div");
        overlay.className = "cascade-overlay";
        this._overlay = overlay;
        this._isOpen = true;

        // Header
        var header = document.createElement("div");
        header.className = "cascade-header";

        var titleWrap = document.createElement("div");
        var title = document.createElement("div");
        title.className = "cascade-title";
        title.textContent = "Biomarker Cascades";
        titleWrap.appendChild(title);

        var subtitle = document.createElement("div");
        subtitle.className = "cascade-subtitle";
        subtitle.textContent = "How your lab results connect — and what they could lead to";
        titleWrap.appendChild(subtitle);

        var closeBtn = document.createElement("button");
        closeBtn.className = "cascade-close";
        closeBtn.textContent = "\u00d7";
        closeBtn.addEventListener("click", function() { self.close(); });

        header.appendChild(titleWrap);
        header.appendChild(closeBtn);
        overlay.appendChild(header);

        // Main content area
        var content = document.createElement("div");
        content.className = "cascade-content";

        if (!data.active_cascades || data.active_cascades.length === 0) {
            var empty = document.createElement("div");
            empty.className = "cascade-empty";
            empty.textContent = "No active biomarker cascades detected in your lab results. This view will show connections when abnormal lab values are present.";
            content.appendChild(empty);
            overlay.appendChild(content);
            document.body.appendChild(overlay);
            return;
        }

        // Left panel: cascade list
        var leftPanel = document.createElement("div");
        leftPanel.className = "cascade-left-panel";

        var listTitle = document.createElement("div");
        listTitle.className = "cascade-list-title";
        listTitle.textContent = "Active Cascades";
        leftPanel.appendChild(listTitle);

        for (var i = 0; i < data.active_cascades.length; i++) {
            var cascade = data.active_cascades[i];
            var item = document.createElement("div");
            item.className = "cascade-list-item";
            item.setAttribute("data-cascade", cascade.name);

            var itemName = document.createElement("div");
            itemName.className = "cascade-item-name";
            itemName.textContent = cascade.name;
            item.appendChild(itemName);

            var itemMeta = document.createElement("div");
            itemMeta.className = "cascade-item-meta";
            itemMeta.textContent = cascade.active_nodes + " of " + cascade.total_nodes + " markers active \u2014 " + cascade.category;
            item.appendChild(itemMeta);

            (function(cascadeName) {
                item.addEventListener("click", function() {
                    self._highlightCascade(cascadeName);
                    // Update active state
                    var items = leftPanel.querySelectorAll(".cascade-list-item");
                    for (var j = 0; j < items.length; j++) {
                        items[j].classList.remove("active");
                    }
                    this.classList.add("active");
                });
            })(cascade.name);

            leftPanel.appendChild(item);
        }

        content.appendChild(leftPanel);

        // Right panel: D3 graph
        var graphPanel = document.createElement("div");
        graphPanel.className = "cascade-graph-panel";
        graphPanel.id = "cascade-graph";
        content.appendChild(graphPanel);

        // Detail panel (bottom)
        var detailPanel = document.createElement("div");
        detailPanel.className = "cascade-detail-panel";
        detailPanel.id = "cascade-detail";

        var detailEmpty = document.createElement("div");
        detailEmpty.className = "cascade-detail-empty";
        detailEmpty.textContent = "Click a node to see details about the biomarker connection";
        detailPanel.appendChild(detailEmpty);

        content.appendChild(detailPanel);

        overlay.appendChild(content);

        // Partner note
        var partnerNote = document.createElement("div");
        partnerNote.className = "cascade-partner-note";

        var headline = document.createElement("div");
        headline.className = "cascade-partner-headline";
        headline.textContent = "Understanding connections helps you ask better questions.";
        partnerNote.appendChild(headline);

        var body = document.createElement("div");
        body.className = "cascade-partner-body";
        body.textContent = "These cascades show how one lab result can affect others over time. Red markers are values your records show as abnormal. Grey markers are downstream effects to watch for. Your doctor visit printout will include these connections.";
        partnerNote.appendChild(body);

        overlay.appendChild(partnerNote);

        document.body.appendChild(overlay);

        // Render the D3 graph
        this._renderGraph(data);

        // Auto-select the first cascade
        var firstItem = leftPanel.querySelector(".cascade-list-item");
        if (firstItem) {
            firstItem.classList.add("active");
            this._highlightCascade(data.active_cascades[0].name);
        }
    },

    _renderGraph: function(data) {
        var self = this;
        var container = document.getElementById("cascade-graph");
        if (!container) return;

        var width = container.clientWidth || 700;
        var height = container.clientHeight || 450;

        // Clear existing
        while (container.firstChild) container.removeChild(container.firstChild);

        var svg = d3.select(container)
            .append("svg")
            .attr("width", width)
            .attr("height", height);

        // Arrow marker for directed edges
        svg.append("defs").append("marker")
            .attr("id", "cascade-arrow")
            .attr("viewBox", "0 -5 10 10")
            .attr("refX", 22)
            .attr("refY", 0)
            .attr("markerWidth", 6)
            .attr("markerHeight", 6)
            .attr("orient", "auto")
            .append("path")
            .attr("d", "M0,-5L10,0L0,5")
            .attr("fill", "#666");

        // Edges
        var links = svg.append("g").selectAll("line")
            .data(data.edges)
            .enter()
            .append("line")
            .attr("class", "cascade-edge")
            .attr("stroke", "#444")
            .attr("stroke-width", 1.5)
            .attr("stroke-opacity", 0.5)
            .attr("marker-end", "url(#cascade-arrow)");

        // Nodes
        var nodeGroup = svg.append("g").selectAll("g")
            .data(data.nodes)
            .enter()
            .append("g")
            .attr("class", "cascade-node-group")
            .call(d3.drag()
                .on("start", function(event, d) {
                    if (!event.active && self._simulation) self._simulation.alphaTarget(0.3).restart();
                    d.fx = d.x;
                    d.fy = d.y;
                })
                .on("drag", function(event, d) {
                    d.fx = event.x;
                    d.fy = event.y;
                })
                .on("end", function(event, d) {
                    if (!event.active && self._simulation) self._simulation.alphaTarget(0);
                    d.fx = null;
                    d.fy = null;
                })
            );

        nodeGroup.append("circle")
            .attr("r", function(d) { return d.patient_has ? 14 : 10; })
            .attr("fill", function(d) {
                if (d.patient_has) return "#ef4444"; // Red — abnormal
                if (d.type === "organ_effect") return "#6b7280"; // Dark grey
                return "#9ca3af"; // Light grey — predictive
            })
            .attr("stroke", function(d) {
                return d.patient_has ? "#fca5a5" : "#d1d5db";
            })
            .attr("stroke-width", function(d) { return d.patient_has ? 2.5 : 1; })
            .attr("class", "cascade-node");

        nodeGroup.append("text")
            .text(function(d) { return d.label; })
            .attr("dx", 18)
            .attr("dy", 4)
            .attr("font-size", "11px")
            .attr("fill", function(d) { return d.patient_has ? "#fca5a5" : "#9ca3af"; });

        // Click handler for detail
        nodeGroup.on("click", function(event, d) {
            self._showNodeDetail(d, data);
        });

        // Simulation
        var nodeMap = {};
        for (var i = 0; i < data.nodes.length; i++) {
            nodeMap[data.nodes[i].id] = data.nodes[i];
        }

        // Resolve edge references
        var resolvedEdges = [];
        for (var j = 0; j < data.edges.length; j++) {
            var e = data.edges[j];
            var src = nodeMap[e.source] || nodeMap[e.source.id];
            var tgt = nodeMap[e.target] || nodeMap[e.target.id];
            if (src && tgt) {
                resolvedEdges.push({ source: src, target: tgt, mechanism: e.mechanism, cascade: e.cascade });
            }
        }

        this._simulation = d3.forceSimulation(data.nodes)
            .force("link", d3.forceLink(resolvedEdges).id(function(d) { return d.id; }).distance(100))
            .force("charge", d3.forceManyBody().strength(-200))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide(30))
            .on("tick", function() {
                links
                    .attr("x1", function(d) { return d.source.x; })
                    .attr("y1", function(d) { return d.source.y; })
                    .attr("x2", function(d) { return d.target.x; })
                    .attr("y2", function(d) { return d.target.y; });

                nodeGroup
                    .attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; });
            });
    },

    _highlightCascade: function(cascadeName) {
        if (!this._overlay) return;
        var svg = this._overlay.querySelector("svg");
        if (!svg) return;

        // Dim all nodes/edges, then highlight the selected cascade
        d3.select(svg).selectAll(".cascade-node-group")
            .attr("opacity", function(d) {
                return d.cascade === cascadeName ? 1 : 0.2;
            });

        d3.select(svg).selectAll(".cascade-edge")
            .attr("stroke-opacity", function(d) {
                return d.cascade === cascadeName ? 0.7 : 0.08;
            });
    },

    _showNodeDetail: function(d, data) {
        var panel = document.getElementById("cascade-detail");
        if (!panel) return;

        while (panel.firstChild) panel.removeChild(panel.firstChild);

        // Node name + status
        var header = document.createElement("div");
        header.className = "cascade-detail-header";

        var statusDot = document.createElement("span");
        statusDot.className = d.patient_has ? "cascade-dot-active" : "cascade-dot-inactive";
        header.appendChild(statusDot);

        var nameEl = document.createElement("strong");
        nameEl.textContent = d.label;
        header.appendChild(nameEl);

        if (d.patient_has && d.patient_value) {
            var valEl = document.createElement("span");
            valEl.className = "cascade-detail-value";
            valEl.textContent = " \u2014 " + d.patient_value;
            if (d.patient_flag) {
                valEl.textContent += " [" + d.patient_flag.toUpperCase() + "]";
            }
            header.appendChild(valEl);
        }

        panel.appendChild(header);

        // Cascade name
        var cascadeLabel = document.createElement("div");
        cascadeLabel.className = "cascade-detail-cascade";
        cascadeLabel.textContent = "Part of: " + d.cascade;
        panel.appendChild(cascadeLabel);

        // Find incoming and outgoing edges
        var incoming = [];
        var outgoing = [];
        for (var i = 0; i < data.edges.length; i++) {
            var e = data.edges[i];
            var srcId = (typeof e.source === "string") ? e.source : e.source.id;
            var tgtId = (typeof e.target === "string") ? e.target : e.target.id;
            if (tgtId === d.id) incoming.push(e);
            if (srcId === d.id) outgoing.push(e);
        }

        if (incoming.length > 0) {
            var inTitle = document.createElement("div");
            inTitle.className = "cascade-detail-section";
            inTitle.textContent = "Caused by:";
            panel.appendChild(inTitle);

            for (var j = 0; j < incoming.length; j++) {
                var srcNode = this._findNode(data.nodes, incoming[j].source);
                var mech = document.createElement("div");
                mech.className = "cascade-detail-mech";
                mech.textContent = (srcNode ? srcNode.label : "?") + " \u2192 " + incoming[j].mechanism;
                panel.appendChild(mech);
            }
        }

        if (outgoing.length > 0) {
            var outTitle = document.createElement("div");
            outTitle.className = "cascade-detail-section";
            outTitle.textContent = "Can lead to:";
            panel.appendChild(outTitle);

            for (var k = 0; k < outgoing.length; k++) {
                var tgtNode = this._findNode(data.nodes, outgoing[k].target);
                var mechOut = document.createElement("div");
                mechOut.className = "cascade-detail-mech";
                mechOut.textContent = (tgtNode ? tgtNode.label : "?") + " \u2014 " + outgoing[k].mechanism;
                panel.appendChild(mechOut);
            }
        }

        // Reassurance
        var reassure = document.createElement("div");
        reassure.className = "cascade-reassure";
        if (d.patient_has) {
            reassure.textContent = "This value is flagged in your records. I\u2019ll include the downstream connections in your doctor visit printout.";
        } else {
            reassure.textContent = "This hasn\u2019t shown up in your records yet \u2014 it\u2019s something your doctor may want to monitor.";
        }
        panel.appendChild(reassure);
    },

    _findNode: function(nodes, ref) {
        var id = (typeof ref === "string") ? ref : ref.id;
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].id === id) return nodes[i];
        }
        return null;
    },
};
