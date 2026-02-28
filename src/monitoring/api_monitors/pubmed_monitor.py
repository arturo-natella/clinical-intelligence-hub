"""
Clinical Intelligence Hub — PubMed Monitoring

Checks for new publications relevant to the patient's conditions,
medications, and genetic variants.

Uses NCBI E-utilities (free, 3 req/sec without API key, 10/sec with key).
"""

import logging
from datetime import date, timedelta
from typing import Optional

from src.models import AlertSeverity, MonitoringAlert, PatientProfile

logger = logging.getLogger("CIH-Monitor-PubMed")


class PubMedMonitor:
    """Monitors PubMed for new relevant publications."""

    def __init__(self, api_key: str = None):
        self._api_key = api_key

    def check(self, profile: PatientProfile,
              days_back: int = 7) -> list[MonitoringAlert]:
        """
        Check PubMed for new publications relevant to the patient.

        Args:
            profile: The patient's clinical profile
            days_back: How many days back to search

        Returns:
            List of monitoring alerts for relevant new publications
        """
        alerts = []
        queries = self._build_queries(profile)

        if not queries:
            return []

        try:
            from src.validation.pubmed import PubMedClient
            client = PubMedClient(api_key=self._api_key)
        except Exception as e:
            logger.error(f"PubMed client init failed: {e}")
            return []

        # Add date filter
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
        date_filter = (
            f" AND (\"{start_date.strftime('%Y/%m/%d')}\""
            f"[\"{end_date.strftime('%Y/%m/%d')}\"]"
            f"[Date - Publication])"
        )

        for query_info in queries:
            try:
                full_query = query_info["query"] + date_filter
                citations = client.search(full_query, max_results=3)

                for cit in citations:
                    alerts.append(MonitoringAlert(
                        source="PubMed",
                        title=cit.title or "New publication",
                        description=(
                            f"New study: \"{cit.title}\" "
                            f"({cit.authors or 'Unknown'}, {cit.year}). "
                            f"Published in {cit.journal or 'Unknown journal'}."
                        ),
                        relevance_explanation=query_info["relevance"],
                        severity=query_info.get("severity", AlertSeverity.LOW),
                        url=(
                            f"https://pubmed.ncbi.nlm.nih.gov/{cit.pubmed_id}/"
                            if cit.pubmed_id else None
                        ),
                    ))

            except Exception as e:
                logger.debug(f"PubMed query failed: {e}")

        logger.info(f"PubMed monitor found {len(alerts)} alerts")
        return alerts

    def _build_queries(self, profile: PatientProfile) -> list[dict]:
        """Build PubMed search queries from the patient profile."""
        queries = []
        timeline = profile.clinical_timeline

        if not timeline:
            return []

        # Queries for active medications + safety
        for med in (timeline.medications or []):
            status_val = getattr(med.status, "value", str(med.status)).lower()
            if med.status and status_val in ("active", "prn"):
                queries.append({
                    "query": (
                        f'"{med.name}"[MeSH Terms] AND '
                        f'("drug-related side effects and adverse reactions"[MeSH] '
                        f'OR "safety"[Title])'
                    ),
                    "relevance": f"Patient is currently taking {med.name}.",
                    "severity": AlertSeverity.MODERATE,
                })

        # Queries for diagnoses + treatment advances
        for dx in (timeline.diagnoses or []):
            if dx.status and dx.status.lower() in ("active", "chronic"):
                queries.append({
                    "query": (
                        f'"{dx.name}"[MeSH Terms] AND '
                        f'("therapy"[Subheading] OR "treatment"[Title]) AND '
                        f'(clinical trial[pt] OR meta-analysis[pt])'
                    ),
                    "relevance": f"Patient has active diagnosis: {dx.name}.",
                    "severity": AlertSeverity.LOW,
                })

        # Queries for genetic variants + pharmacogenomics
        for variant in (timeline.genetics or []):
            if variant.clinical_significance and "actionable" in variant.clinical_significance.lower():
                queries.append({
                    "query": (
                        f'"{variant.gene}"[Title] AND '
                        f'"pharmacogenomics"[MeSH Terms]'
                    ),
                    "relevance": (
                        f"Patient has {variant.gene} {variant.variant} variant "
                        f"({variant.phenotype})."
                    ),
                    "severity": AlertSeverity.MODERATE,
                })

        return queries
