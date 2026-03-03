"""
Clinical Intelligence Hub — UniProt (Universal Protein Resource)

UniProt is the most comprehensive, high-quality protein knowledgebase in the
world. It contains detailed information about protein function, 3D structure,
protein-protein interactions, disease associations, post-translational
modifications, and subcellular localization for proteins across all species.

When a genetic variant is identified through sequencing or clinical testing,
UniProt explains what the resulting protein does and how mutations might affect
its function. UniProt entries connect a gene name to:

- What the protein does (catalytic activity, biological process)
- Where it acts in the cell (membrane, nucleus, mitochondria)
- What diseases are linked to mutations in the gene
- What other proteins it interacts with
- What known natural variants exist and their clinical effects

UniProt has two tiers:
    Swiss-Prot — manually curated, reviewed (~570K entries)
    TrEMBL — automatically annotated, unreviewed (~250M entries)

For clinical use, we query Swiss-Prot (reviewed:true) entries only when
searching by gene, to get the highest-quality curated annotations.

API: https://rest.uniprot.org (RESTful, JSON)
Docs: https://www.uniprot.org/help/api
Free, no authentication required.
"""

import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-UniProt")

UNIPROT_BASE = "https://rest.uniprot.org"


class UniProtClient:
    """UniProt protein knowledgebase client for gene/protein lookup."""

    # ── Public methods ──────────────────────────────────────

    def search_protein(
        self, query: str, organism: str = "human", limit: int = 10
    ) -> list[dict]:
        """
        Search UniProt for proteins matching a free-text query.

        Works with protein names, gene names, accessions, keywords,
        or any combination. Filters by organism (default: human).

        Returns list of protein summaries with accession, name, gene,
        organism, existence evidence, and sequence length.
        """
        encoded_query = urllib.parse.quote(f"{query} AND organism_name:{organism}")
        url = (
            f"{UNIPROT_BASE}/uniprotkb/search"
            f"?query={encoded_query}"
            f"&size={limit}"
            f"&format=json"
        )

        try:
            data = api_get(url)
            if not data:
                return []

            results_list = data.get("results", [])
            if not isinstance(results_list, list):
                return []

            proteins = []
            for entry in results_list:
                if not isinstance(entry, dict):
                    continue

                parsed = self._parse_protein_summary(entry)
                if parsed:
                    proteins.append(parsed)

            return proteins

        except Exception as e:
            logger.debug(f"UniProt search failed for '{query}': {e}")
            return []

    def get_protein(self, accession: str) -> Optional[dict]:
        """
        Get full protein details by UniProt accession (e.g., P04637).

        Returns comprehensive protein record including function
        description, subcellular location, disease associations,
        gene names, and keywords.
        """
        url = f"{UNIPROT_BASE}/uniprotkb/{urllib.parse.quote(accession)}.json"

        try:
            data = api_get(url)
            if not data or not isinstance(data, dict):
                return None

            return self._parse_protein_detail(data)

        except Exception as e:
            logger.debug(f"UniProt get_protein failed for {accession}: {e}")
            return None

    def search_by_gene(self, gene_symbol: str) -> Optional[dict]:
        """
        Search for the reviewed (Swiss-Prot) human protein for a gene.

        Uses organism_id:9606 (Homo sapiens) and reviewed:true to get
        only manually curated Swiss-Prot entries. Returns the best
        match with full protein details.

        This is the primary entry point when you have a gene symbol
        from a genetic test result.
        """
        encoded_query = urllib.parse.quote(
            f"gene:{gene_symbol} AND organism_id:9606 AND reviewed:true"
        )
        url = (
            f"{UNIPROT_BASE}/uniprotkb/search"
            f"?query={encoded_query}"
            f"&size=1"
            f"&format=json"
        )

        try:
            data = api_get(url)
            if not data:
                return None

            results_list = data.get("results", [])
            if not isinstance(results_list, list) or not results_list:
                return None

            entry = results_list[0]
            if not isinstance(entry, dict):
                return None

            return self._parse_protein_detail(entry)

        except Exception as e:
            logger.debug(f"UniProt search_by_gene failed for '{gene_symbol}': {e}")
            return None

    def get_function(self, gene_symbol: str) -> Optional[dict]:
        """
        Get the protein's functional annotation for a gene.

        Answers: "What does this protein do?" — extracts the function
        description, catalytic activity, and pathway information from
        the Swiss-Prot entry.
        """
        entry = self.search_by_gene(gene_symbol)
        if not entry:
            return None

        return {
            "gene": gene_symbol,
            "protein_name": entry.get("name", ""),
            "accession": entry.get("accession", ""),
            "function_description": entry.get("function_description", ""),
            "catalytic_activity": self._extract_catalytic_activity(entry),
            "pathway": self._extract_pathway(entry),
            "url": entry.get("url", ""),
            "source": "UniProt",
        }

    def get_disease_associations(self, gene_symbol: str) -> list[dict]:
        """
        Get diseases associated with variants in a gene.

        Extracts disease annotations from the Swiss-Prot entry,
        including MIM (OMIM) cross-references and descriptions
        of how mutations in this gene cause disease.
        """
        entry = self.search_by_gene(gene_symbol)
        if not entry:
            return []

        diseases = entry.get("disease_associations", [])
        if not isinstance(diseases, list):
            return []

        return diseases

    def get_variants(self, gene_symbol: str, limit: int = 50) -> list[dict]:
        """
        Get known natural protein variants and their effects.

        Extracts variant features (type="Natural variant") from the
        Swiss-Prot entry. These are amino acid substitutions observed
        in human populations, often with disease associations and
        dbSNP cross-references.
        """
        entry_data = self._fetch_raw_entry_by_gene(gene_symbol)
        if not entry_data:
            return []

        features = entry_data.get("features", [])
        if not isinstance(features, list):
            return []

        variants = []
        for feature in features:
            if not isinstance(feature, dict):
                continue

            feat_type = feature.get("type", "")
            if feat_type != "Natural variant":
                continue

            # Location
            location = feature.get("location", {})
            start = None
            end = None
            if isinstance(location, dict):
                start_obj = location.get("start", {})
                end_obj = location.get("end", {})
                if isinstance(start_obj, dict):
                    start = start_obj.get("value")
                elif isinstance(start_obj, (int, float)):
                    start = int(start_obj)
                if isinstance(end_obj, dict):
                    end = end_obj.get("value")
                elif isinstance(end_obj, (int, float)):
                    end = int(end_obj)

            # Alternativesequence (original and variant amino acids)
            alt_seq = feature.get("alternativeSequence", {})
            original_aa = ""
            variant_aa = ""
            if isinstance(alt_seq, dict):
                original_seq = alt_seq.get("originalSequence", "")
                original_aa = original_seq if isinstance(original_seq, str) else ""

                alt_seqs = alt_seq.get("alternativeSequences", [])
                if isinstance(alt_seqs, list) and alt_seqs:
                    variant_aa = str(alt_seqs[0]) if alt_seqs[0] else ""

            # Description and disease
            description = feature.get("description", "")
            if not isinstance(description, str):
                description = ""

            # Look for dbSNP cross-references in evidences or description
            dbsnp_id = ""
            evidences = feature.get("evidences", [])
            if isinstance(evidences, list):
                for ev in evidences:
                    if not isinstance(ev, dict):
                        continue
                    source = ev.get("source", {})
                    if isinstance(source, dict):
                        if source.get("name") == "dbSNP" or source.get("id", "").startswith("rs"):
                            dbsnp_id = source.get("id", "")
                            break

            # Also check the ftId (feature ID) which sometimes has dbSNP
            feat_id = feature.get("featureId", "")
            if not dbsnp_id and isinstance(feat_id, str) and feat_id.startswith("rs"):
                dbsnp_id = feat_id

            # Parse disease association from description
            disease_association = ""
            if description:
                # UniProt variant descriptions often contain "in DISEASE_NAME"
                desc_lower = description.lower()
                if " in " in desc_lower:
                    disease_association = description

            variants.append({
                "position": start,
                "original_aa": original_aa,
                "variant_aa": variant_aa,
                "description": description,
                "disease_association": disease_association,
                "dbSNP_id": dbsnp_id,
                "feature_id": feat_id if isinstance(feat_id, str) else "",
                "source": "UniProt",
            })

            if len(variants) >= limit:
                break

        return variants

    def get_interactions(self, gene_symbol: str) -> list[dict]:
        """
        Get protein-protein interactions for a gene.

        Extracts interaction comments from the Swiss-Prot entry,
        showing which other proteins this protein physically
        interacts with and how many experiments support the interaction.
        """
        entry_data = self._fetch_raw_entry_by_gene(gene_symbol)
        if not entry_data:
            return []

        comments = entry_data.get("comments", [])
        if not isinstance(comments, list):
            return []

        interactions = []
        for comment in comments:
            if not isinstance(comment, dict):
                continue

            if comment.get("commentType") != "INTERACTION":
                continue

            interaction_list = comment.get("interactions", [])
            if not isinstance(interaction_list, list):
                continue

            for interaction in interaction_list:
                if not isinstance(interaction, dict):
                    continue

                # Interactant details
                interactant_one = interaction.get("interactantOne", {})
                interactant_two = interaction.get("interactantTwo", {})

                # We want the OTHER protein (interactant two)
                partner = interactant_two if isinstance(interactant_two, dict) else {}

                partner_gene = ""
                partner_accession = ""

                # Gene name from interactant
                gene_name_obj = partner.get("geneName")
                if isinstance(gene_name_obj, str):
                    partner_gene = gene_name_obj
                elif isinstance(gene_name_obj, dict):
                    partner_gene = gene_name_obj.get("value", "")

                # Accession
                partner_accession = partner.get("uniProtkbAccession", "")
                if not partner_accession:
                    chain_id = partner.get("chainId", "")
                    int_id = partner.get("intActId", "")
                    partner_accession = chain_id or int_id

                # Number of experiments
                experiments = interaction.get("numberOfExperiments", 0)
                if not isinstance(experiments, (int, float)):
                    try:
                        experiments = int(experiments)
                    except (ValueError, TypeError):
                        experiments = 0

                if partner_gene or partner_accession:
                    interactions.append({
                        "interactor_gene": partner_gene,
                        "interactor_accession": partner_accession,
                        "experiments_count": experiments,
                        "source": "UniProt",
                    })

        return interactions

    # ── Internal helpers ────────────────────────────────────

    def _fetch_raw_entry_by_gene(self, gene_symbol: str) -> Optional[dict]:
        """
        Fetch the raw UniProt JSON entry for a human gene.

        Used by methods that need to parse features or comments
        directly from the full entry structure.
        """
        encoded_query = urllib.parse.quote(
            f"gene:{gene_symbol} AND organism_id:9606 AND reviewed:true"
        )
        url = (
            f"{UNIPROT_BASE}/uniprotkb/search"
            f"?query={encoded_query}"
            f"&size=1"
            f"&format=json"
        )

        try:
            data = api_get(url)
            if not data:
                return None

            results_list = data.get("results", [])
            if not isinstance(results_list, list) or not results_list:
                return None

            entry = results_list[0]
            return entry if isinstance(entry, dict) else None

        except Exception as e:
            logger.debug(f"UniProt raw fetch failed for '{gene_symbol}': {e}")
            return None

    # ── Parsing helpers ─────────────────────────────────────

    def _parse_protein_summary(self, entry: dict) -> Optional[dict]:
        """
        Parse a UniProt search result entry into a protein summary.

        Extracts the most useful fields defensively from the
        nested UniProt JSON structure.
        """
        try:
            accession = ""
            accessions = entry.get("primaryAccession", "")
            if isinstance(accessions, str):
                accession = accessions
            elif isinstance(accessions, list) and accessions:
                accession = str(accessions[0])

            # Protein name — deeply nested
            name = self._extract_protein_name(entry)

            # Gene names
            gene_names = self._extract_gene_names(entry)

            # Organism
            organism_obj = entry.get("organism", {})
            organism = ""
            if isinstance(organism_obj, dict):
                organism = organism_obj.get("scientificName", "")

            # Protein existence level
            protein_existence = ""
            pe_obj = entry.get("proteinExistence", "")
            if isinstance(pe_obj, str):
                protein_existence = pe_obj
            elif isinstance(pe_obj, dict):
                protein_existence = pe_obj.get("value", "")

            # Sequence length
            length = None
            seq = entry.get("sequence", {})
            if isinstance(seq, dict):
                length = seq.get("length")

            return {
                "accession": accession,
                "name": name,
                "gene_names": gene_names,
                "organism": organism,
                "protein_existence": protein_existence,
                "length": length,
                "url": f"https://www.uniprot.org/uniprotkb/{accession}" if accession else "",
                "source": "UniProt",
            }

        except Exception as e:
            logger.debug(f"UniProt parse summary failed: {e}")
            return None

    def _parse_protein_detail(self, entry: dict) -> Optional[dict]:
        """
        Parse a full UniProt entry into a comprehensive protein record.

        Extracts function, subcellular location, disease associations,
        gene names, and keywords from the deeply nested JSON.
        """
        try:
            # Start with summary fields
            summary = self._parse_protein_summary(entry)
            if not summary:
                return None

            # Function description
            function_desc = self._extract_comment_text(entry, "FUNCTION")

            # Subcellular location
            subcellular = self._extract_subcellular_location(entry)

            # Disease associations
            diseases = self._extract_disease_associations(entry)

            # Keywords
            keywords = []
            kw_list = entry.get("keywords", [])
            if isinstance(kw_list, list):
                for kw in kw_list:
                    if isinstance(kw, dict):
                        val = kw.get("name") or kw.get("value", "")
                        if val:
                            keywords.append(val)
                    elif isinstance(kw, str):
                        keywords.append(kw)

            summary["function_description"] = function_desc
            summary["subcellular_location"] = subcellular
            summary["disease_associations"] = diseases
            summary["keywords"] = keywords
            # Stash the raw comments and features for downstream helpers
            summary["_raw_comments"] = entry.get("comments", [])
            summary["_raw_features"] = entry.get("features", [])

            return summary

        except Exception as e:
            logger.debug(f"UniProt parse detail failed: {e}")
            return None

    def _extract_protein_name(self, entry: dict) -> str:
        """
        Extract protein recommended name from the nested structure.

        Path: protein.recommendedName.fullName.value
        Fallback: protein.submittedName[0].fullName.value
        """
        protein = entry.get("proteinDescription", {})
        if not isinstance(protein, dict):
            return ""

        # Try recommendedName first
        rec_name = protein.get("recommendedName", {})
        if isinstance(rec_name, dict):
            full_name = rec_name.get("fullName", {})
            if isinstance(full_name, dict):
                return full_name.get("value", "")
            elif isinstance(full_name, str):
                return full_name

        # Fallback: submittedName
        submitted = protein.get("submittedName", [])
        if isinstance(submitted, list) and submitted:
            first = submitted[0]
            if isinstance(first, dict):
                full_name = first.get("fullName", {})
                if isinstance(full_name, dict):
                    return full_name.get("value", "")
                elif isinstance(full_name, str):
                    return full_name

        return ""

    def _extract_gene_names(self, entry: dict) -> list[str]:
        """
        Extract all gene names/synonyms from the entry.

        UniProt stores genes as a list of objects, each with
        geneName and synonyms.
        """
        genes_list = entry.get("genes", [])
        if not isinstance(genes_list, list):
            return []

        names = []
        for gene_obj in genes_list:
            if not isinstance(gene_obj, dict):
                continue

            # Primary gene name
            gene_name = gene_obj.get("geneName", {})
            if isinstance(gene_name, dict):
                val = gene_name.get("value", "")
                if val:
                    names.append(val)
            elif isinstance(gene_name, str) and gene_name:
                names.append(gene_name)

            # Synonyms
            synonyms = gene_obj.get("synonyms", [])
            if isinstance(synonyms, list):
                for syn in synonyms:
                    if isinstance(syn, dict):
                        val = syn.get("value", "")
                        if val:
                            names.append(val)
                    elif isinstance(syn, str) and syn:
                        names.append(syn)

        return names

    def _extract_comment_text(self, entry: dict, comment_type: str) -> str:
        """
        Extract text content from a specific comment type.

        UniProt comments have commentType and nested texts[].value.
        """
        comments = entry.get("comments", [])
        if not isinstance(comments, list):
            return ""

        texts = []
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            if comment.get("commentType") != comment_type:
                continue

            # texts[] array
            text_list = comment.get("texts", [])
            if isinstance(text_list, list):
                for text_obj in text_list:
                    if isinstance(text_obj, dict):
                        val = text_obj.get("value", "")
                        if val:
                            texts.append(val)
                    elif isinstance(text_obj, str) and text_obj:
                        texts.append(text_obj)

            # Some comments have a direct "text" field
            direct_text = comment.get("text", "")
            if isinstance(direct_text, str) and direct_text and direct_text not in texts:
                texts.append(direct_text)

        return " ".join(texts)

    def _extract_subcellular_location(self, entry: dict) -> list[str]:
        """
        Extract subcellular location annotations.

        Path: comments[commentType=SUBCELLULAR LOCATION].subcellularLocations[].location.value
        """
        comments = entry.get("comments", [])
        if not isinstance(comments, list):
            return []

        locations = []
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            if comment.get("commentType") != "SUBCELLULAR LOCATION":
                continue

            sub_locs = comment.get("subcellularLocations", [])
            if not isinstance(sub_locs, list):
                continue

            for loc_obj in sub_locs:
                if not isinstance(loc_obj, dict):
                    continue

                location = loc_obj.get("location", {})
                if isinstance(location, dict):
                    val = location.get("value", "")
                    if val and val not in locations:
                        locations.append(val)
                elif isinstance(location, str) and location not in locations:
                    locations.append(location)

            # Also check note/text
            note = comment.get("note", {})
            if isinstance(note, dict):
                note_texts = note.get("texts", [])
                if isinstance(note_texts, list):
                    for nt in note_texts:
                        if isinstance(nt, dict):
                            val = nt.get("value", "")
                            if val and val not in locations:
                                locations.append(val)

        return locations

    def _extract_disease_associations(self, entry: dict) -> list[dict]:
        """
        Extract disease associations from DISEASE comments.

        Each disease comment contains disease name, MIM reference,
        description, and evidence.
        """
        comments = entry.get("comments", [])
        if not isinstance(comments, list):
            return []

        diseases = []
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            if comment.get("commentType") != "DISEASE":
                continue

            disease_obj = comment.get("disease", {})
            if not isinstance(disease_obj, dict):
                continue

            disease_name = ""
            disease_id_val = ""
            description = ""

            # Disease name
            disease_name = disease_obj.get("diseaseId", "")
            if not isinstance(disease_name, str):
                disease_name = ""

            # Disease accession (MIM number)
            disease_acc = disease_obj.get("diseaseAccession", "")
            if isinstance(disease_acc, str):
                disease_id_val = disease_acc

            # Also check cross-reference for MIM
            dbref = disease_obj.get("diseaseCrossReference", {})
            if isinstance(dbref, dict):
                db_name = dbref.get("database", "")
                db_id = dbref.get("id", "")
                if db_name == "MIM" and db_id:
                    disease_id_val = db_id

            # Description from note
            note = comment.get("note", {})
            if isinstance(note, dict):
                note_texts = note.get("texts", [])
                if isinstance(note_texts, list):
                    desc_parts = []
                    for nt in note_texts:
                        if isinstance(nt, dict):
                            val = nt.get("value", "")
                            if val:
                                desc_parts.append(val)
                        elif isinstance(nt, str) and nt:
                            desc_parts.append(nt)
                    description = " ".join(desc_parts)

            # Direct text on the comment
            if not description:
                text_obj = comment.get("text", {})
                if isinstance(text_obj, dict):
                    description = text_obj.get("value", "")
                elif isinstance(text_obj, str):
                    description = text_obj

            # Abbreviation / full name from disease object
            disease_full_name = disease_obj.get("acronym", "")
            if not disease_name and disease_full_name:
                disease_name = disease_full_name

            # Evidence
            evidence = []
            ev_list = comment.get("evidences", [])
            if isinstance(ev_list, list):
                for ev in ev_list:
                    if isinstance(ev, dict):
                        ev_code = ev.get("evidenceCode", "")
                        if ev_code:
                            evidence.append(ev_code)

            if disease_name or disease_id_val:
                diseases.append({
                    "disease_name": disease_name,
                    "disease_id": disease_id_val,
                    "description": description[:500] if description else "",
                    "evidence": evidence,
                    "source": "UniProt",
                })

        return diseases

    def _extract_catalytic_activity(self, entry: dict) -> list[str]:
        """
        Extract catalytic activity descriptions from the entry.

        Stored in the _raw_comments from the parsed detail.
        """
        comments = entry.get("_raw_comments", [])
        if not isinstance(comments, list):
            return []

        activities = []
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            if comment.get("commentType") != "CATALYTIC ACTIVITY":
                continue

            reaction = comment.get("reaction", {})
            if isinstance(reaction, dict):
                name = reaction.get("name", "")
                if name:
                    activities.append(name)

        return activities

    def _extract_pathway(self, entry: dict) -> list[str]:
        """
        Extract pathway annotations from the entry.

        Stored in the _raw_comments from the parsed detail.
        """
        comments = entry.get("_raw_comments", [])
        if not isinstance(comments, list):
            return []

        pathways = []
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            if comment.get("commentType") != "PATHWAY":
                continue

            texts = comment.get("texts", [])
            if isinstance(texts, list):
                for text_obj in texts:
                    if isinstance(text_obj, dict):
                        val = text_obj.get("value", "")
                        if val:
                            pathways.append(val)
                    elif isinstance(text_obj, str) and text_obj:
                        pathways.append(text_obj)

        return pathways
