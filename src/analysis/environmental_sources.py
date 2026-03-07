"""
Environmental source catalog and local manifest helpers.

This module keeps the environmental data surface explicit so the UI can
show what MedPrep currently considers, what is planned, and which
datasets have actually been staged locally.
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("CIH-EnvironmentalSources")


ENVIRONMENTAL_SOURCE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "medprep_regional_library",
        "name": "MedPrep Regional Risk Library",
        "provider": "MedPrep",
        "category": "clinical-context",
        "layer": "implemented",
        "time_horizon": "historical-context",
        "geography": "state / region",
        "cadence": "versioned with app updates",
        "auth": "No key required",
        "endpoint": "local rules",
        "purpose": "Maps broad regional exposures and endemic patterns to the patient's conditions, symptoms, and labs.",
        "status": "active-now",
    },
    {
        "id": "airnow",
        "name": "EPA AirNow",
        "provider": "EPA / AirNow",
        "category": "air-quality",
        "layer": "planned-live",
        "time_horizon": "current + short-range",
        "geography": "lat/lon / ZIP / county",
        "cadence": "real-time and forecast",
        "auth": "API key required",
        "endpoint": "https://docs.airnowapi.org/",
        "purpose": "Current AQI, PM2.5, ozone, and smoke-related exposure context.",
        "status": "planned",
    },
    {
        "id": "nws",
        "name": "NOAA / National Weather Service",
        "provider": "NOAA / NWS",
        "category": "weather-alerts",
        "layer": "planned-live",
        "time_horizon": "current + forecast",
        "geography": "lat/lon / zone / county",
        "cadence": "near-real-time",
        "auth": "No key required; contact header recommended",
        "endpoint": "https://www.weather.gov/documentation/services-web-api",
        "purpose": "Heat, flood, wildfire, severe weather, and public hazard alerts that can worsen health risks.",
        "status": "planned",
    },
    {
        "id": "fema_openfema",
        "name": "FEMA OpenFEMA Disaster Declarations",
        "provider": "FEMA",
        "category": "disaster",
        "layer": "planned-live",
        "time_horizon": "current + recent history",
        "geography": "county / state",
        "cadence": "frequent refresh",
        "auth": "No key required",
        "endpoint": "https://www.fema.gov/openfema-data-page/disaster-declarations-summaries-v2",
        "purpose": "Adds recent disasters and declarations that may change environmental exposure risk.",
        "status": "planned",
    },
    {
        "id": "nominatim_geocoder",
        "name": "OpenStreetMap Nominatim Geocoder",
        "provider": "OpenStreetMap / Nominatim",
        "category": "geographic-resolution",
        "layer": "planned-foundation",
        "time_horizon": "reference",
        "geography": "city / ZIP / lat/lon",
        "cadence": "reference",
        "auth": "No key required; contact recommended for repeated use",
        "endpoint": "https://nominatim.org/release-docs/5.0/api/Search/",
        "purpose": "Fallback geocoder for city/state or ZIP style locations when the Census geocoder needs coordinates first.",
        "status": "planned",
    },
    {
        "id": "census_geocoder",
        "name": "U.S. Census Geocoder",
        "provider": "U.S. Census Bureau",
        "category": "geographic-resolution",
        "layer": "planned-foundation",
        "time_horizon": "reference",
        "geography": "address / tract / county / FIPS",
        "cadence": "reference",
        "auth": "No key required",
        "endpoint": "https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html",
        "purpose": "Normalizes patient location into tract, county, and FIPS keys for joining external environmental datasets.",
        "status": "planned",
    },
    {
        "id": "atsdr_eji",
        "name": "ATSDR Environmental Justice Index",
        "provider": "CDC / ATSDR",
        "category": "cumulative-burden",
        "layer": "planned-historical",
        "time_horizon": "structural / historical",
        "geography": "census tract",
        "cadence": "periodic releases",
        "auth": "No key required",
        "endpoint": "https://www.atsdr.cdc.gov/place-health/php/eji/index.html",
        "purpose": "Provides tract-level cumulative environmental burden using environmental, social, and health factors.",
        "status": "planned",
    },
    {
        "id": "cdc_tracking",
        "name": "CDC Environmental Public Health Tracking",
        "provider": "CDC",
        "category": "public-health-tracking",
        "layer": "planned-historical",
        "time_horizon": "historical + baseline",
        "geography": "county / tract / state",
        "cadence": "varies by topic",
        "auth": "No key required",
        "endpoint": "https://www.cdc.gov/environmental-health-tracking/php/index.html",
        "purpose": "Adds environmental-health indicators such as air, water, drought, transportation, and vulnerability context.",
        "status": "planned",
    },
    {
        "id": "epa_echo",
        "name": "EPA ECHO",
        "provider": "EPA",
        "category": "facilities-compliance",
        "layer": "planned-historical",
        "time_horizon": "historical + recent",
        "geography": "facility / county / watershed",
        "cadence": "varies by program",
        "auth": "No key required",
        "endpoint": "https://echo.epa.gov/tools/data-downloads",
        "purpose": "Captures regulated facility, compliance, enforcement, PFAS, and water infrastructure context.",
        "status": "planned",
    },
    {
        "id": "epa_envirofacts",
        "name": "EPA Envirofacts",
        "provider": "EPA",
        "category": "environmental-platform",
        "layer": "planned-historical",
        "time_horizon": "historical + baseline",
        "geography": "facility / county / state",
        "cadence": "varies by dataset",
        "auth": "No key required",
        "endpoint": "https://www.epa.gov/enviro/data-downloads",
        "purpose": "Supports facility, TRI, RadNet, SDWIS, UV, and other EPA environmental data joins.",
        "status": "planned",
    },
    {
        "id": "epa_tri",
        "name": "EPA Toxics Release Inventory",
        "provider": "EPA",
        "category": "chemical-history",
        "layer": "planned-historical",
        "time_horizon": "long-term historical",
        "geography": "facility / county / state",
        "cadence": "annual reporting",
        "auth": "No key required",
        "endpoint": "https://www.epa.gov/toxics-release-inventory-tri-program",
        "purpose": "Tracks industrial toxic chemical releases and waste management for long-horizon community exposure context.",
        "status": "planned",
    },
    {
        "id": "epa_nutrient_pollution",
        "name": "EPA Nutrient Pollution Indicators",
        "provider": "EPA",
        "category": "water-quality",
        "layer": "planned-historical",
        "time_horizon": "historical baseline",
        "geography": "state / watershed",
        "cadence": "periodic releases",
        "auth": "No key required",
        "endpoint": "https://www.epa.gov/nutrientpollution",
        "purpose": "Adds nutrient loading, algal bloom, groundwater nitrate, and impaired-water context for long-term water exposure review.",
        "status": "planned",
    },
    {
        "id": "epa_envirofacts_additional",
        "name": "EPA Additional Envirofacts Datasets",
        "provider": "EPA",
        "category": "environmental-platform",
        "layer": "planned-historical",
        "time_horizon": "historical + baseline",
        "geography": "varies by dataset",
        "cadence": "varies by dataset",
        "auth": "No key required",
        "endpoint": "https://www.epa.gov/enviro/download-additional-envirofacts-datasets",
        "purpose": "Exposes additional structured datasets such as SDWIS, Safer Choice, and ECHO exports for local staging.",
        "status": "planned",
    },
    {
        "id": "epa_cdr",
        "name": "EPA Chemical Data Reporting",
        "provider": "EPA",
        "category": "chemical-history",
        "layer": "planned-historical",
        "time_horizon": "long-term historical",
        "geography": "facility / national",
        "cadence": "multi-year reporting cycles",
        "auth": "No key required",
        "endpoint": "https://www.epa.gov/chemical-data-reporting/access-chemical-data-reporting-data",
        "purpose": "Adds long-horizon industrial chemical manufacture, import, and use context.",
        "status": "planned",
    },
    {
        "id": "epa_esam",
        "name": "EPA ESAM Program",
        "provider": "EPA",
        "category": "sampling-methodology",
        "layer": "reference",
        "time_horizon": "incident / remediation reference",
        "geography": "incident site",
        "cadence": "program guidance updates",
        "auth": "No key required",
        "endpoint": "https://www.epa.gov/esam",
        "purpose": "Reference methods for environmental sampling, analytical methods, data quality, and remediation-response workflows.",
        "status": "reference",
    },
    {
        "id": "ipums_nhgis",
        "name": "IPUMS NHGIS Environmental Summaries",
        "provider": "IPUMS / NHGIS",
        "category": "structural-baseline",
        "layer": "candidate",
        "time_horizon": "historical baseline",
        "geography": "tract / county / census geography",
        "cadence": "periodic releases",
        "auth": "Registration / API access",
        "endpoint": "https://www.nhgis.org/environmental-summaries",
        "purpose": "Potential long-term land cover and climate baseline context for tract and county analysis.",
        "status": "candidate",
    },
]


DEFAULT_MANIFEST: dict[str, Any] = {
    "schema_version": 1,
    "updated_at": "",
    "sources": {},
}

DEFAULT_SYNC_SETTINGS: dict[str, Any] = {
    "schema_version": 1,
    "enabled": False,
    "interval_hours": 24,
    "source_ids": [
        "nominatim_geocoder",
        "census_geocoder",
        "nws",
        "fema_openfema",
        "airnow",
        "epa_nutrient_pollution",
    ],
    "last_run_at": "",
    "next_run_at": "",
    "last_status": "idle",
    "last_error": "",
    "last_summary": {},
}


def _manifest_path(data_dir: Path | str | None) -> Path | None:
    if not data_dir:
        return None
    return Path(data_dir) / "environmental" / "source_manifest.json"


def _sync_settings_path(data_dir: Path | str | None) -> Path | None:
    if not data_dir:
        return None
    return Path(data_dir) / "environmental" / "auto_sync_settings.json"


def load_environmental_manifest(data_dir: Path | str | None) -> dict[str, Any]:
    manifest_path = _manifest_path(data_dir)
    if not manifest_path or not manifest_path.exists():
        return deepcopy(DEFAULT_MANIFEST)

    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load environmental manifest: %s", exc)
        return deepcopy(DEFAULT_MANIFEST)


def save_environmental_manifest(
    data_dir: Path | str | None,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    manifest_path = _manifest_path(data_dir)
    if not manifest_path:
        return manifest

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = deepcopy(manifest)
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def update_environmental_manifest_source(
    data_dir: Path | str | None,
    source_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    manifest = load_environmental_manifest(data_dir)
    manifest.setdefault("sources", {})
    existing = manifest["sources"].get(source_id, {})
    merged = deepcopy(existing)
    merged.update(updates)
    manifest["sources"][source_id] = merged
    return save_environmental_manifest(data_dir, manifest)


def get_environmental_source_catalog(
    data_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    manifest = load_environmental_manifest(data_dir)
    manifest_sources = manifest.get("sources", {}) or {}

    catalog = []
    for source in ENVIRONMENTAL_SOURCE_CATALOG:
        item = deepcopy(source)
        manifest_entry = manifest_sources.get(item["id"], {}) or {}
        item["downloaded"] = bool(manifest_entry.get("downloaded"))
        item["last_checked"] = manifest_entry.get("last_checked", "")
        item["last_updated"] = manifest_entry.get("last_updated", "")
        item["local_path"] = manifest_entry.get("local_path", "")
        item["history_dir"] = manifest_entry.get("history_dir", "")
        item["record_count"] = manifest_entry.get("record_count")
        item["snapshot_count"] = manifest_entry.get("snapshot_count")
        item["coverage_notes"] = manifest_entry.get("coverage_notes", "")
        catalog.append(item)
    return catalog


def summarize_environmental_sources(
    catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    layer_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    downloaded = 0

    for item in catalog:
        layer_counts[item["layer"]] = layer_counts.get(item["layer"], 0) + 1
        category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
        if item.get("downloaded"):
            downloaded += 1

    return {
        "total_sources": len(catalog),
        "downloaded_sources": downloaded,
        "layer_counts": layer_counts,
        "category_counts": category_counts,
        "status_counts": status_counts,
    }


def load_environmental_sync_settings(
    data_dir: Path | str | None,
) -> dict[str, Any]:
    settings_path = _sync_settings_path(data_dir)
    if not settings_path or not settings_path.exists():
        return deepcopy(DEFAULT_SYNC_SETTINGS)

    try:
        loaded = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load environmental sync settings: %s", exc)
        return deepcopy(DEFAULT_SYNC_SETTINGS)

    merged = deepcopy(DEFAULT_SYNC_SETTINGS)
    merged.update(loaded or {})
    source_ids = merged.get("source_ids") or []
    merged["source_ids"] = [str(source_id) for source_id in source_ids]
    return merged


def save_environmental_sync_settings(
    data_dir: Path | str | None,
    settings: dict[str, Any],
) -> dict[str, Any]:
    settings_path = _sync_settings_path(data_dir)
    if not settings_path:
        return settings

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    merged = deepcopy(DEFAULT_SYNC_SETTINGS)
    merged.update(settings or {})
    source_ids = merged.get("source_ids") or []
    merged["source_ids"] = [str(source_id) for source_id in source_ids]
    settings_path.write_text(
        json.dumps(merged, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return merged


def update_environmental_sync_settings(
    data_dir: Path | str | None,
    updates: dict[str, Any],
) -> dict[str, Any]:
    settings = load_environmental_sync_settings(data_dir)
    settings.update(updates or {})
    return save_environmental_sync_settings(data_dir, settings)
