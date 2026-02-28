"""
Clinical Intelligence Hub — PharmGKB Monitoring

Checks for updated pharmacogenomic guidelines and drug-gene
annotations relevant to the patient's genetic profile.

Uses PharmGKB REST API (free, public).
API: https://api.pharmgkb.org/
"""

import json
import logging
import urllib.parse
import urllib.request

from src.models import AlertSeverity, MonitoringAlert, PatientProfile

logger = logging.getLogger("CIH-Monitor-PharmGKB")

API_BASE = "https://api.pharmgkb.org/v1/data"


class PharmGKBMonitor:
    """Monitors PharmGKB for pharmacogenomic updates."""

    def check(self, profile: PatientProfile) -> list[MonitoringAlert]:
        """
        Check PharmGKB for updated drug-gene guidelines.

        Args:
            profile: Patient profile with genetic and medication data

        Returns:
            List of monitoring alerts
        """
        alerts = []
        timeline = profile.clinical_timeline

        if not timeline:
            return []

        # Check gene-based clinical annotations
        for variant in (timeline.genetics or []):
            if not variant.gene:
                continue

            try:
                annotations = self._get_clinical_annotations(variant.gene)

                for ann in annotations:
                    # Check if any of patient's medications appear
                    ann_drugs = ann.get("drugs", [])
                    patient_meds = {
                        m.name.lower()
                        for m in (timeline.medications or [])
                        if m.status and getattr(m.status, "value", str(m.status)).lower() in ("active", "prn")
                    }

                    matching_drugs = [
                        d for d in ann_drugs
                        if d.lower() in patient_meds
                    ]

                    if matching_drugs:
                        for drug in matching_drugs:
                            alerts.append(MonitoringAlert(
                                source="PharmGKB",
                                title=f"PGx update: {variant.gene} + {drug}",
                                description=(
                                    f"PharmGKB clinical annotation for "
                                    f"{variant.gene} and {drug}: "
                                    f"{ann.get('summary', 'Updated guidance available.')}."
                                ),
                                relevance_explanation=(
                                    f"Patient has {variant.gene} {variant.variant} "
                                    f"({variant.phenotype}) and takes {drug}."
                                ),
                                severity=AlertSeverity.HIGH,
                                url=ann.get("url"),
                            ))

            except Exception as e:
                logger.debug(f"PharmGKB check failed for {variant.gene}: {e}")

        # Check for guideline updates on patient's medications
        for med in (timeline.medications or []):
            if not med.status or getattr(med.status, "value", str(med.status)).lower() not in ("active", "prn"):
                continue

            try:
                guidelines = self._get_drug_guidelines(med.name)
                for gl in guidelines[:1]:  # Limit per medication
                    alerts.append(MonitoringAlert(
                        source="PharmGKB",
                        title=f"PGx guideline: {med.name}",
                        description=(
                            f"Pharmacogenomic guideline for {med.name}: "
                            f"{gl.get('name', '')}. "
                            f"Source: {gl.get('source', 'CPIC/DPWG')}."
                        ),
                        relevance_explanation=(
                            f"Patient takes {med.name}. Guideline may "
                            f"recommend dose adjustments based on genetic profile."
                        ),
                        severity=AlertSeverity.MODERATE,
                        url=gl.get("url"),
                    ))
            except Exception as e:
                logger.debug(f"PharmGKB guideline check failed for {med.name}: {e}")

        logger.info(f"PharmGKB monitor found {len(alerts)} alerts")
        return alerts

    def _get_clinical_annotations(self, gene: str) -> list[dict]:
        """Get clinical annotations for a gene from PharmGKB."""
        url = f"{API_BASE}/clinicalAnnotation?gene={urllib.parse.quote(gene)}"

        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ClinicalIntelligenceHub/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())

            results = []
            for item in data.get("data", []):
                drugs = []
                for rel in item.get("relatedChemicals", []):
                    drugs.append(rel.get("name", ""))

                results.append({
                    "drugs": drugs,
                    "summary": item.get("summary", ""),
                    "url": f"https://www.pharmgkb.org/clinicalAnnotation/{item.get('id', '')}",
                })

            return results

        except Exception as e:
            logger.debug(f"PharmGKB clinical annotation query failed: {e}")
            return []

    def _get_drug_guidelines(self, drug_name: str) -> list[dict]:
        """Get pharmacogenomic guidelines for a drug."""
        url = f"{API_BASE}/guideline?chemical={urllib.parse.quote(drug_name)}"

        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ClinicalIntelligenceHub/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())

            results = []
            for item in data.get("data", []):
                results.append({
                    "name": item.get("name", ""),
                    "source": item.get("source", ""),
                    "url": f"https://www.pharmgkb.org/guideline/{item.get('id', '')}",
                })

            return results

        except Exception as e:
            logger.debug(f"PharmGKB guideline query failed: {e}")
            return []
