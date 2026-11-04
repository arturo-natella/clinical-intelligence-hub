"""Conservative local repair of lab tests exported under procedure headings.

A name moves to labs only when it is a known single test, or an infection test
named only by what it looks for, how, and a few qualifiers (antigen, PCR,
culture, a kit's name...). Specimen collection, vaccines, questionnaires and
other interventions stay put, and so do panels such as a CBC: they are orders
whose results arrive as separate tests. The moved lab keeps the original entry
as `source_procedure` and is never given a result of its own. A lab moved under
an earlier rule that no longer qualifies goes back to procedures, and a moved
test that duplicates a same-day result is kept as that result's source instead.

Also the shared rules for what a lab entry says about its result, mirrored for
the browser in src/ui/static/js/lab_results.js.
"""

from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
import re

from src.models import LabResult, Procedure

# Word sets, matched in any order after dropping "poc"/"poct", "point of care",
# "test(s)", a kit size (digits followed by "t"), and the connecting words "in"/"of".
_LAB_TEST_NAMES = {frozenset(name.split()) for name in (
    # Urine dipstick and other urine tests
    "urine glucose", "urine protein", "urine ketones", "urine blood",
    "urine nitrite", "urine leukocytes", "urine leukocyte esterase",
    "urine bilirubin", "urine urobilinogen", "urine specific gravity",
    "urine ph", "urine microalbumin", "urine albumin", "urine culture",
    # Pregnancy
    "pregnancy", "urine pregnancy", "serum pregnancy", "hcg", "urine hcg",
    "serum hcg",
    # Vaginal fluid tests done at the visit
    "vaginal ph", "wet mount", "vaginal wet mount", "wet prep", "koh prep",
    # Glucose, A1c and other common single tests
    "fingerstick glucose", "finger stick glucose", "capillary glucose",
    "capillary blood glucose", "blood glucose", "hemoglobin a1c",
    "haemoglobin a1c", "hba1c", "a1c", "hemoglobin", "inr", "pt inr", "tsh",
    "thyroid stimulating hormone", "free t4", "ferritin", "monospot",
    # Stool screening
    "cologuard", "stool dna", "fit dna", "fecal immunochemical",
    "fecal occult blood", "stool occult blood", "fobt", "hemoccult",
    "stool culture",
)}
# Alone these are an obstetric history line or a fertility injection as often
# as a test, so they need the word "test" beside them ("Pregnancy test").
_NEEDS_A_TEST_WORD = {frozenset({"pregnancy"}), frozenset({"hcg"})}
_TEST_MARKERS = frozenset({"test", "tests", "poc", "poct"})

# An infection test names what it looks for, how it looks, and otherwise only
# these qualifiers, so "COVID-19 exposure screening" or "Flu test declined"
# stays a procedure.
_ORGANISM_WORDS = frozenset({
    "flu", "influenza", "sars", "covid", "covid19", "rsv", "strep",
    "streptococcal", "streptococcus", "mono", "mononucleosis", "hiv",
    "chlamydia", "gonorrhea", "trichomonas", "hpv",
})
_ASSAY_WORDS = frozenset({
    "antigen", "ag", "pcr", "naat", "rapid", "fia", "immunoassay", "culture",
    "test", "testing", "dna", "rna",
})
# Screening for these is a test. "COVID-19 screening" or "Flu screen" is
# usually a check-in or vaccination questionnaire, so it needs a method word.
_SCREENED_BY_A_TEST = frozenset({
    "hiv", "chlamydia", "gonorrhea", "trichomonas", "hpv", "mono", "mononucleosis",
    "strep", "streptococcal", "streptococcus",
})
_SCREEN_WORDS = frozenset({"screen", "screening"})
_INFECTION_QUALIFIERS = frozenset({
    "a", "b", "ab", "group", "type", "types", "1", "2", "19", "cov", "cov2",
    "and", "or", "with", "qualitative", "antibody", "antibodies", "hr",
    "trachomatis", "neisseria", "gonorrhoeae", "vaginalis", "virus", "viral",
    "human", "papillomavirus", "nasal", "nasopharyngeal", "throat", "probe",
    "amplified", "nucleic", "acid", "detection", "screen", "screening",
    # Point-of-care analyzers and kits a test is often named after
    "sofia", "binaxnow", "binax", "card", "quickvue", "osom", "veritor",
    "oraquick", "determine", "combo", "lucira", "xpert", "xpress",
})
_INTERVENTION_WORDS = frozenset({
    "collection", "collect", "collected", "vaccine", "vaccination",
    "vaccinations", "immunization", "immunizations", "injection", "shot",
    "booster", "counseling", "counselling", "education", "referral",
    "administration", "administered", "treatment", "therapy", "prophylaxis",
})
_IGNORED_WORDS = frozenset({"poc", "poct", "test", "tests", "in", "of"})

# Result text that only says what happened to a test: every word is a status
# or filler word, and at least one is a status.
_STATUS_WORDS = frozenset({
    "completed", "complete", "done", "performed", "ordered", "placed",
    "pending", "progress", "scheduled", "cancelled", "canceled", "cancel",
    "declined", "refused", "collected", "drawn", "sent", "received",
    "hemolyzed", "haemolyzed", "hemolysed", "haemolysed", "qns",
    "rejected", "see", "reported", "follow", "tnp", "unable",
    "scanned", "deferred", "postponed", "reviewed", "discussed", "awaiting",
    "unavailable", "clotted", "requested", "redraw", "recollect",
    # Order and report states, and what a model writes for a missing value
    "final", "finalized", "resulted", "preliminary", "prelim", "process",
    "processing", "transit", "discontinued", "duplicate", "error", "lost",
    "unsatisfactory", "hold", "active", "aborted", "registered", "unknown",
    "unspecified", "specified", "recorded", "documented", "mentioned", "stated",
    "provided", "tbd", "due", "overdue", "mailed", "given", "dispensed",
    "returned", "lipemic", "lipemia", "icteric", "icterus", "hemolysis", "inadequate",
    "invalid", "referred", "sendout", "mislabeled", "mislabelled", "unlabeled",
    "unlabelled", "recollection", "corrected", "amended", "partial", "verification",
    "left", "obtained", "mychart", "portal",
})
_STATUS_FILLER = frozenset({
    "not", "no", "none", "in", "to", "out", "lab", "labs", "laboratory",
    "specimen", "specimens", "sample", "samples", "test", "tests", "testing",
    "patient", "pt", "by", "the", "a", "an", "for", "quantity",
    "note", "notes", "comment", "comments", "report", "reports", "below",
    "above", "attached", "result", "results", "value", "values", "order",
    "orders", "was", "were", "been", "has", "have", "is", "will", "be", "and",
    "of", "at", "per", "on", "office", "clinic", "provider", "chart", "into",
    "separately", "outside", "external", "reference", "obtain", "obtained",
    "yet", "with", "today", "visit", "elsewhere", "send", "sending", "found",
    "available", "applicable", "further", "details", "please", "repeat",
    "entered", "review", "kit", "kits", "card", "cards", "next", "later",
    "facility", "grossly", "this", "from", "via", "up", "date", "quest", "labcorp",
    "arup", "mayo", "sonic", "bioreference", "diagnostics", "collect", "analysis",
    # Alone, "Insufficient" is a vitamin D category; beside a status it is not.
    "insufficient", "enough", "show",
})
# "No result", "Not available", "Not enough specimen", "No show".
_NEGATED_WHAT = frozenset({
    "result", "results", "value", "values", "specimen", "specimens", "sample", "samples",
    "available", "enough", "show",
})
_NO_RESULT_PHRASES = frozenset({
    "na", "n a", "not applicable", "not available", "no result", "no results",
    "no value", "null",
})
_QNS = re.compile(
    r"\b(?:quantity|specimen|sample|volume)\s+(?:not\s+sufficient|insufficient)"
    r"(?:\s+for\s+(?:testing|analysis|the\s+test))?\b"
    r"|\binsufficient\s+(?:sample\s+|specimen\s+)?(?:quantity|specimen|sample|volume)\b"
    r"|\binsufficient\s+for\s+(?:testing|analysis|the\s+test)\b"
)
_SEND_OUT = re.compile(r"\bsend\s*-?\s*outs?\b")
# Words that grade the specimen, not the result: "Specimen hemolyzed 3+" is no result.
_QUALITY_WORDS = frozenset({
    "hemolyzed", "haemolyzed", "hemolysed", "haemolysed", "hemolysis", "lipemic",
    "lipemia", "icteric", "icterus", "clotted",
})
_MONTHS = (
    r"(?:january|february|march|april|may|june|july|august|september|october"
    r"|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
)
# Full dates and clock times written with am/pm. A bare "1/3" or "4:30" can be
# the result (a stool card, a bleeding time), so it is a time only after a
# status word (_STATUS_TIME).
_DATE_OR_TIME = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}t\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:z|[+-]\d{2}:?\d{2})?"
    r"|\b\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}\b"
    r"|\b(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\s*[ap]\.?m\b\.?"
    r"|\b(?:0?[1-9]|1[0-2])\s*[ap]\.?m\b\.?"
    rf"|\b{_MONTHS}\b\.?(?:\s*\d{{1,2}}(?:st|nd|rd|th)?\b)?(?:,?\s*\d{{4}}\b)?"
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}\b\.?(?:,?\s*\d{{4}}\b)?",
    re.ASCII,
)
# "Collected 0915", "Pending 3/4", "Received @ 14:32": when the status happened.
_STATUS_TIME = re.compile(
    r"\b(collected|received|drawn|reported|resulted|completed|done|pending|ordered|scheduled"
    r"|cancelled|canceled|sent|performed|at|on)\s*@?\s*"
    r"(?:(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])(?:/\d{2,4})?"
    r"|(?:[01]?\d|2[0-3]):[0-5]\d|(?:[01]\d|2[0-3])[0-5]\d)\b"
    r"|@\s*(?:[01]?\d|2[0-3]):?[0-5]\d\b",
    re.ASCII,
)
_NUMBER = re.compile(r"([<>]=?)?\s*(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)", re.ASCII)
_UNIT_TOKEN = (
    r"(?:%|percent|[a-z0-9\u00b5\u03bc^*.]*[a-z\u00b5\u03bc][a-z0-9\u00b5\u03bc^*.]*/[a-z0-9\u00b5\u03bc^*./]+"
    r"|/[a-z\u00b5\u03bc][a-z0-9\u00b5\u03bc^*./]*)"
)
# A number with the unit it is printed with: '15 ug/L' says no more than 15.
_NUMBER_WITH_UNIT = re.compile(
    r"([<>]=?)?\s*(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*" + _UNIT_TOKEN + "?", re.ASCII)
_UNIT_AFTER_NUMBER = re.compile(r"\d\s*" + _UNIT_TOKEN + r"(?![a-z0-9])", re.ASCII)
# A titer or a dipstick grade is a result even though it has no letters.
_TITER = re.compile(r"(?<![\d.])(?:[<>]=?\s*)?1\s*:\s*\d+", re.ASCII)
_GRADE = re.compile(r"(?<![\w+])(?:[1-4]\s?\+|\+{1,4}|\+\s?/\s?-|\u00b1)(?![\w+])", re.ASCII)
# A flag written after a listed result: '9.4 % (H)', '212 mg/dL H'.
_FLAG_NOTE = re.compile(
    r"\s*\((?:h|l|a|hh|ll|high|low|abnormal|abn|critical|crit)\)\s*$"
    r"|\s+(?:h|l|a|hh|ll|high|low|abnormal|abn|critical|crit)\s*$",
    re.ASCII,
)
# What a procedure listing's outcome has to be to count as the result: a
# number with an optional unit, or a word that states a finding.
_MEASUREMENT = re.compile(
    r"(?:(?:result|value|level)\s*:?\s*)?(?:[<>]=?\s*)?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:\s*" + _UNIT_TOKEN + ")?",
    re.ASCII,
)
_RESULT_WORDS = frozenset({
    "positive", "negative", "pos", "neg", "detected", "reactive", "nonreactive",
    "trace", "growth", "indeterminate", "equivocal", "inconclusive", "borderline",
    "immune", "nonimmune",
})
# "High" or "Abnormal" with no value interprets a result the listing does not give.
_INTERPRETATION_WORDS = frozenset({
    "high", "low", "abnormal", "elevated", "increased", "decreased", "critical",
})
# Every space the browser's \s matches, so both sides read text alike.
_SPACES = re.compile("[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+")

# Flags compared by their words ("Non-Reactive" is "non reactive"), or a symbol as written.
_NOT_FLAGGED = frozenset({
    "normal", "n", "nl", "wnl", "within normal limits", "within normal range", "normal range",
    "in range", "within range", "within reference range", "negative", "neg", "non reactive",
    "nonreactive", "not reactive", "nr", "not detected", "none detected", "nd",
})
_PLACEHOLDER_FLAGS = frozenset({
    "none", "null", "nil", "n a", "na", "unknown", "not applicable", "not flagged", "no flag",
    "unflagged", "none flagged",
})
_DASHES = frozenset({"-", "--", "---", "\u2013", "\u2014", ".", "..", "...", "?", "??"})
_HIGH_FLAGS = frozenset({"high", "h", "hh", "critical high", "high critical", "elevated", "\u2191", "\u25b2"})
_LOW_FLAGS = frozenset({"low", "l", "ll", "critical low", "low critical", "\u2193", "\u25bc"})
# Flags that say a result is abnormal without saying which way.
_ABNORMAL_FLAGS = frozenset({
    "abnormal", "abn", "a", "aa", "critical", "crit", "c", "positive", "pos", "reactive",
    "detected", "*", "**", "!", "!!",
})
_BLANK_TEXTS = frozenset({"null", "na", "n a", "not applicable", "unknown", "tbd"})

NO_RESULT_TEXT = "Result not recorded"
FLAG_ONLY_TEXT = "Value not recorded"


def _words(name) -> list:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(name or "").lower())
    return re.sub(r"\bpoint of care\b", " poc ", normalized).split()


def is_lab_test_name(name: str) -> bool:
    """Recognize a known single test or an infection test, never an intervention."""
    words = set(_words(name))
    if not words or words & _INTERVENTION_WORDS:
        return False
    if words & {"hpv", "papillomavirus"}:
        words -= {"high", "risk"}  # "high-risk HPV" names the types tested
    core = {w for w in words if w not in _IGNORED_WORDS and not re.fullmatch(r"\d+t", w)}
    assays = _ASSAY_WORDS | (_SCREEN_WORDS if words & _SCREENED_BY_A_TEST else frozenset())
    infection_words = _ORGANISM_WORDS | _ASSAY_WORDS | _INFECTION_QUALIFIERS
    if words & _ORGANISM_WORDS and words & assays and core <= infection_words:
        return True
    core = frozenset(core)
    if core in _NEEDS_A_TEST_WORD and (not words & _TEST_MARKERS or words & {"in", "of"}):
        return False
    return core in _LAB_TEST_NAMES


def _field(record, key):
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return number_text(value)
    return _SPACES.sub(" ", str(value)).strip(" ")


def _without_dates(text) -> str:
    """Lowercase text with its dates and status times taken out; statuses spelled one way."""
    text = _SEND_OUT.sub(" sendout ", _QNS.sub(" qns ", text))
    return _STATUS_TIME.sub(r" \1 ", _DATE_OR_TIME.sub(" ", text))


def says_no_result(text) -> bool:
    """True for text that only reports a status, such as 'Cancelled' or 'Specimen hemolyzed'."""
    cleaned = _text(text).lower()
    if not cleaned:
        return False
    cleaned = _without_dates(cleaned)
    quality = set(re.findall(r"[a-z]+", cleaned)) & _QUALITY_WORDS
    if _TITER.search(cleaned) or (not quality and _GRADE.search(cleaned)):
        return False
    if quality:
        cleaned = _GRADE.sub(" ", cleaned)  # a hemolysis grade, not a result
    words = re.findall(r"[a-z0-9]+", cleaned)
    if not words:
        return True  # only punctuation, a date or a time
    if " ".join(words) in _NO_RESULT_PHRASES:
        return True
    found = set(words)
    status = found & _STATUS_WORDS or (found & {"no", "not"} and found & _NEGATED_WHAT)
    return bool(status) and found <= _STATUS_WORDS | _STATUS_FILLER


def outcome_states_result(text) -> bool:
    """Whether a procedure listing's outcome plainly states a result.

    Listings mostly carry a status in words no list can cover, so only a
    measurement, a titer, a grade or a finding such as 'Negative' counts, with
    or without a flag beside it. 'High' or 'Abnormal' alone interprets a
    result the listing never gives.
    """
    cleaned = _text(text).lower()
    if not cleaned:
        return False
    if _MEASUREMENT.fullmatch(_FLAG_NOTE.sub("", cleaned)):
        return True  # '9.4 %', or '9.4 % (H)' with the flag written after it
    cleaned = _without_dates(cleaned)
    words = set(re.findall(r"[a-z0-9]+", cleaned))
    if words & _QUALITY_WORDS:
        return False
    if _TITER.search(cleaned) or words & _RESULT_WORDS:
        return True
    if words & _INTERPRETATION_WORDS:
        return False
    return bool(_GRADE.search(cleaned))


def procedure_outcome(lab) -> str:
    """The outcome written on the procedure entry a lab test was moved from."""
    source = _field(lab, "source_procedure")
    return _text(source.get("outcome")) if isinstance(source, dict) else ""


def _flag_words(flag) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", _text(flag).lower()))


def lab_flag(lab) -> str:
    """The entry's flag as written, or '' when it is blank, a dash or a placeholder
    such as 'None'. A symbol such as '*' or an arrow is a flag."""
    flag = _text(_field(lab, "flag"))
    if not flag or flag in _DASHES or _flag_words(flag) in _PLACEHOLDER_FLAGS:
        return ""
    return flag


def flag_key(flag) -> str:
    """A flag for comparing: its words ('non reactive'), or its symbol ('\u2191')."""
    flag = lab_flag({"flag": flag})
    return _flag_words(flag) or flag


def is_flagged(flag) -> bool:
    """Whether a flag marks a result: 'High', 'Critical', '*', not 'WNL', 'Not detected' or 'None'."""
    key = flag_key(flag)
    return bool(key) and key not in _NOT_FLAGGED


def says_abnormal(flag) -> bool:
    """Whether a flag says abnormal without saying which way ('Abnormal', 'Critical', '*')."""
    return flag_key(flag) in _ABNORMAL_FLAGS


def flag_direction(lab) -> str:
    """'high' or 'low' when the flag says which. A bare 'Critical' or 'Abnormal'
    takes it from the value and range when they show one; otherwise ''."""
    key = flag_key(_field(lab, "flag"))
    if key in _HIGH_FLAGS:
        return "high"
    if key in _LOW_FLAGS:
        return "low"
    if not is_flagged(key):
        return ""
    try:
        value = float(_field(lab, "value"))
        low, high = _field(lab, "reference_low"), _field(lab, "reference_high")
        if high is not None and value > float(high):
            return "high"
        if low is not None and value < float(low):
            return "low"
    except (TypeError, ValueError):
        pass
    return ""


def _measured(lab) -> bool:
    """A test reported as a number: it has a range, or a unit other than a count per field."""
    if _field(lab, "reference_low") is not None or _field(lab, "reference_high") is not None:
        return True
    unit = _text(_field(lab, "unit")).lower()
    return bool(unit) and not re.search(r"hpf|lpf|field", unit)


def _own_text(lab) -> str:
    """The entry's result text, or '' for a blank written as text: 'null', '-',
    or 'None' for a test measured as a number (for microscopy 'None' is the finding)."""
    text = _text(_field(lab, "value_text"))
    words = _flag_words(text)
    if not words:
        return text if _GRADE.search(text.lower()) else ""
    if words in _BLANK_TEXTS or (words in ("none", "nil") and _measured(lab)):
        return ""
    return text


def lab_has_result(lab, include_outcome: bool = True) -> bool:
    """True when the entry records a result: a value, a flag, or text that states one.

    With include_outcome, the outcome written on the procedure entry a test was
    moved from counts when it plainly states one, so 'Positive' does and
    'Completed' or 'Final' does not.
    """
    if _field(lab, "value") is not None or lab_flag(lab):
        return True
    text = _own_text(lab)
    if text and not says_no_result(text):
        return True
    return include_outcome and outcome_states_result(procedure_outcome(lab))


def number_text(value) -> str:
    """A number as the browser writes it: 7, 7.2, 0.00005, 1e-7, 1e+21."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number != number or abs(number) == float("inf"):
        return str(value)
    if number == 0:
        return "0"
    if 1e-6 <= abs(number) < 1e21:
        text = format(Decimal(repr(number)), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    mantissa, _, exponent = repr(number).partition("e")
    return f"{mantissa}e{int(exponent):+d}"


def _unit_spelling(unit) -> str:
    return re.sub(r"\s+", "", _text(unit).lower()).replace("\u00b5", "u").replace("\u03bc", "u").replace("mcg", "ug")


def _with_unit(text, unit) -> str:
    """Text with its unit, unless the text already writes it, in any spelling."""
    if not unit:
        return text
    lowered = text.lower()
    if _UNIT_AFTER_NUMBER.search(lowered) or re.search(
            rf"(?<![a-z]){re.escape(_unit_spelling(unit))}(?![a-z])", _unit_spelling(lowered)):
        return text
    return f"{text} {unit}"


def _numbers(text) -> set:
    return {number_text(match.group(2).replace(",", "")) for match in _NUMBER.finditer(text)}


def lab_result_text(lab, include_unit: bool = True) -> str:
    """What the record says the result is, in words a reader can trust.

    A value or result text comes first, and text printed beside a number
    ('<0.01', 'Reactive') is kept with it. Otherwise the outcome written on
    the procedure entry is shown as exactly that, and failing both the test is
    plainly marked as having no recorded value or result.
    """
    unit = _text(_field(lab, "unit"))
    shown_unit = unit if include_unit else ""
    value = _field(lab, "value")
    text = _own_text(lab)
    if value is not None:
        number = number_text(value)
        if not text or _result_key(text, unit) == number:
            return _with_unit(number, shown_unit)
        if number in _numbers(text):
            return _with_unit(text, shown_unit)
        return f"{_with_unit(number, shown_unit)} ({text})"
    if text:
        return _with_unit(text, shown_unit)
    outcome = procedure_outcome(lab)
    if lab_flag(lab) and not outcome_states_result(outcome):
        return FLAG_ONLY_TEXT
    if outcome:
        return f"{outcome} (listed with procedures)"
    return NO_RESULT_TEXT


def _result_key(text, unit="") -> str:
    """Comparable form of result text: '90 mg/dL' with unit mg/dL is '90'."""
    key = " ".join(_text(text).lower().split())
    unit = " ".join(_text(unit).lower().split())
    if unit and key.endswith(unit) and not re.search(r"[a-z\u00b5\u03bc]$", key[: -len(unit)]):
        key = key[: -len(unit)].strip()
    match = _NUMBER_WITH_UNIT.fullmatch(key)
    if match:
        return (match.group(1) or "") + number_text(match.group(2).replace(",", ""))
    return key


def plain_number(lab):
    """The entry's value when nothing printed beside it qualifies it, else None."""
    value = _field(lab, "value")
    if value is None:
        return None
    text = _own_text(lab)
    if text and _result_key(text, _text(_field(lab, "unit"))) != number_text(value):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def unit_key(lab) -> str:
    """The entry's unit for comparing two results: case, spaces and the micro sign ignored."""
    return re.sub(r"\s+", "", _text(_field(lab, "unit")).lower()).replace("µ", "u").replace("μ", "u")


def lab_result_token(lab) -> str:
    """What deduplication compares as the result of a lab entry.

    A number and the same number written as text are one result, text beside
    a number that says more keeps entries apart, and a test listed without a
    result is told apart by the outcome written with it.
    """
    unit = _text(_field(lab, "unit"))
    value = _field(lab, "value")
    text = _result_key(_own_text(lab), unit)
    if value is not None:
        number = number_text(value)
        return number if not text or text == number else f"{number}|{text}"
    if text:
        return text
    flag = lab_flag(lab).lower()
    if flag:
        return f"flag:{flag}"
    return "listed:" + _result_key(procedure_outcome(lab), unit)


def _name_key(lab) -> str:
    """A name blind to case, spaces and punctuation: 'Vitamin B-12' is 'vitaminb12'."""
    return re.sub(r"[^a-z0-9]", "", _text(_field(lab, "name") or _field(lab, "test_name")).lower())


def lab_test_key(lab) -> str:
    """One key for a test however it is written, as the Labs page groups them:
    its LOINC code when it has one ('HbA1c' and 'Hemoglobin A1c'), else its name."""
    code = _text(_field(lab, "loinc_code"))
    return f"loinc:{code}" if code else _name_key(lab)


def _date_key(lab) -> str:
    value = _field(lab, "test_date") or _field(lab, "date") or _field(lab, "collected_date")
    return value.isoformat() if hasattr(value, "isoformat") else _text(value)


def newest_results(labs) -> list:
    """Entries with a result, newest first.

    On one day an entry with a result of its own comes before one listed with
    procedures, and a flagged one before an unflagged one, since nothing says
    which came later; otherwise stored order is kept. Undated entries come last.
    """
    resulted = [lab for lab in labs if lab_has_result(lab)]
    return sorted(
        resulted,
        key=lambda lab: (_date_key(lab), lab_has_result(lab, include_outcome=False),
                         is_flagged(lab_flag(lab))),
        reverse=True,
    )


def latest_results(labs) -> list:
    """The newest result of each test, however its name is written."""
    latest = {}
    for lab in newest_results(labs):
        latest.setdefault(lab_test_key(lab), lab)
    return list(latest.values())


# Words that leave a test unchanged when an engine names it: "Glucose, fasting"
# and "TSH, 3rd generation" are those tests; "Urine glucose" and "Hemoglobin A1c" are not.
_SAME_TEST_WORDS = frozenset({
    "serum", "plasma", "blood", "venous", "capillary", "level", "levels", "total", "test",
    "result", "value", "quantitative", "quant", "fasting", "random", "poc", "poct",
    "fingerstick", "finger", "stick", "count", "calc", "calculated", "3rd", "generation",
    "ultrasensitive", "sensitive", "intact", "activity", "ia", "ckd", "epi", "mdrd", "auto",
    "automated",
})
_LOINC = []


def _loinc_db():
    if not _LOINC:
        from src.standardization.loinc import LOINCDatabase

        _LOINC.append(LOINCDatabase())
    return _LOINC[0]


@lru_cache(maxsize=4096)
def _code_of_name(name) -> str:
    match = _loinc_db().lookup(name) if _text(name) else None
    return match["code"] if match else ""


def _singular(words) -> set:
    return {w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words}


def _name_variants(name) -> list:
    """The name's words, and the words outside and inside any parentheses:
    'Creatine Kinase (CK)' is also 'creatine kinase' and 'ck'."""
    text = _text(name).lower()
    variants = [text, re.sub(r"\([^)]*\)", " ", text)] + re.findall(r"\(([^)]*)\)", text)
    return [_singular(re.findall(r"[a-z0-9]+", variant)) for variant in variants]


def matches_test(lab, test_name) -> bool:
    """Whether an entry is a result of the test an engine names: the same LOINC
    code, or every word of the test with only words that leave it unchanged."""
    wanted = _singular(re.findall(r"[a-z0-9]+", _text(test_name).lower()))
    if not wanted:
        return False
    name = _field(lab, "name") or _field(lab, "test_name")
    code = _code_of_name(test_name)
    if code and code == (_text(_field(lab, "loinc_code")) or _code_of_name(name)):
        return True
    return any(
        words and wanted <= words and words - wanted <= _SAME_TEST_WORDS
        for words in _name_variants(name)
    )


def _is_listing(lab) -> bool:
    """An entry with no value, result text or flag of its own."""
    return _field(lab, "value") is None and not _own_text(lab) and not lab_flag(lab)


def _same_test(a, b) -> bool:
    code = _text(_field(a, "loinc_code"))
    return bool(code and code == _text(_field(b, "loinc_code"))) or bool(
        _name_key(a) and _name_key(a) == _name_key(b)
    )


def _same_listing(a, b) -> bool:
    """Two procedure entries that list one test the same way: name, day and outcome,
    whatever provenance or empty fields each carries."""
    def day(entry):
        return _day(entry.get("procedure_date") or entry.get("test_date"))
    return (
        _name_key(a) == _name_key(b) and day(a) == day(b)
        and _result_key(a.get("outcome")) == _result_key(b.get("outcome"))
    )


def _interpretation(outcome) -> str:
    """'high', 'low' or 'abnormal' when an outcome only interprets a result."""
    words = set(re.findall(r"[a-z]+", _text(outcome).lower()))
    stated = words & _INTERPRETATION_WORDS
    if not stated or not words <= _INTERPRETATION_WORDS | _STATUS_WORDS | _STATUS_FILLER:
        return ""
    if stated <= {"high", "elevated", "increased"}:
        return "high"
    if stated <= {"low", "decreased"}:
        return "low"
    return "abnormal"


def _records(lab, outcome) -> bool:
    """Whether a result entry records a listing's outcome: any result for a bare
    status, one flagged that way for 'High' or 'Abnormal', else the same result."""
    if not outcome or says_no_result(outcome):
        return True
    direction = _interpretation(outcome)
    if direction == "abnormal":
        return is_flagged(lab_flag(lab))
    if direction:
        return flag_direction(lab) == direction
    unit = _text(_field(lab, "unit"))
    keys = {_result_key(_field(lab, "value_text"), unit)}
    if _field(lab, "value") is not None:
        keys.add(number_text(_field(lab, "value")))
    return _result_key(outcome, unit) in keys


def _day(value) -> str:
    """A calendar day, or '' for a date the fold cannot compare ('September 3, 2023')."""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    text = _text(value)
    return text[:10] if re.match(r"\d{4}-\d{2}-\d{2}(?!\d)", text) else ""


def _with_source(lab, source):
    if isinstance(lab, dict):
        return {**lab, "source_procedure": deepcopy(source)}
    return lab.model_copy(update={"source_procedure": deepcopy(source)})


def fold_listings(labs, same_test=_same_test) -> list:
    """Fold each test listed without a result into the one result it lists.

    A listing matches an entry with a result of its own for the same test on
    the same calendar day when its outcome is empty, only a status, 'High' or
    'Abnormal' for a result flagged that way, or that result. It is kept as
    the result's source_procedure; a listing that has no procedure entry, or
    one that lists the test the same way as the kept one, carries nothing more
    and is dropped. A result that already keeps a different listing's
    procedure leaves this one in place, and so does a listing that no single
    entry matches. Entries are copied, never changed in place.
    """
    labs = list(labs)
    by_day = {}
    for index, item in enumerate(labs):
        day = _day(_field(item, "test_date"))
        if day:
            by_day.setdefault(day, []).append(index)

    folded = set()
    for indexes in by_day.values():
        for i in indexes:
            listing = labs[i]
            if not _is_listing(listing):
                continue
            outcome = procedure_outcome(listing)
            matches = [
                j for j in indexes
                if j not in folded and lab_has_result(labs[j], include_outcome=False)
                and same_test(listing, labs[j]) and _records(labs[j], outcome)
            ]
            if len(matches) != 1:
                continue
            source = _field(listing, "source_procedure")
            kept = _field(labs[matches[0]], "source_procedure")
            if isinstance(source, dict):
                if isinstance(kept, dict) and not _same_listing(kept, source):
                    continue
                if not kept:
                    labs[matches[0]] = _with_source(labs[matches[0]], source)
            folded.add(i)

    return [item for index, item in enumerate(labs) if index not in folded]


def _restored_procedure(lab):
    """The procedure a lab came from, when its name no longer passes as a lab test."""
    source = _field(lab, "source_procedure")
    if not isinstance(source, dict) or not _is_listing(lab) or is_lab_test_name(_field(lab, "name")):
        return None
    record = lab.model_dump(mode="json") if hasattr(lab, "model_dump") else lab
    restored = {key: deepcopy(source[key]) for key in Procedure.model_fields if key in source}
    restored["name"] = restored.get("name") or record.get("name")
    # The lab's own date and provenance were validated; the source's may not be.
    restored["procedure_date"] = record.get("test_date")
    restored["provenance"] = deepcopy(record.get("provenance"))
    try:
        Procedure.model_validate(restored)
    except Exception:
        return None
    return restored


def normalize_lab_procedures(timeline: dict) -> dict:
    """Return a copy with lab tests moved out of procedures; the input is untouched.

    Accepts serialized or Pydantic records and is idempotent. The API reads use
    it on saved profiles without changing them, but ClinicalTimeline validation
    runs it too, so the next pipeline save stores the repaired categories.
    """
    labs, moved, procedures, restored = [], [], [], []
    for item in timeline.get("labs") or []:
        procedure = _restored_procedure(item)
        if procedure is None:
            labs.append(item)
        else:
            restored.append(procedure)

    for item in timeline.get("procedures") or []:
        record = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        if not isinstance(record, dict) or not is_lab_test_name(record.get("name")):
            procedures.append(item)
            continue

        # Keep explicit result fields if an extractor supplied them. An outcome
        # such as 'Completed' stays in source_procedure, never in the result.
        lab = {key: deepcopy(record[key]) for key in LabResult.model_fields if key in record}
        lab["test_date"] = record.get("test_date") or record.get("procedure_date")
        lab["ordering_provider"] = record.get("ordering_provider") or record.get("provider")
        lab["lab_facility"] = record.get("lab_facility") or record.get("facility")
        lab["source_procedure"] = {
            key: deepcopy(record[key]) for key in Procedure.model_fields if key in record
        }
        moved.append(lab)

    folded = fold_listings(labs + moved)
    if not moved and not restored and len(folded) == len(labs):
        return timeline
    return {**timeline, "labs": folded, "procedures": procedures + restored}
