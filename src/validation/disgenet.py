"""
Clinical Intelligence Hub -- DisGeNET

DisGeNET is the largest public collection of gene-disease associations,
integrating data from multiple expert-curated repositories, GWAS catalogs,
animal models, and scientific literature. It provides:

- Over 1.1 million gene-disease associations
- Coverage of 30,000+ diseases and 21,000+ genes
- Evidence scores combining source reliability, replication, and literature support
- Variant-disease associations with genomic coordinates

Data sources include UniProt, ClinGen, CGI, GWAS Catalog, ClinVar, ORPHANET,
CTD, PsyGeNET, and text-mined associations from MEDLINE abstracts. Each
association carries a GDA (Gene-Disease Association) score from 0 to 1 that
reflects the number and type of sources reporting the association, the
consistency of the evidence, and the level of curation.

DisGeNET is used by over 16,000 registered users and cited in more than
8,000 scientific publications. It is free for academic use.

API: https://www.disgenet.org/api
Downloadable TSV: https://disgenet.com/static/disgenet_ap1/files/downloads/all_gene_disease_associations.tsv.gz
Rate limits: API is rate-limited; an API key increases quotas.
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-DisGeNET")

# ── API Endpoints ────────────────────────────────────────────────
# Kept as constants so URLs are easy to adjust if the API changes.

DISGENET_API = "https://www.disgenet.org/api"

# GDA (Gene-Disease Association) endpoints
GDA_DISEASE_URL = f"{DISGENET_API}/gda/disease"
GDA_GENE_URL = f"{DISGENET_API}/gda/gene"
GDA_SEARCH_URL = f"{DISGENET_API}/gda/search"

# VDA (Variant-Disease Association) endpoints
VDA_GENE_URL = f"{DISGENET_API}/vda/gene"

# Disease-Disease similarity / network
DISEASE_SEARCH_URL = f"{DISGENET_API}/disease/search"

DISGENET_WEB = "https://www.disgenet.org"


class DisGeNETClient:
    """DisGeNET client for gene-disease association lookup and network analysis."""

    def __init__(self, api_key: str = None, data_dir: str = None):
        """
        Args:
            api_key: Optional DisGeNET API key for higher rate limits.
                     Register at https://www.disgenet.org/signup/
            data_dir: Optional path to directory containing downloaded
                      DisGeNET TSV files for local lookup (not yet
                      implemented -- reserved for offline mode).
        """
        self._api_key = api_key
        self._data_dir = data_dir

    # ── Public methods ──────────────────────────────────────

    def search_disease_genes(
        self, disease_name: str, limit: int = 20
    ) -> list[dict]:
        """
        Search for genes associated with a disease.

        Queries DisGeNET's gene-disease association endpoint by disease
        name. Returns genes ranked by association score (strongest
        evidence first).

        Args:
            disease_name: Disease or condition name (e.g., "Alzheimer's
                          disease", "breast cancer", "type 2 diabetes")
            limit: Maximum number of gene associations to return.

        Returns:
            List of gene-disease associations, each with gene_symbol,
            gene_name, disease_name, score (0-1), evidence_count,
            pmid_count, and source.
        """
        if not disease_name or not disease_name.strip():
            return []

        disease_clean = disease_name.strip()

        # Try the search endpoint first (more flexible name matching)
        url = self._build_url(
            GDA_SEARCH_URL,
            {"disease": disease_clean, "limit": str(limit), "format": "json"},
        )

        try:
            data = api_get(url, headers=self._auth_headers())
            items = self._unwrap_results(data)

            # If the search endpoint didn't work, try the disease endpoint
            if not items:
                encoded_name = urllib.parse.quote(disease_clean)
                url = self._build_url(
                    f"{GDA_DISEASE_URL}/{encoded_name}",
                    {"limit": str(limit), "format": "json"},
                )
                data = api_get(url, headers=self._auth_headers())
                items = self._unwrap_results(data)

            if not items:
                return []

            results = []
            for item in items[:limit]:
                if not isinstance(item, dict):
                    continue

                parsed = self._parse_gda(item)
                if parsed:
                    results.append(parsed)

            # Sort by score descending (strongest associations first)
            results.sort(key=lambda r: r.get("score", 0), reverse=True)
            return results

        except Exception as e:
            logger.debug(
                "DisGeNET search_disease_genes failed for '%s': %s",
                disease_name,
                e,
            )
            return []

    def search_gene_diseases(
        self, gene_symbol: str, limit: int = 20
    ) -> list[dict]:
        """
        Search for diseases associated with a gene (reverse lookup).

        Given a gene symbol, returns all diseases linked to it in
        DisGeNET, ranked by association score. Useful for understanding
        the full disease spectrum of a gene.

        Args:
            gene_symbol: HGNC gene symbol (e.g., "BRCA1", "TP53",
                         "APOE", "CYP2D6")
            limit: Maximum number of disease associations to return.

        Returns:
            List of disease associations, each with disease_name,
            disease_id, score (0-1), and evidence_count.
        """
        if not gene_symbol or not gene_symbol.strip():
            return []

        gene_clean = gene_symbol.strip().upper()
        encoded_gene = urllib.parse.quote(gene_clean)

        url = self._build_url(
            f"{GDA_GENE_URL}/{encoded_gene}",
            {"limit": str(limit), "format": "json"},
        )

        try:
            data = api_get(url, headers=self._auth_headers())
            items = self._unwrap_results(data)

            if not items:
                return []

            results = []
            for item in items[:limit]:
                if not isinstance(item, dict):
                    continue

                disease_name = (
                    item.get("disease_name")
                    or item.get("diseaseName")
                    or item.get("disease", {}).get("disease_name", "")
                    if isinstance(item.get("disease"), dict)
                    else item.get("disease_name", "")
                )

                disease_id = (
                    item.get("diseaseid")
                    or item.get("diseaseId")
                    or item.get("disease_id")
                    or item.get("disease", {}).get("diseaseId", "")
                    if isinstance(item.get("disease"), dict)
                    else item.get("diseaseid", "")
                )

                score = self._safe_float(
                    item.get("score")
                    or item.get("score_gda")
                    or item.get("associationScore")
                )

                ei = self._safe_float(
                    item.get("ei")
                    or item.get("evidence_index")
                    or item.get("evidenceIndex")
                )

                results.append({
                    "disease_name": disease_name or "Unknown",
                    "disease_id": disease_id or None,
                    "score": score,
                    "evidence_index": ei,
                    "evidence_count": self._safe_int(
                        item.get("Nsources")
                        or item.get("nSources")
                        or item.get("source_count")
                    ),
                    "pmid_count": self._safe_int(
                        item.get("Npmids")
                        or item.get("nPmids")
                        or item.get("pmid_count")
                    ),
                    "gene_symbol": gene_clean,
                    "url": (
                        f"{DISGENET_WEB}/browser/1/1/{disease_id}/"
                        if disease_id
                        else None
                    ),
                    "source": "DisGeNET",
                })

            results.sort(key=lambda r: r.get("score", 0), reverse=True)
            return results

        except Exception as e:
            logger.debug(
                "DisGeNET search_gene_diseases failed for '%s': %s",
                gene_symbol,
                e,
            )
            return []

    def get_gene_disease_association(
        self, gene_symbol: str, disease_name: str
    ) -> Optional[dict]:
        """
        Check the specific association between a gene and a disease.

        Queries DisGeNET for the direct association between a named
        gene and disease, returning the evidence score, evidence index,
        source breakdown, and literature support.

        Args:
            gene_symbol: HGNC gene symbol (e.g., "BRCA1")
            disease_name: Disease name (e.g., "breast cancer")

        Returns:
            Association details with score, evidence_index, sources,
            and pmid_count, or None if no association is found.
        """
        if not gene_symbol or not disease_name:
            return None

        gene_clean = gene_symbol.strip().upper()
        disease_clean = disease_name.strip()

        # Search for the gene, then filter by disease name
        url = self._build_url(
            GDA_SEARCH_URL,
            {
                "gene": gene_clean,
                "disease": disease_clean,
                "limit": "5",
                "format": "json",
            },
        )

        try:
            data = api_get(url, headers=self._auth_headers())
            items = self._unwrap_results(data)

            # Fallback: search gene associations and filter client-side
            if not items:
                gene_results = self.search_gene_diseases(gene_clean, limit=50)
                for result in gene_results:
                    result_disease = (
                        result.get("disease_name", "").lower()
                    )
                    if disease_clean.lower() in result_disease:
                        return {
                            "gene_symbol": gene_clean,
                            "disease_name": result.get("disease_name", ""),
                            "disease_id": result.get("disease_id"),
                            "score": result.get("score"),
                            "evidence_index": result.get("evidence_index"),
                            "evidence_count": result.get("evidence_count"),
                            "pmid_count": result.get("pmid_count"),
                            "association_found": True,
                            "source": "DisGeNET",
                        }
                return None

            # Parse the best matching result
            for item in items:
                if not isinstance(item, dict):
                    continue

                parsed = self._parse_gda(item)
                if not parsed:
                    continue

                return {
                    "gene_symbol": parsed.get("gene_symbol", gene_clean),
                    "gene_name": parsed.get("gene_name"),
                    "disease_name": parsed.get("disease_name", disease_clean),
                    "disease_id": parsed.get("disease_id"),
                    "score": parsed.get("score"),
                    "evidence_index": parsed.get("evidence_index"),
                    "evidence_count": parsed.get("evidence_count"),
                    "pmid_count": parsed.get("pmid_count"),
                    "sources": parsed.get("sources"),
                    "association_found": True,
                    "source": "DisGeNET",
                }

            return None

        except Exception as e:
            logger.debug(
                "DisGeNET get_gene_disease_association failed for "
                "'%s' / '%s': %s",
                gene_symbol,
                disease_name,
                e,
            )
            return None

    def get_disease_network(
        self, disease_name: str, limit: int = 20
    ) -> list[dict]:
        """
        Get diseases that share genes with the queried disease.

        This reveals hidden connections between seemingly unrelated
        conditions. For example, Alzheimer's disease shares genetic
        associations with type 2 diabetes through APOE and IDE genes.
        These shared-gene networks are critical for cross-disciplinary
        clinical analysis.

        Args:
            disease_name: Disease name to find network connections for.
            limit: Maximum number of related diseases to return.

        Returns:
            List of related diseases with shared_gene_count and
            jaccard_index (similarity metric from 0-1).
        """
        if not disease_name or not disease_name.strip():
            return []

        disease_clean = disease_name.strip()

        # Step 1: Get the genes associated with the query disease
        query_genes = self.search_disease_genes(disease_clean, limit=50)
        if not query_genes:
            return []

        query_gene_set = {
            g["gene_symbol"]
            for g in query_genes
            if g.get("gene_symbol")
        }

        if not query_gene_set:
            return []

        # Step 2: For each gene, find other diseases associated with it,
        # then compute overlap. We limit to top genes to stay within
        # rate limits.
        disease_gene_map: dict[str, set] = {}  # disease_name -> set of genes

        top_genes = sorted(
            query_genes, key=lambda g: g.get("score", 0), reverse=True
        )[:15]  # Top 15 genes to keep API calls reasonable

        for gene_entry in top_genes:
            gene_sym = gene_entry.get("gene_symbol", "")
            if not gene_sym:
                continue

            gene_diseases = self.search_gene_diseases(gene_sym, limit=30)
            for gd in gene_diseases:
                other_disease = gd.get("disease_name", "")
                if not other_disease:
                    continue
                # Skip the query disease itself
                if other_disease.lower() == disease_clean.lower():
                    continue

                if other_disease not in disease_gene_map:
                    disease_gene_map[other_disease] = set()
                disease_gene_map[other_disease].add(gene_sym)

        if not disease_gene_map:
            return []

        # Step 3: Compute Jaccard index for each related disease
        results = []
        for other_disease, shared_genes in disease_gene_map.items():
            shared_count = len(shared_genes & query_gene_set)
            if shared_count == 0:
                continue

            union_count = len(shared_genes | query_gene_set)
            jaccard = round(shared_count / union_count, 4) if union_count else 0

            results.append({
                "disease_name": other_disease,
                "query_disease": disease_clean,
                "shared_gene_count": shared_count,
                "shared_genes": sorted(shared_genes & query_gene_set),
                "jaccard_index": jaccard,
                "source": "DisGeNET",
            })

        # Sort by shared gene count descending
        results.sort(key=lambda r: r["shared_gene_count"], reverse=True)
        return results[:limit]

    def get_gene_variants(
        self, gene_symbol: str, limit: int = 20
    ) -> list[dict]:
        """
        Get variant-disease associations (VDAs) for a gene.

        Returns specific genetic variants (identified by rsID) that
        are associated with diseases, along with the VDA score.

        Args:
            gene_symbol: HGNC gene symbol (e.g., "BRCA1", "APOE")
            limit: Maximum number of variant associations to return.

        Returns:
            List of variant-disease associations, each with rsid,
            disease name, and VDA score.
        """
        if not gene_symbol or not gene_symbol.strip():
            return []

        gene_clean = gene_symbol.strip().upper()
        encoded_gene = urllib.parse.quote(gene_clean)

        url = self._build_url(
            f"{VDA_GENE_URL}/{encoded_gene}",
            {"limit": str(limit), "format": "json"},
        )

        try:
            data = api_get(url, headers=self._auth_headers())
            items = self._unwrap_results(data)

            if not items:
                return []

            results = []
            for item in items[:limit]:
                if not isinstance(item, dict):
                    continue

                # Variant ID (rsID)
                rsid = (
                    item.get("variantid")
                    or item.get("variantId")
                    or item.get("variant_id")
                    or item.get("snpId")
                    or ""
                )

                # Disease info
                disease_name = (
                    item.get("disease_name")
                    or item.get("diseaseName")
                    or ""
                )
                if not disease_name and isinstance(item.get("disease"), dict):
                    disease_name = item["disease"].get("disease_name", "")

                disease_id = (
                    item.get("diseaseid")
                    or item.get("diseaseId")
                    or item.get("disease_id")
                    or ""
                )
                if not disease_id and isinstance(item.get("disease"), dict):
                    disease_id = item["disease"].get("diseaseId", "")

                score = self._safe_float(
                    item.get("score")
                    or item.get("score_vda")
                    or item.get("associationScore")
                )

                pmid_count = self._safe_int(
                    item.get("Npmids")
                    or item.get("nPmids")
                    or item.get("pmid_count")
                )

                if not rsid and not disease_name:
                    continue

                results.append({
                    "rsid": rsid,
                    "gene_symbol": gene_clean,
                    "disease_name": disease_name or "Unknown",
                    "disease_id": disease_id or None,
                    "score": score,
                    "pmid_count": pmid_count,
                    "url": (
                        f"https://www.ncbi.nlm.nih.gov/snp/{rsid}"
                        if rsid and rsid.startswith("rs")
                        else None
                    ),
                    "source": "DisGeNET",
                })

            results.sort(key=lambda r: r.get("score", 0), reverse=True)
            return results

        except Exception as e:
            logger.debug(
                "DisGeNET get_gene_variants failed for '%s': %s",
                gene_symbol,
                e,
            )
            return []

    # ── Authentication ────────────────────────────────────────

    def _auth_headers(self) -> Optional[dict]:
        """
        Build authentication headers if an API key is available.

        DisGeNET accepts the key as either a Bearer token or a query
        parameter. We send it as a header for cleanliness.
        """
        if not self._api_key:
            return None

        return {"Authorization": f"Bearer {self._api_key}"}

    # ── URL builder ───────────────────────────────────────────

    @staticmethod
    def _build_url(base: str, params: dict) -> str:
        """
        Build a full API URL with query parameters.

        Filters out None values from params before encoding.
        """
        filtered = {k: v for k, v in params.items() if v is not None}
        if not filtered:
            return base

        query_string = urllib.parse.urlencode(filtered)
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}{query_string}"

    # ── Response unwrapping ───────────────────────────────────

    @staticmethod
    def _unwrap_results(response) -> list:
        """
        Unwrap DisGeNET API response into a list of result items.

        The API response format may vary:
        - Direct list of associations
        - Dict with "results" or "data" key containing a list
        - Dict with "payload" key
        - Single association dict
        """
        if response is None:
            return []
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            # Try common wrapper keys
            for key in ("results", "data", "payload", "associations"):
                value = response.get(key)
                if isinstance(value, list):
                    return value
                if isinstance(value, dict):
                    return [value]
            # Maybe the dict itself is a single result
            if response.get("gene_symbol") or response.get("geneid"):
                return [response]
            return []
        return []

    # ── GDA parsing ───────────────────────────────────────────

    def _parse_gda(self, item: dict) -> Optional[dict]:
        """
        Parse a gene-disease association record from the API response.

        Handles multiple possible field naming conventions defensively.
        """
        try:
            # Gene info — field names vary across API versions
            gene_symbol = (
                item.get("gene_symbol")
                or item.get("geneSymbol")
                or ""
            )
            if not gene_symbol and isinstance(item.get("gene"), dict):
                gene_symbol = (
                    item["gene"].get("gene_symbol")
                    or item["gene"].get("symbol")
                    or ""
                )

            gene_name = (
                item.get("gene_name")
                or item.get("geneName")
                or ""
            )
            if not gene_name and isinstance(item.get("gene"), dict):
                gene_name = item["gene"].get("gene_name", "")

            # Disease info
            disease_name = (
                item.get("disease_name")
                or item.get("diseaseName")
                or ""
            )
            if not disease_name and isinstance(item.get("disease"), dict):
                disease_name = item["disease"].get("disease_name", "")

            disease_id = (
                item.get("diseaseid")
                or item.get("diseaseId")
                or item.get("disease_id")
                or ""
            )
            if not disease_id and isinstance(item.get("disease"), dict):
                disease_id = item["disease"].get("diseaseId", "")

            # Scores
            score = self._safe_float(
                item.get("score")
                or item.get("score_gda")
                or item.get("associationScore")
            )

            ei = self._safe_float(
                item.get("ei")
                or item.get("evidence_index")
                or item.get("evidenceIndex")
            )

            # Evidence counts
            evidence_count = self._safe_int(
                item.get("Nsources")
                or item.get("nSources")
                or item.get("source_count")
            )

            pmid_count = self._safe_int(
                item.get("Npmids")
                or item.get("nPmids")
                or item.get("pmid_count")
            )

            # Source breakdown
            sources = (
                item.get("source")
                or item.get("sources")
                or item.get("sourceList")
            )
            if isinstance(sources, str):
                sources = [s.strip() for s in sources.split(";") if s.strip()]
            elif not isinstance(sources, list):
                sources = None

            if not gene_symbol and not disease_name:
                return None

            return {
                "gene_symbol": gene_symbol or "Unknown",
                "gene_name": gene_name or None,
                "disease_name": disease_name or "Unknown",
                "disease_id": disease_id or None,
                "score": score,
                "evidence_index": ei,
                "evidence_count": evidence_count,
                "pmid_count": pmid_count,
                "sources": sources,
                "url": (
                    f"{DISGENET_WEB}/browser/0/1/{gene_symbol}/"
                    if gene_symbol
                    else None
                ),
                "source": "DisGeNET",
            }

        except Exception as e:
            logger.debug("DisGeNET GDA parse failed: %s", e)
            return None

    # ── Type coercion helpers ─────────────────────────────────

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        """Convert a value to float, returning None on failure."""
        if value is None:
            return None
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        """Convert a value to int, returning None on failure."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
