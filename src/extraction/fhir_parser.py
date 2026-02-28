"""
Clinical Intelligence Hub — FHIR JSON Bundle Parser

Parses FHIR (Fast Healthcare Interoperability Resources) JSON bundles
exported from EHR systems like Epic/MyChart into our Pydantic models.

Supports:
  - Bundle resources (collection of entries)
  - Patient, Observation, MedicationRequest, Condition, AllergyIntolerance,
    Procedure, DiagnosticReport resources
"""

import json
import logging
from datetime import date, datetime
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
    Vital,
)

logger = logging.getLogger("CIH-FHIR")

# FHIR vital sign LOINC codes mapped to human-readable names
VITAL_LOINC = {
    "85354-9": "Blood Pressure",
    "8867-4": "Heart Rate",
    "8310-5": "Body Temperature",
    "9279-1": "Respiratory Rate",
    "29463-7": "Body Weight",
    "8302-2": "Body Height",
    "39156-5": "BMI",
    "2708-6": "SpO2",
}


class FHIRParser:
    """Parses FHIR JSON bundles into CIH Pydantic models."""

    def __init__(self, source_file: str):
        self.source_file = source_file

    def parse_bundle(self, json_path: Path) -> dict:
        """
        Parse a FHIR Bundle JSON file.
        Returns dict of clinical data lists keyed by type.
        """
        with open(json_path, 'r') as f:
            data = json.load(f)

        resource_type = data.get("resourceType", "")

        if resource_type == "Bundle":
            return self._parse_bundle_entries(data)
        elif resource_type in ("Patient", "Observation", "MedicationRequest",
                                "Condition", "AllergyIntolerance", "Procedure"):
            return self._parse_single_resource(data)
        else:
            logger.warning(f"Unsupported FHIR resourceType: {resource_type}")
            return {}

    def _parse_bundle_entries(self, bundle: dict) -> dict:
        """Parse all entries in a FHIR Bundle."""
        results = {
            "medications": [],
            "labs": [],
            "diagnoses": [],
            "allergies": [],
            "procedures": [],
            "notes": [],
            "vitals": [],
        }

        entries = bundle.get("entry", [])
        logger.info(f"Parsing FHIR Bundle with {len(entries)} entries")

        for entry in entries:
            resource = entry.get("resource", {})
            rtype = resource.get("resourceType", "")

            if rtype == "MedicationRequest":
                med = self._parse_medication(resource)
                if med:
                    results["medications"].append(med)

            elif rtype == "Observation":
                # Could be lab or vital sign
                obs = self._parse_observation(resource)
                if obs:
                    if isinstance(obs, Vital):
                        results["vitals"].append(obs)
                    else:
                        results["labs"].append(obs)

            elif rtype == "Condition":
                dx = self._parse_condition(resource)
                if dx:
                    results["diagnoses"].append(dx)

            elif rtype == "AllergyIntolerance":
                allergy = self._parse_allergy(resource)
                if allergy:
                    results["allergies"].append(allergy)

            elif rtype == "Procedure":
                proc = self._parse_procedure(resource)
                if proc:
                    results["procedures"].append(proc)

            elif rtype == "DiagnosticReport":
                note = self._parse_diagnostic_report(resource)
                if note:
                    results["notes"].append(note)

        total = sum(len(v) for v in results.values())
        logger.info(f"Parsed {total} clinical items from FHIR Bundle")
        return results

    def _parse_single_resource(self, resource: dict) -> dict:
        """Parse a standalone FHIR resource."""
        results = self._parse_bundle_entries({"entry": [{"resource": resource}]})
        return results

    def _make_provenance(self) -> Provenance:
        """Create a provenance record for FHIR-sourced data."""
        return Provenance(
            source_file=self.source_file,
            extraction_model="fhir-parser",
            confidence=1.0,  # Structured data — no inference needed
        )

    # ── Resource Parsers ───────────────────────────────────

    def _parse_medication(self, resource: dict) -> Optional[Medication]:
        """Parse a MedicationRequest into a Medication."""
        try:
            med_ref = resource.get("medicationCodeableConcept", {})
            name = self._get_display(med_ref)
            if not name:
                return None

            # Extract RxNorm code if present
            rxnorm = self._get_code(med_ref, "http://www.nlm.nih.gov/research/umls/rxnorm")

            # Status mapping
            fhir_status = resource.get("status", "")
            status = MedicationStatus.ACTIVE if fhir_status == "active" else MedicationStatus.DISCONTINUED

            # Dosage
            dosage_text = None
            dosage_list = resource.get("dosageInstruction", [])
            if dosage_list:
                dosage_text = dosage_list[0].get("text")

            # Dates
            authored = self._parse_date(resource.get("authoredOn"))

            return Medication(
                name=name,
                rxnorm_cui=rxnorm,
                dosage=dosage_text,
                start_date=authored,
                status=status,
                provenance=self._make_provenance(),
            )
        except Exception as e:
            logger.debug(f"Failed to parse MedicationRequest: {e}")
            return None

    def _parse_observation(self, resource: dict):
        """Parse an Observation into a LabResult or Vital."""
        try:
            code_obj = resource.get("code", {})
            name = self._get_display(code_obj)
            if not name:
                return None

            loinc = self._get_code(code_obj, "http://loinc.org")

            # Check if it's a vital sign
            if loinc in VITAL_LOINC:
                return self._parse_vital(resource, VITAL_LOINC.get(loinc, name), loinc)

            # Extract value
            value = None
            value_text = None
            unit = None

            value_quantity = resource.get("valueQuantity", {})
            if value_quantity:
                value = value_quantity.get("value")
                unit = value_quantity.get("unit")
            elif "valueString" in resource:
                value_text = resource["valueString"]
            elif "valueCodeableConcept" in resource:
                value_text = self._get_display(resource["valueCodeableConcept"])

            # Reference range
            ref_low = None
            ref_high = None
            ref_range = resource.get("referenceRange", [])
            if ref_range:
                low = ref_range[0].get("low", {})
                high = ref_range[0].get("high", {})
                ref_low = low.get("value")
                ref_high = high.get("value")

            # Flag
            flag = None
            interpretation = resource.get("interpretation", [])
            if interpretation:
                flag = self._get_display(interpretation[0])

            test_date = self._parse_date(resource.get("effectiveDateTime"))

            return LabResult(
                name=name,
                loinc_code=loinc,
                value=value,
                value_text=value_text,
                unit=unit,
                reference_low=ref_low,
                reference_high=ref_high,
                flag=flag,
                test_date=test_date,
                provenance=self._make_provenance(),
            )
        except Exception as e:
            logger.debug(f"Failed to parse Observation: {e}")
            return None

    def _parse_vital(self, resource: dict, name: str, loinc: str) -> Optional[Vital]:
        """Parse a vital sign observation."""
        value_quantity = resource.get("valueQuantity", {})
        value = str(value_quantity.get("value", "")) if value_quantity else None
        unit = value_quantity.get("unit")
        measurement_date = self._parse_date(resource.get("effectiveDateTime"))

        return Vital(
            name=name,
            value=value,
            unit=unit,
            measurement_date=measurement_date,
            provenance=self._make_provenance(),
        )

    def _parse_condition(self, resource: dict) -> Optional[Diagnosis]:
        """Parse a Condition into a Diagnosis."""
        try:
            code_obj = resource.get("code", {})
            name = self._get_display(code_obj)
            if not name:
                return None

            snomed = self._get_code(code_obj, "http://snomed.info/sct")
            icd10 = self._get_code(code_obj, "http://hl7.org/fhir/sid/icd-10-cm")

            onset_date = self._parse_date(resource.get("onsetDateTime"))
            status = resource.get("clinicalStatus", {})
            status_text = self._get_code(status, "http://terminology.hl7.org/CodeSystem/condition-clinical")

            return Diagnosis(
                name=name,
                snomed_code=snomed,
                icd10_code=icd10,
                date_diagnosed=onset_date,
                status=status_text,
                provenance=self._make_provenance(),
            )
        except Exception as e:
            logger.debug(f"Failed to parse Condition: {e}")
            return None

    def _parse_allergy(self, resource: dict) -> Optional[Allergy]:
        """Parse an AllergyIntolerance."""
        try:
            code_obj = resource.get("code", {})
            allergen = self._get_display(code_obj)
            if not allergen:
                return None

            reaction_text = None
            severity = None
            reactions = resource.get("reaction", [])
            if reactions:
                manifestations = reactions[0].get("manifestation", [])
                if manifestations:
                    reaction_text = self._get_display(manifestations[0])
                severity = reactions[0].get("severity")

            return Allergy(
                allergen=allergen,
                reaction=reaction_text,
                severity=severity,
                provenance=self._make_provenance(),
            )
        except Exception as e:
            logger.debug(f"Failed to parse AllergyIntolerance: {e}")
            return None

    def _parse_procedure(self, resource: dict) -> Optional[Procedure]:
        """Parse a Procedure resource."""
        try:
            code_obj = resource.get("code", {})
            name = self._get_display(code_obj)
            if not name:
                return None

            snomed = self._get_code(code_obj, "http://snomed.info/sct")
            performed = self._parse_date(resource.get("performedDateTime"))

            return Procedure(
                name=name,
                snomed_code=snomed,
                procedure_date=performed,
                provenance=self._make_provenance(),
            )
        except Exception as e:
            logger.debug(f"Failed to parse Procedure: {e}")
            return None

    def _parse_diagnostic_report(self, resource: dict) -> Optional[ClinicalNote]:
        """Parse a DiagnosticReport into a ClinicalNote."""
        try:
            name = self._get_display(resource.get("code", {}))
            conclusion = resource.get("conclusion", "")
            effective_date = self._parse_date(resource.get("effectiveDateTime"))

            text = resource.get("text", {}).get("div", "")
            summary = conclusion or text or name or ""

            if not summary.strip():
                return None

            return ClinicalNote(
                note_date=effective_date,
                note_type="diagnostic_report",
                summary=summary,
                provenance=self._make_provenance(),
            )
        except Exception as e:
            logger.debug(f"Failed to parse DiagnosticReport: {e}")
            return None

    # ── FHIR Utility Helpers ───────────────────────────────

    @staticmethod
    def _get_display(codeable_concept: dict) -> Optional[str]:
        """Extract the display text from a FHIR CodeableConcept."""
        if not codeable_concept:
            return None
        # Try direct text
        text = codeable_concept.get("text")
        if text:
            return text
        # Try coding display
        codings = codeable_concept.get("coding", [])
        for coding in codings:
            display = coding.get("display")
            if display:
                return display
        return None

    @staticmethod
    def _get_code(codeable_concept: dict, system: str) -> Optional[str]:
        """Extract a code from a specific coding system."""
        if not codeable_concept:
            return None
        codings = codeable_concept.get("coding", [])
        for coding in codings:
            if coding.get("system") == system:
                return coding.get("code")
        return None

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[date]:
        """Parse a FHIR date string into a Python date."""
        if not date_str:
            return None
        try:
            # FHIR dates can be YYYY, YYYY-MM, or YYYY-MM-DD, or full datetime
            if "T" in date_str:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            parts = date_str.split("-")
            if len(parts) >= 3:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            elif len(parts) == 2:
                return date(int(parts[0]), int(parts[1]), 1)
            elif len(parts) == 1:
                return date(int(parts[0]), 1, 1)
        except (ValueError, TypeError):
            pass
        return None
