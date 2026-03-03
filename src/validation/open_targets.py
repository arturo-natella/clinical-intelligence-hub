"""
Clinical Intelligence Hub -- Open Targets Platform

Integrates 23 public data sources to build evidence chains linking
diseases to drug targets to therapeutics.  Open Targets aggregates:

  - Genetic associations (GWAS, UniProt, Gene2Phenotype, ClinGen)
  - Known drugs (ChEMBL, FDA clinical trials, DailyMed)
  - Pathways (Reactome, Gene Ontology)
  - Animal models (PhenoDigm, IMPC)
  - Literature mining (EuropePMC, EPMC NLP)
  - Somatic mutations (COSMIC, IntOGen, cancer biomarkers)

For a given disease the platform answers: "What genes are involved, how
strong is the evidence, and which drugs already target them?"  This is
uniquely valuable for cross-disciplinary analysis -- it connects
genetics, pharmacology, and clinical evidence in a single scored graph.

API: https://api.platform.opentargets.org/api/v4/graphql (GraphQL)
Docs: https://platform-docs.opentargets.org/data-access/graphql-api
License: CC0 1.0 Universal -- completely open, no key required.
"""

import json
import logging
from typing import Optional

from src.validation._http import api_get, api_post

logger = logging.getLogger("CIH-OpenTargets")

OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"


class OpenTargetsClient:
    """Open Targets Platform GraphQL client for disease-target-drug evidence."""

    # ── GraphQL Transport ────────────────────────────────────

    def _query(
        self, graphql_query: str, variables: dict = None
    ) -> Optional[dict]:
        """
        Execute a GraphQL query against the Open Targets API.

        Args:
            graphql_query: GraphQL query string.
            variables: Optional variable mapping for parameterized queries.

        Returns:
            Parsed ``data`` dict from the GraphQL response, or None on failure.
        """
        payload = {"query": graphql_query}
        if variables:
            payload["variables"] = variables

        try:
            response = api_post(
                OT_GRAPHQL,
                body=json.dumps(payload).encode("utf-8"),
                content_type="application/json",
                timeout=20,
            )
            if not response:
                return None

            # GraphQL errors are returned inside the response body
            if response.get("errors"):
                msgs = [e.get("message", "") for e in response["errors"]]
                logger.debug(
                    "Open Targets GraphQL errors: %s", "; ".join(msgs)
                )
                # Some queries return partial data alongside errors
                if not response.get("data"):
                    return None

            return response.get("data")

        except Exception as e:
            logger.debug("Open Targets GraphQL query failed: %s", e)
            return None

    # ── Disease Search ───────────────────────────────────────

    def search_disease(
        self, disease_name: str, limit: int = 10
    ) -> list[dict]:
        """
        Search for diseases by name, returning EFO IDs and descriptions.

        Uses the platform-wide search endpoint filtered to disease entities.

        Args:
            disease_name: Disease or condition name (e.g. "lupus", "Crohn's disease")
            limit: Maximum number of results
        """
        query = """
        query SearchDisease($name: String!, $size: Int!) {
          search(queryString: $name, entityNames: ["disease"], page: {size: $size, index: 0}) {
            hits {
              id
              name
              description
              entity
            }
          }
        }
        """

        data = self._query(query, {"name": disease_name, "size": limit})
        if not data:
            return []

        hits = (
            data.get("search", {}).get("hits") or []
        )

        results = []
        for hit in hits:
            results.append({
                "disease_id": hit.get("id", ""),
                "name": hit.get("name", ""),
                "description": (hit.get("description") or "")[:500],
                "entity": hit.get("entity", ""),
                "source": "Open Targets Platform",
            })

        return results

    # ── Disease -> Targets ───────────────────────────────────

    def get_disease_targets(
        self, disease_id: str, limit: int = 20
    ) -> list[dict]:
        """
        Get the top gene targets associated with a disease.

        Returns targets ranked by overall association score, with per-datatype
        breakdowns (genetic_association, known_drug, literature, etc.).

        Args:
            disease_id: EFO disease ID (e.g. "EFO_0000270" for asthma)
            limit: Maximum number of targets
        """
        query = """
        query DiseaseTargets($efoId: String!, $size: Int!) {
          disease(efoId: $efoId) {
            associatedTargets(page: {size: $size, index: 0}) {
              rows {
                target {
                  id
                  approvedSymbol
                  approvedName
                }
                score
                datatypeScores {
                  id
                  score
                }
              }
            }
          }
        }
        """

        data = self._query(query, {"efoId": disease_id, "size": limit})
        if not data:
            return []

        rows = (
            data.get("disease", {})
            .get("associatedTargets", {})
            .get("rows") or []
        )

        results = []
        for row in rows:
            target = row.get("target", {})
            datatype_scores = row.get("datatypeScores") or []

            evidence_types = {}
            for dt in datatype_scores:
                dt_id = dt.get("id", "")
                dt_score = dt.get("score", 0)
                if dt_score > 0:
                    evidence_types[dt_id] = round(dt_score, 4)

            results.append({
                "target_id": target.get("id", ""),
                "gene_symbol": target.get("approvedSymbol", ""),
                "gene_name": target.get("approvedName", ""),
                "overall_score": round(row.get("score", 0), 4),
                "evidence_types": evidence_types,
                "source": "Open Targets Platform",
            })

        return results

    # ── Disease -> Drugs ─────────────────────────────────────

    def get_disease_drugs(
        self, disease_id: str, limit: int = 20
    ) -> list[dict]:
        """
        Get known drugs for a disease with clinical trial phase and mechanism.

        Args:
            disease_id: EFO disease ID
            limit: Maximum number of drug entries
        """
        query = """
        query DiseaseDrugs($efoId: String!, $size: Int!) {
          disease(efoId: $efoId) {
            knownDrugs(size: $size) {
              rows {
                drug {
                  id
                  name
                }
                phase
                mechanismOfAction
                status
                urls {
                  niceName
                  url
                }
              }
            }
          }
        }
        """

        data = self._query(query, {"efoId": disease_id, "size": limit})
        if not data:
            return []

        rows = (
            data.get("disease", {})
            .get("knownDrugs", {})
            .get("rows") or []
        )

        results = []
        for row in rows:
            drug = row.get("drug") or {}
            urls = row.get("urls") or []
            references = [
                {"name": u.get("niceName", ""), "url": u.get("url", "")}
                for u in urls
                if u.get("url")
            ]

            results.append({
                "drug_name": drug.get("name", ""),
                "drug_id": drug.get("id", ""),
                "phase": row.get("phase"),
                "mechanism_of_action": row.get("mechanismOfAction", ""),
                "approval_status": row.get("status", ""),
                "references": references,
                "source": "Open Targets Platform",
            })

        return results

    # ── Target (gene) -> Drugs ───────────────────────────────

    def get_target_drugs(
        self, gene_symbol: str, limit: int = 20
    ) -> list[dict]:
        """
        Get drugs that target a specific gene.

        First resolves the gene symbol to an Ensembl ID via the search
        endpoint, then queries knownDrugs for that target.

        Args:
            gene_symbol: HGNC gene symbol (e.g. "BRCA1", "EGFR", "TNF")
            limit: Maximum number of drug entries
        """
        # Step 1: Resolve gene symbol to Ensembl target ID
        search_query = """
        query SearchTarget($symbol: String!) {
          search(queryString: $symbol, entityNames: ["target"], page: {size: 1, index: 0}) {
            hits {
              id
              name
            }
          }
        }
        """

        search_data = self._query(search_query, {"symbol": gene_symbol})
        if not search_data:
            return []

        hits = (
            search_data.get("search", {}).get("hits") or []
        )
        if not hits:
            logger.debug(
                "Open Targets: no target found for gene symbol '%s'",
                gene_symbol,
            )
            return []

        target_id = hits[0].get("id", "")
        if not target_id:
            return []

        # Step 2: Get drugs for this target
        drugs_query = """
        query TargetDrugs($ensemblId: String!, $size: Int!) {
          target(ensemblId: $ensemblId) {
            approvedSymbol
            knownDrugs(size: $size) {
              rows {
                drug {
                  id
                  name
                }
                phase
                mechanismOfAction
                status
                disease {
                  id
                  name
                }
                urls {
                  niceName
                  url
                }
              }
            }
          }
        }
        """

        data = self._query(
            drugs_query, {"ensemblId": target_id, "size": limit}
        )
        if not data:
            return []

        target_info = data.get("target") or {}
        rows = (
            target_info.get("knownDrugs", {}).get("rows") or []
        )

        results = []
        for row in rows:
            drug = row.get("drug") or {}
            disease = row.get("disease") or {}
            urls = row.get("urls") or []
            references = [
                {"name": u.get("niceName", ""), "url": u.get("url", "")}
                for u in urls
                if u.get("url")
            ]

            results.append({
                "drug_name": drug.get("name", ""),
                "drug_id": drug.get("id", ""),
                "phase": row.get("phase"),
                "mechanism_of_action": row.get("mechanismOfAction", ""),
                "approval_status": row.get("status", ""),
                "disease_name": disease.get("name", ""),
                "disease_id": disease.get("id", ""),
                "target_symbol": target_info.get("approvedSymbol", gene_symbol),
                "target_id": target_id,
                "references": references,
                "source": "Open Targets Platform",
            })

        return results

    # ── Disease-Target Evidence ──────────────────────────────

    def get_evidence(
        self, disease_id: str, target_id: str, limit: int = 10
    ) -> list[dict]:
        """
        Get individual evidence items linking a specific disease-target pair.

        Each evidence item comes from one of Open Targets' 23 data sources
        and includes a score, type classification, and literature references.

        Args:
            disease_id: EFO disease ID
            target_id: Ensembl gene/target ID
            limit: Maximum number of evidence items
        """
        query = """
        query Evidence($ensemblId: String!, $efoId: String!, $size: Int!) {
          disease(efoId: $efoId) {
            evidences(ensemblIds: [$ensemblId], size: $size) {
              rows {
                id
                score
                datasourceId
                datatypeId
                literature
                targetFromSourceId
                diseaseFromSourceMappedId
              }
            }
          }
        }
        """

        data = self._query(
            query,
            {"ensemblId": target_id, "efoId": disease_id, "size": limit},
        )
        if not data:
            return []

        rows = (
            data.get("disease", {})
            .get("evidences", {})
            .get("rows") or []
        )

        results = []
        for row in rows:
            pmids = row.get("literature") or []
            literature_refs = [
                f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"
                for pmid in pmids
                if pmid
            ]

            results.append({
                "evidence_id": row.get("id", ""),
                "score": round(row.get("score", 0), 4),
                "data_source": row.get("datasourceId", ""),
                "evidence_type": row.get("datatypeId", ""),
                "target_from_source": row.get("targetFromSourceId", ""),
                "disease_from_source": row.get("diseaseFromSourceMappedId", ""),
                "literature_refs": literature_refs,
                "source": "Open Targets Platform",
            })

        return results

    # ── Convenience Pipeline ─────────────────────────────────

    def disease_to_drug_pipeline(self, disease_name: str) -> dict:
        """
        High-level convenience method: disease name -> targets + drugs.

        Chains three queries: search disease, get top targets, get known drugs.
        Returns a single summary dict suitable for report integration.

        Args:
            disease_name: Human-readable disease name (e.g. "Parkinson's disease")
        """
        result = {
            "query": disease_name,
            "disease_name": None,
            "disease_id": None,
            "top_targets": [],
            "known_drugs": [],
            "evidence_summary": {},
            "source": "Open Targets Platform",
        }

        # Step 1: Find the disease
        diseases = self.search_disease(disease_name, limit=1)
        if not diseases:
            logger.debug(
                "Open Targets pipeline: no disease found for '%s'",
                disease_name,
            )
            return result

        disease = diseases[0]
        disease_id = disease["disease_id"]
        result["disease_name"] = disease["name"]
        result["disease_id"] = disease_id

        # Step 2: Get top associated targets
        targets = self.get_disease_targets(disease_id, limit=10)
        result["top_targets"] = [
            {
                "gene_symbol": t["gene_symbol"],
                "gene_name": t["gene_name"],
                "overall_score": t["overall_score"],
                "evidence_types": t["evidence_types"],
            }
            for t in targets
        ]

        # Step 3: Get known drugs
        drugs = self.get_disease_drugs(disease_id, limit=20)
        result["known_drugs"] = [
            {
                "drug_name": d["drug_name"],
                "drug_id": d["drug_id"],
                "phase": d["phase"],
                "mechanism_of_action": d["mechanism_of_action"],
                "approval_status": d["approval_status"],
            }
            for d in drugs
        ]

        # Build evidence summary
        evidence_type_counts: dict[str, int] = {}
        for t in targets:
            for etype in t.get("evidence_types", {}):
                evidence_type_counts[etype] = (
                    evidence_type_counts.get(etype, 0) + 1
                )

        max_phase = None
        for d in drugs:
            phase = d.get("phase")
            if phase is not None:
                if max_phase is None or phase > max_phase:
                    max_phase = phase

        result["evidence_summary"] = {
            "total_targets": len(targets),
            "total_drugs": len(drugs),
            "evidence_type_counts": evidence_type_counts,
            "max_clinical_phase": max_phase,
        }

        return result
