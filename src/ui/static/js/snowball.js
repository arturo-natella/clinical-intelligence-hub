/**
 * Snowball Differential Diagnostician - D3 Force Graph
 * =====================================================
 * Clinical Intelligence Hub
 *
 * Renders a force-directed network graph where:
 *   - Blue nodes  = patient findings
 *   - Colored circles = candidate conditions (colored by organ system)
 *   - Edge thickness = confidence weight
 *   - Click a condition to see matched/missing findings
 */

var SnowballDx = {

    // State
    _svg: null,
    _simulation: null,
    _overlay: null,
    _graphData: null,
    _isOpen: false,

    // --- PUBLIC ---

    toggle: function() {
        if (this._isOpen) {
            this.close();
        } else {
            this.open();
        }
    },

    open: function() {
        this._ensureOverlay();
        this._overlay.style.display = 'flex';
        this._isOpen = true;
        this._fetchAndRender();
    },

    close: function() {
        if (this._overlay) {
            this._overlay.style.display = 'none';
        }
        this._isOpen = false;
        if (this._simulation) {
            this._simulation.stop();
        }
    },

    // --- OVERLAY SETUP ---

    _ensureOverlay: function() {
        if (this._overlay) return;

        var overlay = document.createElement('div');
        overlay.id = 'snowball-overlay';
        overlay.className = 'snowball-overlay';

        var container = document.createElement('div');
        container.className = 'snowball-container';

        // Header
        var header = document.createElement('div');
        header.className = 'snowball-header';

        var title = document.createElement('h3');
        title.textContent = 'Snowball Differential Diagnostician';
        header.appendChild(title);

        var subtitle = document.createElement('span');
        subtitle.className = 'snowball-subtitle';
        subtitle.textContent = 'Helping you understand your records and partner with your doctor';
        header.appendChild(subtitle);

        var closeBtn = document.createElement('button');
        closeBtn.className = 'snowball-close';
        closeBtn.textContent = '\u00D7';
        closeBtn.onclick = function() { SnowballDx.close(); };
        header.appendChild(closeBtn);

        container.appendChild(header);

        // Body
        var body = document.createElement('div');
        body.className = 'snowball-body';

        var graphDiv = document.createElement('div');
        graphDiv.className = 'snowball-graph';
        graphDiv.id = 'snowball-graph';
        body.appendChild(graphDiv);

        var detailDiv = document.createElement('div');
        detailDiv.className = 'snowball-detail';
        detailDiv.id = 'snowball-detail';
        var emptyMsg = document.createElement('div');
        emptyMsg.className = 'snowball-detail-empty';
        emptyMsg.textContent = 'Click a condition to explore what your records suggest';
        detailDiv.appendChild(emptyMsg);
        body.appendChild(detailDiv);

        container.appendChild(body);

        // Legend
        var legend = document.createElement('div');
        legend.className = 'snowball-legend';
        legend.id = 'snowball-legend';
        container.appendChild(legend);

        // Partner approach note — this frames the tool's purpose, not a disclaimer
        var disc = document.createElement('div');
        disc.className = 'snowball-partner-note';

        var noteLine1 = document.createElement('div');
        noteLine1.className = 'snowball-partner-headline';
        noteLine1.textContent = 'This is your starting point, not the finish line.';
        disc.appendChild(noteLine1);

        var noteLine2 = document.createElement('div');
        noteLine2.className = 'snowball-partner-body';
        noteLine2.textContent = 'These results give you an idea of what might be going on based on your records. Bring them to your doctor to explore which possibilities are reasonable and medically sound. This tool helps you start the conversation and become an active partner in your medical journey.';
        disc.appendChild(noteLine2);
        container.appendChild(disc);

        overlay.appendChild(container);
        document.body.appendChild(overlay);
        this._overlay = overlay;
    },

    // --- DATA ---

    _fetchAndRender: function() {
        var self = this;
        var graphEl = document.getElementById('snowball-graph');
        if (!graphEl) return;

        graphEl.textContent = '';
        var loading = document.createElement('div');
        loading.className = 'snowball-loading';
        loading.textContent = 'Analyzing findings...';
        graphEl.appendChild(loading);

        fetch('/api/snowball-diagnoses', { method: 'POST' })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                self._graphData = data;
                if (!data.nodes || data.nodes.length === 0) {
                    graphEl.textContent = '';
                    var empty = document.createElement('div');
                    empty.className = 'snowball-empty';
                    var p1 = document.createElement('p');
                    p1.textContent = 'No differential diagnoses to display.';
                    var p2 = document.createElement('p');
                    p2.textContent = 'Upload medical records first, then return here.';
                    empty.appendChild(p1);
                    empty.appendChild(p2);
                    graphEl.appendChild(empty);
                    return;
                }
                self._renderGraph(data);
                self._renderLegend(data);
                self._renderRankedList(data.ranked_conditions || []);
            })
            .catch(function(err) {
                graphEl.textContent = '';
                var errDiv = document.createElement('div');
                errDiv.className = 'snowball-empty';
                errDiv.textContent = 'Error loading data: ' + err.message;
                graphEl.appendChild(errDiv);
            });
    },

    // --- D3 GRAPH ---

    _renderGraph: function(data) {
        var container = document.getElementById('snowball-graph');
        if (!container) return;
        container.textContent = '';

        var width = container.clientWidth || 600;
        var height = container.clientHeight || 500;

        var svg = d3.select(container)
            .append('svg')
            .attr('width', width)
            .attr('height', height)
            .attr('viewBox', [0, 0, width, height]);

        this._svg = svg;

        // Zoom
        var g = svg.append('g');
        svg.call(d3.zoom()
            .scaleExtent([0.3, 4])
            .on('zoom', function(event) {
                g.attr('transform', event.transform);
            }));

        // Force simulation
        var simulation = d3.forceSimulation(data.nodes)
            .force('link', d3.forceLink(data.edges)
                .id(function(d) { return d.id; })
                .distance(function(d) { return d.dashed ? 120 : 80; })
                .strength(function(d) { return d.dashed ? 0.1 : 0.3; }))
            .force('charge', d3.forceManyBody().strength(-200))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(function(d) {
                return (d.radius || 10) + 5;
            }));

        this._simulation = simulation;

        // Edges
        var link = g.append('g')
            .attr('class', 'snowball-links')
            .selectAll('line')
            .data(data.edges)
            .enter().append('line')
            .attr('stroke', function(d) { return d.dashed ? '#555' : '#667'; })
            .attr('stroke-width', function(d) { return Math.max(1, d.weight * 1.5); })
            .attr('stroke-dasharray', function(d) { return d.dashed ? '4,4' : null; })
            .attr('stroke-opacity', 0.5);

        // Nodes
        var self = this;
        var node = g.append('g')
            .attr('class', 'snowball-nodes')
            .selectAll('g')
            .data(data.nodes)
            .enter().append('g')
            .attr('class', 'snowball-node')
            .style('cursor', 'pointer')
            .call(d3.drag()
                .on('start', function(event, d) {
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    d.fx = d.x;
                    d.fy = d.y;
                })
                .on('drag', function(event, d) {
                    d.fx = event.x;
                    d.fy = event.y;
                })
                .on('end', function(event, d) {
                    if (!event.active) simulation.alphaTarget(0);
                    d.fx = null;
                    d.fy = null;
                }))
            .on('click', function(event, d) {
                if (d.type === 'condition') {
                    self._showDetail(d);
                }
            });

        // Circle for each node
        node.append('circle')
            .attr('r', function(d) { return d.radius || 8; })
            .attr('fill', function(d) {
                if (d.type === 'finding') return '#3498db';
                if (d.ruled_out) return '#7f8c8d';
                if (d.is_expanded) return d.color ? self._lighten(d.color) : '#bdc3c7';
                return d.color || '#e67e22';
            })
            .attr('stroke', function(d) {
                if (d.type === 'finding') return '#2980b9';
                if (d.ruled_out) return '#555';
                return d.color || '#d35400';
            })
            .attr('stroke-width', function(d) {
                return d.type === 'condition' ? 2 : 1;
            })
            .attr('opacity', function(d) {
                if (d.ruled_out) return 0.4;
                if (d.is_expanded) return 0.6;
                return 0.9;
            });

        // Labels
        node.append('text')
            .text(function(d) { return d.label; })
            .attr('dx', function(d) { return (d.radius || 8) + 4; })
            .attr('dy', 4)
            .attr('font-size', function(d) {
                return d.type === 'condition' ? '11px' : '9px';
            })
            .attr('fill', '#ccc')
            .attr('font-weight', function(d) {
                return d.type === 'condition' ? '600' : '400';
            });

        // Match tier badge on condition nodes (qualitative, not percentage)
        node.filter(function(d) { return d.type === 'condition' && d.confidence > 0; })
            .append('text')
            .text(function(d) { return self._matchTier(d.confidence).label; })
            .attr('dy', function(d) { return -(d.radius || 12) - 4; })
            .attr('text-anchor', 'middle')
            .attr('font-size', '8px')
            .attr('fill', function(d) { return self._matchTier(d.confidence).color; })
            .attr('font-weight', '600');

        // Tick
        simulation.on('tick', function() {
            link
                .attr('x1', function(d) { return d.source.x; })
                .attr('y1', function(d) { return d.source.y; })
                .attr('x2', function(d) { return d.target.x; })
                .attr('y2', function(d) { return d.target.y; });

            node.attr('transform', function(d) {
                return 'translate(' + d.x + ',' + d.y + ')';
            });
        });
    },

    _lighten: function(hex) {
        var r = parseInt(hex.slice(1, 3), 16);
        var gg = parseInt(hex.slice(3, 5), 16);
        var b = parseInt(hex.slice(5, 7), 16);
        r = Math.min(255, r + 80);
        gg = Math.min(255, gg + 80);
        b = Math.min(255, b + 80);
        return '#' + [r, gg, b].map(function(c) {
            return c.toString(16).padStart(2, '0');
        }).join('');
    },

    // --- MATCH TIER HELPERS ---

    /**
     * Convert raw confidence score to a qualitative tier.
     * This avoids patients misinterpreting match ratios as
     * diagnosis probabilities (e.g., "39%" ≠ "39% chance of IBD").
     */
    _matchTier: function(confidence) {
        var pct = confidence * 100;
        if (pct >= 60) return { label: "Strong match", color: "#e06c8a", level: 4 };
        if (pct >= 40) return { label: "Moderate match", color: "#d4a84b", level: 3 };
        if (pct >= 20) return { label: "Possible", color: "#3498db", level: 2 };
        return { label: "Weak match", color: "#7f8c8d", level: 1 };
    },

    /**
     * Build a "why" summary from matched findings for the ranked list toggle.
     */
    _matchWhy: function(d) {
        var matched = d.matched || [];
        var expected = d.expected_count || 0;
        if (matched.length === 0) return "";
        var names = matched.slice(0, 4).join(", ");
        if (matched.length > 4) names += " +" + (matched.length - 4) + " more";
        return "Your records show " + names + " \u2014 " + matched.length + " of " + expected + " findings typically linked to this.";
    },

    // --- DETAIL PANEL ---

    _showDetail: function(d) {
        var panel = document.getElementById('snowball-detail');
        if (!panel) return;

        // Clear panel
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        var card = document.createElement('div');
        card.className = 'snowball-detail-card';

        // Title
        var titleEl = document.createElement('div');
        titleEl.className = 'snowball-detail-title';
        titleEl.textContent = d.label;
        card.appendChild(titleEl);

        // Category
        var catEl = document.createElement('div');
        catEl.className = 'snowball-detail-category';
        catEl.style.color = d.color || '#95a5a6';
        catEl.textContent = (d.category || '').replace('_', ' ');
        card.appendChild(catEl);

        // Match tier badge (qualitative, not percentage)
        var tier = this._matchTier(d.confidence);

        var tierBadge = document.createElement('div');
        tierBadge.className = 'snowball-tier-badge';
        tierBadge.style.color = tier.color;
        tierBadge.style.borderColor = tier.color;
        tierBadge.textContent = tier.label;
        card.appendChild(tierBadge);

        // Confidence bar (uses tier color, no percentage label)
        var confidencePct = Math.round(d.confidence * 100);
        var barWrap = document.createElement('div');
        barWrap.className = 'snowball-confidence-bar';
        var barFill = document.createElement('div');
        barFill.className = 'snowball-confidence-fill';
        barFill.style.width = confidencePct + '%';
        barFill.style.background = tier.color;
        barWrap.appendChild(barFill);
        card.appendChild(barWrap);

        // Combined why + stat — one clear explanation
        var matched = d.matched || [];
        if (matched.length > 0) {
            var whyStat = document.createElement('div');
            whyStat.className = 'snowball-detail-why';
            var names = matched.slice(0, 5).join(', ');
            if (matched.length > 5) names += ' +' + (matched.length - 5) + ' more';
            whyStat.textContent = 'Your records show ' + names + ' \u2014 that\u2019s ' + d.matched_count + ' of ' + d.expected_count + ' findings typically linked to this condition.';
            card.appendChild(whyStat);
        }

        // Ruled out — framed gently
        if (d.ruled_out) {
            var warn = document.createElement('div');
            warn.className = 'snowball-ruled-out';
            warn.textContent = 'Your records contain evidence that may work against this possibility.';
            card.appendChild(warn);
        }

        // Additional tests — shown with clear purpose + printout promise
        if (d.missing && d.missing.length > 0) {
            var secTitle = document.createElement('div');
            secTitle.className = 'snowball-section-title';
            secTitle.textContent = 'Additional tests that could help your doctor confirm or rule this out:';
            card.appendChild(secTitle);

            var list = document.createElement('ul');
            list.className = 'snowball-missing-list';
            var showCount = Math.min(d.missing.length, 4);
            for (var i = 0; i < showCount; i++) {
                var li = document.createElement('li');
                li.textContent = d.missing[i];
                list.appendChild(li);
            }
            if (d.missing.length > 4) {
                var more = document.createElement('li');
                more.className = 'snowball-missing-more';
                more.textContent = '+ ' + (d.missing.length - 4) + ' more';
                list.appendChild(more);
            }
            card.appendChild(list);

            // Direct connection: these tests → your printout
            var reassure = document.createElement('div');
            reassure.className = 'snowball-reassure';
            reassure.textContent = "I\u2019m adding these to your doctor visit printout so you can bring them up together.";
            card.appendChild(reassure);
        } else {
            // No missing tests — general reassurance
            var reassure = document.createElement('div');
            reassure.className = 'snowball-reassure';
            reassure.textContent = "I\u2019m noting all of this for your doctor visit printout.";
            card.appendChild(reassure);
        }

        panel.appendChild(card);
    },

    // --- LEGEND ---

    _renderLegend: function(data) {
        var el = document.getElementById('snowball-legend');
        if (!el) return;

        while (el.firstChild) el.removeChild(el.firstChild);

        // Finding dot
        var findingItem = document.createElement('span');
        findingItem.className = 'snowball-legend-item';
        var findingDot = document.createElement('span');
        findingDot.className = 'snowball-dot';
        findingDot.style.background = '#3498db';
        findingItem.appendChild(findingDot);
        findingItem.appendChild(document.createTextNode(' Finding'));
        el.appendChild(findingItem);

        // Unique categories
        var seen = {};
        for (var i = 0; i < data.nodes.length; i++) {
            var n = data.nodes[i];
            if (n.type === 'condition' && n.category && !seen[n.category]) {
                seen[n.category] = true;
                var item = document.createElement('span');
                item.className = 'snowball-legend-item';
                var dot = document.createElement('span');
                dot.className = 'snowball-dot';
                dot.style.background = n.color || '#95a5a6';
                item.appendChild(dot);
                var label = n.category.charAt(0).toUpperCase() + n.category.slice(1);
                item.appendChild(document.createTextNode(' ' + label));
                el.appendChild(item);
            }
        }
    },

    // --- RANKED LIST ---

    _renderRankedList: function(ranked) {
        var panel = document.getElementById('snowball-detail');
        if (!panel || ranked.length === 0) return;

        // Clear existing
        while (panel.firstChild) panel.removeChild(panel.firstChild);

        var title = document.createElement('div');
        title.className = 'snowball-ranked-title';
        title.textContent = 'Ranked Differentials';
        panel.appendChild(title);

        var rankedNote = document.createElement('div');
        rankedNote.className = 'snowball-ranked-note';
        rankedNote.textContent = 'Based on your records, here are conditions worth exploring with your doctor.';
        panel.appendChild(rankedNote);

        var top = ranked.slice(0, 10);
        var self = this;
        for (var i = 0; i < top.length; i++) {
            (function(c) {
                var tier = self._matchTier(c.confidence);
                var pct = Math.round(c.confidence * 100);

                var item = document.createElement('div');
                item.className = 'snowball-ranked-item';
                item.onclick = function() { self._showDetail(c); };

                // Top row: name + tier + why toggle
                var row = document.createElement('div');
                row.className = 'snowball-ranked-row';

                var labelSpan = document.createElement('span');
                labelSpan.className = 'snowball-ranked-label';
                labelSpan.textContent = c.label;
                row.appendChild(labelSpan);

                var tierSpan = document.createElement('span');
                tierSpan.className = 'snowball-ranked-tier';
                tierSpan.style.color = tier.color;
                tierSpan.textContent = tier.label;
                row.appendChild(tierSpan);

                item.appendChild(row);

                // Expandable "why" box — collapsed by default
                var why = self._matchWhy(c);
                if (why) {
                    var whyToggle = document.createElement('button');
                    whyToggle.className = 'snowball-why-toggle';
                    whyToggle.textContent = 'Why?';
                    row.appendChild(whyToggle);

                    var whyBox = document.createElement('div');
                    whyBox.className = 'snowball-ranked-why';
                    whyBox.style.display = 'none';
                    whyBox.textContent = why;
                    item.appendChild(whyBox);

                    (function(btn, box) {
                        btn.onclick = function(e) {
                            e.stopPropagation();
                            if (box.style.display === 'none') {
                                box.style.display = 'block';
                                btn.textContent = 'Hide';
                            } else {
                                box.style.display = 'none';
                                btn.textContent = 'Why?';
                            }
                        };
                    })(whyToggle, whyBox);
                }

                panel.appendChild(item);
            })(top[i]);
        }
    },
};
