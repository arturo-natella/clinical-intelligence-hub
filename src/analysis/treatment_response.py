"""
Clinical Intelligence Hub — Treatment Response Analyzer (Phase 3)

Per-medication scorecard showing:
  1. Lab effectiveness — baseline vs current for each relevant lab
  2. Tolerability — from linked symptom episodes
  3. Conversation guide — plain-language text for doctor discussions

Results feed into:
  - Trajectories overlay (response summary box per medication)
  - Word report (Section 4b: Treatment Response)
  - Visit Prep module
"""

import logging
import math
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger("CIH-TreatmentResponse")


class TreatmentResponseAnalyzer:
    """
    Analyzes how each medication is performing based on lab values
    and symptom episode data.
    """

    def analyze(
        self,
        medications: list[dict],
        labs: list[dict],
        symptoms: list[dict],
        genetics: list[dict],
        med_lab_mapping_fn=None,
    ) -> dict:
        """
        For each medication, compute:
          1. Lab effectiveness — baseline vs current for each relevant lab
          2. Tolerability — from linked symptom episodes
          3. Conversation guide text

        Args:
            medications: List of medication dicts from clinical_timeline
            labs: List of lab result dicts from clinical_timeline
            symptoms: List of symptom dicts (each with episodes list)
            genetics: List of genetic variant dicts
            med_lab_mapping_fn: Optional override for get_relevant_medications

        Returns:
            {
                "medication_responses": [ ... per-medication dicts ... ],
                "summary": { "total_analyzed": N, "effective_count": N, ... },
            }
        """
        from src.analysis.med_lab_mapping import MED_LAB_EFFECTS, _find_mapping_key
        from src.analysis.side_effect_scorer import SideEffectScorer

        # Step 1: Build medication-to-lab mappings
        # med_lab_mapping.py's get_relevant_medications goes lab→medications (for Phase 1 charts).
        # We need medication→labs, so use MED_LAB_EFFECTS directly.
        try:
            if med_lab_mapping_fn:
                # Allow test injection of custom mapping function
                med_lab_mappings = med_lab_mapping_fn(medications, labs)
            else:
                med_lab_mappings = []
                for med in medications:
                    med_name = med.get("name", "")
                    generic = med.get("generic_name", "")
                    mapping_key = _find_mapping_key(med_name) or _find_mapping_key(generic)
                    if mapping_key:
                        matched_labs = list(MED_LAB_EFFECTS.get(mapping_key, set()))
                        med_lab_mappings.append({
                            "medication": med,
                            "matched_lab_keys": matched_labs,
                        })
                    else:
                        logger.info("No lab mapping found for medication: %s", med_name)
        except Exception as e:
            logger.warning("Med-lab mapping failed, continuing with empty mappings: %s", e)
            med_lab_mappings = []

        # Step 2: Get side effect scores
        try:
            scorer = SideEffectScorer()
            side_effect_results = scorer.score_all_linked_episodes(
                symptoms, medications, genetics
            )
        except Exception as e:
            logger.warning("Side effect scoring failed, continuing without tolerability: %s", e)
            side_effect_results = []

        # Index side effects by medication name for lookup
        # score_all_linked_episodes returns {med_name: [scored_episodes]}
        side_effect_by_med: dict[str, dict] = {}
        if isinstance(side_effect_results, dict):
            # Direct dict keyed by medication name → list of scored episodes
            for med_name, episodes in side_effect_results.items():
                key = med_name.lower().strip()
                if key and episodes:
                    # Build a summary structure from the scored episodes
                    intensity_counts = {"high": 0, "mid": 0, "low": 0}
                    for ep in episodes:
                        sev = (ep.get("intensity") or "mid").lower()
                        if sev in intensity_counts:
                            intensity_counts[sev] += 1
                    total = len(episodes)
                    # Determine tolerability rating
                    if intensity_counts["high"] >= 3 or total >= 5:
                        rating = "poor"
                    elif total >= 2:
                        rating = "fair"
                    else:
                        rating = "good"
                    side_effect_by_med[key] = {
                        "medication_name": med_name,
                        "total_episodes": total,
                        "intensity_breakdown": intensity_counts,
                        "tolerability": rating,
                        "intensity_trend": "insufficient data",
                        "linked_episodes": episodes,
                    }
        elif isinstance(side_effect_results, list):
            # Legacy list-of-dicts format (for custom scorers)
            for se in side_effect_results:
                key = (se.get("medication_name") or "").lower().strip()
                if key:
                    side_effect_by_med[key] = se

        # Step 3: Analyze each medication
        medication_responses = []
        effective_count = 0
        tolerated_count = 0

        for mapping in med_lab_mappings:
            med = mapping["medication"]
            med_name = (med.get("name") or "").strip()
            med_start = self._parse_date(med.get("start_date"))
            dosage = med.get("dosage") or ""

            # Lab effectiveness
            lab_results = self._compute_lab_effectiveness(
                med_start, mapping.get("matched_lab_keys", []), labs
            )

            # Tolerability
            med_key = med_name.lower().strip()
            side_effects = side_effect_by_med.get(med_key, {})
            tolerability = self._compute_tolerability(side_effects)

            # Conversation guide
            guide = self._build_conversation_guide(
                med_name, dosage, lab_results, tolerability
            )

            # Overall effectiveness assessment
            has_improvement = any(
                lr["assessment"] == "improved" for lr in lab_results
            )
            has_worsening = any(
                lr["assessment"] == "worsened" for lr in lab_results
            )
            if has_improvement:
                effective_count += 1
            if tolerability.get("rating") in ("good", "fair"):
                tolerated_count += 1

            response = {
                "medication_name": med_name,
                "dosage": dosage,
                "start_date": str(med_start) if med_start else None,
                "lab_effectiveness": lab_results,
                "tolerability": tolerability,
                "conversation_guide": guide,
                "overall": {
                    "has_improvement": has_improvement,
                    "has_worsening": has_worsening,
                    "tolerability_rating": tolerability.get("rating", "unknown"),
                },
            }
            medication_responses.append(response)

        # Also analyze medications that have side effects but no lab mapping
        analyzed_names = {
            r["medication_name"].lower().strip()
            for r in medication_responses
        }
        for se_key, se_data in side_effect_by_med.items():
            if se_key not in analyzed_names:
                med_name = se_data.get("medication_name", se_key)
                tolerability = self._compute_tolerability(se_data)
                guide = self._build_conversation_guide(
                    med_name, "", [], tolerability
                )
                if tolerability.get("rating") in ("good", "fair"):
                    tolerated_count += 1

                medication_responses.append({
                    "medication_name": med_name,
                    "dosage": "",
                    "start_date": se_data.get("medication_start_date"),
                    "lab_effectiveness": [],
                    "tolerability": tolerability,
                    "conversation_guide": guide,
                    "overall": {
                        "has_improvement": False,
                        "has_worsening": False,
                        "tolerability_rating": tolerability.get("rating", "unknown"),
                    },
                })

        return {
            "medication_responses": medication_responses,
            "summary": {
                "total_analyzed": len(medication_responses),
                "effective_count": effective_count,
                "tolerated_count": tolerated_count,
                "with_lab_data": len(med_lab_mappings),
            },
        }

    # ── Lab Effectiveness ────────────────────────────────────

    def _compute_lab_effectiveness(
        self,
        med_start: Optional[date],
        matched_lab_keys: list[str],
        all_labs: list[dict],
    ) -> list[dict]:
        """
        For each relevant lab test, compute baseline vs current and rate of change.

        CRITICAL logic:
        - Baseline: most recent lab value BEFORE medication start date
        - Current: most recent lab value while on the medication
        - Rate: linear regression on all values during medication period
        """
        results = []

        for lab_key in matched_lab_keys:
            # Gather all lab values for this test
            lab_points = self._get_lab_points(lab_key, all_labs)
            if not lab_points:
                continue

            # Partition into before-med and during-med
            baseline_point = None
            during_points = []

            if med_start:
                before_points = [p for p in lab_points if p["date"] < med_start]
                during_points = [p for p in lab_points if p["date"] >= med_start]

                if before_points:
                    # Most recent before medication start
                    baseline_point = before_points[-1]  # already sorted by date
            else:
                # No start date — all points are "during", no baseline
                during_points = lab_points

            current_point = during_points[-1] if during_points else None

            if not current_point:
                continue

            # Build result
            lab_result = {
                "lab_name": current_point["display_name"],
                "lab_key": lab_key,
                "unit": current_point.get("unit", ""),
            }

            # Baseline
            if baseline_point:
                lab_result["baseline"] = {
                    "value": baseline_point["value"],
                    "date": str(baseline_point["date"]),
                    "source_file": baseline_point.get("source_file", ""),
                    "source_page": baseline_point.get("source_page"),
                }
            else:
                lab_result["baseline"] = None
                lab_result["baseline_note"] = "no baseline available"

            # Current
            lab_result["current"] = {
                "value": current_point["value"],
                "date": str(current_point["date"]),
                "source_file": current_point.get("source_file", ""),
                "source_page": current_point.get("source_page"),
            }

            # Assessment (baseline vs current)
            if baseline_point and current_point:
                baseline_val = baseline_point["value"]
                current_val = current_point["value"]
                pct_change = self._percent_change(baseline_val, current_val)

                lab_result["change_pct"] = round(pct_change, 1)

                if abs(pct_change) <= 5.0:
                    lab_result["assessment"] = "stable"
                elif self._is_improvement(lab_key, baseline_val, current_val):
                    lab_result["assessment"] = "improved"
                else:
                    lab_result["assessment"] = "worsened"
            else:
                lab_result["assessment"] = "no baseline"
                lab_result["change_pct"] = None

            # Rate of improvement (linear regression on during-med period)
            if len(during_points) >= 2:
                regression = self._linear_regression(during_points)
                lab_result["regression"] = regression
            else:
                lab_result["regression"] = None

            results.append(lab_result)

        return results

    def _get_lab_points(
        self, lab_key: str, all_labs: list[dict]
    ) -> list[dict]:
        """
        Extract numeric lab values for a given test key, sorted by date.
        Includes provenance info.
        """
        points = []
        for lab in all_labs:
            name = (lab.get("name") or lab.get("test_name") or "").strip()
            if not name:
                continue

            name_lower = name.lower()
            if lab_key not in name_lower and name_lower not in lab_key:
                continue

            value = self._parse_numeric(lab.get("value") or lab.get("value_text"))
            if value is None:
                continue

            test_date = self._parse_date(lab.get("test_date") or lab.get("date"))
            if not test_date:
                continue

            # Extract provenance
            prov = lab.get("provenance", {})
            if isinstance(prov, dict):
                source_file = prov.get("source_file", "")
                source_page = prov.get("source_page")
            else:
                source_file = ""
                source_page = None

            points.append({
                "date": test_date,
                "value": value,
                "display_name": name,
                "unit": lab.get("unit", ""),
                "source_file": source_file,
                "source_page": source_page,
            })

        points.sort(key=lambda p: p["date"])
        return points

    def _linear_regression(self, points: list[dict]) -> dict:
        """
        Compute linear regression on lab values over time.
        Reuses the same math as trajectory.py.

        Returns:
            {
                "slope_per_month": float,
                "r_squared": float,
                "direction": "rising" | "falling" | "stable",
                "confidence": "high" | "moderate" | "low",
            }
        """
        if len(points) < 2:
            return {
                "slope_per_month": 0.0,
                "r_squared": 0.0,
                "direction": "stable",
                "confidence": "low",
            }

        first_date = points[0]["date"]
        xs = [(p["date"] - first_date).days for p in points]
        ys = [p["value"] for p in points]
        n = len(xs)

        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_x2 = sum(x * x for x in xs)

        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            return {
                "slope_per_month": 0.0,
                "r_squared": 0.0,
                "direction": "stable",
                "confidence": "low",
            }

        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n

        # R-squared
        y_mean = sum_y / n
        ss_tot = sum((y - y_mean) ** 2 for y in ys)
        ss_res = sum(
            (y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys)
        )
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        r_squared = max(0.0, min(1.0, r_squared))

        # Slope per month (30.44 days)
        slope_per_month = slope * 30.44

        # Direction (same threshold logic as trajectory.py)
        annual_change = abs(slope_per_month) * 12
        stable_threshold = max(0.05, 0.02 * abs(y_mean)) if y_mean != 0 else 0.05
        if annual_change < stable_threshold:
            direction = "stable"
        elif slope > 0:
            direction = "rising"
        else:
            direction = "falling"

        # Confidence
        if r_squared > 0.7:
            confidence = "high"
        elif r_squared > 0.4:
            confidence = "moderate"
        else:
            confidence = "low"

        return {
            "slope_per_month": round(slope_per_month, 4),
            "r_squared": round(r_squared, 3),
            "direction": direction,
            "confidence": confidence,
        }

    # ── Tolerability ─────────────────────────────────────────

    def _compute_tolerability(self, side_effect_data: dict) -> dict:
        """
        Build tolerability summary from side effect scorer output.
        """
        if not side_effect_data:
            return {
                "rating": "good",
                "total_episodes": 0,
                "intensity_breakdown": {"high": 0, "mid": 0, "low": 0},
                "intensity_trend": "no data",
                "linked_episodes": [],
            }

        total = side_effect_data.get("total_episodes", 0)
        breakdown = side_effect_data.get("intensity_breakdown", {"high": 0, "mid": 0, "low": 0})
        trend = side_effect_data.get("intensity_trend", "insufficient data")
        rating = side_effect_data.get("tolerability", "good")

        return {
            "rating": rating,
            "total_episodes": total,
            "intensity_breakdown": breakdown,
            "intensity_trend": trend,
            "linked_episodes": side_effect_data.get("linked_episodes", []),
        }

    # ── Conversation Guide ───────────────────────────────────

    def _build_conversation_guide(
        self,
        med_name: str,
        dosage: str,
        lab_results: list[dict],
        tolerability: dict,
    ) -> dict:
        """
        Build patient-friendly conversation guide for doctor visits.

        Returns:
            {
                "what_labs_show": "plain language summary",
                "what_you_reported": "plain language summary",
                "discuss_because": "conversation starter",
            }
        """
        med_label = med_name
        if dosage:
            med_label += f" {dosage}"

        # "What your labs show"
        lab_lines = []
        for lr in lab_results:
            name = lr.get("lab_name", lr.get("lab_key", ""))
            assessment = lr.get("assessment", "")
            baseline = lr.get("baseline")
            current = lr.get("current", {})

            if assessment == "improved":
                if baseline:
                    lab_lines.append(
                        f"{name} improved from {baseline['value']} to {current['value']}"
                    )
                else:
                    lab_lines.append(f"{name} is currently at {current['value']}")
            elif assessment == "worsened":
                if baseline:
                    lab_lines.append(
                        f"{name} changed from {baseline['value']} to {current['value']} "
                        f"(moving in a direction worth discussing)"
                    )
                else:
                    lab_lines.append(f"{name} is currently at {current['value']}")
            elif assessment == "stable":
                lab_lines.append(f"{name} has stayed stable at {current['value']}")
            elif assessment == "no baseline":
                lab_lines.append(
                    f"{name} is currently at {current['value']} "
                    f"(no baseline available before starting {med_name})"
                )

        if lab_lines:
            what_labs_show = "Since starting " + med_label + ": " + ". ".join(lab_lines) + "."
        else:
            what_labs_show = f"No relevant lab trends available for {med_label}."

        # "What you reported"
        total_eps = tolerability.get("total_episodes", 0)
        breakdown = tolerability.get("intensity_breakdown", {})
        trend = tolerability.get("intensity_trend", "no data")

        if total_eps == 0:
            what_reported = f"No symptoms have been linked to {med_name}."
        else:
            parts = []
            if breakdown.get("high", 0) > 0:
                parts.append(f"{breakdown['high']} severe")
            if breakdown.get("mid", 0) > 0:
                parts.append(f"{breakdown['mid']} moderate")
            if breakdown.get("low", 0) > 0:
                parts.append(f"{breakdown['low']} mild")

            severity_text = ", ".join(parts) if parts else f"{total_eps} total"
            what_reported = (
                f"You reported {total_eps} symptom episode"
                + ("s" if total_eps != 1 else "")
                + f" that may be related to {med_name} ({severity_text})."
            )
            if trend == "getting worse":
                what_reported += " These symptoms appear to be getting worse over time."
            elif trend == "improving":
                what_reported += " These symptoms appear to be improving over time."

        # "Discuss with your doctor because"
        discuss_reasons = []
        has_worsening = any(lr.get("assessment") == "worsened" for lr in lab_results)
        has_improvement = any(lr.get("assessment") == "improved" for lr in lab_results)
        poor_tolerability = tolerability.get("rating") == "poor"

        if has_worsening and poor_tolerability:
            discuss_reasons.append(
                f"some lab values have moved in an unexpected direction while on {med_name}, "
                f"and you've reported symptoms that may be side effects"
            )
        elif has_worsening:
            discuss_reasons.append(
                f"some lab values have changed since starting {med_name} "
                f"and your doctor can help determine if this is expected"
            )
        elif poor_tolerability:
            discuss_reasons.append(
                f"you've reported multiple symptoms that may be related to {med_name}, "
                f"and your doctor may be able to adjust the dose or suggest alternatives"
            )
        elif has_improvement:
            discuss_reasons.append(
                f"{med_name} appears to be working well for you based on lab trends, "
                f"and your doctor can confirm this positive direction"
            )
        else:
            discuss_reasons.append(
                f"regular check-ins about {med_name} help ensure it continues "
                f"to work well for you"
            )

        discuss_because = "Discuss with your doctor because " + discuss_reasons[0] + "."

        return {
            "what_labs_show": what_labs_show,
            "what_you_reported": what_reported,
            "discuss_because": discuss_because,
        }

    # ── Assessment Helpers ───────────────────────────────────

    @staticmethod
    def _is_improvement(lab_key: str, baseline: float, current: float) -> bool:
        """
        Determine if the change from baseline to current is an improvement.
        This depends on the lab test — for some, lower is better; for others, higher.
        """
        # Labs where LOWER is better
        lower_is_better = {
            "hba1c", "hemoglobin a1c", "glucose", "fasting glucose",
            "ldl", "total cholesterol", "triglycerides",
            "creatinine", "alt", "ast", "crp", "esr",
            "uric acid", "bun", "bilirubin", "ggt",
            "alkaline phosphatase", "tsh",  # if high (hyperthyroid treatment)
            "psa", "inr",
        }
        # Labs where HIGHER is better
        higher_is_better = {
            "egfr", "hdl", "hemoglobin", "hematocrit", "albumin",
            "vitamin d", "25-hydroxy vitamin d", "vitamin b12",
            "folate", "ferritin", "iron",
        }

        lab_lower = lab_key.lower()

        for key in lower_is_better:
            if key in lab_lower or lab_lower in key:
                return current < baseline

        for key in higher_is_better:
            if key in lab_lower or lab_lower in key:
                return current > baseline

        # Default: assume lower is better (conservative)
        return current < baseline

    @staticmethod
    def _percent_change(baseline: float, current: float) -> float:
        """Calculate percent change from baseline to current."""
        if baseline == 0:
            return 0.0 if current == 0 else 100.0
        return ((current - baseline) / abs(baseline)) * 100.0

    @staticmethod
    def _parse_numeric(value) -> Optional[float]:
        """Extract numeric value from various formats."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            if "-" in cleaned and not cleaned.startswith("-"):
                cleaned = cleaned.split("-")[0]
            for prefix in ("<", ">", "<=", ">="):
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
            try:
                return float(cleaned)
            except (ValueError, TypeError):
                return None
        return None

    @staticmethod
    def _parse_date(date_val) -> Optional[date]:
        """Parse date from various formats."""
        if isinstance(date_val, date) and not isinstance(date_val, datetime):
            return date_val
        if isinstance(date_val, datetime):
            return date_val.date()
        if isinstance(date_val, str):
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(date_val.strip(), fmt).date()
                except ValueError:
                    continue
        return None
