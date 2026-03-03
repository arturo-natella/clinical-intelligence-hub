"""
Clinical Intelligence Hub — GARD (Genetic and Rare Diseases Information Center)

GARD is run by NCATS (National Center for Advancing Translational Sciences)
at NIH. It provides patient-facing information about rare diseases,
cross-referenced with OMIM, Orphanet, ICD, and other sources.

API: https://rarediseases.info.nih.gov/api (free, public, no key required)

GARD is particularly valuable because it:
- Provides plain-language disease descriptions for patients
- Cross-references to OMIM, Orphanet, MedlinePlus, and ClinicalTrials.gov
- Includes information about expert centers and patient organizations
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-GARD")

GARD_BASE = "https://rarediseases.info.nih.gov"
GARD_API = f"{GARD_BASE}/api"


class GARDClient:
    """NIH GARD rare disease information client."""

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search GARD for rare diseases by name.

        Returns diseases with GARD IDs, names, and synonyms.
        """
        url = f"{GARD_API}/diseases/search/{urllib.parse.quote(query)}"

        try:
            data = api_get(url)
            if not data:
                return []

            results = []
            diseases = data if isinstance(data, list) else data.get("data", [])
            if not isinstance(diseases, list):
                diseases = [diseases] if diseases else []

            for disease in diseases[:limit]:
                if not isinstance(disease, dict):
                    continue

                gard_id = disease.get("diseaseId") or disease.get("gardId")
                name = disease.get("diseaseName") or disease.get("name", "")

                if not name:
                    continue

                synonyms = disease.get("synonyms", [])
                if isinstance(synonyms, str):
                    synonyms = [s.strip() for s in synonyms.split(";") if s.strip()]

                results.append({
                    "gard_id": gard_id,
                    "name": name,
                    "synonyms": synonyms[:5] if synonyms else [],
                    "categories": disease.get("diseaseCategories", []),
                    "url": f"{GARD_BASE}/diseases/{gard_id}" if gard_id else None,
                    "source": "NIH GARD",
                })

            return results

        except Exception as e:
            logger.debug(f"GARD search failed for '{query}': {e}")
            return []

    def get_disease(self, gard_id) -> Optional[dict]:
        """
        Get detailed information about a rare disease by GARD ID.

        Returns description, cross-references, and clinical resources.
        """
        url = f"{GARD_API}/diseases/{gard_id}"

        try:
            data = api_get(url)
            if not data:
                return None

            disease = data if isinstance(data, dict) else {}

            # Extract cross-references to other databases
            cross_refs = {}
            xrefs = disease.get("crossReferences", [])
            if isinstance(xrefs, list):
                for ref in xrefs:
                    if isinstance(ref, dict):
                        db = ref.get("database", "")
                        db_id = ref.get("id", "")
                        if db and db_id:
                            cross_refs[db] = db_id
            elif isinstance(xrefs, dict):
                cross_refs = xrefs

            synonyms = disease.get("synonyms", [])
            if isinstance(synonyms, str):
                synonyms = [s.strip() for s in synonyms.split(";") if s.strip()]

            return {
                "gard_id": gard_id,
                "name": disease.get("diseaseName") or disease.get("name", ""),
                "synonyms": synonyms,
                "categories": disease.get("diseaseCategories", []),
                "description": (
                    disease.get("description", "") or ""
                )[:1000] or None,
                "inheritance": disease.get("inheritance", []),
                "age_of_onset": disease.get("ageOfOnset", []),
                "cross_references": cross_refs,
                "omim_ids": cross_refs.get("OMIM", "").split(",")
                    if cross_refs.get("OMIM") else [],
                "orpha_codes": cross_refs.get("Orphanet", "").split(",")
                    if cross_refs.get("Orphanet") else [],
                "url": f"{GARD_BASE}/diseases/{gard_id}",
                "source": "NIH GARD",
            }

        except Exception as e:
            logger.debug(f"GARD disease lookup failed for {gard_id}: {e}")
            return None

    def get_resources(self, gard_id) -> list[dict]:
        """
        Get patient resources for a rare disease.

        Returns links to patient organizations, support groups,
        expert centers, and educational materials.
        """
        url = f"{GARD_API}/diseases/{gard_id}/resources"

        try:
            data = api_get(url)
            if not data:
                return []

            resources = []
            resource_list = data if isinstance(data, list) else data.get("resources", [])
            if not isinstance(resource_list, list):
                resource_list = [resource_list] if resource_list else []

            for res in resource_list:
                if not isinstance(res, dict):
                    continue

                resources.append({
                    "name": res.get("name", ""),
                    "type": res.get("resourceType", ""),
                    "url": res.get("url", ""),
                    "description": (res.get("description", "") or "")[:200],
                    "source": "NIH GARD",
                })

            return resources

        except Exception as e:
            logger.debug(f"GARD resources failed for {gard_id}: {e}")
            return []

    def validate_rare_disease(self, disease_name: str) -> Optional[dict]:
        """
        Check if a disease is recognized as a rare disease by GARD.

        Returns the best match, or None if not found.
        Useful for confirming rare disease status.
        """
        results = self.search(disease_name, limit=3)
        if not results:
            return None

        # Check for close name match
        name_lower = disease_name.lower()
        for result in results:
            result_name = result.get("name", "").lower()
            if (
                name_lower in result_name
                or result_name in name_lower
                or name_lower == result_name
            ):
                return result

        # Return best match even if not exact
        return results[0]

