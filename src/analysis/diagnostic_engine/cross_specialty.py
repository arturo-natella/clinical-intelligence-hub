"""
Clinical Intelligence Hub — Cross-Specialty Correlation Engine

The "House M.D." module. Scans the patient's complete profile for
fragmented symptoms, diagnoses, and lab findings spread across
specialties to identify hidden systemic diseases.

Refactored from SQLite to profile_data dict input.
Expanded from 5 → 22 systemic disease triads.
Includes symptom logger data in the analysis corpus.
Optional Gemini/Ollama layer for unexpected pattern discovery.

Results feed into:
  - Cross-Disciplinary view
  - Doctor Visit Prep
  - Snowball (as additional context)
"""

import logging
from typing import Optional

logger = logging.getLogger("CIH-CrossSpecialty")


# ── Systemic Disease Triads ──────────────────────────────────
#
# 22 conditions that present across multiple seemingly unrelated
# specialties.  Each entry has:
#   specialties      – which departments might each see a piece
#   symptoms         – terms to match in diagnoses, symptoms, findings
#   lab_markers      – terms to match in labs (flag-independent)
#   description      – plain-English explanation for the patient
#   diagnostic_source – formal criteria / guideline this entry is based on

SYSTEMIC_DISEASE_TRIADS = {
    # ── Original 5 ────────────────────────────────────────
    "Sarcoidosis": {
        "specialties": ["Pulmonology", "Ophthalmology", "Dermatology"],
        "symptoms": [
            "granuloma", "dry cough", "uveitis", "erythema nodosum",
            "lymphadenopathy", "hilar lymph", "bilateral hilar",
        ],
        "lab_markers": ["ace level", "hypercalcemia", "angiotensin converting"],
        "description": (
            "An inflammatory disease that forms tiny clumps of cells "
            "(granulomas) in multiple organs — most commonly the lungs, "
            "skin, and eyes."
        ),
        "diagnostic_source": (
            "ATS/ERS/WASOG Statement on Sarcoidosis (Am J Respir Crit "
            "Care Med 1999;160:736-755); Crouser et al., Diagnosis and "
            "Detection of Sarcoidosis (Am J Respir Crit Care Med 2020)"
        ),
    },
    "Lupus (SLE)": {
        "specialties": ["Rheumatology", "Dermatology", "Nephrology"],
        "symptoms": [
            "butterfly rash", "malar rash", "joint pain", "arthralgia",
            "photosensitivity", "mouth ulcer", "oral ulcer", "pleurisy",
            "serositis", "raynaud",
        ],
        "lab_markers": [
            "ana positive", "antinuclear", "proteinuria", "low complement",
            "anti-dsdna", "anti-smith", "lupus anticoagulant",
        ],
        "description": (
            "An autoimmune disease where the immune system attacks its "
            "own tissues, causing widespread inflammation in the joints, "
            "skin, kidneys, and other organs."
        ),
        "diagnostic_source": (
            "2019 EULAR/ACR Classification Criteria for SLE "
            "(Ann Rheum Dis 2019;78:1151-1159)"
        ),
    },
    "Hemochromatosis": {
        "specialties": ["Hepatology", "Endocrinology", "Cardiology", "Rheumatology"],
        "symptoms": [
            "fatigue", "joint pain", "bronze skin", "arrhythmia",
            "loss of libido", "liver disease", "hepatomegaly",
        ],
        "lab_markers": [
            "high ferritin", "ferritin", "high transferrin saturation",
            "transferrin", "high iron", "serum iron",
        ],
        "description": (
            "A genetic disorder causing the body to absorb too much iron "
            "from food, leading to organ toxicity over decades."
        ),
        "diagnostic_source": (
            "AASLD Practice Guidelines: Diagnosis and Management of "
            "Hemochromatosis (Hepatology 2011;54:328-343); "
            "EASL Clinical Practice Guidelines (J Hepatol 2022)"
        ),
    },
    "Ehlers-Danlos Syndrome (EDS)": {
        "specialties": ["Rheumatology", "Cardiology", "Gastroenterology"],
        "symptoms": [
            "joint hypermobility", "hypermobile", "skin hyperextensibility",
            "easy bruising", "chronic pain", "gi dysmotility", "pots",
            "postural tachycardia", "subluxation", "dislocation",
        ],
        "lab_markers": [],
        "description": (
            "A group of connective tissue disorders affecting collagen, "
            "leading to fragile skin, unstable joints, and digestive issues."
        ),
        "diagnostic_source": (
            "2017 International Classification of EDS (Am J Med Genet "
            "Part C 2017;175C:8-26); Beighton Score for hypermobility"
        ),
    },
    "Multiple Sclerosis (MS)": {
        "specialties": ["Neurology", "Ophthalmology", "Urology"],
        "symptoms": [
            "optic neuritis", "numbness", "tingling", "paresthesia",
            "muscle weakness", "bladder dysfunction", "spasticity",
            "demyelinating", "nystagmus",
        ],
        "lab_markers": ["oligoclonal bands", "mri brain lesion", "mri spine lesion"],
        "description": (
            "A demyelinating disease where the immune system attacks the "
            "protective covering of nerves, causing communication problems "
            "between the brain and body."
        ),
        "diagnostic_source": (
            "2017 Revised McDonald Criteria for Diagnosis of MS "
            "(Lancet Neurol 2018;17:162-173)"
        ),
    },

    # ── Expanded 17 ───────────────────────────────────────
    "Sjögren's Syndrome": {
        "specialties": ["Rheumatology", "Ophthalmology", "Dentistry", "Pulmonology"],
        "symptoms": [
            "dry eyes", "dry mouth", "xerostomia", "keratoconjunctivitis",
            "parotid swelling", "joint pain", "fatigue", "vaginal dryness",
        ],
        "lab_markers": ["ssa", "ssb", "anti-ro", "anti-la", "rf positive", "ana positive"],
        "description": (
            "An autoimmune disease that attacks moisture-producing glands, "
            "causing persistent dryness of eyes and mouth — but can also "
            "affect joints, lungs, and kidneys."
        ),
        "diagnostic_source": (
            "2016 ACR/EULAR Classification Criteria for Primary "
            "Sjögren's Syndrome (Ann Rheum Dis 2017;76:9-16)"
        ),
    },
    "Celiac Disease": {
        "specialties": ["Gastroenterology", "Dermatology", "Neurology", "Endocrinology"],
        "symptoms": [
            "diarrhea", "bloating", "malabsorption", "dermatitis herpetiformis",
            "iron deficiency", "weight loss", "abdominal pain", "steatorrhea",
            "peripheral neuropathy", "ataxia",
        ],
        "lab_markers": ["ttg-iga", "tissue transglutaminase", "endomysial", "gliadin"],
        "description": (
            "An immune reaction to eating gluten that damages the small "
            "intestine lining. Can cause neurological, skin, and nutritional "
            "problems far beyond the gut."
        ),
        "diagnostic_source": (
            "ACG Clinical Guideline: Diagnosis and Management of Celiac "
            "Disease (Am J Gastroenterol 2013;108:656-676); "
            "ESPGHAN Guidelines (J Pediatr Gastroenterol Nutr 2020)"
        ),
    },
    "Mast Cell Activation Syndrome (MCAS)": {
        "specialties": ["Allergy/Immunology", "Gastroenterology", "Dermatology", "Cardiology"],
        "symptoms": [
            "flushing", "hives", "urticaria", "anaphylaxis", "abdominal cramp",
            "diarrhea", "tachycardia", "hypotension", "brain fog",
            "angioedema", "nasal congestion",
        ],
        "lab_markers": ["tryptase", "histamine", "prostaglandin d2", "chromogranin"],
        "description": (
            "A condition where mast cells release too many chemical "
            "mediators, causing episodes of flushing, GI distress, "
            "cardiovascular symptoms, and allergic-type reactions."
        ),
        "diagnostic_source": (
            "Valent et al., Proposed Diagnostic Algorithm for MCAS "
            "(J Allergy Clin Immunol Pract 2019;7:1125-1133); "
            "Akin et al., MCAS Consensus Criteria (J Allergy Clin "
            "Immunol 2010;126:1099-1104)"
        ),
    },
    "POTS (Postural Orthostatic Tachycardia Syndrome)": {
        "specialties": ["Cardiology", "Neurology", "Gastroenterology"],
        "symptoms": [
            "pots", "postural tachycardia", "orthostatic", "lightheaded",
            "dizziness on standing", "exercise intolerance", "brain fog",
            "palpitations", "nausea", "fainting", "syncope",
        ],
        "lab_markers": ["tilt table", "norepinephrine"],
        "description": (
            "A dysautonomia condition where heart rate increases abnormally "
            "upon standing, causing dizziness, brain fog, and fatigue. "
            "Often co-occurs with EDS and MCAS."
        ),
        "diagnostic_source": (
            "Heart Rhythm Society Expert Consensus Statement on POTS "
            "(Heart Rhythm 2015;12:e41-e63); Sheldon et al., "
            "2015 HRS Consensus (Heart Rhythm 2015)"
        ),
    },
    "Wilson's Disease": {
        "specialties": ["Hepatology", "Neurology", "Psychiatry", "Ophthalmology"],
        "symptoms": [
            "liver disease", "tremor", "psychiatric symptoms", "dysarthria",
            "kayser-fleischer", "hepatitis", "cirrhosis", "personality change",
            "depression", "parkinsonism",
        ],
        "lab_markers": ["ceruloplasmin", "copper", "24-hour urine copper"],
        "description": (
            "A rare genetic disorder where copper accumulates in the liver, "
            "brain, and eyes — causing liver disease, neurological problems, "
            "and psychiatric symptoms."
        ),
        "diagnostic_source": (
            "EASL Clinical Practice Guidelines: Wilson's Disease "
            "(J Hepatol 2012;56:671-685); AASLD Practice Guidance "
            "on Wilson Disease (Hepatology 2023)"
        ),
    },
    "Addison's Disease": {
        "specialties": ["Endocrinology", "Dermatology", "Gastroenterology"],
        "symptoms": [
            "fatigue", "weight loss", "hyperpigmentation", "salt craving",
            "nausea", "hypotension", "muscle weakness", "abdominal pain",
            "dizziness",
        ],
        "lab_markers": [
            "low cortisol", "cortisol", "acth", "low sodium", "hyponatremia",
            "high potassium", "hyperkalemia",
        ],
        "description": (
            "Adrenal insufficiency — the adrenal glands don't produce "
            "enough cortisol and aldosterone, causing fatigue, weight loss, "
            "and darkening of the skin."
        ),
        "diagnostic_source": (
            "Endocrine Society Clinical Practice Guideline: Diagnosis "
            "and Treatment of Primary Adrenal Insufficiency "
            "(J Clin Endocrinol Metab 2016;101:364-389)"
        ),
    },
    "Cushing's Syndrome": {
        "specialties": ["Endocrinology", "Psychiatry", "Dermatology", "Orthopedics"],
        "symptoms": [
            "moon face", "buffalo hump", "central obesity", "striae",
            "easy bruising", "muscle weakness", "mood changes", "hirsutism",
            "osteoporosis", "hypertension",
        ],
        "lab_markers": [
            "high cortisol", "cortisol", "dexamethasone suppression",
            "24-hour urine cortisol", "midnight salivary cortisol",
        ],
        "description": (
            "Excess cortisol production causing weight gain in the face "
            "and trunk, skin changes, mood swings, and bone weakening."
        ),
        "diagnostic_source": (
            "Endocrine Society Clinical Practice Guideline: Treatment "
            "of Cushing's Syndrome (J Clin Endocrinol Metab 2015;"
            "100:2807-2831); Nieman et al., Diagnosis of Cushing's "
            "(J Clin Endocrinol Metab 2008;93:1526-1540)"
        ),
    },
    "Fibromyalgia": {
        "specialties": ["Rheumatology", "Neurology", "Psychiatry", "Pain Medicine"],
        "symptoms": [
            "widespread pain", "fibromyalgia", "tender points", "fatigue",
            "cognitive dysfunction", "brain fog", "sleep disturbance",
            "ibs", "headache", "paresthesia",
        ],
        "lab_markers": [],
        "description": (
            "A chronic condition causing widespread musculoskeletal pain, "
            "fatigue, sleep issues, and cognitive difficulties. Labs are "
            "typically normal — diagnosis is clinical."
        ),
        "diagnostic_source": (
            "2016 Revisions to the 2010/2011 ACR Fibromyalgia "
            "Diagnostic Criteria (Semin Arthritis Rheum 2016;46:319-329); "
            "Wolfe et al., 2010 ACR Preliminary Criteria (Arthritis "
            "Care Res 2010;62:600-610)"
        ),
    },
    "Chronic Fatigue Syndrome (ME/CFS)": {
        "specialties": ["Rheumatology", "Neurology", "Infectious Disease", "Psychiatry"],
        "symptoms": [
            "chronic fatigue", "post-exertional malaise", "unrefreshing sleep",
            "cognitive impairment", "orthostatic intolerance", "sore throat",
            "tender lymph nodes", "myalgia",
        ],
        "lab_markers": [],
        "description": (
            "A complex, long-term illness causing extreme fatigue that "
            "worsens after physical or mental effort and doesn't improve "
            "with rest."
        ),
        "diagnostic_source": (
            "IOM (NAM) Report: Beyond Myalgic Encephalomyelitis/Chronic "
            "Fatigue Syndrome: Redefining an Illness (National Academies "
            "Press, 2015); Fukuda et al., CDC Criteria (Ann Intern Med "
            "1994;121:953-959)"
        ),
    },
    "Antiphospholipid Syndrome (APS)": {
        "specialties": ["Rheumatology", "Hematology", "Obstetrics/Gynecology", "Neurology"],
        "symptoms": [
            "dvt", "deep vein thrombosis", "pulmonary embolism",
            "recurrent miscarriage", "stroke", "livedo reticularis",
            "thrombocytopenia", "migraine",
        ],
        "lab_markers": [
            "anticardiolipin", "lupus anticoagulant", "anti-beta2 glycoprotein",
            "aptt prolonged",
        ],
        "description": (
            "An autoimmune disorder where the immune system mistakenly "
            "produces antibodies that make blood too sticky, leading to "
            "clots in veins and arteries."
        ),
        "diagnostic_source": (
            "2023 ACR/EULAR Antiphospholipid Syndrome Classification "
            "Criteria (Ann Rheum Dis 2023;82:1258-1270); supersedes "
            "2006 Revised Sapporo Criteria"
        ),
    },
    "Behçet's Disease": {
        "specialties": ["Rheumatology", "Ophthalmology", "Dermatology", "Gastroenterology"],
        "symptoms": [
            "oral ulcer", "genital ulcer", "uveitis", "skin lesion",
            "erythema nodosum", "pathergy", "arthritis", "vasculitis",
        ],
        "lab_markers": ["hla-b51", "esr elevated", "crp elevated"],
        "description": (
            "A rare disorder causing blood vessel inflammation throughout "
            "the body, presenting as recurrent mouth sores, genital sores, "
            "eye inflammation, and skin problems."
        ),
        "diagnostic_source": (
            "International Criteria for Behçet's Disease (ICBD) "
            "(J Eur Acad Dermatol Venereol 2014;28:338-347); "
            "ISG Criteria for Behçet's (Lancet 1990;335:1078-1080)"
        ),
    },
    "Amyloidosis": {
        "specialties": ["Hematology", "Cardiology", "Nephrology", "Neurology"],
        "symptoms": [
            "proteinuria", "nephrotic", "cardiomyopathy", "peripheral neuropathy",
            "macroglossia", "hepatomegaly", "weight loss", "carpal tunnel",
            "easy bruising",
        ],
        "lab_markers": [
            "free light chains", "serum protein electrophoresis", "spep",
            "urine protein electrophoresis", "bnp elevated",
        ],
        "description": (
            "A group of diseases where abnormal proteins (amyloid) build "
            "up in organs, affecting the heart, kidneys, nerves, and "
            "digestive system."
        ),
        "diagnostic_source": (
            "NCCN Guidelines for Systemic Light Chain Amyloidosis; "
            "Gillmore et al., Nonbiopsy Diagnosis of Cardiac "
            "Transthyretin Amyloidosis (Circulation 2016;133:2404-2412)"
        ),
    },
    "Thyroid Eye Disease (Graves')": {
        "specialties": ["Endocrinology", "Ophthalmology", "Cardiology"],
        "symptoms": [
            "exophthalmos", "proptosis", "eye bulging", "double vision",
            "weight loss", "tremor", "tachycardia", "heat intolerance",
            "graves", "goiter",
        ],
        "lab_markers": [
            "low tsh", "tsh receptor antibody", "trab", "high free t4",
            "high free t3", "thyroid stimulating immunoglobulin",
        ],
        "description": (
            "An autoimmune thyroid condition that also attacks eye muscles "
            "and tissue, causing bulging eyes and vision changes alongside "
            "hyperthyroid symptoms."
        ),
        "diagnostic_source": (
            "ATA/AACE Guidelines for Hyperthyroidism and Thyrotoxicosis "
            "(Thyroid 2016;26:1343-1421); EUGOGO Consensus Statement "
            "on Graves' Orbitopathy (Eur J Endocrinol 2016;174:G1-G39)"
        ),
    },
    "Inflammatory Bowel Disease (IBD)": {
        "specialties": ["Gastroenterology", "Rheumatology", "Dermatology", "Ophthalmology"],
        "symptoms": [
            "crohn", "ulcerative colitis", "bloody diarrhea", "abdominal pain",
            "weight loss", "perianal fistula", "arthritis", "uveitis",
            "erythema nodosum", "pyoderma gangrenosum",
        ],
        "lab_markers": [
            "calprotectin", "crp elevated", "esr elevated", "anemia",
            "low albumin",
        ],
        "description": (
            "Chronic inflammation of the digestive tract that can also "
            "cause joint pain, skin problems, and eye inflammation — "
            "symptoms that span multiple specialties."
        ),
        "diagnostic_source": (
            "ACG Clinical Guidelines: Ulcerative Colitis (Am J "
            "Gastroenterol 2019;114:384-413); ACG Clinical Guidelines: "
            "Management of Crohn's Disease (Am J Gastroenterol 2018;"
            "113:481-517)"
        ),
    },
    "Systemic Vasculitis": {
        "specialties": ["Rheumatology", "Pulmonology", "Nephrology", "Neurology"],
        "symptoms": [
            "vasculitis", "purpura", "sinusitis", "hemoptysis",
            "glomerulonephritis", "neuropathy", "fever", "weight loss",
            "skin ulcer",
        ],
        "lab_markers": [
            "anca", "p-anca", "c-anca", "anti-mpo", "anti-pr3",
            "crp elevated", "esr elevated",
        ],
        "description": (
            "A group of disorders where blood vessel inflammation causes "
            "organ damage across the lungs, kidneys, skin, and nerves — "
            "each piece often seen by a different specialist."
        ),
        "diagnostic_source": (
            "2022 ACR/EULAR Classification Criteria for ANCA-Associated "
            "Vasculitis (Ann Rheum Dis 2022;81:1616-1625); Revised "
            "Chapel Hill Consensus Conference Nomenclature (Arthritis "
            "Rheum 2013;65:1-11)"
        ),
    },
    "Hyperparathyroidism": {
        "specialties": ["Endocrinology", "Nephrology", "Orthopedics", "Gastroenterology"],
        "symptoms": [
            "kidney stone", "nephrolithiasis", "osteoporosis", "bone pain",
            "abdominal pain", "constipation", "fatigue", "depression",
            "cognitive changes",
        ],
        "lab_markers": [
            "high calcium", "hypercalcemia", "pth elevated", "parathyroid hormone",
            "low phosphorus",
        ],
        "description": (
            "Overactive parathyroid glands cause high calcium levels — the "
            "classic \"bones, stones, groans, and moans\" presentation spans "
            "orthopedics, urology, GI, and psychiatry."
        ),
        "diagnostic_source": (
            "Fourth International Workshop on Asymptomatic Primary "
            "Hyperparathyroidism (J Clin Endocrinol Metab 2014;99:"
            "3580-3594); AAES Guidelines for Definitive Management "
            "(Ann Surg 2016;264:919-929)"
        ),
    },
    "Systemic Sclerosis (Scleroderma)": {
        "specialties": ["Rheumatology", "Pulmonology", "Gastroenterology", "Cardiology"],
        "symptoms": [
            "raynaud", "skin thickening", "scleroderma", "sclerodactyly",
            "dysphagia", "gerd", "pulmonary fibrosis", "pulmonary hypertension",
            "digital ulcer", "calcinosis",
        ],
        "lab_markers": [
            "anti-scl-70", "anticentromere", "ana positive",
        ],
        "description": (
            "An autoimmune connective tissue disease causing skin hardening "
            "and internal organ fibrosis — the lungs, GI tract, and heart "
            "can all be affected."
        ),
        "diagnostic_source": (
            "2013 ACR/EULAR Classification Criteria for Systemic "
            "Sclerosis (Ann Rheum Dis 2013;72:1747-1755)"
        ),
    },

    # ── Expanded Triads (v3.1) — 18 new conditions ─────────

    # Nutrition / Metabolic
    "Vitamin B12 Deficiency": {
        "specialties": ["Nutrition", "Neurology", "Hematology", "Psychiatry"],
        "symptoms": [
            "neuropathy", "tingling", "numbness", "paresthesia",
            "cognitive changes", "memory loss", "depression", "fatigue",
            "glossitis", "mouth sore", "balance problems", "gait ataxia",
        ],
        "lab_markers": [
            "low b12", "vitamin b12", "methylmalonic acid", "homocysteine",
            "macrocytosis", "megaloblastic", "mcv elevated",
        ],
        "description": (
            "Low vitamin B12 can damage nerves and affect thinking, "
            "mood, and blood cell production. It often gets missed "
            "because the symptoms look like separate problems — "
            "a neurologist sees neuropathy, a psychiatrist sees "
            "depression, and a hematologist sees anemia."
        ),
        "diagnostic_source": (
            "BMJ Best Practice: Vitamin B12 Deficiency (2024); "
            "Langan RC, Goodbred AJ, Vitamin B12 Deficiency: "
            "Recognition and Management (Am Fam Physician 2017;"
            "96:384-389)"
        ),
    },
    "Iron Deficiency": {
        "specialties": ["Nutrition", "Hematology", "Gastroenterology", "Cardiology"],
        "symptoms": [
            "fatigue", "shortness of breath", "palpitations", "dizziness",
            "pale skin", "brittle nails", "hair loss", "restless legs",
            "pica", "cold intolerance",
        ],
        "lab_markers": [
            "low ferritin", "ferritin", "low iron", "iron saturation",
            "tibc elevated", "microcytic", "mcv low", "anemia",
        ],
        "description": (
            "Iron deficiency causes anemia and fatigue, but also "
            "heart symptoms like palpitations and breathlessness. "
            "It often signals hidden GI blood loss — connecting "
            "your blood work to your digestive health."
        ),
        "diagnostic_source": (
            "WHO Global Anaemia Estimates (2021); Camaschella C, "
            "Iron-Deficiency Anemia (NEJM 2015;372:1832-1843)"
        ),
    },
    "Vitamin D Deficiency": {
        "specialties": ["Nutrition", "Endocrinology", "Rheumatology", "Psychiatry"],
        "symptoms": [
            "bone pain", "muscle weakness", "fatigue", "depression",
            "frequent infections", "hair loss", "slow wound healing",
        ],
        "lab_markers": [
            "vitamin d", "25-hydroxyvitamin d", "low vitamin d",
            "pth elevated", "low calcium", "alkaline phosphatase",
        ],
        "description": (
            "Vitamin D deficiency weakens bones and muscles, but also "
            "affects mood and immune function. It can mimic fibromyalgia, "
            "depression, or even autoimmune disease."
        ),
        "diagnostic_source": (
            "Endocrine Society Clinical Practice Guideline: Vitamin D "
            "Deficiency (J Clin Endocrinol Metab 2011;96:1911-1930; "
            "updated 2024)"
        ),
    },

    # Sleep Medicine
    "Obstructive Sleep Apnea": {
        "specialties": ["Sleep Medicine", "Cardiology", "Neurology", "Endocrinology"],
        "symptoms": [
            "snoring", "sleep apnea", "daytime sleepiness", "fatigue",
            "morning headache", "nocturia", "hypertension", "atrial fibrillation",
            "obesity", "difficulty concentrating",
        ],
        "lab_markers": [
            "hemoglobin elevated", "polycythemia", "hba1c elevated",
        ],
        "description": (
            "Sleep apnea doesn't just cause snoring — it drives high "
            "blood pressure, heart rhythm problems, insulin resistance, "
            "and cognitive decline. Each specialist sees their piece, "
            "but the root cause is disrupted sleep."
        ),
        "diagnostic_source": (
            "AASM Clinical Practice Guideline for Diagnostic Testing "
            "for OSA (J Clin Sleep Med 2017;13:479-504); AHA/ACC "
            "Scientific Statement on Sleep Apnea and CV Disease "
            "(Circulation 2021;144:e56-e67)"
        ),
    },

    # Oncology — Paraneoplastic syndromes
    "Paraneoplastic Syndrome": {
        "specialties": ["Oncology", "Neurology", "Endocrinology", "Dermatology"],
        "symptoms": [
            "unexplained weight loss", "neuropathy", "muscle weakness",
            "cerebellar ataxia", "dermatomyositis", "acanthosis nigricans",
            "hypercalcemia", "cushing", "siadh", "lambert-eaton",
        ],
        "lab_markers": [
            "hypercalcemia", "hyponatremia", "anti-hu", "anti-yo",
            "anti-amphiphysin", "ca-125 elevated", "cea elevated",
        ],
        "description": (
            "Sometimes the immune system's response to a hidden cancer "
            "causes symptoms far from the tumor itself — nerve damage, "
            "skin changes, or hormone imbalances. These clues from "
            "different specialists can point to an undiagnosed cancer."
        ),
        "diagnostic_source": (
            "Darnell RB, Posner JB, Paraneoplastic Syndromes (NEJM "
            "2003;349:1543-1554); Graus F et al., Updated Diagnostic "
            "Criteria for Paraneoplastic Neurological Syndromes "
            "(Neurology 2021;96:e1-e14)"
        ),
    },

    # Genetics / Connective Tissue
    "Marfan Syndrome": {
        "specialties": ["Genetics", "Cardiology", "Ophthalmology", "Orthopedics"],
        "symptoms": [
            "tall stature", "long limbs", "arachnodactyly", "joint hypermobility",
            "lens subluxation", "ectopia lentis", "aortic root dilation",
            "mitral valve prolapse", "pectus excavatum", "scoliosis",
            "spontaneous pneumothorax", "dural ectasia",
        ],
        "lab_markers": [
            "fbn1 mutation", "fibrillin",
        ],
        "description": (
            "A genetic connective tissue disorder affecting the heart, "
            "eyes, and skeleton. An eye doctor notices a shifted lens, "
            "a cardiologist finds an enlarged aorta, and an orthopedist "
            "sees unusual height and flexibility — together, they point "
            "to Marfan syndrome."
        ),
        "diagnostic_source": (
            "Revised Ghent Nosology for Marfan Syndrome "
            "(J Med Genet 2010;47:476-485); 2022 ACC/AHA Guideline "
            "for the Diagnosis and Management of Aortic Disease"
        ),
    },

    # Vascular Medicine
    "Antiphospholipid Syndrome": {
        "specialties": ["Vascular Medicine", "Hematology", "Obstetrics/Gynecology", "Neurology"],
        "symptoms": [
            "deep vein thrombosis", "dvt", "pulmonary embolism",
            "stroke", "tia", "miscarriage", "recurrent pregnancy loss",
            "livedo reticularis", "thrombocytopenia",
        ],
        "lab_markers": [
            "lupus anticoagulant", "anticardiolipin", "anti-beta2 glycoprotein",
            "aptt prolonged",
        ],
        "description": (
            "An autoimmune clotting disorder that causes blood clots "
            "in veins and arteries, strokes, and pregnancy complications. "
            "A hematologist, neurologist, and OB/GYN may each see "
            "different pieces of the same disease."
        ),
        "diagnostic_source": (
            "2023 ACR/EULAR Antiphospholipid Syndrome Classification "
            "Criteria (Ann Rheum Dis 2023;82:1258-1270)"
        ),
    },

    # Environmental / Toxicology
    "Lead Toxicity": {
        "specialties": ["Toxicology", "Neurology", "Hematology", "Nephrology"],
        "symptoms": [
            "abdominal pain", "constipation", "headache", "memory loss",
            "irritability", "neuropathy", "wrist drop", "foot drop",
            "fatigue", "lead line",
        ],
        "lab_markers": [
            "lead level", "blood lead", "basophilic stippling",
            "free erythrocyte protoporphyrin", "anemia",
        ],
        "description": (
            "Lead exposure causes damage to the brain, nerves, kidneys, "
            "and blood. The symptoms — belly pain, tingling hands, "
            "memory problems, and anemia — are often treated separately "
            "until someone checks a lead level."
        ),
        "diagnostic_source": (
            "CDC/ATSDR Toxicological Profile for Lead (2020); "
            "Hauptman M et al., An Update on Childhood Lead Poisoning "
            "(Clin Ped Emerg Med 2017;18:181-192)"
        ),
    },

    # Infectious Disease
    "Lyme Disease": {
        "specialties": ["Infectious Disease", "Neurology", "Rheumatology", "Cardiology"],
        "symptoms": [
            "erythema migrans", "bull's eye rash", "joint pain", "arthritis",
            "facial palsy", "bell's palsy", "meningitis", "heart block",
            "fatigue", "cognitive changes", "radiculopathy",
        ],
        "lab_markers": [
            "lyme antibody", "lyme igg", "lyme igm", "western blot",
        ],
        "description": (
            "A tick-borne infection that can affect the joints, nervous "
            "system, and heart. A rheumatologist sees arthritis, a "
            "neurologist sees facial palsy, and a cardiologist sees "
            "heart block — but it's all one infection."
        ),
        "diagnostic_source": (
            "IDSA/AAN/ACR 2020 Guidelines for Prevention, Diagnosis, "
            "and Treatment of Lyme Disease (Clin Infect Dis 2021;"
            "72:e1-e48)"
        ),
    },

    # Psychiatry / Endocrine overlap
    "Hypothyroidism": {
        "specialties": ["Endocrinology", "Psychiatry", "Cardiology", "Dermatology"],
        "symptoms": [
            "fatigue", "weight gain", "cold intolerance", "constipation",
            "depression", "brain fog", "dry skin", "hair loss",
            "bradycardia", "edema", "hoarseness", "menstrual irregularity",
        ],
        "lab_markers": [
            "tsh elevated", "high tsh", "low t4", "free t4 low",
            "thyroid peroxidase", "anti-tpo",
        ],
        "description": (
            "An underactive thyroid slows everything down — metabolism, "
            "heart rate, mood, and skin renewal. Patients often see a "
            "psychiatrist for depression, a dermatologist for hair loss, "
            "and a cardiologist for slow heart rate before someone "
            "checks their thyroid."
        ),
        "diagnostic_source": (
            "ATA Guidelines for Treatment of Hypothyroidism "
            "(Thyroid 2014;24:1670-1751); Garber JR et al., "
            "Clinical Practice Guidelines for Hypothyroidism in Adults "
            "(Endocr Pract 2012;18:988-1028)"
        ),
    },
    "Pheochromocytoma": {
        "specialties": ["Endocrinology", "Cardiology", "Psychiatry", "Genetics"],
        "symptoms": [
            "episodic hypertension", "palpitations", "headache",
            "sweating", "anxiety", "panic attack", "tremor",
            "pallor", "weight loss",
        ],
        "lab_markers": [
            "metanephrine", "normetanephrine", "catecholamine",
            "vanillylmandelic acid", "vma",
        ],
        "description": (
            "A rare tumor of the adrenal gland that releases bursts "
            "of adrenaline, causing sudden high blood pressure, racing "
            "heart, and panic — often misdiagnosed as anxiety disorder "
            "or essential hypertension for years."
        ),
        "diagnostic_source": (
            "Endocrine Society Clinical Practice Guideline: "
            "Pheochromocytoma and Paraganglioma (J Clin Endocrinol "
            "Metab 2014;99:1915-1942; updated 2024)"
        ),
    },

    # Dermatology as systemic indicator
    "Dermatomyositis": {
        "specialties": ["Dermatology", "Rheumatology", "Oncology", "Pulmonology"],
        "symptoms": [
            "heliotrope rash", "gottron papules", "proximal muscle weakness",
            "dysphagia", "interstitial lung disease", "mechanic's hands",
            "periungual erythema", "calcinosis",
        ],
        "lab_markers": [
            "cpk elevated", "creatine kinase", "aldolase", "anti-jo1",
            "anti-mi2", "anti-mda5", "ana positive",
        ],
        "description": (
            "An inflammatory disease causing characteristic skin rashes "
            "and muscle weakness. It can also affect the lungs and — "
            "critically — is associated with hidden cancers, especially "
            "in adults over 40."
        ),
        "diagnostic_source": (
            "Bohan & Peter Criteria (NEJM 1975;292:344-347, 403-407); "
            "2017 EULAR/ACR Classification Criteria for Idiopathic "
            "Inflammatory Myopathies (Ann Rheum Dis 2017;76:1955-1964)"
        ),
    },

    # ENT / Multi-system
    "Granulomatosis with Polyangiitis (Wegener's)": {
        "specialties": ["ENT", "Pulmonology", "Nephrology", "Rheumatology"],
        "symptoms": [
            "sinusitis", "nasal crusting", "saddle nose", "epistaxis",
            "hemoptysis", "cough", "glomerulonephritis", "hematuria",
            "hearing loss", "otitis media", "proptosis",
        ],
        "lab_markers": [
            "c-anca", "anti-pr3", "crp elevated", "esr elevated",
            "hematuria", "proteinuria",
        ],
        "description": (
            "A vasculitis that starts with stubborn sinus problems and "
            "nosebleeds, then attacks the lungs and kidneys. An ENT "
            "doctor, a pulmonologist, and a nephrologist may each see "
            "their own piece of a single blood vessel disease."
        ),
        "diagnostic_source": (
            "2022 ACR/EULAR Classification Criteria for GPA "
            "(Ann Rheum Dis 2022;81:315-320); Revised Chapel Hill "
            "Nomenclature (Arthritis Rheum 2013;65:1-11)"
        ),
    },

    # Pain / Multi-system
    "Complex Regional Pain Syndrome (CRPS)": {
        "specialties": ["Pain Medicine", "Neurology", "Orthopedics", "Psychiatry"],
        "symptoms": [
            "burning pain", "allodynia", "swelling", "skin color changes",
            "temperature asymmetry", "excessive sweating", "hair changes",
            "nail changes", "muscle weakness", "tremor",
        ],
        "lab_markers": [],
        "description": (
            "Severe, burning pain — usually in a limb — with skin "
            "changes, swelling, and temperature differences. Often "
            "starts after an injury or surgery and is frequently "
            "dismissed or misdiagnosed across multiple specialists."
        ),
        "diagnostic_source": (
            "Budapest Criteria for CRPS (Pain 2010;150:268-274); "
            "Harden RN et al., Validation of Proposed Diagnostic "
            "Criteria (Pain Med 2010;11:1257-1268)"
        ),
    },

    # Geriatrics / Polypharmacy
    "Polypharmacy Syndrome": {
        "specialties": ["Geriatrics", "Clinical Pharmacology", "Neurology", "Cardiology"],
        "symptoms": [
            "dizziness", "falls", "confusion", "cognitive decline",
            "orthostatic hypotension", "fatigue", "nausea", "constipation",
            "urinary retention", "bradycardia",
        ],
        "lab_markers": [
            "renal function", "creatinine", "electrolyte imbalance",
            "hyponatremia", "hyperkalemia",
        ],
        "description": (
            "When multiple medications interact, the side effects can "
            "look like new diseases — dizziness, falls, confusion, "
            "and heart rhythm changes. Each specialist may add another "
            "drug without realizing the problem IS the medications."
        ),
        "diagnostic_source": (
            "AGS Beers Criteria for Potentially Inappropriate "
            "Medication Use in Older Adults (J Am Geriatr Soc 2023;"
            "71:2052-2095); STOPP/START Criteria v3 (Age Ageing 2023)"
        ),
    },

    # Celiac / Nutrition overlap
    "Malabsorption Syndrome": {
        "specialties": ["Gastroenterology", "Nutrition", "Hematology", "Endocrinology"],
        "symptoms": [
            "diarrhea", "steatorrhea", "weight loss", "bloating",
            "osteoporosis", "muscle cramps", "fatigue", "bruising",
            "peripheral neuropathy", "anemia",
        ],
        "lab_markers": [
            "low albumin", "low vitamin d", "low b12", "low folate",
            "low iron", "prolonged inr", "low calcium", "low magnesium",
        ],
        "description": (
            "When your gut can't properly absorb nutrients, the effects "
            "ripple through your whole body — weak bones, nerve damage, "
            "anemia, and bleeding problems. The underlying cause could "
            "be celiac disease, Crohn's, or pancreatic insufficiency."
        ),
        "diagnostic_source": (
            "AGA Clinical Practice Update on Small Intestinal "
            "Malabsorption (Gastroenterology 2021;160:1163-1174)"
        ),
    },

    # OB/GYN / Endocrine
    "Polycystic Ovary Syndrome (PCOS)": {
        "specialties": ["Obstetrics/Gynecology", "Endocrinology", "Dermatology", "Psychiatry"],
        "symptoms": [
            "irregular periods", "oligomenorrhea", "amenorrhea",
            "hirsutism", "acne", "hair loss", "weight gain",
            "infertility", "anxiety", "depression",
            "acanthosis nigricans", "pelvic pain",
        ],
        "lab_markers": [
            "testosterone elevated", "dhea-s elevated", "lh elevated",
            "lh/fsh ratio", "insulin elevated", "hba1c elevated",
            "amh elevated",
        ],
        "description": (
            "A hormonal condition causing irregular periods, acne, "
            "excess hair growth, and insulin resistance. A gynecologist "
            "sees the period problems, a dermatologist treats the acne, "
            "and an endocrinologist manages the metabolic effects — "
            "but it's all one syndrome."
        ),
        "diagnostic_source": (
            "International Evidence-Based Guideline for PCOS "
            "(2023 Update, Monash University/ESHRE); Rotterdam "
            "Criteria (Fertil Steril 2004;81:19-25)"
        ),
    },

    # Vascular / Hematology
    "Hereditary Hemorrhagic Telangiectasia (HHT)": {
        "specialties": ["Vascular Medicine", "Pulmonology", "Gastroenterology", "Genetics"],
        "symptoms": [
            "nosebleed", "epistaxis", "telangiectasia", "anemia",
            "shortness of breath", "gi bleeding", "brain abscess",
            "stroke", "migraine", "liver avm",
        ],
        "lab_markers": [
            "low hemoglobin", "anemia", "iron deficiency",
        ],
        "description": (
            "A genetic disorder causing abnormal blood vessel connections "
            "(AVMs) in the nose, lungs, brain, and liver. Frequent "
            "nosebleeds and anemia are the visible part — but hidden "
            "lung AVMs can cause strokes and brain abscesses."
        ),
        "diagnostic_source": (
            "Curacao Criteria for HHT (Am J Med Genet 2000;91:66-67); "
            "Second International Guidelines for HHT (Ann Intern Med "
            "2020;173:989-1001)"
        ),
    },
}


class CrossSpecialtyEngine:
    """
    The 'House M.D.' module — detects systemic diseases hiding across
    multiple specialties by correlating all available patient data.

    Accepts profile_data dict (vault-based architecture, no SQLite).
    Optionally uses Gemini/Ollama for unexpected pattern discovery.
    """

    def __init__(self, api_key: str = None):
        self._api_key = api_key

    def analyze(self, profile_data: dict) -> list[dict]:
        """
        Scan the patient profile for cross-specialty systemic correlations.

        Returns list of alerts:
        [
            {
                "type": "systemic_correlation",
                "disease": "Lupus (SLE)",
                "specialties": ["Rheumatology", "Dermatology", "Nephrology"],
                "severity": "high" | "moderate",
                "description": "...",
                "matched_symptoms": [...],
                "matched_labs": [...],
                "total_hits": 4,
                "threshold": 2,
                "recommendation": "...",
            },
        ]
        """
        corpus = self._build_corpus(profile_data)
        corpus_text = " | ".join(corpus)

        alerts = []

        for disease, profile in SYSTEMIC_DISEASE_TRIADS.items():
            symptom_hits = []
            for symptom in profile["symptoms"]:
                if symptom.lower() in corpus_text:
                    symptom_hits.append(symptom)

            lab_hits = []
            for lab in profile["lab_markers"]:
                # Flexible matching — strip qualifiers
                lab_base = (
                    lab.lower()
                    .replace("high ", "")
                    .replace("low ", "")
                    .replace(" positive", "")
                    .replace(" elevated", "")
                )
                if lab_base in corpus_text:
                    lab_hits.append(lab)

            total_hits = len(symptom_hits) + len(lab_hits)
            total_possible = len(profile["symptoms"]) + len(profile["lab_markers"])
            # Threshold: at least 2 hits, or half the symptoms (whichever is larger)
            threshold = max(2, len(profile["symptoms"]) // 3)

            if total_hits >= threshold:
                severity = "high" if total_hits >= threshold * 2 else "moderate"

                spec_names = ", ".join(profile["specialties"][:3])
                alerts.append({
                    "type": "systemic_correlation",
                    "disease": disease,
                    "specialties": profile["specialties"],
                    "severity": severity,
                    "description": profile["description"],
                    "matched_symptoms": symptom_hits,
                    "matched_labs": lab_hits,
                    "total_hits": total_hits,
                    "total_possible": total_possible,
                    "threshold": threshold,
                    "diagnostic_source": profile.get("diagnostic_source", ""),
                    "evidence_source": (
                        "Validated systemic disease pattern database "
                        "(22 clinically documented multi-specialty conditions)"
                    ),
                    "recommendation": (
                        f"We found findings in your records that "
                        f"touch {spec_names} \u2014 areas that don\u2019t always "
                        f"talk to each other. We\u2019ve noted this so you "
                        f"can ask your doctor about {disease}."
                    ),
                })

        # Sort by hit count descending
        alerts.sort(key=lambda a: -a["total_hits"])

        # Optional: Gemini-powered pattern discovery for unexpected connections
        if self._api_key and corpus:
            ai_alerts = self._gemini_pattern_discovery(corpus, alerts)
            alerts.extend(ai_alerts)

        logger.info(
            "Cross-specialty analysis: %d correlations found from %d diseases checked",
            len(alerts),
            len(SYSTEMIC_DISEASE_TRIADS),
        )

        return alerts

    # ── Corpus Builder ────────────────────────────────────

    def _build_corpus(self, profile_data: dict) -> list[str]:
        """
        Build a searchable corpus from ALL patient data:
        diagnoses, labs, medications, symptoms, imaging, genetics.
        """
        corpus = []
        timeline = profile_data.get("clinical_timeline", {})

        # Diagnoses
        for dx in timeline.get("diagnoses", []):
            name = dx.get("name", "").lower()
            status = dx.get("status", "").lower()
            if status not in ("resolved", "inactive", "historical"):
                corpus.append(name)

        # Labs — include name + flag info
        for lab in timeline.get("labs", []):
            name = lab.get("name", "").lower()
            flag = lab.get("flag", "").lower()
            if name:
                corpus.append(name)
                if flag and flag not in ("normal", ""):
                    corpus.append(f"{flag} {name}")
                    corpus.append(f"{name} {flag}")

        # Medications (can hint at conditions)
        for med in timeline.get("medications", []):
            name = med.get("name", "").lower()
            status = med.get("status", "").lower()
            if name and status not in ("discontinued", "stopped"):
                corpus.append(name)

        # Symptom logger — symptom names + episode descriptions
        for symptom in timeline.get("symptoms", []):
            sname = symptom.get("symptom_name", "").lower()
            if sname:
                corpus.append(sname)

            for ep in symptom.get("episodes", []):
                desc = ep.get("description", "").lower()
                if desc:
                    corpus.append(desc)
                triggers = ep.get("triggers", "").lower()
                if triggers:
                    corpus.append(triggers)

        # Imaging findings
        for img in timeline.get("imaging", []):
            desc = img.get("description", "").lower()
            if desc:
                corpus.append(desc)
            for finding in img.get("findings", []):
                if isinstance(finding, str):
                    corpus.append(finding.lower())
                elif isinstance(finding, dict):
                    corpus.append(finding.get("description", "").lower())

        # Genetic variants
        for variant in timeline.get("genetics", []):
            gene = variant.get("gene", "").lower()
            var_name = variant.get("variant", "").lower()
            if gene:
                corpus.append(gene)
            if var_name:
                corpus.append(var_name)

        return [c for c in corpus if c.strip()]

    # ── PubMed Client ──────────────────────────────────────

    def _get_pubmed_client(self):
        """Get PubMed client for citation verification. Returns None on failure."""
        try:
            from src.validation.pubmed import PubMedClient
            return PubMedClient()
        except Exception:
            logger.debug("PubMed client unavailable for verification")
            return None

    # ── Gemini Pattern Discovery ──────────────────────────

    def _gemini_pattern_discovery(
        self, corpus: list[str], existing_alerts: list[dict],
    ) -> list[dict]:
        """
        Use Gemini to look for unexpected cross-specialty connections
        beyond the known triads. Returns additional alerts.
        """
        if not self._api_key:
            return []

        # Don't send to LLM if corpus is too small
        if len(corpus) < 5:
            return []

        # Build a condensed corpus summary
        corpus_summary = ", ".join(set(corpus))[:3000]
        already_found = [a["disease"] for a in existing_alerts]

        prompt = (
            "You are a cross-specialty medical analyst. Below are clinical "
            "findings from a patient's records. Identify any SYSTEMIC diseases "
            "or cross-specialty connections that span multiple specialties \u2014 "
            "conditions where different doctors might each see one piece but "
            "miss the big picture.\n\n"
            f"Patient findings: {corpus_summary}\n\n"
            f"Already identified: {', '.join(already_found) or 'none'}\n\n"
            "Return ONLY conditions NOT already identified. For each, provide:\n"
            "- disease: condition name\n"
            "- specialties: list of relevant specialties\n"
            "- evidence: which patient findings support this (array of strings)\n"
            "- description: plain English explanation written at a 6th grade "
            "reading level. Start with 'Here\u2019s something we found.' and "
            "explain what it means in simple terms.\n"
            "- sources: array of specific medical sources you drew from. "
            "REQUIRED. Must be real, verifiable sources such as:\n"
            "  * Clinical practice guidelines (ADA, ACC/AHA, CPIC, USPSTF, KDIGO, etc.)\n"
            "  * Peer-reviewed journals (NEJM, JAMA, Lancet, BMJ, etc.)\n"
            "  * Medical reference databases (UpToDate, DynaMed)\n"
            "  * Standard medical criteria (DSM-5, Rome IV, ACR criteria, etc.)\n"
            "- evidence_strength: 'strong' (RCTs, meta-analyses, major guidelines), "
            "'moderate' (cohort studies, smaller guidelines), or "
            "'emerging' (case series, expert opinion)\n\n"
            "Return as JSON array. If nothing new found, return [].\n"
            "CRITICAL: Only suggest conditions with genuine clinical basis "
            "in the patient's data. Every suggestion MUST include at least "
            "one citable medical source. Do NOT speculate or fabricate sources."
        )

        try:
            import google.generativeai as genai
            import json
            import re

            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            text = response.text

            # Parse JSON from response
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if not json_match:
                return []

            suggestions = json.loads(json_match.group())
            ai_alerts = []

            # PubMed verification — check if real literature supports
            # each Gemini suggestion (filters to reviews + trials only)
            pubmed = self._get_pubmed_client()

            for s in suggestions[:3]:  # Cap at 3 AI-discovered conditions
                if not isinstance(s, dict):
                    continue
                disease = s.get("disease", "")
                if not disease or disease in already_found:
                    continue

                sources = s.get("sources", [])
                strength = s.get("evidence_strength", "moderate")
                source_text = (
                    ", ".join(sources) if sources
                    else "Gemini medical literature analysis"
                )

                # ── PubMed Verification ──────────────────────
                pubmed_verified = False
                pubmed_citations = []
                if pubmed:
                    specialties = s.get("specialties", [])
                    primary_spec = specialties[0] if specialties else ""
                    try:
                        citations = pubmed.search_cross_disciplinary(
                            disease, primary_spec,
                        )
                        if citations:
                            pubmed_verified = True
                            pubmed_citations = [
                                {
                                    "title": c.title,
                                    "journal": c.journal,
                                    "year": c.year,
                                    "pmid": c.pubmed_id,
                                }
                                for c in citations[:3]
                            ]
                    except Exception as e:
                        logger.debug(
                            "PubMed verification failed for %s: %s",
                            disease, e,
                        )

                ai_alerts.append({
                    "type": "ai_discovered_correlation",
                    "disease": disease,
                    "specialties": s.get("specialties", []),
                    "severity": "moderate",
                    "description": s.get("description", ""),
                    "matched_symptoms": s.get("evidence", []),
                    "matched_labs": [],
                    "total_hits": len(s.get("evidence", [])),
                    "total_possible": 0,
                    "threshold": 0,
                    "evidence_source": source_text,
                    "evidence_strength": strength,
                    "pubmed_verified": pubmed_verified,
                    "pubmed_citations": pubmed_citations,
                    "recommendation": (
                        f"We found a pattern in your records that "
                        f"could be related to {disease}. We\u2019ve noted "
                        f"this so you can bring it up at your next visit."
                    ),
                })

            return ai_alerts

        except Exception as e:
            logger.debug("Gemini cross-specialty discovery failed: %s", e)
            return []


# ── Legacy compatibility ──────────────────────────────────
# The old function signature for any code that still calls it

def analyze_cross_specialty_patterns(db_path_or_profile=None):
    """
    Legacy entry point. Now accepts either a db path (ignored) or
    profile_data dict.
    """
    if isinstance(db_path_or_profile, dict):
        engine = CrossSpecialtyEngine()
        return engine.analyze(db_path_or_profile)
    # Can't do anything without profile data
    logger.warning("Cross-specialty called with non-dict input; returning empty.")
    return []
