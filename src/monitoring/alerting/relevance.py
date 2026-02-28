"""
Clinical Intelligence Hub — Alert Relevance Assessment

Evaluates whether a monitoring alert is genuinely relevant to the
specific patient, filters noise, and generates addendum documents
for significant findings.
"""

import logging
from typing import Optional

from src.models import AlertSeverity, MonitoringAlert, PatientProfile

logger = logging.getLogger("CIH-Relevance")


class RelevanceAssessor:
    """Assesses whether monitoring alerts are truly relevant to the patient."""

    # Severity thresholds for generating addendums
    ADDENDUM_THRESHOLD = {
        AlertSeverity.CRITICAL: True,
        AlertSeverity.HIGH: True,
        AlertSeverity.MODERATE: False,
        AlertSeverity.LOW: False,
        AlertSeverity.INFO: False,
    }

    def assess(self, alert: MonitoringAlert,
               profile: PatientProfile) -> dict:
        """
        Assess alert relevance to the specific patient.

        Returns:
            dict with:
                relevant (bool): Whether alert applies to this patient
                confidence (float): 0-1 confidence score
                explanation (str): Why it's relevant or not
                generate_addendum (bool): Whether to create a report addendum
        """
        # Default assessment
        result = {
            "relevant": False,
            "confidence": 0.0,
            "explanation": "",
            "generate_addendum": False,
        }

        if not profile or not profile.clinical_timeline:
            result["explanation"] = "No patient profile loaded."
            return result

        timeline = profile.clinical_timeline

        # Check medication relevance
        med_match = self._check_medication_relevance(alert, timeline)
        if med_match["relevant"]:
            result.update(med_match)
            result["generate_addendum"] = self.ADDENDUM_THRESHOLD.get(
                alert.severity, False
            )
            return result

        # Check condition relevance
        dx_match = self._check_condition_relevance(alert, timeline)
        if dx_match["relevant"]:
            result.update(dx_match)
            result["generate_addendum"] = (
                alert.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH)
            )
            return result

        # Check genetic relevance
        gen_match = self._check_genetic_relevance(alert, timeline)
        if gen_match["relevant"]:
            result.update(gen_match)
            result["generate_addendum"] = True  # PGx is always important
            return result

        result["explanation"] = "Alert does not match patient's medications, conditions, or genetics."
        return result

    def filter_alerts(self, alerts: list[MonitoringAlert],
                      profile: PatientProfile) -> list[tuple[MonitoringAlert, dict]]:
        """
        Filter a list of alerts for relevance.

        Returns:
            List of (alert, assessment) tuples for relevant alerts only.
        """
        relevant = []
        for alert in alerts:
            assessment = self.assess(alert, profile)
            if assessment["relevant"]:
                relevant.append((alert, assessment))

        # Sort by severity (critical first)
        severity_order = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.HIGH: 1,
            AlertSeverity.MODERATE: 2,
            AlertSeverity.LOW: 3,
            AlertSeverity.INFO: 4,
        }
        relevant.sort(key=lambda x: severity_order.get(x[0].severity, 4))

        return relevant

    def generate_addendums(self, alerts: list[MonitoringAlert],
                           profile: PatientProfile,
                           output_dir) -> list:
        """
        Generate addendum documents for significant alerts.

        Returns:
            List of generated addendum file paths.
        """
        from pathlib import Path
        output_dir = Path(output_dir)
        paths = []

        try:
            from src.report.addendum import AddendumBuilder
            builder = AddendumBuilder()
        except Exception as e:
            logger.error(f"AddendumBuilder init failed: {e}")
            return []

        relevant = self.filter_alerts(alerts, profile)

        for alert, assessment in relevant:
            if assessment["generate_addendum"]:
                try:
                    path = builder.generate(alert, profile, output_dir)
                    paths.append(path)
                    logger.info(f"Generated addendum: {path.name}")
                except Exception as e:
                    logger.error(f"Addendum generation failed: {e}")

        return paths

    # ── Relevance Checks ──────────────────────────────

    def _check_medication_relevance(self, alert, timeline) -> dict:
        """Check if alert relates to patient's medications."""
        if not timeline.medications:
            return {"relevant": False}

        active_meds = {
            m.name.lower()
            for m in timeline.medications
            if m.status and getattr(m.status, "value", str(m.status)).lower() in ("active", "prn")
        }

        alert_text = (
            f"{alert.title} {alert.description} "
            f"{alert.relevance_explanation or ''}"
        ).lower()

        for med_name in active_meds:
            if med_name in alert_text:
                return {
                    "relevant": True,
                    "confidence": 0.9,
                    "explanation": f"Alert mentions patient's active medication: {med_name}.",
                }

        return {"relevant": False}

    def _check_condition_relevance(self, alert, timeline) -> dict:
        """Check if alert relates to patient's conditions."""
        if not timeline.diagnoses:
            return {"relevant": False}

        conditions = {
            dx.name.lower()
            for dx in timeline.diagnoses
            if dx.status and dx.status.lower() in ("active", "chronic")
        }

        alert_text = (
            f"{alert.title} {alert.description} "
            f"{alert.relevance_explanation or ''}"
        ).lower()

        for condition in conditions:
            if condition in alert_text:
                return {
                    "relevant": True,
                    "confidence": 0.8,
                    "explanation": f"Alert relates to patient's condition: {condition}.",
                }

        return {"relevant": False}

    def _check_genetic_relevance(self, alert, timeline) -> dict:
        """Check if alert relates to patient's genetic variants."""
        if not timeline.genetics:
            return {"relevant": False}

        genes = {
            v.gene.lower()
            for v in timeline.genetics
            if v.gene
        }

        alert_text = (
            f"{alert.title} {alert.description} "
            f"{alert.relevance_explanation or ''}"
        ).lower()

        for gene in genes:
            if gene in alert_text:
                return {
                    "relevant": True,
                    "confidence": 0.85,
                    "explanation": f"Alert relates to patient's genetic variant: {gene}.",
                }

        return {"relevant": False}
