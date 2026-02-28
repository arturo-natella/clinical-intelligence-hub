"""
Clinical Intelligence Hub — Passes 3-4: Deep Research

Pass 3: Pattern Detection & Cross-Disciplinary Analysis
  - Cross-provider contradictions
  - Drug-drug / drug-gene interactions
  - Screening gaps per guidelines
  - Imaging change tracking
  - 29-specialty cross-disciplinary search
  - 7 adjacent domain analysis

Pass 4: Literature Search
  - PubMed / clinical guidelines
  - Pharmacogenomics databases
  - Clinical trial matching

Model: gemini-deep-research-pro-preview-12-2025
Fallback: gemini-3.1-pro-preview (if Deep Research unavailable)
"""

import json
import logging
from typing import Optional

from src.models import (
    AlertSeverity,
    ClinicalFlag,
    CrossDisciplinaryConnection,
    FindingCategory,
    LiteratureCitation,
)

logger = logging.getLogger("CIH-DeepResearch")

# Deep Research model ID
DEEP_RESEARCH_MODEL = "gemini-deep-research-pro-preview-12-2025"
FALLBACK_MODEL = "gemini-3.1-pro-preview"


class DeepResearch:
    """
    Passes 3-4: Deep Research for pattern detection and literature search.

    Uses Gemini Deep Research for comprehensive medical analysis,
    falling back to standard Gemini 3.1 Pro if Deep Research is unavailable.
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None
        self._deep_model = None
        self._fallback_model = None
        self._deep_available = False
        self._setup_client()

    def analyze(self, profile_summary: str,
                cross_disciplinary_queries: list[dict]) -> dict:
        """
        Run Pass 3 (patterns) and Pass 4 (literature) analysis.

        Args:
            profile_summary: PII-redacted patient profile summary
            cross_disciplinary_queries: Queries from CrossDisciplinaryEngine

        Returns:
            dict with:
              - flags: list of ClinicalFlag
              - connections: list of CrossDisciplinaryConnection
              - literature: list of LiteratureCitation
              - questions: list of str (questions for doctor)
        """
        results = {
            "flags": [],
            "connections": [],
            "literature": [],
            "questions": [],
        }

        if not self._client:
            logger.error("Gemini client not initialized")
            return results

        # Pass 3: Pattern Detection & Cross-Disciplinary
        logger.info("Pass 3: Running cross-disciplinary pattern analysis...")
        pass3_results = self._run_pass3(profile_summary, cross_disciplinary_queries)
        if pass3_results:
            results["flags"].extend(pass3_results.get("flags", []))
            results["connections"].extend(pass3_results.get("connections", []))
            results["questions"].extend(pass3_results.get("questions", []))

        # Pass 4: Literature Search
        logger.info("Pass 4: Running literature search...")
        pass4_results = self._run_pass4(profile_summary, results["connections"])
        if pass4_results:
            results["literature"].extend(pass4_results.get("literature", []))
            # Literature may generate additional questions
            results["questions"].extend(pass4_results.get("questions", []))

        logger.info(
            f"Deep Research complete: {len(results['flags'])} flags, "
            f"{len(results['connections'])} connections, "
            f"{len(results['literature'])} citations, "
            f"{len(results['questions'])} questions for doctor"
        )
        return results

    # ── Pass 3: Pattern Detection ───────────────────────────

    def _run_pass3(self, profile_summary: str,
                   queries: list[dict]) -> Optional[dict]:
        """
        Pass 3: Cross-disciplinary pattern detection.

        This is the core analytical pass — finds connections between
        conditions, labs, medications, and genetics across specialties.
        """
        from src.analysis.cross_disciplinary import CrossDisciplinaryEngine

        engine = CrossDisciplinaryEngine()
        prompt = engine.get_deep_research_prompt(queries, profile_summary)

        try:
            model = self._deep_model or self._fallback_model
            if not model:
                return None

            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 16384,
                    "response_mime_type": "application/json",
                },
            )

            raw_findings = json.loads(response.text)
            return self._parse_pass3_results(raw_findings)

        except json.JSONDecodeError as e:
            logger.warning(f"Pass 3 returned invalid JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Pass 3 analysis failed: {e}")
            return None

    def _parse_pass3_results(self, findings: list | dict) -> dict:
        """Parse Pass 3 raw JSON into structured results."""
        results = {"flags": [], "connections": [], "questions": []}

        # Handle both list and dict responses
        if isinstance(findings, dict):
            findings = findings.get("findings", [findings])

        for finding in findings:
            if not isinstance(finding, dict):
                continue

            # Create CrossDisciplinaryConnection
            specialties = finding.get("specialties", [])
            connection = finding.get("connection", "")
            evidence = finding.get("evidence", "")
            significance = finding.get("significance", "moderate")
            question = finding.get("question_for_doctor", "")

            if connection:
                severity = self._map_significance(significance)

                results["connections"].append(CrossDisciplinaryConnection(
                    title=connection[:200] if len(connection) > 200 else connection,
                    description=str(evidence),
                    specialties=specialties if isinstance(specialties, list) else [str(specialties)],
                    patient_data_points=[str(evidence)],
                    severity=severity,
                    question_for_doctor=question or None,
                ))

                # Also create a ClinicalFlag for high/critical findings
                if severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH):
                    results["flags"].append(ClinicalFlag(
                        category=FindingCategory.CROSS_DISCIPLINARY,
                        severity=severity,
                        title=connection[:100],
                        description=str(evidence),
                        specialties_involved=specialties if isinstance(specialties, list) else [],
                        source_pass="pass_3_deep_research",
                    ))

            if question:
                results["questions"].append(question)

        return results

    # ── Pass 4: Literature Search ───────────────────────────

    def _run_pass4(self, profile_summary: str,
                   connections: list) -> Optional[dict]:
        """
        Pass 4: Literature search for evidence supporting findings.
        """
        # Build literature search prompt from connections
        connection_summaries = []
        for conn in connections[:10]:  # Limit to top 10
            title = conn.title if hasattr(conn, 'title') else str(conn)
            connection_summaries.append(f"- {title}")

        connections_text = "\n".join(connection_summaries) if connection_summaries else "No specific connections to validate."

        prompt = f"""You are a medical literature researcher. Search for published
evidence supporting or refuting the following clinical connections
found in a patient's profile.

PATIENT CONTEXT (PII-redacted):
{profile_summary}

CONNECTIONS TO VALIDATE:
{connections_text}

For each connection, find:
1. Published studies (prioritize meta-analyses, RCTs, systematic reviews)
2. Clinical guideline recommendations
3. Pharmacogenomic evidence if applicable

For each citation, provide:
- title: Full paper title
- authors: First author et al.
- journal: Journal name
- year: Publication year
- doi: DOI if available
- relevance_summary: 1-2 sentences on how this relates to the patient

Also generate any additional questions the patient should ask their doctor
based on the literature findings.

Output as JSON with:
  "literature": [array of citation objects],
  "questions": [array of question strings]"""

        try:
            model = self._deep_model or self._fallback_model
            if not model:
                return None

            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 8192,
                    "response_mime_type": "application/json",
                },
            )

            raw = json.loads(response.text)
            return self._parse_pass4_results(raw)

        except json.JSONDecodeError as e:
            logger.warning(f"Pass 4 returned invalid JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Pass 4 literature search failed: {e}")
            return None

    def _parse_pass4_results(self, raw: dict) -> dict:
        """Parse Pass 4 raw JSON into LiteratureCitation models."""
        results = {"literature": [], "questions": []}

        for cite in raw.get("literature", []):
            if not isinstance(cite, dict):
                continue
            title = cite.get("title", "")
            if title:
                results["literature"].append(LiteratureCitation(
                    title=title,
                    authors=cite.get("authors"),
                    journal=cite.get("journal"),
                    year=cite.get("year"),
                    doi=cite.get("doi"),
                    pubmed_id=cite.get("pubmed_id"),
                    relevance_summary=cite.get("relevance_summary"),
                ))

        results["questions"] = [
            q for q in raw.get("questions", []) if isinstance(q, str)
        ]

        return results

    # ── Setup ───────────────────────────────────────────────

    def _setup_client(self):
        """Initialize Gemini clients (Deep Research + fallback)."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)
            self._client = genai

            # Try Deep Research model first
            try:
                self._deep_model = genai.GenerativeModel(DEEP_RESEARCH_MODEL)
                self._deep_available = True
                logger.info(f"Deep Research model initialized: {DEEP_RESEARCH_MODEL}")
            except Exception:
                logger.warning(
                    f"Deep Research model unavailable ({DEEP_RESEARCH_MODEL}). "
                    f"Falling back to {FALLBACK_MODEL}"
                )

            # Always set up fallback
            self._fallback_model = genai.GenerativeModel(FALLBACK_MODEL)

        except ImportError:
            logger.error(
                "google-generativeai not installed. "
                "Run: pip install google-generativeai"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _map_significance(significance: str) -> AlertSeverity:
        """Map text significance to AlertSeverity enum."""
        sig_lower = str(significance).lower()
        if sig_lower == "critical":
            return AlertSeverity.CRITICAL
        elif sig_lower == "high":
            return AlertSeverity.HIGH
        elif sig_lower == "moderate":
            return AlertSeverity.MODERATE
        elif sig_lower == "low":
            return AlertSeverity.LOW
        return AlertSeverity.INFO
