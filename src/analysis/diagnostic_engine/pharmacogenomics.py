"""
Clinical Intelligence Hub — Pharmacogenomic Collision Engine

Expanded knowledge base of 15+ pharmacogenes mapping to common drugs.
Given a patient's genetic variants and active medications, identifies
gene-drug collisions where metabolizer status makes the drug dangerous
or ineffective.

Returns:
  - Collision alerts (gene + drug + severity + recommendation)
  - D3-compatible bipartite graph (drug nodes ↔ gene nodes, edges by severity)

Data model:
  - GeneticVariant (from models.py): gene, variant, phenotype, clinical_significance
  - Medication: name, dosage, frequency, reason
  - DrugInteraction: drug_a, drug_b, gene, severity, description, source

Results feed into:
  - PGx Collision Map overlay (D3 bipartite graph)
  - Doctor Visit Prep
  - Flags view
"""

import logging
from typing import Optional

logger = logging.getLogger("CIH-Pharmacogenomics")


# ── PGx Knowledge Base ───────────────────────────────────
#
# Each gene has a set of metabolizer phenotypes, each listing:
#   drugs_affected  — list of drug names (lowered for matching)
#   severity        — "critical", "high", "moderate"
#   risk            — clinical risk description
#   impact          — what the patient will experience
#   action          — recommended clinical action

PGX_INTERACTIONS = {
    # ── CYP2C19 (Antiplatelet / Antidepressants / Antifungals) ──
    "CYP2C19": {
        "poor_metabolizer": {
            "drugs_affected": [
                "clopidogrel", "plavix",
                "citalopram", "celexa",
                "escitalopram", "lexapro",
                "voriconazole",
                "omeprazole", "prilosec",
                "pantoprazole", "protonix",
            ],
            "severity": "critical",
            "risk": "Prodrug cannot convert to active form; drug is ineffective.",
            "impact": "Clopidogrel: high risk of stent thrombosis and cardiovascular events. SSRIs: inadequate antidepressant response. PPIs: suboptimal acid suppression.",
            "action": "Consider alternative antiplatelet (prasugrel/ticagrelor), alternative antidepressant, or PPI dose adjustment.",
        },
        "ultra_rapid_metabolizer": {
            "drugs_affected": [
                "clopidogrel", "plavix",
                "omeprazole", "prilosec",
            ],
            "severity": "high",
            "risk": "Over-activation of prodrug causing excessive effect.",
            "impact": "Clopidogrel: increased bleeding risk. PPIs: reduced efficacy due to rapid clearance.",
            "action": "Monitor for hemorrhage with clopidogrel. May need higher PPI doses.",
        },
    },

    # ── CYP2D6 (Opioids / Antidepressants / Tamoxifen) ──────
    "CYP2D6": {
        "poor_metabolizer": {
            "drugs_affected": [
                "codeine", "tramadol",
                "tamoxifen", "nolvadex",
                "hydrocodone",
                "oxycodone",
                "metoprolol",
                "paroxetine", "paxil",
                "fluoxetine", "prozac",
                "atomoxetine", "strattera",
            ],
            "severity": "critical",
            "risk": "Prodrug cannot convert to active metabolite; drug is ineffective or accumulates as parent compound.",
            "impact": "Codeine/tramadol: no pain relief. Tamoxifen: treatment failure in breast cancer. Beta-blockers: excessive effect.",
            "action": "Use alternative analgesics (non-prodrug opioids). Consider aromatase inhibitor for tamoxifen. Reduce beta-blocker dose.",
        },
        "ultra_rapid_metabolizer": {
            "drugs_affected": [
                "codeine", "tramadol",
                "hydrocodone",
            ],
            "severity": "critical",
            "risk": "Rapid conversion to active form causing severe toxicity.",
            "impact": "Risk of respiratory depression and fatal overdose even at normal doses. Especially dangerous in children and nursing mothers.",
            "action": "AVOID codeine and tramadol entirely. Use non-opioid analgesics or morphine (not a prodrug).",
        },
        "intermediate_metabolizer": {
            "drugs_affected": [
                "tamoxifen", "nolvadex",
                "codeine",
            ],
            "severity": "moderate",
            "risk": "Reduced conversion to active metabolite.",
            "impact": "Tamoxifen: suboptimal endoxifen levels; may reduce breast cancer protection. Codeine: diminished analgesia.",
            "action": "Consider endoxifen level monitoring for tamoxifen. Alternative analgesics for codeine.",
        },
    },

    # ── DPYD (Fluoropyrimidines) ─────────────────────────────
    "DPYD": {
        "poor_metabolizer": {
            "drugs_affected": [
                "fluorouracil", "5-fu",
                "capecitabine", "xeloda",
                "tegafur",
            ],
            "severity": "critical",
            "risk": "Severe, potentially fatal toxicity — drug cannot be cleared from the system.",
            "impact": "Life-threatening neutropenia, mucositis, diarrhea, and death. Even standard doses can be lethal.",
            "action": "REDUCE dose by 50% or AVOID entirely. Requires pre-treatment DPYD testing per FDA label.",
        },
        "intermediate_metabolizer": {
            "drugs_affected": [
                "fluorouracil", "5-fu",
                "capecitabine", "xeloda",
            ],
            "severity": "high",
            "risk": "Increased toxicity due to reduced drug clearance.",
            "impact": "Higher risk of severe myelosuppression and GI toxicity.",
            "action": "Start at reduced dose (25-50% reduction) with careful monitoring.",
        },
    },

    # ── CYP2C9 (Warfarin / NSAIDs / Sulfonylureas) ──────────
    "CYP2C9": {
        "poor_metabolizer": {
            "drugs_affected": [
                "warfarin", "coumadin",
                "phenytoin", "dilantin",
                "celecoxib", "celebrex",
                "glipizide",
                "losartan", "cozaar",
            ],
            "severity": "critical",
            "risk": "Dramatically reduced drug clearance causing accumulation and toxicity.",
            "impact": "Warfarin: severe bleeding risk at standard doses. Phenytoin: CNS toxicity. Celecoxib: GI bleeding.",
            "action": "Warfarin requires 50-80% dose reduction + VKORC1 genotype. Reduce phenytoin dose. Monitor INR closely.",
        },
        "intermediate_metabolizer": {
            "drugs_affected": [
                "warfarin", "coumadin",
                "phenytoin", "dilantin",
            ],
            "severity": "moderate",
            "risk": "Moderately reduced drug clearance.",
            "impact": "May need dose reduction to prevent accumulation.",
            "action": "Use pharmacogenomic-guided dosing for warfarin. Monitor phenytoin levels.",
        },
    },

    # ── CYP3A4 (Huge substrate list) ─────────────────────────
    "CYP3A4": {
        "poor_metabolizer": {
            "drugs_affected": [
                "simvastatin", "zocor",
                "atorvastatin", "lipitor",
                "tacrolimus", "prograf",
                "cyclosporine",
                "midazolam",
                "fentanyl",
                "quetiapine", "seroquel",
                "apixaban", "eliquis",
            ],
            "severity": "high",
            "risk": "Reduced clearance of drugs metabolized by CYP3A4.",
            "impact": "Statins: rhabdomyolysis risk. Tacrolimus: nephrotoxicity. Benzodiazepines: excessive sedation. Fentanyl: respiratory depression.",
            "action": "Lower statin doses. Monitor tacrolimus trough levels. Reduce benzodiazepine/opioid doses.",
        },
    },

    # ── CYP1A2 (Caffeine / Theophylline / Clozapine) ────────
    "CYP1A2": {
        "poor_metabolizer": {
            "drugs_affected": [
                "clozapine", "clozaril",
                "theophylline",
                "duloxetine", "cymbalta",
                "olanzapine", "zyprexa",
            ],
            "severity": "high",
            "risk": "Reduced drug clearance causing accumulation.",
            "impact": "Clozapine: agranulocytosis risk at standard doses. Theophylline: seizures. Olanzapine: excessive sedation.",
            "action": "Reduce clozapine dose by 50%. Monitor theophylline levels. Lower olanzapine dose.",
        },
        "ultra_rapid_metabolizer": {
            "drugs_affected": [
                "clozapine", "clozaril",
                "olanzapine", "zyprexa",
            ],
            "severity": "moderate",
            "risk": "Rapid clearance reducing drug efficacy.",
            "impact": "May need higher doses to achieve therapeutic levels.",
            "action": "Monitor clinical response. May need dose increase.",
        },
    },

    # ── UGT1A1 (Irinotecan / Atazanavir) ────────────────────
    "UGT1A1": {
        "poor_metabolizer": {
            "drugs_affected": [
                "irinotecan", "camptosar",
                "atazanavir", "reyataz",
            ],
            "severity": "critical",
            "risk": "Impaired glucuronidation causing severe toxicity.",
            "impact": "Irinotecan: life-threatening neutropenia and diarrhea. Atazanavir: severe hyperbilirubinemia (Gilbert syndrome link).",
            "action": "Reduce irinotecan dose by 30-50%. Monitor bilirubin with atazanavir.",
        },
    },

    # ── TPMT (Thiopurines — Azathioprine / 6-MP) ────────────
    "TPMT": {
        "poor_metabolizer": {
            "drugs_affected": [
                "azathioprine", "imuran",
                "mercaptopurine", "6-mp", "purinethol",
                "thioguanine",
            ],
            "severity": "critical",
            "risk": "Thiopurine accumulates as active metabolite causing fatal myelosuppression.",
            "impact": "Severe pancytopenia, life-threatening infections.",
            "action": "REDUCE dose by 90% or AVOID. Pre-treatment TPMT testing is standard of care.",
        },
        "intermediate_metabolizer": {
            "drugs_affected": [
                "azathioprine", "imuran",
                "mercaptopurine", "6-mp",
            ],
            "severity": "high",
            "risk": "Reduced thiopurine metabolism increasing toxicity risk.",
            "impact": "Higher risk of myelosuppression at standard doses.",
            "action": "Start at 30-50% reduced dose with CBC monitoring.",
        },
    },

    # ── SLCO1B1 (Statin Myopathy) ───────────────────────────
    "SLCO1B1": {
        "poor_transporter": {
            "drugs_affected": [
                "simvastatin", "zocor",
                "atorvastatin", "lipitor",
                "rosuvastatin", "crestor",
                "pravastatin", "pravachol",
            ],
            "severity": "high",
            "risk": "Impaired hepatic uptake of statins increases plasma levels.",
            "impact": "Significantly increased risk of statin-induced myopathy and rhabdomyolysis.",
            "action": "Avoid simvastatin >20mg. Consider pravastatin or rosuvastatin (lower SLCO1B1 dependence). Monitor CK levels.",
        },
    },

    # ── HLA-B (Severe Drug Hypersensitivity) ─────────────────
    "HLA-B": {
        "hla_b_5701_positive": {
            "drugs_affected": [
                "abacavir", "ziagen",
            ],
            "severity": "critical",
            "risk": "Hypersensitivity reaction — potentially fatal.",
            "impact": "Abacavir hypersensitivity syndrome: fever, rash, GI symptoms, respiratory distress. Can be fatal on rechallenge.",
            "action": "NEVER prescribe abacavir. FDA requires HLA-B*5701 testing before starting. This is an absolute contraindication.",
        },
        "hla_b_1502_positive": {
            "drugs_affected": [
                "carbamazepine", "tegretol",
                "phenytoin", "dilantin",
                "oxcarbazepine", "trileptal",
            ],
            "severity": "critical",
            "risk": "Stevens-Johnson Syndrome / Toxic Epidermal Necrolysis.",
            "impact": "Life-threatening skin reaction. Higher prevalence in Southeast Asian ancestry.",
            "action": "AVOID carbamazepine entirely in HLA-B*1502 carriers. FDA requires testing before starting.",
        },
        "hla_b_5801_positive": {
            "drugs_affected": [
                "allopurinol", "zyloprim",
            ],
            "severity": "critical",
            "risk": "Severe cutaneous adverse reactions (SCAR) including SJS/TEN.",
            "impact": "Life-threatening skin reaction to allopurinol. Higher prevalence in Korean, Thai, and African American populations.",
            "action": "AVOID allopurinol. Use febuxostat as alternative for gout.",
        },
    },

    # ── VKORC1 (Warfarin Sensitivity) ────────────────────────
    "VKORC1": {
        "high_sensitivity": {
            "drugs_affected": [
                "warfarin", "coumadin",
            ],
            "severity": "high",
            "risk": "Warfarin target is highly sensitive — standard doses cause excessive anticoagulation.",
            "impact": "Major bleeding risk at standard warfarin doses.",
            "action": "Reduce warfarin starting dose by 25-50%. Use combined CYP2C9 + VKORC1 dosing algorithm.",
        },
        "low_sensitivity": {
            "drugs_affected": [
                "warfarin", "coumadin",
            ],
            "severity": "moderate",
            "risk": "Warfarin target is resistant — standard doses may be insufficient.",
            "impact": "Subtherapeutic INR at standard doses; inadequate anticoagulation.",
            "action": "May need higher warfarin doses. Use pharmacogenomic-guided dosing algorithm.",
        },
    },

    # ── G6PD (Hemolytic Anemia Risk) ─────────────────────────
    "G6PD": {
        "deficient": {
            "drugs_affected": [
                "primaquine",
                "dapsone",
                "rasburicase", "elitek",
                "methylene blue",
                "nitrofurantoin", "macrobid",
                "sulfamethoxazole", "bactrim",
            ],
            "severity": "critical",
            "risk": "Drug-induced hemolytic anemia in G6PD-deficient patients.",
            "impact": "Acute hemolysis, jaundice, dark urine, potentially fatal anemia. Higher prevalence in African, Mediterranean, and Asian ancestry.",
            "action": "AVOID oxidant drugs. Screen before prescribing primaquine or rasburicase. Use alternative antibiotics.",
        },
    },

    # ── NUDT15 (Thiopurine — East Asian populations) ─────────
    "NUDT15": {
        "poor_metabolizer": {
            "drugs_affected": [
                "azathioprine", "imuran",
                "mercaptopurine", "6-mp",
            ],
            "severity": "critical",
            "risk": "Severe thiopurine toxicity (similar to TPMT but more prevalent in East Asian populations).",
            "impact": "Fatal leukopenia and myelosuppression at standard doses.",
            "action": "REDUCE dose dramatically or AVOID. Test NUDT15 alongside TPMT before starting thiopurines.",
        },
    },

    # ── CYP2B6 (Efavirenz / Methadone) ──────────────────────
    "CYP2B6": {
        "poor_metabolizer": {
            "drugs_affected": [
                "efavirenz", "sustiva",
                "methadone",
            ],
            "severity": "high",
            "risk": "Reduced clearance causing CNS toxicity.",
            "impact": "Efavirenz: severe neuropsychiatric side effects (vivid dreams, psychosis, suicidality). Methadone: QT prolongation.",
            "action": "Reduce efavirenz dose or switch to alternative ART. Monitor QTc with methadone.",
        },
    },

    # ── CYP3A5 (Tacrolimus Dosing) ──────────────────────────
    "CYP3A5": {
        "non_expressor": {
            "drugs_affected": [
                "tacrolimus", "prograf",
            ],
            "severity": "moderate",
            "risk": "Higher tacrolimus levels at standard doses.",
            "impact": "Nephrotoxicity and neurotoxicity from tacrolimus accumulation.",
            "action": "Start at lower tacrolimus dose. Monitor trough levels closely.",
        },
        "expressor": {
            "drugs_affected": [
                "tacrolimus", "prograf",
            ],
            "severity": "moderate",
            "risk": "Rapid tacrolimus clearance — standard doses may be insufficient.",
            "impact": "Risk of transplant rejection due to subtherapeutic levels.",
            "action": "May need higher starting dose. Frequent trough level monitoring.",
        },
    },

    # ── IFNL3 (IL28B) (Hepatitis C Response) ────────────────
    "IFNL3": {
        "unfavorable_genotype": {
            "drugs_affected": [
                "peginterferon", "pegasys",
                "ribavirin", "copegus",
            ],
            "severity": "moderate",
            "risk": "Reduced response to interferon-based hepatitis C therapy.",
            "impact": "Lower sustained virologic response (SVR) rates.",
            "action": "Consider direct-acting antiviral (DAA) regimens instead (sofosbuvir-based).",
        },
    },

    # ── CYP4F2 (Warfarin — additional modifier) ─────────────
    "CYP4F2": {
        "high_activity": {
            "drugs_affected": [
                "warfarin", "coumadin",
            ],
            "severity": "moderate",
            "risk": "Increased vitamin K clearance requiring higher warfarin dose.",
            "impact": "Subtherapeutic INR if dose not adjusted.",
            "action": "Incorporate into multi-gene warfarin dosing algorithm (CYP2C9 + VKORC1 + CYP4F2).",
        },
    },
}


# ── Phenotype Synonym Matching ───────────────────────────
#
# Patients' genetic reports use various terms. We need flexible
# matching from free-text phenotype to our knowledge base keys.

PHENOTYPE_ALIASES = {
    # Poor metabolizer variants
    "poor_metabolizer": [
        "poor metabolizer", "pm", "poor", "absent activity",
        "no activity", "non-functional", "null/null",
    ],
    "ultra_rapid_metabolizer": [
        "ultra rapid metabolizer", "ultra-rapid metabolizer",
        "ultrarapid", "um", "increased activity",
    ],
    "intermediate_metabolizer": [
        "intermediate metabolizer", "im", "intermediate",
        "decreased activity", "reduced activity",
    ],
    # HLA-specific
    "hla_b_5701_positive": [
        "hla-b*5701 positive", "hla-b*57:01 positive",
        "5701 positive", "hla-b*5701", "*5701",
    ],
    "hla_b_1502_positive": [
        "hla-b*1502 positive", "hla-b*15:02 positive",
        "1502 positive", "hla-b*1502", "*1502",
    ],
    "hla_b_5801_positive": [
        "hla-b*5801 positive", "hla-b*58:01 positive",
        "5801 positive", "hla-b*5801", "*5801",
    ],
    # VKORC1
    "high_sensitivity": [
        "high sensitivity", "sensitive", "low-dose warfarin",
        "a/a genotype", "rs9923231 t/t",
    ],
    "low_sensitivity": [
        "low sensitivity", "resistant", "high-dose warfarin",
        "g/g genotype", "rs9923231 g/g",
    ],
    # G6PD
    "deficient": [
        "deficient", "deficiency", "g6pd deficiency",
        "g6pd deficient", "class ii", "class iii",
    ],
    # SLCO1B1
    "poor_transporter": [
        "poor transporter", "decreased function",
        "521 t/c", "521 c/c", "rs4149056 c/c", "rs4149056 t/c",
    ],
    # CYP3A5
    "non_expressor": [
        "non-expressor", "non expressor", "*3/*3",
        "cyp3a5 non-expressor",
    ],
    "expressor": [
        "expressor", "*1/*1", "*1/*3",
        "cyp3a5 expressor",
    ],
    # NUDT15
    # Shares poor/intermediate from above
    # IFNL3
    "unfavorable_genotype": [
        "unfavorable", "ct genotype", "tt genotype",
        "non-cc", "rs12979860 ct", "rs12979860 tt",
    ],
    # CYP4F2
    "high_activity": [
        "high activity", "increased function",
        "v433m", "rs2108622",
    ],
}


class PharmacogenomicEngine:
    """
    Scans patient's genetic variants + active medications for
    gene-drug collisions. Returns alerts and D3-compatible
    bipartite graph data.
    """

    def analyze(self, profile_data: dict) -> dict:
        """
        Returns:
        {
            "collisions": [
                {
                    "gene": "CYP2D6",
                    "phenotype": "Poor Metabolizer",
                    "drug": "Codeine",
                    "severity": "critical",
                    "risk": "...",
                    "impact": "...",
                    "action": "...",
                },
            ],
            "gene_nodes": [
                {"id": "gene_CYP2D6", "label": "CYP2D6", "phenotype": "Poor Metabolizer",
                 "type": "gene"},
            ],
            "drug_nodes": [
                {"id": "drug_codeine", "label": "Codeine", "type": "drug",
                 "is_active": true},
            ],
            "edges": [
                {"source": "gene_CYP2D6", "target": "drug_codeine",
                 "severity": "critical", "risk": "..."},
            ],
            "summary": {
                "total_genes_tested": 5,
                "total_collisions": 3,
                "critical_count": 1,
                "high_count": 1,
                "moderate_count": 1,
            },
        }
        """
        timeline = profile_data.get("clinical_timeline", {})
        genetics = timeline.get("genetics", [])
        medications = timeline.get("medications", [])

        # Build lookups
        gene_profiles = self._parse_genetic_profiles(genetics)
        active_meds = self._parse_medications(medications)

        collisions = []
        gene_nodes = {}
        drug_nodes = {}
        edges = []
        seen_edges = set()
        matched_med_names = set()  # Track which meds already have a node

        for gene_name, phenotype_key, phenotype_display in gene_profiles:
            gene_upper = gene_name.upper()

            # Look up this gene in our knowledge base
            if gene_upper not in PGX_INTERACTIONS:
                continue

            profiles = PGX_INTERACTIONS[gene_upper]
            if phenotype_key not in profiles:
                continue

            profile = profiles[phenotype_key]

            # Check each drug in this profile against patient's active meds
            for drug_pattern in profile["drugs_affected"]:
                matched_med = self._match_medication(drug_pattern, active_meds)
                if not matched_med:
                    continue

                drug_display = matched_med.get("display_name", drug_pattern.capitalize())
                gene_id = "gene_" + gene_upper
                drug_id = "drug_" + drug_pattern.replace(" ", "_").replace("-", "_")
                edge_key = (gene_id, drug_id)

                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)

                # Add collision
                collisions.append({
                    "gene": gene_upper,
                    "phenotype": phenotype_display,
                    "drug": drug_display,
                    "severity": profile["severity"],
                    "risk": profile["risk"],
                    "impact": profile["impact"],
                    "action": profile["action"],
                })

                # Build graph nodes
                if gene_id not in gene_nodes:
                    gene_nodes[gene_id] = {
                        "id": gene_id,
                        "label": gene_upper,
                        "phenotype": phenotype_display,
                        "type": "gene",
                    }

                if drug_id not in drug_nodes:
                    drug_nodes[drug_id] = {
                        "id": drug_id,
                        "label": drug_display,
                        "type": "drug",
                        "is_active": True,
                    }

                matched_med_names.add(matched_med["name_lower"])

                edges.append({
                    "source": gene_id,
                    "target": drug_id,
                    "severity": profile["severity"],
                    "risk": profile["risk"],
                    "action": profile["action"],
                })

        # Also add gene nodes for genes tested but with no collisions
        for gene_name, phenotype_key, phenotype_display in gene_profiles:
            gene_id = "gene_" + gene_name.upper()
            if gene_id not in gene_nodes:
                gene_nodes[gene_id] = {
                    "id": gene_id,
                    "label": gene_name.upper(),
                    "phenotype": phenotype_display,
                    "type": "gene",
                    "no_collisions": True,
                }

        # Add drug nodes for all active medications (even if no collision)
        for med in active_meds:
            if med["name_lower"] in matched_med_names:
                continue  # Already has a node from collision matching
            drug_id = "drug_" + med["name_lower"].replace(" ", "_").replace("-", "_")
            if drug_id not in drug_nodes:
                drug_nodes[drug_id] = {
                    "id": drug_id,
                    "label": med["display_name"],
                    "type": "drug",
                    "is_active": True,
                    "no_collisions": True,
                }

        # Summary
        critical = sum(1 for c in collisions if c["severity"] == "critical")
        high = sum(1 for c in collisions if c["severity"] == "high")
        moderate = sum(1 for c in collisions if c["severity"] == "moderate")

        return {
            "collisions": sorted(collisions, key=lambda c: (
                {"critical": 0, "high": 1, "moderate": 2}.get(c["severity"], 3),
                c["gene"],
            )),
            "gene_nodes": list(gene_nodes.values()),
            "drug_nodes": list(drug_nodes.values()),
            "edges": edges,
            "summary": {
                "total_genes_tested": len(gene_profiles),
                "total_collisions": len(collisions),
                "critical_count": critical,
                "high_count": high,
                "moderate_count": moderate,
            },
        }

    # ── Internal Helpers ─────────────────────────────────

    def _parse_genetic_profiles(self, genetics: list) -> list:
        """
        Parse genetic variants into (gene_name, phenotype_key, phenotype_display) tuples.

        Handles various formats:
          - gene="CYP2D6", phenotype="Poor Metabolizer"
          - gene="HLA-B", variant="*5701", phenotype="Positive"
          - gene="G6PD", clinical_significance="Deficient"
        """
        profiles = []

        for variant in genetics:
            gene = (variant.get("gene") or "").strip()
            if not gene:
                continue

            # Build a text blob to match against phenotype aliases
            phenotype_text = " ".join([
                (variant.get("phenotype") or ""),
                (variant.get("variant") or ""),
                (variant.get("clinical_significance") or ""),
                (variant.get("implications") or ""),
            ]).lower().strip()

            if not phenotype_text:
                continue

            # Try to match against known phenotype aliases
            for pheno_key, aliases in PHENOTYPE_ALIASES.items():
                for alias in aliases:
                    if alias in phenotype_text:
                        # Build display name
                        display = variant.get("phenotype") or pheno_key.replace("_", " ").title()
                        profiles.append((gene, pheno_key, display))
                        break
                else:
                    continue
                break  # Found a match for this variant

        return profiles

    def _parse_medications(self, medications: list) -> list:
        """Parse active medications into a lookup-friendly list."""
        active = []
        for med in medications:
            status = (med.get("status") or "").lower()
            if status not in ("active", "current", ""):
                continue

            name = (med.get("name") or "").strip()
            if not name:
                continue

            active.append({
                "name_lower": name.lower(),
                "display_name": name,
            })

        return active

    def _match_medication(self, drug_pattern: str, active_meds: list) -> dict:
        """
        Check if any active medication matches a drug pattern.
        Handles brand/generic name variants via substring matching.
        """
        pattern = drug_pattern.lower()
        for med in active_meds:
            if pattern in med["name_lower"] or med["name_lower"] in pattern:
                return med
        return None


# ── Legacy Compatibility ─────────────────────────────────

def analyze_pgx_collisions(profile_data: dict = None, db_path: str = None):
    """
    Legacy wrapper. Accepts either profile_data dict (new) or
    db_path (old, returns empty — SQLite no longer used).
    """
    if profile_data:
        engine = PharmacogenomicEngine()
        result = engine.analyze(profile_data)
        return result.get("collisions", [])

    logger.warning("analyze_pgx_collisions called with db_path — SQLite no longer used")
    return []
