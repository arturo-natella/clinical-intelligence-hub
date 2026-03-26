"""
Clinical Intelligence Hub — Pydantic V2 Data Models

Every clinical data type carries provenance fields:
  source_file, source_page, date_extracted, confidence

This is the single source of truth for data shapes across the entire system.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────

class FileType(str, Enum):
    PDF_TEXT = "pdf_text"          # PDF with extractable text layer
    PDF_SCANNED = "pdf_scanned"   # PDF requiring OCR
    DICOM = "dicom"
    FHIR_JSON = "fhir_json"
    IMAGE = "image"               # JPG/PNG medical images
    GENETIC = "genetic"           # Genetic test result files
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PREPROCESSING = "preprocessing"   # Pass 0
    EXTRACTING = "extracting"         # Pass 1a/1b/1c
    REDACTING = "redacting"           # Pass 1.5
    ANALYZING = "analyzing"           # Pass 2-4
    VALIDATING = "validating"         # Pass 5
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"               # Duplicate or unsupported


class ProfileStatus(str, Enum):
    """High-level status of a patient profile."""
    PROCESSING = "processing"
    PARTIAL_READY = "partial_ready"   # Some data available, still processing
    READY = "ready"
    FAILED_PARTIAL = "failed_partial" # Failed but some data was saved
    FAILED = "failed"


class JobStatus(str, Enum):
    """Status of a background processing job."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class SectionStatus(str, Enum):
    """Status of an individual profile section (labs, meds, etc.)."""
    PENDING = "pending"
    PROCESSING = "processing"
    AVAILABLE = "available"
    WARNING = "warning"
    FAILED = "failed"


class ProcessingStage(str, Enum):
    """Granular processing stages used for checkpoint/resume."""
    UPLOADED = "uploaded"
    OCR_COMPLETE = "ocr_complete"
    CLASSIFIED = "classified"
    ENTITIES_EXTRACTED = "entities_extracted"
    NORMALIZED = "normalized"
    LINKED_TO_PROFILE = "linked_to_profile"
    SNAPSHOT_APPLIED = "snapshot_applied"


class BodySystem(str, Enum):
    GI = "gi"
    MUSCULOSKELETAL = "musculoskeletal"
    NEUROLOGICAL = "neurological"
    MOOD_ENERGY = "mood_energy"
    CARDIOVASCULAR = "cardiovascular"
    SLEEP = "sleep"
    SKIN = "skin"
    OTHER = "other"


class MedicationStatus(str, Enum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    PRN = "prn"                       # As-needed
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    CRITICAL = "critical"     # Drug interaction, dangerous threshold
    HIGH = "high"             # Significant clinical finding
    MODERATE = "moderate"     # Worth discussing with doctor
    LOW = "low"               # Informational
    INFO = "info"             # Background context


class FindingCategory(str, Enum):
    DRUG_INTERACTION = "drug_interaction"
    DRUG_GENE_INTERACTION = "drug_gene_interaction"
    LAB_THRESHOLD = "lab_threshold"
    SCREENING_GAP = "screening_gap"
    IMAGING_CHANGE = "imaging_change"
    CROSS_DISCIPLINARY = "cross_disciplinary"
    COMMUNITY_PATTERN = "community_pattern"
    GUIDELINE_UPDATE = "guideline_update"
    ADVERSE_EVENT = "adverse_event"


# ── Provenance (attached to every clinical data point) ─────

class Provenance(BaseModel):
    """Tracks where every piece of data came from."""
    source_file: str = Field(description="Original filename")
    source_page: Optional[int] = Field(default=None, description="Page number in source document")
    date_extracted: datetime = Field(default_factory=datetime.now, description="When this data was extracted")
    extraction_model: Optional[str] = Field(default=None, description="Which model extracted this (e.g., 'medgemma-27b', 'monai-lung')")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Model confidence score")
    raw_text: Optional[str] = Field(default=None, description="Original text snippet this was extracted from")


# ── File Tracking ──────────────────────────────────────────

class ProcessedFile(BaseModel):
    """Tracks each file through the pipeline."""
    file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    file_type: FileType
    sha256_hash: str
    file_size_bytes: int
    status: ProcessingStatus = ProcessingStatus.PENDING
    current_pass: Optional[str] = None
    error_message: Optional[str] = None
    date_added: datetime = Field(default_factory=datetime.now)
    date_completed: Optional[datetime] = None
    page_count: Optional[int] = None


# ── Patient Demographics ───────────────────────────────────

class Demographics(BaseModel):
    """Basic patient information (stored encrypted)."""
    biological_sex: Optional[str] = None
    birth_year: Optional[int] = None
    blood_type: Optional[str] = None
    ethnicity: Optional[str] = None
    location: Optional[str] = None  # County + State (e.g., "Maricopa County, AZ")


# ── Clinical Data Types (all carry Provenance) ─────────────

class Medication(BaseModel):
    """A single medication entry."""
    name: str
    generic_name: Optional[str] = None
    rxnorm_cui: Optional[str] = Field(default=None, description="RxNorm Concept Unique Identifier")
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None             # oral, IV, topical, etc.
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: MedicationStatus = MedicationStatus.UNKNOWN
    prescriber: Optional[str] = None
    reason: Optional[str] = None            # Why prescribed
    provenance: Provenance


class LabResult(BaseModel):
    """A single lab test result."""
    name: str
    loinc_code: Optional[str] = Field(default=None, description="LOINC code for this lab test")
    value: Optional[float] = None
    value_text: Optional[str] = None        # For non-numeric results (e.g., "Positive")
    unit: Optional[str] = None
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    flag: Optional[str] = None              # "High", "Low", "Critical", "Normal"
    test_date: Optional[date] = None
    ordering_provider: Optional[str] = None
    lab_facility: Optional[str] = None
    provenance: Provenance


class ImagingStudy(BaseModel):
    """A single imaging study with findings."""
    study_date: Optional[date] = None
    modality: Optional[str] = None          # CT, MRI, X-ray, Ultrasound, PET
    body_region: Optional[str] = None       # Chest, Abdomen, Head, etc.
    description: Optional[str] = None       # Free-text description from MedGemma 4B
    facility: Optional[str] = None
    ordering_provider: Optional[str] = None
    findings: list[ImagingFinding] = Field(default_factory=list)
    provenance: Provenance


class ImagingFinding(BaseModel):
    """A specific finding within an imaging study."""
    description: str
    snomed_code: Optional[str] = None
    body_region: Optional[str] = None
    measurements: Optional[dict] = None     # e.g., {"volume_mm3": 120, "diameter_mm": 8}
    monai_model: Optional[str] = None       # Which MONAI model detected this
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    comparison_to_prior: Optional[str] = None  # "Stable", "Increased", "Decreased", "New"
    radiomic_features: Optional[dict] = None  # Quantitative texture/shape/intensity features


class Diagnosis(BaseModel):
    """A diagnosis or medical condition."""
    name: str
    snomed_code: Optional[str] = Field(default=None, description="SNOMED CT code")
    icd10_code: Optional[str] = None
    date_diagnosed: Optional[date] = None
    status: Optional[str] = None            # "Active", "Resolved", "Chronic"
    diagnosing_provider: Optional[str] = None
    provenance: Provenance


class Procedure(BaseModel):
    """A medical procedure or surgery."""
    name: str
    snomed_code: Optional[str] = None
    procedure_date: Optional[date] = None
    provider: Optional[str] = None
    facility: Optional[str] = None
    outcome: Optional[str] = None
    provenance: Provenance


class Allergy(BaseModel):
    """An allergy or adverse reaction."""
    allergen: str
    reaction: Optional[str] = None
    severity: Optional[str] = None          # "Mild", "Moderate", "Severe", "Life-threatening"
    date_reported: Optional[date] = None
    provenance: Provenance


class GeneticVariant(BaseModel):
    """A genetic test result."""
    gene: str
    variant: Optional[str] = None
    phenotype: Optional[str] = None         # e.g., "Poor Metabolizer"
    clinical_significance: Optional[str] = None  # "Pathogenic", "Benign", "VUS"
    implications: Optional[str] = None
    test_date: Optional[date] = None
    testing_lab: Optional[str] = None
    provenance: Provenance


class ClinicalNote(BaseModel):
    """A clinical note, visit summary, or patient diary entry."""
    note_date: Optional[date] = None
    note_type: Optional[str] = None         # "visit_summary", "referral", "patient_log", "provider_note"
    provider: Optional[str] = None
    facility: Optional[str] = None
    summary: str
    provenance: Provenance


class Vital(BaseModel):
    """A vital sign measurement."""
    name: str                               # "Blood Pressure", "Heart Rate", "Weight", etc.
    value: Optional[str] = None             # String to handle "120/80" for BP
    unit: Optional[str] = None
    measurement_date: Optional[date] = None
    provenance: Provenance


# ── Symptom Tracking (user-reported) ──────────────────────

class SymptomIntensity(str, Enum):
    HIGH = "high"
    MID = "mid"
    LOW = "low"


# Backward-compatible alias for existing code
SymptomSeverity = SymptomIntensity


class SymptomEpisode(BaseModel):
    """A single occurrence of a symptom."""
    episode_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    episode_date: Optional[date] = None
    time_of_day: Optional[str] = None      # morning/afternoon/evening/night
    intensity: SymptomIntensity = SymptomIntensity.MID
    description: Optional[str] = None      # "Throbbing pain behind left eye, lasted 2 hours"
    duration: Optional[str] = None
    triggers: Optional[str] = None         # "after skipping lunch"
    end_date: Optional[date] = Field(default=None, description="When the symptom resolved (null = still ongoing)")
    resolution_notes: Optional[str] = Field(default=None, description="What helped resolve it (e.g. 'had tea', 'took ibuprofen')")
    linked_medication_id: Optional[str] = Field(
        default=None,
        description="Medication name this symptom is associated with (patient-reported)",
    )
    counter_values: dict = Field(default_factory=dict)  # {"stress": 2} or {"sitting_weird": false}
    body_system: Optional[str] = Field(default=None, description="Auto-classified body system (gi, neurological, etc.)")
    date_logged: datetime = Field(default_factory=datetime.now)


class CounterMeasureType(str, Enum):
    SCALE = "scale"        # 1-5
    YES_NO = "yes_no"
    FREE_TEXT = "free_text"


class CounterDefinition(BaseModel):
    """Defines how to track a doctor's claimed cause.

    Example: Doctor says headaches = stress → track stress level 1-5 each episode.
    NEVER deleted — archived when resolved but data stays in analytics.
    Can be unarchived if doctor revisits the claim.
    """
    counter_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doctor_claim: str                      # "stress", "sitting weird"
    measure_type: CounterMeasureType       # scale/yes_no/free_text
    measure_label: Optional[str] = None    # "Stress level" (auto-generated from claim)
    date_added: datetime = Field(default_factory=datetime.now)
    date_archived: Optional[datetime] = None  # when resolved (None = active)
    archived: bool = False                 # UI toggle; data always included in analytics


class Symptom(BaseModel):
    """A named symptom category containing episodes and counter-evidence.

    Example: 'Nerve pain on left leg' with 5 episodes and 2 counter definitions.
    """
    symptom_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symptom_name: str                      # "Headaches", "Nerve pain on left leg"
    episodes: list[SymptomEpisode] = Field(default_factory=list)
    counter_definitions: list[CounterDefinition] = Field(default_factory=list)
    date_created: datetime = Field(default_factory=datetime.now)


# ── Analysis Results ───────────────────────────────────────

class ClinicalFlag(BaseModel):
    """A finding, pattern, or alert from the analysis pipeline."""
    flag_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: FindingCategory
    severity: AlertSeverity
    title: str                              # Short summary (one line)
    description: str                        # Full explanation
    specialties_involved: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)   # References to supporting data
    literature_citations: list[str] = Field(default_factory=list)  # PubMed DOIs
    question_for_doctor: Optional[str] = None
    date_flagged: datetime = Field(default_factory=datetime.now)
    source_pass: Optional[str] = None       # Which pipeline pass generated this


class DrugInteraction(BaseModel):
    """A drug-drug or drug-gene interaction."""
    drug_a: str
    drug_b: Optional[str] = None            # None for drug-gene interactions
    gene: Optional[str] = None              # For pharmacogenomic interactions
    severity: AlertSeverity
    description: str
    source: str                             # "OpenFDA", "DrugBank", "PharmGKB"
    evidence_url: Optional[str] = None


class CommunityInsight(BaseModel):
    """A pattern from Reddit community analysis (anecdotal, NOT clinical)."""
    subreddit: str
    description: str
    upvote_count: int
    post_url: Optional[str] = None
    cross_disciplinary_context: Optional[str] = None  # Gemini explanation of biological mechanism
    date_found: datetime = Field(default_factory=datetime.now)
    disclaimer: str = "Unverified community report — NOT clinical data. For discussion with your doctor only."


class LiteratureCitation(BaseModel):
    """A published research paper citation."""
    title: str
    authors: Optional[str] = None
    journal: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    pubmed_id: Optional[str] = None
    relevance_summary: Optional[str] = None


# ── Cross-Disciplinary Connection ──────────────────────────

class CrossDisciplinaryConnection(BaseModel):
    """A connection found across medical specialties or adjacent domains."""
    connection_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    specialties: list[str]                  # Which specialties are involved
    patient_data_points: list[str]          # Which patient data supports this
    supporting_literature: list[LiteratureCitation] = Field(default_factory=list)
    severity: AlertSeverity
    question_for_doctor: Optional[str] = None
    date_found: datetime = Field(default_factory=datetime.now)


# ── Monitoring Alert ───────────────────────────────────────

class MonitoringAlert(BaseModel):
    """An alert from continuous monitoring (new research, drug safety, etc.)."""
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str                             # "PubMed", "OpenFDA", "ClinVar", "AHA", etc.
    title: str
    description: str
    relevance_explanation: str              # Why this matters for THIS patient
    severity: AlertSeverity
    url: Optional[str] = None
    date_detected: datetime = Field(default_factory=datetime.now)
    addressed: bool = False


# ── Patient Profile (top-level aggregate) ──────────────────

class ClinicalTimeline(BaseModel):
    """All clinical data organized for the patient."""
    medications: list[Medication] = Field(default_factory=list)
    labs: list[LabResult] = Field(default_factory=list)
    imaging: list[ImagingStudy] = Field(default_factory=list)
    diagnoses: list[Diagnosis] = Field(default_factory=list)
    procedures: list[Procedure] = Field(default_factory=list)
    allergies: list[Allergy] = Field(default_factory=list)
    genetics: list[GeneticVariant] = Field(default_factory=list)
    notes: list[ClinicalNote] = Field(default_factory=list)
    vitals: list[Vital] = Field(default_factory=list)
    symptoms: list[Symptom] = Field(default_factory=list)


class AnalysisResults(BaseModel):
    """All analysis outputs from the pipeline."""
    flags: list[ClinicalFlag] = Field(default_factory=list)
    drug_interactions: list[DrugInteraction] = Field(default_factory=list)
    cross_disciplinary: list[CrossDisciplinaryConnection] = Field(default_factory=list)
    community_insights: list[CommunityInsight] = Field(default_factory=list)
    literature: list[LiteratureCitation] = Field(default_factory=list)
    monitoring_alerts: list[MonitoringAlert] = Field(default_factory=list)
    questions_for_doctor: list[str] = Field(default_factory=list)


class PatientProfile(BaseModel):
    """Top-level patient profile — the complete data model."""
    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    demographics: Demographics = Field(default_factory=Demographics)
    clinical_timeline: ClinicalTimeline = Field(default_factory=ClinicalTimeline)
    analysis: AnalysisResults = Field(default_factory=AnalysisResults)
    processed_files: list[ProcessedFile] = Field(default_factory=list)
    pipeline_version: str = "1.0.0"
    # Incremental persistence fields
    profile_status: ProfileStatus = ProfileStatus.PROCESSING
    job_id: Optional[str] = None
    current_stage: Optional[str] = None
    progress_percent: int = 0
    section_statuses: dict = Field(default_factory=dict)


class ProfileSnapshot(BaseModel):
    """Lightweight renderable profile snapshot for immediate UI display.

    Written to the database after each meaningful pipeline stage so the UI
    can show partial results while processing continues.
    """
    profile_id: str
    status: ProfileStatus = ProfileStatus.PROCESSING
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    # Progress
    current_stage: Optional[str] = None
    progress_percent: int = 0
    job_id: Optional[str] = None
    # Data counts (available even during processing)
    file_count: int = 0
    medication_count: int = 0
    lab_count: int = 0
    diagnosis_count: int = 0
    imaging_count: int = 0
    note_count: int = 0
    flag_count: int = 0
    # Per-section statuses: {"labs": "available", "medications": "pending", ...}
    sections: dict = Field(default_factory=dict)
    # Basic demographics (populated as soon as extracted)
    demographics: dict = Field(default_factory=dict)
    # Full profile payload — included so the UI can render available sections
    profile_data: Optional[dict] = None


# ── PII Redaction Log ─────────────────────────────────────

class RedactionEntry(BaseModel):
    """A single PII redaction event for the audit trail."""
    original_type: str                      # "PERSON", "DATE_OF_BIRTH", "ADDRESS", etc.
    context: str                            # Surrounding text (with redacted item replaced)
    file_source: str
    timestamp: datetime = Field(default_factory=datetime.now)


# Forward reference resolution for ImagingStudy -> ImagingFinding
ImagingStudy.model_rebuild()
