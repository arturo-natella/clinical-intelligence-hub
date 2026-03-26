"""
Tests for Features 14, 16, and 18:
  F14 — Diagnosis Confirmation Tracking
  F16 — Family Medical History
  F18 — Medication Adherence Tracking
"""

import sys
import uuid
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import (
    ClinicalTimeline,
    Diagnosis,
    DiagnosisConfirmationEvent,
    DiagnosisConfirmationStatus,
    FamilyCondition,
    FamilyMember,
    Medication,
    MedicationDose,
    MedicationStatus,
    PatientProfile,
    Provenance,
)


def _prov():
    return Provenance(source_file="test.pdf")


# ═══════════════════════════════════════════════════════════
# F14 — Diagnosis Confirmation Tracking
# ═══════════════════════════════════════════════════════════

def test_diagnosis_has_confirmation_fields():
    """Diagnosis model carries confirmation_status and patient_agreement."""
    dx = Diagnosis(name="Type 2 Diabetes", provenance=_prov())

    # Defaults
    assert dx.diagnosis_id, "diagnosis_id must be auto-generated"
    assert dx.confirmation_status == DiagnosisConfirmationStatus.PENDING
    assert dx.patient_agreement is None
    assert dx.confirmation_history == []

    print("✓ F14: Diagnosis has confirmation fields with correct defaults")


def test_diagnosis_confirmation_status_enum():
    """All DiagnosisConfirmationStatus values are usable."""
    valid = [
        DiagnosisConfirmationStatus.PENDING,
        DiagnosisConfirmationStatus.SUSPECTED,
        DiagnosisConfirmationStatus.PROBABLE,
        DiagnosisConfirmationStatus.CONFIRMED,
        DiagnosisConfirmationStatus.RULED_OUT,
    ]
    for s in valid:
        dx = Diagnosis(
            name="Test", confirmation_status=s, provenance=_prov()
        )
        assert dx.confirmation_status == s

    print("✓ F14: All confirmation status enum values accepted")


def test_diagnosis_confirmation_history_lifecycle():
    """Confirmation events can be appended and are ordered correctly."""
    dx = Diagnosis(name="Migraine", provenance=_prov())

    event1 = DiagnosisConfirmationEvent(
        status=DiagnosisConfirmationStatus.SUSPECTED,
        provider="Dr. Chen",
        notes="Recurring headaches — referred to neurology",
    )
    event2 = DiagnosisConfirmationEvent(
        status=DiagnosisConfirmationStatus.CONFIRMED,
        provider="Dr. Patel",
        notes="ICHD-3 criteria met, MRI unremarkable",
    )

    dx.confirmation_history.append(event1)
    dx.confirmation_history.append(event2)
    dx.confirmation_status = DiagnosisConfirmationStatus.CONFIRMED

    assert len(dx.confirmation_history) == 2
    assert dx.confirmation_history[0].status == DiagnosisConfirmationStatus.SUSPECTED
    assert dx.confirmation_history[1].status == DiagnosisConfirmationStatus.CONFIRMED
    assert dx.confirmation_history[1].provider == "Dr. Patel"
    assert dx.confirmation_status == DiagnosisConfirmationStatus.CONFIRMED

    print("✓ F14: Confirmation history lifecycle works correctly")


def test_diagnosis_patient_agreement():
    """Patient agreement field accepts agree/disagree/unsure."""
    for agreement in ("agree", "disagree", "unsure"):
        dx = Diagnosis(
            name="Test",
            patient_agreement=agreement,
            patient_agreement_reason="Because I said so",
            provenance=_prov(),
        )
        assert dx.patient_agreement == agreement
        assert dx.patient_agreement_reason == "Because I said so"

    print("✓ F14: Patient agreement field works correctly")


def test_diagnosis_serializes_with_confirmation():
    """Diagnosis with full confirmation data round-trips through JSON."""
    dx = Diagnosis(
        name="Peripheral Neuropathy",
        icd10_code="G62.9",
        confirmation_status=DiagnosisConfirmationStatus.PROBABLE,
        patient_agreement="agree",
        provenance=_prov(),
    )
    dx.confirmation_history.append(
        DiagnosisConfirmationEvent(
            status=DiagnosisConfirmationStatus.SUSPECTED,
            provider="Dr. A",
        )
    )

    data = dx.model_dump(mode="json")
    restored = Diagnosis.model_validate(data)

    assert restored.confirmation_status == DiagnosisConfirmationStatus.PROBABLE
    assert len(restored.confirmation_history) == 1
    assert restored.confirmation_history[0].provider == "Dr. A"

    print("✓ F14: Diagnosis serializes/deserializes with confirmation data")


# ═══════════════════════════════════════════════════════════
# F16 — Family Medical History
# ═══════════════════════════════════════════════════════════

def test_family_member_model():
    """FamilyMember has all required fields and sane defaults."""
    member = FamilyMember(relationship="mother")

    assert member.member_id, "member_id must be auto-generated"
    assert member.relationship == "mother"
    assert member.conditions == []
    assert member.deceased is False
    assert member.cause_of_death is None

    print("✓ F16: FamilyMember model has correct defaults")


def test_family_condition_model():
    """FamilyCondition stores condition details correctly."""
    cond = FamilyCondition(
        name="Type 2 Diabetes Mellitus",
        age_at_diagnosis=48,
        status="Active",
    )
    assert cond.name == "Type 2 Diabetes Mellitus"
    assert cond.age_at_diagnosis == 48

    print("✓ F16: FamilyCondition model works correctly")


def test_family_member_with_conditions():
    """FamilyMember can hold multiple conditions."""
    member = FamilyMember(
        relationship="father",
        conditions=[
            FamilyCondition(name="Hypertension", age_at_diagnosis=50),
            FamilyCondition(name="Coronary artery disease", age_at_diagnosis=62),
        ],
        deceased=False,
    )
    assert len(member.conditions) == 2
    assert member.conditions[0].name == "Hypertension"
    assert member.conditions[1].age_at_diagnosis == 62

    print("✓ F16: FamilyMember with multiple conditions works correctly")


def test_patient_profile_has_family_history():
    """PatientProfile carries family_history list."""
    profile = PatientProfile()
    assert hasattr(profile, "family_history")
    assert isinstance(profile.family_history, list)
    assert profile.family_history == []

    member = FamilyMember(
        relationship="maternal_grandmother",
        conditions=[FamilyCondition(name="Alzheimer's disease", age_at_diagnosis=72)],
        deceased=True,
        cause_of_death="Complications from Alzheimer's disease",
    )
    profile.family_history.append(member)
    assert len(profile.family_history) == 1

    print("✓ F16: PatientProfile.family_history works correctly")


def test_family_history_serializes():
    """Family history round-trips through JSON cleanly."""
    profile = PatientProfile()
    profile.family_history.append(
        FamilyMember(
            relationship="sibling",
            conditions=[
                FamilyCondition(name="Migraine with aura", age_at_diagnosis=25),
            ],
        )
    )

    data = profile.model_dump(mode="json")
    restored = PatientProfile.model_validate(data)

    assert len(restored.family_history) == 1
    assert restored.family_history[0].relationship == "sibling"
    assert restored.family_history[0].conditions[0].name == "Migraine with aura"

    print("✓ F16: Family history serializes/deserializes correctly")


# ═══════════════════════════════════════════════════════════
# F18 — Medication Adherence Tracking
# ═══════════════════════════════════════════════════════════

def test_medication_dose_model():
    """MedicationDose model has all required fields."""
    dose = MedicationDose(
        medication_id="med-001",
        medication_name="Metformin",
        dose_date=date(2026, 3, 1),
        dose_time="morning",
        taken=True,
    )
    assert dose.dose_id, "dose_id must be auto-generated"
    assert dose.taken is True
    assert dose.reaction is None
    assert dose.reaction_severity is None

    print("✓ F18: MedicationDose model has correct defaults")


def test_medication_dose_skipped():
    """A skipped dose records reason and taken=False."""
    dose = MedicationDose(
        medication_id="med-001",
        medication_name="Metformin",
        dose_date=date(2026, 3, 5),
        taken=False,
        skipped_reason="Forgot",
    )
    assert dose.taken is False
    assert dose.skipped_reason == "Forgot"

    print("✓ F18: Skipped dose records correctly")


def test_medication_dose_with_reaction():
    """A dose with a reaction stores reaction text and severity."""
    dose = MedicationDose(
        medication_id="med-002",
        medication_name="Gabapentin",
        dose_date=date(2026, 3, 10),
        taken=True,
        reaction="Felt dizzy for 30 minutes",
        reaction_severity="mild",
    )
    assert dose.reaction == "Felt dizzy for 30 minutes"
    assert dose.reaction_severity == "mild"

    print("✓ F18: Dose with reaction records correctly")


def test_clinical_timeline_has_medication_doses():
    """ClinicalTimeline.medication_doses is a list, defaults to empty."""
    timeline = ClinicalTimeline()
    assert hasattr(timeline, "medication_doses")
    assert timeline.medication_doses == []

    print("✓ F18: ClinicalTimeline.medication_doses exists with correct default")


def test_adherence_calculation():
    """Adherence percentage is calculated correctly from dose log."""
    doses = [
        MedicationDose(
            medication_id="m1", medication_name="Metformin",
            dose_date=date(2026, 3, i + 1), taken=(i not in {4, 14}),
        )
        for i in range(20)
    ]
    total = len(doses)
    taken = sum(1 for d in doses if d.taken)
    missed = total - taken
    pct = round(taken / total * 100)

    assert total == 20
    assert missed == 2
    assert pct == 90

    print(f"✓ F18: Adherence calculation: {taken}/{total} = {pct}%")


def test_medication_dose_serializes():
    """MedicationDose round-trips through JSON."""
    dose = MedicationDose(
        medication_id="med-001",
        medication_name="Lisinopril",
        dose_date=date(2026, 3, 15),
        taken=True,
        reaction="Slight headache",
        reaction_severity="mild",
    )

    data = dose.model_dump(mode="json")
    restored = MedicationDose.model_validate(data)

    assert restored.medication_id == "med-001"
    assert restored.taken is True
    assert restored.reaction == "Slight headache"
    assert str(restored.dose_date) == "2026-03-15"

    print("✓ F18: MedicationDose serializes/deserializes correctly")


def test_full_profile_with_all_new_features():
    """PatientProfile with F14+F16+F18 data serializes cleanly."""
    profile = PatientProfile()

    # F18: medication + doses
    med = Medication(
        medication_id="m1",
        name="Metformin",
        status=MedicationStatus.ACTIVE,
        provenance=_prov(),
    )
    profile.clinical_timeline.medications.append(med)
    profile.clinical_timeline.medication_doses.append(
        MedicationDose(
            medication_id="m1",
            medication_name="Metformin",
            dose_date=date(2026, 3, 1),
            taken=True,
        )
    )

    # F14: diagnosis with confirmation
    dx = Diagnosis(
        name="Hypertension",
        confirmation_status=DiagnosisConfirmationStatus.CONFIRMED,
        patient_agreement="agree",
        provenance=_prov(),
    )
    dx.confirmation_history.append(
        DiagnosisConfirmationEvent(
            status=DiagnosisConfirmationStatus.CONFIRMED,
            provider="Dr. Chen",
        )
    )
    profile.clinical_timeline.diagnoses.append(dx)

    # F16: family history
    profile.family_history.append(
        FamilyMember(
            relationship="mother",
            conditions=[FamilyCondition(name="Hypertension", age_at_diagnosis=52)],
        )
    )

    # Round-trip
    data = profile.model_dump(mode="json")
    restored = PatientProfile.model_validate(data)

    assert len(restored.clinical_timeline.medications) == 1
    assert len(restored.clinical_timeline.medication_doses) == 1
    assert len(restored.clinical_timeline.diagnoses) == 1
    assert restored.clinical_timeline.diagnoses[0].confirmation_status == DiagnosisConfirmationStatus.CONFIRMED
    assert len(restored.family_history) == 1
    assert restored.family_history[0].relationship == "mother"

    print("✓ All three features coexist cleanly in PatientProfile")


if __name__ == "__main__":
    # F14
    test_diagnosis_has_confirmation_fields()
    test_diagnosis_confirmation_status_enum()
    test_diagnosis_confirmation_history_lifecycle()
    test_diagnosis_patient_agreement()
    test_diagnosis_serializes_with_confirmation()

    # F16
    test_family_member_model()
    test_family_condition_model()
    test_family_member_with_conditions()
    test_patient_profile_has_family_history()
    test_family_history_serializes()

    # F18
    test_medication_dose_model()
    test_medication_dose_skipped()
    test_medication_dose_with_reaction()
    test_clinical_timeline_has_medication_doses()
    test_adherence_calculation()
    test_medication_dose_serializes()
    test_full_profile_with_all_new_features()

    print("\n══════════════════════════════════════════════════")
    print("  F14 + F16 + F18: ALL TESTS PASSED")
    print("══════════════════════════════════════════════════")
