/**
 * Lab Trajectory Forecasting — D3 Line Charts
 *
 * Shows lab value trends with:
 *   - Historical data points (solid dots)
 *   - Regression trend line (solid line)
 *   - Projected values (dashed line)
 *   - Confidence interval (shaded area)
 *   - Reference range (green/yellow/red bands)
 *   - Threshold crossing warnings (alert markers)
 *
 * Overlay pattern matches Snowball / Cascades / PGx.
 */

/* global d3 */

var Trajectories = {
    _overlay: null,
    _isOpen: false,
    _data: null,
    _activeIdx: 0,

    open: function() {
        if (this._isOpen) return;

        fetch("/api/trajectories")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                Trajectories._data = data;
                Trajectories._activeIdx = 0;
                Trajectories._buildOverlay(data);
            })
            .catch(function(err) {
                console.error("Trajectories fetch failed:", err);
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
        overlay.className = "traj-overlay";
        this._overlay = overlay;
        this._isOpen = true;

        // Header
        var header = document.createElement("div");
        header.className = "traj-header";

        var titleWrap = document.createElement("div");
        var title = document.createElement("div");
        title.className = "traj-title";
        title.textContent = "Lab Trajectories";
        titleWrap.appendChild(title);

        var subtitle = document.createElement("div");
        subtitle.className = "traj-subtitle";
        subtitle.textContent = "How your lab values are trending over time";
        titleWrap.appendChild(subtitle);

        var closeBtn = document.createElement("button");
        closeBtn.className = "traj-close";
        closeBtn.textContent = "\u00d7";
        closeBtn.addEventListener("click", function() { self.close(); });

        header.appendChild(titleWrap);
        header.appendChild(closeBtn);
        overlay.appendChild(header);

        // Summary bar
        var summary = data.summary || {};
        if (summary.total_tracked > 0) {
            var summaryBar = document.createElement("div");
            summaryBar.className = "traj-summary-bar";

            var tracked = document.createElement("span");
            tracked.className = "traj-summary-stat";
            tracked.textContent = summary.total_tracked + " lab" + (summary.total_tracked > 1 ? "s" : "") + " with trends";
            summaryBar.appendChild(tracked);

            if (summary.rising_count > 0) {
                var rising = document.createElement("span");
                rising.className = "traj-summary-badge traj-badge-rising";
                rising.textContent = summary.rising_count + " rising";
                summaryBar.appendChild(rising);
            }
            if (summary.falling_count > 0) {
                var falling = document.createElement("span");
                falling.className = "traj-summary-badge traj-badge-falling";
                falling.textContent = summary.falling_count + " falling";
                summaryBar.appendChild(falling);
            }
            if (summary.stable_count > 0) {
                var stab = document.createElement("span");
                stab.className = "traj-summary-badge traj-badge-stable";
                stab.textContent = summary.stable_count + " stable";
                summaryBar.appendChild(stab);
            }
            if (summary.warnings_count > 0) {
                var warns = document.createElement("span");
                warns.className = "traj-summary-badge traj-badge-warn";
                warns.textContent = summary.warnings_count + " warning" + (summary.warnings_count > 1 ? "s" : "");
                summaryBar.appendChild(warns);
            }

            overlay.appendChild(summaryBar);
        }

        // Content
        var content = document.createElement("div");
        content.className = "traj-content";

        var trajectories = data.trajectories || [];
        if (trajectories.length === 0) {
            var empty = document.createElement("div");
            empty.className = "traj-empty";
            empty.textContent = "No lab trends available. Trajectories appear when a lab test has 3 or more results over time.";
            content.appendChild(empty);
            overlay.appendChild(content);
            document.body.appendChild(overlay);
            return;
        }

        // Left panel — test list
        var leftPanel = document.createElement("div");
        leftPanel.className = "traj-left-panel";
        leftPanel.id = "traj-list";

        var listTitle = document.createElement("div");
        listTitle.className = "traj-list-title";
        listTitle.textContent = "Lab Tests";
        leftPanel.appendChild(listTitle);

        for (var i = 0; i < trajectories.length; i++) {
            (function(idx) {
                var t = trajectories[idx];
                var item = document.createElement("div");
                item.className = "traj-list-item" + (idx === 0 ? " active" : "");
                item.setAttribute("data-idx", idx);

                var nameEl = document.createElement("div");
                nameEl.className = "traj-item-name";
                nameEl.textContent = t.test_name;
                item.appendChild(nameEl);

                var metaEl = document.createElement("div");
                metaEl.className = "traj-item-meta";
                var arrow = t.trend.direction === "rising" ? "\u2191" :
                            t.trend.direction === "falling" ? "\u2193" : "\u2192";
                var warnTag = t.warnings && t.warnings.length > 0 ? " \u26a0" : "";
                metaEl.textContent = arrow + " " + t.trend.direction + " (R\u00b2=" + t.trend.r_squared + ")" + warnTag;
                item.appendChild(metaEl);

                item.addEventListener("click", function() {
                    self._selectTest(idx);
                });

                leftPanel.appendChild(item);
            })(i);
        }

        content.appendChild(leftPanel);

        // Right panel — chart
        var chartPanel = document.createElement("div");
        chartPanel.className = "traj-chart-panel";
        chartPanel.id = "traj-chart";
        content.appendChild(chartPanel);

        overlay.appendChild(content);

        // Warning detail
        var detailPanel = document.createElement("div");
        detailPanel.className = "traj-detail-panel";
        detailPanel.id = "traj-detail";
        overlay.appendChild(detailPanel);

        // Partner note
        var partnerNote = document.createElement("div");
        partnerNote.className = "traj-partner-note";

        var headline = document.createElement("div");
        headline.className = "traj-partner-headline";
        headline.textContent = "Trends tell a story your single results can\u2019t.";
        partnerNote.appendChild(headline);

        var body = document.createElement("div");
        body.className = "traj-partner-body";
        body.textContent = "A value in the normal range today may be heading toward a threshold. These projections help you and your doctor spot changes early \u2014 before they become problems.";
        partnerNote.appendChild(body);

        overlay.appendChild(partnerNote);
        document.body.appendChild(overlay);

        // Render first chart
        this._renderChart(trajectories[0]);
        this._renderDetail(trajectories[0]);
    },

    _selectTest: function(idx) {
        this._activeIdx = idx;
        var items = document.querySelectorAll(".traj-list-item");
        for (var i = 0; i < items.length; i++) {
            if (parseInt(items[i].getAttribute("data-idx")) === idx) {
                items[i].classList.add("active");
            } else {
                items[i].classList.remove("active");
            }
        }
        var t = this._data.trajectories[idx];
        this._renderChart(t);
        this._renderDetail(t);
    },

    _renderChart: function(trajectory) {
        var container = document.getElementById("traj-chart");
        if (!container) return;
        while (container.firstChild) container.removeChild(container.firstChild);

        var margin = { top: 30, right: 40, bottom: 40, left: 60 };
        var width = (container.clientWidth || 600) - margin.left - margin.right;
        var height = (container.clientHeight || 400) - margin.top - margin.bottom;

        if (width < 100 || height < 100) return;

        var svg = d3.select(container)
            .append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom);

        var g = svg.append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        var points = trajectory.data_points;
        var proj6 = trajectory.projection_6mo;
        var proj12 = trajectory.projection_12mo;
        var trendLine = trajectory.trend_line;
        var ref = trajectory.reference_range;

        // Parse dates
        var parseDate = d3.timeParse("%Y-%m-%d");
        var allDates = points.map(function(p) { return parseDate(p.date); });
        if (proj12) allDates.push(parseDate(proj12.date));
        var allValues = points.map(function(p) { return p.value; });
        if (proj12) {
            allValues.push(proj12.ci_high);
            allValues.push(proj12.ci_low);
        }
        if (ref) {
            if (ref.low != null) allValues.push(ref.low);
            if (ref.high != null) allValues.push(ref.high);
        }

        var xScale = d3.scaleTime()
            .domain(d3.extent(allDates))
            .range([0, width]);

        var yMin = d3.min(allValues) * 0.9;
        var yMax = d3.max(allValues) * 1.1;
        var yScale = d3.scaleLinear()
            .domain([yMin, yMax])
            .range([height, 0]);

        // Reference range bands
        if (ref) {
            if (ref.low != null && ref.high != null) {
                g.append("rect")
                    .attr("x", 0)
                    .attr("y", yScale(ref.high))
                    .attr("width", width)
                    .attr("height", yScale(ref.low) - yScale(ref.high))
                    .attr("fill", "rgba(92, 212, 127, 0.06)")
                    .attr("stroke", "none");
            }

            // Reference lines
            if (ref.high != null) {
                g.append("line")
                    .attr("x1", 0).attr("x2", width)
                    .attr("y1", yScale(ref.high)).attr("y2", yScale(ref.high))
                    .attr("stroke", "rgba(92, 212, 127, 0.3)")
                    .attr("stroke-dasharray", "4,4");

                g.append("text")
                    .text("High: " + ref.high)
                    .attr("x", width - 4).attr("y", yScale(ref.high) - 4)
                    .attr("text-anchor", "end")
                    .attr("font-size", "9px")
                    .attr("fill", "rgba(92, 212, 127, 0.5)");
            }
            if (ref.low != null) {
                g.append("line")
                    .attr("x1", 0).attr("x2", width)
                    .attr("y1", yScale(ref.low)).attr("y2", yScale(ref.low))
                    .attr("stroke", "rgba(92, 212, 127, 0.3)")
                    .attr("stroke-dasharray", "4,4");

                g.append("text")
                    .text("Low: " + ref.low)
                    .attr("x", width - 4).attr("y", yScale(ref.low) + 12)
                    .attr("text-anchor", "end")
                    .attr("font-size", "9px")
                    .attr("fill", "rgba(92, 212, 127, 0.5)");
            }
        }

        // Confidence interval area (projected region)
        if (proj6 && proj12) {
            var lastPt = points[points.length - 1];
            var lastDate = parseDate(lastPt.date);
            var p6Date = parseDate(proj6.date);
            var p12Date = parseDate(proj12.date);

            var ciData = [
                { date: lastDate, low: lastPt.value, high: lastPt.value },
                { date: p6Date, low: proj6.ci_low, high: proj6.ci_high },
                { date: p12Date, low: proj12.ci_low, high: proj12.ci_high },
            ];

            var area = d3.area()
                .x(function(d) { return xScale(d.date); })
                .y0(function(d) { return yScale(d.low); })
                .y1(function(d) { return yScale(d.high); });

            g.append("path")
                .datum(ciData)
                .attr("d", area)
                .attr("fill", "rgba(90, 143, 252, 0.08)")
                .attr("stroke", "none");
        }

        // Trend line (full regression line, dashed in projection zone)
        if (trendLine && trendLine.length >= 2) {
            var lastDataDate = parseDate(points[points.length - 1].date);

            // Solid part (historical)
            var tl0 = parseDate(trendLine[0].date);
            g.append("line")
                .attr("x1", xScale(tl0)).attr("y1", yScale(trendLine[0].value))
                .attr("x2", xScale(lastDataDate)).attr("y2", yScale(
                    trendLine[0].value + (trendLine[1].value - trendLine[0].value) *
                    ((lastDataDate - tl0) / (parseDate(trendLine[1].date) - tl0))
                ))
                .attr("stroke", "#5a8ffc")
                .attr("stroke-width", 1.5)
                .attr("stroke-opacity", 0.6);

            // Dashed part (projection)
            var projYAtLast = trendLine[0].value + (trendLine[1].value - trendLine[0].value) *
                ((lastDataDate - tl0) / (parseDate(trendLine[1].date) - tl0));

            g.append("line")
                .attr("x1", xScale(lastDataDate)).attr("y1", yScale(projYAtLast))
                .attr("x2", xScale(parseDate(trendLine[1].date))).attr("y2", yScale(trendLine[1].value))
                .attr("stroke", "#5a8ffc")
                .attr("stroke-width", 1.5)
                .attr("stroke-dasharray", "6,4")
                .attr("stroke-opacity", 0.5);
        }

        // Data points
        g.selectAll(".data-point")
            .data(points)
            .enter()
            .append("circle")
            .attr("cx", function(d) { return xScale(parseDate(d.date)); })
            .attr("cy", function(d) { return yScale(d.value); })
            .attr("r", 5)
            .attr("fill", "#5a8ffc")
            .attr("stroke", "#1e40af")
            .attr("stroke-width", 2);

        // Projection dots (hollow)
        if (proj6) {
            g.append("circle")
                .attr("cx", xScale(parseDate(proj6.date)))
                .attr("cy", yScale(proj6.value))
                .attr("r", 5)
                .attr("fill", "none")
                .attr("stroke", "#5a8ffc")
                .attr("stroke-width", 2)
                .attr("stroke-dasharray", "2,2");
        }
        if (proj12) {
            g.append("circle")
                .attr("cx", xScale(parseDate(proj12.date)))
                .attr("cy", yScale(proj12.value))
                .attr("r", 5)
                .attr("fill", "none")
                .attr("stroke", "#5a8ffc")
                .attr("stroke-width", 2)
                .attr("stroke-dasharray", "2,2");
        }

        // Warning markers
        var warnings = trajectory.warnings || [];
        for (var w = 0; w < warnings.length; w++) {
            var warn = warnings[w];
            if (warn.crossing_date && warn.threshold != null) {
                var wDate = parseDate(warn.crossing_date);
                if (wDate) {
                    g.append("line")
                        .attr("x1", xScale(wDate)).attr("x2", xScale(wDate))
                        .attr("y1", 0).attr("y2", height)
                        .attr("stroke", "#ef4444")
                        .attr("stroke-width", 1)
                        .attr("stroke-dasharray", "3,3")
                        .attr("stroke-opacity", 0.5);

                    g.append("text")
                        .text("\u26a0")
                        .attr("x", xScale(wDate))
                        .attr("y", 12)
                        .attr("text-anchor", "middle")
                        .attr("font-size", "14px");
                }
            }
        }

        // Axes
        g.append("g")
            .attr("transform", "translate(0," + height + ")")
            .call(d3.axisBottom(xScale).ticks(6).tickFormat(d3.timeFormat("%b %Y")))
            .selectAll("text")
            .attr("fill", "#6b7280")
            .attr("font-size", "10px");

        g.append("g")
            .call(d3.axisLeft(yScale).ticks(6))
            .selectAll("text")
            .attr("fill", "#6b7280")
            .attr("font-size", "10px");

        // Style axis lines
        g.selectAll(".domain").attr("stroke", "#374151");
        g.selectAll(".tick line").attr("stroke", "#374151");

        // Title
        svg.append("text")
            .text(trajectory.test_name + (trajectory.unit ? " (" + trajectory.unit + ")" : ""))
            .attr("x", margin.left + width / 2)
            .attr("y", 18)
            .attr("text-anchor", "middle")
            .attr("font-size", "13px")
            .attr("font-weight", "600")
            .attr("fill", "#d1d5db");
    },

    _renderDetail: function(trajectory) {
        var panel = document.getElementById("traj-detail");
        if (!panel) return;
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        var trend = trajectory.trend;
        var proj6 = trajectory.projection_6mo;
        var proj12 = trajectory.projection_12mo;
        var warnings = trajectory.warnings || [];

        // Trend summary
        var trendEl = document.createElement("div");
        trendEl.className = "traj-detail-trend";
        var arrow = trend.direction === "rising" ? "\u2191" :
                    trend.direction === "falling" ? "\u2193" : "\u2192";
        trendEl.textContent = trajectory.test_name + ": " + arrow + " " + trend.direction +
            " at " + Math.abs(trend.slope_per_month).toFixed(2) + "/month" +
            " (confidence: " + trend.confidence + ")";
        panel.appendChild(trendEl);

        // Projections
        if (proj6) {
            var p6El = document.createElement("span");
            p6El.className = "traj-detail-proj";
            p6El.textContent = "6mo: " + proj6.value + " (" + proj6.ci_low + "\u2013" + proj6.ci_high + ")";
            panel.appendChild(p6El);
        }
        if (proj12) {
            var p12El = document.createElement("span");
            p12El.className = "traj-detail-proj";
            p12El.textContent = "  12mo: " + proj12.value + " (" + proj12.ci_low + "\u2013" + proj12.ci_high + ")";
            panel.appendChild(p12El);
        }

        // Warnings
        for (var w = 0; w < warnings.length; w++) {
            var warnEl = document.createElement("div");
            warnEl.className = "traj-detail-warn";
            warnEl.textContent = "\u26a0 " + warnings[w].message;
            panel.appendChild(warnEl);
        }

        if (warnings.length === 0 && trend.direction === "stable") {
            var safeEl = document.createElement("div");
            safeEl.className = "traj-detail-safe";
            safeEl.textContent = "This value is stable over time. No concerns.";
            panel.appendChild(safeEl);
        }
    },
};
