"""
Clinical Intelligence Hub — LOINC Terminology Validation

LOINC (Logical Observation Identifiers Names and Codes) is the universal
standard for identifying laboratory tests, clinical measurements, and
survey instruments. With over 99,000 terms, it is used by virtually every
hospital and laboratory system worldwide to uniquely identify what was
measured (e.g., "Hemoglobin A1c" = LOINC 4548-4).

Critical for normalizing lab results across providers — the same test
ordered at different hospitals will have the same LOINC code, enabling
apples-to-apples comparison of results over time and across institutions.

API: LOINC FHIR Terminology Service (https://fhir.loinc.org)
Auth: Basic auth with loinc.org username/password (optional — some
      endpoints work without authentication)
"""

import base64
import logging
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-LOINC")

LOINC_FHIR = "https://fhir.loinc.org"


class LOINCClient:
    """LOINC FHIR Terminology Service client for lab test identification."""

    def __init__(self, username: str = None, password: str = None):
        """
        Args:
            username: loinc.org account username (optional — some endpoints
                      work without authentication)
            password: loinc.org account password
        """
        self._auth_header = None
        if username and password:
            credentials = base64.b64encode(
                f"{username}:{password}".encode()
            ).decode()
            self._auth_header = f"Basic {credentials}"

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search LOINC for lab tests, measurements, or survey instruments.

        Uses ValueSet $expand with filter for broad text search.
        Returns matching LOINC codes with names and properties.
        """
        params = {
            "url": "http://loinc.org/vs",
            "filter": query,
            "count": str(limit),
        }
        url = f"{LOINC_FHIR}/ValueSet/$expand?{urllib.parse.urlencode(params)}"

        try:
            data = self._fhir_get(url)
            if not data:
                return []

            expansion = data.get("expansion", {})
            contains = expansion.get("contains", [])
            if not contains:
                return []

            results = []
            for item in contains[:limit]:
                result = {
                    "loinc_code": item.get("code", ""),
                    "long_name": item.get("display", ""),
                    "short_name": None,
                    "component": None,
                    "property": None,
                    "system": None,
                    "scale": None,
                    "source": "LOINC",
                }

                # Extract designation details if present
                for designation in item.get("designation", []):
                    use_code = (
                        designation.get("use", {}).get("code", "")
                    )
                    value = designation.get("value", "")
                    if use_code == "SHORTNAME":
                        result["short_name"] = value
                    elif use_code == "COMPONENT":
                        result["component"] = value

                results.append(result)

            return results

        except Exception as e:
            logger.debug(f"LOINC search failed for '{query}': {e}")
            return []

    def get_code(self, loinc_code: str) -> Optional[dict]:
        """
        Look up a specific LOINC code and return full details.

        Uses CodeSystem $lookup to retrieve all properties for a code.
        """
        params = {
            "system": "http://loinc.org",
            "code": loinc_code,
        }
        url = (
            f"{LOINC_FHIR}/CodeSystem/$lookup"
            f"?{urllib.parse.urlencode(params)}"
        )

        try:
            data = self._fhir_get(url)
            if not data:
                return None

            return self._parse_lookup_response(data, loinc_code)

        except Exception as e:
            logger.debug(f"LOINC code lookup failed for '{loinc_code}': {e}")
            return None

    def search_lab_test(self, test_name: str, limit: int = 10) -> list[dict]:
        """
        Search for a lab test by common name (e.g., "hemoglobin a1c",
        "glucose", "creatinine").

        Convenience wrapper around search() for lab-specific queries.
        """
        return self.search(test_name, limit=limit)

    def get_related_codes(self, loinc_code: str) -> list[dict]:
        """
        Find LOINC codes related to the given code.

        Looks up the code's component (the analyte being measured),
        then searches for other codes measuring the same thing.
        For example, given a serum glucose code, finds urine glucose,
        CSF glucose, etc.
        """
        # Get the source code details to extract component
        details = self.get_code(loinc_code)
        if not details:
            return []

        component = details.get("component")
        if not component:
            return []

        # Search for other codes with the same component
        related = self.search(component, limit=20)

        # Exclude the original code
        return [
            r for r in related
            if r.get("loinc_code") != loinc_code
        ]

    def validate_lab_test(self, test_name: str) -> Optional[dict]:
        """
        Check if a lab test name maps to a valid LOINC code.

        Returns the best match, or None if no reasonable match found.
        """
        results = self.search(test_name, limit=3)
        if not results:
            return None

        # Return the top match (FHIR server ranks by relevance)
        return results[0]

    def get_reference_ranges(self, loinc_code: str) -> Optional[dict]:
        """
        Retrieve reference/normal ranges for a LOINC code if available.

        The LOINC FHIR service may include example reference ranges
        in the code properties. Returns ranges by age/sex when present.

        Note: Reference ranges are institution-specific. LOINC provides
        general guidance, not definitive clinical ranges.
        """
        details = self.get_code(loinc_code)
        if not details:
            return None

        # Reference ranges may be in the properties or in a related
        # ObservationDefinition resource
        # Try fetching the ObservationDefinition if it exists
        url = (
            f"{LOINC_FHIR}/ObservationDefinition"
            f"?code={urllib.parse.quote(loinc_code)}"
        )

        try:
            data = self._fhir_get(url)
            if not data:
                return self._build_basic_range_info(details)

            entries = data.get("entry", [])
            if not entries:
                return self._build_basic_range_info(details)

            resource = entries[0].get("resource", {})
            ranges = []

            for qual in resource.get("qualifiedInterval", []):
                range_info = {
                    "category": qual.get("category", ""),
                    "context": (
                        qual.get("context", {}).get("text", "")
                    ),
                    "age_low": None,
                    "age_high": None,
                    "gender": qual.get("gender", ""),
                    "range_low": None,
                    "range_high": None,
                }

                age = qual.get("age", {})
                if age:
                    low = age.get("low", {})
                    high = age.get("high", {})
                    range_info["age_low"] = low.get("value")
                    range_info["age_high"] = high.get("value")

                interval_range = qual.get("range", {})
                if interval_range:
                    low = interval_range.get("low", {})
                    high = interval_range.get("high", {})
                    range_info["range_low"] = low.get("value")
                    range_info["range_high"] = high.get("value")
                    range_info["unit"] = (
                        low.get("unit") or high.get("unit")
                    )

                ranges.append(range_info)

            if not ranges:
                return self._build_basic_range_info(details)

            return {
                "loinc_code": loinc_code,
                "long_name": details.get("long_name", ""),
                "scale_type": details.get("scale_type"),
                "ranges": ranges,
                "source": "LOINC",
            }

        except Exception as e:
            logger.debug(
                f"LOINC reference range lookup failed for '{loinc_code}': {e}"
            )
            return self._build_basic_range_info(details)

    # -- FHIR Response Parsing -----------------------------------------

    def _parse_lookup_response(
        self, data: dict, loinc_code: str
    ) -> Optional[dict]:
        """
        Parse a FHIR CodeSystem/$lookup response.

        $lookup returns a Parameters resource with an array of parameter
        objects, each having a name and a valueString (or valueCoding, etc.).
        """
        parameters = data.get("parameter", [])
        if not parameters:
            return None

        result = {
            "loinc_code": loinc_code,
            "long_name": None,
            "short_name": None,
            "component": None,
            "property": None,
            "time_aspect": None,
            "system": None,
            "scale_type": None,
            "method": None,
            "class_name": None,
            "status": None,
            "source": "LOINC",
        }

        # Direct top-level parameters (display name, etc.)
        for param in parameters:
            name = param.get("name", "")
            value = (
                param.get("valueString")
                or param.get("valueCode")
                or param.get("valueBoolean")
            )

            if name == "display":
                result["long_name"] = value
            elif name == "name":
                result["long_name"] = result["long_name"] or value

            # LOINC properties come as nested "property" parameters
            # with sub-parameters for code and value
            if name == "property":
                self._extract_property(param, result)

        # If we didn't get a display name, the code may be invalid
        if not result["long_name"]:
            return None

        return result

    @staticmethod
    def _extract_property(param: dict, result: dict) -> None:
        """
        Extract a LOINC property from a nested FHIR parameter.

        FHIR $lookup nests properties as:
            { "name": "property",
              "part": [
                  {"name": "code", "valueCode": "COMPONENT"},
                  {"name": "value", "valueString": "Hemoglobin A1c"}
              ] }
        """
        parts = param.get("part", [])
        prop_code = None
        prop_value = None

        for part in parts:
            part_name = part.get("name", "")
            if part_name == "code":
                prop_code = (
                    part.get("valueCode")
                    or part.get("valueString")
                )
            elif part_name == "value":
                prop_value = (
                    part.get("valueString")
                    or part.get("valueCode")
                    or part.get("valueCoding", {}).get("display")
                )

        if not prop_code or prop_value is None:
            return

        # Map LOINC property codes to result fields
        prop_map = {
            "COMPONENT": "component",
            "PROPERTY": "property",
            "TIME_ASPCT": "time_aspect",
            "SYSTEM": "system",
            "SCALE_TYP": "scale_type",
            "METHOD_TYP": "method",
            "CLASS": "class_name",
            "STATUS": "status",
            "SHORTNAME": "short_name",
        }

        field = prop_map.get(prop_code)
        if field:
            result[field] = prop_value

    @staticmethod
    def _build_basic_range_info(details: dict) -> Optional[dict]:
        """
        Build minimal range info from code details when no
        ObservationDefinition is available.
        """
        if not details:
            return None

        scale = details.get("scale_type")
        if not scale:
            return None

        return {
            "loinc_code": details.get("loinc_code"),
            "long_name": details.get("long_name", ""),
            "scale_type": scale,
            "ranges": [],
            "note": (
                "No reference ranges available from LOINC. "
                "Reference ranges are institution-specific."
            ),
            "source": "LOINC",
        }

    # -- HTTP Helper ---------------------------------------------------

    def _fhir_get(self, url: str) -> Optional[dict]:
        """
        Make a GET request to the LOINC FHIR server.

        Adds Basic auth header if credentials were provided.
        Uses application/fhir+json Accept header.
        """
        headers = {}
        if self._auth_header:
            headers["Authorization"] = self._auth_header

        data = api_get(url, headers=headers, accept="application/fhir+json")

        if data is None:
            logger.debug(f"LOINC FHIR request returned no data: {url[:80]}")

        return data
