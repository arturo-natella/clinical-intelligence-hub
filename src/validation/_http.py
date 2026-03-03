"""
Shared HTTP utilities for all validation API clients.

Handles SSL certificate verification using certifi (macOS Python
doesn't ship with CA certificates by default), consistent User-Agent,
and standard timeout/error handling.
"""

import json
import logging
import ssl
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger("CIH-HTTP")

# User-Agent that works with all medical APIs
USER_AGENT = "Mozilla/5.0 (compatible; ClinicalIntelligenceHub/1.0; +health)"

# Default timeout for all API calls (seconds)
DEFAULT_TIMEOUT = 15


def get_ssl_context() -> ssl.SSLContext:
    """
    Get an SSL context with proper CA certificates.

    macOS Python often doesn't have system CA certs configured,
    so we use certifi's CA bundle if available.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def api_get(
    url: str,
    headers: dict = None,
    timeout: int = DEFAULT_TIMEOUT,
    accept: str = "application/json",
) -> Optional[dict | list]:
    """
    Make a GET request and return parsed JSON.

    Handles SSL, User-Agent, timeouts, and HTTP errors consistently.
    Returns None on any failure (never raises).
    """
    all_headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
    }
    if headers:
        all_headers.update(headers)

    try:
        req = urllib.request.Request(url, headers=all_headers)
        ctx = get_ssl_context()

        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
            return json.loads(response.read().decode())

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        logger.debug(f"HTTP {e.code} for {url[:80]}: {e.reason}")
        return None
    except Exception as e:
        logger.debug(f"API call failed for {url[:80]}: {e}")
        return None


def api_post(
    url: str,
    data: dict = None,
    body: bytes = None,
    headers: dict = None,
    timeout: int = DEFAULT_TIMEOUT,
    content_type: str = "application/x-www-form-urlencoded",
) -> Optional[dict | list]:
    """
    Make a POST request and return parsed JSON.

    Used for OAuth token requests and similar.
    """
    all_headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": content_type,
    }
    if headers:
        all_headers.update(headers)

    if body is None and data:
        body = urllib.parse.urlencode(data).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=body, headers=all_headers)
        ctx = get_ssl_context()

        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
            return json.loads(response.read().decode())

    except urllib.error.HTTPError as e:
        logger.debug(f"POST HTTP {e.code} for {url[:80]}: {e.reason}")
        return None
    except Exception as e:
        logger.debug(f"POST failed for {url[:80]}: {e}")
        return None
