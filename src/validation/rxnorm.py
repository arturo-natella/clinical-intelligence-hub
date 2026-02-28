"""
Clinical Intelligence Hub — Pass 5: RxNorm Medication Validation

Uses the NLM RxNorm REST API to:
  - Standardize medication names (brand → generic mapping)
  - Get RxCUI (RxNorm Concept Unique Identifier)
  - Check drug interactions via NLM Interaction API

Free public API — no API key required.

Salvaged from old deep_research.py RxNorm API call (working code).
"""

import json
import logging
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger("CIH-RxNorm")

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
INTERACTION_BASE = "https://rxnav.nlm.nih.gov/REST/interaction"


class RxNormClient:
    """NLM RxNorm API client for medication standardization and interactions."""

    def resolve_medication(self, name: str) -> Optional[dict]:
        """
        Resolve a medication name to its standardized RxNorm entry.

        Handles brand names → generic names (e.g., "Glucophage" → "Metformin").
        """
        try:
            # Try approximate match first (handles misspellings, brand names)
            params = {"name": name, "maxEntries": "1"}
            data = self._api_call(f"{RXNORM_BASE}/approximateTerm.json", params)

            if not data:
                return None

            candidates = data.get("approximateGroup", {}).get("candidate", [])
            if not candidates:
                return None

            rxcui = candidates[0].get("rxcui")
            if not rxcui:
                return None

            # Get full properties for the resolved medication
            props = self._get_properties(rxcui)
            if not props:
                return {"rxcui": rxcui, "name": name}

            return {
                "rxcui": rxcui,
                "name": props.get("name", name),
                "synonym": props.get("synonym"),
                "tty": props.get("tty"),  # Term type (e.g., "SBD" for Semantic Branded Drug)
            }

        except Exception as e:
            logger.error(f"RxNorm resolution failed for {name}: {e}")
            return None

    def get_interactions(self, rxcui: str) -> list[dict]:
        """
        Get known drug interactions for a medication by RxCUI.
        """
        try:
            data = self._api_call(
                f"{INTERACTION_BASE}/interaction/list.json",
                {"rxcuis": rxcui}
            )

            if not data:
                return []

            interactions = []
            for group in data.get("fullInteractionTypeGroup", []):
                for interaction_type in group.get("fullInteractionType", []):
                    for pair in interaction_type.get("interactionPair", []):
                        description = pair.get("description", "")
                        severity = pair.get("severity", "N/A")

                        # Extract the interacting drugs
                        concepts = pair.get("interactionConcept", [])
                        drug_names = [
                            c.get("minConceptItem", {}).get("name", "")
                            for c in concepts
                        ]

                        interactions.append({
                            "description": description,
                            "severity": severity,
                            "drugs": drug_names,
                            "source": group.get("sourceName", ""),
                        })

            return interactions

        except Exception as e:
            logger.error(f"RxNorm interaction query failed for {rxcui}: {e}")
            return []

    def check_pairwise_interactions(self, rxcuis: list[str]) -> list[dict]:
        """
        Check interactions between multiple medications.

        Uses the NLM interaction list API with multiple RxCUIs.
        """
        if len(rxcuis) < 2:
            return []

        try:
            rxcui_string = "+".join(rxcuis)
            data = self._api_call(
                f"{INTERACTION_BASE}/list.json",
                {"rxcuis": rxcui_string}
            )

            if not data:
                return []

            interactions = []
            for group in data.get("fullInteractionTypeGroup", []):
                for interaction_type in group.get("fullInteractionType", []):
                    for pair in interaction_type.get("interactionPair", []):
                        concepts = pair.get("interactionConcept", [])
                        drug_names = [
                            c.get("minConceptItem", {}).get("name", "")
                            for c in concepts
                        ]

                        interactions.append({
                            "description": pair.get("description", ""),
                            "severity": pair.get("severity", ""),
                            "drugs": drug_names,
                            "source": group.get("sourceName", ""),
                        })

            return interactions

        except Exception as e:
            logger.error(f"RxNorm pairwise interaction check failed: {e}")
            return []

    # ── Helpers ──────────────────────────────────────────────

    def _get_properties(self, rxcui: str) -> Optional[dict]:
        """Get properties for an RxCUI."""
        try:
            data = self._api_call(
                f"{RXNORM_BASE}/rxcui/{rxcui}/properties.json",
                {}
            )
            if data:
                return data.get("properties", {})
            return None
        except Exception:
            return None

    @staticmethod
    def _api_call(url: str, params: dict) -> Optional[dict]:
        """Make an API call to RxNorm/NLM."""
        if params:
            query_string = urllib.parse.urlencode(params)
            full_url = f"{url}?{query_string}" if "?" not in url else f"{url}&{query_string}"
        else:
            full_url = url

        try:
            req = urllib.request.Request(
                full_url,
                headers={"User-Agent": "ClinicalIntelligenceHub/1.0"},
            )

            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode())

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            logger.warning(f"RxNorm HTTP {e.code}: {e.reason}")
            return None
        except Exception as e:
            logger.error(f"RxNorm API call failed: {e}")
            return None
