/**
 * Clinical Intelligence Hub — Flowing Timeline Visualization
 *
 * D3.js swim-lane timeline that renders health events as nodes
 * on a horizontal time axis. Each event type (medication, lab,
 * diagnosis, procedure, imaging, symptom) gets its own lane,
 * color-coded to match the existing design system.
 *
 * Features:
 *   - Horizontal time axis with zoom/pan (d3.zoom)
 *   - Swim lanes grouped by event type
 *   - Hover tooltips with event details
 *   - Filter integration (show/hide lanes)
 *   - Date range brushing (mini-map)
 *   - Responsive: auto-sizes to container
 *
 * XSS: All user content rendered via D3 text nodes (textContent)
 * or escaped with _esc() before DOM insertion.
 */

var TimelineFlow = (function () {
    "use strict";

    // ── Lane configuration ─────────────────────────────────
    var LANES = [
        { type: "medication", label: "Medications", color: "#5a8ffc" },
        { type: "diagnosis",  label: "Diagnoses",   color: "#a07aff" },
        { type: "lab",        label: "Labs",         color: "#dc2626" },
        { type: "procedure",  label: "Procedures",   color: "#f0c550" },
        { type: "imaging",    label: "Imaging",      color: "#5cd47f" },
        { type: "symptom",    label: "Symptoms",     color: "#e06c8a" },
    ];

    var LANE_MAP = {};
    LANES.forEach(function (l, i) { LANE_MAP[l.type] = i; });

    // ── Layout constants ───────────────────────────────────
    var MARGIN   = { top: 40, right: 30, bottom: 60, left: 120 };
    var LANE_H   = 48;  // px per swim lane
    var NODE_R   = 6;   // event node radius
    var MINI_H   = 40;  // mini-map (brush) height
    var MINI_GAP = 12;
    var LABEL_GAP = 18; // minimum px gap between visible labels in a lane
    var LABEL_CHAR_W = 6.5; // rough text width estimate used for label culling

    // ── State ──────────────────────────────────────────────
    var allEvents = [];
    var filteredEvents = [];
    var currentFilter = "all";
    var svg, mainG, miniG, xScale, xScaleMini, yScale;
    var tooltipEl, detailPanelEl;
    var zoom;
    var container;
    var width, height;
    var selectedClusterKey = null;

    // ── Public API ─────────────────────────────────────────

    function init(events, filterType) {
        allEvents = (events || []).slice();
        currentFilter = filterType || "all";
        selectedClusterKey = null;

        // Parse dates
        allEvents.forEach(function (e) {
            if (typeof e.date === "string") {
                e._date = new Date(e.date);
            } else {
                e._date = e.date;
            }
        });

        // Sort ascending by date
        allEvents.sort(function (a, b) { return a._date - b._date; });
        allEvents.forEach(function (e, i) {
            e._timelineKey = e.type + ":" + (e.date || "") + ":" + i;
        });

        _applyFilter();
        _buildChart();
    }

    function filter(type) {
        currentFilter = type;
        selectedClusterKey = null;
        _applyFilter();
        _render();
        _renderDetailEmpty();
    }

    function resize() {
        if (!container || !allEvents.length) return;
        _buildChart();
    }

    // ── Internal ───────────────────────────────────────────

    function _applyFilter() {
        if (currentFilter === "all") {
            filteredEvents = allEvents;
        } else {
            filteredEvents = allEvents.filter(function (e) {
                return e.type === currentFilter;
            });
        }
    }

    function _buildChart() {
        container = document.getElementById("timeline-flow-container");
        detailPanelEl = document.getElementById("timeline-detail-panel");
        if (!container) return;

        // Clear previous
        while (container.firstChild) container.removeChild(container.firstChild);

        if (!filteredEvents.length) {
            var msg = document.createElement("div");
            msg.style.cssText = "color:var(--text-muted); text-align:center; padding:40px;";
            msg.textContent = "No events to display.";
            container.appendChild(msg);
            _renderDetailEmpty("No events to display.");
            return;
        }

        _renderDetailEmpty();

        // Dimensions
        var rect = container.getBoundingClientRect();
        width = rect.width || 800;
        var visibleLanes = _getVisibleLanes();
        var chartH = MARGIN.top + visibleLanes.length * LANE_H + MARGIN.bottom;
        height = chartH + MINI_GAP + MINI_H + 10;

        // ── Tooltip (built with DOM, not innerHTML) ─────
        tooltipEl = document.createElement("div");
        tooltipEl.className = "tl-tooltip";
        tooltipEl.style.opacity = "0";
        container.appendChild(tooltipEl);

        // ── SVG ─────────────────────────────────────────
        svg = d3.select(container)
            .append("svg")
            .attr("width", width)
            .attr("height", height);

        // Clip path for main chart area
        svg.append("defs")
            .append("clipPath")
            .attr("id", "tl-clip")
            .append("rect")
            .attr("width", width - MARGIN.left - MARGIN.right)
            .attr("height", chartH - MARGIN.top);

        // ── Scales ──────────────────────────────────────
        var dateExtent = d3.extent(filteredEvents, function (d) { return d._date; });
        // Pad by 5% on each side
        var pad = (dateExtent[1] - dateExtent[0]) * 0.05 || 86400000;
        var domainStart = new Date(dateExtent[0].getTime() - pad);
        var domainEnd = new Date(dateExtent[1].getTime() + pad);

        xScale = d3.scaleTime()
            .domain([domainStart, domainEnd])
            .range([0, width - MARGIN.left - MARGIN.right]);

        xScaleMini = d3.scaleTime()
            .domain([domainStart, domainEnd])
            .range([0, width - MARGIN.left - MARGIN.right]);

        yScale = d3.scaleOrdinal()
            .domain(visibleLanes.map(function (l) { return l.type; }))
            .range(visibleLanes.map(function (_, i) { return i * LANE_H + LANE_H / 2; }));

        // ── Main chart group ────────────────────────────
        mainG = svg.append("g")
            .attr("transform", "translate(" + MARGIN.left + "," + MARGIN.top + ")");

        // Lane backgrounds
        var laneG = mainG.append("g").attr("class", "tl-lanes");
        visibleLanes.forEach(function (lane, i) {
            laneG.append("rect")
                .attr("x", 0)
                .attr("y", i * LANE_H)
                .attr("width", width - MARGIN.left - MARGIN.right)
                .attr("height", LANE_H)
                .attr("fill", i % 2 === 0 ? "rgba(255,255,255,0.02)" : "transparent")
                .attr("class", "tl-lane-bg");
        });

        // Lane labels (left side)
        var labelG = svg.append("g")
            .attr("transform", "translate(0," + MARGIN.top + ")");
        visibleLanes.forEach(function (lane, i) {
            labelG.append("circle")
                .attr("cx", 16)
                .attr("cy", i * LANE_H + LANE_H / 2)
                .attr("r", 5)
                .attr("fill", lane.color);

            labelG.append("text")
                .attr("x", 28)
                .attr("y", i * LANE_H + LANE_H / 2 + 4)
                .attr("fill", "var(--text-secondary)")
                .style("font-size", "12px")
                .style("font-weight", "500")
                .text(lane.label);
        });

        // ── Zoom on main chart ──────────────────────────
        zoom = d3.zoom()
            .scaleExtent([0.5, 20])
            .translateExtent([[-50, 0], [width * 2, height]])
            .on("zoom", function (event) {
                var newX = event.transform.rescaleX(xScaleMini);
                xScale.domain(newX.domain());
                _renderNodes();
                _renderAxis(visibleLanes);
                _renderGrid(visibleLanes);
            });

        mainG.append("rect")
            .attr("class", "tl-zoom-overlay")
            .attr("width", width - MARGIN.left - MARGIN.right)
            .attr("height", visibleLanes.length * LANE_H)
            .attr("fill", "transparent")
            .style("cursor", "grab")
            .on("click", function (event) {
                if (event.defaultPrevented) return;
                selectedClusterKey = null;
                tooltipEl.style.opacity = "0";
                _renderDetailEmpty();
                _renderNodes();
            })
            .call(zoom);

        // Clipped group for nodes and grid
        var clipped = mainG.append("g")
            .attr("clip-path", "url(#tl-clip)");

        // Grid lines (will be updated by zoom)
        clipped.append("g").attr("class", "tl-grid");

        // Event nodes group
        clipped.append("g").attr("class", "tl-nodes");

        // ── X axis ──────────────────────────────────────
        mainG.append("g")
            .attr("class", "tl-x-axis")
            .attr("transform", "translate(0," + (visibleLanes.length * LANE_H) + ")");

        // ── Mini-map ────────────────────────────────────
        var miniTop = chartH + MINI_GAP;
        miniG = svg.append("g")
            .attr("transform", "translate(" + MARGIN.left + "," + miniTop + ")");

        miniG.append("rect")
            .attr("width", width - MARGIN.left - MARGIN.right)
            .attr("height", MINI_H)
            .attr("fill", "rgba(255,255,255,0.03)")
            .attr("stroke", "var(--border-faint)")
            .attr("rx", 4);

        // Mini event dots
        var miniYScale = d3.scaleOrdinal()
            .domain(LANES.map(function (l) { return l.type; }))
            .range(LANES.map(function (_, i) {
                return (i + 0.5) * MINI_H / LANES.length;
            }));

        miniG.selectAll(".tl-mini-dot")
            .data(filteredEvents)
            .enter()
            .append("circle")
            .attr("class", "tl-mini-dot")
            .attr("cx", function (d) { return xScaleMini(d._date); })
            .attr("cy", function (d) { return miniYScale(d.type) || MINI_H / 2; })
            .attr("r", 2)
            .attr("fill", function (d) {
                var lane = LANES[LANE_MAP[d.type]];
                return lane ? lane.color : "#888";
            })
            .attr("opacity", 0.6);

        // ── Brush on mini-map ───────────────────────────
        var brush = d3.brushX()
            .extent([[0, 0], [width - MARGIN.left - MARGIN.right, MINI_H]])
            .on("brush end", function (event) {
                if (!event.selection) {
                    // Reset to full view
                    xScale.domain([domainStart, domainEnd]);
                } else {
                    var s = event.selection;
                    xScale.domain([xScaleMini.invert(s[0]), xScaleMini.invert(s[1])]);
                }
                _renderNodes();
                _renderAxis(visibleLanes);
                _renderGrid(visibleLanes);
            });

        miniG.append("g")
            .attr("class", "tl-brush")
            .call(brush);

        // Initial render
        _render();
    }

    function _render() {
        if (!mainG) return;
        var visibleLanes = _getVisibleLanes();
        _renderNodes();
        _renderAxis(visibleLanes);
        _renderGrid(visibleLanes);
    }

    function _renderNodes() {
        var nodesG = mainG.select(".tl-nodes");
        var chartW = width - MARGIN.left - MARGIN.right;
        var displayItems = _buildDisplayItems(chartW);
        var labelLayout = _buildLabelLayout(displayItems, chartW);

        var nodes = nodesG.selectAll(".tl-node")
            .data(displayItems, function (d) { return d._clusterKey; });

        // Exit
        nodes.exit().remove();

        // Enter
        var enter = nodes.enter()
            .append("g")
            .attr("class", "tl-node");

        enter.append("circle")
            .attr("fill", function (d) {
                var lane = LANES[LANE_MAP[d.type]];
                return lane ? lane.color : "#888";
            })
            .attr("stroke", "var(--bg-primary)")
            .attr("stroke-width", 2)
            .style("cursor", "pointer");

        enter.append("text")
            .attr("class", "tl-node-count")
            .attr("text-anchor", "middle")
            .attr("dy", 4)
            .style("font-size", "9px")
            .style("font-weight", "700")
            .style("pointer-events", "none");

        enter.append("text")
            .attr("class", "tl-node-label")
            .attr("dy", -12)
            .attr("text-anchor", "middle")
            .attr("fill", "var(--text-secondary)")
            .style("font-size", "10px")
            .style("pointer-events", "none");

        // Merge enter + update
        var merged = enter.merge(nodes);

        merged.attr("transform", function (d) {
            var x = d._x;
            var y = yScale(d.type);
            if (y === undefined) y = 0;
            return "translate(" + x + "," + y + ")";
        })
        .style("display", function (d) {
            var x = d._x;
            return (x < -20 || x > chartW + 20) ? "none" : null;
        });

        merged.select("circle")
            .attr("r", function (d) {
                return _nodeRadius(d);
            })
            .attr("stroke", function (d) {
                return d._clusterKey === selectedClusterKey
                    ? "rgba(255,255,255,0.92)"
                    : "var(--bg-primary)";
            })
            .attr("stroke-width", function (d) {
                return d._clusterKey === selectedClusterKey ? 3 : 2;
            })
            .on("mouseenter", function (event, d) {
                var baseRadius = _nodeRadius(d);
                d3.select(this)
                    .transition().duration(150)
                    .attr("r", baseRadius + 2)
                    .attr("stroke-width", Math.max(3, d._clusterKey === selectedClusterKey ? 4 : 3));

                _showTooltip(event, d);
            })
            .on("mouseleave", function (event, d) {
                d3.select(this)
                    .transition().duration(150)
                    .attr("r", _nodeRadius(d))
                    .attr("stroke", d._clusterKey === selectedClusterKey
                        ? "rgba(255,255,255,0.92)"
                        : "var(--bg-primary)")
                    .attr("stroke-width", d._clusterKey === selectedClusterKey ? 3 : 2);

                tooltipEl.style.opacity = "0";
            })
            .on("click", function (event, d) {
                tooltipEl.style.opacity = "0";
                _toggleSelection(d);
                _renderNodes();
                event.stopPropagation();
            });

        merged.select(".tl-node-count")
            .style("display", function (d) {
                return d._count > 1 ? null : "none";
            })
            .text(function (d) {
                return d._count > 1 ? String(d._count) : "";
            });

        // D3 .text() uses textContent (safe, no XSS)
        merged.select(".tl-node-label")
            .attr("dy", function (d) {
                var layout = labelLayout[d._clusterKey];
                return layout ? layout.dy : -12;
            })
            .style("display", function (d) {
                return labelLayout[d._clusterKey] ? null : "none";
            })
            .text(function (d) {
                var layout = labelLayout[d._clusterKey];
                return layout ? layout.text : "";
            });
    }

    function _renderAxis(visibleLanes) {
        var axisG = mainG.select(".tl-x-axis");
        var xAxis = d3.axisBottom(xScale)
            .ticks(Math.max(4, Math.floor((width - MARGIN.left - MARGIN.right) / 120)))
            .tickFormat(d3.timeFormat("%b %Y"));

        axisG.attr("transform", "translate(0," + (visibleLanes.length * LANE_H) + ")")
            .call(xAxis)
            .selectAll("text")
            .attr("fill", "var(--text-muted)")
            .style("font-size", "11px");

        axisG.selectAll("line").attr("stroke", "var(--border-faint)");
        axisG.select(".domain").attr("stroke", "var(--border-faint)");
    }

    function _renderGrid(visibleLanes) {
        var gridG = mainG.select(".tl-grid");
        gridG.selectAll("*").remove();

        var ticks = xScale.ticks(
            Math.max(4, Math.floor((width - MARGIN.left - MARGIN.right) / 120))
        );
        var laneH = visibleLanes.length * LANE_H;

        ticks.forEach(function (t) {
            gridG.append("line")
                .attr("x1", xScale(t))
                .attr("x2", xScale(t))
                .attr("y1", 0)
                .attr("y2", laneH)
                .attr("stroke", "var(--border-faint)")
                .attr("stroke-dasharray", "2,4")
                .attr("opacity", 0.5);
        });

        // Horizontal lane separators
        for (var i = 1; i < visibleLanes.length; i++) {
            gridG.append("line")
                .attr("x1", 0)
                .attr("x2", width - MARGIN.left - MARGIN.right)
                .attr("y1", i * LANE_H)
                .attr("y2", i * LANE_H)
                .attr("stroke", "var(--border-faint)")
                .attr("opacity", 0.3);
        }
    }

    /**
     * Build tooltip using safe DOM methods only — no innerHTML.
     * All text goes through textContent (which auto-escapes).
     */
    function _showTooltip(event, d) {
        var lane = LANES[LANE_MAP[d.type]];
        var color = lane ? lane.color : "#888";

        // Clear tooltip safely
        while (tooltipEl.firstChild) tooltipEl.removeChild(tooltipEl.firstChild);

        // Build tooltip DOM
        var wrapper = document.createElement("div");
        wrapper.style.cssText = "border-left:3px solid " + color + "; padding-left:8px;";

        if (d._count > 1) {
            var clusterTitleDiv = document.createElement("div");
            clusterTitleDiv.style.cssText = "font-weight:600; margin-bottom:4px;";
            clusterTitleDiv.textContent = d._count + " " + _typeLabel(d.type, d._count);
            wrapper.appendChild(clusterTitleDiv);

            var clusterDateDiv = document.createElement("div");
            clusterDateDiv.style.cssText = "color:var(--text-muted); font-size:11px; margin-bottom:6px;";
            clusterDateDiv.textContent = _formatDateRange(d._dateStart, d._dateEnd);
            wrapper.appendChild(clusterDateDiv);

            d._events.slice(0, 4).forEach(function (eventItem) {
                var eventDiv = document.createElement("div");
                eventDiv.style.cssText = "font-size:12px; color:var(--text-secondary); margin-top:3px;";
                eventDiv.textContent = "\u2022 " + (eventItem.title || "");
                wrapper.appendChild(eventDiv);
            });

            if (d._events.length > 4) {
                var moreDiv = document.createElement("div");
                moreDiv.style.cssText = "font-size:11px; color:var(--text-muted); margin-top:4px;";
                moreDiv.textContent = "+" + (d._events.length - 4) + " more";
                wrapper.appendChild(moreDiv);
            }
        } else {
            var titleDiv = document.createElement("div");
            titleDiv.style.cssText = "font-weight:600; margin-bottom:4px;";
            titleDiv.textContent = d.title || "";
            wrapper.appendChild(titleDiv);

            var dateDiv = document.createElement("div");
            dateDiv.style.cssText = "color:var(--text-muted); font-size:11px; margin-bottom:4px;";
            dateDiv.textContent = _formatDate(d._date);
            wrapper.appendChild(dateDiv);

            if (d.detail) {
                var detailDiv = document.createElement("div");
                detailDiv.style.cssText = "font-size:12px; color:var(--text-secondary);";
                detailDiv.textContent = d.detail;
                wrapper.appendChild(detailDiv);
            }
        }

        tooltipEl.appendChild(wrapper);
        tooltipEl.style.opacity = "1";

        // Position relative to container
        var containerRect = container.getBoundingClientRect();
        var tipX = event.clientX - containerRect.left + 15;
        var tipY = event.clientY - containerRect.top - 10;

        // Keep tooltip in bounds
        var tipW = tooltipEl.offsetWidth || 200;
        if (tipX + tipW > containerRect.width - 10) {
            tipX = event.clientX - containerRect.left - tipW - 15;
        }

        tooltipEl.style.left = tipX + "px";
        tooltipEl.style.top = tipY + "px";
    }

    function _toggleSelection(d) {
        if (selectedClusterKey === d._clusterKey) {
            selectedClusterKey = null;
            _renderDetailEmpty();
            return;
        }

        selectedClusterKey = d._clusterKey;
        _renderDetailPanel(d);
    }

    function _renderDetailEmpty(message) {
        if (!detailPanelEl) return;
        _clearElement(detailPanelEl);

        var empty = document.createElement("div");
        empty.className = "tl-detail-empty";
        empty.textContent = message || "Click a bubble to see the details for that event.";
        detailPanelEl.appendChild(empty);
    }

    function _renderDetailPanel(item) {
        if (!detailPanelEl) return;
        _clearElement(detailPanelEl);

        var header = document.createElement("div");
        header.className = "tl-detail-header";

        var headerCopy = document.createElement("div");
        var title = document.createElement("div");
        title.className = "tl-detail-title";
        title.textContent = item._count > 1
            ? item._count + " " + _typeLabel(item.type, item._count)
            : (item._events[0].title || item.title || "Timeline event");
        headerCopy.appendChild(title);

        var meta = document.createElement("div");
        meta.className = "tl-detail-meta";
        meta.textContent = item._count > 1
            ? _formatDateRange(item._dateStart, item._dateEnd)
            : _formatDate(item._events[0]._date || item._date);
        headerCopy.appendChild(meta);
        header.appendChild(headerCopy);

        var closeBtn = document.createElement("button");
        closeBtn.className = "tl-detail-close";
        closeBtn.type = "button";
        closeBtn.textContent = "Close";
        closeBtn.addEventListener("click", function () {
            selectedClusterKey = null;
            _renderDetailEmpty();
            _renderNodes();
        });
        header.appendChild(closeBtn);

        detailPanelEl.appendChild(header);

        if (item._count > 1) {
            var summary = document.createElement("div");
            summary.className = "tl-detail-body";
            summary.textContent = "This bubble groups several nearby events. Each item below can be expanded to show the full details for that event.";
            detailPanelEl.appendChild(summary);

            var list = document.createElement("div");
            list.className = "tl-detail-list";
            item._events.forEach(function (eventItem, index) {
                var row = document.createElement("details");
                row.className = "tl-detail-list-item tl-detail-accordion";
                row.open = item._events.length <= 4 || index === 0;

                var rowSummary = document.createElement("summary");
                rowSummary.className = "tl-detail-accordion-summary";

                var rowHead = document.createElement("div");
                rowHead.className = "tl-detail-accordion-head";

                var rowTitle = document.createElement("div");
                rowTitle.className = "tl-detail-list-title";
                rowTitle.textContent = eventItem.title || "Event";
                rowHead.appendChild(rowTitle);

                var rowMeta = document.createElement("div");
                rowMeta.className = "tl-detail-list-meta";
                rowMeta.textContent = _formatDate(eventItem._date);
                rowHead.appendChild(rowMeta);

                if (eventItem.detail) {
                    var rowBody = document.createElement("div");
                    rowBody.className = "tl-detail-list-body";
                    rowBody.textContent = eventItem.detail;
                    rowHead.appendChild(rowBody);
                }

                rowSummary.appendChild(rowHead);
                row.appendChild(rowSummary);

                var rowContent = document.createElement("div");
                rowContent.className = "tl-detail-accordion-content";
                _appendEventDetails(rowContent, eventItem);
                row.appendChild(rowContent);

                list.appendChild(row);
            });
            detailPanelEl.appendChild(list);
            return;
        }

        var eventData = item._events[0];
        _appendEventDetails(detailPanelEl, eventData);
    }

    function _appendEventDetails(containerEl, eventData) {
        var grid = document.createElement("div");
        grid.className = "tl-detail-grid";

        if (eventData.type === "medication") {
            _appendDetailField(grid, "Dose", eventData.dosage);
            _appendDetailField(grid, "Frequency", eventData.frequency);
            _appendDetailField(grid, "Route", eventData.route);
            _appendDetailField(grid, "Prescriber", eventData.prescriber);
            _appendDetailField(grid, "Status", eventData.status);
        } else if (eventData.type === "lab") {
            _appendDetailField(grid, "Result", _compactParts([eventData.value, eventData.value_text, eventData.unit]));
            _appendDetailField(grid, "Flag", eventData.flag);
            _appendDetailField(grid, "Reference Range", _formatReferenceRange(eventData.reference_low, eventData.reference_high, eventData.unit));
        } else if (eventData.type === "diagnosis") {
            _appendDetailField(grid, "Status", eventData.status);
            _appendDetailField(grid, "ICD-10", eventData.icd10);
            _appendDetailField(grid, "Provider", eventData.provider);
        } else if (eventData.type === "procedure") {
            _appendDetailField(grid, "Provider", eventData.provider);
        } else if (eventData.type === "imaging") {
            _appendDetailField(grid, "Modality", eventData.modality);
            _appendDetailField(grid, "Region", eventData.body_region);
            _appendDetailField(grid, "Provider", eventData.provider);
        } else if (eventData.type === "symptom") {
            _appendDetailField(grid, "Intensity", eventData.intensity);
            _appendDetailField(grid, "Time of Day", eventData.time_of_day);
            _appendDetailField(grid, "Triggers", eventData.triggers);
        }

        if (grid.childNodes.length) {
            containerEl.appendChild(grid);
        }

        if (eventData.type === "medication") {
            _appendDetailBody(containerEl, "Reason", eventData.reason);
        } else if (eventData.type === "procedure") {
            _appendDetailBody(containerEl, "Results", eventData.notes || eventData.detail);
        } else if (eventData.type === "imaging") {
            _appendDetailBody(containerEl, "Summary", eventData.description);
            _appendDetailBody(containerEl, "Findings", eventData.findings || eventData.detail);
        } else if (eventData.type === "symptom") {
            _appendDetailBody(containerEl, "Description", eventData.description || eventData.detail);
        } else if (eventData.detail) {
            _appendDetailBody(containerEl, "Details", eventData.detail);
        }
    }

    function _appendDetailField(containerEl, label, value) {
        if (!value && value !== 0) return;

        var field = document.createElement("div");

        var labelEl = document.createElement("div");
        labelEl.className = "tl-detail-field-label";
        labelEl.textContent = label;
        field.appendChild(labelEl);

        var valueEl = document.createElement("div");
        valueEl.className = "tl-detail-field-value";
        valueEl.textContent = String(value);
        field.appendChild(valueEl);

        containerEl.appendChild(field);
    }

    function _appendDetailBody(containerEl, label, value) {
        if (!value && value !== 0) return;

        var body = document.createElement("div");
        body.className = "tl-detail-body";

        var labelEl = document.createElement("div");
        labelEl.className = "tl-detail-field-label";
        labelEl.textContent = label;
        body.appendChild(labelEl);

        var valueEl = document.createElement("div");
        valueEl.className = "tl-detail-field-value";
        valueEl.textContent = String(value);
        body.appendChild(valueEl);

        containerEl.appendChild(body);
    }

    function _clearElement(el) {
        while (el && el.firstChild) el.removeChild(el.firstChild);
    }

    function _getVisibleLanes() {
        if (currentFilter === "all") return LANES;
        return LANES.filter(function (l) { return l.type === currentFilter; });
    }

    function _buildDisplayItems(chartW) {
        var byLane = {};
        var threshold = currentFilter === "all" ? 28 : 20;
        var displayItems = [];

        filteredEvents.forEach(function (d) {
            var x = xScale(d._date);
            if (x < -24 || x > chartW + 24) return;

            var laneItems = byLane[d.type];
            if (!laneItems) {
                laneItems = [];
                byLane[d.type] = laneItems;
            }

            laneItems.push({
                event: d,
                x: x,
            });
        });

        Object.keys(byLane).forEach(function (laneType) {
            var laneItems = byLane[laneType]
                .sort(function (a, b) { return a.x - b.x; });
            var cluster = null;

            laneItems.forEach(function (item) {
                if (!cluster) {
                    cluster = _startCluster(laneType, item);
                    return;
                }

                if (item.x - cluster.maxX <= threshold) {
                    cluster.events.push(item.event);
                    cluster.sumX += item.x;
                    cluster.maxX = item.x;
                    return;
                }

                displayItems.push(_finalizeCluster(cluster));
                cluster = _startCluster(laneType, item);
            });

            if (cluster) {
                displayItems.push(_finalizeCluster(cluster));
            }
        });

        return displayItems;
    }

    function _buildLabelLayout(displayItems, chartW) {
        var byLane = {};
        var layout = {};
        var maxPerLane = currentFilter === "all"
            ? Math.max(3, Math.floor(chartW / 320))
            : Math.max(6, Math.floor(chartW / 180));

        displayItems.forEach(function (item) {
            var laneItems = byLane[item.type];
            if (!laneItems) {
                laneItems = [];
                byLane[item.type] = laneItems;
            }

            laneItems.push({
                item: item,
                x: item._x,
                text: _getLabelText(item),
            });
        });

        Object.keys(byLane).forEach(function (laneType) {
            var laneItems = byLane[laneType]
                .sort(function (a, b) { return a.x - b.x; });
            var lastRight = -Infinity;
            var shown = 0;

            laneItems.forEach(function (item) {
                if (!item.text || shown >= maxPerLane) return;

                var estWidth = Math.max(36, item.text.length * LABEL_CHAR_W);
                var left = item.x - estWidth / 2;
                var right = item.x + estWidth / 2;

                if (left < lastRight + LABEL_GAP) return;

                layout[item.item._clusterKey] = {
                    text: item.text,
                    dy: -12,
                };
                lastRight = right;
                shown += 1;
            });
        });

        return layout;
    }

    function _getLabelText(d) {
        var domain = xScale.domain();
        var spanMs = domain[1] - domain[0];
        var spanYears = spanMs / (365 * 24 * 60 * 60 * 1000);
        var maxLen;

        if (d._count > 1) {
            return d._count + " " + _typeLabel(d.type, d._count);
        }

        if (currentFilter === "all") {
            maxLen = spanYears > 4 ? 16 : 20;
        } else {
            maxLen = spanYears > 4 ? 20 : 28;
        }

        return _truncate(d.title, maxLen);
    }

    function _truncate(text, maxLen) {
        if (!text) return "";
        if (text.length <= maxLen) return text;
        return text.substring(0, maxLen - 1) + "\u2026";
    }

    function _formatDate(d) {
        if (!d || !(d instanceof Date) || isNaN(d)) return "";
        var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        return months[d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear();
    }

    function _formatDateRange(start, end) {
        if (!start) return "";
        if (!end || start.getTime() === end.getTime()) return _formatDate(start);
        return _formatDate(start) + " to " + _formatDate(end);
    }

    function _compactParts(parts) {
        return parts
            .filter(function (part) {
                return part !== null && part !== undefined && String(part).trim() !== "";
            })
            .join(" ");
    }

    function _formatReferenceRange(low, high, unit) {
        if (low == null && high == null) return "";
        var range = "";

        if (low != null && high != null) {
            range = low + " to " + high;
        } else if (low != null) {
            range = "\u2265 " + low;
        } else {
            range = "\u2264 " + high;
        }

        if (unit) range += " " + unit;
        return range;
    }

    function _nodeRadius(d) {
        if (d._count <= 1) return NODE_R;
        return Math.min(12, NODE_R + Math.sqrt(d._count) * 2);
    }

    function _typeLabel(type, count) {
        var lane = LANES[LANE_MAP[type]];
        var label = lane ? lane.label.toLowerCase() : "events";
        if (count === 1 && label.slice(-1) === "s") {
            return label.slice(0, -1);
        }
        return label;
    }

    function _startCluster(laneType, item) {
        return {
            type: laneType,
            events: [item.event],
            minX: item.x,
            maxX: item.x,
            sumX: item.x,
        };
    }

    function _finalizeCluster(cluster) {
        var first = cluster.events[0];
        var last = cluster.events[cluster.events.length - 1];
        var count = cluster.events.length;

        return {
            _clusterKey: first._timelineKey + "::" + last._timelineKey + "::" + count,
            _count: count,
            _events: cluster.events,
            _x: cluster.sumX / count,
            _date: count === 1
                ? first._date
                : new Date((first._date.getTime() + last._date.getTime()) / 2),
            _dateStart: first._date,
            _dateEnd: last._date,
            type: first.type,
            title: first.title,
            detail: first.detail,
        };
    }

    // ── Public interface ───────────────────────────────────
    return {
        init: init,
        filter: filter,
        resize: resize,
    };

})();
