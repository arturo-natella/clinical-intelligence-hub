"""
Clinical Intelligence Hub -- gnomAD (Genome Aggregation Database)

gnomAD aggregates exome and genome sequencing data from over 800,000
individuals across large-scale research projects worldwide.  It provides
allele frequencies broken down by population:

    Global, European (non-Finnish), Finnish, African/African-American,
    Latino/Admixed American, Ashkenazi Jewish, East Asian, South Asian,
    Middle Eastern, and Other.

This data is critical for interpreting genetic testing results.  When a
patient's report lists a variant, the first clinical question is:
"How common is this in the general population?"

    - Allele frequency < 0.01 (1%)   ->  Rare, more likely disease-causing
    - Allele frequency 0.01 - 0.05   ->  Uncommon, evaluate in context
    - Allele frequency >= 0.05 (5%)  ->  Common, likely benign polymorphism

gnomAD also provides gene-level constraint metrics (pLI, LOEUF) that
quantify how intolerant a gene is to loss-of-function mutations.  A high
pLI score (>0.9) means the gene is under strong selection pressure --
loss-of-function variants in that gene are likely deleterious.

API: GraphQL at https://gnomad.broadinstitute.org/api
No authentication required, free and open access.
"""

import json
import logging
from typing import Optional

from src.validation._http import api_post

logger = logging.getLogger("CIH-gnomAD")

GNOMAD_API = "https://gnomad.broadinstitute.org/api"


class GnomADClient:
    """gnomAD GraphQL client for population allele frequency lookup."""

    # -- GraphQL Transport -----------------------------------------------

    def _query(self, graphql_query: str) -> Optional[dict]:
        """
        Execute a GraphQL query against the gnomAD API.

        Args:
            graphql_query: GraphQL query string.

        Returns:
            Parsed ``data`` dict from the GraphQL response, or None on failure.
        """
        payload = {"query": graphql_query}

        try:
            response = api_post(
                GNOMAD_API,
                body=json.dumps(payload).encode("utf-8"),
                content_type="application/json",
                timeout=30,
            )
            if not response:
                return None

            # GraphQL errors are returned inside the response body
            if response.get("errors"):
                msgs = [e.get("message", "") for e in response["errors"]]
                logger.debug(
                    "gnomAD GraphQL errors: %s", "; ".join(msgs)
                )
                # Some queries return partial data alongside errors
                if not response.get("data"):
                    return None

            return response.get("data")

        except Exception as e:
            logger.debug("gnomAD GraphQL query failed: %s", e)
            return None

    # -- Variant Lookup --------------------------------------------------

    def get_variant(
        self, variant_id: str, dataset: str = "gnomad_r4"
    ) -> Optional[dict]:
        """
        Get allele frequency and summary data for a variant.

        Args:
            variant_id: gnomAD-style variant ID in the format
                        "chrom-pos-ref-alt" (e.g. "1-55516888-G-A").
            dataset: gnomAD dataset version (e.g. "gnomad_r4", "gnomad_r3").

        Returns:
            Variant summary with global allele frequency, counts, flags,
            and rsIDs, or None if the variant is not found.
        """
        if not variant_id or not variant_id.strip():
            return None

        variant_id = variant_id.strip()

        query = """
        {
          variant(variantId: "%s", dataset: %s) {
            variant_id
            rsids
            chrom
            pos
            ref
            alt
            exome {
              ac
              an
              af
            }
            genome {
              ac
              an
              af
            }
            flags
            joint {
              ac
              an
              af
            }
          }
        }
        """ % (variant_id, dataset)

        data = self._query(query)
        if not data:
            return None

        variant = data.get("variant")
        if not variant:
            return None

        return self._parse_variant(variant)

    def get_variant_by_rsid(
        self, rs_id: str, dataset: str = "gnomad_r4"
    ) -> Optional[dict]:
        """
        Look up a variant by its dbSNP rs identifier.

        gnomAD's GraphQL API does not support direct rsID lookup, so we
        first use the variant_search endpoint to resolve the rsID to a
        gnomAD variant ID, then fetch full variant data.

        Args:
            rs_id: dbSNP rs identifier (e.g. "rs1234", "RS1234", or "1234").
            dataset: gnomAD dataset version.

        Returns:
            Same format as get_variant, or None if not found.
        """
        if not rs_id or not rs_id.strip():
            return None

        # Normalize to "rs" prefix
        cleaned = rs_id.strip().lower()
        if not cleaned.startswith("rs"):
            cleaned = f"rs{cleaned}"

        # Step 1: Search for the rsID to get a gnomAD variant ID
        search_query = """
        {
          variant_search(query: "%s", dataset: %s) {
            variant_id
          }
        }
        """ % (cleaned, dataset)

        data = self._query(search_query)
        if not data:
            return None

        search_results = data.get("variant_search")
        if not search_results or not isinstance(search_results, list):
            return None

        if len(search_results) == 0:
            logger.debug(
                "gnomAD: no variant found for rsID '%s'", rs_id
            )
            return None

        # Use the first matching variant ID
        resolved_id = search_results[0].get("variant_id")
        if not resolved_id:
            return None

        # Step 2: Fetch full variant data
        return self.get_variant(resolved_id, dataset=dataset)

    # -- Population Frequencies ------------------------------------------

    def get_variant_populations(
        self, variant_id: str, dataset: str = "gnomad_r4"
    ) -> Optional[dict]:
        """
        Get allele frequency broken down by ancestry population.

        Returns frequencies for each gnomAD population: African (afr),
        Latino/Admixed American (amr), Ashkenazi Jewish (asj), East Asian
        (eas), Finnish (fin), Non-Finnish European (nfe), South Asian (sas),
        Middle Eastern (mid), and Other (oth).

        Args:
            variant_id: gnomAD-style variant ID ("chrom-pos-ref-alt").
            dataset: gnomAD dataset version.

        Returns:
            Dict with variant_id and populations mapping each population
            to its allele count, allele number, and frequency.
        """
        if not variant_id or not variant_id.strip():
            return None

        variant_id = variant_id.strip()

        query = """
        {
          variant(variantId: "%s", dataset: %s) {
            variant_id
            genome {
              populations {
                id
                ac
                an
                af
              }
            }
            exome {
              populations {
                id
                ac
                an
                af
              }
            }
          }
        }
        """ % (variant_id, dataset)

        data = self._query(query)
        if not data:
            return None

        variant = data.get("variant")
        if not variant:
            return None

        return self._parse_populations(variant)

    # -- Gene Constraint -------------------------------------------------

    def get_gene_variants(
        self, gene_symbol: str, dataset: str = "gnomad_r4"
    ) -> Optional[dict]:
        """
        Get gene-level information and constraint metrics from gnomAD.

        Constraint metrics measure how tolerant a gene is to different
        types of mutations:

        - **pLI**: Probability of loss-of-function intolerance.
          pLI > 0.9 means the gene is extremely intolerant to LoF
          variants -- haploinsufficiency is likely deleterious.

        - **LOEUF** (oe_lof_upper): Loss-of-function observed/expected
          upper bound. Lower values = more constrained. LOEUF < 0.35
          is the modern replacement for pLI in gnomAD v4.

        Args:
            gene_symbol: HGNC gene symbol (e.g. "BRCA1", "TP53", "SCN5A").
            dataset: gnomAD dataset version.

        Returns:
            Gene summary with constraint metrics, or None if not found.
        """
        if not gene_symbol or not gene_symbol.strip():
            return None

        gene_symbol = gene_symbol.strip().upper()

        query = """
        {
          gene(gene_symbol: "%s", reference_genome: GRCh38) {
            gene_id
            symbol
            name
            chrom
            start
            stop
            gnomad_constraint {
              pLI
              oe_lof
              oe_lof_lower
              oe_lof_upper
            }
          }
        }
        """ % gene_symbol

        data = self._query(query)
        if not data:
            return None

        gene = data.get("gene")
        if not gene:
            return None

        return self._parse_gene(gene)

    # -- Rarity Classification -------------------------------------------

    def is_rare(
        self,
        variant_id: str,
        threshold: float = 0.01,
        dataset: str = "gnomad_r4",
    ) -> Optional[dict]:
        """
        Determine whether a variant is rare in the general population.

        Clinical classification:
            - frequency < 0.001  (0.1%):  rare
            - frequency < threshold (default 1%):  rare
            - frequency < 0.05  (5%):  uncommon
            - frequency >= 0.05 (5%):  common

        A variant with no frequency data (not observed in gnomAD) is
        classified as rare -- absence from a database of 800k+ people
        is itself strong evidence of rarity.

        Args:
            variant_id: gnomAD-style variant ID ("chrom-pos-ref-alt").
            threshold: Frequency cutoff for "rare" (default 0.01 = 1%).
            dataset: gnomAD dataset version.

        Returns:
            Dict with variant_id, allele_frequency, is_rare bool,
            and human-readable classification string.
        """
        if not variant_id or not variant_id.strip():
            return None

        variant_id = variant_id.strip()

        variant_data = self.get_variant(variant_id, dataset=dataset)

        # If variant is not in gnomAD at all, it's extremely rare
        if not variant_data:
            return {
                "variant_id": variant_id,
                "allele_frequency": None,
                "is_rare": True,
                "classification": "rare",
                "detail": (
                    "Variant not found in gnomAD (800k+ individuals). "
                    "Absence from population databases is strong evidence "
                    "of rarity."
                ),
                "threshold_used": threshold,
                "source": "gnomAD",
            }

        af = variant_data.get("allele_frequency")

        # No frequency data available
        if af is None:
            return {
                "variant_id": variant_id,
                "allele_frequency": None,
                "is_rare": True,
                "classification": "rare",
                "detail": "Variant exists in gnomAD but has no frequency data.",
                "threshold_used": threshold,
                "source": "gnomAD",
            }

        # Classify based on frequency
        if af < threshold:
            classification = "rare"
        elif af < 0.05:
            classification = "uncommon"
        else:
            classification = "common"

        return {
            "variant_id": variant_id,
            "allele_frequency": af,
            "is_rare": af < threshold,
            "classification": classification,
            "detail": (
                f"Allele frequency {af:.6f} "
                f"({'below' if af < threshold else 'above'} "
                f"{threshold:.2%} threshold)"
            ),
            "threshold_used": threshold,
            "source": "gnomAD",
        }

    # -- Response Parsing ------------------------------------------------

    @staticmethod
    def _parse_variant(variant: dict) -> Optional[dict]:
        """
        Parse a gnomAD variant response into a standardized summary.

        Prefers joint (exome+genome combined) frequency when available,
        then falls back to genome, then exome.
        """
        try:
            # Extract the best available allele frequency and counts.
            # Preference order: joint > genome > exome
            af = None
            ac = None
            an = None
            freq_source = None

            joint = variant.get("joint") or {}
            genome = variant.get("genome") or {}
            exome = variant.get("exome") or {}

            if joint.get("af") is not None:
                af = joint["af"]
                ac = joint.get("ac")
                an = joint.get("an")
                freq_source = "joint"
            elif genome.get("af") is not None:
                af = genome["af"]
                ac = genome.get("ac")
                an = genome.get("an")
                freq_source = "genome"
            elif exome.get("af") is not None:
                af = exome["af"]
                ac = exome.get("ac")
                an = exome.get("an")
                freq_source = "exome"

            rsids = variant.get("rsids") or []

            return {
                "variant_id": variant.get("variant_id", ""),
                "rsids": rsids,
                "chromosome": variant.get("chrom", ""),
                "position": variant.get("pos"),
                "ref": variant.get("ref", ""),
                "alt": variant.get("alt", ""),
                "allele_frequency": af,
                "allele_count": ac,
                "allele_number": an,
                "frequency_source": freq_source,
                "flags": variant.get("flags") or [],
                "exome": {
                    "ac": exome.get("ac"),
                    "an": exome.get("an"),
                    "af": exome.get("af"),
                } if exome else None,
                "genome": {
                    "ac": genome.get("ac"),
                    "an": genome.get("an"),
                    "af": genome.get("af"),
                } if genome else None,
                "url": (
                    f"https://gnomad.broadinstitute.org/variant/"
                    f"{variant.get('variant_id', '')}"
                ),
                "source": "gnomAD",
            }

        except Exception as e:
            logger.debug("gnomAD variant parse failed: %s", e)
            return None

    @staticmethod
    def _parse_populations(variant: dict) -> Optional[dict]:
        """
        Parse population-level frequency data from a gnomAD variant response.

        Merges genome and exome population data, preferring genome when
        both are present (larger sample size for most populations).
        """
        try:
            populations = {}

            # Collect genome populations (primary)
            genome = variant.get("genome") or {}
            genome_pops = genome.get("populations") or []
            for pop in genome_pops:
                if not isinstance(pop, dict):
                    continue
                pop_id = pop.get("id", "")
                if not pop_id:
                    continue
                populations[pop_id] = {
                    "allele_count": pop.get("ac"),
                    "allele_number": pop.get("an"),
                    "allele_frequency": pop.get("af"),
                    "source": "genome",
                }

            # Add exome populations (fill gaps or note separately)
            exome = variant.get("exome") or {}
            exome_pops = exome.get("populations") or []
            for pop in exome_pops:
                if not isinstance(pop, dict):
                    continue
                pop_id = pop.get("id", "")
                if not pop_id:
                    continue
                if pop_id not in populations:
                    populations[pop_id] = {
                        "allele_count": pop.get("ac"),
                        "allele_number": pop.get("an"),
                        "allele_frequency": pop.get("af"),
                        "source": "exome",
                    }

            return {
                "variant_id": variant.get("variant_id", ""),
                "populations": populations,
                "url": (
                    f"https://gnomad.broadinstitute.org/variant/"
                    f"{variant.get('variant_id', '')}"
                ),
                "source": "gnomAD",
            }

        except Exception as e:
            logger.debug("gnomAD population parse failed: %s", e)
            return None

    @staticmethod
    def _parse_gene(gene: dict) -> Optional[dict]:
        """
        Parse a gnomAD gene response into a standardized summary
        with constraint metrics.
        """
        try:
            constraint = gene.get("gnomad_constraint") or {}

            pli = constraint.get("pLI")
            oe_lof = constraint.get("oe_lof")
            oe_lof_lower = constraint.get("oe_lof_lower")
            oe_lof_upper = constraint.get("oe_lof_upper")

            # Interpret constraint for clinical context
            constraint_interpretation = None
            if pli is not None:
                if pli > 0.9:
                    constraint_interpretation = (
                        "Highly intolerant to loss-of-function variants "
                        "(pLI > 0.9). Loss-of-function mutations in this "
                        "gene are likely deleterious."
                    )
                elif pli > 0.5:
                    constraint_interpretation = (
                        "Moderately constrained (pLI 0.5-0.9). Some "
                        "intolerance to loss-of-function variants."
                    )
                else:
                    constraint_interpretation = (
                        "Tolerant to loss-of-function variants (pLI < 0.5). "
                        "Heterozygous LoF variants may be tolerated."
                    )

            return {
                "gene_id": gene.get("gene_id", ""),
                "symbol": gene.get("symbol", ""),
                "name": gene.get("name", ""),
                "chromosome": gene.get("chrom", ""),
                "start": gene.get("start"),
                "stop": gene.get("stop"),
                "pLI": pli,
                "oe_lof": oe_lof,
                "oe_lof_lower": oe_lof_lower,
                "oe_lof_upper": oe_lof_upper,
                "constraint_interpretation": constraint_interpretation,
                "url": (
                    f"https://gnomad.broadinstitute.org/gene/"
                    f"{gene.get('gene_id', '')}"
                ),
                "source": "gnomAD",
            }

        except Exception as e:
            logger.debug("gnomAD gene parse failed: %s", e)
            return None
