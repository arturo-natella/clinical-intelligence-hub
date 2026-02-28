"""
Clinical Intelligence Hub — ClinicalTrials.gov Monitoring

Checks for new clinical trials relevant to the patient's conditions,
medications, and genetic profile.

Uses the ClinicalTrials.gov API v2 (free, public).
API: https://clinicaltrials.gov/data-api/about-api
"""

import json
import logging
import urllib.parse
import urllib.request

from src.models import AlertSeverity, MonitoringAlert, PatientProfile

logger = logging.getLogger("CIH-Monitor-ClinicalTrials")

API_BASE = "https://clinicaltrials.gov/api/v2/studies"


class ClinicalTrialsMonitor:
    """Monitors ClinicalTrials.gov for relevant new trials."""

    def check(self, profile: PatientProfile) -> list[MonitoringAlert]:
        """
        Check ClinicalTrials.gov for new relevant trials.

        Searches for recruiting trials that match the patient's conditions.
        """
        alerts = []
        timeline = profile.clinical_timeline

        if not timeline or not timeline.diagnoses:
            return []

        active_conditions = [
            dx for dx in timeline.diagnoses
            if dx.status and dx.status.lower() in ("active", "chronic")
        ]

        for dx in active_conditions:
            try:
                trials = self._search_trials(dx.name, status="RECRUITING")

                for trial in trials[:2]:  # Limit to 2 per condition
                    title = trial.get("title", "Untitled trial")
                    nct_id = trial.get("nct_id", "")
                    phase = trial.get("phase", "")
                    summary = trial.get("summary", "")

                    alerts.append(MonitoringAlert(
                        source="ClinicalTrials.gov",
                        title=f"Clinical trial: {dx.name}",
                        description=(
                            f"Recruiting trial: \"{title}\""
                            f"{' (Phase ' + phase + ')' if phase else ''}. "
                            f"{summary[:200] + '...' if len(summary) > 200 else summary}"
                        ),
                        relevance_explanation=(
                            f"Patient has {dx.name}. This trial may be relevant."
                        ),
                        severity=AlertSeverity.INFO,
                        url=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None,
                    ))

            except Exception as e:
                logger.debug(f"ClinicalTrials.gov search failed for {dx.name}: {e}")

        logger.info(f"ClinicalTrials.gov monitor found {len(alerts)} alerts")
        return alerts

    def _search_trials(self, condition: str, status: str = "RECRUITING",
                       max_results: int = 5) -> list[dict]:
        """Search ClinicalTrials.gov API v2."""
        params = {
            "query.cond": condition,
            "filter.overallStatus": status,
            "pageSize": str(max_results),
            "sort": "LastUpdatePostDate",
            "format": "json",
        }

        url = f"{API_BASE}?{urllib.parse.urlencode(params)}"

        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ClinicalIntelligenceHub/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())

            studies = data.get("studies", [])
            results = []

            for study in studies:
                protocol = study.get("protocolSection", {})
                ident = protocol.get("identificationModule", {})
                status_mod = protocol.get("statusModule", {})
                design = protocol.get("designModule", {})
                desc = protocol.get("descriptionModule", {})

                results.append({
                    "title": ident.get("briefTitle", ""),
                    "nct_id": ident.get("nctId", ""),
                    "phase": ", ".join(design.get("phases", [])),
                    "summary": desc.get("briefSummary", ""),
                })

            return results

        except Exception as e:
            logger.debug(f"ClinicalTrials.gov API call failed: {e}")
            return []
