"""Cross-disciplinary unification (2026-07-30 spec) — model, merge, wiring.

Grown alongside the implementation; each block pins one seam that was
previously silent-failing (see docs/superpowers/specs/2026-07-30-crossdisc-unify-design.md).
"""

from src.models import CrossDisciplinaryConnection


# ── Model round-trip: layer fields must survive validation ──

def test_connection_model_retains_layer_fields():
    """Regression: these fields were silently dropped by model_validate."""
    payload = {
        "title": "Iron overload pattern",
        "description": "Ferritin and joint findings across specialties.",
        "specialties": ["Hepatology", "Rheumatology"],
        "patient_data_points": ["joint pain", "fatigue"],
        "severity": "high",
        "connection_type": "pattern_database",
        "total_hits": 5,
        "total_possible": 12,
        "matched_labs": ["ferritin", "transferrin saturation"],
        "evidence_source": "Validated systemic disease pattern database",
        "diagnostic_source": "ACG Clinical Guideline (2019)",
        "pubmed_verified": True,
    }
    conn = CrossDisciplinaryConnection.model_validate(payload)
    dumped = conn.model_dump(mode="json")

    assert dumped["connection_type"] == "pattern_database"
    assert dumped["total_hits"] == 5
    assert dumped["total_possible"] == 12
    assert dumped["matched_labs"] == ["ferritin", "transferrin saturation"]
    assert dumped["evidence_source"].startswith("Validated")
    assert dumped["diagnostic_source"].startswith("ACG")
    assert dumped["pubmed_verified"] is True


def test_connection_model_defaults_cloud_analysis():
    conn = CrossDisciplinaryConnection.model_validate({
        "title": "T",
        "description": "D",
        "specialties": ["Cardiology"],
        "patient_data_points": [],
        "severity": "moderate",
    })
    assert conn.connection_type == "cloud_analysis"
    assert conn.total_hits is None
    assert conn.matched_labs == []
    assert conn.pubmed_verified is None


# ── Merge helper ────────────────────────────────────────────

from pathlib import Path

from src.analysis.crossdisc_merge import merge_connections

REPO = Path(__file__).resolve().parent.parent


def _engine_aps():
    return {
        "type": "systemic_correlation",
        "disease": "Antiphospholipid Syndrome",
        "specialties": ["Hematology", "Neurology"],
        "severity": "high",
        "description": "Engine description.",
        "matched_symptoms": ["dvt"],
        "matched_labs": ["anticardiolipin"],
        "total_hits": 4,
        "total_possible": 15,
        "diagnostic_source": "ACR/EULAR 2023",
        "evidence_source": "pattern db",
        "recommendation": "Ask about APS.",
    }


def test_merge_dedupes_parenthetical_titles_with_specialty_overlap():
    stored = [{
        "title": "Antiphospholipid Syndrome (APS)",
        "specialties": ["Rheumatology", "Hematology"],
        "severity": "moderate",
        "description": "Cloud found it.",
        "connection_type": "cloud_analysis",
    }]
    merged = merge_connections(stored, [_engine_aps()])

    assert len(merged) == 1
    entry = merged[0]
    assert entry["connection_type"] == "cloud_analysis"       # stored is base
    assert entry["also_matched_by"] == ["pattern_database"]   # origin recorded
    assert entry["severity"] == "high"                        # escalated
    assert entry["total_hits"] == 4                           # evidence filled
    assert "Neurology" in entry["specialties"]                # union
    assert entry["diagnostic_source"] == "ACR/EULAR 2023"


def test_merge_keeps_distinct_findings_separate():
    stored = [{
        "title": "Metabolic syndrome cluster",
        "specialties": ["Endocrinology"],
        "severity": "moderate",
        "description": "d",
    }]
    merged = merge_connections(stored, [_engine_aps()])
    assert len(merged) == 2


def test_merge_normalizes_local_ai_citations():
    engine = [{
        "type": "ai_discovered_correlation",
        "disease": "Thyroid-lipid correlation",
        "specialties": ["Endocrinology", "Cardiology"],
        "severity": "moderate",
        "description": "d",
        "pubmed_verified": True,
        "pubmed_citations": [{"title": "Paper", "journal": "J", "year": 2024, "pmid": "123"}],
        "recommendation": "r",
    }]
    merged = merge_connections([], engine)
    entry = merged[0]
    assert entry["connection_type"] == "local_ai"
    assert entry["pubmed_verified"] is True
    assert entry["supporting_literature"][0]["pubmed_id"] == "123"
    assert entry["title"] == "Thyroid-lipid correlation"
    assert entry["question_for_doctor"] == "r"


# ── Rule table hygiene ──────────────────────────────────────

def test_rule_table_single_aps_entry_and_dynamic_count():
    from src.analysis.diagnostic_engine.cross_specialty import SYSTEMIC_DISEASE_TRIADS

    aps_keys = [k for k in SYSTEMIC_DISEASE_TRIADS if "antiphospholipid" in k.lower()]
    assert len(aps_keys) == 1, f"duplicate APS triads: {aps_keys}"

    source = (REPO / "src/analysis/diagnostic_engine/cross_specialty.py").read_text()
    assert "22 clinically documented" not in source, "hardcoded stale count"
    assert "len(SYSTEMIC_DISEASE_TRIADS)" in source


# ── Pass 3 query wiring ─────────────────────────────────────

def test_prioritized_queries_capped_and_high_first():
    from src.analysis.cross_disciplinary import CrossDisciplinaryEngine

    profile = {
        "medications": [{"name": f"Med{i}", "status": "active"} for i in range(12)],
        "labs": [{"name": f"Lab{i}", "value": 1, "flag": "High"} for i in range(12)],
        "diagnoses": [{"name": f"Dx{i}", "status": "Active"} for i in range(10)],
        "genetics": [],
    }
    queries = CrossDisciplinaryEngine().build_prioritized_queries(profile, cap=10)

    assert len(queries) == 10
    rank = {"high": 0, "medium": 1, "low": 2}
    ranks = [rank.get(str(q.get("priority", "medium")).lower(), 1) for q in queries]
    assert ranks == sorted(ranks), "queries must be priority-ordered"


def test_pipeline_no_longer_sends_empty_query_list():
    source = (REPO / "src/ui/pipeline.py").read_text()
    assert "dr.analyze(profile_summary, [])" not in source
    assert "build_prioritized_queries" in source


# ── Pass 4 citation attachment ──────────────────────────────

def test_pass4_citations_attach_to_matching_connection():
    from src.analysis.deep_research import DeepResearch

    dr = DeepResearch.__new__(DeepResearch)  # bypass client init
    conn = CrossDisciplinaryConnection(
        title="Statin-Diabetes glucose effect",
        description="d",
        specialties=["Cardiology", "Endocrinology"],
        patient_data_points=[],
        severity="moderate",
    )
    raw = {
        "literature": [
            {
                "title": "Statins and glycemic control",
                "journal": "JAMA",
                "year": 2023,
                "connection_title": "Statin-Diabetes glucose effect",
            },
            {"title": "Unrelated paper", "connection_title": "Something else entirely"},
        ],
        "questions": ["Q1"],
    }
    results = dr._parse_pass4_results(raw, [conn])

    assert len(results["literature"]) == 2          # flat list keeps everything
    assert len(conn.supporting_literature) == 1     # only the match attaches
    assert conn.supporting_literature[0].journal == "JAMA"


# ── Snapshot caching for the engine ─────────────────────────

def test_cross_specialty_snapshot_cached_until_inputs_change(monkeypatch):
    from src.analysis import deep_insights

    calls = {"n": 0}

    def fake_compute(profile_data):
        calls["n"] += 1
        return {"connections": [_engine_aps()]}

    monkeypatch.setitem(deep_insights._COMPUTERS, "cross_specialty", fake_compute)

    profile = {"clinical_timeline": {
        "diagnoses": [{"name": "D1"}], "labs": [], "medications": [],
        "symptoms": [], "imaging": [], "genetics": [],
    }}

    result1, changed1 = deep_insights.compute_deep_insight(profile, "cross_specialty")
    result2, changed2 = deep_insights.compute_deep_insight(profile, "cross_specialty")
    assert calls["n"] == 1 and changed1 and not changed2
    assert result2["connections"][0]["disease"] == "Antiphospholipid Syndrome"

    profile["clinical_timeline"]["diagnoses"].append({"name": "D2"})
    _, changed3 = deep_insights.compute_deep_insight(profile, "cross_specialty")
    assert calls["n"] == 2 and changed3


# ── Report: shared merge + honest empty copy ────────────────

def test_report_merges_snapshot_with_stored_connections():
    from src.models import AnalysisResults, DeepInsightSnapshot
    from src.report.builder import ReportBuilder

    builder = ReportBuilder.__new__(ReportBuilder)  # helper needs no doc state
    analysis = AnalysisResults(
        cross_disciplinary=[CrossDisciplinaryConnection(
            title="Antiphospholipid Syndrome (APS)",
            description="Cloud description.",
            specialties=["Rheumatology", "Hematology"],
            patient_data_points=[],
            severity="moderate",
        )],
        cross_specialty_patterns=DeepInsightSnapshot(
            insight_type="cross_specialty",
            input_fingerprint="f",
            data={"connections": [_engine_aps()]},
        ),
    )
    merged = builder._merged_cross_disciplinary(analysis)
    assert len(merged) == 1
    assert merged[0]["also_matched_by"] == ["pattern_database"]


def test_report_empty_copy_is_a_technical_status_not_reassurance():
    source = (REPO / "src/report/builder.py").read_text()
    assert "well-coordinated across providers" not in source
    assert "not a clinical finding" in source


# ── Visit Prep legacy-entry regression ──────────────────────

def test_visit_prep_add_survives_legacy_string_entries(monkeypatch):
    from src.ui import app as app_module

    monkeypatch.setattr(app_module, "_profile_data", {
        "analysis": {"questions_for_doctor": ["legacy plain string question"]},
    })
    monkeypatch.setattr(app_module, "_save_symptoms_to_vault", lambda: True)

    client = app_module.app.test_client()
    resp = client.post("/api/questions", json={"question": "New question?"})
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True


# ── Graph static contract ───────────────────────────────────

def test_graph_covers_five_severities_and_credits_local_ai():
    js = (REPO / "src/ui/static/js/crossdisc_graph.js").read_text()

    assert "critical: 32" in js and "info: 13" in js, "severity radius map incomplete"
    assert 'critical: "#C84040"' in js and 'info: "#7AB0F0"' in js
    assert "Object.keys(self._sevColor)" in js, "gradient defs must cover every severity"

    assert "Gemini identified" not in js, "local-AI findings must not be credited to Gemini"
    assert "Gemini cites" not in js
    assert "local AI model" in js

    assert "_buildFilterBar" in js
    assert "Not relevant" in js, "dismissal must be persisted, not session-only"
    assert "/api/findings/dismiss" in js
    assert "_hidden" not in js, "session-only hiding was replaced by vault-persisted dismissals"
    assert "Nutrition/Metabolic Medicine" in js, "canonical taxonomy colors missing"
