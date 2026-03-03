"""
Clinical Intelligence Hub — SIDER (Side Effect Resource) Database

SIDER is a comprehensive database of 1,430 drugs and 5,880 adverse drug
reactions (ADRs), comprising 140,064 drug-side-effect pairs with frequency
information where available. All data is extracted from FDA-approved drug
labels (package inserts) using text-mining techniques.

SIDER connects drugs (identified by STITCH/PubChem compound IDs) to MedDRA
preferred terms for side effects, with optional frequency data ranging from
"rare" (<0.01%) to "very common" (>=10%).

This client operates in two modes:
  1. Local mode — reads from pre-downloaded TSV files for fast, offline
     lookups. Files available from http://sideeffects.embl.de/download/
     or in cleaned format from https://github.com/dhimmel/SIDER4.
  2. API mode — queries the SIDER website directly when local data is
     not available.

License: CC-BY-NC-SA 4.0 (Creative Commons Attribution-NonCommercial-ShareAlike).
"""

import collections
import gzip
import logging
import os
import urllib.parse
from typing import Optional

from src.validation._http import api_get

logger = logging.getLogger("CIH-SIDER")

# ── SIDER Website ────────────────────────────────────────────────
SIDER_BASE = "http://sideeffects.embl.de"

# Expected local TSV files
SIDE_EFFECTS_FILE = "meddra_all_se.tsv.gz"
FREQUENCIES_FILE = "meddra_freq.tsv.gz"

SOURCE_LABEL = "SIDER"

# Column indices for meddra_all_se.tsv.gz
# Columns: STITCH_flat, STITCH_stereo, UMLS_CUI_from_label,
#           MedDRA_concept_type, UMLS_CUI_from_MedDRA, side_effect_name
_SE_COL_STITCH_FLAT = 0
_SE_COL_STITCH_STEREO = 1
_SE_COL_UMLS_LABEL = 2
_SE_COL_MEDDRA_TYPE = 3
_SE_COL_UMLS_MEDDRA = 4
_SE_COL_SE_NAME = 5

# Column indices for meddra_freq.tsv.gz
# Columns: STITCH_flat, STITCH_stereo, UMLS_CUI_from_label,
#           placebo, frequency, lower_bound, upper_bound,
#           MedDRA_concept_type, UMLS_CUI_from_MedDRA, side_effect_name
_FREQ_COL_STITCH_FLAT = 0
_FREQ_COL_STITCH_STEREO = 1
_FREQ_COL_UMLS_LABEL = 2
_FREQ_COL_PLACEBO = 3
_FREQ_COL_FREQUENCY = 4
_FREQ_COL_LOWER = 5
_FREQ_COL_UPPER = 6
_FREQ_COL_MEDDRA_TYPE = 7
_FREQ_COL_UMLS_MEDDRA = 8
_FREQ_COL_SE_NAME = 9

# Frequency description mapping (MedDRA/CIOMS standard)
_FREQUENCY_DESCRIPTIONS = {
    "very common": ">=10%",
    "common": "1% to <10%",
    "uncommon": "0.1% to <1%",
    "rare": "0.01% to <0.1%",
    "very rare": "<0.01%",
    "postmarketing": "Frequency not established (postmarketing reports)",
}


class SIDERClient:
    """
    Client for the SIDER (Side Effect Resource) database.

    Provides lookups for drug side effects, reverse lookups (which drugs
    cause a given side effect), and multi-drug side-effect overlap analysis.

    Operates in local mode (fast, from TSV files) or API mode (web queries).
    """

    def __init__(self, data_dir: str = None):
        """
        Initialize the SIDER client.

        Args:
            data_dir: Optional path to a directory containing SIDER TSV files
                      (meddra_all_se.tsv.gz, meddra_freq.tsv.gz). If provided
                      and the files exist, data is loaded into memory for fast
                      offline lookups.
        """
        # drug_name (lowercase) -> list of side-effect dicts
        self._drug_effects: dict[str, list[dict]] = {}

        # side_effect_name (lowercase) -> list of drug names
        self._effect_drugs: dict[str, list[str]] = {}

        # All known side-effect names (lowercase -> canonical name)
        self._effect_names: dict[str, str] = {}

        # STITCH ID -> drug name mapping (populated from data)
        self._stitch_to_drug: dict[str, str] = {}

        # Frequency data: (stitch_id, umls_cui) -> frequency info
        self._frequencies: dict[tuple[str, str], dict] = {}

        self._data_loaded = False

        if data_dir:
            self.load_data(data_dir)

    def search_drug_side_effects(
        self, drug_name: str, limit: int = 30
    ) -> list[dict]:
        """
        Get known side effects for a drug.

        If local SIDER data is loaded, searches by drug name in the
        in-memory index. Otherwise, attempts to query the SIDER website.

        Args:
            drug_name: Drug name (generic or brand).
            limit: Maximum number of side effects to return.

        Returns:
            List of side-effect dicts with keys: side_effect_name,
            meddra_id, frequency, frequency_description, source.
        """
        if not drug_name or not drug_name.strip():
            return []

        drug_key = drug_name.strip().lower()

        # ── Local mode ──────────────────────────────────────────
        if self._data_loaded:
            effects = self._drug_effects.get(drug_key, [])
            if not effects:
                # Try partial match
                effects = self._partial_drug_match(drug_key)

            if not effects:
                logger.debug(
                    f"SIDER: No local data for drug '{drug_name}'. "
                    f"Drug may not be in the SIDER database."
                )
                return []

            return effects[:limit]

        # ── API mode ────────────────────────────────────────────
        return self._api_drug_side_effects(drug_name, limit)

    def get_side_effect_drugs(
        self, side_effect: str, limit: int = 20
    ) -> list[dict]:
        """
        Reverse lookup: find drugs that list a given side effect.

        Args:
            side_effect: Side effect name (e.g., "Nausea", "Headache").
            limit: Maximum number of drugs to return.

        Returns:
            List of dicts with keys: drug_name, side_effect_name, source.
        """
        if not side_effect or not side_effect.strip():
            return []

        se_key = side_effect.strip().lower()

        if self._data_loaded:
            drugs = self._effect_drugs.get(se_key, [])
            if not drugs:
                # Try partial match on side-effect names
                drugs = self._partial_effect_drug_match(se_key)

            if not drugs:
                logger.debug(
                    f"SIDER: No drugs found for side effect '{side_effect}'."
                )
                return []

            canonical_name = self._effect_names.get(se_key, side_effect)

            results = []
            for drug in drugs[:limit]:
                results.append({
                    "drug_name": drug,
                    "side_effect_name": canonical_name,
                    "source": SOURCE_LABEL,
                })

            return results

        # API fallback: search for the side effect
        return self._api_side_effect_drugs(side_effect, limit)

    def search_side_effect(
        self, query: str, limit: int = 10
    ) -> list[dict]:
        """
        Search for a side effect by name.

        Args:
            query: Partial or full side-effect name to search.
            limit: Maximum number of results.

        Returns:
            List of matching side-effect terms with MedDRA IDs.
        """
        if not query or not query.strip():
            return []

        query_lower = query.strip().lower()

        if self._data_loaded:
            matches = []

            for se_lower, canonical in self._effect_names.items():
                if query_lower in se_lower:
                    # Count how many drugs list this side effect
                    drug_count = len(self._effect_drugs.get(se_lower, []))

                    matches.append({
                        "side_effect_name": canonical,
                        "meddra_id": self._get_meddra_id_for_effect(se_lower),
                        "drug_count": drug_count,
                        "source": SOURCE_LABEL,
                    })

            # Sort by drug count (most common side effects first)
            matches.sort(key=lambda x: x["drug_count"], reverse=True)
            return matches[:limit]

        # API mode: try the SIDER website
        return self._api_search_side_effect(query, limit)

    def check_side_effects(self, drug_names: list[str]) -> dict:
        """
        For a list of drugs, find ALL side effects and identify COMMON ones.

        This is valuable for polypharmacy analysis: when multiple medications
        share the same adverse effect, the patient may experience compounded
        risk. For example, if three drugs all list "drowsiness", the combined
        sedative burden may be clinically significant.

        Args:
            drug_names: List of drug names to analyze.

        Returns:
            Dict with:
              - per_drug: dict mapping each drug name to its side-effect list
              - shared_side_effects: list of side effects appearing in 2+
                drugs, sorted by the number of drugs sharing that effect
              - drug_count: number of drugs analyzed
              - source: "SIDER"
        """
        if not drug_names:
            return {
                "per_drug": {},
                "shared_side_effects": [],
                "drug_count": 0,
                "source": SOURCE_LABEL,
            }

        per_drug = {}
        effect_counter = collections.Counter()

        for drug_name in drug_names:
            effects = self.search_drug_side_effects(drug_name, limit=100)
            per_drug[drug_name] = effects

            for effect in effects:
                se_name = effect.get("side_effect_name", "").lower()
                if se_name:
                    effect_counter[se_name] += 1

        # Find side effects shared by 2+ drugs
        shared = []
        for se_name, count in effect_counter.items():
            if count >= 2:
                # Which drugs share this side effect?
                drugs_with_effect = [
                    drug for drug in drug_names
                    if any(
                        e.get("side_effect_name", "").lower() == se_name
                        for e in per_drug.get(drug, [])
                    )
                ]

                canonical = self._effect_names.get(se_name, se_name.title())

                shared.append({
                    "side_effect_name": canonical,
                    "drug_count": count,
                    "drugs": drugs_with_effect,
                    "source": SOURCE_LABEL,
                })

        # Sort by number of drugs sharing the effect (descending)
        shared.sort(key=lambda x: x["drug_count"], reverse=True)

        logger.info(
            f"SIDER side-effect check: {len(drug_names)} drugs, "
            f"{len(shared)} shared side effects found"
        )

        return {
            "per_drug": per_drug,
            "shared_side_effects": shared,
            "drug_count": len(drug_names),
            "source": SOURCE_LABEL,
        }

    def load_data(self, data_dir: str) -> bool:
        """
        Load SIDER TSV files from a directory into memory.

        Expected files:
          - meddra_all_se.tsv.gz: All side effects (drug-ADR pairs)
          - meddra_freq.tsv.gz: Side effects with frequency information

        The TSV files use tab-separated columns. Both gzipped and
        uncompressed files are supported.

        Args:
            data_dir: Path to directory containing the SIDER data files.

        Returns:
            True if data was loaded successfully, False otherwise.
        """
        if not data_dir or not os.path.isdir(data_dir):
            logger.warning(
                f"SIDER data directory not found: {data_dir}. "
                f"Operating in API-only mode."
            )
            return False

        # Load frequency data first (so we can enrich side-effect records)
        freq_loaded = self._load_frequencies(data_dir)

        # Load side effects
        se_loaded = self._load_side_effects(data_dir)

        if se_loaded:
            self._data_loaded = True
            drug_count = len(self._drug_effects)
            effect_count = len(self._effect_names)
            logger.info(
                f"SIDER data loaded: {drug_count} drugs, "
                f"{effect_count} side effects"
                + (f", frequency data available" if freq_loaded else "")
            )
            return True

        logger.warning(
            f"SIDER: Could not load side-effect data from '{data_dir}'. "
            f"Download from http://sideeffects.embl.de/download/ or "
            f"https://github.com/dhimmel/SIDER4 and place files in "
            f"'{data_dir}'."
        )
        return False

    # ── Local Data Loading ───────────────────────────────────────

    def _load_side_effects(self, data_dir: str) -> bool:
        """Load meddra_all_se.tsv.gz into in-memory dicts."""
        lines = self._read_tsv(data_dir, SIDE_EFFECTS_FILE)
        if lines is None:
            return False

        count = 0
        for line in lines:
            cols = line.split("\t")
            if len(cols) < 6:
                continue

            stitch_flat = cols[_SE_COL_STITCH_FLAT].strip()
            umls_meddra = cols[_SE_COL_UMLS_MEDDRA].strip()
            se_name = cols[_SE_COL_SE_NAME].strip()
            meddra_type = cols[_SE_COL_MEDDRA_TYPE].strip()

            if not se_name:
                continue

            # Only use preferred terms (PT), not lower-level terms
            if meddra_type and meddra_type.lower() not in ("pt", ""):
                continue

            se_lower = se_name.lower()

            # Build drug name from STITCH ID
            # SIDER uses STITCH IDs (CIDm or CIDs prefixed compound IDs).
            # We store the STITCH ID as the drug identifier when no
            # name mapping is available.
            drug_name = self._stitch_to_drug.get(
                stitch_flat, stitch_flat
            )
            drug_key = drug_name.lower()

            # Look up frequency data if available
            freq_key = (stitch_flat, umls_meddra)
            freq_info = self._frequencies.get(freq_key, {})

            record = {
                "side_effect_name": se_name,
                "meddra_id": umls_meddra,
                "frequency": freq_info.get("frequency", ""),
                "frequency_description": freq_info.get(
                    "frequency_description", ""
                ),
                "source": SOURCE_LABEL,
            }

            # Index by drug
            if drug_key not in self._drug_effects:
                self._drug_effects[drug_key] = []
            self._drug_effects[drug_key].append(record)

            # Index by side effect (reverse lookup)
            if se_lower not in self._effect_drugs:
                self._effect_drugs[se_lower] = []
            if drug_name not in self._effect_drugs[se_lower]:
                self._effect_drugs[se_lower].append(drug_name)

            # Canonical name mapping
            self._effect_names[se_lower] = se_name

            count += 1

        logger.debug(f"SIDER: Loaded {count} side-effect records")
        return count > 0

    def _load_frequencies(self, data_dir: str) -> bool:
        """Load meddra_freq.tsv.gz into the frequency lookup dict."""
        lines = self._read_tsv(data_dir, FREQUENCIES_FILE)
        if lines is None:
            return False

        count = 0
        for line in lines:
            cols = line.split("\t")
            if len(cols) < 10:
                continue

            stitch_flat = cols[_FREQ_COL_STITCH_FLAT].strip()
            umls_meddra = cols[_FREQ_COL_UMLS_MEDDRA].strip()
            frequency_raw = cols[_FREQ_COL_FREQUENCY].strip()
            lower_bound = cols[_FREQ_COL_LOWER].strip()
            upper_bound = cols[_FREQ_COL_UPPER].strip()

            if not stitch_flat or not umls_meddra:
                continue

            freq_desc = self._interpret_frequency(
                frequency_raw, lower_bound, upper_bound
            )

            self._frequencies[(stitch_flat, umls_meddra)] = {
                "frequency": frequency_raw,
                "frequency_description": freq_desc,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
            }

            count += 1

        logger.debug(f"SIDER: Loaded {count} frequency records")
        return count > 0

    @staticmethod
    def _read_tsv(
        data_dir: str, filename: str
    ) -> Optional[list[str]]:
        """
        Read a TSV file from the data directory.

        Tries the gzipped version first, then uncompressed.
        Returns a list of lines (excluding empty lines and comments),
        or None if the file cannot be read.
        """
        gz_path = os.path.join(data_dir, filename)
        plain_path = gz_path.rstrip(".gz") if filename.endswith(".gz") else gz_path

        # Try gzipped file first
        if os.path.isfile(gz_path) and filename.endswith(".gz"):
            try:
                with gzip.open(gz_path, "rt", encoding="utf-8") as f:
                    lines = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]
                logger.debug(
                    f"SIDER: Read {len(lines)} lines from {gz_path}"
                )
                return lines
            except Exception as e:
                logger.warning(f"SIDER: Error reading {gz_path}: {e}")

        # Try uncompressed file
        if os.path.isfile(plain_path):
            try:
                with open(plain_path, "r", encoding="utf-8") as f:
                    lines = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]
                logger.debug(
                    f"SIDER: Read {len(lines)} lines from {plain_path}"
                )
                return lines
            except Exception as e:
                logger.warning(f"SIDER: Error reading {plain_path}: {e}")

        logger.debug(f"SIDER: File not found: {gz_path}")
        return None

    # ── API Mode (Web Queries) ───────────────────────────────────

    def _api_drug_side_effects(
        self, drug_name: str, limit: int
    ) -> list[dict]:
        """
        Query the SIDER website for side effects of a drug.

        Falls back gracefully if the website is unreachable or the
        drug is not found.
        """
        safe_name = urllib.parse.quote(drug_name.strip().lower(), safe="")
        url = f"{SIDER_BASE}/drugs/{safe_name}/"

        try:
            data = api_get(url, accept="application/json")

            if not data:
                logger.debug(
                    f"SIDER: No API results for '{drug_name}'. "
                    f"Consider downloading SIDER data for local lookups: "
                    f"http://sideeffects.embl.de/download/"
                )
                return []

            # Parse response — structure depends on endpoint format
            effects = self._parse_api_side_effects(data, drug_name)
            return effects[:limit]

        except Exception as e:
            logger.debug(f"SIDER API query failed for '{drug_name}': {e}")
            return []

    def _api_side_effect_drugs(
        self, side_effect: str, limit: int
    ) -> list[dict]:
        """Query the SIDER website for drugs causing a given side effect."""
        safe_name = urllib.parse.quote(
            side_effect.strip().lower(), safe=""
        )
        url = f"{SIDER_BASE}/se/{safe_name}/"

        try:
            data = api_get(url, accept="application/json")
            if not data:
                logger.debug(
                    f"SIDER: No API results for side effect "
                    f"'{side_effect}'. Consider downloading SIDER data "
                    f"for local lookups."
                )
                return []

            results = self._parse_api_drug_list(data, side_effect)
            return results[:limit]

        except Exception as e:
            logger.debug(
                f"SIDER API query failed for side effect "
                f"'{side_effect}': {e}"
            )
            return []

    def _api_search_side_effect(
        self, query: str, limit: int
    ) -> list[dict]:
        """Search the SIDER website for side-effect terms."""
        safe_query = urllib.parse.quote(query.strip(), safe="")
        url = f"{SIDER_BASE}/se/?q={safe_query}"

        try:
            data = api_get(url, accept="application/json")
            if not data:
                logger.debug(
                    f"SIDER: No API results for side-effect search "
                    f"'{query}'. Consider downloading SIDER data for "
                    f"local lookups."
                )
                return []

            results = self._parse_api_se_search(data)
            return results[:limit]

        except Exception as e:
            logger.debug(
                f"SIDER API side-effect search failed for "
                f"'{query}': {e}"
            )
            return []

    # ── API Response Parsing ─────────────────────────────────────

    @staticmethod
    def _parse_api_side_effects(data, drug_name: str) -> list[dict]:
        """Parse side-effect data from a SIDER API response."""
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (
                data.get("side_effects")
                or data.get("effects")
                or data.get("results")
                or data.get("data")
                or []
            )
            if isinstance(items, dict):
                items = [items]
        else:
            return []

        if not isinstance(items, list):
            return []

        results = []
        for item in items:
            if not isinstance(item, dict):
                continue

            se_name = (
                item.get("side_effect_name")
                or item.get("name")
                or item.get("effect")
                or item.get("term", "")
            )
            if not se_name:
                continue

            results.append({
                "side_effect_name": se_name,
                "meddra_id": (
                    item.get("meddra_id")
                    or item.get("umls_cui")
                    or item.get("cui", "")
                ),
                "frequency": (
                    item.get("frequency")
                    or item.get("freq", "")
                ),
                "frequency_description": (
                    item.get("frequency_description")
                    or item.get("freq_description", "")
                ),
                "source": SOURCE_LABEL,
            })

        return results

    @staticmethod
    def _parse_api_drug_list(data, side_effect: str) -> list[dict]:
        """Parse a list of drugs from a SIDER API response."""
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (
                data.get("drugs")
                or data.get("results")
                or data.get("data")
                or []
            )
            if isinstance(items, dict):
                items = [items]
        else:
            return []

        if not isinstance(items, list):
            return []

        results = []
        for item in items:
            if isinstance(item, str):
                drug_name = item
            elif isinstance(item, dict):
                drug_name = (
                    item.get("drug_name")
                    or item.get("name")
                    or item.get("drug", "")
                )
            else:
                continue

            if not drug_name:
                continue

            results.append({
                "drug_name": drug_name,
                "side_effect_name": side_effect,
                "source": SOURCE_LABEL,
            })

        return results

    @staticmethod
    def _parse_api_se_search(data) -> list[dict]:
        """Parse side-effect search results from a SIDER API response."""
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (
                data.get("side_effects")
                or data.get("results")
                or data.get("data")
                or []
            )
            if isinstance(items, dict):
                items = [items]
        else:
            return []

        if not isinstance(items, list):
            return []

        results = []
        for item in items:
            if not isinstance(item, dict):
                continue

            se_name = (
                item.get("side_effect_name")
                or item.get("name")
                or item.get("term", "")
            )
            if not se_name:
                continue

            results.append({
                "side_effect_name": se_name,
                "meddra_id": (
                    item.get("meddra_id")
                    or item.get("umls_cui")
                    or item.get("cui", "")
                ),
                "drug_count": item.get("drug_count", 0),
                "source": SOURCE_LABEL,
            })

        return results

    # ── Lookup Helpers ───────────────────────────────────────────

    def _partial_drug_match(self, drug_key: str) -> list[dict]:
        """
        Search for a drug by partial name match in the local index.

        Tries substring matching against all loaded drug names. Returns
        the results from the best (shortest) matching drug name, to
        prefer exact or near-exact matches over very broad ones.
        """
        candidates = []

        for loaded_drug in self._drug_effects:
            if drug_key in loaded_drug or loaded_drug in drug_key:
                candidates.append(loaded_drug)

        if not candidates:
            return []

        # Prefer the shortest match (closest to exact)
        candidates.sort(key=len)
        best_match = candidates[0]

        logger.debug(
            f"SIDER: Partial drug match '{drug_key}' -> '{best_match}'"
        )
        return self._drug_effects.get(best_match, [])

    def _partial_effect_drug_match(self, se_key: str) -> list[str]:
        """
        Search for a side effect by partial name match.

        Returns the drug list from the best matching side-effect name.
        """
        candidates = []

        for loaded_se in self._effect_drugs:
            if se_key in loaded_se or loaded_se in se_key:
                candidates.append(loaded_se)

        if not candidates:
            return []

        # Prefer the shortest match
        candidates.sort(key=len)
        best_match = candidates[0]

        logger.debug(
            f"SIDER: Partial side-effect match '{se_key}' -> "
            f"'{best_match}'"
        )
        return self._effect_drugs.get(best_match, [])

    def _get_meddra_id_for_effect(self, se_lower: str) -> str:
        """
        Get the MedDRA UMLS CUI for a side effect name.

        Looks through the drug_effects index to find a record with
        a matching side-effect name and return its meddra_id.
        """
        for drug_effects in self._drug_effects.values():
            for record in drug_effects:
                if record.get("side_effect_name", "").lower() == se_lower:
                    meddra_id = record.get("meddra_id", "")
                    if meddra_id:
                        return meddra_id
        return ""

    @staticmethod
    def _interpret_frequency(
        frequency_raw: str,
        lower_bound: str,
        upper_bound: str,
    ) -> str:
        """
        Convert raw SIDER frequency data into a human-readable description.

        SIDER stores frequencies in several formats:
          - Descriptive terms: "common", "rare", "very common", etc.
          - Percentage values: "0.01" meaning 1%
          - Fraction ranges: lower_bound and upper_bound as decimals

        This method normalizes them all into a readable string.
        """
        if not frequency_raw:
            return ""

        freq_lower = frequency_raw.strip().lower()

        # Check for standard descriptive terms
        if freq_lower in _FREQUENCY_DESCRIPTIONS:
            return (
                f"{frequency_raw.strip().title()} "
                f"({_FREQUENCY_DESCRIPTIONS[freq_lower]})"
            )

        # Try to interpret as a numeric percentage
        try:
            freq_val = float(frequency_raw)
            if 0 <= freq_val <= 1:
                pct = freq_val * 100
                return f"{pct:.1f}%"
            return f"{freq_val}%"
        except (ValueError, TypeError):
            pass

        # If we have bounds, format as a range
        try:
            low = float(lower_bound) if lower_bound else None
            high = float(upper_bound) if upper_bound else None

            if low is not None and high is not None:
                return f"{low * 100:.1f}% - {high * 100:.1f}%"
            if low is not None:
                return f">={low * 100:.1f}%"
            if high is not None:
                return f"<={high * 100:.1f}%"
        except (ValueError, TypeError):
            pass

        # Return raw value as fallback
        return frequency_raw.strip()
