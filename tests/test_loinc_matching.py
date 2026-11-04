"""A lab name gets a LOINC code only when its words support that one test.

The code decides the reference range attached to a result and which records
deduplication treats as the same test, so a name that is unknown, qualified
or ambiguous gets no code rather than the nearest-looking one. All records
are synthetic.
"""

from copy import deepcopy

import pytest

from src.models import PatientProfile
from src.standardization.loinc import CODES_VERSION, LOINC_SEED, LOINCDatabase


@pytest.fixture(scope="module")
def loinc():
    return LOINCDatabase()


def code_of(loinc, name):
    match = loinc.lookup(name)
    return match["code"] if match else None


@pytest.mark.parametrize("name", [
    "Urine ketones", "Ketones", "Vitamin K", "Haptoglobin", "Procalcitonin",
    "Prealbumin", "CK", "CK-MB", "C-peptide", "Mononucleosis screen",
    "Hemoglobin electrophoresis", "Urinalysis", "Transferrin", "pH",
    "Differential", "Stool DNA",
])
def test_short_names_never_match_inside_other_words(loinc, name):
    assert code_of(loinc, name) is None


@pytest.mark.parametrize("name", [
    "Creatinine, urine", "Urine sodium", "Leukocytes, urine", "CSF glucose",
    "Stool hemoglobin",
])
def test_another_specimen_never_borrows_the_blood_test(loinc, name):
    assert code_of(loinc, name) is None


@pytest.mark.parametrize("name", [
    "Free testosterone", "Calcium, ionized", "Non-HDL cholesterol",
    "Estimated average glucose", "BUN/Creatinine ratio", "Cholesterol/HDL ratio",
    "Bilirubin, indirect", "Free PSA", "PT/INR", "Albumin/Globulin ratio",
])
def test_a_qualifier_that_changes_the_test_blocks_the_match(loinc, name):
    assert code_of(loinc, name) is None


@pytest.mark.parametrize("name", [
    "Cholesterol/HDL", "CHOLESTEROL/HDL", "Total Cholesterol/HDL", "HDL/Total Cholesterol",
    "Cholesterol:HDL", "LDL/Cholesterol", "Bilirubin (Total/Direct)",
    "Bilirubin, Total & Direct", "Direct/Total Bilirubin", "Bilirubin, Total, Direct",
    "T3 Free/Total", "Free/Total T4", "Free T4 + Total T4",
])
def test_a_name_that_combines_tests_names_none_of_them(loinc, name):
    assert code_of(loinc, name) is None


@pytest.mark.parametrize("name, code", [
    ("Creatinine, Serum", "2160-0"), ("Serum creatinine", "2160-0"),
    ("AST (SGOT)", "1920-8"), ("ALT (SGPT)", "1742-6"),
    ("Cholesterol, Total", "2093-3"), ("Bilirubin, total", "1975-2"),
    ("Bilirubin, direct", "1968-7"), ("Hemoglobin A1c", "4548-4"),
    ("HbA1c", "4548-4"), ("Hgb A1c", "4548-4"), ("Glucose", "2345-7"),
    ("Glucose, fasting", "1558-6"), ("Iron, serum", "2498-4"),
    ("Uric acid", "3084-1"), ("Lipase", "3040-3"), ("Potassium", "2823-3"),
    ("K", "2823-3"), ("Urea nitrogen (BUN)", "3094-0"),
    ("Carbon dioxide, total", "2028-9"), ("Vitamin D, 25-Hydroxy", "62292-8"),
    ("Vitamin D, 25-OH, Total", "62292-8"), ("Urine protein", "5804-0"),
    ("Protein, urine", "5804-0"), ("Urine glucose", "25428-4"),
    ("Glucose, urine", "25428-4"), ("Albumin, urine", "14957-5"),
    ("Microalbumin, urine", "14957-5"), ("TSH", "3016-3"),
    ("Platelets", "777-3"), ("Testosterone, total", "2986-8"),
    ("Ferritin, serum", "2276-4"), ("Protein, total, serum", "2885-2"),
    ("Glucose, serum/plasma", "2345-7"), ("Albumin/Creatinine Ratio", "9318-7"),
    # Method and edition words leave the test unchanged.
    ("Triglyceride", "2571-8"), ("LDL Cholesterol, Calculated", "13457-7"),
    ("HbA1c (NGSP)", "4548-4"), ("Hemoglobin A1c, POC", "4548-4"),
    ("TSH, 3rd Generation", "3016-3"), ("Vitamin D, 25-OH, Total, IA", "62292-8"),
    ("Phosphorus, Inorganic", "2777-1"), ("Glucose in Blood", "2345-7"),
    # LOINC long names, as health-record exports write them.
    ("Potassium [Moles/volume] in Serum or Plasma", "2823-3"),
    ("Leukocytes [#/volume] in Blood by Automated count", "6690-2"),
    ("Ferritin [Mass/volume] in Serum or Plasma", "2276-4"),
    ("Iron binding capacity [Mass/volume] in Serum or Plasma", "2500-7"),
    ("Protein [Mass/volume] in Urine by Test strip", "5804-0"),
])
def test_known_tests_match_in_common_report_formats(loinc, name, code):
    assert code_of(loinc, name) == code


@pytest.mark.parametrize("name", [
    "Erythrocytes [#/area] in Urine sediment by Microscopy high power field",
    "Glucose [Mass/volume] in Cerebral spinal fluid",
    "Calcium.ionized [Moles/volume] in Blood",
])
def test_a_long_name_for_another_specimen_or_form_gets_no_code(loinc, name):
    assert code_of(loinc, name) is None


# Codes checked against loinc.org on 2026-11-03; several seed rows used to hold
# another test's code.
@pytest.mark.parametrize("name, code", [
    ("Free T4", "3024-7"), ("Free T3", "3051-0"), ("Fasting glucose", "1558-6"),
    ("TIBC", "2500-7"), ("Ferritin", "2276-4"), ("Iron saturation", "2502-3"),
    ("Vitamin D", "62292-8"), ("PTT", "14979-9"), ("Microalbumin", "14957-5"),
    ("ACR", "9318-7"), ("Creatinine clearance", "2164-2"), ("DHEA-S", "2191-5"),
    ("Cortisol", "2143-6"), ("Insulin", "20448-7"), ("ANA", "8061-4"),
    ("Anti-dsDNA", "5130-0"), ("Rheumatoid factor", "11572-5"), ("Anti-CCP", "33935-8"),
    ("AFP", "1834-1"), ("CA 19-9", "24108-3"), ("Urine RBC", "13945-1"),
    ("Hepatitis A IgM", "13950-1"), ("Hepatitis C antibody", "16128-1"),
    ("Hemoglobin S", "4625-0"), ("Bicarbonate", "1963-8"), ("Lactate", "2524-7"),
])
def test_seed_rows_carry_their_own_standard_code(loinc, name, code):
    assert code_of(loinc, name) == code


def test_each_seed_code_names_one_test():
    codes = [row[0] for row in LOINC_SEED]
    assert len(codes) == len(set(codes))


def test_iron_and_ast_no_longer_borrow_another_test_s_range(loinc):
    # Iron's normal range differs by sex, so the seed gives none; AST has its own.
    iron, ast = loinc.lookup("Iron"), loinc.lookup("AST")
    assert (iron["reference_low"], iron["reference_high"]) == (None, None)
    assert (ast["reference_low"], ast["reference_high"]) == (10.0, 40.0)


def test_ua_is_not_read_as_uric_acid(loinc):
    # On lab orders "UA" almost always means urinalysis.
    assert code_of(loinc, "UA") is None


# ── Attaching a code and range to an entry ───────────────────

@pytest.mark.parametrize("name, unit, expected", [
    # A unit from another kind of test means the name match is wrong.
    ("WBC", "/HPF", (None, None, None)),
    ("RBC", "/hpf", (None, None, None)),
    ("Glucose", "mmol/L", (None, None, None)),
    ("Hemoglobin", "g/L", (None, None, None)),
    # The same unit written another way still agrees.
    ("Potassium", "mmol/L", ("2823-3", 3.5, 5.0)),
    ("WBC", "K/uL", ("6690-2", 4.5, 11.0)),
    ("Platelets", "x10E3/uL", ("777-3", 150.0, 400.0)),
    ("Ferritin", "ug/L", ("2276-4", None, None)),
    ("TSH", "uIU/mL", ("3016-3", 0.4, 4.0)),
    ("INR", "ratio", ("6301-6", 0.8, 1.1)),
    # Without a unit the code stands, but not the range: the value could be
    # in another unit system.
    ("Glucose", None, ("2345-7", None, None)),
])
def test_a_name_match_is_used_only_when_the_unit_agrees(loinc, name, unit, expected):
    assert loinc.standardize(name, unit=unit) == expected


def test_a_code_the_record_supplied_is_kept(loinc):
    # Not in the seed: kept as written, with no range invented for it.
    assert loinc.standardize("Synthetic marker", code="99999-9", unit="mg/dL") == (
        "99999-9", None, None)
    assert loinc.standardize("Ferritin", code="99999-9") == ("99999-9", None, None)
    # In the seed: the range comes along only when the units agree.
    assert loinc.standardize("Iron binding capacity", code="2500-7", unit="ug/dL") == (
        "2500-7", 250.0, 370.0)
    assert loinc.standardize("Glucose", code="2345-7", unit="mmol/L") == ("2345-7", None, None)
    # A range already on the entry is never replaced.
    assert loinc.standardize("Potassium", code="2823-3", reference_low=3.6,
                             reference_high=5.2) == ("2823-3", 3.6, 5.2)


def _lab(name, **fields):
    return {"name": name, "test_date": "2000-01-02",
            "provenance": {"source_file": "synthetic-results.pdf", "source_page": 1}, **fields}


def test_new_extractions_keep_the_code_the_record_printed(tmp_path):
    from src.ui.pipeline import Pipeline

    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._profile = PatientProfile()
    pipeline._append_extraction_results({"labs": [
        _lab("Potassium [Moles/volume] in Serum or Plasma", loinc_code="2823-3",
             value=5.9, unit="mmol/L"),
        _lab("Triglyceride", loinc_code="2571-8", value=120, unit="mg/dL"),
        _lab("HbA1c (Synthetic method)", loinc_code="4548-4", value=6.1, unit="%"),
        _lab("Potassium", value=5.9, unit="mmol/L"),
    ]})
    stored = {(lab.name, lab.loinc_code, lab.reference_low, lab.reference_high)
              for lab in pipeline._profile.clinical_timeline.labs}
    assert stored == {
        ("Potassium [Moles/volume] in Serum or Plasma", "2823-3", 3.5, 5.0),
        ("Triglyceride", "2571-8", None, 150.0),
        ("HbA1c (Synthetic method)", "4548-4", 4.0, 5.6),
    }


# What the matcher before 2026-11-03 saved, and what it is repaired to.
SAVED_BY_OLD_MATCHER = [
    # 'k' inside 'ketones' was Potassium.
    (_lab("Urine ketones", value_text="Negative", loinc_code="2823-3",
          reference_low=3.5, reference_high=5.0), (None, None, None)),
    # Iron's code was shared with Uric Acid, whose range was attached: it goes,
    # and no seed range replaces it, as iron's normal range differs by sex.
    (_lab("Iron", value=80, unit="ug/dL", loinc_code="2498-4", reference_low=3.0,
          reference_high=7.0), ("2498-4", None, None)),
    (_lab("Iron", value=80, loinc_code="2498-4", reference_low=3.0, reference_high=7.0),
     ("2498-4", None, None)),
    # The old matcher returned this code with Lipase's range.
    (_lab("AST", value=30, unit="U/L", loinc_code="1920-8", reference_low=0.0,
          reference_high=160.0), ("1920-8", 10.0, 40.0)),
    # The old seed's Ferritin code, which is TIBC's, and its one-sex range.
    (_lab("Ferritin", value=40, unit="ng/mL", loinc_code="2500-7", reference_low=12.0,
          reference_high=150.0), ("2276-4", None, None)),
    # A record's own TIBC code, given Ferritin's range by the old seed.
    (_lab("Iron binding capacity [Mass/volume] in Serum or Plasma", value=320, unit="ug/dL",
          loinc_code="2500-7", reference_low=12.0, reference_high=150.0),
     ("2500-7", 250.0, 370.0)),
    # A long name the old matcher also coded: the code and range stay.
    (_lab("Potassium [Moles/volume] in Serum or Plasma", value=4.0, unit="mmol/L",
          loinc_code="2823-3", reference_low=3.5, reference_high=5.0),
     ("2823-3", 3.5, 5.0)),
    # A code and range the old matcher never produced came from the record.
    (_lab("Erythrocyte distribution width", value=13, loinc_code="788-0",
          reference_low=11.0, reference_high=15.0), ("788-0", 11.0, 15.0)),
    (_lab("Glucose", value=90, unit="mg/dL", loinc_code="2345-7", reference_low=70.0,
          reference_high=100.0), ("2345-7", 70.0, 100.0)),
    # A record range is kept when an old code is removed.
    (_lab("Haptoglobin", value=120, loinc_code="5902-2", reference_low=30.0,
          reference_high=200.0), (None, 30.0, 200.0)),
]


def _coded(lab):
    get = lab.get if isinstance(lab, dict) else lambda key: getattr(lab, key)
    return get("loinc_code"), get("reference_low"), get("reference_high")


class _SavedVault:
    def __init__(self, profile):
        self.profile, self.saved = profile, None

    def load_profile(self):
        return deepcopy(self.profile)

    def save_profile(self, profile):
        self.saved = profile


def test_a_saved_profile_is_repaired_once_when_the_pipeline_loads_it(tmp_path):
    from src.ui.pipeline import Pipeline

    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._vault = _SavedVault({"clinical_timeline": {
        "labs": [lab for lab, _ in SAVED_BY_OLD_MATCHER]}})
    profile = pipeline._load_profile()
    assert [_coded(lab) for lab in profile.clinical_timeline.labs] == [
        expected for _, expected in SAVED_BY_OLD_MATCHER]
    assert profile.lab_codes_version == CODES_VERSION

    # Once repaired, a code a later record supplies is never redone.
    pipeline._profile = profile
    pipeline._append_extraction_results({"labs": [
        _lab("Urine ketones", value_text="Trace", loinc_code="2823-3", test_date="2000-02-03"),
    ]})
    pipeline._vault = _SavedVault(pipeline._profile.model_dump(mode="json"))
    reloaded = pipeline._load_profile()
    assert _coded(reloaded.clinical_timeline.labs[-1])[0] == "2823-3"


def test_the_app_shows_repaired_codes_as_soon_as_a_profile_opens(monkeypatch):
    import src.encryption
    import src.ui.app as module

    saved = {"clinical_timeline": {"labs": [lab for lab, _ in SAVED_BY_OLD_MATCHER]}}

    class FakeVault(_SavedVault):
        def __init__(self, *args, **kwargs):
            super().__init__(saved)
            self.active_profile_id = None

        def list_profiles(self):
            return [{"id": "synthetic"}]

        def load_profile(self, profile_id=None):
            return deepcopy(saved)

    monkeypatch.setattr(src.encryption, "EncryptedVault", FakeVault)
    monkeypatch.setattr(module, "_passphrase", "synthetic-test-passphrase")
    monkeypatch.setattr(module, "_pipeline_thread", None)
    monkeypatch.setattr(module, "_active_profile_id", None)
    monkeypatch.setattr(module, "_profile_data", None)
    with module.app.test_client() as client:
        assert client.post("/api/profiles/synthetic/activate").status_code == 200
        labs = client.get("/api/labs").get_json()
    assert [_coded(lab) for lab in labs] == [expected for _, expected in SAVED_BY_OLD_MATCHER]
    assert module._profile_data["lab_codes_version"] == CODES_VERSION


@pytest.mark.parametrize("name, code", [
    # A method that names the test is kept; one that only says how it was run is not.
    ("C reactive protein [Mass/volume] in Serum or Plasma by High sensitivity method", "30522-7"),
    ("C reactive protein [Mass/volume] in Blood by High sensitivity method", "30522-7"),
    ("C reactive protein [Mass/volume] in Serum or Plasma", "1988-5"),
    ("Hematocrit [Volume Fraction] of Blood by Automated count", "4544-3"),
    ("MCV [Entitic volume] by Automated count", "787-2"),
    ("Hemoglobin A1c/Hemoglobin.total in Blood", "4548-4"),
    ("Glomerular filtration rate/1.73 sq M.predicted [Volume Rate/Area] in Serum or Plasma"
     " by Creatinine-based formula (MDRD)", "33914-3"),
    ("Erythrocyte sedimentation rate by Westergren method", "4537-7"),
    ("RDW-CV", "788-0"), ("CO2 Content", "2028-9"), ("Pro-BNP", "33762-6"),
    ("GGT (GGT)", "2324-2"), ("Testosterone, Total, MS", "2986-8"),
])
def test_official_long_names_and_common_labels_keep_their_test(loinc, name, code):
    assert code_of(loinc, name) == code


@pytest.mark.parametrize("name", [
    # The method makes it another test than the seed row.
    "Troponin I.cardiac [Mass/volume] in Serum or Plasma by High sensitivity method",
    "Hemoglobin A1c/Hemoglobin.total in Blood by HPLC",
    "Glomerular filtration rate/1.73 sq M.predicted [Volume Rate/Area] in Serum or Plasma"
    " by Creatinine-based formula (CKD-EPI)",
    # The property is another kind of measurement than the seed row's unit.
    "Glucose [Moles/volume] in Serum or Plasma", "Creatinine [Moles/volume] in Serum or Plasma",
    "Calcium [Moles/volume] in Serum or Plasma", "Lactate [Mass/volume] in Serum or Plasma",
])
def test_a_method_or_property_that_changes_the_test_gets_no_code(loinc, name):
    assert code_of(loinc, name) is None


def test_a_seed_range_needs_a_unit_that_agrees(loinc):
    # Without a unit the value could be in another unit system.
    assert loinc.standardize("Glucose") == ("2345-7", None, None)
    assert loinc.standardize("Glucose", unit="mg/dL") == ("2345-7", 70.0, 100.0)
    # A test without units needs none.
    assert loinc.standardize("INR") == ("6301-6", 0.8, 1.1)
    assert loinc.standardize("Urine pH") == ("5803-2", 4.5, 8.0)


def test_hs_crp_keeps_its_code_and_range_through_the_repair(loinc):
    name = "C reactive protein [Mass/volume] in Serum or Plasma by High sensitivity method"
    assert loinc.standardize(name, unit="mg/L") == ("30522-7", None, 1.0)
    assert loinc.standardize(name, code="30522-7", unit="mg/L", reference_high=1.0,
                             saved_by_old_matcher=True) == ("30522-7", None, 1.0)


def test_the_pipeline_repairs_shared_codes_before_folding_listings(tmp_path):
    from src.ui.pipeline import Pipeline

    pipeline = Pipeline(tmp_path, "synthetic-test-passphrase")
    pipeline._vault = _SavedVault({"clinical_timeline": {"labs": [
        _lab("Creatine Kinase", loinc_code="2160-0"),
        _lab("Creatinine", value=1.0, unit="mg/dL", loinc_code="2160-0",
             reference_low=0.6, reference_high=1.2),
    ]}})
    profile = pipeline._load_profile()
    assert sorted(lab.name for lab in profile.clinical_timeline.labs) == [
        "Creatine Kinase", "Creatinine"]


class _FakeVault(_SavedVault):
    def __init__(self, saved):
        super().__init__(saved)
        self.active_profile_id = None

    def list_profiles(self):
        return [{"id": "synthetic"}]

    def load_profile(self, profile_id=None):
        return deepcopy(self.profile)


def _activate(monkeypatch, saved):
    import src.encryption
    import src.ui.app as module

    monkeypatch.setattr(src.encryption, "EncryptedVault", lambda *a, **k: _FakeVault(saved))
    monkeypatch.setattr(module, "_passphrase", "synthetic-test-passphrase")
    monkeypatch.setattr(module, "_pipeline_thread", None)
    monkeypatch.setattr(module, "_active_profile_id", None)
    monkeypatch.setattr(module, "_profile_data", None)
    client = module.app.test_client()
    assert client.post("/api/profiles/synthetic/activate").status_code == 200
    return module, client


def test_an_empty_profile_stays_empty_when_it_opens(monkeypatch):
    module, client = _activate(monkeypatch, {})
    assert module._profile_data == {}
    assert client.get("/api/dashboard").get_json()["has_data"] is False


def test_the_saved_sample_patient_is_left_exactly_as_saved(monkeypatch):
    from copy import deepcopy

    import src.ui.app as app_module

    sample = app_module._build_demo_profile()
    module, _ = _activate(monkeypatch, deepcopy(sample))
    assert module._profile_data == sample
    assert module._matches_builtin_demo_profile(module._profile_data)


def test_the_repair_writes_only_fields_it_changes(monkeypatch):
    module, _ = _activate(monkeypatch, {"clinical_timeline": {"labs": [
        {"name": "Synthetic marker", "value": 1, "test_date": "2000-01-02"},
    ]}})
    assert module._profile_data["clinical_timeline"]["labs"] == [
        {"name": "Synthetic marker", "value": 1, "test_date": "2000-01-02"},
    ]


def test_every_view_sees_procedure_listed_tests_as_labs_once_a_profile_opens(monkeypatch):
    module, _ = _activate(monkeypatch, {"clinical_timeline": {
        "labs": [_lab("Hemoglobin A1c", value=8.4, unit="%", flag="High", test_date="2025-09-29")],
        "procedures": [{"name": "Hemoglobin A1c", "procedure_date": "2026-09-19",
                        "outcome": "6.8 %", "provenance": {"source_file": "synthetic.pdf",
                                                           "source_page": 2}}],
    }})
    timeline = module._profile_data["clinical_timeline"]
    assert timeline["procedures"] == []
    assert sorted(lab["test_date"] for lab in timeline["labs"]) == ["2025-09-29", "2026-09-19"]


def test_saves_during_a_run_keep_the_lab_code_version(monkeypatch):
    import src.ui.app as module

    monkeypatch.setattr(module, "_profile_data", {"demographics": {"sex": "synthetic"}})
    module._merge_pipeline_snapshot({"clinical_timeline": {"labs": []},
                                     "lab_codes_version": CODES_VERSION})
    assert module._profile_data == {"demographics": {"sex": "synthetic"},
                                    "clinical_timeline": {"labs": []},
                                    "lab_codes_version": CODES_VERSION}


@pytest.mark.parametrize("name, code", [
    # A qualifier written in brackets is part of the name, not a LOINC property.
    ("Creatinine [Urine]", None), ("Sodium [Urine]", None), ("Calcium [Ionized]", None),
    ("Glucose [CSF]", None), ("Cortisol [PM]", None), ("Testosterone [Free]", None),
    ("Iron [TIBC]", None), ("Folate [RBC]", None), ("PSA [Ultrasensitive]", None),
    ("Cholesterol [LDL]", "13457-7"), ("Cholesterol [HDL]", "2085-9"),
    ("Bilirubin [Direct]", "1968-7"), ("CRP [hs]", "30522-7"),
    # Maternal serum AFP is a prenatal screen, not the tumor marker.
    ("MS-AFP", None), ("AFP, MS", None), ("MS AFP", None), ("AFP (MS)", None),
])
def test_a_bracketed_qualifier_or_a_maternal_serum_label_keeps_its_meaning(loinc, name, code):
    assert code_of(loinc, name) == code


@pytest.mark.parametrize("name, code", [
    ("Thyrotropin [Units/volume] in Serum or Plasma by Detection limit <= 0.005 mIU/L", "3016-3"),
    ("Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma by With P-5'-P", "1742-6"),
    ("Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma"
     " by No addition of P-5'-P", "1742-6"),
    ("Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma by With P-5'-P", "1920-8"),
    ("Albumin [Mass/volume] in Serum or Plasma by Bromocresol green (BCG) dye binding method", "1751-7"),
    ("Albumin [Mass/volume] in Serum or Plasma by Bromocresol purple (BCP) dye binding method", "1751-7"),
    ("Hemoglobin [Mass/volume] in Blood by Oximetry", "718-7"),
    ("Lactate dehydrogenase [Enzymatic activity/volume] in Serum or Plasma"
     " by Lactate to pyruvate reaction", "2532-0"),
    ("Testosterone, Total, MS", "2986-8"), ("NT-Pro BNP", "33762-6"),
    ("Sedimentation Rate-Westergren", "4537-7"),
])
def test_a_method_that_only_says_how_the_test_ran_keeps_its_code(loinc, name, code):
    assert code_of(loinc, name) == code


@pytest.mark.parametrize("name, unit, code", [
    ("Testosterone", "ng/dL", "2986-8"), ("Ferritin", "ng/mL", "2276-4"),
    ("RBC", "10^6/uL", "789-8"), ("ESR", "mm/hr", "4537-7"), ("Uric Acid", "mg/dL", "3084-1"),
    ("Iron", "ug/dL", "2498-4"),
])
def test_a_range_that_depends_on_sex_or_age_is_never_attached(loinc, name, unit, code):
    # No single range holds for every adult, and the record's own is not kept.
    assert loinc.standardize(name, unit=unit) == (code, None, None)


def test_a_test_moved_from_procedures_when_a_profile_opens_gets_its_code(monkeypatch):
    module, client = _activate(monkeypatch, {"clinical_timeline": {
        "labs": [_lab("HbA1c", value=6.1, unit="%", test_date="2026-01-10")],
        "procedures": [{"name": "Hemoglobin A1c", "procedure_date": "2026-10-01",
                        "outcome": "9.4 % (H)", "provenance": {"source_file": "synthetic.pdf",
                                                               "source_page": 2}}],
    }})
    labs = module._profile_data["clinical_timeline"]["labs"]
    assert {lab["loinc_code"] for lab in labs} == {"4548-4"}
    latest = client.get("/api/dashboard").get_json()["latest_labs"]
    assert [(item["name"], item["test_date"]) for item in latest] == [("Hemoglobin A1c", "2026-10-01")]
