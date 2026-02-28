"""
Phase 6 Tests — Clinical Validation (Pass 5)

Tests the structural and logic components of clinical validation.
Actual API calls require network access, so these tests verify:
  - LOINC: seed database, lookups, aliases, reference ranges
  - SNOMED: seed database, lookups, aliases, categories
  - RxNorm Local: seed database, brand→generic, drug class
  - Validator: orchestrator initialization, client setup
  - DrugBank: PGx interaction map, severity mapping
  - OpenFDA: client structure
  - PubMed: client structure
  - RxNorm API: client structure
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import AlertSeverity, MedicationStatus


# ── LOINC Tests ──────────────────────────────────────────────

def test_loinc_seed_count():
    """LOINC seed has substantial coverage."""
    from src.standardization.loinc import LOINCDatabase

    loinc = LOINCDatabase()
    assert loinc.count >= 80, f"Expected at least 80 LOINC codes, got {loinc.count}"
    print(f"✓ LOINC seed: {loinc.count} codes loaded")


def test_loinc_lookup_common_labs():
    """Common lab tests resolve correctly."""
    from src.standardization.loinc import LOINCDatabase

    loinc = LOINCDatabase()

    # HbA1c by various names
    result = loinc.lookup("Hemoglobin A1c")
    assert result is not None, "Should find HbA1c"
    assert result["code"] == "4548-4"
    assert result["unit"] == "%"

    result = loinc.lookup("A1c")
    assert result is not None, "Should find A1c by alias"
    assert result["code"] == "4548-4"

    result = loinc.lookup("HbA1c")
    assert result is not None, "Should find HbA1c alias"

    # TSH
    result = loinc.lookup("TSH")
    assert result is not None
    assert result["reference_low"] == 0.4
    assert result["reference_high"] == 4.0

    # Vitamin D
    result = loinc.lookup("Vitamin D")
    assert result is not None
    assert result["reference_low"] == 30.0

    # eGFR
    result = loinc.lookup("GFR")
    assert result is not None
    assert result["code"] == "33914-3"

    print("✓ LOINC common lab lookups work correctly")


def test_loinc_reference_ranges():
    """Reference ranges are clinically reasonable."""
    from src.standardization.loinc import LOINCDatabase

    loinc = LOINCDatabase()

    glucose = loinc.lookup("Glucose")
    assert glucose is not None
    assert glucose["reference_low"] == 70.0
    assert glucose["reference_high"] == 100.0

    potassium = loinc.lookup("Potassium")
    assert potassium is not None
    assert potassium["reference_low"] == 3.5
    assert potassium["reference_high"] == 5.0

    # Some labs have only upper bound (e.g., cholesterol)
    tc = loinc.lookup("Total Cholesterol")
    assert tc is not None
    assert tc["reference_low"] is None
    assert tc["reference_high"] == 200.0

    print("✓ LOINC reference ranges are clinically reasonable")


def test_loinc_search():
    """LOINC search returns relevant results."""
    from src.standardization.loinc import LOINCDatabase

    loinc = LOINCDatabase()

    results = loinc.search("cholesterol")
    assert len(results) >= 2, "Should find multiple cholesterol-related tests"

    results = loinc.search("troponin")
    assert len(results) >= 1, "Should find troponin"

    print("✓ LOINC search works")


# ── SNOMED Tests ─────────────────────────────────────────────

def test_snomed_seed_count():
    """SNOMED seed has substantial coverage."""
    from src.standardization.snomed import SNOMEDDatabase

    snomed = SNOMEDDatabase()
    assert snomed.count >= 80, f"Expected at least 80 SNOMED concepts, got {snomed.count}"
    print(f"✓ SNOMED seed: {snomed.count} concepts loaded")


def test_snomed_lookup_common_conditions():
    """Common conditions resolve correctly."""
    from src.standardization.snomed import SNOMEDDatabase

    snomed = SNOMEDDatabase()

    # Diabetes by various names
    result = snomed.lookup("Type 2 Diabetes")
    assert result is not None
    assert result["code"] == "44054006"
    assert result["category"] == "Endocrine"

    result = snomed.lookup("DM2")
    assert result is not None, "Should resolve DM2 abbreviation"
    assert result["code"] == "44054006"

    # Hypertension
    result = snomed.lookup("HTN")
    assert result is not None
    assert result["code"] == "38341003"
    assert result["category"] == "Cardiovascular"

    # Depression
    result = snomed.lookup("Depression")
    assert result is not None
    assert result["category"] == "Mental Health"

    # COPD
    result = snomed.lookup("COPD")
    assert result is not None

    print("✓ SNOMED common condition lookups work correctly")


def test_snomed_icd10_mapping():
    """SNOMED codes map to ICD-10."""
    from src.standardization.snomed import SNOMEDDatabase

    snomed = SNOMEDDatabase()

    icd10 = snomed.get_icd10("44054006")  # Type 2 DM
    assert icd10 == "E11"

    icd10 = snomed.get_icd10("38341003")  # HTN
    assert icd10 == "I10"

    print("✓ SNOMED → ICD-10 mapping works")


def test_snomed_categories():
    """SNOMED categories contain expected conditions."""
    from src.standardization.snomed import SNOMEDDatabase

    snomed = SNOMEDDatabase()

    cardio = snomed.get_by_category("Cardiovascular")
    assert len(cardio) >= 5, "Should have 5+ cardiovascular conditions"

    neuro = snomed.get_by_category("Neurological")
    assert len(neuro) >= 5, "Should have 5+ neurological conditions"

    mental = snomed.get_by_category("Mental Health")
    assert len(mental) >= 5, "Should have 5+ mental health conditions"

    print("✓ SNOMED category grouping works")


# ── RxNorm Local DB Tests ────────────────────────────────────

def test_rxnorm_db_seed_count():
    """RxNorm local DB has substantial coverage."""
    from src.standardization.rxnorm_db import RxNormLocalDB

    rxdb = RxNormLocalDB()
    assert rxdb.count >= 150, f"Expected at least 150 medications, got {rxdb.count}"
    print(f"✓ RxNorm local DB: {rxdb.count} medications loaded")


def test_rxnorm_brand_to_generic():
    """Brand names resolve to generic names."""
    from src.standardization.rxnorm_db import RxNormLocalDB

    rxdb = RxNormLocalDB()

    # Glucophage → Metformin
    result = rxdb.lookup("Glucophage")
    assert result is not None
    assert result["generic_name"] == "Metformin"
    assert result["drug_class"] == "Biguanide"

    # Lipitor → Atorvastatin
    result = rxdb.lookup("Lipitor")
    assert result is not None
    assert result["generic_name"] == "Atorvastatin"

    # Zoloft → Sertraline
    result = rxdb.lookup("Zoloft")
    assert result is not None
    assert result["generic_name"] == "Sertraline"
    assert result["drug_class"] == "SSRI"

    # Synthroid → Levothyroxine
    result = rxdb.lookup("Synthroid")
    assert result is not None
    assert result["generic_name"] == "Levothyroxine"

    # Generic name also works
    result = rxdb.lookup("Metformin")
    assert result is not None
    assert result["generic_name"] == "Metformin"

    print("✓ Brand → generic mapping works correctly")


def test_rxnorm_drug_classes():
    """Drug class grouping works."""
    from src.standardization.rxnorm_db import RxNormLocalDB

    rxdb = RxNormLocalDB()

    statins = rxdb.get_by_class("HMG-CoA Reductase Inhibitor")
    assert len(statins) >= 4, f"Should find 4+ statins, got {len(statins)}"

    ssris = rxdb.get_by_class("SSRI")
    assert len(ssris) >= 4, f"Should find 4+ SSRIs, got {len(ssris)}"

    ace_inhibitors = rxdb.get_by_class("ACE Inhibitor")
    assert len(ace_inhibitors) >= 2

    print("✓ Drug class grouping works")


def test_rxnorm_therapeutic_categories():
    """Therapeutic categories group medications correctly."""
    from src.standardization.rxnorm_db import RxNormLocalDB

    rxdb = RxNormLocalDB()

    antidiabetics = rxdb.get_by_category("Antidiabetic")
    assert len(antidiabetics) >= 8, "Should have 8+ antidiabetic medications"

    antihypertensives = rxdb.get_by_category("Antihypertensive")
    assert len(antihypertensives) >= 10, "Should have 10+ antihypertensives"

    print("✓ Therapeutic category grouping works")


# ── DrugBank PGx Tests ───────────────────────────────────────

def test_drugbank_pgx_map():
    """DrugBank pharmacogenomic map has expected entries."""
    from src.validation.drugbank import DrugInteractionChecker

    checker = DrugInteractionChecker()

    # Test PGx interactions
    medications = [
        {"name": "Codeine", "status": "active"},
    ]
    genetics = [
        {"gene": "CYP2D6", "phenotype": "Poor Metabolizer"},
    ]

    interactions = checker.check_drug_gene_interactions(medications, genetics)
    assert len(interactions) >= 1, "Should flag Codeine + CYP2D6 poor metabolizer"
    assert interactions[0].severity == AlertSeverity.HIGH
    assert "CYP2D6" in interactions[0].gene

    print("✓ DrugBank PGx map flags codeine + CYP2D6 poor metabolizer")


def test_drugbank_pgx_no_false_positive():
    """DrugBank PGx doesn't flag irrelevant combinations."""
    from src.validation.drugbank import DrugInteractionChecker

    checker = DrugInteractionChecker()

    medications = [
        {"name": "Aspirin", "status": "active"},
    ]
    genetics = [
        {"gene": "CYP2D6", "phenotype": "Poor Metabolizer"},
    ]

    interactions = checker.check_drug_gene_interactions(medications, genetics)
    assert len(interactions) == 0, "Aspirin should not be flagged for CYP2D6"

    print("✓ DrugBank PGx correctly ignores irrelevant combinations")


def test_drugbank_warfarin_vkorc1():
    """DrugBank flags Warfarin + VKORC1 interaction."""
    from src.validation.drugbank import DrugInteractionChecker

    checker = DrugInteractionChecker()

    medications = [{"name": "Warfarin", "status": "active"}]
    genetics = [{"gene": "VKORC1", "phenotype": "Increased sensitivity"}]

    interactions = checker.check_drug_gene_interactions(medications, genetics)
    assert len(interactions) >= 1, "Should flag Warfarin + VKORC1"

    print("✓ DrugBank flags Warfarin + VKORC1 increased sensitivity")


# ── Validator Orchestrator Tests ──────────────────────────────

def test_validator_initializes():
    """ClinicalValidator initializes without errors."""
    from src.validation.validator import ClinicalValidator

    validator = ClinicalValidator()
    # Should not crash even without network
    assert validator is not None

    print("✓ ClinicalValidator initializes successfully")


def test_validator_empty_profile():
    """Validator handles empty profile gracefully."""
    from src.validation.validator import ClinicalValidator
    from src.models import PatientProfile

    validator = ClinicalValidator()
    profile = PatientProfile()

    results = validator.validate(profile)
    assert isinstance(results, dict)
    assert "drug_interactions" in results
    assert "adverse_events" in results
    assert "literature" in results
    assert "standardization" in results
    assert "recalls" in results

    print("✓ Validator handles empty profile without errors")


# ── Client Structure Tests ────────────────────────────────────

def test_openfda_client_structure():
    """OpenFDA client has expected methods."""
    from src.validation.openfda import OpenFDAClient

    client = OpenFDAClient()
    assert hasattr(client, "get_adverse_events")
    assert hasattr(client, "get_drug_label")
    assert hasattr(client, "check_drug_recalls")
    assert hasattr(client, "validate_drug_interactions")

    print("✓ OpenFDA client has all expected methods")


def test_pubmed_client_structure():
    """PubMed client has expected methods."""
    from src.validation.pubmed import PubMedClient

    client = PubMedClient()
    assert hasattr(client, "search")
    assert hasattr(client, "search_drug_evidence")
    assert hasattr(client, "search_interaction")
    assert hasattr(client, "search_cross_disciplinary")

    print("✓ PubMed client has all expected methods")


def test_rxnorm_client_structure():
    """RxNorm client has expected methods."""
    from src.validation.rxnorm import RxNormClient

    client = RxNormClient()
    assert hasattr(client, "resolve_medication")
    assert hasattr(client, "get_interactions")
    assert hasattr(client, "check_pairwise_interactions")

    print("✓ RxNorm client has all expected methods")


# ── Run All Tests ────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 6 Tests — Clinical Validation")
    print("=" * 60)

    # LOINC
    test_loinc_seed_count()
    test_loinc_lookup_common_labs()
    test_loinc_reference_ranges()
    test_loinc_search()

    # SNOMED
    test_snomed_seed_count()
    test_snomed_lookup_common_conditions()
    test_snomed_icd10_mapping()
    test_snomed_categories()

    # RxNorm Local DB
    test_rxnorm_db_seed_count()
    test_rxnorm_brand_to_generic()
    test_rxnorm_drug_classes()
    test_rxnorm_therapeutic_categories()

    # DrugBank PGx
    test_drugbank_pgx_map()
    test_drugbank_pgx_no_false_positive()
    test_drugbank_warfarin_vkorc1()

    # Validator
    test_validator_initializes()
    test_validator_empty_profile()

    # Client structure
    test_openfda_client_structure()
    test_pubmed_client_structure()
    test_rxnorm_client_structure()

    print()
    print("=" * 60)
    print("All Phase 6 tests passed ✓")
    print("=" * 60)
