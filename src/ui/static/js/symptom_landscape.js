/**
 * Symptom Landscape — Unified Symptom Timeline by Body System
 *
 * D3 swim-lane visualization grouping ALL patient-reported symptoms
 * by body system on a single timeline. Features:
 *   - Medication bars at top for context
 *   - Swim lanes per body system with episode dots
 *   - Dot size by intensity, color by body system
 *   - Unattributed symptoms highlighted (dashed border + "?")
 *   - Temporal cluster bands (vertical highlights)
 *   - Click-to-detail panel
 *   - Left panel with body system filters
 *
 * Overlay pattern matches Trajectories / Snowball / Cascades.
 * XSS: All user content via .textContent, never innerHTML.
 */

/* global d3, escapeHtml */

var SymptomLandscape = {
    _overlay: null,
    _isOpen: false,
    _data: null,
    _activeFilters: {},
    _detailPanel: null,

    // Body system color palette
    COLORS: {
        gi: "#f97316",
        musculoskeletal: "#3b82f6",
        neurological: "#a07aff",
        mood_energy: "#e06c8a",
        cardiovascular: "#dc2626",
        sleep: "#6366f1",
        skin: "#f0c550",
        other: "#6b7280"
    },

    LABELS: {
        gi: "GI / Digestive",
        musculoskeletal: "Musculoskeletal",
        neurological: "Neurological",
        mood_energy: "Mood & Energy",
        cardiovascular: "Cardiovascular",
        sleep: "Sleep",
        skin: "Skin",
        other: "Other"
    },

    // ── Public API ─────────────────────────────────────────

    open: function() {
        var self = this;
        var container = document.getElementById("view-symptom-landscape");
        if (!container) {
            console.error("Symptom Landscape: #view-symptom-landscape not found");
            return;
        }

        // Clear previous content
        while (container.firstChild) container.removeChild(container.firstChild);

        fetch("/api/symptom-landscape")
            .then(function(r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            })
            .then(function(data) {
                self._data = data;
                // Enable all systems by default
                self._activeFilters = {};
                var systems = Object.keys(data.by_body_system || {});
                for (var i = 0; i < systems.length; i++) {
                    self._activeFilters[systems[i]] = true;
                }
                self._buildView(container, data);
                self._isOpen = true;
            })
            .catch(function(err) {
                console.error("Symptom Landscape fetch failed:", err);
            });
    },

    close: function() {
        this._isOpen = false;
        this._detailPanel = null;
    },

    // ── View Construction ────────────────────────────────

    _buildView: function(container, data) {
        var self = this;

        // Wrap everything in a .sl-view container (inline, not overlay)
        var wrapper = document.createElement("div");
        wrapper.className = "sl-view";

        // ── Header ──
        var header = document.createElement("div");
        header.className = "sl-header";

        var titleWrap = document.createElement("div");
        var title = document.createElement("div");
        title.className = "sl-title";
        title.textContent = "Symptom Landscape";
        titleWrap.appendChild(title);

        var subtitle = document.createElement("div");
        subtitle.className = "sl-subtitle";
        subtitle.textContent = "All symptoms organized by body system across your timeline";
        titleWrap.appendChild(subtitle);

        header.appendChild(titleWrap);
        wrapper.appendChild(header);

        // ── Summary Bar ──
        var summaryBar = document.createElement("div");
        summaryBar.className = "sl-summary-bar";

        var summary = data.summary || {};
        var badges = [
            { label: (summary.total_symptoms || 0) + " symptoms", cls: "sl-summary-badge sl-badge-info" },
            { label: (summary.body_systems_involved || 0) + " body systems", cls: "sl-summary-badge sl-badge-systems" },
            { label: (summary.unattributed_count || 0) + " unattributed", cls: "sl-summary-badge sl-badge-unattributed" },
            { label: (summary.cluster_count || 0) + " clusters", cls: "sl-summary-badge sl-badge-clusters" },
        ];

        for (var b = 0; b < badges.length; b++) {
            var badge = document.createElement("span");
            badge.className = badges[b].cls;
            badge.textContent = badges[b].label;
            summaryBar.appendChild(badge);
        }

        wrapper.appendChild(summaryBar);

        // ── Content Area ──
        var content = document.createElement("div");
        content.className = "sl-content";

        // Left panel: body system filter list
        var leftPanel = document.createElement("div");
        leftPanel.className = "sl-left-panel";
        this._buildFilterPanel(leftPanel, data);
        content.appendChild(leftPanel);

        // Chart panel
        var chartPanel = document.createElement("div");
        chartPanel.className = "sl-chart-panel";
        content.appendChild(chartPanel);

        wrapper.appendChild(content);
        container.appendChild(wrapper);

        // Render the D3 timeline after DOM insertion
        requestAnimationFrame(function() {
            self._renderTimeline(chartPanel, data);
        });
    },

    // ── Filter Panel (Left Sidebar) ────────────────────────

    _buildFilterPanel: function(container, data) {
        var self = this;
        var bySystem = data.by_body_system || {};

        var heading = document.createElement("div");
        heading.className = "sl-filter-heading";
        heading.textContent = "Body Systems";
        container.appendChild(heading);

        var systems = Object.keys(bySystem);
        // Sort by number of symptoms descending
        systems.sort(function(a, b) {
            return (bySystem[b] || []).length - (bySystem[a] || []).length;
        });

        for (var i = 0; i < systems.length; i++) {
            (function(system) {
                var symptoms = bySystem[system] || [];
                var totalEpisodes = 0;
                for (var j = 0; j < symptoms.length; j++) {
                    totalEpisodes += (symptoms[j].episode_count || 0);
                }

                var item = document.createElement("div");
                item.className = "sl-filter-item" + (self._activeFilters[system] ? " active" : "");
                item.dataset.system = system;

                var indicator = document.createElement("span");
                indicator.className = "sl-filter-indicator";
                indicator.style.backgroundColor = self.COLORS[system] || self.COLORS.other;
                item.appendChild(indicator);

                var label = document.createElement("span");
                label.className = "sl-filter-label";
                label.textContent = self.LABELS[system] || system;
                item.appendChild(label);

                var count = document.createElement("span");
                count.className = "sl-filter-count";
                count.textContent = symptoms.length + " (" + totalEpisodes + ")";
                item.appendChild(count);

                item.addEventListener("click", function() {
                    self._activeFilters[system] = !self._activeFilters[system];
                    item.classList.toggle("active", self._activeFilters[system]);
                    // Re-render timeline with updated filters
                    var viewContainer = document.getElementById("view-symptom-landscape");
                    var chartPanel = viewContainer ? viewContainer.querySelector(".sl-chart-panel") : null;
                    if (chartPanel) {
                        while (chartPanel.firstChild) {
                            chartPanel.removeChild(chartPanel.firstChild);
                        }
                        self._renderTimeline(chartPanel, self._data);
                    }
                });

                container.appendChild(item);

                // Show symptom names under the system
                for (var k = 0; k < symptoms.length; k++) {
                    var subItem = document.createElement("div");
                    subItem.className = "sl-filter-symptom";
                    subItem.textContent = symptoms[k].symptom_name || "Unknown";
                    container.appendChild(subItem);
                }
            })(systems[i]);
        }

        if (systems.length === 0) {
            var empty = document.createElement("div");
            empty.className = "sl-filter-empty";
            empty.textContent = "No symptoms tracked yet. Start tracking symptoms to see them organized by body system.";
            container.appendChild(empty);
        }
    },

    // ── D3 Timeline Rendering ──────────────────────────────

    _renderTimeline: function(container, data) {
        var self = this;
        var bySystem = data.by_body_system || {};
        var medications = data.medications || [];
        var clusters = data.temporal_clusters || [];

        // Filter to active systems only
        var activeSystems = [];
        var allEpisodes = [];
        var systemKeys = Object.keys(bySystem);

        for (var i = 0; i < systemKeys.length; i++) {
            var sys = systemKeys[i];
            if (!self._activeFilters[sys]) continue;
            activeSystems.push(sys);
            var symptoms = bySystem[sys] || [];
            for (var j = 0; j < symptoms.length; j++) {
                var s = symptoms[j];
                var eps = s.episodes || [];
                for (var k = 0; k < eps.length; k++) {
                    var ep = eps[k];
                    if (!ep.episode_date) continue;
                    allEpisodes.push({
                        date: new Date(ep.episode_date),
                        intensity: ep.intensity || "mid",
                        description: ep.description,
                        symptomName: s.symptom_name,
                        bodySystem: sys,
                        linkedMedication: ep.linked_medication_id || s.linked_medication || null,
                        episodeId: ep.episode_id,
                        timeOfDay: ep.time_of_day,
                        duration: ep.duration,
                        triggers: ep.triggers,
                    });
                }
            }
        }

        if (activeSystems.length === 0 && systemKeys.length > 0) {
            var notice = document.createElement("div");
            notice.className = "sl-empty";
            notice.textContent = "All body systems are filtered out. Click a system in the left panel to show it.";
            container.appendChild(notice);
            return;
        }

        if (allEpisodes.length === 0) {
            var emptyMsg = document.createElement("div");
            emptyMsg.className = "sl-empty";
            emptyMsg.textContent = "No symptom episodes to display. Start tracking symptoms to see your symptom landscape.";
            container.appendChild(emptyMsg);
            return;
        }

        // Layout constants
        var margin = { top: 20, right: 30, bottom: 40, left: 10 };
        var medBarHeight = 24;
        var medGap = 4;
        var medSectionPadding = 16;
        var laneHeight = 60;
        var laneGap = 8;

        var activeMeds = medications.filter(function(m) { return m.start_date; });
        var medSectionH = activeMeds.length > 0
            ? (activeMeds.length * (medBarHeight + medGap)) + medSectionPadding + 24
            : 0;

        var totalHeight = margin.top + medSectionH
            + (activeSystems.length * (laneHeight + laneGap))
            + margin.bottom;

        var rect = container.getBoundingClientRect();
        var width = rect.width || 800;
        var innerW = width - margin.left - margin.right;

        // ── Date extent ──
        var allDates = allEpisodes.map(function(e) { return e.date; });
        // Include medication dates
        for (var mi = 0; mi < activeMeds.length; mi++) {
            if (activeMeds[mi].start_date) allDates.push(new Date(activeMeds[mi].start_date));
            if (activeMeds[mi].end_date) allDates.push(new Date(activeMeds[mi].end_date));
        }
        var dateExtent = d3.extent(allDates);
        // Pad by 7 days on each side
        var padMs = 7 * 24 * 60 * 60 * 1000;
        dateExtent[0] = new Date(dateExtent[0].getTime() - padMs);
        dateExtent[1] = new Date(dateExtent[1].getTime() + padMs);

        var xScale = d3.scaleTime()
            .domain(dateExtent)
            .range([0, innerW]);

        // ── SVG ──
        var svg = d3.select(container)
            .append("svg")
            .attr("width", width)
            .attr("height", totalHeight)
            .attr("class", "sl-svg");

        var g = svg.append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        // ── Medication Bars Section ──
        var currentY = 0;
        if (activeMeds.length > 0) {
            g.append("text")
                .attr("x", 0)
                .attr("y", currentY + 12)
                .attr("class", "sl-section-label")
                .text("Medications");

            currentY += 20;

            for (var m = 0; m < activeMeds.length; m++) {
                var med = activeMeds[m];
                var startDate = new Date(med.start_date);
                var endDate = med.end_date ? new Date(med.end_date) : dateExtent[1];

                var barX = xScale(startDate);
                var barW = Math.max(4, xScale(endDate) - barX);

                g.append("rect")
                    .attr("x", barX)
                    .attr("y", currentY)
                    .attr("width", barW)
                    .attr("height", medBarHeight)
                    .attr("rx", 4)
                    .attr("fill", med.color || "#3b82f6")
                    .attr("opacity", 0.3)
                    .attr("class", "sl-med-bar");

                g.append("text")
                    .attr("x", barX + 6)
                    .attr("y", currentY + medBarHeight / 2 + 4)
                    .attr("class", "sl-med-label")
                    .text(med.name || "Unknown");

                currentY += medBarHeight + medGap;
            }

            currentY += medSectionPadding;
        }

        // ── Cluster Bands ──
        this._renderClusterBands(g, clusters, xScale, activeSystems, currentY, laneHeight, laneGap);

        // ── Swim Lanes ──
        for (var li = 0; li < activeSystems.length; li++) {
            var system = activeSystems[li];
            var laneY = currentY + (li * (laneHeight + laneGap));
            var color = self.COLORS[system] || self.COLORS.other;

            // Lane background
            g.append("rect")
                .attr("x", 0)
                .attr("y", laneY)
                .attr("width", innerW)
                .attr("height", laneHeight)
                .attr("fill", color)
                .attr("opacity", 0.04)
                .attr("rx", 4)
                .attr("class", "sl-lane-bg");

            // Lane label
            g.append("text")
                .attr("x", 6)
                .attr("y", laneY + 14)
                .attr("class", "sl-lane-label")
                .attr("fill", color)
                .text(self.LABELS[system] || system);

            // Episode dots for this system
            var systemEpisodes = allEpisodes.filter(function(e) {
                return e.bodySystem === system;
            });

            for (var ei = 0; ei < systemEpisodes.length; ei++) {
                (function(ep, idx) {
                    var cx = xScale(ep.date);
                    // Jitter Y within lane to avoid overlap
                    var jitter = (idx % 3 - 1) * 8;
                    var cy = laneY + laneHeight / 2 + 4 + jitter;

                    // Size by intensity
                    var sizeMap = { low: 4, mid: 6, high: 9 };
                    var r = sizeMap[ep.intensity] || 6;

                    var isUnattributed = !ep.linkedMedication;

                    var dot = g.append("circle")
                        .attr("cx", cx)
                        .attr("cy", cy)
                        .attr("r", r)
                        .attr("fill", color)
                        .attr("opacity", 0.8)
                        .attr("class", "sl-dot" + (isUnattributed ? " sl-dot-unattributed" : " sl-dot-attributed"))
                        .attr("stroke", isUnattributed ? color : "none")
                        .attr("stroke-width", isUnattributed ? 1.5 : 0)
                        .attr("stroke-dasharray", isUnattributed ? "3,2" : "none")
                        .attr("fill-opacity", isUnattributed ? 0.4 : 0.8);

                    // "?" indicator for unattributed
                    if (isUnattributed && r >= 6) {
                        g.append("text")
                            .attr("x", cx)
                            .attr("y", cy + 3)
                            .attr("text-anchor", "middle")
                            .attr("class", "sl-dot-question")
                            .attr("font-size", "8px")
                            .attr("fill", color)
                            .text("?");
                    }

                    // Click handler for detail
                    dot.on("click", function() {
                        self._showDetail(ep, container);
                    });

                    // Hover tooltip
                    dot.on("mouseenter", function(event) {
                        var tip = document.createElement("div");
                        tip.className = "sl-tooltip";
                        tip.style.position = "fixed";
                        tip.style.left = event.clientX + 12 + "px";
                        tip.style.top = event.clientY - 10 + "px";

                        var nameEl = document.createElement("div");
                        nameEl.className = "sl-tooltip-name";
                        nameEl.textContent = ep.symptomName;
                        tip.appendChild(nameEl);

                        var dateEl = document.createElement("div");
                        dateEl.className = "sl-tooltip-date";
                        dateEl.textContent = ep.date.toLocaleDateString();
                        tip.appendChild(dateEl);

                        if (ep.intensity) {
                            var sevEl = document.createElement("div");
                            sevEl.className = "sl-tooltip-intensity";
                            sevEl.textContent = "Intensity: " + ep.intensity;
                            tip.appendChild(sevEl);
                        }

                        document.body.appendChild(tip);
                        tip.id = "sl-active-tooltip";
                    });

                    dot.on("mouseleave", function() {
                        var existing = document.getElementById("sl-active-tooltip");
                        if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
                    });
                })(systemEpisodes[ei], ei);
            }
        }

        // ── X Axis ──
        var axisY = currentY + (activeSystems.length * (laneHeight + laneGap)) + 4;
        var xAxis = d3.axisBottom(xScale)
            .ticks(d3.timeMonth.every(1))
            .tickFormat(d3.timeFormat("%b %Y"));

        g.append("g")
            .attr("transform", "translate(0," + axisY + ")")
            .attr("class", "sl-x-axis")
            .call(xAxis);
    },

    // ── Cluster Bands ──────────────────────────────────────

    _renderClusterBands: function(g, clusters, xScale, activeSystems, startY, laneHeight, laneGap) {
        if (!clusters || clusters.length === 0) return;

        var totalLanesH = activeSystems.length * (laneHeight + laneGap);

        for (var c = 0; c < clusters.length; c++) {
            var cluster = clusters[c];
            if (!cluster.window_start || !cluster.window_end) continue;

            // Check if any involved body system is active
            var involvedSystems = cluster.body_systems_involved || [];
            var anyActive = false;
            for (var s = 0; s < involvedSystems.length; s++) {
                if (this._activeFilters[involvedSystems[s]]) {
                    anyActive = true;
                    break;
                }
            }
            if (!anyActive) continue;

            var x1 = xScale(new Date(cluster.window_start));
            var x2 = xScale(new Date(cluster.window_end));
            var bandW = Math.max(4, x2 - x1);

            g.append("rect")
                .attr("x", x1)
                .attr("y", startY - 4)
                .attr("width", bandW)
                .attr("height", totalLanesH + 8)
                .attr("fill", cluster.cross_system ? "rgba(160, 122, 255, 0.08)" : "rgba(99, 102, 241, 0.06)")
                .attr("stroke", cluster.cross_system ? "rgba(160, 122, 255, 0.2)" : "rgba(99, 102, 241, 0.15)")
                .attr("stroke-width", 1)
                .attr("stroke-dasharray", "4,3")
                .attr("rx", 4)
                .attr("class", "sl-cluster-band");

            // Small cluster label at top
            g.append("text")
                .attr("x", x1 + bandW / 2)
                .attr("y", startY - 8)
                .attr("text-anchor", "middle")
                .attr("class", "sl-cluster-label")
                .text("Cluster (" + (cluster.symptoms || []).length + ")");
        }
    },

    // ── Detail Panel ───────────────────────────────────────

    _showDetail: function(episode, container) {
        // Remove existing detail panel
        var existing = container.querySelector(".sl-detail-panel");
        if (existing && existing.parentNode) existing.parentNode.removeChild(existing);

        var panel = document.createElement("div");
        panel.className = "sl-detail-panel";

        // Close button
        var closeBtn = document.createElement("button");
        closeBtn.className = "sl-detail-close";
        closeBtn.textContent = "\u00d7";
        closeBtn.addEventListener("click", function() {
            if (panel.parentNode) panel.parentNode.removeChild(panel);
        });
        panel.appendChild(closeBtn);

        // Title
        var titleEl = document.createElement("div");
        titleEl.className = "sl-detail-title";
        titleEl.textContent = episode.symptomName;
        panel.appendChild(titleEl);

        // Date
        this._addDetailRow(panel, "Date", episode.date.toLocaleDateString());

        // Severity
        var sevRow = document.createElement("div");
        sevRow.className = "sl-detail-row";
        var sevLabel = document.createElement("span");
        sevLabel.className = "sl-detail-label";
        sevLabel.textContent = "Intensity: ";
        sevRow.appendChild(sevLabel);
        var sevBadge = document.createElement("span");
        sevBadge.className = "sl-intensity-badge sl-int-" + (episode.intensity || "mid");
        sevBadge.textContent = (episode.intensity || "mid").charAt(0).toUpperCase() + (episode.intensity || "mid").slice(1);
        sevRow.appendChild(sevBadge);
        panel.appendChild(sevRow);

        // Body system
        var sysRow = document.createElement("div");
        sysRow.className = "sl-detail-row";
        var sysLabel = document.createElement("span");
        sysLabel.className = "sl-detail-label";
        sysLabel.textContent = "Body System: ";
        sysRow.appendChild(sysLabel);
        var sysVal = document.createElement("span");
        sysVal.className = "sl-detail-system";
        sysVal.style.color = this.COLORS[episode.bodySystem] || this.COLORS.other;
        sysVal.textContent = this.LABELS[episode.bodySystem] || episode.bodySystem;
        sysRow.appendChild(sysVal);
        panel.appendChild(sysRow);

        // Optional fields
        if (episode.description) this._addDetailRow(panel, "Description", episode.description);
        if (episode.timeOfDay) this._addDetailRow(panel, "Time of Day", episode.timeOfDay);
        if (episode.duration) this._addDetailRow(panel, "Duration", episode.duration);
        if (episode.triggers) this._addDetailRow(panel, "Triggers", episode.triggers);

        // Attribution status
        var attrRow = document.createElement("div");
        attrRow.className = "sl-detail-row sl-detail-attribution";
        var attrLabel = document.createElement("span");
        attrLabel.className = "sl-detail-label";
        attrLabel.textContent = "Attribution: ";
        attrRow.appendChild(attrLabel);
        var attrVal = document.createElement("span");
        if (episode.linkedMedication) {
            attrVal.textContent = "Linked to " + episode.linkedMedication;
            attrVal.className = "sl-attr-linked";
        } else {
            attrVal.textContent = "Not linked to any medication";
            attrVal.className = "sl-attr-unlinked";
        }
        attrRow.appendChild(attrVal);
        panel.appendChild(attrRow);

        // Doctor discussion framing
        var discussEl = document.createElement("div");
        discussEl.className = "sl-detail-discuss";
        discussEl.textContent = "Discuss with your doctor because tracking symptom patterns over time can reveal connections that individual visits might miss.";
        panel.appendChild(discussEl);

        container.appendChild(panel);
        this._detailPanel = panel;
    },

    _addDetailRow: function(panel, labelText, valueText) {
        var row = document.createElement("div");
        row.className = "sl-detail-row";
        var label = document.createElement("span");
        label.className = "sl-detail-label";
        label.textContent = labelText + ": ";
        row.appendChild(label);
        var val = document.createElement("span");
        val.textContent = valueText;
        row.appendChild(val);
        panel.appendChild(row);
    },
};
