/*!
 * timeline.js
 * Handles the logic for the correlative health timeline, scrubbing, and data plotting.
 */

class TimelineController {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.patientData = null;
        this.tracks = {
            labs: document.getElementById('track-labs'),
            meds: document.getElementById('track-meds'),
            symptoms: document.getElementById('track-symptoms')
        };
        this.minDate = new Date();
        this.maxDate = new Date();
    }

    initialize(patientData) {
        this.patientData = patientData;

        // 1. Find the earliest and latest dates across all records
        this._calculateDateRange();

        // 2. Draw dots on the tracks
        this._plotLabs();
        this._plotMeds();
        this._plotSymptoms();

        // 3. Attach slider logic
        this._setupScrubber();
    }

    _calculateDateRange() {
        const d = this.patientData.clinical_timeline;
        let allDates = [];

        d.medications.forEach(m => { allDates.push(new Date(m.start_date)); });
        d.labs.forEach(l => { allDates.push(new Date(l.date)); });
        d.imaging.forEach(i => { allDates.push(new Date(i.date)); });
        d.symptoms_and_diary.forEach(s => { allDates.push(new Date(s.date)); });

        if (allDates.length > 0) {
            this.minDate = new Date(Math.min(...allDates));
            this.maxDate = new Date(Math.max(...allDates));
        }
    }

    _calculatePositionPercent(dateString) {
        /* Utility to map a date to a percentage width on the timeline scale */
        const targetDate = new Date(dateString);
        const totalSpan = this.maxDate - this.minDate;
        if (totalSpan === 0) return 50; // Everything on one day

        const currentSpan = targetDate - this.minDate;
        return (currentSpan / totalSpan) * 100;
    }

    _plotLabs() {
        const labs = this.patientData?.clinical_timeline?.labs || [];
        labs.forEach(lab => {
            const pct = this._calculatePositionPercent(lab.date);
            const dot = document.createElement('div');
            dot.className = 'timeline-point lab-point';
            dot.style.cssText = `
                position: absolute;
                left: ${pct}%;
                bottom: 20px;
                width: 10px; height: 10px;
                background: ${lab.flag === 'High' ? '#ef4444' : 'var(--primary)'};
                border-radius: 50%;
                transform: translateX(-50%);
                cursor: pointer;
            `;
            dot.title = `${lab.name}: ${lab.value} ${lab.unit} (${lab.date})`;
            this.tracks.labs.appendChild(dot);
        });
    }

    _plotMeds() {
        // Advanced logic: A line that represents duration, not just a dot.
        const meds = this.patientData?.clinical_timeline?.medications || [];
        meds.forEach(med => {
            const startPct = this._calculatePositionPercent(med.start_date);

            // If active, map to the max date (current day)
            const endDateToUse = med.status === 'active' ? this.maxDate.toISOString() : med.end_date;
            const endPct = this._calculatePositionPercent(endDateToUse);

            const bar = document.createElement('div');
            bar.className = 'timeline-span med-span';
            bar.style.cssText = `
                position: absolute;
                left: ${startPct}%;
                width: ${endPct - startPct}%;
                bottom: 20px;
                height: 8px;
                background: rgba(16, 185, 129, 0.4); /* --accent */
                border-radius: 4px;
                cursor: pointer;
            `;
            bar.title = `${med.name} (${med.dosage}) - ${med.status}`;
            this.tracks.meds.appendChild(bar);
        });
    }

    _plotSymptoms() {
        const symptoms = this.patientData?.clinical_timeline?.symptoms_and_diary || [];
        symptoms.forEach(sym => {
            const pct = this._calculatePositionPercent(sym.date);
            const dot = document.createElement('div');
            dot.className = 'timeline-point sym-point';
            dot.style.cssText = `
                position: absolute;
                left: ${pct}%;
                bottom: 20px;
                width: 12px; height: 12px;
                background: #f59e0b; /* Amber warning color */
                border-radius: 2px; /* Square for diary logs */
                transform: translateX(-50%) rotate(45deg); /* Diamond shape */
                cursor: pointer;
            `;
            // E.g., "Patient Log (Severity 5): Persistent dry cough"
            dot.title = `[${sym.date}] ${sym.type} (Severity ${sym.severity}): ${sym.description}`;
            this.tracks.symptoms.appendChild(dot);
        });
    }

    _setupScrubber() {
        const slider = this.container.querySelector('input[type="range"]');

        slider.addEventListener('input', (e) => {
            const pct = e.target.value;
            // The "Magic" feature: Highlight points near this date percentage across all tracks.
            document.querySelectorAll('.timeline-point, .timeline-span').forEach(el => {
                const elLeftPct = parseFloat(el.style.left);
                const elWidth = parseFloat(el.style.width || "0");

                // If it's a point within ~3% of the scrubber, or an active med span that covers the scrubber
                if (Math.abs(elLeftPct - pct) < 3 || (pct >= elLeftPct && pct <= (elLeftPct + elWidth))) {
                    el.style.opacity = "1";
                    el.style.boxShadow = "0 0 10px white";
                } else {
                    el.style.opacity = "0.3";
                    el.style.boxShadow = "none";
                }
            });
        });
    }
}
