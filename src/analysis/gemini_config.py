"""Shared configuration for every paid Gemini cloud call."""

from typing import Optional


# Keep one model ID for extraction, cross-disciplinary analysis, literature
# synthesis, and community mechanism explanations. Centralizing this prevents
# an expensive Pro/agent model from being reintroduced in only one pass.
GEMINI_MODEL_ID = "gemini-3-flash-preview"


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
    return client.models.generate_content(
        model=GEMINI_MODEL_ID,
        contents=prompt,
        config=config,
    )
