"""
Clinical Intelligence Hub — BioGRID (Biological General Repository for Interaction Datasets)

BioGRID is a curated biological interaction database containing over 2 million
protein and genetic interactions from major model organism species. It maps
physical and genetic interactions between proteins, showing how one mutated
protein can cascade to affect others through interaction networks.

Interaction types include:

    Physical interactions — direct protein-protein binding (co-immunoprecipitation,
    two-hybrid, affinity capture, reconstituted complex, etc.)

    Genetic interactions — functional relationships where mutation in one gene
    modifies the phenotype of another (synthetic lethality, dosage rescue,
    phenotypic enhancement/suppression, etc.)

BioGRID is useful for understanding how a gene variant can cascade through
protein interaction networks. If a patient has a pathogenic variant in gene X,
BioGRID reveals which other proteins are directly affected — partners that
depend on gene X for normal function. This is critical for predicting
downstream phenotypic effects beyond the directly mutated gene.

API: https://wiki.thebiogrid.org/doku.php/biogridrest
Base: https://webservice.thebiogrid.org/interactions/
Requires: Free API key from https://webservice.thebiogrid.org/
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-BioGRID")

BIOGRID_BASE = "https://webservice.thebiogrid.org"


class BioGRIDClient:
    """BioGRID interaction database client for protein interaction network lookup."""

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: BioGRID REST API key (free registration at
                     https://webservice.thebiogrid.org/). Required for
                     most endpoints.
        """
        self._api_key = api_key

    # ── Public methods ──────────────────────────────────────

    def get_interactions(
        self,
        gene_symbol: str,
        limit: int = 50,
        organism: int = 9606,
    ) -> list[dict]:
        """
        Get protein interactions involving a gene.

        Queries BioGRID for all interactions where the given gene
        appears as either interactor A or interactor B. Organism
        9606 is Homo sapiens (human).

        Returns list of interactions with gene pair, interaction
        type (physical/genetic), experimental system, PubMed ID,
        and throughput level.
        """
        if not gene_symbol or not gene_symbol.strip():
            return []

        if not self._api_key:
            logger.warning(
                "BioGRID API key not configured — most endpoints "
                "require an access key. Register free at "
                "https://webservice.thebiogrid.org/"
            )
            return []

        gene_clean = gene_symbol.strip().upper()

        params = {
            "accesskey": self._api_key,
            "format": "json",
            "searchNames": "true",
            "geneList": gene_clean,
            "taxId": str(organism),
            "max": str(limit),
        }
        url = self._build_url("/interactions/", params)

        try:
            data = api_get(url, timeout=20)
            if not data:
                return []

            # BioGRID returns a dict keyed by interaction ID
            if not isinstance(data, dict):
                return []

            interactions = []
            for interaction_id, entry in data.items():
                if not isinstance(entry, dict):
                    continue

                parsed = self._parse_interaction(interaction_id, entry)
                if parsed:
                    interactions.append(parsed)

            return interactions

        except Exception as e:
            logger.debug(
                f"BioGRID get_interactions failed for '{gene_symbol}': {e}"
            )
            return []

    def get_interaction_partners(
        self, gene_symbol: str, limit: int = 30
    ) -> list[dict]:
        """
        Get unique interaction partners for a gene.

        Fetches interactions and deduplicates by partner gene,
        aggregating interaction counts and types for each partner.

        Returns list of partners with partner gene name, total
        interaction count, set of interaction types observed,
        and evidence count (number of publications).
        """
        if not gene_symbol or not gene_symbol.strip():
            return []

        gene_clean = gene_symbol.strip().upper()

        # Fetch more interactions than the partner limit to ensure
        # good coverage after deduplication
        interactions = self.get_interactions(gene_clean, limit=limit * 3)
        if not interactions:
            return []

        # Aggregate by partner gene
        partner_map: dict[str, dict] = {}
        for interaction in interactions:
            gene_a = (interaction.get("gene_a") or "").upper()
            gene_b = (interaction.get("gene_b") or "").upper()

            # Determine which gene is the partner
            if gene_a == gene_clean:
                partner = interaction.get("gene_b", "")
            elif gene_b == gene_clean:
                partner = interaction.get("gene_a", "")
            else:
                # Both genes match (self-interaction) or neither
                partner = gene_b if gene_b != gene_clean else gene_a

            if not partner:
                continue

            partner_upper = partner.upper()

            if partner_upper not in partner_map:
                partner_map[partner_upper] = {
                    "partner_gene": partner,
                    "interaction_count": 0,
                    "interaction_types": set(),
                    "pubmed_ids": set(),
                }

            entry = partner_map[partner_upper]
            entry["interaction_count"] += 1

            itype = interaction.get("interaction_type", "")
            if itype:
                entry["interaction_types"].add(itype)

            pubmed = interaction.get("pubmed_id")
            if pubmed:
                entry["pubmed_ids"].add(str(pubmed))

        # Convert sets to lists and build output
        partners = []
        for partner_data in sorted(
            partner_map.values(),
            key=lambda x: x["interaction_count"],
            reverse=True,
        ):
            partners.append({
                "partner_gene": partner_data["partner_gene"],
                "interaction_count": partner_data["interaction_count"],
                "interaction_types": sorted(partner_data["interaction_types"]),
                "evidence_count": len(partner_data["pubmed_ids"]),
                "source": "BioGRID",
            })

            if len(partners) >= limit:
                break

        return partners

    def get_shared_interactions(
        self, gene_a: str, gene_b: str
    ) -> list[dict]:
        """
        Find proteins that interact with BOTH genes.

        Retrieves interaction partners for each gene and finds
        the intersection — shared interactors that bridge both
        proteins. Useful for understanding how two genes are
        connected through common partners.

        Returns list of shared interactors with interaction
        details for each gene.
        """
        if not gene_a or not gene_b:
            return []

        gene_a_clean = gene_a.strip().upper()
        gene_b_clean = gene_b.strip().upper()

        # Get partners for each gene
        partners_a = self.get_interaction_partners(gene_a_clean, limit=100)
        partners_b = self.get_interaction_partners(gene_b_clean, limit=100)

        if not partners_a or not partners_b:
            return []

        # Build lookup sets
        partners_a_map = {
            p["partner_gene"].upper(): p for p in partners_a
        }
        partners_b_map = {
            p["partner_gene"].upper(): p for p in partners_b
        }

        # Find intersection
        shared_genes = (
            set(partners_a_map.keys()) & set(partners_b_map.keys())
        )

        # Exclude the query genes themselves from the shared set
        shared_genes.discard(gene_a_clean)
        shared_genes.discard(gene_b_clean)

        shared = []
        for gene in sorted(shared_genes):
            pa = partners_a_map[gene]
            pb = partners_b_map[gene]

            shared.append({
                "shared_interactor": pa["partner_gene"],
                "interactions_with_a": {
                    "gene": gene_a_clean,
                    "count": pa["interaction_count"],
                    "types": pa["interaction_types"],
                },
                "interactions_with_b": {
                    "gene": gene_b_clean,
                    "count": pb["interaction_count"],
                    "types": pb["interaction_types"],
                },
                "total_evidence": pa["evidence_count"] + pb["evidence_count"],
                "source": "BioGRID",
            })

        return shared

    def get_interaction_network(
        self, gene_symbol: str, depth: int = 1
    ) -> dict:
        """
        Build an interaction network centered on a gene.

        depth=1: Returns the gene and its direct interaction partners.
        depth=2: Also includes partners of partners (second-degree
        neighbors), providing a broader view of the interaction
        neighborhood.

        Returns a network dict with center gene, node list (each
        with gene name and degree), and edge list (each with source,
        target, and interaction type).
        """
        if not gene_symbol or not gene_symbol.strip():
            return {
                "center_gene": gene_symbol or "",
                "nodes": [],
                "edges": [],
                "source": "BioGRID",
            }

        gene_clean = gene_symbol.strip().upper()
        depth = max(1, min(depth, 2))  # Clamp to 1-2

        nodes: dict[str, int] = {}  # gene -> degree
        edges: list[dict] = []
        seen_edges: set[tuple] = set()

        # Depth 1: direct partners
        interactions = self.get_interactions(gene_clean, limit=50)

        nodes[gene_clean] = 0

        for interaction in interactions:
            gene_a = (interaction.get("gene_a") or "").upper()
            gene_b = (interaction.get("gene_b") or "").upper()
            itype = interaction.get("interaction_type", "")

            if not gene_a or not gene_b:
                continue

            # Track nodes
            for g in (gene_a, gene_b):
                nodes[g] = nodes.get(g, 0)

            # Track edges (deduplicate by sorted pair)
            edge_key = (min(gene_a, gene_b), max(gene_a, gene_b))
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append({
                    "source": interaction.get("gene_a", ""),
                    "target": interaction.get("gene_b", ""),
                    "type": itype,
                })

        # Calculate degree for depth-1 nodes
        for edge in edges:
            src = (edge.get("source") or "").upper()
            tgt = (edge.get("target") or "").upper()
            if src in nodes:
                nodes[src] = nodes.get(src, 0) + 1
            if tgt in nodes:
                nodes[tgt] = nodes.get(tgt, 0) + 1

        # Depth 2: partners of partners
        if depth >= 2:
            depth1_partners = [
                g for g in nodes if g != gene_clean
            ]
            # Limit second-degree expansion to avoid excessive API calls
            for partner in depth1_partners[:10]:
                partner_interactions = self.get_interactions(
                    partner, limit=20
                )

                for interaction in partner_interactions:
                    gene_a = (interaction.get("gene_a") or "").upper()
                    gene_b = (interaction.get("gene_b") or "").upper()
                    itype = interaction.get("interaction_type", "")

                    if not gene_a or not gene_b:
                        continue

                    for g in (gene_a, gene_b):
                        if g not in nodes:
                            nodes[g] = 0

                    edge_key = (min(gene_a, gene_b), max(gene_a, gene_b))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append({
                            "source": interaction.get("gene_a", ""),
                            "target": interaction.get("gene_b", ""),
                            "type": itype,
                        })

            # Recalculate degrees after depth-2 expansion
            for g in nodes:
                nodes[g] = 0
            for edge in edges:
                src = (edge.get("source") or "").upper()
                tgt = (edge.get("target") or "").upper()
                if src in nodes:
                    nodes[src] += 1
                if tgt in nodes:
                    nodes[tgt] += 1

        return {
            "center_gene": gene_clean,
            "nodes": [
                {"gene": gene, "degree": degree}
                for gene, degree in sorted(
                    nodes.items(), key=lambda x: x[1], reverse=True
                )
            ],
            "edges": edges,
            "source": "BioGRID",
        }

    def search_interactions(
        self, gene_list: list[str], limit: int = 100
    ) -> list[dict]:
        """
        Search for interactions among a list of genes.

        Queries BioGRID with a pipe-separated gene list to find
        interactions between any of the listed genes. Useful for
        checking whether a set of genes from a patient's results
        have known interactions with each other.

        Returns interactions between any of the listed genes.
        """
        if not gene_list:
            return []

        if not self._api_key:
            logger.warning(
                "BioGRID API key not configured — most endpoints "
                "require an access key. Register free at "
                "https://webservice.thebiogrid.org/"
            )
            return []

        # Clean and join gene symbols
        cleaned_genes = [
            g.strip().upper() for g in gene_list if g and g.strip()
        ]
        if not cleaned_genes:
            return []

        pipe_separated = "|".join(cleaned_genes)

        params = {
            "accesskey": self._api_key,
            "format": "json",
            "geneList": pipe_separated,
            "taxId": "9606",
            "max": str(limit),
        }
        url = self._build_url("/interactions/", params)

        try:
            data = api_get(url, timeout=20)
            if not data:
                return []

            if not isinstance(data, dict):
                return []

            interactions = []
            for interaction_id, entry in data.items():
                if not isinstance(entry, dict):
                    continue

                parsed = self._parse_interaction(interaction_id, entry)
                if parsed:
                    interactions.append(parsed)

            return interactions

        except Exception as e:
            logger.debug(
                f"BioGRID search_interactions failed for "
                f"{cleaned_genes[:3]}...: {e}"
            )
            return []

    # ── Parsing helpers ────────────────────────────────────

    @staticmethod
    def _parse_interaction(
        interaction_id: str, entry: dict
    ) -> Optional[dict]:
        """
        Parse a BioGRID interaction entry into a standardized dict.

        BioGRID REST API returns interactions keyed by numeric ID,
        with fields for both interactors, experimental system, and
        publication metadata.
        """
        try:
            # Gene symbols for both interactors
            gene_a = entry.get("OFFICIAL_SYMBOL_A", "")
            gene_b = entry.get("OFFICIAL_SYMBOL_B", "")

            if not gene_a and not gene_b:
                return None

            # Interaction type: physical or genetic
            experimental_system = entry.get("EXPERIMENTAL_SYSTEM", "")
            system_type = entry.get("EXPERIMENTAL_SYSTEM_TYPE", "")

            # Determine interaction type from system type
            interaction_type = system_type.lower() if system_type else ""
            if not interaction_type:
                # Infer from experimental system name
                physical_systems = {
                    "affinity capture-ms", "affinity capture-western",
                    "co-fractionation", "co-localization",
                    "co-purification", "reconstituted complex",
                    "two-hybrid", "far western", "fret",
                    "protein-peptide", "co-crystal structure",
                    "biochemical activity", "pca",
                    "affinity capture-luminescence",
                    "affinity capture-rna", "protein-rna",
                }
                if experimental_system.lower() in physical_systems:
                    interaction_type = "physical"
                else:
                    interaction_type = "genetic"

            # PubMed ID
            pubmed_id = entry.get("PUBMED_ID")
            if pubmed_id:
                try:
                    pubmed_id = int(pubmed_id)
                except (ValueError, TypeError):
                    pubmed_id = None

            # Throughput (high/low)
            throughput = entry.get("THROUGHPUT", "")

            return {
                "interaction_id": str(interaction_id),
                "gene_a": gene_a,
                "gene_b": gene_b,
                "interaction_type": interaction_type,
                "experimental_system": experimental_system,
                "pubmed_id": pubmed_id,
                "throughput": throughput.lower() if throughput else "",
                "organism_a": entry.get("ORGANISM_A", ""),
                "organism_b": entry.get("ORGANISM_B", ""),
                "source": "BioGRID",
            }

        except Exception as e:
            logger.debug(
                f"BioGRID parse failed for interaction {interaction_id}: {e}"
            )
            return None

    # ── URL builder ────────────────────────────────────────

    def _build_url(self, endpoint: str, params: dict) -> str:
        """
        Build a full BioGRID REST API URL.

        Constructs the URL with query parameters. The access key
        is included in the params dict by the caller.
        """
        query_string = urllib.parse.urlencode(params)
        return f"{BIOGRID_BASE}{endpoint}?{query_string}"
