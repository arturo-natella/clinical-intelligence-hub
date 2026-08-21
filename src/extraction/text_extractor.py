"""
Clinical Intelligence Hub — Pass 1a: MedGemma 27B Text Extraction

Uses local MedGemma 27B (via Ollama) to extract structured clinical
data from medical document text. Runs 100% locally — no network calls.

Key design decisions:
  - keep_alive: "0" — unloads model from memory after extraction
  - Chunking for documents over 8K tokens
  - Pydantic output validation
  - Provenance tagging on every extracted item

Salvaged Ollama call pattern from old medgemma_text.py.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from src.models import (
    Allergy,
    ClinicalNote,
    Diagnosis,
    GeneticVariant,
    LabResult,
    Medication,
    MedicationStatus,
    Procedure,
    Provenance,
)

logger = logging.getLogger("CIH-TextExtractor")

# MedGemma 27B model (Q8 quantization for highest local quality)
MODEL_NAME = "jwang580/medgemma_27b_q8_0"

# Maximum characters per chunk — smaller chunks produce less output,
# reducing the chance of hitting the num_predict token ceiling mid-JSON.
MAX_CHUNK_CHARS = 12000
EXTRACTION_KEYS = (
    "medications",
    "labs",
    "diagnoses",
    "procedures",
    "allergies",
    "genetics",
    "notes",
)
MAX_TRUNCATION_RETRY_DEPTH = 2


class TextExtractor:
    """Pass 1a: Extracts structured clinical data from text using MedGemma 27B."""

    def __init__(self, progress_callback=None, pause_event=None,
                 on_chunk_complete=None, on_chunk_checkpoint=None):
        self._progress = progress_callback or (lambda *a: None)
        self._pause_event = pause_event
        self._on_chunk_complete = on_chunk_complete
        self._on_chunk_checkpoint = on_chunk_checkpoint
        self._available = self._check_ollama()

    def extract(self, pages: list[dict], source_file: str,
                start_chunk: int = 0) -> dict:
        """
        Extract clinical data from document pages.

        Args:
            pages: list of {page: int, text: str} from preprocessor
            source_file: original filename for provenance
            start_chunk: number of contiguous chunks already checkpointed

        Returns:
            dict with keys: medications, labs, diagnoses, procedures,
                           allergies, genetics, notes
        """
        if not pages:
            return {}

        results = self._empty_result()

        # Chunk pages to fit model context window
        chunks = self._build_chunks(pages)
        total_chunks = len(chunks)
        start_chunk = max(0, int(start_chunk or 0))
        if start_chunk > total_chunks:
            logger.warning(
                "Stored text checkpoint exceeds current chunk count; "
                "restarting extraction (checkpoint=%s, chunks=%s)",
                start_chunk,
                total_chunks,
            )
            start_chunk = 0

        logger.info(
            "Starting text extraction (pages=%s, chunks=%s, resume_after=%s)",
            len(pages),
            total_chunks,
            start_chunk,
        )

        if start_chunk:
            self._progress(
                "log",
                f"  Resuming text extraction after chunk "
                f"{start_chunk}/{total_chunks}",
                -1,
            )

        if start_chunk == total_chunks:
            logger.info("Text extraction already complete at stored checkpoint")
            return results

        if not self._available:
            logger.warning("Ollama not available — skipping MedGemma extraction")
            self._progress(
                "log",
                "  MedGemma extraction skipped — see preflight warning above.",
                -1,
            )
            return {}

        failure_reason = None

        for i, (chunk_pages, chunk_text) in enumerate(chunks, 1):
            if i <= start_chunk:
                continue

            # Pause check between chunks
            if self._pause_event and not self._pause_event.is_set():
                self._progress("log", f"  Paused at chunk {i}/{len(chunks)} — safe to close laptop", -1)
                self._pause_event.wait()
                self._progress("log", f"  Resumed at chunk {i}/{len(chunks)}", -1)

            page_range = f"pp.{chunk_pages[0]['page']}-{chunk_pages[-1]['page']}"
            self._progress("log", f"  Chunk {i}/{len(chunks)} ({page_range}) — sending to MedGemma...", -1)
            logger.info(
                "Processing text extraction chunk "
                "(index=%s, total=%s, pages=%s, characters=%s)",
                i,
                len(chunks),
                len(chunk_pages),
                len(chunk_text),
            )

            extracted = self._extract_chunk(chunk_text)
            if extracted is None:
                failure_reason = (
                    f"MedGemma extraction failed at chunk {i}/{total_chunks}"
                )
                self._progress("log", f"  ERROR: {failure_reason}", -1)
                break

            # Build provenance for this chunk
            page_nums = [p["page"] for p in chunk_pages]
            first_page = page_nums[0] if page_nums else None

            # Track counts before merge to extract the delta
            prev_counts = {k: len(v) for k, v in results.items()}
            self._merge_results(results, extracted, source_file, first_page)

            chunk_items = sum(len(v) for v in extracted.values() if isinstance(v, list))
            self._progress("log",
                           f"  Chunk {i}/{len(chunks)} — extracted {chunk_items} clinical items",
                           -1)

            # Persist the encrypted profile before advancing the SQLite cursor.
            try:
                if self._on_chunk_complete:
                    delta = {}
                    for k, v in results.items():
                        start = prev_counts.get(k, 0)
                        if len(v) > start:
                            delta[k] = v[start:]
                    self._on_chunk_complete(delta)

                if self._on_chunk_checkpoint:
                    self._on_chunk_checkpoint(i, total_chunks)
            except Exception as e:
                logger.warning(
                    "Chunk checkpoint persistence failed (error_type=%s)",
                    type(e).__name__,
                )
                failure_reason = "Text extraction checkpoint persistence failed"
                break

        # Unload model from memory
        self._unload_model()
        self._progress("log", "  MedGemma 27B unloaded from memory", -1)

        if failure_reason:
            raise RuntimeError(failure_reason)

        total = sum(len(v) for v in results.values())
        logger.info("Text extraction complete (clinical_items=%s)", total)
        self._progress("log", f"  Total: {total} clinical items", -1)
        return results

    def count_chunks(self, pages: list[dict]) -> int:
        """Return the deterministic chunk count used by extraction/resume."""
        return len(self._build_chunks(pages))

    def _extract_chunk(self, text: str, retry_depth: int = 0) -> Optional[dict]:
        """Send a text chunk to MedGemma 27B for extraction."""
        result_text = ""
        try:
            import ollama

            prompt = self._build_prompt(text)
            logger.info(f"Sending {len(text)} chars to MedGemma (prompt total: {len(prompt)} chars)")

            response = ollama.chat(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={
                    "temperature": 0.0,
                    "num_predict": 16384,
                },
                keep_alive="0",
            )

            result_text = response["message"]["content"]
            logger.info(
                "MedGemma response received (characters=%s)",
                len(result_text),
            )

            parsed = json.loads(result_text)

            if not isinstance(parsed, dict):
                logger.warning(
                    "MedGemma returned JSON with an invalid top-level type"
                )
                self._progress(
                    "log",
                    "    WARNING: MedGemma returned JSON in an unexpected format",
                    -1,
                )
                return None

            # Empty dict {} is falsy — detect and warn explicitly
            if not parsed:
                logger.warning("MedGemma returned an empty JSON object")
                self._progress("log", "    WARNING: MedGemma returned empty JSON — model may not understand this document format", -1)
                return self._empty_result()

            # Check if all arrays are empty (valid JSON but no extractions)
            if all(
                isinstance(v, list) and len(v) == 0
                for v in parsed.values()
            ):
                logger.warning("MedGemma returned valid JSON but all categories are empty arrays")
                self._progress("log", "    WARNING: MedGemma found 0 clinical items — text may be unreadable or non-clinical", -1)
                return self._empty_result()

            return parsed

        except json.JSONDecodeError as e:
            logger.warning(
                "MedGemma returned invalid JSON (error_type=%s)",
                type(e).__name__,
            )
            # Attempt to salvage truncated JSON (common when num_predict is hit)
            repaired = self._repair_truncated_json(result_text)
            if repaired:
                items = sum(len(v) for v in repaired.values() if isinstance(v, list))
                logger.info(f"Salvaged {items} items from truncated JSON")
                self._progress("log", f"    WARNING: MedGemma JSON was truncated — salvaged {items} items", -1)
                if retry_depth < MAX_TRUNCATION_RETRY_DEPTH:
                    retried = self._retry_truncated_chunk(text, retry_depth + 1)
                    if retried:
                        recovered = self._merge_extracted_results(repaired, retried)
                        recovered_items = sum(
                            len(v) for v in recovered.values() if isinstance(v, list)
                        )
                        if recovered_items >= items:
                            logger.info(
                                "Recovered %s items by retrying truncated chunk in "
                                "smaller slices (depth=%s)",
                                recovered_items,
                                retry_depth + 1,
                            )
                            self._progress(
                                "log",
                                f"    Retried truncated chunk in smaller slices — recovered {recovered_items} items",
                                -1,
                            )
                            return recovered
                return repaired
            self._progress(
                "log",
                f"    WARNING: MedGemma returned invalid JSON ({type(e).__name__})",
                -1,
            )
            return None
        except Exception as e:
            error_type = type(e).__name__
            logger.error(
                "MedGemma extraction failed (error_type=%s)",
                error_type,
            )
            self._progress(
                "log",
                f"    ERROR: MedGemma call failed ({error_type})",
                -1,
            )
            return None

    def _build_prompt(self, text: str) -> str:
        """Build the clinical extraction prompt."""
        return f"""You are an expert clinical data extractor. Read the following medical record text and extract ALL clinical entities into strict JSON.

Extract these categories:
1. **medications** — name, generic_name, dosage, frequency, route, status (active/discontinued/prn), reason
2. **labs** — name, loinc_code (only when explicitly present), value (numeric), value_text (non-numeric), unit, flag (High/Low/Normal/Critical), test_date (YYYY-MM-DD)
3. **diagnoses** — name, date_diagnosed (YYYY-MM-DD), status (Active/Resolved/Chronic/Ruled out)
4. **procedures** — name, procedure_date (YYYY-MM-DD), outcome
5. **allergies** — allergen, reaction, severity (Mild/Moderate/Severe/Life-threatening)
6. **genetics** — gene, variant, phenotype, clinical_significance, implications
7. **notes** — note_type (visit_summary/referral/patient_log/provider_note), summary (brief), provider, note_date (YYYY-MM-DD)

Rules:
- Extract EVERY clinical entity you find, no matter how minor
- Conditions listed under a "Pertinent Negatives" heading, or explicitly negated in the text ("denies", "no history of", "negative for", "ruled out"), are conditions the patient does NOT have — set their status to "Ruled out", never "Active"
- Use null for fields you cannot determine
- Dates should be YYYY-MM-DD format when possible
- Do NOT invent data — only extract what is explicitly stated
- Return valid JSON with the 7 keys above, each containing an array

Medical Record Text:
\"\"\"{text}\"\"\"

Output strictly valid JSON:"""

    def _build_chunks(self, pages: list[dict]) -> list[tuple]:
        """Split pages into chunks that fit the model context window."""
        chunks = []
        current_pages = []
        current_text = ""

        for page in pages:
            page_text = page["text"]

            if len(current_text) + len(page_text) > MAX_CHUNK_CHARS and current_pages:
                chunks.append((current_pages, current_text))
                current_pages = []
                current_text = ""

            current_pages.append(page)
            current_text += f"\n--- Page {page['page']} ---\n{page_text}"

        if current_pages:
            chunks.append((current_pages, current_text))

        return chunks

    @staticmethod
    def _empty_result() -> dict:
        """Return the canonical empty extraction result shape."""
        return {key: [] for key in EXTRACTION_KEYS}

    @classmethod
    def _merge_extracted_results(cls, *payloads: Optional[dict]) -> dict:
        """Merge multiple extraction payloads and drop exact duplicates."""
        merged = cls._empty_result()

        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            for key in EXTRACTION_KEYS:
                values = payload.get(key, [])
                if isinstance(values, list):
                    merged[key].extend(v for v in values if isinstance(v, dict))

        for key in EXTRACTION_KEYS:
            deduped = []
            seen = set()
            for item in merged[key]:
                fingerprint = json.dumps(item, sort_keys=True, default=str)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                deduped.append(item)
            merged[key] = deduped

        return merged

    def _retry_truncated_chunk(self, text: str, retry_depth: int) -> Optional[dict]:
        """
        Retry a truncated extraction by splitting the chunk into smaller slices.

        This favors data completeness over speed only when the primary response
        was malformed, so normal chunks stay on the fast path.
        """
        parts = self._split_text_for_retry(text)
        if len(parts) < 2:
            return None

        repaired_parts = []
        for index, part in enumerate(parts, 1):
            self._progress(
                "log",
                f"    Retrying truncated chunk slice {index}/{len(parts)}...",
                -1,
            )
            extracted = self._extract_chunk(part, retry_depth=retry_depth)
            if extracted:
                repaired_parts.append(extracted)

        if not repaired_parts:
            return None

        return self._merge_extracted_results(*repaired_parts)

    @staticmethod
    def _split_text_for_retry(text: str) -> list[str]:
        """Split a chunk near page boundaries before falling back to midpoint."""
        page_blocks = []
        parts = re.split(r"(\n--- Page \d+ ---\n)", text)
        pending_marker = None

        for part in parts:
            if not part:
                continue
            if re.fullmatch(r"\n--- Page \d+ ---\n", part):
                pending_marker = part
                continue

            if pending_marker:
                page_blocks.append(f"{pending_marker}{part}".strip())
                pending_marker = None
            elif part.strip():
                page_blocks.append(part.strip())

        if len(page_blocks) >= 2:
            midpoint = len(page_blocks) // 2
            return [
                "\n".join(page_blocks[:midpoint]).strip(),
                "\n".join(page_blocks[midpoint:]).strip(),
            ]

        midpoint = len(text) // 2
        split_at = text.rfind("\n", 0, midpoint)
        if split_at < max(1, midpoint // 2):
            split_at = text.find("\n", midpoint)
        if split_at == -1:
            split_at = midpoint

        left = text[:split_at].strip()
        right = text[split_at:].strip()
        return [part for part in (left, right) if part]

    def _merge_results(self, results: dict, extracted: dict,
                       source_file: str, first_page: Optional[int]):
        """Merge extracted data into results with provenance."""
        provenance = Provenance(
            source_file=source_file,
            source_page=first_page,
            extraction_model="medgemma-27b",
        )

        for med_data in extracted.get("medications", []):
            if isinstance(med_data, dict) and med_data.get("name"):
                try:
                    status = MedicationStatus.UNKNOWN
                    raw_status = (med_data.get("status") or "").lower()
                    if raw_status in ("active", "discontinued", "prn"):
                        status = MedicationStatus(raw_status)

                    results["medications"].append(Medication(
                        name=med_data["name"],
                        generic_name=med_data.get("generic_name"),
                        dosage=med_data.get("dosage"),
                        frequency=med_data.get("frequency"),
                        route=med_data.get("route"),
                        status=status,
                        reason=med_data.get("reason"),
                        provenance=provenance,
                    ))
                except Exception as e:
                    self._log_parse_failure("medication", e)

        for lab_data in extracted.get("labs", []):
            if isinstance(lab_data, dict) and lab_data.get("name"):
                try:
                    value = lab_data.get("value")
                    if isinstance(value, str):
                        try:
                            value = float(value)
                        except ValueError:
                            lab_data["value_text"] = value
                            value = None

                    results["labs"].append(LabResult(
                        name=lab_data["name"],
                        loinc_code=lab_data.get("loinc_code"),
                        value=value,
                        value_text=lab_data.get("value_text"),
                        unit=lab_data.get("unit"),
                        flag=lab_data.get("flag"),
                        test_date=self._try_parse_date(lab_data.get("test_date")),
                        provenance=provenance,
                    ))
                except Exception as e:
                    self._log_parse_failure("lab", e)

        for dx_data in extracted.get("diagnoses", []):
            if isinstance(dx_data, dict) and dx_data.get("name"):
                try:
                    results["diagnoses"].append(Diagnosis(
                        name=dx_data["name"],
                        date_diagnosed=self._try_parse_date(dx_data.get("date_diagnosed")),
                        status=dx_data.get("status"),
                        provenance=provenance,
                    ))
                except Exception as e:
                    self._log_parse_failure("diagnosis", e)

        for proc_data in extracted.get("procedures", []):
            if isinstance(proc_data, dict) and proc_data.get("name"):
                try:
                    results["procedures"].append(Procedure(
                        name=proc_data["name"],
                        procedure_date=self._try_parse_date(proc_data.get("procedure_date")),
                        outcome=proc_data.get("outcome"),
                        provenance=provenance,
                    ))
                except Exception as e:
                    self._log_parse_failure("procedure", e)

        for allergy_data in extracted.get("allergies", []):
            if isinstance(allergy_data, dict) and allergy_data.get("allergen"):
                try:
                    results["allergies"].append(Allergy(
                        allergen=allergy_data["allergen"],
                        reaction=allergy_data.get("reaction"),
                        severity=allergy_data.get("severity"),
                        provenance=provenance,
                    ))
                except Exception as e:
                    self._log_parse_failure("allergy", e)

        for gen_data in extracted.get("genetics", []):
            if isinstance(gen_data, dict) and gen_data.get("gene"):
                try:
                    results["genetics"].append(GeneticVariant(
                        gene=gen_data["gene"],
                        variant=gen_data.get("variant"),
                        phenotype=gen_data.get("phenotype"),
                        clinical_significance=gen_data.get("clinical_significance"),
                        implications=gen_data.get("implications"),
                        provenance=provenance,
                    ))
                except Exception as e:
                    self._log_parse_failure("genetic", e)

        for note_data in extracted.get("notes", []):
            if isinstance(note_data, dict) and note_data.get("summary"):
                try:
                    results["notes"].append(ClinicalNote(
                        note_type=note_data.get("note_type"),
                        summary=note_data["summary"],
                        provider=note_data.get("provider"),
                        note_date=self._try_parse_date(note_data.get("note_date")),
                        provenance=provenance,
                    ))
                except Exception as e:
                    self._log_parse_failure("note", e)

    @staticmethod
    def _log_parse_failure(category: str, error: Exception):
        """Log a dropped extraction without exposing clinical input values."""
        logger.warning(
            "Dropped %s item during parsing (error_type=%s)",
            category,
            type(error).__name__,
        )

    def _unload_model(self):
        """Explicitly unload MedGemma 27B from memory."""
        try:
            import ollama
            ollama.generate(model=MODEL_NAME, prompt="", keep_alive="0")
            logger.info("MedGemma 27B unloaded from memory")
        except Exception as e:
            logger.warning(
                "Failed to unload MedGemma from memory (error_type=%s)",
                type(e).__name__,
            )

    @staticmethod
    def _try_parse_date(date_str):
        """Try to parse a date string into a date object."""
        if not date_str:
            return None
        try:
            from datetime import date
            parts = str(date_str).split("-")
            if len(parts) == 3:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, TypeError):
            pass
        return None

    @staticmethod
    def _repair_truncated_json(text: str) -> Optional[dict]:
        """
        Attempt to salvage a truncated JSON response.

        When the model hits its token limit, the JSON is often cut off mid-item.
        Strategy: scan each known top-level array and keep only complete objects
        that finished before the truncation point.
        """
        if not text or not text.strip().startswith("{"):
            return None

        repaired = TextExtractor._empty_result()

        for key in EXTRACTION_KEYS:
            items = TextExtractor._extract_complete_array_items(text, key)
            if items:
                repaired[key] = items

        if any(repaired.values()):
            return repaired

        return None

    @staticmethod
    def _extract_complete_array_items(text: str, key: str) -> list[dict]:
        """Extract complete JSON objects from one top-level array in a cut-off response."""
        key_pos = text.find(f'"{key}"')
        if key_pos == -1:
            return []

        array_start = text.find("[", key_pos)
        if array_start == -1:
            return []

        items = []
        in_string = False
        escape = False
        bracket_depth = 1
        brace_depth = 0
        object_start = None

        for idx in range(array_start + 1, len(text)):
            char = text[idx]

            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                continue

            if char == "[":
                bracket_depth += 1
                continue

            if char == "]":
                bracket_depth -= 1
                if bracket_depth == 0:
                    break
                continue

            if char == "{":
                brace_depth += 1
                if brace_depth == 1 and bracket_depth == 1:
                    object_start = idx
                continue

            if char == "}":
                if brace_depth == 0:
                    continue
                brace_depth -= 1
                if brace_depth == 0 and bracket_depth == 1 and object_start is not None:
                    raw_object = text[object_start:idx + 1]
                    try:
                        parsed = json.loads(raw_object)
                    except json.JSONDecodeError:
                        object_start = None
                        continue
                    if isinstance(parsed, dict):
                        items.append(parsed)
                    object_start = None

        return items

    def _check_ollama(self) -> bool:
        """Verify Ollama daemon is reachable AND the required model is pulled.

        A bare daemon ping passes even when the model is missing, which
        produces 1 silent 404 per chunk at extraction time. Checking the
        model list here surfaces the problem once at startup with an
        actionable message.
        """
        try:
            import ollama
            listing = ollama.list()
        except Exception as e:
            msg = (
                "Ollama daemon is not reachable "
                f"({type(e).__name__}). Start it with `ollama serve` or "
                "launch the Ollama app."
            )
            logger.warning(msg)
            self._progress("log", f"  WARNING: {msg}", -1)
            return False

        entries = getattr(listing, "models", None)
        if entries is None and isinstance(listing, dict):
            entries = listing.get("models", [])
        entries = entries or []

        available: set[str] = set()
        for entry in entries:
            name = getattr(entry, "model", None)
            if name is None and isinstance(entry, dict):
                name = entry.get("model") or entry.get("name")
            if name:
                available.add(name)
                available.add(name.split(":", 1)[0])

        candidates = {MODEL_NAME, f"{MODEL_NAME}:latest", MODEL_NAME.split(":", 1)[0]}
        if not (candidates & available):
            msg = (
                f"Ollama is running but model '{MODEL_NAME}' is not pulled. "
                f"Run: ollama pull {MODEL_NAME}"
            )
            logger.warning(msg)
            self._progress("log", f"  WARNING: {msg}", -1)
            return False

        return True
