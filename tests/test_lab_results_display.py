"""A test listed without a result is shown as such, and never stands in for one.

All records are synthetic.
"""

import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from src.models import PatientProfile
from src.standardization.record_categories import lab_has_result, lab_result_text, says_no_result

LAB_RESULTS_JS = Path(__file__).parents[1] / "src/ui/static/js/lab_results.js"
PROVENANCE = {"source_file": "synthetic-results.pdf", "source_page": 1}

STATUS_TEXTS = [
    "Completed", "completed 03/04/2000", "Done", "Ordered", "Order placed", "Pending",
    "In progress", "Scheduled", "Cancelled - patient declined", "Canceled", "Declined",
    "Specimen hemolyzed - test not performed", "QNS", "Quantity not sufficient",
    "Specimen rejected", "See note", "See comment", "Not performed", "Not done",
    "Not reported", "Result to follow", "Sent to lab", "Collected", "N/A", "TNP",
    "Unable to obtain specimen", "Awaiting results", "No result available",
    "Collected Mar 4, 2000 10:30 AM",
]
RESULT_TEXTS = [
    "Negative", "Positive", "2+", "3+ (high)", "Not detected", "No growth", "None seen",
    "248 mg/dL", "Completed - normal", "Done; negative", "1:160", "Reactive", "Normal",
    "WNL", "Trace", "<0.01", "Completed 248", "Indeterminate", "Specimen positive",
]


def lab(name, **fields):
    return {"name": name, "test_date": "2000-01-02", "provenance": PROVENANCE, **fields}


def procedure(name, **fields):
    return {"name": name, "procedure_date": "2000-01-02", "provenance": PROVENANCE, **fields}


@pytest.mark.parametrize("text", STATUS_TEXTS)
def test_text_that_only_reports_a_status_says_no_result(text):
    assert says_no_result(text)


@pytest.mark.parametrize("text", RESULT_TEXTS + ["", None])
def test_text_that_states_a_finding_is_a_result(text):
    assert not says_no_result(text)


@pytest.mark.parametrize("record, expected", [
    ({"value": 0}, True), ({"value_text": "Negative"}, True), ({"flag": "High"}, True),
    ({}, False), ({"value": None, "value_text": "  ", "flag": ""}, False),
    # A procedure outcome is the result when it states one, not when it is a status.
    ({"source_procedure": {"outcome": "Positive"}}, True),
    ({"source_procedure": {"outcome": 0}}, True),
    ({"source_procedure": {"outcome": "Completed"}}, False),
    # Result text that says no result was produced is not a result.
    ({"value_text": "Specimen hemolyzed - test not performed"}, False),
    ({"value_text": "Cancelled", "flag": "Abnormal"}, True),
])
def test_a_result_is_a_value_a_flag_or_text_that_states_one(record, expected):
    assert lab_has_result(record) is expected


def test_only_the_entry_itself_counts_when_outcomes_are_left_out():
    listed = {"source_procedure": {"outcome": "Positive"}}
    assert not lab_has_result(listed, include_outcome=False)
    assert lab_has_result({"value_text": "Positive"}, include_outcome=False)


@pytest.mark.parametrize("record, expected", [
    ({"value": 0, "unit": "mg/dL"}, "0 mg/dL"),
    ({"value": 4.5}, "4.5"),
    ({"value_text": "Negative"}, "Negative"),
    ({"value": 7.0, "value_text": "7.0 %", "unit": "%"}, "7 %"),
    ({"source_procedure": {"outcome": "Positive"}}, "Positive (listed with procedures)"),
    ({"value_text": "2+", "source_procedure": {"outcome": "Completed"}}, "2+"),
    ({"source_procedure": {"outcome": " "}}, "Result not recorded"),
    ({"source_procedure": {"outcome": 0}}, "0 (listed with procedures)"),
    ({}, "Result not recorded"),
    # Numbers read the same in the report as on screen.
    ({"value": 5e-05, "unit": "ng/mL"}, "0.00005 ng/mL"),
    ({"value": 1e-07}, "1e-7"),
    ({"value": 1e21}, "1e+21"),
    ({"value": 123456.5}, "123456.5"),
])
def test_result_text_states_what_the_record_says(record, expected):
    assert lab_result_text(record) == expected


# ── JS mirror (src/ui/static/js/lab_results.js) ──────────────

def run_lab_results_js(expression):
    if not shutil.which("node"):
        pytest.skip("Node unavailable")
    script = (
        "const vm = require('vm'), fs = require('fs');"
        "const context = {}; vm.createContext(context);"
        f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB_RESULTS_JS))}, 'utf8'), context);"
        f"process.stdout.write(JSON.stringify(vm.runInContext({json.dumps(expression)}, context)));"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_js_result_rules_match_the_server():
    cases = [
        {"value": 0, "unit": "mg/dL"}, {"value": 4.5}, {"value_text": "Negative"},
        {"source_procedure": {"outcome": "Positive"}}, {"source_procedure": {"outcome": 0}},
        {"source_procedure": {"outcome": "Completed"}}, {"flag": "High"}, {},
        {"value_text": "Specimen hemolyzed - test not performed"},
        {"value_text": "Cancelled", "flag": "Abnormal"},
        {"value": 5e-05, "unit": "ng/mL"}, {"value": 1e-07}, {"value": 1e21}, {"value": 123456.5},
    ]
    has_result, text = run_lab_results_js(
        f"var cases = {json.dumps(cases)};"
        "[cases.map(function(c) { return LabResults.hasResult(c); }),"
        " cases.map(function(c) { return LabResults.resultText(c, true); })]"
    )
    assert has_result == [lab_has_result(case) for case in cases]
    assert text == [lab_result_text(case) for case in cases]


def test_js_status_words_match_the_server():
    texts = STATUS_TEXTS + RESULT_TEXTS
    said = run_lab_results_js(
        f"{json.dumps(texts)}.map(function(t) {{ return LabResults.saysNoResult(t); }})"
    )
    assert said == [says_no_result(text) for text in texts]


def test_js_latest_prefers_the_newest_entry_with_a_result():
    picked = run_lab_results_js(
        "[LabResults.newestWithResult([{test_date: '2000-03-04'}, {test_date: '2000-02-03', value: 9}, {test_date: '2000-01-02', value: 7}]),"
        " LabResults.newestWithResult([{test_date: '2000-03-04'}, {test_date: '2000-02-03'}]),"
        # A newer outcome written with the procedures is the latest result...
        " LabResults.newestWithResult([{test_date: '2000-03-04', source_procedure: {outcome: 'Positive'}}, {test_date: '2000-01-02', value_text: 'Negative'}]),"
        # ...but a newer status is not.
        " LabResults.newestWithResult([{test_date: '2000-03-04', source_procedure: {outcome: 'Completed'}}, {test_date: '2000-01-02', value_text: 'Negative'}])]"
    )
    assert picked == [
        {"test_date": "2000-02-03", "value": 9}, {"test_date": "2000-03-04"},
        {"test_date": "2000-03-04", "source_procedure": {"outcome": "Positive"}},
        {"test_date": "2000-01-02", "value_text": "Negative"},
    ]


def test_dashboard_panel_states_qualitative_and_zero_results():
    if not shutil.which("node"):
        pytest.skip("Node unavailable")
    charts = Path(__file__).parents[1] / "src/ui/static/js/dashboard_charts.js"
    labs = [
        {"name": "Rapid strep", "value_text": "Positive", "flag": "Abnormal"},
        {"name": "Urine protein", "value_text": "2+", "flag": "High"},
        {"name": "Sodium", "value": 140, "unit": "mEq/L", "reference_low": 136, "reference_high": 145},
        {"name": "Marker", "value": 0, "unit": "%"},
        {"name": "Strep listed", "source_procedure": {"outcome": "Negative"}},
    ]
    script = (
        "const fs = require('fs'); const texts = [];"
        "function node() { const o = { attr: () => o, append: () => node(),"
        " text: (t) => { texts.push(String(t)); return o; } }; return o; }"
        "var d3 = { select: () => node(), scaleLinear: () => { const s = () => 0;"
        " s.domain = () => s; s.range = () => s; s.clamp = () => s; return s; } };"
        "var document = { getElementById: () => ({ clientWidth: 400, firstChild: null }) };"
        f"eval(fs.readFileSync({json.dumps(str(LAB_RESULTS_JS))}, 'utf8') + ';'"
        f" + fs.readFileSync({json.dumps(str(charts))}, 'utf8'));"
        f"DashboardCharts.renderLabRangeBars('panel', {json.dumps(labs)});"
        "process.stdout.write(JSON.stringify(texts));"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    shown = json.loads(result.stdout)
    assert "Positive (Abnormal)" in shown and "2+ (HIGH)" in shown
    assert "140 mEq/L" in shown and "0 %" in shown
    assert "Negative (listed with procedures)" in shown
    assert "—" not in shown and "— %" not in shown


def test_js_flag_text_never_calls_an_unflagged_result_normal():
    labels = run_lab_results_js(
        "[LabResults.flagText(null, true), LabResults.flagText('', false), LabResults.flagText('Normal', true),"
        " LabResults.flagText('h', true), LabResults.flagText('Critical low', true), LabResults.flagText('Abnormal', true)]"
    )
    assert labels == ["Not flagged", "", "Normal", "HIGH", "LOW", "Abnormal"]


# ── Server views ─────────────────────────────────────────────

def _client_with(monkeypatch, timeline):
    import src.ui.app as module

    monkeypatch.setattr(module, "_profile_data", {"clinical_timeline": timeline})
    return module.app.test_client()


def test_timeline_shows_a_procedure_outcome_as_the_listed_result(monkeypatch):
    with _client_with(monkeypatch, {"procedures": [
        procedure("Rapid strep antigen", outcome="Positive"),
        procedure("Urine nitrite"),
    ]}) as client:
        events = client.get("/api/timeline").get_json()
    details = {e["name"]: e["detail"] for e in events if e["type"] == "lab"}
    assert details == {
        "Rapid strep antigen": "Positive (listed with procedures)",
        "Urine nitrite": "Result not recorded",
    }


def test_timeline_related_labs_prefer_the_entry_that_has_a_result(monkeypatch):
    with _client_with(monkeypatch, {
        "labs": [lab("Urine protein"), lab("Urine protein", value_text="2+", flag="High")],
        "diagnoses": [{"name": "Synthetic condition", "date_diagnosed": "2000-01-02",
                       "provenance": PROVENANCE}],
    }) as client:
        events = client.get("/api/timeline").get_json()
    diagnosis = next(e for e in events if e["type"] == "diagnosis")
    assert [(item["title"], item["detail"]) for item in diagnosis["related_labs"]] == [
        ("Urine protein", "2+ High"),
    ]


def test_dashboard_latest_counts_a_flag_without_a_value():
    from src.ui.app import _get_latest_labs

    older = lab("Potassium", value=4.1)
    flagged = lab("Potassium", flag="High", test_date="2000-02-03")
    listed = lab("Potassium", test_date="2000-03-04")
    assert [entry["test_date"] for entry in _get_latest_labs([older, flagged, listed])] == [
        "2000-02-03",
    ]


def test_dashboard_latest_uses_a_newer_outcome_but_not_a_newer_status():
    from src.ui.app import _get_latest_labs

    latest = _get_latest_labs([
        lab("Rapid strep antigen", value_text="Negative"),
        lab("Rapid strep antigen", test_date="2000-03-04",
            source_procedure={"outcome": "Positive"}),
        lab("Potassium", value=5.9, flag="High"),
        lab("Potassium", test_date="2000-02-03",
            value_text="Specimen hemolyzed - test not performed"),
    ])
    assert {entry["name"]: entry["test_date"] for entry in latest} == {
        "Rapid strep antigen": "2000-03-04", "Potassium": "2000-01-02",
    }


def test_visit_prep_flags_the_measured_result_not_a_newer_listing():
    from src.analysis.visit_prep import VisitPrepGenerator

    flagged = VisitPrepGenerator()._flagged_labs({"labs": [
        lab("Urine protein", value_text="2+", flag="High"),
        lab("Urine protein", test_date="2000-02-03"),
        lab("Potassium", value=5.9, unit="mmol/L", flag="High"),
        lab("Potassium", test_date="2000-02-03",
            value_text="Specimen hemolyzed - test not performed"),
    ]})
    assert [(f["name"], f["result"], f["flag"], f["test_date"]) for f in flagged] == [
        ("Urine protein", "2+", "high", "2000-01-02"),
        ("Potassium", "5.9 mmol/L", "high", "2000-01-02"),
    ]


def test_visit_prep_sheet_states_each_flagged_result_as_recorded(tmp_path):
    import docx

    from src.analysis.visit_prep import VisitPrepGenerator

    generator = VisitPrepGenerator()
    flagged = generator._flagged_labs({"labs": [
        lab("Urine protein", value_text="1+", unit=None, flag="High"),
        lab("Urine protein", value_text="3+", unit=None, flag="High", test_date="2000-02-03"),
        lab("Hemoglobin A1c", flag="High", unit=None),
        lab("Ferritin", value=8, unit=None, flag="Low"),
        lab("Glucose", value=0, unit="mg/dL", flag="Low"),
        lab("Sodium", value=150, unit="mmol/L", flag="High"),
        lab("Sodium", value=140, unit="mmol/L", test_date="1999-12-01"),
    ]})
    assert {f["name"]: (f["result"], f["trend"]) for f in flagged} == {
        "Urine protein": ("3+", "—"),
        "Hemoglobin A1c": ("Value not recorded", "—"),
        "Ferritin": ("8", "—"),
        "Glucose": ("0 mg/dL", "—"),
        "Sodium": ("150 mmol/L", "↑"),
    }
    out = generator.generate_docx({"flagged_labs": flagged}, tmp_path / "visit.docx")
    cells = [cell.text for table in docx.Document(str(out)).tables
             for row in table.rows for cell in row.cells]
    assert "3+" in cells and "0 mg/dL" in cells
    assert not [cell for cell in cells if "None" in cell]
    app_js = (Path(__file__).parents[1] / "src/ui/static/app.js").read_text()
    assert "return [l.name, l.result || LabResults.resultText(l, true)," in app_js


def test_cascade_lookup_ignores_entries_without_results():
    from src.analysis.biomarker_cascades import BiomarkerCascadeEngine

    lookup = BiomarkerCascadeEngine()._build_lab_lookup([
        lab("Ferritin", value=8, flag="Low"), lab("Ferritin", test_date="2000-02-03"),
    ])
    assert (lookup["ferritin"]["value"], lookup["ferritin"]["flag"]) == (8, "low")


def test_cascade_markers_state_the_result_as_recorded():
    from src.analysis.biomarker_cascades import BiomarkerCascadeEngine

    engine = BiomarkerCascadeEngine()
    lookup = engine._build_lab_lookup([
        lab("Glucose", value_text="Positive", unit=None, flag="High"),
        lab("Hemoglobin", value=8.0, unit=None, flag="Low"),
    ])
    shown = {name: entry["display"] for name, entry in lookup.items()}
    assert shown == {"glucose": "Positive", "hemoglobin": "8"}
    match = engine._match_node({"tests": ["Glucose"], "flag": "high"}, lookup)
    assert match["display"] == "Positive"


def test_snowball_input_leaves_out_tests_without_results():
    from src.analysis.deep_insights import _snowball_input

    normalized, _ = _snowball_input({"clinical_timeline": {"labs": [
        lab("Urine protein"), lab("Glucose", value=150, flag="High"),
        lab("TSH", value=2.0, flag="Normal"),
        # Only a name would reach the engine, so a listed outcome is left out.
        lab("Rapid strep antigen", source_procedure={"outcome": "Negative"}),
    ]}})
    assert [item["text"] for item in normalized["labs"]] == ["Glucose elevated", "TSH normal"]


def test_monitoring_gaps_count_only_tests_with_results():
    from src.analysis.missing_negatives import MissingNegativeDetector

    history = MissingNegativeDetector()._build_lab_history([
        lab("Hemoglobin A1c", value=7.2, flag="High", test_date="2000-01-02"),
        lab("Hemoglobin A1c", test_date="2002-01-02",
            source_procedure={"outcome": "Cancelled - patient declined"}),
        lab("Hemoglobin A1c", test_date="2002-02-03"),
    ])
    assert str(history["hemoglobin a1c"]) == "2000-01-02"


def test_anomaly_details_come_from_the_entry_with_the_result():
    from datetime import date

    from src.analysis.anomaly_investigator import AnomalyInvestigator

    info = AnomalyInvestigator.__new__(AnomalyInvestigator)._find_anomaly_info(
        date(2000, 3, 4), "HbA1c", {"clinical_timeline": {"labs": [
            lab("HbA1c", test_date="2000-03-04"),
            lab("HbA1c", value=0, unit="%", flag="Low", test_date="2000-03-04"),
        ]}},
    )
    assert info["value"] == 0


def test_related_labs_rank_results_ahead_of_tests_listed_without_one(monkeypatch):
    diagnosis = {"name": "Synthetic condition", "date_diagnosed": "2000-01-02",
                 "provider": "Synthetic clinician", "provenance": PROVENANCE}
    resulted = [f"Synthetic marker {letter}" for letter in "ABCDE"]
    listed = ["Urine glucose", "Urine ketones", "Urine nitrite", "Urine blood", "Urine protein"]
    with _client_with(monkeypatch, {
        "labs": [lab(name, value=9, flag="High") for name in resulted],
        "procedures": [procedure(name, provider="Synthetic clinician") for name in listed],
        "diagnoses": [diagnosis],
    }) as client:
        events = client.get("/api/timeline").get_json()
    related = next(e for e in events if e["type"] == "diagnosis")["related_labs"]
    assert sorted(item["title"] for item in related) == resulted


def test_chat_context_lists_only_current_flagged_results_with_dates():
    from src.ui.app import _build_chat_profile_context

    context = _build_chat_profile_context({"clinical_timeline": {"labs": [
        lab("Synthetic potassium", value=5.9, unit="mmol/L", flag="High"),
        lab("Synthetic potassium", value=4.2, unit="mmol/L", flag="Normal",
            test_date="2000-06-01"),
        lab("Urine protein", value_text="2+", flag="High", test_date="2000-03-04"),
        lab("Urine protein", test_date="2000-07-01"),
    ]}})
    line = next(row for row in context.splitlines() if row.startswith("Flagged labs:"))
    assert "Synthetic potassium" not in line
    assert "Urine protein 2+ (High, 2000-03-04)" in line


@pytest.mark.parametrize("timeline", [
    {},
    {"procedures": [procedure("Rapid strep antigen", outcome="Positive")]},
    {"labs": [lab("Synthetic marker", value=9.9, reference_low=1.0, reference_high=5.0)]},
])
def test_chat_fallback_never_infers_normal_results_from_missing_flags(monkeypatch, timeline):
    import src.ui.app as module

    monkeypatch.setattr(module, "_profile_data", {"clinical_timeline": timeline})
    reply = module._simple_chat_response("What do my lab results show?")
    assert "normal range" not in reply.lower()


def test_engines_accept_a_missing_flag_and_status():
    from src.analysis.diagnostic_engine.cross_specialty import CrossSpecialtyEngine
    from src.analysis.missing_negatives import MissingNegativeDetector

    profile = PatientProfile.model_validate({"clinical_timeline": {
        "diagnoses": [{"name": "Type 2 diabetes", "status": None, "provenance": PROVENANCE}],
        "labs": [lab("Glucose", value=150)],
    }}).model_dump(mode="json")
    corpus = CrossSpecialtyEngine()._build_corpus(profile)
    assert "type 2 diabetes" in corpus and "glucose" in corpus
    matched = MissingNegativeDetector()._match_conditions(
        profile["clinical_timeline"]["diagnoses"], [],
    )
    assert "diabetes" in matched


def test_cross_specialty_corpus_accepts_every_empty_field():
    from src.analysis.diagnostic_engine.cross_specialty import CrossSpecialtyEngine

    corpus = CrossSpecialtyEngine()._build_corpus({"clinical_timeline": {
        "medications": [{"name": "Synthetic medication", "status": None}, {"name": None}],
        "symptoms": [{"symptom_name": "Palpitations", "episodes": [
            {"description": None, "triggers": None}, {"description": "after coffee"},
        ]}, {"symptom_name": None}],
        "imaging": [{"description": None, "findings": []}],
        "genetics": [{"gene": "SYNTH1", "variant": None}, {"gene": None}],
        # A test listed without a result adds no evidence to search.
        "labs": [lab("Rapid strep antigen"), lab("Ferritin", value=8, flag="Low")],
    }})
    assert corpus == [
        "ferritin", "low ferritin", "ferritin low", "synthetic medication",
        "palpitations", "after coffee", "synth1",
    ]


# ── Word report ──────────────────────────────────────────────

def _report_text(tmp_path, monkeypatch, timeline):
    import docx

    from src.report.builder import ReportBuilder

    def _no_network(*args, **kwargs):
        raise OSError("network disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    out = ReportBuilder().generate(PatientProfile.model_validate({"clinical_timeline": timeline}),
                                   tmp_path / "report.docx")
    document = docx.Document(str(out))
    paragraphs = [p.text for p in document.paragraphs]
    rows = [[cell.text for cell in row.cells] for table in document.tables for row in table.rows]
    return paragraphs, rows


def _tables_after(tmp_path, monkeypatch, timeline, heading):
    """Rows of the first table that follows the heading paragraph."""
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    _report_text(tmp_path, monkeypatch, timeline)
    document = docx.Document(str(tmp_path / "report.docx"))
    seen = False
    for block in document.element.body.iterchildren():
        if block.tag.endswith("}p") and Paragraph(block, document).text == heading:
            seen = True
        elif seen and block.tag.endswith("}tbl"):
            return [[cell.text for cell in row.cells] for row in Table(block, document).rows][1:]
    return None


def _section(paragraphs, heading, stop):
    start = paragraphs.index(heading) + 1
    end = next(i for i in range(start, len(paragraphs)) if paragraphs[i].startswith(stop))
    return paragraphs[start:end]


def test_report_states_results_and_never_calls_a_missing_result_normal(tmp_path, monkeypatch):
    timeline = {
        "labs": [lab("Urine protein", value_text="2+", flag="High"), lab("Sodium", value=140)],
        "procedures": [procedure("Urine protein", outcome="Completed"),
                       procedure("Rapid strep antigen", outcome="Positive"),
                       procedure("Urine nitrite")],
    }
    paragraphs, rows = _report_text(tmp_path, monkeypatch, timeline)
    names = ("Urine protein", "Sodium", "Rapid strep antigen", "Urine nitrite")
    flagged = [p for p in paragraphs if p.startswith("Urine protein:")]
    assert flagged and "2+" in flagged[0] and "[High]" in flagged[0]
    assert not [p for p in paragraphs if "None" in p and any(n in p for n in names)]
    measured = _tables_after(tmp_path, monkeypatch, timeline, "All Lab Results")
    # The same-day listing of urine protein is kept as the result's source.
    assert {(row[0], row[1]): row[3] for row in measured} == {
        ("Urine protein", "2+"): "High",
        ("Sodium", "140"): "Not flagged",
        # A listed outcome never carried a flag, so none is claimed.
        ("Rapid strep antigen", "Positive (listed with procedures)"): "—",
    }
    listed = _tables_after(tmp_path, monkeypatch, timeline, "Tests Listed Without a Result")
    assert [row[:2] for row in listed] == [["Urine nitrite", "—"]]
    timeline_lines = [" | ".join(row) for row in rows if len(row) == 4]
    assert any("Rapid strep antigen: Positive (listed with procedures)" in line
               for line in timeline_lines)
    assert not any("None" in line for line in timeline_lines)


def test_report_flagged_results_state_the_flagged_value_and_the_latest(tmp_path, monkeypatch):
    paragraphs, _ = _report_text(tmp_path, monkeypatch, {"labs": [
        lab("Glucose", value=100, unit="mg/dL"),
        lab("Glucose", value=310, unit="mg/dL", flag="High", test_date="2000-02-03"),
        lab("Glucose", value=100, unit="mg/dL", test_date="2000-03-04"),
        lab("Synthetic antibody screen", value_text="Reactive", flag="Abnormal"),
        lab("Synthetic antibody screen", value_text="Nonreactive", test_date="2000-03-04"),
        lab("GGT", value=140, unit="U/L", flag="High", reference_low=0.0, reference_high=65.0),
    ]})
    section = _section(paragraphs, "Flagged Results", "All Lab Results")
    assert section == [
        "Glucose: 310 mg/dL [High] on 2000-02-03  [synthetic-results.pdf, p.1]",
        "    Most recent result: 100 mg/dL [Not flagged] on 2000-03-04",
        "    Trend: → Same as the earliest dated result: 100 mg/dL on 2000-01-02"
        " → 100 mg/dL on 2000-03-04",
        "Synthetic antibody screen: Reactive [Abnormal] on 2000-01-02  [synthetic-results.pdf, p.1]",
        "    Most recent result: Nonreactive [Not flagged] on 2000-03-04",
        "GGT: 140 U/L [High] on 2000-01-02 (Reference: 0 to 65 U/L)  [synthetic-results.pdf, p.1]",
    ]


def test_report_trend_compares_only_dated_numbers_in_one_unit(tmp_path, monkeypatch):
    paragraphs, _ = _report_text(tmp_path, monkeypatch, {"labs": [
        # Different units: no direction is claimed.
        lab("Glucose", value=6.1, unit="mmol/L", flag="High"),
        lab("Glucose", value=99, unit="mg/dL", test_date="2000-03-04"),
        # Same day: the first stored entry is the latest, as on the Labs page.
        lab("Sodium", value=150, unit="mmol/L", flag="High"),
        lab("Sodium", value=140, unit="mmol/L"),
        # Undated: never the latest, never a trend end.
        lab("Potassium", value=6.1, unit="mmol/L", flag="High", test_date=None),
        lab("Potassium", value=4.0, unit="mmol/L", test_date="2000-03-04"),
        # Text between numbers is not a measurement.
        lab("Chloride", value=110, unit="mmol/L", flag="High"),
        lab("Chloride", value_text="Specimen hemolyzed", test_date="2000-02-03"),
        lab("Chloride", value=100, unit="mmol/L", test_date="2000-03-04"),
    ]})
    section = _section(paragraphs, "Flagged Results", "All Lab Results")
    assert section == [
        "Glucose: 6.1 mmol/L [High] on 2000-01-02  [synthetic-results.pdf, p.1]",
        "    Most recent result: 99 mg/dL [Not flagged] on 2000-03-04",
        "Sodium: 150 mmol/L [High] on 2000-01-02  [synthetic-results.pdf, p.1]",
        # Undated: never the latest, never a trend end, and not called older.
        "Potassium: 6.1 mmol/L [High] on date not recorded  [synthetic-results.pdf, p.1]",
        "    Another result: 4 mmol/L [Not flagged] on 2000-03-04",
        "Chloride: 110 mmol/L [High] on 2000-01-02  [synthetic-results.pdf, p.1]",
        "    Most recent result: 100 mmol/L [Not flagged] on 2000-03-04",
        "    Trend: ↘ Lower than the earliest dated result: 110 mmol/L on 2000-01-02"
        " → 100 mmol/L on 2000-03-04",
    ]


def test_report_lab_table_keeps_measured_results_and_says_what_it_leaves_out(
        tmp_path, monkeypatch):
    measured = [lab(f"Synthetic analyte {i}", value=i, test_date=f"1999-{1 + i % 12:02d}-01")
                for i in range(101)]
    listed = [lab(f"Urine {name}", test_date="2000-05-06", source_procedure={"outcome": "Completed"})
              for name in ("glucose", "protein", "ketones", "blood", "nitrite")]
    timeline = {"labs": measured + listed}
    paragraphs, rows = _report_text(tmp_path, monkeypatch, timeline)
    table = _tables_after(tmp_path, monkeypatch, timeline, "All Lab Results")
    assert len(table) == 100 and all(not row[1].startswith("Completed") for row in table)
    assert "(Showing 100 of 101 lab results. The full list is in the Hub.)" in paragraphs
    assert len(_tables_after(tmp_path, monkeypatch, timeline, "Tests Listed Without a Result")) == 5
    assert any("Lab Results on File: 101 (plus 5 tests listed without a result)" in p
               for p in paragraphs)
    stats = {row[0]: row[1] for row in rows if len(row) == 2}
    assert stats["Lab Results Found"] == "101"
    assert stats["Tests Listed Without a Result"] == "5"


# ── Outcomes, placeholders, ties and one name per test ───────

# A procedure listing mostly carries a status, so its outcome is the result
# only when it plainly states one; anything else stays a listing.
STATUS_OUTCOMES = [
    "Final", "Final result", "Resulted", "Not resulted", "Preliminary", "In process",
    "Discontinued", "Specimen lost", "Done - lab error", "See scanned document",
    "Results in MyChart", "active", "aborted", "on-hold", "entered-in-error",
    "registered", "Unknown", "null", "None", "Not specified", "Not documented",
    "Not recorded", "Pending review", "TBD", "Result not recorded", "-", "—", "?",
    "In office", "Outside lab", "Today", "Repeat", "Lab order", "Collected 10:15",
    "Completed 10/1", "Overdue", "Due", "Kit mailed to patient", "Not done - patient left",
    "Will do at next visit", "Sent to Quest", "Collected 03/04/2024 10:30\u202fAM",
    "Specimen grossly hemolyzed", "High", "Abnormal", "Elevated",
    "Abnormal - see provider note", "10,000 units IM", "Followed up at 6 weeks",
    "Received flu vaccine at pharmacy", "Uneventful",
]
RESULT_OUTCOMES = [
    "Positive", "Negative", "Positive for influenza A", "Not detected", "Detected",
    "Non-reactive", "Reactive", "6.8 %", "9.4 percent", "450 mg/dL", "<20 copies/mL",
    "2+", "Trace", "No growth", "1:160", "1:40", "Indeterminate", "Completed - negative",
    0, 7.0,
]
# Result text is the entry's own result field, so only plain statuses and
# placeholders are no result there.
MORE_STATUS_TEXTS = [
    "Final", "Not resulted", "In process", "Discontinued", "Preliminary", "Specimen lost",
    "Unsatisfactory specimen", "No specimen", "Entered in error", "Duplicate order",
    "On hold", "Pending review", "Collected 10:15", "Received 14:32", "Pending 3/4",
    "Cancelled 11/2", "-", "—", "--", "?", "null", "Unknown", "Not recorded",
    "Result not recorded", "Overdue", "Kit mailed to patient",
    "Collected 03/04/2024 10:30\u202fAM", "Collected 03/04/2024 10:30\u00a0AM",
    "Collected Mar 4,\u00a02024",
]
MORE_RESULT_TEXTS = ["Insufficient", "Sufficient", "Yellow", "Clear", "Few", "1:40", "1:20", "+"]


@pytest.mark.parametrize("outcome", STATUS_OUTCOMES)
def test_an_outcome_that_does_not_state_a_result_is_no_result(outcome):
    assert not lab_has_result({"source_procedure": {"outcome": outcome}})


@pytest.mark.parametrize("outcome", RESULT_OUTCOMES)
def test_an_outcome_that_states_a_result_is_one(outcome):
    assert lab_has_result({"source_procedure": {"outcome": outcome}})


@pytest.mark.parametrize("text", MORE_STATUS_TEXTS)
def test_statuses_and_placeholders_in_result_text_say_no_result(text):
    assert says_no_result(text)
    assert not lab_has_result({"value_text": text})


@pytest.mark.parametrize("text", MORE_RESULT_TEXTS)
def test_categories_titers_and_grades_in_result_text_are_results(text):
    assert not says_no_result(text)
    assert lab_has_result({"value_text": text})


def test_js_outcome_and_text_rules_match_the_server():
    cases = [{"source_procedure": {"outcome": o}} for o in STATUS_OUTCOMES + RESULT_OUTCOMES]
    cases += [{"value_text": t} for t in MORE_STATUS_TEXTS + MORE_RESULT_TEXTS + ["\ufeff"]]
    has_result, own, text = run_lab_results_js(
        f"var cases = {json.dumps(cases)};"
        "[cases.map(function(c) { return LabResults.hasResult(c); }),"
        " cases.map(function(c) { return LabResults.hasResult(c, false); }),"
        " cases.map(function(c) { return LabResults.resultText(c, true); })]"
    )
    assert has_result == [lab_has_result(case) for case in cases]
    assert own == [lab_has_result(case, include_outcome=False) for case in cases]
    assert text == [lab_result_text(case) for case in cases]


@pytest.mark.parametrize("flag", ["None", "null", "N/A", "na", "-", "Unknown", " "])
def test_a_placeholder_flag_is_no_flag(flag):
    assert not lab_has_result({"flag": flag})
    assert lab_result_text({"flag": flag}) == "Result not recorded"


FLAGS = [
    ("High", True), ("L", True), ("Critical", True), ("Abnormal", True), ("A", True),
    ("Normal", False), ("N", False), ("WNL", False), ("Within normal limits", False),
    ("Negative", False), ("neg", False), ("None", False), ("N/A", False), ("", False),
    (None, False),
]


@pytest.mark.parametrize("flag, flagged", FLAGS)
def test_one_rule_says_which_flags_mark_a_result(flag, flagged):
    from src.standardization.record_categories import is_flagged

    assert is_flagged(flag) is flagged


def test_js_flag_rule_matches_the_server():
    from src.standardization.record_categories import is_flagged

    flags = [flag for flag, _ in FLAGS]
    said = run_lab_results_js(f"{json.dumps(flags)}.map(function(f) {{ return LabResults.isFlagged(f); }})")
    assert said == [is_flagged(flag) for flag in flags]


RESULT_TEXT_CASES = [
    # Text printed beside a number says more than the number alone.
    ({"value": 0.01, "value_text": "<0.01", "unit": "ng/mL"}, "<0.01 ng/mL"),
    ({"value": 100000, "value_text": ">100,000 CFU/mL", "unit": "CFU/mL"}, ">100,000 CFU/mL"),
    ({"value": 12.4, "value_text": "Reactive", "unit": "S/CO"}, "12.4 S/CO (Reactive)"),
    ({"value": 20, "value_text": "<20 copies/mL (not detected)", "unit": "copies/mL"},
     "<20 copies/mL (not detected)"),
    ({"value_text": ">100,000 CFU/mL", "unit": "CFU/mL"}, ">100,000 CFU/mL"),
    ({"value": 90, "value_text": "90 mg/dL", "unit": "mg/dL"}, "90 mg/dL"),
    # A status from the procedure list never takes a flagged entry's value slot.
    ({"flag": "Abnormal", "source_procedure": {"outcome": "Completed"}}, "Value not recorded"),
    ({"flag": "Abnormal", "source_procedure": {"outcome": "Positive"}},
     "Positive (listed with procedures)"),
    ({"source_procedure": {"outcome": 7.0}}, "7 (listed with procedures)"),
    ({"value_text": "\ufeff"}, "Result not recorded"),
    ({"value_text": "Positive\u00a0 "}, "Positive"),
]


@pytest.mark.parametrize("record, expected", RESULT_TEXT_CASES)
def test_result_text_keeps_what_the_record_wrote_beside_a_number(record, expected):
    assert lab_result_text(record) == expected


def test_js_result_text_keeps_what_the_record_wrote_beside_a_number():
    records = [record for record, _ in RESULT_TEXT_CASES]
    shown = run_lab_results_js(
        f"{json.dumps(records)}.map(function(c) {{ return LabResults.resultText(c, true); }})"
    )
    assert shown == [expected for _, expected in RESULT_TEXT_CASES]


def test_js_badge_never_says_not_flagged_for_a_listing():
    badges = run_lab_results_js(
        "[LabResults.badgeText({value: 4}), LabResults.badgeText({value: 4, flag: 'H'}),"
        " LabResults.badgeText({source_procedure: {outcome: 'Positive'}}),"
        " LabResults.badgeText({source_procedure: {outcome: 'Completed'}}),"
        " LabResults.badgeText({flag: 'WNL', value: 4}), LabResults.badgeText({flag: 'None'})]"
    )
    assert badges == ["Not flagged", "HIGH", "", "", "Normal", ""]


def _a1c(test_date, **fields):
    return lab("Hemoglobin A1c", test_date=test_date, **fields)


FLAGGED_A1C = dict(value=9.4, unit="%", flag="High", reference_low=4.0, reference_high=5.6)
NEWER_LISTINGS = ["Final", "Overdue", "High", "Not recorded", "Kit mailed to patient",
                  "Collected 10/01/2026 10:15\u202fAM"]


def _js_latest(entries):
    return run_lab_results_js(
        f"var e = {json.dumps(entries)}.sort(function(a, b) {{"
        " var ad = a.test_date || '', bd = b.test_date || '';"
        " if (ad === bd) return 0; if (!ad) return 1; if (!bd) return -1; return bd.localeCompare(ad); });"
        " LabResults.newestWithResult(e)"
    )


@pytest.mark.parametrize("outcome", NEWER_LISTINGS)
def test_a_newer_listing_never_hides_the_flagged_result(outcome):
    from src.analysis.biomarker_cascades import BiomarkerCascadeEngine
    from src.analysis.missing_negatives import MissingNegativeDetector
    from src.analysis.visit_prep import VisitPrepGenerator
    from src.ui.app import _current_flagged_labs, _get_latest_labs

    labs = [_a1c("2026-01-10", **FLAGGED_A1C),
            _a1c("2026-10-01", source_procedure={"outcome": outcome})]
    flagged = VisitPrepGenerator()._flagged_labs({"labs": labs})
    assert [(f["result"], f["test_date"]) for f in flagged] == [("9.4 %", "2026-01-10")]
    assert [item["test_date"] for item in _current_flagged_labs(labs, limit=5)] == ["2026-01-10"]
    assert [item["test_date"] for item in _get_latest_labs(labs)] == ["2026-01-10"]
    assert _js_latest(labs)["test_date"] == "2026-01-10"
    from src.standardization.record_categories import lab_test_key

    lookup = BiomarkerCascadeEngine()._build_lab_lookup(labs)
    assert lookup[lab_test_key(labs[0])]["date"] == "2026-01-10"
    history = MissingNegativeDetector()._build_lab_history(labs)
    assert str(history["hemoglobin a1c"]) == "2026-01-10"


def test_on_the_same_day_a_measured_result_outranks_a_listed_one():
    from datetime import date

    from src.analysis.anomaly_investigator import AnomalyInvestigator
    from src.analysis.visit_prep import VisitPrepGenerator
    from src.ui.app import _current_flagged_labs, _get_latest_labs

    labs = [_a1c("2026-10-01", source_procedure={"outcome": "9.4 percent"}),
            _a1c("2026-10-01", **FLAGGED_A1C)]
    flagged = VisitPrepGenerator()._flagged_labs({"labs": labs})
    assert [(f["result"], f["flag"]) for f in flagged] == [("9.4 %", "high")]
    assert [item["value"] for item in _current_flagged_labs(labs, limit=5)] == [9.4]
    assert [item["value"] for item in _get_latest_labs(labs)] == [9.4]
    assert _js_latest(labs)["value"] == 9.4
    info = AnomalyInvestigator.__new__(AnomalyInvestigator)._find_anomaly_info(
        date(2026, 10, 1), "Hemoglobin A1c", {"clinical_timeline": {"labs": labs}},
    )
    assert info["value"] == 9.4


def test_related_labs_keep_the_measured_entry_of_a_same_day_pair(monkeypatch):
    with _client_with(monkeypatch, {
        "labs": [_a1c("2026-10-01", **FLAGGED_A1C)],
        "procedures": [procedure("Hemoglobin A1c", procedure_date="2026-10-01",
                                 outcome="9.4 percent")],
        "diagnoses": [{"name": "Synthetic condition", "date_diagnosed": "2026-10-01",
                       "provenance": PROVENANCE}],
    }) as client:
        events = client.get("/api/timeline").get_json()
    diagnosis = next(e for e in events if e["type"] == "diagnosis")
    assert [item["detail"] for item in diagnosis["related_labs"]] == ["9.4 % High"]


def test_every_reader_treats_one_test_written_two_ways_as_one():
    from src.analysis.visit_prep import VisitPrepGenerator
    from src.ui.app import _build_chat_profile_context, _current_flagged_labs, _get_latest_labs

    labs = [
        lab("Vitamin D, 25-OH", test_date="2024-01-05", value=18, unit="ng/mL", flag="Low"),
        lab("vitamin D 25-OH", test_date="2024-08-01", value=35, unit="ng/mL"),
        _a1c("2026-01-10", **FLAGGED_A1C),
        lab("HEMOGLOBIN A1C", test_date="2026-10-01", value=5.4, unit="%"),
    ]
    assert VisitPrepGenerator()._flagged_labs({"labs": labs}) == []
    assert _current_flagged_labs(labs, limit=5) == []
    assert sorted(item["test_date"] for item in _get_latest_labs(labs)) == ["2024-08-01", "2026-10-01"]
    context = _build_chat_profile_context({"clinical_timeline": {"labs": labs}})
    assert not [row for row in context.splitlines() if row.startswith("Flagged labs:")]


def test_visit_prep_trend_compares_plain_numbers_in_one_unit():
    from src.analysis.visit_prep import VisitPrepGenerator

    flagged = VisitPrepGenerator()._flagged_labs({"labs": [
        lab("Glucose", test_date="2000-01-02", value=95, unit="mg/dl"),
        lab("Glucose", test_date="2000-03-04", value=300, unit="mg/dL", flag="High"),
        lab("Troponin I", test_date="2000-01-02", value=0.01, value_text="<0.01", unit="ng/mL"),
        lab("Troponin I", test_date="2000-03-04", value=0.5, unit="ng/mL", flag="High"),
    ]})
    assert {f["name"]: f["trend"] for f in flagged} == {"Glucose": "↑", "Troponin I": "—"}


def test_js_trend_uses_plain_numbers_in_one_unit():
    picked = run_lab_results_js(
        "[LabResults.trendNumber({value: 7.5}), LabResults.trendNumber({value_text: '7.5'}),"
        " LabResults.trendNumber({value: 0.01, value_text: '<0.01'}),"
        " LabResults.trendNumber({value: 90, value_text: '90 mg/dL', unit: 'mg/dL'}),"
        " LabResults.sameUnit({unit: 'mg/dl'}, {unit: 'mg/dL'}), LabResults.sameUnit({unit: '%'}, {unit: 'mmol/mol'}),"
        " LabResults.sameUnit({}, {unit: ''})]"
    )
    assert picked == [7.5, None, None, 90, True, False, True]


def test_dashboard_trend_series_keep_one_unit():
    from src.ui.app import _get_lab_trends

    trends = _get_lab_trends([
        lab("Hemoglobin A1c", test_date="2000-01-02", value=7.5, unit="%"),
        lab("Hemoglobin A1c", test_date="2000-02-03", value=58, unit="mmol/mol"),
        lab("Hemoglobin A1c", test_date="2000-03-04", value=7.6, unit="%"),
        lab("Hemoglobin A1c", test_date="2000-04-05", value=7.7, unit="%"),
    ])
    assert [point["value"] for points in trends.values() for point in points] == [7.5, 7.6, 7.7]


def test_a_critical_flag_takes_its_direction_from_the_range():
    from src.analysis.biomarker_cascades import BiomarkerCascadeEngine
    from src.analysis.deep_insights import _snowball_input

    engine = BiomarkerCascadeEngine()
    low = engine._build_lab_lookup([lab("Glucose", value=38, unit="mg/dL", flag="Critical",
                                        reference_low=70, reference_high=100)])
    high = engine._build_lab_lookup([lab("Glucose", value=600, unit="mg/dL", flag="Critical",
                                         reference_low=70, reference_high=100)])
    node = {"tests": ["Glucose"], "flag": "high"}
    assert engine._match_node(node, low) is None
    assert engine._match_node(node, high)["display"] == "600 mg/dL"
    normalized, _ = _snowball_input({"clinical_timeline": {"labs": [
        lab("Potassium", value=2.4, unit="mmol/L", flag="Critical", reference_low=3.5,
            reference_high=5.1),
        lab("Sodium", value=120, unit="mmol/L", flag="Critical"),
    ]}})
    assert [item["text"] for item in normalized["labs"]] == ["Potassium low", "Sodium abnormal"]


def test_cascade_nodes_match_whole_test_names_not_parts_of_others():
    from src.analysis.biomarker_cascades import BiomarkerCascadeEngine

    engine = BiomarkerCascadeEngine()
    lookup = engine._build_lab_lookup([
        _a1c("2000-01-02", **FLAGGED_A1C), lab("HGB", value=13.8),
        lab("Urine glucose", value_text="2+", flag="High"),
        lab("Glucose, fasting", value=130, unit="mg/dL", flag="High"),
    ])
    assert engine._match_node({"tests": ["Hemoglobin"], "flag": "any"}, lookup) is None
    match = engine._match_node({"tests": ["Glucose"], "flag": "high"}, lookup)
    assert match["display"] == "130 mg/dL"


def test_trajectory_points_keep_a_measured_zero():
    from src.analysis.trajectory import TrajectoryForecaster

    groups = TrajectoryForecaster.__new__(TrajectoryForecaster)._group_labs([
        lab("Synthetic marker", test_date="2026-06-10", value=1.5),
        lab("Synthetic marker", test_date="2026-09-10", value=0.0),
    ])
    assert [point["value"] for point in next(iter(groups.values()))["points"]] == [1.5, 0.0]


def test_report_trend_names_both_ends_and_skips_what_it_cannot_compare(tmp_path, monkeypatch):
    paragraphs, _ = _report_text(tmp_path, monkeypatch, {"labs": [
        # The newest result is text: no direction is claimed.
        lab("Glucose", value=250, unit="mg/dL", flag="High"),
        lab("Glucose", value=200, unit="mg/dL", flag="High", test_date="2000-02-03"),
        lab("Glucose", value_text="HI (>600)", unit="mg/dL", flag="Critical", test_date="2000-03-04"),
        # The earliest result is text.
        lab("CRP", value_text="<5", unit="mg/L"),
        lab("CRP", value=80, unit="mg/L", flag="High", test_date="2000-02-03"),
        lab("CRP", value=40, unit="mg/L", flag="High", test_date="2000-03-04"),
        # Units written in another case are one unit.
        lab("Calcium", value=9.5, unit="mg/dl"),
        lab("Calcium", value=11.5, unit="mg/dL", flag="High", test_date="2000-02-03"),
        lab("Calcium", value=10.0, unit="mg/dL", test_date="2000-03-04"),
        # Two values on the earliest day: either end could be the start.
        lab("Potassium", value=3.0, unit="mmol/L", flag="Low"),
        lab("Potassium", value=5.0, unit="mmol/L"),
        lab("Potassium", value=4.0, unit="mmol/L", test_date="2000-03-04"),
    ]})
    section = _section(paragraphs, "Flagged Results", "All Lab Results")
    trends = [line for line in section if line.startswith("    Trend:")]
    assert trends == [
        "    Trend: ↗ Higher than the earliest dated result: 9.5 mg/dl on 2000-01-02"
        " → 10 mg/dL on 2000-03-04",
    ]


def test_report_names_another_result_without_claiming_it_is_newer(tmp_path, monkeypatch):
    paragraphs, _ = _report_text(tmp_path, monkeypatch, {"labs": [
        lab("Potassium", value=6.1, unit="mmol/L", flag="High", test_date=None),
        lab("Potassium", value=4.0, unit="mmol/L", test_date="2000-03-04"),
        lab("Sodium", value=150, unit="mmol/L", flag="High", test_date="2000-03-04"),
        lab("Sodium", source_procedure={"outcome": "140 mmol/L"}, test_date="2000-03-04"),
    ]})
    section = _section(paragraphs, "Flagged Results", "All Lab Results")
    assert "    Another result: 4 mmol/L [Not flagged] on 2000-03-04" in section
    assert not [line for line in section if "Most recent result" in line]
    assert not [line for line in section if "140 mmol/L" in line]


def test_report_never_calls_a_listed_outcome_not_flagged(tmp_path, monkeypatch):
    timeline = {"procedures": [procedure("Rapid strep antigen", outcome="Positive")]}
    measured = _tables_after(tmp_path, monkeypatch, timeline, "All Lab Results")
    assert [row[:4] for row in measured] == [
        ["Rapid strep antigen", "Positive (listed with procedures)", "—", "—"],
    ]


def test_report_listings_keep_their_own_status(tmp_path, monkeypatch):
    timeline = {"labs": [lab("Urine culture", value_text="Cancelled")],
                "procedures": [procedure("Urine culture", outcome="Completed")]}
    listed = _tables_after(tmp_path, monkeypatch, timeline, "Tests Listed Without a Result")
    assert sorted(row[1] for row in listed) == ["Cancelled", "Completed"]


def test_report_timeline_states_a_procedure_outcome(tmp_path, monkeypatch):
    _, rows = _report_text(tmp_path, monkeypatch, {"procedures": [
        procedure("Knee X-ray", outcome="No fracture"), procedure("Physical therapy evaluation"),
    ]})
    lines = [" | ".join(row) for row in rows if len(row) == 4]
    assert any("Knee X-ray: No fracture" in line for line in lines)
    assert any(line.split(" | ")[2] == "Physical therapy evaluation" for line in lines)


def test_report_groups_one_test_written_two_ways(tmp_path, monkeypatch):
    paragraphs, _ = _report_text(tmp_path, monkeypatch, {"labs": [
        lab("Vitamin D, 25-OH", test_date="2024-01-05", value=18, unit="ng/mL", flag="Low"),
        lab("Vitamin D 25-OH", test_date="2024-08-01", value=35, unit="ng/mL"),
    ]})
    section = _section(paragraphs, "Flagged Results", "All Lab Results")
    assert "    Most recent result: 35 ng/mL [Not flagged] on 2024-08-01" in section


def test_report_reads_normal_and_placeholder_flags_as_not_flagged(tmp_path, monkeypatch):
    paragraphs, _ = _report_text(tmp_path, monkeypatch, {"labs": [
        lab("Sodium", value=140, unit="mmol/L", flag="N"),
        lab("Chloride", value=101, unit="mmol/L", flag="WNL"),
        lab("Rapid strep antigen", value_text="Negative", flag="Negative"),
        lab("Urine ketones", flag="None"),
        lab("Potassium", value=6.1, unit="mmol/L", flag="High"),
    ]})
    section = _section(paragraphs, "Flagged Results", "All Lab Results")
    assert [line.split(":")[0] for line in section] == ["Potassium"]
    assert any("Lab Results on File: 4 (plus 1 test listed without a result)" in p
               for p in paragraphs)


# ── Flags written as symbols, result notations, outcomes with their flag ──

SYMBOL_FLAGS = [
    ("*", True, ""), ("!", True, ""), ("↑", True, "high"), ("↓", True, "low"),
    ("▲", True, "high"), ("▼", True, "low"),
    ("-", False, ""), ("—", False, ""), (".", False, ""), ("?", False, ""),
]


@pytest.mark.parametrize("flag, flagged, direction", SYMBOL_FLAGS)
def test_a_flag_written_as_a_symbol_is_a_flag(flag, flagged, direction):
    from src.standardization.record_categories import flag_direction, is_flagged

    assert is_flagged(flag) is flagged
    assert flag_direction({"flag": flag, "value": 6.1}) == direction
    assert lab_has_result({"flag": flag}) is flagged


def test_js_symbol_flags_match_the_server():
    from src.standardization.record_categories import is_flagged

    flags = [flag for flag, _, _ in SYMBOL_FLAGS]
    flagged, shown = run_lab_results_js(
        f"var f = {json.dumps(flags)}; [f.map(function(x) {{ return LabResults.isFlagged(x); }}),"
        " f.map(function(x) { return LabResults.flagText(x, true); })]"
    )
    assert flagged == [is_flagged(flag) for flag in flags]
    assert shown == ["*", "!", "HIGH", "LOW", "HIGH", "LOW",
                     "Not flagged", "Not flagged", "Not flagged", "Not flagged"]


NOT_FLAGGED_WORDS = [
    "Non-reactive", "Nonreactive", "Not reactive", "Not detected", "None detected", "ND",
    "NR", "In range", "Within range", "Within reference range", "Within normal range",
    "Normal range", "Normal.", "neg.", "No flag", "Unflagged", "N.A.", "n.a.", "None flagged",
]


@pytest.mark.parametrize("flag", NOT_FLAGGED_WORDS)
def test_normal_words_and_placeholders_in_the_flag_field_are_not_flagged(flag):
    from src.standardization.record_categories import is_flagged

    assert not is_flagged(flag)


def test_js_normal_flag_words_match_the_server():
    from src.standardization.record_categories import is_flagged

    said = run_lab_results_js(
        f"{json.dumps(NOT_FLAGGED_WORDS)}.map(function(f) {{ return LabResults.isFlagged(f); }})")
    assert said == [is_flagged(flag) for flag in NOT_FLAGGED_WORDS]


# Fractions, titers beside a comment, and times written as a result are results;
# a time or date next to a status word is when the status happened.
RESULT_NOTATIONS = ["1/3", "0/3", "1:40, see comment", "1:16 - see note", "4:30", "11:30",
                    "±", "(±)", "None", "Nil", "None seen", "Insufficient"]
STATUS_WITH_TIMES = [
    "Collected 0915", "Received 1415", "Collected 10:15", "Pending 3/4", "Drawn at 7:30",
    "Received @ 14:32", "Result not available", "Results not available", "Test not available",
    "Specimen insufficient for analysis", "Insufficient sample volume", "Insufficient for testing",
    "QNS - insufficient", "Not enough specimen", "Inadequate specimen", "Invalid", "Test invalid",
    "Sent to Quest", "Send out", "Referred to reference lab", "Not obtained", "Unable to collect",
    "Patient left", "No show", "Mislabeled specimen", "Recollection requested", "Corrected",
    "Amended", "Partial", "Pending verification", "Results in MyChart", "Specimen hemolyzed 3+",
    "Grossly hemolyzed (4+), test not performed",
]


@pytest.mark.parametrize("text", RESULT_NOTATIONS)
def test_notations_written_as_results_are_results(text):
    assert not says_no_result(text)
    assert lab_has_result({"value_text": text})


@pytest.mark.parametrize("text", STATUS_WITH_TIMES)
def test_statuses_with_their_time_or_reason_say_no_result(text):
    assert says_no_result(text)


def test_js_notation_and_status_rules_match_the_server():
    texts = RESULT_NOTATIONS + STATUS_WITH_TIMES
    said = run_lab_results_js(f"{json.dumps(texts)}.map(function(t) {{ return LabResults.saysNoResult(t); }})")
    assert said == [says_no_result(text) for text in texts]


NONE_CASES = [
    # "None" or "Nil" for a measured test is a blank; for microscopy it is the finding.
    ({"value_text": "None", "unit": "mmol/L"}, False, "Result not recorded"),
    ({"value_text": "Nil", "reference_low": 3.5, "reference_high": 5.1}, False, "Result not recorded"),
    ({"value_text": "None", "unit": "/HPF"}, True, "None /HPF"),
    ({"value_text": "None"}, True, "None"),
    ({"value_text": "null"}, False, "Result not recorded"),
    ({"value_text": "-"}, False, "Result not recorded"),
]


@pytest.mark.parametrize("record, has_result, shown", NONE_CASES)
def test_none_is_a_blank_only_for_a_measured_test(record, has_result, shown):
    assert lab_has_result(record) is has_result
    assert lab_result_text(record) == shown


def test_js_none_rules_match_the_server():
    records = [record for record, _, _ in NONE_CASES]
    has, shown = run_lab_results_js(
        f"var r = {json.dumps(records)}; [r.map(function(c) {{ return LabResults.hasResult(c); }}),"
        " r.map(function(c) { return LabResults.resultText(c, true); })]"
    )
    assert has == [h for _, h, _ in NONE_CASES]
    assert shown == [s for _, _, s in NONE_CASES]


OUTCOMES_WITH_FLAG = ["9.4 % (H)", "9.4 % H", "212 mg/dL (H)", "Positive (Abnormal)",
                      "Detected (Critical)", "Negative (Normal)", "Positive (A)"]


@pytest.mark.parametrize("outcome", OUTCOMES_WITH_FLAG)
def test_an_outcome_stated_with_its_flag_is_still_the_result(outcome):
    assert lab_has_result({"source_procedure": {"outcome": outcome}})


def test_js_outcomes_with_a_flag_match_the_server():
    cases = [{"source_procedure": {"outcome": o}} for o in OUTCOMES_WITH_FLAG]
    has = run_lab_results_js(f"{json.dumps(cases)}.map(function(c) {{ return LabResults.hasResult(c); }})")
    assert has == [True] * len(cases)


UNIT_SPELLINGS = [
    ({"value": 15, "value_text": "15 ug/L", "unit": "µg/L"}, "15 µg/L"),
    ({"value": 7.5, "value_text": "7.5 K/µL", "unit": "K/uL"}, "7.5 K/uL"),
    ({"value": 7.5, "value_text": "7.5 x10E3/uL", "unit": "x10^3/uL"}, "7.5 x10^3/uL"),
    ({"value": 10, "value_text": "<10 mcg/L", "unit": "µg/L"}, "<10 mcg/L"),
    ({"value": 5, "value_text": "5 mg/dL", "unit": "g/dL"}, "5 g/dL"),
    ({"value_text": "<10 mcg/L", "unit": "µg/L"}, "<10 mcg/L"),
]


@pytest.mark.parametrize("record, expected", UNIT_SPELLINGS)
def test_a_unit_written_another_way_is_not_repeated(record, expected):
    assert lab_result_text(record) == expected


def test_js_unit_spellings_match_the_server():
    records = [record for record, _ in UNIT_SPELLINGS]
    shown = run_lab_results_js(f"{json.dumps(records)}.map(function(c) {{ return LabResults.resultText(c, true); }})")
    assert shown == [expected for _, expected in UNIT_SPELLINGS]


def test_on_one_day_a_flagged_result_is_the_one_shown():
    from src.analysis.visit_prep import VisitPrepGenerator
    from src.ui.app import _current_flagged_labs, _get_latest_labs

    for labs in (
        [lab("Potassium", test_date="2026-10-01", value=4.3, unit="mmol/L"),
         lab("Potassium", test_date="2026-10-01", value=6.1, unit="mmol/L", flag="High")],
        [lab("Potassium", test_date="2026-10-01", value=6.1, unit="mmol/L", flag="High"),
         lab("Potassium", test_date="2026-10-01", value=4.3, unit="mmol/L")],
    ):
        assert [f["result"] for f in VisitPrepGenerator()._flagged_labs({"labs": labs})] == ["6.1 mmol/L"]
        assert [item["value"] for item in _current_flagged_labs(labs, limit=5)] == [6.1]
        assert [item["value"] for item in _get_latest_labs(labs)] == [6.1]
        assert _js_latest(labs)["value"] == 6.1


def test_related_labs_keep_both_results_of_one_day(monkeypatch):
    with _client_with(monkeypatch, {
        "labs": [lab("Potassium", test_date="2026-10-01", value=4.3, unit="mmol/L"),
                 lab("Potassium", test_date="2026-10-01", value=6.1, unit="mmol/L", flag="High")],
        "diagnoses": [{"name": "Synthetic condition", "date_diagnosed": "2026-10-01",
                       "provenance": PROVENANCE}],
    }) as client:
        events = client.get("/api/timeline").get_json()
    diagnosis = next(e for e in events if e["type"] == "diagnosis")
    assert sorted(item["detail"] for item in diagnosis["related_labs"]) == ["4.3 mmol/L", "6.1 mmol/L High"]


def test_js_trend_compares_only_results_from_different_days():
    picked = run_lab_results_js(
        "[LabResults.comparable({value: 6.1, unit: 'mmol/L', test_date: '2026-10-01'}, {value: 4.3, unit: 'mmol/L', test_date: '2026-10-01'}),"
        " LabResults.comparable({value: 6.1, unit: 'mmol/L', test_date: '2026-10-01'}, {value: 4.3, unit: 'mmol/L', test_date: '2026-09-01'}),"
        " LabResults.comparable({value: 6.1, unit: 'mmol/L', test_date: '2026-10-01'}, {value: 4.3, unit: 'mEq/L', test_date: '2026-09-01'})]"
    )
    assert picked == [False, True, False]


def test_one_test_under_two_names_is_one_test():
    from src.analysis.visit_prep import VisitPrepGenerator
    from src.ui.app import _current_flagged_labs, _get_latest_labs

    labs = [
        lab("HbA1c", test_date="2026-01-10", value=9.4, unit="%", flag="High", loinc_code="4548-4"),
        lab("Hemoglobin A1c", test_date="2026-10-01", value=6.2, unit="%", loinc_code="4548-4"),
        lab("Vitamin B-12", test_date="2025-12-01", value=150, unit="pg/mL", flag="Low"),
        lab("Vitamin B12", test_date="2026-06-12", value=450, unit="pg/mL"),
    ]
    assert VisitPrepGenerator()._flagged_labs({"labs": labs}) == []
    assert _current_flagged_labs(labs, limit=5) == []
    assert sorted(item["test_date"] for item in _get_latest_labs(labs)) == ["2026-06-12", "2026-10-01"]
    keys = run_lab_results_js(f"{json.dumps(labs)}.map(function(l) {{ return LabResults.testKey(l); }})")
    assert keys[0] == keys[1] and keys[2] == keys[3]


CASCADE_SPELLINGS = [
    ("Platelets", "platelet", "low"), ("Platelet Count", "platelet", "low"),
    ("ALT (SGPT)", "alt", "high"), ("AST (SGOT)", "ast", "high"),
    ("Vitamin D, 25-Hydroxy", "vitamin d", "low"), ("PTH, Intact", "pth", "high"),
    ("TSH, 3rd Generation", "tsh", "high"), ("TSH, Ultrasensitive", "tsh", "high"),
    ("eGFR (CKD-EPI 2021)", "egfr", "low"), ("Cortisol, AM", "cortisol", "high"),
    ("Creatine Kinase (CK)", "ck", "high"), ("NT-Pro BNP", "nt-probnp", "high"),
    ("Hemoglobin A1c", "hba1c", "high"), ("Sedimentation Rate-Westergren", "esr", "high"),
    ("Vitamin B12 (Cobalamin)", "b12", "low"), ("Renin Activity, Plasma", "renin", "high"),
]


@pytest.mark.parametrize("name, node_test, direction", CASCADE_SPELLINGS)
def test_cascade_nodes_reach_common_report_spellings(name, node_test, direction):
    from src.analysis.biomarker_cascades import BiomarkerCascadeEngine

    engine = BiomarkerCascadeEngine()
    lookup = engine._build_lab_lookup([lab(name, value=1, flag=direction.title())])
    assert engine._match_node({"tests": [node_test], "flag": direction}, lookup)


def test_the_ldl_node_never_shows_total_cholesterol():
    from src.analysis import biomarker_cascades
    from src.analysis.biomarker_cascades import BiomarkerCascadeEngine

    engine = BiomarkerCascadeEngine()
    source = Path(biomarker_cascades.__file__).read_text()
    assert '"tests": ["ldl", "cholesterol", "ldl cholesterol"]' not in source
    ldl_node = {"tests": ["ldl", "ldl cholesterol", "ldl-c"], "flag": "high"}
    normal_ldl = engine._build_lab_lookup([
        lab("LDL Cholesterol", value=92, unit="mg/dL"),
        lab("Cholesterol, Total", value=228, unit="mg/dL", flag="High"),
    ])
    assert engine._match_node(ldl_node, normal_ldl) is None
    high_ldl = engine._build_lab_lookup([
        lab("LDL Cholesterol", value=160, unit="mg/dL", flag="High"),
        lab("Total Cholesterol", value=214, unit="mg/dL", flag="High"),
    ])
    assert engine._match_node(ldl_node, high_ldl)["display"] == "160 mg/dL"


def test_treatment_response_reads_only_the_named_test_in_one_unit():
    from src.analysis.treatment_response import TreatmentResponseAnalyzer

    analyzer = TreatmentResponseAnalyzer.__new__(TreatmentResponseAnalyzer)
    hemoglobin = analyzer._get_lab_points("hemoglobin", [
        lab("Hemoglobin", test_date="2026-01-10", value=9.6, unit="g/dL"),
        lab("Hemoglobin A1c", test_date="2026-09-01", value=5.4, unit="%"),
    ])
    assert [p["value"] for p in hemoglobin] == [9.6]
    glucose = analyzer._get_lab_points("glucose", [
        lab("Glucose", test_date="2026-01-10", value=182, unit="mg/dL"),
        lab("Urine glucose", test_date="2026-09-01", value=500, unit="mg/dL"),
    ])
    assert [p["value"] for p in glucose] == [182]
    a1c = analyzer._get_lab_points("hemoglobin a1c", [
        lab("Hemoglobin A1c", test_date="2025-01-10", value=8.4, unit="%"),
        lab("Hemoglobin A1c", test_date="2025-06-10", value=58, unit="mmol/mol"),
        lab("Hemoglobin A1c", test_date="2025-09-10", value=6.9, unit="%"),
        lab("Hemoglobin A1c", test_date="2026-01-10", value=64, unit="mmol/mol"),
    ])
    assert [p["value"] for p in a1c] == [58, 64]


def test_trajectories_keep_plain_numbers_in_the_newest_unit():
    from src.analysis.trajectory import TrajectoryForecaster

    groups = TrajectoryForecaster.__new__(TrajectoryForecaster)._group_labs([
        lab("Hemoglobin A1c", test_date="2025-01-10", value=8.4, unit="%"),
        lab("Hemoglobin A1c", test_date="2025-06-10", value=58, unit="mmol/mol"),
        lab("Hemoglobin A1c", test_date="2025-09-10", value=6.9, unit="%"),
        lab("Hemoglobin A1c", test_date="2026-01-10", value=64, unit="mmol/mol"),
        lab("Troponin I", test_date="2026-01-10", value=0.5, unit="ng/mL"),
        lab("Troponin I", test_date="2026-02-10", value=0.2, unit="ng/mL"),
        lab("Troponin I", test_date="2026-03-10", value=0.01, value_text="<0.01", unit="ng/mL"),
    ])
    points = {group["display_name"]: [p["value"] for p in group["points"]] for group in groups.values()}
    assert points == {"Hemoglobin A1c": [58, 64], "Troponin I": [0.5, 0.2]}


def test_a_monitoring_gap_uses_the_newest_result_under_any_name():
    from src.analysis.missing_negatives import MissingNegativeDetector

    detector = MissingNegativeDetector()
    history = detector._build_lab_history([
        lab("Vitamin D, 25-OH", test_date="2024-01-05", value=18, flag="Low"),
        lab("Vitamin D 25-OH", test_date="2026-08-01", value=35),
        lab("TSH", test_date="2025-01-10", value=8.9, flag="High"),
        lab("TSH, 3rd Generation", test_date="2026-06-10", value=2.1),
    ])
    assert str(detector._find_test_in_history("vitamin d", history)) == "2026-08-01"
    assert str(detector._find_test_in_history("tsh", history)) == "2026-06-10"


def test_cross_specialty_evidence_reads_each_test_s_newest_result():
    from src.analysis.diagnostic_engine.evidence_match import build_evidence

    evidence = build_evidence({"clinical_timeline": {"labs": [
        lab("Vitamin D, 25-Hydroxy", test_date="2024-01-05", value=18, unit="ng/mL", flag="Low"),
        lab("Vitamin D, 25-Hydroxy", test_date="2026-08-01", value=35, unit="ng/mL"),
    ]}})
    assert not evidence.match_lab_marker("low vitamin d")


def test_snowball_reads_a_normal_word_flag_as_normal():
    from src.analysis.deep_insights import _snowball_input

    normalized, _ = _snowball_input({"clinical_timeline": {"labs": [
        lab("SPEP", value_text="No monoclonal protein detected", flag="Not Detected"),
        lab("Sodium", value=140, unit="mmol/L", flag="No flag"),
        lab("Potassium", value=6.1, unit="mmol/L", flag="*"),
    ]}})
    assert [item["text"] for item in normalized["labs"]] == [
        "SPEP not detected", "Sodium", "Potassium abnormal"]


def test_dashboard_panel_keeps_the_qualifier_of_a_ranged_result():
    if not shutil.which("node"):
        pytest.skip("Node unavailable")
    charts = Path(__file__).parents[1] / "src/ui/static/js/dashboard_charts.js"
    labs = [
        {"name": "HIV-1 RNA", "value": 20, "value_text": "<20 copies/mL (not detected)",
         "unit": "copies/mL", "reference_low": 0, "reference_high": 20},
        {"name": "eGFR", "value": 60, "value_text": ">60", "unit": "mL/min/1.73m2",
         "reference_low": 60, "reference_high": 120},
        {"name": "Sodium", "value": 140, "unit": "mEq/L", "reference_low": 136, "reference_high": 145},
        {"name": "HIV 1/2 Ag/Ab", "value_text": "Non-reactive", "flag": "Non-reactive"},
    ]
    script = (
        "const fs = require('fs'); const texts = [];"
        "function node() { const o = { attr: () => o, append: () => node(),"
        " text: (t) => { texts.push(String(t)); return o; } }; return o; }"
        "var d3 = { select: () => node(), scaleLinear: () => { const s = () => 0;"
        " s.domain = () => s; s.range = () => s; s.clamp = () => s; return s; } };"
        "var document = { getElementById: () => ({ clientWidth: 400, firstChild: null }) };"
        f"eval(fs.readFileSync({json.dumps(str(LAB_RESULTS_JS))}, 'utf8') + ';'"
        f" + fs.readFileSync({json.dumps(str(charts))}, 'utf8'));"
        f"DashboardCharts.renderLabRangeBars('panel', {json.dumps(labs)});"
        "process.stdout.write(JSON.stringify(texts));"
    )
    result = subprocess.run(["node"], input=script, capture_output=True, text=True, check=True)
    shown = json.loads(result.stdout)
    assert "<20 copies/mL (not detected)" in shown and ">60 mL/min/1.73m2" in shown
    assert "20 copies/mL" not in shown and "60 mL/min/1.73m2" not in shown
    assert "140 mEq/L" in shown
    # A flag the result already says is not repeated.
    assert "Non-reactive" in shown and "Non-reactive (Non-reactive)" not in shown


def test_an_insight_saved_by_an_older_engine_is_computed_again():
    from src.analysis import deep_insights

    profile = {"clinical_timeline": {"labs": [
        lab("Glucose", value=38, unit="mg/dL", flag="Critical", reference_low=70, reference_high=100),
    ]}}
    # What an earlier build saved: the same inputs, keyed without an engine version.
    stale = {"active_cascades": ["Elevated Glucose"]}
    profile["analysis"] = {"biomarker_cascades": {
        "insight_type": "biomarker_cascades", "generated_at": "2026-01-01T00:00:00",
        "input_fingerprint": deep_insights._fingerprint(
            deep_insights._relevant_inputs(profile, "biomarker_cascades")),
        "provenance": [], "data": stale,
    }}
    result, changed = deep_insights.compute_deep_insight(profile, "biomarker_cascades")
    assert changed and result != stale
    # Computed once with this engine, it is reused.
    again, changed_again = deep_insights.compute_deep_insight(profile, "biomarker_cascades")
    assert again == result and not changed_again
