"""
Clinical Intelligence Hub — SNOMED CT Terminology Validation

Uses the NLM FHIR Terminology Services API to validate that disease names,
symptom terms, and clinical concepts are real SNOMED CT coded terms.

SNOMED CT is the most comprehensive clinical terminology system in the world
(350,000+ concepts). If a term exists in SNOMED CT, it's a real clinical concept.

API: https://cts.nlm.nih.gov/fhir/ (free, public, no key required)
Fallback: https://snowstorm.ihtsdotools.org/fhir/ (SNOMED International public browser)
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-SNOMED")

# NLM FHIR Terminology Services (primary — US edition of SNOMED CT)
NLM_FHIR_BASE = "https://cts.nlm.nih.gov/fhir"

# SNOMED International Snowstorm (fallback — international edition)
SNOWSTORM_BASE = "https://snowstorm.ihtsdotools.org"
SNOWSTORM_BRANCH = "MAIN"


class SNOMEDClient:
    """Validates clinical terms against SNOMED CT terminology."""

    def validate_term(self, term: str) -> Optional[dict]:
        """
        Check if a clinical term exists in SNOMED CT.

        Returns dict with SNOMED concept ID and preferred term,
        or None if no match found.
        """
        result = self._search_snowstorm(term)
        if result:
            return result

        result = self._search_nlm_fhir(term)
        return result

    def validate_disease(self, disease_name: str) -> Optional[dict]:
        """
        Validate a disease name specifically (semantic tag: disorder).

        More targeted than validate_term — only matches clinical disorders.
        """
        result = self._search_snowstorm(disease_name, semantic_tag="disorder")
        if result:
            return result

        # Fallback to general search
        return self._search_snowstorm(disease_name)

    def validate_symptom(self, symptom: str) -> Optional[dict]:
        """
        Validate a symptom/finding term (semantic tag: finding).
        """
        result = self._search_snowstorm(symptom, semantic_tag="finding")
        if result:
            return result

        return self._search_snowstorm(symptom)

    def get_concept_details(self, concept_id: str) -> Optional[dict]:
        """
        Get full details for a SNOMED CT concept by ID.

        Returns concept with fully specified name, synonyms, and hierarchy.
        """
        url = (
            f"{SNOWSTORM_BASE}/browser/{SNOWSTORM_BRANCH}"
            f"/concepts/{concept_id}"
        )

        try:
            data = api_get(url)
            if not data:
                return None

            return {
                "concept_id": data.get("conceptId"),
                "preferred_term": data.get("pt", {}).get("term"),
                "fully_specified_name": data.get("fsn", {}).get("term"),
                "active": data.get("active", False),
                "definition_status": data.get("definitionStatus"),
            }

        except Exception as e:
            logger.debug(f"SNOMED concept lookup failed for {concept_id}: {e}")
            return None

    def get_children(self, concept_id: str) -> list[dict]:
        """
        Get child concepts (subtypes) of a SNOMED concept.

        Useful for finding specific subtypes of a disease category.
        """
        url = (
            f"{SNOWSTORM_BASE}/{SNOWSTORM_BRANCH}/concepts"
            f"/{concept_id}/children"
        )

        try:
            data = api_get(url)
            if not data or not isinstance(data, list):
                return []

            return [
                {
                    "concept_id": c.get("conceptId"),
                    "preferred_term": c.get("pt", {}).get("term")
                        if isinstance(c.get("pt"), dict)
                        else c.get("fsn", {}).get("term"),
                    "active": c.get("active", False),
                }
                for c in data[:20]
            ]

        except Exception as e:
            logger.debug(f"SNOMED children lookup failed for {concept_id}: {e}")
            return []

    # ── Snowstorm Search (primary) ───────────────────────────

    def _search_snowstorm(
        self, term: str, semantic_tag: str = None
    ) -> Optional[dict]:
        """Search SNOMED CT via Snowstorm browser API."""
        params = {
            "term": term,
            "limit": "5",
            "activeFilter": "true",
            "language": "en",
        }
        if semantic_tag:
            params["semanticTag"] = semantic_tag

        url = (
            f"{SNOWSTORM_BASE}/browser/{SNOWSTORM_BRANCH}/descriptions"
            f"?{urllib.parse.urlencode(params)}"
        )

        try:
            data = api_get(url)
            if not data:
                return None

            items = data.get("items", [])
            if not items:
                return None

            # Return best match
            best = items[0]
            concept = best.get("concept", {})

            return {
                "concept_id": concept.get("conceptId"),
                "preferred_term": concept.get("pt", {}).get("term")
                    if isinstance(concept.get("pt"), dict)
                    else best.get("term"),
                "fully_specified_name": concept.get("fsn", {}).get("term")
                    if isinstance(concept.get("fsn"), dict)
                    else None,
                "active": concept.get("active", True),
                "match_term": best.get("term"),
                "semantic_tag": semantic_tag,
                "source": "SNOMED CT (Snowstorm)",
            }

        except Exception as e:
            logger.debug(f"Snowstorm search failed for '{term}': {e}")
            return None

    # ── NLM FHIR Search (fallback) ───────────────────────────

    def _search_nlm_fhir(self, term: str) -> Optional[dict]:
        """Search SNOMED CT via NLM FHIR ValueSet expansion."""
        params = {
            "url": "http://snomed.info/sct",
            "filter": term,
            "count": "5",
        }

        url = (
            f"{NLM_FHIR_BASE}/ValueSet/$expand"
            f"?{urllib.parse.urlencode(params)}"
        )

        try:
            data = api_get(url, accept="application/fhir+json")
            if not data:
                return None

            expansion = data.get("expansion", {})
            contains = expansion.get("contains", [])
            if not contains:
                return None

            best = contains[0]
            return {
                "concept_id": best.get("code"),
                "preferred_term": best.get("display"),
                "active": True,
                "source": "SNOMED CT (NLM FHIR)",
            }

        except Exception as e:
            logger.debug(f"NLM FHIR search failed for '{term}': {e}")
            return None

