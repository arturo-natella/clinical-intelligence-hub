"""
Clinical Intelligence Hub — Anomaly Investigation Engine

Detects anomalous lab values (spikes/drops that deviate significantly from
the linear regression trend) and investigates what happened in the days
leading up to each anomaly by aggregating medical records, medication
changes, and symptom reports.

Key features:
  - Flags data points whose residual exceeds 2x the regression SE
  - Detects direction reversals (improving trend that suddenly worsens)
  - Configurable investigation windows per lab type (7–90 days)
  - Aggregates events from multiple clinical sources with provenance
  - Generates plain-language correlation summaries for doctor discussions

Results feed into:
  - Trajectories overlay (pulsing anomaly indicators)
  - Investigation panel ("What Happened Here?")
"""

import logging
import math
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger("CIH-AnomalyInvestigator")


# ── Investigation Windows ────────────────────────────────────
#
# How many days before the anomalous lab draw to search for
# contributing events.  Each window reflects how long the test's
# values are influenced by clinical changes.

INVESTIGATION_WINDOWS = {
    "hba1c": 90, "hemoglobin a1c": 90,       # 3-month glycation window
    "glucose": 7, "fasting glucose": 7,       # point-in-time, 1 week context
    "crp": 14, "c-reactive protein": 14,      # acute phase, 2 weeks
    "tsh": 60,                                # thyroid is slow-moving
    "egfr": 60, "creatinine": 60,             # kidney changes over weeks
    "alt": 30, "ast": 30,                     # liver enzymes, 1 month
    "ldl": 60, "hdl": 60, "triglycerides": 60,  # lipids, 2 months
    "default": 60,
}


class AnomalyInvestigator:
    """
    Detects anomalous lab data points and investigates causal events
    in the preceding clinical timeline.
    """

    # ── Anomaly Detection ─────────────────────────────────────

    def detect_anomalies(self, trajectory: dict) -> list:
        """
        Flag data points where:
        1. Residual from trend line > 2 x standard_error, OR
        2. Direction reversal (was improving, now worsening based on
           reference range context).

        Uses the regression parameters already computed in trajectory['trend'].
        Recomputes residuals from the linear regression.

        Args:
            trajectory: A single trajectory dict from TrajectoryForecaster
                        containing data_points, trend, trend_line, and
                        optionally reference_range.

        Returns:
            List of anomaly dicts:
            [{
                date: ISO string,
                value: float,
                expected: float,
                deviation: float,
                deviation_pct: float,
                direction: 'spike' | 'drop',
                severity: 'major' | 'moderate',
            }]
        """
        data_points = trajectory.get("data_points", [])
        trend = trajectory.get("trend", {})
        trend_line = trajectory.get("trend_line", [])

        if len(data_points) < 3 or len(trend_line) < 2:
            return []

        # Reconstruct regression parameters from trend_line endpoints.
        # trend_line[0] = {date: first_date_iso, value: intercept}
        # trend_line[1] = {date: proj_date_iso, value: proj_value}
        first_date = self._parse_date(trend_line[0]["date"])
        last_tl_date = self._parse_date(trend_line[1]["date"])
        if not first_date or not last_tl_date:
            logger.warning("Cannot parse trend_line dates for anomaly detection")
            return []

        tl_span_days = (last_tl_date - first_date).days
        if tl_span_days == 0:
            return []

        intercept = trend_line[0]["value"]
        slope = (trend_line[1]["value"] - intercept) / tl_span_days

        # Compute residuals and SE
        xs = []
        ys = []
        for dp in data_points:
            d = self._parse_date(dp["date"])
            if not d:
                continue
            days = (d - first_date).days
            xs.append(days)
            ys.append(dp["value"])

        n = len(xs)
        if n < 3:
            return []

        residuals = []
        for x, y in zip(xs, ys):
            expected = slope * x + intercept
            residuals.append(y - expected)

        ss_res = sum(r * r for r in residuals)
        se = math.sqrt(ss_res / (n - 2)) if n > 2 else 0

        # Use Median Absolute Deviation (MAD) as a robust SE estimate.
        # Standard SE is inflated by the very outliers we're trying to detect,
        # so MAD gives a stable baseline that doesn't mask anomalies.
        abs_residuals = sorted(abs(r) for r in residuals)
        median_idx = len(abs_residuals) // 2
        if len(abs_residuals) % 2 == 1:
            mad = abs_residuals[median_idx]
        else:
            mad = (abs_residuals[median_idx - 1] + abs_residuals[median_idx]) / 2

        # Convert MAD to SE-equivalent (MAD * 1.4826 approximates std dev
        # for normally distributed data)
        robust_se = mad * 1.4826 if mad > 0 else se

        # Use the more conservative (smaller) of robust_se and se to
        # detect anomalies — if either method flags it, it's anomalous.
        # In practice, robust_se will be smaller when outliers inflate se.
        detection_se = min(se, robust_se) if robust_se > 0 else se

        if detection_se == 0 and se == 0:
            # Perfect fit — no anomalies possible
            return []

        # Get reference range for direction context
        ref_range = trajectory.get("reference_range", {})
        trend_direction = trend.get("direction", "stable")

        anomalies = []
        for i, (x, y, r) in enumerate(zip(xs, ys, residuals)):
            abs_r = abs(r)
            expected = slope * x + intercept

            # Check 1: Residual exceeds threshold
            se_multiple = abs_r / detection_se if detection_se > 0 else 0
            is_anomalous = se_multiple > 2.0

            # Check 2: Direction reversal detection
            is_reversal = False
            if i >= 2 and not is_anomalous:
                is_reversal = self._check_direction_reversal(
                    i, xs, ys, trend_direction, ref_range
                )
                if is_reversal:
                    is_anomalous = True

            if not is_anomalous:
                continue

            dp_date = self._parse_date(data_points[i]["date"])
            if not dp_date:
                continue

            deviation = y - expected
            deviation_pct = (abs(deviation) / abs(expected) * 100) if expected != 0 else 0

            # Determine direction relative to trend
            direction = "spike" if deviation > 0 else "drop"

            # Severity: major if > 3xSE, moderate if > 2xSE
            severity = "major" if se_multiple > 3.0 else "moderate"
            if is_reversal and not (se_multiple > 2.0):
                severity = "moderate"

            anomalies.append({
                "date": dp_date.isoformat(),
                "value": round(y, 2),
                "expected": round(expected, 2),
                "deviation": round(deviation, 2),
                "deviation_pct": round(deviation_pct, 1),
                "direction": direction,
                "severity": severity,
            })

        return anomalies

    def _check_direction_reversal(
        self, idx: int, xs: list, ys: list,
        trend_direction: str, ref_range: dict
    ) -> bool:
        """
        Detect if data point at idx represents a direction reversal:
        the trend was improving but this point worsens.

        "Improving" depends on the test and its reference range:
        - For tests where high is bad (most): improving = falling toward range
        - For tests where low is bad (eGFR, HDL): improving = rising toward range
        """
        if idx < 2:
            return False

        # Determine what "improving" means for this test
        # By default, assume lower is better (most lab tests)
        high_is_bad = True

        ref_high = ref_range.get("high")
        ref_low = ref_range.get("low")

        # If the trend is falling and the most recent value is above reference,
        # falling is improving.  If trend is rising and below reference,
        # rising is improving.
        if trend_direction == "falling":
            # Falling trend — was this improving or worsening?
            # If values are above reference high, falling = improving
            # If values are below reference low, falling = worsening
            if ref_low is not None and ys[idx] < ref_low:
                high_is_bad = False  # low is bad, falling is worsening already
            else:
                high_is_bad = True   # high is bad, falling is improving
        elif trend_direction == "rising":
            if ref_high is not None and ys[idx] > ref_high:
                high_is_bad = True   # high is bad, rising is worsening
            else:
                high_is_bad = False  # low is bad, rising is improving

        # Look at the local trajectory (last 3 points including current)
        recent_ys = ys[max(0, idx - 2):idx + 1]
        if len(recent_ys) < 3:
            return False

        # Was improving (moving toward normal) but now reversed?
        prev_change = recent_ys[1] - recent_ys[0]
        curr_change = recent_ys[2] - recent_ys[1]

        if high_is_bad:
            # High is bad: improving = falling, worsening = rising
            was_improving = prev_change < 0
            now_worsening = curr_change > 0
        else:
            # Low is bad: improving = rising, worsening = falling
            was_improving = prev_change > 0
            now_worsening = curr_change < 0

        # Only flag if the reversal is significant (> 50% of prev change magnitude)
        if was_improving and now_worsening:
            if abs(prev_change) > 0 and abs(curr_change) / abs(prev_change) > 0.5:
                return True

        return False

    # ── Event Investigation ───────────────────────────────────

    def investigate(
        self,
        anomaly_date: str,
        test_name: str,
        profile_data: dict,
    ) -> dict:
        """
        Gather all clinical events within the investigation window
        before the anomaly date.

        Args:
            anomaly_date: ISO date string of the anomalous lab draw
            test_name: Name of the lab test (e.g. "HbA1c")
            profile_data: Full patient profile dict

        Returns:
            {
                anomaly: {date, value, expected, deviation},
                window: {start_date, end_date, days},
                events_by_source: {
                    medical_records: [...],
                    medication_changes: [...],
                    symptom_reports: [...],
                },
                event_count: int,
                correlation_summary: {
                    discuss_because: str,
                    how_to_bring_up: str,
                },
            }
        """
        anom_date = self._parse_date(anomaly_date)
        if not anom_date:
            logger.warning("Cannot parse anomaly_date: %s", anomaly_date)
            return self._empty_investigation(anomaly_date, test_name)

        # Determine investigation window
        window_days = self._get_window_days(test_name)
        window_start = anom_date - timedelta(days=window_days)

        # Find the anomaly data in the trajectory
        anomaly_info = self._find_anomaly_info(
            anom_date, test_name, profile_data
        )

        # Gather events
        timeline = profile_data.get("clinical_timeline", {})

        medical_records = self._gather_medical_records(
            timeline, window_start, anom_date
        )
        medication_changes = self._gather_medication_changes(
            timeline, window_start, anom_date
        )
        symptom_reports = self._gather_symptom_reports(
            timeline, window_start, anom_date
        )

        all_events = medical_records + medication_changes + symptom_reports
        event_count = len(all_events)

        # Build correlation summary
        correlation_summary = self._build_correlation_summary(
            anomaly_info, test_name, window_days,
            medical_records, medication_changes, symptom_reports
        )

        return {
            "anomaly": anomaly_info,
            "window": {
                "start_date": window_start.isoformat(),
                "end_date": anom_date.isoformat(),
                "days": window_days,
            },
            "events_by_source": {
                "medical_records": medical_records,
                "medication_changes": medication_changes,
                "symptom_reports": symptom_reports,
            },
            "event_count": event_count,
            "correlation_summary": correlation_summary,
        }

    # ── Private Helpers ───────────────────────────────────────

    def _get_window_days(self, test_name: str) -> int:
        """Look up investigation window for a lab test."""
        key = test_name.lower().strip()
        if key in INVESTIGATION_WINDOWS:
            return INVESTIGATION_WINDOWS[key]

        # Partial match
        for wk, wv in INVESTIGATION_WINDOWS.items():
            if wk == "default":
                continue
            if wk in key or key in wk:
                return wv

        return INVESTIGATION_WINDOWS["default"]

    def _find_anomaly_info(
        self, anom_date: date, test_name: str, profile_data: dict
    ) -> dict:
        """Find the anomaly value and compute expected from regression."""
        timeline = profile_data.get("clinical_timeline", {})
        labs = timeline.get("labs", [])

        # Find the matching lab result
        key = test_name.lower().strip()
        actual_value = None
        for lab in labs:
            lab_name = (lab.get("name") or lab.get("test_name") or "").strip()
            if lab_name.lower() != key:
                continue
            lab_date = self._parse_date(lab.get("test_date") or lab.get("date"))
            if lab_date and lab_date == anom_date:
                actual_value = self._parse_numeric(
                    lab.get("value") or lab.get("value_text")
                )
                break

        return {
            "date": anom_date.isoformat(),
            "value": actual_value,
            "test_name": test_name,
        }

    def _gather_medical_records(
        self, timeline: dict, window_start: date, window_end: date
    ) -> list:
        """Gather diagnoses and procedures within the window."""
        records = []

        # Diagnoses
        for dx in timeline.get("diagnoses", []):
            dx_date = self._parse_date(
                dx.get("date_diagnosed") or dx.get("date")
            )
            if not dx_date:
                continue
            if window_start <= dx_date <= window_end:
                provenance = {}
                if dx.get("source_file"):
                    provenance["source_file"] = dx["source_file"]
                if dx.get("source_page"):
                    provenance["source_page"] = dx["source_page"]
                if dx.get("provider"):
                    provenance["provider"] = dx["provider"]

                records.append({
                    "date": dx_date.isoformat(),
                    "title": "Diagnosis: " + (dx.get("name") or "Unknown"),
                    "description": (
                        (dx.get("name") or "Unknown condition") +
                        (" — " + dx.get("icd10") if dx.get("icd10") else "") +
                        (" (severity: " + dx.get("severity") + ")" if dx.get("severity") else "")
                    ),
                    "event_type": "diagnosis",
                    "provenance": provenance,
                })

        # Procedures
        for proc in timeline.get("procedures", []):
            proc_date = self._parse_date(proc.get("procedure_date"))
            if not proc_date:
                continue
            if window_start <= proc_date <= window_end:
                provenance = {}
                if proc.get("source_file"):
                    provenance["source_file"] = proc["source_file"]
                if proc.get("source_page"):
                    provenance["source_page"] = proc["source_page"]
                if proc.get("provider"):
                    provenance["provider"] = proc["provider"]

                records.append({
                    "date": proc_date.isoformat(),
                    "title": "Procedure: " + (proc.get("name") or "Unknown"),
                    "description": (
                        (proc.get("name") or "Unknown procedure") +
                        (" — " + proc.get("notes") if proc.get("notes") else "")
                    ),
                    "event_type": "procedure",
                    "provenance": provenance,
                })

        # Sort by date
        records.sort(key=lambda r: r["date"])
        return records

    def _gather_medication_changes(
        self, timeline: dict, window_start: date, window_end: date
    ) -> list:
        """Find medication starts, stops, and dose changes within the window."""
        changes = []

        for med in timeline.get("medications", []):
            med_name = med.get("name") or "Unknown medication"

            # Check start_date
            start_date = self._parse_date(med.get("start_date"))
            if start_date and window_start <= start_date <= window_end:
                provenance = {}
                if med.get("source_file"):
                    provenance["source_file"] = med["source_file"]
                if med.get("source_page"):
                    provenance["source_page"] = med["source_page"]
                if med.get("prescriber"):
                    provenance["prescriber"] = med["prescriber"]

                changes.append({
                    "date": start_date.isoformat(),
                    "medication": med_name,
                    "change_type": "started",
                    "detail": (
                        "Started " + med_name +
                        (" " + med.get("dose", "") if med.get("dose") else "") +
                        (" " + med.get("frequency", "") if med.get("frequency") else "") +
                        (" — " + med.get("reason", "") if med.get("reason") else "")
                    ),
                    "provenance": provenance,
                })

            # Check end_date (discontinuation)
            end_date = self._parse_date(med.get("end_date"))
            if end_date and window_start <= end_date <= window_end:
                provenance = {}
                if med.get("source_file"):
                    provenance["source_file"] = med["source_file"]
                if med.get("source_page"):
                    provenance["source_page"] = med["source_page"]
                if med.get("prescriber"):
                    provenance["prescriber"] = med["prescriber"]

                changes.append({
                    "date": end_date.isoformat(),
                    "medication": med_name,
                    "change_type": "stopped",
                    "detail": (
                        "Stopped " + med_name +
                        (" — " + med.get("reason", "") if med.get("reason") else "")
                    ),
                    "provenance": provenance,
                })

            # Check dose_changes if present
            for dc in med.get("dose_changes", []):
                dc_date = self._parse_date(dc.get("date"))
                if dc_date and window_start <= dc_date <= window_end:
                    provenance = {}
                    if dc.get("source_file"):
                        provenance["source_file"] = dc["source_file"]
                    if dc.get("source_page"):
                        provenance["source_page"] = dc["source_page"]

                    changes.append({
                        "date": dc_date.isoformat(),
                        "medication": med_name,
                        "change_type": "dose_changed",
                        "detail": (
                            med_name + " dose changed" +
                            (" from " + str(dc.get("from_dose", "")) if dc.get("from_dose") else "") +
                            (" to " + str(dc.get("to_dose", "")) if dc.get("to_dose") else "") +
                            (" — " + dc.get("reason", "") if dc.get("reason") else "")
                        ),
                        "provenance": provenance,
                    })

        changes.sort(key=lambda c: c["date"])
        return changes

    def _gather_symptom_reports(
        self, timeline: dict, window_start: date, window_end: date
    ) -> list:
        """Find symptom episodes within the window."""
        reports = []

        for symptom in timeline.get("symptoms", []):
            symptom_name = symptom.get("symptom_name") or "Unknown symptom"

            for episode in symptom.get("episodes", []):
                ep_date = self._parse_date(episode.get("episode_date"))
                if not ep_date:
                    continue
                if window_start <= ep_date <= window_end:
                    reports.append({
                        "date": ep_date.isoformat(),
                        "symptom_name": symptom_name,
                        "intensity": episode.get("intensity", "unknown"),
                        "description": episode.get("description", ""),
                        "triggers": episode.get("triggers", ""),
                    })

        reports.sort(key=lambda r: r["date"])
        return reports

    def _build_correlation_summary(
        self,
        anomaly_info: dict,
        test_name: str,
        window_days: int,
        medical_records: list,
        medication_changes: list,
        symptom_reports: list,
    ) -> dict:
        """
        Generate a plain-language correlation summary suitable for
        discussing with a doctor.
        """
        value = anomaly_info.get("value")
        value_str = str(value) if value is not None else "an unexpected level"

        total_events = len(medical_records) + len(medication_changes) + len(symptom_reports)

        if total_events == 0:
            return {
                "discuss_because": (
                    "Your " + test_name + " showed an unexpected value of " +
                    value_str + ". No recorded events were found in the " +
                    str(window_days) + " days before this test. "
                    "Discuss with your doctor whether unreported changes "
                    "(diet, stress, missed doses) could explain this result."
                ),
                "how_to_bring_up": (
                    "I noticed my " + test_name + " result of " + value_str +
                    " was different from what we expected. I couldn't find "
                    "anything obvious that changed. Can we discuss what "
                    "might have caused this?"
                ),
            }

        # Build event summary text
        event_parts = []
        if medical_records:
            record_names = [r["title"] for r in medical_records[:3]]
            event_parts.append(
                str(len(medical_records)) + " medical record(s): " +
                ", ".join(record_names)
            )
        if medication_changes:
            change_descs = [c["detail"] for c in medication_changes[:3]]
            event_parts.append(
                str(len(medication_changes)) + " medication change(s): " +
                ", ".join(change_descs)
            )
        if symptom_reports:
            symptom_names = list(set(
                s["symptom_name"] for s in symptom_reports
            ))[:3]
            event_parts.append(
                str(len(symptom_reports)) + " symptom report(s): " +
                ", ".join(symptom_names)
            )

        events_text = "; ".join(event_parts)

        discuss_because = (
            "Your " + test_name + " showed an unexpected value of " +
            value_str + ". During the " + str(window_days) +
            " days before this test, your records show: " +
            events_text + ". Discuss with your doctor to determine "
            "whether these events explain the change."
        )

        how_to_bring_up = (
            "I noticed my " + test_name + " result of " + value_str +
            " was different from what we expected. In the " +
            str(window_days) + " days before, there were " +
            str(total_events) + " recorded events. Can we review "
            "whether any of these could explain the change?"
        )

        return {
            "discuss_because": discuss_because,
            "how_to_bring_up": how_to_bring_up,
        }

    def _empty_investigation(self, anomaly_date: str, test_name: str) -> dict:
        """Return an empty investigation result on error."""
        return {
            "anomaly": {"date": anomaly_date, "value": None, "test_name": test_name},
            "window": {"start_date": anomaly_date, "end_date": anomaly_date, "days": 0},
            "events_by_source": {
                "medical_records": [],
                "medication_changes": [],
                "symptom_reports": [],
            },
            "event_count": 0,
            "correlation_summary": {
                "discuss_because": "Unable to investigate this anomaly.",
                "how_to_bring_up": "I had an unexpected lab result but need help understanding it.",
            },
        }

    def _parse_date(self, date_val) -> Optional[date]:
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

    def _parse_numeric(self, value) -> Optional[float]:
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
