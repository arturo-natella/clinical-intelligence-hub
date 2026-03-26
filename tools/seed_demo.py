#!/usr/bin/env python3
"""
Seed a MedPrep vault with realistic ghost patient data for demo purposes.

Usage:
    cd MedPrep
    python tools/seed_demo.py

Creates a vault with passphrase "demo" at data/patient_profile.enc
containing a comprehensive ghost patient that exercises all 13 features.

Ghost patient: "Alex Rivera", 35F, Maricopa County, AZ
  - 4 active conditions (diabetes T2, hypothyroidism, migraine, peripheral neuropathy)
  - 5 active medications (metformin, levothyroxine, lisinopril, atorvastatin, gabapentin)
  - 25+ lab results across 3 dates (HbA1c trending up, TSH, lipids, CMP, CBC, vitamin D)
  - 3 genetic variants (CYP2D6 poor metabolizer, CYP2C19 intermediate, SLCO1B1 decreased)
  - 1 imaging study (chest CT with 7mm lung nodule)
  - 3 tracked symptoms with 6-10 episodes each + counter-evidence
  - Vitals across 3 dates
"""

import sys
import json
import uuid
from pathlib import Path
from datetime import date, datetime, timedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.encryption import EncryptedVault

PASSPHRASE = "demo"
DATA_DIR = PROJECT_ROOT / "data"


def uid():
    return str(uuid.uuid4())


def prov(source="Demo Data", doc_date=None):
    """Minimal provenance dict."""
    return {
        "source_file": source,
        "page_number": None,
        "extraction_method": "manual_entry",
        "confidence": 1.0,
        "extracted_at": datetime.now().isoformat(),
        "document_date": doc_date,
    }


def build_demographics():
    return {
        "biological_sex": "female",
        "birth_year": 1991,
        "blood_type": "O+",
        "ethnicity": "Hispanic/Latino",
        "location": "Maricopa County, AZ",
    }


def build_medications():
    return [
        {
            "name": "Metformin",
            "generic_name": "metformin hydrochloride",
            "dosage": "1000mg",
            "frequency": "twice daily",
            "route": "oral",
            "start_date": "2023-06-15",
            "status": "active",
            "reason": "Type 2 diabetes management",
            "provenance": prov("Lab Report 2023-06"),
        },
        {
            "name": "Levothyroxine",
            "generic_name": "levothyroxine sodium",
            "dosage": "75mcg",
            "frequency": "once daily",
            "route": "oral",
            "start_date": "2022-03-10",
            "status": "active",
            "reason": "Hypothyroidism",
            "provenance": prov("Endocrinology Visit 2022-03"),
        },
        {
            "name": "Lisinopril",
            "generic_name": "lisinopril",
            "dosage": "10mg",
            "frequency": "once daily",
            "route": "oral",
            "start_date": "2024-01-20",
            "status": "active",
            "reason": "Blood pressure management, renal protection",
            "provenance": prov("Primary Care Visit 2024-01"),
        },
        {
            "name": "Atorvastatin",
            "generic_name": "atorvastatin calcium",
            "dosage": "20mg",
            "frequency": "once daily at bedtime",
            "route": "oral",
            "start_date": "2024-01-20",
            "status": "active",
            "reason": "Elevated LDL cholesterol",
            "provenance": prov("Primary Care Visit 2024-01"),
        },
        {
            "name": "Gabapentin",
            "generic_name": "gabapentin",
            "dosage": "300mg",
            "frequency": "three times daily",
            "route": "oral",
            "start_date": "2025-04-01",
            "status": "active",
            "reason": "Peripheral neuropathy pain management",
            "provenance": prov("Neurology Visit 2025-04"),
        },
        {
            "name": "Vitamin D3",
            "generic_name": "cholecalciferol",
            "dosage": "2000 IU",
            "frequency": "once daily",
            "route": "oral",
            "start_date": "2024-08-15",
            "status": "active",
            "reason": "Vitamin D deficiency",
            "provenance": prov("Lab Report 2024-08"),
        },
    ]


def build_diagnoses():
    return [
        {
            "diagnosis_id": uid(),
            "name": "Type 2 Diabetes Mellitus",
            "icd10_code": "E11.9",
            "date_diagnosed": "2023-06-15",
            "status": "Active",
            "confirmation_status": "confirmed",
            "patient_agreement": "agree",
            "confirmation_history": [
                {
                    "event_id": uid(),
                    "status": "suspected",
                    "provider": "Dr. Chen (Primary Care)",
                    "notes": "HbA1c 6.8% at initial screening",
                    "date": "2023-06-15T10:00:00",
                },
                {
                    "event_id": uid(),
                    "status": "confirmed",
                    "provider": "Dr. Martinez (Endocrinology)",
                    "notes": "Confirmed after fasting glucose 148 mg/dL and repeat HbA1c 7.2%",
                    "date": "2023-08-20T14:30:00",
                },
            ],
            "provenance": prov("Lab Report 2023-06"),
        },
        {
            "diagnosis_id": uid(),
            "name": "Hypothyroidism",
            "icd10_code": "E03.9",
            "date_diagnosed": "2022-03-10",
            "status": "Active",
            "confirmation_status": "confirmed",
            "patient_agreement": "agree",
            "confirmation_history": [
                {
                    "event_id": uid(),
                    "status": "confirmed",
                    "provider": "Dr. Martinez (Endocrinology)",
                    "notes": "TSH 8.4 mIU/L, confirmed Hashimoto's pattern on ultrasound",
                    "date": "2022-03-10T09:00:00",
                },
            ],
            "provenance": prov("Endocrinology Visit 2022-03"),
        },
        {
            "diagnosis_id": uid(),
            "name": "Migraine without aura",
            "icd10_code": "G43.009",
            "date_diagnosed": "2021-11-01",
            "status": "Active",
            "confirmation_status": "confirmed",
            "patient_agreement": "agree",
            "confirmation_history": [
                {
                    "event_id": uid(),
                    "status": "suspected",
                    "provider": "Dr. Chen (Primary Care)",
                    "notes": "Recurring headaches, referred to neurology",
                    "date": "2021-09-15T11:00:00",
                },
                {
                    "event_id": uid(),
                    "status": "confirmed",
                    "provider": "Dr. Patel (Neurology)",
                    "notes": "ICHD-3 criteria met, MRI unremarkable",
                    "date": "2021-11-01T15:00:00",
                },
            ],
            "provenance": prov("Neurology Visit 2021-11"),
        },
        {
            "diagnosis_id": uid(),
            "name": "Peripheral neuropathy",
            "icd10_code": "G62.9",
            "date_diagnosed": "2025-03-20",
            "status": "Active",
            "confirmation_status": "probable",
            "patient_agreement": "agree",
            "confirmation_history": [
                {
                    "event_id": uid(),
                    "status": "suspected",
                    "provider": "Dr. Patel (Neurology)",
                    "notes": "Tingling in feet correlates with elevated HbA1c; EMG ordered",
                    "date": "2025-01-10T10:00:00",
                },
                {
                    "event_id": uid(),
                    "status": "probable",
                    "provider": "Dr. Patel (Neurology)",
                    "notes": "EMG shows mild sensory abnormalities consistent with diabetic neuropathy",
                    "date": "2025-03-20T14:00:00",
                },
            ],
            "provenance": prov("Neurology Visit 2025-03"),
        },
        {
            "diagnosis_id": uid(),
            "name": "Essential hypertension",
            "icd10_code": "I10",
            "date_diagnosed": "2024-01-20",
            "status": "Active",
            "confirmation_status": "confirmed",
            "patient_agreement": "agree",
            "confirmation_history": [
                {
                    "event_id": uid(),
                    "status": "confirmed",
                    "provider": "Dr. Chen (Primary Care)",
                    "notes": "Persistent SBP > 140 over 3 visits",
                    "date": "2024-01-20T09:30:00",
                },
            ],
            "provenance": prov("Primary Care Visit 2024-01"),
        },
        {
            "diagnosis_id": uid(),
            "name": "Hyperlipidemia",
            "icd10_code": "E78.5",
            "date_diagnosed": "2024-01-20",
            "status": "Active",
            "confirmation_status": "confirmed",
            "patient_agreement": "agree",
            "confirmation_history": [
                {
                    "event_id": uid(),
                    "status": "confirmed",
                    "provider": "Dr. Chen (Primary Care)",
                    "notes": "LDL 168 mg/dL, started atorvastatin",
                    "date": "2024-01-20T09:30:00",
                },
            ],
            "provenance": prov("Primary Care Visit 2024-01"),
        },
    ]


def build_labs():
    """3 dates of labs to enable trajectory forecasting (requires 3+ points)."""
    labs = []
    dates = ["2024-08-15", "2025-04-10", "2025-11-20"]

    # HbA1c — trending UP (concerning)
    hba1c_values = [6.8, 7.2, 7.6]
    for d, v in zip(dates, hba1c_values):
        labs.append({
            "name": "HbA1c",
            "value": v,
            "unit": "%",
            "reference_low": 4.0,
            "reference_high": 5.6,
            "flag": "High",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # Fasting glucose — trending up
    glucose_values = [142, 155, 168]
    for d, v in zip(dates, glucose_values):
        labs.append({
            "name": "Glucose, Fasting",
            "value": v,
            "unit": "mg/dL",
            "reference_low": 70,
            "reference_high": 100,
            "flag": "High",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # TSH — improving (was high, normalizing)
    tsh_values = [8.2, 5.5, 4.1]
    for d, v in zip(dates, tsh_values):
        labs.append({
            "name": "TSH",
            "value": v,
            "unit": "mIU/L",
            "reference_low": 0.4,
            "reference_high": 4.0,
            "flag": "High" if v > 4.0 else "Normal",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # LDL — improving with statin
    ldl_values = [162, 138, 112]
    for d, v in zip(dates, ldl_values):
        labs.append({
            "name": "LDL Cholesterol",
            "value": v,
            "unit": "mg/dL",
            "reference_low": 0,
            "reference_high": 100,
            "flag": "High" if v > 100 else "Normal",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # Total Cholesterol
    tc_values = [245, 218, 195]
    for d, v in zip(dates, tc_values):
        labs.append({
            "name": "Total Cholesterol",
            "value": v,
            "unit": "mg/dL",
            "reference_low": 0,
            "reference_high": 200,
            "flag": "High" if v > 200 else "Normal",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # HDL — stable, borderline low
    hdl_values = [42, 44, 45]
    for d, v in zip(dates, hdl_values):
        labs.append({
            "name": "HDL Cholesterol",
            "value": v,
            "unit": "mg/dL",
            "reference_low": 50,
            "reference_high": 999,
            "flag": "Low" if v < 50 else "Normal",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # Triglycerides — improving
    trig_values = [205, 180, 155]
    for d, v in zip(dates, trig_values):
        labs.append({
            "name": "Triglycerides",
            "value": v,
            "unit": "mg/dL",
            "reference_low": 0,
            "reference_high": 150,
            "flag": "High" if v > 150 else "Normal",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # Creatinine — stable
    creat_values = [0.9, 0.85, 0.88]
    for d, v in zip(dates, creat_values):
        labs.append({
            "name": "Creatinine",
            "value": v,
            "unit": "mg/dL",
            "reference_low": 0.6,
            "reference_high": 1.1,
            "flag": "Normal",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # eGFR — stable
    egfr_values = [92, 95, 93]
    for d, v in zip(dates, egfr_values):
        labs.append({
            "name": "eGFR",
            "value": v,
            "unit": "mL/min/1.73m2",
            "reference_low": 90,
            "reference_high": 999,
            "flag": "Normal",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # Vitamin D — was deficient, improving with supplementation
    vitd_values = [18, 28, 35]
    for d, v in zip(dates, vitd_values):
        labs.append({
            "name": "Vitamin D, 25-Hydroxy",
            "value": v,
            "unit": "ng/mL",
            "reference_low": 30,
            "reference_high": 100,
            "flag": "Low" if v < 30 else "Normal",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # CRP — elevated (inflammation marker, useful for cross-specialty)
    crp_values = [3.8, 4.2, 5.1]
    for d, v in zip(dates, crp_values):
        labs.append({
            "name": "C-Reactive Protein",
            "value": v,
            "unit": "mg/L",
            "reference_low": 0,
            "reference_high": 3.0,
            "flag": "High",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    # Urine Albumin — slightly elevated (early diabetic nephropathy sign)
    alb_values = [22, 28, 35]
    for d, v in zip(dates, alb_values):
        labs.append({
            "name": "Urine Albumin",
            "value": v,
            "unit": "mg/L",
            "reference_low": 0,
            "reference_high": 30,
            "flag": "High" if v > 30 else "Normal",
            "test_date": d,
            "provenance": prov(f"Lab Report {d}"),
        })

    return labs


def build_genetics():
    """Genetic variants for PGx collision map."""
    return [
        {
            "gene": "CYP2D6",
            "variant": "*4/*4",
            "phenotype": "Poor Metabolizer",
            "clinical_significance": "Actionable",
            "implications": "Reduced metabolism of codeine, tramadol, metoprolol, and many antidepressants. Codeine will be ineffective (no conversion to morphine). Avoid codeine and tramadol.",
            "test_date": "2024-06-20",
            "testing_lab": "GeneSight Pharmacogenomics",
            "provenance": prov("Genetic Report 2024-06"),
        },
        {
            "gene": "CYP2C19",
            "variant": "*1/*2",
            "phenotype": "Intermediate Metabolizer",
            "clinical_significance": "Actionable",
            "implications": "Reduced activation of clopidogrel. If clopidogrel is needed, consider alternative antiplatelet therapy. Affects some SSRIs and PPIs.",
            "test_date": "2024-06-20",
            "testing_lab": "GeneSight Pharmacogenomics",
            "provenance": prov("Genetic Report 2024-06"),
        },
        {
            "gene": "SLCO1B1",
            "variant": "*5/*5",
            "phenotype": "Decreased Function",
            "clinical_significance": "Actionable",
            "implications": "Increased risk of statin-induced myopathy with simvastatin. Consider lower doses or alternative statins (rosuvastatin, pravastatin).",
            "test_date": "2024-06-20",
            "testing_lab": "GeneSight Pharmacogenomics",
            "provenance": prov("Genetic Report 2024-06"),
        },
    ]


def build_imaging():
    """Imaging with measurements for radiomics."""
    return [
        {
            "study_date": "2025-09-15",
            "modality": "CT",
            "body_region": "Chest",
            "description": "Low-dose CT lung cancer screening. Single 7mm ground-glass nodule in right lower lobe.",
            "facility": "Desert Imaging Center",
            "findings": [
                {
                    "description": "7mm ground-glass nodule in right lower lobe, posterior basal segment. No calcification. No associated lymphadenopathy.",
                    "body_region": "Lung - Right Lower Lobe",
                    "measurements": {
                        "diameter_mm": 7.0,
                        "volume_mm3": 180,
                        "density_hu": -520,
                    },
                    "comparison_to_prior": "New",
                    "radiomic_features": None,
                },
                {
                    "description": "Mild dependent atelectasis bilaterally. No pleural effusion.",
                    "body_region": "Lung - Bilateral",
                    "measurements": None,
                    "comparison_to_prior": None,
                },
            ],
            "provenance": prov("CT Chest Report 2025-09"),
        },
        {
            "study_date": "2025-05-10",
            "modality": "MRI",
            "body_region": "Brain",
            "description": "MRI brain with and without contrast for headache evaluation. No acute intracranial abnormality.",
            "facility": "Desert Imaging Center",
            "findings": [
                {
                    "description": "No mass lesion, acute infarct, or hemorrhage. Normal ventricular system. No abnormal enhancement.",
                    "body_region": "Brain",
                    "measurements": None,
                    "comparison_to_prior": None,
                },
            ],
            "provenance": prov("MRI Brain Report 2025-05"),
        },
    ]


def build_vitals():
    dates = ["2024-08-15", "2025-04-10", "2025-11-20"]
    vitals = []
    bp_values = ["138/88", "134/84", "130/82"]
    hr_values = ["78", "74", "72"]
    wt_values = ["172", "168", "165"]

    for d, bp, hr, wt in zip(dates, bp_values, hr_values, wt_values):
        vitals.append({
            "name": "Blood Pressure",
            "value": bp,
            "unit": "mmHg",
            "measurement_date": d,
            "provenance": prov(f"Visit {d}"),
        })
        vitals.append({
            "name": "Heart Rate",
            "value": hr,
            "unit": "bpm",
            "measurement_date": d,
            "provenance": prov(f"Visit {d}"),
        })
        vitals.append({
            "name": "Weight",
            "value": wt,
            "unit": "lbs",
            "measurement_date": d,
            "provenance": prov(f"Visit {d}"),
        })

    return vitals


def build_symptoms():
    """3 symptoms with rich episode data for analytics."""
    today = date.today()

    # ── Symptom 1: Migraines (doctor says anxiety — patient disagrees)
    migraine_episodes = []
    migraine_dates = [
        today - timedelta(days=d) for d in [3, 8, 14, 21, 28, 42, 56, 70]
    ]
    descriptions = [
        "Throbbing pain behind left eye, lasted 3 hours. Light sensitivity.",
        "Started after waking, moderate intensity. Nausea but no vomiting.",
        "Severe migraine with aura. Visual disturbances for 20 minutes before onset.",
        "Dull headache that escalated to throbbing by afternoon. Lasted 5 hours.",
        "Woke up with headache after poor sleep. Pressure behind both eyes.",
        "Sudden onset during work. Pulsating pain, had to lie down in dark room.",
        "Moderate headache after eating processed food. Lasted 2 hours.",
        "Morning migraine after skipping breakfast. Resolved with rest and water.",
    ]
    severities = ["high", "mid", "high", "mid", "low", "high", "mid", "low"]
    times_of_day = ["morning", "morning", "afternoon", "afternoon", "morning", "afternoon", "evening", "morning"]
    triggers = [
        "poor sleep, screen time",
        "poor sleep",
        "bright lights, stress at work",
        "skipped lunch",
        "poor sleep, dehydration",
        "fluorescent lights",
        "processed food, MSG",
        "skipped breakfast, dehydration",
    ]
    # Counter: anxiety level (scale 1-5) — patient's data will show LOW anxiety
    anxiety_counter_values = [1, 2, 1, 2, 1, 3, 1, 2]

    for i, (d, desc, sev, tod, trig, anx) in enumerate(
        zip(migraine_dates, descriptions, severities, times_of_day, triggers, anxiety_counter_values)
    ):
        migraine_episodes.append({
            "episode_id": uid(),
            "episode_date": d.isoformat(),
            "time_of_day": tod,
            "severity": sev,
            "description": desc,
            "duration": ["3 hours", "2 hours", "4 hours", "5 hours", "1 hour", "6 hours", "2 hours", "1.5 hours"][i],
            "triggers": trig,
            "counter_values": {"anxiety": anx},
            "date_logged": datetime.now().isoformat(),
        })

    migraine_symptom = {
        "symptom_id": uid(),
        "symptom_name": "Migraines",
        "episodes": migraine_episodes,
        "counter_definitions": [
            {
                "counter_id": uid(),
                "doctor_claim": "anxiety",
                "measure_type": "scale",
                "measure_label": "Anxiety level",
                "date_added": (today - timedelta(days=80)).isoformat(),
                "date_archived": None,
                "archived": False,
            },
        ],
        "date_created": (today - timedelta(days=80)).isoformat(),
    }

    # ── Symptom 2: Tingling/numbness in feet (doctor says sitting position — patient disagrees)
    tingling_episodes = []
    tingling_dates = [
        today - timedelta(days=d) for d in [2, 7, 12, 18, 25, 35]
    ]
    tingling_descs = [
        "Burning tingling in both feet, worse at night. Couldn't sleep.",
        "Numbness in toes after walking. Feet felt like pins and needles.",
        "Tingling started in afternoon, spread from toes to ankles.",
        "Burning sensation in soles of feet while lying in bed.",
        "Pins and needles in both feet after standing for 30 minutes.",
        "Numbness and tingling, cold sensation in toes despite warm room.",
    ]
    tingling_sevs = ["high", "mid", "mid", "high", "mid", "low"]
    tingling_tods = ["night", "afternoon", "afternoon", "night", "evening", "night"]
    tingling_trigs = [
        "standing all day",
        "walking 2 miles",
        "after eating sugary food",
        "no obvious trigger",
        "standing at kitchen counter",
        "cold floor",
    ]
    # Counter: sitting weird (yes/no) — mostly NO, disproving the doctor's claim
    sitting_values = [False, False, False, False, True, False]

    for i, (d, desc, sev, tod, trig, sit) in enumerate(
        zip(tingling_dates, tingling_descs, tingling_sevs, tingling_tods, tingling_trigs, sitting_values)
    ):
        tingling_episodes.append({
            "episode_id": uid(),
            "episode_date": d.isoformat(),
            "time_of_day": tod,
            "severity": sev,
            "description": desc,
            "duration": ["4 hours", "2 hours", "3 hours", "all night", "1 hour", "2 hours"][i],
            "triggers": trig,
            "counter_values": {"sitting_weird": sit},
            "date_logged": datetime.now().isoformat(),
        })

    tingling_symptom = {
        "symptom_id": uid(),
        "symptom_name": "Tingling in feet",
        "episodes": tingling_episodes,
        "counter_definitions": [
            {
                "counter_id": uid(),
                "doctor_claim": "sitting weird",
                "measure_type": "yes_no",
                "measure_label": "Were you sitting in an unusual position?",
                "date_added": (today - timedelta(days=40)).isoformat(),
                "date_archived": None,
                "archived": False,
            },
        ],
        "date_created": (today - timedelta(days=40)).isoformat(),
    }

    # ── Symptom 3: Fatigue (doctor says depression — patient has counter data showing low depression)
    fatigue_episodes = []
    fatigue_dates = [
        today - timedelta(days=d) for d in [1, 5, 10, 16, 22, 30, 40, 50, 60]
    ]
    fatigue_descs = [
        "Exhausted by 2pm despite sleeping 8 hours. Brain fog, couldn't focus.",
        "Crashed after lunch. Felt like I was walking through mud.",
        "Low energy all day. Managed work but needed 2 coffees by noon.",
        "Extreme fatigue after mild exercise (15 min walk). Had to sit down.",
        "Morning fatigue. Hit snooze 4 times. Felt unrefreshed despite 9 hours sleep.",
        "Energy dropped sharply mid-afternoon. Cold hands and feet.",
        "Could barely get through work day. Fell asleep at desk twice.",
        "Moderate tiredness. Better day but still not normal energy.",
        "Dragging all day. Muscles felt heavy. Short of breath climbing stairs.",
    ]
    fatigue_sevs = ["high", "mid", "mid", "high", "mid", "high", "high", "low", "mid"]
    fatigue_tods = ["afternoon", "afternoon", "morning", "afternoon", "morning", "afternoon", "afternoon", "morning", "morning"]
    fatigue_trigs = [
        "after eating carbs",
        "after lunch",
        "poor sleep quality",
        "after mild exercise",
        "poor sleep quality",
        "no obvious trigger",
        "stressful work day",
        "slightly better sleep",
        "after eating heavy meal",
    ]
    # Counter: depression/sadness (scale 1-5) — patient's data shows LOW depression
    depression_values = [1, 2, 1, 1, 2, 1, 2, 1, 1]

    for i, (d, desc, sev, tod, trig, dep) in enumerate(
        zip(fatigue_dates, fatigue_descs, fatigue_sevs, fatigue_tods, fatigue_trigs, depression_values)
    ):
        fatigue_episodes.append({
            "episode_id": uid(),
            "episode_date": d.isoformat(),
            "time_of_day": tod,
            "severity": sev,
            "description": desc,
            "duration": ["6 hours", "4 hours", "all day", "3 hours", "all day", "5 hours", "all day", "3 hours", "all day"][i],
            "triggers": trig,
            "counter_values": {"depression": dep},
            "date_logged": datetime.now().isoformat(),
        })

    fatigue_symptom = {
        "symptom_id": uid(),
        "symptom_name": "Fatigue",
        "episodes": fatigue_episodes,
        "counter_definitions": [
            {
                "counter_id": uid(),
                "doctor_claim": "depression",
                "measure_type": "scale",
                "measure_label": "Depression/sadness level",
                "date_added": (today - timedelta(days=65)).isoformat(),
                "date_archived": None,
                "archived": False,
            },
        ],
        "date_created": (today - timedelta(days=65)).isoformat(),
    }

    return [migraine_symptom, tingling_symptom, fatigue_symptom]


def build_notes():
    return [
        {
            "note_date": "2025-11-20",
            "note_type": "visit_summary",
            "provider": "Dr. Sarah Chen",
            "facility": "Desert Primary Care",
            "summary": "Follow-up for diabetes and hypertension. HbA1c rising despite metformin 1000mg BID. Discussed diet and exercise. Consider adding second agent if next HbA1c > 8.0. Blood pressure improved on lisinopril. Continue current regimen.",
            "provenance": prov("Visit Note 2025-11"),
        },
        {
            "note_date": "2025-04-01",
            "note_type": "referral",
            "provider": "Dr. James Park",
            "facility": "Southwest Neurology",
            "summary": "Referred for peripheral neuropathy evaluation. Patient reports progressive tingling and numbness in bilateral feet over 4 months. EMG/NCS shows mild sensorimotor polyneuropathy. Started gabapentin 300mg TID. Consider diabetic neuropathy given HbA1c trend.",
            "provenance": prov("Neurology Referral 2025-04"),
        },
    ]


def build_allergies():
    return [
        {
            "name": "Penicillin",
            "reaction": "Hives and facial swelling",
            "severity": "Moderate",
            "provenance": prov("Allergy List"),
        },
        {
            "name": "Sulfa drugs",
            "reaction": "Rash",
            "severity": "Mild",
            "provenance": prov("Allergy List"),
        },
    ]


def build_medication_doses():
    """Realistic 30-day dose log for Metformin and Gabapentin (F18)."""
    doses = []
    today = date(2026, 3, 26)
    # Metformin (twice daily) — 30 days, 92% adherence
    metformin_id = "demo-metformin"
    for i in range(30):
        d = (today - timedelta(days=29 - i)).isoformat()
        # Morning dose — always taken
        doses.append({
            "dose_id": uid(),
            "medication_id": metformin_id,
            "medication_name": "Metformin",
            "dose_date": d,
            "dose_time": "morning",
            "taken": True,
            "skipped_reason": None,
            "reaction": None,
            "reaction_severity": "none",
            "date_logged": d + "T08:15:00",
        })
        # Evening dose — missed 3 times
        missed_days = {5, 14, 22}
        if i in missed_days:
            doses.append({
                "dose_id": uid(),
                "medication_id": metformin_id,
                "medication_name": "Metformin",
                "dose_date": d,
                "dose_time": "evening",
                "taken": False,
                "skipped_reason": "Forgot",
                "reaction": None,
                "reaction_severity": "none",
                "date_logged": d + "T20:00:00",
            })
        else:
            doses.append({
                "dose_id": uid(),
                "medication_id": metformin_id,
                "medication_name": "Metformin",
                "dose_date": d,
                "dose_time": "evening",
                "taken": True,
                "skipped_reason": None,
                "reaction": None,
                "reaction_severity": "none",
                "date_logged": d + "T19:45:00",
            })
    # Gabapentin (three times daily) — 14 days, 2 reactions logged
    gabapentin_id = "demo-gabapentin"
    for i in range(14):
        d = (today - timedelta(days=13 - i)).isoformat()
        for dose_time, hour in [("morning", "08"), ("afternoon", "14"), ("evening", "20")]:
            reaction = None
            severity = "none"
            if i == 3 and dose_time == "morning":
                reaction = "Felt dizzy for about 30 minutes"
                severity = "mild"
            elif i == 9 and dose_time == "afternoon":
                reaction = "Mild nausea after lunch dose"
                severity = "mild"
            doses.append({
                "dose_id": uid(),
                "medication_id": gabapentin_id,
                "medication_name": "Gabapentin",
                "dose_date": d,
                "dose_time": dose_time,
                "taken": True,
                "skipped_reason": None,
                "reaction": reaction,
                "reaction_severity": severity,
                "date_logged": f"{d}T{hour}:10:00",
            })
    return doses


def build_family_history():
    """Family medical history for the ghost patient (F16)."""
    return [
        {
            "member_id": uid(),
            "relationship": "mother",
            "name": None,
            "conditions": [
                {"name": "Type 2 Diabetes Mellitus", "age_at_diagnosis": 48, "status": "Active"},
                {"name": "Hypothyroidism", "age_at_diagnosis": 45, "status": "Active"},
                {"name": "Breast cancer", "age_at_diagnosis": 58, "status": "Resolved"},
            ],
            "deceased": False,
            "cause_of_death": None,
            "notes": "Mother manages both diabetes and hypothyroidism with medication",
            "date_added": datetime.now().isoformat(),
        },
        {
            "member_id": uid(),
            "relationship": "father",
            "name": None,
            "conditions": [
                {"name": "Essential hypertension", "age_at_diagnosis": 50, "status": "Active"},
                {"name": "Coronary artery disease", "age_at_diagnosis": 62, "status": "Active"},
                {"name": "Type 2 Diabetes Mellitus", "age_at_diagnosis": 55, "status": "Active"},
            ],
            "deceased": False,
            "cause_of_death": None,
            "notes": "Father had CABG at 64",
            "date_added": datetime.now().isoformat(),
        },
        {
            "member_id": uid(),
            "relationship": "maternal_grandmother",
            "name": None,
            "conditions": [
                {"name": "Alzheimer's disease", "age_at_diagnosis": 72, "status": "Deceased"},
                {"name": "Osteoporosis", "age_at_diagnosis": 68, "status": "Deceased"},
            ],
            "deceased": True,
            "cause_of_death": "Complications from Alzheimer's disease",
            "notes": None,
            "date_added": datetime.now().isoformat(),
        },
        {
            "member_id": uid(),
            "relationship": "paternal_grandfather",
            "name": None,
            "conditions": [
                {"name": "Colorectal cancer", "age_at_diagnosis": 65, "status": "Deceased"},
            ],
            "deceased": True,
            "cause_of_death": "Colorectal cancer",
            "notes": "Diagnosed at 65, passed at 68",
            "date_added": datetime.now().isoformat(),
        },
        {
            "member_id": uid(),
            "relationship": "sibling",
            "name": None,
            "conditions": [
                {"name": "Migraine with aura", "age_at_diagnosis": 25, "status": "Active"},
                {"name": "Polycystic ovary syndrome", "age_at_diagnosis": 22, "status": "Active"},
            ],
            "deceased": False,
            "cause_of_death": None,
            "notes": "Older sister, 38",
            "date_added": datetime.now().isoformat(),
        },
    ]


def build_profile():
    """Build the complete ghost patient profile."""
    return {
        "profile_id": uid(),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "demographics": build_demographics(),
        "clinical_timeline": {
            "medications": build_medications(),
            "medication_doses": build_medication_doses(),
            "labs": build_labs(),
            "imaging": build_imaging(),
            "diagnoses": build_diagnoses(),
            "procedures": [],
            "allergies": build_allergies(),
            "genetics": build_genetics(),
            "notes": build_notes(),
            "vitals": build_vitals(),
            "symptoms": build_symptoms(),
        },
        "analysis": {
            "flags": [],
            "snowball_results": None,
        },
        "family_history": build_family_history(),
        "processed_files": [
            {
                "filename": "demo_data_seed.json",
                "file_hash": "demo",
                "processed_at": datetime.now().isoformat(),
                "record_counts": {
                    "medications": 6,
                    "labs": 36,
                    "diagnoses": 6,
                    "genetics": 3,
                    "imaging": 2,
                    "symptoms": 3,
                },
            }
        ],
        "pipeline_version": "2.0.0",
    }


def main():
    print("=" * 60)
    print("  MedPrep Demo Vault Seeder")
    print("=" * 60)
    print()

    # Build profile
    profile = build_profile()

    # Count data
    tl = profile["clinical_timeline"]
    fh = profile.get("family_history", [])
    print(f"  Ghost patient: 35F, Maricopa County, AZ")
    print(f"  Conditions:    {len(tl['diagnoses'])}")
    print(f"  Medications:   {len(tl['medications'])}")
    print(f"  Dose log:      {len(tl.get('medication_doses', []))} entries (30-day Metformin + 14-day Gabapentin)")
    print(f"  Lab results:   {len(tl['labs'])}")
    print(f"  Genetic tests: {len(tl['genetics'])}")
    print(f"  Imaging:       {len(tl['imaging'])} studies")
    print(f"  Symptoms:      {len(tl['symptoms'])} tracked")
    total_episodes = sum(len(s["episodes"]) for s in tl["symptoms"])
    print(f"  Episodes:      {total_episodes} total")
    print(f"  Vitals:        {len(tl['vitals'])}")
    print(f"  Notes:         {len(tl['notes'])}")
    print(f"  Allergies:     {len(tl['allergies'])}")
    print(f"  Family history:{len(fh)} members")
    print()

    # Save to vault
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Remove existing vault if present
    vault_file = DATA_DIR / "patient_profile.enc"
    if vault_file.exists():
        vault_file.unlink()
        print(f"  Removed existing vault at {vault_file}")

    vault = EncryptedVault(DATA_DIR, PASSPHRASE)
    vault.save_profile(profile)

    print(f"  Vault created at: {vault_file}")
    print(f"  Passphrase: {PASSPHRASE}")
    print()
    print("  Features exercised:")
    print("   1. Symptom Logger          — 3 symptoms, 23 episodes, 3 counter definitions")
    print("   2. Doctor Visit Prep       — conditions + labs + meds + symptoms + counters")
    print("   3. Pattern Monitor         — episodes over 80 days, multiple time-of-day patterns")
    print("   4. AI Snowball             — 6 conditions, 36 labs, 6 meds, symptoms + demographics")
    print("   5. Missing Negatives       — diabetes without dilated eye exam, foot exam on record")
    print("   6. Cross-Specialty         — scattered findings (CRP + neuropathy + fatigue + diabetes)")
    print("   7. Biomarker Cascades      — HbA1c + glucose + CRP + urine albumin chain")
    print("   8. PGx Collision Map       — CYP2D6, CYP2C19, SLCO1B1 × 6 active meds")
    print("   9. Trajectories            — 3 dates × 12 lab tests = 36 data points")
    print("  10. PubMed Sweeps           — symptom + med + condition + genetic queries")
    print("  11. Environmental           — Maricopa County, AZ (Valley Fever, extreme heat)")
    print("  12. Deep Radiomics          — 7mm lung nodule with measurements")
    print("  13. Symptom Analytics       — counter-evidence verdicts, calendar heatmaps, AI insights")
    print("  14. Diagnosis Confirmation  — confirmation history on all 6 diagnoses")
    print("  15. Family Medical History  — 5 members, diabetes+hypertension+cancer hereditary risk")
    print("  16. Medication Adherence    — 30-day Metformin log (92%), 14-day Gabapentin (2 reactions)")
    print()
    print("  Counter-evidence highlights:")
    print("   - Migraines: Doctor says anxiety → avg 1.6/5 → STRONGLY CONTRADICTS")
    print("   - Tingling:  Doctor says sitting weird → 83% No → STRONGLY CONTRADICTS")
    print("   - Fatigue:   Doctor says depression → avg 1.3/5 → STRONGLY CONTRADICTS")
    print()
    print("=" * 60)
    print("  Run the app and unlock with passphrase: demo")
    print("=" * 60)


if __name__ == "__main__":
    main()
