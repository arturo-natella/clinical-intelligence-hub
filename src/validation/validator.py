"""
Clinical Intelligence Hub — Pass 5: Clinical Validation Orchestrator

Coordinates all validation sources (OpenFDA, RxNorm, PubMed, DrugBank)
to cross-reference AI findings against validated clinical databases.

This is the single entry point for Pass 5 of the pipeline.
"""

import logging
from typing import Optional

from src.models import (
    AlertSeverity,
    ClinicalFlag,
    ClinicalTimeline,
    DrugInteraction,
    FindingCategory,
    LiteratureCitation,
    Medication,
    PatientProfile,
)

logger = logging.getLogger("CIH-Validator")


class ClinicalValidator:
    """
    Pass 5 orchestrator — validates AI findings against
    OpenFDA, RxNorm, PubMed, and DrugBank.

    Each validation source is optional: if a client can't be
    initialized (e.g., network down), the others still run.
    """

    def __init__(self, pubmed_api_key: str = None):
        self._openfda = None
        self._rxnorm = None
        self._pubmed = None
        self._drugbank = None
        self._setup_clients(pubmed_api_key)

    def validate(self, profile: PatientProfile) -> dict:
        """
        Run all Pass 5 validations against a patient profile.

        Returns:
            dict with keys:
              - drug_interactions: list[DrugInteraction]
              - adverse_events: list[ClinicalFlag]
              - literature: list[LiteratureCitation]
              - standardization: dict of medication/lab mappings
              - recalls: list[ClinicalFlag]
        """
        timeline = profile.clinical_timeline
        results = {
            "drug_interactions": [],
            "adverse_events": [],
            "literature": [],
            "standardization": {},
            "recalls": [],
        }

        logger.info("Pass 5: Starting clinical validation")

        # ── Step 1: Medication Standardization (RxNorm) ──────
        if self._rxnorm:
            results["standardization"] = self._standardize_medications(
                timeline.medications
            )

        # ── Step 2: Drug-Drug Interactions (DrugBank + RxNorm) ─
        if self._drugbank:
            med_dicts = [
                {"name": m.name, "status": m.status.value}
                for m in timeline.medications
            ]
            ddi = self._drugbank.check_interactions(med_dicts)
            results["drug_interactions"].extend(ddi)

            # Drug-gene interactions if genetics available
            if timeline.genetics:
                gen_dicts = [
                    {"gene": g.gene, "phenotype": g.phenotype or ""}
                    for g in timeline.genetics
                ]
                pgx = self._drugbank.check_drug_gene_interactions(
                    med_dicts, gen_dicts
                )
                results["drug_interactions"].extend(pgx)

        # ── Step 3: Adverse Event Screening (OpenFDA) ────────
        if self._openfda:
            ae_flags = self._screen_adverse_events(timeline.medications)
            results["adverse_events"].extend(ae_flags)

            recall_flags = self._check_recalls(timeline.medications)
            results["recalls"].extend(recall_flags)

        # ── Step 4: Literature Search (PubMed) ───────────────
        if self._pubmed:
            lit = self._search_literature(timeline)
            results["literature"].extend(lit)

        # Summary
        total_findings = (
            len(results["drug_interactions"])
            + len(results["adverse_events"])
            + len(results["literature"])
            + len(results["recalls"])
        )
        logger.info(
            f"Pass 5 complete: {total_findings} findings, "
            f"{len(results['standardization'])} medications standardized"
        )

        return results

    # ── Medication Standardization ────────────────────────────

    def _standardize_medications(
        self, medications: list[Medication]
    ) -> dict:
        """
        Resolve each medication through RxNorm to get
        standardized names, RxCUIs, and brand→generic mapping.
        """
        mapping = {}

        for med in medications:
            try:
                resolved = self._rxnorm.resolve_medication(med.name)
                if resolved:
                    mapping[med.name] = {
                        "rxcui": resolved.get("rxcui"),
                        "standardized_name": resolved.get("name", med.name),
                        "synonym": resolved.get("synonym"),
                        "term_type": resolved.get("tty"),
                    }
                    logger.debug(
                        f"Resolved '{med.name}' → "
                        f"'{resolved.get('name')}' (RxCUI: {resolved.get('rxcui')})"
                    )
            except Exception as e:
                logger.debug(f"Could not resolve '{med.name}': {e}")

        return mapping

    # ── Adverse Event Screening ───────────────────────────────

    def _screen_adverse_events(
        self, medications: list[Medication]
    ) -> list[ClinicalFlag]:
        """
        Screen active medications against OpenFDA FAERS for
        high-frequency adverse events.
        """
        flags = []

        active_meds = [
            m for m in medications
            if m.status.value in ("active", "prn", "unknown")
        ]

        for med in active_meds:
            events = self._openfda.get_adverse_events(med.name, limit=5)
            if not events:
                continue

            # Flag the top adverse event if it has significant reports
            top_event = events[0]
            if top_event.get("count", 0) >= 100:
                flags.append(ClinicalFlag(
                    category=FindingCategory.ADVERSE_EVENT,
                    severity=AlertSeverity.MODERATE,
                    title=f"{med.name}: Top FAERS adverse event",
                    description=(
                        f"Most reported adverse event for {med.name} is "
                        f"'{top_event['reaction']}' with "
                        f"{top_event['count']:,} reports in FDA FAERS. "
                        f"This does not mean the drug caused the reaction — "
                        f"it means patients on this drug reported it."
                    ),
                    evidence=[
                        f"OpenFDA FAERS: {top_event['count']:,} reports"
                    ],
                    source_pass="pass_5",
                ))

            # Check for boxed warning
            label = self._openfda.get_drug_label(med.name)
            if label and label.get("boxed_warning"):
                flags.append(ClinicalFlag(
                    category=FindingCategory.ADVERSE_EVENT,
                    severity=AlertSeverity.HIGH,
                    title=f"{med.name}: FDA boxed warning",
                    description=(
                        f"{med.name} has an FDA boxed warning "
                        f"(the most serious type of drug warning). "
                        f"Discuss with your prescribing provider."
                    ),
                    evidence=["OpenFDA Drug Label: Boxed Warning present"],
                    source_pass="pass_5",
                ))

        return flags

    # ── Drug Recall Check ─────────────────────────────────────

    def _check_recalls(
        self, medications: list[Medication]
    ) -> list[ClinicalFlag]:
        """Check for recent drug recalls on active medications."""
        flags = []

        active_meds = [
            m for m in medications
            if m.status.value in ("active", "prn", "unknown")
        ]

        for med in active_meds:
            recalls = self._openfda.check_drug_recalls(med.name, limit=3)
            for recall in recalls:
                severity = AlertSeverity.HIGH
                if recall.get("classification") == "Class I":
                    severity = AlertSeverity.CRITICAL

                flags.append(ClinicalFlag(
                    category=FindingCategory.ADVERSE_EVENT,
                    severity=severity,
                    title=f"{med.name}: FDA recall",
                    description=(
                        f"FDA {recall.get('classification', 'recall')} "
                        f"for {med.name}: "
                        f"{recall.get('reason', 'See FDA details')}. "
                        f"Status: {recall.get('status', 'Unknown')}."
                    ),
                    evidence=[
                        f"OpenFDA Enforcement: "
                        f"{recall.get('report_date', 'Unknown date')}"
                    ],
                    source_pass="pass_5",
                ))

        return flags

    # ── Literature Search ─────────────────────────────────────

    def _search_literature(
        self, timeline: ClinicalTimeline
    ) -> list[LiteratureCitation]:
        """
        Search PubMed for literature supporting clinical findings.

        Searches for:
        - Drug-drug interaction evidence (for each med pair)
        - Drug-condition evidence
        - Cross-disciplinary connections
        """
        citations = []
        seen_titles = set()

        # Drug-drug interaction literature
        active_meds = [
            m.name for m in timeline.medications
            if m.status.value in ("active", "prn", "unknown")
        ]

        if len(active_meds) >= 2:
            for i, drug_a in enumerate(active_meds[:5]):
                for drug_b in active_meds[i + 1:5]:
                    results = self._pubmed.search_interaction(drug_a, drug_b)
                    for citation in results:
                        if citation.title not in seen_titles:
                            seen_titles.add(citation.title)
                            citations.append(citation)

        # Drug-condition evidence for active medications
        active_diagnoses = [
            d.name for d in timeline.diagnoses
            if d.status and d.status.lower() in ("active", "chronic")
        ]

        for med_name in active_meds[:5]:
            for dx_name in active_diagnoses[:3]:
                results = self._pubmed.search_drug_evidence(
                    med_name, dx_name
                )
                for citation in results:
                    if citation.title not in seen_titles:
                        seen_titles.add(citation.title)
                        citations.append(citation)

        logger.info(
            f"PubMed search: {len(citations)} unique citations found"
        )
        return citations

    # ── Setup ─────────────────────────────────────────────────

    def _setup_clients(self, pubmed_api_key: str = None):
        """Initialize validation API clients."""
        try:
            from src.validation.openfda import OpenFDAClient
            self._openfda = OpenFDAClient()
        except Exception:
            logger.debug("OpenFDA client not available")

        try:
            from src.validation.rxnorm import RxNormClient
            self._rxnorm = RxNormClient()
        except Exception:
            logger.debug("RxNorm client not available")

        try:
            from src.validation.pubmed import PubMedClient
            self._pubmed = PubMedClient(api_key=pubmed_api_key)
        except Exception:
            logger.debug("PubMed client not available")

        try:
            from src.validation.drugbank import DrugInteractionChecker
            self._drugbank = DrugInteractionChecker()
        except Exception:
            logger.debug("DrugBank client not available")
