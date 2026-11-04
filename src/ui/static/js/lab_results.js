/* What a lab entry says about its result, mirroring the server rules in
   src/standardization/record_categories.py. A test listed without a result
   is shown as exactly that, and never stands in for a measured result. */
var LabResults = {
    NO_RESULT: "Result not recorded",
    FLAG_ONLY: "Value not recorded",

    // Result text that only reports a status: every word is a status or
    // filler word, and at least one is a status.
    _STATUS_WORDS: [
        "completed", "complete", "done", "performed", "ordered", "placed",
        "pending", "progress", "scheduled", "cancelled", "canceled", "cancel",
        "declined", "refused", "collected", "drawn", "sent", "received",
        "hemolyzed", "haemolyzed", "hemolysed", "haemolysed", "qns",
        "rejected", "see", "reported", "follow", "tnp", "unable",
        "scanned", "deferred", "postponed", "reviewed", "discussed", "awaiting",
        "unavailable", "clotted", "requested", "redraw", "recollect",
        "final", "finalized", "resulted", "preliminary", "prelim", "process",
        "processing", "transit", "discontinued", "duplicate", "error", "lost",
        "unsatisfactory", "hold", "active", "aborted", "registered", "unknown",
        "unspecified", "specified", "recorded", "documented", "mentioned", "stated",
        "provided", "tbd", "due", "overdue", "mailed", "given", "dispensed",
        "returned", "lipemic", "lipemia", "icteric", "icterus", "hemolysis", "inadequate",
        "invalid", "referred", "sendout", "mislabeled", "mislabelled", "unlabeled",
        "unlabelled", "recollection", "corrected", "amended", "partial", "verification",
        "left", "obtained", "mychart", "portal"
    ],
    _STATUS_FILLER: [
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
        "insufficient", "enough", "show"
    ],
    _NEGATED_WHAT: [
        "result", "results", "value", "values", "specimen", "specimens", "sample", "samples",
        "available", "enough", "show"
    ],
    _NO_RESULT_PHRASES: [
        "na", "n a", "not applicable", "not available", "no result", "no results",
        "no value", "null"
    ],
    _QUALITY_WORDS: [
        "hemolyzed", "haemolyzed", "hemolysed", "haemolysed", "hemolysis", "lipemic",
        "lipemia", "icteric", "icterus", "clotted"
    ],
    _QNS: new RegExp(
        "\\b(?:quantity|specimen|sample|volume)\\s+(?:not\\s+sufficient|insufficient)"
        + "(?:\\s+for\\s+(?:testing|analysis|the\\s+test))?\\b"
        + "|\\binsufficient\\s+(?:sample\\s+|specimen\\s+)?(?:quantity|specimen|sample|volume)\\b"
        + "|\\binsufficient\\s+for\\s+(?:testing|analysis|the\\s+test)\\b",
        "g"
    ),
    _SEND_OUT: /\bsend\s*-?\s*outs?\b/g,
    // Full dates and clock times written with am/pm. A bare "1/3" or "4:30"
    // can be the result, so it is a time only after a status word.
    _DATE_OR_TIME: new RegExp(
        "\\b\\d{4}-\\d{1,2}-\\d{1,2}t\\d{1,2}:\\d{2}(?::\\d{2}(?:\\.\\d+)?)?(?:z|[+-]\\d{2}:?\\d{2})?"
        + "|\\b\\d{1,4}[/.-]\\d{1,2}[/.-]\\d{1,4}\\b"
        + "|\\b(?:[01]?\\d|2[0-3]):[0-5]\\d(?::[0-5]\\d)?\\s*[ap]\\.?m\\b\\.?"
        + "|\\b(?:0?[1-9]|1[0-2])\\s*[ap]\\.?m\\b\\.?"
        + "|\\b(?:january|february|march|april|may|june|july|august|september|october"
        + "|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\\b"
        + "\\.?(?:\\s*\\d{1,2}(?:st|nd|rd|th)?\\b)?(?:,?\\s*\\d{4}\\b)?"
        + "|\\b\\d{1,2}(?:st|nd|rd|th)?\\s+(?:january|february|march|april|may|june|july"
        + "|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept"
        + "|oct|nov|dec)\\b\\.?(?:,?\\s*\\d{4}\\b)?",
        "g"
    ),
    // "Collected 0915", "Pending 3/4", "Received @ 14:32": when the status happened.
    _STATUS_TIME: new RegExp(
        "\\b(collected|received|drawn|reported|resulted|completed|done|pending|ordered|scheduled"
        + "|cancelled|canceled|sent|performed|at|on)\\s*@?\\s*"
        + "(?:(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\\d|3[01])(?:/\\d{2,4})?"
        + "|(?:[01]?\\d|2[0-3]):[0-5]\\d|(?:[01]\\d|2[0-3])[0-5]\\d)\\b"
        + "|@\\s*(?:[01]?\\d|2[0-3]):?[0-5]\\d\\b",
        "g"
    ),
    _NUMBER: "([<>]=?)?\\s*(-?(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?)",
    _UNIT_TOKEN: "(?:%|percent|[a-z0-9µμ^*.]*[a-zµμ][a-z0-9µμ^*.]*/[a-z0-9µμ^*./]+"
        + "|/[a-zµμ][a-z0-9µμ^*./]*)",
    // A titer or a dipstick grade is a result even though it has no letters.
    _TITER: /(?<![\d.])(?:[<>]=?\s*)?1\s*:\s*\d+/,
    _GRADE: /(?<![\w+])(?:[1-4]\s?\+|\+{1,4}|\+\s?\/\s?-|±)(?![\w+])/,
    // A flag written after a listed result: "9.4 % (H)", "212 mg/dL H".
    _FLAG_NOTE: /\s*\((?:h|l|a|hh|ll|high|low|abnormal|abn|critical|crit)\)\s*$|\s+(?:h|l|a|hh|ll|high|low|abnormal|abn|critical|crit)\s*$/,
    _RESULT_WORDS: [
        "positive", "negative", "pos", "neg", "detected", "reactive", "nonreactive",
        "trace", "growth", "indeterminate", "equivocal", "inconclusive", "borderline",
        "immune", "nonimmune"
    ],
    _INTERPRETATION_WORDS: ["high", "low", "abnormal", "elevated", "increased", "decreased", "critical"],
    // Every space \s matches, as the server's pattern lists them.
    _SPACES: /[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+/g,
    // Flags compared by their words ("Non-Reactive" is "non reactive"), or a symbol as written.
    _NOT_FLAGGED: [
        "normal", "n", "nl", "wnl", "within normal limits", "within normal range", "normal range",
        "in range", "within range", "within reference range", "negative", "neg", "non reactive",
        "nonreactive", "not reactive", "nr", "not detected", "none detected", "nd"
    ],
    _NORMAL_LABELS: [
        "normal", "n", "nl", "wnl", "within normal limits", "within normal range", "normal range",
        "in range", "within range", "within reference range"
    ],
    _PLACEHOLDER_FLAGS: [
        "none", "null", "nil", "n a", "na", "unknown", "not applicable", "not flagged", "no flag",
        "unflagged", "none flagged"
    ],
    _DASHES: ["-", "--", "---", "–", "—", ".", "..", "...", "?", "??"],
    _HIGH_FLAGS: ["high", "h", "hh", "critical high", "high critical", "elevated", "↑", "▲"],
    _LOW_FLAGS: ["low", "l", "ll", "critical low", "low critical", "↓", "▼"],
    _BLANK_TEXTS: ["null", "na", "n a", "not applicable", "unknown", "tbd"],

    _numberText: function(value) {
        var number = Number(value);
        return value !== null && String(value).trim() !== "" && isFinite(number) ? String(number) : String(value);
    },

    _text: function(value) {
        if (value == null) return "";
        if (typeof value === "number") return LabResults._numberText(value);
        return String(value).replace(LabResults._SPACES, " ").replace(/^ +| +$/g, "");
    },

    _words: function(text) {
        return text.match(/[a-z0-9]+/g) || [];
    },

    _wordText: function(text) {
        return LabResults._words(LabResults._text(text).toLowerCase()).join(" ");
    },

    _has: function(list, words) {
        return words.some(function(word) { return list.indexOf(word) !== -1; });
    },

    // Dates and status times taken out; statuses spelled one way.
    _withoutDates: function(text) {
        text = text.replace(LabResults._QNS, " qns ").replace(LabResults._SEND_OUT, " sendout ");
        return text.replace(LabResults._DATE_OR_TIME, " ").replace(LabResults._STATUS_TIME, " $1 ");
    },

    saysNoResult: function(text) {
        var cleaned = LabResults._text(text).toLowerCase();
        if (!cleaned) return false;
        cleaned = LabResults._withoutDates(cleaned);
        var quality = LabResults._has(LabResults._QUALITY_WORDS, cleaned.match(/[a-z]+/g) || []);
        if (LabResults._TITER.test(cleaned) || (!quality && LabResults._GRADE.test(cleaned))) return false;
        if (quality) cleaned = cleaned.replace(new RegExp(LabResults._GRADE.source, "g"), " ");
        var words = LabResults._words(cleaned);
        if (!words.length) return true;  // only punctuation, a date or a time
        if (LabResults._NO_RESULT_PHRASES.indexOf(words.join(" ")) !== -1) return true;
        var status = LabResults._has(LabResults._STATUS_WORDS, words);
        if (!status && LabResults._has(["no", "not"], words)) {
            status = LabResults._has(LabResults._NEGATED_WHAT, words);
        }
        var known = words.every(function(word) {
            return LabResults._STATUS_WORDS.indexOf(word) !== -1 || LabResults._STATUS_FILLER.indexOf(word) !== -1;
        });
        return status && known;
    },

    // Whether a procedure listing's outcome plainly states a result: a
    // measurement, a titer, a grade, or a finding such as "Negative".
    outcomeStatesResult: function(text) {
        var cleaned = LabResults._text(text).toLowerCase();
        if (!cleaned) return false;
        var measurement = new RegExp(
            "^(?:(?:result|value|level)\\s*:?\\s*)?(?:[<>]=?\\s*)?-?(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?"
            + "(?:\\s*" + LabResults._UNIT_TOKEN + ")?$");
        if (measurement.test(cleaned.replace(LabResults._FLAG_NOTE, ""))) return true;
        cleaned = LabResults._withoutDates(cleaned);
        var words = LabResults._words(cleaned);
        if (LabResults._has(LabResults._QUALITY_WORDS, words)) return false;
        if (LabResults._TITER.test(cleaned) || LabResults._has(LabResults._RESULT_WORDS, words)) return true;
        if (LabResults._has(LabResults._INTERPRETATION_WORDS, words)) return false;
        return LabResults._GRADE.test(cleaned);
    },

    // The outcome written on the procedure entry a lab test was moved from.
    procedureOutcome: function(lab) {
        var source = lab.source_procedure;
        return source && typeof source === "object" ? LabResults._text(source.outcome) : "";
    },

    // The flag as written, or "" when it is blank, a dash or a placeholder
    // such as "None". A symbol such as "*" or an arrow is a flag.
    labFlag: function(lab) {
        var flag = LabResults._text(lab.flag);
        if (!flag || LabResults._DASHES.indexOf(flag) !== -1) return "";
        return LabResults._PLACEHOLDER_FLAGS.indexOf(LabResults._wordText(flag)) !== -1 ? "" : flag;
    },

    flagKey: function(flag) {
        var shown = LabResults.labFlag({flag: flag});
        return LabResults._wordText(shown) || shown;
    },

    isFlagged: function(flag) {
        var key = LabResults.flagKey(flag);
        return !!key && LabResults._NOT_FLAGGED.indexOf(key) === -1;
    },

    // A test reported as a number: it has a range, or a unit other than a count per field.
    _measured: function(lab) {
        if (lab.reference_low != null || lab.reference_high != null) return true;
        var unit = LabResults._text(lab.unit).toLowerCase();
        return !!unit && !/hpf|lpf|field/.test(unit);
    },

    // The result text, or "" for a blank written as text: "null", "-", or
    // "None" for a test measured as a number (for microscopy it is the finding).
    _ownText: function(lab) {
        var text = LabResults._text(lab.value_text);
        var words = LabResults._wordText(text);
        if (!words) return LabResults._GRADE.test(text.toLowerCase()) ? text : "";
        if (LabResults._BLANK_TEXTS.indexOf(words) !== -1) return "";
        if ((words === "none" || words === "nil") && LabResults._measured(lab)) return "";
        return text;
    },

    // A value, a flag, or text that states a result; a procedure outcome
    // counts when it plainly states one, unless includeOutcome is false.
    hasResult: function(lab, includeOutcome) {
        if (lab.value != null || LabResults.labFlag(lab)) return true;
        var text = LabResults._ownText(lab);
        if (text && !LabResults.saysNoResult(text)) return true;
        return includeOutcome !== false && LabResults.outcomeStatesResult(LabResults.procedureOutcome(lab));
    },

    _unitSpelling: function(unit) {
        return LabResults._text(unit).toLowerCase().replace(/\s+/g, "").replace(/[µμ]/g, "u").replace(/mcg/g, "ug");
    },

    // Text with its unit, unless the text already writes it, in any spelling.
    _withUnit: function(text, unit) {
        if (!unit) return text;
        var lowered = text.toLowerCase();
        if (new RegExp("\\d\\s*" + LabResults._UNIT_TOKEN + "(?![a-z0-9])").test(lowered)) return text;
        var escaped = LabResults._unitSpelling(unit).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        return new RegExp("(?<![a-z])" + escaped + "(?![a-z])").test(LabResults._unitSpelling(lowered)) ? text : text + " " + unit;
    },

    _numbers: function(text) {
        var found = [], match, pattern = new RegExp(LabResults._NUMBER, "g");
        while ((match = pattern.exec(text)) !== null) {
            found.push(LabResults._numberText(match[2].replace(/,/g, "")));
        }
        return found;
    },

    _resultKey: function(text, unit) {
        var key = LabResults._text(text).toLowerCase();
        var u = LabResults._text(unit).toLowerCase();
        if (u && key.slice(-u.length) === u && !/[a-z]$/.test(key.slice(0, key.length - u.length))) {
            key = key.slice(0, key.length - u.length).replace(/^ +| +$/g, "");
        }
        var match = new RegExp("^" + LabResults._NUMBER + "\\s*" + LabResults._UNIT_TOKEN + "?$").exec(key);
        return match ? (match[1] || "") + LabResults._numberText(match[2].replace(/,/g, "")) : key;
    },

    // What the record says the result is. Text printed beside a number
    // ("<0.01", "Reactive") is kept with it.
    resultText: function(lab, withUnit) {
        var unit = LabResults._text(lab.unit);
        var shownUnit = withUnit ? unit : "";
        var text = LabResults._ownText(lab);
        if (lab.value != null) {
            var number = LabResults._numberText(lab.value);
            if (!text || LabResults._resultKey(text, unit) === number) return LabResults._withUnit(number, shownUnit);
            if (LabResults._numbers(text).indexOf(number) !== -1) return LabResults._withUnit(text, shownUnit);
            return LabResults._withUnit(number, shownUnit) + " (" + text + ")";
        }
        if (text) return LabResults._withUnit(text, shownUnit);
        var outcome = LabResults.procedureOutcome(lab);
        if (LabResults.labFlag(lab) && !LabResults.outcomeStatesResult(outcome)) return LabResults.FLAG_ONLY;
        if (outcome) return outcome + " (listed with procedures)";
        return LabResults.NO_RESULT;
    },

    // One key for a test however it is written: its LOINC code when it has
    // one ("HbA1c" and "Hemoglobin A1c"), else its name without spaces or
    // punctuation ("Vitamin B-12" and "Vitamin B12").
    testKey: function(lab) {
        var code = LabResults._text(lab.loinc_code);
        if (code) return "loinc:" + code;
        return LabResults._text(lab.name || lab.test_name).toLowerCase().replace(/[^a-z0-9]/g, "");
    },

    // Entries sorted newest first; the newest with a result, else the newest.
    // On one day an entry's own result comes before one listed with
    // procedures, and a flagged one before an unflagged one.
    newestWithResult: function(entries) {
        var best = null, bestRank = -1;
        for (var i = 0; i < entries.length; i++) {
            var lab = entries[i];
            if (!LabResults.hasResult(lab)) continue;
            if (best && (lab.test_date || "") !== (best.test_date || "")) break;
            var rank = (LabResults.hasResult(lab, false) ? 2 : 0) + (LabResults.isFlagged(LabResults.labFlag(lab)) ? 1 : 0);
            if (rank > bestRank) { best = lab; bestRank = rank; }
        }
        return best || (entries.length ? entries[0] : null);
    },

    // The value when nothing printed beside it qualifies it ("<0.01"), else null.
    trendNumber: function(lab) {
        if (!lab || lab.value == null) return null;
        var text = LabResults._ownText(lab);
        if (text && LabResults._resultKey(text, lab.unit) !== LabResults._numberText(lab.value)) return null;
        var number = Number(String(lab.value).replace(/,/g, ""));
        return isFinite(number) ? number : null;
    },

    unitKey: function(lab) {
        return LabResults._text(lab && lab.unit).toLowerCase().replace(/\s+/g, "").replace(/[µμ]/g, "u");
    },

    sameUnit: function(a, b) {
        return LabResults.unitKey(a) === LabResults.unitKey(b);
    },

    // Two results a trend can compare: plain numbers, one unit, two days.
    comparable: function(a, b) {
        return !!a && !!b && LabResults.trendNumber(a) != null && LabResults.trendNumber(b) != null
            && LabResults.sameUnit(a, b) && !!a.test_date && !!b.test_date && a.test_date !== b.test_date;
    },

    // A missing flag is never shown as "Normal": the record did not say so.
    flagText: function(flag, hasResult) {
        var shown = LabResults.labFlag({flag: flag}), key = LabResults.flagKey(flag);
        if (!shown) return hasResult ? "Not flagged" : "";
        if (LabResults._HIGH_FLAGS.indexOf(key) !== -1) return "HIGH";
        if (LabResults._LOW_FLAGS.indexOf(key) !== -1) return "LOW";
        if (LabResults._NORMAL_LABELS.indexOf(key) !== -1) return "Normal";
        return shown;
    },

    // "Not flagged" only for an entry's own result: an outcome copied from a
    // procedure list never carried a flag, so no claim is made about one.
    badgeText: function(lab) {
        return LabResults.flagText(lab.flag, LabResults.hasResult(lab, false));
    }
};
