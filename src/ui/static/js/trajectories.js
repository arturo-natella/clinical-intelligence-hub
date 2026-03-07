/**
 * Lab Trajectory Forecasting — D3 Line Charts + Treatment Bars
 *
 * Shows lab value trends with:
 *   - Historical data points (solid dots)
 *   - Regression trend line (solid line)
 *   - Projected values (dashed line)
 *   - Confidence interval (shaded area)
 *   - Reference range (green/yellow/red bands)
 *   - Threshold crossing warnings (alert markers)
 *   - Treatment bars showing active medications (Phase 1)
 *
 * Overlay pattern matches Snowball / Cascades / PGx.
 * Security: All user-facing text rendered via .textContent / escapeHtml()
 */

/* global d3 */

var Trajectories = {
    _overlay: null,
    _isOpen: false,
    _data: null,
    _treatmentData: null,
    _activeIdx: 0,

    /** Escape HTML entities for safe text insertion. */
    _escapeHtml: function(str) {
        if (!str) return "";
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    },

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
        // Use a fixed chart height so treatment bars stack below predictably
        var medCount = (trajectory.relevant_medications || []).length;
        var chartHeight = 320;
        var height = chartHeight - margin.top - margin.bottom;

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

        // Anomaly indicators — pulsing circles on anomalous data points
        var anomalies = trajectory.anomalies || [];
        var testName = trajectory.test_name;
        for (var a = 0; a < anomalies.length; a++) {
            (function(anomaly) {
                var anomDate = parseDate(anomaly.date);
                if (!anomDate) return;

                var cx = xScale(anomDate);
                var cy = yScale(anomaly.value);

                // Pulsing ring (SVG animation for reliable cross-browser behavior)
                var pulseCircle = g.append("circle")
                    .attr("class", "anomaly-point-pulse")
                    .attr("cx", cx)
                    .attr("cy", cy)
                    .attr("r", 8)
                    .attr("fill", "none")
                    .attr("stroke", anomaly.severity === "major" ? "#ef4444" : "#f97316")
                    .attr("stroke-width", 2)
                    .attr("stroke-opacity", 0.7);

                // SVG animate for pulsing effect
                var animateR = document.createElementNS("http://www.w3.org/2000/svg", "animate");
                animateR.setAttribute("attributeName", "r");
                animateR.setAttribute("values", "8;14;8");
                animateR.setAttribute("dur", "2s");
                animateR.setAttribute("repeatCount", "indefinite");
                pulseCircle.node().appendChild(animateR);

                var animateOpacity = document.createElementNS("http://www.w3.org/2000/svg", "animate");
                animateOpacity.setAttribute("attributeName", "stroke-opacity");
                animateOpacity.setAttribute("values", "0.7;0.15;0.7");
                animateOpacity.setAttribute("dur", "2s");
                animateOpacity.setAttribute("repeatCount", "indefinite");
                pulseCircle.node().appendChild(animateOpacity);

                // Static indicator circle (clickable)
                g.append("circle")
                    .attr("class", "anomaly-point")
                    .attr("cx", cx)
                    .attr("cy", cy)
                    .attr("r", 8)
                    .attr("fill", "none")
                    .attr("stroke", anomaly.severity === "major" ? "#ef4444" : "#f97316")
                    .attr("stroke-width", 2.5)
                    .attr("cursor", "pointer")
                    .on("click", function() {
                        Trajectories._openInvestigation(testName, anomaly);
                    });

                // Small "?" label above the anomaly point
                g.append("text")
                    .attr("class", "anomaly-label")
                    .text("?")
                    .attr("x", cx)
                    .attr("y", cy - 14)
                    .attr("text-anchor", "middle")
                    .attr("font-size", "11px")
                    .attr("font-weight", "700")
                    .attr("fill", anomaly.severity === "major" ? "#ef4444" : "#f97316")
                    .attr("cursor", "pointer")
                    .on("click", function() {
                        Trajectories._openInvestigation(testName, anomaly);
                    });
            })(anomalies[a]);
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

        // ── Treatment Bars (Phase 1) ────────────────────────
        this._renderTreatmentBars(container, trajectory, xScale, margin, width);
    },

    /**
     * Render medication treatment bars below the chart SVG.
     *
     * Each medication that affects this lab gets a colored bar spanning
     * its start_date → end_date, positioned using the chart's xScale.
     * Dose change ticks and start/stop event lines are overlaid.
     *
     * DESIGN: Each medication is in its own .med-group container.
     * Phase 2 will add a .side-effect-lane child inside each .med-group.
     */
    _renderTreatmentBars: function(container, trajectory, xScale, margin, chartWidth) {
        var meds = trajectory.relevant_medications || [];
        if (meds.length === 0) return;

        var parseDate = d3.timeParse("%Y-%m-%d");
        var xDomain = xScale.domain();  // [Date, Date]
        var xMin = xDomain[0];
        var xMax = xDomain[1];

        // Remove any previous treatment section in this container
        var existing = container.querySelector(".traj-treatments-section");
        if (existing) existing.parentNode.removeChild(existing);

        // Section container
        var section = document.createElement("div");
        section.className = "traj-treatments-section";

        // Section label
        var label = document.createElement("div");
        label.className = "traj-treatments-label";
        label.textContent = "TREATMENTS";
        section.appendChild(label);

        // Build each medication bar
        for (var i = 0; i < meds.length; i++) {
            var med = meds[i];
            var medGroup = this._buildMedGroup(med, parseDate, xScale, xMin, xMax, margin, chartWidth);
            if (medGroup) {
                section.appendChild(medGroup);
            }
        }

        // Append to container (after the SVG chart)
        container.appendChild(section);
    },

    /**
     * Build a single .med-group for one medication.
     * Contains: label, treatment-lane with bar + dose ticks, event lines.
     * Leaves room for an optional .side-effect-lane child (Phase 2).
     */
    _buildMedGroup: function(med, parseDate, xScale, xMin, xMax, margin, chartWidth) {
        var medName = med.name || "Unknown";
        var color = med.color || "#3b82f6";
        var startDate = med.start_date ? parseDate(med.start_date) : null;
        var endDate = med.end_date ? parseDate(med.end_date) : null;

        // If no start date, log and skip
        if (!startDate) {
            console.warn("Treatment bar skipped — no start_date for medication:", medName);
            return null;
        }

        // Clamp to chart x domain
        var barStart = startDate < xMin ? xMin : startDate;
        var barEnd = endDate ? (endDate > xMax ? xMax : endDate) : xMax;

        // If the medication doesn't overlap the chart's time range at all, skip
        if (barStart >= xMax || barEnd <= xMin) {
            return null;
        }

        var leftPx = xScale(barStart);
        var rightPx = xScale(barEnd);
        var barWidth = Math.max(rightPx - leftPx, 4); // minimum 4px so it's visible

        // .med-group container (flex column — Phase 2 side effect lane goes below)
        var group = document.createElement("div");
        group.className = "med-group";

        // Horizontal row: label + treatment lane
        var row = document.createElement("div");
        row.className = "med-group-row";

        // Medication name label
        var labelEl = document.createElement("div");
        labelEl.className = "med-group-label";
        labelEl.textContent = medName;
        row.appendChild(labelEl);

        // Treatment lane (contains the bar, positioned relative)
        var lane = document.createElement("div");
        lane.className = "treatment-lane";

        // The colored bar
        var bar = document.createElement("div");
        bar.className = "treatment-bar";
        bar.style.left = (margin.left + leftPx) + "px";
        bar.style.width = barWidth + "px";
        bar.style.backgroundColor = color;

        // Dosage text inside bar
        var dosageText = med.dosage || "";
        if (dosageText) {
            var barText = document.createElement("span");
            barText.className = "treatment-bar-text";
            barText.textContent = dosageText;
            bar.appendChild(barText);
        }

        // Dose change ticks inside bar
        var doseChanges = med.dose_changes || [];
        for (var d = 0; d < doseChanges.length; d++) {
            var dc = doseChanges[d];
            var dcDate = dc.date ? parseDate(dc.date) : null;
            if (dcDate && dcDate >= barStart && dcDate <= barEnd) {
                var tickX = xScale(dcDate) - leftPx;

                var tick = document.createElement("div");
                tick.className = "dose-tick";
                tick.style.left = tickX + "px";
                bar.appendChild(tick);

                // Tick label above
                var tickLabel = document.createElement("div");
                tickLabel.className = "dose-tick-label";
                tickLabel.style.left = tickX + "px";
                tickLabel.textContent = "\u2191 " + (dc.to_dose || "");
                bar.appendChild(tickLabel);
            }
        }

        lane.appendChild(bar);

        // Event lines (dashed vertical lines for start/stop/dose changes)
        var events = med.events || [];
        for (var e = 0; e < events.length; e++) {
            var evt = events[e];
            var evtDate = evt.date ? parseDate(evt.date) : null;
            if (evtDate && evtDate >= xMin && evtDate <= xMax) {
                var evtX = margin.left + xScale(evtDate);

                // Dashed event line
                var eventLine = document.createElement("div");
                eventLine.className = "event-line";
                eventLine.style.left = evtX + "px";
                lane.appendChild(eventLine);

                // Event flag label
                var flag = document.createElement("div");
                flag.className = "event-flag";
                flag.style.left = evtX + "px";
                flag.textContent = evt.label || evt.type || "";
                lane.appendChild(flag);
            }
        }

        row.appendChild(lane);
        group.appendChild(row);

        // ── Phase 2: Side Effect Lane ───────────────────
        var sideEffects = med.side_effects || [];
        if (sideEffects.length > 0) {
            var seLane = this._buildSideEffectLane(
                sideEffects, parseDate, xScale, xMin, xMax, margin
            );
            group.appendChild(seLane);
        }

        return group;
    },

    /**
     * Build the .side-effect-lane for a single medication.
     * Contains: label + positioned dots for each side effect episode.
     */
    _buildSideEffectLane: function(sideEffects, parseDate, xScale, xMin, xMax, margin) {
        var self = this;

        // Outer row: label + lane container
        var laneRow = document.createElement("div");
        laneRow.className = "side-effect-lane";

        // Left label
        var seLabelEl = document.createElement("div");
        seLabelEl.className = "side-effect-label";
        seLabelEl.textContent = "side effects";
        laneRow.appendChild(seLabelEl);

        // Dot container (positioned relative, same width as treatment-lane)
        var dotContainer = document.createElement("div");
        dotContainer.className = "side-effect-dot-container";

        for (var i = 0; i < sideEffects.length; i++) {
            var se = sideEffects[i];
            var epDate = se.episode_date ? parseDate(se.episode_date) : null;
            if (!epDate) {
                console.warn("Side effect dot skipped — no episode_date:", se);
                continue;
            }

            // Clamp to chart domain
            if (epDate < xMin || epDate > xMax) continue;

            var dotX = margin.left + xScale(epDate);

            // Severity class mapping
            var sevClass = "se-low";
            var sev = (se.intensity || "mid").toLowerCase();
            if (sev === "high") sevClass = "se-high";
            else if (sev === "mid" || sev === "moderate") sevClass = "se-mid";

            // Dot wrapper (for positioning)
            var dotWrap = document.createElement("div");
            dotWrap.className = "se-dot-wrap";
            dotWrap.style.left = dotX + "px";

            // Dot
            var dot = document.createElement("span");
            dot.className = "se-dot " + sevClass;
            dotWrap.appendChild(dot);

            // Label below dot
            var dotLabel = document.createElement("span");
            dotLabel.className = "se-dot-label";
            dotLabel.textContent = se.symptom_name || "";
            dotWrap.appendChild(dotLabel);

            // Tooltip on hover
            (function(seData, wrapEl) {
                wrapEl.addEventListener("mouseenter", function(evt) {
                    self._showSideEffectTooltip(evt, seData, wrapEl);
                });
                wrapEl.addEventListener("mouseleave", function() {
                    self._hideSideEffectTooltip();
                });
            })(se, dotWrap);

            dotContainer.appendChild(dotWrap);
        }

        laneRow.appendChild(dotContainer);
        return laneRow;
    },

    /**
     * Show the "Discuss with your doctor" tooltip for a side effect dot.
     */
    _showSideEffectTooltip: function(evt, seData, anchorEl) {
        this._hideSideEffectTooltip();

        var tooltip = document.createElement("div");
        tooltip.className = "se-tooltip";
        tooltip.id = "se-tooltip-active";

        // Header
        var header = document.createElement("div");
        header.className = "se-tooltip-header";
        header.textContent = "\uD83D\uDCAC Discuss with your doctor";
        tooltip.appendChild(header);

        // Detail block
        var detail = document.createElement("div");
        detail.className = "se-tooltip-detail";

        var nameRow = document.createElement("div");
        nameRow.style.fontWeight = "600";
        nameRow.textContent = this._escapeHtml(seData.symptom_name || "Symptom");
        detail.appendChild(nameRow);

        var dateRow = document.createElement("div");
        dateRow.style.cssText = "font-size:11px; color:var(--text-muted); margin-top:2px;";
        dateRow.textContent = "Date: " + (seData.episode_date || "Unknown") +
            "  |  Intensity: " + (seData.intensity || "mid").toUpperCase();
        detail.appendChild(dateRow);

        tooltip.appendChild(detail);

        // Likelihood badge
        var likelihood = seData.likelihood || "low";
        var badge = document.createElement("div");
        badge.className = "likelihood-badge lh-" + likelihood.replace("_", "-");
        badge.textContent = likelihood.toUpperCase().replace("_", " ");
        tooltip.appendChild(badge);

        // Factor checklist
        var factors = seData.factors || [];
        if (factors.length > 0) {
            var factorSection = document.createElement("div");
            factorSection.style.marginTop = "8px";
            for (var f = 0; f < factors.length; f++) {
                var factor = factors[f];
                var fRow = document.createElement("div");
                fRow.className = "factor-row";

                var icon = document.createElement("span");
                icon.className = factor.matched ? "factor-check" : "factor-x";
                icon.textContent = factor.matched ? "\u2713" : "\u2717";
                fRow.appendChild(icon);

                var fText = document.createElement("span");
                fText.textContent = " " + this._escapeHtml(factor.name);
                fRow.appendChild(fText);

                factorSection.appendChild(fRow);
            }
            tooltip.appendChild(factorSection);
        }

        // Position near the dot
        document.body.appendChild(tooltip);
        var rect = anchorEl.getBoundingClientRect();
        tooltip.style.left = rect.left + "px";
        tooltip.style.top = (rect.bottom + 6) + "px";

        // Ensure tooltip stays on screen
        requestAnimationFrame(function() {
            var ttRect = tooltip.getBoundingClientRect();
            if (ttRect.right > window.innerWidth - 10) {
                tooltip.style.left = (window.innerWidth - ttRect.width - 10) + "px";
            }
            if (ttRect.bottom > window.innerHeight - 10) {
                tooltip.style.top = (rect.top - ttRect.height - 6) + "px";
            }
        });
    },

    _hideSideEffectTooltip: function() {
        var existing = document.getElementById("se-tooltip-active");
        if (existing && existing.parentNode) {
            existing.parentNode.removeChild(existing);
        }
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

    // ── Anomaly Investigation ────────────────────────────────

    _openInvestigation: function(testName, anomaly) {
        // Remove any existing investigation panel (only one at a time)
        var existing = document.querySelector(".investigation-panel");
        if (existing) {
            existing.parentNode.removeChild(existing);
        }

        // Build the panel container
        var panel = document.createElement("div");
        panel.className = "investigation-panel";

        // Show loading state
        var loading = document.createElement("div");
        loading.className = "investigation-loading";
        loading.textContent = "Investigating what happened before this result\u2026";
        panel.appendChild(loading);

        // Insert panel after the chart panel
        var chartPanel = document.getElementById("traj-chart");
        if (chartPanel && chartPanel.parentNode) {
            chartPanel.parentNode.insertBefore(panel, chartPanel.nextSibling);
        } else {
            // Fallback: append to the overlay content area
            var content = document.querySelector(".traj-content");
            if (content) {
                content.appendChild(panel);
            } else {
                console.warn("Could not find chart panel or content area for investigation panel");
                return;
            }
        }

        // Fetch investigation data
        fetch("/api/trajectories/investigate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                test_name: testName,
                anomaly_date: anomaly.date
            })
        })
        .then(function(r) {
            if (!r.ok) {
                throw new Error("Investigation request failed: " + r.status);
            }
            return r.json();
        })
        .then(function(data) {
            Trajectories._renderInvestigationPanel(panel, data, anomaly);
        })
        .catch(function(err) {
            console.warn("Investigation fetch failed:", err);
            while (panel.firstChild) panel.removeChild(panel.firstChild);
            var errEl = document.createElement("div");
            errEl.className = "investigation-loading";
            errEl.textContent = "Could not load investigation data. Please try again.";
            panel.appendChild(errEl);
        });
    },

    _renderInvestigationPanel: function(panel, data, anomaly) {
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        // ── Header ──
        var header = document.createElement("div");
        header.className = "investigation-header";

        var iconEl = document.createElement("span");
        iconEl.className = "investigation-icon";
        iconEl.textContent = "\uD83D\uDD0D"; // magnifying glass emoji
        header.appendChild(iconEl);

        var titleWrap = document.createElement("div");

        var titleEl = document.createElement("div");
        titleEl.className = "investigation-title";
        titleEl.textContent = "What Happened Here?";
        titleWrap.appendChild(titleEl);

        var subtitleEl = document.createElement("div");
        subtitleEl.className = "investigation-subtitle";
        var subtitleText = "";
        if (anomaly.expected != null && anomaly.value != null) {
            subtitleText = "Expected ~" + anomaly.expected + " but got " +
                anomaly.value + " (" + anomaly.direction + ", " +
                anomaly.severity + ")";
        } else if (anomaly.value != null) {
            subtitleText = "Value: " + anomaly.value + " (" +
                anomaly.direction + ", " + anomaly.severity + ")";
        }
        subtitleEl.textContent = subtitleText;
        titleWrap.appendChild(subtitleEl);

        header.appendChild(titleWrap);

        // Close button
        var closeBtn = document.createElement("button");
        closeBtn.className = "traj-close";
        closeBtn.textContent = "\u00d7";
        closeBtn.style.marginLeft = "auto";
        closeBtn.addEventListener("click", function() {
            if (panel.parentNode) panel.parentNode.removeChild(panel);
        });
        header.appendChild(closeBtn);

        panel.appendChild(header);

        // ── Window info ──
        var window_ = data.window || {};
        if (window_.start_date && window_.end_date) {
            var windowInfo = document.createElement("div");
            windowInfo.className = "investigation-window";
            windowInfo.textContent = "Investigation window: " +
                window_.start_date + " \u2014 " + window_.end_date +
                " (" + window_.days + " days)";
            panel.appendChild(windowInfo);
        }

        // ── Event source groups ──
        var events = data.events_by_source || {};

        // Medical Records
        var medRecords = events.medical_records || [];
        if (medRecords.length > 0) {
            panel.appendChild(
                this._buildEventSourceGroup(
                    "\uD83D\uDCCB FROM YOUR MEDICAL RECORDS",
                    medRecords,
                    "medical"
                )
            );
        }

        // Medication Changes
        var medChanges = events.medication_changes || [];
        if (medChanges.length > 0) {
            panel.appendChild(
                this._buildEventSourceGroup(
                    "\uD83D\uDC8A MEDICATION CHANGES",
                    medChanges,
                    "medication"
                )
            );
        }

        // Symptom Reports
        var symptoms = events.symptom_reports || [];
        if (symptoms.length > 0) {
            panel.appendChild(
                this._buildEventSourceGroup(
                    "\uD83D\uDCDD SYMPTOM TRACKER",
                    symptoms,
                    "symptom"
                )
            );
        }

        // No events found message
        if (data.event_count === 0) {
            var noEvents = document.createElement("div");
            noEvents.className = "investigation-window";
            noEvents.style.textAlign = "center";
            noEvents.style.padding = "16px";
            noEvents.textContent = "No recorded events found in this window. " +
                "Unreported changes (diet, stress, missed doses) may explain this result.";
            panel.appendChild(noEvents);
        }

        // ── Correlation Summary ──
        var summary = data.correlation_summary || {};
        if (summary.discuss_because || summary.how_to_bring_up) {
            var summaryBox = document.createElement("div");
            summaryBox.className = "investigation-summary";

            var summaryTitle = document.createElement("div");
            summaryTitle.className = "investigation-summary-title";
            summaryTitle.textContent = "DISCUSS WITH YOUR DOCTOR";
            summaryBox.appendChild(summaryTitle);

            if (summary.discuss_because) {
                var summaryText = document.createElement("div");
                summaryText.className = "investigation-summary-text";
                summaryText.textContent = summary.discuss_because;
                summaryBox.appendChild(summaryText);
            }

            if (summary.how_to_bring_up) {
                var convoEl = document.createElement("div");
                convoEl.className = "investigation-conversation";
                convoEl.textContent = "\"" + summary.how_to_bring_up + "\"";
                summaryBox.appendChild(convoEl);
            }

            panel.appendChild(summaryBox);
        }
    },

    _buildEventSourceGroup: function(headerText, events, eventType) {
        var group = document.createElement("div");
        group.className = "event-source-group";

        var headerEl = document.createElement("div");
        headerEl.className = "event-source-header";
        headerEl.textContent = headerText;
        group.appendChild(headerEl);

        for (var i = 0; i < events.length; i++) {
            var evt = events[i];
            var row = document.createElement("div");
            row.className = "event-row";

            var dateCol = document.createElement("div");
            dateCol.className = "event-date";
            dateCol.textContent = evt.date || "";
            row.appendChild(dateCol);

            var descCol = document.createElement("div");
            descCol.className = "event-desc-col";

            var desc = document.createElement("div");
            desc.className = "event-desc";

            if (eventType === "medical") {
                desc.textContent = evt.description || evt.title || "";
            } else if (eventType === "medication") {
                desc.textContent = evt.detail || "";
            } else if (eventType === "symptom") {
                var symText = (evt.symptom_name || "") +
                    (evt.intensity ? " (" + evt.intensity + ")" : "") +
                    (evt.description ? " \u2014 " + evt.description : "");
                desc.textContent = symText;
            }
            descCol.appendChild(desc);

            // Source tag (provenance)
            var prov = evt.provenance || {};
            var sourceText = "";
            if (prov.source_file) {
                sourceText = "Source: " + prov.source_file;
                if (prov.source_page) {
                    sourceText += ", p." + prov.source_page;
                }
            } else if (prov.provider) {
                sourceText = "Provider: " + prov.provider;
            } else if (prov.prescriber) {
                sourceText = "Prescriber: " + prov.prescriber;
            }

            if (sourceText) {
                var sourceTag = document.createElement("div");
                sourceTag.className = "event-source-tag";
                sourceTag.textContent = sourceText;
                descCol.appendChild(sourceTag);
            }

            row.appendChild(descCol);
            group.appendChild(row);
        }

        return group;
    },

    // ── Treatment Response Rendering (Phase 3) ───────────────

    _loadTreatmentResponse: function() {
        fetch("/api/treatment-response")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data && !data.error) {
                    Trajectories._treatmentData = data;
                    Trajectories._renderTreatmentPanel(data);
                } else {
                    console.warn("Treatment response returned error or empty:", data);
                }
            })
            .catch(function(err) {
                console.warn("Treatment response fetch failed:", err);
            });
    },

    _renderTreatmentPanel: function(data) {
        var panel = document.getElementById("traj-treatment");
        if (!panel) return;
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        var responses = data.medication_responses || [];
        if (responses.length === 0) return;

        var sectionTitle = document.createElement("div");
        sectionTitle.className = "traj-treatment-title";
        sectionTitle.textContent = "Treatment Response \u2014 Discuss with your doctor";
        panel.appendChild(sectionTitle);

        for (var m = 0; m < responses.length; m++) {
            var resp = responses[m];
            var medGroup = document.createElement("div");
            medGroup.className = "med-group";

            var medHeading = document.createElement("div");
            medHeading.className = "med-group-heading";
            medHeading.textContent = resp.medication_name + (resp.dosage ? " " + resp.dosage : "");
            medGroup.appendChild(medHeading);

            var summaryBox = document.createElement("div");
            summaryBox.className = "response-summary";

            var row = document.createElement("div");
            row.className = "response-row";

            // Lab Effectiveness column
            var labCol = document.createElement("div");
            labCol.className = "response-col";
            var labLabel = document.createElement("div");
            labLabel.className = "response-label";
            labLabel.textContent = "Lab Effectiveness";
            labCol.appendChild(labLabel);

            var labs = resp.lab_effectiveness || [];
            if (labs.length === 0) {
                var noLab = document.createElement("div");
                noLab.className = "response-item";
                noLab.textContent = "No relevant lab data available";
                labCol.appendChild(noLab);
            } else {
                for (var l = 0; l < labs.length; l++) {
                    var lab = labs[l];
                    var labItem = document.createElement("div");
                    var assessment = lab.assessment || "no baseline";
                    if (assessment === "improved") {
                        labItem.className = "response-item response-good";
                        labItem.textContent = "\u2713 " + lab.lab_name;
                        if (lab.baseline && lab.current) labItem.textContent += " improved " + lab.baseline.value + " \u2192 " + lab.current.value;
                    } else if (assessment === "stable") {
                        labItem.className = "response-item response-warn";
                        labItem.textContent = "\u25cb " + lab.lab_name;
                        if (lab.current) labItem.textContent += " stable at " + lab.current.value;
                    } else if (assessment === "worsened") {
                        labItem.className = "response-item response-bad";
                        labItem.textContent = "\u25cf " + lab.lab_name;
                        if (lab.baseline && lab.current) labItem.textContent += " worsened " + lab.baseline.value + " \u2192 " + lab.current.value;
                    } else {
                        labItem.className = "response-item";
                        labItem.textContent = lab.lab_name;
                        if (lab.current) labItem.textContent += " at " + lab.current.value + " (no baseline)";
                    }
                    labCol.appendChild(labItem);
                }
            }
            row.appendChild(labCol);

            // Tolerability column
            var tolCol = document.createElement("div");
            tolCol.className = "response-col";
            var tolLabel = document.createElement("div");
            tolLabel.className = "response-label";
            tolLabel.textContent = "Tolerability";
            tolCol.appendChild(tolLabel);

            var tol = resp.tolerability || {};
            var totalEps = tol.total_episodes || 0;
            if (totalEps === 0) {
                var noEps = document.createElement("div");
                noEps.className = "response-item response-good";
                noEps.textContent = "No reported side effects";
                tolCol.appendChild(noEps);
            } else {
                var epsItem = document.createElement("div");
                epsItem.className = "response-item";
                epsItem.textContent = totalEps + " reported episode" + (totalEps !== 1 ? "s" : "");
                tolCol.appendChild(epsItem);

                var breakdown = tol.intensity_breakdown || {};
                var bParts = [];
                if (breakdown.high) bParts.push(breakdown.high + " severe");
                if (breakdown.mid) bParts.push(breakdown.mid + " moderate");
                if (breakdown.low) bParts.push(breakdown.low + " mild");
                if (bParts.length > 0) {
                    var bItem = document.createElement("div");
                    bItem.className = "response-item";
                    bItem.textContent = bParts.join(", ");
                    tolCol.appendChild(bItem);
                }

                var trend = tol.intensity_trend || "";
                if (trend && trend !== "no data" && trend !== "insufficient data") {
                    var trendItem = document.createElement("div");
                    trendItem.className = trend === "getting worse" ? "response-item response-bad" :
                        trend === "improving" ? "response-item response-good" : "response-item response-warn";
                    trendItem.textContent = "Trend: " + trend;
                    tolCol.appendChild(trendItem);
                }

                var rating = tol.rating || "unknown";
                var ratingItem = document.createElement("div");
                ratingItem.className = rating === "good" ? "response-item response-good" :
                    rating === "fair" ? "response-item response-warn" :
                    rating === "poor" ? "response-item response-bad" : "response-item";
                ratingItem.textContent = "Overall: " + rating + " tolerability";
                tolCol.appendChild(ratingItem);
            }
            row.appendChild(tolCol);
            summaryBox.appendChild(row);

            // Conversation guide
            var guide = resp.conversation_guide || {};
            if (guide.discuss_because) {
                var guideWrap = document.createElement("div");
                guideWrap.className = "response-guide";
                var guideText = document.createElement("div");
                guideText.className = "response-guide-text";
                guideText.textContent = guide.discuss_because;
                guideWrap.appendChild(guideText);
                summaryBox.appendChild(guideWrap);
            }

            medGroup.appendChild(summaryBox);
            panel.appendChild(medGroup);
        }
    },
};

/* ══════════════════════════════════════════════════════════
   Drug-Drug Interaction Timeline — Overlay Module
   ══════════════════════════════════════════════════════════

   Fetches interaction overlap zones from /api/interaction-timeline
   and renders them as clickable overlays on a medication timeline.
   Each zone is color-coded by severity. Clicking opens a detail
   panel with interaction description, symptoms, and PGx context.

   Security: All user content rendered via .textContent or _escHtml().
   ══════════════════════════════════════════════════════════ */

var InteractionTimeline = {
    _overlay: null,
    _isOpen: false,
    _data: null,
    _detailPanel: null,

    open: function() {
        if (this._isOpen) return;

        fetch("/api/interaction-timeline")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    console.error("InteractionTimeline error:", data.error);
                    return;
                }
                InteractionTimeline._data = data;
                InteractionTimeline._buildOverlay(data);
            })
            .catch(function(err) {
                console.error("InteractionTimeline fetch failed:", err);
            });
    },

    close: function() {
        InteractionTimeline._closeDetail();
        if (this._overlay && this._overlay.parentNode) {
            this._overlay.parentNode.removeChild(this._overlay);
        }
        this._overlay = null;
        this._isOpen = false;
    },

    _escHtml: function(text) {
        if (!text) return "";
        var el = document.createElement("span");
        el.textContent = String(text);
        return el.innerHTML;
    },

    _buildOverlay: function(data) {
        var self = this;
        var zones = data.overlap_zones || [];
        var pgxFlags = data.pharmacogenomic_flags || [];

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
        title.textContent = "Drug Interaction Timeline";
        titleWrap.appendChild(title);

        var subtitle = document.createElement("div");
        subtitle.className = "traj-subtitle";
        subtitle.textContent = "Overlapping medications with known interactions";
        titleWrap.appendChild(subtitle);

        var closeBtn = document.createElement("button");
        closeBtn.className = "traj-close";
        closeBtn.textContent = "\u00d7";
        closeBtn.addEventListener("click", function() { self.close(); });

        header.appendChild(titleWrap);
        header.appendChild(closeBtn);
        overlay.appendChild(header);

        // Summary bar
        if (data.interaction_summary) {
            var summaryBar = document.createElement("div");
            summaryBar.className = "traj-summary-bar";

            var summaryText = document.createElement("span");
            summaryText.className = "traj-summary-stat";
            summaryText.textContent = data.interaction_summary;
            summaryBar.appendChild(summaryText);

            // Severity badges
            var critCount = 0, highCount = 0, modCount = 0, activeCount = 0;
            for (var s = 0; s < zones.length; s++) {
                var sev = zones[s].interaction.severity;
                if (sev === "critical") critCount++;
                else if (sev === "high") highCount++;
                else if (sev === "moderate") modCount++;
                if (zones[s].is_active) activeCount++;
            }

            if (critCount > 0) {
                var critBadge = document.createElement("span");
                critBadge.className = "traj-summary-badge traj-badge-rising";
                critBadge.textContent = critCount + " critical";
                summaryBar.appendChild(critBadge);
            }
            if (highCount > 0) {
                var highBadge = document.createElement("span");
                highBadge.className = "traj-summary-badge traj-badge-warn";
                highBadge.textContent = highCount + " high";
                summaryBar.appendChild(highBadge);
            }
            if (activeCount > 0) {
                var activeBadge = document.createElement("span");
                activeBadge.className = "traj-summary-badge traj-badge-falling";
                activeBadge.textContent = activeCount + " active now";
                summaryBar.appendChild(activeBadge);
            }

            overlay.appendChild(summaryBar);
        }

        // Content area
        var content = document.createElement("div");
        content.className = "traj-content";
        content.style.flexDirection = "column";

        if (zones.length === 0) {
            var empty = document.createElement("div");
            empty.className = "traj-empty";
            empty.textContent = "No overlapping medications with known interactions were found. This is good news!";
            content.appendChild(empty);
            overlay.appendChild(content);
            document.body.appendChild(overlay);
            return;
        }

        // Render the medication timeline with interaction zones
        var timelineContainer = document.createElement("div");
        timelineContainer.className = "interaction-timeline-container";
        timelineContainer.style.padding = "16px";
        timelineContainer.style.overflowX = "auto";

        this._renderTimeline(timelineContainer, zones, pgxFlags);
        content.appendChild(timelineContainer);

        // Zone list (clickable cards)
        var zoneList = document.createElement("div");
        zoneList.style.padding = "0 16px 16px";

        var listTitle = document.createElement("div");
        listTitle.className = "traj-list-title";
        listTitle.textContent = "Interaction Details";
        listTitle.style.marginBottom = "8px";
        zoneList.appendChild(listTitle);

        for (var z = 0; z < zones.length; z++) {
            (function(idx) {
                var zone = zones[idx];
                var card = self._buildZoneCard(zone, idx);
                card.addEventListener("click", function() {
                    self._showDetail(zone);
                });
                zoneList.appendChild(card);
            })(z);
        }

        content.appendChild(zoneList);
        overlay.appendChild(content);

        // Partner note
        var partnerNote = document.createElement("div");
        partnerNote.className = "traj-partner-note";

        var headline = document.createElement("div");
        headline.className = "traj-partner-headline";
        headline.textContent = "Discuss with your doctor before making changes.";
        partnerNote.appendChild(headline);

        var body = document.createElement("div");
        body.className = "traj-partner-body";
        body.textContent = "Drug interactions do not always mean you should stop a medication. Many interactions are manageable with monitoring. Bring this timeline to your next appointment so your doctor can review these overlaps with you.";
        partnerNote.appendChild(body);

        overlay.appendChild(partnerNote);
        document.body.appendChild(overlay);
    },

    _renderTimeline: function(container, zones, pgxFlags) {
        /* Renders a horizontal medication bar chart with interaction zones.
           Each unique medication gets a horizontal bar on the time axis.
           Interaction zones are shaded overlays spanning both bars. */

        if (typeof d3 === "undefined") {
            container.textContent = "D3.js required for timeline visualization";
            console.error("InteractionTimeline: d3 not available");
            return;
        }

        // Collect all unique medications and their date ranges
        var medMap = {};
        for (var z = 0; z < zones.length; z++) {
            var zone = zones[z];
            var parseD = d3.timeParse("%Y-%m-%d");

            var meds = [
                { name: zone.med_a, start: zone.med_a_start, end: zone.med_a_end },
                { name: zone.med_b, start: zone.med_b_start, end: zone.med_b_end },
            ];
            for (var m = 0; m < meds.length; m++) {
                var med = meds[m];
                if (!medMap[med.name]) {
                    medMap[med.name] = { start: parseD(med.start), end: parseD(med.end) };
                } else {
                    var s = parseD(med.start);
                    var e = parseD(med.end);
                    if (s < medMap[med.name].start) medMap[med.name].start = s;
                    if (e > medMap[med.name].end) medMap[med.name].end = e;
                }
            }
        }

        var medNames = Object.keys(medMap);
        if (medNames.length === 0) return;

        var margin = { top: 30, right: 30, bottom: 30, left: 140 };
        var barHeight = 28;
        var barGap = 10;
        var pgxLaneH = 20;

        // Determine if any meds have PGx flags
        var medHasPgx = {};
        for (var p = 0; p < pgxFlags.length; p++) {
            var drug = pgxFlags[p].drug;
            for (var mn = 0; mn < medNames.length; mn++) {
                if (drug.toLowerCase().indexOf(medNames[mn].toLowerCase()) >= 0 ||
                    medNames[mn].toLowerCase().indexOf(drug.toLowerCase()) >= 0) {
                    medHasPgx[medNames[mn]] = pgxFlags[p];
                }
            }
        }

        var totalLaneH = barHeight + barGap;
        var pgxCount = Object.keys(medHasPgx).length;
        var height = medNames.length * totalLaneH + pgxCount * (pgxLaneH + 2);
        var width = Math.max((container.clientWidth || 600) - margin.left - margin.right, 400);

        // Compute global time extent
        var allDates = [];
        for (var k in medMap) {
            allDates.push(medMap[k].start, medMap[k].end);
        }

        var xScale = d3.scaleTime()
            .domain(d3.extent(allDates))
            .range([0, width]);

        var svg = d3.select(container)
            .append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom);

        var g = svg.append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        // Draw medication bars
        var yOffset = 0;
        var medY = {};  // maps med name to y center for zone drawing

        for (var i = 0; i < medNames.length; i++) {
            var name = medNames[i];
            var med = medMap[name];

            var x1 = xScale(med.start);
            var x2 = xScale(med.end);
            var barY = yOffset;

            medY[name] = barY + barHeight / 2;

            // Treatment bar
            g.append("rect")
                .attr("class", "treatment-bar")
                .attr("x", x1)
                .attr("y", barY)
                .attr("width", Math.max(x2 - x1, 2))
                .attr("height", barHeight)
                .attr("rx", 4)
                .attr("fill", "rgba(90, 143, 252, 0.25)")
                .attr("stroke", "rgba(90, 143, 252, 0.5)")
                .attr("stroke-width", 1);

            // Label
            g.append("text")
                .text(name)
                .attr("x", -8)
                .attr("y", barY + barHeight / 2 + 4)
                .attr("text-anchor", "end")
                .attr("font-size", "12px")
                .attr("font-weight", "500")
                .attr("fill", "#d1d5db");

            yOffset += totalLaneH;

            // PGx flag bar (if applicable)
            if (medHasPgx[name]) {
                var pgx = medHasPgx[name];
                var pgxX1 = xScale(med.start);
                var pgxX2 = xScale(med.end);

                g.append("rect")
                    .attr("class", "pgx-flag-marker")
                    .attr("x", pgxX1)
                    .attr("y", yOffset - barGap)
                    .attr("width", Math.max(pgxX2 - pgxX1, 2))
                    .attr("height", pgxLaneH)
                    .attr("rx", 3)
                    .attr("fill", "rgba(240, 197, 80, 0.08)")
                    .attr("stroke", "#f0c550")
                    .attr("stroke-width", 1)
                    .attr("stroke-dasharray", "4,3");

                g.append("text")
                    .text(pgx.gene + " " + (pgx.variant || pgx.phenotype || ""))
                    .attr("x", pgxX1 + 6)
                    .attr("y", yOffset - barGap + pgxLaneH / 2 + 4)
                    .attr("font-size", "10px")
                    .attr("fill", "#f0c550");

                yOffset += pgxLaneH + 2;
            }
        }

        // Draw interaction zone overlays
        var severityColors = {
            critical: { bg: "rgba(239,68,68,0.2)",  border: "rgba(239,68,68,0.4)" },
            high:     { bg: "rgba(249,115,22,0.2)",  border: "rgba(249,115,22,0.4)" },
            moderate: { bg: "rgba(234,179,8,0.2)",   border: "rgba(234,179,8,0.4)" },
            low:      { bg: "rgba(107,114,128,0.15)", border: "rgba(107,114,128,0.3)" },
        };

        var self = this;
        var parseDate = d3.timeParse("%Y-%m-%d");

        for (var zi = 0; zi < zones.length; zi++) {
            (function(zone) {
                var oStart = parseDate(zone.overlap_start);
                var oEnd = parseDate(zone.overlap_end);
                if (!oStart || !oEnd) return;

                var yA = medY[zone.med_a];
                var yB = medY[zone.med_b];
                if (yA == null || yB == null) return;

                var sev = zone.interaction.severity || "moderate";
                var colors = severityColors[sev] || severityColors.moderate;

                var zoneTop = Math.min(yA, yB) - barHeight / 2;
                var zoneBottom = Math.max(yA, yB) + barHeight / 2;

                g.append("rect")
                    .attr("class", "interaction-zone interaction-zone-" + sev)
                    .attr("x", xScale(oStart))
                    .attr("y", zoneTop)
                    .attr("width", Math.max(xScale(oEnd) - xScale(oStart), 2))
                    .attr("height", zoneBottom - zoneTop)
                    .attr("rx", 4)
                    .attr("fill", colors.bg)
                    .attr("stroke", colors.border)
                    .attr("stroke-width", 1)
                    .attr("cursor", "pointer")
                    .on("click", function() {
                        self._showDetail(zone);
                    });
            })(zones[zi]);
        }

        // Time axis
        g.append("g")
            .attr("transform", "translate(0," + yOffset + ")")
            .call(d3.axisBottom(xScale).ticks(6).tickFormat(d3.timeFormat("%b %Y")))
            .selectAll("text")
            .attr("fill", "#6b7280")
            .attr("font-size", "10px");

        g.selectAll(".domain").attr("stroke", "#374151");
        g.selectAll(".tick line").attr("stroke", "#374151");

        // Title
        svg.append("text")
            .text("Medication Overlap Timeline")
            .attr("x", margin.left + width / 2)
            .attr("y", 18)
            .attr("text-anchor", "middle")
            .attr("font-size", "13px")
            .attr("font-weight", "600")
            .attr("fill", "#d1d5db");
    },

    _buildZoneCard: function(zone, idx) {
        var sev = zone.interaction.severity || "moderate";

        var card = document.createElement("div");
        card.className = "interaction-zone-card";
        card.style.cursor = "pointer";
        card.style.padding = "12px";
        card.style.marginBottom = "8px";
        card.style.borderRadius = "8px";
        card.style.background = "var(--bg-raised, #1f1f1f)";
        card.style.border = "1px solid var(--border-muted, #333)";

        var header = document.createElement("div");
        header.style.display = "flex";
        header.style.alignItems = "center";
        header.style.gap = "8px";
        header.style.marginBottom = "4px";

        var badge = document.createElement("span");
        badge.className = "interaction-severity interaction-zone-" + sev;
        badge.textContent = sev.charAt(0).toUpperCase() + sev.slice(1);
        header.appendChild(badge);

        var title = document.createElement("span");
        title.style.fontWeight = "600";
        title.style.fontSize = "13px";
        title.style.color = "var(--text-primary)";
        title.textContent = zone.med_a + " + " + zone.med_b;
        header.appendChild(title);

        if (zone.is_active) {
            var activeDot = document.createElement("span");
            activeDot.style.width = "6px";
            activeDot.style.height = "6px";
            activeDot.style.borderRadius = "50%";
            activeDot.style.background = "#ef4444";
            activeDot.style.display = "inline-block";
            activeDot.title = "Currently active overlap";
            header.appendChild(activeDot);
        }

        card.appendChild(header);

        var desc = document.createElement("div");
        desc.style.fontSize = "12px";
        desc.style.color = "var(--text-secondary)";
        desc.style.marginTop = "4px";
        var descText = zone.duration_days + " days overlap";
        if (zone.symptoms_during && zone.symptoms_during.length > 0) {
            descText += " \u2022 " + zone.symptoms_during.length + " symptom" +
                (zone.symptoms_during.length > 1 ? "s" : "") + " during period";
        }
        if (zone.pgx_flags && zone.pgx_flags.length > 0) {
            descText += " \u2022 PGx flag";
        }
        desc.textContent = descText;
        card.appendChild(desc);

        return card;
    },

    _showDetail: function(zone) {
        this._closeDetail();

        var self = this;
        var sev = zone.interaction.severity || "moderate";

        // Backdrop
        var backdrop = document.createElement("div");
        backdrop.className = "interaction-detail-backdrop";
        backdrop.style.position = "fixed";
        backdrop.style.top = "0";
        backdrop.style.left = "0";
        backdrop.style.width = "100%";
        backdrop.style.height = "100%";
        backdrop.style.background = "rgba(0,0,0,0.5)";
        backdrop.style.zIndex = "999";
        backdrop.addEventListener("click", function() { self._closeDetail(); });

        var panel = document.createElement("div");
        panel.className = "interaction-detail-panel";

        // Close button
        var closeBtn = document.createElement("button");
        closeBtn.style.position = "absolute";
        closeBtn.style.top = "12px";
        closeBtn.style.right = "12px";
        closeBtn.style.background = "transparent";
        closeBtn.style.border = "none";
        closeBtn.style.color = "var(--text-secondary)";
        closeBtn.style.fontSize = "20px";
        closeBtn.style.cursor = "pointer";
        closeBtn.textContent = "\u00d7";
        closeBtn.addEventListener("click", function() { self._closeDetail(); });
        panel.appendChild(closeBtn);

        // Title
        var h4 = document.createElement("h4");
        h4.style.margin = "0 0 8px 0";
        h4.style.fontSize = "16px";
        h4.style.fontWeight = "600";
        h4.style.color = "var(--text-primary, #f5f5f5)";
        h4.textContent = "Drug Interaction: " + zone.med_a + " + " + zone.med_b;
        panel.appendChild(h4);

        // Severity badge
        var sevBadge = document.createElement("div");
        sevBadge.className = "interaction-severity interaction-zone-" + sev;
        sevBadge.textContent = sev.charAt(0).toUpperCase() + sev.slice(1) + " Severity";
        panel.appendChild(sevBadge);

        // Description
        var descP = document.createElement("p");
        descP.className = "interaction-desc";
        descP.textContent = zone.interaction.description || "No description available.";
        panel.appendChild(descP);

        // Mechanism
        if (zone.interaction.mechanism) {
            var mechP = document.createElement("p");
            mechP.className = "interaction-desc";
            mechP.style.fontStyle = "italic";
            mechP.textContent = "Mechanism: " + zone.interaction.mechanism;
            panel.appendChild(mechP);
        }

        // Management
        if (zone.interaction.management) {
            var mgmtP = document.createElement("p");
            mgmtP.className = "interaction-desc";
            mgmtP.textContent = "Management: " + zone.interaction.management;
            panel.appendChild(mgmtP);
        }

        // Overlap info
        var overlapInfo = document.createElement("div");
        overlapInfo.className = "interaction-overlap-info";
        overlapInfo.textContent = "Overlap: " + zone.overlap_start + " \u2014 " +
            (zone.is_active ? "Present" : zone.overlap_end) +
            " (" + zone.duration_days + " days)";
        panel.appendChild(overlapInfo);

        // Symptoms during overlap
        if (zone.symptoms_during && zone.symptoms_during.length > 0) {
            var sympH5 = document.createElement("h5");
            sympH5.style.margin = "16px 0 8px";
            sympH5.style.fontSize = "13px";
            sympH5.style.fontWeight = "600";
            sympH5.style.color = "var(--text-primary)";
            sympH5.textContent = "Symptoms During Overlap";
            panel.appendChild(sympH5);

            for (var si = 0; si < zone.symptoms_during.length; si++) {
                var symp = zone.symptoms_during[si];
                var sympDiv = document.createElement("div");
                sympDiv.className = "interaction-symptom";
                sympDiv.textContent = symp.symptom_name + " \u2014 " +
                    symp.intensity + " \u2014 " + symp.episode_date;
                panel.appendChild(sympDiv);
            }
        }

        // PGx flags
        if (zone.pgx_flags && zone.pgx_flags.length > 0) {
            var pgxH5 = document.createElement("h5");
            pgxH5.style.margin = "16px 0 8px";
            pgxH5.style.fontSize = "13px";
            pgxH5.style.fontWeight = "600";
            pgxH5.style.color = "var(--text-primary)";
            pgxH5.textContent = "Genetic Context";
            panel.appendChild(pgxH5);

            for (var pi = 0; pi < zone.pgx_flags.length; pi++) {
                var pgx = zone.pgx_flags[pi];
                var pgxDiv = document.createElement("div");
                pgxDiv.className = "pgx-flag-label";
                pgxDiv.style.marginBottom = "4px";
                pgxDiv.textContent = pgx.gene + " " + (pgx.variant || "") +
                    " \u2014 " + (pgx.phenotype || "") +
                    " \u2014 affects " + pgx.drug + " processing";
                panel.appendChild(pgxDiv);
            }
        }

        // Source
        var srcDiv = document.createElement("div");
        srcDiv.className = "interaction-source";
        srcDiv.textContent = "Source: " + (zone.interaction.source || "Clinical Knowledge Base");
        panel.appendChild(srcDiv);

        // Doctor discussion guide
        var discuss = document.createElement("div");
        discuss.className = "interaction-discuss";
        var discussText = "Discuss with your doctor: you are taking " +
            zone.med_a + " and " + zone.med_b + " simultaneously";
        if (zone.is_active) {
            discussText += " and they currently overlap";
        }
        discussText += ". Your doctor should review whether this combination is appropriate for your situation.";
        discuss.textContent = discussText;
        panel.appendChild(discuss);

        document.body.appendChild(backdrop);
        document.body.appendChild(panel);
        this._detailPanel = { panel: panel, backdrop: backdrop };
    },

    _closeDetail: function() {
        if (this._detailPanel) {
            if (this._detailPanel.panel && this._detailPanel.panel.parentNode) {
                this._detailPanel.panel.parentNode.removeChild(this._detailPanel.panel);
            }
            if (this._detailPanel.backdrop && this._detailPanel.backdrop.parentNode) {
                this._detailPanel.backdrop.parentNode.removeChild(this._detailPanel.backdrop);
            }
            this._detailPanel = null;
        }
    },
};
