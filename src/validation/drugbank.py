"""
Clinical Intelligence Hub — Pass 5: DrugBank Drug Interaction Checking

Uses the NLM Drug Interaction API (same backend as DailyMed/DrugBank)
and OpenFDA drug labels to identify drug-drug interactions.

The NLM interaction API is free and public.
For deeper interaction data, DrugBank offers a paid API — this module
is structured to support both the free NLM API and a future DrugBank
API key if the user obtains one.
"""

import logging
from typing import Optional

from src.models import AlertSeverity, DrugInteraction

logger = logging.getLogger("CIH-DrugBank")


class DrugInteractionChecker:
    """
    Checks drug-drug interactions using RxNorm interaction API
    and OpenFDA drug label cross-referencing.
    """

    def __init__(self):
        self._rxnorm = None
        self._openfda = None
        self._setup_clients()

    def check_interactions(self, medications: list) -> list[DrugInteraction]:
        """
        Check for interactions among a list of medications.

        Args:
            medications: List of medication dicts or Medication models

        Returns:
            List of DrugInteraction models
        """
        interactions = []

        # Extract medication names
        med_names = []
        for med in medications:
            name = (med.get("name", "") if isinstance(med, dict)
                    else getattr(med, "name", ""))
            status = (med.get("status", "") if isinstance(med, dict)
                      else getattr(med, "status", ""))
            if name and str(status).lower() in ("active", "prn", "unknown", ""):
                med_names.append(name)

        if len(med_names) < 2:
            return []

        logger.info(f"Checking interactions among {len(med_names)} medications")

        # Method 1: RxNorm interaction API
        if self._rxnorm:
            rxnorm_interactions = self._check_via_rxnorm(med_names)
            interactions.extend(rxnorm_interactions)

        # Method 2: OpenFDA label cross-reference
        if self._openfda:
            openfda_interactions = self._openfda.validate_drug_interactions(med_names)
            # Deduplicate against RxNorm results
            existing_pairs = {
                (i.drug_a.lower(), (i.drug_b or "").lower())
                for i in interactions
            }
            for interaction in openfda_interactions:
                pair = (interaction.drug_a.lower(), (interaction.drug_b or "").lower())
                reverse_pair = (pair[1], pair[0])
                if pair not in existing_pairs and reverse_pair not in existing_pairs:
                    interactions.append(interaction)

        logger.info(f"Found {len(interactions)} drug interactions")
        return interactions

    def check_drug_gene_interactions(self, medications: list,
                                      genetics: list) -> list[DrugInteraction]:
        """
        Check for drug-gene (pharmacogenomic) interactions.

        Uses known pharmacogenomic relationships to flag medications
        that may be affected by the patient's genetic variants.
        """
        interactions = []

        # Known pharmacogenomic relationships
        # This is a curated subset — full PharmGKB integration is in monitoring
        pgx_map = {
            "CYP2D6": {
                "poor_metabolizer": [
                    "codeine", "tramadol", "tamoxifen", "metoprolol",
                    "fluoxetine", "paroxetine", "venlafaxine", "aripiprazole",
                ],
                "ultrarapid_metabolizer": [
                    "codeine", "tramadol",
                ],
            },
            "CYP2C19": {
                "poor_metabolizer": [
                    "clopidogrel", "omeprazole", "pantoprazole",
                    "escitalopram", "citalopram", "voriconazole",
                ],
            },
            "CYP2C9": {
                "poor_metabolizer": [
                    "warfarin", "phenytoin", "celecoxib", "fluvastatin",
                ],
            },
            "VKORC1": {
                "increased_sensitivity": [
                    "warfarin",
                ],
            },
            "HLA-B*5701": {
                "positive": [
                    "abacavir",
                ],
            },
            "SLCO1B1": {
                "decreased_function": [
                    "simvastatin", "atorvastatin", "rosuvastatin",
                ],
            },
        }

        med_names_lower = set()
        for med in medications:
            name = (med.get("name", "") if isinstance(med, dict)
                    else getattr(med, "name", ""))
            if name:
                med_names_lower.add(name.lower())

        for variant in genetics:
            gene = (variant.get("gene", "") if isinstance(variant, dict)
                    else getattr(variant, "gene", ""))
            phenotype = (variant.get("phenotype", "") if isinstance(variant, dict)
                         else getattr(variant, "phenotype", ""))

            if not gene:
                continue

            # Check if this gene has known PGx relationships
            gene_data = pgx_map.get(gene, {})

            for phenotype_key, affected_drugs in gene_data.items():
                # Check if patient's phenotype matches
                if phenotype and phenotype_key.replace("_", " ") in phenotype.lower():
                    for drug in affected_drugs:
                        if drug in med_names_lower:
                            interactions.append(DrugInteraction(
                                drug_a=drug.title(),
                                gene=gene,
                                severity=AlertSeverity.HIGH,
                                description=(
                                    f"Patient has {gene} {phenotype} variant. "
                                    f"{drug.title()} metabolism may be significantly "
                                    f"affected. Dose adjustment may be needed."
                                ),
                                source="PharmGKB (curated)",
                            ))

        return interactions

    # ── Setup ───────────────────────────────────────────────

    def _setup_clients(self):
        """Initialize API clients."""
        try:
            from src.validation.rxnorm import RxNormClient
            self._rxnorm = RxNormClient()
        except Exception:
            logger.debug("RxNorm client not available")

        try:
            from src.validation.openfda import OpenFDAClient
            self._openfda = OpenFDAClient()
        except Exception:
            logger.debug("OpenFDA client not available")

    def _check_via_rxnorm(self, med_names: list[str]) -> list[DrugInteraction]:
        """Check interactions via RxNorm interaction API."""
        interactions = []

        # Resolve RxCUIs
        rxcuis = []
        name_to_rxcui = {}
        for name in med_names:
            resolved = self._rxnorm.resolve_medication(name)
            if resolved and resolved.get("rxcui"):
                rxcuis.append(resolved["rxcui"])
                name_to_rxcui[resolved["rxcui"]] = name

        if len(rxcuis) < 2:
            return []

        # Check pairwise interactions
        raw_interactions = self._rxnorm.check_pairwise_interactions(rxcuis)

        for raw in raw_interactions:
            drug_names = raw.get("drugs", [])
            description = raw.get("description", "")
            severity_str = raw.get("severity", "").lower()

            # Map severity
            if "high" in severity_str or "severe" in severity_str:
                severity = AlertSeverity.CRITICAL
            elif "moderate" in severity_str:
                severity = AlertSeverity.HIGH
            else:
                severity = AlertSeverity.MODERATE

            drug_a = drug_names[0] if len(drug_names) > 0 else "Unknown"
            drug_b = drug_names[1] if len(drug_names) > 1 else None

            interactions.append(DrugInteraction(
                drug_a=drug_a,
                drug_b=drug_b,
                severity=severity,
                description=description,
                source=f"NLM Drug Interaction API ({raw.get('source', '')})",
            ))

        return interactions
