/* ══════════════════════════════════════════════════════════
   DashboardCharts — Full-size D3 visualization components
   for the diagnostic command center.

   Professional gradient-based palette with cohesive cool-tone
   color scheme. All themed for GNOME dark.
   ══════════════════════════════════════════════════════════ */

var DashboardCharts = {

    // Gradient pairs: [top/light, bottom/dark] — cohesive blue-teal family
    gradients: [
        ["#6B9BF7", "#3565C7"],   // Azure
        ["#7EC4E8", "#3A8BB8"],   // Cyan
        ["#5ED4C8", "#2A9D90"],   // Teal
        ["#8BA8E8", "#4A68B8"],   // Steel
        ["#9B8BE0", "#6050B0"],   // Indigo
        ["#6BD4A8", "#38A078"],   // Sage
        ["#7AB0F0", "#4070C0"],   // Cornflower
        ["#68C8D8", "#3090A8"],   // Aqua
    ],

    // Flat midpoint color for legends and dots
    palette: [
        "#5090E8", "#5AACCC", "#48C4B0", "#6888D0",
        "#7E6EC8", "#52B890", "#5C98D8", "#50B4C0",
    ],

    // Wider-spread palette for multi-series line charts where distinction matters
    linePalette: [
        "#5090E8",  // Blue
        "#48C4B0",  // Teal
        "#C8A848",  // Amber (warm accent)
        "#7E6EC8",  // Indigo
        "#58B888",  // Sage green
        "#C87860",  // Terracotta
        "#5AACCC",  // Cyan
        "#B08088",  // Mauve
    ],

    // Severity uses warm tones but muted, not candy
    severityGrad: {
        critical: ["#C84040", "#8B1A1A"],
        high:     ["#C87850", "#984828"],
        moderate: ["#C8A848", "#987820"],
        low:      ["#58B888", "#308860"],
    },
    severityFlat: {
        critical: "#A82828", high: "#B06038",
        moderate: "#B09030", low: "#48A878",
    },

    colors: {
        bg: "#171717", grid: "#2a2a2a", axis: "#555",
        text: "#888", textBright: "#ccc",
        inRange: "#48A878", outRange: "#C84040",
    },

    _clear: function(el) {
        while (el.firstChild) el.removeChild(el.firstChild);
    },

    // Create an SVG linearGradient and return its url() reference
    _grad: function(defs, id, top, bot, vertical) {
        var g = defs.append("linearGradient").attr("id", id)
            .attr("x1", "0%").attr("y1", "0%")
            .attr("x2", vertical ? "0%" : "100%")
            .attr("y2", vertical ? "100%" : "0%");
        g.append("stop").attr("offset", "0%").attr("stop-color", top);
        g.append("stop").attr("offset", "100%").attr("stop-color", bot);
        return "url(#" + id + ")";
    },

    // ══════════════════════════════════════════════════════
    //  LINE CHART — area fill, axes, gridlines, legend
    // ══════════════════════════════════════════════════════

    renderLineChart: function(containerId, series, opts) {
        if (typeof d3 === "undefined") return;
        var el = document.getElementById(containerId);
        if (!el) return;
        this._clear(el);

        opts = opts || {};
        var margin = { top: 16, right: 12, bottom: 36, left: 42 };
        var W = opts.width || el.clientWidth || 320;
        var H = opts.height || 180;
        var w = W - margin.left - margin.right;
        var h = H - margin.top - margin.bottom;
        var self = this;

        var svg = d3.select(el).append("svg")
            .attr("width", W).attr("height", H)
            .attr("viewBox", "0 0 " + W + " " + H);
        var defs = svg.append("defs");
        var g = svg.append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        if (series.length && series[0].date !== undefined) {
            series = [{ name: opts.label || "", color: self.palette[0], points: series }];
        }

        series.forEach(function(s) {
            s.points.forEach(function(p) {
                if (!(p.date instanceof Date)) p.date = new Date(p.date);
            });
            s.points.sort(function(a, b) { return a.date - b.date; });
        });

        var allPoints = [];
        series.forEach(function(s) { allPoints = allPoints.concat(s.points); });
        var x = d3.scaleTime()
            .domain(d3.extent(allPoints, function(p) { return p.date; }))
            .range([0, w]);
        var yMax = d3.max(allPoints, function(p) { return p.value; }) || 1;
        var y = d3.scaleLinear().domain([0, yMax * 1.1]).range([h, 0]);

        // Gridlines
        g.selectAll(".grid-line").data(y.ticks(4)).enter().append("line")
            .attr("x1", 0).attr("x2", w)
            .attr("y1", function(d) { return y(d); })
            .attr("y2", function(d) { return y(d); })
            .attr("stroke", self.colors.grid).attr("stroke-dasharray", "3,3");

        // X axis
        g.append("g").attr("transform", "translate(0," + h + ")")
            .call(d3.axisBottom(x).ticks(Math.min(allPoints.length, 6)).tickFormat(d3.timeFormat("%b %d")))
            .selectAll("text").attr("fill", self.colors.text).attr("font-size", "10px");
        g.selectAll(".domain, .tick line").attr("stroke", self.colors.grid);

        // Y axis
        g.append("g").call(d3.axisLeft(y).ticks(4).tickFormat(function(d) {
            return d >= 1000 ? (d / 1000).toFixed(1) + "K" : d;
        })).selectAll("text").attr("fill", self.colors.text).attr("font-size", "10px");
        g.selectAll(".domain, .tick line").attr("stroke", self.colors.grid);

        // Draw series with gradient area fills
        series.forEach(function(s, si) {
            var gp = self.gradients[si % self.gradients.length];
            var color = s.color || self.palette[si % self.palette.length];
            var fillRef = self._grad(defs, "line-area-" + si, gp[0], gp[1], true);

            var area = d3.area()
                .x(function(p) { return x(p.date); }).y0(h)
                .y1(function(p) { return y(p.value); }).curve(d3.curveMonotoneX);
            g.append("path").datum(s.points)
                .attr("fill", fillRef).attr("fill-opacity", 0.15).attr("d", area);

            var line = d3.line()
                .x(function(p) { return x(p.date); })
                .y(function(p) { return y(p.value); }).curve(d3.curveMonotoneX);
            g.append("path").datum(s.points)
                .attr("fill", "none").attr("stroke", color).attr("stroke-width", 2).attr("d", line);

            g.selectAll(".dot-" + si).data(s.points).enter().append("circle")
                .attr("cx", function(p) { return x(p.date); })
                .attr("cy", function(p) { return y(p.value); })
                .attr("r", s.points.length > 20 ? 2 : 3.5)
                .attr("fill", color).attr("stroke", self.colors.bg).attr("stroke-width", 1);
        });

        // Legend
        if (series.length > 1) {
            var legend = svg.append("g").attr("transform", "translate(" + margin.left + ",4)");
            var lx = 0;
            series.forEach(function(s, si) {
                var color = s.color || self.palette[si % self.palette.length];
                legend.append("line").attr("x1", lx).attr("x2", lx + 16)
                    .attr("y1", 6).attr("y2", 6).attr("stroke", color).attr("stroke-width", 2);
                legend.append("circle").attr("cx", lx + 8).attr("cy", 6).attr("r", 2.5).attr("fill", color);
                legend.append("text").attr("x", lx + 20).attr("y", 10)
                    .attr("fill", self.colors.text).attr("font-size", "10px").text(s.name);
                lx += 20 + (s.name.length * 6) + 16;
            });
        }
    },

    // ══════════════════════════════════════════════════════
    //  VERTICAL BAR CHART — gradient bars, axes, labels
    // ══════════════════════════════════════════════════════

    renderBarChart: function(containerId, items, opts) {
        if (typeof d3 === "undefined") return;
        var el = document.getElementById(containerId);
        if (!el || !items || !items.length) return;
        this._clear(el);

        opts = opts || {};
        var margin = { top: 8, right: 8, bottom: 40, left: 40 };
        var W = opts.width || el.clientWidth || 320;
        var H = opts.height || 160;
        var w = W - margin.left - margin.right;
        var h = H - margin.top - margin.bottom;
        var self = this;

        var svg = d3.select(el).append("svg")
            .attr("width", W).attr("height", H)
            .attr("viewBox", "0 0 " + W + " " + H);
        var defs = svg.append("defs");
        var g = svg.append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

        // Create gradients for each bar
        items.forEach(function(d, i) {
            var gp = self.gradients[i % self.gradients.length];
            self._grad(defs, "bar-" + i, gp[0], gp[1], true);
        });

        var x = d3.scaleBand().domain(items.map(function(d) { return d.label; }))
            .range([0, w]).padding(0.25);
        var y = d3.scaleLinear()
            .domain([0, d3.max(items, function(d) { return d.value; }) * 1.15 || 1])
            .range([h, 0]);

        // Gridlines
        g.selectAll(".grid").data(y.ticks(4)).enter().append("line")
            .attr("x1", 0).attr("x2", w)
            .attr("y1", function(d) { return y(d); })
            .attr("y2", function(d) { return y(d); })
            .attr("stroke", self.colors.grid).attr("stroke-dasharray", "3,3");

        // Bars with gradients
        g.selectAll("rect").data(items).enter().append("rect")
            .attr("x", function(d) { return x(d.label); })
            .attr("y", function(d) { return y(d.value); })
            .attr("width", x.bandwidth())
            .attr("height", function(d) { return h - y(d.value); })
            .attr("fill", function(d, i) { return "url(#bar-" + i + ")"; });

        // Value labels
        g.selectAll(".val-label").data(items).enter().append("text")
            .attr("x", function(d) { return x(d.label) + x.bandwidth() / 2; })
            .attr("y", function(d) { return y(d.value) - 4; })
            .attr("text-anchor", "middle").attr("fill", self.colors.textBright)
            .attr("font-size", "10px").attr("font-weight", "600")
            .text(function(d) { return d.value; });

        // X axis
        g.append("g").attr("transform", "translate(0," + h + ")")
            .call(d3.axisBottom(x).tickSize(0))
            .selectAll("text").attr("fill", self.colors.text).attr("font-size", "9px")
            .attr("transform", "rotate(-25)").attr("text-anchor", "end");
        g.selectAll(".domain").attr("stroke", self.colors.grid);

        // Y axis
        g.append("g").call(d3.axisLeft(y).ticks(4))
            .selectAll("text").attr("fill", self.colors.text).attr("font-size", "10px");
        g.selectAll(".domain, .tick line").attr("stroke", self.colors.grid);
    },

    // ══════════════════════════════════════════════════════
    //  HORIZONTAL BAR CHART — gradient bars with labels
    // ══════════════════════════════════════════════════════

    renderHBars: function(containerId, items, opts) {
        if (typeof d3 === "undefined") return;
        var el = document.getElementById(containerId);
        if (!el || !items || !items.length) return;
        this._clear(el);

        opts = opts || {};
        var barH = opts.barHeight || 22;
        var gap = 8;
        var labelW = opts.labelWidth || 100;
        var W = opts.width || el.clientWidth || 300;
        var data = items.slice(0, opts.maxItems || 8);
        var H = data.length * (barH + gap) + 4;
        var barArea = W - labelW - 50;
        var maxVal = d3.max(data, function(d) { return d.value; }) || 1;
        var self = this;

        var svg = d3.select(el).append("svg")
            .attr("width", W).attr("height", H)
            .attr("viewBox", "0 0 " + W + " " + H);
        var defs = svg.append("defs");

        data.forEach(function(d, i) {
            var yPos = i * (barH + gap) + 2;
            var bw = (d.value / maxVal) * barArea;
            var gp = self.gradients[i % self.gradients.length];
            var gradRef = self._grad(defs, "hbar-" + i, gp[0], gp[1], false);

            // Label
            svg.append("text").attr("x", labelW - 6).attr("y", yPos + barH / 2 + 4)
                .attr("text-anchor", "end").attr("fill", self.colors.text).attr("font-size", "11px")
                .text(d.label.length > 16 ? d.label.substring(0, 16) + "…" : d.label);

            // Background
            svg.append("rect").attr("x", labelW).attr("y", yPos)
                .attr("width", barArea).attr("height", barH).attr("fill", "#1f1f1f");

            // Value bar with gradient
            svg.append("rect").attr("x", labelW).attr("y", yPos)
                .attr("width", Math.max(bw, 3)).attr("height", barH).attr("fill", gradRef);

            // Value text
            svg.append("text").attr("x", labelW + barArea + 8).attr("y", yPos + barH / 2 + 4)
                .attr("fill", self.colors.textBright).attr("font-size", "11px").attr("font-weight", "600")
                .text(d.value);
        });
    },

    // ══════════════════════════════════════════════════════
    //  DONUT CHART — gradient ring with center and legend
    // ══════════════════════════════════════════════════════

    renderDonut: function(containerId, segments, opts) {
        if (typeof d3 === "undefined") return;
        var el = document.getElementById(containerId);
        if (!el || !segments || !segments.length) return;
        this._clear(el);

        opts = opts || {};
        var size = opts.size || 140;
        var thick = opts.thickness || 14;
        var self = this;

        var wrapper = document.createElement("div");
        wrapper.style.cssText = "display:flex; align-items:center; gap:16px;";
        var chartDiv = document.createElement("div");
        chartDiv.style.cssText = "flex-shrink:0;";
        wrapper.appendChild(chartDiv);
        var legendDiv = document.createElement("div");
        legendDiv.style.cssText = "flex:1; min-width:0;";
        wrapper.appendChild(legendDiv);
        el.appendChild(wrapper);

        var svg = d3.select(chartDiv).append("svg")
            .attr("width", size).attr("height", size)
            .attr("viewBox", "0 0 " + size + " " + size);
        var defs = svg.append("defs");
        var gNode = svg.append("g")
            .attr("transform", "translate(" + size / 2 + "," + size / 2 + ")");

        // Create gradient for each segment — use explicit color if provided
        segments.forEach(function(seg, i) {
            if (seg.color) {
                // Derive gradient from explicit color (lighten for top)
                self._grad(defs, "donut-" + containerId + "-" + i, seg.color, seg.colorDark || seg.color, true);
            } else {
                var gp = self.gradients[i % self.gradients.length];
                self._grad(defs, "donut-" + containerId + "-" + i, gp[0], gp[1], true);
            }
        });

        var radius = size / 2 - 4;
        var pie = d3.pie().value(function(d) { return d.value; }).sort(null).padAngle(0.005);
        var arc = d3.arc().innerRadius(radius - thick).outerRadius(radius);

        gNode.selectAll("path").data(pie(segments)).enter().append("path")
            .attr("d", arc)
            .attr("fill", function(d, i) { return "url(#donut-" + containerId + "-" + i + ")"; });

        // Center text
        if (opts.centerText !== undefined) {
            gNode.append("text").attr("text-anchor", "middle").attr("dy", "-0.1em")
                .attr("fill", opts.centerColor || "#fff")
                .attr("font-size", opts.centerSize || "24px").attr("font-weight", "700")
                .text(opts.centerText);
            if (opts.centerLabel) {
                gNode.append("text").attr("text-anchor", "middle").attr("dy", "1.3em")
                    .attr("fill", self.colors.text).attr("font-size", "10px")
                    .text(opts.centerLabel);
            }
        }

        // Legend — use explicit color when provided (e.g. severity)
        segments.forEach(function(seg, i) {
            var color = seg.color || self.palette[i % self.palette.length];
            var row = document.createElement("div");
            row.style.cssText = "display:flex; align-items:center; gap:8px; margin-bottom:6px;";
            var dot = document.createElement("div");
            dot.style.cssText = "width:10px; height:10px; border-radius:2px; flex-shrink:0; background:" + color;
            row.appendChild(dot);
            var label = document.createElement("span");
            label.style.cssText = "font-size:12px; color:#888; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;";
            label.textContent = seg.label;
            row.appendChild(label);
            var val = document.createElement("span");
            val.style.cssText = "font-size:12px; color:#ccc; font-weight:600;";
            val.textContent = seg.value;
            row.appendChild(val);
            legendDiv.appendChild(row);
        });
    },

    // ══════════════════════════════════════════════════════
    //  RISK GAUGE — half-circle arc with gradient fill
    // ══════════════════════════════════════════════════════

    renderRiskGauge: function(containerId, score, maxScore) {
        if (typeof d3 === "undefined") return;
        var el = document.getElementById(containerId);
        if (!el) return;
        this._clear(el);

        maxScore = maxScore || 100;
        score = Math.min(Math.max(score || 0, 0), maxScore);
        var pct = score / maxScore;
        var self = this;

        var w = 100, h = 65;
        var svg = d3.select(el).append("svg")
            .attr("width", w).attr("height", h)
            .attr("viewBox", "0 0 " + w + " " + h);
        var defs = svg.append("defs");

        var cx = w / 2, cy = h - 4;
        var r = 38;
        var start = -Math.PI, end = 0;
        var scoreAngle = start + pct * (end - start);

        var gp;
        if (pct <= 0.3) gp = self.severityGrad.low;
        else if (pct <= 0.6) gp = self.severityGrad.moderate;
        else if (pct <= 0.8) gp = self.severityGrad.high;
        else gp = self.severityGrad.critical;
        var gradRef = self._grad(defs, "gauge-fill", gp[0], gp[1], false);

        var color;
        if (pct <= 0.3) color = self.severityFlat.low;
        else if (pct <= 0.6) color = self.severityFlat.moderate;
        else if (pct <= 0.8) color = self.severityFlat.high;
        else color = self.severityFlat.critical;

        var arc = d3.arc().innerRadius(r - 10).outerRadius(r)
            .startAngle(function(d) { return d[0]; })
            .endAngle(function(d) { return d[1]; });

        svg.append("path").datum([start, end]).attr("d", arc)
            .attr("fill", "#2a2a2a")
            .attr("transform", "translate(" + cx + "," + cy + ")");

        if (score > 0) {
            svg.append("path").datum([start, scoreAngle]).attr("d", arc)
                .attr("fill", gradRef)
                .attr("transform", "translate(" + cx + "," + cy + ")");
        }

        svg.append("text").attr("x", cx).attr("y", cy - 14)
            .attr("text-anchor", "middle").attr("fill", color)
            .attr("font-size", "22px").attr("font-weight", "700").text(score);
        svg.append("text").attr("x", cx).attr("y", cy + 1)
            .attr("text-anchor", "middle").attr("fill", self.colors.text)
            .attr("font-size", "9px").text("RISK SCORE");
    },

    // ══════════════════════════════════════════════════════
    //  LAB RANGE BARS — value marker on reference range
    // ══════════════════════════════════════════════════════

    renderLabRangeBars: function(containerId, labs, opts) {
        if (typeof d3 === "undefined") return;
        var el = document.getElementById(containerId);
        if (!el || !labs || !labs.length) return;
        this._clear(el);

        opts = opts || {};
        var max = opts.maxItems || 8;
        var rH = 32;
        var lW = 90;
        var data = labs.slice(0, max);
        var W = el.clientWidth || 300;
        var H = data.length * rH + 4;
        var bW = W - lW - 50;
        var self = this;

        var svg = d3.select(el).append("svg")
            .attr("width", W).attr("height", H)
            .attr("viewBox", "0 0 " + W + " " + H);

        data.forEach(function(lab, i) {
            var yPos = i * rH + 2;
            var name = lab.test_name || lab.name || "?";
            var val = parseFloat(lab.value);
            var lo = lab.reference_low != null ? parseFloat(lab.reference_low) : null;
            var hi = lab.reference_high != null ? parseFloat(lab.reference_high) : null;
            var unit = lab.unit || "";

            svg.append("text").attr("x", lW - 6).attr("y", yPos + 18)
                .attr("text-anchor", "end").attr("fill", self.colors.text).attr("font-size", "11px")
                .text(name.length > 12 ? name.substring(0, 12) + "…" : name);

            if (lo !== null && hi !== null && !isNaN(val)) {
                var margin = (hi - lo) * 0.4;
                var scale = d3.scaleLinear()
                    .domain([lo - margin, hi + margin]).range([0, bW]).clamp(true);

                svg.append("rect").attr("x", lW).attr("y", yPos + 10)
                    .attr("width", bW).attr("height", 10).attr("fill", "#1f1f1f");
                svg.append("rect")
                    .attr("x", lW + scale(lo)).attr("y", yPos + 10)
                    .attr("width", Math.max(scale(hi) - scale(lo), 4)).attr("height", 10)
                    .attr("fill", "rgba(72,168,120,0.18)");

                var inRange = val >= lo && val <= hi;
                svg.append("circle")
                    .attr("cx", lW + scale(val)).attr("cy", yPos + 15).attr("r", 6)
                    .attr("fill", inRange ? self.colors.inRange : self.colors.outRange)
                    .attr("stroke", self.colors.bg).attr("stroke-width", 2);
                svg.append("text").attr("x", lW + bW + 6).attr("y", yPos + 18)
                    .attr("fill", inRange ? self.colors.inRange : self.colors.outRange)
                    .attr("font-size", "11px").attr("font-weight", "600")
                    .text(val + (unit ? " " + unit : ""));
            } else {
                svg.append("text").attr("x", lW).attr("y", yPos + 18)
                    .attr("fill", self.colors.text).attr("font-size", "11px")
                    .text((val || lab.value || "—") + (unit ? " " + unit : ""));
            }
        });
    },

    // ══════════════════════════════════════════════════════
    //  SEVERITY BAR — gradient stacked horizontal + legend
    // ══════════════════════════════════════════════════════

    renderSeverityBar: function(containerId, counts) {
        if (typeof d3 === "undefined") return;
        var el = document.getElementById(containerId);
        if (!el) return;
        this._clear(el);

        var total = (counts.critical || 0) + (counts.high || 0) + (counts.moderate || 0) + (counts.low || 0);
        if (total === 0) return;
        var self = this;

        var W = el.clientWidth || 280;
        var svg = d3.select(el).append("svg")
            .attr("width", W).attr("height", 32)
            .attr("viewBox", "0 0 " + W + " 32");
        var defs = svg.append("defs");

        var segs = [
            { key: "Critical", n: counts.critical || 0, g: self.severityGrad.critical, c: self.severityFlat.critical },
            { key: "High", n: counts.high || 0, g: self.severityGrad.high, c: self.severityFlat.high },
            { key: "Moderate", n: counts.moderate || 0, g: self.severityGrad.moderate, c: self.severityFlat.moderate },
            { key: "Low", n: counts.low || 0, g: self.severityGrad.low, c: self.severityFlat.low },
        ];

        var x = 0;
        segs.forEach(function(s, i) {
            if (!s.n) return;
            var sw = (s.n / total) * W;
            var gradRef = self._grad(defs, "sev-" + i, s.g[0], s.g[1], false);
            svg.append("rect").attr("x", x).attr("y", 0)
                .attr("width", Math.max(sw, 3)).attr("height", 14).attr("fill", gradRef);
            x += sw;
        });

        var lx = 0;
        segs.forEach(function(s) {
            if (!s.n) return;
            svg.append("rect").attr("x", lx).attr("y", 22).attr("width", 8).attr("height", 8).attr("fill", s.c);
            svg.append("text").attr("x", lx + 12).attr("y", 29)
                .attr("fill", self.colors.text).attr("font-size", "10px")
                .text(s.n + " " + s.key);
            lx += 12 + (s.n + " " + s.key).length * 6 + 14;
        });
    },
};
