"""
Clinical Intelligence Hub — HPO (Human Phenotype Ontology)

HPO provides a standardized vocabulary of phenotypic abnormalities
(symptoms, signs, lab findings) and maps them to diseases.

This is critical for rare disease diagnosis — HPO links specific
clinical features to known genetic disorders, enabling differential
diagnosis from symptom patterns.

API: https://ontology.jax.org/api/hp (free, public, no key required)
Also: https://hpo.jax.org/app/ (web interface)

HPO contains ~18,000 phenotype terms mapped to ~8,000 diseases.
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-HPO")

HPO_API_BASE = "https://ontology.jax.org/api/hp"


class HPOClient:
    """Human Phenotype Ontology client for phenotype-disease mapping."""

    def search_phenotype(self, term: str, limit: int = 10) -> list[dict]:
        """
        Search HPO for phenotype terms (symptoms, signs, findings).

        Returns HPO terms with IDs, names, and definitions.
        """
        url = (
            f"{HPO_API_BASE}/search"
            f"?q={urllib.parse.quote(term)}"
            f"&max={limit}"
            f"&category=terms"
        )

        try:
            data = api_get(url)
            if not data:
                return []

            terms = data.get("terms", [])
            results = []

            for t in terms:
                results.append({
                    "hpo_id": t.get("id", ""),
                    "name": t.get("name", ""),
                    "definition": t.get("definition", ""),
                    "synonyms": t.get("synonyms", []),
                    "is_obsolete": t.get("isObsolete", False),
                    "url": f"https://hpo.jax.org/browse/term/{t.get('id', '')}",
                    "source": "HPO",
                })

            return results

        except Exception as e:
            logger.debug(f"HPO search failed for '{term}': {e}")
            return []

    def get_term(self, hpo_id: str) -> Optional[dict]:
        """
        Get details for a specific HPO term (e.g., HP:0001250 for seizures).
        """
        url = f"{HPO_API_BASE}/terms/{urllib.parse.quote(hpo_id)}"

        try:
            data = api_get(url)
            if not data:
                return None

            return {
                "hpo_id": data.get("id", hpo_id),
                "name": data.get("name", ""),
                "definition": data.get("definition", ""),
                "synonyms": data.get("synonyms", []),
                "parents": data.get("parents", []),
                "children": data.get("children", []),
                "is_obsolete": data.get("isObsolete", False),
                "source": "HPO",
            }

        except Exception as e:
            logger.debug(f"HPO term lookup failed for {hpo_id}: {e}")
            return None

    def get_diseases_for_phenotype(
        self, hpo_id: str, limit: int = 20
    ) -> list[dict]:
        """
        Get diseases associated with a specific phenotype (symptom).

        This is the KEY function for rare disease diagnosis —
        given a symptom, what diseases could cause it?
        """
        url = f"{HPO_API_BASE}/terms/{urllib.parse.quote(hpo_id)}/diseases"

        try:
            data = api_get(url)
            if not data:
                return []

            diseases = data.get("diseases", data) if isinstance(data, dict) else data
            if not isinstance(diseases, list):
                return []

            results = []
            for disease in diseases[:limit]:
                if not isinstance(disease, dict):
                    continue

                results.append({
                    "disease_id": disease.get("diseaseId", ""),
                    "disease_name": disease.get("diseaseName", ""),
                    "database": disease.get("db", ""),
                    "source": "HPO",
                })

            return results

        except Exception as e:
            logger.debug(f"HPO diseases for {hpo_id} failed: {e}")
            return []

    def get_phenotypes_for_disease(
        self, disease_id: str, limit: int = 50
    ) -> list[dict]:
        """
        Get all phenotypes (symptoms) associated with a disease.

        Disease ID can be OMIM (e.g., "OMIM:154700") or ORPHA (e.g., "ORPHA:558").
        Returns symptoms with frequency information.
        """
        url = (
            f"{HPO_API_BASE}/diseases"
            f"/{urllib.parse.quote(disease_id)}/phenotypes"
        )

        try:
            data = api_get(url)
            if not data:
                return []

            phenotypes = data.get("phenotypes", data) if isinstance(data, dict) else data
            if not isinstance(phenotypes, list):
                return []

            results = []
            for pheno in phenotypes[:limit]:
                if not isinstance(pheno, dict):
                    continue

                results.append({
                    "hpo_id": pheno.get("hpoId") or pheno.get("ontologyId", ""),
                    "name": pheno.get("name") or pheno.get("hpoName", ""),
                    "frequency": pheno.get("frequency", ""),
                    "onset": pheno.get("onset", ""),
                    "source": "HPO",
                })

            return results

        except Exception as e:
            logger.debug(f"HPO phenotypes for {disease_id} failed: {e}")
            return []

    def phenotype_to_disease_search(
        self, hpo_ids: list[str], limit: int = 20
    ) -> list[dict]:
        """
        Given a SET of phenotypes (symptoms), find matching diseases.

        This is differential diagnosis from phenotype profile —
        the more HPO terms matched, the stronger the candidate.

        Uses the HPO disease-phenotype association data.
        """
        if not hpo_ids:
            return []

        # For each HPO term, get associated diseases
        disease_scores = {}  # disease_id -> {name, count, total_terms}

        for hpo_id in hpo_ids:
            diseases = self.get_diseases_for_phenotype(hpo_id, limit=50)
            for disease in diseases:
                d_id = disease.get("disease_id", "")
                d_name = disease.get("disease_name", "")
                if not d_id:
                    continue

                if d_id not in disease_scores:
                    disease_scores[d_id] = {
                        "disease_id": d_id,
                        "disease_name": d_name,
                        "matched_phenotypes": [],
                        "match_count": 0,
                    }

                disease_scores[d_id]["matched_phenotypes"].append(hpo_id)
                disease_scores[d_id]["match_count"] += 1

        # Sort by number of matched phenotypes (most matches first)
        ranked = sorted(
            disease_scores.values(),
            key=lambda d: d["match_count"],
            reverse=True,
        )

        results = []
        for disease in ranked[:limit]:
            total_terms = len(hpo_ids)
            match_ratio = disease["match_count"] / total_terms if total_terms else 0

            results.append({
                "disease_id": disease["disease_id"],
                "disease_name": disease["disease_name"],
                "matched_phenotypes": disease["matched_phenotypes"],
                "match_count": disease["match_count"],
                "total_query_terms": total_terms,
                "match_ratio": round(match_ratio, 3),
                "source": "HPO phenotype-disease mapping",
            })

        return results

    def validate_phenotype(self, symptom: str) -> Optional[dict]:
        """
        Validate that a symptom/finding is a recognized HPO phenotype.

        Returns the best match, or None.
        """
        results = self.search_phenotype(symptom, limit=3)
        if not results:
            return None

        # Filter out obsolete terms
        active = [r for r in results if not r.get("is_obsolete")]
        return active[0] if active else results[0]

