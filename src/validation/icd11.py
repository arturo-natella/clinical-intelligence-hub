"""
Clinical Intelligence Hub — ICD-11 Disease Classification

Uses the WHO ICD-11 REST API to look up disease classification codes,
validate diagnoses, and get hierarchical disease categorization.

ICD-11 is the International Classification of Diseases (11th revision)
maintained by WHO. It's the global standard for diagnostic coding.

API: https://icd.who.int/icdapi (free, requires client ID + secret)
Fallback: https://icd.who.int/ct11/icd11_mms/en (public search, no auth)

Token endpoint: https://icdaccessmanagement.who.int/connect/token
"""

import logging
import time
import urllib.parse
from typing import Optional

from src.validation._http import api_get, api_post

logger = logging.getLogger("CIH-ICD11")

ICD11_BASE = "https://id.who.int/icd"
TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"

# Linear search (no auth required, publicly accessible)
ICD11_SEARCH = "https://id.who.int/icd/release/11/2024-01/mms/search"


class ICD11Client:
    """WHO ICD-11 disease classification lookup and validation."""

    def __init__(self, client_id: str = None, client_secret: str = None):
        """
        Args:
            client_id: WHO ICD API client ID (optional — search works without auth)
            client_secret: WHO ICD API client secret
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = None
        self._token_expires = 0

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search ICD-11 for a disease or condition.

        Returns matches with ICD-11 codes, titles, and category hierarchy.
        """
        params = {
            "q": query,
            "subtreeFilterUsesFoundationDescendants": "false",
            "includeKeywordResult": "false",
            "useFlexisearch": "true",
            "flatResults": "true",
            "highlightingEnabled": "false",
        }

        url = f"{ICD11_SEARCH}?{urllib.parse.urlencode(params)}"

        try:
            headers = {
                "Accept-Language": "en",
                "API-Version": "v2",
            }

            # Add auth token if available
            token = self._get_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"

            data = api_get(url, headers=headers)
            if not data:
                return []

            results = []
            for item in (data.get("destinationEntities") or [])[:limit]:
                code = item.get("theCode", "")
                title = item.get("title", "")
                # Clean HTML tags from title
                if "<" in title:
                    title = self._strip_html(title)

                results.append({
                    "icd11_code": code,
                    "title": title,
                    "foundation_uri": item.get("id", ""),
                    "chapter": item.get("chapter", ""),
                    "score": item.get("score", 0),
                    "source": "WHO ICD-11",
                })

            return results

        except Exception as e:
            logger.debug(f"ICD-11 search failed for '{query}': {e}")
            return []

    def validate_diagnosis(self, diagnosis: str) -> Optional[dict]:
        """
        Validate that a diagnosis name maps to a real ICD-11 code.

        Returns the best match, or None if nothing found.
        """
        results = self.search(diagnosis, limit=3)
        if not results:
            return None

        # Return the highest-scoring match
        return results[0]

    def get_code_details(self, code: str) -> Optional[dict]:
        """
        Get details for a specific ICD-11 code (e.g., '5A11' for Type 2 diabetes).
        """
        url = f"{ICD11_BASE}/release/11/2024-01/mms/codeinfo/{code}"

        try:
            headers = {
                "Accept-Language": "en",
                "API-Version": "v2",
            }

            token = self._get_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"

            data = api_get(url, headers=headers)
            if not data:
                return None

            stem_id = data.get("stemId", "")
            return {
                "icd11_code": code,
                "stem_id": stem_id,
                "source": "WHO ICD-11",
            }

        except Exception as e:
            logger.debug(f"ICD-11 code lookup failed for '{code}': {e}")
            return None

    def get_entity(self, entity_uri: str) -> Optional[dict]:
        """
        Get full entity details from a foundation or linearization URI.
        """
        try:
            headers = {
                "Accept-Language": "en",
                "API-Version": "v2",
            }

            token = self._get_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"

            data = api_get(entity_uri, headers=headers)
            if not data:
                return None

            title = data.get("title", {})
            if isinstance(title, dict):
                title = title.get("@value", "")

            definition = data.get("definition", {})
            if isinstance(definition, dict):
                definition = definition.get("@value", "")

            parents = []
            for p in data.get("parent", []):
                if isinstance(p, str):
                    parents.append(p)

            return {
                "uri": entity_uri,
                "title": title,
                "definition": definition or None,
                "code": data.get("code", ""),
                "coded_elsewhere": [
                    e.get("label", {}).get("@value", "")
                    for e in data.get("codedElsewhere", [])
                    if isinstance(e, dict)
                ],
                "parents": parents,
                "source": "WHO ICD-11",
            }

        except Exception as e:
            logger.debug(f"ICD-11 entity lookup failed: {e}")
            return None

    # ── OAuth Token ──────────────────────────────────────────

    def _get_token(self) -> Optional[str]:
        """Get OAuth token for authenticated API access."""
        if not self._client_id or not self._client_secret:
            return None

        # Reuse valid token
        if self._token and time.time() < self._token_expires:
            return self._token

        try:
            token_data = api_post(
                TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                    "scope": "icdapi_access",
                },
                timeout=10,
            )
            if not token_data:
                return None

            self._token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)
            self._token_expires = time.time() + expires_in - 60

            return self._token

        except Exception as e:
            logger.debug(f"ICD-11 token acquisition failed: {e}")
            return None

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from ICD-11 search results."""
        import re
        return re.sub(r"<[^>]+>", "", text)
