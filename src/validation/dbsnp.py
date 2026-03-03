"""
Clinical Intelligence Hub — dbSNP (NCBI)

dbSNP (Database of Single Nucleotide Polymorphisms) is NCBI's primary public
repository for simple genetic polymorphisms. It catalogues:

- Single nucleotide polymorphisms (SNPs) — single base-pair changes
- Small insertions and deletions (indels)
- Microsatellite repeats and other short variants

Each variant is assigned a stable "rs" identifier (e.g., rs1234) that serves
as a universal reference across the genomics community. dbSNP aggregates
submissions from sequencing projects worldwide and links to:

- Population allele frequencies (1000 Genomes, gnomAD, TOPMED, etc.)
- ClinVar clinical significance annotations
- Gene and transcript context (chromosome, position, consequence)

dbSNP is critical for interpreting genetic testing results and understanding
variant frequency. When a patient's genetic test reports a variant, the rs
number is the key to looking up everything known about it — how common it is
across populations, whether it has clinical significance, and what gene or
protein it affects.

API: NCBI E-utilities + Variation Services
E-utilities base: https://eutils.ncbi.nlm.nih.gov/entrez/eutils
Variation services: https://api.ncbi.nlm.nih.gov/variation/v0
Rate limits: 3 req/sec without API key, 10 req/sec with key.
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-dbSNP")

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
VARIATION_BASE = "https://api.ncbi.nlm.nih.gov/variation/v0"

# Maximum variants for batch_lookup to avoid overloading the API
BATCH_LIMIT = 10


class dbSNPClient:
    """NCBI dbSNP client for genetic variant lookup and frequency data."""

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: Optional NCBI API key (increases rate limit
                     from 3/sec to 10/sec). Register free at
                     https://www.ncbi.nlm.nih.gov/account/
        """
        self._api_key = api_key

    # -- Public methods -----------------------------------------------

    def get_variant(self, rs_id: str) -> Optional[dict]:
        """
        Get full details for a variant by its rs identifier.

        Accepts "rs1234", "RS1234", or just "1234".

        Returns variant summary including type, gene, chromosome,
        position, alleles, clinical significance, and global minor
        allele frequency, or None if not found.
        """
        rs_number = self._clean_rs_id(rs_id)
        if not rs_number:
            logger.debug(f"Invalid rs ID: {rs_id}")
            return None

        url = f"{VARIATION_BASE}/refsnp/{rs_number}"
        if self._api_key:
            url += f"?api_key={urllib.parse.quote(self._api_key)}"

        try:
            data = api_get(url, timeout=20)
            if not data:
                return None

            return self._parse_variant(rs_number, data)

        except Exception as e:
            logger.debug(f"dbSNP get_variant failed for rs{rs_number}: {e}")
            return None

    def search_gene(self, gene_symbol: str, limit: int = 20) -> list[dict]:
        """
        Search dbSNP for variants in a gene.

        Uses NCBI E-utilities esearch against the SNP database with
        a gene symbol filter.

        Returns a list of rs IDs found in the gene. Does NOT fetch
        full details for each variant (that would be too slow for
        large gene result sets — use get_variant individually).
        """
        if not gene_symbol or not gene_symbol.strip():
            return []

        gene_clean = gene_symbol.strip()
        url = self._build_eutils_url(
            "/esearch.fcgi",
            {
                "db": "snp",
                "term": f"{gene_clean}[gene]",
                "retmax": str(min(limit, 500)),
                "retmode": "json",
            },
        )

        try:
            data = api_get(url)
            if not data:
                return []

            id_list = data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                return []

            results = []
            for snp_id in id_list:
                results.append({
                    "rs_id": f"rs{snp_id}",
                    "gene": gene_clean,
                    "url": f"https://www.ncbi.nlm.nih.gov/snp/rs{snp_id}",
                    "source": "dbSNP (NCBI)",
                })

            return results

        except Exception as e:
            logger.debug(
                f"dbSNP search_gene failed for '{gene_symbol}': {e}"
            )
            return []

    def get_frequency(self, rs_id: str) -> Optional[dict]:
        """
        Get allele frequency data for a variant across populations.

        Returns frequency breakdowns for global, European, African,
        East Asian, South Asian, and other populations where available.
        """
        rs_number = self._clean_rs_id(rs_id)
        if not rs_number:
            logger.debug(f"Invalid rs ID for frequency lookup: {rs_id}")
            return None

        url = f"{VARIATION_BASE}/refsnp/{rs_number}"
        if self._api_key:
            url += f"?api_key={urllib.parse.quote(self._api_key)}"

        try:
            data = api_get(url, timeout=20)
            if not data:
                return None

            return self._parse_frequency(rs_number, data)

        except Exception as e:
            logger.debug(f"dbSNP get_frequency failed for rs{rs_number}: {e}")
            return None

    def get_clinical_significance(self, rs_id: str) -> Optional[dict]:
        """
        Get ClinVar clinical significance annotations for a variant.

        Extracts any clinical significance classifications and
        associated conditions linked from the dbSNP variant record.

        Returns None if the variant has no clinical annotations.
        """
        rs_number = self._clean_rs_id(rs_id)
        if not rs_number:
            logger.debug(
                f"Invalid rs ID for clinical significance: {rs_id}"
            )
            return None

        url = f"{VARIATION_BASE}/refsnp/{rs_number}"
        if self._api_key:
            url += f"?api_key={urllib.parse.quote(self._api_key)}"

        try:
            data = api_get(url, timeout=20)
            if not data:
                return None

            return self._parse_clinical_significance(rs_number, data)

        except Exception as e:
            logger.debug(
                f"dbSNP get_clinical_significance failed for "
                f"rs{rs_number}: {e}"
            )
            return None

    def batch_lookup(self, rs_ids: list[str]) -> list[dict]:
        """
        Look up multiple variants and return summaries for each.

        Limits to the first 10 IDs to avoid overloading the API.
        Skips any IDs that fail individually — partial results are
        returned rather than failing the entire batch.
        """
        if not rs_ids:
            return []

        # Cap at BATCH_LIMIT to be a good API citizen
        capped = rs_ids[:BATCH_LIMIT]

        results = []
        for rs_id in capped:
            variant = self.get_variant(rs_id)
            if variant:
                results.append(variant)

        return results

    # -- Input cleaning -----------------------------------------------

    @staticmethod
    def _clean_rs_id(rs_id: str) -> Optional[str]:
        """
        Normalize an rs identifier to just the numeric portion.

        Accepts "rs1234", "RS1234", "rs 1234", or plain "1234".
        Returns the numeric string, or None if input is invalid.
        """
        if not rs_id:
            return None

        cleaned = rs_id.strip().lower()

        # Strip "rs" prefix if present
        if cleaned.startswith("rs"):
            cleaned = cleaned[2:].strip()

        # Must be numeric after stripping prefix
        if not cleaned.isdigit():
            return None

        return cleaned

    # -- Response parsing (Variation Services API) --------------------

    def _parse_variant(self, rs_number: str, data: dict) -> Optional[dict]:
        """
        Parse the NCBI Variation Services refsnp response into a
        standardized variant summary.

        The response structure is deeply nested:
        - primary_snapshot_data.placements_with_allele — position info
        - primary_snapshot_data.allele_annotations — clinical data
        """
        try:
            snapshot = data.get("primary_snapshot_data", {})
            if not snapshot:
                return None

            # -- Variant type --
            variant_type = snapshot.get("variant_type", "")

            # -- Gene, chromosome, position from placements --
            gene_symbol = ""
            chromosome = ""
            position = None
            alleles = []

            placements = snapshot.get("placements_with_allele", [])
            for placement in placements:
                if not isinstance(placement, dict):
                    continue

                # Look for assembly placement (GRCh38 preferred)
                seq_id = placement.get("seq_id", "")
                is_ptlp = placement.get("is_ptlp", False)

                # Extract chromosome from placement_annot
                placement_annot = placement.get("placement_annot", {})
                if isinstance(placement_annot, dict):
                    seq_id_trait = placement_annot.get(
                        "seq_id_traits_by_assembly", []
                    )
                    if isinstance(seq_id_trait, list):
                        for trait in seq_id_trait:
                            if not isinstance(trait, dict):
                                continue
                            assembly = trait.get("assembly_name", "")
                            if "GRCh38" in assembly or "GRCh37" in assembly:
                                chromosome = trait.get("chr", "") or chromosome

                # Extract alleles from this placement
                placement_alleles = placement.get("alleles", [])
                for allele_entry in placement_alleles:
                    if not isinstance(allele_entry, dict):
                        continue

                    allele_info = allele_entry.get("allele", {})
                    if not isinstance(allele_info, dict):
                        continue

                    spdi = allele_info.get("spdi", {})
                    if isinstance(spdi, dict):
                        ins_seq = spdi.get("inserted_sequence", "")
                        del_seq = spdi.get("deleted_sequence", "")
                        seq_pos = spdi.get("position")

                        if ins_seq and ins_seq not in alleles:
                            alleles.append(ins_seq)
                        if del_seq and del_seq not in alleles:
                            alleles.append(del_seq)

                        # Use position from the first SPDI we find
                        if seq_pos is not None and position is None:
                            position = seq_pos

                    # Extract gene from assembly annotation on
                    # primary top-level placement
                    if is_ptlp:
                        hgvs = allele_entry.get("hgvs", "")
                        if isinstance(hgvs, str) and "(" in hgvs:
                            # Gene symbol often appears in parentheses
                            # in HGVS notation
                            start = hgvs.find("(")
                            end = hgvs.find(")")
                            if start != -1 and end != -1:
                                candidate = hgvs[start + 1 : end]
                                if candidate.isalpha():
                                    gene_symbol = gene_symbol or candidate

            # -- Gene from allele_annotations if not found above --
            allele_annotations = snapshot.get("allele_annotations", [])
            if not gene_symbol and allele_annotations:
                gene_symbol = self._extract_gene_from_annotations(
                    allele_annotations
                )

            # -- Clinical significance from allele_annotations --
            clinical_significance = self._extract_clinical_from_annotations(
                allele_annotations
            )

            # -- Global minor allele frequency --
            gmaf = self._extract_gmaf(allele_annotations)

            return {
                "rs_id": f"rs{rs_number}",
                "variant_type": variant_type or "unknown",
                "gene_symbol": gene_symbol or None,
                "chromosome": chromosome or None,
                "position": position,
                "alleles": alleles if alleles else None,
                "clinical_significance": clinical_significance or None,
                "global_minor_allele_frequency": gmaf,
                "url": f"https://www.ncbi.nlm.nih.gov/snp/rs{rs_number}",
                "source": "dbSNP (NCBI)",
            }

        except Exception as e:
            logger.debug(f"dbSNP parse failed for rs{rs_number}: {e}")
            return None

    def _parse_frequency(
        self, rs_number: str, data: dict
    ) -> Optional[dict]:
        """
        Extract population allele frequency data from a refsnp response.

        Frequency data lives in primary_snapshot_data.allele_annotations
        under frequency entries, broken down by study (1000 Genomes,
        TOPMED, gnomAD, etc.) and population.
        """
        try:
            snapshot = data.get("primary_snapshot_data", {})
            if not snapshot:
                return None

            allele_annotations = snapshot.get("allele_annotations", [])
            if not allele_annotations:
                return {
                    "rs_id": f"rs{rs_number}",
                    "alleles": [],
                    "populations": [],
                    "url": f"https://www.ncbi.nlm.nih.gov/snp/rs{rs_number}",
                    "source": "dbSNP (NCBI)",
                }

            # Collect frequency entries across annotation blocks
            frequency_entries = []
            observed_alleles = set()

            for annotation_block in allele_annotations:
                if not isinstance(annotation_block, dict):
                    continue

                freq_data = annotation_block.get("frequency", [])
                if not isinstance(freq_data, list):
                    continue

                for freq in freq_data:
                    if not isinstance(freq, dict):
                        continue

                    study = freq.get("study_name", "")
                    allele_count = freq.get("allele_count", 0)
                    total_count = freq.get("total_count", 0)
                    observation = freq.get("observation", {})

                    allele = ""
                    if isinstance(observation, dict):
                        allele = observation.get(
                            "inserted_sequence",
                            observation.get("deleted_sequence", ""),
                        )

                    if allele:
                        observed_alleles.add(allele)

                    frequency_val = None
                    if total_count and total_count > 0:
                        frequency_val = round(
                            allele_count / total_count, 6
                        )

                    frequency_entries.append({
                        "study": study,
                        "allele": allele,
                        "allele_count": allele_count,
                        "total_count": total_count,
                        "frequency": frequency_val,
                    })

            # Group by study for a cleaner output
            studies = {}
            for entry in frequency_entries:
                study = entry.get("study", "unknown")
                if study not in studies:
                    studies[study] = []
                studies[study].append({
                    "allele": entry["allele"],
                    "frequency": entry["frequency"],
                    "allele_count": entry["allele_count"],
                    "total_count": entry["total_count"],
                })

            return {
                "rs_id": f"rs{rs_number}",
                "alleles": sorted(observed_alleles),
                "populations": [
                    {"study": study, "frequencies": freqs}
                    for study, freqs in studies.items()
                ],
                "url": f"https://www.ncbi.nlm.nih.gov/snp/rs{rs_number}",
                "source": "dbSNP (NCBI)",
            }

        except Exception as e:
            logger.debug(
                f"dbSNP frequency parse failed for rs{rs_number}: {e}"
            )
            return None

    def _parse_clinical_significance(
        self, rs_number: str, data: dict
    ) -> Optional[dict]:
        """
        Extract ClinVar clinical significance from a refsnp response.

        Clinical data is nested under allele_annotations, within
        clinical entries that reference ClinVar submissions.
        """
        try:
            snapshot = data.get("primary_snapshot_data", {})
            if not snapshot:
                return None

            allele_annotations = snapshot.get("allele_annotations", [])

            clinical_significances = []
            associated_conditions = []
            review_statuses = set()

            for annotation_block in allele_annotations:
                if not isinstance(annotation_block, dict):
                    continue

                clinical_entries = annotation_block.get("clinical", [])
                if not isinstance(clinical_entries, list):
                    continue

                for clinical in clinical_entries:
                    if not isinstance(clinical, dict):
                        continue

                    # Clinical significance descriptions
                    sig_descriptions = clinical.get(
                        "clinical_significances", []
                    )
                    if isinstance(sig_descriptions, list):
                        for sig in sig_descriptions:
                            if sig and sig not in clinical_significances:
                                clinical_significances.append(sig)
                    elif isinstance(sig_descriptions, str):
                        if (
                            sig_descriptions
                            and sig_descriptions not in clinical_significances
                        ):
                            clinical_significances.append(sig_descriptions)

                    # Associated disease/condition names
                    disease_names = clinical.get("disease_names", [])
                    if isinstance(disease_names, list):
                        for name in disease_names:
                            if name and name not in associated_conditions:
                                associated_conditions.append(name)
                    elif isinstance(disease_names, str):
                        if (
                            disease_names
                            and disease_names not in associated_conditions
                        ):
                            associated_conditions.append(disease_names)

                    # Review status
                    review = clinical.get("review_status", "")
                    if review:
                        review_statuses.add(review)

                    # Also check nested accession info for conditions
                    accessions = clinical.get("accession_version", "")
                    citations = clinical.get("citations", [])

            if not clinical_significances:
                return {
                    "rs_id": f"rs{rs_number}",
                    "clinical_significances": [],
                    "associated_conditions": [],
                    "review_status": None,
                    "has_clinical_data": False,
                    "url": (
                        f"https://www.ncbi.nlm.nih.gov/snp/rs{rs_number}"
                    ),
                    "source": "dbSNP (NCBI)",
                }

            return {
                "rs_id": f"rs{rs_number}",
                "clinical_significances": clinical_significances,
                "associated_conditions": associated_conditions,
                "review_status": (
                    sorted(review_statuses)[0] if review_statuses else None
                ),
                "has_clinical_data": True,
                "url": f"https://www.ncbi.nlm.nih.gov/snp/rs{rs_number}",
                "source": "dbSNP (NCBI)",
            }

        except Exception as e:
            logger.debug(
                f"dbSNP clinical significance parse failed for "
                f"rs{rs_number}: {e}"
            )
            return None

    # -- Annotation extraction helpers --------------------------------

    @staticmethod
    def _extract_gene_from_annotations(
        allele_annotations: list,
    ) -> str:
        """
        Try to extract a gene symbol from allele_annotations.

        Gene info can appear in assembly_annotation or clinical
        entries within the annotations.
        """
        for annotation_block in allele_annotations:
            if not isinstance(annotation_block, dict):
                continue

            # Check assembly_annotation for gene references
            assembly_ann = annotation_block.get("assembly_annotation", [])
            if isinstance(assembly_ann, list):
                for ann in assembly_ann:
                    if not isinstance(ann, dict):
                        continue
                    genes = ann.get("genes", [])
                    if isinstance(genes, list):
                        for gene in genes:
                            if isinstance(gene, dict):
                                name = gene.get("name", "") or gene.get(
                                    "locus", ""
                                )
                                if name:
                                    return name

            # Check clinical entries for gene context
            clinical_entries = annotation_block.get("clinical", [])
            if isinstance(clinical_entries, list):
                for clinical in clinical_entries:
                    if not isinstance(clinical, dict):
                        continue
                    gene_names = clinical.get("gene_names", [])
                    if isinstance(gene_names, list) and gene_names:
                        return gene_names[0]
                    elif isinstance(gene_names, str) and gene_names:
                        return gene_names

        return ""

    @staticmethod
    def _extract_clinical_from_annotations(
        allele_annotations: list,
    ) -> list[str]:
        """
        Extract clinical significance values from allele_annotations.

        Returns a deduplicated list of significance strings
        (e.g., ["pathogenic", "likely pathogenic"]).
        """
        significances = []

        for annotation_block in allele_annotations:
            if not isinstance(annotation_block, dict):
                continue

            clinical_entries = annotation_block.get("clinical", [])
            if not isinstance(clinical_entries, list):
                continue

            for clinical in clinical_entries:
                if not isinstance(clinical, dict):
                    continue

                sigs = clinical.get("clinical_significances", [])
                if isinstance(sigs, list):
                    for sig in sigs:
                        if sig and sig not in significances:
                            significances.append(sig)
                elif isinstance(sigs, str) and sigs:
                    if sigs not in significances:
                        significances.append(sigs)

        return significances

    @staticmethod
    def _extract_gmaf(allele_annotations: list) -> Optional[float]:
        """
        Extract the global minor allele frequency (GMAF) from
        allele_annotations.

        Looks for a frequency entry from a major study (preferring
        1000 Genomes or TOPMED global data) and returns the minor
        allele frequency.
        """
        preferred_studies = [
            "1000Genomes",
            "TOPMED",
            "GnomAD",
            "gnomAD",
            "ExAC",
        ]

        best_freq = None
        best_priority = len(preferred_studies)  # worst priority

        for annotation_block in allele_annotations:
            if not isinstance(annotation_block, dict):
                continue

            freq_data = annotation_block.get("frequency", [])
            if not isinstance(freq_data, list):
                continue

            for freq in freq_data:
                if not isinstance(freq, dict):
                    continue

                study = freq.get("study_name", "")
                allele_count = freq.get("allele_count", 0)
                total_count = freq.get("total_count", 0)

                if not total_count or total_count <= 0:
                    continue

                frequency_val = allele_count / total_count

                # Minor allele frequency is the smaller of the two
                maf = min(frequency_val, 1.0 - frequency_val)

                # Determine study priority
                priority = len(preferred_studies)
                for i, pref in enumerate(preferred_studies):
                    if pref.lower() in study.lower():
                        priority = i
                        break

                if priority < best_priority:
                    best_priority = priority
                    best_freq = round(maf, 6)
                elif best_freq is None:
                    best_freq = round(maf, 6)

        return best_freq

    # -- URL builder (E-utilities) ------------------------------------

    def _build_eutils_url(self, endpoint: str, params: dict) -> str:
        """
        Build a full E-utilities URL with optional API key.

        Appends the NCBI API key if one was provided at init.
        """
        if self._api_key:
            params["api_key"] = self._api_key

        query_string = urllib.parse.urlencode(params)
        return f"{EUTILS_BASE}{endpoint}?{query_string}"
