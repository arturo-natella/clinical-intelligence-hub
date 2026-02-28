// research.js - Handles the Answers & Interventions Panel logic

document.addEventListener('DOMContentLoaded', () => {
    // We would normally fetch this from the backend. 
    // For the UI sandbox preview, we simulate the fetch response format.
    const fdaFeed = document.getElementById('fda-alerts-feed');
    const redditFeed = document.getElementById('reddit-alerts-feed');
    const questionsFeed = document.getElementById('questions-feed');

    window.updateResearchInsights = function (profileData) {
        if (!profileData || !profileData.ai_analysis) return;

        const analysis = profileData.ai_analysis;

        // 1. Populate FDA / Clinical Validated Flags
        if (analysis.flags && analysis.flags.length > 0) {
            fdaFeed.innerHTML = ''; // Clear placeholder
            analysis.flags.forEach(flag => {
                const flagEl = document.createElement('div');
                flagEl.className = 'question-card';
                flagEl.innerHTML = `
                    <strong>${flag.alert_type}:</strong> ${flag.description}
                    <br>
                    <span class="citation-tag">Source: FDA / Clinical Guidelines</span>
                `;
                fdaFeed.appendChild(flagEl);
            });
        }

        // 2. Populate Community Correlates (The Sizeable Reddit citations)
        if (analysis.community_insights && analysis.community_insights.length > 0) {
            redditFeed.innerHTML = ''; // Clear placeholder
            analysis.community_insights.forEach(insight => {
                const insightEl = document.createElement('div');
                insightEl.className = 'question-card warning-card'; // Adds orange border for unverified data

                // If the cross-disciplinary check was successful, format it differently
                const crossDisciplineHtml = insight.cross_disciplinary_context
                    ? `<div style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.1);">
                           <strong style="color: var(--primary); font-size: 0.85rem;">🧬 Emerging Science Link:</strong>
                           <div style="font-size: 0.85rem; color: var(--text-main);">${insight.cross_disciplinary_context}</div>
                       </div>`
                    : '';

                insightEl.innerHTML = `
                    <strong>Observation:</strong> Patients taking ${insight.medication} also report ${insight.correlated_symptom}.
                    <br>
                    <span class="citation-tag" style="background: rgba(245, 158, 11, 0.1); color: #f59e0b;">
                        Source: ${insight.source} (${insight.upvotes}+ Upvotes)
                    </span>
                    ${crossDisciplineHtml}
                `;
                redditFeed.appendChild(insightEl);
            });
        } else {
            // Let the user know the pipeline has run, even if no insights were found
            redditFeed.innerHTML = '<div style="font-size: 0.9rem; color: var(--text-muted); font-style: italic;">No significant community correlates found (>1000 reports).</div>';
        }

        // 3. Populate The "3 Questions for Your Doctor" (Citation Backed)
        if (analysis.questions_for_doctor && analysis.questions_for_doctor.length > 0) {
            questionsFeed.innerHTML = ''; // Clear placeholder
            analysis.questions_for_doctor.forEach((q, idx) => {
                const qEl = document.createElement('div');
                qEl.className = 'question-card';
                qEl.innerHTML = `
                    <strong>${idx + 1}.</strong> ${q.question}
                    <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 8px;">
                        <em>Context:</em> ${q.reasoning}
                    </div>
                    <span class="citation-tag">Citation: ${q.citations}</span>
                `;
                questionsFeed.appendChild(qEl);
            });
        }
    };
});
