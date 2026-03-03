"""
Clinical Intelligence Hub — PubChem (NCBI) Chemical/Drug Validation

Queries NCBI PubChem — the world's largest open chemical database with
116M+ compounds, 308M+ substances, and 1.5M+ bioassays. PubChem provides
molecular-level drug intelligence that no other free database matches:

  - Mechanisms of action (how a drug works at the molecular level)
  - Molecular targets (what proteins/receptors/enzymes a drug binds to)
  - Biological pathways (KEGG, Reactome pathway associations)
  - Pharmacology data (ADME — absorption, distribution, metabolism, excretion)
  - Drug interactions (pharmacological basis for interactions)
  - Synonyms and brand-name mappings

Answers the question: "What does this drug actually do?"

API: PUG REST (Power User Gateway)
Docs: https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
Free public API — no API key required. Rate limit: 5 requests/second.
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-PubChem")

PUG_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUG_VIEW = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"


class PubChemClient:
    """NCBI PubChem API client for drug mechanisms, targets, and pharmacology."""

    def search_compound(self, name: str, limit: int = 5) -> list[dict]:
        """
        Search PubChem for compounds matching a drug/chemical name.

        Returns basic compound info: CID, name, molecular formula,
        molecular weight, and IUPAC name.

        Args:
            name: Drug or chemical name (e.g., "metformin", "aspirin")
            limit: Max number of results to return
        """
        try:
            # Step 1: Resolve name to CID(s)
            encoded_name = urllib.parse.quote(name, safe="")
            url = f"{PUG_BASE}/compound/name/{encoded_name}/cids/JSON"

            data = api_get(url)
            if not data:
                return []

            cids = data.get("IdentifierList", {}).get("CID", [])
            if not cids:
                return []

            cids = cids[:limit]

            # Step 2: Get properties for each CID
            cid_list = ",".join(str(c) for c in cids)
            props_url = (
                f"{PUG_BASE}/compound/cid/{cid_list}/property/"
                f"MolecularFormula,MolecularWeight,IUPACName,IsomericSMILES/JSON"
            )

            props_data = api_get(props_url)
            if not props_data:
                # Return bare CIDs if property fetch fails
                return [
                    {
                        "cid": cid,
                        "name": name,
                        "source": "PubChem (NCBI)",
                    }
                    for cid in cids
                ]

            properties = props_data.get("PropertyTable", {}).get("Properties", [])

            results = []
            for prop in properties:
                results.append({
                    "cid": prop.get("CID"),
                    "name": name,
                    "molecular_formula": prop.get("MolecularFormula"),
                    "molecular_weight": prop.get("MolecularWeight"),
                    "iupac_name": prop.get("IUPACName"),
                    "source": "PubChem (NCBI)",
                })

            return results

        except Exception as e:
            logger.debug(f"PubChem compound search failed for '{name}': {e}")
            return []

    def get_compound(self, cid: int) -> Optional[dict]:
        """
        Get full compound details by PubChem CID.

        Args:
            cid: PubChem Compound ID
        """
        url = (
            f"{PUG_BASE}/compound/cid/{cid}/property/"
            f"MolecularFormula,MolecularWeight,IUPACName,CanonicalSMILES/JSON"
        )

        try:
            data = api_get(url)
            if not data:
                return None

            properties = data.get("PropertyTable", {}).get("Properties", [])
            if not properties:
                return None

            prop = properties[0]
            return {
                "cid": prop.get("CID"),
                "molecular_formula": prop.get("MolecularFormula"),
                "molecular_weight": prop.get("MolecularWeight"),
                "iupac_name": prop.get("IUPACName"),
                "canonical_smiles": prop.get("CanonicalSMILES"),
                "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                "source": "PubChem (NCBI)",
            }

        except Exception as e:
            logger.debug(f"PubChem compound lookup failed for CID {cid}: {e}")
            return None

    def get_drug_mechanism(self, drug_name: str) -> Optional[dict]:
        """
        Get the mechanism of action for a drug.

        Uses PUG View to fetch the 'Mechanism of Action' section
        from the compound's full record. This tells you HOW the drug
        works at a molecular level (e.g., "selective serotonin reuptake
        inhibitor" or "competitive antagonist at angiotensin II receptors").

        Args:
            drug_name: Drug name (brand or generic)
        """
        try:
            cid = self._resolve_name_to_cid(drug_name)
            if not cid:
                return None

            url = (
                f"{PUG_VIEW}/data/compound/{cid}/JSON"
                f"?heading=Mechanism+of+Action"
            )

            data = api_get(url, timeout=20)
            if not data:
                return None

            mechanism_text = self._extract_pug_view_text(data)
            if not mechanism_text:
                return None

            return {
                "drug_name": drug_name,
                "cid": cid,
                "mechanism_of_action": mechanism_text,
                "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                "source": "PubChem (NCBI)",
            }

        except Exception as e:
            logger.debug(
                f"PubChem mechanism of action lookup failed for '{drug_name}': {e}"
            )
            return None

    def get_pharmacology(self, drug_name: str) -> Optional[dict]:
        """
        Get pharmacology data for a drug (ADME profile).

        Returns absorption, distribution, metabolism, and excretion
        information — critical for understanding drug behavior in the body,
        dose adjustments, and interaction mechanisms.

        Args:
            drug_name: Drug name (brand or generic)
        """
        try:
            cid = self._resolve_name_to_cid(drug_name)
            if not cid:
                return None

            url = (
                f"{PUG_VIEW}/data/compound/{cid}/JSON"
                f"?heading=Pharmacology"
            )

            data = api_get(url, timeout=20)
            if not data:
                return None

            pharmacology_text = self._extract_pug_view_text(data)
            if not pharmacology_text:
                return None

            return {
                "drug_name": drug_name,
                "cid": cid,
                "pharmacology": pharmacology_text,
                "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                "source": "PubChem (NCBI)",
            }

        except Exception as e:
            logger.debug(
                f"PubChem pharmacology lookup failed for '{drug_name}': {e}"
            )
            return None

    def get_drug_targets(self, drug_name: str) -> list[dict]:
        """
        Get molecular targets for a drug from PubChem BioAssay data.

        Parses bioassay summaries to find what proteins, receptors,
        or enzymes a drug interacts with (e.g., "COX-2", "HMG-CoA reductase").

        Args:
            drug_name: Drug name (brand or generic)
        """
        try:
            encoded_name = urllib.parse.quote(drug_name, safe="")
            url = f"{PUG_BASE}/compound/name/{encoded_name}/assaysummary/JSON"

            data = api_get(url, timeout=20)
            if not data:
                return []

            columns = data.get("Table", {}).get("Columns", {}).get("Column", [])
            rows = data.get("Table", {}).get("Row", [])

            if not columns or not rows:
                return []

            # Build column index for field lookup
            col_index = {col: i for i, col in enumerate(columns)}

            target_name_idx = col_index.get("Target Name")
            target_type_idx = col_index.get("Target Type")
            outcome_idx = col_index.get("Activity Outcome")

            if target_name_idx is None:
                return []

            # Collect unique targets
            seen_targets = set()
            targets = []

            for row in rows:
                cells = row.get("Cell", [])
                if not cells:
                    continue

                target_name = (
                    cells[target_name_idx] if target_name_idx < len(cells)
                    else None
                )
                if not target_name or target_name in seen_targets:
                    continue

                target_type = (
                    cells[target_type_idx] if target_type_idx is not None
                    and target_type_idx < len(cells)
                    else None
                )

                activity_outcome = (
                    cells[outcome_idx] if outcome_idx is not None
                    and outcome_idx < len(cells)
                    else None
                )

                seen_targets.add(target_name)
                targets.append({
                    "target_name": target_name,
                    "target_type": target_type,
                    "activity_outcome": activity_outcome,
                    "source": "PubChem (NCBI)",
                })

            return targets

        except Exception as e:
            logger.debug(
                f"PubChem drug targets lookup failed for '{drug_name}': {e}"
            )
            return []

    def get_drug_interactions_pharmacology(
        self, drug_name: str
    ) -> Optional[dict]:
        """
        Get drug interaction information from PubChem compound view.

        This provides the pharmacological basis for drug interactions —
        which enzymes are inhibited/induced, which transporters are affected.
        Complements RxNorm's clinical interaction data with mechanism details.

        Args:
            drug_name: Drug name (brand or generic)
        """
        try:
            cid = self._resolve_name_to_cid(drug_name)
            if not cid:
                return None

            url = (
                f"{PUG_VIEW}/data/compound/{cid}/JSON"
                f"?heading=Drug+Interactions"
            )

            data = api_get(url, timeout=20)
            if not data:
                return None

            interaction_text = self._extract_pug_view_text(data)
            if not interaction_text:
                return None

            return {
                "drug_name": drug_name,
                "cid": cid,
                "drug_interactions": interaction_text,
                "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                "source": "PubChem (NCBI)",
            }

        except Exception as e:
            logger.debug(
                f"PubChem drug interactions lookup failed for '{drug_name}': {e}"
            )
            return None

    def get_synonyms(self, drug_name: str) -> list[str]:
        """
        Get alternative names and brand names for a drug.

        PubChem maintains extensive synonym lists including brand names,
        IUPAC names, registry numbers, and international trade names.
        Useful for cross-referencing across databases that use different
        naming conventions.

        Args:
            drug_name: Drug name (brand or generic)
        """
        try:
            encoded_name = urllib.parse.quote(drug_name, safe="")
            url = f"{PUG_BASE}/compound/name/{encoded_name}/synonyms/JSON"

            data = api_get(url)
            if not data:
                return []

            info_list = (
                data.get("InformationList", {}).get("Information", [])
            )
            if not info_list:
                return []

            # First entry contains the synonym list for the resolved compound
            synonyms = info_list[0].get("Synonym", [])
            return synonyms

        except Exception as e:
            logger.debug(
                f"PubChem synonym lookup failed for '{drug_name}': {e}"
            )
            return []

    # ── Helpers ──────────────────────────────────────────────

    def _resolve_name_to_cid(self, name: str) -> Optional[int]:
        """
        Resolve a drug/chemical name to a PubChem Compound ID (CID).

        Handles brand names, generic names, and common abbreviations.
        Returns the first (most relevant) CID match, or None.
        """
        try:
            encoded_name = urllib.parse.quote(name, safe="")
            url = f"{PUG_BASE}/compound/name/{encoded_name}/cids/JSON"

            data = api_get(url)
            if not data:
                return None

            cids = data.get("IdentifierList", {}).get("CID", [])
            return cids[0] if cids else None

        except Exception as e:
            logger.debug(f"PubChem CID resolution failed for '{name}': {e}")
            return None

    @staticmethod
    def _extract_pug_view_text(data: dict) -> Optional[str]:
        """
        Extract text content from a PUG View JSON response.

        PUG View responses have deeply nested structures:
            Record
              -> Section[]
                -> Section[]
                  -> Information[]
                    -> Value
                      -> StringWithMarkup[]
                        -> String

        This method walks the tree and collects all text fragments,
        joining them into a single readable string.
        """
        if not data:
            return None

        try:
            record = data.get("Record", {})
            sections = record.get("Section", [])

            text_parts = []
            PubChemClient._walk_sections(sections, text_parts)

            if not text_parts:
                return None

            return "\n\n".join(text_parts)

        except Exception:
            return None

    @staticmethod
    def _walk_sections(sections: list, text_parts: list) -> None:
        """
        Recursively walk PUG View sections to extract text.

        Sections can be nested arbitrarily deep. Each section may
        contain an Information array with StringWithMarkup values.
        """
        for section in sections:
            # Check for nested subsections
            subsections = section.get("Section", [])
            if subsections:
                PubChemClient._walk_sections(subsections, text_parts)

            # Extract text from Information entries
            for info in section.get("Information", []):
                value = info.get("Value", {})

                # StringWithMarkup is the most common text container
                markup_list = value.get("StringWithMarkup", [])
                for markup in markup_list:
                    text = markup.get("String", "")
                    if text and text.strip():
                        text_parts.append(text.strip())

                # Some entries use plain Number or Boolean values
                if not markup_list:
                    num = value.get("Number")
                    if num is not None:
                        text_parts.append(str(num))
