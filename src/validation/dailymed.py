"""
Clinical Intelligence Hub — DailyMed Drug Label Validation

DailyMed is a service provided by the National Library of Medicine (NLM)
that makes available FDA-approved drug labels (package inserts) with full
prescribing information. Labels include indications, dosage, warnings,
contraindications, drug interactions, and adverse reactions — the same
information a pharmacist or physician would reference.

API: https://dailymed.nlm.nih.gov/dailymed/services/v2/
     (free, public, no key required)

Note: The /spls search endpoint returns JSON, but individual SPL documents
(/spls/{SETID}) return XML only (HL7 v3 Structured Product Labeling format).
This client parses the XML to extract labeling sections by LOINC code.
"""

import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-DailyMed")

BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"

# HL7 v3 namespace used in SPL XML documents
HL7_NS = "{urn:hl7-org:v3}"

# LOINC codes for standard drug label sections
LOINC_SECTIONS = {
    "drug_interactions": "34073-7",
    "contraindications": "34070-3",
    "warnings_and_precautions": "43685-7",
    "warnings": "34071-1",
    "boxed_warning": "34066-1",
    "dosage_and_administration": "34068-7",
    "adverse_reactions": "34084-4",
    "indications_and_usage": "34067-9",
    "clinical_pharmacology": "34090-1",
    "overdosage": "34088-5",
    "description": "34089-3",
}


class DailyMedClient:
    """NLM DailyMed API client for FDA-approved drug labels and prescribing information."""

    def search(self, drug_name: str, limit: int = 10) -> list[dict]:
        """
        Search DailyMed for drug labels (SPLs) by drug name.

        Args:
            drug_name: Generic or brand name of the drug.
            limit: Maximum number of results to return (max 100).

        Returns:
            List of matching SPL entries with setid, title, and published_date.
        """
        safe_name = urllib.parse.quote(drug_name, safe="")
        page_size = min(limit, 100)
        url = f"{BASE_URL}/spls.json?drug_name={safe_name}&pagesize={page_size}"

        try:
            data = api_get(url)
            if not data:
                return []

            results_list = data.get("data", [])
            if not isinstance(results_list, list):
                return []

            results = []
            for entry in results_list[:limit]:
                if not isinstance(entry, dict):
                    continue

                setid = entry.get("setid", "")
                title = entry.get("title", "")
                if not setid:
                    continue

                results.append({
                    "setid": setid,
                    "title": title,
                    "published_date": entry.get("published_date", ""),
                    "spl_version": entry.get("spl_version"),
                    "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}",
                    "source": "DailyMed (NLM)",
                })

            return results

        except Exception as e:
            logger.debug(f"DailyMed search failed for '{drug_name}': {e}")
            return []

    def get_label(self, set_id: str) -> Optional[dict]:
        """
        Fetch the full drug label (SPL) for a given SET ID.

        The DailyMed individual SPL endpoint returns XML only (HL7 v3 format).
        This method fetches the XML, parses it, and extracts all labeled
        sections into a dict keyed by section name.

        Args:
            set_id: The SPL SET ID (UUID format).

        Returns:
            Dict with title, sections dict, and metadata, or None on failure.
        """
        url = f"{BASE_URL}/spls/{urllib.parse.quote(set_id, safe='')}.xml"

        try:
            xml_text = self._fetch_xml(url)
            if not xml_text:
                return None

            root = ET.fromstring(xml_text)

            # Extract title
            title_el = root.find(f"{HL7_NS}title")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""

            # Extract effective date
            eff_time = root.find(f"{HL7_NS}effectiveTime")
            effective_date = ""
            if eff_time is not None:
                effective_date = eff_time.get("value", "")

            # Extract all sections by LOINC code
            sections = {}
            all_section_elements = root.iter(f"{HL7_NS}section")
            for section_el in all_section_elements:
                code_el = section_el.find(f"{HL7_NS}code")
                if code_el is None:
                    continue

                loinc_code = code_el.get("code", "")
                section_name = self._loinc_to_name(loinc_code)
                if not section_name:
                    # Use the displayName attribute as fallback
                    display = code_el.get("displayName", "")
                    if display:
                        section_name = display.lower().replace(" ", "_").replace("&", "and")
                    else:
                        continue

                # Extract section title
                sec_title_el = section_el.find(f"{HL7_NS}title")
                sec_title = ""
                if sec_title_el is not None and sec_title_el.text:
                    sec_title = sec_title_el.text.strip()

                # Extract text content
                text_el = section_el.find(f"{HL7_NS}text")
                text_content = self._extract_text(text_el) if text_el is not None else ""

                if text_content or sec_title:
                    sections[section_name] = {
                        "title": sec_title,
                        "text": text_content,
                        "loinc_code": loinc_code,
                    }

            return {
                "set_id": set_id,
                "title": title,
                "effective_date": effective_date,
                "sections": sections,
                "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}",
                "source": "DailyMed (NLM)",
            }

        except ET.ParseError as e:
            logger.debug(f"DailyMed XML parse error for {set_id}: {e}")
            return None
        except Exception as e:
            logger.debug(f"DailyMed label fetch failed for {set_id}: {e}")
            return None

    def get_drug_interactions(self, drug_name: str) -> Optional[dict]:
        """
        Get drug interaction information from the FDA label.

        Searches for the drug, fetches the first matching label,
        and extracts the drug_interactions section.

        Args:
            drug_name: Generic or brand name of the drug.

        Returns:
            Dict with drug name, interaction text, and source, or None.
        """
        return self._get_section_for_drug(
            drug_name,
            section_keys=["drug_interactions"],
            result_key="interactions",
        )

    def get_contraindications(self, drug_name: str) -> Optional[dict]:
        """
        Get contraindication information from the FDA label.

        Args:
            drug_name: Generic or brand name of the drug.

        Returns:
            Dict with drug name, contraindication text, and source, or None.
        """
        return self._get_section_for_drug(
            drug_name,
            section_keys=["contraindications"],
            result_key="contraindications",
        )

    def get_warnings(self, drug_name: str) -> Optional[dict]:
        """
        Get warnings and precautions from the FDA label.

        Looks for warnings_and_precautions first, then falls back to
        boxed_warning if available.

        Args:
            drug_name: Generic or brand name of the drug.

        Returns:
            Dict with drug name, warning text, boxed warning (if any),
            and source, or None.
        """
        label = self._get_label_for_drug(drug_name)
        if not label:
            return None

        sections = label.get("sections", {})

        # Try warnings_and_precautions, then generic warnings
        warnings_text = ""
        for key in ("warnings_and_precautions", "warnings"):
            section = sections.get(key)
            if isinstance(section, dict) and section.get("text"):
                warnings_text = section["text"]
                break

        # Also check for boxed warning (the most severe FDA warning)
        boxed_text = ""
        boxed_section = sections.get("boxed_warning")
        if isinstance(boxed_section, dict) and boxed_section.get("text"):
            boxed_text = boxed_section["text"]

        if not warnings_text and not boxed_text:
            return None

        result = {
            "drug_name": drug_name,
            "set_id": label.get("set_id", ""),
            "title": label.get("title", ""),
            "source": "DailyMed (NLM)",
        }

        if warnings_text:
            result["warnings"] = warnings_text
        if boxed_text:
            result["boxed_warning"] = boxed_text
            result["has_boxed_warning"] = True

        return result

    def get_dosing(self, drug_name: str) -> Optional[dict]:
        """
        Get dosage and administration information from the FDA label.

        Args:
            drug_name: Generic or brand name of the drug.

        Returns:
            Dict with drug name, dosing text, and source, or None.
        """
        return self._get_section_for_drug(
            drug_name,
            section_keys=["dosage_and_administration"],
            result_key="dosing",
        )

    # ── Internal Helpers ─────────────────────────────────────

    def _get_label_for_drug(self, drug_name: str) -> Optional[dict]:
        """
        Search for a drug and fetch the first matching label.

        Returns the parsed label dict, or None if not found.
        """
        results = self.search(drug_name, limit=3)
        if not results:
            logger.debug(f"DailyMed: No search results for '{drug_name}'")
            return None

        # Use the first result's setid
        set_id = results[0].get("setid", "")
        if not set_id:
            return None

        return self.get_label(set_id)

    def _get_section_for_drug(
        self,
        drug_name: str,
        section_keys: list[str],
        result_key: str,
    ) -> Optional[dict]:
        """
        Generic helper: search for a drug, fetch its label, extract a section.

        Tries each key in section_keys until one is found.

        Args:
            drug_name: Drug name to search for.
            section_keys: Ordered list of section keys to try.
            result_key: Key name for the section text in the returned dict.

        Returns:
            Dict with drug_name, section text, and source, or None.
        """
        label = self._get_label_for_drug(drug_name)
        if not label:
            return None

        sections = label.get("sections", {})

        section_text = ""
        for key in section_keys:
            section = sections.get(key)
            if isinstance(section, dict) and section.get("text"):
                section_text = section["text"]
                break

        if not section_text:
            return None

        return {
            "drug_name": drug_name,
            "set_id": label.get("set_id", ""),
            "title": label.get("title", ""),
            result_key: section_text,
            "source": "DailyMed (NLM)",
        }

    def _fetch_xml(self, url: str) -> Optional[str]:
        """
        Fetch raw XML text from a URL.

        The individual SPL endpoint returns XML, not JSON, so we
        bypass api_get and use the same SSL/timeout/User-Agent
        pattern directly.
        """
        import ssl
        import urllib.request

        try:
            from src.validation._http import get_ssl_context, USER_AGENT, DEFAULT_TIMEOUT
        except ImportError:
            # Fallback if _http internals aren't importable
            USER_AGENT = "Mozilla/5.0 (compatible; ClinicalIntelligenceHub/1.0; +health)"
            DEFAULT_TIMEOUT = 15

            def get_ssl_context():
                try:
                    import certifi
                    return ssl.create_default_context(cafile=certifi.where())
                except ImportError:
                    return ssl.create_default_context()

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/xml",
                },
            )
            ctx = get_ssl_context()

            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT, context=ctx) as response:
                return response.read().decode("utf-8")

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            logger.debug(f"DailyMed XML HTTP {e.code} for {url[:80]}: {e.reason}")
            return None
        except Exception as e:
            logger.debug(f"DailyMed XML fetch failed for {url[:80]}: {e}")
            return None

    @staticmethod
    def _loinc_to_name(loinc_code: str) -> Optional[str]:
        """Map a LOINC code to a human-readable section name."""
        for name, code in LOINC_SECTIONS.items():
            if code == loinc_code:
                return name
        return None

    @staticmethod
    def _extract_text(element) -> str:
        """
        Recursively extract all text content from an XML element.

        Handles paragraphs, lists, tables, and other nested HL7 v3
        text elements, joining them with newlines.
        """
        if element is None:
            return ""

        parts = []

        # Direct text on this element
        if element.text and element.text.strip():
            parts.append(element.text.strip())

        # Recurse into children
        for child in element:
            # Strip namespace prefix for tag comparison
            tag = child.tag.replace(HL7_NS, "") if isinstance(child.tag, str) else ""

            if tag in ("paragraph", "content", "caption"):
                child_text = DailyMedClient._extract_text(child)
                if child_text:
                    parts.append(child_text)

            elif tag == "list":
                for item in child.findall(f"{HL7_NS}item"):
                    item_text = DailyMedClient._extract_text(item)
                    if item_text:
                        parts.append(f"- {item_text}")

            elif tag == "table":
                # Extract table rows as simple text
                for row in child.iter(f"{HL7_NS}tr"):
                    cells = []
                    for cell in row:
                        cell_text = DailyMedClient._extract_text(cell)
                        if cell_text:
                            cells.append(cell_text)
                    if cells:
                        parts.append(" | ".join(cells))

            elif tag in ("br", "br/"):
                parts.append("")

            else:
                # Generic fallback: extract text from unknown elements
                child_text = DailyMedClient._extract_text(child)
                if child_text:
                    parts.append(child_text)

            # Tail text (text after a child element but before next sibling)
            if child.tail and child.tail.strip():
                parts.append(child.tail.strip())

        return "\n".join(parts)
