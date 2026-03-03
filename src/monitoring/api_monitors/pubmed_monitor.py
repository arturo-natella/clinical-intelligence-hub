"""
Clinical Intelligence Hub — PubMed Monitoring (v2.0)

Checks for new publications relevant to the patient's conditions,
medications, genetic variants, and tracked symptoms.

Uses NCBI E-utilities (free, 3 req/sec without API key, 10/sec with key).

v2.0 additions:
  - Symptom-based queries from the symptom log
  - Medication combination queries (polypharmacy interaction research)
  - Expanded genetic variant queries (all variants, not just "actionable")
  - Gemini relevance scoring to filter noise
  - Dict-based input for vault compatibility
"""

import json
import logging
import urllib.parse
import urllib.request
from datetime import date, timedelta
from itertools import combinations
from typing import Optional

from src.models import AlertSeverity, MonitoringAlert, PatientProfile

logger = logging.getLogger("CIH-Monitor-PubMed")


# ── Query Category Tags ──────────────────────────────────

CATEGORY_SYMPTOM = "symptom_research"
CATEGORY_MED_SAFETY = "medication_safety"
CATEGORY_MED_COMBO = "medication_combination"
CATEGORY_DIAGNOSIS = "diagnosis_treatment"
CATEGORY_GENETICS = "genetic_variant"


class PubMedMonitor:
    """Monitors PubMed for new relevant publications.

    Builds targeted queries across 5 categories:
      1. Symptom research — new findings for tracked symptoms
      2. Medication safety — adverse reactions for active meds
      3. Medication combinations — interaction studies for drug pairs
      4. Diagnosis treatment — clinical trials and reviews for conditions
      5. Genetic variants — pharmacogenomic updates for all known variants
    """

    def __init__(self, api_key: str = None, gemini_api_key: str = None):
        self._api_key = api_key
        self._gemini_api_key = gemini_api_key

    # ── Public API ──────────────────────────────────────────

    def check(self, profile: PatientProfile,
              days_back: int = 7) -> list[MonitoringAlert]:
        """Legacy interface: check using PatientProfile model."""
        alerts = []
        queries = self._build_queries(profile)
        return self._execute_queries(queries, days_back)

    def check_from_dict(self, profile_data: dict,
                        days_back: int = 30) -> list[MonitoringAlert]:
        """
        v2.0 interface: check using raw profile_data dict from vault.

        Supports symptom-based queries, medication combos, and expanded
        genetic queries. Optionally scores results with Gemini.

        Args:
            profile_data: The patient profile dict from the vault
            days_back: How many days back to search (default 30 for sweeps)

        Returns:
            List of monitoring alerts, optionally ranked by relevance
        """
        queries = self._build_queries_from_dict(profile_data)
        alerts = self._execute_queries(queries, days_back)

        # Score with Gemini if available
        if self._gemini_api_key and alerts:
            alerts = self._score_relevance(alerts, profile_data)

        return alerts

    # ── Query Execution ────────────────────────────────────

    def _execute_queries(self, queries: list[dict],
                         days_back: int) -> list[MonitoringAlert]:
        """Execute a batch of PubMed queries and return alerts."""
        if not queries:
            return []

        try:
            from src.validation.pubmed import PubMedClient
            client = PubMedClient(api_key=self._api_key)
        except Exception as e:
            logger.error("PubMed client init failed: %s", e)
            return []

        # Date filter
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
        date_filter = (
            f' AND ("{start_date.strftime("%Y/%m/%d")}"'
            f'[Date - Publication] : "{end_date.strftime("%Y/%m/%d")}"'
            f'[Date - Publication])'
        )

        alerts = []
        seen_titles = set()  # deduplicate across queries

        for query_info in queries:
            try:
                full_query = query_info["query"] + date_filter
                citations = client.search(full_query, max_results=3)

                for cit in citations:
                    # Skip duplicates
                    title_key = (cit.title or "").lower().strip()
                    if title_key in seen_titles:
                        continue
                    seen_titles.add(title_key)

                    alerts.append(MonitoringAlert(
                        source="PubMed",
                        title=cit.title or "New publication",
                        description=(
                            f"New study: \"{cit.title}\" "
                            f"({cit.authors or 'Unknown'}, {cit.year}). "
                            f"Published in {cit.journal or 'Unknown journal'}."
                        ),
                        relevance_explanation=query_info["relevance"],
                        severity=query_info.get("severity", AlertSeverity.LOW),
                        url=(
                            f"https://pubmed.ncbi.nlm.nih.gov/{cit.pubmed_id}/"
                            if cit.pubmed_id else None
                        ),
                    ))

            except Exception as e:
                logger.debug("PubMed query failed: %s", e)

        logger.info("PubMed monitor found %d alerts from %d queries",
                     len(alerts), len(queries))
        return alerts

    # ── Query Builders ─────────────────────────────────────

    def _build_queries(self, profile: PatientProfile) -> list[dict]:
        """Build queries from PatientProfile (legacy v1 interface)."""
        queries = []
        timeline = profile.clinical_timeline

        if not timeline:
            return []

        # Medication safety
        for med in (timeline.medications or []):
            status_val = getattr(med.status, "value", str(med.status)).lower()
            if med.status and status_val in ("active", "prn"):
                queries.append({
                    "query": (
                        f'"{med.name}"[MeSH Terms] AND '
                        f'("drug-related side effects and adverse reactions"[MeSH] '
                        f'OR "safety"[Title])'
                    ),
                    "relevance": f"Patient is currently taking {med.name}.",
                    "severity": AlertSeverity.MODERATE,
                    "category": CATEGORY_MED_SAFETY,
                })

        # Diagnosis treatment
        for dx in (timeline.diagnoses or []):
            if dx.status and dx.status.lower() in ("active", "chronic"):
                queries.append({
                    "query": (
                        f'"{dx.name}"[MeSH Terms] AND '
                        f'("therapy"[Subheading] OR "treatment"[Title]) AND '
                        f'(clinical trial[pt] OR meta-analysis[pt])'
                    ),
                    "relevance": f"Patient has active diagnosis: {dx.name}.",
                    "severity": AlertSeverity.LOW,
                    "category": CATEGORY_DIAGNOSIS,
                })

        # Genetic variants
        for variant in (timeline.genetics or []):
            if variant.clinical_significance and "actionable" in variant.clinical_significance.lower():
                queries.append({
                    "query": (
                        f'"{variant.gene}"[Title] AND '
                        f'"pharmacogenomics"[MeSH Terms]'
                    ),
                    "relevance": (
                        f"Patient has {variant.gene} {variant.variant} variant "
                        f"({variant.phenotype})."
                    ),
                    "severity": AlertSeverity.MODERATE,
                    "category": CATEGORY_GENETICS,
                })

        return queries

    def _build_queries_from_dict(self, profile_data: dict) -> list[dict]:
        """
        Build expanded queries from raw profile_data dict.

        Generates 5 categories of queries:
          1. Symptom research
          2. Medication safety
          3. Medication combinations (pairs)
          4. Diagnosis treatment advances
          5. Genetic variant updates
        """
        queries = []
        timeline = profile_data.get("clinical_timeline", {})

        # ── 1. Symptom-based queries ──────────────────────
        symptoms = timeline.get("symptoms", [])
        for symptom in symptoms:
            name = symptom.get("symptom_name", "")
            if not name:
                continue

            episodes = symptom.get("episodes", [])
            episode_count = len(episodes)

            # Only search for symptoms with enough data to be meaningful
            if episode_count < 2:
                continue

            # Core symptom research
            queries.append({
                "query": (
                    f'"{name}"[Title/Abstract] AND '
                    f'("etiology"[Subheading] OR "pathophysiology"[MeSH] '
                    f'OR "diagnosis"[Subheading]) AND '
                    f'(review[pt] OR systematic review[pt])'
                ),
                "relevance": (
                    f"Patient tracks {name} ({episode_count} episodes logged). "
                    f"Searching for recent research on causes and diagnosis."
                ),
                "severity": AlertSeverity.LOW,
                "category": CATEGORY_SYMPTOM,
            })

            # If the symptom has counter-evidence, search for that too
            counters = symptom.get("counter_definitions", [])
            for counter in counters:
                claim = counter.get("doctor_claim", "")
                archived = counter.get("archived", False)
                if claim and not archived:
                    queries.append({
                        "query": (
                            f'"{name}"[Title/Abstract] AND '
                            f'"{claim}"[Title/Abstract] AND '
                            f'("risk factors"[MeSH] OR "causality"[MeSH])'
                        ),
                        "relevance": (
                            f"Doctor attributes {name} to {claim}. "
                            f"Searching for evidence on this association."
                        ),
                        "severity": AlertSeverity.LOW,
                        "category": CATEGORY_SYMPTOM,
                    })

        # ── 2. Medication safety queries ──────────────────
        active_meds = []
        for med in timeline.get("medications", []):
            status = med.get("status", "")
            if isinstance(status, dict):
                status = status.get("value", "")
            status = str(status).lower()
            if status in ("active", "prn", "current"):
                med_name = med.get("name", "")
                if med_name:
                    active_meds.append(med_name)
                    queries.append({
                        "query": (
                            f'"{med_name}"[MeSH Terms] AND '
                            f'("drug-related side effects and adverse reactions"[MeSH] '
                            f'OR "safety"[Title])'
                        ),
                        "relevance": f"Patient is currently taking {med_name}.",
                        "severity": AlertSeverity.MODERATE,
                        "category": CATEGORY_MED_SAFETY,
                    })

        # ── 3. Medication combination queries ─────────────
        # Search for interaction research between pairs of active meds
        if len(active_meds) >= 2:
            # Limit to first 5 meds to avoid query explosion
            med_subset = active_meds[:5]
            for drug_a, drug_b in combinations(med_subset, 2):
                queries.append({
                    "query": (
                        f'"{drug_a}"[MeSH Terms] AND "{drug_b}"[MeSH Terms] '
                        f'AND ("drug interactions"[MeSH Terms] '
                        f'OR "polypharmacy"[MeSH Terms])'
                    ),
                    "relevance": (
                        f"Patient takes both {drug_a} and {drug_b}. "
                        f"Searching for interaction studies."
                    ),
                    "severity": AlertSeverity.MODERATE,
                    "category": CATEGORY_MED_COMBO,
                })

        # Also search for medication + condition combos
        diagnoses = timeline.get("diagnoses", [])
        active_dx_names = []
        for dx in diagnoses:
            dx_status = str(dx.get("status", "")).lower()
            if dx_status in ("active", "chronic"):
                dx_name = dx.get("name", "")
                if dx_name:
                    active_dx_names.append(dx_name)

        # For each active med × active condition (limit combos)
        for med_name in active_meds[:3]:
            for dx_name in active_dx_names[:3]:
                queries.append({
                    "query": (
                        f'"{med_name}"[MeSH Terms] AND '
                        f'"{dx_name}"[MeSH Terms] AND '
                        f'("efficacy"[Title/Abstract] OR "outcome"[Title/Abstract]) '
                        f'AND (clinical trial[pt] OR meta-analysis[pt])'
                    ),
                    "relevance": (
                        f"Patient takes {med_name} for {dx_name}. "
                        f"Searching for treatment efficacy updates."
                    ),
                    "severity": AlertSeverity.LOW,
                    "category": CATEGORY_MED_COMBO,
                })

        # ── 4. Diagnosis treatment queries ────────────────
        for dx_name in active_dx_names:
            queries.append({
                "query": (
                    f'"{dx_name}"[MeSH Terms] AND '
                    f'("therapy"[Subheading] OR "treatment"[Title]) AND '
                    f'(clinical trial[pt] OR meta-analysis[pt])'
                ),
                "relevance": f"Patient has active diagnosis: {dx_name}.",
                "severity": AlertSeverity.LOW,
                "category": CATEGORY_DIAGNOSIS,
            })

        # ── 5. Genetic variant queries (expanded) ─────────
        genetics = timeline.get("genetics", [])
        for variant in genetics:
            gene = variant.get("gene", "")
            variant_name = variant.get("variant", "")
            phenotype = variant.get("phenotype", "")

            if not gene:
                continue

            # Pharmacogenomic research (all variants, not just actionable)
            queries.append({
                "query": (
                    f'"{gene}"[Title] AND '
                    f'("pharmacogenomics"[MeSH Terms] OR '
                    f'"pharmacogenetics"[MeSH Terms])'
                ),
                "relevance": (
                    f"Patient has {gene} variant"
                    f"{' (' + variant_name + ')' if variant_name else ''}"
                    f"{' — ' + phenotype if phenotype else ''}."
                ),
                "severity": AlertSeverity.MODERATE,
                "category": CATEGORY_GENETICS,
            })

            # If we have the specific allele, search for that too
            if variant_name and "*" in variant_name:
                queries.append({
                    "query": (
                        f'"{gene}"[Title] AND "{variant_name}"[Title/Abstract]'
                    ),
                    "relevance": (
                        f"Searching for research on specific allele "
                        f"{gene} {variant_name}."
                    ),
                    "severity": AlertSeverity.MODERATE,
                    "category": CATEGORY_GENETICS,
                })

            # Gene × active medications
            for med_name in active_meds[:5]:
                queries.append({
                    "query": (
                        f'"{gene}"[Title/Abstract] AND '
                        f'"{med_name}"[MeSH Terms] AND '
                        f'"pharmacogenomics"[MeSH Terms]'
                    ),
                    "relevance": (
                        f"Patient has {gene} variant and takes {med_name}. "
                        f"Searching for gene-drug interaction updates."
                    ),
                    "severity": AlertSeverity.HIGH,
                    "category": CATEGORY_GENETICS,
                })

        logger.info("Built %d PubMed queries across 5 categories", len(queries))
        return queries

    # ── Gemini Relevance Scoring ───────────────────────────

    def _score_relevance(self, alerts: list[MonitoringAlert],
                         profile_data: dict) -> list[MonitoringAlert]:
        """
        Use Gemini to score alert relevance and filter noise.

        Each alert is scored 0.0-1.0 for clinical relevance to the
        specific patient. Alerts below 0.3 are dropped.

        Falls back to returning all alerts if Gemini is unavailable.
        """
        try:
            scored = self._gemini_score(alerts, profile_data)
            # Filter out low-relevance noise
            filtered = [a for a in scored if a.get("score", 1.0) >= 0.3]
            # Sort by score descending
            filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
            return [a["alert"] for a in filtered]
        except Exception as e:
            logger.warning("Gemini relevance scoring failed, returning "
                           "unscored results: %s", e)
            return alerts

    def _gemini_score(self, alerts: list[MonitoringAlert],
                      profile_data: dict) -> list[dict]:
        """Call Gemini to score alert relevance."""
        # Build a concise patient summary for context
        summary = self._build_patient_summary(profile_data)

        # Build alert summaries
        alert_items = []
        for i, alert in enumerate(alerts):
            alert_items.append({
                "index": i,
                "title": alert.title,
                "relevance_context": alert.relevance_explanation or "",
            })

        prompt = (
            "You are a clinical relevance assessor. Score each PubMed article "
            "for relevance to this specific patient (0.0 = irrelevant, "
            "1.0 = highly relevant).\n\n"
            f"PATIENT SUMMARY:\n{summary}\n\n"
            f"ARTICLES TO SCORE:\n{json.dumps(alert_items, indent=2)}\n\n"
            "Return ONLY a JSON array of objects with 'index' and 'score' "
            "fields. No explanation needed."
        )

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash:generateContent"
            f"?key={self._gemini_api_key}"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())

        text = (result.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", ""))

        # Parse the JSON response — strip markdown fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        scores = json.loads(text)
        score_map = {s["index"]: s["score"] for s in scores}

        results = []
        for i, alert in enumerate(alerts):
            results.append({
                "alert": alert,
                "score": score_map.get(i, 0.5),
            })

        return results

    def _build_patient_summary(self, profile_data: dict) -> str:
        """Build a concise patient summary for Gemini context."""
        parts = []
        timeline = profile_data.get("clinical_timeline", {})

        # Demographics
        demo = profile_data.get("demographics", {})
        if demo:
            age = demo.get("age", "")
            sex = demo.get("sex", "")
            if age or sex:
                parts.append(f"Demographics: {sex} {age}")

        # Diagnoses
        dx_names = []
        for dx in timeline.get("diagnoses", []):
            status = str(dx.get("status", "")).lower()
            if status in ("active", "chronic"):
                dx_names.append(dx.get("name", ""))
        if dx_names:
            parts.append(f"Active diagnoses: {', '.join(dx_names)}")

        # Medications
        med_names = []
        for med in timeline.get("medications", []):
            status = str(med.get("status", "")).lower()
            if status in ("active", "prn", "current"):
                med_names.append(med.get("name", ""))
        if med_names:
            parts.append(f"Active medications: {', '.join(med_names)}")

        # Symptoms
        symptom_names = []
        for sym in timeline.get("symptoms", []):
            name = sym.get("symptom_name", "")
            count = len(sym.get("episodes", []))
            if name:
                symptom_names.append(f"{name} ({count} episodes)")
        if symptom_names:
            parts.append(f"Tracked symptoms: {', '.join(symptom_names)}")

        # Genetics
        gene_info = []
        for g in timeline.get("genetics", []):
            gene = g.get("gene", "")
            phenotype = g.get("phenotype", "")
            if gene:
                gene_info.append(f"{gene} ({phenotype})" if phenotype else gene)
        if gene_info:
            parts.append(f"Genetic variants: {', '.join(gene_info)}")

        return "\n".join(parts) if parts else "No patient data available."
