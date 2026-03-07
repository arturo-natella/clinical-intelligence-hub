"""
Automated environmental data staging.

The first pass focuses on sources that can be fetched reliably around a
patient's saved location and cached locally as JSON snapshots. Bulk EPA
and CDC datasets remain in the source registry and manifest, but are not
automatically mirrored yet.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.analysis.environmental_sources import (
    get_environmental_source_catalog,
    load_environmental_sync_settings,
    update_environmental_sync_settings,
    update_environmental_manifest_source,
)
from src.validation._http import USER_AGENT, get_ssl_context

logger = logging.getLogger("CIH-EnvironmentalSync")


STATE_NAME_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

PUBLIC_FILE_SOURCE_CONFIG: dict[str, dict[str, Any]] = {
    "atsdr_eji": {
        "seed_urls": [
            "https://www.atsdr.cdc.gov/place-health/php/eji/eji-data-download.html",
            "https://atsdr.cdc.gov/place-health/php/eji/eji-data-download.html",
        ],
        "page_prefixes": [
            "https://www.atsdr.cdc.gov/place-health/php/eji/",
            "https://atsdr.cdc.gov/place-health/php/eji/",
            "https://www.cdc.gov/place-health/php/eji/",
        ],
        "max_pages": 10,
        "max_files": 20,
    },
    "epa_echo": {
        "seed_urls": [
            "https://echo.epa.gov/tools/data-downloads",
        ],
        "page_prefixes": [
            "https://echo.epa.gov/tools/",
            "https://echo.epa.gov/",
        ],
        "max_pages": 12,
        "max_files": 20,
    },
    "epa_envirofacts": {
        "seed_urls": [
            "https://www.epa.gov/enviro/data-downloads",
        ],
        "page_prefixes": [
            "https://www.epa.gov/enviro/",
        ],
        "max_pages": 12,
        "max_files": 20,
    },
    "epa_envirofacts_additional": {
        "seed_urls": [
            "https://www.epa.gov/enviro/download-additional-envirofacts-datasets",
        ],
        "page_prefixes": [
            "https://www.epa.gov/enviro/",
        ],
        "max_pages": 10,
        "max_files": 20,
    },
    "epa_tri": {
        "seed_urls": [
            "https://www.epa.gov/toxics-release-inventory-tri-program/tri-data-and-tools",
            "https://www.epa.gov/toxics-release-inventory-tri-program/tri-basic-data-files-calendar-years-1987-present",
            "https://www.epa.gov/toxics-release-inventory-tri-program/tri-basic-plus-data-files-calendar-years-1987-present",
            "https://www.epa.gov/toxics-release-inventory-tri-program/custom-files-tri-data-users",
        ],
        "page_prefixes": [
            "https://www.epa.gov/toxics-release-inventory-tri-program/",
        ],
        "max_pages": 16,
        "max_files": 30,
    },
    "epa_cdr": {
        "seed_urls": [
            "https://www.epa.gov/chemical-data-reporting/access-chemical-data-reporting-data",
        ],
        "page_prefixes": [
            "https://www.epa.gov/chemical-data-reporting/",
        ],
        "max_pages": 10,
        "max_files": 20,
    },
}

DOWNLOADABLE_EXTENSIONS = (
    ".zip",
    ".csv",
    ".xlsx",
    ".xls",
    ".json",
    ".xml",
    ".kml",
    ".kmz",
    ".txt",
    ".tsv",
)


class EnvironmentalDataSync:
    """Fetch and stage environmental snapshots around a saved location."""

    AUTOMATED_SOURCE_IDS = (
        "nominatim_geocoder",
        "census_geocoder",
        "nws",
        "fema_openfema",
        "airnow",
        "epa_nutrient_pollution",
    )
    REFRESH_HOURS = {
        "nominatim_geocoder": 24 * 30,
        "census_geocoder": 24 * 30,
        "nws": 6,
        "fema_openfema": 24,
        "airnow": 6,
        "epa_nutrient_pollution": 24 * 30,
    }

    def __init__(self, data_dir: Path | str, api_keys: dict[str, Any] | None = None):
        self.data_dir = Path(data_dir)
        self.api_keys = api_keys or {}
        self.environmental_dir = self.data_dir / "environmental"
        self.raw_dir = self.environmental_dir / "raw"
        self.normalized_dir = self.environmental_dir / "normalized"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.normalized_dir.mkdir(parents=True, exist_ok=True)

    def sync_profile(
        self,
        profile_data: dict[str, Any],
        source_ids: list[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        catalog = get_environmental_source_catalog(self.data_dir)
        catalog_map = {item["id"]: item for item in catalog}
        if source_ids:
            target_ids = [source_id for source_id in source_ids if source_id in catalog_map]
        else:
            target_ids = [
                source_id for source_id in self.AUTOMATED_SOURCE_IDS
                if source_id in catalog_map
            ]

        location = self._get_location(profile_data)
        location_context = self._load_existing_location_context()
        if (
            location
            and location_context.get("original_location")
            and location_context.get("original_location", "").strip().lower() != location.strip().lower()
        ):
            location_context = {}
        results = []

        if "nominatim_geocoder" in target_ids:
            nominatim_result = self._sync_nominatim_geocoder(location, force=force)
            results.append(nominatim_result)
            if nominatim_result.get("location_context"):
                location_context = self._merge_location_context(
                    location_context,
                    nominatim_result["location_context"],
                )

        if "census_geocoder" in target_ids:
            census_result = self._sync_census_geocoder(location, location_context, force=force)
            results.append(census_result)
            if census_result.get("location_context"):
                location_context = self._merge_location_context(
                    location_context,
                    census_result["location_context"],
                )

        handlers = {
            "nws": self._sync_nws,
            "fema_openfema": self._sync_fema,
            "airnow": self._sync_airnow,
            "epa_nutrient_pollution": self._sync_epa_nutrient_pollution,
        }

        for source_id in target_ids:
            if source_id in {"nominatim_geocoder", "census_geocoder"}:
                continue

            source = catalog_map[source_id]
            handler = handlers.get(source_id)
            if handler:
                results.append(handler(source, location_context, force=force))
            else:
                results.append(self._record_deferred_source(source))

        success_count = sum(1 for item in results if item.get("status") == "downloaded")
        cached_count = sum(1 for item in results if item.get("status") == "cached")
        error_count = sum(1 for item in results if item.get("status") == "error")
        skipped_count = sum(1 for item in results if item.get("status") == "skipped")

        return {
            "synced_at": self._now(),
            "location": location,
            "location_context": location_context,
            "results": results,
            "summary": {
                "requested_sources": len(target_ids),
                "downloaded": success_count,
                "cached": cached_count,
                "errors": error_count,
                "skipped": skipped_count,
            },
        }

    def _sync_nominatim_geocoder(self, location: str, force: bool = False) -> dict[str, Any]:
        source_id = "nominatim_geocoder"
        if not location:
            return self._record_skip(source_id, "No saved location to geocode.")

        location_key = self._location_key({"original_location": location}, location)
        cached = self._get_cached_result(source_id, location_key, force=force)
        if cached:
            cached_context = self._load_json_path(cached.get("normalized_path"))
            return {
                "source_id": source_id,
                "status": "cached",
                "record_count": cached.get("record_count", 1),
                "local_path": cached.get("local_path", ""),
                "location_context": cached_context or {},
            }

        params = urllib.parse.urlencode({
            "q": location,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        })
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        headers = {
            "Accept": "application/json",
            "User-Agent": self._nws_user_agent(),
        }
        payload = self._fetch_json(url, headers=headers)
        if not payload:
            parsed = self._parse_location_text(location)
            if parsed:
                return self._record_skip(
                    source_id,
                    "Fallback geocoder returned no data; state/county text parsing only is available.",
                )
            return self._record_error(source_id, "Fallback geocoder returned no data.")

        match = payload[0] if isinstance(payload, list) and payload else {}
        location_context = self._build_location_context_from_nominatim(location, match)
        raw_bundle = self._write_json_snapshot(source_id, "latest.json", payload)
        normalized_bundle = self._write_json_snapshot(
            source_id,
            "location_context.json",
            location_context,
            normalized=True,
        )
        manifest_updates = {
            "downloaded": True,
            "last_checked": self._now(),
            "last_updated": self._now(),
            "local_path": raw_bundle["latest_path"],
            "history_dir": raw_bundle["history_dir"],
            "snapshot_count": raw_bundle["snapshot_count"],
            "normalized_path": normalized_bundle["latest_path"],
            "record_count": len(payload) if isinstance(payload, list) else 1,
            "coverage_notes": f"Resolved '{location}' to coordinates using fallback geocoding.",
            "location_key": location_key,
        }
        update_environmental_manifest_source(self.data_dir, source_id, manifest_updates)
        return {
            "source_id": source_id,
            "status": "downloaded",
            "record_count": manifest_updates["record_count"],
            "local_path": raw_bundle["latest_path"],
            "location_context": location_context,
        }

    def _sync_census_geocoder(
        self,
        location: str,
        location_context: dict[str, Any],
        force: bool = False,
    ) -> dict[str, Any]:
        source_id = "census_geocoder"
        if not location:
            return self._record_skip(source_id, "No saved location to geocode.")

        location_key = self._location_key(location_context, location)
        cached = self._get_cached_result(source_id, location_key, force=force)
        if cached:
            cached_context = self._load_json_path(cached.get("normalized_path"))
            return {
                "source_id": source_id,
                "status": "cached",
                "record_count": cached.get("record_count", 1),
                "local_path": cached.get("local_path", ""),
                "location_context": cached_context or location_context or {},
            }

        url = self._census_lookup_url(location, location_context)
        if not url:
            parsed = self._parse_location_text(location)
            if parsed:
                fallback_context = dict(location_context or {})
                fallback_context.update(parsed)
                normalized_bundle = self._write_json_snapshot(
                    source_id,
                    "location_context.json",
                    fallback_context,
                    normalized=True,
                )
                update_environmental_manifest_source(
                    self.data_dir,
                    source_id,
                    {
                        "last_checked": self._now(),
                        "normalized_path": normalized_bundle["latest_path"],
                        "coverage_notes": (
                            "Stored parsed state/county context from the saved location text. "
                            "Add a ZIP code or street address to unlock tract-level joins."
                        ),
                        "location_key": self._location_key(fallback_context, location),
                    },
                )
                return {
                    "source_id": source_id,
                    "status": "skipped",
                    "message": "Location text was parsed, but coordinates were not resolved.",
                    "location_context": fallback_context,
                }
            return self._record_error(source_id, "No usable Census lookup could be built from the saved location.")

        payload = self._fetch_json(url)
        if not payload:
            return self._record_error(source_id, "Census geocoder returned no data.")

        resolved_context, record_count = self._extract_census_context(location, location_context, payload)
        if not resolved_context:
            return self._record_error(source_id, f"No Census geocoder match for '{location}'.")

        raw_bundle = self._write_json_snapshot(source_id, "latest.json", payload)
        normalized_bundle = self._write_json_snapshot(
            source_id,
            "location_context.json",
            resolved_context,
            normalized=True,
        )

        update_environmental_manifest_source(
            self.data_dir,
            source_id,
            {
                "downloaded": True,
                "last_checked": self._now(),
                "last_updated": self._now(),
                "local_path": raw_bundle["latest_path"],
                "history_dir": raw_bundle["history_dir"],
                "snapshot_count": raw_bundle["snapshot_count"],
                "normalized_path": normalized_bundle["latest_path"],
                "record_count": record_count,
                "coverage_notes": f"Resolved '{location}' to county and tract context.",
                "location_key": self._location_key(resolved_context, location),
            },
        )
        return {
            "source_id": source_id,
            "status": "downloaded",
            "record_count": record_count,
            "local_path": raw_bundle["latest_path"],
            "location_context": resolved_context,
        }

    def _sync_nws(
        self,
        source: dict[str, Any],
        location_context: dict[str, Any],
        force: bool = False,
    ) -> dict[str, Any]:
        source_id = source["id"]
        lat = location_context.get("latitude")
        lon = location_context.get("longitude")
        if lat is None or lon is None:
            return self._record_skip(source_id, "No lat/lon available for NWS queries.")

        location_key = self._location_key(location_context, location_context.get("original_location", ""))
        cached = self._get_cached_result(source_id, location_key, force=force)
        if cached:
            return {
                "source_id": source_id,
                "status": "cached",
                "record_count": cached.get("record_count", 0),
                "local_path": cached.get("local_path", ""),
            }

        headers = {
            "Accept": "application/geo+json",
            "User-Agent": self._nws_user_agent(),
        }
        points_url = f"https://api.weather.gov/points/{lat},{lon}"
        alerts_url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
        points_payload = self._fetch_json(points_url, headers=headers)
        alerts_payload = self._fetch_json(alerts_url, headers=headers)
        if not points_payload and not alerts_payload:
            return self._record_error(source_id, "NWS returned no data.")

        payload = {
            "points": points_payload,
            "alerts": alerts_payload,
        }
        record_count = len((alerts_payload or {}).get("features", []) or [])
        raw_bundle = self._write_json_snapshot(source_id, "latest.json", payload)
        update_environmental_manifest_source(
            self.data_dir,
            source_id,
            {
                "downloaded": True,
                "last_checked": self._now(),
                "last_updated": self._now(),
                "local_path": raw_bundle["latest_path"],
                "history_dir": raw_bundle["history_dir"],
                "snapshot_count": raw_bundle["snapshot_count"],
                "record_count": record_count,
                "coverage_notes": "Stored point metadata and active alerts for the saved location.",
                "location_key": location_key,
            },
        )
        return {
            "source_id": source_id,
            "status": "downloaded",
            "record_count": record_count,
            "local_path": raw_bundle["latest_path"],
        }

    def _sync_fema(
        self,
        source: dict[str, Any],
        location_context: dict[str, Any],
        force: bool = False,
    ) -> dict[str, Any]:
        source_id = source["id"]
        state_abbr = location_context.get("state_abbr")
        if not state_abbr:
            return self._record_skip(source_id, "No state available for FEMA queries.")

        location_key = self._location_key(location_context, location_context.get("original_location", ""))
        cached = self._get_cached_result(source_id, location_key, force=force)
        if cached:
            return {
                "source_id": source_id,
                "status": "cached",
                "record_count": cached.get("record_count", 0),
                "local_path": cached.get("local_path", ""),
            }

        filter_expr = urllib.parse.quote(f"state eq '{state_abbr}'")
        url = (
            "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
            f"?$filter={filter_expr}&$top=250"
        )
        payload = self._fetch_json(url)
        if not payload:
            return self._record_error(source_id, "FEMA returned no declaration data.")

        declarations = payload.get("DisasterDeclarationsSummaries", []) if isinstance(payload, dict) else []
        raw_bundle = self._write_json_snapshot(source_id, "latest.json", payload)
        update_environmental_manifest_source(
            self.data_dir,
            source_id,
            {
                "downloaded": True,
                "last_checked": self._now(),
                "last_updated": self._now(),
                "local_path": raw_bundle["latest_path"],
                "history_dir": raw_bundle["history_dir"],
                "snapshot_count": raw_bundle["snapshot_count"],
                "record_count": len(declarations),
                "coverage_notes": f"Stored FEMA disaster declarations for {state_abbr}.",
                "location_key": location_key,
            },
        )
        return {
            "source_id": source_id,
            "status": "downloaded",
            "record_count": len(declarations),
            "local_path": raw_bundle["latest_path"],
        }

    def _sync_airnow(
        self,
        source: dict[str, Any],
        location_context: dict[str, Any],
        force: bool = False,
    ) -> dict[str, Any]:
        source_id = source["id"]
        api_key = self.api_keys.get("airnow")
        if not api_key:
            return self._record_skip(source_id, "AirNow API key is not configured.")

        lat = location_context.get("latitude")
        lon = location_context.get("longitude")
        if lat is None or lon is None:
            return self._record_skip(source_id, "No lat/lon available for AirNow queries.")

        location_key = self._location_key(location_context, location_context.get("original_location", ""))
        cached = self._get_cached_result(source_id, location_key, force=force)
        if cached:
            return {
                "source_id": source_id,
                "status": "cached",
                "record_count": cached.get("record_count", 0),
                "local_path": cached.get("local_path", ""),
            }

        params = urllib.parse.urlencode({
            "format": "application/json",
            "latitude": lat,
            "longitude": lon,
            "distance": 25,
            "API_KEY": api_key,
        })
        url = f"https://www.airnowapi.org/aq/observation/latLong/current/?{params}"
        payload = self._fetch_json(url)
        if payload is None:
            return self._record_error(source_id, "AirNow returned no current observations.")

        record_count = len(payload) if isinstance(payload, list) else 0
        raw_bundle = self._write_json_snapshot(source_id, "latest.json", payload)
        update_environmental_manifest_source(
            self.data_dir,
            source_id,
            {
                "downloaded": True,
                "last_checked": self._now(),
                "last_updated": self._now(),
                "local_path": raw_bundle["latest_path"],
                "history_dir": raw_bundle["history_dir"],
                "snapshot_count": raw_bundle["snapshot_count"],
                "record_count": record_count,
                "coverage_notes": "Stored current air-quality observations for the saved location.",
                "location_key": location_key,
            },
        )
        return {
            "source_id": source_id,
            "status": "downloaded",
            "record_count": record_count,
            "local_path": raw_bundle["latest_path"],
        }

    def _sync_epa_nutrient_pollution(
        self,
        source: dict[str, Any],
        location_context: dict[str, Any],
        force: bool = False,
    ) -> dict[str, Any]:
        source_id = source["id"]
        cached = self._get_cached_result(source_id, "", force=force)
        if cached:
            return {
                "source_id": source_id,
                "status": "cached",
                "record_count": cached.get("record_count", 0),
                "local_path": cached.get("local_path", ""),
            }

        seed_urls = [
            "https://www.epa.gov/nutrientpollution/nutrient-indicators-dataset",
            "https://www.epa.gov/nutrientpollution/nutrient-data",
        ]
        page_map: dict[str, dict[str, Any]] = {}
        resource_map: dict[str, dict[str, Any]] = {}
        queued = list(seed_urls)
        visited: set[str] = set()

        while queued and len(visited) < 20:
            page_url = queued.pop(0)
            if page_url in visited:
                continue
            visited.add(page_url)

            body = self._fetch_text(page_url)
            if not body:
                continue

            page_links = self._extract_html_links(body, page_url)
            xlsx_links = [link for link in page_links if link.lower().endswith(".xlsx")]
            summary = self._extract_page_summary(body)
            title = self._extract_html_title(body) or page_url

            page_map[page_url] = {
                "title": title,
                "url": page_url,
                "summary": summary,
                "xlsx_links": xlsx_links,
            }

            for link in page_links:
                if self._should_follow_nutrient_link(link, visited, queued):
                    queued.append(link)

            for xlsx_url in xlsx_links:
                if xlsx_url in resource_map:
                    continue
                binary = self._fetch_bytes(xlsx_url)
                if not binary:
                    continue
                file_info = self._write_binary_resource(source_id, xlsx_url, binary)
                resource_map[xlsx_url] = {
                    "url": xlsx_url,
                    "filename": file_info["filename"],
                    "local_path": file_info["path"],
                    "size_bytes": file_info["size_bytes"],
                }

        if not page_map:
            return self._record_skip(
                source_id,
                "EPA nutrient pollution pages were unavailable during this sync window.",
            )

        pages = sorted(page_map.values(), key=lambda item: item["title"].lower())
        resources = sorted(resource_map.values(), key=lambda item: item["filename"].lower())
        normalized_payload = {
            "page_count": len(pages),
            "resource_count": len(resources),
            "pages": pages,
            "resources": resources,
        }
        raw_bundle = self._write_json_snapshot(source_id, "latest.json", normalized_payload)
        normalized_bundle = self._write_json_snapshot(
            source_id,
            "normalized_summary.json",
            normalized_payload,
            normalized=True,
        )
        update_environmental_manifest_source(
            self.data_dir,
            source_id,
            {
                "downloaded": True,
                "last_checked": self._now(),
                "last_updated": self._now(),
                "local_path": raw_bundle["latest_path"],
                "history_dir": raw_bundle["history_dir"],
                "snapshot_count": raw_bundle["snapshot_count"],
                "normalized_path": normalized_bundle["latest_path"],
                "record_count": len(resources) or len(pages),
                "coverage_notes": (
                    f"Staged {len(resources)} EPA nutrient-pollution table files "
                    f"across {len(pages)} official nutrient pages."
                ),
            },
        )
        return {
            "source_id": source_id,
            "status": "downloaded",
            "record_count": len(resources) or len(pages),
            "local_path": raw_bundle["latest_path"],
        }

    def _record_deferred_source(self, source: dict[str, Any]) -> dict[str, Any]:
        source_id = source["id"]
        note = "Automated staging for this source is not implemented yet."
        update_environmental_manifest_source(
            self.data_dir,
            source_id,
            {
                "last_checked": self._now(),
                "coverage_notes": note,
            },
        )
        return {
            "source_id": source_id,
            "status": "skipped",
            "message": note,
        }

    def _record_skip(self, source_id: str, message: str) -> dict[str, Any]:
        update_environmental_manifest_source(
            self.data_dir,
            source_id,
            {
                "last_checked": self._now(),
                "coverage_notes": message,
            },
        )
        return {
            "source_id": source_id,
            "status": "skipped",
            "message": message,
        }

    def _record_error(self, source_id: str, message: str) -> dict[str, Any]:
        update_environmental_manifest_source(
            self.data_dir,
            source_id,
            {
                "last_checked": self._now(),
                "coverage_notes": message,
            },
        )
        return {
            "source_id": source_id,
            "status": "error",
            "message": message,
        }

    def _load_existing_location_context(self) -> dict[str, Any]:
        for source_id in ("census_geocoder", "nominatim_geocoder"):
            context = self._load_json_path(
                str(self.normalized_dir / source_id / "location_context.json")
            )
            if context:
                return context
        return {}

    def _census_lookup_url(self, location: str, location_context: dict[str, Any]) -> str:
        lat = location_context.get("latitude")
        lon = location_context.get("longitude")
        if lat is not None and lon is not None:
            return (
                "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
                f"?x={lon}&y={lat}&benchmark=Public_AR_Current&vintage=Current_Current&format=json"
            )

        encoded_location = urllib.parse.quote(location)
        return (
            "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
            f"?address={encoded_location}&benchmark=Public_AR_Current&vintage=Current_Current&format=json"
        )

    def _extract_census_context(
        self,
        original_location: str,
        existing_context: dict[str, Any],
        payload: Any,
    ) -> tuple[dict[str, Any], int]:
        if not isinstance(payload, dict):
            return {}, 0

        result = payload.get("result", {}) or {}
        geographies = result.get("geographies", {}) or {}
        if geographies:
            return self._build_location_context_from_geographies(
                original_location,
                existing_context,
                geographies,
            ), sum(
                len(values) for values in geographies.values()
                if isinstance(values, list)
            )

        address_matches = result.get("addressMatches", []) or []
        if address_matches:
            match = address_matches[0]
            return self._build_location_context_from_address_match(original_location, match), len(address_matches)

        return {}, 0

    def _build_location_context_from_address_match(
        self,
        original_location: str,
        match: dict[str, Any],
    ) -> dict[str, Any]:
        coordinates = match.get("coordinates", {}) if isinstance(match, dict) else {}
        geographies = match.get("geographies", {}) if isinstance(match, dict) else {}
        context = self._build_location_context_from_geographies(original_location, {}, geographies)
        context.update({
            "matched_address": match.get("matchedAddress", ""),
            "latitude": coordinates.get("y", context.get("latitude")),
            "longitude": coordinates.get("x", context.get("longitude")),
        })
        return context

    def _build_location_context_from_geographies(
        self,
        original_location: str,
        existing_context: dict[str, Any],
        geographies: dict[str, Any],
    ) -> dict[str, Any]:
        counties = geographies.get("Counties", []) if isinstance(geographies, dict) else []
        tracts = geographies.get("Census Tracts", []) if isinstance(geographies, dict) else []
        states = geographies.get("States", []) if isinstance(geographies, dict) else []
        county = counties[0] if counties else {}
        tract = tracts[0] if tracts else {}
        state = states[0] if states else {}

        state_name = (
            state.get("NAME")
            or existing_context.get("state_name")
            or self._parse_location_text(original_location).get("state_name", "")
        )
        state_abbr = (
            state.get("STUSAB")
            or existing_context.get("state_abbr")
            or self._state_abbr_from_context(state_name, original_location)
        )
        county_name = county.get("NAME") or county.get("BASENAME") or existing_context.get("county_name", "")

        return {
            "original_location": original_location,
            "matched_address": existing_context.get("matched_address", original_location),
            "latitude": existing_context.get("latitude"),
            "longitude": existing_context.get("longitude"),
            "county_name": county_name,
            "county_fips": county.get("GEOID", existing_context.get("county_fips", "")),
            "tract_geoid": tract.get("GEOID", existing_context.get("tract_geoid", "")),
            "state_name": state_name,
            "state_abbr": state_abbr,
        }

    def _build_location_context_from_nominatim(
        self,
        original_location: str,
        match: dict[str, Any],
    ) -> dict[str, Any]:
        address = match.get("address", {}) if isinstance(match, dict) else {}
        state_name = address.get("state", "")
        state_abbr = self._state_abbr_from_context(state_name, original_location)
        county_name = (
            address.get("county")
            or address.get("state_district")
            or ""
        )
        return {
            "original_location": original_location,
            "matched_address": match.get("display_name", ""),
            "latitude": self._to_float(match.get("lat")),
            "longitude": self._to_float(match.get("lon")),
            "county_name": county_name,
            "county_fips": "",
            "tract_geoid": "",
            "state_name": state_name,
            "state_abbr": state_abbr,
        }

    def _parse_location_text(self, location: str) -> dict[str, Any]:
        text = (location or "").strip()
        if not text:
            return {}

        parts = [part.strip() for part in text.split(",") if part.strip()]
        state_token = parts[-1] if parts else text
        county_name = ""
        if len(parts) >= 2 and "county" in parts[-2].lower():
            county_name = parts[-2]

        state_abbr = self._state_abbr_from_context("", state_token)
        state_name = self._state_name_from_abbr(state_abbr) if state_abbr else ""
        if not state_name and state_token:
            lowered = state_token.lower()
            if lowered in STATE_NAME_TO_ABBR:
                state_name = lowered.title()
                state_abbr = STATE_NAME_TO_ABBR[lowered]

        return {
            "original_location": text,
            "matched_address": text,
            "latitude": None,
            "longitude": None,
            "county_name": county_name,
            "county_fips": "",
            "tract_geoid": "",
            "state_name": state_name,
            "state_abbr": state_abbr,
        }

    def _get_cached_result(
        self,
        source_id: str,
        location_key: str,
        force: bool = False,
    ) -> dict[str, Any] | None:
        if force:
            return None

        entry = self._manifest_entry(source_id)
        if not entry.get("downloaded"):
            return None
        if not entry.get("local_path"):
            return None
        if location_key and entry.get("location_key") and entry.get("location_key") != location_key:
            return None
        if not self._is_entry_fresh(source_id, entry):
            return None
        if not Path(entry["local_path"]).exists():
            return None
        return entry

    def _manifest_entry(self, source_id: str) -> dict[str, Any]:
        manifest_path = self.environmental_dir / "source_manifest.json"
        if not manifest_path.exists():
            return {}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return (manifest.get("sources", {}) or {}).get(source_id, {}) or {}

    def _is_entry_fresh(self, source_id: str, entry: dict[str, Any]) -> bool:
        refresh_hours = self.REFRESH_HOURS.get(source_id)
        if refresh_hours is None:
            return False
        last_updated = entry.get("last_updated")
        if not last_updated:
            return False
        parsed = self._parse_datetime(last_updated)
        if not parsed:
            return False
        return datetime.now(timezone.utc) - parsed < timedelta(hours=refresh_hours)

    def _location_key(self, location_context: dict[str, Any], raw_location: str) -> str:
        if not isinstance(location_context, dict):
            return (raw_location or "").strip().lower()
        parts = [
            str(location_context.get("county_fips") or "").strip(),
            str(location_context.get("tract_geoid") or "").strip(),
            str(location_context.get("state_abbr") or "").strip(),
            str(location_context.get("original_location") or raw_location or "").strip().lower(),
        ]
        return "|".join(parts)

    def _load_json_path(self, path_str: str | None) -> dict[str, Any] | list[Any] | None:
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _merge_location_context(
        self,
        base: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(base or {})
        for key, value in (incoming or {}).items():
            if value in (None, "", []):
                continue
            merged[key] = value
        return merged

    def _extract_html_links(self, body: str, base_url: str) -> list[str]:
        links = []
        for match in re.finditer(r'href=["\']([^"\']+)["\']', body, re.IGNORECASE):
            href = html.unescape(match.group(1).strip())
            if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
                continue
            links.append(urllib.parse.urljoin(base_url, href))
        return list(dict.fromkeys(links))

    def _extract_html_title(self, body: str) -> str:
        match = re.search(r"<title>\s*(.*?)\s*</title>", body, re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        title = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()
        return title

    def _extract_page_summary(self, body: str) -> str:
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", body, re.IGNORECASE | re.DOTALL)
        for paragraph in paragraphs:
            text = re.sub(r"<[^>]+>", " ", paragraph)
            text = re.sub(r"\s+", " ", html.unescape(text)).strip()
            if len(text) >= 50:
                return text
        return ""

    def _should_follow_nutrient_link(
        self,
        url: str,
        visited: set[str],
        queued: list[str],
    ) -> bool:
        if url in visited or url in queued:
            return False
        if not url.startswith("https://www.epa.gov/"):
            return False
        if "/nutrientpollution/" not in url and "/nutrient-policy-data/" not in url:
            return False
        if url.lower().endswith((".xlsx", ".xls", ".zip", ".csv", ".pdf")):
            return False
        return True

    def _state_abbr_from_context(self, state_name: str, original_location: str) -> str:
        if state_name:
            abbr = STATE_NAME_TO_ABBR.get(state_name.lower())
            if abbr:
                return abbr

        lowered = (original_location or "").strip().lower()
        if lowered in STATE_NAME_TO_ABBR:
            return STATE_NAME_TO_ABBR[lowered]

        match = re.search(r",\s*([A-Z]{2})(?:\b|$)", original_location or "")
        if match:
            return match.group(1).upper()
        return ""

    def _state_name_from_abbr(self, abbr: str) -> str:
        upper = (abbr or "").upper()
        for state_name, state_abbr in STATE_NAME_TO_ABBR.items():
            if state_abbr == upper:
                return state_name
        return ""

    def _fetch_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        all_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if headers:
            all_headers.update(headers)

        try:
            request = urllib.request.Request(url, headers=all_headers)
            with urllib.request.urlopen(
                request,
                timeout=30,
                context=get_ssl_context(),
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("Environmental sync fetch failed for %s: %s", url, exc)
            return None

    def _fetch_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        body = self._fetch_bytes(url, headers=headers)
        if body is None:
            return ""
        return body.decode("utf-8", errors="replace")

    def _fetch_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes | None:
        all_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        }
        if headers:
            all_headers.update(headers)

        try:
            request = urllib.request.Request(url, headers=all_headers)
            with urllib.request.urlopen(
                request,
                timeout=30,
                context=get_ssl_context(),
            ) as response:
                return response.read()
        except Exception as exc:
            logger.warning("Environmental sync fetch failed for %s: %s", url, exc)
            return None

    def _write_json_snapshot(
        self,
        source_id: str,
        filename: str,
        payload: Any,
        normalized: bool = False,
    ) -> dict[str, Any]:
        root = self.normalized_dir if normalized else self.raw_dir
        source_dir = root / source_id
        source_dir.mkdir(parents=True, exist_ok=True)
        latest_path = source_dir / filename
        latest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

        timestamp_name = f"{self._snapshot_stamp()}_{filename}"
        snapshot_path = source_dir / timestamp_name
        snapshot_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        snapshot_count = len([item for item in source_dir.glob("*.json") if item.name != filename])
        return {
            "latest_path": str(latest_path),
            "snapshot_path": str(snapshot_path),
            "history_dir": str(source_dir),
            "snapshot_count": snapshot_count,
        }

    def _write_binary_resource(
        self,
        source_id: str,
        url: str,
        payload: bytes,
    ) -> dict[str, Any]:
        source_dir = self.raw_dir / source_id / "files"
        source_dir.mkdir(parents=True, exist_ok=True)

        parsed = urllib.parse.urlparse(url)
        basename = Path(parsed.path).name or "resource.bin"
        safe_basename = re.sub(r"[^A-Za-z0-9._-]+", "_", basename)
        path = source_dir / safe_basename
        path.write_bytes(payload)
        return {
            "filename": safe_basename,
            "path": str(path),
            "size_bytes": len(payload),
        }

    def _get_location(self, profile_data: dict[str, Any]) -> str:
        demographics = profile_data.get("demographics", {}) if isinstance(profile_data, dict) else {}
        return (demographics.get("location") or "").strip()

    def _nws_user_agent(self) -> str:
        contact = (self.api_keys.get("nws_contact") or "").strip()
        if contact:
            return f"ClinicalIntelligenceHub/1.0 ({contact})"
        return "ClinicalIntelligenceHub/1.0"

    def _snapshot_stamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def _parse_datetime(self, value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _to_float(self, value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class EnvironmentalAutoSyncWorker:
    """Background worker that keeps environmental snapshots current."""

    def __init__(
        self,
        data_dir: Path | str,
        get_profile_data,
        get_api_keys,
        is_ready,
        wake_interval_seconds: int = 300,
    ):
        self.data_dir = Path(data_dir)
        self.get_profile_data = get_profile_data
        self.get_api_keys = get_api_keys
        self.is_ready = is_ready
        self.wake_interval_seconds = wake_interval_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._run_lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._loop,
            name="environmental-auto-sync",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def trigger_now(self, force: bool = False) -> dict[str, Any] | None:
        return self._run_once(force=force)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._run_once(force=False)
            except Exception as exc:
                logger.error("Environmental auto-sync loop failed: %s", exc)
            self._stop_event.wait(self.wake_interval_seconds)

    def _run_once(self, force: bool = False) -> dict[str, Any] | None:
        settings = load_environmental_sync_settings(self.data_dir)
        if not settings.get("enabled"):
            return None
        if not force and not self._is_due(settings):
            return None
        if not self.is_ready():
            return None
        if not self._run_lock.acquire(blocking=False):
            return None

        try:
            profile_data = self.get_profile_data() or {}
            api_keys = self.get_api_keys() or {}
            source_ids = settings.get("source_ids") or list(EnvironmentalDataSync.AUTOMATED_SOURCE_IDS)
            syncer = EnvironmentalDataSync(self.data_dir, api_keys=api_keys)
            result = syncer.sync_profile(profile_data, source_ids=source_ids, force=force)
            synced_at = result.get("synced_at", datetime.now(timezone.utc).isoformat())
            summary = result.get("summary", {}) or {}
            status = "ok" if not summary.get("errors") else "error"
            update_environmental_sync_settings(
                self.data_dir,
                {
                    "last_run_at": synced_at,
                    "next_run_at": self._next_run_at(settings.get("interval_hours", 24), synced_at),
                    "last_status": status,
                    "last_error": "" if status == "ok" else "One or more environmental sources failed during sync.",
                    "last_summary": summary,
                },
            )
            return result
        except Exception as exc:
            now = datetime.now(timezone.utc).isoformat()
            update_environmental_sync_settings(
                self.data_dir,
                {
                    "last_run_at": now,
                    "next_run_at": self._next_run_at(settings.get("interval_hours", 24), now),
                    "last_status": "error",
                    "last_error": str(exc),
                },
            )
            logger.error("Environmental auto-sync run failed: %s", exc)
            return None
        finally:
            self._run_lock.release()

    def _is_due(self, settings: dict[str, Any]) -> bool:
        next_run_at = self._parse_datetime(settings.get("next_run_at", ""))
        if next_run_at is None:
            return True
        return datetime.now(timezone.utc) >= next_run_at

    def _next_run_at(self, interval_hours: int, synced_at: str) -> str:
        base = self._parse_datetime(synced_at) or datetime.now(timezone.utc)
        hours = max(1, int(interval_hours or 24))
        return (base + timedelta(hours=hours)).isoformat()

    def _parse_datetime(self, value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync environmental data snapshots for MedPrep.")
    parser.add_argument("--data-dir", default="data", help="Base MedPrep data directory")
    parser.add_argument("--location", default="", help="Location string to sync without a full profile")
    parser.add_argument("--airnow-key", default="", help="Optional AirNow API key")
    parser.add_argument("--nws-contact", default="", help="Optional NWS contact email")
    parser.add_argument("--source", action="append", dest="sources", help="Specific source id(s) to sync")
    parser.add_argument("--force", action="store_true", help="Ignore freshness windows and fetch again")
    args = parser.parse_args()

    profile = {}
    if args.location:
        profile = {"demographics": {"location": args.location}}

    syncer = EnvironmentalDataSync(
        data_dir=Path(args.data_dir),
        api_keys={
            "airnow": args.airnow_key,
            "nws_contact": args.nws_contact,
        },
    )
    result = syncer.sync_profile(profile, source_ids=args.sources, force=args.force)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
