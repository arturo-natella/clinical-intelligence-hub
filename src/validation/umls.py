"""
Clinical Intelligence Hub — UMLS (Unified Medical Language System) Cross-Vocabulary Mapping

The UMLS is the Rosetta Stone of medical terminologies. It integrates 190+
biomedical source vocabularies — ICD-10, SNOMED CT, MeSH, RxNorm, LOINC,
and more — into a single metathesaurus. Every concept gets a Concept Unique
Identifier (CUI) that links equivalent terms across all systems.

This means you can take a SNOMED CT code, find its CUI, and immediately get
the corresponding ICD-10, MeSH, RxNorm, and LOINC codes — all through one API.
The metathesaurus contains ~3.49 million concepts from ~190 source vocabularies.

API: https://uts-ws.nlm.nih.gov/rest
Docs: https://documentation.uts.nlm.nih.gov/
Requires: Free NLM API key (register at https://uts.nlm.nih.gov/uts/signup-login)
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-UMLS")

UTS_BASE = "https://uts-ws.nlm.nih.gov/rest"


class UMLSClient:
    """NLM UMLS Terminology Services client for cross-vocabulary mapping."""

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: NLM API key (free — register at https://uts.nlm.nih.gov/uts/signup-login).
                     Required for all UMLS operations.
        """
        self._api_key = api_key
        if not api_key:
            logger.warning(
                "UMLS client initialized without API key — all queries will "
                "return empty results. Get a free key at "
                "https://uts.nlm.nih.gov/uts/signup-login"
            )

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search the UMLS Metathesaurus for concepts matching a query.

        Returns list of concepts with CUI, name, and source vocabularies.
        """
        if not self._api_key:
            return []

        params = {
            "string": query,
            "apiKey": self._api_key,
            "pageSize": str(min(limit, 200)),
        }
        url = f"{UTS_BASE}/search/current?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            if not data:
                return []

            # Response: { "result": { "results": [...] } }
            result_wrapper = data.get("result", {})
            if not isinstance(result_wrapper, dict):
                return []

            items = result_wrapper.get("results", [])
            if not isinstance(items, list):
                return []

            results = []
            for item in items[:limit]:
                if not isinstance(item, dict):
                    continue

                cui = item.get("ui", "")
                name = item.get("name", "")

                # Skip "NO RESULTS" sentinel returned by the API
                if cui == "NONE" or not name:
                    continue

                results.append({
                    "cui": cui,
                    "name": name,
                    "source_vocabulary": item.get("rootSource", ""),
                    "uri": item.get("uri", ""),
                    "source": "UMLS (NLM)",
                })

            return results

        except Exception as e:
            logger.debug(f"UMLS search failed for '{query}': {e}")
            return []

    def get_concept(self, cui: str) -> Optional[dict]:
        """
        Get full details for a UMLS concept by CUI.

        Returns concept name, semantic types, atom count, and metadata.
        """
        if not self._api_key:
            return None

        params = {"apiKey": self._api_key}
        url = f"{UTS_BASE}/content/current/CUI/{urllib.parse.quote(cui)}?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            if not data:
                return None

            result = data.get("result", {})
            if not isinstance(result, dict):
                return None

            # Parse semantic types
            semantic_types = []
            for st in result.get("semanticTypes", []):
                if isinstance(st, dict):
                    semantic_types.append(st.get("name", ""))
                elif isinstance(st, str):
                    semantic_types.append(st)

            return {
                "cui": result.get("ui", cui),
                "name": result.get("name", ""),
                "semantic_types": semantic_types,
                "atom_count": result.get("atomCount", 0),
                "relation_count": result.get("relationCount", 0),
                "definition_count": result.get("definitionCount", 0),
                "suppressible": result.get("suppressible", False),
                "date_added": result.get("dateAdded"),
                "major_revision_date": result.get("majorRevisionDate"),
                "status": result.get("status"),
                "source": "UMLS (NLM)",
            }

        except Exception as e:
            logger.debug(f"UMLS concept lookup failed for '{cui}': {e}")
            return None

    def get_crosswalk(self, cui: str, target_source: str = None) -> list[dict]:
        """
        Map a concept (by CUI) to its codes in other vocabularies.

        THIS IS THE KEY METHOD — the core of UMLS cross-vocabulary mapping.
        Given a CUI, returns all the codes that concept has in different
        source vocabularies.

        Args:
            cui: UMLS Concept Unique Identifier (e.g., "C0011849" for diabetes)
            target_source: Filter to a specific vocabulary. Examples:
                - "SNOMEDCT_US" — SNOMED CT (US edition)
                - "ICD10CM" — ICD-10-CM
                - "MSH" — MeSH
                - "RXNORM" — RxNorm
                - "LNC" — LOINC
                - None — return all cross-references

        Returns:
            List of {source_vocabulary, code, name, term_type} dicts.
        """
        if not self._api_key:
            return []

        params = {
            "apiKey": self._api_key,
            "pageSize": "50",
        }
        if target_source:
            params["sabs"] = target_source

        url = (
            f"{UTS_BASE}/content/current/CUI/{urllib.parse.quote(cui)}/atoms"
            f"?{urllib.parse.urlencode(params)}"
        )

        try:
            data = api_get(url)
            if not data:
                return []

            # Response: { "result": [...atoms...] }
            items = data.get("result", [])
            if not isinstance(items, list):
                return []

            results = []
            seen = set()

            for atom in items:
                if not isinstance(atom, dict):
                    continue

                source_vocab = atom.get("rootSource", "")
                name = atom.get("name", "")
                term_type = atom.get("termType", "")

                # Extract source code from the code URI
                # The API returns a URI like ".../content/current/source/ICD10CM/E11"
                code_uri = atom.get("code", "")
                code = ""
                if isinstance(code_uri, str) and "/" in code_uri:
                    code = code_uri.rsplit("/", 1)[-1]
                elif isinstance(code_uri, str):
                    code = code_uri

                # Deduplicate by source+code
                dedup_key = f"{source_vocab}:{code}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                if source_vocab and (code or name):
                    results.append({
                        "source_vocabulary": source_vocab,
                        "code": code,
                        "name": name,
                        "term_type": term_type,
                        "source": "UMLS (NLM)",
                    })

            return results

        except Exception as e:
            logger.debug(f"UMLS crosswalk failed for '{cui}': {e}")
            return []

    def map_term(self, term: str, from_source: str, to_source: str) -> list[dict]:
        """
        High-level cross-vocabulary mapping: search term → get CUI → crosswalk.

        Example:
            map_term("diabetes mellitus", "SNOMEDCT_US", "ICD10CM")
            → returns ICD-10-CM codes for diabetes

        Args:
            term: The medical term to map.
            from_source: Source vocabulary (e.g., "SNOMEDCT_US").
            to_source: Target vocabulary (e.g., "ICD10CM").

        Returns:
            List of mapped codes in the target vocabulary.
        """
        if not self._api_key:
            return []

        # Step 1: Search for the term to get a CUI
        search_results = self.search(term, limit=5)
        if not search_results:
            return []

        # Find the best match from the requested source vocabulary
        cui = None
        for result in search_results:
            if result.get("source_vocabulary") == from_source:
                cui = result.get("cui")
                break

        # Fall back to the first result if no source-specific match
        if not cui:
            cui = search_results[0].get("cui")

        if not cui:
            return []

        # Step 2: Crosswalk to the target vocabulary
        crosswalk_results = self.get_crosswalk(cui, target_source=to_source)

        # Add the source CUI for reference
        for result in crosswalk_results:
            result["from_cui"] = cui
            result["from_term"] = term

        return crosswalk_results

    def get_definitions(self, cui: str) -> list[dict]:
        """
        Get definitions for a concept from different source vocabularies.

        Not all concepts have definitions — the API may return an empty list.
        """
        if not self._api_key:
            return []

        params = {"apiKey": self._api_key}
        url = (
            f"{UTS_BASE}/content/current/CUI/{urllib.parse.quote(cui)}/definitions"
            f"?{urllib.parse.urlencode(params)}"
        )

        try:
            data = api_get(url)
            if not data:
                return []

            # Response: { "result": [...definitions...] }
            items = data.get("result", [])
            if not isinstance(items, list):
                return []

            results = []
            for defn in items:
                if not isinstance(defn, dict):
                    continue

                value = defn.get("value", "")
                if not value:
                    continue

                results.append({
                    "definition": value,
                    "root_source": defn.get("rootSource", ""),
                    "source_originated": defn.get("sourceOriginated", False),
                    "source": "UMLS (NLM)",
                })

            return results

        except Exception as e:
            logger.debug(f"UMLS definitions failed for '{cui}': {e}")
            return []

    def get_relations(self, cui: str, limit: int = 20) -> list[dict]:
        """
        Get related concepts (broader, narrower, related, etc.).

        Returns relationships such as parent/child, associated concepts,
        and other semantic links.
        """
        if not self._api_key:
            return []

        params = {
            "apiKey": self._api_key,
            "pageSize": str(min(limit, 200)),
        }
        url = (
            f"{UTS_BASE}/content/current/CUI/{urllib.parse.quote(cui)}/relations"
            f"?{urllib.parse.urlencode(params)}"
        )

        try:
            data = api_get(url)
            if not data:
                return []

            # Response: { "result": [...relations...] }
            items = data.get("result", [])
            if not isinstance(items, list):
                return []

            results = []
            for rel in items[:limit]:
                if not isinstance(rel, dict):
                    continue

                relation_label = rel.get("relationLabel", "")
                additional_label = rel.get("additionalRelationLabel", "")
                related_name = rel.get("relatedIdName", "")
                related_id = rel.get("relatedId", "")

                # Extract CUI from relatedId URI if present
                related_cui = ""
                if isinstance(related_id, str) and "/" in related_id:
                    related_cui = related_id.rsplit("/", 1)[-1]
                elif isinstance(related_id, str):
                    related_cui = related_id

                if not related_name and not related_cui:
                    continue

                results.append({
                    "relation": relation_label,
                    "additional_relation": additional_label,
                    "related_cui": related_cui,
                    "related_name": related_name,
                    "root_source": rel.get("rootSource", ""),
                    "source": "UMLS (NLM)",
                })

            return results

        except Exception as e:
            logger.debug(f"UMLS relations failed for '{cui}': {e}")
            return []

    def normalize_term(self, term: str) -> Optional[dict]:
        """
        Normalize any medical term to a universal identifier (CUI).

        Searches for the term, returns the best-match CUI with all its
        vocabulary codes. This lets you take any medical term — however
        it's phrased — and get its canonical identity plus all its codes
        across every terminology system.

        Returns:
            Dict with CUI, preferred name, semantic types, and a list of
            all vocabulary codes, or None if no match found.
        """
        if not self._api_key:
            return None

        # Step 1: Search for the term
        search_results = self.search(term, limit=1)
        if not search_results:
            return None

        cui = search_results[0].get("cui")
        if not cui:
            return None

        # Step 2: Get concept details
        concept = self.get_concept(cui)

        # Step 3: Get all vocabulary codes
        crosswalk = self.get_crosswalk(cui)

        # Build normalized result
        result = {
            "cui": cui,
            "name": search_results[0].get("name", ""),
            "semantic_types": [],
            "vocabulary_codes": crosswalk,
            "source": "UMLS (NLM)",
        }

        if concept:
            result["name"] = concept.get("name", result["name"])
            result["semantic_types"] = concept.get("semantic_types", [])
            result["atom_count"] = concept.get("atom_count", 0)

        return result
