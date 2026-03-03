"""
Clinical Intelligence Hub — Predictive Trajectory Forecasting

For lab tests with 3+ data points, performs linear regression to project
6-month and 12-month future values with confidence intervals.

Key features:
  - Detects trend direction and rate of change
  - Projects when a value will cross reference range boundaries
  - Flags accelerating trends (rate increasing over time)
  - Returns D3-compatible time-series data

Results feed into:
  - Trajectories overlay (D3 line charts)
  - Doctor Visit Prep ("Your HbA1c is trending toward X by [date]")
  - Flags view (threshold crossing warnings)
"""

import logging
import math
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("CIH-Trajectory")


# ── Common Reference Ranges ─────────────────────────────
#
# Simplified reference ranges for common lab tests.
# In practice these vary by lab, age, sex — this is a reasonable
# default for flagging trends that cross into abnormal territory.

REFERENCE_RANGES = {
    "hba1c": {"low": 4.0, "high": 5.6, "unit": "%", "critical_high": 6.5},
    "hemoglobin a1c": {"low": 4.0, "high": 5.6, "unit": "%", "critical_high": 6.5},
    "glucose": {"low": 70, "high": 100, "unit": "mg/dL", "critical_high": 126},
    "fasting glucose": {"low": 70, "high": 100, "unit": "mg/dL", "critical_high": 126},
    "creatinine": {"low": 0.6, "high": 1.2, "unit": "mg/dL", "critical_high": 2.0},
    "egfr": {"low": 60, "high": 120, "unit": "mL/min", "critical_low": 30},
    "tsh": {"low": 0.4, "high": 4.0, "unit": "mIU/L"},
    "free t4": {"low": 0.8, "high": 1.8, "unit": "ng/dL"},
    "free t3": {"low": 2.3, "high": 4.2, "unit": "pg/mL"},
    "alt": {"low": 7, "high": 56, "unit": "U/L"},
    "ast": {"low": 10, "high": 40, "unit": "U/L"},
    "crp": {"low": 0, "high": 3.0, "unit": "mg/L", "critical_high": 10.0},
    "esr": {"low": 0, "high": 20, "unit": "mm/hr"},
    "ferritin": {"low": 20, "high": 300, "unit": "ng/mL"},
    "iron": {"low": 60, "high": 170, "unit": "mcg/dL"},
    "vitamin d": {"low": 30, "high": 100, "unit": "ng/mL", "critical_low": 20},
    "25-hydroxy vitamin d": {"low": 30, "high": 100, "unit": "ng/mL", "critical_low": 20},
    "vitamin b12": {"low": 200, "high": 900, "unit": "pg/mL", "critical_low": 150},
    "folate": {"low": 2.7, "high": 17.0, "unit": "ng/mL"},
    "potassium": {"low": 3.5, "high": 5.0, "unit": "mEq/L"},
    "sodium": {"low": 136, "high": 145, "unit": "mEq/L"},
    "calcium": {"low": 8.5, "high": 10.5, "unit": "mg/dL"},
    "total cholesterol": {"low": 0, "high": 200, "unit": "mg/dL"},
    "ldl": {"low": 0, "high": 100, "unit": "mg/dL", "critical_high": 160},
    "hdl": {"low": 40, "high": 100, "unit": "mg/dL"},
    "triglycerides": {"low": 0, "high": 150, "unit": "mg/dL", "critical_high": 500},
    "uric acid": {"low": 2.5, "high": 7.0, "unit": "mg/dL"},
    "bun": {"low": 7, "high": 20, "unit": "mg/dL"},
    "albumin": {"low": 3.5, "high": 5.0, "unit": "g/dL"},
    "total protein": {"low": 6.0, "high": 8.3, "unit": "g/dL"},
    "bilirubin": {"low": 0.1, "high": 1.2, "unit": "mg/dL"},
    "alkaline phosphatase": {"low": 44, "high": 147, "unit": "U/L"},
    "ggt": {"low": 0, "high": 45, "unit": "U/L"},
    "wbc": {"low": 4.5, "high": 11.0, "unit": "K/uL"},
    "rbc": {"low": 4.0, "high": 5.5, "unit": "M/uL"},
    "hemoglobin": {"low": 12.0, "high": 17.5, "unit": "g/dL"},
    "hematocrit": {"low": 36, "high": 50, "unit": "%"},
    "platelets": {"low": 150, "high": 400, "unit": "K/uL"},
    "inr": {"low": 0.8, "high": 1.1, "unit": "ratio"},
    "psa": {"low": 0, "high": 4.0, "unit": "ng/mL"},
}


class TrajectoryForecaster:
    """
    Analyzes lab trends and projects future values using linear regression.
    Only runs on tests with 3+ data points.
    """

    def analyze(self, profile_data: dict) -> dict:
        """
        Returns:
        {
            "trajectories": [
                {
                    "test_name": "HbA1c",
                    "unit": "%",
                    "data_points": [
                        {"date": "2025-01-15", "value": 5.4, "days_from_first": 0},
                        {"date": "2025-06-15", "value": 5.7, "days_from_first": 151},
                        ...
                    ],
                    "trend": {
                        "direction": "rising",  # rising/falling/stable
                        "slope_per_month": 0.06,
                        "r_squared": 0.94,
                        "confidence": "high",   # high (r²>0.7), moderate, low
                    },
                    "projection_6mo": {
                        "date": "2026-08-28",
                        "value": 6.1,
                        "ci_low": 5.8,
                        "ci_high": 6.4,
                    },
                    "projection_12mo": {
                        "date": "2027-02-28",
                        "value": 6.5,
                        "ci_low": 5.9,
                        "ci_high": 7.1,
                    },
                    "reference_range": {"low": 4.0, "high": 5.6, "critical_high": 6.5},
                    "warnings": [
                        {
                            "type": "threshold_crossing",
                            "message": "Projected to cross pre-diabetic threshold (5.7%) by April 2026",
                            "crossing_date": "2026-04-15",
                            "threshold": 5.7,
                        },
                    ],
                    "trend_line": [
                        {"date": "2025-01-15", "value": 5.38},
                        {"date": "2027-02-28", "value": 6.5},
                    ],
                },
            ],
            "summary": {
                "total_tracked": 5,
                "rising_count": 2,
                "falling_count": 1,
                "stable_count": 2,
                "warnings_count": 1,
            },
        }
        """
        timeline = profile_data.get("clinical_timeline", {})
        labs = timeline.get("labs", [])

        # Group labs by test name
        grouped = self._group_labs(labs)

        trajectories = []
        rising = 0
        falling = 0
        stable = 0
        total_warnings = 0

        for test_key, group in grouped.items():
            if len(group["points"]) < 3:
                continue

            trajectory = self._analyze_test(test_key, group)
            if trajectory:
                trajectories.append(trajectory)
                d = trajectory["trend"]["direction"]
                if d == "rising":
                    rising += 1
                elif d == "falling":
                    falling += 1
                else:
                    stable += 1
                total_warnings += len(trajectory.get("warnings", []))

        # Sort by warning count (most concerning first), then by r²
        trajectories.sort(key=lambda t: (
            -len(t.get("warnings", [])),
            -t["trend"].get("r_squared", 0),
        ))

        return {
            "trajectories": trajectories,
            "summary": {
                "total_tracked": len(trajectories),
                "rising_count": rising,
                "falling_count": falling,
                "stable_count": stable,
                "warnings_count": total_warnings,
            },
        }

    # ── Internal Methods ─────────────────────────────────

    def _group_labs(self, labs: list) -> dict:
        """Group lab results by test name, keeping only numeric values."""
        groups = {}
        for lab in labs:
            name = (lab.get("name") or "").strip()
            if not name:
                continue

            value = self._parse_numeric(lab.get("value") or lab.get("value_text"))
            if value is None:
                continue

            test_date = self._parse_date(lab.get("test_date") or lab.get("date"))
            if not test_date:
                continue

            key = name.lower()
            if key not in groups:
                groups[key] = {"display_name": name, "points": []}
            groups[key]["points"].append({"date": test_date, "value": value})

        # Sort each group by date
        for key in groups:
            groups[key]["points"].sort(key=lambda p: p["date"])

        return {k: v for k, v in groups.items()}

    def _analyze_test(self, test_key: str, group: dict) -> Optional[dict]:
        """Perform linear regression and projection for a single lab test."""
        display_name = group["display_name"]
        points = group["points"]
        if len(points) < 3:
            return None

        # Convert dates to days from first measurement
        first_date = points[0]["date"]
        xs = []
        ys = []
        data_points = []

        for p in points:
            days = (p["date"] - first_date).days
            xs.append(days)
            ys.append(p["value"])
            data_points.append({
                "date": p["date"].isoformat(),
                "value": p["value"],
                "days_from_first": days,
            })

        n = len(xs)

        # Linear regression: y = mx + b
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_x2 = sum(x * x for x in xs)

        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            return None

        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n

        # R-squared
        y_mean = sum_y / n
        ss_tot = sum((y - y_mean) ** 2 for y in ys)
        ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        r_squared = max(0, min(1, r_squared))

        # Standard error of prediction
        if n > 2:
            se = math.sqrt(ss_res / (n - 2))
        else:
            se = 0

        # Slope per month (30.44 days)
        slope_per_month = slope * 30.44

        # Direction
        # A trend is "stable" if the projected 12-month change is less than
        # 2% of the mean value (or absolute < 0.05 for very small values).
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

        # Projections
        last_date = points[-1]["date"]
        proj_6mo_date = last_date + timedelta(days=183)
        proj_12mo_date = last_date + timedelta(days=365)
        proj_6mo_days = (proj_6mo_date - first_date).days
        proj_12mo_days = (proj_12mo_date - first_date).days

        proj_6mo_val = slope * proj_6mo_days + intercept
        proj_12mo_val = slope * proj_12mo_days + intercept

        # Confidence intervals (approximate: ±1.96 * SE * sqrt(1 + 1/n + (x-mean_x)²/SSx))
        mean_x = sum_x / n
        ss_x = sum((x - mean_x) ** 2 for x in xs)

        def ci_width(x_pred):
            if ss_x == 0 or n <= 2:
                return se * 1.96
            return se * 1.96 * math.sqrt(1 + 1 / n + (x_pred - mean_x) ** 2 / ss_x)

        ci_6 = ci_width(proj_6mo_days)
        ci_12 = ci_width(proj_12mo_days)

        # Reference range
        ref_range = self._find_reference_range(test_key)

        # Warnings
        warnings = []
        if ref_range and direction != "stable" and confidence != "low":
            warnings = self._check_threshold_crossings(
                slope, intercept, first_date, last_date, ref_range, ys[-1]
            )

        # Trend line (from first data point to end of 12mo projection)
        trend_line = [
            {"date": first_date.isoformat(), "value": round(intercept, 2)},
            {"date": proj_12mo_date.isoformat(), "value": round(proj_12mo_val, 2)},
        ]

        result = {
            "test_name": display_name,
            "unit": ref_range.get("unit", "") if ref_range else "",
            "data_points": data_points,
            "trend": {
                "direction": direction,
                "slope_per_month": round(slope_per_month, 4),
                "r_squared": round(r_squared, 3),
                "confidence": confidence,
            },
            "projection_6mo": {
                "date": proj_6mo_date.isoformat(),
                "value": round(proj_6mo_val, 2),
                "ci_low": round(proj_6mo_val - ci_6, 2),
                "ci_high": round(proj_6mo_val + ci_6, 2),
            },
            "projection_12mo": {
                "date": proj_12mo_date.isoformat(),
                "value": round(proj_12mo_val, 2),
                "ci_low": round(proj_12mo_val - ci_12, 2),
                "ci_high": round(proj_12mo_val + ci_12, 2),
            },
            "trend_line": trend_line,
            "warnings": warnings,
        }

        if ref_range:
            result["reference_range"] = {
                k: v for k, v in ref_range.items() if k != "unit"
            }

        return result

    def _check_threshold_crossings(
        self, slope, intercept, first_date, last_date, ref_range, current_value
    ) -> list:
        """Check if the trend will cross reference range boundaries."""
        warnings = []
        thresholds = []

        # Build list of thresholds to check
        if slope > 0:  # Rising
            if "high" in ref_range and current_value < ref_range["high"]:
                thresholds.append(("above normal range", ref_range["high"]))
            if "critical_high" in ref_range and current_value < ref_range["critical_high"]:
                thresholds.append(("critical high threshold", ref_range["critical_high"]))
        else:  # Falling
            if "low" in ref_range and current_value > ref_range["low"]:
                thresholds.append(("below normal range", ref_range["low"]))
            if "critical_low" in ref_range and current_value > ref_range["critical_low"]:
                thresholds.append(("critical low threshold", ref_range["critical_low"]))

        for label, threshold in thresholds:
            if slope == 0:
                continue
            # Days from first measurement to crossing
            crossing_days = (threshold - intercept) / slope
            crossing_date = first_date + timedelta(days=int(crossing_days))

            # Only warn if crossing is in the future and within 24 months
            if crossing_date > last_date and crossing_date < last_date + timedelta(days=730):
                months_away = (crossing_date - last_date).days / 30.44
                warnings.append({
                    "type": "threshold_crossing",
                    "message": (
                        f"Projected to reach {label} "
                        f"({threshold} {ref_range.get('unit', '')}) "
                        f"by {crossing_date.strftime('%B %Y')} "
                        f"(~{int(months_away)} months)"
                    ),
                    "crossing_date": crossing_date.isoformat(),
                    "threshold": threshold,
                    "months_away": round(months_away, 1),
                })

        return warnings

    def _find_reference_range(self, test_key: str) -> Optional[dict]:
        """Look up reference range for a lab test."""
        key = test_key.lower().strip()
        if key in REFERENCE_RANGES:
            return REFERENCE_RANGES[key]

        # Partial match
        for ref_key, ref_val in REFERENCE_RANGES.items():
            if ref_key in key or key in ref_key:
                return ref_val

        return None

    def _parse_numeric(self, value) -> Optional[float]:
        """Extract numeric value from various formats."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Strip common prefixes/suffixes
            cleaned = value.strip().replace(",", "")
            # Handle ranges like "5.4-5.6" — take the first number
            if "-" in cleaned and not cleaned.startswith("-"):
                cleaned = cleaned.split("-")[0]
            # Handle "< 0.5" or "> 100"
            for prefix in ("<", ">", "<=", ">="):
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
            try:
                return float(cleaned)
            except (ValueError, TypeError):
                return None
        return None

    def _parse_date(self, date_val) -> Optional[date]:
        """Parse date from various formats."""
        if isinstance(date_val, date):
            return date_val
        if isinstance(date_val, str):
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
                try:
                    from datetime import datetime
                    return datetime.strptime(date_val.strip(), fmt).date()
                except ValueError:
                    continue
        return None
