"""
Clinical Intelligence Hub — Drug-Drug Interaction Timeline Analyzer

For each pair of medications with overlapping time periods:
  1. Calculate overlap window (start_date, end_date)
  2. Map overlap against known drug interactions (DDinter + RxNorm + static fallback)
  3. Correlate symptoms that occurred during the overlap period
  4. Integrate pharmacogenomic flags for the interacting medications

Returns interaction overlap zones, a summary, and pharmacogenomic flags
for rendering on the treatment bar timeline and in the clinical report.
"""

import itertools
import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("CIH-InteractionTimeline")

# ── Static Fallback Interaction Table ─────────────────────────
#
# Used when DDinter and RxNorm APIs are unavailable. Covers ~30
# of the most clinically important drug-drug interactions.

STATIC_INTERACTIONS: list[dict] = [
    # Statins + Fibrates
    {
        "pair": ("simvastatin", "gemfibrozil"),
        "severity": "critical",
        "description": "Greatly increased risk of rhabdomyolysis (muscle breakdown). Gemfibrozil inhibits statin metabolism via CYP2C8/OATP1B1.",
        "mechanism": "CYP2C8 / OATP1B1 inhibition",
        "management": "Avoid combination. Use fenofibrate if fibrate needed with statin.",
    },
    {
        "pair": ("atorvastatin", "gemfibrozil"),
        "severity": "high",
        "description": "Increased risk of rhabdomyolysis. Gemfibrozil raises statin plasma levels.",
        "mechanism": "CYP2C8 / OATP1B1 inhibition",
        "management": "Avoid combination or use lowest statin dose with close CK monitoring.",
    },
    # Warfarin + NSAIDs
    {
        "pair": ("warfarin", "ibuprofen"),
        "severity": "critical",
        "description": "Significantly increased risk of GI bleeding and hemorrhage. NSAIDs inhibit platelet function and may displace warfarin from protein binding.",
        "mechanism": "Platelet inhibition + protein binding displacement",
        "management": "Avoid combination. If needed, use acetaminophen for pain and monitor INR closely.",
    },
    {
        "pair": ("warfarin", "naproxen"),
        "severity": "critical",
        "description": "Significantly increased risk of GI bleeding. Naproxen inhibits platelet aggregation and has long half-life.",
        "mechanism": "Platelet inhibition + protein binding displacement",
        "management": "Avoid combination. Consider acetaminophen alternative.",
    },
    {
        "pair": ("warfarin", "aspirin"),
        "severity": "high",
        "description": "Increased bleeding risk from additive anticoagulant and antiplatelet effects.",
        "mechanism": "Additive anticoagulant + antiplatelet effects",
        "management": "Use only when specifically indicated (e.g., mechanical valve). Monitor INR closely.",
    },
    # Metformin + Contrast agents
    {
        "pair": ("metformin", "iodinated contrast"),
        "severity": "high",
        "description": "Risk of lactic acidosis if renal function declines after contrast exposure.",
        "mechanism": "Contrast-induced nephropathy reduces metformin clearance",
        "management": "Hold metformin before and for 48h after contrast. Check renal function before restarting.",
    },
    # ACE inhibitors + Potassium-sparing diuretics
    {
        "pair": ("lisinopril", "spironolactone"),
        "severity": "high",
        "description": "Risk of dangerous hyperkalemia. Both medications increase potassium retention.",
        "mechanism": "Additive potassium retention via RAAS blockade + ENaC blockade",
        "management": "Monitor potassium closely. Start spironolactone at low dose. Check K+ within 1 week.",
    },
    {
        "pair": ("enalapril", "spironolactone"),
        "severity": "high",
        "description": "Risk of dangerous hyperkalemia from additive potassium retention.",
        "mechanism": "Additive potassium retention",
        "management": "Monitor potassium closely. Reduce doses if K+ rises above 5.0 mEq/L.",
    },
    {
        "pair": ("lisinopril", "triamterene"),
        "severity": "high",
        "description": "Risk of hyperkalemia. Both agents increase serum potassium.",
        "mechanism": "Additive potassium retention",
        "management": "Monitor serum potassium regularly.",
    },
    # SSRIs + MAOIs
    {
        "pair": ("fluoxetine", "phenelzine"),
        "severity": "critical",
        "description": "Life-threatening serotonin syndrome: hyperthermia, rigidity, autonomic instability, coma, death.",
        "mechanism": "Massive serotonin excess from combined reuptake inhibition and MAO inhibition",
        "management": "NEVER combine. Wait 5 weeks after fluoxetine before starting MAOI (due to long half-life).",
    },
    {
        "pair": ("sertraline", "phenelzine"),
        "severity": "critical",
        "description": "Life-threatening serotonin syndrome.",
        "mechanism": "Serotonin excess from dual mechanism",
        "management": "NEVER combine. Wait 2 weeks between agents.",
    },
    {
        "pair": ("sertraline", "tranylcypromine"),
        "severity": "critical",
        "description": "Life-threatening serotonin syndrome.",
        "mechanism": "Serotonin excess",
        "management": "Absolute contraindication. Wait 2 weeks between agents.",
    },
    # SSRIs + Triptans
    {
        "pair": ("sertraline", "sumatriptan"),
        "severity": "moderate",
        "description": "Potential serotonin syndrome risk, though clinical significance debated. Monitor for symptoms.",
        "mechanism": "Additive serotonergic activity",
        "management": "Monitor for serotonin syndrome symptoms. Many patients use this combination safely.",
    },
    # Methotrexate + NSAIDs
    {
        "pair": ("methotrexate", "ibuprofen"),
        "severity": "high",
        "description": "NSAIDs reduce methotrexate renal clearance, increasing toxicity risk (pancytopenia, mucositis).",
        "mechanism": "Reduced renal clearance of methotrexate",
        "management": "Avoid NSAIDs with high-dose methotrexate. Monitor CBC and renal function.",
    },
    {
        "pair": ("methotrexate", "naproxen"),
        "severity": "high",
        "description": "Naproxen reduces methotrexate clearance, increasing toxicity risk.",
        "mechanism": "Reduced renal clearance of methotrexate",
        "management": "Avoid combination. Use acetaminophen for pain if possible.",
    },
    # Digoxin interactions
    {
        "pair": ("digoxin", "amiodarone"),
        "severity": "high",
        "description": "Amiodarone increases digoxin levels by 70-100%, risking toxicity (arrhythmias, visual disturbances, nausea).",
        "mechanism": "P-glycoprotein inhibition + renal clearance reduction",
        "management": "Reduce digoxin dose by 50% when starting amiodarone. Monitor digoxin levels.",
    },
    {
        "pair": ("digoxin", "verapamil"),
        "severity": "high",
        "description": "Verapamil increases digoxin levels by 50-75% and adds AV nodal blockade.",
        "mechanism": "P-glycoprotein inhibition + additive AV block",
        "management": "Reduce digoxin dose by 30-50%. Monitor HR and digoxin levels.",
    },
    # Potassium + ACE/ARB
    {
        "pair": ("potassium chloride", "lisinopril"),
        "severity": "moderate",
        "description": "Increased risk of hyperkalemia when potassium supplements given with ACE inhibitors.",
        "mechanism": "ACE inhibitor reduces aldosterone, retaining potassium",
        "management": "Monitor serum potassium. Avoid unless hypokalemia documented.",
    },
    {
        "pair": ("potassium chloride", "losartan"),
        "severity": "moderate",
        "description": "Increased hyperkalemia risk from potassium supplementation with ARB.",
        "mechanism": "ARB reduces aldosterone, retaining potassium",
        "management": "Monitor serum potassium regularly.",
    },
    # Lithium interactions
    {
        "pair": ("lithium", "ibuprofen"),
        "severity": "high",
        "description": "NSAIDs increase lithium levels by 15-30%, risking toxicity (tremor, confusion, renal damage).",
        "mechanism": "Reduced renal lithium clearance via prostaglandin inhibition",
        "management": "Avoid if possible. If used, check lithium level within 5 days.",
    },
    {
        "pair": ("lithium", "lisinopril"),
        "severity": "moderate",
        "description": "ACE inhibitors may increase lithium levels through reduced renal clearance.",
        "mechanism": "Reduced renal clearance of lithium",
        "management": "Monitor lithium levels when starting or adjusting ACE inhibitor dose.",
    },
    # QT prolongation combinations
    {
        "pair": ("amiodarone", "sotalol"),
        "severity": "critical",
        "description": "Additive QT prolongation risking torsades de pointes and sudden cardiac death.",
        "mechanism": "Additive potassium channel blockade (IKr)",
        "management": "Generally contraindicated. If used, continuous cardiac monitoring required.",
    },
    {
        "pair": ("methadone", "ondansetron"),
        "severity": "moderate",
        "description": "Additive QT prolongation risk, especially at higher doses.",
        "mechanism": "Additive hERG channel blockade",
        "management": "Use lowest effective doses. Monitor ECG if high doses or other risk factors.",
    },
    # Clopidogrel + PPI
    {
        "pair": ("clopidogrel", "omeprazole"),
        "severity": "moderate",
        "description": "Omeprazole inhibits CYP2C19, reducing conversion of clopidogrel to its active metabolite and decreasing antiplatelet effect.",
        "mechanism": "CYP2C19 inhibition reduces prodrug activation",
        "management": "Use pantoprazole instead (less CYP2C19 inhibition). FDA warns against omeprazole + clopidogrel.",
    },
    # Thyroid + Calcium/Iron
    {
        "pair": ("levothyroxine", "calcium carbonate"),
        "severity": "moderate",
        "description": "Calcium reduces levothyroxine absorption by forming insoluble complexes in the gut.",
        "mechanism": "Chelation reduces GI absorption",
        "management": "Separate doses by at least 4 hours. Take levothyroxine on empty stomach.",
    },
    {
        "pair": ("levothyroxine", "ferrous sulfate"),
        "severity": "moderate",
        "description": "Iron reduces levothyroxine absorption through chelation in the gut.",
        "mechanism": "Chelation reduces GI absorption",
        "management": "Separate doses by at least 4 hours.",
    },
    # Fluoroquinolone + NSAIDs
    {
        "pair": ("ciprofloxacin", "ibuprofen"),
        "severity": "moderate",
        "description": "Increased seizure risk. NSAIDs may inhibit GABA binding in the presence of fluoroquinolones.",
        "mechanism": "GABA receptor antagonism",
        "management": "Monitor for CNS symptoms. Avoid in patients with seizure history.",
    },
    # Diabetes — sulfonylurea + beta-blocker
    {
        "pair": ("glipizide", "metoprolol"),
        "severity": "moderate",
        "description": "Beta-blockers may mask hypoglycemia symptoms (tachycardia, tremor) and prolong hypoglycemic episodes.",
        "mechanism": "Beta-blockade masks adrenergic hypoglycemia warning signs",
        "management": "Educate patient to monitor blood glucose frequently. Recognize non-adrenergic hypoglycemia symptoms (sweating, hunger).",
    },
    # Metformin + ACE inhibitor (common combo, low severity)
    {
        "pair": ("metformin", "lisinopril"),
        "severity": "low",
        "description": "Generally safe and commonly co-prescribed. Minor risk of lactic acidosis if ACE inhibitor causes renal impairment.",
        "mechanism": "Potential renal function changes affecting metformin clearance",
        "management": "Monitor renal function periodically. Standard of care for diabetic patients with hypertension.",
    },
    # Statin + Amlodipine
    {
        "pair": ("simvastatin", "amlodipine"),
        "severity": "moderate",
        "description": "Amlodipine inhibits CYP3A4, increasing simvastatin levels and myopathy risk.",
        "mechanism": "CYP3A4 inhibition",
        "management": "Limit simvastatin to 20mg/day with amlodipine. Consider atorvastatin as alternative.",
    },
]


# ── Severity Normalization ────────────────────────────────────

_SEVERITY_NORMALIZE = {
    "contraindicated": "critical",
    "severe": "critical",
    "major": "critical",
    "critical": "critical",
    "high": "high",
    "significant": "high",
    "moderate": "moderate",
    "minor": "low",
    "low": "low",
    "n/a": "low",
    "unknown": "low",
}


def _normalize_severity(raw: str) -> str:
    """Map external severity labels to our 4-tier system."""
    return _SEVERITY_NORMALIZE.get(raw.lower().strip(), "moderate")


def _drug_name_key(name: str) -> str:
    """Normalize a drug name for comparison."""
    return name.lower().strip()


def _drug_matches(name_a: str, name_b: str) -> bool:
    """Check if two drug names refer to the same medication (substring match)."""
    a = _drug_name_key(name_a)
    b = _drug_name_key(name_b)
    return a == b or a in b or b in a


# ── Static Fallback Lookup ────────────────────────────────────

def _static_lookup(drug_a: str, drug_b: str) -> Optional[dict]:
    """
    Search the static interaction table for a matching pair.
    Returns interaction dict or None.
    """
    a_key = _drug_name_key(drug_a)
    b_key = _drug_name_key(drug_b)

    for entry in STATIC_INTERACTIONS:
        p0 = _drug_name_key(entry["pair"][0])
        p1 = _drug_name_key(entry["pair"][1])

        if (_drug_matches(a_key, p0) and _drug_matches(b_key, p1)) or \
           (_drug_matches(a_key, p1) and _drug_matches(b_key, p0)):
            return {
                "description": entry["description"],
                "severity": entry["severity"],
                "mechanism": entry["mechanism"],
                "management": entry.get("management", ""),
                "source": "Static Clinical Knowledge Base",
            }

    return None


class InteractionTimelineAnalyzer:
    """
    Analyzes medication overlap windows for drug-drug interactions,
    correlates symptoms during overlap periods, and integrates
    pharmacogenomic context.
    """

    def analyze(
        self,
        medications: list[dict],
        interactions: list[dict],
        symptoms: list[dict],
        genetics: list[dict],
    ) -> dict:
        """
        Analyze drug interaction timeline.

        Args:
            medications: List of medication dicts with name, start_date, end_date, status
            interactions: Pre-computed drug interactions (from analysis pipeline)
            symptoms: List of symptom dicts with episodes
            genetics: List of genetic variant dicts

        Returns:
            {
                overlap_zones: [{
                    med_a, med_b,
                    overlap_start, overlap_end,
                    duration_days,
                    interaction: {description, severity, mechanism, source},
                    symptoms_during: [{symptom_name, episode_date, severity}],
                    pgx_flags: [{gene, variant, impact, source}],
                }],
                interaction_summary: str,
                pharmacogenomic_flags: [{gene, drug, variant, impact}],
            }
        """
        today = date.today()

        # Parse medications into a normalized form
        parsed_meds = self._parse_medications(medications, today)

        if len(parsed_meds) < 2:
            logger.info("InteractionTimeline: fewer than 2 medications, no pairs to check")
            return {
                "overlap_zones": [],
                "interaction_summary": "Fewer than 2 medications on file. No interaction analysis needed.",
                "pharmacogenomic_flags": [],
            }

        # Parse symptom episodes into a flat date-indexed list
        symptom_episodes = self._flatten_symptoms(symptoms)

        # Parse genetic variants
        pgx_map = self._build_pgx_map(genetics)

        # Build pre-computed interaction lookup from pipeline data
        precomputed = self._index_precomputed_interactions(interactions)

        # Check every medication pair
        overlap_zones = []
        all_pgx_flags = []

        for med_a, med_b in itertools.combinations(parsed_meds, 2):
            # Calculate overlap
            overlap = self._calculate_overlap(med_a, med_b)
            if overlap is None:
                continue

            overlap_start, overlap_end = overlap
            duration_days = (overlap_end - overlap_start).days
            if duration_days < 1:
                continue

            # Look up interaction
            interaction = self._find_interaction(
                med_a["name"], med_b["name"], precomputed
            )
            if interaction is None:
                continue

            # Correlate symptoms during overlap
            symptoms_during = self._correlate_symptoms(
                overlap_start, overlap_end, symptom_episodes
            )

            # Check PGx flags for both medications
            pgx_flags = self._check_pgx(med_a["name"], med_b["name"], pgx_map)
            all_pgx_flags.extend(pgx_flags)

            overlap_zones.append({
                "med_a": med_a["display_name"],
                "med_b": med_b["display_name"],
                "med_a_start": str(med_a["start"]),
                "med_a_end": str(med_a["end"]),
                "med_b_start": str(med_b["start"]),
                "med_b_end": str(med_b["end"]),
                "overlap_start": str(overlap_start),
                "overlap_end": str(overlap_end),
                "duration_days": duration_days,
                "is_active": overlap_end >= today,
                "interaction": interaction,
                "symptoms_during": symptoms_during,
                "pgx_flags": pgx_flags,
            })

        # Sort by severity (critical first), then by duration descending
        severity_rank = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
        overlap_zones.sort(key=lambda z: (
            severity_rank.get(z["interaction"]["severity"], 4),
            -z["duration_days"],
        ))

        # Deduplicate pgx flags
        seen_pgx = set()
        unique_pgx = []
        for flag in all_pgx_flags:
            key = (flag["gene"], flag["drug"])
            if key not in seen_pgx:
                seen_pgx.add(key)
                unique_pgx.append(flag)

        # Build summary
        summary = self._build_summary(overlap_zones)

        logger.info(
            "InteractionTimeline: %d overlap zones found among %d medications "
            "(%d active overlaps)",
            len(overlap_zones),
            len(parsed_meds),
            sum(1 for z in overlap_zones if z["is_active"]),
        )

        return {
            "overlap_zones": overlap_zones,
            "interaction_summary": summary,
            "pharmacogenomic_flags": unique_pgx,
        }

    # ── Medication Parsing ────────────────────────────────────

    def _parse_medications(self, medications: list[dict], today: date) -> list[dict]:
        """Parse medications into a normalized form with date objects."""
        parsed = []
        for med in medications:
            name = (med.get("name") or "").strip()
            if not name:
                continue

            # Skip discontinued medications without dates (no overlap possible)
            status = (med.get("status") or "").lower()

            start = self._parse_date(med.get("start_date"))
            end = self._parse_date(med.get("end_date"))

            # If no start_date, we cannot position this on a timeline
            if start is None:
                continue

            # If no end_date, treat as still active (use today)
            if end is None:
                end = today

            parsed.append({
                "name": name,
                "display_name": name,
                "name_key": _drug_name_key(name),
                "start": start,
                "end": end,
                "status": status,
            })

        return parsed

    @staticmethod
    def _parse_date(value) -> Optional[date]:
        """Parse a date from various formats."""
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            # Try ISO format
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
                try:
                    from datetime import datetime
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
        return None

    # ── Overlap Calculation ───────────────────────────────────

    @staticmethod
    def _calculate_overlap(
        med_a: dict, med_b: dict
    ) -> Optional[tuple[date, date]]:
        """
        Calculate the temporal overlap between two medications.

        Returns (overlap_start, overlap_end) or None if no overlap.
        """
        overlap_start = max(med_a["start"], med_b["start"])
        overlap_end = min(med_a["end"], med_b["end"])

        if overlap_start < overlap_end:
            return (overlap_start, overlap_end)
        return None

    # ── Interaction Lookup ────────────────────────────────────

    def _find_interaction(
        self,
        drug_a: str,
        drug_b: str,
        precomputed: dict,
    ) -> Optional[dict]:
        """
        Find a known interaction between two drugs.

        Lookup order:
          1. Pre-computed interactions from the pipeline
          2. DDinter API (with fallback on failure)
          3. RxNorm API (with fallback on failure)
          4. Static fallback table
        """
        # 1. Check pre-computed interactions
        result = self._check_precomputed(drug_a, drug_b, precomputed)
        if result:
            return result

        # 2. Try DDinter API
        result = self._check_ddinter(drug_a, drug_b)
        if result:
            return result

        # 3. Try RxNorm API
        result = self._check_rxnorm(drug_a, drug_b)
        if result:
            return result

        # 4. Static fallback
        result = _static_lookup(drug_a, drug_b)
        if result:
            logger.info(
                "InteractionTimeline: using static fallback for %s + %s",
                drug_a, drug_b,
            )
            return result

        return None

    def _check_precomputed(
        self, drug_a: str, drug_b: str, precomputed: dict
    ) -> Optional[dict]:
        """Check pre-computed interactions from the pipeline."""
        a_key = _drug_name_key(drug_a)
        b_key = _drug_name_key(drug_b)
        pair_key = tuple(sorted([a_key, b_key]))

        if pair_key in precomputed:
            return precomputed[pair_key]

        # Try substring matching against precomputed keys
        for key, interaction in precomputed.items():
            if (_drug_matches(a_key, key[0]) and _drug_matches(b_key, key[1])) or \
               (_drug_matches(a_key, key[1]) and _drug_matches(b_key, key[0])):
                return interaction

        return None

    @staticmethod
    def _check_ddinter(drug_a: str, drug_b: str) -> Optional[dict]:
        """Check DDinter 2.0 for a pairwise interaction."""
        try:
            from src.validation.ddinter import DDinterClient

            client = DDinterClient()
            result = client.check_pair(drug_a, drug_b)

            if result:
                return {
                    "description": result.get("description", ""),
                    "severity": _normalize_severity(
                        result.get("severity", "unknown")
                    ),
                    "mechanism": result.get("mechanism", ""),
                    "management": result.get("management_strategy", ""),
                    "source": result.get("source", "DDinter 2.0"),
                }
        except Exception as e:
            logger.warning(
                "DDinter lookup failed for %s + %s: %s", drug_a, drug_b, e
            )
        return None

    @staticmethod
    def _check_rxnorm(drug_a: str, drug_b: str) -> Optional[dict]:
        """Check RxNorm/NLM Interaction API for a pairwise interaction."""
        try:
            from src.validation.rxnorm import RxNormClient

            client = RxNormClient()
            # Resolve both to RxCUIs
            res_a = client.resolve_medication(drug_a)
            res_b = client.resolve_medication(drug_b)

            if not res_a or not res_b:
                return None

            rxcui_a = res_a.get("rxcui")
            rxcui_b = res_b.get("rxcui")

            if not rxcui_a or not rxcui_b:
                return None

            interactions = client.check_pairwise_interactions(
                [rxcui_a, rxcui_b]
            )

            if interactions:
                # Find the interaction that matches our drug pair
                for ix in interactions:
                    drugs = [d.lower() for d in ix.get("drugs", [])]
                    a_lower = drug_a.lower()
                    b_lower = drug_b.lower()
                    if any(a_lower in d for d in drugs) or \
                       any(b_lower in d for d in drugs) or \
                       len(interactions) == 1:
                        return {
                            "description": ix.get("description", ""),
                            "severity": _normalize_severity(
                                ix.get("severity", "unknown")
                            ),
                            "mechanism": "",
                            "management": "",
                            "source": ix.get("source", "NLM RxNorm"),
                        }
        except Exception as e:
            logger.warning(
                "RxNorm lookup failed for %s + %s: %s", drug_a, drug_b, e
            )
        return None

    def _index_precomputed_interactions(
        self, interactions: list[dict]
    ) -> dict:
        """
        Build a lookup dict from pre-computed pipeline interactions.
        Key: tuple of sorted lowercase drug names.
        """
        index = {}
        for ix in interactions:
            drug_a = (ix.get("drug_a") or "").strip()
            drug_b = (ix.get("drug_b") or ix.get("interacting_drug") or "").strip()
            if not drug_a or not drug_b:
                continue

            pair_key = tuple(sorted([
                _drug_name_key(drug_a),
                _drug_name_key(drug_b),
            ]))

            index[pair_key] = {
                "description": ix.get("description", ""),
                "severity": _normalize_severity(
                    ix.get("severity", "unknown")
                ),
                "mechanism": ix.get("mechanism", ""),
                "management": ix.get("management_strategy", ix.get("management", "")),
                "source": ix.get("source", "Pipeline Analysis"),
            }

        return index

    # ── Symptom Correlation ───────────────────────────────────

    def _flatten_symptoms(self, symptoms: list[dict]) -> list[dict]:
        """
        Flatten nested symptom data into a list of episode dicts
        with date, name, and severity.
        """
        flat = []

        for symptom in symptoms:
            name = (
                symptom.get("symptom_name")
                or symptom.get("name")
                or ""
            ).strip()
            if not name:
                continue

            episodes = symptom.get("episodes", [])
            for ep in episodes:
                ep_date = self._parse_date(ep.get("episode_date"))
                if ep_date is None:
                    continue

                intensity = ep.get("intensity", "mid")
                if isinstance(intensity, dict):
                    intensity = intensity.get("value", "mid")

                flat.append({
                    "symptom_name": name,
                    "episode_date": ep_date,
                    "intensity": str(intensity),
                })

        return flat

    def _correlate_symptoms(
        self,
        overlap_start: date,
        overlap_end: date,
        symptom_episodes: list[dict],
    ) -> list[dict]:
        """Find symptom episodes that occurred during the overlap period."""
        correlated = []

        for ep in symptom_episodes:
            if overlap_start <= ep["episode_date"] <= overlap_end:
                correlated.append({
                    "symptom_name": ep["symptom_name"],
                    "episode_date": str(ep["episode_date"]),
                    "intensity": ep["intensity"],
                })

        # Sort by date
        correlated.sort(key=lambda x: x["episode_date"])
        return correlated

    # ── Pharmacogenomic Context ───────────────────────────────

    def _build_pgx_map(self, genetics: list[dict]) -> dict:
        """
        Build a map of gene -> variant info from patient genetics.
        """
        pgx_map = {}
        for variant in genetics:
            gene = (variant.get("gene") or "").strip().upper()
            if not gene:
                continue

            pgx_map[gene] = {
                "gene": gene,
                "variant": variant.get("variant", ""),
                "phenotype": variant.get("phenotype", ""),
                "clinical_significance": variant.get("clinical_significance", ""),
            }

        return pgx_map

    def _check_pgx(
        self, drug_a: str, drug_b: str, pgx_map: dict
    ) -> list[dict]:
        """
        Check if either medication in the pair has known gene-drug
        interactions with the patient's genetic profile.
        """
        flags = []

        try:
            from src.analysis.diagnostic_engine.pharmacogenomics import (
                PGX_INTERACTIONS,
            )
        except ImportError:
            logger.warning("InteractionTimeline: pharmacogenomics module not available")
            return flags

        for drug_name in [drug_a, drug_b]:
            drug_lower = drug_name.lower()

            for gene, profiles in PGX_INTERACTIONS.items():
                # Check if patient has this gene tested
                if gene not in pgx_map:
                    continue

                patient_gene = pgx_map[gene]

                for phenotype_key, profile in profiles.items():
                    affected_drugs = [d.lower() for d in profile["drugs_affected"]]

                    if any(_drug_matches(drug_lower, ad) for ad in affected_drugs):
                        # Check if patient phenotype matches this profile
                        phenotype_text = " ".join([
                            patient_gene.get("phenotype", ""),
                            patient_gene.get("variant", ""),
                            patient_gene.get("clinical_significance", ""),
                        ]).lower()

                        # Import phenotype aliases for matching
                        try:
                            from src.analysis.diagnostic_engine.pharmacogenomics import (
                                PHENOTYPE_ALIASES,
                            )
                            aliases = PHENOTYPE_ALIASES.get(phenotype_key, [])
                            matched = any(
                                alias in phenotype_text for alias in aliases
                            )
                        except ImportError:
                            matched = phenotype_key.replace("_", " ") in phenotype_text

                        if matched:
                            flags.append({
                                "gene": gene,
                                "drug": drug_name,
                                "variant": patient_gene.get("variant", ""),
                                "phenotype": patient_gene.get("phenotype", ""),
                                "impact": profile["impact"],
                                "severity": profile["severity"],
                                "action": profile["action"],
                                "source": "Pharmacogenomic Knowledge Base",
                            })

        return flags

    # ── Summary Generation ────────────────────────────────────

    def _build_summary(self, overlap_zones: list[dict]) -> str:
        """Build a human-readable summary of the interaction timeline."""
        if not overlap_zones:
            return "No overlapping medication periods with known interactions were found."

        total = len(overlap_zones)
        active = sum(1 for z in overlap_zones if z["is_active"])
        critical = sum(1 for z in overlap_zones
                       if z["interaction"]["severity"] == "critical")
        high = sum(1 for z in overlap_zones
                   if z["interaction"]["severity"] == "high")

        parts = [f"{total} drug interaction overlap"]
        if total > 1:
            parts[0] += "s"
        parts[0] += " found"

        severity_parts = []
        if critical:
            severity_parts.append(f"{critical} critical")
        if high:
            severity_parts.append(f"{high} high-severity")
        if severity_parts:
            parts.append(f"({', '.join(severity_parts)})")

        if active:
            parts.append(
                f"-- {active} currently active"
            )

        parts.append(
            ". Discuss with your doctor before making any medication changes."
        )

        return " ".join(parts)
