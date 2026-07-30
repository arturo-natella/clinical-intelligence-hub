"""Shared configuration for every paid Gemini cloud call."""

import os
import threading
import time
from typing import Optional


# Keep one model ID for extraction, cross-disciplinary analysis, literature
# synthesis, and community mechanism explanations. Centralizing this prevents
# an expensive Pro/agent model from being reintroduced in only one pass.
GEMINI_MODEL_ID = "gemini-3-flash-preview"

_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0


def _float_env(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _is_retryable(error: Exception) -> bool:
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    error_type = type(error).__name__.lower()
    return any(token in error_type for token in (
        "timeout", "connection", "resourceexhausted", "serviceunavailable",
        "toomanyrequests",
    ))


def create_client(api_key: str):
    """Create the supported Google Gen AI SDK client."""
    from google import genai

    return genai.Client(api_key=api_key)


def generate_content(
    client,
    prompt: str,
    *,
    temperature: float,
    max_output_tokens: int,
    response_mime_type: Optional[str] = None,
):
    """Generate content with the centrally approved Gemini model."""
    from google.genai import types

    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type=response_mime_type,
    )
    min_interval = _float_env("MEDPREP_GEMINI_MIN_INTERVAL_SECONDS", 0.25)
    backoff = _float_env("MEDPREP_GEMINI_RETRY_BACKOFF_SECONDS", 1.0)
    max_attempts = 3

    global _LAST_REQUEST_AT
    for attempt in range(max_attempts):
        try:
            with _REQUEST_LOCK:
                elapsed = time.monotonic() - _LAST_REQUEST_AT
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                try:
                    return client.models.generate_content(
                        model=GEMINI_MODEL_ID,
                        contents=prompt,
                        config=config,
                    )
                finally:
                    _LAST_REQUEST_AT = time.monotonic()
        except Exception as error:
            if attempt == max_attempts - 1 or not _is_retryable(error):
                raise
            time.sleep(backoff * (2 ** attempt))

    raise RuntimeError("Gemini request retry loop exited unexpectedly")
