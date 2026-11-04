"""Conditions page: notes are linked by source page, and the list stays small.

conditions.js runs in Node against a minimal DOM; all records are synthetic.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CONDITIONS_JS = Path(__file__).parents[1] / "src/ui/static/js/conditions.js"

FAKE_DOM = r"""
class FakeNode {
    constructor(tag) {
        this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {};
        this.listeners = {}; this.className = ""; this.value = ""; this.open = false; this._text = "";
    }
    appendChild(child) { this.children.push(child); return child; }
    replaceChildren(...nodes) { this.children = []; nodes.forEach((n) => this.appendChild(n)); }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    getAttribute(key) { return this.attributes[key]; }
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
    dispatch(type) { (this.listeners[type] || []).forEach((fn) => fn({ type: type, target: this })); }
    focus() {}
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
}
const elements = {};
var document = { createElement: (tag) => new FakeNode(tag) };
function $(id) { return elements[id] || (elements[id] = new FakeNode("div")); }
function formatConfidence(value) { return Math.round(value * 100) + "%"; }
var App = { _activeProfileId: "synthetic", _demoMode: false };
var apiData = null;
async function api() { return apiData; }
function countNodes(node) { return 1 + node.children.reduce((n, c) => n + countNodes(c), 0); }
function find(node, tag) {
    if (node.tagName === tag) return [node];
    return node.children.reduce((all, c) => all.concat(find(c, tag)), []);
}
"""


def run_conditions_js(body, data):
    if not shutil.which("node"):
        pytest.skip("Node unavailable")
    script = (
        FAKE_DOM
        + CONDITIONS_JS.read_text()
        + f"\napiData = {json.dumps(data)};\n"
        + "(async () => { const out = await (async () => {" + body + "})();"
        + " process.stdout.write(JSON.stringify(out)); })();"
    )
    # On stdin: a large data set is too long to pass as an argument.
    result = subprocess.run(["node"], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def source(page, file="synthetic-history.pdf"):
    return {"source_file": file, "source_page": page}


def condition(name, page, **fields):
    return {"name": name, "status": "Active", "provenance": source(page), **fields}


def note(summary, page, file="synthetic-history.pdf"):
    return {"note_type": "visit_summary", "summary": summary, "provenance": source(page, file)}


def test_notes_are_linked_to_a_condition_only_from_the_same_page():
    data = {"conditions": [condition("Synthetic condition", 3)], "notes": [
        note("same page", 3), note("other page", 9), note("other file", 3, "other.pdf"),
    ]}
    linked = run_conditions_js(
        "await Conditions.load(); return Conditions.notesFor(Conditions.records[0]).map((n) => n.summary);",
        data,
    )
    assert linked == ["same page"]


def test_linked_note_cards_are_built_only_when_opened():
    data = {"conditions": [condition("Synthetic condition", 3)],
            "notes": [note("first note", 3), note("second note", 3)]}
    sizes = run_conditions_js(
        "await Conditions.load();"
        "const details = find($('conditions-list'), 'DETAILS')[0];"
        "const before = find(details, 'ARTICLE').length;"
        "details.open = true; details.dispatch('toggle');"
        "return [before, find(details, 'ARTICLE').length];",
        data,
    )
    assert sizes == [0, 2]


def test_one_large_document_keeps_the_page_small():
    pages = range(1, 301)
    data = {"conditions": [condition(f"Condition {p}", p) for p in pages],
            "notes": [note(f"Note {p}", p) for p in pages]}
    count = run_conditions_js("await Conditions.load(); return countNodes($('conditions-list'));", data)
    assert count < 40 * len(pages)


def test_condition_search_matches_the_condition_itself_not_its_notes():
    data = {"conditions": [condition("Synthetic condition", 3), condition("Other condition", 4)],
            "notes": [note("mentions zebra pattern", 3)]}
    shown = run_conditions_js(
        "await Conditions.load(); $('conditions-search').value = 'zebra'; Conditions.render();"
        "const conditions = find($('conditions-list'), 'ARTICLE').length;"
        "const message = $('conditions-list').textContent;"
        "const placeholder = $('conditions-search').placeholder;"
        "Conditions.setMode('notes');"
        "return [conditions, message, placeholder, find($('conditions-list'), 'ARTICLE').length,"
        " $('conditions-search').placeholder];",
        data,
    )
    conditions, message, placeholder, notes, notes_placeholder = shown
    assert (conditions, notes) == (0, 1)
    # The dead end points to where the match is.
    assert "1 record note matches" in message and "Available record notes" in message
    assert "note" not in placeholder.lower() and "note" in notes_placeholder.lower()


def test_link_copy_says_how_notes_were_matched():
    data = {"conditions": [condition("Synthetic condition", 3), condition("Unpaged condition", None),
                           condition("Lonely condition", 7)],
            "notes": [note("first note", 3), note("second note", 3)]}
    texts = run_conditions_js(
        "await Conditions.load();"
        "return find($('conditions-list'), 'ARTICLE').map((card) => card.textContent);",
        data,
    )
    linked, unpaged, lonely = texts[1], texts[2], texts[0]
    assert "View notes from the same part of the record (2)" in linked
    assert "A file without page numbers counts as a single page." in linked
    assert "page in the record was not saved, so notes can't be matched to it" in unpaged
    assert "No saved notes come from the same part of the record" in lonely


def test_reset_clears_counts_from_the_previous_profile():
    data = {"conditions": [condition("Synthetic condition", 3)], "notes": [note("A note", 3)]}
    state = run_conditions_js(
        "await Conditions.load(); Conditions.setMode('notes'); Conditions.reset();"
        "return [$('conditions-tab').textContent, $('condition-notes-tab').textContent,"
        " $('conditions-tab').getAttribute('aria-pressed'), $('conditions-list').getAttribute('aria-busy')];",
        data,
    )
    # No count is shown until a list has loaded.
    assert state == ["Conditions", "Available record notes", "true", "false"]


def test_many_notes_on_one_page_render_quickly():
    size = 4000
    data = {"conditions": [condition(f"Condition {i}", 1) for i in range(size)],
            "notes": [note(f"Note {i}", 1) for i in range(size)]}
    elapsed = run_conditions_js(
        "const start = Date.now(); await Conditions.load(); Conditions.render();"
        "return Date.now() - start;",
        data,
    )
    assert elapsed < 3000


def test_conditions_endpoint_returns_conditions_and_notes_uncached(monkeypatch):
    import src.ui.app as module

    monkeypatch.setattr(module, "_profile_data", {"clinical_timeline": {
        "diagnoses": [condition("Synthetic condition", 3)], "notes": [note("A note", 3)],
    }})
    with module.app.test_client() as client:
        response = client.get("/api/conditions")
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    assert [c["name"] for c in body["conditions"]] == ["Synthetic condition"]
    assert [n["summary"] for n in body["notes"]] == ["A note"]


def test_tabs_show_counts_only_once_the_list_has_loaded():
    data = {"conditions": [condition("Synthetic condition", 3)], "notes": [note("A note", 3)]}
    state = run_conditions_js(
        "await Conditions.load(); const loaded = [$('conditions-tab').textContent,"
        " $('condition-notes-tab').textContent];"
        "apiData = null; await Conditions.load();"
        "return [loaded, [$('conditions-tab').textContent, $('condition-notes-tab').textContent],"
        " $('conditions-count').textContent];",
        data,
    )
    loaded, failed, message = state
    assert loaded == ["Conditions (1)", "Available record notes (1)"]
    assert failed == ["Conditions", "Available record notes"]
    assert message.startswith("Could not load conditions")


def test_notes_search_points_back_to_matching_conditions():
    data = {"conditions": [condition("Synthetic diabetes", 3)], "notes": [note("A note", 3)]}
    shown = run_conditions_js(
        "await Conditions.load(); Conditions.setMode('notes');"
        " $('conditions-search').value = 'diabetes'; Conditions.render();"
        " const notes = [$('conditions-list').textContent, $('conditions-count').textContent];"
        " Conditions.setMode('conditions'); $('conditions-search').value = 'note'; Conditions.render();"
        " return notes.concat([$('conditions-count').textContent]);",
        data,
    )
    notes_list, notes_status, conditions_status = shown
    assert "1 condition matches" in notes_list and "Select Conditions" in notes_list
    # The pointer is read out with the count, not only shown in the list.
    assert "1 condition matches" in notes_status
    assert "1 record note matches" in conditions_status


def test_search_matches_what_the_cards_show():
    data = {"conditions": [
        condition("Asthma", 3, status="Inactive"),
        {"name": "Essential hypertension", "status": "Active",
         "provenance": {"source_file": "diabetes-clinic.pdf", "source_page": 4}},
    ], "notes": [{"note_type": "progress_note", "summary": "Synthetic summary",
                  "provenance": source(3)}]}
    counts = run_conditions_js(
        "await Conditions.load(); const shown = (q, mode) => { Conditions.setMode(mode);"
        " $('conditions-search').value = q; Conditions.render();"
        " return find($('conditions-list'), 'ARTICLE').length; };"
        "return [shown('active', 'conditions'), shown('diabetes', 'conditions'),"
        " shown('progress note', 'notes'), shown('asth', 'conditions')];",
        data,
    )
    assert counts == [1, 0, 1, 1]


def test_a_reload_during_a_run_keeps_the_list_and_open_notes():
    data = {"conditions": [condition("Synthetic condition", 3)],
            "notes": [note("first note", 3), note("second note", 3)]}
    state = run_conditions_js(
        "await Conditions.load();"
        "let details = find($('conditions-list'), 'DETAILS')[0];"
        "details.open = true; details.dispatch('toggle');"
        "const pending = Conditions.load();"
        "const during = [find($('conditions-list'), 'ARTICLE').length,"
        " find($('conditions-list'), 'DETAILS')[0].open];"
        "await pending;"
        "details = find($('conditions-list'), 'DETAILS')[0];"
        "return during.concat([details.open, find(details, 'ARTICLE').length]);",
        data,
    )
    # The card and its open notes stay on screen, and are open again after.
    assert state == [1, True, True, 2]


def test_a_card_names_the_page_its_record_section_starts_on():
    data = {"conditions": [condition("Synthetic condition", 4)], "notes": []}
    text = run_conditions_js(
        "await Conditions.load(); return find($('conditions-list'), 'ARTICLE')[0].textContent;", data)
    assert "Section starts on page: 4" in text


def test_dashboard_card_lists_current_conditions_first_with_their_status():
    shown = run_conditions_js(
        "Conditions.reset(); const loading = $('dash-dx-chart').textContent;"
        "Conditions.renderPreview([{name: 'Pneumonia', status: 'Resolved'},"
        " {name: 'Type 2 diabetes', status: 'Active'}, {name: 'Synthetic condition'}]);"
        "const items = find($('dash-dx-chart'), 'LI').map((li) => li.textContent);"
        "Conditions.renderPreviewMessage('Conditions could not be loaded.');"
        "return [loading, items, $('dash-dx-chart').textContent];",
        {"conditions": [], "notes": []},
    )
    loading, items, failed = shown
    assert loading == "Loading conditions…"
    assert items == ["Type 2 diabetes · Active", "Pneumonia · Resolved", "Synthetic condition"]
    assert failed == "Conditions could not be loaded."


def test_dashboard_lists_conditions_with_status_and_leaves_out_ruled_out(monkeypatch):
    import src.ui.app as module

    monkeypatch.setattr(module, "_profile_data", {"clinical_timeline": {"diagnoses": [
        {"name": "Pneumonia", "status": "Resolved"}, {"name": "Lupus", "status": "Ruled out"},
        {"name": "Type 2 diabetes", "status": "Active"},
    ]}})
    with module.app.test_client() as client:
        body = client.get("/api/dashboard").get_json()
    assert [(d["name"], d["status"]) for d in body["diagnoses_list"]] == [
        ("Type 2 diabetes", "Active"), ("Pneumonia", "Resolved"),
    ]
    assert body["diagnoses_count"] == 2


def test_a_single_letter_or_number_in_a_search_matches_a_whole_word():
    data = {"conditions": [
        condition("Hepatitis B, chronic", 3, status="Chronic", date_diagnosed="2016-09-30"),
        condition("Type 1 diabetes mellitus", 4, date_diagnosed="2015-06-01"),
        condition("Chronic kidney disease stage 4", 5, icd10_code="N18.4", date_diagnosed="2023-03-30"),
        condition("Chronic kidney disease stage 3a", 6, icd10_code="N18.31"),
        condition("Vitamin B12 deficiency", 7),
    ], "notes": []}
    counts = run_conditions_js(
        "await Conditions.load(); const shown = (q) => { $('conditions-search').value = q;"
        " Conditions.render(); return find($('conditions-list'), 'ARTICLE').map((a) => a.children[0].textContent); };"
        "return [shown('hepatitis c'), shown('type 2 diabetes'), shown('stage 3'), shown('N18.3'),"
        " shown('vitamin d deficiency'), shown('hepatitis b'), shown('stage 3a'), shown('diab')];",
        data,
    )
    # "N18.3" finds stage 3a (N18.31), never stage 4 through a date such as "30".
    assert counts == [[], [], ["Chronic kidney disease stage 3a"], ["Chronic kidney disease stage 3a"],
                      [], ["Hepatitis B, chronic"], ["Chronic kidney disease stage 3a"],
                      ["Type 1 diabetes mellitus"]]


def test_view_all_opens_the_full_condition_list():
    data = {"conditions": [condition("Synthetic condition", 3)], "notes": [note("kidney note", 3)]}
    state = run_conditions_js(
        "await Conditions.load(); Conditions.setMode('notes'); $('conditions-search').value = 'kidney';"
        "App.navigateTo = function() {}; Conditions.showAll();"
        "return [Conditions.mode, $('conditions-search').value];",
        data,
    )
    assert state == ["conditions", ""]


def test_dashboard_card_says_when_only_ruled_out_entries_are_on_file():
    shown = run_conditions_js(
        "Conditions.renderPreview([], 2); const none = [$('dash-dx-chart').textContent];"
        "Conditions.renderPreview([{name: 'Type 2 diabetes', status: 'Active'}], 1);"
        "return none.concat([$('dash-dx-preview-count').textContent]);",
        {"conditions": [], "notes": []},
    )
    assert "No current conditions" in shown[0] and "2 ruled-out entries" in shown[0]
    assert "1 ruled-out entry" in shown[1]


def test_dashboard_counts_ruled_out_entries_it_leaves_out(monkeypatch):
    import src.ui.app as module

    monkeypatch.setattr(module, "_profile_data", {"clinical_timeline": {"diagnoses": [
        {"name": "Lupus", "status": "Ruled out"}, {"name": "Type 2 diabetes", "status": "Active"},
    ]}})
    with module.app.test_client() as client:
        body = client.get("/api/dashboard").get_json()
    assert body["ruled_out_count"] == 1


def test_typing_a_search_does_not_rebuild_open_notes():
    data = {"conditions": [condition("Synthetic condition", 3)],
            "notes": [note("first note", 3), note("second note", 3)]}
    state = run_conditions_js(
        "await Conditions.load(); let details = find($('conditions-list'), 'DETAILS')[0];"
        "details.open = true; details.dispatch('toggle');"
        "$('conditions-search').value = 'synthetic'; Conditions.render();"
        "details = find($('conditions-list'), 'DETAILS')[0];"
        "return [details.open, find(details, 'ARTICLE').length];",
        data,
    )
    assert state == [False, 0]


def test_two_entries_with_the_same_name_and_page_open_separately():
    data = {"conditions": [condition("Synthetic condition", 3, status="Active"),
                           condition("Synthetic condition", 3, status="Resolved")],
            "notes": [note("a note", 3)]}
    state = run_conditions_js(
        "await Conditions.load(); let all = find($('conditions-list'), 'DETAILS');"
        "all[0].open = true; all[0].dispatch('toggle'); await Conditions.load();"
        "all = find($('conditions-list'), 'DETAILS'); return all.map((d) => d.open);",
        data,
    )
    assert state == [True, False]
