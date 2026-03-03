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

    // ── State ──────────────────────────────────────────────
    var allEvents = [];
    var filteredEvents = [];
    var currentFilter = "all";
    var svg, mainG, miniG, xScale, xScaleMini, yScale;
    var tooltipEl;
    var zoom;
    var container;
    var width, height;

    // ── Public API ─────────────────────────────────────────

    function init(events, filterType) {
        allEvents = (events || []).slice();
        currentFilter = filterType || "all";

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

        _applyFilter();
        _buildChart();
    }

    function filter(type) {
        currentFilter = type;
        _applyFilter();
        _render();
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
        if (!container) return;

        // Clear previous
        while (container.firstChild) container.removeChild(container.firstChild);

        if (!filteredEvents.length) {
            var msg = document.createElement("div");
            msg.style.cssText = "color:var(--text-muted); text-align:center; padding:40px;";
            msg.textContent = "No events to display.";
            container.appendChild(msg);
            return;
        }

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
            .call(zoom);

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

        var nodes = nodesG.selectAll(".tl-node")
            .data(filteredEvents, function (d, i) { return d.date + d.type + i; });

        // Exit
        nodes.exit().remove();

        // Enter
        var enter = nodes.enter()
            .append("g")
            .attr("class", "tl-node");

        enter.append("circle")
            .attr("r", NODE_R)
            .attr("fill", function (d) {
                var lane = LANES[LANE_MAP[d.type]];
                return lane ? lane.color : "#888";
            })
            .attr("stroke", "var(--bg-primary)")
            .attr("stroke-width", 2)
            .style("cursor", "pointer");

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
            var x = xScale(d._date);
            var y = yScale(d.type);
            if (y === undefined) y = 0;
            return "translate(" + x + "," + y + ")";
        })
        .style("display", function (d) {
            var x = xScale(d._date);
            return (x < -20 || x > chartW + 20) ? "none" : null;
        });

        merged.select("circle")
            .attr("r", NODE_R)
            .on("mouseenter", function (event, d) {
                d3.select(this)
                    .transition().duration(150)
                    .attr("r", NODE_R + 3)
                    .attr("stroke-width", 3);

                _showTooltip(event, d);
            })
            .on("mouseleave", function () {
                d3.select(this)
                    .transition().duration(150)
                    .attr("r", NODE_R)
                    .attr("stroke-width", 2);

                tooltipEl.style.opacity = "0";
            });

        // D3 .text() uses textContent (safe, no XSS)
        merged.select(".tl-node-label")
            .text(function (d) {
                return _truncate(d.title, 20);
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

    function _getVisibleLanes() {
        if (currentFilter === "all") return LANES;
        return LANES.filter(function (l) { return l.type === currentFilter; });
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

    // ── Public interface ───────────────────────────────────
    return {
        init: init,
        filter: filter,
        resize: resize,
    };

})();
