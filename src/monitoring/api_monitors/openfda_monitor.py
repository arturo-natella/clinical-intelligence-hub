"""
Clinical Intelligence Hub — OpenFDA Monitoring

Checks for new drug recalls, safety alerts, and adverse event signals
relevant to the patient's medications.

Uses the free OpenFDA API (240 requests/min without key).
"""

import logging
from datetime import date, timedelta

from src.models import AlertSeverity, MonitoringAlert, PatientProfile

logger = logging.getLogger("CIH-Monitor-OpenFDA")


class OpenFDAMonitor:
    """Monitors OpenFDA for drug recalls and safety alerts."""

    def __init__(self, api_key: str = None):
        self._api_key = api_key

    def check(self, profile: PatientProfile,
              days_back: int = 30) -> list[MonitoringAlert]:
        """
        Check OpenFDA for recalls and safety alerts.

        Args:
            profile: The patient's clinical profile
            days_back: How many days back to check

        Returns:
            List of monitoring alerts
        """
        alerts = []
        timeline = profile.clinical_timeline

        if not timeline or not timeline.medications:
            return []

        try:
            from src.validation.openfda import OpenFDAClient
            client = OpenFDAClient(api_key=self._api_key)
        except Exception as e:
            logger.error(f"OpenFDA client init failed: {e}")
            return []

        active_meds = [
            m for m in timeline.medications
            if m.status and getattr(m.status, "value", str(m.status)).lower() in ("active", "prn")
        ]

        for med in active_meds:
            # Check for recent recalls
            try:
                recalls = client.check_drug_recalls(med.name, limit=5)
                cutoff = (date.today() - timedelta(days=days_back)).strftime("%Y%m%d")

                for recall in recalls:
                    recall_date = recall.get("report_date", "")
                    if recall_date >= cutoff:
                        classification = recall.get("classification", "")
                        severity = AlertSeverity.CRITICAL if "I" in classification else AlertSeverity.HIGH

                        alerts.append(MonitoringAlert(
                            source="OpenFDA",
                            title=f"Drug recall: {med.name}",
                            description=(
                                f"FDA {classification} recall: "
                                f"{recall.get('reason', 'See FDA notice')}. "
                                f"Status: {recall.get('status', 'Unknown')}."
                            ),
                            relevance_explanation=(
                                f"Patient is currently taking {med.name} "
                                f"({med.dosage} {med.frequency})."
                            ),
                            severity=severity,
                        ))
            except Exception as e:
                logger.debug(f"OpenFDA recall check failed for {med.name}: {e}")

            # Check for new adverse event signals
            try:
                events = client.get_adverse_events(med.name, limit=5)
                # Flag any new serious reactions with high report counts
                for event in events:
                    if event.get("count", 0) > 1000:
                        reaction = event.get("reaction", "Unknown")
                        alerts.append(MonitoringAlert(
                            source="OpenFDA FAERS",
                            title=f"Adverse event signal: {med.name}",
                            description=(
                                f"High frequency adverse event for {med.name}: "
                                f"{reaction} ({event['count']} reports in FAERS)."
                            ),
                            relevance_explanation=(
                                f"Patient takes {med.name}. Discuss with doctor "
                                f"if experiencing {reaction.lower()}."
                            ),
                            severity=AlertSeverity.MODERATE,
                        ))
            except Exception as e:
                logger.debug(f"OpenFDA adverse events check failed for {med.name}: {e}")

        logger.info(f"OpenFDA monitor found {len(alerts)} alerts")
        return alerts
