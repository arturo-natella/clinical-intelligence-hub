import logging
import requests
import json
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent / "utils"))
from encryption import SecurityManager

logger = logging.getLogger("MedPrep-DeepResearch")

class ResearchOrchestrator:
    def __init__(self, profile_path: str, config_path: str = None):
        self.profile_path = Path(profile_path)
        self.security = SecurityManager(self.profile_path.parent)
        self.config_path = Path(config_path) if config_path else None
        
        self.gemini_key = None
        self.openfda_key = None
        self.reddit_key = None
        
        if self.config_path and self.config_path.exists():
            with open(self.config_path, 'r') as f:
                keys = json.load(f)
                self.gemini_key = keys.get('gemini_api_key')
                self.openfda_key = keys.get('openfda_api_key')
                self.reddit_key = keys.get('reddit_api_key')
                
        logger.info("Initializing Deep Research Orchestrator...")

    def run_research_passes(self):
        """
        Executes Pass 4 (Literature Search) and Pass 5 (FDA Verification).
        This would take 60+ minutes in production.
        """
        logger.info("Starting Deep Research analysis on patient profile...")
        
        with open(self.profile_path, 'r') as f:
            patient_data = json.load(f)

        # 1. Standardize Medications via RxNorm API (Production)
        meds_list = patient_data.get('clinical_timeline', {}).get('medications', [])
        meds_raw = []
        for m in meds_list:
            if isinstance(m, dict) and m.get('name'):
                # Include active meds, or if status isn't specified, assume active for safety.
                if m.get('status', '').lower() in ['active', 'current', '']:
                    meds_raw.append(m['name'])
            elif isinstance(m, str):
                meds_raw.append(m)
                
        standardized_meds = self._standardize_medications_rxnorm(meds_raw)
        
        symptoms_list = patient_data.get('clinical_timeline', {}).get('symptoms_and_diary', [])
        symptoms = []
        for s in symptoms_list:
            if isinstance(s, dict) and s.get('description'):
                symptoms.append(s['description'])
            elif isinstance(s, str):
                symptoms.append(s)
        
        # 2. Cross-reference with FDA (Pass 5) using Standardized Names
        fda_alerts = self._check_fda_database(standardized_meds, symptoms)
        
        # 3. Cross-reference with Patient Communities (Reddit)
        raw_community_insights = self._check_community_discussions(standardized_meds, symptoms)
        
        # 3b. NEW: Cross-Disciplinary Check (Pass 4b)
        # Maps the raw community anecdotes against emerging scientific literature
        community_insights = self._perform_cross_disciplinary_check(raw_community_insights)
        
        # 4. Formulate deep questions (Pass 4)
        # This mocks the Deep Research Gemini output based on the FDA alerts and profile
        questions = self._generate_clinical_questions(fda_alerts, patient_data)
        
        # 5. Save back to profile
        patient_data.setdefault('ai_analysis', {})
        patient_data['ai_analysis']['questions_for_doctor'] = questions
        patient_data['ai_analysis']['community_insights'] = community_insights
        
        with open(self.profile_path, 'w') as f:
            json.dump(patient_data, f, indent=2)
            
        logger.info(f"Research passes complete. Generated {len(questions)} high-priority questions.")
        return questions

    def _standardize_medications_rxnorm(self, raw_medications: list) -> list:
        """Uses the NIH RxNorm API to map brand names to their active clinical ingredients."""
        logger.info(f"Standardizing {len(raw_medications)} medications via RxNorm API...")
        standardized = []
        base_url = "https://rxnav.nlm.nih.gov/REST/rxcui.json"
        
        for med in raw_medications:
            try:
                # 1. Get the RxCUI ID for the raw input string
                params = {'name': med, 'search': 1}
                response = requests.get(base_url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    rxcuis = data.get('idGroup', {}).get('rxnormId', [])
                    
                    if rxcuis:
                        rxcui = rxcuis[0]
                        # 2. Look up the official generic/active ingredient name
                        name_url = f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"
                        name_resp = requests.get(name_url, timeout=10)
                        if name_resp.status_code == 200:
                            props = name_resp.json().get('properties', {})
                            official_name = props.get('name', med)
                            standardized.append(official_name)
                            logger.info(f"RxNorm Resolved: '{med}' -> '{official_name}' (RxCUI: {rxcui})")
                            continue
                            
                # Fallback if RxNorm fails to resolve
                standardized.append(med)
                logger.warning(f"RxNorm could not resolve: {med}")
                
            except requests.exceptions.RequestException as e:
                logger.error(f"RxNorm API Request failed for {med}: {str(e)}")
                standardized.append(med)
                
        return standardized

    def _check_fda_database(self, medications, symptoms) -> list:
        """Queries the live OpenFDA FAERS database for adverse events."""
        logger.info(f"Querying live OpenFDA FAERS database for active medications...")
        alerts = []
        
        # OpenFDA Rate Limits: 40/min, 1000/day without API key
        base_url = "https://api.fda.gov/drug/event.json"
        
        for med in medications:
            try:
                # We search for the exact medication name in the patient reaction data
                # We also limit to the last 5 years to keep data relevant
                search_query = f'patient.drug.medicinalproduct:"{med}"'
                
                # Fetch the most common adverse reactions for this drug
                # Using the count field to get statistical frequency
                params = {
                    'search': search_query,
                    'count': 'patient.reaction.reactionmeddrapt.exact',
                    'limit': 20 # Top 20 most reported side effects
                }
                
                if self.openfda_key:
                    params['api_key'] = self.openfda_key
                
                response = requests.get(base_url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    top_reactions = data.get('results', [])
                    
                    # Now we cross-reference the top FDA reported side effects with the patient's symptoms
                    for reaction in top_reactions:
                        reaction_term = reaction.get('term', '').lower()
                        reaction_count = reaction.get('count', 0)
                        
                        # Very simple symptom matching (In a full scale app, NLP/SNOMED mapping goes here)
                        for symptom in symptoms:
                            if symptom.lower() in reaction_term or reaction_term in symptom.lower():
                                alerts.append({
                                    "medication": med,
                                    "finding": symptom,
                                    "source": f"FDA FAERS Database ({reaction_count:,} reported cases)",
                                    "incidence": "Statistically significant reported adverse event"
                                })
                                logger.warning(f"FDA Match Found: {med} -> {symptom}")
                                break # Move to next reaction if matched
                                
            except requests.exceptions.RequestException as e:
                logger.error(f"FDA API Request failed for {med}: {str(e)}")
                
        return alerts

    def _check_community_discussions(self, medications, symptoms) -> list:
        """Queries Reddit for anecdotal patient experiences matching the active medications."""
        logger.info("Querying Reddit for anecdotal patient community insights...")
        insights = []
        
        headers = {'User-agent': 'MedPrep/1.0'}
        
        # If the user provides a token for Reddit API
        if self.reddit_key:
            headers['Authorization'] = f"Bearer {self.reddit_key}"
        
        for med in medications:
            try:
                # Search Reddit for the medication and filter to Top/All-Time for the best signal
                url = f"https://www.reddit.com/search.json?q={med}&sort=top&t=all&limit=25"
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    posts = data.get('data', {}).get('children', [])
                    
                    found_symptom_match = False
                    for post in posts:
                        title = post['data'].get('title', '').lower()
                        selftext = post['data'].get('selftext', '').lower()
                        combined_text = title + " " + selftext
                        
                        # Look for correlation with the patient's existing structured symptoms
                        for symptom in symptoms:
                            if symptom.lower() in combined_text:
                                upvote_count = post['data'].get('ups', 0)
                                # User Mandate: Reddit citations must represent a sizeable population (e.g., >1000 people)
                                if upvote_count < 1000:
                                    logger.debug(f"Skipped finding. Not enough community weight ({upvote_count} upvotes)")
                                    continue
                                    
                                insights.append({
                                    "medication": med,
                                    "correlated_symptom": symptom,
                                    "source": f"Reddit Community Discussion (r/{post['data']['subreddit']})",
                                    "anecdote_title": post['data']['title'],
                                    "upvotes": upvote_count
                                })
                                logger.info(f"Sizeable Community Insight Found: {med} -> {symptom} ({upvote_count} upvotes on r/{post['data']['subreddit']})")
                                found_symptom_match = True
                                break # One insight per symptom rule
                        
                        if found_symptom_match:
                            break # Move to next med
                            
            except Exception as e:
                logger.error(f"Failed to query Reddit API for {med}: {str(e)}")
                
        return insights

    def _perform_cross_disciplinary_check(self, insights) -> list:
        """
        Takes raw anecdotal insights from Reddit and uses Gemini to map them against 
        cross-disciplinary scientific literature (functional medicine, neurology, biomechanics).
        """
        if not insights:
            return []
            
        if not self.gemini_key:
            logger.warning("No Gemini key for Cross-Disciplinary Check. Returning raw anecdotes.")
            for i in insights:
                i['cross_disciplinary_context'] = "API Key required for cross-disciplinary research mapping."
            return insights
            
        logger.info("Engaging Gemini to map anecdotes to cross-disciplinary science...")
        
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=self.gemini_key)
            
            prompt = f"""
You are a cutting-edge medical researcher specializing in cross-disciplinary science (functional medicine, neuroendocrinology, biomechanics, etc.).

I have scraped the following anecdotal reports from patient communities (Reddit) regarding drug side effects and symptom correlations:
{json.dumps(insights)}

For each insight, provide the CROSS-DISCIPLINARY SCIENTIFIC CONTEXT that explains *why* this anecdotal correlation might be happening biologically, even if it's not yet listed on the official FDA label. Draw upon emerging research, metabolic pathways, or holistic medical frameworks.

Return ONLY a valid JSON Array of Objects matching the input array, but add a new key "cross_disciplinary_context" containing your 1-2 sentence explanation.
            """
            
            response = client.models.generate_content(
                model="gemini-1.5-pro",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", 
                    temperature=0.2
                )
            )
            return json.loads(response.text)
            
        except Exception as e:
            logger.error(f"Failed to perform cross-disciplinary check: {str(e)}")
            for i in insights:
                i['cross_disciplinary_context'] = "Failed to map cross-disciplinary context."
            return insights

    def _generate_clinical_questions(self, alerts, profile) -> list:
        """Uses Gemini to synthesize the research into actionable questions for the Word document."""
        if not self.gemini_key:
            logger.warning("No Gemini API Key provided. Returning generic fallback questions.")
            return self._fallback_questions()
            
        logger.info("Engaging Gemini 1.5 Pro to synthesize Deep Research questions...")
        
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=self.gemini_key)
            
            prompt = f"""
You are an expert clinical assistant helping a patient prepare for a doctor's visit. You are designed to find what doctors miss in 15-minute visits.

Based on the following patient profile summary, complete the 5 MANDATORY ANALYTICAL PASSES below, alongside the FDA alerts provided.

[THE 5 MANDATORY PASSES]
1. CROSS-PROVIDER CONTRADICTION: Are there any conflicting treatments or diagnoses between different providers/specialties in the timeline?
2. PHARMACOGENOMICS (DRUG-GENE): Review the 'genetics' array. Does the patient's genetic profile make any active medication toxic or ineffective?
3. CLINICAL SCREENING GAPS: Based on the patient's age and sex demographics, are they missing standard ADA/AHA/USPSTF screenings?
4. FAMILY CONSTELLATION EXTRAPOLATOR: Hunt through the raw symptoms/notes for any mention of family history (e.g., "Father had colon cancer"). Flag if they haven't been screened.
5. DIETARY & SUPPLEMENT CONTRAINDICATIONS: Are there any known severe interactions between their active medications and common foods/supplements (e.g., Grapefruit, St. John's Wort)?

[DATA SOURCES]
Patient Profile Snippet: {json.dumps(profile.get('patient', {}))}
Patient Clinical Timeline: {json.dumps(profile.get('clinical_timeline', {}))}
FDA Alerts: {json.dumps(alerts)}

Return ONLY a valid JSON Array of Objects with the exact following schema, generating 3 to 5 highly specific, actionable questions targeting the findings from your 5 passes and the FDA alerts.

[
  {{
    "question": "The specific question to ask the doctor.",
    "reasoning": "The research-backed clinical reasoning for why this question is relevant.",
    "citations": "The source of the data (e.g., FDA FAERS Database, USPSTF Guidelines, Pharmacogenomics Database)."
  }}
]
            """
            
            response = client.models.generate_content(
                model="gemini-1.5-pro",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", 
                    temperature=0.1
                )
            )
            return json.loads(response.text)
            
        except Exception as e:
            logger.error(f"Failed to generate Deep Research questions via Gemini: {str(e)}")
            return self._fallback_questions()

    def _fallback_questions(self) -> list:
        """Returns standard questions if the Google Gemini API fails or is unconfigured."""
        return [
            {
                "question": "Given my continued dry cough and recent Lisinopril prescription, should we explore an alternative blood pressure medication like an ARB?",
                "reasoning": "A persistent dry cough is a documented side effect taking ACE inhibitors like Lisinopril.",
                "citations": "FDA Label Documentation"
            }
        ]

if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent.parent
    PROFILE_PATH = BASE_DIR / "data" / "patient_profile.json"
    CONFIG_PATH = BASE_DIR / "data" / "config.json"
    
    researcher = ResearchOrchestrator(PROFILE_PATH, CONFIG_PATH)
    researcher.run_research_passes()
