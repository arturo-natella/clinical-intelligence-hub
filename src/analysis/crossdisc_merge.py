"""Merge the three cross-disciplinary layers into one deduplicated list.

Layers: stored Pass-3 cloud connections (model-shaped dicts), plus the
snapshot-cached engine results (rule-triad "pattern_database" and
"local_ai" discovery, engine-shaped dicts). The UI endpoint and the Word
report both render the same merged output, so every surface agrees.
"""

from __future__ import annotations

import re

_SEVERITY_RANK = {"critical": 4, "high": 3, "moderate": 2, "low": 1, "info": 0}


def _dedupe_key(title: str) -> str:
    """Casefolded title with parentheticals stripped — 'APS (…)' == 'APS'."""
    text = re.sub(r"\([^)]*\)", " ", str(title or ""))
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def _citation_from_pubmed(raw: dict) -> dict | None:
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    return {
        "title": title,
        "authors": raw.get("authors"),
        "journal": raw.get("journal"),
        "year": raw.get("year"),
        "doi": raw.get("doi"),
        "pubmed_id": raw.get("pmid") or raw.get("pubmed_id"),
        "relevance_summary": raw.get("relevance_summary"),
    }


def _normalize_engine_entry(raw: dict) -> dict:
    """Engine-shaped correlation → model-shaped connection dict."""
    legacy_type = raw.get("type", "systemic_correlation")
    connection_type = raw.get("connection_type") or (
        "local_ai" if legacy_type == "ai_discovered_correlation" else "pattern_database"
    )
    entry = {
        "type": legacy_type,  # legacy key some frontend branches still read
        "connection_type": connection_type,
        "title": raw.get("disease") or raw.get("title") or "",
        "description": raw.get("description", ""),
        "specialties": list(raw.get("specialties", []) or []),
        "severity": raw.get("severity", "moderate"),
        "patient_data_points": list(
            raw.get("matched_symptoms") or raw.get("patient_data_points") or []
        ),
        "matched_labs": list(raw.get("matched_labs", []) or []),
        "question_for_doctor": raw.get("recommendation")
        or raw.get("question_for_doctor")
        or "",
        "total_hits": raw.get("total_hits"),
        "total_possible": raw.get("total_possible"),
        "evidence_source": raw.get("evidence_source", ""),
        "diagnostic_source": raw.get("diagnostic_source", ""),
    }
    if connection_type == "local_ai":
        entry["pubmed_verified"] = bool(raw.get("pubmed_verified", False))
        citations = raw.get("pubmed_citations", []) or []
        entry["pubmed_citations"] = citations  # legacy passthrough for the graph
        entry["supporting_literature"] = [
            c for c in (_citation_from_pubmed(x) for x in citations if isinstance(x, dict)) if c
        ]
    return entry


def _specialties_overlap(a: dict, b: dict) -> bool:
    sa = {str(s).lower() for s in a.get("specialties", []) if s}
    sb = {str(s).lower() for s in b.get("specialties", []) if s}
    if not sa or not sb:
        return True
    return bool(sa & sb)


def _union_list(base: list, extra: list) -> list:
    seen = {str(item).lower() for item in base}
    for item in extra or []:
        if str(item).lower() not in seen:
            base.append(item)
            seen.add(str(item).lower())
    return base


def _merge_into(base: dict, incoming: dict) -> None:
    """Fold a duplicate finding into the kept entry, preserving evidence."""
    also = set(base.get("also_matched_by", []))
    if incoming.get("connection_type") and incoming["connection_type"] != base.get("connection_type"):
        also.add(incoming["connection_type"])
    if also:
        base["also_matched_by"] = sorted(also)

    if not base.get("description") and incoming.get("description"):
        base["description"] = incoming["description"]
    for field in ("question_for_doctor", "evidence_source", "diagnostic_source"):
        if not base.get(field) and incoming.get(field):
            base[field] = incoming[field]
    for field in ("total_hits", "total_possible"):
        if base.get(field) is None and incoming.get(field) is not None:
            base[field] = incoming[field]

    _union_list(base.setdefault("specialties", []), incoming.get("specialties", []))
    _union_list(base.setdefault("patient_data_points", []), incoming.get("patient_data_points", []))
    _union_list(base.setdefault("matched_labs", []), incoming.get("matched_labs", []))

    base_lit = base.setdefault("supporting_literature", [])
    have_titles = {
        str(item.get("title", "")).lower() for item in base_lit if isinstance(item, dict)
    }
    for item in incoming.get("supporting_literature", []) or []:
        if isinstance(item, dict) and str(item.get("title", "")).lower() not in have_titles:
            base_lit.append(item)
            have_titles.add(str(item.get("title", "")).lower())

    incoming_rank = _SEVERITY_RANK.get(str(incoming.get("severity", "")).lower(), -1)
    base_rank = _SEVERITY_RANK.get(str(base.get("severity", "")).lower(), -1)
    if incoming_rank > base_rank:
        base["severity"] = incoming["severity"]


def merge_connections(stored: list, engine_results: list) -> list[dict]:
    """Stored cloud connections + engine correlations, deduped and enriched.

    Duplicate = same parenthetical-stripped casefolded title AND at least one
    shared specialty (an empty specialty list on either side counts as
    overlapping). Stored entries are kept as the base; duplicates merge their
    evidence in rather than appearing twice.
    """
    merged: list[dict] = [dict(item) for item in stored or [] if isinstance(item, dict)]
    index: dict[str, dict] = {}
    for entry in merged:
        key = _dedupe_key(entry.get("title", ""))
        if key:
            index.setdefault(key, entry)

    for raw in engine_results or []:
        if not isinstance(raw, dict):
            continue
        entry = _normalize_engine_entry(raw)
        key = _dedupe_key(entry.get("title", ""))
        if not key:
            continue
        existing = index.get(key)
        if existing is not None and _specialties_overlap(existing, entry):
            _merge_into(existing, entry)
        else:
            merged.append(entry)
            index.setdefault(key, entry)

    return merged
