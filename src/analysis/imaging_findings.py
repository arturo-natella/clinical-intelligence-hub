"""One reading of imaging ``findings``, shared by every corpus builder.

The canonical model is ``ImagingStudy.findings: list[ImagingFinding]``. Profiles
written before that contract was enforced — and any hand-edited vault — can
still carry a single free-text string per study. Iterating a string yields
characters, so consumers that assumed the canonical shape either crashed
(``'str' object has no attribute 'get'``) or quietly filled their corpus with
single letters.

``normalize_findings`` is the single place that reconciles the shapes. It
coerces, it does not filter: callers keep their own emptiness rules, so a MONAI
finding carrying radiomic threshold flags but no description survives.
"""

from __future__ import annotations


def normalize_findings(raw) -> list[dict]:
    """Return imaging findings as a list of dicts, whatever shape they arrived in.

    Accepts the canonical ``list[dict]``, a bare ``str`` (legacy per-study
    free text), a lone ``dict``, or a list mixing strings and dicts. Dicts pass
    through untouched so downstream fields such as ``radiomic_features`` and
    ``confidence`` are preserved. Anything else contributes nothing.
    """
    if not raw:
        return []

    if isinstance(raw, (str, dict)):
        raw = [raw]
    elif not isinstance(raw, (list, tuple)):
        return []

    normalized: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            normalized.append(item)
        elif isinstance(item, str) and item.strip():
            normalized.append({"description": item.strip()})
    return normalized
