"""
Clinical Intelligence Hub — Community Insights (Reddit)

Searches patient communities on Reddit for anecdotal patterns that
match the patient's conditions and medications. Useful for:
  - Identifying side effects not yet in clinical databases
  - Finding management tips from other patients
  - Discovering patterns doctors and databases haven't caught

IMPORTANT: All outputs are clearly labeled as:
  "Unverified community report — NOT clinical data.
   For discussion with your doctor only."

These are NEVER presented as clinical data or medical advice.
They're signal — patterns worth discussing with a doctor.

Salvaged from old deep_research.py._check_community_discussions
with improvements: upvote threshold (>1000), Gemini cross-disciplinary
mapping for biological mechanism explanations.
"""

import json
import logging
from typing import Optional

from src.models import CommunityInsight

logger = logging.getLogger("CIH-Community")


class CommunityInsights:
    """
    Searches Reddit for patient community patterns.

    Results are clearly labeled as anecdotal and unverified.
    Uses Gemini to explain potential biological mechanisms
    behind community-reported patterns.
    """

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: Gemini API key for mechanism explanation (optional)
        """
        self._api_key = api_key
        self._gemini_model = None
        if api_key:
            self._setup_gemini()

    def search(self, medications: list, diagnoses: list,
               symptoms: list = None) -> list[CommunityInsight]:
        """
        Search Reddit for community patterns matching patient profile.

        Args:
            medications: List of medication names/dicts
            diagnoses: List of diagnosis names/dicts
            symptoms: Optional list of reported symptoms

        Returns:
            List of CommunityInsight (each labeled as unverified)
        """
        insights = []

        # Build search terms from profile
        search_terms = self._build_search_terms(medications, diagnoses, symptoms)

        if not search_terms:
            return []

        logger.info(f"Searching Reddit for {len(search_terms)} patient community queries")

        for query_info in search_terms:
            results = self._search_reddit(
                query=query_info["query"],
                subreddits=query_info["subreddits"],
            )

            for post in results:
                # Only include posts with significant community engagement
                if post.get("upvotes", 0) < 100:
                    continue

                insight = CommunityInsight(
                    subreddit=post.get("subreddit", "unknown"),
                    description=post.get("summary", ""),
                    upvote_count=post.get("upvotes", 0),
                    post_url=post.get("url"),
                    cross_disciplinary_context=None,
                )

                # Add Gemini mechanism explanation if available
                if self._gemini_model and insight.upvote_count >= 1000:
                    mechanism = self._explain_mechanism(
                        insight.description,
                        query_info.get("context", ""),
                    )
                    if mechanism:
                        insight.cross_disciplinary_context = mechanism

                insights.append(insight)

        logger.info(f"Found {len(insights)} community insights")
        return insights

    # ── Search Term Building ────────────────────────────────

    def _build_search_terms(self, medications: list, diagnoses: list,
                            symptoms: list = None) -> list[dict]:
        """Build Reddit search queries from patient profile."""
        terms = []

        # Medication experience searches
        for med in medications:
            name = med.get("name", "") if isinstance(med, dict) else getattr(med, "name", str(med))
            if not name:
                continue

            terms.append({
                "query": f"{name} side effects experience",
                "subreddits": self._subreddits_for_medication(name),
                "context": f"Patient is on {name}",
            })

        # Diagnosis community searches
        for dx in diagnoses:
            name = dx.get("name", "") if isinstance(dx, dict) else getattr(dx, "name", str(dx))
            if not name:
                continue

            terms.append({
                "query": f"{name} management tips treatment",
                "subreddits": self._subreddits_for_condition(name),
                "context": f"Patient has {name}",
            })

        # Cross-medication experience (polypharmacy)
        med_names = []
        for med in medications:
            name = med.get("name", "") if isinstance(med, dict) else getattr(med, "name", str(med))
            if name:
                med_names.append(name)

        if len(med_names) >= 2:
            combo = " and ".join(med_names[:3])
            terms.append({
                "query": f"{combo} together combination experience",
                "subreddits": ["AskDocs", "pharmacy", "medicine"],
                "context": f"Patient is on combination: {combo}",
            })

        return terms

    def _search_reddit(self, query: str, subreddits: list) -> list[dict]:
        """
        Search Reddit for posts matching the query.

        Uses Reddit's public JSON API (no auth required for read-only).
        Falls back gracefully if Reddit is unavailable.
        """
        import urllib.request
        import urllib.parse

        results = []

        for subreddit in subreddits[:3]:  # Limit to 3 subreddits per query
            try:
                # Reddit public JSON API
                encoded_query = urllib.parse.quote(query)
                url = (
                    f"https://www.reddit.com/r/{subreddit}/search.json"
                    f"?q={encoded_query}&sort=top&t=year&limit=5"
                )

                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "ClinicalIntelligenceHub/1.0"},
                )

                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode())

                posts = data.get("data", {}).get("children", [])
                for post in posts:
                    post_data = post.get("data", {})
                    upvotes = post_data.get("ups", 0)

                    results.append({
                        "subreddit": subreddit,
                        "title": post_data.get("title", ""),
                        "summary": (
                            post_data.get("title", "") + " — " +
                            (post_data.get("selftext", "")[:300] or "")
                        ),
                        "upvotes": upvotes,
                        "url": f"https://reddit.com{post_data.get('permalink', '')}",
                        "num_comments": post_data.get("num_comments", 0),
                    })

            except Exception as e:
                logger.debug(f"Reddit search failed for r/{subreddit}: {e}")
                continue

        return results

    # ── Mechanism Explanation ────────────────────────────────

    def _explain_mechanism(self, community_pattern: str,
                           patient_context: str) -> Optional[str]:
        """
        Use Gemini to explain potential biological mechanism behind
        a community-reported pattern.
        """
        if not self._gemini_model:
            return None

        prompt = f"""A patient community on Reddit reports the following pattern:
"{community_pattern}"

Patient context: {patient_context}

If there is a plausible biological or pharmacological mechanism that
could explain this community-reported pattern, explain it briefly
(2-3 sentences). Cite the relevant medical domain(s).

If there is NO plausible mechanism, respond with "No established mechanism."

Note: This is for educational purposes. The community report is unverified."""

        try:
            response = self._gemini_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 256,
                },
            )
            text = response.text.strip()
            if "no established mechanism" in text.lower():
                return None
            return text

        except Exception as e:
            logger.debug(f"Mechanism explanation failed: {e}")
            return None

    # ── Subreddit Mapping ───────────────────────────────────

    @staticmethod
    def _subreddits_for_medication(medication: str) -> list[str]:
        """Map medication to relevant subreddits."""
        med_lower = medication.lower()

        # Common medication → subreddit mappings
        if any(kw in med_lower for kw in ["metformin", "insulin", "glipizide"]):
            return ["diabetes", "diabetes_t2", "AskDocs"]
        elif any(kw in med_lower for kw in ["lisinopril", "metoprolol", "amlodipine", "losartan"]):
            return ["hypertension", "HeartHealth", "AskDocs"]
        elif any(kw in med_lower for kw in ["atorvastatin", "rosuvastatin", "simvastatin"]):
            return ["cholesterol", "HeartHealth", "AskDocs"]
        elif any(kw in med_lower for kw in ["levothyroxine", "synthroid"]):
            return ["Hypothyroidism", "thyroidhealth", "AskDocs"]
        elif any(kw in med_lower for kw in ["sertraline", "fluoxetine", "escitalopram", "lexapro"]):
            return ["antidepressants", "depression", "anxiety"]
        elif any(kw in med_lower for kw in ["gabapentin", "pregabalin"]):
            return ["ChronicPain", "Fibromyalgia", "AskDocs"]

        # Generic fallback
        return ["AskDocs", "pharmacy", "medicine"]

    @staticmethod
    def _subreddits_for_condition(condition: str) -> list[str]:
        """Map condition to relevant subreddits."""
        cond_lower = condition.lower()

        if "diabetes" in cond_lower:
            return ["diabetes", "diabetes_t2", "AskDocs"]
        elif "hypertension" in cond_lower or "blood pressure" in cond_lower:
            return ["hypertension", "HeartHealth", "AskDocs"]
        elif "anxiety" in cond_lower:
            return ["Anxiety", "mentalhealth", "AskDocs"]
        elif "depression" in cond_lower:
            return ["depression", "mentalhealth", "AskDocs"]
        elif "arthritis" in cond_lower:
            return ["rheumatoid", "Arthritis", "AskDocs"]
        elif "cancer" in cond_lower or "oncol" in cond_lower:
            return ["cancer", "AskDocs", "medical"]
        elif "heart" in cond_lower or "cardiac" in cond_lower:
            return ["HeartHealth", "AskDocs", "medical"]
        elif "thyroid" in cond_lower:
            return ["Hypothyroidism", "thyroidhealth", "AskDocs"]
        elif "asthma" in cond_lower or "copd" in cond_lower:
            return ["Asthma", "COPD", "AskDocs"]

        return ["AskDocs", "medical", "medicine"]

    # ── Setup ───────────────────────────────────────────────

    def _setup_gemini(self):
        """Initialize Gemini for mechanism explanation."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._gemini_model = genai.GenerativeModel("gemini-3.1-pro-preview")
        except Exception as e:
            logger.debug(f"Gemini mechanism explainer not available: {e}")
