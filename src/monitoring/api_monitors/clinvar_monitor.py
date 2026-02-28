"""
Clinical Intelligence Hub — ClinVar Monitoring

Checks for updated variant classifications that may affect
the patient's genetic test results.

Uses NCBI E-utilities (free API).
"""

import json
import logging
import urllib.parse
import urllib.request
from datetime import date, timedelta

from src.models import AlertSeverity, MonitoringAlert, PatientProfile

logger = logging.getLogger("CIH-Monitor-ClinVar")

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class ClinVarMonitor:
    """Monitors ClinVar for reclassified genetic variants."""

    def __init__(self, api_key: str = None, email: str = None):
        self._api_key = api_key
        self._email = email or "clinicalintelligencehub@example.com"

    def check(self, profile: PatientProfile,
              days_back: int = 30) -> list[MonitoringAlert]:
        """
        Check ClinVar for reclassified variants relevant to the patient.

        Args:
            profile: Patient profile with genetic data
            days_back: Days to look back for changes

        Returns:
            List of monitoring alerts
        """
        alerts = []
        timeline = profile.clinical_timeline

        if not timeline or not timeline.genetics:
            return []

        cutoff = date.today() - timedelta(days=days_back)
        date_str = cutoff.strftime("%Y/%m/%d")

        for variant in timeline.genetics:
            if not variant.gene:
                continue

            try:
                query = f"{variant.gene}[gene] AND {date_str}:3000[MDAT]"
                results = self._search_clinvar(query, max_results=5)

                for result in results:
                    title = result.get("title", "")
                    significance = result.get("clinical_significance", "")

                    # Alert if significance changed or new entry
                    if significance and "pathogenic" in significance.lower():
                        alerts.append(MonitoringAlert(
                            source="ClinVar",
                            title=f"Variant update: {variant.gene}",
                            description=(
                                f"ClinVar updated classification for "
                                f"{variant.gene}: {title}. "
                                f"Current significance: {significance}."
                            ),
                            relevance_explanation=(
                                f"Patient has {variant.gene} {variant.variant} "
                                f"({variant.phenotype}). "
                                f"Updated classification may affect clinical guidance."
                            ),
                            severity=AlertSeverity.HIGH,
                        ))
                    elif significance:
                        alerts.append(MonitoringAlert(
                            source="ClinVar",
                            title=f"Variant update: {variant.gene}",
                            description=(
                                f"New ClinVar entry for {variant.gene}: {title}. "
                                f"Significance: {significance}."
                            ),
                            relevance_explanation=(
                                f"Patient has {variant.gene} {variant.variant}."
                            ),
                            severity=AlertSeverity.LOW,
                        ))

            except Exception as e:
                logger.debug(f"ClinVar check failed for {variant.gene}: {e}")

        logger.info(f"ClinVar monitor found {len(alerts)} alerts")
        return alerts

    def _search_clinvar(self, query: str, max_results: int = 5) -> list[dict]:
        """Search ClinVar via E-utilities."""
        # Step 1: esearch for IDs
        params = {
            "db": "clinvar",
            "term": query,
            "retmax": str(max_results),
            "retmode": "json",
            "email": self._email,
        }
        if self._api_key:
            params["api_key"] = self._api_key

        url = f"{EUTILS_BASE}/esearch.fcgi?{urllib.parse.urlencode(params)}"

        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ClinicalIntelligenceHub/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())

            ids = data.get("esearchresult", {}).get("idlist", [])
            if not ids:
                return []

            # Step 2: esummary for details
            params2 = {
                "db": "clinvar",
                "id": ",".join(ids),
                "retmode": "json",
                "email": self._email,
            }
            if self._api_key:
                params2["api_key"] = self._api_key

            url2 = f"{EUTILS_BASE}/esummary.fcgi?{urllib.parse.urlencode(params2)}"
            req2 = urllib.request.Request(
                url2, headers={"User-Agent": "ClinicalIntelligenceHub/1.0"}
            )
            with urllib.request.urlopen(req2, timeout=15) as response2:
                summary = json.loads(response2.read().decode())

            results = []
            result_data = summary.get("result", {})
            for uid in ids:
                entry = result_data.get(uid, {})
                if entry:
                    results.append({
                        "title": entry.get("title", ""),
                        "clinical_significance": entry.get(
                            "clinical_significance", {}).get("description", ""),
                    })

            return results

        except Exception as e:
            logger.debug(f"ClinVar search failed: {e}")
            return []
