"""
Clinical Intelligence Hub — Biomarker Cascade Engine

Knowledge base of 30+ biomarker cascade chains showing how one
abnormal value can trigger downstream effects across body systems.

Example: elevated cortisol → insulin resistance → elevated glucose
         → diabetic nephropathy → elevated creatinine

Given a patient's lab data, identifies which cascades are active
(patient has the upstream abnormality) and which downstream effects
to watch for. Returns D3-compatible directed graph data.

Results feed into:
  - Biomarker Cascades overlay (D3 force-directed graph)
  - Doctor Visit Prep
"""

import logging
from typing import Optional

logger = logging.getLogger("CIH-BiomarkerCascades")


# ── Cascade Knowledge Base ────────────────────────────────
#
# Each cascade is a chain of biomarker nodes connected by edges.
# Nodes have:
#   id       — unique across all cascades
#   label    — display name
#   type     — "biomarker", "condition", or "organ_effect"
#   tests    — lab test names that map to this node (for patient matching)
#   flag     — which direction is abnormal: "high", "low", or "any"
#
# Edges have:
#   source   — upstream node id
#   target   — downstream node id
#   mechanism — brief explanation of the causal link

CASCADE_CHAINS = [
    # ── Cortisol / Metabolic ────────────────────────
    {
        "name": "Cortisol-Metabolic Cascade",
        "category": "Endocrine/Metabolic",
        "nodes": [
            {"id": "cortisol_high", "label": "Elevated Cortisol", "type": "biomarker",
             "tests": ["cortisol"], "flag": "high"},
            {"id": "insulin_resist", "label": "Insulin Resistance", "type": "condition",
             "tests": ["homa-ir", "fasting insulin"], "flag": "high"},
            {"id": "glucose_high", "label": "Elevated Glucose", "type": "biomarker",
             "tests": ["glucose", "fasting glucose", "hba1c"], "flag": "high"},
            {"id": "triglycerides_high", "label": "Elevated Triglycerides", "type": "biomarker",
             "tests": ["triglycerides", "triglyceride"], "flag": "high"},
            {"id": "nephropathy", "label": "Diabetic Nephropathy", "type": "organ_effect",
             "tests": ["microalbumin", "urine albumin", "uacr"], "flag": "high"},
            {"id": "creatinine_high", "label": "Elevated Creatinine", "type": "biomarker",
             "tests": ["creatinine"], "flag": "high"},
        ],
        "edges": [
            {"source": "cortisol_high", "target": "insulin_resist",
             "mechanism": "Cortisol promotes gluconeogenesis and opposes insulin action"},
            {"source": "insulin_resist", "target": "glucose_high",
             "mechanism": "Cells can't absorb glucose efficiently"},
            {"source": "insulin_resist", "target": "triglycerides_high",
             "mechanism": "Liver increases VLDL production under insulin resistance"},
            {"source": "glucose_high", "target": "nephropathy",
             "mechanism": "Chronic hyperglycemia damages glomerular capillaries"},
            {"source": "nephropathy", "target": "creatinine_high",
             "mechanism": "Kidney filtration declines as nephrons are damaged"},
        ],
    },
    # ── Iron Overload ───────────────────────────────
    {
        "name": "Iron Overload Cascade",
        "category": "Hematology/Hepatology",
        "nodes": [
            {"id": "ferritin_high", "label": "Elevated Ferritin", "type": "biomarker",
             "tests": ["ferritin"], "flag": "high"},
            {"id": "transferrin_high", "label": "High Transferrin Sat.", "type": "biomarker",
             "tests": ["transferrin saturation", "transferrin sat", "tibc"], "flag": "high"},
            {"id": "liver_damage", "label": "Hepatocellular Damage", "type": "organ_effect",
             "tests": ["alt", "ast", "liver function"], "flag": "high"},
            {"id": "fibrosis", "label": "Hepatic Fibrosis", "type": "condition",
             "tests": ["fib-4", "fibroscan"], "flag": "high"},
            {"id": "cardiac_iron", "label": "Cardiac Iron Deposition", "type": "organ_effect",
             "tests": ["cardiac mri", "t2*"], "flag": "any"},
            {"id": "dm_iron", "label": "Iron-Induced Diabetes", "type": "condition",
             "tests": ["hba1c", "glucose"], "flag": "high"},
        ],
        "edges": [
            {"source": "ferritin_high", "target": "liver_damage",
             "mechanism": "Excess iron generates free radicals damaging hepatocytes"},
            {"source": "transferrin_high", "target": "ferritin_high",
             "mechanism": "Saturated transferrin leads to iron deposition in tissues"},
            {"source": "liver_damage", "target": "fibrosis",
             "mechanism": "Chronic hepatocyte injury triggers collagen deposition"},
            {"source": "ferritin_high", "target": "cardiac_iron",
             "mechanism": "Iron deposits in cardiac myocytes cause cardiomyopathy"},
            {"source": "ferritin_high", "target": "dm_iron",
             "mechanism": "Iron deposition in pancreatic beta cells impairs insulin secretion"},
        ],
    },
    # ── Thyroid Cascade ─────────────────────────────
    {
        "name": "Thyroid-Metabolic Cascade",
        "category": "Endocrine",
        "nodes": [
            {"id": "tsh_high", "label": "Elevated TSH", "type": "biomarker",
             "tests": ["tsh"], "flag": "high"},
            {"id": "ft4_low", "label": "Low Free T4", "type": "biomarker",
             "tests": ["free t4", "ft4", "thyroxine"], "flag": "low"},
            {"id": "cholesterol_high", "label": "Elevated LDL Cholesterol", "type": "biomarker",
             "tests": ["ldl", "cholesterol", "ldl cholesterol"], "flag": "high"},
            {"id": "cpk_high", "label": "Elevated CPK", "type": "biomarker",
             "tests": ["cpk", "creatine kinase", "ck"], "flag": "high"},
            {"id": "anemia_hypo", "label": "Anemia of Hypothyroidism", "type": "condition",
             "tests": ["hemoglobin", "hematocrit"], "flag": "low"},
            {"id": "cardiac_risk_thyroid", "label": "Increased Cardiac Risk", "type": "organ_effect",
             "tests": ["lipid panel"], "flag": "high"},
        ],
        "edges": [
            {"source": "tsh_high", "target": "ft4_low",
             "mechanism": "Failing thyroid can't produce adequate T4 despite TSH stimulation"},
            {"source": "ft4_low", "target": "cholesterol_high",
             "mechanism": "Thyroid hormone normally clears LDL receptors; deficiency raises LDL"},
            {"source": "ft4_low", "target": "cpk_high",
             "mechanism": "Hypothyroidism causes myopathy with muscle enzyme leak"},
            {"source": "ft4_low", "target": "anemia_hypo",
             "mechanism": "Reduced erythropoietin production and iron absorption"},
            {"source": "cholesterol_high", "target": "cardiac_risk_thyroid",
             "mechanism": "Chronic hyperlipidemia accelerates atherosclerosis"},
        ],
    },
    # ── Kidney-Bone Cascade ─────────────────────────
    {
        "name": "CKD-Mineral Bone Cascade",
        "category": "Nephrology/Endocrine",
        "nodes": [
            {"id": "egfr_low", "label": "Low eGFR", "type": "biomarker",
             "tests": ["egfr", "gfr", "estimated gfr"], "flag": "low"},
            {"id": "phosphorus_high", "label": "Elevated Phosphorus", "type": "biomarker",
             "tests": ["phosphorus", "phosphate"], "flag": "high"},
            {"id": "vitd_low", "label": "Low Vitamin D", "type": "biomarker",
             "tests": ["vitamin d", "25-hydroxy", "25-oh vitamin d"], "flag": "low"},
            {"id": "pth_high", "label": "Elevated PTH", "type": "biomarker",
             "tests": ["pth", "parathyroid hormone"], "flag": "high"},
            {"id": "calcium_low", "label": "Low Calcium", "type": "biomarker",
             "tests": ["calcium"], "flag": "low"},
            {"id": "bone_loss", "label": "Renal Osteodystrophy", "type": "organ_effect",
             "tests": ["dexa", "bone density"], "flag": "any"},
            {"id": "vascular_calc", "label": "Vascular Calcification", "type": "organ_effect",
             "tests": ["coronary calcium", "cac score"], "flag": "high"},
        ],
        "edges": [
            {"source": "egfr_low", "target": "phosphorus_high",
             "mechanism": "Kidneys can't excrete phosphorus adequately"},
            {"source": "egfr_low", "target": "vitd_low",
             "mechanism": "Kidneys can't convert vitamin D to active form (1,25-OH)"},
            {"source": "vitd_low", "target": "calcium_low",
             "mechanism": "Without active vitamin D, calcium absorption drops"},
            {"source": "calcium_low", "target": "pth_high",
             "mechanism": "Low calcium triggers parathyroid glands to compensate"},
            {"source": "phosphorus_high", "target": "pth_high",
             "mechanism": "High phosphorus stimulates PTH secretion"},
            {"source": "pth_high", "target": "bone_loss",
             "mechanism": "Chronic PTH elevation pulls calcium from bones"},
            {"source": "phosphorus_high", "target": "vascular_calc",
             "mechanism": "Excess phosphorus deposits in blood vessel walls"},
        ],
    },
    # ── Inflammation Cascade ────────────────────────
    {
        "name": "Chronic Inflammation Cascade",
        "category": "Immunology/Cardiology",
        "nodes": [
            {"id": "crp_high", "label": "Elevated CRP", "type": "biomarker",
             "tests": ["crp", "c-reactive protein", "hs-crp"], "flag": "high"},
            {"id": "esr_high", "label": "Elevated ESR", "type": "biomarker",
             "tests": ["esr", "sed rate", "sedimentation rate"], "flag": "high"},
            {"id": "il6_high", "label": "Elevated IL-6", "type": "biomarker",
             "tests": ["il-6", "interleukin-6", "interleukin 6"], "flag": "high"},
            {"id": "endothelial", "label": "Endothelial Dysfunction", "type": "condition",
             "tests": [], "flag": "any"},
            {"id": "atherosclerosis", "label": "Accelerated Atherosclerosis", "type": "organ_effect",
             "tests": ["carotid imt", "coronary calcium"], "flag": "high"},
            {"id": "anemia_chronic", "label": "Anemia of Chronic Disease", "type": "condition",
             "tests": ["hemoglobin", "hematocrit", "ferritin"], "flag": "low"},
        ],
        "edges": [
            {"source": "il6_high", "target": "crp_high",
             "mechanism": "IL-6 drives hepatic CRP production"},
            {"source": "il6_high", "target": "esr_high",
             "mechanism": "IL-6 increases fibrinogen, raising ESR"},
            {"source": "crp_high", "target": "endothelial",
             "mechanism": "CRP directly damages endothelial lining of arteries"},
            {"source": "endothelial", "target": "atherosclerosis",
             "mechanism": "Damaged endothelium attracts lipid deposits and plaque"},
            {"source": "il6_high", "target": "anemia_chronic",
             "mechanism": "IL-6 increases hepcidin, trapping iron in stores"},
        ],
    },
    # ── Liver-Coagulation Cascade ───────────────────
    {
        "name": "Liver-Coagulation Cascade",
        "category": "Hepatology/Hematology",
        "nodes": [
            {"id": "alt_high", "label": "Elevated ALT", "type": "biomarker",
             "tests": ["alt", "alanine aminotransferase", "sgpt"], "flag": "high"},
            {"id": "ast_high", "label": "Elevated AST", "type": "biomarker",
             "tests": ["ast", "aspartate aminotransferase", "sgot"], "flag": "high"},
            {"id": "albumin_low", "label": "Low Albumin", "type": "biomarker",
             "tests": ["albumin"], "flag": "low"},
            {"id": "inr_high", "label": "Elevated INR", "type": "biomarker",
             "tests": ["inr", "pt", "prothrombin time"], "flag": "high"},
            {"id": "plt_low", "label": "Low Platelets", "type": "biomarker",
             "tests": ["platelet", "plt"], "flag": "low"},
            {"id": "bleed_risk", "label": "Bleeding Risk", "type": "organ_effect",
             "tests": [], "flag": "any"},
        ],
        "edges": [
            {"source": "alt_high", "target": "albumin_low",
             "mechanism": "Damaged hepatocytes reduce albumin synthesis"},
            {"source": "ast_high", "target": "albumin_low",
             "mechanism": "Ongoing liver injury impairs protein production"},
            {"source": "albumin_low", "target": "inr_high",
             "mechanism": "Liver also produces clotting factors; failure raises INR"},
            {"source": "alt_high", "target": "plt_low",
             "mechanism": "Portal hypertension from liver disease causes splenic sequestration"},
            {"source": "inr_high", "target": "bleed_risk",
             "mechanism": "Impaired coagulation increases bleeding tendency"},
            {"source": "plt_low", "target": "bleed_risk",
             "mechanism": "Low platelets reduce primary hemostasis"},
        ],
    },
    # ── Vitamin D Cascade ───────────────────────────
    {
        "name": "Vitamin D Deficiency Cascade",
        "category": "Endocrine/Immunology",
        "nodes": [
            {"id": "vitd_deficient", "label": "Low Vitamin D", "type": "biomarker",
             "tests": ["vitamin d", "25-hydroxy", "25-oh vitamin d", "cholecalciferol"],
             "flag": "low"},
            {"id": "calcium_low_d", "label": "Low Calcium", "type": "biomarker",
             "tests": ["calcium"], "flag": "low"},
            {"id": "pth_secondary", "label": "Secondary Hyperparathyroidism", "type": "condition",
             "tests": ["pth", "parathyroid hormone"], "flag": "high"},
            {"id": "osteo_d", "label": "Osteoporosis / Osteomalacia", "type": "organ_effect",
             "tests": ["dexa", "bone density"], "flag": "any"},
            {"id": "immune_dysreg", "label": "Immune Dysregulation", "type": "condition",
             "tests": [], "flag": "any"},
            {"id": "fatigue_d", "label": "Fatigue / Mood Changes", "type": "condition",
             "tests": [], "flag": "any"},
        ],
        "edges": [
            {"source": "vitd_deficient", "target": "calcium_low_d",
             "mechanism": "Vitamin D is required for intestinal calcium absorption"},
            {"source": "calcium_low_d", "target": "pth_secondary",
             "mechanism": "Low calcium stimulates PTH to maintain levels"},
            {"source": "pth_secondary", "target": "osteo_d",
             "mechanism": "Chronic PTH elevation mobilizes calcium from bones"},
            {"source": "vitd_deficient", "target": "immune_dysreg",
             "mechanism": "Vitamin D modulates T-cell and macrophage function"},
            {"source": "vitd_deficient", "target": "fatigue_d",
             "mechanism": "Vitamin D receptors in brain affect mood and energy"},
        ],
    },
    # ── B12 Deficiency Cascade ──────────────────────
    {
        "name": "B12 Deficiency Cascade",
        "category": "Hematology/Neurology",
        "nodes": [
            {"id": "b12_low", "label": "Low Vitamin B12", "type": "biomarker",
             "tests": ["vitamin b12", "b12", "cobalamin"], "flag": "low"},
            {"id": "homocysteine_high", "label": "Elevated Homocysteine", "type": "biomarker",
             "tests": ["homocysteine"], "flag": "high"},
            {"id": "mma_high", "label": "Elevated Methylmalonic Acid", "type": "biomarker",
             "tests": ["methylmalonic acid", "mma"], "flag": "high"},
            {"id": "megaloblastic", "label": "Megaloblastic Anemia", "type": "condition",
             "tests": ["mcv", "hemoglobin"], "flag": "high"},
            {"id": "neuro_b12", "label": "Peripheral Neuropathy", "type": "organ_effect",
             "tests": [], "flag": "any"},
            {"id": "cv_risk_b12", "label": "Cardiovascular Risk", "type": "organ_effect",
             "tests": [], "flag": "any"},
        ],
        "edges": [
            {"source": "b12_low", "target": "homocysteine_high",
             "mechanism": "B12 is a cofactor for homocysteine metabolism"},
            {"source": "b12_low", "target": "mma_high",
             "mechanism": "B12 required for methylmalonyl-CoA to succinyl-CoA conversion"},
            {"source": "b12_low", "target": "megaloblastic",
             "mechanism": "Impaired DNA synthesis produces abnormally large red blood cells"},
            {"source": "mma_high", "target": "neuro_b12",
             "mechanism": "MMA accumulation damages myelin sheaths of nerves"},
            {"source": "homocysteine_high", "target": "cv_risk_b12",
             "mechanism": "Elevated homocysteine damages vascular endothelium"},
        ],
    },
    # ── Renin-Angiotensin Cascade ───────────────────
    {
        "name": "Renin-Angiotensin-Aldosterone Cascade",
        "category": "Cardiology/Nephrology",
        "nodes": [
            {"id": "renin_high", "label": "Elevated Renin", "type": "biomarker",
             "tests": ["renin", "plasma renin"], "flag": "high"},
            {"id": "aldosterone_high", "label": "Elevated Aldosterone", "type": "biomarker",
             "tests": ["aldosterone"], "flag": "high"},
            {"id": "sodium_retain", "label": "Sodium Retention", "type": "condition",
             "tests": ["sodium"], "flag": "high"},
            {"id": "k_low", "label": "Low Potassium", "type": "biomarker",
             "tests": ["potassium"], "flag": "low"},
            {"id": "htn_raas", "label": "Hypertension", "type": "organ_effect",
             "tests": [], "flag": "any"},
            {"id": "cardiac_remodel", "label": "Cardiac Remodeling", "type": "organ_effect",
             "tests": ["bnp", "nt-probnp", "echocardiogram"], "flag": "high"},
        ],
        "edges": [
            {"source": "renin_high", "target": "aldosterone_high",
             "mechanism": "Renin converts angiotensinogen → angiotensin I → II → aldosterone"},
            {"source": "aldosterone_high", "target": "sodium_retain",
             "mechanism": "Aldosterone promotes sodium reabsorption in kidneys"},
            {"source": "aldosterone_high", "target": "k_low",
             "mechanism": "Aldosterone exchanges sodium for potassium excretion"},
            {"source": "sodium_retain", "target": "htn_raas",
             "mechanism": "Sodium retention expands blood volume, raising pressure"},
            {"source": "htn_raas", "target": "cardiac_remodel",
             "mechanism": "Chronic pressure overload causes ventricular hypertrophy"},
        ],
    },
    # ── Uric Acid Cascade ───────────────────────────
    {
        "name": "Uric Acid Cascade",
        "category": "Rheumatology/Nephrology",
        "nodes": [
            {"id": "uric_high", "label": "Elevated Uric Acid", "type": "biomarker",
             "tests": ["uric acid", "urate"], "flag": "high"},
            {"id": "gout_attack", "label": "Gout / Crystal Arthropathy", "type": "condition",
             "tests": [], "flag": "any"},
            {"id": "kidney_stones_ua", "label": "Uric Acid Kidney Stones", "type": "organ_effect",
             "tests": [], "flag": "any"},
            {"id": "ckd_ua", "label": "Urate Nephropathy", "type": "organ_effect",
             "tests": ["creatinine", "egfr"], "flag": "any"},
            {"id": "cv_risk_ua", "label": "Cardiovascular Risk", "type": "organ_effect",
             "tests": [], "flag": "any"},
        ],
        "edges": [
            {"source": "uric_high", "target": "gout_attack",
             "mechanism": "Urate crystals deposit in joints causing acute inflammation"},
            {"source": "uric_high", "target": "kidney_stones_ua",
             "mechanism": "Uric acid supersaturation in urine forms stones"},
            {"source": "uric_high", "target": "ckd_ua",
             "mechanism": "Chronic urate deposition damages renal tubules"},
            {"source": "uric_high", "target": "cv_risk_ua",
             "mechanism": "Hyperuricemia promotes endothelial dysfunction and oxidative stress"},
        ],
    },
]


class BiomarkerCascadeEngine:
    """Analyzes patient labs against cascade knowledge base."""

    def analyze(self, profile_data: dict) -> dict:
        """
        Returns D3-compatible directed graph of biomarker cascades.

        Output:
        {
            "nodes": [
                {"id": "cortisol_high", "label": "Elevated Cortisol",
                 "type": "biomarker", "patient_has": true,
                 "patient_value": "28 mcg/dL", "cascade": "Cortisol-Metabolic"},
            ],
            "edges": [
                {"source": "cortisol_high", "target": "insulin_resist",
                 "mechanism": "..."},
            ],
            "active_cascades": [
                {"name": "Cortisol-Metabolic Cascade", "category": "...",
                 "active_nodes": 3, "total_nodes": 6},
            ],
        }
        """
        timeline = profile_data.get("clinical_timeline", {})
        labs = timeline.get("labs", [])

        # Build lab lookup: lowered name → {value, unit, flag, date}
        lab_lookup = self._build_lab_lookup(labs)

        all_nodes = []
        all_edges = []
        active_cascades = []

        for chain in CASCADE_CHAINS:
            chain_nodes = []
            active_count = 0

            for node_def in chain["nodes"]:
                patient_match = self._match_node(node_def, lab_lookup)
                node = {
                    "id": node_def["id"],
                    "label": node_def["label"],
                    "type": node_def["type"],
                    "cascade": chain["name"],
                    "category": chain["category"],
                    "patient_has": patient_match is not None,
                    "patient_value": patient_match.get("display") if patient_match else None,
                    "patient_flag": patient_match.get("flag") if patient_match else None,
                }
                chain_nodes.append(node)
                if patient_match:
                    active_count += 1

            # Only include cascades where at least 1 node matches patient data
            if active_count > 0:
                all_nodes.extend(chain_nodes)
                for edge in chain["edges"]:
                    all_edges.append({
                        "source": edge["source"],
                        "target": edge["target"],
                        "mechanism": edge["mechanism"],
                        "cascade": chain["name"],
                    })
                active_cascades.append({
                    "name": chain["name"],
                    "category": chain["category"],
                    "active_nodes": active_count,
                    "total_nodes": len(chain["nodes"]),
                })

        # Sort cascades by active node count descending
        active_cascades.sort(key=lambda c: -c["active_nodes"])

        logger.info(
            "Biomarker cascade analysis: %d active cascades, %d nodes, %d edges",
            len(active_cascades), len(all_nodes), len(all_edges),
        )

        return {
            "nodes": all_nodes,
            "edges": all_edges,
            "active_cascades": active_cascades,
        }

    # ── Helpers ───────────────────────────────────────

    def _build_lab_lookup(self, labs: list) -> dict:
        """Build lookup: lowered test name → latest result dict."""
        lookup = {}
        for lab in labs:
            name = lab.get("name", "").lower().strip()
            if not name:
                continue

            entry = {
                "value": lab.get("value", lab.get("value_text", "")),
                "unit": lab.get("unit", ""),
                "flag": (lab.get("flag") or "").lower(),
                "date": lab.get("test_date", ""),
            }

            # Keep most recent
            if name not in lookup or (entry["date"] > lookup[name]["date"]):
                lookup[name] = entry

        return lookup

    def _match_node(self, node_def: dict, lab_lookup: dict) -> Optional[dict]:
        """
        Check if a cascade node matches any of the patient's labs.
        Returns match info or None.
        """
        expected_flag = node_def.get("flag", "any")
        test_names = node_def.get("tests", [])

        for test in test_names:
            test_lower = test.lower()

            # Direct match
            match = lab_lookup.get(test_lower)
            if not match:
                # Partial match
                for lab_name, lab_entry in lab_lookup.items():
                    if test_lower in lab_name or lab_name in test_lower:
                        match = lab_entry
                        break

            if match:
                lab_flag = match.get("flag", "")
                # Check if the flag direction matches what we expect
                if expected_flag == "any":
                    if lab_flag and lab_flag not in ("normal", ""):
                        return {
                            "display": f"{match['value']} {match['unit']}".strip(),
                            "flag": lab_flag,
                        }
                elif expected_flag == "high":
                    if lab_flag in ("high", "critical high", "h", "critical"):
                        return {
                            "display": f"{match['value']} {match['unit']}".strip(),
                            "flag": lab_flag,
                        }
                elif expected_flag == "low":
                    if lab_flag in ("low", "critical low", "l"):
                        return {
                            "display": f"{match['value']} {match['unit']}".strip(),
                            "flag": lab_flag,
                        }

        return None
