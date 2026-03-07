# Scope of Work: Lab Trends + Treatment Timeline with Side Effect Tracking

**Date:** 2026-03-07
**Requested by:** Dr. feedback session
**Status:** Proposed

---

## Overview

Add a unified view that correlates lab value trends with active treatments AND patient-reported side effects on the same timeline. The goal: a doctor should be able to look at one chart and see "this medication moved the lab value in the right direction, but the patient reported these side effects during that period." When something unexpected happens — a spike, a crash, a reversal — the system surfaces what was going on at that time.

**Core principle: "Discuss with your doctor"** — This tool does not diagnose, prescribe, or tell the patient what to do. It surfaces evidence from real data sources (medical records, symptom tracker, health devices, clinical databases) and structures the conversation. Every finding leads with "Discuss with your doctor because..." and includes a suggested conversation starter. The doctor interprets and decides.

**No fabricated data.** Every data point must trace back to a real source: an uploaded medical record (with page number), a patient-entered symptom log entry (with timestamp), a connected health device reading (with sync date), or a clinical database reference (OpenFDA, DailyMed, SIDER, PharmGKB). The system surfaces co-occurring events — it never guesses or infers.

This feature has six parts:
1. Treatment bars on lab trend charts (x-axis medication timeline)
2. Side effect overlay from the symptom log
3. Treatment response summary in the downloadable clinical report
4. Contextual event correlation for anomalous lab values ("What happened here?")
5. Unified symptom timeline (symptom mapping across all body systems)
6. Drug-drug interaction timeline (flagging known interactions when medications overlap)

---

## Part 1: Lab Trend + Treatment Timeline

### What it shows
For each tracked lab value (HbA1c, eGFR, LDL, etc.), display:
- **Top:** Lab value trend line with data points, reference range, and projection (already built in Trajectories)
- **Bottom:** Horizontal bars showing which medications were active during that time period

### Treatment bar details
- Each medication gets a colored bar spanning its start → end date (or present if active)
- Dose changes shown as vertical tick marks on the bar with the new dose labeled
- Discontinued medications end with a visible cutoff
- Only medications relevant to that lab are shown (e.g., HbA1c chart shows diabetes meds, not statins)

### Medication-to-lab mapping
The system needs to know which medications affect which labs. Approach:
- Maintain a mapping table (medication class → relevant lab tests)
- Example: "Metformin" → [HbA1c, Fasting Glucose, eGFR]
- Example: "Atorvastatin" → [LDL, HDL, Triglycerides, ALT, AST]
- Fallback: show all active medications if no mapping exists

### Event markers
- Dashed vertical lines on the chart at key medication events (started, stopped, dose changed)
- Helps visually connect "medication X was added here" with "lab value changed direction here"

### Data sources
- Lab values: already extracted in Pass 1a (clinical_timeline.labs)
- Medications: already extracted in Pass 1a (clinical_timeline.medications)
- Medication start/end dates and dosage changes come from the extracted records

---

## Part 2: Side Effect Overlay (Symptom Log Integration)

### The problem this solves
A patient responds great to a diabetes medication (HbA1c drops from 9.4 to 8.2) but they're experiencing significant side effects — GI issues, fatigue, muscle pain. The doctor needs to see BOTH the lab improvement AND the side effect burden to make a treatment decision.

### How it works

**Patient input (Symptom Log):**
- Patient logs symptoms in the existing Symptom Tracker
- When logging a symptom, patient can optionally tag it to a medication: "I think this is from Metformin"
- Severity rating (1-10) and frequency already captured in symptom episodes

**What appears on the chart:**
- Below the treatment bars, a "Side Effects" row appears for medications that have patient-reported symptoms
- Labeled dots along the medication bar showing the symptom name and when it was reported
- Color intensity = severity (light = mild, dark = severe)
- Each dot is visibly labeled (e.g., "Nausea", "Diarrhea", "Muscle pain") — no anonymous dots
- Hovering/clicking shows: "Discuss with your doctor because..." framing, severity, frequency, evidence factors, patient's notes
- All tooltip/report language leads with the doctor-discussion framing and includes a suggested conversation starter

**Example timeline reading:**
```
HbA1c:     9.4 ──── 9.1 ──── 8.5 ──── 7.8 ──── 8.2
              ↓ improving ↓

Metformin:  ████████ 1000mg ████ ↑ 2000mg █████████████
Side effects:          ·  ·  ··· ●●● ●● ··
                           (nausea, diarrhea — peaked after dose increase)

Insulin:                        ████████████████████████
Side effects:                    · · ·
                                (injection site irritation — mild)
```

**Doctor takeaway at a glance:** "HbA1c is improving nicely, but the patient is having significant GI side effects from the Metformin dose increase. Worth discussing whether to reduce back to 1000mg or switch to extended-release."

### Symptom Log changes needed
- Add optional "Linked Medication" field to symptom episodes
- Dropdown populated from the patient's active medication list
- This is patient-reported — they choose which medication they think is causing it
- No forced attribution; the field is optional

### Data flow
```
Symptom Log (patient input)
    → symptom episodes with optional medication tag
    → Treatment Timeline chart pulls tagged symptoms
    → Side effect dots rendered on the medication bar
    → Same data feeds into the downloadable report
```

---

## Part 3: Treatment Response Summary in Clinical Report

### New report section: "Treatment Response & Tolerability"

Added to the downloadable Word document (Pass 6 report builder). For each active medication, summarize:

**Treatment Effectiveness:**
- Which lab values improved after starting this medication
- Rate of improvement (e.g., "HbA1c decreased 0.3% per quarter")
- Whether the patient is approaching target ranges

**Tolerability:**
- Patient-reported side effects linked to this medication
- Severity trend (getting better, stable, getting worse)
- Frequency of reported episodes
- Time relationship (e.g., "GI symptoms appeared 2 weeks after dose increase to 2000mg")

**"Discuss with your doctor" framing:**
- Every medication section leads with "Discuss with your doctor because..."
- Includes a suggested conversation starter in the patient's own language
- The tool structures the conversation — the doctor makes the decisions

**Example report entry:**
```
METFORMIN 2000mg (started Dec 2024, dose increased Jun 2025)

  What your labs show:
    HbA1c improved from 9.4% to 8.2% (-1.2% over 12 months).
    Fasting glucose improved from 178 to 156 mg/dL.

  What you reported:
    You logged 8 side effect episodes you associated with this medication:
    - Nausea (severity up to 6/10) — Very high likelihood of association
      with Metformin. Known side effect in 25% of patients (OpenFDA).
    - Diarrhea (severity up to 7/10) — Very high likelihood of association.
      Reported in 53% of patients (DailyMed).

  💬 Discuss with your doctor because:
    Your records show GI symptoms consistent with Metformin, especially
    after the dose increase. They appear to be improving on their own.

    How to bring this up: "I've been having stomach issues since my
    Metformin dose went up to 2000mg. The nausea and diarrhea have
    gotten better over the last few months, but I wanted to mention it.
    Is there an extended-release version that might be easier on my
    stomach if they come back?"
```

### Report section placement
This goes in the report after the Lab Results section and before Cross-Disciplinary Findings. It bridges "what the labs show" with "what the patient experiences."

---

## Part 4: Contextual Event Correlation ("What Happened Here?")

### The problem this solves
A patient has well-controlled diabetes — HbA1c trending down nicely at 7.2%, 7.0%, 6.8%. Then suddenly it spikes to 9.1%. The doctor sees the spike on the chart but has to dig through months of records to figure out why. Was there an infection? Did they stop a medication? Were they hospitalized? Did a new stressor emerge?

This feature answers the question: **"What was happening in the patient's life around the time this lab value changed unexpectedly?"**

### Critical constraint: NO fabricated data
Every event surfaced must come from a verified data source with provenance:
- **Medical records** (extracted in Pass 1a from uploaded PDFs)
- **Symptom Tracker** (patient-reported entries with timestamps)
- **Connected health devices** (CGM, Fitbit, Apple Watch, blood pressure monitors)
- **Medication timeline** (extracted prescriptions and refill history)

The system does NOT guess or infer. It surfaces co-occurring events from the patient's own data. The doctor interprets causality.

### How anomaly detection works

**Step 1: Detect the anomaly**
- Compare each new lab value against the patient's personal trajectory (already computed in Trajectories engine)
- Flag when a value deviates significantly from the projected trend
- Configurable sensitivity: mild deviation (yellow) vs. major spike (red)
- Direction matters: HbA1c going UP is bad; eGFR going DOWN is bad

**Step 2: Define the investigation window**
- Look at the 30–90 day window before the lab draw date
- This is the period where events would have affected the lab value
- Window size varies by lab type (HbA1c reflects ~90 days; fasting glucose reflects ~24-48 hours)

**Step 3: Surface all events in that window**
Pull from every available data source:

**From medical records (Pass 1a extraction):**
- New diagnoses (infections, illnesses, hospitalizations)
- Procedures and surgeries
- ER/urgent care visits
- Clinical notes mentioning acute events
- Specialist referral notes

**From medication timeline (Pass 1a extraction):**
- Medications started, stopped, or dose-changed during the window
- Prescription gaps (refill dates showing potential non-adherence)
- New medications that could interact with existing ones

**From Symptom Tracker (patient-reported):**
- Logged symptoms during the window
- Changes in symptom severity or frequency
- New symptoms that appeared
- Patient notes ("I was sick for 2 weeks in January")

**From health device data (new integration):**
- CGM: daily glucose averages, time-in-range changes, spike frequency
- Activity trackers: step count drops (illness indicator), sleep disruption
- Blood pressure monitors: BP changes
- Heart rate monitors: resting HR changes (infection, stress indicator)

### What appears on the chart

When a lab value is flagged as anomalous, a pulsing indicator appears on that data point. Clicking it opens a **"What Happened Here?"** panel showing:

```
⚠ HbA1c spiked from 6.8% → 9.1% (Jan 2026 draw)
  Expected: ~6.6% based on trajectory
  Investigation window: Oct 2025 – Jan 2026

MEDICAL RECORDS (from uploaded records)
  📋 Nov 12, 2025 — Pneumonia diagnosis (ER visit)
     Source: Regional Medical Center discharge summary, p.3
  📋 Nov 12–19, 2025 — Hospitalization (7 days)
     Source: Same discharge summary
  📋 Nov 15, 2025 — Prednisone 40mg prescribed (10-day taper)
     Source: Hospital medication reconciliation, p.1

MEDICATION CHANGES
  💊 Nov 15 — Prednisone started (known to raise blood sugar)
  💊 Nov 22 — Prednisone tapered off
  💊 Dec 3 — Metformin refill gap (14 days between fills)
     Source: Pharmacy records

SYMPTOM TRACKER (patient-reported)
  📝 Nov 10 — "Terrible cough, fever 101°F" (severity 8/10)
  📝 Nov 25 — "Still weak, not eating well" (severity 5/10)
  📝 Dec 8 — "Back to normal, but forgot to take meds for a week"

HEALTH DEVICES (if connected)
  ⌚ Nov 5–20 — Daily steps dropped from 6,200 → 800 avg
     Source: Fitbit sync
  📊 Nov 14–28 — CGM time-in-range dropped from 72% → 31%
     Source: Dexcom G7 sync
  ❤️ Nov 11–18 — Resting HR elevated 68 → 92 bpm
     Source: Apple Watch

DOCTOR TAKEAWAY:
  HbA1c spike likely explained by: pneumonia hospitalization
  (Nov 2025) + prednisone course (steroid-induced hyperglycemia)
  + 2-week metformin gap during recovery. CGM data confirms
  glucose control deteriorated during this exact window.
  All three factors have resolved — next HbA1c may show recovery.
```

### Event source attribution
Every event shown has a source tag:
- Medical records: file name, page number, date extracted
- Symptom Tracker: entry timestamp, patient-entered
- Health devices: device name, sync date
- Medications: prescription source document

This follows the project's core principle: **clinical provenance on everything.**

### Health device integration (new capability)
This is a new integration point. The system would support:
- **Apple Health** (via exported XML or FHIR — already on Mac)
- **Fitbit** (exported data or API)
- **Dexcom/Libre CGM** (exported CSV or Clarity reports)
- **Blood pressure monitors** (manual entry or device export)
- **Garmin, Oura, Whoop** (exported data)

Approach: patient uploads device export files (CSV, XML, JSON) alongside their medical records. The pipeline extracts timestamped readings during Pass 0.

### Data flow
```
Anomaly detected in lab trajectory
    → Define investigation window (lab-specific: 30-90 days before draw)
    → Query medical records timeline for events in window
    → Query medication changes in window
    → Query symptom log entries in window
    → Query health device data in window
    → Group and display events chronologically
    → Include source attribution for every event
    → Same data feeds into the downloadable report
```

### In the downloadable report

When an anomalous lab value is identified, the report includes a **"Lab Anomaly Context"** callout:

```
LAB ANOMALY: HbA1c spike (6.8% → 9.1%, Jan 2026)

Contributing factors identified in your records:
  1. Pneumonia hospitalization (Nov 12-19, 2025)
     — Illness and physical stress elevate blood sugar
  2. Prednisone 40mg for 10 days (Nov 15-25, 2025)
     — Corticosteroids are known to cause hyperglycemia
  3. Metformin gap: 14 days between refills (Dec 2025)
     — Primary diabetes medication was interrupted

Supporting device data:
  — CGM showed glucose time-in-range dropped from 72% to 31%
    during Nov 14–28 (matches illness period exactly)
  — Activity level dropped 87% during hospitalization

Assessment: This spike appears to be a transient event caused by
acute illness, steroid treatment, and medication interruption.
All three factors have resolved. Next scheduled HbA1c should show
whether baseline control has been restored.
```

---

## Part 5: Unified Symptom Timeline (Symptom Mapping)

### The problem this solves

Parts 1–4 are **medication-centric** — symptoms are attached to specific medications. But that's not how patients or doctors think. A patient doesn't experience "Atorvastatin side effects" and "Metformin side effects" separately. They experience symptoms — fatigue, nausea, muscle pain, brain fog — and the question is: **what's causing each one?**

The current design only captures symptoms the patient explicitly tags to a medication. That misses three critical categories:
1. **Symptoms the patient doesn't know how to attribute** — "I've been tired for months, I don't know why"
2. **Symptoms caused by medication interactions** rather than a single drug
3. **Symptoms that track across body systems** — GI issues + fatigue + mood changes might be one connected pattern, not three separate things

A doctor looking at a patient with 6 medications and 12 symptoms over 18 months needs to see the **full symptom landscape** — not just the ones the patient guessed were medication-related.

### What it shows

A dedicated "Symptom Timeline" view (alongside the existing lab-specific charts) that displays ALL patient-reported symptoms on a single unified timeline, regardless of whether they've been tagged to a medication.

**Timeline structure:**
```
              Jan     Mar     May     Jul     Sep     Nov     Jan
              2025    2025    2025    2025    2025    2025    2026
              │       │       │       │       │       │       │
MEDICATIONS   ████ Metformin 2000mg ██████████████████████████████
              ░░░░░░░░░░░░░░░████ Atorvastatin 40mg █████████████
              ░░░░░░░░░░░░░░░░░░░░░░░░░░░░████ Gabapentin 300mg █

GI            ●───●●──●●●────●●──●─────·─────·─────·
              nausea  diarrhea        (resolving)

MUSCULOSKELETAL                    ●──●───●●──●●●───●●──●
                                   muscle aches (escalating)

NEUROLOGICAL                                   ●──●●──●──●●
                                               drowsy  dizzy

MOOD/ENERGY   ·──●──●●───●──●●──●●●──●●──●●──●──●──●
              fatigue (persistent, crosses multiple med periods)

SLEEP                                          ●──●●──●●●
                                               insomnia (new)
```

**Key features:**
- **Symptoms grouped by body system** (GI, musculoskeletal, neurological, mood/energy, cardiovascular, sleep, skin, etc.) — not by medication
- **All symptoms shown** — tagged to a medication or not
- **Medication bars at the top** provide context — the doctor can visually correlate symptom clusters with medication periods
- **Pattern detection:** When symptoms across different body systems share temporal patterns, the system highlights the cluster (e.g., "Fatigue + muscle aches + mood changes all started within 2 weeks of each other")
- **Unattributed symptoms are prominent, not hidden** — these are often the most clinically interesting because nobody has investigated them yet

### Symptom-to-body-system mapping

Each logged symptom maps to a body system for timeline grouping:
- **GI:** nausea, diarrhea, constipation, bloating, stomach pain, appetite changes
- **Musculoskeletal:** muscle pain, cramps, weakness, joint pain, stiffness
- **Neurological:** headache, dizziness, drowsiness, numbness, tingling, brain fog
- **Mood/Energy:** fatigue, anxiety, depression, irritability, mood swings, low motivation
- **Cardiovascular:** palpitations, chest tightness, shortness of breath, swelling
- **Sleep:** insomnia, excessive sleepiness, restless sleep, vivid dreams
- **Skin:** rash, itching, bruising, hair changes, sensitivity
- **Other:** anything that doesn't fit cleanly

The system assigns body systems automatically based on symptom keywords. Patient can override if the auto-assignment is wrong.

### What the doctor gets from this view

1. **"This patient has 5 unattributed symptoms — nobody has investigated these yet"**
   - Symptoms not tagged to any medication stand out. They're clinical opportunities.
2. **"These 3 symptoms from different body systems started at the same time"**
   - Cross-system pattern: fatigue (mood) + muscle aches (musculoskeletal) + insomnia (sleep) all appearing within the same 2-week window after starting Atorvastatin
3. **"This symptom predates all current medications — it's not a side effect"**
   - Chronic fatigue that was present before any medications started is a different clinical conversation than fatigue that appeared after a medication change
4. **"The GI symptoms resolved on their own but the muscle symptoms are escalating"**
   - Trajectory matters: resolving vs. stable vs. worsening tells different stories

### Severity visualization

- Dot size reflects severity (small = mild 1-3, medium = moderate 4-6, large = severe 7-10)
- Connecting lines between dots of the same symptom show trajectory
- Color indicates body system (consistent with the grouping)
- A rising connecting line between dots = escalating severity — this is a red flag

### How Symptom Mapping Connects to Each Existing Feature

The symptom timeline is the thing that's hardest for a doctor to reconstruct in a 15-minute visit. A patient walks in with a medication list and lab results — the doctor can look those up quickly. But the full symptom picture? That lives in the patient's memory, scattered across months of "I mentioned this to my neurologist" and "I forgot to tell my PCP about that." This feature closes that gap.

Here's what the tool does today with Parts 1–4, and what symptom mapping adds to each:

---

**Part 1: Lab Trends (Treatment Timeline)**

*What it does today:*
Lab value trend lines with medication bars underneath. The doctor sees "HbA1c was going down while on Metformin" or "LDL dropped after starting Atorvastatin." It answers the question: **is the medication working?**

*What symptom mapping adds:*
Lab charts only show ONE dimension — the number. A patient's HbA1c might look great (9.4 → 7.8), but if they're also logging fatigue, nausea, and mood changes across three body systems during that same period, the "success" story is incomplete. When the doctor opens the unified symptom timeline alongside the lab trend, they see the FULL cost of that lab improvement. Not just "the number went down" but "the number went down AND here's what the patient was experiencing while it went down."

*What the doctor couldn't see before:*
A lab chart says the treatment is working. The symptom timeline says at what cost. Both are needed for the treatment decision.

---

**Part 2: Side Effects (Symptom Log Overlay)**

*What it does today:*
Patients tag symptoms to specific medications: "I think my nausea is from Metformin." Those tagged symptoms appear as dots on the medication bars. The doctor sees "this patient reports GI issues during Metformin."

*What symptom mapping adds:*
The patient can only tag what they think they know. That creates three blind spots:
1. **Symptoms the patient doesn't know how to attribute** — "I've been exhausted for 6 months, I have no idea why." These don't show up on any medication bar because the patient didn't tag them.
2. **Symptoms from drug interactions** — if fatigue is caused by Atorvastatin AND Gabapentin together, the patient can't tag it to one medication because it's not one medication. These fall through the cracks.
3. **Symptoms that started BEFORE the current medications** — chronic fatigue predating all current prescriptions. The patient might wrongly tag it to a new drug, or not tag it at all. Either way, the doctor gets a distorted picture.

The unified symptom timeline shows EVERY symptom — tagged and untagged — on one view. The untagged ones are often the most clinically interesting because nobody has investigated them yet.

*What the doctor couldn't see before:*
Part 2 shows symptoms the patient already attributed. Part 5 shows the symptoms nobody attributed — the open questions, the patterns nobody has investigated, the things that fell between the cracks of specialist visits.

---

**Part 3: Treatment Response (Clinical Report Summary)**

*What it does today:*
For each medication, the report summarizes: did the target lab values improve? What side effects did the patient report? It gives the doctor a per-medication scorecard in the downloadable report.

*What symptom mapping adds:*
The per-medication scorecard becomes a full-body impact assessment. Instead of just "Metformin: HbA1c improved, patient reported nausea," the Treatment Response section can now include:

- **Unattributed symptoms that appeared during this medication's active period** — the system doesn't claim causation, but it surfaces the temporal overlap. "While on Atorvastatin, you also reported fatigue and insomnia that you did not attribute to any medication. These symptoms began 3 weeks after starting Atorvastatin."
- **Cross-system patterns** — "You reported muscle aches (musculoskeletal), fatigue (mood/energy), and insomnia (sleep) all starting within the same 2-week window. These span three body systems."
- **Symptom trajectory relative to treatment changes** — "Your GI symptoms resolved on their own 6 weeks after the Metformin dose increase, but your muscle symptoms have been escalating since starting Atorvastatin."

The report goes from "here's what the patient told us about this drug" to "here's everything the patient was experiencing during this treatment period, attributed or not."

*What the doctor couldn't see before:*
A medication scorecard only shows what the patient linked. The symptom landscape shows what was ACTUALLY happening — including things the patient didn't connect to any medication. That's where undiagnosed problems hide.

---

**Part 4: "What Happened Here?" (Event Correlation)**

*What it does today:*
When a lab value spikes or drops unexpectedly, the system surfaces everything that was happening in the patient's life during the investigation window — hospitalizations, medication changes, logged symptoms, device data. It answers: **why did this lab value change?**

*What symptom mapping adds:*
This dovetails with "What Happened Here?" perfectly. The current event correlation pulls from four data sources (medical records, medication timeline, symptom tracker, health devices). Symptom mapping adds a fifth dimension: **the pattern of symptoms across body systems in that same window.**

Example: HbA1c spikes from 6.8 to 9.1. The "What Happened Here?" panel already shows the pneumonia hospitalization, the Prednisone course, the Metformin gap. But with symptom mapping, it can ALSO show:
- "During this same Oct–Jan window, you reported escalating fatigue (mood/energy), reduced appetite (GI), and disrupted sleep (sleep) — a cross-system cluster consistent with prolonged illness recovery."
- "Three of these symptoms were unattributed. After the acute events resolved (Dec 2025), the fatigue and sleep disruption persisted into January. This pattern may warrant separate investigation."

The "What Happened Here?" panel goes from "here are the medical events" to "here are the medical events AND here's what the patient's body was doing across every system during that same window."

*What the doctor couldn't see before:*
Event correlation shows discrete events (hospitalization, medication change). Symptom mapping shows the body's continuous response — the symptoms that started, escalated, persisted, or resolved around those events. One is the chapter headings; the other is the narrative.

---

**Why all five parts together matter:**

Parts 1–4 are medication-centric. Each starts with a drug or a lab value and works outward. That's useful for answering: "Is this medication working?" and "What caused this lab change?"

Part 5 flips the perspective. It starts with the PATIENT and works inward: "Here's everything I've been feeling. Now help me figure out what's causing what."

A doctor with all five parts sees:
- The lab trends (Part 1) — is the treatment moving the numbers?
- The tagged side effects (Part 2) — what does the patient think is causing their symptoms?
- The treatment scorecard (Part 3) — effectiveness vs. tolerability for each drug
- The event context (Part 4) — what explains unexpected changes?
- The full symptom landscape (Part 5) — what is the patient ACTUALLY experiencing across their whole body, and what hasn't been investigated yet?

That's the difference between managing medications and managing a patient.

### In the downloadable report

New section: **"Symptom Landscape"** — a narrative summary of all symptoms organized by body system, with:
- Which symptoms are tagged to medications (and what the evidence says)
- Which symptoms are unattributed (and when they started)
- Cross-system patterns the doctor should investigate
- Timeline context: "This symptom has been present for 14 months across 3 medication changes — it may not be medication-related"

**Example report entry:**
```
SYMPTOM LANDSCAPE

  Musculoskeletal symptoms (5 reports over 18 months):
    You logged muscle aches and weakness starting Jun 2024, escalating
    in frequency and severity. You attributed these to Atorvastatin.

    💬 Discuss with your doctor because:
      This is a recognized pattern. Your records show 5 reports of
      escalating muscle symptoms while on Atorvastatin, and your genetic
      test shows a SLCO1B1 variant associated with statin muscle effects.
      However, you also started Gabapentin in Jul 2025, and muscle
      weakness is a known Gabapentin side effect too.

      How to bring this up: "My muscle aches have been getting worse
      over the past year and a half. I'm on both Atorvastatin and
      Gabapentin now — could either or both be contributing? Is there
      a way to figure out which one it is?"

  Unattributed symptoms (not tagged to any medication):
    - Fatigue: 12 reports spanning the full 18-month window.
      Present before Atorvastatin dose change and before Gabapentin
      was started. May be independent of current medications.
    - Insomnia: 4 reports starting Sep 2025 — appeared ~2 months
      after Gabapentin was started. Not yet investigated.

    💬 Discuss with your doctor because:
      You have two symptoms that haven't been linked to a specific
      medication. The fatigue has been ongoing and may warrant separate
      investigation. The insomnia is newer and coincides with starting
      Gabapentin — worth mentioning.

      How to bring this up: "I've been really tired for over a year
      now, and I'm not sure it's from any of my medications. Also,
      I've started having trouble sleeping since around September —
      could the Gabapentin be affecting my sleep?"
```

### Data sources
- Symptom episodes from the Symptom Tracker (all entries, not just medication-tagged)
- Medication timeline (for visual correlation context)
- Health device data (sleep quality from wearable, activity levels to distinguish exercise fatigue from medication fatigue)
- Clinical databases (SIDER, OpenFDA) for known side effect lookups across all active medications

### Data flow
```
ALL symptom episodes (Symptom Tracker)
    → Classify by body system (auto-assignment from symptom keywords)
    → Arrange on unified timeline
    → Detect temporal clusters (symptoms that start/change together)
    → Overlay medication periods for visual correlation
    → Identify unattributed symptoms (no medication tag)
    → Feed into "Symptom Landscape" section of downloadable report
    → Cross-reference with Part 2 (medication-tagged view stays separate)
```

---

## Part 6: Drug-Drug Interaction Timeline

### The problem this solves

A patient sees a cardiologist who prescribes Atorvastatin and an endocrinologist who prescribes Metformin. Neither specialist reviews the other's prescriptions carefully. Six months later, a rheumatologist adds Colchicine for gout — and nobody flags that Atorvastatin + Colchicine is a known interaction that increases the risk of rhabdomyolysis (serious muscle breakdown).

Multi-specialist patients are the most vulnerable to drug interactions because **no single doctor sees the full medication picture.** The patient's primary care doctor should catch it at reconciliation, but in practice, many interactions slip through — especially when specialists prescribe between PCP visits.

This feature answers: **"Which of my medications have known interactions, and when did those overlap periods start?"**

### What it shows

On the treatment timeline, whenever two (or more) medications with a known interaction overlap in time, the system draws a visual interaction zone:

```
              Jan     Mar     May     Jul     Sep     Nov
              2025    2025    2025    2025    2025    2025
              │       │       │       │       │       │

Atorvastatin  ████████████████████████████████████████████
              40mg

Colchicine                          ███████████████████████
                                    0.6mg (gout)

              ░░░░░░░░░░░░░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
                                    ⚠ INTERACTION ZONE
                                    Atorvastatin + Colchicine
                                    Risk: Increased myopathy/
                                    rhabdomyolysis risk
                                    Severity: MAJOR
                                    Source: DrugBank, DailyMed
```

**Interaction zone details (hover/click):**
```
⚠ Drug-Drug Interaction: Atorvastatin + Colchicine
  Severity: MAJOR
  Risk: Coadministration increases the risk of myopathy and
        rhabdomyolysis (serious muscle breakdown)
  Overlap period: Jul 2025 – present (5 months)

  What your records show:
    You have been on both medications simultaneously for 5 months.
    During this overlap, you reported 3 muscle-related symptoms
    (muscle aches, weakness, cramps).

  💬 Discuss with your doctor because:
    These two medications have a known major interaction. Your
    records show muscle symptoms during the overlap period, which
    is consistent with the interaction risk. Your doctor may want
    to monitor your CK (creatine kinase) levels or adjust one of
    these medications.

    How to bring this up: "I noticed I'm on both Atorvastatin and
    Colchicine. I've read these can interact and cause muscle
    problems — and I have been having muscle aches. Should we check
    my CK levels or consider alternatives?"
```

### Interaction severity levels

Using standard clinical interaction severity (aligned with DrugBank/DailyMed):

| Severity | Meaning | Visual | Example |
|----------|---------|--------|---------|
| **MAJOR** | Can cause serious harm, avoid combination or monitor closely | Red zone, pulsing indicator | Atorvastatin + Colchicine (rhabdomyolysis risk) |
| **MODERATE** | May worsen condition or require dose adjustment | Orange zone | Metformin + ACE inhibitor (hypoglycemia risk in renal impairment) |
| **MINOR** | Unlikely to be clinically significant, be aware | Yellow zone, subtle | Most benign interactions |

Only MAJOR and MODERATE interactions are shown on the chart by default. MINOR interactions are available in the detailed report but don't clutter the visual timeline.

### Interaction detection approach

**Step 1: Build the overlap matrix**
For every pair of concurrently active medications, check if they have a known interaction:
```
Active medications: [Atorvastatin, Metformin, Lisinopril, Gabapentin, Colchicine]
Pairs to check: Ator+Met, Ator+Lis, Ator+Gab, Ator+Col, Met+Lis, Met+Gab, Met+Col, Lis+Gab, Lis+Col, Gab+Col
```

**Step 2: Look up each pair in interaction databases**
- **DrugBank** — comprehensive drug interaction database with severity classifications
- **DailyMed** — FDA drug label interaction sections
- **RxNorm** — for normalizing medication names to standard identifiers before lookup
- **OpenFDA drug event reports** — real-world adverse event data for drug combinations

**Step 3: Calculate overlap periods**
For each flagged pair, compute the date range where both medications were concurrently active. This becomes the interaction zone on the timeline.

**Step 4: Correlate with symptoms**
During the interaction overlap period, were there patient-reported symptoms consistent with the interaction risk? If yes, this strengthens the signal and is noted in the interaction detail.

### Multi-drug interactions

Some interactions involve three or more drugs. The system handles this by:
- Checking all pairwise combinations first (most common)
- Flagging known triple interactions separately (less common but clinically significant)
- Example: Statin + Fibrate + CYP3A4 inhibitor = elevated rhabdomyolysis risk beyond any single pair

### Pharmacogenomic context

When the patient has genetic test results (e.g., SLCO1B1 for statin metabolism), the interaction zone incorporates this:
```
⚠ Drug-Drug Interaction: Atorvastatin + Colchicine
  + Genetic factor: SLCO1B1 variant (reduced statin clearance)
  Combined risk: The interaction risk is ELEVATED because your
  genetic variant already reduces how quickly your body clears
  Atorvastatin. Adding Colchicine further increases muscle risk.
```

This connects to the existing pharmacogenomic analysis in the pipeline (Pass 1a genetic test extraction).

### What the doctor gets from this view

1. **"This patient has 2 major interactions I wasn't aware of"**
   - Especially when medications were prescribed by different specialists
2. **"The muscle symptoms correlate with the interaction overlap period"**
   - Symptoms that appeared during the interaction zone are highlighted
3. **"This interaction has been active for 8 months — needs review"**
   - Duration matters: longer overlaps without monitoring are higher priority
4. **"The genetic variant makes this interaction more dangerous than usual"**
   - Pharmacogenomic context elevates the clinical significance

### In the downloadable report

New section: **"Medication Interaction Review"** — placed after the Treatment Response section:

**Example report entry:**
```
MEDICATION INTERACTION REVIEW

  ⚠ MAJOR INTERACTION: Atorvastatin 40mg + Colchicine 0.6mg
    Overlap period: Jul 2025 – present (5 months)
    Risk: Increased myopathy and rhabdomyolysis risk
    Sources: DrugBank (DB00091 + DB01394), DailyMed label

    Genetic context: Your SLCO1B1 variant (rs4149056 CT)
    further reduces statin clearance, compounding this risk.

    Your symptom data during overlap:
      - 3 muscle-related reports (aches, weakness, cramps)
      - Escalating severity: 4/10 → 6/10 → 7/10

    💬 Discuss with your doctor because:
      You are on two medications with a known major interaction,
      and your genetic profile increases the risk further. You've
      been reporting worsening muscle symptoms during the overlap
      period. Your doctor may want to check your CK levels, adjust
      the Atorvastatin dose, or consider an alternative gout
      treatment.

      How to bring this up: "I'm taking both Atorvastatin and
      Colchicine, and I've been having worsening muscle pain.
      I also have a gene variant that affects how I process
      statins. Can we review whether these two medications are
      safe together for me?"

  ℹ MODERATE INTERACTION: Metformin + Lisinopril
    Overlap period: Jan 2024 – present (2+ years)
    Risk: ACE inhibitors may enhance hypoglycemic effect of
          Metformin, particularly in renal impairment
    Sources: DrugBank, clinical literature

    Context: Your eGFR has been stable at 62-68 mL/min (mild
    reduction). This interaction is generally well-managed at
    your current kidney function but worth monitoring.

    No concerning symptoms reported during overlap.

    💬 For reference: This is a common, usually well-tolerated
    combination. Worth mentioning at your next appointment if
    you experience episodes of low blood sugar (shakiness,
    sweating, confusion).
```

### Data sources
- **DrugBank** — primary interaction database with severity classifications, mechanism descriptions
- **DailyMed** — FDA-approved drug labels with interaction sections
- **RxNorm** — medication name normalization (so "Lipitor" and "atorvastatin" map to the same entity)
- **OpenFDA Adverse Event Reporting System (FAERS)** — real-world adverse event data for drug combinations
- **PharmGKB** — pharmacogenomic interaction data (gene-drug-drug interactions)
- **Patient's medication timeline** — extracted from medical records in Pass 1a
- **Patient's genetic test results** — extracted in Pass 1a if available
- **Patient's symptom log** — for correlating symptoms with interaction overlap periods

### Data flow
```
Medication timeline (all active medications with date ranges)
    → Generate all pairwise combinations of concurrent medications
    → Look up each pair in DrugBank + DailyMed + FAERS
    → Filter to MAJOR and MODERATE severity
    → Calculate overlap periods for each flagged pair
    → Check for pharmacogenomic factors that modify interaction risk
    → Correlate patient symptoms during overlap windows
    → Render interaction zones on the treatment timeline
    → Feed into "Medication Interaction Review" section of report
    → Flag multi-drug interactions (3+ medications)
```

---

## How the Analysis Works (Data Architecture & Methodology)

This section explains how data moves through the system — from raw patient records to the findings that appear on screen and in the downloadable report. Every layer is designed so a physician can trace any finding back to its source and evaluate the reasoning.

### Methodology Overview

The system works in three stages: **collect**, **structure**, **analyze**. No stage invents data. Every output traces back to something the patient uploaded, entered, or that exists in a published clinical database.

**Stage 1 — Collect.** The patient uploads medical records (PDFs, FHIR), genetic test reports, and health device exports. They also log symptoms directly in the app. The system adds reference knowledge from 8 clinical databases (OpenFDA, DrugBank, DailyMed, SIDER, PharmGKB, RxNorm, PubMed, LOINC/SNOMED CT). That's the complete input set — nothing else enters.

**Stage 2 — Structure.** Raw PDFs go through OCR and a medical AI model (MedGemma, running locally — records never leave the machine) that extracts structured fields: lab values with dates, medications with start/stop/dose, diagnoses, procedures, genetic variants. Every extracted field is tagged with its source file and page number. Before anything touches a cloud API, all personally identifiable information is stripped by a dedicated redaction layer. The output is a structured clinical timeline stored in an encrypted local database.

**Stage 3 — Analyze.** Six analysis methods run against the structured timeline:

| Method | What It Does | Key Principle |
|--------|-------------|---------------|
| **Side effect scoring** | Evaluates whether a patient-reported symptom is associated with a medication, using 5 evidence factors adapted from the Naranjo scale (a validated clinical pharmacology tool from 1981) | Transparent scoring — every factor shown, doctor can agree or disagree |
| **Lab anomaly detection** | Flags when a lab value deviates from the patient's own historical trajectory | Compares patient to themselves, not to population averages |
| **Temporal correlation** | Connects medication changes to lab shifts and symptom appearances using time-window analysis | Shows co-occurrence, never claims causation |
| **Symptom cluster detection** | Identifies when symptoms across different body systems appear in the same time window | Surfaces patterns for investigation, not diagnoses |
| **Drug interaction detection** | Checks all concurrent medication pairs against DrugBank/DailyMed for known interactions, calculates overlap periods | Severity comes from published databases, not the system's judgment |
| **Treatment effectiveness** | Calculates lab value changes during medication periods | Reports facts ("HbA1c went from 9.4 to 8.2"), not conclusions ("Metformin caused the drop") |

**What connects all six methods:** Every finding leads with "Discuss with your doctor because..." and cites specific data sources. The system assembles and organizes evidence. It does not diagnose, does not claim causation, does not recommend treatment changes, and does not fabricate data. A physician reviewing any finding can see exactly what data it's based on, how the scoring worked, and can override the system's assessment with their own clinical judgment.

The layers below describe each stage in full detail.

---

### Layer 1: What Goes In (Raw Data Sources)

The system accepts five categories of input. Nothing is generated or inferred at this stage — it's all patient data or published reference material.

#### Patient Data (uploaded or entered by the patient)

**Medical records** — PDF scans, digitally-generated PDFs, or FHIR JSON files. These contain lab results, diagnoses, medications, procedures, clinical notes, imaging reports, discharge summaries, specialist referrals. The patient collects these from their providers and uploads them. Each file is hashed (SHA-256) on upload so duplicate files are detected and not processed twice.

**Genetic test reports** — PDF reports from services like 23andMe, GeneSight, Tempus, Color Genomics, Invitae, or clinical pharmacogenomic panels ordered by a physician. These contain pharmacogenomic variants (SLCO1B1, CYP2D6, CYP2C19, CYP3A4, CYP2C9, VKORC1, HLA-B, etc.) and disease risk alleles. The system extracts the specific variant, the genotype, the functional phenotype (poor metabolizer, intermediate metabolizer, normal metabolizer, rapid metabolizer), and the clinical significance for each gene-drug pair.

**Symptom Tracker entries** — The patient logs symptoms directly in the app. Each entry captures: symptom name (free text or selected from a list), severity (1-10 scale), frequency (how often it occurs), an optional medication tag ("I think this is from Metformin"), an optional body system classification, free-text notes, and a timestamp. These are patient-reported — the patient decides what to log and how to describe it. The system does not prompt or suggest symptoms.

**Health device exports** — Exported data files from consumer health devices. Supported formats include Apple Health XML (which aggregates data from Apple Watch, iPhone sensors, and connected apps), Fitbit CSV/JSON exports, Dexcom/Libre continuous glucose monitor (CGM) CSV files or Clarity reports, blood pressure monitor exports, and manual entries. These provide timestamped readings: steps, heart rate, resting heart rate, sleep stages and duration, blood glucose (continuous), blood pressure, SpO2, respiratory rate, and activity minutes.

#### Reference Knowledge (queried automatically by the system)

These are published clinical databases. They contain no patient data — they contain population-level medical knowledge that the system uses to contextualize the patient's data.

**OpenFDA (U.S. Food & Drug Administration)**
What it is: The FDA's public database of adverse event reports (FAERS — FDA Adverse Event Reporting System) and structured drug labels. FAERS contains millions of voluntary reports from patients, physicians, and pharmaceutical companies about suspected adverse drug reactions.
How the system uses it: When a patient reports a symptom tagged to a medication, the system queries OpenFDA to determine (a) whether this symptom has been reported as an adverse event for this medication and (b) how frequently. Example output: "OpenFDA has 45,000+ adverse event reports linking atorvastatin to muscle-related symptoms." This is population-level frequency data, not a diagnosis — it tells the doctor "other people have reported this too" and at what scale.
Limitation: FAERS is a voluntary reporting system. It captures reports, not confirmed adverse reactions. Reporting rates don't equal true incidence rates. The system states the report count, not a percentage, to avoid implying precision that doesn't exist in this data source.

**DailyMed (National Library of Medicine)**
What it is: The FDA-approved drug label (package insert) for every marketed medication in the U.S. This is the same document a pharmacist reads — it includes indications, dosing, contraindications, warnings, drug interactions, adverse reactions with rates from clinical trials, and pharmacokinetics.
How the system uses it: Primary source for (a) known side effects with clinical trial incidence rates (e.g., "myalgia reported in 3.7% of patients in controlled trials"), (b) drug interaction sections listing known interactions with severity and mechanism, (c) black box warnings, and (d) pharmacokinetic data (half-life, metabolism pathway, renal clearance) used in temporal correlation windows. DailyMed is the most authoritative side effect source because the rates come from controlled clinical trials, not voluntary reports.

**SIDER (Side Effect Resource)**
What it is: A research database maintained by the European Molecular Biology Laboratory (EMBL) that extracts and structures side effect information from drug labels and published literature. It maps medications to side effects with frequency classifications (very common >10%, common 1-10%, uncommon 0.1-1%, rare 0.01-0.1%, very rare <0.01%).
How the system uses it: Supplements DailyMed with structured frequency data. When the system says "nausea is a common side effect of Metformin (reported in 25% of patients)," that frequency often comes from SIDER's structured extraction of the drug label data. SIDER is useful because it normalizes frequency data across thousands of medications into a consistent, queryable format.

**DrugBank**
What it is: A comprehensive pharmaceutical database maintained by the University of Alberta. Contains detailed drug data including molecular targets, pharmacology, interactions, and clinical data. The interaction database pairs every known drug-drug interaction with a severity classification (MAJOR, MODERATE, MINOR), a mechanism description, and an evidence level.
How the system uses it: Primary source for drug-drug interaction detection. When the system identifies two concurrent medications, it queries DrugBank for interaction records. Example: DrugBank returns that atorvastatin + colchicine has a MAJOR interaction — "Colchicine may increase the risk of myopathy and rhabdomyolysis when combined with statins by inhibiting P-glycoprotein efflux transport." The severity classification (MAJOR/MODERATE/MINOR) comes directly from DrugBank — the system does not invent or adjust severity levels.
Important: DrugBank's severity classifications are the same ones used by pharmacy drug interaction checkers (Lexicomp, Clinical Pharmacology, Micromedex). When this tool says "MAJOR interaction," it's using the same classification system a pharmacist uses at the dispensing counter.

**PharmGKB (Pharmacogenomics Knowledgebase)**
What it is: A resource maintained by Stanford University that curates gene-drug relationships with evidence levels. Each relationship is assigned a Clinical Annotation Level of Evidence: Level 1A (annotation based on a CPIC or DPWG guideline), Level 1B (annotation based on published literature with strong evidence), Level 2A/2B (moderate evidence), Level 3 (low evidence), Level 4 (case report only).
How the system uses it: When the patient has genetic test results, the system cross-references each extracted variant against PharmGKB to determine clinical significance. Example: SLCO1B1 rs4149056 CT genotype → PharmGKB Level 1A evidence → "Reduced function allele associated with increased risk of simvastatin-induced myopathy. CPIC guideline recommends considering lower statin dose or alternative statin." The evidence level is crucial — a Level 1A finding with CPIC guideline support carries far more clinical weight than a Level 3 finding from a single case report. The system displays the evidence level alongside every pharmacogenomic finding so the doctor can judge accordingly.

**RxNorm (National Library of Medicine)**
What it is: A standardized nomenclature for clinical drugs. It maps brand names, generic names, dose forms, and strengths to a single normalized identifier (RxCUI). Example: "Lipitor," "atorvastatin," "atorvastatin calcium 40mg tablet," and "ATORVASTATIN 40 MG ORAL TABLET" all map to the same RxCUI.
How the system uses it: Before any database lookup (interactions, side effects, genetic relationships), the system normalizes every medication name through RxNorm. This is essential because medical records are inconsistent — one doctor writes "Lipitor 40mg," another writes "atorvastatin calcium," a pharmacy label says "ATORVASTATIN 40 MG TABLET." Without normalization, the system would treat these as different medications and miss interactions, side effects, and genetic relationships. RxNorm also provides medication class information (e.g., atorvastatin → HMG-CoA reductase inhibitor → statin) used in the medication-to-lab mapping.

**PubMed / MEDLINE (National Library of Medicine)**
What it is: The primary index of biomedical literature. Contains citations and abstracts for over 36 million articles from peer-reviewed journals.
How the system uses it: Referenced for cross-disciplinary findings in later analysis passes (Passes 3-4). When the system identifies a pattern that spans multiple medical specialties (e.g., a connection between a cardiac medication and a neurological symptom through a shared metabolic pathway), it cites relevant PubMed literature. These citations give the doctor a trail to follow if they want to investigate a finding further. PubMed is a reference source, not a decision-making input — the system doesn't change its analysis based on literature search results.

**LOINC / SNOMED CT**
What they are: LOINC (Logical Observation Identifiers Names and Codes) standardizes laboratory and clinical test names. SNOMED CT (Systematized Nomenclature of Medicine — Clinical Terms) standardizes clinical terminology for diagnoses, procedures, and findings.
How the system uses them: Lab test name normalization. Medical records are wildly inconsistent — one lab report says "A1c," another says "HbA1c," another says "Hemoglobin A1c," another says "Glycated Hemoglobin." These all need to map to the same concept (LOINC code 4548-4) so the system can build a single trend line. Same for diagnoses — "Type 2 DM," "T2DM," "diabetes mellitus type 2," and "non-insulin-dependent diabetes" must resolve to the same SNOMED concept. Without this normalization, the system would fragment data that belongs together and miss trends that depend on combining results from multiple labs and providers.

---

### Layer 2: How Records Become Structured Data (Extraction Pipeline)

Raw PDFs are not queryable. A scanned lab report is just an image with text on it. The extraction pipeline converts uploaded files into structured, timestamped clinical data that can be correlated across sources. Here's every step:

#### Pass 0 — File Classification & OCR

When a patient uploads a file:

1. **Hash and dedup.** A SHA-256 hash is computed for the file. If this hash already exists in the database, the file is a duplicate and is skipped. This prevents re-processing the same lab report uploaded twice.

2. **File type classification.** The system classifies the file into categories: lab report, clinical note, discharge summary, imaging report, pathology report, genetic test, prescription/medication list, insurance document, or unknown. Classification uses a combination of structural cues (PDF metadata, formatting patterns) and content analysis.

3. **Text extraction (OCR).** For scanned PDFs (images of paper documents), the system runs optical character recognition to convert the image to machine-readable text. Primary OCR engine: Apple Vision framework (built into macOS, high accuracy on medical documents). Fallback: Tesseract OCR (open source, handles edge cases Apple Vision misses). For digitally-generated PDFs (text is already embedded), the text is extracted directly — no OCR needed. For FHIR JSON files, the structured data is parsed directly into the system's data model without OCR.

4. **Output.** Raw text + file metadata (filename, page count, file type classification, SHA-256 hash). This raw text proceeds to the next pass.

#### Pass 1a — Medical Text Extraction (Local AI)

This is where raw text becomes structured clinical data. The extraction is performed by **MedGemma 27B**, a medical-domain AI model that runs locally on the patient's Mac.

**Why local matters:** MedGemma runs entirely on the patient's computer using Ollama (a local model server). The raw medical records — containing names, dates of birth, Social Security numbers, medical record numbers, diagnoses, and other protected health information — never leave the machine. There is no cloud API call at this stage. This is a hard architectural constraint, not a preference.

**What MedGemma extracts from each page:**

- **Lab results:** Test name, numeric value, units, reference range (low-high), date drawn, ordering physician, performing laboratory. Example: from the text "HbA1c 9.4% (ref: 4.0-5.6%) drawn 01/15/2024 ordered by Dr. Smith, LabCorp," the system extracts {test: "HbA1c", value: 9.4, unit: "%", ref_range: "4.0-5.6", date: "2024-01-15", ordering_provider: "Dr. Smith", lab: "LabCorp"}.

- **Medications:** Drug name, dose, route, frequency, start date, end date (or "ongoing"), prescribing physician, indication if stated. Dose changes are extracted as separate records linked to the same medication. Example: "Increased Metformin from 1000mg to 2000mg daily on 6/15/2025" becomes a dose_increase record linked to the existing Metformin entry.

- **Diagnoses:** Condition name, date diagnosed, ICD-10 code if present in the document, diagnosing provider, status (active, resolved, chronic). Example: "Assessment: Type 2 Diabetes Mellitus (E11.9), poorly controlled" extracts as {condition: "Type 2 Diabetes Mellitus", icd10: "E11.9", qualifier: "poorly controlled", status: "active"}.

- **Procedures:** Procedure name, date, facility, performing physician, findings if documented. Includes surgeries, imaging studies, endoscopies, biopsies, and other procedural notes.

- **Vital signs:** Blood pressure, heart rate, respiratory rate, temperature, weight, height, BMI, date recorded.

- **Clinical notes:** Key phrases from physician notes — assessment/plan sections, chief complaints, history of present illness summaries. These are extracted as searchable text linked to their source, not as structured data fields.

**Provenance tagging:** Every extracted field is tagged with where it came from:
```
{
  source_file: "LabCorp_2024-01.pdf",
  source_page: 2,
  date_extracted: "2026-03-07",
  extraction_method: "medgemma_27b_local",
  confidence: 0.94
}
```
The confidence score (0.0 to 1.0) reflects how certain the extraction model is about the value. A clearly printed "HbA1c: 9.4%" gets 0.97. A handwritten note with an ambiguous digit might get 0.72. Low-confidence extractions are flagged for the cloud fallback pass.

**Memory management:** MedGemma 27B requires significant RAM. The system loads it into memory, processes all text extraction tasks, then unloads it completely (explicit garbage collection + GPU memory cache clearing) before loading any other model. Only one large model is in memory at any time. Peak memory usage stays under 36GB on a 64GB machine.

#### Pass 1b/1c — Medical Imaging (Local)

For imaging files (DICOM, radiology PDFs with embedded images):

- **MedGemma 4B** (smaller imaging-focused model, also local) generates text descriptions of medical images — what's visible in a chest X-ray, CT scan, or MRI.
- **MONAI pre-trained models** (medical imaging AI from NVIDIA, running locally via PyTorch) run inference on applicable scans — detecting structures, measuring volumes, identifying anomalies.
- Output: structured image descriptions with provenance, linked to the patient's clinical timeline.

MedGemma 27B is fully unloaded before MedGemma 4B loads. Sequential model loading, never concurrent.

#### Pass 1.5 — PII Redaction (Before Any Cloud Call)

This is the privacy gate. Before ANY data touches a cloud API (Google Gemini, or any external service), all personally identifiable information is stripped.

**How it works:** Microsoft Presidio (an open-source PII detection and anonymization framework) scans all extracted text and structured data for:
- Patient names (first, last, middle)
- Dates of birth
- Social Security numbers
- Medical record numbers (MRN)
- Addresses (street, city, state, zip)
- Phone numbers
- Email addresses
- Insurance policy numbers
- Any other identifying information

Each PII element is replaced with a token: "[PATIENT]", "[DOB_REDACTED]", "[MRN_REDACTED]", "[ADDRESS_REDACTED]", etc. The original PII remains in the local encrypted database — only the redacted version can proceed to cloud APIs.

**This is a one-way gate.** There is no configuration option, no override, no "trust this API" exception. If data needs to go to a cloud service, it goes through Presidio first. Period.

#### Pass 2 — Cloud AI Fallback (Gemini, redacted data only)

If MedGemma couldn't extract something — low confidence score, unusual document format, handwriting it couldn't read, a foreign-language document — the system sends the **PII-redacted** text to Google Gemini 3.1 Pro for a second extraction attempt.

Gemini sees: "[PATIENT] was seen on [DATE_REDACTED]. HbA1c result: [value unclear from local extraction]. Assessment: Type 2 DM, consider adjusting Metformin."

Gemini returns its extraction, which is merged with the local extraction. Cloud-extracted data carries a lower baseline confidence score and is tagged with {extraction_method: "gemini_fallback"} in provenance so the doctor can see that a finding relied on cloud extraction rather than local-only processing.

#### What Comes Out of the Extraction Pipeline

A structured clinical timeline, stored in an encrypted SQLite database (AES-256-GCM encryption at rest, Argon2id key derivation from the patient's password):

```
clinical_timeline:
  labs:        [{test, value, unit, ref_range, date, source_file, source_page, confidence}, ...]
  medications: [{name, dose, route, start_date, end_date, changes[], source_file, source_page}, ...]
  diagnoses:   [{condition, icd10, date, status, source_file, source_page}, ...]
  procedures:  [{name, date, facility, source_file, source_page}, ...]
  genetic_variants: [{gene, variant, genotype, phenotype, clinical_significance, source_file, source_page}, ...]
  symptoms:    [{name, severity, frequency, date, tagged_medication, body_system, notes, source: "symptom_tracker"}, ...]
  device_data: [{type, value, date, source_device}, ...]
  vitals:      [{type, value, date, source_file, source_page}, ...]
  clinical_notes: [{text, date, provider, context, source_file, source_page}, ...]
```

**Every field has provenance.** There is no data in this structure that doesn't trace to a specific file + page number, a patient entry with a timestamp, a device sync, or a named clinical database. This is the foundational principle — if you can't cite the source, the data doesn't exist in the system.

---

### Layer 3: How the System Produces Findings (Analysis Methodology)

The structured clinical timeline feeds into six analysis methods. Each one is designed to be transparent — a doctor should be able to look at any finding and understand exactly why the system produced it, what data supports it, and where they might disagree.

#### 3A. Side Effect Likelihood Scoring (Modified Naranjo Criteria)

**What it does:** When a patient reports a symptom and tags it to a medication ("I think my muscle aches are from Atorvastatin"), the system evaluates the strength of that association using 5 evidence factors.

**Where the methodology comes from:** This is adapted from the **Naranjo Adverse Drug Reaction Probability Scale**, a validated clinical tool published in 1981 by Naranjo et al. in *Clinical Pharmacology & Therapeutics*. The Naranjo scale has been the standard ADR probability assessment in clinical pharmacology for over 40 years. It's used by pharmacists, pharmacovigilance teams, and drug safety boards worldwide.

The original Naranjo scale has 10 questions scored on a three-point scale. Our adaptation condenses these into 5 factors that can be computed automatically from the data available in the system, while preserving the core methodology: evaluate multiple independent evidence streams and combine them into an overall probability assessment.

**Factor 1: Known Side Effect (database lookup)**

Question: Is this symptom listed as a known side effect of this medication in published clinical databases?

How it's computed:
- Query OpenFDA FAERS for adverse event reports matching this medication + this symptom
- Query DailyMed drug label "Adverse Reactions" section for this symptom
- Query SIDER for structured frequency data

Scoring:
- **+2** — The symptom appears in the drug label's adverse reactions section (DailyMed) AND has significant adverse event report volume in OpenFDA (>1,000 reports). This means the side effect was documented in clinical trials and has continued to be reported post-market at scale.
- **+1** — The symptom appears in either the drug label OR has moderate OpenFDA report volume (100-1,000 reports), but not both. Or it appears in SIDER with frequency classified as "uncommon" (0.1-1%).
- **0** — Insufficient data. The symptom is not listed in available databases for this medication, but the databases may not cover this specific combination. No evidence for or against.
- **-1** — The databases specifically note that this symptom is NOT associated with this medication class, or the symptom is listed as a side effect of the medication but in the opposite direction (e.g., the patient reports constipation, but the medication is known to cause diarrhea, not constipation).

Example: Patient reports "muscle aches" tagged to Atorvastatin.
- DailyMed label: "Myalgia" listed in adverse reactions, reported in 3.7% of patients in controlled clinical trials.
- OpenFDA FAERS: 45,000+ adverse event reports associating statins with muscle-related symptoms.
- SIDER: Myalgia classified as "common" (1-10%) for atorvastatin.
- Score: **+2** (documented in clinical trials + extensive post-market reporting).

**Factor 2: Temporal Relationship (timeline analysis)**

Question: Did the symptom start after the medication was started, or worsen after a dose change?

How it's computed:
- Compare symptom first-appearance date (from Symptom Tracker) against medication start date (from extracted records)
- If a dose change occurred, compare symptom onset/worsening against the dose change date
- Compare against the known onset window for this side effect from SIDER/DailyMed (how quickly this side effect typically appears after starting the medication)

Scoring:
- **+2** — Symptom appeared within the known typical onset window after starting the medication or after a dose increase. Example: GI symptoms appearing within 1-2 weeks of starting Metformin (known rapid-onset GI side effect).
- **+1** — Symptom appeared after the medication was started but outside the typical onset window, or the onset window isn't well-defined for this particular side effect. Example: Muscle aches appearing 5 months after starting Atorvastatin — statin myopathy can have delayed onset (weeks to months), so this is plausible but not the strongest temporal signal.
- **0** — Insufficient data. Can't determine temporal relationship — missing dates, unclear medication start date, or symptom predates all current medications.
- **-1** — Symptom clearly predates the medication. Example: Patient had fatigue for 2 years before Atorvastatin was started. The medication can't have caused a symptom that existed before it was prescribed.

Example: Patient first logged "muscle aches" in June 2024. Atorvastatin started January 2024. Symptom appeared 5 months after medication start. Statin myalgia typically appears weeks to months after initiation — 5 months is at the outer edge but within the documented range.
Score: **+1** (symptom post-dates medication, but longer gap than typical onset).

**Factor 3: Dose-Response Relationship (severity tracking)**

Question: Does the symptom severity correlate with medication dose — worsening after dose increases, improving after dose decreases?

How it's computed:
- Map dose change events from the medication timeline against symptom severity changes from the Symptom Tracker
- Look for severity increases within 2-4 weeks of dose increases
- Look for severity decreases within 2-4 weeks of dose decreases
- Assess overall severity trajectory (escalating, stable, improving, fluctuating)

Scoring:
- **+2** — Clear dose-response correlation. Symptom severity increased after a dose increase and/or decreased after a dose decrease. This is one of the strongest indicators of a true drug-symptom relationship.
- **+1** — Suggestive pattern. Symptom severity is escalating over time while on the medication, but there was no dose change to directly correlate with. Or there was a dose change with a temporally consistent severity change, but other confounders were also present.
- **0** — No dose changes occurred, or insufficient severity data to assess trend.
- **-1** — Dose was increased but symptoms improved, or dose was decreased but symptoms worsened. This argues against a medication-symptom relationship.

Example: No dose change recorded for Atorvastatin. Patient's symptom severity is escalating independently: 4/10 → 5/10 → 5/10 → 6/10 → 7/10 over 18 months. The escalating pattern is consistent with progressive medication effect, but there's no dose change to directly correlate with.
Score: **+1** (escalating severity pattern, but no dose correlation available).

**Factor 4: Genetic Factors (pharmacogenomic cross-reference)**

Question: Does the patient have a known pharmacogenomic variant that affects this medication's metabolism, efficacy, or side effect risk?

How it's computed:
- Cross-reference extracted genetic variants (from genetic test reports) against PharmGKB gene-drug relationships
- Check the evidence level (Level 1A = CPIC/DPWG guideline, Level 1B = strong published evidence, Level 2A/2B = moderate, Level 3 = low, Level 4 = case report)
- Check whether the patient's specific genotype places them in a higher-risk functional phenotype

Scoring:
- **+2** — Patient has a variant with Level 1A or 1B evidence in PharmGKB that specifically increases risk for this side effect. Example: SLCO1B1 rs4149056 CT or TT genotype with a statin — PharmGKB Level 1A evidence, CPIC guideline specifically recommends dose adjustment or alternative statin for this variant because of increased myopathy risk. The FDA statin labels reference this variant.
- **+1** — Patient has a variant with Level 2 evidence, or has a variant that affects the medication's metabolism pathway (e.g., CYP2D6 poor metabolizer status for a drug metabolized by CYP2D6) but the specific side effect link is less direct.
- **0** — No genetic test results available, or the patient's genotype is normal/typical function for all relevant genes. No evidence for or against — genetic data simply isn't present.
- **-1** — Patient has a variant that would be expected to REDUCE risk of this side effect (e.g., rapid metabolizer clearing the drug faster than average, reducing exposure).

Example: Patient has SLCO1B1 rs4149056 CT genotype. PharmGKB Level 1A evidence: "The CT genotype (intermediate function) is associated with increased risk of statin-induced myopathy compared to the CC genotype (normal function). CPIC guideline: consider lower dose of simvastatin or alternative statin." The FDA atorvastatin label includes SLCO1B1 as a pharmacogenomic consideration.
Score: **+2** (Level 1A evidence with CPIC guideline support).

**Factor 5: Alternative Explanations (confounding assessment)**

Question: Are there other plausible causes for this symptom besides this medication?

How it's computed:
- Check all OTHER active medications for the same side effect in their databases
- Check recent diagnoses that could explain the symptom
- Check health device data for relevant context (e.g., unusual activity levels, sleep disruption, heart rate changes)
- Check whether the symptom is common in the general population for the patient's age and conditions

Scoring:
- **+2** — No plausible alternative explanation found. The patient's other medications don't list this symptom, no recent diagnoses explain it, and device data doesn't suggest a non-medication cause.
- **+1** — An alternative explanation exists but is less likely based on timeline or other evidence. Example: Patient is also on Gabapentin which lists muscle weakness as a side effect, but the muscle symptoms started 13 months before Gabapentin was prescribed — timeline doesn't support Gabapentin as the primary cause.
- **0** — Can't assess. Insufficient data about other possible causes.
- **-1** — A strong alternative explanation exists. Example: Patient started a new exercise program 2 weeks before muscle aches appeared (visible in Fitbit step count data), or patient has a recent diagnosis of fibromyalgia, or another medication with a stronger known association with this symptom was started at the same time.

Example: Patient is also on Gabapentin (started July 2025), which lists muscle weakness as a side effect. However, muscle symptoms were first reported in June 2024 — 13 months before Gabapentin was started. Gabapentin is a possible contributor to recent worsening, but can't be the primary cause given the timeline. No other strong alternative found.
Score: **+1** (alternative exists but timeline argues against it as primary cause).

**How the scores combine:**

```
Individual factor scores are summed:

Total score range: -5 to +10

  8-10  →  VERY HIGH likelihood of association
  5-7   →  HIGH likelihood
  3-4   →  MODERATE likelihood
  1-2   →  LOW likelihood
  ≤0    →  UNLIKELY association

Worked example (muscle aches + Atorvastatin):
  Factor 1 (Known SE):      +2  (DailyMed + 45K OpenFDA reports)
  Factor 2 (Temporal):      +1  (post-dates med, but 5-month gap)
  Factor 3 (Dose-response): +1  (escalating, no dose change to correlate)
  Factor 4 (Genetic):       +2  (SLCO1B1 CT, PharmGKB Level 1A)
  Factor 5 (Alternatives):  +1  (Gabapentin possible but timeline argues against)
  ─────────────────────────────
  TOTAL:                     7  →  HIGH likelihood of association
```

**What the doctor sees:** The tooltip/report shows the overall likelihood AND the individual factor breakdown. The factor breakdown is the point. A doctor might look at this and think "actually, 5 months is a very typical onset window for statin myopathy — I'd score Factor 2 as +2, not +1, which pushes this to VERY HIGH." Or they might think "this patient does heavy weightlifting and always has some muscle soreness — Factor 5 should be -1." The tool provides the framework and the data. The doctor applies clinical judgment to evaluate each factor. The system is designed to be challenged, not to be the final word.

**What this methodology does NOT do:**
- Does not diagnose an adverse drug reaction. "High likelihood of association" means the evidence pattern is consistent with a medication-symptom relationship — it is not a confirmed ADR.
- Does not account for all possible confounders. The system only knows what's in the patient's records, symptom log, and device data. It doesn't know the patient went to the gym yesterday, had a stressful week, or changed their diet.
- Does not replace pharmacovigilance. The Naranjo scale in clinical practice is assessed by a trained clinician who can ask follow-up questions, examine the patient, and order confirmatory tests (e.g., CK level for statin myopathy). This tool provides the data assembly — the clinical assessment is the doctor's job.

#### 3B. Lab Anomaly Detection (Statistical Deviation from Personal Trajectory)

**What it does:** Flags when a lab value deviates unexpectedly from the patient's own historical trend.

**Key design decision — patient vs. population:** The system compares each patient **to themselves**, not to population reference ranges. Why? A patient whose eGFR has been stable at 65 mL/min for 3 years and suddenly drops to 48 mL/min has a clinically significant change — even though both values are technically in the "Stage 3a CKD" range. Population reference ranges would miss this because both values fall in the same category. Personal trajectory catches it because it represents a 26% decline from the patient's established baseline.

Population reference ranges are still displayed on every chart (the shaded "normal" zone) for context — they're just not what triggers the anomaly flag.

**How it works:**

**Step 1: Build the personal trajectory.** Collect all historical values for a given lab test (e.g., HbA1c: 9.4%, 9.1%, 8.5%, 7.8%, 7.2%, 7.0%, 6.8% over 3 years). Fit a regression model to these data points, weighted toward recent values (the last 3-4 data points carry more weight than older ones because they better represent the patient's current trajectory). Calculate the expected next value and a confidence interval based on the spread and trajectory of existing data.

**Step 2: Compare new values.** When a new lab value arrives, compare it to the model's prediction:
- Within the confidence interval → **Normal.** Trend continues as expected. No flag.
- 1-2 standard deviations outside prediction → **Mild deviation.** Yellow flag. Noted but not prominently flagged. Could be normal variation.
- Greater than 2 standard deviations outside prediction → **Major anomaly.** Red flag. This triggers the "What Happened Here?" investigation panel.

**Step 3: Direction awareness.** Not all deviations are equal. Each lab type has a clinically-informed "bad direction":
- HbA1c: UP is bad (worsening glycemic control)
- eGFR: DOWN is bad (worsening kidney function)
- LDL: UP is bad (worsening lipid control)
- TSH: context-dependent (up = hypothyroid worsening, down = hyperthyroid worsening or overtreatment)
- ALT/AST: UP is bad (liver stress)

A deviation in the "good direction" (e.g., LDL dropping faster than expected) is noted but flagged differently than a deviation in the bad direction.

**Step 4: Investigation window.** When a major anomaly is flagged, the system defines an investigation window — the time period before the lab draw where events would have affected the result. This window is lab-type-specific because different labs reflect different time horizons:
- **HbA1c:** 90-day window (reflects ~3 months of average blood glucose)
- **Fasting glucose:** 24-48 hours (reflects immediate metabolic state)
- **eGFR/Creatinine:** 7-30 days (kidney function changes over days to weeks)
- **LDL cholesterol:** 30-60 days (lipid levels respond over weeks)
- **TSH:** 30-60 days (thyroid hormone levels shift gradually)
- **ALT/AST:** 7-30 days (liver enzymes can spike quickly from acute injury or change slowly from chronic damage)

These windows come from published pharmacology and clinical pathology literature — they reflect how quickly each lab value responds to changes in the body.

**What this triggers:** The investigation window feeds into Part 4 (Contextual Event Correlation), which queries ALL data sources for events during that window — medical records, medication changes, symptom log entries, health device data. These events are presented chronologically for the doctor to evaluate. The system surfaces co-occurring events. The doctor determines whether they explain the anomaly.

**What this does NOT do:**
- Does not diagnose the cause of the anomaly
- Does not compare to population averages for flagging (population ranges shown as context only)
- Does not predict future values as medical guidance
- Does not account for expected changes after known events (e.g., HbA1c is expected to rise during a steroid course — the system would still flag this as an anomaly, and the "What Happened Here?" panel would show the steroid prescription, allowing the doctor to immediately see the explanation)

#### 3C. Temporal Correlation (Connecting Events to Outcomes)

**What it does:** When the system places a medication change next to a lab value shift, or connects symptoms to a medication period, it's using temporal co-occurrence analysis — not causal inference.

**The critical distinction:**
The system says: "Your HbA1c went from 9.4% to 8.2% during the period you were on Metformin."
The system does NOT say: "Metformin lowered your HbA1c by 1.2%."

Why? Because the patient might have also changed their diet, started exercising, lost weight, or had another medication adjusted during the same period. The system knows what's in the records — it doesn't know everything that happened in the patient's life. Claiming causation from observational data without controlling for confounders would be methodologically dishonest.

**How temporal correlation works:**

**Medication → Lab correlation:** A medication is considered "potentially related" to a lab change if the lab inflection point falls within the medication's known physiological response window. These windows come from published pharmacokinetic/pharmacodynamic data:
- Metformin → HbA1c: 8-12 weeks for measurable change (full effect at 3-6 months)
- Atorvastatin → LDL: 4-6 weeks for measurable change (steady state at ~4 weeks)
- Lisinopril → eGFR: 1-2 weeks for initial hemodynamic effect on creatinine/eGFR
- Levothyroxine → TSH: 6-8 weeks for measurable TSH change
- Insulin → Fasting glucose: hours to days

When a lab value changes direction and there's a medication event (start, stop, dose change) within the corresponding response window, the system notes the temporal correlation. It shows the medication event as a dashed vertical line on the chart at the same time position as the lab inflection point — visually suggesting the relationship without stating it as causal.

**Medication → Symptom correlation:** A symptom is temporally correlated with a medication if it first appeared AFTER the medication was started (or after a dose change). Stronger signal if the symptom appeared within the medication's known onset window for that specific side effect. These onset windows come from SIDER and DailyMed:
- Statin myalgia: typically weeks to months after initiation
- Metformin GI side effects: typically days to weeks after starting or dose increase
- ACE inhibitor cough: typically weeks to months after starting
- Gabapentin drowsiness: typically days to weeks after starting

**Event → Lab correlation (for the "What Happened Here?" panel):** Events in the investigation window are presented as co-occurring, not as causes. The language is always: "During this period, your records show..." never "This was caused by..."

**Language guardrails — the system is hardcoded to avoid causal language:**

| ✅ System says | ❌ System never says |
|---|---|
| "associated with" | "caused by" |
| "coincides with" | "resulted from" |
| "your records show X during this period" | "this was caused by" |
| "consistent with" | "proves that" |
| "multiple evidence sources support this association" | "this medication is responsible for" |
| "appeared after starting" | "was triggered by" |

**What this does NOT do:**
- Does not claim causation between any medication and any outcome
- Does not dismiss confounders — if 3 medications could cause fatigue, all 3 are mentioned
- Does not assume post-hoc-ergo-propter-hoc (after this, therefore because of this)

#### 3D. Symptom Cluster Detection (Cross-System Pattern Recognition)

**What it does:** Detects when symptoms from different body systems appear or change in the same time window. This surfaces patterns that individual symptom reports would miss — because a patient reports "muscle aches" to their rheumatologist, "fatigue" to their PCP, and "insomnia" to their psychiatrist, and nobody connects the three.

**How it works:**

**Step 1: Classify symptoms by body system.** Each symptom from the Symptom Tracker is mapped to a body system:
- **GI:** nausea, diarrhea, constipation, bloating, stomach pain, appetite changes, acid reflux
- **Musculoskeletal:** muscle pain, cramps, weakness, joint pain, stiffness, back pain
- **Neurological:** headache, dizziness, drowsiness, numbness, tingling, brain fog, tremor
- **Mood/Energy:** fatigue, anxiety, depression, irritability, mood swings, low motivation
- **Cardiovascular:** palpitations, chest tightness, shortness of breath, swelling, lightheadedness
- **Sleep:** insomnia, excessive sleepiness, restless sleep, vivid dreams, sleep apnea symptoms
- **Skin:** rash, itching, bruising, hair changes, sun sensitivity, dry skin
- **Other:** anything that doesn't fit cleanly

Classification is keyword-based — the patient types "muscle aches" and it maps to musculoskeletal. Patient can override if the auto-classification is wrong.

**Step 2: Identify key dates for each symptom.**
- First appearance date (when it was first logged)
- Dates of severity escalation (severity score increased by ≥2 points)
- Dates of resolution (no reports for 60+ days after the last report)

**Step 3: Compare key dates across all symptoms using a proximity window.** Default window: 14 days. If 2 or more symptoms from DIFFERENT body systems have key dates within 14 days of each other, flag as a temporal cluster.

```
Example:
  Jul 2, 2025:  Muscle aches first logged          (musculoskeletal)
  Jul 8, 2025:  Fatigue severity escalated 4→7     (mood/energy)
  Jul 12, 2025: Drowsiness first logged            (neurological)

  All 3 events within 10 days, across 3 different body systems.
  Context: Gabapentin was started Jun 28, 2025 (4 days before the cluster).

  Finding: "3 symptoms across different body systems appeared or
  worsened within 2 weeks of starting Gabapentin"
```

**Step 4: Add medication context.** When a cluster is detected, the system checks: were there any medication events (starts, stops, dose changes) within the proximity window? If yes, this is noted as context — not as a causal claim.

**What this surfaces for the doctor:**
1. **Multi-system patterns nobody connected:** "This patient has 3 new symptoms from 3 different body systems that all started within 2 weeks" — this is a signal worth investigating.
2. **Symptoms that predate all medications:** Chronic fatigue present for 2 years before any current medications → "This is probably not a medication side effect."
3. **Unattributed symptoms:** Symptoms the patient never tagged to any medication stand out in this view — these are clinical opportunities. Nobody has investigated them yet.
4. **Trajectory differences:** "The GI symptoms are resolving on their own, but the muscle symptoms are escalating." Different trajectories in the same patient tell different clinical stories.

**What this does NOT do:**
- Does not diagnose "Gabapentin is causing all three symptoms"
- Does not claim the cluster represents a syndrome or connected pathology
- Does not know about non-medical life events (the doctor may know the patient also started a new stressful job that week)

#### 3E. Drug-Drug Interaction Detection

**What it does:** Checks all concurrent medications for known interactions using published clinical databases. When two medications with a known interaction overlap in time, the system flags the interaction, calculates the overlap duration, and checks whether the patient has reported symptoms consistent with the interaction risk.

**Why this is different from other methods:** This is the most **database-driven** analysis. It relies almost entirely on published interaction data — there is very little statistical inference involved. When the system says "MAJOR interaction between Atorvastatin and Colchicine," that classification comes from DrugBank's curated database, which uses the same severity system as pharmacy drug interaction checkers (Lexicomp, Clinical Pharmacology, Micromedex). The system is essentially doing what a pharmacist's interaction checker does — but across the full medication history, not just at the point of dispensing.

**Step-by-step process:**

**Step 1: Normalize all medication names.** Medical records are wildly inconsistent. The same drug appears as "Lipitor 40mg" (brand name + dose), "atorvastatin calcium" (generic + salt form), "ATORVASTATIN 40 MG ORAL TABLET" (pharmacy format), or "atorvastatin" (shorthand in clinical notes). The system passes every medication name through RxNorm to get a single normalized identifier (RxCUI). "Lipitor," "atorvastatin," and "atorvastatin calcium 40mg tablet" all resolve to the same RxCUI (83367). This ensures that the interaction lookup doesn't miss matches due to name variation.

**Step 2: Build the concurrent medication matrix.** For every time period in the patient's history, identify which medications were simultaneously active. With 5 medications, there are 10 possible pairs. With 8 medications, there are 28 pairs. The system checks every pair.

**Step 3: Look up each pair in interaction databases.**
- **DrugBank:** Returns an interaction record (if one exists) with severity (MAJOR/MODERATE/MINOR), mechanism description, and evidence level (clinical study, case report, theoretical).
- **DailyMed:** Checks the "Drug Interactions" section of each medication's FDA-approved label.
- **OpenFDA FAERS:** Checks for real-world adverse event reports where both medications are listed as suspect drugs in the same event report. A high co-report volume suggests the interaction manifests in real patients, not just in theory.

**Step 4: Calculate overlap periods.** For each flagged interaction pair, compute the exact date range where both medications were concurrently active. Example: Atorvastatin started Jan 2024 (ongoing), Colchicine started Jul 2025 (ongoing) → overlap is Jul 2025 to present (8 months). Duration matters clinically — an interaction that's been active for 8 months without monitoring is higher priority than one that started 2 weeks ago.

**Step 5: Correlate with patient symptoms (optional enrichment).** During the overlap period, did the patient report symptoms consistent with the known interaction risk? This is optional enrichment — it strengthens the clinical signal but is NOT presented as proof. Example: DrugBank says Atorvastatin + Colchicine increases myopathy risk. During the 8-month overlap, the patient reported 3 muscle-related symptoms (aches, weakness, cramps) with escalating severity. The system notes: "Your symptom reports during this overlap period are consistent with the known interaction risk." This is correlation, not causation.

**Step 6: Add pharmacogenomic modifier (if genetic data available).** When the patient has genetic test results, certain interactions become more or less clinically significant. Example: SLCO1B1 rs4149056 CT genotype → reduced statin clearance (PharmGKB Level 1A). The base Atorvastatin + Colchicine interaction is MAJOR. With the SLCO1B1 variant, the patient clears the statin more slowly than average, meaning the statin stays at higher concentrations for longer, compounding the interaction risk. The system notes: "This interaction carries additional risk given your SLCO1B1 genetic variant, which reduces how quickly your body clears Atorvastatin."

**Interaction severity levels:**

| Severity | Source | What It Means | On Chart |
|----------|--------|--------------|----------|
| **MAJOR** | DrugBank classification | Can cause serious harm. Avoid combination or monitor closely. | Red zone, pulsing indicator |
| **MODERATE** | DrugBank classification | May worsen a condition or require dose adjustment. | Orange zone |
| **MINOR** | DrugBank classification | Unlikely to be clinically significant. Be aware. | Not shown on chart (in report only) |

Only MAJOR and MODERATE interactions appear on the visual timeline. MINOR interactions are documented in the full report but don't clutter the chart.

**Multi-drug interactions:** Some clinically significant interactions involve 3+ drugs. Example: statin + fibrate + CYP3A4 inhibitor = rhabdomyolysis risk that exceeds any single pair. The system handles this by checking all pairwise combinations first, then flagging known triple-drug interactions from DrugBank separately, and noting compound risk when a patient has 2 flagged pairwise interactions that share a mechanism.

#### 3F. Treatment Effectiveness Assessment

**What it does:** Calculates how lab values changed during the period a medication was active. States the facts without attributing causation.

**How it works:**

1. **Identify the medication period.** Metformin: started Feb 2024, dose increased Jun 2025, still active.

2. **Collect lab values before and during.** HbA1c before Metformin: 9.4% (Jan 2024). HbA1c during Metformin: 9.1% (Apr 2024), 8.5% (Jul 2024), 7.8% (Jan 2025), 8.2% (Jan 2026).

3. **Calculate changes.**
   - Overall change: 9.4% → 8.2% = -1.2% improvement
   - Rate: approximately -0.3% per quarter during the first year
   - Trend direction: improving through the first year, with a recent uptick (8.2% after being as low as 7.8%)
   - Approaching target: Standard target is <7.0% for most patients; the patient got close (7.8%) but hasn't reached it

4. **Report facts, not conclusions.** The system says: "Your HbA1c went from 9.4% to 8.2% during the period you were on Metformin (-1.2% over 12 months)." It does NOT say: "Metformin lowered your HbA1c by 1.2%." Why? Because diet changes, exercise, weight loss, or other medications might have contributed. The system can't isolate the medication's effect from other factors — only a controlled clinical trial can do that.

---

### Layer 4: The Evidence Chain (Worked Example)

To make the full pipeline concrete, here's one finding — from raw uploaded PDF to the final output the doctor reads — with every step shown.

**The finding that appears on screen:**
> "💬 Discuss with your doctor because: Your records show 5 reports of worsening muscle symptoms over 18 months while on Atorvastatin. Multiple evidence sources support this association."

**Step 1 — Raw input (what the patient uploaded and entered):**
- `PCP_Note_2024-01.pdf` page 2: Contains "Atorvastatin 40mg daily, started 1/15/2024"
- `GeneSight_2023.pdf` page 4: Contains "SLCO1B1 rs4149056: CT (Intermediate Metabolizer)"
- Symptom Tracker: 5 entries tagged to Atorvastatin between Jun 2024 and Nov 2025

**Step 2 — Extraction (what the system derived from those inputs):**
- MedGemma (local) extracted: {medication: "Atorvastatin", dose: "40mg", start_date: "2024-01-15"} with confidence 0.96 from PCP_Note_2024-01.pdf page 2
- MedGemma (local) extracted: {gene: "SLCO1B1", variant: "rs4149056", genotype: "CT"} with confidence 0.98 from GeneSight_2023.pdf page 4
- Symptom Tracker provided: 5 timestamped entries with severity scores 4, 5, 5, 6, 7

**Step 3 — Analysis (what the system computed):**
- Modified Naranjo scoring: Factor 1 (+2, known SE in DailyMed + OpenFDA) + Factor 2 (+1, 5-month onset) + Factor 3 (+1, escalating) + Factor 4 (+2, SLCO1B1 Level 1A) + Factor 5 (+1, Gabapentin exists but predated) = 7 → HIGH
- Symptom trajectory: escalating (4→5→5→6→7 over 18 months)
- Drug interaction check: Atorvastatin + Colchicine = MAJOR (DrugBank), 3 of 5 symptoms during overlap
- RxNorm normalization confirmed "Atorvastatin" → RxCUI 83367

**Step 4 — Output (what the doctor reads):**
Every bullet point in the finding cites a specific source:
- "Muscle pain is a known side effect" → DailyMed label + OpenFDA FAERS (45K+ reports)
- "Your genetic test shows an SLCO1B1 variant" → GeneSight_2023.pdf, page 4 + PharmGKB Level 1A
- "Known major interaction with Colchicine" → DrugBank (DB00091 + DB01394)
- "Severity 4→7 over 18 months" → 5 Symptom Tracker entries with timestamps
- "How to bring this up: 'My muscle pain has been getting worse...'" → System-generated conversation starter

**Nothing in the output is unsourced.** The doctor can check the GeneSight report page 4 for the SLCO1B1 result, look up DrugBank DB00091 for the interaction record, verify the DailyMed label for the myalgia rate, and review the 5 symptom log entries with their timestamps. Every claim is verifiable.

---

### Layer 5: What the System Explicitly Does NOT Do

| The System Does | The System Does NOT Do |
|----------------|----------------------|
| Surfaces associations between medications and symptoms | Diagnose side effects or adverse drug reactions |
| Shows temporal co-occurrence ("X started, then Y appeared") | Claim causation ("X caused Y") |
| Reports published interaction severity from DrugBank | Invent or upgrade/downgrade interaction severity |
| Shows the patient's own lab trajectory and deviations | Predict future lab values as medical guidance |
| Scores evidence using transparent, auditable factors | Hide reasoning or use opaque "AI confidence scores" |
| Presents ALL plausible explanations, including non-medication ones | Cherry-pick the most alarming explanation |
| Says "Discuss with your doctor because..." | Says "You should stop taking..." or "Your doctor should..." |
| Reports what clinical databases say about a drug/gene/interaction | Practice medicine, interpret results, or recommend treatment |
| Shows data from the patient's records with file names and page numbers | Fabricate, interpolate, or infer data that isn't in the records |
| Flags symptoms the patient hasn't connected to any medication | Assume all symptoms are medication-related |

**The fundamental design constraint:** A physician reviewing any finding should be able to (1) see exactly what data the finding is based on, (2) see the scoring methodology and agree or disagree with each individual factor, and (3) make their own clinical judgment. The tool assembles and organizes evidence. The doctor decides what it means.

---

## Current Implementation Status

The tool's foundation pieces — each subsystem — are built and working independently. What's not built yet is the **integration layer** that wires them together into the unified view described in Parts 1–6.

### What's Built (foundations)

| Component | Status | Where it lives |
|---|---|---|
| Lab trend analysis + charting | ✅ Working | `src/analysis/trajectory.py` (regression, projections, D3 output) → `src/ui/static/js/trajectories.js` (D3 line charts with confidence bands) |
| Symptom logging + episodes | ✅ Working | `SymptomEpisode` model in `src/models.py` → API routes in `app.py` → Symptom Tracker UI |
| Symptom analytics | ✅ Working | `src/analysis/symptom_analytics.py` (correlations, heatmaps, counter-evidence scoring, trigger analysis) |
| Timeline flow visualization | ✅ Working | `src/ui/static/js/timeline_flow.js` (swim-lane timeline with medications, labs, diagnoses, symptoms) |
| Drug interaction databases | ✅ Working | `src/validation/ddinter.py` (DDinter 2.0), `drugbank.py`, `rxnorm.py`, `pubchem.py` — all query live clinical databases |
| Drug interaction model | ✅ Working | `DrugInteraction` in `src/models.py` (drug_a, drug_b, gene, severity, description, source) |
| Report generation framework | ✅ Working | `src/report/builder.py` (10-section Word doc with lab results, medications, conditions, imaging, genetics) |
| Anomaly detection (basic) | ✅ Working | Trajectory engine detects threshold crossings and deviations from projected trends |
| Pharmacogenomics analysis | ✅ Working | `src/analysis/diagnostic_engine/pharmacogenomics.py` (gene-drug lookups from PharmGKB) |
| HTML mockup | ✅ Exists | `mockup-lab-treatment-timeline.html` — shows the target design for all 6 parts, not wired to data |

### What's NOT Built Yet (the integration layer)

These are the pieces that connect the foundations above into the unified view described in this scope doc.

| Feature | What's Missing | Part |
|---|---|---|
| Medication bars on lab charts | No medication-to-lab mapping table, no D3 bars rendering under lab trends, no dose change tick marks, no event markers for start/stop | Part 1 |
| "Linked Medication" field on symptoms | `SymptomEpisode` has no `linked_medication_id` field — patients can't tag symptoms to specific medications yet | Part 2 |
| Side effect dots on medication bars | No overlay rendering of symptom dots on treatment bars, no severity-to-color mapping, no "Discuss with your doctor" tooltip | Part 2 |
| Treatment response correlation | No logic to correlate a medication's start date with lab value changes and compute "rate of improvement" | Part 3 |
| "Treatment Response & Tolerability" report section | Report lists medications and labs separately — no per-medication scorecard with effectiveness + tolerability + conversation starters | Part 3 |
| Investigation window logic | No code to look 30–90 days before an anomalous lab draw and pull all events from that window | Part 4 |
| "What Happened Here?" UI panel | No modal/panel when clicking an anomalous data point — no multi-source event aggregation (records + medications + symptoms + devices) | Part 4 |
| Health device integration | No importers for Apple Health XML, Fitbit CSV, Dexcom/Libre CSV — no device readings in the timeline | Part 4, 5 |
| Body system classification | `SymptomEpisode` has no `body_system` field, no auto-classifier mapping symptom keywords to GI/musculoskeletal/neurological/etc. | Part 5 |
| Unified symptom timeline by body system | No dedicated view grouping ALL symptoms by body system on one timeline — current timeline mixes symptoms with other event types | Part 5 |
| Cross-system pattern detection | No temporal cluster analysis (detecting symptoms from different body systems starting/changing in the same window) | Part 5 |
| "Symptom Landscape" report section | No report section for body-system-grouped symptoms with attributed vs. unattributed breakdown and cross-system patterns | Part 5 |
| Interaction zone visualization | No D3 rendering of interaction zones when two medications with known interactions overlap in time | Part 6 |
| Overlap period calculation | No code to compute concurrent medication windows and match them against DrugBank interaction pairs | Part 6 |
| Symptom-during-overlap correlation | No logic to check if patient-reported symptoms occurred during a drug interaction overlap and are consistent with the known interaction | Part 6 |
| Pharmacogenomic interaction context | PGx analysis exists but isn't wired to the interaction timeline (e.g., SLCO1B1 variant modifying statin interaction severity) | Part 6 |
| "Medication Interaction Review" report section | No report section summarizing interactions with overlap durations, severity, patient symptoms, and genetic context | Part 6 |

### What this means

The hardest parts are done — OCR extraction, trajectory analysis, drug interaction databases, symptom tracking, pharmacogenomics, report generation. These are the pieces that took months to build and validate against clinical databases.

What remains is **correlation logic and visualization**: wiring the existing subsystems so they talk to each other on a shared timeline. This is less risky work — the data is already there, it just needs to be connected.

The Implementation Phases below describe the build sequence.

---

## Implementation Phases

### Phase 1: Treatment bars on lab charts
- Build medication-to-lab mapping table
- Modify Trajectories overlay to render treatment bars below each chart
- Pull medication start/end dates and dose changes from profile data
- Add event markers for medication changes
- **Estimated scope:** Modify trajectories.js + trajectory.py

### Phase 2: Symptom log medication tagging
- Add "Linked Medication" optional field to symptom episode model
- Update Symptom Tracker UI with medication dropdown
- Store medication tags in symptom episodes
- **Estimated scope:** Modify models.py, symptoms.js, app.py

### Phase 3: Side effect overlay on timeline
- Pull medication-tagged symptoms into trajectory data
- Render side effect indicators on treatment bars
- Add hover/click detail panel
- **Estimated scope:** Modify trajectory.py, trajectories.js

### Phase 4: Anomaly detection + contextual event correlation
- Add anomaly detection to Trajectories engine (deviation from projected trend)
- Build event window query: medical records + medications + symptoms + device data in date range
- Render "What Happened Here?" panel on anomalous data points
- Source attribution on every surfaced event
- **Estimated scope:** Modify trajectory.py, trajectories.js, new event_correlation.py

### Phase 5: Health device data import
- Add device data importers for common formats (Apple Health XML, Fitbit CSV, Dexcom CSV/Clarity)
- Extract timestamped readings during Pass 0 (file classification)
- Store device data in clinical_timeline alongside labs and medications
- **Estimated scope:** New device_import.py in extraction/, modify models.py, modify Pass 0

### Phase 6: Unified symptom timeline (symptom mapping)
- Build symptom-to-body-system classifier (keyword-based mapping with patient override)
- Create new "Symptom Timeline" view alongside per-lab charts
- Render all symptoms grouped by body system on a single timeline
- Detect temporal clusters (symptoms starting/changing in the same window)
- Overlay medication periods for visual correlation
- Highlight unattributed symptoms prominently
- Add "Symptom Landscape" section to downloadable report
- **Estimated scope:** New symptom_timeline.js in ui/static/, new symptom_mapping.py, modify models.py (body system classification), modify report/builder.py

### Phase 7: Drug-drug interaction timeline
- Integrate DrugBank/DailyMed interaction lookup (normalize medication names via RxNorm first)
- Build pairwise overlap matrix from concurrent medications
- Render interaction zones on the treatment timeline
- Add severity-based visual styling (red = major, orange = moderate)
- Correlate patient symptoms during interaction overlap windows
- Incorporate pharmacogenomic factors from genetic test results
- Add "Medication Interaction Review" section to downloadable report
- **Estimated scope:** New drug_interactions.py in validation/, modify trajectories.js (interaction zone rendering), modify report/builder.py

### Phase 8: Report integration
- Add "Treatment Response & Tolerability" section to report builder
- Add "Lab Anomaly Context" callouts for anomalous values
- Add "Symptom Landscape" section from Phase 6
- Add "Medication Interaction Review" section from Phase 7
- Correlate lab trends with medication periods
- Include patient-reported side effects with severity/frequency
- Include health device supporting data where available
- **Estimated scope:** Modify report/builder.py

---

## Dependencies

- Existing: Trajectories engine (lab trend analysis) — already working
- Existing: Symptom Tracker (episode logging) — already working
- Existing: Medication extraction (Pass 1a) — already working
- Existing: Report builder (Word doc generation) — already working
- New: Medication-to-lab mapping table
- New: Medication tag field on symptom episodes
- New: Treatment response correlation logic
- New: Anomaly detection threshold logic (per-lab-type sensitivity)
- New: Event window query engine (cross-source timeline query)
- New: Health device data importers (Apple Health, Fitbit, CGM)
- New: Device data model and storage
- New: Symptom-to-body-system classifier (keyword mapping + patient override)
- New: Temporal cluster detection (symptoms co-occurring within configurable window)
- New: DrugBank / DailyMed interaction database integration
- New: RxNorm medication name normalization (for interaction lookups)
- New: Pairwise overlap matrix computation from medication timeline
- New: Pharmacogenomic interaction risk modifier (gene-drug-drug)

---

## Open Design Problems

### False attribution anxiety (the "gym problem")

If a patient goes to the gym and has normal post-exercise muscle soreness, they might log "muscle aches" in the symptom tracker and tag it to Atorvastatin. The system then flags it as "VERY HIGH LIKELIHOOD" based on the known-side-effect + genetic-risk factors — and the patient panics unnecessarily. The tool could cause people to over-index on medication side effects when there are perfectly normal explanations.

This is the fundamental tension: **the system surfaces associations, but people read causation.** Even with "Discuss with your doctor" framing, a "VERY HIGH" badge next to muscle pain is alarming.

**Why this is hard:**
- The system correctly identifies that Atorvastatin + SLCO1B1 + muscle pain = high association. That's factually accurate.
- But the system has no way to know the patient went to the gym yesterday. Activity data from Fitbit/Apple Watch could help, but the patient may not have a connected device.
- Asking "Did you exercise recently?" at the time of symptom entry adds friction and might feel patronizing.
- Lowering the likelihood score to compensate would undermine genuinely concerning cases.

**Possible approaches to revisit:**
1. When health device data IS available, factor in activity spikes (e.g., "Your step count was 3x your average yesterday — could this be exercise-related?")
2. Add an optional "What were you doing?" context field when logging symptoms — not mandatory, but available
3. In the report/tooltip, always include a line acknowledging common non-medication explanations (e.g., "Muscle aches can also be associated with exercise, physical strain, or illness")
4. Differentiate between a single report and a pattern — one "muscle aches" entry is different from 5 escalating reports over 18 months
5. Use language that's informative without being alarming — the badge system might need calibration

**No solution yet.** Flagging this for future design iteration. The risk is real: the tool could make someone afraid of a medication they need because they logged gym soreness.

---

## What the patient sees

A non-technical 60-year-old should be able to:
1. Open Trajectories and see their lab trends WITH the medications shown below
2. See colored dots showing when they reported side effects
3. Click on a spike in their labs and see in plain language what was happening at that time
4. Download a report that says in plain language: "Your diabetes medication is working (HbA1c went down) but you've been having stomach issues since the dose increase — bring this up with your doctor"
5. See that a lab spike was explained by real events in their records: "Your HbA1c went up because you were in the hospital with pneumonia and were on a steroid — it should come back down"
6. See ALL their symptoms on one timeline organized by body system — including ones they haven't linked to any medication — and understand what's getting better vs. worse
7. See a clear warning when two of their medications have a known interaction, especially when they're experiencing symptoms consistent with that interaction

## What the doctor sees

A physician reviewing the report or dashboard should be able to:
1. Correlate treatment changes with lab inflection points at a glance
2. See the side effect burden alongside treatment effectiveness
3. Make informed decisions about continuing, adjusting, or switching medications
4. See pharmacogenomic context (e.g., SLCO1B1 variant) inline with the treatment data
5. Click on any anomalous lab value and immediately see all concurrent events — diagnoses, medication changes, symptoms, device data — without digging through records
6. See health device data (CGM, activity, vitals) corroborating the clinical picture
7. Distinguish transient spikes (explainable) from unexplained deterioration (action needed)
8. See the full symptom landscape across body systems — not just medication-tagged symptoms — including unattributed symptoms that warrant investigation and cross-system temporal patterns
9. See drug-drug interaction warnings with overlap durations, severity classifications, and correlation with patient-reported symptoms during the interaction period — especially critical for multi-specialist patients where no single prescriber has the full picture
