"""
Clinical Intelligence Hub — Pass 5: OpenFDA Validation

Queries the FDA Adverse Event Reporting System (FAERS) and drug labeling
to validate AI-detected findings against real-world safety data.

Free public API — no API key required (but rate limited to 240/min).

Salvaged from old deep_research.py OpenFDA FAERS query (working code).
"""

import json
import logging
import urllib.parse
import urllib.request
from typing import Optional

from src.models import AlertSeverity, DrugInteraction

logger = logging.getLogger("CIH-OpenFDA")

BASE_URL = "https://api.fda.gov"


class OpenFDAClient:
    """Queries OpenFDA for adverse events, drug labels, and recalls."""

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: Optional OpenFDA API key (increases rate limit).
                     Works without one at 240 requests/minute.
        """
        self._api_key = api_key

    def get_adverse_events(self, drug_name: str,
                           limit: int = 10) -> list[dict]:
        """
        Get adverse event reports for a drug from FAERS.

        Returns top adverse reactions by report count.
        """
        try:
            search = f'patient.drug.medicinalproduct:"{drug_name}"'
            params = {
                "search": search,
                "count": "patient.reaction.reactionmeddrapt.exact",
                "limit": str(limit),
            }

            data = self._api_call("/drug/event.json", params)
            if not data:
                return []

            results = data.get("results", [])
            return [
                {
                    "reaction": r.get("term", "Unknown"),
                    "count": r.get("count", 0),
                }
                for r in results
            ]

        except Exception as e:
            logger.error(f"OpenFDA adverse events query failed for {drug_name}: {e}")
            return []

    def get_drug_label(self, drug_name: str) -> Optional[dict]:
        """
        Get drug label information (warnings, interactions, contraindications).
        """
        try:
            search = f'openfda.brand_name:"{drug_name}"+openfda.generic_name:"{drug_name}"'
            params = {
                "search": search,
                "limit": "1",
            }

            data = self._api_call("/drug/label.json", params)
            if not data or not data.get("results"):
                return None

            label = data["results"][0]
            return {
                "brand_name": self._extract_openfda(label, "brand_name"),
                "generic_name": self._extract_openfda(label, "generic_name"),
                "warnings": self._first_text(label.get("warnings", [])),
                "drug_interactions": self._first_text(label.get("drug_interactions", [])),
                "contraindications": self._first_text(label.get("contraindications", [])),
                "adverse_reactions": self._first_text(label.get("adverse_reactions", [])),
                "boxed_warning": self._first_text(label.get("boxed_warning", [])),
            }

        except Exception as e:
            logger.error(f"OpenFDA label query failed for {drug_name}: {e}")
            return None

    def check_drug_recalls(self, drug_name: str, limit: int = 5) -> list[dict]:
        """Check for drug recalls/safety alerts."""
        try:
            search = f'product_description:"{drug_name}"'
            params = {
                "search": search,
                "limit": str(limit),
                "sort": "report_date:desc",
            }

            data = self._api_call("/drug/enforcement.json", params)
            if not data:
                return []

            return [
                {
                    "reason": r.get("reason_for_recall", ""),
                    "classification": r.get("classification", ""),
                    "status": r.get("status", ""),
                    "report_date": r.get("report_date", ""),
                    "description": r.get("product_description", ""),
                }
                for r in data.get("results", [])
            ]

        except Exception as e:
            logger.debug(f"OpenFDA recall query for {drug_name}: {e}")
            return []

    def validate_drug_interactions(self, drug_names: list[str]) -> list[DrugInteraction]:
        """
        Check OpenFDA for known interactions between medications.

        Uses drug label interaction sections to find warnings.
        """
        interactions = []

        for drug_name in drug_names:
            label = self.get_drug_label(drug_name)
            if not label or not label.get("drug_interactions"):
                continue

            interaction_text = label["drug_interactions"]

            # Check if any other patient medications are mentioned
            for other_drug in drug_names:
                if other_drug.lower() == drug_name.lower():
                    continue

                if other_drug.lower() in interaction_text.lower():
                    interactions.append(DrugInteraction(
                        drug_a=drug_name,
                        drug_b=other_drug,
                        severity=AlertSeverity.HIGH,
                        description=(
                            f"FDA drug label for {drug_name} mentions "
                            f"interaction with {other_drug}."
                        ),
                        source="OpenFDA Drug Label",
                    ))

        return interactions

    # ── API Call Helper ─────────────────────────────────────

    def _api_call(self, endpoint: str, params: dict) -> Optional[dict]:
        """Make an API call to OpenFDA."""
        if self._api_key:
            params["api_key"] = self._api_key

        query_string = urllib.parse.urlencode(params)
        url = f"{BASE_URL}{endpoint}?{query_string}"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ClinicalIntelligenceHub/1.0"},
            )

            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode())

        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.debug(f"OpenFDA: No results for {endpoint}")
                return None
            logger.warning(f"OpenFDA HTTP {e.code}: {e.reason}")
            return None
        except Exception as e:
            logger.error(f"OpenFDA API call failed: {e}")
            return None

    @staticmethod
    def _extract_openfda(label: dict, field: str) -> Optional[str]:
        """Extract a field from the openfda section of a label."""
        openfda = label.get("openfda", {})
        values = openfda.get(field, [])
        return values[0] if values else None

    @staticmethod
    def _first_text(text_list: list) -> Optional[str]:
        """Get the first non-empty text from a list."""
        if text_list and len(text_list) > 0:
            return text_list[0]
        return None
