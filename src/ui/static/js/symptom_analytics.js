/**
 * Symptom Analytics — D3.js Visualizations
 *
 * Renders inside the Symptoms view "Analytics" sub-tab:
 *   1. Calendar heatmap  — episode density per day (GitHub-style)
 *   2. Time-of-day heatmap — 4×7 grid
 *   3. Correlation matrix — symptom co-occurrence
 *   4. Counter-evidence scorecards — bar/donut + verdict
 *   5. Trigger frequency chart
 *   6. AI Insights cards
 */

/* global d3 */

var SymptomAnalytics = {
    _data: null,
    _insights: null,
    _container: null,

    // ── Public API ──────────────────────────────────────

    load: function(containerId) {
        var self = this;
        self._container = document.getElementById(containerId);
        if (!self._container) return;

        // Clear previous content safely
        while (self._container.firstChild) {
            self._container.removeChild(self._container.firstChild);
        }

        // Loading state
        var loading = document.createElement("div");
        loading.style.cssText = "text-align:center; padding:40px; color:var(--text-muted);";
        loading.textContent = "Loading analytics...";
        self._container.appendChild(loading);

        fetch("/api/symptom-analytics")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                self._data = data;
                self._render();
            })
            .catch(function(err) {
                while (self._container.firstChild) {
                    self._container.removeChild(self._container.firstChild);
                }
                var errEl = document.createElement("div");
                errEl.style.cssText = "text-align:center; padding:40px; color:var(--text-muted);";
                errEl.textContent = "Could not load analytics.";
                self._container.appendChild(errEl);
                console.error("Analytics load error:", err);
            });
    },

    _render: function() {
        var self = this;
        var c = self._container;
        while (c.firstChild) c.removeChild(c.firstChild);

        if (!self._data || self._data.summary.total_episodes === 0) {
            var empty = document.createElement("div");
            empty.style.cssText = "text-align:center; padding:60px; color:var(--text-muted);";
            empty.textContent = "Log a few episodes to see your analytics here.";
            c.appendChild(empty);
            return;
        }

        // Summary bar
        self._renderSummary(c);

        // Counter-evidence scorecards (the most important section)
        self._renderCounterScorecards(c);

        // Calendar heatmap
        self._renderCalendarHeatmap(c);

        // Time-of-day heatmap
        self._renderTimeHeatmap(c);

        // Correlation matrix
        self._renderCorrelationMatrix(c);

        // Trigger chart
        self._renderTriggerChart(c);

        // AI Insights
        self._renderInsightsSection(c);
    },

    // ── Summary ─────────────────────────────────────────

    _renderSummary: function(parent) {
        var s = this._data.summary;
        var card = this._makeCard("Overview", parent);
        var grid = document.createElement("div");
        grid.style.cssText = "display:grid; grid-template-columns:repeat(auto-fit, minmax(140px,1fr)); gap:16px;";

        var stats = [
            { label: "Symptoms tracked", value: s.total_symptoms },
            { label: "Total episodes", value: s.total_episodes },
            { label: "Most active", value: s.most_active || "—" },
            { label: "Avg per symptom", value: s.avg_episodes_per_symptom },
        ];

        stats.forEach(function(stat) {
            var box = document.createElement("div");
            box.style.cssText = "text-align:center; padding:12px; background:var(--bg-inset); border-radius:8px;";
            var val = document.createElement("div");
            val.style.cssText = "font-size:24px; font-weight:700; color:var(--accent-primary);";
            val.textContent = stat.value;
            var lbl = document.createElement("div");
            lbl.style.cssText = "font-size:12px; color:var(--text-muted); margin-top:4px;";
            lbl.textContent = stat.label;
            box.appendChild(val);
            box.appendChild(lbl);
            grid.appendChild(box);
        });

        card.appendChild(grid);
    },

    // ── Counter-Evidence Scorecards ──────────────────────

    _renderCounterScorecards: function(parent) {
        var scorecards = this._data.counter_scorecards || [];
        if (scorecards.length === 0) return;

        var card = this._makeCard("Counter-Evidence Scorecards", parent);
        var sub = document.createElement("div");
        sub.style.cssText = "font-size:13px; color:var(--text-muted); margin-bottom:16px;";
        sub.textContent = "What your data says about your doctor's claims";
        card.appendChild(sub);

        var self = this;
        scorecards.forEach(function(sc) {
            self._renderSingleScorecard(card, sc);
        });
    },

    _renderSingleScorecard: function(parent, sc) {
        var wrapper = document.createElement("div");
        wrapper.style.cssText = "background:var(--bg-inset); border-radius:10px; padding:16px; margin-bottom:12px;";

        // Header: "Headaches — Doctor says: stress"
        var header = document.createElement("div");
        header.style.cssText = "display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;";

        var title = document.createElement("div");
        var nameSpan = document.createElement("span");
        nameSpan.style.cssText = "font-weight:600; color:var(--text-primary);";
        nameSpan.textContent = sc.symptom_name;
        var claimSpan = document.createElement("span");
        claimSpan.style.cssText = "color:var(--text-secondary); margin-left:8px;";
        claimSpan.textContent = "Doctor says: " + sc.doctor_claim;
        title.appendChild(nameSpan);
        title.appendChild(claimSpan);

        // Verdict badge
        var badge = document.createElement("span");
        var verdictColors = {
            "strongly_contradicts": { bg: "#22c55e33", text: "#22c55e", label: "Contradicts" },
            "inconclusive": { bg: "#eab30833", text: "#eab308", label: "Inconclusive" },
            "supports_claim": { bg: "#ef444433", text: "#ef4444", label: "Supports" },
            "insufficient_data": { bg: "#64748b33", text: "#94a3b8", label: "Need more data" },
            "review_text": { bg: "#64748b33", text: "#94a3b8", label: "Review text" },
        };
        var vc = verdictColors[sc.verdict] || verdictColors["insufficient_data"];
        badge.style.cssText = "padding:4px 12px; border-radius:12px; font-size:12px; font-weight:600; background:" + vc.bg + "; color:" + vc.text + ";";
        badge.textContent = vc.label;

        header.appendChild(title);
        header.appendChild(badge);
        wrapper.appendChild(header);

        // Scale distribution bar chart
        if (sc.measure_type === "scale" && sc.distribution) {
            var barContainer = document.createElement("div");
            barContainer.style.cssText = "display:flex; align-items:flex-end; gap:4px; height:60px; margin-bottom:8px;";

            var maxCount = Math.max.apply(null, sc.distribution.map(function(d) { return d.count; }));
            sc.distribution.forEach(function(d) {
                var barWrapper = document.createElement("div");
                barWrapper.style.cssText = "flex:1; display:flex; flex-direction:column; align-items:center;";

                var bar = document.createElement("div");
                var h = maxCount > 0 ? (d.count / maxCount * 50) : 0;
                bar.style.cssText = "width:100%; height:" + h + "px; background:var(--accent-primary); border-radius:3px 3px 0 0; min-height:2px;";

                var label = document.createElement("div");
                label.style.cssText = "font-size:10px; color:var(--text-muted); margin-top:4px;";
                label.textContent = d.level;

                var count = document.createElement("div");
                count.style.cssText = "font-size:10px; color:var(--text-secondary);";
                count.textContent = d.count > 0 ? d.count : "";

                barWrapper.appendChild(count);
                barWrapper.appendChild(bar);
                barWrapper.appendChild(label);
                barContainer.appendChild(barWrapper);
            });

            wrapper.appendChild(barContainer);

            // Mean line
            var meanLine = document.createElement("div");
            meanLine.style.cssText = "font-size:12px; color:var(--text-secondary); text-align:center;";
            meanLine.textContent = "Average: " + sc.mean + "/5 across " + sc.episode_count + " episodes";
            wrapper.appendChild(meanLine);
        }

        // Yes/No donut (simple percentage bars)
        if (sc.measure_type === "yes_no") {
            var pctBar = document.createElement("div");
            pctBar.style.cssText = "display:flex; height:24px; border-radius:12px; overflow:hidden; margin-bottom:8px;";

            var yesPart = document.createElement("div");
            yesPart.style.cssText = "width:" + sc.pct_yes + "%; background:#ef4444; display:flex; align-items:center; justify-content:center; font-size:11px; color:white; font-weight:600;";
            if (sc.pct_yes >= 15) yesPart.textContent = "Yes " + sc.pct_yes + "%";

            var noPart = document.createElement("div");
            noPart.style.cssText = "width:" + sc.pct_no + "%; background:#22c55e; display:flex; align-items:center; justify-content:center; font-size:11px; color:white; font-weight:600;";
            if (sc.pct_no >= 15) noPart.textContent = "No " + sc.pct_no + "%";

            pctBar.appendChild(yesPart);
            pctBar.appendChild(noPart);
            wrapper.appendChild(pctBar);

            var countLabel = document.createElement("div");
            countLabel.style.cssText = "font-size:12px; color:var(--text-secondary); text-align:center;";
            countLabel.textContent = sc.yes_count + " yes, " + sc.no_count + " no across " + sc.episode_count + " episodes";
            wrapper.appendChild(countLabel);
        }

        // Archived badge
        if (sc.archived) {
            var archived = document.createElement("div");
            archived.style.cssText = "font-size:11px; color:var(--text-muted); font-style:italic; margin-top:8px;";
            archived.textContent = "Archived — data included in analytics";
            wrapper.appendChild(archived);
        }

        parent.appendChild(wrapper);
    },

    // ── Calendar Heatmap ────────────────────────────────

    _renderCalendarHeatmap: function(parent) {
        var heatmaps = this._data.calendar_heatmap || [];
        if (heatmaps.length === 0) return;

        var card = this._makeCard("Episode Calendar", parent);
        var sub = document.createElement("div");
        sub.style.cssText = "font-size:13px; color:var(--text-muted); margin-bottom:16px;";
        sub.textContent = "Episode frequency over the past 12 months";
        card.appendChild(sub);

        heatmaps.forEach(function(hm) {
            var section = document.createElement("div");
            section.style.cssText = "margin-bottom:20px;";

            var label = document.createElement("div");
            label.style.cssText = "font-size:14px; font-weight:600; color:var(--text-primary); margin-bottom:8px;";
            label.textContent = hm.symptom_name + " (" + hm.total_episodes + " episodes)";
            section.appendChild(label);

            // D3 calendar grid
            var svgContainer = document.createElement("div");
            svgContainer.style.cssText = "overflow-x:auto;";
            section.appendChild(svgContainer);

            if (typeof d3 !== "undefined") {
                var cellSize = 12;
                var weeks = Math.ceil(hm.days.length / 7) + 1;
                var width = weeks * (cellSize + 2) + 40;
                var height = 7 * (cellSize + 2) + 20;

                var svg = d3.select(svgContainer).append("svg")
                    .attr("width", width)
                    .attr("height", height);

                var colorScale = d3.scaleLinear()
                    .domain([0, Math.max(hm.max_count, 1)])
                    .range(["var(--bg-inset)", "var(--accent-primary)"]);

                // Day labels
                var dayLabels = ["M", "", "W", "", "F", "", "S"];
                svg.selectAll(".day-label")
                    .data(dayLabels)
                    .enter().append("text")
                    .attr("x", 10)
                    .attr("y", function(d, i) { return i * (cellSize + 2) + cellSize + 5; })
                    .attr("font-size", "9px")
                    .attr("fill", "var(--text-muted)")
                    .attr("text-anchor", "middle")
                    .text(function(d) { return d; });

                // Cells
                svg.selectAll(".day-cell")
                    .data(hm.days)
                    .enter().append("rect")
                    .attr("class", "day-cell")
                    .attr("x", function(d, i) { return Math.floor(i / 7) * (cellSize + 2) + 25; })
                    .attr("y", function(d) { return d.weekday * (cellSize + 2) + 5; })
                    .attr("width", cellSize)
                    .attr("height", cellSize)
                    .attr("rx", 2)
                    .attr("fill", function(d) { return d.count > 0 ? colorScale(d.count) : "var(--bg-inset)"; })
                    .attr("stroke", "var(--border-faint)")
                    .attr("stroke-width", 0.5);
            } else {
                var fallback = document.createElement("div");
                fallback.style.cssText = "color:var(--text-muted); font-size:13px;";
                fallback.textContent = hm.total_episodes + " episodes in the last year";
                section.appendChild(fallback);
            }

            card.appendChild(section);
        });
    },

    // ── Time-of-Day Heatmap ─────────────────────────────

    _renderTimeHeatmap: function(parent) {
        var heatmaps = this._data.time_heatmap || [];
        if (heatmaps.length === 0) return;

        var card = this._makeCard("When Symptoms Cluster", parent);
        var sub = document.createElement("div");
        sub.style.cssText = "font-size:13px; color:var(--text-muted); margin-bottom:16px;";
        sub.textContent = "Time of day × day of week";
        card.appendChild(sub);

        heatmaps.forEach(function(hm) {
            var section = document.createElement("div");
            section.style.cssText = "margin-bottom:20px;";

            var label = document.createElement("div");
            label.style.cssText = "font-size:14px; font-weight:600; color:var(--text-primary); margin-bottom:8px;";
            label.textContent = hm.symptom_name + (hm.peak ? " — peaks " + hm.peak : "");
            section.appendChild(label);

            // Table grid
            var table = document.createElement("div");
            table.style.cssText = "display:grid; grid-template-columns:80px repeat(7, 1fr); gap:3px;";

            // Header row
            var corner = document.createElement("div");
            table.appendChild(corner);
            hm.day_names.forEach(function(day) {
                var th = document.createElement("div");
                th.style.cssText = "text-align:center; font-size:11px; color:var(--text-muted); padding:4px;";
                th.textContent = day;
                table.appendChild(th);
            });

            // Data rows
            var maxVal = hm.max_count || 1;
            hm.time_slots.forEach(function(slot, si) {
                var rowLabel = document.createElement("div");
                rowLabel.style.cssText = "font-size:12px; color:var(--text-secondary); padding:4px; display:flex; align-items:center;";
                rowLabel.textContent = slot.charAt(0).toUpperCase() + slot.slice(1);
                table.appendChild(rowLabel);

                for (var di = 0; di < 7; di++) {
                    var cell = document.createElement("div");
                    var val = hm.grid[si][di];
                    var intensity = val / maxVal;
                    var bg = val > 0 ? "rgba(239, 68, 68, " + (0.2 + intensity * 0.6) + ")" : "var(--bg-inset)";
                    cell.style.cssText = "text-align:center; padding:8px 4px; border-radius:4px; font-size:12px; font-weight:600; background:" + bg + "; color:" + (val > 0 ? "var(--text-primary)" : "var(--text-muted)") + ";";
                    cell.textContent = val > 0 ? val : "";
                    table.appendChild(cell);
                }
            });

            section.appendChild(table);
            card.appendChild(section);
        });
    },

    // ── Correlation Matrix ──────────────────────────────

    _renderCorrelationMatrix: function(parent) {
        var corr = this._data.correlations || {};
        if (!corr.names || corr.names.length < 2) return;

        var card = this._makeCard("Symptom Co-occurrence", parent);
        var sub = document.createElement("div");
        sub.style.cssText = "font-size:13px; color:var(--text-muted); margin-bottom:16px;";
        sub.textContent = "Which symptoms flare together (within 1-2 days)";
        card.appendChild(sub);

        // Pairs list
        (corr.pairs || []).forEach(function(pair) {
            var row = document.createElement("div");
            row.style.cssText = "display:flex; align-items:center; gap:12px; padding:10px; background:var(--bg-inset); border-radius:8px; margin-bottom:8px;";

            var names = document.createElement("div");
            names.style.cssText = "font-weight:600; color:var(--text-primary); flex:1;";
            names.textContent = pair.symptom_a + " ↔ " + pair.symptom_b;

            var score = document.createElement("div");
            var pct = Math.round(pair.jaccard * 100);
            var color = pct > 50 ? "#ef4444" : pct > 30 ? "#eab308" : "#22c55e";
            score.style.cssText = "font-weight:700; color:" + color + ";";
            score.textContent = pct + "% overlap";

            var lag = document.createElement("div");
            lag.style.cssText = "font-size:12px; color:var(--text-muted);";
            lag.textContent = pair.avg_lag_days !== null ? "avg " + pair.avg_lag_days + " days apart" : "";

            row.appendChild(names);
            row.appendChild(score);
            row.appendChild(lag);
            card.appendChild(row);
        });
    },

    // ── Trigger Chart ───────────────────────────────────

    _renderTriggerChart: function(parent) {
        var triggers = this._data.trigger_analysis || [];
        if (triggers.length === 0) return;

        var card = this._makeCard("Top Triggers", parent);
        var sub = document.createElement("div");
        sub.style.cssText = "font-size:13px; color:var(--text-muted); margin-bottom:16px;";
        sub.textContent = "Most frequently reported triggers across all episodes";
        card.appendChild(sub);

        var maxCount = triggers[0] ? triggers[0].count : 1;

        triggers.slice(0, 8).forEach(function(t) {
            var row = document.createElement("div");
            row.style.cssText = "display:flex; align-items:center; gap:12px; margin-bottom:6px;";

            var label = document.createElement("div");
            label.style.cssText = "width:140px; font-size:13px; color:var(--text-primary); text-align:right; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;";
            label.textContent = t.trigger;

            var barBg = document.createElement("div");
            barBg.style.cssText = "flex:1; height:20px; background:var(--bg-inset); border-radius:10px; overflow:hidden;";

            var barFill = document.createElement("div");
            var w = Math.max(5, (t.count / maxCount) * 100);
            barFill.style.cssText = "height:100%; width:" + w + "%; background:var(--accent-primary); border-radius:10px; transition:width 0.3s;";

            barBg.appendChild(barFill);

            var count = document.createElement("div");
            count.style.cssText = "width:30px; font-size:12px; color:var(--text-muted); text-align:right;";
            count.textContent = t.count + "×";

            row.appendChild(label);
            row.appendChild(barBg);
            row.appendChild(count);
            card.appendChild(row);
        });
    },

    // ── AI Insights ─────────────────────────────────────

    _renderInsightsSection: function(parent) {
        var self = this;
        var card = self._makeCard("AI Insights", parent);

        var sub = document.createElement("div");
        sub.style.cssText = "font-size:13px; color:var(--text-muted); margin-bottom:12px;";
        sub.textContent = "Pattern detection across your symptom descriptions";
        card.appendChild(sub);

        // Loading initially
        var insightArea = document.createElement("div");
        insightArea.style.cssText = "min-height:60px;";
        card.appendChild(insightArea);

        // Fetch insights
        fetch("/api/symptom-analytics/insights", { method: "POST" })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                self._insights = data;
                self._renderInsightCards(insightArea, data);
            })
            .catch(function() {
                var msg = document.createElement("div");
                msg.style.cssText = "color:var(--text-muted); font-size:13px;";
                msg.textContent = "Log more episodes for AI pattern detection.";
                insightArea.appendChild(msg);
            });
    },

    _renderInsightCards: function(container, data) {
        while (container.firstChild) container.removeChild(container.firstChild);

        var icons = {
            patterns: "🔍",
            connections: "🔗",
            counter_narratives: "📊",
            suggestions: "💡",
        };

        var sections = ["patterns", "connections", "counter_narratives", "suggestions"];
        var hasContent = false;

        sections.forEach(function(section) {
            var items = data[section] || [];
            if (items.length === 0) return;
            hasContent = true;

            items.forEach(function(item) {
                var card = document.createElement("div");
                card.style.cssText = "display:flex; gap:12px; padding:12px; background:var(--bg-inset); border-radius:8px; margin-bottom:8px; border-left:3px solid var(--accent-primary);";

                var icon = document.createElement("div");
                icon.style.cssText = "font-size:20px; flex-shrink:0;";
                icon.textContent = icons[section] || "•";

                var text = document.createElement("div");
                text.style.cssText = "font-size:13px; color:var(--text-secondary); line-height:1.5;";
                text.textContent = item.message || JSON.stringify(item);

                card.appendChild(icon);
                card.appendChild(text);
                container.appendChild(card);
            });
        });

        if (!hasContent) {
            var msg = document.createElement("div");
            msg.style.cssText = "color:var(--text-muted); font-size:13px; text-align:center; padding:20px;";
            msg.textContent = "Log more episodes for AI pattern detection.";
            container.appendChild(msg);
        }

        // Source badge
        if (data.source) {
            var badge = document.createElement("div");
            badge.style.cssText = "text-align:right; font-size:11px; color:var(--text-muted); margin-top:8px;";
            badge.textContent = "Source: " + data.source;
            container.appendChild(badge);
        }
    },

    // ── Helpers ──────────────────────────────────────────

    _makeCard: function(title, parent) {
        var card = document.createElement("div");
        card.style.cssText = "background:var(--bg-raised); border:1px solid var(--border-faint); border-radius:12px; padding:20px; margin-bottom:20px;";

        var h = document.createElement("h3");
        h.style.cssText = "font-size:16px; font-weight:600; color:var(--text-primary); margin:0 0 12px 0;";
        h.textContent = title;
        card.appendChild(h);

        parent.appendChild(card);
        return card;
    },
};
