"""
Clinical Intelligence Hub — NLM MeSH Vocabulary Validation

Uses the NLM MeSH REST API to validate that medical terms
(diseases, drugs, procedures, anatomy) are standard MeSH headings.

MeSH (Medical Subject Headings) is the controlled vocabulary used by
PubMed/MEDLINE — if a term is in MeSH, it's an established medical concept.

API: https://id.nlm.nih.gov/mesh/ (free, public, no key required)
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-MeSH")

MESH_BASE = "https://id.nlm.nih.gov/mesh"


class MeSHClient:
    """Validates medical terms against NLM MeSH vocabulary."""

    def lookup(self, term: str, limit: int = 5) -> Optional[dict]:
        """
        Look up a term in MeSH. Returns the best match with
        MeSH descriptor ID, preferred label, and tree numbers.
        """
        results = self._search(term, limit)
        if not results:
            return None
        return results[0]

    def validate_term(self, term: str) -> Optional[dict]:
        """
        Check if a term exists as a MeSH heading.

        Returns dict with MeSH UID, label, and category, or None.
        """
        return self.lookup(term, limit=1)

    def search(self, term: str, limit: int = 10) -> list[dict]:
        """
        Search MeSH for terms matching a query.

        Returns list of matching descriptors.
        """
        return self._search(term, limit)

    def get_descriptor(self, mesh_uid: str) -> Optional[dict]:
        """
        Get full details for a MeSH descriptor by UID (e.g., D003920).

        Returns preferred label, scope note (definition), tree numbers,
        and pharmacological actions.
        """
        url = f"{MESH_BASE}/lookup/descriptor/{mesh_uid}"
        params = {"format": "json"}

        try:
            full_url = f"{url}?{urllib.parse.urlencode(params)}"
            data = api_get(full_url)
            if not data:
                return None

            return self._parse_descriptor(data)

        except Exception as e:
            logger.debug(f"MeSH descriptor lookup failed for {mesh_uid}: {e}")
            return None

    def get_tree_ancestors(self, tree_number: str) -> list[dict]:
        """
        Get parent categories for a MeSH tree number.

        Tree numbers like C14.280.067 represent:
          C = Diseases
          C14 = Cardiovascular Diseases
          C14.280 = Heart Diseases
          C14.280.067 = Arrhythmias, Cardiac

        This returns the hierarchy for context.
        """
        parts = tree_number.split(".")
        ancestors = []

        for i in range(1, len(parts)):
            parent_tree = ".".join(parts[:i])
            result = self._tree_lookup(parent_tree)
            if result:
                ancestors.append(result)

        return ancestors

    # ── Search ───────────────────────────────────────────────

    def _search(self, term: str, limit: int) -> list[dict]:
        """Search MeSH via the suggestions/lookup API."""
        # Try the SPARQL-backed search endpoint
        params = {
            "label": term,
            "match": "contains",
            "limit": str(limit),
            "format": "json",
        }
        url = f"{MESH_BASE}/lookup/descriptor?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            if not data:
                # Fallback to suggestions endpoint
                return self._search_suggestions(term, limit)

            results = []
            for item in data if isinstance(data, list) else [data]:
                parsed = self._parse_descriptor(item)
                if parsed:
                    results.append(parsed)

            return results if results else self._search_suggestions(term, limit)

        except Exception as e:
            logger.debug(f"MeSH search failed for '{term}': {e}")
            return self._search_suggestions(term, limit)

    def _search_suggestions(self, term: str, limit: int) -> list[dict]:
        """Fallback search using MeSH auto-suggest API."""
        params = {
            "searchTerms": term,
            "limit": str(limit),
        }
        url = f"{MESH_BASE}/suggest?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            if not data:
                return []

            results = []
            for item in data if isinstance(data, list) else []:
                resource = item.get("resource", "")
                label = item.get("label", "")

                # Extract MeSH UID from resource URI
                mesh_uid = resource.split("/")[-1] if resource else None

                if label:
                    results.append({
                        "mesh_uid": mesh_uid,
                        "preferred_label": label,
                        "resource_uri": resource,
                        "source": "NLM MeSH",
                    })

            return results

        except Exception as e:
            logger.debug(f"MeSH suggest failed for '{term}': {e}")
            return []

    # ── Tree Lookup ──────────────────────────────────────────

    def _tree_lookup(self, tree_number: str) -> Optional[dict]:
        """Look up a descriptor by tree number."""
        url = f"{MESH_BASE}/lookup/descriptor"
        params = {
            "treeNumber": tree_number,
            "format": "json",
        }

        try:
            full_url = f"{url}?{urllib.parse.urlencode(params)}"
            data = api_get(full_url)
            if not data:
                return None

            parsed = self._parse_descriptor(data)
            if parsed:
                parsed["tree_number"] = tree_number
            return parsed

        except Exception:
            return None

    # ── Parsing ──────────────────────────────────────────────

    @staticmethod
    def _parse_descriptor(data: dict) -> Optional[dict]:
        """Parse a MeSH descriptor response into a clean dict."""
        if not data:
            return None

        # Handle both single descriptor and list
        if isinstance(data, list):
            data = data[0] if data else {}

        label = data.get("label") or data.get("prefLabel")
        uid = data.get("identifier") or data.get("descriptorUI")

        # Try to extract from @id URI
        if not uid:
            resource = data.get("@id", "") or data.get("resource", "")
            if resource:
                uid = resource.split("/")[-1]

        if not label and not uid:
            return None

        scope_note = data.get("scopeNote") or data.get("annotation")
        tree_numbers = data.get("treeNumber", [])
        if isinstance(tree_numbers, str):
            tree_numbers = [tree_numbers]

        # Determine category from tree number
        category = None
        if tree_numbers:
            first_tree = tree_numbers[0] if tree_numbers else ""
            category = _TREE_CATEGORIES.get(first_tree[0]) if first_tree else None

        return {
            "mesh_uid": uid,
            "preferred_label": label,
            "scope_note": scope_note,
            "tree_numbers": tree_numbers,
            "category": category,
            "source": "NLM MeSH",
        }



# MeSH tree number category mapping
_TREE_CATEGORIES = {
    "A": "Anatomy",
    "B": "Organisms",
    "C": "Diseases",
    "D": "Chemicals and Drugs",
    "E": "Analytical, Diagnostic, and Therapeutic Techniques",
    "F": "Psychiatry and Psychology",
    "G": "Phenomena and Processes",
    "H": "Disciplines and Occupations",
    "I": "Anthropology, Education, Sociology",
    "J": "Technology, Industry, Agriculture",
    "K": "Humanities",
    "L": "Information Science",
    "M": "Named Groups",
    "N": "Health Care",
    "V": "Publication Characteristics",
    "Z": "Geographicals",
}
