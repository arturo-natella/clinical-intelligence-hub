"""
Clinical Intelligence Hub — Symptom Pattern Monitor

Analyzes symptom data over time to detect:
  - Frequency trends (episodes per week, trending up/down/stable)
  - Severity trends (average severity over time)
  - Time-of-day patterns ("80% of headaches occur in morning")
  - Medication correlations (symptom started/worsened after med X)
  - Cluster detection (symptoms that co-occur within 24-48 hours)
  - Alerts for concerning patterns
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger("CIH-SymptomMonitor")


class SymptomPatternMonitor:
    """Analyze symptom patterns over time."""

    def analyze(
        self,
        symptoms: list,
        medications: list = None,
    ) -> dict:
        """Return comprehensive pattern analysis."""
        medications = medications or []

        per_symptom = []
        for sym in symptoms:
            episodes = sym.get("episodes", [])
            if not episodes:
                per_symptom.append({
                    "symptom_id": sym.get("symptom_id"),
                    "name": sym.get("symptom_name", "Unknown"),
                    "total_episodes": 0,
                    "frequency": None,
                    "intensity_trend": None,
                    "time_patterns": None,
                    "medication_correlations": [],
                    "alerts": [],
                })
                continue

            analysis = {
                "symptom_id": sym.get("symptom_id"),
                "name": sym.get("symptom_name", "Unknown"),
                "total_episodes": len(episodes),
                "frequency": self._frequency_analysis(episodes),
                "intensity_trend": self._intensity_trend(episodes),
                "time_patterns": self._time_of_day_patterns(episodes),
                "medication_correlations": self._medication_correlations(
                    sym, medications
                ),
                "weekly_sparkline": self._weekly_sparkline(episodes),
                "alerts": [],
            }

            # Generate alerts from analysis
            analysis["alerts"] = self._generate_alerts(analysis, sym)
            per_symptom.append(analysis)

        # Cross-symptom cluster detection
        clusters = self._cluster_detection(symptoms)

        return {
            "per_symptom": per_symptom,
            "clusters": clusters,
            "summary": self._summary(per_symptom),
        }

    # ── Frequency Analysis ───────────────────────────────

    def _frequency_analysis(self, episodes: list) -> dict:
        """Episodes per week over different time windows."""
        today = date.today()
        dated = self._dated_episodes(episodes)
        if not dated:
            return {"per_week_4w": 0, "per_week_12w": 0, "direction": "stable"}

        # Last 4 weeks
        cutoff_4w = today - timedelta(days=28)
        recent_4w = [d for d, _ in dated if d >= cutoff_4w]
        per_week_4w = round(len(recent_4w) / 4, 1)

        # Last 12 weeks
        cutoff_12w = today - timedelta(days=84)
        recent_12w = [d for d, _ in dated if d >= cutoff_12w]
        per_week_12w = round(len(recent_12w) / 12, 1) if recent_12w else 0

        # Direction: compare recent 4w rate vs prior 8w rate
        cutoff_8w = today - timedelta(days=56)
        prior_8w = [d for d, _ in dated if cutoff_8w <= d < cutoff_4w]
        per_week_prior = round(len(prior_8w) / 4, 1) if prior_8w else 0

        if per_week_4w > per_week_prior * 1.3 and per_week_prior > 0:
            direction = "increasing"
        elif per_week_4w < per_week_prior * 0.7 and per_week_4w > 0:
            direction = "decreasing"
        else:
            direction = "stable"

        return {
            "per_week_4w": per_week_4w,
            "per_week_12w": per_week_12w,
            "direction": direction,
        }

    # ── Intensity Trend ──────────────────────────────────

    def _intensity_trend(self, episodes: list) -> dict:
        """Intensity trend: compare first half vs second half."""
        sev_map = {"high": 3, "mid": 2, "low": 1}

        dated = self._dated_episodes(episodes)
        if len(dated) < 2:
            return {
                "current_avg": sev_map.get(
                    episodes[0].get("intensity", "mid"), 2
                ) if episodes else 2,
                "direction": "insufficient_data",
            }

        # Sort chronologically
        dated.sort(key=lambda x: x[0])
        scores = [sev_map.get(ep.get("intensity", "mid"), 2) for _, ep in dated]

        mid = len(scores) // 2
        first_avg = sum(scores[:mid]) / mid
        second_avg = sum(scores[mid:]) / (len(scores) - mid)
        current_avg = round(second_avg, 1)

        if second_avg > first_avg + 0.4:
            direction = "worsening"
        elif second_avg < first_avg - 0.4:
            direction = "improving"
        else:
            direction = "stable"

        return {"current_avg": current_avg, "direction": direction}

    # ── Time-of-Day Patterns ─────────────────────────────

    def _time_of_day_patterns(self, episodes: list) -> dict:
        """When do episodes cluster?"""
        counts = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}
        total = 0

        for ep in episodes:
            tod = ep.get("time_of_day")
            if tod and tod in counts:
                counts[tod] += 1
                total += 1

        if total == 0:
            return {"peak": None, "distribution": counts, "peak_pct": 0}

        peak = max(counts, key=counts.get)
        peak_pct = round(counts[peak] / total * 100)

        return {
            "peak": peak,
            "distribution": counts,
            "peak_pct": peak_pct,
        }

    # ── Medication Correlations ──────────────────────────

    def _medication_correlations(
        self, symptom: dict, medications: list
    ) -> list:
        """Did this symptom start/worsen after starting a medication?"""
        episodes = symptom.get("episodes", [])
        dated = self._dated_episodes(episodes)
        if not dated:
            return []

        # Earliest episode date
        dated.sort(key=lambda x: x[0])
        first_episode = dated[0][0]

        correlations = []
        for med in medications:
            med_start = self._parse_date(med.get("start_date"))
            if not med_start:
                continue

            status = (med.get("status") or "").lower()
            if status in ("discontinued", "stopped", "completed"):
                continue

            # Check if symptom started within 30 days of medication start
            delta = (first_episode - med_start).days
            if 0 <= delta <= 30:
                correlations.append({
                    "medication": med.get("name", "Unknown"),
                    "type": "onset_after_start",
                    "days_after": delta,
                    "description": (
                        f"First episode was {delta} days after "
                        f"starting {med.get('name', '')}"
                    ),
                })

            # Check if intensity worsened after medication start
            if len(dated) >= 4:
                sev_map = {"high": 3, "mid": 2, "low": 1}
                before = [
                    sev_map.get(ep.get("intensity", "mid"), 2)
                    for d, ep in dated if d < med_start
                ]
                after = [
                    sev_map.get(ep.get("intensity", "mid"), 2)
                    for d, ep in dated if d >= med_start
                ]
                if before and after:
                    avg_before = sum(before) / len(before)
                    avg_after = sum(after) / len(after)
                    if avg_after > avg_before + 0.5:
                        correlations.append({
                            "medication": med.get("name", "Unknown"),
                            "type": "severity_increase",
                            "description": (
                                f"Severity increased after starting "
                                f"{med.get('name', '')}"
                            ),
                        })

        return correlations

    # ── Weekly Sparkline Data ────────────────────────────

    def _weekly_sparkline(self, episodes: list, weeks: int = 12) -> list:
        """Episode counts per week for the last N weeks (sparkline data)."""
        today = date.today()
        dated = self._dated_episodes(episodes)
        buckets = [0] * weeks

        for ep_date, _ in dated:
            week_ago = (today - ep_date).days // 7
            if 0 <= week_ago < weeks:
                buckets[weeks - 1 - week_ago] += 1

        return buckets

    # ── Cluster Detection ────────────────────────────────

    def _cluster_detection(self, symptoms: list) -> list:
        """Find symptoms that co-occur within 48 hours."""
        # Build date→symptom map
        date_map = {}  # date_str → set of symptom names
        for sym in symptoms:
            name = sym.get("symptom_name", "")
            for ep in sym.get("episodes", []):
                ep_date = ep.get("episode_date")
                if ep_date:
                    if ep_date not in date_map:
                        date_map[ep_date] = set()
                    date_map[ep_date].add(name)

        # Find pairs that co-occur (same day or adjacent days)
        sorted_dates = sorted(date_map.keys())
        pair_counts = {}

        for i, d in enumerate(sorted_dates):
            # Same day co-occurrences
            names = list(date_map[d])
            for a in range(len(names)):
                for b in range(a + 1, len(names)):
                    pair = tuple(sorted([names[a], names[b]]))
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1

            # Adjacent day co-occurrences
            if i + 1 < len(sorted_dates):
                next_d = sorted_dates[i + 1]
                try:
                    d1 = date.fromisoformat(d)
                    d2 = date.fromisoformat(next_d)
                    if (d2 - d1).days <= 2:
                        combined = date_map[d] | date_map[next_d]
                        names_c = list(combined)
                        for a in range(len(names_c)):
                            for b in range(a + 1, len(names_c)):
                                pair = tuple(sorted([names_c[a], names_c[b]]))
                                pair_counts[pair] = pair_counts.get(pair, 0) + 1
                except (ValueError, TypeError):
                    pass

        clusters = []
        for pair, count in pair_counts.items():
            if count >= 2:  # At least 2 co-occurrences
                clusters.append({
                    "symptoms": list(pair),
                    "co_occurrences": count,
                    "description": (
                        f"{pair[0]} and {pair[1]} occurred within "
                        f"48 hours {count} times"
                    ),
                })

        clusters.sort(key=lambda x: x["co_occurrences"], reverse=True)
        return clusters

    # ── Alert Generation ─────────────────────────────────

    def _generate_alerts(self, analysis: dict, symptom: dict) -> list:
        """Generate alerts from pattern analysis."""
        alerts = []
        name = analysis.get("name", "")

        # Frequency increasing
        freq = analysis.get("frequency") or {}
        if freq.get("direction") == "increasing":
            alerts.append({
                "severity": "moderate",
                "type": "frequency_increase",
                "message": (
                    f"{name}: frequency increasing "
                    f"({freq.get('per_week_4w', 0)}/week, "
                    f"up from prior period)"
                ),
            })

        # Intensity worsening
        sev = analysis.get("intensity_trend") or {}
        if sev.get("direction") == "worsening":
            alerts.append({
                "severity": "moderate",
                "type": "intensity_worsening",
                "message": f"{name}: intensity trending upward",
            })

        # High frequency
        if freq.get("per_week_4w", 0) >= 5:
            alerts.append({
                "severity": "high",
                "type": "high_frequency",
                "message": (
                    f"{name}: {freq['per_week_4w']} episodes/week "
                    f"(very frequent)"
                ),
            })

        # Medication correlations
        med_corrs = analysis.get("medication_correlations", [])
        for corr in med_corrs:
            alerts.append({
                "severity": "moderate",
                "type": "medication_correlation",
                "message": corr.get("description", ""),
            })

        return alerts

    # ── Summary ──────────────────────────────────────────

    def _summary(self, per_symptom: list) -> dict:
        """Overall summary statistics."""
        total_episodes = sum(s.get("total_episodes", 0) for s in per_symptom)
        worsening = [
            s["name"] for s in per_symptom
            if (s.get("intensity_trend") or {}).get("direction") == "worsening"
        ]
        increasing = [
            s["name"] for s in per_symptom
            if (s.get("frequency") or {}).get("direction") == "increasing"
        ]
        all_alerts = []
        for s in per_symptom:
            all_alerts.extend(s.get("alerts", []))

        return {
            "tracked_symptoms": len(per_symptom),
            "total_episodes": total_episodes,
            "worsening": worsening,
            "increasing_frequency": increasing,
            "alert_count": len(all_alerts),
        }

    # ── Helpers ───────────────────────────────────────────

    def _dated_episodes(self, episodes: list) -> list:
        """Return list of (date, episode) tuples with valid dates."""
        result = []
        for ep in episodes:
            d = self._parse_date(ep.get("episode_date"))
            if d:
                result.append((d, ep))
        return result

    def _parse_date(self, val) -> Optional[date]:
        """Parse a date string or date object."""
        if isinstance(val, date):
            return val
        if isinstance(val, str):
            try:
                return date.fromisoformat(val[:10])
            except (ValueError, TypeError):
                return None
        return None
