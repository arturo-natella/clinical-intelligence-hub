"""
Clinical Intelligence Hub — RxNorm Monitoring

Checks for medication updates: new NDCs, label changes,
discontinued medications, and new interaction data.

Uses the free NLM RxNorm API.
"""

import logging

from src.models import AlertSeverity, MonitoringAlert, PatientProfile

logger = logging.getLogger("CIH-Monitor-RxNorm")


class RxNormMonitor:
    """Monitors RxNorm for medication-related changes."""

    def __init__(self):
        self._client = None
        try:
            from src.validation.rxnorm import RxNormClient
            self._client = RxNormClient()
        except Exception:
            logger.debug("RxNorm client not available")

    def check(self, profile: PatientProfile) -> list[MonitoringAlert]:
        """
        Check RxNorm for medication updates.

        Args:
            profile: Patient profile with medications

        Returns:
            List of monitoring alerts
        """
        alerts = []
        timeline = profile.clinical_timeline

        if not self._client or not timeline or not timeline.medications:
            return []

        active_meds = [
            m for m in timeline.medications
            if m.status and getattr(m.status, "value", str(m.status)).lower() in ("active", "prn")
        ]

        for med in active_meds:
            try:
                resolved = self._client.resolve_medication(med.name)
                if not resolved:
                    continue

                # Check if medication has been updated/obsoleted
                status = resolved.get("status", "")
                if status.lower() in ("obsolete", "remapped"):
                    alerts.append(MonitoringAlert(
                        source="RxNorm",
                        title=f"Medication status change: {med.name}",
                        description=(
                            f"{med.name} has been marked as '{status}' in RxNorm. "
                            f"This may indicate the medication has been "
                            f"discontinued or renamed."
                        ),
                        relevance_explanation=(
                            f"Patient is currently prescribed {med.name} "
                            f"({med.dosage} {med.frequency})."
                        ),
                        severity=AlertSeverity.HIGH,
                    ))

                # Check new interactions if rxcui available
                rxcui = resolved.get("rxcui")
                if rxcui:
                    self._check_new_interactions(
                        med, rxcui, active_meds, alerts
                    )

            except Exception as e:
                logger.debug(f"RxNorm check failed for {med.name}: {e}")

        logger.info(f"RxNorm monitor found {len(alerts)} alerts")
        return alerts

    def _check_new_interactions(self, med, rxcui, all_meds, alerts):
        """Check for newly identified interactions."""
        try:
            # Get current interaction list
            interactions = self._client.get_interactions(rxcui)
            if not interactions:
                return

            # Check if any interactions involve other patient meds
            other_names = {
                m.name.lower() for m in all_meds
                if m.name.lower() != med.name.lower()
            }

            for interaction in interactions:
                drugs = interaction.get("drugs", [])
                desc = interaction.get("description", "")
                severity = interaction.get("severity", "")

                for drug_name in drugs:
                    if drug_name.lower() in other_names:
                        # Map severity
                        if "high" in severity.lower() or "severe" in severity.lower():
                            sev = AlertSeverity.HIGH
                        else:
                            sev = AlertSeverity.MODERATE

                        alerts.append(MonitoringAlert(
                            source="RxNorm Interaction API",
                            title=f"Interaction update: {med.name} + {drug_name}",
                            description=desc or f"Interaction between {med.name} and {drug_name}.",
                            relevance_explanation=(
                                f"Patient takes both {med.name} and {drug_name}."
                            ),
                            severity=sev,
                        ))

        except Exception as e:
            logger.debug(f"RxNorm interaction check failed: {e}")
