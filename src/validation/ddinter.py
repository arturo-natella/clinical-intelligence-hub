"""
Clinical Intelligence Hub — DDinter 2.0 Drug Interaction Database

DDinter 2.0 is a comprehensive drug-drug interaction (DDI) database
maintained by the Xiangya School of Pharmaceutical Sciences. It covers
2,310 drugs with 302,516 DDI records, including mechanism descriptions,
severity levels, and management strategies.

Beyond traditional DDIs, DDinter 2.0 also provides:
  - Drug-food interactions (DFI)
  - Drug-disease interactions (DDSI)
  - Therapeutic duplication warnings

Each interaction record includes the pharmacological mechanism,
clinical significance rating, and recommended management approach.

Website: https://ddinter2.scbdd.com/
API Base: https://ddinter2.scbdd.com/api/
"""

import itertools
import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-DDinter")

# ── API Endpoints ────────────────────────────────────────────────
# These are best-guess paths based on the DDinter 2.0 website.
# Adjust if the actual API structure differs.

DDINTER_BASE = "https://ddinter2.scbdd.com/api"

DRUG_SEARCH_URL = f"{DDINTER_BASE}/drug/search/"
DDI_SEARCH_URL = f"{DDINTER_BASE}/ddi/search/"
DDI_CHECK_URL = f"{DDINTER_BASE}/ddi/check/"
DFI_SEARCH_URL = f"{DDINTER_BASE}/dfi/search/"
DDSI_SEARCH_URL = f"{DDINTER_BASE}/ddsi/search/"

SOURCE_LABEL = "DDinter 2.0"

# Severity ranking for sorting interactions (higher = more severe)
_SEVERITY_RANK = {
    "major": 4,
    "severe": 4,
    "contraindicated": 5,
    "moderate": 3,
    "minor": 2,
    "low": 1,
    "unknown": 0,
}


class DDinterClient:
    """
    Client for the DDinter 2.0 drug interaction database.

    Provides lookups for drug-drug interactions, drug-food interactions,
    drug-disease interactions, and prescription-wide pairwise checks.
    """

    def search_drug(self, drug_name: str, limit: int = 10) -> list[dict]:
        """
        Search DDinter for a drug by name.

        Args:
            drug_name: Drug name to search (brand or generic)
            limit: Maximum results to return

        Returns:
            List of matching drugs with IDs and names.
        """
        params = {"name": urllib.parse.quote(drug_name)}
        url = f"{DRUG_SEARCH_URL}?name={params['name']}"

        try:
            data = api_get(url)
            if not data:
                return []

            results = self._extract_list(data, "drugs", "results", "data")

            parsed = []
            for drug in results[:limit]:
                if not isinstance(drug, dict):
                    continue

                parsed.append({
                    "drug_id": drug.get("id") or drug.get("drug_id") or drug.get("ddinter_id"),
                    "name": drug.get("name") or drug.get("drug_name", ""),
                    "aliases": drug.get("aliases", []),
                    "drugbank_id": drug.get("drugbank_id"),
                    "cas_number": drug.get("cas_number") or drug.get("cas"),
                    "source": SOURCE_LABEL,
                })

            return parsed

        except Exception as e:
            logger.debug(f"DDinter drug search failed for '{drug_name}': {e}")
            return []

    def get_interactions(self, drug_name: str, limit: int = 20) -> list[dict]:
        """
        Get all drug-drug interactions for a given drug.

        Args:
            drug_name: Drug name to look up
            limit: Maximum interactions to return

        Returns:
            List of DDI records with interacting drug, severity,
            mechanism, and management strategy.
        """
        params = urllib.parse.quote(drug_name)
        url = f"{DDI_SEARCH_URL}?drug={params}"

        try:
            data = api_get(url)
            if not data:
                return []

            results = self._extract_list(data, "interactions", "results", "data")

            parsed = []
            for record in results[:limit]:
                if not isinstance(record, dict):
                    continue

                parsed.append(self._parse_interaction(record, queried_drug=drug_name))

            return parsed

        except Exception as e:
            logger.debug(f"DDinter interaction lookup failed for '{drug_name}': {e}")
            return []

    def check_pair(self, drug_a: str, drug_b: str) -> Optional[dict]:
        """
        Check interaction between two specific drugs.

        Args:
            drug_a: First drug name
            drug_b: Second drug name

        Returns:
            Interaction details dict, or None if no interaction found.
        """
        params_a = urllib.parse.quote(drug_a)
        params_b = urllib.parse.quote(drug_b)
        url = f"{DDI_CHECK_URL}?drug1={params_a}&drug2={params_b}"

        try:
            data = api_get(url)
            if not data:
                return None

            # The API may return the interaction directly or nested
            if isinstance(data, list):
                record = data[0] if data else None
            elif isinstance(data, dict):
                # Could be nested under a key or the record itself
                record = (
                    data.get("interaction")
                    or data.get("result")
                    or data.get("data")
                    or data
                )
                # Unwrap single-element list
                if isinstance(record, list):
                    record = record[0] if record else None
            else:
                return None

            if not record or not isinstance(record, dict):
                return None

            # If API returned a "no interaction" indicator, respect it
            if record.get("interaction") is False or record.get("found") is False:
                return None

            result = self._parse_interaction(record, queried_drug=drug_a)
            result["drug_a"] = drug_a
            result["drug_b"] = drug_b
            return result

        except Exception as e:
            logger.debug(f"DDinter pair check failed for '{drug_a}' + '{drug_b}': {e}")
            return None

    def get_food_interactions(self, drug_name: str) -> list[dict]:
        """
        Get drug-food interactions for a given drug.

        Args:
            drug_name: Drug name to look up

        Returns:
            List of drug-food interaction records.
        """
        params = urllib.parse.quote(drug_name)
        url = f"{DFI_SEARCH_URL}?drug={params}"

        try:
            data = api_get(url)
            if not data:
                return []

            results = self._extract_list(data, "interactions", "results", "data")

            parsed = []
            for record in results:
                if not isinstance(record, dict):
                    continue

                parsed.append({
                    "drug": drug_name,
                    "food": (
                        record.get("food")
                        or record.get("food_name")
                        or record.get("interacting_substance", "")
                    ),
                    "severity": (
                        record.get("severity")
                        or record.get("risk_level")
                        or record.get("level", "")
                    ),
                    "description": record.get("description") or record.get("effect", ""),
                    "mechanism": record.get("mechanism", ""),
                    "management": (
                        record.get("management")
                        or record.get("management_strategy", "")
                    ),
                    "source": SOURCE_LABEL,
                })

            return parsed

        except Exception as e:
            logger.debug(f"DDinter food interaction lookup failed for '{drug_name}': {e}")
            return []

    def get_disease_interactions(self, drug_name: str) -> list[dict]:
        """
        Get drug-disease interactions for a given drug.

        Args:
            drug_name: Drug name to look up

        Returns:
            List of drug-disease interaction records.
        """
        params = urllib.parse.quote(drug_name)
        url = f"{DDSI_SEARCH_URL}?drug={params}"

        try:
            data = api_get(url)
            if not data:
                return []

            results = self._extract_list(data, "interactions", "results", "data")

            parsed = []
            for record in results:
                if not isinstance(record, dict):
                    continue

                parsed.append({
                    "drug": drug_name,
                    "disease": (
                        record.get("disease")
                        or record.get("disease_name")
                        or record.get("condition", "")
                    ),
                    "severity": (
                        record.get("severity")
                        or record.get("risk_level")
                        or record.get("level", "")
                    ),
                    "description": record.get("description") or record.get("effect", ""),
                    "mechanism": record.get("mechanism", ""),
                    "management": (
                        record.get("management")
                        or record.get("management_strategy", "")
                    ),
                    "source": SOURCE_LABEL,
                })

            return parsed

        except Exception as e:
            logger.debug(f"DDinter disease interaction lookup failed for '{drug_name}': {e}")
            return []

    def check_prescription(self, drug_names: list[str]) -> list[dict]:
        """
        Check ALL pairwise drug-drug interactions among a list of drugs.

        Useful as a prescription safety checker: given a patient's full
        medication list, this finds every interacting pair.

        Args:
            drug_names: List of drug names to check pairwise

        Returns:
            List of found interactions, sorted by severity
            (most severe first).
        """
        if len(drug_names) < 2:
            return []

        logger.info(
            f"DDinter prescription check: {len(drug_names)} drugs, "
            f"{len(list(itertools.combinations(drug_names, 2)))} pairs"
        )

        interactions = []

        for drug_a, drug_b in itertools.combinations(drug_names, 2):
            result = self.check_pair(drug_a, drug_b)
            if result:
                interactions.append(result)

        # Sort by severity (most severe first)
        interactions.sort(
            key=lambda x: _SEVERITY_RANK.get(
                str(x.get("severity", "")).lower(), 0
            ),
            reverse=True,
        )

        logger.info(
            f"DDinter prescription check found {len(interactions)} interactions "
            f"among {len(drug_names)} drugs"
        )

        return interactions

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _extract_list(data, *keys: str) -> list:
        """
        Extract a list from an API response, trying multiple possible keys.

        The DDinter API response structure may vary, so we try several
        common patterns: direct list, nested under known keys, etc.
        """
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, list):
                    return value
                if isinstance(value, dict):
                    # One more level of nesting
                    for subkey in keys:
                        subvalue = value.get(subkey)
                        if isinstance(subvalue, list):
                            return subvalue

        return []

    @staticmethod
    def _parse_interaction(record: dict, queried_drug: str = "") -> dict:
        """
        Parse a single DDI record into a standardized dict.

        Handles multiple possible field names since the exact API
        schema is not yet confirmed.
        """
        interacting_drug = (
            record.get("drug_b")
            or record.get("drug2")
            or record.get("interacting_drug")
            or record.get("drug_name")
            or record.get("name", "")
        )

        severity = (
            record.get("severity")
            or record.get("risk_level")
            or record.get("level")
            or record.get("risk_rating", "")
        )

        return {
            "drug_a": queried_drug,
            "interacting_drug": interacting_drug,
            "severity": severity,
            "mechanism": record.get("mechanism") or record.get("mechanism_description", ""),
            "description": record.get("description") or record.get("effect", ""),
            "management_strategy": (
                record.get("management")
                or record.get("management_strategy")
                or record.get("recommendation", "")
            ),
            "ddinter_id": record.get("id") or record.get("ddinter_id"),
            "source": SOURCE_LABEL,
        }
