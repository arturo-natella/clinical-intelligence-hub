"""Lab tests in an imported procedure section must retain their true category.

Every name below is invented, generic vocabulary; none is copied from a record.
"""

from copy import deepcopy
from datetime import date

import pytest

from src.models import ClinicalTimeline, LabResult, PatientProfile, Procedure, Provenance
from src.standardization.record_categories import (
    is_lab_test_name,
    normalize_lab_procedures,
)


def procedure(name, **fields):
    return {
        "name": name, "procedure_date": "2000-01-02",
        "provenance": {"source_file": "synthetic.pdf", "source_page": 3},
        **fields,
    }


def lab(name, **fields):
    return {
        "name": name, "test_date": "2000-01-02",
        "provenance": {"source_file": "synthetic-results.pdf", "source_page": 1},
        **fields,
    }


@pytest.mark.parametrize("name", [
    "Urine glucose", "Glucose, urine", "Protein in urine", "Urine ketones",
    "URINE NITRITE (POC)", "Urine leukocyte esterase", "Urine hCG",
    "Pregnancy test, urine", "Rapid strep antigen", "Strep A rapid test - point of care",
    "Influenza A/B antigen", "COVID-19 rapid antigen", "SARS-CoV-2 PCR",
    "RSV antigen", "Mononucleosis screen", "Vaginal pH", "Wet mount", "KOH prep",
    "Fingerstick glucose", "Hemoglobin A1c", "HbA1c POC", "TSH",
    "Stool DNA test", "Fecal occult blood test", "Urine culture",
    "POCT Hemoglobin A1C", "POCT urine pregnancy", "POCT INR", "HIV screening",
    "SARS-CoV-2 RNA", "Influenza A and B antigen", "Chlamydia trachomatis NAAT",
    "COVID-19 testing", "Strep culture",
])
def test_recognizes_common_lab_and_point_of_care_tests(name):
    assert is_lab_test_name(name)


@pytest.mark.parametrize("name", [
    "Influenza vaccine injection", "Flu shot", "COVID-19 vaccination",
    "Nasal swab collection for COVID test", "Urine specimen collection",
    "Blood draw", "Venipuncture", "Glucose infusion", "Strep throat counseling",
    "HIV test counseling", "Skin biopsy", "Knee X-ray", "Cardiac stress test",
    "Allergy skin test", "Pulmonary function test", "Hearing test",
    "Physical therapy evaluation", "Unknown test", "Urine protein counseling",
    # Panels are orders whose results arrive as separate tests.
    "Complete blood count panel", "Lipid panel", "Comprehensive metabolic panel",
    "Urinalysis with microscopy", "Pap smear",
    # Questionnaires, kits, referrals and tests not done name an organism and
    # a test word but are not a test result.
    "COVID-19 exposure screening", "COVID-19 symptom screening",
    "COVID-19 screening questionnaire", "COVID-19 home test kits provided",
    "HIV self-test kit distributed", "HIV risk screening", "Referred for COVID-19 test",
    "Strep test not performed", "Flu test declined", "HIV screening declined",
    # A Pap smear stays a procedure when an HPV test rides along.
    "Pap smear and HPV test", "Pap smear with HPV DNA", "ThinPrep Pap with HPV DNA",
    "Cervical cancer screening (Pap with HPV)", "Cervical cytology with HPV screening",
])
def test_keeps_interventions_panels_and_unknown_items_as_procedures(name):
    assert not is_lab_test_name(name)


def test_extraction_prompts_follow_the_same_category_rule():
    from pathlib import Path

    from src.analysis import gemini_fallback
    from src.extraction import text_extractor

    for module in (text_extractor, gemini_fallback):
        source = Path(module.__file__).read_text()
        rule = next(line for line in source.splitlines() if "Classify by the clinical item" in line)
        single_tests, _, panels = rule.partition("Panels such as")
        assert "urinalysis" not in single_tests.lower()
        assert panels.startswith(" urinalysis, CBC") and "stay in procedures" in panels


def test_read_normalization_preserves_source_and_does_not_invent_results():
    record = procedure("Urine ketones", provider="Test clinician",
                       facility="Test clinic", outcome="Completed",
                       snomed_code="original-code", extractor_extra="dropped")
    source = {"procedures": [record, procedure("Influenza vaccine injection")], "labs": []}
    before = deepcopy(source)
    normalized = normalize_lab_procedures(source)
    assert source == before
    assert [p["name"] for p in normalized["procedures"]] == ["Influenza vaccine injection"]
    moved = normalized["labs"][0]
    assert moved["test_date"] == "2000-01-02"
    assert moved["ordering_provider"] == "Test clinician"
    assert moved["lab_facility"] == "Test clinic"
    assert moved["provenance"] == record["provenance"]
    assert moved.get("value") is None and moved.get("value_text") is None
    # Only lab fields reach the lab, and only procedure fields are kept as its source.
    assert set(moved) <= set(LabResult.model_fields)
    assert moved["source_procedure"] == {k: v for k, v in record.items() if k != "extractor_extra"}
    assert normalize_lab_procedures(normalized) == normalized


def test_model_restore_keeps_original_procedure_and_actual_results():
    source = procedure("Urine ketones", outcome="Completed")
    timeline = ClinicalTimeline.model_validate({
        "procedures": [source, procedure("Urine nitrite", procedure_date="2000-03-04")],
        "labs": [lab("Urine ketones", value=0)],
    })
    assert timeline.procedures == []
    # The same-day listing is kept as the result's source, not as a second row.
    assert [(item.name, item.value) for item in timeline.labs] == [
        ("Urine ketones", 0), ("Urine nitrite", None),
    ]
    assert timeline.labs[0].source_procedure == source
    restored = ClinicalTimeline.model_validate(timeline.model_dump(mode="json"))
    assert restored == timeline


def test_labs_moved_under_an_earlier_rule_return_to_procedures():
    # What an earlier rule saved: panels and a questionnaire stored as labs.
    saved = [
        lab(name, test_date="2000-03-04", source_procedure={
            "name": name, "procedure_date": "03/04/2000", "outcome": "Completed",
        })
        for name in ("Lipid panel", "Comprehensive metabolic panel",
                     "COVID-19 exposure screening")
    ]
    kept = lab("Urine ketones", source_procedure=procedure("Urine ketones"))
    resulted = lab("Lipid panel", value_text="See report", flag="Abnormal",
                   source_procedure={"name": "Lipid panel"})
    timeline = ClinicalTimeline.model_validate({"labs": saved + [kept, resulted]})
    assert [item.name for item in timeline.labs] == ["Urine ketones", "Lipid panel"]
    assert [(p.name, str(p.procedure_date), p.outcome) for p in timeline.procedures] == [
        ("Lipid panel", "2000-03-04", "Completed"),
        ("Comprehensive metabolic panel", "2000-03-04", "Completed"),
        ("COVID-19 exposure screening", "2000-03-04", "Completed"),
    ]
    assert all(p.provenance.source_file == "synthetic-results.pdf" for p in timeline.procedures)
    assert ClinicalTimeline.model_validate(timeline.model_dump(mode="json")) == timeline


def test_pipeline_routes_typed_and_dict_inputs_and_deduplicates(tmp_path):
    from src.ui.pipeline import Pipeline

    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._profile = PatientProfile()
    records = {"procedures": [
        Procedure(name="Urine ketones", procedure_date=date(2000, 1, 2),
                  provenance=Provenance(source_file="synthetic.pdf")),
        procedure("Urine nitrite"), procedure("Influenza vaccine injection"),
    ]}
    pipeline._append_extraction_results(records)
    pipeline._append_extraction_results(records)
    timeline = pipeline._profile.clinical_timeline
    assert len(timeline.labs) == 2
    assert [p.name for p in timeline.procedures] == ["Influenza vaccine injection"]
    assert all(lab.value is None and lab.value_text is None for lab in timeline.labs)
    assert all(lab.source_procedure for lab in timeline.labs)


def test_text_extractor_repairs_category_before_model_fields_are_lost():
    from src.extraction.text_extractor import TextExtractor

    extractor = TextExtractor.__new__(TextExtractor)
    result = {key: [] for key in (
        "labs", "procedures", "medications", "diagnoses", "allergies", "genetics", "notes",
    )}
    extractor._merge_results(result, {
        "procedures": [procedure("Urine ketones", outcome="Completed")],
    }, "synthetic.pdf", 3)
    assert not result["procedures"]
    assert result["labs"][0].source_procedure["outcome"] == "Completed"
    assert result["labs"][0].value_text is None


def test_existing_profile_apis_agree_without_modifying_saved_records(monkeypatch):
    import src.ui.app as module

    source = {"clinical_timeline": {"procedures": [
        procedure("Urine ketones"), procedure("Urine nitrite"),
        procedure("Influenza vaccine injection"), procedure("Skin biopsy"),
    ], "labs": [{"name": "Existing result", "value": 0, "test_date": "2000-01-02"}]}}
    before = deepcopy(source)
    monkeypatch.setattr(module, "_profile_data", source)
    with module.app.test_client() as client:
        events = client.get("/api/timeline").get_json()
        labs = client.get("/api/labs").get_json()
        dashboard = client.get("/api/dashboard").get_json()
    assert source == before
    assert len(labs) == 3
    assert len(events) == 5
    assert {e["name"] for e in events if e["type"] == "procedure"} == {
        "Influenza vaccine injection", "Skin biopsy",
    }
    missing = [e for e in events if e["type"] == "lab" and e["name"].startswith("Urine")]
    assert all(e["detail"] == "Result not recorded" for e in missing)
    assert all(e["source_page"] == 3 and e["source_procedure"] for e in missing)
    assert next(e for e in events if e["name"] == "Existing result")["detail"] == "0"
    # Tests listed without a result never appear as the latest results.
    assert [entry["name"] for entry in dashboard["latest_labs"]] == ["Existing result"]


def test_a_visit_listing_several_tests_keeps_each_test(tmp_path):
    from src.extraction.text_extractor import TextExtractor
    from src.ui.pipeline import Pipeline

    visit = {"procedures": [
        procedure("Urine ketones", outcome="Negative"),
        procedure("Urine nitrite", outcome="Completed"),
        procedure("Urine leukocyte esterase"),
        procedure("Rapid strep antigen", outcome="Positive"),
        procedure("RSV antigen", outcome="Negative"),
        procedure("Mononucleosis screen"),
        procedure("Influenza vaccine injection"),
    ]}
    results = {key: [] for key in (
        "labs", "procedures", "medications", "diagnoses", "allergies", "genetics", "notes",
    )}
    TextExtractor.__new__(TextExtractor)._merge_results(results, visit, "synthetic.pdf", 3)
    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._profile = PatientProfile()
    pipeline._append_extraction_results(results)
    timeline = pipeline._profile.clinical_timeline

    assert sorted(lab.name for lab in timeline.labs) == sorted(
        p["name"] for p in visit["procedures"][:6]
    )
    assert [p.name for p in timeline.procedures] == ["Influenza vaccine injection"]
    assert all(lab.loinc_code is None for lab in timeline.labs)
    outcomes = {lab.name: lab.source_procedure.get("outcome") for lab in timeline.labs}
    assert outcomes["Rapid strep antigen"] == "Positive"
    assert outcomes["Urine ketones"] == "Negative"


def test_value_less_labs_from_extraction_are_not_merged_by_a_shared_code(tmp_path):
    from src.ui.pipeline import Pipeline

    names = ["Urine ketones", "Haptoglobin", "Procalcitonin", "Vitamin K",
             "CK-MB", "Mononucleosis screen"]
    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._profile = PatientProfile()
    pipeline._append_extraction_results({"labs": [lab(name) for name in names]})
    stored = pipeline._profile.clinical_timeline.labs
    assert sorted(item.name for item in stored) == sorted(names)
    assert all(item.reference_low is None and item.reference_high is None for item in stored)


def test_different_tests_with_the_same_qualitative_result_stay_separate(tmp_path):
    from src.ui.pipeline import Pipeline

    names = ["Urine ketones", "Urine nitrite", "Urine leukocyte esterase"]
    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._profile = PatientProfile()
    pipeline._append_extraction_results({
        "labs": [lab(name, value_text="Negative") for name in names],
    })
    assert sorted(item.name for item in pipeline._profile.clinical_timeline.labs) == sorted(names)


def test_the_same_result_given_as_number_and_as_text_is_one_record(tmp_path):
    from src.ui.pipeline import Pipeline

    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._profile = PatientProfile()
    pipeline._append_extraction_results({"labs": [
        lab("Glucose", value=90, unit="mg/dL"),
        lab("Glucose", value=90, value_text="90", unit="mg/dL"),
    ]})
    assert len(pipeline._profile.clinical_timeline.labs) == 1


def test_a_result_and_its_procedure_listing_with_the_same_outcome_merge(tmp_path):
    from src.ui.pipeline import Pipeline

    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._profile = PatientProfile()
    pipeline._append_extraction_results({
        "labs": [lab("Rapid strep antigen", value_text="Positive")],
        "procedures": [procedure("Rapid strep antigen", outcome="Positive"),
                       procedure("Rapid strep antigen", outcome="Negative",
                                 procedure_date="2000-03-04")],
    })
    stored = pipeline._profile.clinical_timeline.labs
    assert len(stored) == 2
    assert {str(item.test_date) for item in stored} == {"2000-01-02", "2000-03-04"}


def _merged(tmp_path, *batches, profile=None):
    from src.ui.pipeline import Pipeline

    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._profile = profile or PatientProfile()
    for batch in batches:
        pipeline._append_extraction_results(batch)
    return pipeline._profile.clinical_timeline


@pytest.mark.parametrize("listing, result", [
    (procedure("INR", outcome="3.8"), lab("INR", value=3.8, flag="High")),
    (procedure("Urine protein", outcome="2+"), lab("Urine protein", value_text="2+", flag="High")),
    (procedure("Protein, urine", outcome="2+"), lab("Urine protein", value_text="2+", flag="High")),
    (procedure("Rapid strep antigen", outcome="Positive"),
     lab("Rapid strep antigen", value_text="Positive", flag="Abnormal")),
    (procedure("Urine protein"), lab("Urine protein", value_text="2+", flag="High")),
])
def test_a_later_result_is_never_absorbed_by_an_earlier_listing(tmp_path, listing, result):
    for timeline in (
        _merged(tmp_path, {"procedures": [listing]}, {"labs": [result]}),
        _merged(tmp_path, {"labs": [result]}, {"procedures": [listing]}),
        _merged(tmp_path, {"labs": [result]}, profile=PatientProfile.model_validate(
            {"clinical_timeline": {"procedures": [listing]}})),
    ):
        assert len(timeline.labs) == 1
        stored = timeline.labs[0]
        assert (stored.value, stored.value_text, stored.flag) == (
            result.get("value"), result.get("value_text"), result["flag"])
        assert stored.source_procedure["name"] == listing["name"]


def test_results_that_share_a_number_but_differ_in_text_stay_separate(tmp_path):
    timeline = _merged(tmp_path, {"labs": [
        lab("Urine culture", value=100000, unit="CFU/mL", value_text="Escherichia coli"),
        lab("Urine culture", value=100000, unit="CFU/mL", value_text="Enterococcus faecalis"),
        lab("Troponin I", value=0.01, unit="ng/mL", value_text="<0.01"),
        lab("Troponin I", value=0.01, unit="ng/mL"),
    ]})
    assert sorted((item.name, item.value_text or "") for item in timeline.labs) == [
        ("Troponin I", ""), ("Troponin I", "<0.01"),
        ("Urine culture", "Enterococcus faecalis"), ("Urine culture", "Escherichia coli"),
    ]


def test_a_whole_number_given_as_text_is_the_same_result(tmp_path):
    timeline = _merged(tmp_path, {"labs": [
        lab("Glucose", value=90, unit="mg/dL"), lab("Glucose", value_text="90", unit="mg/dL"),
        lab("Glucose", value_text="90 mg/dL", unit="mg/dL"),
    ]})
    assert len(timeline.labs) == 1


def test_text_extractor_keeps_result_text_beside_a_non_numeric_value():
    from src.extraction.text_extractor import TextExtractor

    results = {key: [] for key in (
        "labs", "procedures", "medications", "diagnoses", "allergies", "genetics", "notes",
    )}
    TextExtractor.__new__(TextExtractor)._merge_results(results, {"labs": [
        {"name": "Urine culture", "value": ">100,000", "unit": "CFU/mL",
         "value_text": "Escherichia coli", "test_date": "2000-01-02"},
        {"name": "Troponin I", "value": "<0.01", "unit": "ng/mL", "test_date": "2000-01-02"},
    ]}, "synthetic.pdf", 1)
    assert [item.value_text for item in results["labs"]] == ["Escherichia coli >100,000", "<0.01"]


def test_pipeline_does_not_merge_unreported_and_qualitative_results(tmp_path):
    from src.ui.pipeline import Pipeline

    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._profile = PatientProfile()
    pipeline._append_extraction_results({
        "procedures": [procedure("Urine glucose")],
        "labs": [lab("Urine glucose", value_text=value) for value in ["Negative", "Positive"]],
    })
    assert {item.value_text for item in pipeline._profile.clinical_timeline.labs} == {
        None, "Negative", "Positive",
    }


@pytest.mark.parametrize("name", [
    # Point-of-care kits are often named after the analyzer or the kit.
    "Sofia Influenza A+B FIA", "Veritor Flu A+B antigen 30T", "BinaxNOW COVID-19 Ag Card",
    "QuickVue Influenza A+B test", "OSOM Strep A test", "OraQuick HIV test",
    "Determine HIV-1/2 Ag/Ab Combo", "Lucira COVID-19 test",
    # A screen that names a test method, and tests named with the word "test".
    "COVID-19 screening test", "Pregnancy test", "hCG test", "HPV high risk DNA",
])
def test_recognizes_tests_named_after_their_kit_or_method(name):
    assert is_lab_test_name(name)


@pytest.mark.parametrize("name", [
    # Check-in and immunization screens.
    "COVID-19 screening", "COVID screening", "COVID-19 screen", "Influenza screening",
    "Flu screening", "Flu screen", "COVID-19 high-risk screening", "HIV high-risk screening",
    # An obstetric or fertility line, not a test.
    "High-risk pregnancy", "High risk pregnancy", "Pregnancy, high risk", "Pregnancy",
    "hCG", "Tests in pregnancy",
])
def test_keeps_screens_and_bare_words_as_procedures(name):
    assert not is_lab_test_name(name)


def test_extraction_prompts_keep_a_status_only_test_with_its_status():
    from pathlib import Path

    from src.analysis import gemini_fallback
    from src.extraction import text_extractor

    for module in (text_extractor, gemini_fallback):
        source = Path(module.__file__).read_text()
        rule = next(line for line in source.splitlines() if "Classify by the clinical item" in line)
        assert "a single laboratory test on a specimen" in rule
        assert "keep it under procedures with that status as the outcome" in rule


def test_listings_fold_only_into_a_result_from_the_same_calendar_day():
    # Dates the model wrote in words are not days the fold can compare.
    normalized = normalize_lab_procedures({
        "labs": [lab("Rapid strep test", value_text="Positive", test_date="September 28, 2024")],
        "procedures": [procedure("Rapid strep test", outcome="Positive",
                                 procedure_date="September 3, 2023")],
    })
    assert len(normalized["labs"]) == 2


def test_a_status_entry_absorbs_no_listing():
    normalized = normalize_lab_procedures({
        "labs": [lab("Urine culture", value_text="Cancelled")],
        "procedures": [procedure("Urine culture", outcome="Completed")],
    })
    assert len(normalized["labs"]) == 2


def test_a_flagged_entry_keeps_its_wording_when_a_status_listing_folds_in():
    from src.standardization.record_categories import lab_result_text

    normalized = normalize_lab_procedures({
        "labs": [lab("Urine protein", flag="Abnormal")],
        "procedures": [procedure("Urine protein", outcome="Completed")],
    })
    (only,) = normalized["labs"]
    assert lab_result_text(only) == "Value not recorded"


def test_a_second_listing_stays_when_the_result_already_has_a_source():
    normalized = normalize_lab_procedures({
        "labs": [lab("Hemoglobin A1c", value=8.4, unit="%", flag="High")],
        "procedures": [
            procedure("Hemoglobin A1c", outcome="Completed", provider="Synthetic clinician one"),
            procedure("Hemoglobin A1c", outcome="Cancelled", provider="Synthetic clinician two"),
        ],
    })
    providers = sorted((item.get("source_procedure") or {}).get("provider") or ""
                       for item in normalized["labs"])
    assert providers == ["Synthetic clinician one", "Synthetic clinician two"]


def test_an_interpretation_folds_only_into_a_result_flagged_that_way():
    def stored(result, outcome):
        return len(normalize_lab_procedures({
            "labs": [result], "procedures": [procedure("Hemoglobin A1c", outcome=outcome)],
        })["labs"])

    assert stored(lab("Hemoglobin A1c", value=9.4, flag="High"), "Abnormal") == 1
    assert stored(lab("Hemoglobin A1c", value=9.4, flag="High"), "Elevated") == 1
    assert stored(lab("Hemoglobin A1c", value=3.9, flag="Low"), "High") == 2
    assert stored(lab("Hemoglobin A1c", value=5.0), "High") == 2


def test_a_duplicate_with_the_flag_and_printed_range_fills_them_in(tmp_path):
    timeline = _merged(
        tmp_path,
        {"labs": [lab("Potassium", value=5.9, unit="mmol/L")]},
        {"labs": [lab("Potassium", value=5.9, unit="mmol/L", flag="High",
                      reference_low=3.5, reference_high=5.1)]},
    )
    (stored,) = timeline.labs
    assert (stored.flag, stored.reference_low, stored.reference_high) == ("High", 3.5, 5.1)
    assert stored.provenance.source_file == "synthetic-results.pdf"


def test_a_repeated_listing_that_says_the_same_thing_folds_away():
    kept = procedure("Hemoglobin A1c", outcome="Completed", provider=None, snomed_code=None)
    again = {"name": "Hemoglobin A1c", "procedure_date": "2000-01-02", "outcome": "Completed",
             "provenance": {"source_file": "synthetic-avs.pdf", "source_page": 1}}
    normalized = normalize_lab_procedures({
        "labs": [lab("Hemoglobin A1c", value=9.1, unit="%", flag="High", source_procedure=kept)],
        "procedures": [again],
    })
    assert len(normalized["labs"]) == 1


def test_the_extractor_keeps_the_day_of_a_date_with_a_time():
    from src.extraction.text_extractor import TextExtractor

    for text in ("2024-06-12 14:05", "2024-06-12T14:05:00", "2024-06-12"):
        assert TextExtractor._try_parse_date(text) == date(2024, 6, 12)
    assert TextExtractor._try_parse_date("June 12, 2024") is None
