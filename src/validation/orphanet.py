"""
Clinical Intelligence Hub — Orphanet Rare Disease Database

Orphanet is the European reference portal for rare diseases, maintained
by INSERM (French National Institute of Health and Medical Research).
It provides disease classifications, prevalence data, and expert center info.

API: https://api.orphacode.org/ (free, public, no key required)
Data source: Orphadata (https://www.orphadata.com/)

Orphanet covers ~6,000+ rare diseases with clinical descriptions,
epidemiology, inheritance patterns, and associated genes.
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-Orphanet")

ORPHA_API_BASE = "https://api.orphacode.org/EN"


class OrphanetClient:
    """Orphanet rare disease database client."""

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search Orphanet for rare diseases by name.

        Returns diseases with ORPHA codes, classifications,
        and prevalence information.
        """
        url = (
            f"{ORPHA_API_BASE}/ClinicalEntity/ApproximateName"
            f"/{urllib.parse.quote(query)}"
        )

        try:
            data = api_get(url, headers={"apiKey": "cih"})
            if not data:
                return []

            results = []
            entities = data if isinstance(data, list) else [data]

            for entity in entities[:limit]:
                orpha_code = entity.get("ORPHAcode")
                name = entity.get("Preferred term") or entity.get("Name", "")

                if not orpha_code:
                    continue

                results.append({
                    "orpha_code": orpha_code,
                    "name": name,
                    "url": f"https://www.orpha.net/en/disease/detail/{orpha_code}",
                    "source": "Orphanet",
                })

            return results

        except Exception as e:
            logger.debug(f"Orphanet search failed for '{query}': {e}")
            return []

    def get_disease(self, orpha_code: int) -> Optional[dict]:
        """
        Get detailed information about a rare disease by ORPHA code.

        Returns classification, prevalence, inheritance, and age of onset.
        """
        url = f"{ORPHA_API_BASE}/ClinicalEntity/{orpha_code}"

        try:
            data = api_get(url, headers={"apiKey": "cih"})
            if not data:
                return None

            name = data.get("Preferred term") or data.get("Name", "")
            definition = data.get("Definition", "")
            group = data.get("Typology", "")

            return {
                "orpha_code": orpha_code,
                "name": name,
                "definition": definition[:500] if definition else None,
                "typology": group,
                "url": f"https://www.orpha.net/en/disease/detail/{orpha_code}",
                "source": "Orphanet",
            }

        except Exception as e:
            logger.debug(f"Orphanet disease lookup failed for {orpha_code}: {e}")
            return None

    def get_prevalence(self, orpha_code: int) -> list[dict]:
        """
        Get epidemiological data for a rare disease.

        Returns prevalence classes (e.g., "1-9 / 100 000"),
        point prevalence estimates, and geographic scope.
        """
        url = f"{ORPHA_API_BASE}/ClinicalEntity/{orpha_code}/Epidemiology"

        try:
            data = api_get(url, headers={"apiKey": "cih"})
            if not data:
                return []

            prevalences = []
            epi_list = data if isinstance(data, list) else data.get("Epidemiology", [])
            if not isinstance(epi_list, list):
                epi_list = [epi_list] if epi_list else []

            for epi in epi_list:
                if not isinstance(epi, dict):
                    continue

                prevalences.append({
                    "prevalence_type": epi.get("PrevalenceType", ""),
                    "prevalence_class": epi.get("PrevalenceClass", ""),
                    "prevalence_geographic": epi.get("PrevalenceGeographic", ""),
                    "prevalence_qualification": epi.get("PrevalenceQualification", ""),
                    "prevalence_validation": epi.get("PrevalenceValidationStatus", ""),
                    "source": "Orphanet",
                })

            return prevalences

        except Exception as e:
            logger.debug(f"Orphanet prevalence failed for {orpha_code}: {e}")
            return []

    def get_genes(self, orpha_code: int) -> list[dict]:
        """
        Get genes associated with a rare disease.

        Returns gene symbols, gene types (causative, modifier, etc.),
        and inheritance patterns.
        """
        url = f"{ORPHA_API_BASE}/ClinicalEntity/{orpha_code}/Gene"

        try:
            data = api_get(url, headers={"apiKey": "cih"})
            if not data:
                return []

            genes = []
            gene_list = data if isinstance(data, list) else data.get("Gene", [])
            if not isinstance(gene_list, list):
                gene_list = [gene_list] if gene_list else []

            for gene in gene_list:
                if not isinstance(gene, dict):
                    continue

                genes.append({
                    "symbol": gene.get("Symbol", ""),
                    "name": gene.get("Name", ""),
                    "gene_type": gene.get("DisorderGeneAssociationType", ""),
                    "gene_status": gene.get("DisorderGeneAssociationStatus", ""),
                    "source": "Orphanet",
                })

            return genes

        except Exception as e:
            logger.debug(f"Orphanet genes failed for {orpha_code}: {e}")
            return []

    def get_inheritance(self, orpha_code: int) -> list[str]:
        """
        Get inheritance patterns for a rare disease.

        Returns list like ["Autosomal dominant", "Autosomal recessive"].
        """
        url = f"{ORPHA_API_BASE}/ClinicalEntity/{orpha_code}/TypeOfInheritance"

        try:
            data = api_get(url, headers={"apiKey": "cih"})
            if not data:
                return []

            inh_list = data if isinstance(data, list) else data.get("TypeOfInheritance", [])
            if not isinstance(inh_list, list):
                inh_list = [inh_list] if inh_list else []

            return [
                i.get("Name", "") if isinstance(i, dict) else str(i)
                for i in inh_list
                if i
            ]

        except Exception as e:
            logger.debug(f"Orphanet inheritance failed for {orpha_code}: {e}")
            return []

    def get_clinical_signs(self, orpha_code: int) -> list[dict]:
        """
        Get clinical signs/symptoms associated with a rare disease.

        Returns HPO-linked phenotypes with frequency classes.
        """
        url = (
            f"{ORPHA_API_BASE}/ClinicalEntity/{orpha_code}"
            f"/PhenotypicAbnormality"
        )

        try:
            data = api_get(url, headers={"apiKey": "cih"})
            if not data:
                return []

            signs = []
            sign_list = data if isinstance(data, list) else data.get("PhenotypicAbnormality", [])
            if not isinstance(sign_list, list):
                sign_list = [sign_list] if sign_list else []

            for sign in sign_list:
                if not isinstance(sign, dict):
                    continue

                signs.append({
                    "hpo_id": sign.get("HPOId", ""),
                    "name": sign.get("HPOTerm", ""),
                    "frequency": sign.get("HPOFrequency", ""),
                    "source": "Orphanet (HPO-linked)",
                })

            return signs

        except Exception as e:
            logger.debug(f"Orphanet clinical signs failed for {orpha_code}: {e}")
            return []

