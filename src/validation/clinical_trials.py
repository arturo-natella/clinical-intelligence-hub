"""
Clinical Intelligence Hub — ClinicalTrials.gov Search

Uses the ClinicalTrials.gov v2 API to find active clinical trials
relevant to a patient's conditions and medications.

This is critical for rare diseases — active trials may represent
the only treatment options beyond standard of care.

API: https://clinicaltrials.gov/api/v2/ (free, public, no key required)
Rate limit: 10 requests/second
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-ClinTrials")

CT_BASE = "https://clinicaltrials.gov/api/v2"


class ClinicalTrialsClient:
    """ClinicalTrials.gov v2 API client for finding relevant trials."""

    def search_condition(
        self, condition: str, limit: int = 10, recruiting_only: bool = True
    ) -> list[dict]:
        """
        Search for clinical trials by condition/disease.

        Args:
            condition: Disease or condition name
            limit: Max results to return
            recruiting_only: If True, only return actively recruiting trials
        """
        params = {
            "query.cond": condition,
            "pageSize": str(limit),
            "sort": "LastUpdatePostDate:desc",
            "format": "json",
            "fields": (
                "NCTId,BriefTitle,OverallStatus,Phase,EnrollmentCount,"
                "Condition,InterventionName,InterventionType,"
                "LeadSponsorName,StartDate,PrimaryCompletionDate,"
                "LocationCity,LocationState,LocationCountry,"
                "BriefSummary,StudyType,EligibilityCriteria"
            ),
        }

        if recruiting_only:
            params["filter.overallStatus"] = (
                "RECRUITING,NOT_YET_RECRUITING,ENROLLING_BY_INVITATION"
            )

        return self._search(params)

    def search_intervention(
        self, drug_or_therapy: str, limit: int = 10
    ) -> list[dict]:
        """
        Search for trials by drug/intervention name.

        Useful for finding trials testing a patient's current medication
        for new indications or in combination therapies.
        """
        params = {
            "query.intr": drug_or_therapy,
            "pageSize": str(limit),
            "sort": "LastUpdatePostDate:desc",
            "format": "json",
            "filter.overallStatus": "RECRUITING,NOT_YET_RECRUITING",
            "fields": (
                "NCTId,BriefTitle,OverallStatus,Phase,EnrollmentCount,"
                "Condition,InterventionName,InterventionType,"
                "LeadSponsorName,StartDate,LocationCity,LocationState,"
                "LocationCountry,BriefSummary"
            ),
        }

        return self._search(params)

    def search_combined(
        self,
        condition: str = None,
        intervention: str = None,
        term: str = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Combined search with condition + intervention + general term.

        Useful for finding targeted trials (e.g., condition=lupus + intervention=belimumab).
        """
        params = {
            "pageSize": str(limit),
            "sort": "LastUpdatePostDate:desc",
            "format": "json",
            "filter.overallStatus": "RECRUITING,NOT_YET_RECRUITING",
            "fields": (
                "NCTId,BriefTitle,OverallStatus,Phase,EnrollmentCount,"
                "Condition,InterventionName,InterventionType,"
                "LeadSponsorName,BriefSummary,StartDate"
            ),
        }

        if condition:
            params["query.cond"] = condition
        if intervention:
            params["query.intr"] = intervention
        if term:
            params["query.term"] = term

        return self._search(params)

    def get_trial(self, nct_id: str) -> Optional[dict]:
        """
        Get full details for a specific trial by NCT ID.
        """
        url = f"{CT_BASE}/studies/{nct_id}?format=json"

        try:
            data = api_get(url, timeout=20)
            if not data:
                return None

            return self._parse_study(data)

        except Exception as e:
            logger.debug(f"ClinicalTrials.gov lookup failed for {nct_id}: {e}")
            return None

    def count_trials(self, condition: str) -> int:
        """
        Count total number of trials for a condition.

        Useful for gauging how well-studied a condition is.
        """
        params = {
            "query.cond": condition,
            "countTotal": "true",
            "pageSize": "0",
            "format": "json",
        }

        url = f"{CT_BASE}/studies?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url, timeout=20)
            if not data:
                return 0

            return data.get("totalCount", 0)

        except Exception:
            return 0

    # ── Internal Search ──────────────────────────────────────

    def _search(self, params: dict) -> list[dict]:
        """Execute search and parse results."""
        url = f"{CT_BASE}/studies?{urllib.parse.urlencode(params, doseq=True)}"

        try:
            data = api_get(url, timeout=20)
            if not data:
                return []

            studies = data.get("studies", [])
            results = []
            for study in studies:
                parsed = self._parse_study(study)
                if parsed:
                    results.append(parsed)

            return results

        except Exception as e:
            logger.debug(f"ClinicalTrials.gov search failed: {e}")
            return []

    # ── Parsing ──────────────────────────────────────────────

    @staticmethod
    def _parse_study(study: dict) -> Optional[dict]:
        """Parse a ClinicalTrials.gov v2 study response."""
        if not study:
            return None

        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status = proto.get("statusModule", {})
        design = proto.get("designModule", {})
        desc = proto.get("descriptionModule", {})
        eligibility = proto.get("eligibilityModule", {})
        sponsor = proto.get("sponsorCollaboratorsModule", {})
        conditions = proto.get("conditionsModule", {})
        interventions = proto.get("armsInterventionsModule", {})
        contacts = proto.get("contactsLocationsModule", {})

        nct_id = ident.get("nctId", "")

        # Extract locations
        locations = []
        for loc in (contacts.get("locations") or [])[:5]:
            parts = [
                loc.get("city", ""),
                loc.get("state", ""),
                loc.get("country", ""),
            ]
            location_str = ", ".join(p for p in parts if p)
            if location_str:
                locations.append(location_str)

        # Extract interventions
        intervention_list = []
        for arm in interventions.get("interventions", []):
            intervention_list.append({
                "name": arm.get("name", ""),
                "type": arm.get("type", ""),
                "description": (arm.get("description", "") or "")[:200],
            })

        # Extract lead sponsor
        lead_sponsor = ""
        sponsor_data = sponsor.get("leadSponsor", {})
        if sponsor_data:
            lead_sponsor = sponsor_data.get("name", "")

        enrollment = design.get("enrollmentInfo", {})
        enrollment_count = enrollment.get("count") if enrollment else None

        return {
            "nct_id": nct_id,
            "title": ident.get("briefTitle", ""),
            "official_title": ident.get("officialTitle", ""),
            "status": status.get("overallStatus", ""),
            "phase": ", ".join(design.get("phases", [])) if design.get("phases") else None,
            "study_type": design.get("studyType", ""),
            "enrollment": enrollment_count,
            "conditions": conditions.get("conditions", []),
            "interventions": intervention_list,
            "brief_summary": (desc.get("briefSummary", "") or "")[:500],
            "eligibility_criteria": (eligibility.get("eligibilityCriteria", "") or "")[:500],
            "sponsor": lead_sponsor,
            "start_date": status.get("startDateStruct", {}).get("date", ""),
            "completion_date": status.get("primaryCompletionDateStruct", {}).get("date", ""),
            "locations": locations,
            "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
            "source": "ClinicalTrials.gov",
        }

