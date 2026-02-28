/*! 
 * bodymap.js
 * Handles rendering the interactive SVG body map and overlaying MONAI/MedGemma findings.
 */

class BodyMapController {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.patientData = null;
    }

    initialize(patientData) {
        this.patientData = patientData;
        this.isFront = true;
        this.currentLayer = 'skin';

        // 1. Determine gender model to load
        const sex = this.patientData?.patient?.demographics?.biological_sex || 'unspecified';
        this.renderBaseSvg(sex);

        // 2. Map findings
        this.overlayMedicalFindings();

        // Bind Rotation Control
        document.getElementById('view-rotate')?.addEventListener('click', () => {
            this.isFront = !this.isFront;
            this._updateViewPort();
            this.overlayMedicalFindings();
        });

        // Bind Layer Toggle Control
        document.getElementById('view-layer')?.addEventListener('change', (e) => {
            this.currentLayer = e.target.value;
            // Force view to front when utilizing deep layers for now
            if (this.currentLayer !== 'skin') {
                this.isFront = true;
            }
            this._updateViewPort();
            this.overlayMedicalFindings();
        });
    }

    _updateViewPort() {
        const placeholder = document.getElementById('body-map-placeholder');

        if (this.isFront) {
            let bgUrl = 'assets/anatomy.png';
            if (this.currentLayer === 'muscle') bgUrl = 'assets/anatomy_muscle.png';
            if (this.currentLayer === 'skeleton') bgUrl = 'assets/anatomy_skeleton.png';
            if (this.currentLayer === 'organs') bgUrl = 'assets/anatomy_organs.png';

            placeholder.style.background = `url('${bgUrl}') center/contain no-repeat`;
            placeholder.innerHTML = `
                <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style="position: absolute; top:0; left:0; width:100%; height:100%;">
                    <circle id="region-head" cx="50" cy="12" r="8" fill="transparent" class="interactive-region" />
                    <circle id="region-chest" cx="50" cy="30" r="12" fill="transparent" class="interactive-region" />
                    <circle id="region-abdomen" cx="50" cy="48" r="10" fill="transparent" class="interactive-region" />
                </svg>
            `;
        } else {
            placeholder.style.background = "url('assets/anatomy_back.png') center/contain no-repeat";
            placeholder.innerHTML = `
                <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style="position: absolute; top:0; left:0; width:100%; height:100%;">
                    <circle id="region-head-back" cx="50" cy="12" r="8" fill="transparent" class="interactive-region" />
                    <rect id="region-spine" x="48" y="20" width="4" height="25" fill="transparent" class="interactive-region" />
                </svg>
            `;
        }

        // Reattach listeners to newly created SVG nodes
        const viewport = document.getElementById('body-map-viewport');
        if (viewport) {
            this._attachHoverListeners(viewport);
        }
    }

    renderBaseSvg(sex) {
        // High fidelity medical grade rendering serving as background
        const placeholder = document.getElementById('body-map-placeholder');

        placeholder.style.position = 'relative';
        placeholder.style.background = "url('assets/anatomy.png') center/contain no-repeat";
        placeholder.style.opacity = "1";

        placeholder.innerHTML = `
            <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style="position: absolute; top:0; left:0; width:100%; height:100%;">
                <!-- Invisible interaction zones mapped onto the anatomical image -->
                
                <!-- Head / Brain -->
                <circle id="region-head" cx="50" cy="12" r="8" fill="transparent" class="interactive-region" />
                
                <!-- Chest / Lungs / Heart -->
                <circle id="region-chest" cx="50" cy="30" r="12" fill="transparent" class="interactive-region" />
                
                <!-- Abdomen / GI -->
                <circle id="region-abdomen" cx="50" cy="48" r="10" fill="transparent" class="interactive-region" />
                
                <!-- Spine (Central vertical) -->
                <rect id="region-spine" x="48" y="20" width="4" height="25" fill="transparent" class="interactive-region" />
            </svg>
        `;

        const viewport = document.getElementById('body-map-viewport');
        viewport.style.position = 'relative'; // Ensure tooltip scopes here

        let tooltip = document.getElementById('bodymap-tooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'bodymap-tooltip';
            tooltip.style.cssText = "position: absolute; display: none; background: rgba(15, 23, 42, 0.95); border: 1px solid var(--accent); padding: 12px; border-radius: 8px; z-index: 100; pointer-events: none; width: 220px; box-shadow: 0 4px 15px rgba(0,0,0,0.5);";
            viewport.appendChild(tooltip);
        }

        this._attachHoverListeners(viewport);
        this._initPanzoom(placeholder);
    }

    _initPanzoom(elem) {
        if (typeof Panzoom !== 'undefined') {
            this.panzoomInstance = Panzoom(elem, {
                maxScale: 5,
                minScale: 1,
                contain: 'outside',
                cursor: 'grab'
            });

            // Enable mouse wheel zooming
            elem.parentElement.addEventListener('wheel', this.panzoomInstance.zoomWithWheel);

            // Bind UI Controls
            document.getElementById('zoom-in').addEventListener('click', () => {
                this.panzoomInstance.zoomIn();
            });
            document.getElementById('zoom-out').addEventListener('click', () => {
                this.panzoomInstance.zoomOut();
            });
            document.getElementById('zoom-reset').addEventListener('click', () => {
                this.panzoomInstance.reset();
            });

            // Handle cursor styling during drag
            elem.addEventListener('panzoomstart', () => { elem.style.cursor = 'grabbing'; });
            elem.addEventListener('panzoomend', () => { elem.style.cursor = 'grab'; });
        } else {
            console.error("Panzoom library not loaded!");
        }
    }

    overlayMedicalFindings() {
        const imaging = this.patientData?.clinical_timeline?.imaging || [];

        imaging.forEach(scan => {
            const bodyPart = scan.body_part.toLowerCase();

            // Map the parsed medical term to the SVG ID based on perspective
            let targetRegion = null;
            if (this.isFront) {
                if (bodyPart.includes('chest') || bodyPart.includes('lung') || bodyPart.includes('heart')) {
                    targetRegion = document.getElementById('region-chest');
                } else if (bodyPart.includes('head') || bodyPart.includes('brain')) {
                    targetRegion = document.getElementById('region-head');
                } else if (bodyPart.includes('abdomen') || bodyPart.includes('pelvis')) {
                    targetRegion = document.getElementById('region-abdomen');
                }
            } else {
                if (bodyPart.includes('spine') || bodyPart.includes('lumbar') || bodyPart.includes('back')) {
                    targetRegion = document.getElementById('region-spine');
                } else if (bodyPart.includes('head') || bodyPart.includes('brain') || bodyPart.includes('occipital')) {
                    targetRegion = document.getElementById('region-head-back');
                }
            }

            if (targetRegion && scan.findings.length > 0) {
                // Apply a visual pulse/highlight indicating AI found something here
                targetRegion.style.fill = "rgba(16, 185, 129, 0.3)"; // using --accent color
                targetRegion.style.stroke = "var(--accent)";
                targetRegion.style.strokeWidth = "2";
                targetRegion.classList.add('has-findings');

                // Store the finding data on the DOM element for the tooltip
                targetRegion.dataset.findings = JSON.stringify(scan.findings);
                targetRegion.dataset.date = scan.date;
            }
        });
    }

    _attachHoverListeners(placeholder) {
        const tooltip = document.getElementById('bodymap-tooltip');

        document.querySelectorAll('.interactive-region').forEach(el => {
            el.addEventListener('mouseenter', (e) => {
                if (e.target.classList.contains('has-findings')) {
                    // Highlight Area
                    e.target.style.fill = "rgba(16, 185, 129, 0.4)";

                    // Show Tooltip
                    const data = JSON.parse(e.target.dataset.findings);
                    const date = e.target.dataset.date;

                    let findingsHtml = data.map(finding => `
                        <div style="margin-bottom: 8px;">
                            <strong style="color:var(--accent);">${finding.description}</strong>
                            <div style="color:var(--text-muted); font-size: 0.75rem;">MONAI metrics: Vol ${finding.monai_metrics?.volume_mm3}mm³, Conf: ${Math.round(finding.monai_metrics?.confidence * 100)}%</div>
                        </div>
                    `).join('');

                    tooltip.innerHTML = `
                        <div style="font-size: 0.75rem; color:var(--text-muted); margin-bottom:4px;">Scan Date: ${date}</div>
                        ${findingsHtml}
                    `;

                    tooltip.style.display = 'block';
                }
            });

            el.addEventListener('mousemove', (e) => {
                // Pin tooltip to cursor
                const cx = e.clientX;
                const cy = e.clientY;
                // Get container offsets from the fixed viewport
                const rect = viewport.getBoundingClientRect();

                // Position relative to viewport (prevents scaling issues)
                tooltip.style.left = (cx - rect.left + 15) + 'px';
                tooltip.style.top = (cy - rect.top + 15) + 'px';
            });

            el.addEventListener('mouseleave', (e) => {
                if (e.target.classList.contains('has-findings')) {
                    e.target.style.fill = "rgba(16, 185, 129, 0.2)"; // Reset to dim highlight
                }
                tooltip.style.display = 'none';
            });
        });
    }
}
