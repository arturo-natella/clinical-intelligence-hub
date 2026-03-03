"""
Clinical Intelligence Hub — PharmGKB (Pharmacogenomics Knowledge Base)

PharmGKB is a comprehensive resource curated by Stanford University that maps
how human genetic variation affects drug response. It integrates data on:

- 715+ drugs with pharmacogenomic annotations
- 1761+ genes involved in drug metabolism and response
- 227+ diseases with pharmacogenomic relevance
- CPIC and DPWG clinical guidelines for drug-gene pairs

This is critical for patients on multiple medications. Pharmacogenomics explains
why standard drug doses work for some patients but cause adverse reactions or
therapeutic failure in others. PharmGKB's clinical annotations link specific
gene variants to drug response phenotypes with graded levels of evidence,
and its dosing guidelines provide genotype-based prescribing recommendations.

API: https://api.pharmgkb.org/v1/data (free, public, no key required)
Website: https://www.pharmgkb.org/
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-PharmGKB")

# ── API Endpoints ────────────────────────────────────────────────
# Kept as constants so URLs are easy to adjust if the API changes.

PHARMGKB_BASE = "https://api.pharmgkb.org/v1/data"

DRUG_SEARCH_URL = f"{PHARMGKB_BASE}/drug"
DRUG_DETAIL_URL = f"{PHARMGKB_BASE}/drug"  # + /{id}
CLINICAL_ANN_URL = f"{PHARMGKB_BASE}/clinicalAnnotation"
DRUG_LABEL_URL = f"{PHARMGKB_BASE}/drugLabel"
GUIDELINE_URL = f"{PHARMGKB_BASE}/guideline"
GENE_SEARCH_URL = f"{PHARMGKB_BASE}/gene"

PHARMGKB_WEB = "https://www.pharmgkb.org"


def _unwrap(response) -> list:
    """
    Unwrap PharmGKB API response.

    The API may return data in a `data` wrapper object or as a direct list.
    Handle both cases defensively.
    """
    if response is None:
        return []
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        data = response.get("data", [])
        if isinstance(data, list):
            return data
        # Single object in data wrapper
        if isinstance(data, dict):
            return [data]
        # Fallback: maybe results are at top level with other keys
        return [response]
    return []


class PharmGKBClient:
    """PharmGKB pharmacogenomics database client."""

    def search_drug(self, drug_name: str, limit: int = 10) -> list[dict]:
        """
        Search PharmGKB for drugs by name.

        Returns drugs with PharmGKB IDs, names, and generic names.
        """
        params = {"name": drug_name}
        url = f"{DRUG_SEARCH_URL}?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            items = _unwrap(data)

            results = []
            for drug in items[:limit]:
                if not isinstance(drug, dict):
                    continue

                pharmgkb_id = drug.get("id") or drug.get("pharmgkbId", "")
                name = drug.get("name", "")

                if not name and not pharmgkb_id:
                    continue

                generic_names = drug.get("genericNames", [])
                if isinstance(generic_names, str):
                    generic_names = [generic_names]
                elif not isinstance(generic_names, list):
                    generic_names = []

                trade_names = drug.get("tradeNames", [])
                if isinstance(trade_names, str):
                    trade_names = [trade_names]
                elif not isinstance(trade_names, list):
                    trade_names = []

                results.append({
                    "pharmgkb_id": pharmgkb_id,
                    "name": name,
                    "generic_names": generic_names[:5],
                    "trade_names": trade_names[:5],
                    "url": f"{PHARMGKB_WEB}/chemical/{pharmgkb_id}" if pharmgkb_id else None,
                    "source": "PharmGKB",
                })

            return results

        except Exception as e:
            logger.debug(f"PharmGKB drug search failed for '{drug_name}': {e}")
            return []

    def get_drug(self, pharmgkb_id: str) -> Optional[dict]:
        """
        Get detailed drug information by PharmGKB ID.

        Returns drug details including cross-references and clinical annotations.
        """
        url = f"{DRUG_DETAIL_URL}/{urllib.parse.quote(pharmgkb_id)}"

        try:
            data = api_get(url)
            if not data:
                return None

            # Unwrap if nested in data key
            drug = data
            if isinstance(data, dict) and "data" in data:
                drug = data["data"] if isinstance(data["data"], dict) else data

            if not isinstance(drug, dict):
                return None

            generic_names = drug.get("genericNames", [])
            if isinstance(generic_names, str):
                generic_names = [generic_names]
            elif not isinstance(generic_names, list):
                generic_names = []

            trade_names = drug.get("tradeNames", [])
            if isinstance(trade_names, str):
                trade_names = [trade_names]
            elif not isinstance(trade_names, list):
                trade_names = []

            cross_refs = []
            xrefs = drug.get("crossReferences", [])
            if isinstance(xrefs, list):
                for ref in xrefs:
                    if isinstance(ref, dict):
                        cross_refs.append({
                            "resource": ref.get("resource", ""),
                            "resource_id": ref.get("resourceId", ""),
                        })

            return {
                "pharmgkb_id": drug.get("id") or pharmgkb_id,
                "name": drug.get("name", ""),
                "generic_names": generic_names,
                "trade_names": trade_names,
                "description": (drug.get("description", "") or "")[:1000] or None,
                "drug_classes": drug.get("drugClasses", []),
                "cross_references": cross_refs[:20],
                "url": f"{PHARMGKB_WEB}/chemical/{pharmgkb_id}",
                "source": "PharmGKB",
            }

        except Exception as e:
            logger.debug(f"PharmGKB drug lookup failed for {pharmgkb_id}: {e}")
            return None

    def get_clinical_annotations(
        self, drug_name: str, limit: int = 20
    ) -> list[dict]:
        """
        Get clinical annotations linking a drug to genes with evidence levels.

        These are the KEY results from PharmGKB -- clinical annotations
        describe how specific gene variants affect response to a drug,
        graded by level of evidence (1A = highest, 4 = lowest).

        Returns: drug, gene, phenotype category, level of evidence,
        and clinical annotation text.
        """
        params = {"relatedChemicals.name": drug_name}
        url = f"{CLINICAL_ANN_URL}?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            items = _unwrap(data)

            results = []
            for ann in items[:limit]:
                if not isinstance(ann, dict):
                    continue

                # Extract related genes
                genes = []
                related_genes = ann.get("relatedGenes", [])
                if isinstance(related_genes, list):
                    for gene in related_genes:
                        if isinstance(gene, dict):
                            genes.append(gene.get("symbol") or gene.get("name", ""))
                        elif isinstance(gene, str):
                            genes.append(gene)

                # Extract related chemicals/drugs
                drugs = []
                related_chems = ann.get("relatedChemicals", [])
                if isinstance(related_chems, list):
                    for chem in related_chems:
                        if isinstance(chem, dict):
                            drugs.append(chem.get("name", ""))
                        elif isinstance(chem, str):
                            drugs.append(chem)

                # Evidence level (1A, 1B, 2A, 2B, 3, 4)
                level = ann.get("evidenceLevel") or ann.get("level", "")

                # Phenotype category
                phenotype_cat = ann.get("phenotypeCategory") or ann.get(
                    "phenotype", {})
                if isinstance(phenotype_cat, dict):
                    phenotype_cat = phenotype_cat.get("name", "")

                annotation_text = ann.get("text") or ann.get("summary", "")
                if isinstance(annotation_text, str):
                    annotation_text = annotation_text[:500]
                else:
                    annotation_text = ""

                ann_id = ann.get("id", "")

                results.append({
                    "annotation_id": ann_id,
                    "drug": drugs[0] if drugs else drug_name,
                    "genes": [g for g in genes if g],
                    "phenotype_category": phenotype_cat if isinstance(phenotype_cat, str) else "",
                    "level_of_evidence": level,
                    "clinical_annotation_text": annotation_text,
                    "url": f"{PHARMGKB_WEB}/clinicalAnnotation/{ann_id}" if ann_id else None,
                    "source": "PharmGKB",
                })

            return results

        except Exception as e:
            logger.debug(
                f"PharmGKB clinical annotations failed for '{drug_name}': {e}"
            )
            return []

    def get_drug_labels(self, drug_name: str) -> list[dict]:
        """
        Get FDA/EMA/etc drug labels with pharmacogenomic information.

        These are official regulatory labels that include pharmacogenomic
        testing recommendations (e.g., "test for HLA-B*5701 before
        prescribing abacavir").
        """
        params = {"relatedChemicals.name": drug_name}
        url = f"{DRUG_LABEL_URL}?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            items = _unwrap(data)

            results = []
            for label in items:
                if not isinstance(label, dict):
                    continue

                # Source agency (FDA, EMA, PMDA, HCSC, etc.)
                agency = label.get("source") or label.get("agency", "")

                # Testing level (e.g., "Testing required", "Actionable PGx")
                testing_level = label.get("testingLevel") or label.get(
                    "pgxLevel", "")

                # Label text or summary
                summary = label.get("summary") or label.get("text", "")
                if isinstance(summary, str):
                    summary = summary[:500]
                else:
                    summary = ""

                # Related drugs
                drugs = []
                related_chems = label.get("relatedChemicals", [])
                if isinstance(related_chems, list):
                    for chem in related_chems:
                        if isinstance(chem, dict):
                            drugs.append(chem.get("name", ""))
                        elif isinstance(chem, str):
                            drugs.append(chem)

                label_id = label.get("id", "")

                results.append({
                    "label_id": label_id,
                    "drug": drugs[0] if drugs else drug_name,
                    "agency": agency,
                    "testing_level": testing_level,
                    "label_text_summary": summary,
                    "url": f"{PHARMGKB_WEB}/drugLabel/{label_id}" if label_id else None,
                    "source": "PharmGKB",
                })

            return results

        except Exception as e:
            logger.debug(f"PharmGKB drug labels failed for '{drug_name}': {e}")
            return []

    def get_guidelines(self, drug_name: str) -> list[dict]:
        """
        Get CPIC/DPWG dosing guidelines based on genotype.

        These are the most actionable results -- specific dosing
        recommendations based on a patient's genetic test results
        (e.g., "CYP2D6 poor metabolizer: reduce codeine dose by 50%").
        """
        params = {"relatedChemicals.name": drug_name}
        url = f"{GUIDELINE_URL}?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            items = _unwrap(data)

            results = []
            for guideline in items:
                if not isinstance(guideline, dict):
                    continue

                # Guideline source (CPIC, DPWG, etc.)
                guideline_source = guideline.get("source") or guideline.get(
                    "guidelineSource", "")

                # Related genes
                genes = []
                related_genes = guideline.get("relatedGenes", [])
                if isinstance(related_genes, list):
                    for gene in related_genes:
                        if isinstance(gene, dict):
                            genes.append(gene.get("symbol") or gene.get("name", ""))
                        elif isinstance(gene, str):
                            genes.append(gene)

                # Related drugs
                drugs = []
                related_chems = guideline.get("relatedChemicals", [])
                if isinstance(related_chems, list):
                    for chem in related_chems:
                        if isinstance(chem, dict):
                            drugs.append(chem.get("name", ""))
                        elif isinstance(chem, str):
                            drugs.append(chem)

                # Recommendation summary
                summary = guideline.get("summary") or guideline.get(
                    "recommendation", "") or guideline.get("text", "")
                if isinstance(summary, str):
                    summary = summary[:500]
                else:
                    summary = ""

                guideline_id = guideline.get("id", "")

                results.append({
                    "guideline_id": guideline_id,
                    "drug": drugs[0] if drugs else drug_name,
                    "genes": [g for g in genes if g],
                    "guideline_source": guideline_source,
                    "recommendation_summary": summary,
                    "url": f"{PHARMGKB_WEB}/guideline/{guideline_id}" if guideline_id else None,
                    "source": "PharmGKB",
                })

            return results

        except Exception as e:
            logger.debug(f"PharmGKB guidelines failed for '{drug_name}': {e}")
            return []

    def search_gene(self, gene_symbol: str, limit: int = 10) -> list[dict]:
        """
        Search PharmGKB for a gene and its drug associations.

        Useful for looking up pharmacogenes like CYP2D6, CYP2C19,
        HLA-B, VKORC1, etc.
        """
        params = {"symbol": gene_symbol}
        url = f"{GENE_SEARCH_URL}?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            items = _unwrap(data)

            results = []
            for gene in items[:limit]:
                if not isinstance(gene, dict):
                    continue

                gene_id = gene.get("id") or gene.get("pharmgkbId", "")
                symbol = gene.get("symbol", "")
                name = gene.get("name", "")

                if not symbol and not gene_id:
                    continue

                # Related drugs
                related_drugs = []
                related_chems = gene.get("relatedChemicals", [])
                if isinstance(related_chems, list):
                    for chem in related_chems:
                        if isinstance(chem, dict):
                            related_drugs.append(chem.get("name", ""))
                        elif isinstance(chem, str):
                            related_drugs.append(chem)

                results.append({
                    "pharmgkb_id": gene_id,
                    "symbol": symbol,
                    "name": name,
                    "related_drugs": related_drugs[:10],
                    "chromosome": gene.get("chromosome", ""),
                    "is_vip": gene.get("isVip", False),
                    "has_cpic_dosing": gene.get("hasCpicDosing", False),
                    "url": f"{PHARMGKB_WEB}/gene/{gene_id}" if gene_id else None,
                    "source": "PharmGKB",
                })

            return results

        except Exception as e:
            logger.debug(f"PharmGKB gene search failed for '{gene_symbol}': {e}")
            return []

    def get_drug_gene_relationships(self, drug_name: str) -> list[dict]:
        """
        Combine clinical annotations + guidelines for a complete picture
        of how genetics affect response to a specific drug.

        Returns a comprehensive drug-gene interaction summary with
        evidence levels, dosing guidelines, and regulatory label info.
        """
        # Gather all pharmacogenomic data for this drug
        annotations = self.get_clinical_annotations(drug_name, limit=30)
        guidelines = self.get_guidelines(drug_name)
        labels = self.get_drug_labels(drug_name)

        # Build per-gene summary
        gene_map = {}  # gene_symbol -> combined data

        # Add clinical annotations
        for ann in annotations:
            for gene in ann.get("genes", []):
                if not gene:
                    continue
                if gene not in gene_map:
                    gene_map[gene] = {
                        "drug": ann.get("drug", drug_name),
                        "gene": gene,
                        "clinical_annotations": [],
                        "guidelines": [],
                        "highest_evidence_level": "",
                        "source": "PharmGKB",
                    }

                gene_map[gene]["clinical_annotations"].append({
                    "phenotype_category": ann.get("phenotype_category", ""),
                    "level_of_evidence": ann.get("level_of_evidence", ""),
                    "text": ann.get("clinical_annotation_text", ""),
                })

                # Track highest evidence level
                current_level = ann.get("level_of_evidence", "")
                existing_level = gene_map[gene]["highest_evidence_level"]
                if _evidence_rank(current_level) > _evidence_rank(existing_level):
                    gene_map[gene]["highest_evidence_level"] = current_level

        # Add guidelines
        for gl in guidelines:
            for gene in gl.get("genes", []):
                if not gene:
                    continue
                if gene not in gene_map:
                    gene_map[gene] = {
                        "drug": gl.get("drug", drug_name),
                        "gene": gene,
                        "clinical_annotations": [],
                        "guidelines": [],
                        "highest_evidence_level": "",
                        "source": "PharmGKB",
                    }

                gene_map[gene]["guidelines"].append({
                    "guideline_source": gl.get("guideline_source", ""),
                    "recommendation": gl.get("recommendation_summary", ""),
                })

        # Add label info as metadata
        has_label_testing = False
        label_agencies = []
        for label in labels:
            testing = label.get("testing_level", "")
            if testing:
                has_label_testing = True
            agency = label.get("agency", "")
            if agency and agency not in label_agencies:
                label_agencies.append(agency)

        # Annotate gene entries with label info
        for gene_data in gene_map.values():
            gene_data["has_regulatory_label"] = has_label_testing
            gene_data["regulatory_agencies"] = label_agencies

        # Sort by evidence level (strongest first)
        results = sorted(
            gene_map.values(),
            key=lambda g: _evidence_rank(g.get("highest_evidence_level", "")),
            reverse=True,
        )

        return results


def _evidence_rank(level: str) -> int:
    """
    Rank PharmGKB evidence levels for sorting.

    1A = highest clinical evidence, 4 = lowest.
    Higher return value = stronger evidence.
    """
    ranks = {
        "1A": 6,
        "1B": 5,
        "2A": 4,
        "2B": 3,
        "3": 2,
        "4": 1,
    }
    return ranks.get(str(level).strip(), 0)
