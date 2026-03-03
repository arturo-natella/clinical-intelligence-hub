/* ══════════════════════════════════════════════════════════
   Sparkline — Reusable D3 mini-chart component
   Renders a compact SVG line chart with optional reference
   range band.  Designed for the dashboard lab-trend widgets.

   Usage:
     Sparkline.render("container-id", dataPoints, options)

   dataPoints = [{ date: "2024-01-15", value: 4.2, ref_low: 3.5, ref_high: 5.0 }, ...]
   options    = { width, height, color, showRefBand }
   ══════════════════════════════════════════════════════════ */

var Sparkline = {

    defaults: {
        width: null,       // null = fit container
        height: 24,
        color: "#5a8ffc",  // bluetron
        refBandColor: "rgba(90,143,252,0.10)",
        outOfRangeColor: "#dc2626",  // heat
        strokeWidth: 1.5,
        showRefBand: true,
        dotRadius: 0,      // 0 = no dots
    },

    render: function(containerId, dataPoints, options) {
        if (typeof d3 === "undefined") return;
        var container = document.getElementById(containerId);
        if (!container || !dataPoints || dataPoints.length < 2) return;

        var opts = {};
        var key;
        for (key in Sparkline.defaults) {
            opts[key] = (options && options[key] !== undefined) ? options[key] : Sparkline.defaults[key];
        }

        var w = opts.width || container.clientWidth || 120;
        var h = opts.height;

        // Clear previous
        while (container.firstChild) container.removeChild(container.firstChild);

        var svg = d3.select(container)
            .append("svg")
            .attr("width", w)
            .attr("height", h)
            .attr("viewBox", "0 0 " + w + " " + h);

        // Parse dates and values
        var parsed = [];
        for (var i = 0; i < dataPoints.length; i++) {
            var dp = dataPoints[i];
            parsed.push({
                date: new Date(dp.date),
                value: +dp.value,
                ref_low: dp.ref_low != null ? +dp.ref_low : null,
                ref_high: dp.ref_high != null ? +dp.ref_high : null,
            });
        }
        parsed.sort(function(a, b) { return a.date - b.date; });

        // Scales
        var pad = 2;
        var xScale = d3.scaleTime()
            .domain(d3.extent(parsed, function(d) { return d.date; }))
            .range([pad, w - pad]);

        var allValues = parsed.map(function(d) { return d.value; });
        var yMin = d3.min(allValues);
        var yMax = d3.max(allValues);

        // Include ref range in domain if present
        var firstRef = parsed[0];
        if (firstRef.ref_low != null) yMin = Math.min(yMin, firstRef.ref_low);
        if (firstRef.ref_high != null) yMax = Math.max(yMax, firstRef.ref_high);

        // Add small padding to domain
        var yPad = (yMax - yMin) * 0.15 || 1;
        var yScale = d3.scaleLinear()
            .domain([yMin - yPad, yMax + yPad])
            .range([h - pad, pad]);

        // Reference band
        if (opts.showRefBand && firstRef.ref_low != null && firstRef.ref_high != null) {
            svg.append("rect")
                .attr("x", 0)
                .attr("y", yScale(firstRef.ref_high))
                .attr("width", w)
                .attr("height", Math.max(0, yScale(firstRef.ref_low) - yScale(firstRef.ref_high)))
                .attr("fill", opts.refBandColor);
        }

        // Line
        var line = d3.line()
            .x(function(d) { return xScale(d.date); })
            .y(function(d) { return yScale(d.value); })
            .curve(d3.curveMonotoneX);

        svg.append("path")
            .datum(parsed)
            .attr("fill", "none")
            .attr("stroke", opts.color)
            .attr("stroke-width", opts.strokeWidth)
            .attr("d", line);

        // End dot — colored red if latest value is out of range
        var latest = parsed[parsed.length - 1];
        var outOfRange = false;
        if (latest.ref_low != null && latest.value < latest.ref_low) outOfRange = true;
        if (latest.ref_high != null && latest.value > latest.ref_high) outOfRange = true;

        svg.append("circle")
            .attr("cx", xScale(latest.date))
            .attr("cy", yScale(latest.value))
            .attr("r", 2.5)
            .attr("fill", outOfRange ? opts.outOfRangeColor : opts.color);
    },
};
