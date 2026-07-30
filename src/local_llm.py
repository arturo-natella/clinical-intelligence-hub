"""
Shared local LLM helpers for Ollama-backed patient-record reasoning.

These utilities keep non-research assistant flows on-device and release
memory after each call so they fit the sequential model-loading rule.
"""

import gc
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("CIH-LocalLLM")

LOCAL_ASSISTANT_MODEL = (
    os.environ.get("MEDPREP_ASSISTANT_MODEL", "gpt-oss:20b").strip()
    or "gpt-oss:20b"
)


def release_local_model_memory():
    """Release Python and MPS memory after a local model call."""
    gc.collect()
    gc.collect()

    try:
        import torch

        if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
    except Exception:
        pass


def call_local_text_model(
    user_prompt: str,
    *,
    system_prompt: str = "",
    num_predict: int = 768,
    temperature: float = 0.2,
    model: str = None,
    json_mode: bool = False,
) -> Optional[str]:
    """Call a local Ollama model and unload it immediately after the response."""
    try:
        import ollama

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        kwargs = {
            "model": model or LOCAL_ASSISTANT_MODEL,
            "messages": messages,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
            "keep_alive": "0",
        }
        if json_mode:
            kwargs["format"] = "json"

        response = ollama.chat(**kwargs)
        text = response.get("message", {}).get("content", "").strip()
        if text:
            logger.info(
                "Local model response generated with %s",
                kwargs["model"],
            )
            return text

    except Exception as e:
        logger.warning(
            "Local model unavailable (model=%s, error_type=%s)",
            model or LOCAL_ASSISTANT_MODEL,
            type(e).__name__,
        )
    finally:
        release_local_model_memory()

    return None


def parse_json_object_from_text(text: str) -> Optional[dict]:
    """Extract the first JSON object from model text output."""
    if not text:
        return None

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(text[start:end + 1])
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None

    return None


def parse_json_array_from_text(text: str) -> Optional[list]:
    """Extract the first JSON array from model text output."""
    if not text:
        return None

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(text[start:end + 1])
        if isinstance(parsed, list):
            return parsed
    except Exception:
        return None

    return None
