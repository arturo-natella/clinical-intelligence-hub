"""
Clinical Intelligence Hub — Feature 13: Symptom Analytics Engine

Deep statistical analysis of symptom data. Returns visualization-ready
structures for D3.js charts in the frontend.

Analyses:
  1. Symptom-to-symptom correlations (Jaccard co-occurrence + lag)
  2. Calendar heatmap data (episode density per day, 12 months)
  3. Time-of-day × day-of-week heatmap (4×7 grid)
  4. Counter-evidence success rates + verdict
  5. Trigger frequency ranking
  6. Severity distribution per symptom
  7. AI qualitative insights (Gemini → Ollama → rule-based fallback)
"""

import logging
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger("CIH-SymptomAnalytics")


# ── Verdict Thresholds ────────────────────────────────────────

# Scale counters: avg < 2.0/5 = "Strongly contradicts"
#                 avg 2.0-3.0 = "Inconclusive"
#                 avg > 3.0   = "Supports claim"
SCALE_THRESHOLDS = {
    "strongly_contradicts": (0.0, 2.0),
    "inconclusive": (2.0, 3.0),
    "supports_claim": (3.0, 5.1),
}

# Yes/No counters: <30% yes = "Strongly contradicts"
#                  30-60% = "Inconclusive"
#                  >60% = "Supports claim"
YESNO_THRESHOLDS = {
    "strongly_contradicts": (0.0, 0.30),
    "inconclusive": (0.30, 0.60),
    "supports_claim": (0.60, 1.01),
}


class SymptomAnalytics:
    """Deep analytics on symptom data."""

    def analyze(
        self,
        symptoms: list,
        medications: list = None,
    ) -> dict:
        """
        Run all analytics on symptom data.

        Args:
            symptoms: List of symptom dicts from clinical_timeline.symptoms
            medications: Optional list of medication dicts for correlation

        Returns:
            Dict with all analytics ready for D3 visualization.
        """
        if not symptoms:
            return self._empty_result()

        return {
            "correlations": self._symptom_correlations(symptoms),
            "calendar_heatmap": self._calendar_heatmap(symptoms),
            "time_heatmap": self._time_of_day_heatmap(symptoms),
            "counter_scorecards": self._counter_scorecards(symptoms),
            "trigger_analysis": self._trigger_analysis(symptoms),
            "severity_distribution": self._severity_distribution(symptoms),
            "summary": self._summary_stats(symptoms),
        }

    def analyze_single(
        self,
        symptom: dict,
    ) -> dict:
        """Detailed analytics for one symptom."""
        if not symptom:
            return {}

        return {
            "calendar_heatmap": self._calendar_heatmap([symptom]),
            "time_heatmap": self._time_of_day_heatmap([symptom]),
            "counter_scorecards": self._counter_scorecards([symptom]),
            "trigger_analysis": self._trigger_analysis([symptom]),
            "severity_distribution": self._severity_distribution([symptom]),
            "episode_timeline": self._episode_timeline(symptom),
        }

    # ── 1. Symptom-to-Symptom Correlations ────────────────────

    def _symptom_correlations(self, symptoms: list) -> dict:
        """
        Co-occurrence matrix: when symptom A flares, does B follow
        within 24-48 hours? Returns Jaccard similarity + lag analysis.
        """
        if len(symptoms) < 2:
            return {"pairs": [], "matrix": []}

        # Build date sets per symptom (episode dates)
        date_sets = {}
        for s in symptoms:
            name = s.get("symptom_name", "Unknown")
            dates = set()
            for ep in s.get("episodes", []):
                ep_date = self._parse_date(ep.get("episode_date"))
                if ep_date:
                    dates.add(ep_date)
                    # Also include ±1 day for co-occurrence window
                    dates.add(ep_date + timedelta(days=1))
                    dates.add(ep_date - timedelta(days=1))
            date_sets[name] = dates

        # Jaccard similarity between all pairs
        names = list(date_sets.keys())
        pairs = []
        matrix = []

        for i, name_a in enumerate(names):
            row = []
            for j, name_b in enumerate(names):
                if i == j:
                    row.append(1.0)
                    continue

                set_a = date_sets[name_a]
                set_b = date_sets[name_b]
                union = len(set_a | set_b)
                if union > 0:
                    jaccard = len(set_a & set_b) / union
                else:
                    jaccard = 0.0
                row.append(round(jaccard, 3))

                # Only add pair once (i < j)
                if i < j:
                    # Lag analysis: avg days between A and B episodes
                    lag = self._compute_lag(
                        symptoms[i], symptoms[j]
                    )
                    pairs.append({
                        "symptom_a": name_a,
                        "symptom_b": name_b,
                        "jaccard": round(jaccard, 3),
                        "avg_lag_days": lag,
                    })

            matrix.append(row)

        return {
            "names": names,
            "matrix": matrix,
            "pairs": sorted(pairs, key=lambda p: p["jaccard"], reverse=True),
        }

    def _compute_lag(self, symptom_a: dict, symptom_b: dict) -> Optional[float]:
        """Average lag in days between symptom A and closest symptom B episode."""
        dates_a = []
        for ep in symptom_a.get("episodes", []):
            d = self._parse_date(ep.get("episode_date"))
            if d:
                dates_a.append(d)

        dates_b = []
        for ep in symptom_b.get("episodes", []):
            d = self._parse_date(ep.get("episode_date"))
            if d:
                dates_b.append(d)

        if not dates_a or not dates_b:
            return None

        # For each A episode, find closest B episode
        lags = []
        for da in dates_a:
            min_lag = min(abs((db - da).days) for db in dates_b)
            if min_lag <= 7:  # Only count if within a week
                lags.append(min_lag)

        return round(sum(lags) / len(lags), 1) if lags else None

    # ── 2. Calendar Heatmap ───────────────────────────────────

    def _calendar_heatmap(self, symptoms: list) -> list:
        """
        GitHub-style contribution grid per symptom. Episode density
        per day over the past 12 months.
        """
        today = date.today()
        year_ago = today - timedelta(days=365)
        result = []

        for s in symptoms:
            name = s.get("symptom_name", "Unknown")
            day_counts = defaultdict(int)

            for ep in s.get("episodes", []):
                ep_date = self._parse_date(ep.get("episode_date"))
                if ep_date and year_ago <= ep_date <= today:
                    day_counts[ep_date.isoformat()] += 1

            # Build full year grid
            days = []
            current = year_ago
            while current <= today:
                iso = current.isoformat()
                days.append({
                    "date": iso,
                    "count": day_counts.get(iso, 0),
                    "weekday": current.weekday(),  # 0=Mon, 6=Sun
                    "week": current.isocalendar()[1],
                })
                current += timedelta(days=1)

            max_count = max((d["count"] for d in days), default=0)

            result.append({
                "symptom_name": name,
                "symptom_id": s.get("symptom_id", ""),
                "days": days,
                "max_count": max_count,
                "total_episodes": sum(d["count"] for d in days),
            })

        return result

    # ── 3. Time-of-Day Heatmap ────────────────────────────────

    def _time_of_day_heatmap(self, symptoms: list) -> list:
        """
        4×7 grid: (morning/afternoon/evening/night) × (Mon-Sun).
        Episode counts per cell.
        """
        time_slots = ["morning", "afternoon", "evening", "night"]
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        result = []

        for s in symptoms:
            name = s.get("symptom_name", "Unknown")
            grid = [[0] * 7 for _ in range(4)]  # 4 time slots × 7 days

            for ep in s.get("episodes", []):
                ep_date = self._parse_date(ep.get("episode_date"))
                time_str = (ep.get("time_of_day") or "").lower().strip()

                if not ep_date:
                    continue

                weekday = ep_date.weekday()  # 0=Mon, 6=Sun

                if time_str in time_slots:
                    slot_idx = time_slots.index(time_str)
                else:
                    slot_idx = 0  # Default to morning if unknown

                grid[slot_idx][weekday] += 1

            # Find peak
            max_val = 0
            peak_cell = None
            for ti in range(4):
                for di in range(7):
                    if grid[ti][di] > max_val:
                        max_val = grid[ti][di]
                        peak_cell = f"{time_slots[ti]}, {day_names[di]}"

            result.append({
                "symptom_name": name,
                "symptom_id": s.get("symptom_id", ""),
                "grid": grid,
                "time_slots": time_slots,
                "day_names": day_names,
                "max_count": max_val,
                "peak": peak_cell,
            })

        return result

    # ── 4. Counter-Evidence Scorecards ────────────────────────

    def _counter_scorecards(self, symptoms: list) -> list:
        """
        Per counter definition: aggregate statistics + verdict.
        The killer stats for doctor visits.
        """
        result = []

        for s in symptoms:
            name = s.get("symptom_name", "Unknown")
            episodes = s.get("episodes", [])

            for counter in s.get("counter_definitions", []):
                counter_id = counter.get("counter_id", "")
                doctor_claim = counter.get("doctor_claim", "Unknown")
                measure_type = counter.get("measure_type", "scale")
                archived = counter.get("archived", False)

                # Collect values from episodes
                values = []
                for ep in episodes:
                    cv = ep.get("counter_values", {})
                    val = cv.get(counter_id)
                    if val is not None:
                        values.append(val)

                if not values:
                    result.append({
                        "symptom_name": name,
                        "symptom_id": s.get("symptom_id", ""),
                        "counter_id": counter_id,
                        "doctor_claim": doctor_claim,
                        "measure_type": measure_type,
                        "archived": archived,
                        "episode_count": 0,
                        "verdict": "insufficient_data",
                        "verdict_label": "Not enough data yet",
                    })
                    continue

                scorecard = {
                    "symptom_name": name,
                    "symptom_id": s.get("symptom_id", ""),
                    "counter_id": counter_id,
                    "doctor_claim": doctor_claim,
                    "measure_type": measure_type,
                    "archived": archived,
                    "episode_count": len(values),
                }

                if measure_type == "scale":
                    numeric = [float(v) for v in values if _is_numeric(v)]
                    if numeric:
                        avg = sum(numeric) / len(numeric)
                        scorecard.update({
                            "mean": round(avg, 2),
                            "median": round(sorted(numeric)[len(numeric) // 2], 2),
                            "std": round(_std(numeric), 2),
                            "min": min(numeric),
                            "max": max(numeric),
                            "distribution": self._scale_distribution(numeric),
                        })
                        # Verdict
                        for verdict_key, (lo, hi) in SCALE_THRESHOLDS.items():
                            if lo <= avg < hi:
                                scorecard["verdict"] = verdict_key
                                break
                    else:
                        scorecard["verdict"] = "insufficient_data"

                elif measure_type == "yes_no":
                    yes_count = sum(1 for v in values if v is True or v == "true" or v == 1)
                    no_count = len(values) - yes_count
                    pct_yes = yes_count / len(values)

                    scorecard.update({
                        "yes_count": yes_count,
                        "no_count": no_count,
                        "pct_yes": round(pct_yes * 100, 1),
                        "pct_no": round((1 - pct_yes) * 100, 1),
                    })
                    # Verdict
                    for verdict_key, (lo, hi) in YESNO_THRESHOLDS.items():
                        if lo <= pct_yes < hi:
                            scorecard["verdict"] = verdict_key
                            break

                elif measure_type == "free_text":
                    # Word frequency for word cloud
                    all_text = " ".join(str(v) for v in values)
                    words = re.findall(r'\b[a-zA-Z]{3,}\b', all_text.lower())
                    word_freq = Counter(words).most_common(20)
                    scorecard.update({
                        "word_frequencies": [
                            {"word": w, "count": c} for w, c in word_freq
                        ],
                    })
                    scorecard["verdict"] = "review_text"

                # Generate verdict label
                verdict_labels = {
                    "strongly_contradicts": "Strongly contradicts",
                    "inconclusive": "Inconclusive",
                    "supports_claim": "Supports claim",
                    "insufficient_data": "Not enough data yet",
                    "review_text": "Review text entries",
                }
                scorecard["verdict_label"] = verdict_labels.get(
                    scorecard.get("verdict", ""), "Unknown"
                )

                result.append(scorecard)

        return result

    def _scale_distribution(self, values: list) -> list:
        """Count episodes at each scale level 1-5."""
        dist = [0] * 5
        for v in values:
            idx = max(0, min(4, int(round(v)) - 1))
            dist[idx] += 1
        return [{"level": i + 1, "count": dist[i]} for i in range(5)]

    # ── 5. Trigger Analysis ───────────────────────────────────

    def _trigger_analysis(self, symptoms: list) -> list:
        """Most common triggers across all episodes, ranked by frequency."""
        trigger_counts = Counter()

        for s in symptoms:
            for ep in s.get("episodes", []):
                triggers = (ep.get("triggers") or "").strip()
                if triggers:
                    # Split on comma, semicolon, or "and"
                    parts = re.split(r'[,;]|\band\b', triggers)
                    for part in parts:
                        clean = part.strip().lower()
                        if clean and len(clean) > 2:
                            trigger_counts[clean] += 1

        return [
            {"trigger": t, "count": c}
            for t, c in trigger_counts.most_common(15)
        ]

    # ── 6. Severity Distribution ──────────────────────────────

    def _severity_distribution(self, symptoms: list) -> list:
        """Per symptom: % high/mid/low, trend direction."""
        result = []

        for s in symptoms:
            name = s.get("symptom_name", "Unknown")
            episodes = s.get("episodes", [])
            if not episodes:
                result.append({
                    "symptom_name": name,
                    "symptom_id": s.get("symptom_id", ""),
                    "high": 0, "mid": 0, "low": 0,
                    "total": 0,
                    "trend": "stable",
                })
                continue

            counts = {"high": 0, "mid": 0, "low": 0}
            for ep in episodes:
                sev = (ep.get("severity") or "mid").lower()
                if sev in counts:
                    counts[sev] += 1

            total = sum(counts.values())
            pcts = {k: round(v / total * 100, 1) if total else 0 for k, v in counts.items()}

            # Trend: compare last 5 episodes to first 5
            trend = self._compute_severity_trend(episodes)

            result.append({
                "symptom_name": name,
                "symptom_id": s.get("symptom_id", ""),
                "high": counts["high"],
                "mid": counts["mid"],
                "low": counts["low"],
                "total": total,
                "pct_high": pcts["high"],
                "pct_mid": pcts["mid"],
                "pct_low": pcts["low"],
                "trend": trend,
            })

        return result

    def _compute_severity_trend(self, episodes: list) -> str:
        """Compare recent vs earlier severity."""
        sev_map = {"high": 3, "mid": 2, "low": 1}
        dated = []
        for ep in episodes:
            d = self._parse_date(ep.get("episode_date"))
            sev = sev_map.get((ep.get("severity") or "mid").lower(), 2)
            if d:
                dated.append((d, sev))

        if len(dated) < 4:
            return "stable"

        dated.sort(key=lambda x: x[0])
        half = len(dated) // 2
        first_avg = sum(s for _, s in dated[:half]) / half
        second_avg = sum(s for _, s in dated[half:]) / (len(dated) - half)

        diff = second_avg - first_avg
        if diff > 0.3:
            return "worsening"
        elif diff < -0.3:
            return "improving"
        return "stable"

    # ── 7. Episode Timeline ───────────────────────────────────

    def _episode_timeline(self, symptom: dict) -> list:
        """Chronological episode list for single-symptom detail view."""
        episodes = symptom.get("episodes", [])
        timeline = []

        for ep in episodes:
            ep_date = self._parse_date(ep.get("episode_date"))
            timeline.append({
                "date": ep_date.isoformat() if ep_date else None,
                "time_of_day": ep.get("time_of_day"),
                "severity": ep.get("severity", "mid"),
                "description": ep.get("description"),
                "duration": ep.get("duration"),
                "triggers": ep.get("triggers"),
            })

        timeline.sort(key=lambda x: x["date"] or "")
        return timeline

    # ── AI Qualitative Insights ───────────────────────────────

    def generate_ai_insights(
        self,
        symptoms: list,
        profile_data: dict = None,
        api_key: str = None,
    ) -> dict:
        """
        LLM analyzes qualitative symptom data + clinical context.
        Cascade: Gemini → rule-based heuristics.

        Returns structured insights: patterns, connections, narratives,
        suggestions.
        """
        insights = {
            "patterns": [],
            "connections": [],
            "counter_narratives": [],
            "suggestions": [],
            "source": "rule_based",
        }

        # Always run rule-based as baseline
        rule_insights = self._rule_based_insights(symptoms)
        insights["patterns"] = rule_insights.get("patterns", [])
        insights["connections"] = rule_insights.get("connections", [])
        insights["counter_narratives"] = rule_insights.get("counter_narratives", [])
        insights["suggestions"] = rule_insights.get("suggestions", [])

        # Try Gemini for richer analysis
        if api_key:
            try:
                gemini_insights = self._gemini_insights(
                    symptoms, profile_data, api_key
                )
                if gemini_insights:
                    insights = gemini_insights
                    insights["source"] = "gemini"
            except Exception as e:
                logger.warning("Gemini insights failed, using rule-based: %s", e)

        return insights

    def _rule_based_insights(self, symptoms: list) -> dict:
        """
        Scan for patterns without LLM.
        - Recurring phrases in descriptions
        - Cross-symptom timing patterns
        - Counter-evidence narratives from stats
        """
        patterns = []
        connections = []
        counter_narratives = []
        suggestions = []

        # Pattern: repeated words across descriptions
        for s in symptoms:
            name = s.get("symptom_name", "Unknown")
            all_descriptions = []
            all_triggers = []

            for ep in s.get("episodes", []):
                desc = (ep.get("description") or "").strip()
                if desc:
                    all_descriptions.append(desc.lower())
                trig = (ep.get("triggers") or "").strip()
                if trig:
                    all_triggers.append(trig.lower())

            # Find repeated phrases (3+ occurrences of 2+ word phrases)
            if len(all_descriptions) >= 3:
                phrase_counts = self._find_repeated_phrases(all_descriptions)
                for phrase, count in phrase_counts[:3]:
                    if count >= 3:
                        patterns.append({
                            "type": "recurring_phrase",
                            "symptom": name,
                            "phrase": phrase,
                            "count": count,
                            "message": (
                                f"You mention '{phrase}' in {count} of "
                                f"{len(all_descriptions)} {name.lower()} "
                                f"episodes — consider tracking this pattern"
                            ),
                        })

            # Find trigger not listed as counter
            trigger_words = set()
            for t in all_triggers:
                trigger_words.update(re.findall(r'\b[a-zA-Z]{3,}\b', t))

            counter_claims = set()
            for c in s.get("counter_definitions", []):
                claim = (c.get("doctor_claim") or "").lower()
                counter_claims.update(re.findall(r'\b[a-zA-Z]{3,}\b', claim))

            new_triggers = trigger_words - counter_claims - {
                "after", "before", "during", "when", "with", "the", "and"
            }
            if new_triggers and len(new_triggers) <= 3:
                for t in list(new_triggers)[:2]:
                    suggestions.append({
                        "type": "track_trigger",
                        "symptom": name,
                        "message": (
                            f"You frequently mention '{t}' as a trigger "
                            f"for {name.lower()} but aren't tracking it "
                            f"as counter-evidence — consider adding it"
                        ),
                    })

        # Counter-evidence narratives
        scorecards = self._counter_scorecards(symptoms)
        for sc in scorecards:
            if sc.get("episode_count", 0) < 3:
                continue

            verdict = sc.get("verdict", "")
            claim = sc.get("doctor_claim", "?")
            symptom_name = sc.get("symptom_name", "?")

            if sc["measure_type"] == "scale" and "mean" in sc:
                avg = sc["mean"]
                n = sc["episode_count"]
                if verdict == "strongly_contradicts":
                    counter_narratives.append({
                        "symptom": symptom_name,
                        "claim": claim,
                        "verdict": verdict,
                        "message": (
                            f"Your data shows {claim} levels averaging "
                            f"{avg:.1f}/5 during {symptom_name.lower()} "
                            f"episodes, with {n} data points. This "
                            f"pattern strongly suggests {claim} is not "
                            f"the primary trigger."
                        ),
                    })
                elif verdict == "supports_claim":
                    counter_narratives.append({
                        "symptom": symptom_name,
                        "claim": claim,
                        "verdict": verdict,
                        "message": (
                            f"Your data shows {claim} levels averaging "
                            f"{avg:.1f}/5 during {symptom_name.lower()} "
                            f"episodes ({n} data points). This data "
                            f"supports your doctor's assessment."
                        ),
                    })

            elif sc["measure_type"] == "yes_no":
                pct_no = sc.get("pct_no", 0)
                n = sc["episode_count"]
                if verdict == "strongly_contradicts":
                    counter_narratives.append({
                        "symptom": symptom_name,
                        "claim": claim,
                        "verdict": verdict,
                        "message": (
                            f"{claim}: '{claim}' was NOT present in "
                            f"{pct_no:.0f}% of your {symptom_name.lower()} "
                            f"episodes ({n} tracked). This strongly "
                            f"contradicts {claim} as the cause."
                        ),
                    })

        # Cross-symptom connections (if correlated)
        if len(symptoms) >= 2:
            corr = self._symptom_correlations(symptoms)
            for pair in corr.get("pairs", []):
                if pair["jaccard"] > 0.3:
                    lag_msg = ""
                    if pair.get("avg_lag_days") is not None:
                        lag_msg = (
                            f" (avg {pair['avg_lag_days']:.0f} days apart)"
                        )
                    connections.append({
                        "type": "co_occurrence",
                        "symptoms": [pair["symptom_a"], pair["symptom_b"]],
                        "jaccard": pair["jaccard"],
                        "message": (
                            f"{pair['symptom_a']} and {pair['symptom_b']} "
                            f"frequently co-occur{lag_msg} — this may "
                            f"indicate a shared underlying cause"
                        ),
                    })

        return {
            "patterns": patterns,
            "connections": connections,
            "counter_narratives": counter_narratives,
            "suggestions": suggestions,
        }

    def _gemini_insights(
        self,
        symptoms: list,
        profile_data: dict,
        api_key: str,
    ) -> Optional[dict]:
        """Call Gemini for qualitative analysis of symptom text."""
        import json
        import urllib.request

        # Build context (redacted — no names/locations)
        episodes_text = []
        for s in symptoms:
            name = s.get("symptom_name", "")
            for ep in s.get("episodes", []):
                desc = (ep.get("description") or "").strip()
                trig = (ep.get("triggers") or "").strip()
                sev = ep.get("severity", "mid")
                if desc:
                    episodes_text.append(
                        f"[{name}|{sev}] {desc}"
                        + (f" (trigger: {trig})" if trig else "")
                    )

        if not episodes_text:
            return None

        # Counter stats
        scorecards = self._counter_scorecards(symptoms)
        counter_summary = []
        for sc in scorecards:
            if sc.get("episode_count", 0) >= 2:
                counter_summary.append(
                    f"- {sc['symptom_name']}: Doctor says '{sc['doctor_claim']}' → "
                    f"verdict: {sc.get('verdict_label', '?')} "
                    f"(n={sc['episode_count']})"
                )

        prompt = (
            "You are a medical data analyst. Analyze the following symptom "
            "episode descriptions and counter-evidence data. Return JSON with "
            "4 arrays: patterns (recurring themes), connections (cross-symptom "
            "links), counter_narratives (plain-English counter-evidence "
            "summaries), suggestions (actionable next steps).\n\n"
            "EPISODES:\n" + "\n".join(episodes_text[:50]) + "\n\n"
            "COUNTER-EVIDENCE:\n" + "\n".join(counter_summary) + "\n\n"
            "Return ONLY valid JSON with this structure:\n"
            '{"patterns": [{"message": "..."}], "connections": [{"message": "..."}], '
            '"counter_narratives": [{"message": "..."}], "suggestions": [{"message": "..."}]}'
        )

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={api_key}"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2000},
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())

        text = (
            body.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            result = json.loads(json_match.group())
            return {
                "patterns": result.get("patterns", []),
                "connections": result.get("connections", []),
                "counter_narratives": result.get("counter_narratives", []),
                "suggestions": result.get("suggestions", []),
                "source": "gemini",
            }

        return None

    # ── Helpers ───────────────────────────────────────────────

    def _find_repeated_phrases(self, texts: list) -> list:
        """Find 2-3 word phrases that repeat across texts."""
        phrase_counts = Counter()

        for text in texts:
            words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
            seen_in_text = set()

            # 2-word phrases
            for i in range(len(words) - 1):
                phrase = f"{words[i]} {words[i+1]}"
                if phrase not in seen_in_text:
                    phrase_counts[phrase] += 1
                    seen_in_text.add(phrase)

            # 3-word phrases
            for i in range(len(words) - 2):
                phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
                if phrase not in seen_in_text:
                    phrase_counts[phrase] += 1
                    seen_in_text.add(phrase)

        # Filter stopword-heavy phrases
        stopwords = {"the", "and", "was", "were", "that", "this", "with", "for", "from"}
        filtered = [
            (p, c) for p, c in phrase_counts.most_common(20)
            if not all(w in stopwords for w in p.split())
        ]

        return filtered[:5]

    def _summary_stats(self, symptoms: list) -> dict:
        """Overall summary statistics."""
        total_episodes = sum(
            len(s.get("episodes", [])) for s in symptoms
        )
        total_symptoms = len(symptoms)

        # Most active symptom
        most_active = max(
            symptoms,
            key=lambda s: len(s.get("episodes", [])),
            default=None,
        )
        most_active_name = most_active.get("symptom_name") if most_active else None

        return {
            "total_symptoms": total_symptoms,
            "total_episodes": total_episodes,
            "most_active": most_active_name,
            "avg_episodes_per_symptom": (
                round(total_episodes / total_symptoms, 1)
                if total_symptoms else 0
            ),
        }

    @staticmethod
    def _parse_date(value) -> Optional[date]:
        """Parse a date from various formats."""
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(value.split("T")[0], fmt.split("T")[0]).date()
                except ValueError:
                    continue
        return None

    @staticmethod
    def _empty_result() -> dict:
        return {
            "correlations": {"pairs": [], "matrix": [], "names": []},
            "calendar_heatmap": [],
            "time_heatmap": [],
            "counter_scorecards": [],
            "trigger_analysis": [],
            "severity_distribution": [],
            "summary": {
                "total_symptoms": 0,
                "total_episodes": 0,
                "most_active": None,
                "avg_episodes_per_symptom": 0,
            },
        }


# ── Module-Level Utilities ────────────────────────────────────

def _is_numeric(val) -> bool:
    """Check if a value can be cast to float."""
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False


def _std(values: list) -> float:
    """Standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return variance ** 0.5
