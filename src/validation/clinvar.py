"""
Clinical Intelligence Hub — ClinVar (NCBI)

ClinVar is NCBI's freely accessible archive of variant-disease
relationships with clinical significance ratings. Each submitted
variant interpretation is classified on a five-tier scale:

    Pathogenic > Likely pathogenic > Uncertain significance
    > Likely benign > Benign

These classifications come from clinical laboratories, research
groups, and expert panels worldwide. ClinVar aggregates them and
assigns a review status (0-4 stars) reflecting the level of
consensus and evidence quality.

ClinVar is critical for interpreting genetic testing results —
it answers the question "has this variant been seen before, and
what did clinical labs conclude about it?"

API: NCBI E-utilities (same infrastructure as PubMed)
Base: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
Database: "clinvar"
Rate limits: 3 req/sec without API key, 10 req/sec with key.
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-ClinVar")

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CLINVAR_DB = "clinvar"


class ClinVarClient:
    """NCBI ClinVar client for genetic variant interpretation lookup."""

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: Optional NCBI API key (increases rate limit
                     from 3/sec to 10/sec). Register free at
                     https://www.ncbi.nlm.nih.gov/account/
        """
        self._api_key = api_key

    # ── Public methods ──────────────────────────────────────

    def search_variant(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search ClinVar for variants matching a free-text query.

        Works with rsIDs (rs80357906), HGVS expressions
        (NM_007294.4:c.5266dupC), gene names, or conditions.

        Returns list of variant summaries with clinical significance.
        """
        ids = self._esearch(query, limit)
        if not ids:
            return []

        return self._esummary_batch(ids)

    def get_variant(self, clinvar_id: str) -> Optional[dict]:
        """
        Get full details for a specific ClinVar variation ID.

        Returns clinical significance, gene, conditions, review
        status, molecular consequence, and variation type.
        """
        url = self._build_url(
            "/esummary.fcgi",
            {"db": CLINVAR_DB, "id": clinvar_id, "retmode": "json"},
        )

        try:
            data = api_get(url)
            if not data:
                return None

            result = data.get("result", {})
            if not result:
                return None

            # esummary returns UIDs as keys under "result"
            uid_list = result.get("uids", [])
            if not uid_list:
                return None

            uid = str(uid_list[0])
            entry = result.get(uid)
            if not entry:
                return None

            return self._parse_variant_detail(uid, entry)

        except Exception as e:
            logger.debug(f"ClinVar get_variant failed for {clinvar_id}: {e}")
            return None

    def search_gene_variants(
        self,
        gene_symbol: str,
        significance: str = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Search for clinically significant variants in a gene.

        Args:
            gene_symbol: HGNC gene symbol (e.g., "BRCA1", "TP53")
            significance: Optional filter — one of:
                "pathogenic", "likely_pathogenic",
                "uncertain_significance", "likely_benign", "benign"
            limit: Max results to return.

        Returns list of variant summaries found in the gene.
        """
        term = f"{gene_symbol}[gene]"
        if significance:
            # ClinVar uses space-separated words in the field
            sig_term = significance.replace("_", " ")
            term += f" AND {sig_term}[clinical_significance]"

        ids = self._esearch(term, limit)
        if not ids:
            return []

        return self._esummary_batch(ids)

    def search_condition_variants(
        self, condition: str, limit: int = 20
    ) -> list[dict]:
        """
        Search for variants associated with a disease or condition.

        Uses ClinVar's disease/phenotype field, which maps to
        MedGen, OMIM, and Orphanet condition identifiers.

        Args:
            condition: Disease name (e.g., "Breast cancer",
                       "Cystic fibrosis", "Long QT syndrome")
            limit: Max results to return.

        Returns list of variants with genes and significance.
        """
        term = f"{condition}[disease/phenotype]"

        ids = self._esearch(term, limit)
        if not ids:
            return []

        return self._esummary_batch(ids)

    def interpret_variant(
        self, gene: str, variant: str
    ) -> Optional[dict]:
        """
        Look up clinical interpretation for a specific variant.

        Handles common formats:
            interpret_variant("BRCA1", "c.5266dupC")
            interpret_variant("BRCA2", "rs80359550")
            interpret_variant("CFTR", "p.Phe508del")

        Returns clinical significance interpretation with review
        stars, or None if the variant is not in ClinVar.
        """
        term = f"{gene}[gene] AND {variant}"

        ids = self._esearch(term, limit=5)
        if not ids:
            return None

        variants = self._esummary_batch(ids)
        if not variants:
            return None

        # Return the best match (first result from ClinVar's ranking)
        best = variants[0]

        # Enrich with interpretation context
        best["query_gene"] = gene
        best["query_variant"] = variant
        best["interpretation_available"] = bool(
            best.get("clinical_significance")
        )

        return best

    # ── E-utilities helpers ────────────────────────────────

    def _esearch(self, term: str, limit: int) -> list[str]:
        """
        Search ClinVar and return a list of variation UIDs.

        Uses E-utilities esearch endpoint with JSON output.
        """
        url = self._build_url(
            "/esearch.fcgi",
            {
                "db": CLINVAR_DB,
                "term": term,
                "retmax": str(limit),
                "retmode": "json",
            },
        )

        try:
            data = api_get(url)
            if not data:
                return []

            return data.get("esearchresult", {}).get("idlist", [])

        except Exception as e:
            logger.debug(f"ClinVar esearch failed for '{term[:60]}': {e}")
            return []

    def _esummary_batch(self, ids: list[str]) -> list[dict]:
        """
        Fetch variant summaries for a list of ClinVar UIDs.

        Joins IDs into a single esummary call (NCBI supports
        comma-separated ID lists up to ~200 IDs).
        """
        if not ids:
            return []

        id_list = ",".join(ids)
        url = self._build_url(
            "/esummary.fcgi",
            {"db": CLINVAR_DB, "id": id_list, "retmode": "json"},
        )

        try:
            data = api_get(url)
            if not data:
                return []

            result = data.get("result", {})
            if not result:
                return []

            uid_list = result.get("uids", [])

            variants = []
            for uid in uid_list:
                entry = result.get(str(uid))
                if not entry:
                    continue

                parsed = self._parse_variant_summary(str(uid), entry)
                if parsed:
                    variants.append(parsed)

            return variants

        except Exception as e:
            logger.debug(f"ClinVar esummary failed: {e}")
            return []

    # ── Parsing helpers ────────────────────────────────────

    def _parse_variant_summary(self, uid: str, entry: dict) -> Optional[dict]:
        """
        Parse an esummary entry into a standardized variant summary.

        ClinVar esummary response structure varies by entry type.
        We extract the most clinically useful fields defensively.
        """
        try:
            # Clinical significance — may be nested or flat
            clinical_sig = (
                entry.get("clinical_significance", {})
                if isinstance(entry.get("clinical_significance"), dict)
                else {}
            )
            significance_desc = (
                clinical_sig.get("description", "")
                or entry.get("clinical_significance", "")
            )
            if isinstance(significance_desc, dict):
                significance_desc = significance_desc.get("description", "")

            # Gene(s)
            genes = entry.get("genes", [])
            gene_symbol = ""
            if isinstance(genes, list) and genes:
                first_gene = genes[0]
                if isinstance(first_gene, dict):
                    gene_symbol = first_gene.get("symbol", "")
                elif isinstance(first_gene, str):
                    gene_symbol = first_gene

            # Condition/trait names
            trait_set = entry.get("trait_set", [])
            conditions = []
            if isinstance(trait_set, list):
                for trait in trait_set:
                    if isinstance(trait, dict):
                        name = trait.get("trait_name", "")
                        if name:
                            conditions.append(name)

            # Review status (star rating)
            review_status = ""
            if isinstance(clinical_sig, dict):
                review_status = clinical_sig.get("review_status", "")
            if not review_status:
                review_status = entry.get("review_status", "")

            return {
                "uid": uid,
                "title": entry.get("title", ""),
                "clinical_significance": str(significance_desc),
                "gene": gene_symbol,
                "condition": "; ".join(conditions) if conditions else "",
                "review_status": str(review_status),
                "variation_type": entry.get("variation_type", ""),
                "accession": entry.get("accession", ""),
                "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/",
                "source": "ClinVar (NCBI)",
            }

        except Exception as e:
            logger.debug(f"ClinVar parse failed for UID {uid}: {e}")
            return None

    def _parse_variant_detail(self, uid: str, entry: dict) -> Optional[dict]:
        """
        Parse an esummary entry into a full variant detail record.

        Includes all fields from the summary plus molecular
        consequence and additional metadata.
        """
        summary = self._parse_variant_summary(uid, entry)
        if not summary:
            return None

        # Additional detail fields
        summary["molecular_consequence"] = entry.get(
            "molecular_consequence", ""
        )
        summary["protein_change"] = entry.get("protein_change", "")
        summary["variation_set"] = entry.get("variation_set", [])
        summary["supporting_submissions"] = entry.get(
            "supporting_submissions", {}
        )

        # Extract gene list if multiple genes
        genes = entry.get("genes", [])
        gene_symbols = []
        if isinstance(genes, list):
            for g in genes:
                if isinstance(g, dict):
                    sym = g.get("symbol", "")
                    if sym:
                        gene_symbols.append(sym)
                elif isinstance(g, str) and g:
                    gene_symbols.append(g)
        summary["gene_symbols"] = gene_symbols

        # Extract all condition names
        trait_set = entry.get("trait_set", [])
        condition_names = []
        if isinstance(trait_set, list):
            for trait in trait_set:
                if isinstance(trait, dict):
                    name = trait.get("trait_name", "")
                    if name:
                        condition_names.append(name)
        summary["condition_names"] = condition_names

        return summary

    # ── URL builder ────────────────────────────────────────

    def _build_url(self, endpoint: str, params: dict) -> str:
        """
        Build a full E-utilities URL with optional API key.

        Appends the NCBI API key if one was provided at init.
        """
        if self._api_key:
            params["api_key"] = self._api_key

        query_string = urllib.parse.urlencode(params)
        return f"{EUTILS_BASE}{endpoint}?{query_string}"
