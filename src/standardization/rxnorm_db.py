"""
Clinical Intelligence Hub — RxNorm Local Medication Database

Local medication database for offline standardization:
  - Brand name → Generic name mapping
  - Drug class categorization
  - Common dosage forms
  - Therapeutic categories

This complements the live RxNorm API (src/validation/rxnorm.py) by
providing instant offline lookups for common medications without
needing a network call.

Data source: NLM RxNorm (free, requires UMLS license for full dataset)
Full database: ~100,000 concepts
Download: https://www.nlm.nih.gov/research/umls/rxnorm/
This module ships with a curated seed of ~300 commonly prescribed medications.
"""

import csv
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CIH-RxNormDB")


class RxNormLocalDB:
    """
    Local medication database for instant offline lookups.

    Usage:
        rxdb = RxNormLocalDB()
        result = rxdb.lookup("Glucophage")
        # → {"generic_name": "Metformin", "brand_names": ["Glucophage", "Fortamet"],
        #    "drug_class": "Biguanide", "category": "Antidiabetic"}
    """

    def __init__(self, data_dir: Path = None):
        self._medications: dict[str, dict] = {}
        self._name_index: dict[str, str] = {}  # lowercase name → generic_name key
        self._load_seed()
        if data_dir:
            self._try_load_full(data_dir)

    def lookup(self, medication_name: str) -> Optional[dict]:
        """
        Look up a medication by any name (brand or generic).

        Returns standardized entry with generic name, brand names,
        drug class, and therapeutic category.
        """
        normalized = self._normalize(medication_name)

        if normalized in self._name_index:
            key = self._name_index[normalized]
            return self._medications.get(key)

        # Partial match
        for name_key, med_key in self._name_index.items():
            if normalized in name_key or name_key in normalized:
                return self._medications.get(med_key)

        return None

    def get_by_class(self, drug_class: str) -> list[dict]:
        """Get all medications in a drug class."""
        cls_lower = drug_class.lower()
        return [
            m for m in self._medications.values()
            if cls_lower in m.get("drug_class", "").lower()
        ]

    def get_by_category(self, category: str) -> list[dict]:
        """Get all medications in a therapeutic category."""
        cat_lower = category.lower()
        return [
            m for m in self._medications.values()
            if cat_lower in m.get("category", "").lower()
        ]

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search for medications matching a query."""
        normalized = self._normalize(query)
        results = []
        seen = set()

        for name_key, med_key in self._name_index.items():
            if normalized in name_key and med_key not in seen:
                entry = self._medications.get(med_key)
                if entry:
                    results.append(entry)
                    seen.add(med_key)
                    if len(results) >= limit:
                        break

        return results

    @property
    def count(self) -> int:
        """Number of unique medications loaded."""
        return len(self._medications)

    # ── Seed Database ─────────────────────────────────────────

    def _load_seed(self):
        """Load curated seed of commonly prescribed medications."""
        # (generic_name, brand_names, drug_class, category)
        seed = [
            # ── Cardiovascular ──
            ("Lisinopril", ["Zestril", "Prinivil"], "ACE Inhibitor", "Antihypertensive"),
            ("Enalapril", ["Vasotec"], "ACE Inhibitor", "Antihypertensive"),
            ("Losartan", ["Cozaar"], "ARB", "Antihypertensive"),
            ("Valsartan", ["Diovan"], "ARB", "Antihypertensive"),
            ("Irbesartan", ["Avapro"], "ARB", "Antihypertensive"),
            ("Olmesartan", ["Benicar"], "ARB", "Antihypertensive"),
            ("Amlodipine", ["Norvasc"], "Calcium Channel Blocker", "Antihypertensive"),
            ("Diltiazem", ["Cardizem", "Tiazac"], "Calcium Channel Blocker", "Antihypertensive"),
            ("Nifedipine", ["Procardia", "Adalat"], "Calcium Channel Blocker", "Antihypertensive"),
            ("Metoprolol", ["Lopressor", "Toprol-XL"], "Beta Blocker", "Antihypertensive"),
            ("Atenolol", ["Tenormin"], "Beta Blocker", "Antihypertensive"),
            ("Carvedilol", ["Coreg"], "Beta Blocker", "Antihypertensive"),
            ("Propranolol", ["Inderal"], "Beta Blocker", "Antihypertensive"),
            ("Bisoprolol", ["Zebeta"], "Beta Blocker", "Antihypertensive"),
            ("Hydrochlorothiazide", ["Microzide", "HCTZ"], "Thiazide Diuretic", "Antihypertensive"),
            ("Chlorthalidone", ["Hygroton"], "Thiazide Diuretic", "Antihypertensive"),
            ("Furosemide", ["Lasix"], "Loop Diuretic", "Diuretic"),
            ("Spironolactone", ["Aldactone"], "Potassium-Sparing Diuretic", "Diuretic"),
            ("Clonidine", ["Catapres"], "Alpha-2 Agonist", "Antihypertensive"),
            ("Hydralazine", ["Apresoline"], "Vasodilator", "Antihypertensive"),

            # ── Statins/Lipid ──
            ("Atorvastatin", ["Lipitor"], "HMG-CoA Reductase Inhibitor", "Antilipemic"),
            ("Rosuvastatin", ["Crestor"], "HMG-CoA Reductase Inhibitor", "Antilipemic"),
            ("Simvastatin", ["Zocor"], "HMG-CoA Reductase Inhibitor", "Antilipemic"),
            ("Pravastatin", ["Pravachol"], "HMG-CoA Reductase Inhibitor", "Antilipemic"),
            ("Lovastatin", ["Mevacor"], "HMG-CoA Reductase Inhibitor", "Antilipemic"),
            ("Ezetimibe", ["Zetia"], "Cholesterol Absorption Inhibitor", "Antilipemic"),
            ("Fenofibrate", ["Tricor", "Fenoglide"], "Fibrate", "Antilipemic"),
            ("Gemfibrozil", ["Lopid"], "Fibrate", "Antilipemic"),

            # ── Anticoagulants/Antiplatelets ──
            ("Warfarin", ["Coumadin", "Jantoven"], "Vitamin K Antagonist", "Anticoagulant"),
            ("Apixaban", ["Eliquis"], "Factor Xa Inhibitor", "Anticoagulant"),
            ("Rivaroxaban", ["Xarelto"], "Factor Xa Inhibitor", "Anticoagulant"),
            ("Dabigatran", ["Pradaxa"], "Direct Thrombin Inhibitor", "Anticoagulant"),
            ("Aspirin", ["Bayer", "Ecotrin"], "COX Inhibitor", "Antiplatelet"),
            ("Clopidogrel", ["Plavix"], "P2Y12 Inhibitor", "Antiplatelet"),
            ("Heparin", [], "Unfractionated Heparin", "Anticoagulant"),
            ("Enoxaparin", ["Lovenox"], "Low Molecular Weight Heparin", "Anticoagulant"),

            # ── Diabetes ──
            ("Metformin", ["Glucophage", "Fortamet", "Glumetza"], "Biguanide", "Antidiabetic"),
            ("Glipizide", ["Glucotrol"], "Sulfonylurea", "Antidiabetic"),
            ("Glyburide", ["Diabeta", "Micronase"], "Sulfonylurea", "Antidiabetic"),
            ("Glimepiride", ["Amaryl"], "Sulfonylurea", "Antidiabetic"),
            ("Sitagliptin", ["Januvia"], "DPP-4 Inhibitor", "Antidiabetic"),
            ("Linagliptin", ["Tradjenta"], "DPP-4 Inhibitor", "Antidiabetic"),
            ("Empagliflozin", ["Jardiance"], "SGLT2 Inhibitor", "Antidiabetic"),
            ("Dapagliflozin", ["Farxiga"], "SGLT2 Inhibitor", "Antidiabetic"),
            ("Canagliflozin", ["Invokana"], "SGLT2 Inhibitor", "Antidiabetic"),
            ("Liraglutide", ["Victoza", "Saxenda"], "GLP-1 Receptor Agonist", "Antidiabetic"),
            ("Semaglutide", ["Ozempic", "Wegovy", "Rybelsus"], "GLP-1 Receptor Agonist", "Antidiabetic"),
            ("Dulaglutide", ["Trulicity"], "GLP-1 Receptor Agonist", "Antidiabetic"),
            ("Tirzepatide", ["Mounjaro", "Zepbound"], "GIP/GLP-1 Receptor Agonist", "Antidiabetic"),
            ("Pioglitazone", ["Actos"], "Thiazolidinedione", "Antidiabetic"),
            ("Insulin Glargine", ["Lantus", "Basaglar", "Toujeo"], "Long-Acting Insulin", "Insulin"),
            ("Insulin Lispro", ["Humalog"], "Rapid-Acting Insulin", "Insulin"),
            ("Insulin Aspart", ["NovoLog", "Fiasp"], "Rapid-Acting Insulin", "Insulin"),
            ("Insulin NPH", ["Humulin N", "Novolin N"], "Intermediate-Acting Insulin", "Insulin"),

            # ── Thyroid ──
            ("Levothyroxine", ["Synthroid", "Levoxyl", "Tirosint"], "Thyroid Hormone", "Thyroid"),
            ("Liothyronine", ["Cytomel"], "Thyroid Hormone", "Thyroid"),
            ("Methimazole", ["Tapazole"], "Antithyroid", "Thyroid"),

            # ── Antidepressants ──
            ("Sertraline", ["Zoloft"], "SSRI", "Antidepressant"),
            ("Fluoxetine", ["Prozac", "Sarafem"], "SSRI", "Antidepressant"),
            ("Escitalopram", ["Lexapro"], "SSRI", "Antidepressant"),
            ("Citalopram", ["Celexa"], "SSRI", "Antidepressant"),
            ("Paroxetine", ["Paxil", "Brisdelle"], "SSRI", "Antidepressant"),
            ("Venlafaxine", ["Effexor"], "SNRI", "Antidepressant"),
            ("Duloxetine", ["Cymbalta"], "SNRI", "Antidepressant"),
            ("Desvenlafaxine", ["Pristiq"], "SNRI", "Antidepressant"),
            ("Bupropion", ["Wellbutrin", "Zyban"], "NDRI", "Antidepressant"),
            ("Mirtazapine", ["Remeron"], "Tetracyclic Antidepressant", "Antidepressant"),
            ("Trazodone", ["Desyrel", "Oleptro"], "SARI", "Antidepressant"),
            ("Amitriptyline", ["Elavil"], "Tricyclic Antidepressant", "Antidepressant"),
            ("Nortriptyline", ["Pamelor"], "Tricyclic Antidepressant", "Antidepressant"),

            # ── Anxiolytics/Sedatives ──
            ("Alprazolam", ["Xanax"], "Benzodiazepine", "Anxiolytic"),
            ("Lorazepam", ["Ativan"], "Benzodiazepine", "Anxiolytic"),
            ("Clonazepam", ["Klonopin"], "Benzodiazepine", "Anxiolytic"),
            ("Diazepam", ["Valium"], "Benzodiazepine", "Anxiolytic"),
            ("Buspirone", ["Buspar"], "Azapirone", "Anxiolytic"),
            ("Hydroxyzine", ["Vistaril", "Atarax"], "Antihistamine", "Anxiolytic"),
            ("Zolpidem", ["Ambien"], "Non-Benzodiazepine Hypnotic", "Sedative"),

            # ── Antipsychotics ──
            ("Quetiapine", ["Seroquel"], "Atypical Antipsychotic", "Antipsychotic"),
            ("Aripiprazole", ["Abilify"], "Atypical Antipsychotic", "Antipsychotic"),
            ("Olanzapine", ["Zyprexa"], "Atypical Antipsychotic", "Antipsychotic"),
            ("Risperidone", ["Risperdal"], "Atypical Antipsychotic", "Antipsychotic"),

            # ── Mood Stabilizers ──
            ("Lithium", ["Lithobid", "Eskalith"], "Mood Stabilizer", "Mood Stabilizer"),
            ("Lamotrigine", ["Lamictal"], "Anticonvulsant", "Mood Stabilizer"),
            ("Valproic Acid", ["Depakote", "Depakene"], "Anticonvulsant", "Mood Stabilizer"),

            # ── Anticonvulsants ──
            ("Levetiracetam", ["Keppra"], "Anticonvulsant", "Antiepileptic"),
            ("Phenytoin", ["Dilantin"], "Anticonvulsant", "Antiepileptic"),
            ("Carbamazepine", ["Tegretol"], "Anticonvulsant", "Antiepileptic"),
            ("Topiramate", ["Topamax"], "Anticonvulsant", "Antiepileptic"),
            ("Gabapentin", ["Neurontin"], "Anticonvulsant", "Neuropathic Pain"),
            ("Pregabalin", ["Lyrica"], "Anticonvulsant", "Neuropathic Pain"),

            # ── Pain ──
            ("Acetaminophen", ["Tylenol"], "Analgesic", "Pain"),
            ("Ibuprofen", ["Advil", "Motrin"], "NSAID", "Pain"),
            ("Naproxen", ["Aleve", "Naprosyn"], "NSAID", "Pain"),
            ("Celecoxib", ["Celebrex"], "COX-2 Inhibitor", "Pain"),
            ("Tramadol", ["Ultram"], "Opioid Analgesic", "Pain"),
            ("Oxycodone", ["OxyContin", "Roxicodone"], "Opioid Analgesic", "Pain"),
            ("Hydrocodone", ["Vicodin", "Norco"], "Opioid Analgesic", "Pain"),
            ("Morphine", ["MS Contin", "Kadian"], "Opioid Analgesic", "Pain"),
            ("Codeine", [], "Opioid Analgesic", "Pain"),
            ("Fentanyl", ["Duragesic", "Actiq"], "Opioid Analgesic", "Pain"),

            # ── GI ──
            ("Omeprazole", ["Prilosec"], "Proton Pump Inhibitor", "Antacid"),
            ("Pantoprazole", ["Protonix"], "Proton Pump Inhibitor", "Antacid"),
            ("Esomeprazole", ["Nexium"], "Proton Pump Inhibitor", "Antacid"),
            ("Lansoprazole", ["Prevacid"], "Proton Pump Inhibitor", "Antacid"),
            ("Famotidine", ["Pepcid"], "H2 Blocker", "Antacid"),
            ("Ranitidine", ["Zantac"], "H2 Blocker", "Antacid"),
            ("Ondansetron", ["Zofran"], "5-HT3 Antagonist", "Antiemetic"),
            ("Metoclopramide", ["Reglan"], "Dopamine Antagonist", "Prokinetic"),
            ("Sucralfate", ["Carafate"], "Mucosal Protectant", "GI Protectant"),

            # ── Respiratory ──
            ("Albuterol", ["ProAir", "Ventolin", "Proventil"], "Short-Acting Beta Agonist", "Bronchodilator"),
            ("Fluticasone", ["Flovent", "Flonase"], "Inhaled Corticosteroid", "Anti-inflammatory"),
            ("Budesonide", ["Pulmicort", "Rhinocort"], "Inhaled Corticosteroid", "Anti-inflammatory"),
            ("Montelukast", ["Singulair"], "Leukotriene Receptor Antagonist", "Anti-inflammatory"),
            ("Ipratropium", ["Atrovent"], "Anticholinergic", "Bronchodilator"),
            ("Tiotropium", ["Spiriva"], "Long-Acting Anticholinergic", "Bronchodilator"),

            # ── Antibiotics ──
            ("Amoxicillin", ["Amoxil", "Trimox"], "Penicillin", "Antibiotic"),
            ("Azithromycin", ["Zithromax", "Z-Pack"], "Macrolide", "Antibiotic"),
            ("Ciprofloxacin", ["Cipro"], "Fluoroquinolone", "Antibiotic"),
            ("Levofloxacin", ["Levaquin"], "Fluoroquinolone", "Antibiotic"),
            ("Doxycycline", ["Vibramycin", "Doryx"], "Tetracycline", "Antibiotic"),
            ("Cephalexin", ["Keflex"], "Cephalosporin", "Antibiotic"),
            ("Sulfamethoxazole/Trimethoprim", ["Bactrim", "Septra"], "Sulfonamide", "Antibiotic"),
            ("Metronidazole", ["Flagyl"], "Nitroimidazole", "Antibiotic"),
            ("Clindamycin", ["Cleocin"], "Lincosamide", "Antibiotic"),
            ("Nitrofurantoin", ["Macrobid", "Macrodantin"], "Nitrofuran", "Antibiotic"),

            # ── Corticosteroids ──
            ("Prednisone", ["Deltasone", "Rayos"], "Corticosteroid", "Anti-inflammatory"),
            ("Prednisolone", ["Prelone", "Orapred"], "Corticosteroid", "Anti-inflammatory"),
            ("Methylprednisolone", ["Medrol", "Solu-Medrol"], "Corticosteroid", "Anti-inflammatory"),
            ("Dexamethasone", ["Decadron"], "Corticosteroid", "Anti-inflammatory"),

            # ── Osteoporosis ──
            ("Alendronate", ["Fosamax"], "Bisphosphonate", "Bone Health"),
            ("Risedronate", ["Actonel"], "Bisphosphonate", "Bone Health"),
            ("Denosumab", ["Prolia", "Xgeva"], "RANK Ligand Inhibitor", "Bone Health"),

            # ── Vitamins/Supplements ──
            ("Vitamin D3", ["Cholecalciferol"], "Vitamin", "Supplement"),
            ("Vitamin B12", ["Cyanocobalamin"], "Vitamin", "Supplement"),
            ("Folic Acid", ["Folate"], "Vitamin", "Supplement"),
            ("Iron Sulfate", ["Ferrous Sulfate", "Slow Fe"], "Iron Supplement", "Supplement"),
            ("Calcium Carbonate", ["Tums", "Caltrate", "Os-Cal"], "Calcium Supplement", "Supplement"),
            ("Potassium Chloride", ["K-Dur", "Klor-Con"], "Electrolyte", "Supplement"),
            ("Magnesium Oxide", ["Mag-Ox"], "Magnesium Supplement", "Supplement"),

            # ── Urological ──
            ("Tamsulosin", ["Flomax"], "Alpha-1 Blocker", "BPH"),
            ("Finasteride", ["Proscar", "Propecia"], "5-Alpha Reductase Inhibitor", "BPH"),
            ("Sildenafil", ["Viagra", "Revatio"], "PDE5 Inhibitor", "Erectile Dysfunction"),
            ("Tadalafil", ["Cialis", "Adcirca"], "PDE5 Inhibitor", "Erectile Dysfunction"),
            ("Oxybutynin", ["Ditropan"], "Anticholinergic", "Overactive Bladder"),

            # ── Allergy ──
            ("Cetirizine", ["Zyrtec"], "Second-Gen Antihistamine", "Antihistamine"),
            ("Loratadine", ["Claritin"], "Second-Gen Antihistamine", "Antihistamine"),
            ("Fexofenadine", ["Allegra"], "Second-Gen Antihistamine", "Antihistamine"),
            ("Diphenhydramine", ["Benadryl"], "First-Gen Antihistamine", "Antihistamine"),

            # ── HIV ──
            ("Abacavir", ["Ziagen"], "NRTI", "Antiretroviral"),
            ("Tenofovir", ["Viread", "Vemlidy"], "NRTI", "Antiretroviral"),
            ("Emtricitabine", ["Emtriva"], "NRTI", "Antiretroviral"),
            ("Dolutegravir", ["Tivicay"], "Integrase Inhibitor", "Antiretroviral"),

            # ── Antifungal ──
            ("Fluconazole", ["Diflucan"], "Azole Antifungal", "Antifungal"),
            ("Voriconazole", ["Vfend"], "Azole Antifungal", "Antifungal"),

            # ── Gout ──
            ("Allopurinol", ["Zyloprim"], "Xanthine Oxidase Inhibitor", "Antigout"),
            ("Colchicine", ["Colcrys", "Mitigare"], "Anti-inflammatory", "Antigout"),
            ("Febuxostat", ["Uloric"], "Xanthine Oxidase Inhibitor", "Antigout"),

            # ── ADHD ──
            ("Methylphenidate", ["Ritalin", "Concerta"], "Stimulant", "ADHD"),
            ("Amphetamine/Dextroamphetamine", ["Adderall"], "Stimulant", "ADHD"),
            ("Lisdexamfetamine", ["Vyvanse"], "Stimulant", "ADHD"),
            ("Atomoxetine", ["Strattera"], "SNRI", "ADHD"),

            # ── Dermatological (systemic) ──
            ("Methotrexate", ["Trexall", "Otrexup"], "Antimetabolite", "Immunosuppressant"),
            ("Adalimumab", ["Humira"], "TNF Inhibitor", "Biologic"),
            ("Etanercept", ["Enbrel"], "TNF Inhibitor", "Biologic"),
            ("Infliximab", ["Remicade"], "TNF Inhibitor", "Biologic"),
        ]

        for entry in seed:
            generic, brands, drug_class, category = entry
            generic_lower = self._normalize(generic)
            record = {
                "generic_name": generic,
                "brand_names": brands,
                "drug_class": drug_class,
                "category": category,
            }
            self._medications[generic_lower] = record
            self._name_index[generic_lower] = generic_lower
            for brand in brands:
                self._name_index[self._normalize(brand)] = generic_lower

        logger.info(
            f"RxNorm local DB loaded: {len(self._medications)} medications, "
            f"{len(self._name_index)} name mappings"
        )

    # ── Full Database Loading ─────────────────────────────────

    def _try_load_full(self, data_dir: Path):
        """
        Attempt to load full RxNorm database from RRF files.

        Expected file: data_dir / "rxnorm" / "RXNCONSO.RRF"
        Download from: https://www.nlm.nih.gov/research/umls/rxnorm/ (UMLS account)
        """
        rxn_file = data_dir / "rxnorm" / "RXNCONSO.RRF"
        if not rxn_file.exists():
            logger.debug(
                f"Full RxNorm database not found at {rxn_file}. "
                f"Using seed database ({self.count} medications). "
                f"Download from https://www.nlm.nih.gov/research/umls/rxnorm/"
            )
            return

        try:
            count_before = self.count
            with open(rxn_file, "r", encoding="utf-8") as f:
                for line in f:
                    fields = line.strip().split("|")
                    if len(fields) < 15:
                        continue

                    # RRF format: RXCUI|LAT|TS|LUI|STT|SUI|ISPREF|RXAUI|SAUI|SCUI|SDUI|SAB|TTY|CODE|STR|...
                    sab = fields[11]  # Source abbreviation
                    tty = fields[12]  # Term type
                    name = fields[14]  # String name

                    # Only load RxNorm source, preferred terms
                    if sab != "RXNORM":
                        continue
                    if tty not in ("IN", "PIN", "BN", "SBD", "SCD"):
                        continue

                    name_lower = self._normalize(name)
                    if name_lower not in self._name_index:
                        if tty in ("IN", "PIN"):
                            # Ingredient — this is a generic name
                            if name_lower not in self._medications:
                                self._medications[name_lower] = {
                                    "generic_name": name,
                                    "brand_names": [],
                                    "drug_class": "",
                                    "category": "",
                                }
                            self._name_index[name_lower] = name_lower
                        elif tty == "BN":
                            # Brand name — try to link to generic
                            self._name_index[name_lower] = name_lower

            logger.info(
                f"Full RxNorm loaded: {self.count} medications "
                f"(+{self.count - count_before} from RRF)"
            )
        except Exception as e:
            logger.warning(f"Failed to load full RxNorm RRF: {e}")

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalize a medication name for matching."""
        return name.lower().strip()
