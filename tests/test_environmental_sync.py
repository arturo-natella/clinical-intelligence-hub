from pathlib import Path

from src.analysis.environmental_sources import (
    ENVIRONMENTAL_SOURCE_CATALOG,
    load_environmental_sync_settings,
    save_environmental_sync_settings,
    update_environmental_manifest_source,
    get_environmental_source_catalog,
)
from src.analysis.environmental_sync import EnvironmentalDataSync


def test_environmental_sync_settings_round_trip(tmp_path: Path):
    settings = save_environmental_sync_settings(
        tmp_path,
        {
            "enabled": True,
            "interval_hours": 12,
            "source_ids": ["nominatim_geocoder", "census_geocoder"],
        },
    )

    loaded = load_environmental_sync_settings(tmp_path)

    assert settings["enabled"] is True
    assert loaded["enabled"] is True
    assert loaded["interval_hours"] == 12
    assert loaded["source_ids"] == ["nominatim_geocoder", "census_geocoder"]


def test_environmental_source_catalog_merges_manifest_fields(tmp_path: Path):
    update_environmental_manifest_source(
        tmp_path,
        "nws",
        {
            "downloaded": True,
            "local_path": "data/environmental/raw/nws/latest.json",
            "snapshot_count": 3,
            "coverage_notes": "Stored point metadata and active alerts.",
        },
    )

    catalog = get_environmental_source_catalog(tmp_path)
    nws = next(item for item in catalog if item["id"] == "nws")

    assert nws["downloaded"] is True
    assert nws["local_path"] == "data/environmental/raw/nws/latest.json"
    assert nws["snapshot_count"] == 3
    assert "active alerts" in nws["coverage_notes"]


def test_environmental_sync_defaults_to_automated_sources(tmp_path: Path):
    syncer = EnvironmentalDataSync(tmp_path)
    result = syncer.sync_profile({})

    expected = {
        "nominatim_geocoder",
        "census_geocoder",
        "nws",
        "fema_openfema",
        "airnow",
        "epa_nutrient_pollution",
    }
    result_ids = {item["source_id"] for item in result["results"]}

    assert result_ids == expected
    assert result["summary"]["requested_sources"] == len(expected)
    assert result["summary"]["downloaded"] == 0
    assert result["summary"]["skipped"] == len(expected)
    assert set(source["id"] for source in ENVIRONMENTAL_SOURCE_CATALOG) >= expected
