"""
Clinical Intelligence Hub — Pass 5: Clinical Validation Orchestrator

Coordinates all validation sources to cross-reference AI findings
against validated clinical databases:

  Original 4:
  - OpenFDA: Adverse events, drug labels, recalls
  - RxNorm: Medication standardization
  - PubMed: Literature citations
  - DrugBank: Drug-drug and drug-gene interactions

  Terminology (3):
  - SNOMED CT: Clinical terminology validation
  - MeSH: Medical vocabulary validation
  - ICD-11: WHO disease classification codes

  Trials + Rare Disease (5):
  - ClinicalTrials.gov: Active clinical trials
  - OMIM: Genetic/rare disease data
  - Orphanet: European rare disease database
  - GARD: NIH rare disease information
  - HPO: Human Phenotype Ontology (symptom→disease mapping)

  Drug & Treatment (5):
  - DailyMed: FDA drug labels/package inserts
  - DDinter: Drug-drug interaction severity
  - PharmGKB: Pharmacogenomics annotations
  - PubChem: Drug mechanisms & targets
  - SIDER: Side effect frequencies

  Genetics & Molecular (5):
  - ClinVar: Variant pathogenicity interpretation
  - dbSNP: Genetic variant references
  - gnomAD: Variant population frequencies
  - DisGeNET: Disease-gene associations
  - BioGRID: Protein-protein interactions

  Cross-Reference (3):
  - Open Targets: Disease→target→drug evidence
  - UMLS: Cross-vocabulary mapping
  - LOINC: Lab test standardization

  Protein Function (1):
  - UniProt: Protein function & disease associations

Total: 26 data sources.

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
    Pass 5 orchestrator — validates AI findings against 26 clinical
    databases. Each source is optional: if a client can't be initialized
    (e.g., network down, missing API key), the others still run.
    """

    def __init__(
        self,
        pubmed_api_key: str = None,
        omim_api_key: str = None,
        icd11_client_id: str = None,
        icd11_client_secret: str = None,
        umls_api_key: str = None,
        biogrid_api_key: str = None,
        disgenet_api_key: str = None,
        loinc_username: str = None,
        loinc_password: str = None,
    ):
        # Original 4 clients
        self._openfda = None
        self._rxnorm = None
        self._pubmed = None
        self._drugbank = None

        # Terminology (3)
        self._snomed = None
        self._mesh = None
        self._icd11 = None

        # Trials + Rare Disease (5)
        self._clinical_trials = None
        self._omim = None
        self._orphanet = None
        self._gard = None
        self._hpo = None

        # Drug & Treatment (5)
        self._dailymed = None
        self._ddinter = None
        self._pharmgkb = None
        self._pubchem = None
        self._sider = None

        # Genetics & Molecular (5)
        self._clinvar = None
        self._dbsnp = None
        self._gnomad = None
        self._disgenet = None
        self._biogrid = None

        # Cross-Reference (3)
        self._open_targets = None
        self._umls = None
        self._loinc = None

        # Protein Function (1)
        self._uniprot = None

        self._setup_clients(
            pubmed_api_key=pubmed_api_key,
            omim_api_key=omim_api_key,
            icd11_client_id=icd11_client_id,
            icd11_client_secret=icd11_client_secret,
            umls_api_key=umls_api_key,
            biogrid_api_key=biogrid_api_key,
            disgenet_api_key=disgenet_api_key,
            loinc_username=loinc_username,
            loinc_password=loinc_password,
        )

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
              - terminology: dict of term→SNOMED/MeSH/ICD-11 validations
              - clinical_trials: list[dict] of relevant active trials
              - rare_disease: dict of OMIM/Orphanet/GARD/HPO enrichment
              - drug_labels: dict of DailyMed + SIDER enrichment
              - interaction_severity: list[dict] of DDinter severity analysis
              - pharmacogenomics: list[dict] of PharmGKB annotations
              - mechanisms: dict of PubChem + Open Targets findings
              - genetic_variants: dict of ClinVar + dbSNP + gnomAD analysis
              - disease_network: dict of DisGeNET + BioGRID + UniProt
              - cross_vocabulary: dict of UMLS + LOINC mappings
        """
        timeline = profile.clinical_timeline
        results = {
            "drug_interactions": [],
            "adverse_events": [],
            "literature": [],
            "standardization": {},
            "recalls": [],
            "terminology": {},
            "clinical_trials": [],
            "rare_disease": {},
            "drug_labels": {},
            "interaction_severity": [],
            "pharmacogenomics": [],
            "mechanisms": {},
            "genetic_variants": {},
            "disease_network": {},
            "cross_vocabulary": {},
        }

        logger.info("Pass 5: Starting clinical validation (26 sources)")

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

        # ── Step 5: Terminology Validation (SNOMED + MeSH + ICD-11) ─
        results["terminology"] = self._validate_terminology(timeline)

        # ── Step 6: Clinical Trials Search ───────────────────
        if self._clinical_trials:
            results["clinical_trials"] = self._search_clinical_trials(timeline)

        # ── Step 7: Rare Disease Enrichment (OMIM + Orphanet + GARD + HPO)
        results["rare_disease"] = self._enrich_rare_disease(timeline)

        # ── Step 8: Drug Label Enrichment (DailyMed + SIDER) ─
        results["drug_labels"] = self._enrich_drug_labels(timeline)

        # ── Step 9: Interaction Severity Analysis (DDinter) ──
        if self._ddinter:
            results["interaction_severity"] = self._analyze_interaction_severity(
                timeline.medications
            )

        # ── Step 10: Pharmacogenomics (PharmGKB) ─────────────
        if self._pharmgkb:
            results["pharmacogenomics"] = self._analyze_pharmacogenomics(
                timeline
            )

        # ── Step 11: Drug Mechanisms & Targets (PubChem + Open Targets) ─
        results["mechanisms"] = self._analyze_drug_mechanisms(timeline)

        # ── Step 12: Genetic Variant Analysis (ClinVar + dbSNP + gnomAD)
        results["genetic_variants"] = self._analyze_genetic_variants(timeline)

        # ── Step 13: Disease-Gene Network (DisGeNET + BioGRID + UniProt)
        results["disease_network"] = self._build_disease_network(timeline)

        # ── Step 14: Cross-Vocabulary Mapping (UMLS + LOINC) ─
        results["cross_vocabulary"] = self._map_cross_vocabulary(timeline)

        # Summary
        total_findings = (
            len(results["drug_interactions"])
            + len(results["adverse_events"])
            + len(results["literature"])
            + len(results["recalls"])
            + len(results["clinical_trials"])
            + len(results["interaction_severity"])
            + len(results["pharmacogenomics"])
        )
        total_enrichments = (
            len(results["standardization"])
            + len(results["terminology"])
            + len(results["rare_disease"])
            + len(results["drug_labels"])
            + len(results["mechanisms"])
            + len(results["genetic_variants"])
            + len(results["disease_network"])
            + len(results["cross_vocabulary"])
        )
        logger.info(
            f"Pass 5 complete: {total_findings} findings, "
            f"{total_enrichments} enrichments across 26 sources"
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

    # ── Terminology Validation ──────────────────────────────────

    def _validate_terminology(self, timeline: ClinicalTimeline) -> dict:
        """
        Validate diagnoses and symptoms against SNOMED CT, MeSH, and ICD-11.

        Returns dict mapping term names to validation results from each source.
        """
        validations = {}

        # Collect terms to validate (diagnoses + top symptoms)
        terms_to_check = []
        for dx in timeline.diagnoses:
            if dx.status and dx.status.lower() not in ("resolved", "historical"):
                terms_to_check.append(("diagnosis", dx.name))

        for symptom in getattr(timeline, "symptoms", []) or []:
            sname = getattr(symptom, "symptom_name", None)
            if sname:
                terms_to_check.append(("symptom", sname))

        for term_type, term_name in terms_to_check[:20]:  # Cap at 20
            entry = {"term": term_name, "type": term_type, "validations": {}}

            if self._snomed:
                try:
                    if term_type == "diagnosis":
                        result = self._snomed.validate_disease(term_name)
                    else:
                        result = self._snomed.validate_symptom(term_name)
                    if result:
                        entry["validations"]["snomed"] = {
                            "concept_id": result.get("concept_id"),
                            "preferred_term": result.get("preferred_term"),
                            "source": "SNOMED CT",
                        }
                except Exception as e:
                    logger.debug(f"SNOMED validation failed for '{term_name}': {e}")

            if self._icd11 and term_type == "diagnosis":
                try:
                    result = self._icd11.validate_diagnosis(term_name)
                    if result:
                        entry["validations"]["icd11"] = {
                            "code": result.get("icd11_code"),
                            "title": result.get("title"),
                            "source": "WHO ICD-11",
                        }
                except Exception as e:
                    logger.debug(f"ICD-11 validation failed for '{term_name}': {e}")

            if self._mesh:
                try:
                    result = self._mesh.validate_term(term_name)
                    if result:
                        entry["validations"]["mesh"] = {
                            "uid": result.get("mesh_uid"),
                            "label": result.get("preferred_label"),
                            "category": result.get("category"),
                            "source": "NLM MeSH",
                        }
                except Exception as e:
                    logger.debug(f"MeSH validation failed for '{term_name}': {e}")

            if entry["validations"]:
                validations[term_name] = entry

        logger.info(
            f"Terminology validation: {len(validations)}/{len(terms_to_check)} "
            f"terms validated"
        )
        return validations

    # ── Clinical Trials Search ────────────────────────────────

    def _search_clinical_trials(
        self, timeline: ClinicalTimeline
    ) -> list[dict]:
        """
        Search ClinicalTrials.gov for active trials relevant
        to the patient's conditions.
        """
        trials = []
        seen_ncts = set()

        active_diagnoses = [
            d.name for d in timeline.diagnoses
            if d.status and d.status.lower() in ("active", "chronic")
        ]

        for dx_name in active_diagnoses[:5]:  # Top 5 conditions
            try:
                results = self._clinical_trials.search_condition(
                    dx_name, limit=5, recruiting_only=True
                )
                for trial in results:
                    nct = trial.get("nct_id")
                    if nct and nct not in seen_ncts:
                        seen_ncts.add(nct)
                        trial["matched_condition"] = dx_name
                        trials.append(trial)
            except Exception as e:
                logger.debug(f"ClinicalTrials.gov search failed for '{dx_name}': {e}")

        logger.info(f"Clinical trials: {len(trials)} active trials found")
        return trials

    # ── Rare Disease Enrichment ──────────────────────────────

    def _enrich_rare_disease(self, timeline: ClinicalTimeline) -> dict:
        """
        Enrich diagnoses with rare disease data from OMIM, Orphanet,
        GARD, and HPO.

        Looks up each diagnosis across all four rare disease databases
        and returns consolidated information.
        """
        enrichments = {}

        active_diagnoses = [
            d.name for d in timeline.diagnoses
            if d.status and d.status.lower() not in ("resolved", "historical")
        ]

        for dx_name in active_diagnoses[:10]:
            entry = {"diagnosis": dx_name, "databases": {}}

            # OMIM — genetic disease data
            if self._omim:
                try:
                    results = self._omim.search(dx_name, limit=3)
                    if results:
                        best = results[0]
                        entry["databases"]["omim"] = {
                            "mim_number": best.get("mim_number"),
                            "title": best.get("title"),
                            "genes": best.get("genes", []),
                            "url": best.get("url"),
                            "source": "OMIM",
                        }
                except Exception as e:
                    logger.debug(f"OMIM lookup failed for '{dx_name}': {e}")

            # Orphanet — rare disease classification
            if self._orphanet:
                try:
                    results = self._orphanet.search(dx_name, limit=3)
                    if results:
                        best = results[0]
                        orpha_code = best.get("orpha_code")
                        db_entry = {
                            "orpha_code": orpha_code,
                            "name": best.get("name"),
                            "url": best.get("url"),
                            "source": "Orphanet",
                        }

                        # Try to get prevalence data
                        if orpha_code:
                            prev = self._orphanet.get_prevalence(orpha_code)
                            if prev:
                                db_entry["prevalence"] = prev[:3]

                        entry["databases"]["orphanet"] = db_entry
                except Exception as e:
                    logger.debug(f"Orphanet lookup failed for '{dx_name}': {e}")

            # GARD — NIH rare disease info + cross-references
            if self._gard:
                try:
                    result = self._gard.validate_rare_disease(dx_name)
                    if result:
                        entry["databases"]["gard"] = {
                            "gard_id": result.get("gard_id"),
                            "name": result.get("name"),
                            "synonyms": result.get("synonyms", []),
                            "url": result.get("url"),
                            "source": "NIH GARD",
                        }
                except Exception as e:
                    logger.debug(f"GARD lookup failed for '{dx_name}': {e}")

            # HPO — phenotype mapping (what symptoms are expected)
            if self._hpo:
                try:
                    pheno = self._hpo.validate_phenotype(dx_name)
                    if pheno:
                        entry["databases"]["hpo"] = {
                            "hpo_id": pheno.get("hpo_id"),
                            "name": pheno.get("name"),
                            "definition": pheno.get("definition"),
                            "source": "HPO",
                        }
                except Exception as e:
                    logger.debug(f"HPO lookup failed for '{dx_name}': {e}")

            if entry["databases"]:
                enrichments[dx_name] = entry

        logger.info(
            f"Rare disease enrichment: {len(enrichments)} diagnoses enriched"
        )
        return enrichments

    # ── Drug Label Enrichment (DailyMed + SIDER) ─────────────

    def _enrich_drug_labels(self, timeline: ClinicalTimeline) -> dict:
        """
        Enrich active medications with FDA label data (DailyMed) and
        side effect frequencies (SIDER).
        """
        labels = {}
        active_meds = [
            m for m in timeline.medications
            if m.status.value in ("active", "prn", "unknown")
        ]

        for med in active_meds[:10]:
            entry = {"drug": med.name, "sources": {}}

            if self._dailymed:
                try:
                    label = self._dailymed.get_label(med.name)
                    if label:
                        entry["sources"]["dailymed"] = {
                            "warnings": self._dailymed.get_warnings(med.name),
                            "contraindications": self._dailymed.get_contraindications(med.name),
                            "interactions": self._dailymed.get_drug_interactions(med.name),
                            "source": "DailyMed (NLM)",
                        }
                except Exception as e:
                    logger.debug(f"DailyMed failed for '{med.name}': {e}")

            if self._sider:
                try:
                    side_effects = self._sider.search_drug_side_effects(
                        med.name, limit=15
                    )
                    if side_effects:
                        entry["sources"]["sider"] = {
                            "side_effects": side_effects,
                            "source": "SIDER",
                        }
                except Exception as e:
                    logger.debug(f"SIDER failed for '{med.name}': {e}")

            if entry["sources"]:
                labels[med.name] = entry

        # Multi-drug side effect overlap (SIDER)
        if self._sider and len(active_meds) >= 2:
            try:
                drug_names = [m.name for m in active_meds[:10]]
                overlap = self._sider.check_side_effects(drug_names)
                if overlap:
                    labels["_shared_side_effects"] = overlap
            except Exception as e:
                logger.debug(f"SIDER overlap check failed: {e}")

        return labels

    # ── Interaction Severity Analysis (DDinter) ──────────────

    def _analyze_interaction_severity(
        self, medications: list[Medication]
    ) -> list[dict]:
        """
        Check all medication pairs through DDinter for severity-ranked
        drug-drug interactions.
        """
        active_meds = [
            m.name for m in medications
            if m.status.value in ("active", "prn", "unknown")
        ]

        if len(active_meds) < 2:
            return []

        try:
            return self._ddinter.check_prescription(active_meds)
        except Exception as e:
            logger.debug(f"DDinter prescription check failed: {e}")
            return []

    # ── Pharmacogenomics (PharmGKB) ──────────────────────────

    def _analyze_pharmacogenomics(
        self, timeline: ClinicalTimeline
    ) -> list[dict]:
        """
        Look up pharmacogenomic annotations for active medications.
        If genetics data is available, cross-reference drug-gene relationships.
        """
        results = []
        active_meds = [
            m for m in timeline.medications
            if m.status.value in ("active", "prn", "unknown")
        ]

        for med in active_meds[:10]:
            try:
                annotations = self._pharmgkb.get_clinical_annotations(med.name)
                if annotations:
                    results.append({
                        "drug": med.name,
                        "annotations": annotations[:5],
                        "source": "PharmGKB",
                    })
            except Exception as e:
                logger.debug(f"PharmGKB failed for '{med.name}': {e}")

        # Cross-reference with patient genetics if available
        if timeline.genetics:
            for gen in timeline.genetics[:10]:
                gene_name = gen.gene
                if not gene_name:
                    continue
                try:
                    rels = self._pharmgkb.get_drug_gene_relationships(gene_name)
                    if rels:
                        results.append({
                            "gene": gene_name,
                            "drug_relationships": rels[:5],
                            "source": "PharmGKB",
                        })
                except Exception as e:
                    logger.debug(f"PharmGKB gene lookup failed for '{gene_name}': {e}")

        return results

    # ── Drug Mechanisms & Targets (PubChem + Open Targets) ───

    def _analyze_drug_mechanisms(self, timeline: ClinicalTimeline) -> dict:
        """
        Look up drug mechanisms of action (PubChem) and disease→drug
        evidence pipelines (Open Targets).
        """
        mechanisms = {}
        active_meds = [
            m for m in timeline.medications
            if m.status.value in ("active", "prn", "unknown")
        ]

        for med in active_meds[:8]:
            entry = {"drug": med.name, "sources": {}}

            if self._pubchem:
                try:
                    mech = self._pubchem.get_drug_mechanism(med.name)
                    if mech:
                        entry["sources"]["pubchem"] = {
                            "mechanism": mech,
                            "source": "PubChem (NCBI)",
                        }
                    targets = self._pubchem.get_drug_targets(med.name)
                    if targets:
                        entry["sources"]["pubchem_targets"] = {
                            "targets": targets[:5],
                            "source": "PubChem (NCBI)",
                        }
                except Exception as e:
                    logger.debug(f"PubChem failed for '{med.name}': {e}")

            if entry["sources"]:
                mechanisms[med.name] = entry

        # Open Targets: disease→drug evidence for diagnoses
        if self._open_targets:
            active_diagnoses = [
                d.name for d in timeline.diagnoses
                if d.status and d.status.lower() in ("active", "chronic")
            ]
            for dx_name in active_diagnoses[:5]:
                try:
                    pipeline = self._open_targets.disease_to_drug_pipeline(dx_name)
                    if pipeline:
                        mechanisms[f"_ot_{dx_name}"] = {
                            "condition": dx_name,
                            "drug_pipeline": pipeline,
                            "source": "Open Targets Platform",
                        }
                except Exception as e:
                    logger.debug(f"Open Targets failed for '{dx_name}': {e}")

        return mechanisms

    # ── Genetic Variant Analysis (ClinVar + dbSNP + gnomAD) ──

    def _analyze_genetic_variants(self, timeline: ClinicalTimeline) -> dict:
        """
        Analyze genetic variants using ClinVar (pathogenicity), dbSNP
        (reference data), and gnomAD (population frequencies).
        """
        if not timeline.genetics:
            return {}

        variants = {}

        for gen in timeline.genetics[:15]:
            gene_name = gen.gene
            variant_id = getattr(gen, "variant", None) or getattr(gen, "rs_id", None)

            entry = {"gene": gene_name, "sources": {}}

            # ClinVar — search gene for pathogenic variants
            if self._clinvar:
                try:
                    results = self._clinvar.search_gene_variants(
                        gene_name, limit=5
                    )
                    if results:
                        entry["sources"]["clinvar"] = {
                            "variants": results,
                            "source": "ClinVar (NCBI)",
                        }
                except Exception as e:
                    logger.debug(f"ClinVar failed for '{gene_name}': {e}")

            # dbSNP — get variant details if rsID is known
            if self._dbsnp and variant_id and variant_id.startswith("rs"):
                try:
                    info = self._dbsnp.get_variant(variant_id)
                    if info:
                        entry["sources"]["dbsnp"] = {
                            "variant_info": info,
                            "source": "dbSNP (NCBI)",
                        }
                except Exception as e:
                    logger.debug(f"dbSNP failed for '{variant_id}': {e}")

            # gnomAD — population frequency
            if self._gnomad and variant_id and variant_id.startswith("rs"):
                try:
                    freq = self._gnomad.get_variant_by_rsid(variant_id)
                    if freq:
                        rarity = self._gnomad.is_rare(variant_id)
                        entry["sources"]["gnomad"] = {
                            "frequency_data": freq,
                            "rarity": rarity,
                            "source": "gnomAD",
                        }
                except Exception as e:
                    logger.debug(f"gnomAD failed for '{variant_id}': {e}")

            if entry["sources"]:
                key = variant_id or gene_name
                variants[key] = entry

        return variants

    # ── Disease-Gene Network (DisGeNET + BioGRID + UniProt) ──

    def _build_disease_network(self, timeline: ClinicalTimeline) -> dict:
        """
        Build disease-gene-protein network using DisGeNET (disease-gene
        associations), BioGRID (protein interactions), and UniProt
        (protein function).
        """
        network = {}

        active_diagnoses = [
            d.name for d in timeline.diagnoses
            if d.status and d.status.lower() not in ("resolved", "historical")
        ]

        # DisGeNET — disease→gene associations
        if self._disgenet:
            for dx_name in active_diagnoses[:5]:
                try:
                    genes = self._disgenet.search_disease_genes(dx_name, limit=10)
                    if genes:
                        network[dx_name] = {
                            "disease_genes": genes,
                            "source": "DisGeNET",
                        }
                except Exception as e:
                    logger.debug(f"DisGeNET failed for '{dx_name}': {e}")

            # Cross-disease gene overlap
            if len(active_diagnoses) >= 2:
                try:
                    disease_net = self._disgenet.get_disease_network(
                        active_diagnoses[:5]
                    )
                    if disease_net:
                        network["_disease_overlap"] = {
                            "network": disease_net,
                            "source": "DisGeNET",
                        }
                except Exception as e:
                    logger.debug(f"DisGeNET network failed: {e}")

        # Collect genes of interest (from genetics + DisGeNET findings)
        genes_of_interest = set()
        if timeline.genetics:
            for gen in timeline.genetics[:10]:
                if gen.gene:
                    genes_of_interest.add(gen.gene)
        for dx_data in network.values():
            if isinstance(dx_data, dict) and "disease_genes" in dx_data:
                for g in dx_data["disease_genes"][:5]:
                    gname = g.get("gene_symbol") or g.get("gene")
                    if gname:
                        genes_of_interest.add(gname)

        # BioGRID — protein interaction partners for key genes
        if self._biogrid and genes_of_interest:
            for gene in list(genes_of_interest)[:8]:
                try:
                    partners = self._biogrid.get_interaction_partners(
                        gene, limit=10
                    )
                    if partners:
                        network[f"_biogrid_{gene}"] = {
                            "gene": gene,
                            "interaction_partners": partners,
                            "source": "BioGRID",
                        }
                except Exception as e:
                    logger.debug(f"BioGRID failed for '{gene}': {e}")

        # UniProt — protein function for key genes
        if self._uniprot and genes_of_interest:
            for gene in list(genes_of_interest)[:8]:
                try:
                    func = self._uniprot.get_function(gene)
                    if func:
                        network[f"_uniprot_{gene}"] = {
                            "gene": gene,
                            "function": func,
                            "source": "UniProt",
                        }
                except Exception as e:
                    logger.debug(f"UniProt failed for '{gene}': {e}")

        return network

    # ── Cross-Vocabulary Mapping (UMLS + LOINC) ──────────────

    def _map_cross_vocabulary(self, timeline: ClinicalTimeline) -> dict:
        """
        Map clinical terms across vocabularies (UMLS) and standardize
        lab tests (LOINC).
        """
        mappings = {}

        # UMLS — cross-vocabulary mapping for diagnoses
        if self._umls:
            for dx in timeline.diagnoses[:10]:
                if dx.status and dx.status.lower() in ("resolved", "historical"):
                    continue
                try:
                    mapped = self._umls.map_term(dx.name)
                    if mapped:
                        mappings[dx.name] = {
                            "umls": mapped,
                            "source": "UMLS (NLM)",
                        }
                except Exception as e:
                    logger.debug(f"UMLS mapping failed for '{dx.name}': {e}")

        # LOINC — lab test standardization
        if self._loinc:
            labs = getattr(timeline, "labs", None) or []
            for lab in labs[:15]:
                lab_name = getattr(lab, "test_name", None) or getattr(lab, "name", None)
                if not lab_name:
                    continue
                try:
                    validated = self._loinc.validate_lab_test(lab_name)
                    if validated:
                        mappings[f"_lab_{lab_name}"] = {
                            "loinc": validated,
                            "source": "LOINC",
                        }
                except Exception as e:
                    logger.debug(f"LOINC validation failed for '{lab_name}': {e}")

        return mappings

    # ── Setup ─────────────────────────────────────────────────

    def _setup_clients(
        self,
        pubmed_api_key: str = None,
        omim_api_key: str = None,
        icd11_client_id: str = None,
        icd11_client_secret: str = None,
        umls_api_key: str = None,
        biogrid_api_key: str = None,
        disgenet_api_key: str = None,
        loinc_username: str = None,
        loinc_password: str = None,
    ):
        """Initialize all validation API clients (26 sources)."""

        # NCBI API key shared by PubMed, ClinVar, dbSNP
        ncbi_api_key = pubmed_api_key

        # ── Original 4 ──────────────────────────────────────
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

        # ── Terminology (SNOMED CT, MeSH, ICD-11) ───────────
        try:
            from src.validation.snomed import SNOMEDClient
            self._snomed = SNOMEDClient()
        except Exception:
            logger.debug("SNOMED CT client not available")

        try:
            from src.validation.mesh import MeSHClient
            self._mesh = MeSHClient()
        except Exception:
            logger.debug("MeSH client not available")

        try:
            from src.validation.icd11 import ICD11Client
            self._icd11 = ICD11Client(
                client_id=icd11_client_id,
                client_secret=icd11_client_secret,
            )
        except Exception:
            logger.debug("ICD-11 client not available")

        # ── Clinical Trials ─────────────────────────────────
        try:
            from src.validation.clinical_trials import ClinicalTrialsClient
            self._clinical_trials = ClinicalTrialsClient()
        except Exception:
            logger.debug("ClinicalTrials.gov client not available")

        # ── Rare Disease (OMIM, Orphanet, GARD, HPO) ────────
        try:
            from src.validation.omim import OMIMClient
            self._omim = OMIMClient(api_key=omim_api_key)
        except Exception:
            logger.debug("OMIM client not available")

        try:
            from src.validation.orphanet import OrphanetClient
            self._orphanet = OrphanetClient()
        except Exception:
            logger.debug("Orphanet client not available")

        try:
            from src.validation.gard import GARDClient
            self._gard = GARDClient()
        except Exception:
            logger.debug("GARD client not available")

        try:
            from src.validation.hpo import HPOClient
            self._hpo = HPOClient()
        except Exception:
            logger.debug("HPO client not available")

        # ── Drug & Treatment (DailyMed, DDinter, PharmGKB, PubChem, SIDER)
        try:
            from src.validation.dailymed import DailyMedClient
            self._dailymed = DailyMedClient()
        except Exception:
            logger.debug("DailyMed client not available")

        try:
            from src.validation.ddinter import DDinterClient
            self._ddinter = DDinterClient()
        except Exception:
            logger.debug("DDinter client not available")

        try:
            from src.validation.pharmgkb import PharmGKBClient
            self._pharmgkb = PharmGKBClient()
        except Exception:
            logger.debug("PharmGKB client not available")

        try:
            from src.validation.pubchem import PubChemClient
            self._pubchem = PubChemClient()
        except Exception:
            logger.debug("PubChem client not available")

        try:
            from src.validation.sider import SIDERClient
            self._sider = SIDERClient()
        except Exception:
            logger.debug("SIDER client not available")

        # ── Genetics & Molecular (ClinVar, dbSNP, gnomAD, DisGeNET, BioGRID)
        try:
            from src.validation.clinvar import ClinVarClient
            self._clinvar = ClinVarClient(api_key=ncbi_api_key)
        except Exception:
            logger.debug("ClinVar client not available")

        try:
            from src.validation.dbsnp import dbSNPClient
            self._dbsnp = dbSNPClient(api_key=ncbi_api_key)
        except Exception:
            logger.debug("dbSNP client not available")

        try:
            from src.validation.gnomad import GnomADClient
            self._gnomad = GnomADClient()
        except Exception:
            logger.debug("gnomAD client not available")

        try:
            from src.validation.disgenet import DisGeNETClient
            self._disgenet = DisGeNETClient(api_key=disgenet_api_key)
        except Exception:
            logger.debug("DisGeNET client not available")

        try:
            from src.validation.biogrid import BioGRIDClient
            self._biogrid = BioGRIDClient(api_key=biogrid_api_key)
        except Exception:
            logger.debug("BioGRID client not available")

        # ── Cross-Reference (Open Targets, UMLS, LOINC) ─────
        try:
            from src.validation.open_targets import OpenTargetsClient
            self._open_targets = OpenTargetsClient()
        except Exception:
            logger.debug("Open Targets client not available")

        try:
            from src.validation.umls import UMLSClient
            self._umls = UMLSClient(api_key=umls_api_key)
        except Exception:
            logger.debug("UMLS client not available")

        try:
            from src.validation.loinc import LOINCClient
            self._loinc = LOINCClient(
                username=loinc_username,
                password=loinc_password,
            )
        except Exception:
            logger.debug("LOINC client not available")

        # ── Protein Function (UniProt) ───────────────────────
        try:
            from src.validation.uniprot import UniProtClient
            self._uniprot = UniProtClient()
        except Exception:
            logger.debug("UniProt client not available")

        # Count available clients
        all_clients = [
            self._openfda, self._rxnorm, self._pubmed, self._drugbank,
            self._snomed, self._mesh, self._icd11, self._clinical_trials,
            self._omim, self._orphanet, self._gard, self._hpo,
            self._dailymed, self._ddinter, self._pharmgkb, self._pubchem,
            self._sider, self._clinvar, self._dbsnp, self._gnomad,
            self._disgenet, self._biogrid, self._open_targets, self._umls,
            self._loinc, self._uniprot,
        ]
        active = sum(1 for c in all_clients if c is not None)
        logger.info(f"Validator initialized: {active}/26 data sources active")
