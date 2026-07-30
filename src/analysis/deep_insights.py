"""Persistable orchestration for the Hub's four deep-insight analyses.

All engines in this module run locally. Results are cached inside the encrypted
``PatientProfile.analysis`` object and invalidated when their clinical inputs
change. The snapshot retains source provenance without copying raw source text.
"""

from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from datetime import date, datetime
from typing import Callable

from src.models import DeepInsightSnapshot, Provenance

logger = logging.getLogger("CIH-DeepInsights")


INSIGHT_FIELDS = {
    "snowball": "snowball_differential",
    "biomarker_cascades": "biomarker_cascades",
    "pgx_collisions": "pgx_collision_map",
    "trajectories": "lab_trajectories",
    "cross_specialty": "cross_specialty_patterns",
}


def _timeline(profile_data: dict) -> dict:
    value = profile_data.get("clinical_timeline", {})
    return value if isinstance(value, dict) else {}


def _analysis(profile_data: dict) -> dict:
    value = profile_data.setdefault("analysis", {})
    if not isinstance(value, dict):
        value = {}
        profile_data["analysis"] = value
    return value


def _relevant_inputs(profile_data: dict, insight_type: str) -> dict:
    timeline = _timeline(profile_data)
    analysis = profile_data.get("analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}

    if insight_type == "snowball":
        return {
            "demographics": profile_data.get("demographics", {}),
            "diagnoses": timeline.get("diagnoses", []),
            "labs": timeline.get("labs", []),
            "medications": timeline.get("medications", []),
            "symptoms": timeline.get("symptoms", []),
            "imaging": timeline.get("imaging", []),
            "flags": analysis.get("flags", []),
        }
    if insight_type == "biomarker_cascades":
        return {"labs": timeline.get("labs", [])}
    if insight_type == "pgx_collisions":
        return {
            "genetics": timeline.get("genetics", []),
            "medications": timeline.get("medications", []),
        }
    if insight_type == "trajectories":
        return {
            "labs": timeline.get("labs", []),
            "medications": timeline.get("medications", []),
            "genetics": timeline.get("genetics", []),
            "symptoms": timeline.get("symptoms", []),
        }
    if insight_type == "cross_specialty":
        # Mirrors CrossSpecialtyEngine._build_corpus inputs.
        return {
            "diagnoses": timeline.get("diagnoses", []),
            "labs": timeline.get("labs", []),
            "medications": timeline.get("medications", []),
            "symptoms": timeline.get("symptoms", []),
            "imaging": timeline.get("imaging", []),
            "genetics": timeline.get("genetics", []),
        }
    raise ValueError(f"Unknown deep insight type: {insight_type}")


def _fingerprint(value: dict) -> str:
    serialized = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _collect_provenance(value) -> list[Provenance]:
    """Collect unique source citations, excluding copied raw clinical text."""
    found: list[Provenance] = []
    seen: set[tuple] = set()

    def visit(item):
        if isinstance(item, dict):
            provenance = item.get("provenance")
            if isinstance(provenance, dict) and provenance.get("source_file"):
                try:
                    clean = dict(provenance)
                    clean.pop("raw_text", None)
                    parsed = Provenance.model_validate(clean)
                    key = (
                        parsed.source_file,
                        parsed.source_page,
                        parsed.extraction_model,
                        parsed.date_extracted.isoformat(),
                    )
                    if key not in seen:
                        seen.add(key)
                        found.append(parsed)
                except (TypeError, ValueError):
                    pass
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found


def _snowball_input(profile_data: dict) -> tuple[dict, dict]:
    """Adapt the canonical nested profile to SnowballEngine's input contract."""
    normalized = deepcopy(profile_data)
    timeline = _timeline(profile_data)
    analysis = profile_data.get("analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}

    normalized["diagnoses"] = timeline.get("diagnoses", [])
    normalized["medications"] = timeline.get("medications", [])

    normalized_labs = []
    for lab in timeline.get("labs", []):
        if not isinstance(lab, dict):
            continue
        item = dict(lab)
        name = str(item.get("name") or item.get("test_name") or "").strip()
        flag = str(item.get("flag") or "").strip().lower()
        direction = {"high": "elevated", "critical": "elevated", "low": "low"}.get(flag, flag)
        item["text"] = " ".join(part for part in (name, direction) if part)
        normalized_labs.append(item)
    normalized["labs"] = normalized_labs

    normalized_flags = []
    for flag in analysis.get("flags", []):
        if not isinstance(flag, dict):
            continue
        item = dict(flag)
        item["text"] = " ".join(
            str(item.get(key) or "").strip()
            for key in ("title", "description")
        ).strip()
        normalized_flags.append(item)
    normalized["flags"] = normalized_flags

    demographics = profile_data.get("demographics", {})
    if not isinstance(demographics, dict):
        demographics = {}
    birth_year = demographics.get("birth_year")
    try:
        age = date.today().year - int(birth_year) if birth_year else None
    except (TypeError, ValueError):
        age = None
    engine_demographics = {
        "age": age,
        "sex": demographics.get("biological_sex"),
    }
    return normalized, engine_demographics


def _compute_snowball(profile_data: dict) -> dict:
    from src.analysis.snowball_engine import SnowballEngine

    normalized, demographics = _snowball_input(profile_data)
    return SnowballEngine(demographics=demographics).analyze(normalized)


def _compute_biomarker_cascades(profile_data: dict) -> dict:
    from src.analysis.biomarker_cascades import BiomarkerCascadeEngine

    return BiomarkerCascadeEngine().analyze(profile_data)


def _compute_pgx_collisions(profile_data: dict) -> dict:
    from src.analysis.diagnostic_engine.pharmacogenomics import PharmacogenomicEngine

    return PharmacogenomicEngine().analyze(profile_data)


def _compute_cross_specialty(profile_data: dict) -> dict:
    """Rule-triad + local-AI cross-specialty correlations, snapshot-cached.

    Wraps the engine list in an object so the generic snapshot plumbing
    (dict-shaped ``data``) applies unchanged.
    """
    from src.analysis.diagnostic_engine.cross_specialty import CrossSpecialtyEngine

    connections = CrossSpecialtyEngine().analyze(profile_data)
    return {"connections": connections if isinstance(connections, list) else []}


def _compute_trajectories(profile_data: dict) -> dict:
    from src.analysis.trajectory import TrajectoryForecaster

    result = TrajectoryForecaster().analyze(profile_data)

    try:
        from src.analysis.side_effect_scorer import SideEffectScorer

        timeline = _timeline(profile_data)
        scored_by_med = SideEffectScorer().score_all_linked_episodes(
            timeline.get("symptoms", []),
            timeline.get("medications", []),
            timeline.get("genetics", []),
        )
        for trajectory in result.get("trajectories", []):
            for medication in trajectory.get("relevant_medications", []):
                med_name = medication.get("name", "")
                medication["side_effects"] = scored_by_med.get(med_name, [])
    except Exception as exc:
        logger.warning(
            "Deep insight side-effect enrichment failed (error_type=%s)",
            type(exc).__name__,
        )

    return result


_COMPUTERS: dict[str, Callable[[dict], dict]] = {
    "snowball": _compute_snowball,
    "biomarker_cascades": _compute_biomarker_cascades,
    "pgx_collisions": _compute_pgx_collisions,
    "trajectories": _compute_trajectories,
    "cross_specialty": _compute_cross_specialty,
}


def compute_deep_insight(
    profile_data: dict,
    insight_type: str,
    *,
    force: bool = False,
) -> tuple[dict, bool]:
    """Return one insight result and whether the encrypted profile changed."""
    if insight_type not in INSIGHT_FIELDS:
        raise ValueError(f"Unknown deep insight type: {insight_type}")

    inputs = _relevant_inputs(profile_data, insight_type)
    fingerprint = _fingerprint(inputs)
    analysis = _analysis(profile_data)
    field_name = INSIGHT_FIELDS[insight_type]
    cached = analysis.get(field_name)

    if not force and isinstance(cached, dict):
        if cached.get("input_fingerprint") == fingerprint and isinstance(cached.get("data"), dict):
            return cached["data"], False

    result = _COMPUTERS[insight_type](profile_data)
    if not isinstance(result, dict):
        raise TypeError(f"{insight_type} engine returned a non-object result")

    snapshot = DeepInsightSnapshot(
        insight_type=insight_type,
        generated_at=datetime.now(),
        input_fingerprint=fingerprint,
        provenance=_collect_provenance(inputs),
        data=result,
    )
    analysis[field_name] = snapshot.model_dump(mode="json")
    profile_data["updated_at"] = datetime.now().isoformat()
    return result, True


def compute_all_deep_insights(profile_data: dict) -> tuple[bool, dict[str, str]]:
    """Compute/cache every insight, degrading safely if one engine fails."""
    changed = False
    errors: dict[str, str] = {}

    for insight_type in INSIGHT_FIELDS:
        try:
            _, insight_changed = compute_deep_insight(profile_data, insight_type)
            changed = changed or insight_changed
        except Exception as exc:
            errors[insight_type] = type(exc).__name__
            logger.warning(
                "Deep insight computation failed (insight=%s, error_type=%s)",
                insight_type,
                type(exc).__name__,
            )

    return changed, errors


def persisted_deep_insights(profile_data: dict) -> dict:
    """Return all persisted snapshots using stable public insight names."""
    analysis = profile_data.get("analysis", {})
    if not isinstance(analysis, dict):
        return {}
    return {
        insight_type: analysis[field_name]
        for insight_type, field_name in INSIGHT_FIELDS.items()
        if isinstance(analysis.get(field_name), dict)
    }
