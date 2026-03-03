"""
Clinical Intelligence Hub — OMIM (Online Mendelian Inheritance in Man)

The gold standard for genetic and rare disease information.
OMIM catalogs all known Mendelian (genetic) disorders and their
associated genes, phenotypes, and inheritance patterns.

API: https://api.omim.org/ (free for non-commercial, requires API key)
Registration: https://omim.org/api

Without an API key, we use the OMIM search page as a fallback.
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-OMIM")

OMIM_API_BASE = "https://api.omim.org/api"


class OMIMClient:
    """OMIM API client for genetic/rare disease lookup."""

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: OMIM API key (free registration at omim.org/api).
                     Without a key, only limited search is available.
        """
        self._api_key = api_key

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search OMIM for genetic disorders matching a query.

        Returns disorder entries with MIM numbers, titles,
        gene symbols, and inheritance patterns.
        """
        if not self._api_key:
            logger.debug("OMIM API key not configured — limited results")
            return self._search_fallback(query, limit)

        params = {
            "apiKey": self._api_key,
            "search": query,
            "format": "json",
            "limit": str(limit),
            "include": "all",
            "filter": "entry_type:disease",
        }

        url = f"{OMIM_API_BASE}/entry/search?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            if not data:
                return []

            entries = (
                data.get("omim", {})
                .get("searchResponse", {})
                .get("entryList", [])
            )

            results = []
            for item in entries:
                entry = item.get("entry", {})
                titles = entry.get("titles", {})

                # Parse gene map if available
                gene_map = entry.get("geneMap", {})
                genes = []
                if gene_map:
                    gene_symbols = gene_map.get("geneSymbols", "")
                    if gene_symbols:
                        genes = [g.strip() for g in gene_symbols.split(",")]

                # Inheritance
                inheritance = []
                if gene_map.get("phenotypeMapList"):
                    for pheno in gene_map["phenotypeMapList"]:
                        pmap = pheno.get("phenotypeMap", {})
                        inh = pmap.get("phenotypeMappingKey", "")
                        if inh:
                            inheritance.append(str(inh))

                results.append({
                    "mim_number": entry.get("mimNumber"),
                    "title": titles.get("preferredTitle", ""),
                    "alternative_titles": titles.get("alternativeTitles", ""),
                    "genes": genes,
                    "inheritance": inheritance,
                    "status": entry.get("status", ""),
                    "url": f"https://omim.org/entry/{entry.get('mimNumber', '')}",
                    "source": "OMIM",
                })

            return results

        except Exception as e:
            logger.debug(f"OMIM search failed for '{query}': {e}")
            return []

    def get_entry(self, mim_number: int) -> Optional[dict]:
        """
        Get a specific OMIM entry by MIM number.

        Returns full entry with clinical synopsis, description,
        gene associations, and references.
        """
        if not self._api_key:
            return {
                "mim_number": mim_number,
                "url": f"https://omim.org/entry/{mim_number}",
                "source": "OMIM",
                "note": "Full data requires OMIM API key",
            }

        params = {
            "apiKey": self._api_key,
            "mimNumber": str(mim_number),
            "format": "json",
            "include": "all",
        }

        url = f"{OMIM_API_BASE}/entry?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            if not data:
                return None

            entries = (
                data.get("omim", {})
                .get("entryList", [])
            )
            if not entries:
                return None

            entry = entries[0].get("entry", {})
            titles = entry.get("titles", {})
            text_sections = entry.get("textSectionList", [])

            # Extract clinical synopsis
            clinical_synopsis = entry.get("clinicalSynopsis", {})
            phenotypes = {}
            if clinical_synopsis:
                for key, value in clinical_synopsis.items():
                    if key.startswith("_") or key in ("mimNumber", "exists"):
                        continue
                    if isinstance(value, str):
                        phenotypes[key] = [
                            v.strip() for v in value.split(";")
                            if v.strip()
                        ]

            # Extract description/text
            description = ""
            for section in text_sections:
                ts = section.get("textSection", {})
                if ts.get("textSectionName") == "description":
                    description = ts.get("textSectionContent", "")[:1000]
                    break

            return {
                "mim_number": mim_number,
                "title": titles.get("preferredTitle", ""),
                "description": description,
                "clinical_synopsis": phenotypes,
                "gene_map": entry.get("geneMap", {}),
                "references_count": len(entry.get("referenceList", [])),
                "url": f"https://omim.org/entry/{mim_number}",
                "source": "OMIM",
            }

        except Exception as e:
            logger.debug(f"OMIM entry lookup failed for {mim_number}: {e}")
            return None

    def search_by_gene(self, gene_symbol: str) -> list[dict]:
        """
        Search OMIM for disorders associated with a specific gene.

        Useful when a patient has genetic testing results.
        """
        return self.search(f"{gene_symbol} gene", limit=10)

    def get_phenotype_series(self, ps_number: int) -> Optional[dict]:
        """
        Get a phenotype series (group of related disorders).

        Example: PS256100 = Netherton syndrome and related conditions.
        """
        if not self._api_key:
            return None

        params = {
            "apiKey": self._api_key,
            "psNumber": f"PS{ps_number}",
            "format": "json",
        }

        url = (
            f"{OMIM_API_BASE}/entry/phenotypeSeries"
            f"?{urllib.parse.urlencode(params)}"
        )

        try:
            data = api_get(url)
            if not data:
                return None

            series = (
                data.get("omim", {})
                .get("phenotypeSeries", {})
            )

            return {
                "ps_number": f"PS{ps_number}",
                "title": series.get("phenotypeSeriesTitle", ""),
                "entries": [
                    {
                        "mim_number": e.get("mimNumber"),
                        "title": e.get("phenotype", ""),
                        "gene": e.get("geneSymbols", ""),
                    }
                    for e in series.get("phenotypeSeriesEntry", [])
                ],
                "source": "OMIM",
            }

        except Exception as e:
            logger.debug(f"OMIM phenotype series failed for PS{ps_number}: {e}")
            return None

    # ── Fallback (no API key) ────────────────────────────────

    def _search_fallback(self, query: str, limit: int) -> list[dict]:
        """
        Limited search without API key — uses OMIM's public geneMap search.

        Returns basic results with MIM numbers and titles.
        """
        params = {
            "search": query,
            "format": "json",
            "limit": str(limit),
        }

        url = f"{OMIM_API_BASE}/geneMap/search?{urllib.parse.urlencode(params)}"

        try:
            data = api_get(url)
            if not data:
                return []

            entries = (
                data.get("omim", {})
                .get("searchResponse", {})
                .get("geneMapList", [])
            )

            results = []
            for item in entries:
                gm = item.get("geneMap", {})
                phenos = gm.get("phenotypeMapList", [])

                for p_entry in phenos:
                    pmap = p_entry.get("phenotypeMap", {})
                    mim = pmap.get("phenotypeMimNumber")
                    phenotype = pmap.get("phenotype", "")

                    if mim and phenotype:
                        results.append({
                            "mim_number": mim,
                            "title": phenotype,
                            "genes": [gm.get("geneSymbols", "")],
                            "url": f"https://omim.org/entry/{mim}",
                            "source": "OMIM",
                        })

            return results[:limit]

        except Exception as e:
            logger.debug(f"OMIM fallback search failed for '{query}': {e}")
            return []

