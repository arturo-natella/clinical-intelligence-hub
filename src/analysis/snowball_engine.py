"""
Snowball Differential Diagnostician
====================================
Clinical Intelligence Hub

Graph-theory engine that starts from patient findings and "snowballs"
outward to build ranked differential diagnoses. Returns a node/edge
graph suitable for D3 force-directed visualization.

Algorithm:
    1. Seed  - collect all patient findings (diagnoses, symptoms, labs, flags)
    2. Match - for each known condition pattern, count matching findings
    3. Expand - for high-scoring candidates, flag missing expected findings
    4. Rank  - sort by match ratio weighted by severity
    5. Return - graph JSON (nodes + edges + scores)
"""

import re
from collections import defaultdict


# ---------------------------------------------------------------
#  CONDITION KNOWLEDGE BASE
# ---------------------------------------------------------------
# Each condition defines:
#   expected  - findings/symptoms/labs that support this diagnosis
#   rules_out - findings that make this diagnosis unlikely
#   related   - commonly co-occurring conditions
#   category  - organ system grouping
#
# Pattern matching is case-insensitive substring/regex.

CONDITION_DB = {
    "congestive_heart_failure": {
        "label": "Congestive Heart Failure",
        "category": "cardiac",
        "expected": [
            "cardiomegaly", "ejection fraction", "BNP elevated",
            "pulmonary edema", "pleural effusion", "peripheral edema",
            "shortness of breath", "dyspnea", "orthopnea",
            "jugular venous distension", "S3 gallop", "fatigue",
            "weight gain", "hepatomegaly",
        ],
        "rules_out": [
            "normal ejection fraction", "BNP normal",
        ],
        "related": [
            "coronary_artery_disease", "hypertension",
            "atrial_fibrillation", "renal_insufficiency",
        ],
    },
    "coronary_artery_disease": {
        "label": "Coronary Artery Disease",
        "category": "cardiac",
        "expected": [
            "chest pain", "angina", "ST depression", "ST elevation",
            "troponin elevated", "coronary stenosis", "atherosclerosis",
            "exertional dyspnea", "diaphoresis", "left arm pain",
            "jaw pain", "EKG abnormal",
        ],
        "rules_out": [
            "normal coronary angiography", "troponin normal",
        ],
        "related": [
            "congestive_heart_failure", "hypertension",
            "hyperlipidemia", "diabetes_type_2",
        ],
    },
    "atrial_fibrillation": {
        "label": "Atrial Fibrillation",
        "category": "cardiac",
        "expected": [
            "irregular rhythm", "palpitations", "atrial fibrillation",
            "rapid ventricular rate", "absent P waves",
            "irregularly irregular", "dizziness", "syncope",
        ],
        "rules_out": [
            "normal sinus rhythm",
        ],
        "related": [
            "congestive_heart_failure", "stroke",
            "hypertension", "hyperthyroidism",
        ],
    },
    "hypertension": {
        "label": "Hypertension",
        "category": "cardiac",
        "expected": [
            "elevated blood pressure", "hypertension", "high blood pressure",
            "headache", "left ventricular hypertrophy", "retinopathy",
            "proteinuria", "renal artery stenosis",
        ],
        "rules_out": [],
        "related": [
            "coronary_artery_disease", "congestive_heart_failure",
            "renal_insufficiency", "stroke",
        ],
    },
    "copd": {
        "label": "COPD",
        "category": "pulmonary",
        "expected": [
            "COPD", "emphysema", "chronic bronchitis", "FEV1 reduced",
            "hyperinflation", "barrel chest", "wheezing",
            "chronic cough", "sputum production", "dyspnea on exertion",
            "air trapping", "flattened diaphragm",
        ],
        "rules_out": [
            "normal spirometry", "FEV1 normal",
        ],
        "related": [
            "pulmonary_hypertension", "lung_cancer",
            "pneumonia",
        ],
    },
    "pneumonia": {
        "label": "Pneumonia",
        "category": "pulmonary",
        "expected": [
            "pneumonia", "consolidation", "infiltrate", "fever",
            "productive cough", "crackles", "leukocytosis",
            "pleuritic chest pain", "tachypnea", "hypoxia",
            "sputum culture positive",
        ],
        "rules_out": [
            "clear lung fields", "WBC normal",
        ],
        "related": [
            "copd", "sepsis", "pleural_effusion",
        ],
    },
    "pulmonary_embolism": {
        "label": "Pulmonary Embolism",
        "category": "pulmonary",
        "expected": [
            "pulmonary embolism", "PE", "D-dimer elevated",
            "tachycardia", "hypoxia", "pleuritic chest pain",
            "DVT", "deep vein thrombosis", "hemoptysis",
            "right heart strain", "saddle embolus",
        ],
        "rules_out": [
            "D-dimer normal", "negative CT angiography",
        ],
        "related": [
            "deep_vein_thrombosis", "atrial_fibrillation",
        ],
    },
    "cirrhosis": {
        "label": "Cirrhosis",
        "category": "hepatic",
        "expected": [
            "cirrhosis", "hepatic fibrosis", "ascites",
            "jaundice", "elevated bilirubin", "ALT elevated",
            "AST elevated", "portal hypertension", "varices",
            "spider angiomata", "coagulopathy", "INR elevated",
            "thrombocytopenia", "hepatomegaly", "splenomegaly",
        ],
        "rules_out": [
            "normal liver enzymes", "normal bilirubin",
        ],
        "related": [
            "hepatocellular_carcinoma", "portal_hypertension",
            "hepatic_encephalopathy",
        ],
    },
    "diabetes_type_2": {
        "label": "Type 2 Diabetes",
        "category": "endocrine",
        "expected": [
            "diabetes", "hyperglycemia", "HbA1c elevated",
            "glucose elevated", "polyuria", "polydipsia",
            "neuropathy", "retinopathy", "nephropathy",
            "insulin resistance", "metabolic syndrome",
        ],
        "rules_out": [
            "HbA1c normal", "fasting glucose normal",
        ],
        "related": [
            "hypertension", "hyperlipidemia",
            "coronary_artery_disease", "renal_insufficiency",
        ],
    },
    "renal_insufficiency": {
        "label": "Chronic Kidney Disease",
        "category": "renal",
        "expected": [
            "creatinine elevated", "BUN elevated", "GFR reduced",
            "proteinuria", "hematuria", "kidney disease",
            "renal insufficiency", "edema", "hypertension",
            "anemia", "electrolyte imbalance", "metabolic acidosis",
        ],
        "rules_out": [
            "creatinine normal", "GFR normal",
        ],
        "related": [
            "diabetes_type_2", "hypertension",
            "congestive_heart_failure",
        ],
    },
    "hypothyroidism": {
        "label": "Hypothyroidism",
        "category": "endocrine",
        "expected": [
            "TSH elevated", "T4 low", "hypothyroidism",
            "fatigue", "weight gain", "cold intolerance",
            "constipation", "dry skin", "bradycardia",
            "myxedema", "goiter",
        ],
        "rules_out": [
            "TSH normal", "T4 normal",
        ],
        "related": [
            "hyperlipidemia", "depression",
        ],
    },
    "hyperthyroidism": {
        "label": "Hyperthyroidism",
        "category": "endocrine",
        "expected": [
            "TSH suppressed", "T4 elevated", "T3 elevated",
            "hyperthyroidism", "tachycardia", "weight loss",
            "tremor", "heat intolerance", "exophthalmos",
            "goiter", "palpitations", "anxiety",
        ],
        "rules_out": [
            "TSH normal",
        ],
        "related": [
            "atrial_fibrillation", "osteoporosis",
        ],
    },
    "anemia": {
        "label": "Anemia",
        "category": "hematologic",
        "expected": [
            "anemia", "hemoglobin low", "hematocrit low",
            "fatigue", "pallor", "tachycardia", "dyspnea",
            "iron deficiency", "B12 deficiency", "MCV low",
            "MCV high", "reticulocyte count",
        ],
        "rules_out": [
            "hemoglobin normal", "hematocrit normal",
        ],
        "related": [
            "renal_insufficiency", "cirrhosis",
            "gastrointestinal_bleeding",
        ],
    },
    "deep_vein_thrombosis": {
        "label": "Deep Vein Thrombosis",
        "category": "vascular",
        "expected": [
            "DVT", "deep vein thrombosis", "leg swelling",
            "calf pain", "D-dimer elevated", "Homan sign",
            "venous duplex positive", "unilateral edema",
        ],
        "rules_out": [
            "D-dimer normal", "negative venous duplex",
        ],
        "related": [
            "pulmonary_embolism",
        ],
    },
    "stroke": {
        "label": "Stroke / CVA",
        "category": "neurologic",
        "expected": [
            "stroke", "CVA", "cerebrovascular accident",
            "hemiparesis", "aphasia", "facial droop",
            "acute infarct", "hemorrhage", "NIHSS",
            "ataxia", "dysarthria", "visual field deficit",
        ],
        "rules_out": [
            "normal MRI brain", "normal CT head",
        ],
        "related": [
            "atrial_fibrillation", "hypertension",
            "carotid_stenosis",
        ],
    },
    "lupus": {
        "label": "Systemic Lupus Erythematosus",
        "category": "autoimmune",
        "expected": [
            "lupus", "SLE", "ANA positive", "anti-dsDNA",
            "malar rash", "butterfly rash", "photosensitivity",
            "arthralgia", "pleuritis", "pericarditis",
            "nephritis", "proteinuria", "leukopenia",
            "complement low", "C3 low", "C4 low",
        ],
        "rules_out": [
            "ANA negative",
        ],
        "related": [
            "renal_insufficiency", "anemia",
        ],
    },
    "rheumatoid_arthritis": {
        "label": "Rheumatoid Arthritis",
        "category": "autoimmune",
        "expected": [
            "rheumatoid arthritis", "RF positive",
            "anti-CCP positive", "joint swelling",
            "morning stiffness", "symmetric arthritis",
            "erosive changes", "ESR elevated", "CRP elevated",
            "rheumatoid nodules",
        ],
        "rules_out": [
            "RF negative", "anti-CCP negative",
        ],
        "related": [
            "osteoporosis", "anemia",
        ],
    },
    "sepsis": {
        "label": "Sepsis",
        "category": "infectious",
        "expected": [
            "sepsis", "bacteremia", "fever", "tachycardia",
            "hypotension", "leukocytosis", "lactic acid elevated",
            "blood culture positive", "altered mental status",
            "organ dysfunction", "procalcitonin elevated",
        ],
        "rules_out": [
            "afebrile", "hemodynamically stable",
            "procalcitonin normal",
        ],
        "related": [
            "pneumonia", "urinary_tract_infection",
        ],
    },
    "pancreatitis": {
        "label": "Pancreatitis",
        "category": "gastrointestinal",
        "expected": [
            "pancreatitis", "lipase elevated", "amylase elevated",
            "epigastric pain", "nausea", "vomiting",
            "pancreatic inflammation", "peripancreatic fluid",
            "gallstones",
        ],
        "rules_out": [
            "lipase normal", "amylase normal",
        ],
        "related": [
            "cirrhosis", "gallstone_disease",
        ],
    },
    "osteoporosis": {
        "label": "Osteoporosis",
        "category": "musculoskeletal",
        "expected": [
            "osteoporosis", "osteopenia", "T-score low",
            "bone density decreased", "compression fracture",
            "vertebral fracture", "DEXA abnormal",
            "kyphosis", "height loss",
        ],
        "rules_out": [
            "T-score normal", "normal bone density",
        ],
        "related": [
            "hypothyroidism", "hyperthyroidism",
            "rheumatoid_arthritis",
        ],
    },

    # ── Expanded Conditions (v2.0) ────────────────────────────

    "sjogren_syndrome": {
        "label": "Sjogren's Syndrome",
        "category": "autoimmune",
        "expected": [
            "sjogren", "dry eyes", "dry mouth", "xerostomia",
            "keratoconjunctivitis sicca", "ANA positive",
            "anti-SSA", "anti-SSB", "Ro antibody", "La antibody",
            "parotid swelling", "fatigue", "arthralgia",
        ],
        "rules_out": ["ANA negative", "anti-SSA negative"],
        "related": ["lupus", "rheumatoid_arthritis"],
    },
    "celiac_disease": {
        "label": "Celiac Disease",
        "category": "gastrointestinal",
        "expected": [
            "celiac", "anti-tTG positive", "anti-endomysial positive",
            "villous atrophy", "diarrhea", "bloating",
            "iron deficiency", "weight loss", "malabsorption",
            "dermatitis herpetiformis", "osteoporosis",
        ],
        "rules_out": ["anti-tTG negative", "normal duodenal biopsy"],
        "related": ["anemia", "osteoporosis", "hypothyroidism"],
    },
    "mast_cell_activation": {
        "label": "Mast Cell Activation Syndrome",
        "category": "autoimmune",
        "expected": [
            "MCAS", "mast cell", "tryptase elevated", "flushing",
            "urticaria", "hives", "anaphylaxis", "abdominal pain",
            "diarrhea", "tachycardia", "hypotension", "brain fog",
            "histamine intolerance",
        ],
        "rules_out": ["tryptase normal"],
        "related": ["postural_orthostatic_tachycardia", "ehlers_danlos"],
    },
    "postural_orthostatic_tachycardia": {
        "label": "POTS",
        "category": "cardiac",
        "expected": [
            "POTS", "postural orthostatic tachycardia", "orthostatic intolerance",
            "tachycardia on standing", "dizziness", "lightheadedness",
            "syncope", "fatigue", "exercise intolerance",
            "blood pooling", "tilt table positive",
        ],
        "rules_out": ["normal tilt table"],
        "related": ["mast_cell_activation", "ehlers_danlos"],
    },
    "ehlers_danlos": {
        "label": "Ehlers-Danlos Syndrome",
        "category": "musculoskeletal",
        "expected": [
            "ehlers danlos", "EDS", "hypermobility", "joint laxity",
            "beighton score", "skin hyperextensibility", "easy bruising",
            "joint subluxation", "chronic pain", "fatigue",
            "gastrointestinal dysfunction",
        ],
        "rules_out": [],
        "related": ["postural_orthostatic_tachycardia", "mast_cell_activation"],
    },
    "fibromyalgia": {
        "label": "Fibromyalgia",
        "category": "musculoskeletal",
        "expected": [
            "fibromyalgia", "widespread pain", "tender points",
            "fatigue", "sleep disturbance", "cognitive dysfunction",
            "brain fog", "morning stiffness", "headache",
            "irritable bowel", "depression", "anxiety",
        ],
        "rules_out": [],
        "related": ["hypothyroidism", "depression", "chronic_fatigue_syndrome"],
    },
    "chronic_fatigue_syndrome": {
        "label": "Chronic Fatigue Syndrome / ME",
        "category": "autoimmune",
        "expected": [
            "chronic fatigue", "ME/CFS", "post-exertional malaise",
            "unrefreshing sleep", "cognitive impairment", "brain fog",
            "orthostatic intolerance", "sore throat",
            "lymph node tenderness", "muscle pain", "joint pain",
        ],
        "rules_out": [],
        "related": ["fibromyalgia", "postural_orthostatic_tachycardia"],
    },
    "multiple_sclerosis": {
        "label": "Multiple Sclerosis",
        "category": "neurologic",
        "expected": [
            "multiple sclerosis", "MS", "demyelination",
            "optic neuritis", "visual changes", "numbness",
            "tingling", "weakness", "spasticity", "fatigue",
            "oligoclonal bands", "white matter lesions",
            "MRI brain lesions", "Uhthoff phenomenon",
        ],
        "rules_out": ["normal MRI brain", "normal CSF"],
        "related": ["lupus"],
    },
    "ankylosing_spondylitis": {
        "label": "Ankylosing Spondylitis",
        "category": "musculoskeletal",
        "expected": [
            "ankylosing spondylitis", "HLA-B27 positive",
            "sacroiliitis", "back pain", "morning stiffness",
            "reduced spinal mobility", "uveitis", "enthesitis",
            "ESR elevated", "CRP elevated",
        ],
        "rules_out": ["HLA-B27 negative", "normal sacroiliac joints"],
        "related": ["ibd", "psoriatic_arthritis"],
    },
    "psoriatic_arthritis": {
        "label": "Psoriatic Arthritis",
        "category": "musculoskeletal",
        "expected": [
            "psoriatic arthritis", "psoriasis", "dactylitis",
            "sausage digits", "nail pitting", "enthesitis",
            "joint swelling", "asymmetric arthritis",
            "distal joint involvement", "ESR elevated",
        ],
        "rules_out": ["RF positive"],
        "related": ["ankylosing_spondylitis", "rheumatoid_arthritis"],
    },
    "gout": {
        "label": "Gout",
        "category": "musculoskeletal",
        "expected": [
            "gout", "uric acid elevated", "hyperuricemia",
            "podagra", "tophi", "joint swelling",
            "monosodium urate crystals", "acute monoarthritis",
            "red hot swollen joint", "first MTP joint",
        ],
        "rules_out": ["uric acid normal", "no crystals on aspiration"],
        "related": ["renal_insufficiency", "hypertension"],
    },
    "addison_disease": {
        "label": "Addison's Disease",
        "category": "endocrine",
        "expected": [
            "addison", "adrenal insufficiency", "cortisol low",
            "ACTH elevated", "hyperpigmentation", "fatigue",
            "weight loss", "hypotension", "hyponatremia",
            "hyperkalemia", "salt craving",
        ],
        "rules_out": ["cortisol normal", "normal ACTH stimulation test"],
        "related": ["hypothyroidism"],
    },
    "cushing_syndrome": {
        "label": "Cushing's Syndrome",
        "category": "endocrine",
        "expected": [
            "cushing", "cortisol elevated", "moon face",
            "buffalo hump", "central obesity", "striae",
            "hypertension", "hyperglycemia", "osteoporosis",
            "easy bruising", "muscle weakness",
        ],
        "rules_out": ["cortisol normal", "normal dexamethasone suppression"],
        "related": ["diabetes_type_2", "hypertension", "osteoporosis"],
    },
    "wilson_disease": {
        "label": "Wilson's Disease",
        "category": "hepatic",
        "expected": [
            "wilson", "ceruloplasmin low", "copper elevated",
            "Kayser-Fleischer rings", "liver disease",
            "neuropsychiatric symptoms", "tremor", "dysarthria",
            "hepatitis", "cirrhosis", "hemolytic anemia",
        ],
        "rules_out": ["ceruloplasmin normal", "copper normal"],
        "related": ["cirrhosis"],
    },
    "hemochromatosis": {
        "label": "Hemochromatosis",
        "category": "hepatic",
        "expected": [
            "hemochromatosis", "iron overload", "ferritin elevated",
            "transferrin saturation elevated", "bronze skin",
            "diabetes", "liver disease", "cirrhosis",
            "arthropathy", "cardiomyopathy", "HFE gene mutation",
        ],
        "rules_out": ["ferritin normal", "transferrin saturation normal"],
        "related": ["cirrhosis", "diabetes_type_2"],
    },
    "antiphospholipid_syndrome": {
        "label": "Antiphospholipid Syndrome",
        "category": "autoimmune",
        "expected": [
            "antiphospholipid", "lupus anticoagulant",
            "anticardiolipin antibody", "anti-beta2 glycoprotein",
            "recurrent thrombosis", "DVT", "PE",
            "pregnancy loss", "thrombocytopenia", "livedo reticularis",
        ],
        "rules_out": [],
        "related": ["lupus", "deep_vein_thrombosis", "pulmonary_embolism"],
    },
    "ibd": {
        "label": "Inflammatory Bowel Disease",
        "category": "gastrointestinal",
        "expected": [
            "crohn", "ulcerative colitis", "inflammatory bowel",
            "bloody diarrhea", "abdominal pain", "weight loss",
            "fistula", "stricture", "perianal disease",
            "ESR elevated", "CRP elevated", "anemia",
            "calprotectin elevated",
        ],
        "rules_out": ["normal colonoscopy", "calprotectin normal"],
        "related": ["ankylosing_spondylitis", "anemia", "celiac_disease"],
    },
    "irritable_bowel_syndrome": {
        "label": "Irritable Bowel Syndrome",
        "category": "gastrointestinal",
        "expected": [
            "IBS", "irritable bowel", "abdominal pain",
            "bloating", "altered bowel habits", "constipation",
            "diarrhea", "mucus in stool",
        ],
        "rules_out": ["bloody diarrhea", "calprotectin elevated", "weight loss"],
        "related": ["fibromyalgia", "celiac_disease"],
    },
    "gerd": {
        "label": "GERD",
        "category": "gastrointestinal",
        "expected": [
            "GERD", "acid reflux", "heartburn", "regurgitation",
            "esophagitis", "Barrett esophagus", "dysphagia",
            "chronic cough", "hoarseness", "chest pain",
        ],
        "rules_out": ["normal upper endoscopy", "normal pH study"],
        "related": ["asthma"],
    },
    "asthma": {
        "label": "Asthma",
        "category": "pulmonary",
        "expected": [
            "asthma", "wheezing", "bronchospasm",
            "cough", "dyspnea", "chest tightness",
            "reversible airway obstruction", "peak flow reduced",
            "eosinophilia", "allergic rhinitis",
        ],
        "rules_out": ["normal spirometry", "irreversible obstruction"],
        "related": ["copd", "gerd"],
    },
    "sleep_apnea": {
        "label": "Obstructive Sleep Apnea",
        "category": "pulmonary",
        "expected": [
            "sleep apnea", "OSA", "snoring", "daytime sleepiness",
            "witnessed apneas", "AHI elevated", "obesity",
            "hypertension", "morning headache", "fatigue",
            "nocturia",
        ],
        "rules_out": ["normal sleep study", "AHI normal"],
        "related": ["hypertension", "atrial_fibrillation", "diabetes_type_2"],
    },
    "depression": {
        "label": "Major Depression",
        "category": "neurologic",
        "expected": [
            "depression", "depressed mood", "anhedonia",
            "insomnia", "hypersomnia", "weight change",
            "fatigue", "poor concentration", "suicidal ideation",
            "PHQ-9 elevated", "psychomotor retardation",
        ],
        "rules_out": [],
        "related": ["hypothyroidism", "fibromyalgia", "chronic_fatigue_syndrome"],
    },
    "vitamin_d_deficiency": {
        "label": "Vitamin D Deficiency",
        "category": "endocrine",
        "expected": [
            "vitamin D low", "vitamin D deficiency", "25-OH vitamin D low",
            "bone pain", "muscle weakness", "fatigue",
            "osteoporosis", "osteomalacia", "frequent infections",
        ],
        "rules_out": ["vitamin D normal"],
        "related": ["osteoporosis", "depression", "fibromyalgia"],
    },

    # ── Expanded v2.0b: Oncologic ─────────────────────────────

    "breast_cancer": {
        "label": "Breast Cancer",
        "category": "oncologic",
        "expected": [
            "breast mass", "breast lump", "mammogram abnormal",
            "breast biopsy", "BRCA positive", "axillary lymphadenopathy",
            "nipple discharge", "skin retraction", "peau d'orange",
        ],
        "rules_out": ["benign breast biopsy", "mammogram normal"],
        "related": ["ovarian_cancer"],
    },
    "lung_cancer": {
        "label": "Lung Cancer",
        "category": "oncologic",
        "expected": [
            "lung mass", "lung nodule", "lung cancer", "NSCLC", "SCLC",
            "hemoptysis", "chronic cough", "weight loss", "chest pain",
            "pleural effusion", "mediastinal lymphadenopathy", "PET positive",
        ],
        "rules_out": ["benign lung nodule", "stable nodule"],
        "related": ["copd", "pulmonary_embolism"],
    },
    "colorectal_cancer": {
        "label": "Colorectal Cancer",
        "category": "oncologic",
        "expected": [
            "colorectal cancer", "colon cancer", "rectal mass",
            "rectal bleeding", "CEA elevated", "iron deficiency anemia",
            "change in bowel habits", "weight loss", "colonoscopy polyp",
            "adenocarcinoma",
        ],
        "rules_out": ["normal colonoscopy", "CEA normal"],
        "related": ["ibd", "anemia"],
    },
    "prostate_cancer": {
        "label": "Prostate Cancer",
        "category": "oncologic",
        "expected": [
            "prostate cancer", "PSA elevated", "Gleason score",
            "prostate nodule", "urinary obstruction", "bone metastases",
            "hematuria", "elevated alkaline phosphatase",
        ],
        "rules_out": ["PSA normal", "benign prostate biopsy"],
        "related": ["renal_insufficiency"],
    },
    "pancreatic_cancer": {
        "label": "Pancreatic Cancer",
        "category": "oncologic",
        "expected": [
            "pancreatic mass", "pancreatic cancer", "CA 19-9 elevated",
            "painless jaundice", "weight loss", "new onset diabetes",
            "Courvoisier sign", "back pain", "steatorrhea",
        ],
        "rules_out": [],
        "related": ["pancreatitis", "diabetes_type_2"],
    },
    "lymphoma": {
        "label": "Lymphoma",
        "category": "oncologic",
        "expected": [
            "lymphoma", "lymphadenopathy", "night sweats",
            "weight loss", "fever", "B symptoms", "splenomegaly",
            "LDH elevated", "PET avid nodes", "Reed-Sternberg cells",
        ],
        "rules_out": ["benign lymph node biopsy"],
        "related": ["anemia", "sepsis"],
    },
    "leukemia": {
        "label": "Leukemia",
        "category": "oncologic",
        "expected": [
            "leukemia", "WBC markedly elevated", "blast cells",
            "pancytopenia", "bone marrow biopsy", "splenomegaly",
            "fatigue", "easy bruising", "recurrent infections",
            "Philadelphia chromosome", "flow cytometry abnormal",
        ],
        "rules_out": ["normal bone marrow biopsy"],
        "related": ["anemia", "sepsis"],
    },
    "multiple_myeloma": {
        "label": "Multiple Myeloma",
        "category": "oncologic",
        "expected": [
            "multiple myeloma", "M protein", "SPEP abnormal",
            "lytic bone lesions", "hypercalcemia", "anemia",
            "renal insufficiency", "Bence Jones protein",
            "bone marrow plasma cells", "elevated beta-2 microglobulin",
        ],
        "rules_out": ["normal SPEP", "normal bone marrow"],
        "related": ["renal_insufficiency", "anemia", "osteoporosis"],
    },
    "melanoma": {
        "label": "Melanoma",
        "category": "oncologic",
        "expected": [
            "melanoma", "atypical mole", "asymmetric lesion",
            "irregular borders", "color variation", "diameter >6mm",
            "sentinel lymph node positive", "Breslow depth",
            "skin biopsy melanoma", "LDH elevated",
        ],
        "rules_out": ["benign skin biopsy"],
        "related": [],
    },
    "thyroid_cancer": {
        "label": "Thyroid Cancer",
        "category": "oncologic",
        "expected": [
            "thyroid cancer", "thyroid nodule", "FNA suspicious",
            "papillary carcinoma", "thyroglobulin elevated",
            "RAI uptake", "cervical lymphadenopathy", "hoarseness",
            "calcitonin elevated",
        ],
        "rules_out": ["benign FNA", "benign thyroid nodule"],
        "related": ["hypothyroidism", "hyperthyroidism"],
    },

    # ── Expanded v2.0b: More Neurologic ───────────────────────

    "parkinsons_disease": {
        "label": "Parkinson's Disease",
        "category": "neurologic",
        "expected": [
            "parkinson", "tremor", "resting tremor", "bradykinesia",
            "rigidity", "cogwheel rigidity", "shuffling gait",
            "postural instability", "masked facies", "micrographia",
        ],
        "rules_out": ["normal DaTscan"],
        "related": ["depression", "dementia"],
    },
    "dementia": {
        "label": "Dementia / Alzheimer's",
        "category": "neurologic",
        "expected": [
            "dementia", "alzheimer", "memory loss", "cognitive decline",
            "MMSE low", "MoCA low", "hippocampal atrophy",
            "amyloid PET positive", "disorientation", "aphasia",
        ],
        "rules_out": ["normal cognitive testing", "MMSE normal"],
        "related": ["parkinsons_disease", "depression"],
    },
    "als": {
        "label": "Amyotrophic Lateral Sclerosis",
        "category": "neurologic",
        "expected": [
            "ALS", "motor neuron disease", "upper motor neuron signs",
            "lower motor neuron signs", "fasciculations", "muscle wasting",
            "bulbar symptoms", "dysphagia", "dysarthria",
            "EMG denervation", "progressive weakness",
        ],
        "rules_out": ["normal EMG"],
        "related": [],
    },
    "myasthenia_gravis": {
        "label": "Myasthenia Gravis",
        "category": "neurologic",
        "expected": [
            "myasthenia gravis", "acetylcholine receptor antibodies",
            "ptosis", "diplopia", "fatigable weakness",
            "bulbar weakness", "dysphagia", "positive edrophonium test",
            "thymoma", "decremental response on EMG",
        ],
        "rules_out": ["AChR antibodies negative", "normal EMG"],
        "related": [],
    },
    "guillain_barre": {
        "label": "Guillain-Barre Syndrome",
        "category": "neurologic",
        "expected": [
            "guillain barre", "ascending weakness", "areflexia",
            "albuminocytologic dissociation", "CSF protein elevated",
            "nerve conduction abnormal", "respiratory failure",
            "preceding infection", "symmetric weakness",
        ],
        "rules_out": ["normal nerve conduction", "normal CSF"],
        "related": [],
    },
    "epilepsy": {
        "label": "Epilepsy",
        "category": "neurologic",
        "expected": [
            "epilepsy", "seizure", "convulsion", "EEG abnormal",
            "epileptiform discharges", "tonic-clonic", "absence seizure",
            "postictal state", "aura", "anticonvulsant",
        ],
        "rules_out": ["normal EEG", "single provoked seizure"],
        "related": ["stroke"],
    },
    "migraine": {
        "label": "Migraine",
        "category": "neurologic",
        "expected": [
            "migraine", "unilateral headache", "pulsating headache",
            "photophobia", "phonophobia", "nausea with headache",
            "aura", "visual disturbance", "triptan responsive",
        ],
        "rules_out": ["normal MRI brain", "thunderclap headache"],
        "related": ["depression"],
    },
    "meningitis": {
        "label": "Meningitis",
        "category": "infectious",
        "expected": [
            "meningitis", "neck stiffness", "nuchal rigidity",
            "Kernig sign", "Brudzinski sign", "photophobia",
            "fever", "headache", "altered mental status",
            "CSF pleocytosis", "CSF glucose low",
        ],
        "rules_out": ["normal CSF", "normal lumbar puncture"],
        "related": ["sepsis"],
    },

    # ── Expanded v2.0b: More Cardiac ──────────────────────────

    "aortic_stenosis": {
        "label": "Aortic Stenosis",
        "category": "cardiac",
        "expected": [
            "aortic stenosis", "systolic murmur", "crescendo-decrescendo",
            "syncope", "angina", "heart failure", "reduced valve area",
            "aortic valve calcification", "pressure gradient elevated",
        ],
        "rules_out": ["normal echocardiogram", "normal valve area"],
        "related": ["congestive_heart_failure"],
    },
    "pericarditis": {
        "label": "Pericarditis",
        "category": "cardiac",
        "expected": [
            "pericarditis", "pleuritic chest pain", "friction rub",
            "diffuse ST elevation", "PR depression", "pericardial effusion",
            "tamponade", "Beck triad", "troponin mildly elevated",
        ],
        "rules_out": ["normal echocardiogram"],
        "related": ["lupus"],
    },
    "endocarditis": {
        "label": "Endocarditis",
        "category": "infectious",
        "expected": [
            "endocarditis", "vegetation", "blood culture positive",
            "new murmur", "fever", "Osler nodes", "Janeway lesions",
            "splinter hemorrhages", "embolic phenomena", "Duke criteria",
        ],
        "rules_out": ["negative blood cultures", "normal echocardiogram"],
        "related": ["sepsis"],
    },
    "cardiomyopathy": {
        "label": "Cardiomyopathy",
        "category": "cardiac",
        "expected": [
            "cardiomyopathy", "dilated cardiomyopathy", "hypertrophic",
            "ejection fraction reduced", "ventricular dilation",
            "heart failure", "arrhythmia", "dyspnea",
            "BNP elevated", "cardiac MRI abnormal",
        ],
        "rules_out": ["normal echocardiogram", "normal ejection fraction"],
        "related": ["congestive_heart_failure", "atrial_fibrillation"],
    },
    "aortic_dissection": {
        "label": "Aortic Dissection",
        "category": "vascular",
        "expected": [
            "aortic dissection", "tearing chest pain", "back pain",
            "blood pressure differential", "widened mediastinum",
            "intimal flap", "aortic regurgitation", "D-dimer elevated",
        ],
        "rules_out": ["normal CT angiography", "normal aorta"],
        "related": ["hypertension"],
    },

    # ── Expanded v2.0b: More Pulmonary ────────────────────────

    "pulmonary_fibrosis": {
        "label": "Pulmonary Fibrosis / ILD",
        "category": "pulmonary",
        "expected": [
            "pulmonary fibrosis", "interstitial lung disease", "ILD",
            "honeycombing", "ground glass opacities", "restrictive pattern",
            "FVC reduced", "DLCO reduced", "velcro crackles",
            "progressive dyspnea", "clubbing",
        ],
        "rules_out": ["normal HRCT", "normal spirometry"],
        "related": ["rheumatoid_arthritis", "scleroderma"],
    },
    "sarcoidosis": {
        "label": "Sarcoidosis",
        "category": "autoimmune",
        "expected": [
            "sarcoidosis", "bilateral hilar lymphadenopathy",
            "non-caseating granulomas", "ACE elevated",
            "erythema nodosum", "uveitis", "hypercalcemia",
            "pulmonary infiltrates", "fatigue", "arthralgia",
        ],
        "rules_out": ["caseating granulomas", "positive AFB"],
        "related": ["hypercalcemia", "pulmonary_fibrosis"],
    },
    "tuberculosis": {
        "label": "Tuberculosis",
        "category": "infectious",
        "expected": [
            "tuberculosis", "TB", "cavitary lesion", "positive PPD",
            "positive QuantiFERON", "night sweats", "weight loss",
            "chronic cough", "hemoptysis", "AFB positive",
            "apical infiltrate",
        ],
        "rules_out": ["negative PPD", "negative QuantiFERON", "AFB negative"],
        "related": ["pneumonia"],
    },
    "pulmonary_hypertension": {
        "label": "Pulmonary Hypertension",
        "category": "pulmonary",
        "expected": [
            "pulmonary hypertension", "PASP elevated",
            "right heart catheterization elevated", "dyspnea on exertion",
            "right ventricular hypertrophy", "tricuspid regurgitation",
            "peripheral edema", "BNP elevated", "exercise intolerance",
        ],
        "rules_out": ["normal PASP", "normal right heart cath"],
        "related": ["copd", "congestive_heart_failure", "scleroderma"],
    },

    # ── Expanded v2.0b: More Renal ────────────────────────────

    "nephrotic_syndrome": {
        "label": "Nephrotic Syndrome",
        "category": "renal",
        "expected": [
            "nephrotic syndrome", "proteinuria >3.5g", "hypoalbuminemia",
            "edema", "hyperlipidemia", "lipiduria", "oval fat bodies",
            "albumin low", "protein/creatinine ratio elevated",
        ],
        "rules_out": ["proteinuria absent", "albumin normal"],
        "related": ["renal_insufficiency", "deep_vein_thrombosis"],
    },
    "nephrolithiasis": {
        "label": "Kidney Stones",
        "category": "renal",
        "expected": [
            "kidney stone", "nephrolithiasis", "renal calculus",
            "flank pain", "hematuria", "hydronephrosis",
            "ureteral obstruction", "colicky pain", "CT stone",
        ],
        "rules_out": ["no hydronephrosis", "no stone on CT"],
        "related": ["gout", "renal_insufficiency"],
    },
    "polycystic_kidney": {
        "label": "Polycystic Kidney Disease",
        "category": "renal",
        "expected": [
            "polycystic kidney", "PKD", "bilateral renal cysts",
            "enlarged kidneys", "flank pain", "hematuria",
            "hypertension", "family history PKD", "liver cysts",
        ],
        "rules_out": ["normal renal ultrasound"],
        "related": ["renal_insufficiency", "hypertension"],
    },

    # ── Expanded v2.0b: More Autoimmune ───────────────────────

    "scleroderma": {
        "label": "Systemic Sclerosis / Scleroderma",
        "category": "autoimmune",
        "expected": [
            "scleroderma", "systemic sclerosis", "skin thickening",
            "Raynaud phenomenon", "sclerodactyly", "anti-Scl-70",
            "anti-centromere", "GERD", "pulmonary fibrosis",
            "digital ulcers", "calcinosis",
        ],
        "rules_out": ["ANA negative"],
        "related": ["pulmonary_fibrosis", "pulmonary_hypertension"],
    },
    "dermatomyositis": {
        "label": "Dermatomyositis / Polymyositis",
        "category": "autoimmune",
        "expected": [
            "dermatomyositis", "polymyositis", "proximal muscle weakness",
            "CK elevated", "heliotrope rash", "Gottron papules",
            "shawl sign", "anti-Jo-1", "anti-Mi-2",
            "EMG myopathic", "dysphagia",
        ],
        "rules_out": ["CK normal", "normal EMG"],
        "related": ["lung_cancer", "scleroderma"],
    },
    "vasculitis_anca": {
        "label": "ANCA Vasculitis",
        "category": "autoimmune",
        "expected": [
            "vasculitis", "ANCA positive", "c-ANCA", "p-ANCA",
            "granulomatosis polyangiitis", "Wegener",
            "sinusitis", "pulmonary hemorrhage", "glomerulonephritis",
            "skin purpura", "mononeuritis multiplex",
        ],
        "rules_out": ["ANCA negative"],
        "related": ["renal_insufficiency"],
    },
    "behcet_disease": {
        "label": "Behcet's Disease",
        "category": "autoimmune",
        "expected": [
            "behcet", "oral ulcers", "genital ulcers",
            "uveitis", "pathergy", "skin lesions",
            "arthritis", "deep vein thrombosis", "CNS involvement",
        ],
        "rules_out": [],
        "related": ["deep_vein_thrombosis", "lupus"],
    },

    # ── Expanded v2.0b: More Hematologic ──────────────────────

    "polycythemia_vera": {
        "label": "Polycythemia Vera",
        "category": "hematologic",
        "expected": [
            "polycythemia vera", "hemoglobin elevated", "hematocrit elevated",
            "JAK2 positive", "erythrocytosis", "splenomegaly",
            "pruritus after bathing", "thrombosis", "headache",
        ],
        "rules_out": ["JAK2 negative", "hemoglobin normal"],
        "related": ["deep_vein_thrombosis"],
    },
    "sickle_cell": {
        "label": "Sickle Cell Disease",
        "category": "hematologic",
        "expected": [
            "sickle cell", "hemoglobin S", "vaso-occlusive crisis",
            "chronic hemolytic anemia", "splenic sequestration",
            "acute chest syndrome", "dactylitis", "avascular necrosis",
            "reticulocyte elevated", "sickle cells on smear",
        ],
        "rules_out": ["normal hemoglobin electrophoresis"],
        "related": ["anemia", "pulmonary_embolism"],
    },
    "ttp": {
        "label": "Thrombotic Thrombocytopenic Purpura",
        "category": "hematologic",
        "expected": [
            "TTP", "thrombocytopenia", "microangiopathic hemolytic anemia",
            "schistocytes", "LDH elevated", "renal impairment",
            "neurologic changes", "fever", "ADAMTS13 deficient",
        ],
        "rules_out": ["ADAMTS13 normal", "no schistocytes"],
        "related": ["anemia", "renal_insufficiency"],
    },
    "hemophilia": {
        "label": "Hemophilia",
        "category": "hematologic",
        "expected": [
            "hemophilia", "factor VIII deficiency", "factor IX deficiency",
            "prolonged PTT", "hemarthrosis", "easy bruising",
            "bleeding episodes", "family history bleeding disorder",
        ],
        "rules_out": ["normal PTT", "normal factor levels"],
        "related": ["deep_vein_thrombosis"],
    },

    # ── Expanded v2.0b: More Infectious ───────────────────────

    "hiv": {
        "label": "HIV / AIDS",
        "category": "infectious",
        "expected": [
            "HIV", "AIDS", "CD4 low", "viral load detectable",
            "opportunistic infection", "weight loss", "lymphadenopathy",
            "oral candidiasis", "Kaposi sarcoma", "PCP pneumonia",
        ],
        "rules_out": ["HIV negative", "undetectable viral load"],
        "related": ["tuberculosis", "lymphoma"],
    },
    "hepatitis_b": {
        "label": "Hepatitis B",
        "category": "infectious",
        "expected": [
            "hepatitis B", "HBsAg positive", "HBV DNA detectable",
            "ALT elevated", "AST elevated", "jaundice",
            "cirrhosis", "hepatocellular carcinoma risk",
        ],
        "rules_out": ["HBsAg negative", "HBV DNA undetectable"],
        "related": ["cirrhosis"],
    },
    "hepatitis_c": {
        "label": "Hepatitis C",
        "category": "infectious",
        "expected": [
            "hepatitis C", "HCV antibody positive", "HCV RNA detectable",
            "ALT elevated", "cirrhosis", "cryoglobulinemia",
            "liver fibrosis", "genotype",
        ],
        "rules_out": ["HCV antibody negative", "HCV RNA undetectable"],
        "related": ["cirrhosis"],
    },
    "lyme_disease": {
        "label": "Lyme Disease",
        "category": "infectious",
        "expected": [
            "lyme disease", "erythema migrans", "bull's eye rash",
            "tick bite", "arthritis", "facial palsy",
            "Lyme antibody positive", "Western blot positive",
            "fatigue", "myalgia",
        ],
        "rules_out": ["Lyme antibody negative"],
        "related": ["rheumatoid_arthritis", "fibromyalgia"],
    },

    # ── Expanded v2.0b: More GI ───────────────────────────────

    "diverticulitis": {
        "label": "Diverticulitis",
        "category": "gastrointestinal",
        "expected": [
            "diverticulitis", "left lower quadrant pain",
            "CT diverticulitis", "fever", "leukocytosis",
            "pericolic fat stranding", "diverticulosis",
            "change in bowel habits",
        ],
        "rules_out": ["normal CT abdomen"],
        "related": ["colorectal_cancer"],
    },
    "peptic_ulcer": {
        "label": "Peptic Ulcer Disease",
        "category": "gastrointestinal",
        "expected": [
            "peptic ulcer", "gastric ulcer", "duodenal ulcer",
            "epigastric pain", "H. pylori positive", "GI bleeding",
            "melena", "hematemesis", "NSAID use",
        ],
        "rules_out": ["normal endoscopy", "H. pylori negative"],
        "related": ["gerd"],
    },
    "cholecystitis": {
        "label": "Cholecystitis",
        "category": "gastrointestinal",
        "expected": [
            "cholecystitis", "gallstones", "right upper quadrant pain",
            "Murphy sign", "gallbladder wall thickening",
            "pericholecystic fluid", "fever", "leukocytosis",
        ],
        "rules_out": ["normal gallbladder ultrasound"],
        "related": ["pancreatitis"],
    },

    # ── Expanded v2.0b: More Endocrine ────────────────────────

    "pheochromocytoma": {
        "label": "Pheochromocytoma",
        "category": "endocrine",
        "expected": [
            "pheochromocytoma", "catecholamines elevated",
            "metanephrines elevated", "adrenal mass",
            "episodic hypertension", "headache", "diaphoresis",
            "palpitations", "tachycardia",
        ],
        "rules_out": ["metanephrines normal", "no adrenal mass"],
        "related": ["hypertension"],
    },
    "hyperparathyroidism": {
        "label": "Hyperparathyroidism",
        "category": "endocrine",
        "expected": [
            "hyperparathyroidism", "calcium elevated", "PTH elevated",
            "kidney stones", "bone pain", "osteoporosis",
            "abdominal pain", "psychiatric symptoms",
            "parathyroid adenoma",
        ],
        "rules_out": ["calcium normal", "PTH normal"],
        "related": ["osteoporosis", "nephrolithiasis"],
    },
    "pcos": {
        "label": "Polycystic Ovary Syndrome",
        "category": "endocrine",
        "expected": [
            "PCOS", "polycystic ovaries", "oligomenorrhea",
            "amenorrhea", "hirsutism", "acne", "insulin resistance",
            "testosterone elevated", "LH/FSH ratio elevated", "obesity",
        ],
        "rules_out": ["normal testosterone", "regular menses"],
        "related": ["diabetes_type_2", "metabolic_syndrome"],
    },
    "acromegaly": {
        "label": "Acromegaly",
        "category": "endocrine",
        "expected": [
            "acromegaly", "growth hormone elevated", "IGF-1 elevated",
            "pituitary adenoma", "coarsened features",
            "enlarged hands and feet", "jaw enlargement",
            "visual field defect", "carpal tunnel", "sleep apnea",
        ],
        "rules_out": ["IGF-1 normal", "normal pituitary MRI"],
        "related": ["diabetes_type_2", "sleep_apnea"],
    },
    "diabetes_insipidus": {
        "label": "Diabetes Insipidus",
        "category": "endocrine",
        "expected": [
            "diabetes insipidus", "polyuria", "polydipsia",
            "urine specific gravity low", "urine osmolality low",
            "serum osmolality elevated", "hypernatremia",
            "water deprivation test abnormal",
        ],
        "rules_out": ["normal urine osmolality", "normal serum sodium"],
        "related": [],
    },

    # ── Expanded v2.0b: More Musculoskeletal ──────────────────

    "osteoarthritis": {
        "label": "Osteoarthritis",
        "category": "musculoskeletal",
        "expected": [
            "osteoarthritis", "joint space narrowing", "osteophytes",
            "crepitus", "morning stiffness <30 min", "joint pain",
            "Heberden nodes", "Bouchard nodes", "weight bearing pain",
        ],
        "rules_out": ["RF positive", "inflammatory markers elevated"],
        "related": ["obesity"],
    },
    "polymyalgia_rheumatica": {
        "label": "Polymyalgia Rheumatica",
        "category": "musculoskeletal",
        "expected": [
            "polymyalgia rheumatica", "shoulder girdle pain",
            "hip girdle pain", "morning stiffness >1 hour",
            "ESR markedly elevated", "CRP elevated",
            "age >50", "rapid response to steroids",
        ],
        "rules_out": ["ESR normal", "age <50"],
        "related": ["giant_cell_arteritis"],
    },
    "giant_cell_arteritis": {
        "label": "Giant Cell Arteritis",
        "category": "vascular",
        "expected": [
            "giant cell arteritis", "temporal arteritis",
            "temporal headache", "jaw claudication",
            "visual loss", "ESR markedly elevated",
            "temporal artery biopsy positive", "scalp tenderness",
        ],
        "rules_out": ["ESR normal", "negative temporal biopsy"],
        "related": ["polymyalgia_rheumatica", "stroke"],
    },

    # ── Expanded v2.0b: Psychiatric ───────────────────────────

    "bipolar_disorder": {
        "label": "Bipolar Disorder",
        "category": "psychiatric",
        "expected": [
            "bipolar", "mania", "hypomania", "mood episodes",
            "grandiosity", "decreased sleep", "pressured speech",
            "racing thoughts", "depressive episodes", "mood stabilizer",
        ],
        "rules_out": [],
        "related": ["depression"],
    },
    "anxiety_disorder": {
        "label": "Generalized Anxiety Disorder",
        "category": "psychiatric",
        "expected": [
            "anxiety", "generalized anxiety", "GAD-7 elevated",
            "excessive worry", "restlessness", "muscle tension",
            "insomnia", "difficulty concentrating", "palpitations",
        ],
        "rules_out": [],
        "related": ["depression", "hyperthyroidism"],
    },

    # ── Expanded v2.0b: Rare but Important ────────────────────

    "amyloidosis": {
        "label": "Amyloidosis",
        "category": "autoimmune",
        "expected": [
            "amyloidosis", "amyloid deposits", "Congo red positive",
            "nephrotic syndrome", "restrictive cardiomyopathy",
            "macroglossia", "hepatomegaly", "neuropathy",
            "proteinuria", "SPEP abnormal",
        ],
        "rules_out": ["negative Congo red stain"],
        "related": ["multiple_myeloma", "congestive_heart_failure"],
    },
    "porphyria": {
        "label": "Porphyria",
        "category": "genetic",
        "expected": [
            "porphyria", "porphobilinogen elevated", "ALA elevated",
            "abdominal pain", "neuropathy", "psychiatric symptoms",
            "photosensitivity", "blistering skin",
            "dark urine", "port-wine urine",
        ],
        "rules_out": ["porphyrins normal"],
        "related": [],
    },
    "marfan_syndrome": {
        "label": "Marfan Syndrome",
        "category": "genetic",
        "expected": [
            "marfan", "tall stature", "arachnodactyly",
            "lens subluxation", "aortic root dilation",
            "mitral valve prolapse", "pectus excavatum",
            "scoliosis", "FBN1 mutation", "joint hypermobility",
        ],
        "rules_out": ["normal aortic root", "FBN1 negative"],
        "related": ["ehlers_danlos", "aortic_dissection"],
    },
    "hemolytic_uremic_syndrome": {
        "label": "Hemolytic Uremic Syndrome",
        "category": "hematologic",
        "expected": [
            "HUS", "hemolytic uremic syndrome", "hemolytic anemia",
            "thrombocytopenia", "renal failure", "schistocytes",
            "bloody diarrhea", "E. coli O157:H7", "LDH elevated",
        ],
        "rules_out": ["no schistocytes", "normal renal function"],
        "related": ["ttp", "renal_insufficiency"],
    },
    "mastocytosis": {
        "label": "Systemic Mastocytosis",
        "category": "hematologic",
        "expected": [
            "mastocytosis", "tryptase markedly elevated",
            "urticaria pigmentosa", "mast cell infiltration",
            "anaphylaxis", "bone marrow mast cells",
            "KIT D816V mutation", "hepatosplenomegaly",
        ],
        "rules_out": ["tryptase normal", "no mast cell infiltration"],
        "related": ["mast_cell_activation"],
    },
}

# Severity weight multipliers for scoring
SEVERITY_WEIGHTS = {
    "critical": 3.0,
    "high": 2.0,
    "moderate": 1.5,
    "low": 1.0,
    "info": 0.5,
}

# Category colors for frontend rendering
CATEGORY_COLORS = {
    "cardiac": "#e74c3c",
    "pulmonary": "#3498db",
    "hepatic": "#f39c12",
    "endocrine": "#9b59b6",
    "renal": "#1abc9c",
    "hematologic": "#e67e22",
    "vascular": "#c0392b",
    "neurologic": "#8e44ad",
    "autoimmune": "#2ecc71",
    "infectious": "#d35400",
    "gastrointestinal": "#f1c40f",
    "musculoskeletal": "#7f8c8d",
    "oncologic": "#c0392b",
    "psychiatric": "#a29bfe",
    "genetic": "#fd79a8",
    "dermatologic": "#fdcb6e",
    "ophthalmologic": "#74b9ff",
    "other": "#95a5a6",
}


class SnowballEngine:
    """
    Graph-theory differential diagnosis engine.

    Builds a network of patient findings -> candidate conditions,
    scored by how many expected findings match. Designed for
    visualization as a D3 force-directed graph.
    """

    def __init__(self, api_key: str = None, demographics: dict = None):
        self.condition_db = CONDITION_DB
        self._demographics = demographics or {}
        self._matcher = None

        # Initialize AI matcher if available
        try:
            from src.analysis.ai_matcher import AIMatcher
            self._matcher = AIMatcher(api_key=api_key)
        except ImportError:
            pass

    def analyze(self, patient_data: dict) -> dict:
        """
        Run snowball analysis on patient data.

        Args:
            patient_data: dict with keys like 'diagnoses', 'medications',
                         'labs', 'flags', 'findings' - each a list of
                         dicts with at least a 'text' or 'name' field.

        Returns:
            dict with 'nodes' and 'edges' for D3 force graph,
            plus 'ranked_conditions' sorted by confidence.
        """
        # Step 1: Seed - collect all patient text into a searchable corpus
        corpus = self._build_corpus(patient_data)

        # Step 2: Match - score each condition against corpus
        scored = {}
        for cond_id, cond in self.condition_db.items():
            result = self._score_condition(cond_id, cond, corpus)
            if result["matched_count"] > 0:
                scored[cond_id] = result

        # Step 2b: Demographic weighting — adjust confidence by age/sex
        if self._matcher and self._demographics:
            age = self._demographics.get("age")
            sex = self._demographics.get("sex")
            if age or sex:
                for cond_id, result in scored.items():
                    weight = self._matcher.assess_demographic_weight(
                        cond_id, age=age, sex=sex
                    )
                    if weight != 1.0:
                        result["confidence"] = round(
                            result["confidence"] * weight, 3
                        )
                        result["demographic_weight"] = round(weight, 2)

        # Step 2c: LLM Discovery — find conditions not in curated DB
        if self._matcher:
            discovered = self._discover_conditions(corpus, scored)
            if discovered:
                # Apply demographic weighting to discovered conditions too
                if self._demographics:
                    age = self._demographics.get("age")
                    sex = self._demographics.get("sex")
                    if age or sex:
                        for cond_id, result in discovered.items():
                            weight = self._matcher.assess_demographic_weight(
                                cond_id, age=age, sex=sex
                            )
                            if weight != 1.0:
                                result["confidence"] = round(
                                    result["confidence"] * weight, 3
                                )
                                result["demographic_weight"] = round(weight, 2)
                scored.update(discovered)

        # Step 3: Expand - find related conditions and missing findings
        expanded = self._expand_graph(scored)

        # Step 4: Rank
        ranked = sorted(
            expanded.values(),
            key=lambda x: x["confidence"],
            reverse=True,
        )

        # Step 5: Build graph
        graph = self._build_graph(corpus, expanded)
        graph["ranked_conditions"] = ranked
        graph["discovery_count"] = len(
            [r for r in ranked if r.get("is_discovered")]
        )

        return graph

    def _build_corpus(self, patient_data: dict) -> list:
        """
        Flatten all patient data into a list of finding dicts,
        each with 'text', 'type', and 'severity'.
        """
        corpus = []

        # Diagnoses
        for dx in patient_data.get("diagnoses", []):
            text = dx.get("text", dx.get("name", ""))
            if text:
                corpus.append({
                    "text": text.lower(),
                    "type": "diagnosis",
                    "severity": dx.get("severity", "moderate"),
                    "original": text,
                })

        # Labs
        for lab in patient_data.get("labs", []):
            text = lab.get("text", lab.get("name", ""))
            if text:
                corpus.append({
                    "text": text.lower(),
                    "type": "lab",
                    "severity": lab.get("severity", "info"),
                    "original": text,
                })

        # Flags
        for flag in patient_data.get("flags", []):
            text = flag.get("text", flag.get("name", ""))
            if text:
                corpus.append({
                    "text": text.lower(),
                    "type": "flag",
                    "severity": flag.get("severity", "moderate"),
                    "original": text,
                })

        # Generic findings
        for finding in patient_data.get("findings", []):
            text = finding.get("text", finding.get("name", ""))
            if text:
                corpus.append({
                    "text": text.lower(),
                    "type": finding.get("type", "finding"),
                    "severity": finding.get("severity", "moderate"),
                    "original": text,
                })

        # Medications (presence implies underlying condition)
        for med in patient_data.get("medications", []):
            text = med.get("text", med.get("name", ""))
            if text:
                corpus.append({
                    "text": text.lower(),
                    "type": "medication",
                    "severity": "info",
                    "original": text,
                })

        # Symptoms from the symptom logger
        timeline = patient_data.get("clinical_timeline", {})
        sev_map = {"high": "high", "mid": "moderate", "low": "low"}

        for symptom in timeline.get("symptoms", []):
            name = symptom.get("symptom_name", "")
            episodes = symptom.get("episodes", [])
            if not name:
                continue

            # Symptom name as a finding (weight by episode count)
            sev = "moderate"
            if len(episodes) >= 10:
                sev = "high"
            elif len(episodes) >= 5:
                sev = "moderate"
            elif len(episodes) >= 1:
                sev = "low"

            corpus.append({
                "text": name.lower(),
                "type": "symptom",
                "severity": sev,
                "original": name,
            })

            # Episode descriptions may contain additional clinical terms
            for ep in episodes:
                desc = (ep.get("description") or "").strip()
                if desc and len(desc) > 10:
                    corpus.append({
                        "text": desc.lower(),
                        "type": "symptom_detail",
                        "severity": sev_map.get(ep.get("intensity", "mid"), "moderate"),
                        "original": desc,
                    })

            # Counter-evidence: penalize conditions the data contradicts
            for counter in symptom.get("counter_definitions", []):
                if counter.get("archived"):
                    continue
                claim = (counter.get("doctor_claim") or "").lower().strip()
                if not claim:
                    continue

                # Compute counter stats to see if the claim is disproven
                measure_type = counter.get("measure_type", "scale")
                counter_id = counter.get("counter_id", "")
                values = []

                for ep in episodes:
                    cv = ep.get("counter_values", {})
                    val = cv.get(counter_id)
                    if val is not None:
                        if measure_type == "scale":
                            try:
                                values.append(float(val))
                            except (ValueError, TypeError):
                                pass
                        elif measure_type == "yes_no":
                            values.append(1 if val else 0)

                if values:
                    avg = sum(values) / len(values)
                    # Scale: avg < 2.5/5 means claim is weakly supported
                    # Yes/No: >60% "No" means claim is weakly supported
                    disproven = False
                    if measure_type == "scale" and avg < 2.5:
                        disproven = True
                    elif measure_type == "yes_no" and avg < 0.4:
                        disproven = True

                    if disproven:
                        corpus.append({
                            "text": f"counter_evidence_against_{claim}",
                            "type": "counter_evidence",
                            "severity": "info",
                            "original": f"Patient data contradicts: {claim} (avg {avg:.1f})",
                        })

        # Imaging findings (from MONAI + radiomics)
        for study in timeline.get("imaging", []):
            for finding in study.get("findings", []):
                desc = finding.get("description", "")
                if desc:
                    corpus.append({
                        "text": desc.lower(),
                        "type": "imaging",
                        "severity": "moderate",
                        "original": desc,
                    })

                # Radiomic threshold flags boost severity
                radiomic = finding.get("radiomic_features", {})
                if radiomic:
                    for flag in radiomic.get("threshold_flags", []):
                        corpus.append({
                            "text": flag.get("message", "").lower(),
                            "type": "radiomic_flag",
                            "severity": flag.get("level", "moderate"),
                            "original": flag.get("message", ""),
                        })

        return corpus

    def _score_condition(
        self, cond_id: str, cond: dict, corpus: list
    ) -> dict:
        """Score how well a condition matches the patient corpus.

        Two-tier matching:
          Tier 1: Fast substring match (always runs)
          Tier 2: AI synonym-aware match via AIMatcher (when available)
        """
        expected = cond["expected"]
        rules_out = cond.get("rules_out", [])

        matched = []
        matched_findings = []
        missing = []
        ruled_out = False

        # Check expected findings — two-tier matching
        for pattern in expected:
            pattern_lower = pattern.lower()
            found = False

            # Tier 1: Direct substring match (fast path)
            for item in corpus:
                if pattern_lower in item["text"]:
                    found = True
                    matched.append(pattern)
                    matched_findings.append(item)
                    break

            # Tier 2: AI synonym-aware match (when Tier 1 misses)
            if not found and self._matcher:
                hit = self._matcher.corpus_match(pattern, corpus)
                if hit:
                    found = True
                    matched.append(pattern)
                    matched_findings.append(hit)

            if not found:
                missing.append(pattern)

        # Check rule-outs — also two-tier
        for pattern in rules_out:
            pattern_lower = pattern.lower()

            # Tier 1: substring
            for item in corpus:
                if pattern_lower in item["text"]:
                    ruled_out = True
                    break

            # Tier 2: synonym match for rule-outs
            if not ruled_out and self._matcher:
                hit = self._matcher.corpus_match(pattern, corpus)
                if hit:
                    ruled_out = True

        # Check counter-evidence: penalize if patient data contradicts
        # a claimed cause that maps to this condition
        counter_penalty = 1.0
        cond_label_lower = cond["label"].lower()
        cond_terms = [cond_label_lower] + [p.lower() for p in expected[:5]]
        for item in corpus:
            if item["type"] == "counter_evidence":
                # Check if this counter-evidence relates to this condition
                claim = item["text"].replace("counter_evidence_against_", "")
                for term in cond_terms:
                    if claim in term or term in claim:
                        counter_penalty *= 0.6  # reduce confidence
                        break

        # Calculate confidence
        if len(expected) == 0:
            ratio = 0.0
        else:
            ratio = len(matched) / len(expected)

        # Weight by severity of matched findings
        severity_boost = 0.0
        for f in matched_findings:
            severity_boost += SEVERITY_WEIGHTS.get(f["severity"], 1.0)

        if matched_findings:
            severity_boost /= len(matched_findings)
        else:
            severity_boost = 1.0

        confidence = ratio * severity_boost * counter_penalty

        # Penalize if ruled out
        if ruled_out:
            confidence *= 0.2

        return {
            "id": cond_id,
            "label": cond["label"],
            "category": cond["category"],
            "confidence": round(confidence, 3),
            "matched": matched,
            "matched_count": len(matched),
            "expected_count": len(expected),
            "missing": missing,
            "ruled_out": ruled_out,
            "related": cond.get("related", []),
            "color": CATEGORY_COLORS.get(cond["category"], "#95a5a6"),
        }

    def _expand_graph(self, scored: dict) -> dict:
        """
        Expand the graph by adding related conditions that aren't
        already scored, with a lower baseline confidence.
        """
        expanded = dict(scored)

        # For top-scoring conditions, add their related conditions
        top = sorted(
            scored.values(),
            key=lambda x: x["confidence"],
            reverse=True,
        )[:5]

        for result in top:
            for related_id in result["related"]:
                if related_id not in expanded and related_id in self.condition_db:
                    cond = self.condition_db[related_id]
                    expanded[related_id] = {
                        "id": related_id,
                        "label": cond["label"],
                        "category": cond["category"],
                        "confidence": round(result["confidence"] * 0.3, 3),
                        "matched": [],
                        "matched_count": 0,
                        "expected_count": len(cond["expected"]),
                        "missing": cond["expected"][:5],
                        "ruled_out": False,
                        "related": cond.get("related", []),
                        "color": CATEGORY_COLORS.get(
                            cond["category"], "#95a5a6"
                        ),
                        "is_expanded": True,
                    }

        return expanded

    def _build_graph(self, corpus: list, conditions: dict) -> dict:
        """Build D3-compatible node/edge graph."""
        nodes = []
        edges = []
        node_ids = set()

        # Add finding nodes (only those that matched something)
        matched_texts = set()
        for cond in conditions.values():
            for m in cond["matched"]:
                matched_texts.add(m.lower())

        for item in corpus:
            for mt in matched_texts:
                if mt in item["text"]:
                    node_id = f"finding_{item['original'][:40]}"
                    if node_id not in node_ids:
                        node_ids.add(node_id)
                        nodes.append({
                            "id": node_id,
                            "label": item["original"][:50],
                            "type": "finding",
                            "subtype": item["type"],
                            "severity": item["severity"],
                            "radius": 8,
                        })
                    break

        # Add condition nodes
        for cond_id, cond in conditions.items():
            node_id = f"condition_{cond_id}"
            node_ids.add(node_id)

            # Size by confidence
            radius = max(12, min(30, int(cond["confidence"] * 30)))

            nodes.append({
                "id": node_id,
                "label": cond["label"],
                "type": "condition",
                "category": cond["category"],
                "confidence": cond["confidence"],
                "matched_count": cond["matched_count"],
                "expected_count": cond["expected_count"],
                "missing": cond["missing"][:5],
                "ruled_out": cond.get("ruled_out", False),
                "is_expanded": cond.get("is_expanded", False),
                "color": cond["color"],
                "radius": radius,
            })

            # Add edges from matched findings to this condition
            for m in cond["matched"]:
                m_lower = m.lower()
                for item in corpus:
                    if m_lower in item["text"]:
                        finding_id = f"finding_{item['original'][:40]}"
                        if finding_id in node_ids:
                            edges.append({
                                "source": finding_id,
                                "target": node_id,
                                "weight": SEVERITY_WEIGHTS.get(
                                    item["severity"], 1.0
                                ),
                                "label": m,
                            })
                        break

            # Add edges between related conditions
            for related_id in cond["related"]:
                related_node = f"condition_{related_id}"
                if related_node in node_ids:
                    edge_id = tuple(sorted([node_id, related_node]))
                    edges.append({
                        "source": node_id,
                        "target": related_node,
                        "weight": 0.5,
                        "label": "associated",
                        "dashed": True,
                    })

        return {"nodes": nodes, "edges": edges}

    # ── LLM Condition Discovery ──────────────────────────────────

    def _discover_conditions(self, corpus: list, already_scored: dict) -> dict:
        """Use LLM to discover conditions not in the curated database.

        Sends the patient's finding corpus to Gemini (or Ollama fallback)
        and asks for additional differential diagnoses beyond what the
        curated CONDITION_DB already covers.

        Returns a dict of condition_id -> scored result dicts in the same
        format as _score_condition() output, ready to merge.
        """
        if not self._matcher or not self._matcher._api_key:
            # Try Ollama as fallback even without Gemini key
            return self._discover_via_ollama(corpus, already_scored)

        # Build a summary of patient findings for the prompt
        finding_texts = []
        for item in corpus:
            if item["type"] not in ("counter_evidence",):
                finding_texts.append(item["original"])

        if not finding_texts:
            return {}

        # Build list of already-identified conditions to exclude
        already_labels = [r["label"] for r in already_scored.values()]

        prompt = (
            "You are a clinical decision support system. Given these patient "
            "findings, suggest additional differential diagnoses that a "
            "clinician should consider.\n\n"
            f"Patient findings:\n"
            + "\n".join(f"- {f}" for f in finding_texts[:50])
            + "\n\n"
            f"Already considered: {', '.join(already_labels[:20])}\n\n"
            "Return a JSON array of objects. Each object must have:\n"
            '  "id": snake_case unique identifier,\n'
            '  "label": human-readable condition name,\n'
            '  "category": one of (cardiac, pulmonary, hepatic, endocrine, '
            "renal, hematologic, vascular, neurologic, autoimmune, "
            "infectious, gastrointestinal, musculoskeletal, oncologic, "
            "psychiatric, dermatologic, ophthalmologic, genetic, other),\n"
            '  "expected": array of 5-15 findings/symptoms/labs for this condition,\n'
            '  "rules_out": array of 1-3 findings that make it unlikely,\n'
            '  "matched": array of which patient findings match (from the list above),\n'
            '  "confidence_reason": brief explanation of why this condition fits\n\n'
            "IMPORTANT:\n"
            "- Only suggest conditions NOT already in the considered list\n"
            "- Include rare and uncommon conditions if the findings support them\n"
            "- Include conditions from ALL specialties\n"
            "- Rank by clinical relevance to the patient's specific findings\n"
            "- Return 5-15 conditions, prioritizing quality over quantity\n"
            "- Return ONLY valid JSON, no explanation outside the array"
        )

        discovered = {}

        # Try Gemini first
        try:
            import json
            import google.generativeai as genai

            genai.configure(api_key=self._matcher._api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")

            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )

            conditions = json.loads(response.text)
            if isinstance(conditions, list):
                discovered = self._parse_discovered(conditions, corpus)

        except Exception as e:
            import logging
            logging.getLogger("CIH-Snowball").debug(
                "Gemini discovery failed: %s", e
            )
            # Fall back to Ollama
            discovered = self._discover_via_ollama(corpus, already_scored)

        return discovered

    def _discover_via_ollama(self, corpus: list, already_scored: dict) -> dict:
        """Fallback: discover conditions via local Ollama/Qwen."""
        finding_texts = [
            item["original"] for item in corpus
            if item["type"] not in ("counter_evidence",)
        ]
        if not finding_texts:
            return {}

        already_labels = [r["label"] for r in already_scored.values()]

        prompt = (
            "Given these findings, suggest 5-10 additional differential "
            "diagnoses not in this list: "
            f"{', '.join(already_labels[:15])}.\n"
            f"Findings: {', '.join(finding_texts[:30])}\n"
            "Return JSON array with objects having: id, label, category, "
            "expected (array), rules_out (array), matched (array)."
        )

        try:
            import json
            import urllib.request

            payload = json.dumps({
                "model": "qwen2.5:32b",
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }).encode()

            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                raw = json.loads(data.get("response", "[]"))

                # Handle both array and object-with-array responses
                if isinstance(raw, dict):
                    for v in raw.values():
                        if isinstance(v, list):
                            raw = v
                            break

                if isinstance(raw, list):
                    return self._parse_discovered(raw, corpus)

        except Exception:
            pass

        return {}

    def _parse_discovered(self, conditions: list, corpus: list) -> dict:
        """Parse LLM-discovered conditions into scored result format.

        Takes the raw LLM output and converts it to the same dict format
        that _score_condition() produces, so it can merge seamlessly.
        """
        discovered = {}

        for cond in conditions:
            if not isinstance(cond, dict):
                continue

            cond_id = cond.get("id", "")
            label = cond.get("label", "")
            if not cond_id or not label:
                continue

            # Sanitize ID
            cond_id = re.sub(r"[^a-z0-9_]", "_", cond_id.lower().strip())

            # Skip if already in curated DB
            if cond_id in self.condition_db:
                continue

            category = cond.get("category", "other").lower()
            expected = cond.get("expected", [])
            rules_out = cond.get("rules_out", [])
            llm_matched = cond.get("matched", [])

            # Re-verify matches against actual corpus (don't trust LLM blindly)
            verified_matched = []
            verified_findings = []
            for pattern in (llm_matched or expected):
                if not isinstance(pattern, str):
                    continue
                pattern_lower = pattern.lower().strip()

                # Check corpus directly
                found = False
                for item in corpus:
                    if pattern_lower in item["text"] or item["text"] in pattern_lower:
                        found = True
                        verified_matched.append(pattern)
                        verified_findings.append(item)
                        break

                # Also try synonym matching if available
                if not found and self._matcher:
                    hit = self._matcher.corpus_match(pattern, corpus)
                    if hit:
                        verified_matched.append(pattern)
                        verified_findings.append(hit)

            # Only include if at least 1 verified match
            if not verified_matched:
                continue

            # Calculate confidence (same formula as curated conditions)
            total_expected = max(len(expected), 1)
            ratio = len(verified_matched) / total_expected

            severity_boost = 0.0
            for f in verified_findings:
                severity_boost += SEVERITY_WEIGHTS.get(f["severity"], 1.0)
            if verified_findings:
                severity_boost /= len(verified_findings)
            else:
                severity_boost = 1.0

            # LLM-discovered conditions get a small discount (0.85x) since
            # they haven't been clinically curated
            confidence = round(ratio * severity_boost * 0.85, 3)

            # Check rule-outs
            ruled_out = False
            for pattern in rules_out:
                if not isinstance(pattern, str):
                    continue
                pattern_lower = pattern.lower().strip()
                for item in corpus:
                    if pattern_lower in item["text"]:
                        ruled_out = True
                        break

            if ruled_out:
                confidence *= 0.2

            discovered[cond_id] = {
                "id": cond_id,
                "label": label,
                "category": category,
                "confidence": confidence,
                "matched": verified_matched,
                "matched_count": len(verified_matched),
                "expected_count": total_expected,
                "missing": [
                    p for p in expected
                    if isinstance(p, str) and p not in verified_matched
                ][:5],
                "ruled_out": ruled_out,
                "related": [],
                "color": CATEGORY_COLORS.get(category, "#95a5a6"),
                "is_discovered": True,  # flag for frontend styling
                "confidence_reason": cond.get("confidence_reason", ""),
            }

        return discovered
