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

# Maximum characters per chunk (approximate 8K token window)
MAX_CHUNK_CHARS = 24000


class TextExtractor:
    """Pass 1a: Extracts structured clinical data from text using MedGemma 27B."""

    def __init__(self, progress_callback=None, pause_event=None):
        self._available = self._check_ollama()
        self._progress = progress_callback or (lambda *a: None)
        self._pause_event = pause_event

    def extract(self, pages: list[dict], source_file: str) -> dict:
        """
        Extract clinical data from document pages.

        Args:
            pages: list of {page: int, text: str} from preprocessor
            source_file: original filename for provenance

        Returns:
            dict with keys: medications, labs, diagnoses, procedures,
                           allergies, genetics, notes
        """
        if not self._available:
            logger.warning("Ollama not available — skipping MedGemma extraction")
            return {}

        if not pages:
            return {}

        results = {
            "medications": [],
            "labs": [],
            "diagnoses": [],
            "procedures": [],
            "allergies": [],
            "genetics": [],
            "notes": [],
        }

        # Chunk pages to fit model context window
        chunks = self._build_chunks(pages)
        logger.info(f"Processing {len(pages)} pages in {len(chunks)} chunks for {source_file}")

        for i, (chunk_pages, chunk_text) in enumerate(chunks, 1):
            # Pause check between chunks
            if self._pause_event and not self._pause_event.is_set():
                self._progress("log", f"  Paused at chunk {i}/{len(chunks)} — safe to close laptop", -1)
                self._pause_event.wait()
                self._progress("log", f"  Resumed at chunk {i}/{len(chunks)}", -1)

            page_range = f"pp.{chunk_pages[0]['page']}-{chunk_pages[-1]['page']}"
            self._progress("log", f"  Chunk {i}/{len(chunks)} ({page_range}) — sending to MedGemma...", -1)

            extracted = self._extract_chunk(chunk_text)
            if not extracted:
                self._progress("log", f"  Chunk {i}/{len(chunks)} — no structured data returned", -1)
                continue

            # Build provenance for this chunk
            page_nums = [p["page"] for p in chunk_pages]
            first_page = page_nums[0] if page_nums else None

            self._merge_results(results, extracted, source_file, first_page)

            chunk_items = sum(len(v) for v in extracted.values() if isinstance(v, list))
            self._progress("log",
                           f"  Chunk {i}/{len(chunks)} — extracted {chunk_items} clinical items",
                           -1)

        # Unload model from memory
        self._unload_model()
        self._progress("log", "  MedGemma 27B unloaded from memory", -1)

        total = sum(len(v) for v in results.values())
        logger.info(f"Extracted {total} clinical items from {source_file}")
        self._progress("log", f"  Total: {total} clinical items from {source_file}", -1)
        return results

    def _extract_chunk(self, text: str) -> Optional[dict]:
        """Send a text chunk to MedGemma 27B for extraction."""
        try:
            import ollama

            prompt = self._build_prompt(text)

            response = ollama.chat(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={
                    "temperature": 0.0,
                    "num_predict": 4096,
                },
                keep_alive="0",
            )

            result_text = response["message"]["content"]
            return json.loads(result_text)

        except json.JSONDecodeError as e:
            logger.warning(f"MedGemma returned invalid JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"MedGemma extraction failed: {e}")
            return None

    def _build_prompt(self, text: str) -> str:
        """Build the clinical extraction prompt."""
        return f"""You are an expert clinical data extractor. Read the following medical record text and extract ALL clinical entities into strict JSON.

Extract these categories:
1. **medications** — name, generic_name, dosage, frequency, route, status (active/discontinued/prn), reason
2. **labs** — name, value (numeric), value_text (non-numeric), unit, flag (High/Low/Normal/Critical), test_date (YYYY-MM-DD)
3. **diagnoses** — name, date_diagnosed (YYYY-MM-DD), status (Active/Resolved/Chronic)
4. **procedures** — name, procedure_date (YYYY-MM-DD), outcome
5. **allergies** — allergen, reaction, severity (Mild/Moderate/Severe/Life-threatening)
6. **genetics** — gene, variant, phenotype, clinical_significance, implications
7. **notes** — note_type (visit_summary/referral/patient_log/provider_note), summary (brief), provider, note_date (YYYY-MM-DD)

Rules:
- Extract EVERY clinical entity you find, no matter how minor
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
                    logger.debug(f"Failed to parse medication: {e}")

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
                        value=value,
                        value_text=lab_data.get("value_text"),
                        unit=lab_data.get("unit"),
                        flag=lab_data.get("flag"),
                        test_date=self._try_parse_date(lab_data.get("test_date")),
                        provenance=provenance,
                    ))
                except Exception as e:
                    logger.debug(f"Failed to parse lab: {e}")

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
                    logger.debug(f"Failed to parse diagnosis: {e}")

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
                    logger.debug(f"Failed to parse procedure: {e}")

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
                    logger.debug(f"Failed to parse allergy: {e}")

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
                    logger.debug(f"Failed to parse genetic: {e}")

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
                    logger.debug(f"Failed to parse note: {e}")

    def _unload_model(self):
        """Explicitly unload MedGemma 27B from memory."""
        try:
            import ollama
            ollama.generate(model=MODEL_NAME, prompt="", keep_alive="0")
            logger.info("MedGemma 27B unloaded from memory")
        except Exception:
            pass  # Best effort

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
    def _check_ollama() -> bool:
        """Check if Ollama is running."""
        try:
            import ollama
            ollama.list()
            return True
        except Exception:
            return False
