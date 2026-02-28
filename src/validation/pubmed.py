"""
Clinical Intelligence Hub — Pass 5: PubMed Literature Search

Uses NCBI E-utilities (free public API) to search PubMed for
clinical evidence supporting AI-detected findings.

API: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
Free tier: 3 requests/second without API key, 10/sec with key.
"""

import json
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional

from src.models import LiteratureCitation

logger = logging.getLogger("CIH-PubMed")

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedClient:
    """NCBI PubMed literature search via E-utilities."""

    def __init__(self, api_key: str = None, email: str = None):
        """
        Args:
            api_key: Optional NCBI API key (increases rate limit to 10/sec)
            email: Required by NCBI for usage tracking
        """
        self._api_key = api_key
        self._email = email or "clinicalintelligencehub@example.com"

    def search(self, query: str, max_results: int = 10) -> list[LiteratureCitation]:
        """
        Search PubMed for articles matching a clinical query.

        Prioritizes: systematic reviews, meta-analyses, clinical trials.
        """
        try:
            # Search for article IDs
            pmids = self._esearch(query, max_results)
            if not pmids:
                return []

            # Fetch article details
            articles = self._efetch(pmids)
            return articles

        except Exception as e:
            logger.error(f"PubMed search failed for '{query[:50]}...': {e}")
            return []

    def search_drug_evidence(self, drug_name: str,
                             condition: str = None) -> list[LiteratureCitation]:
        """Search for evidence about a drug, optionally for a specific condition."""
        query_parts = [f"{drug_name}[MeSH Terms]"]
        if condition:
            query_parts.append(f"{condition}[MeSH Terms]")

        # Prioritize high-quality evidence
        query_parts.append(
            "(systematic review[pt] OR meta-analysis[pt] OR "
            "randomized controlled trial[pt] OR clinical trial[pt])"
        )

        query = " AND ".join(query_parts)
        return self.search(query, max_results=5)

    def search_interaction(self, drug_a: str, drug_b: str) -> list[LiteratureCitation]:
        """Search for drug interaction evidence."""
        query = (
            f'("{drug_a}"[MeSH Terms] AND "{drug_b}"[MeSH Terms] '
            f'AND "drug interactions"[MeSH Terms])'
        )
        return self.search(query, max_results=5)

    def search_cross_disciplinary(self, condition: str,
                                   specialty: str) -> list[LiteratureCitation]:
        """Search for cross-disciplinary connections."""
        query = f'"{condition}" AND "{specialty}" AND (review[pt] OR meta-analysis[pt])'
        return self.search(query, max_results=5)

    # ── E-utilities API ─────────────────────────────────────

    def _esearch(self, query: str, max_results: int) -> list[str]:
        """Search PubMed and return PMIDs."""
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": str(max_results),
            "sort": "relevance",
            "retmode": "json",
            "email": self._email,
        }
        if self._api_key:
            params["api_key"] = self._api_key

        url = f"{EUTILS_BASE}/esearch.fcgi?{urllib.parse.urlencode(params)}"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ClinicalIntelligenceHub/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())

            return data.get("esearchresult", {}).get("idlist", [])

        except Exception as e:
            logger.error(f"PubMed esearch failed: {e}")
            return []

    def _efetch(self, pmids: list[str]) -> list[LiteratureCitation]:
        """Fetch article details for a list of PMIDs."""
        if not pmids:
            return []

        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "email": self._email,
        }
        if self._api_key:
            params["api_key"] = self._api_key

        url = f"{EUTILS_BASE}/efetch.fcgi?{urllib.parse.urlencode(params)}"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ClinicalIntelligenceHub/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                xml_data = response.read().decode()

            return self._parse_pubmed_xml(xml_data)

        except Exception as e:
            logger.error(f"PubMed efetch failed: {e}")
            return []

    def _parse_pubmed_xml(self, xml_data: str) -> list[LiteratureCitation]:
        """Parse PubMed XML response into LiteratureCitation models."""
        citations = []

        try:
            root = ET.fromstring(xml_data)

            for article in root.findall(".//PubmedArticle"):
                try:
                    citation = article.find(".//MedlineCitation")
                    if citation is None:
                        continue

                    pmid_elem = citation.find("PMID")
                    pmid = pmid_elem.text if pmid_elem is not None else None

                    article_elem = citation.find("Article")
                    if article_elem is None:
                        continue

                    # Title
                    title_elem = article_elem.find("ArticleTitle")
                    title = self._get_element_text(title_elem) or "Untitled"

                    # Authors
                    author_list = article_elem.find("AuthorList")
                    authors = self._parse_authors(author_list)

                    # Journal
                    journal_elem = article_elem.find("Journal/Title")
                    journal = journal_elem.text if journal_elem is not None else None

                    # Year
                    year = None
                    pub_date = article_elem.find("Journal/JournalIssue/PubDate")
                    if pub_date is not None:
                        year_elem = pub_date.find("Year")
                        if year_elem is not None:
                            try:
                                year = int(year_elem.text)
                            except (ValueError, TypeError):
                                pass

                    # DOI
                    doi = None
                    for id_elem in article_elem.findall("ELocationID"):
                        if id_elem.get("EIdType") == "doi":
                            doi = id_elem.text

                    citations.append(LiteratureCitation(
                        title=title,
                        authors=authors,
                        journal=journal,
                        year=year,
                        doi=doi,
                        pubmed_id=pmid,
                    ))

                except Exception as e:
                    logger.debug(f"Failed to parse article: {e}")
                    continue

        except ET.ParseError as e:
            logger.error(f"PubMed XML parse error: {e}")

        return citations

    @staticmethod
    def _parse_authors(author_list) -> Optional[str]:
        """Parse author list into 'First Author et al.' format."""
        if author_list is None:
            return None

        authors = author_list.findall("Author")
        if not authors:
            return None

        first = authors[0]
        last_name = first.find("LastName")
        initials = first.find("Initials")

        if last_name is not None:
            name = last_name.text
            if initials is not None:
                name += f" {initials.text}"
            if len(authors) > 1:
                name += " et al."
            return name

        return None

    @staticmethod
    def _get_element_text(elem) -> Optional[str]:
        """Get text content of an XML element, including nested elements."""
        if elem is None:
            return None
        # ElementTree .text may miss nested tags, use itertext
        return "".join(elem.itertext()).strip() or None
