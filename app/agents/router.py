"""
Router Agent - Unified intent dispatch and multi-retriever logic.
"""
import re

from app.core.config import LLM_CHAT_TEMPERATURE
from app.core.logger import get_logger
from app.llm.client import ask_llm
from app.retrievers.sql_retriever import handle_sql
from app.retrievers.vector_retriever import handle_rag, has_relevant_documentation

logger = get_logger("router")


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE) is not None

# Heuristics for reliability
FORCE_RAG_WORDS = [
    "manual", "documentation", "document", "troubleshoot", "troubleshooting",
    "firmware", "ota", "wifi", "router", "gateway", "reset", "recalibrate",
    "calibration", "flashing", "blink", "blinking", "red light", "green light",
    "error code", "e-404", "sleep mode", "companion app",
    "escalate", "escalated", "escalation", "clinical staff", "technical staff",
    "privacy", "security", "policy", "procedure", "handoff",
    "blood pressure review", "sugar level review", "sleep quality review",
    "activity review", "step count review", "combined metric review",
    "data freshness", "stale timestamp", "daily wellness review",
    "shift handoff", "medication intake documentation", "fall risk review",
    "reduced mobility follow-up", "hydration and nutrition", "missing health readings",
    "duplicate readings", "conflicting readings", "manual entry", "device reading",
    "safe language", "safe health summary", "traceability",
]
FORCE_RAG_UNAMBIGUOUS_WORDS = [
    "manual", "documentation", "document", "troubleshoot", "troubleshooting",
    "firmware", "ota", "wifi", "router", "gateway", "reset", "recalibrate",
    "calibration", "flashing", "blink", "blinking", "red light", "green light",
    "error code", "e-404", "sleep mode", "companion app",
    "privacy", "security", "policy", "procedure", "handoff",
    "blood pressure review", "sugar level review", "sleep quality review",
    "activity review", "step count review", "combined metric review",
    "data freshness", "stale timestamp", "daily wellness review",
    "shift handoff", "medication intake documentation", "fall risk review",
    "reduced mobility follow-up", "hydration and nutrition", "missing health readings",
    "duplicate readings", "conflicting readings", "manual entry", "device reading",
    "safe language", "safe health summary", "traceability",
]
FORCE_SQL_WORDS = [
    "resident", "residents", "patient", "patients", "residence", "age", "ages", "flat", "flats",
    "room", "rooms", "bp", "sugar", "step", "steps", "sleep", "slept", "medical", "intake",
    "prescribed", "prescription", "prescriptions", "treatment", "medication", "medications",
    "hypertension", "diabetes", "pre-diabetes", "prediabetes", "arthritis", "asthma",
    "cardiovascular", "cardiac", "osteoporosis", "thyroid", "surgery", "post-surgery",
    "mobility", "chronic", "metformin", "amlodipine", "paracetamol", "salbutamol",
    "atorvastatin", "aspirin", "calcium", "vitamin", "telmisartan", "levothyroxine",
    "multivitamin",
    "metric", "report", "analysis", "score", "scores", "glucose", "systolic", "diastolic",
    "low", "high", "avg", "average", "sum", "count", "history", "histories",
    "record", "records", "detail", "details", "info", "information", "profile", "profiles",
    "older", "younger", "oldest", "eldest", "youngest", "longest", "shortest",
    "care", "priority", "prioritize", "risk", "risks", "critical", "attention",
    "healthy", "healthier", "healthy", "healthiest", "unhealthy", "unhealthier", "unhealthiest", "stable", "unstable",
    "vital", "vitals", "who is", "signal", "uptime",
    "cpu", "processor", "load", "temperature", "humidity", "pressure", "voltage", "current",
    "power", "energy", "device", "devices", "board", "boards", "telemetry", "device status",
]
FORCE_SQL_PHRASES = [
    "more than", "less than", "higher than", "lower than", "greater than",
    "fewer than", "above", "below", "over", "under", "at least", "at most",
    "more care", "most care", "less care", "least care", "needs care", "need care",
    "more acre", "most acre", "less acre", "least acre",
    "requires care", "require care", "requires more care", "requires less care",
    "requires more acre", "requires less acre",
    "highest care", "highest priority", "lowest care", "lowest priority",
    "care priority", "overall health", "health metrics", "health risk",
    "risk score", "needs attention", "need attention", "vital signs",
    "most healthy", "healthiest resident", "not healthy", "least healthy",
    "unhealthy resident", "unhealthiest resident", "most unhealthy", "best health", "worst health",
    "poorest health", "poor health", "most stable", "least stable",
    "lowest risk", "highest risk", "most at risk",
]
FORCE_CHAT_EXACT = {"hi", "hello", "hey", "help", "thanks", "thank you", "bye"}
FORCE_CHAT_PHRASES = ["what are you", "previous chat", "chat history", "greet yourself"]
FORCE_CHAT_PREFIXES = [
    "what is", "what are", "explain", "define", "meaning of",
    "how does", "how do", "why does", "why is",
]
SQL_LOOKUP_PHRASES = [
    "details of", "detail of", "information on", "information about",
    "tell me about", "show me details of", "give the details of",
]
AGE_LOOKUP_RE = re.compile(
    r"\b(?:(?:h?ow)\s+old\s+is|(?:what\s+is\s+)?(?:the\s+)?age\s+of)\s+"
    r"(?:resident\s+|patient\s+)?[a-z]+(?:\s+[a-z]+){0,2}\b",
    re.IGNORECASE,
)
ROOM_LOOKUP_RE = re.compile(
    r"\b(?:(?:where\s+(?:does|is))\s+(?:resident\s+|patient\s+)?"
    r"[a-z]+(?:\s+[a-z]+){0,2}\s+(?:stay|staying|live|living|assigned)|"
    r"(?:what|which)\s+(?:flat|room)(?:\s+(?:number|no))?\s+(?:is|does)\s+"
    r"(?:resident\s+|patient\s+)?[a-z]+(?:\s+[a-z]+){0,2}(?:\s+(?:in|have|has))?)\b",
    re.IGNORECASE,
)
DEVICE_ID_RE = re.compile(r"\bdev[1-5]\b", re.IGNORECASE)
ACKNOWLEDGEMENT_WORDS = [
    "ok", "okay", "fine", "alright", "got it", "cool", "understood",
    "thanks", "thank you", "noted", "sure", "yep", "yes",
]
GREETING_RESPONSES = {
    "hi": "Hello. Ask me anything. I can also help with residents, health metrics, and device issues.",
    "hello": "Hello. Ask me anything. I can also help with residents, health metrics, and device issues.",
    "hey": "Hello. Ask me anything. I can also help with residents, health metrics, and device issues.",
    "help": "Ask a general question, or ask about resident metrics, summaries, charts, and device troubleshooting.",
}

_NAME_LOOKUP_RE = re.compile(r"\b[a-z]+(?:\s+[a-z]+){1,2}\b")

_GENERIC_EXPLANATION_SQL_BLOCKERS = [
    "community", "database", "record", "records", "resident record", "resident records",
    "resident", "residents", "patient", "patients", "age", "ages", "flat", "flats", "room", "rooms",
    "history", "histories", "intake", "prescribed", "prescription", "prescriptions",
    "treatment", "medication", "medications",
    "report", "metric", "average", "avg", "count", "sum", "highest", "lowest",
    "best", "worst", "most", "least", "top", "bottom", "chart", "graph",
    "bp", "blood pressure", "sugar", "glucose", "steps", "step", "sleep", "slept",
    "score", "scores", "quality", "duration", "systolic", "diastolic",
    "oldest", "eldest", "youngest", "longest", "shortest",
    "care", "priority", "prioritize", "risk", "risks", "health metrics",
    "critical", "attention", "healthy", "healthiest", "unhealthy", "unhealthiest",
    "stable", "unstable", "vital", "vitals", "vital signs",
    "compare", "comparison", "details", "detail", "record", "records",
    "more than", "less than", "higher than", "lower than",
]
_GENERAL_CHAT_PROMPT = (
    "You are KuboCare, a chat assistant for resident health metrics, activity insights, and care-related information. "
    "If asked who you are, answer exactly: I am KuboCare analyst, a chat assistant for resident health metrics, activity insights, and care-related information. "
    "Answer general questions naturally and clearly with depth and context. You can help with explanations, writing, planning, "
    "summaries, and general knowledge. "
    "Use recent conversation only to resolve pronouns or follow-ups; do not invent resident database values. "
    "\n"
    "For general clinical education questions about medicines, conditions, symptoms, or health concepts, "
    "provide comprehensive, natural answers using your medical knowledge. Be clear and informative. "
    "Include: what the condition/medicine is, common signs/uses, how it's typically managed, and when professional help is needed. "
    "You can use 3-6 sentences or more for complex topics. "
    "\n"
    "CRITICAL SAFETY RULES:\n"
    "- Do NOT diagnose, prescribe, or change doses.\n"
    "- Do NOT provide personalized medical advice for any specific person.\n"
    "- Do NOT claim this replaces professional medical judgment.\n"
    "- Always remind users to consult their clinician for personal health decisions.\n"
    "- For medicines: mention common uses, key safety notes, and the need to follow prescriber's instructions.\n"
    "- For conditions: explain what it is, general management principles, and importance of professional evaluation.\n"
    "\n"
    "If the user asks for resident-specific data, say that should be checked from the resident records. "
    "If you are unsure or the question needs current facts, say what you know and suggest checking an up-to-date source."
)
_GENERAL_CLINICAL_TERMS = [
    # Common medications
    "amlodipine", "aspirin", "atorvastatin", "calcium", "levothyroxine",
    "metformin", "multivitamin", "paracetamol", "salbutamol", "telmisartan",
    "antibiotic", "inhaler", "insulin", "medicine", "medication", "tablet",
    # Common conditions and diseases
    "arthritis", "asthma", "blood pressure", "bp", "cardiac", "cardiovascular",
    "cholesterol", "diabetes", "fever", "glucose", "heart", "hypertension",
    "osteoporosis", "pre-diabetes", "prediabetes", "stroke", "sugar",
    "thyroid", "vital", "vitals",
    # Additional common medical terms and conditions
    "acid reflux", "acid reflux disease", "gerd", "heartburn", "indigestion",
    "allergies", "allergy", "allergic", "hay fever", "rhinitis",
    "anemia", "iron deficiency", "pernicious",
    "anxiety", "depression", "dementia", "alzheimer", "cognitive",
    "infection", "cold", "flu", "covid", "pneumonia", "bronchitis",
    "migraine", "headache", "migraine headache",
    "kidney", "renal", "liver", "cirrhosis", "hepatitis",
    "cancer", "tumor", "leukemia",
    "osteoarthritis", "rheumatoid arthritis", "joint",
    "ulcer", "gastric", "peptic",
    "eczema", "psoriasis", "dermatitis",
    "copd", "emphysema", "chronic obstructive",
    "syndrome", "syndrome x", "metabolic",
    "obesity", "overweight", "bmi",
    "sleep apnea", "apnea",
    "contraception", "birth control",
    "hormone", "thyroid", "hormone replacement",
    "anticoagulant", "anticoagulation", "blood thinner",
    "vaccine", "vaccination", "immunization",
    "side effect", "side effects", "adverse",
    "symptom", "symptoms", "sign", "signs",
    "diagnosis", "diagnostic",
    "treatment", "therapy", "therapeutic",
    "surgery", "surgical",
    "physical therapy", "rehabilitation",
]
_GENERAL_CLINICAL_DATA_BLOCKERS = [
    "resident", "residents", "patient", "patients", "community", "database",
    "record", "records", "room", "flat", "age", "chart", "graph", "average",
    "avg", "highest", "lowest", "best", "worst", "top", "bottom", "list",
    "show", "give", "which", "who has", "who takes", "who is taking",
]
_GENERAL_CLINICAL_PREFIXES = FORCE_CHAT_PREFIXES + [
    "how is", "how are", "how can", "how should", "how to",
    "side effects", "uses of", "use of", "benefits of", "risks of",
    "common side effects", "explain side effects",
]
_GENERAL_CLINICAL_SUBJECT_PREFIXES = [
    "is", "are", "can", "does", "do", "should",
]
_GENERAL_CLINICAL_TOPIC_NOUNS = [
    "benefit", "benefits", "cause", "causes", "diagnosis", "management",
    "prevention", "risk", "risks", "sign", "signs", "side effect",
    "side effects", "symptom", "symptoms", "therapy", "treatment",
    "treatments", "use", "uses",
]
_POSSESSIVE_NAME_RE = re.compile(r"\b[a-z]+(?:\s+[a-z]+){0,2}'s\b", re.IGNORECASE)
_DOC_ROUTING_DISTANCE = 0.93
_METRIC_CONCEPT_RE = re.compile(
    r"^\s*(?:what\s+(?:is|are|does)|explain|define|meaning\s+of)\s+"
    r"(?:the\s+)?(?:sleep\s+quality\s+score|sleep\s+score|blood\s+pressure|bp|"
    r"sugar\s+level|glucose\s+level|step\s+count|activity\s+steps|sleep\s+duration)"
    r"(?:\s+mean)?\??\s*$",
    re.IGNORECASE,
)
_METRIC_GUIDANCE_TRIGGERS = [
    "ideal", "good", "normal", "healthy", "acceptable", "target",
    "range", "baseline", "threshold", "concerning", "concern",
    "low", "high", "poor", "reduced", "recommended", "should be",
    "qualifies", "count as", "counts as", "best", "worst", "borderline", "elevated", "review signal",
]
_METRIC_GUIDANCE_DATA_BLOCKERS = [
    "resident", "residents", "patient", "patients", "community", "database",
    "record", "records", "list", "show", "give", "which resident", "who has",
    "average", "avg", "highest", "lowest", "top", "bottom", "compare",
    "comparison", "chart", "graph",
]
_KUBOCARE_PRODUCT_TERMS = [
    "company", "product", "device", "devices", "wearable", "wearables",
    "non-wearable", "camera", "cameras",
    "radar", "frequency", "ghz", "mmwave", "millimeter", "fall detection",
    "fall", "privacy", "safety", "ambient", "sensor", "sensors",
]

_METRIC_BASELINES = {
    "sleep_score": (
        "Sleep quality score",
        [
            "80-100: good/ideal",
            "60-79: acceptable, but needs to improve if below 80",
            "50-59: borderline; review with sleep duration and other metrics",
            "below 50: low score and concerning, needs attention",
        ],
        "The sleep quality score is a composite metric influenced by duration, interruptions, restlessness, and consistency. Use it as a screening signal, then confirm with sleep duration and activity levels.",
    ),
    "sleep_duration": (
        "Sleep duration",
        [
            "7-9 hours is a common adult target; many older adults do well around 7-8 hours",
            "6-7 hours: watch trend and context",
            "below 6 hours: reduced in this project",
            "below 5 hours: short/concerning, needs care and attention.",
        ],
        "Read sleep duration together with sleep quality score, activity, and recent health readings.",
    ),
    "bp": (
        "Blood pressure",
        [
            "around 120/80 mmHg: normal reference point, optimal for many adults",
            "130-139 systolic or 85-89 diastolic: borderline, watch trends",
            "140+ systolic or 90+ diastolic: elevated/high, needs care",
            "160+ systolic or 100+ diastolic: very high, need to be monitored",
        ],
        "BP targets can differ by person and care plan, so use this as a review threshold, not a diagnosis.",
    ),
    "sugar": (
        "Sugar/glucose level",
        [
            "fasting below 100: normal reference point",
            "100-125: borderline/prediabetes range",
            "126+ fasting or 140+ in this project: high review signal",
            "180+: very high, needs attention and monitoring",
        ],
        "Interpret sugar with meal timing, diabetes status, medication, and the resident's care plan.",
    ),
    "steps": (
        "Step count/activity",
        [
            "there is no single ideal step count for every older adult",
            "3500+ steps: not flagged as low, generally more active",
            "2500-3499 steps: reduced activity signal",
            "below 2500 steps: low activity signal",
        ],
        "Confirm device wear/sync before treating a low step count as a care issue.",
    ),
}

_CARE_GUIDANCE_TRIGGERS = [
    "what is", "what does", "what do", "explain", "define", "meaning of",
    "how is", "how are", "calculated", "calculate", "computed", "compute",
    "why score", "score mean", "score means", "priority mean", "priority means",
]
_CARE_GUIDANCE_DATA_BLOCKERS = [
    "who", "which resident", "which patient", "list", "show", "give details",
    "details of", "information on", "information about", "compare", "older", "younger",
    "oldest", "youngest", "higher", "lower", "highest", "lowest", "most care",
    "more care", "least care", "less care", "needs care", "need care",
    "require care", "requires care",
]
_CARE_SCORE_RULES = [
    "Age: 75+ adds 1 point; 85+ adds 2 points.",
    "BP: 130/85+ adds 1; 140/90+ adds 2; 160/100+ adds 3.",
    "Sugar/glucose: 125+ adds 1; 140+ adds 2; 180+ adds 3.",
    "Sleep score: below 60 adds 1; below 50 adds 2.",
    "Sleep duration: below 6 hours adds 1; below 5 hours adds 2.",
    "Steps: below 3500 adds 1; below 2500 adds 2.",
    "Medical history keywords such as diabetes, hypertension, cardiac/cardiovascular, post-surgery, asthma, or osteoporosis add 1 point each.",
]
_CLINICAL_CONCEPT_ANSWERS = [
    (
        ["bp", "blood pressure"],
        "BP means blood pressure. It is the pressure of blood pushing against artery walls, usually written as systolic/diastolic, for example 120/80 mmHg. It is commonly measured with a BP cuff or validated monitor. High or very low readings should be interpreted with the resident's care plan and clinician guidance.",
    ),
    (
        ["sugar", "glucose", "sugar level", "glucose level"],
        "Sugar level means blood glucose, the amount of glucose in the blood. It is usually measured with a glucometer, lab test, or recorded clinical reading. The result depends on meal timing, diabetes status, medicines, and the resident's care plan.",
    ),
    (
        ["diabetes"],
        "Diabetes is a condition where blood glucose stays too high because the body does not make enough insulin or cannot use insulin well. It is managed with a clinician-directed plan that may include diet, activity, monitoring, and medication. This is general information, not a diagnosis.",
    ),
    (
        ["hypertension"],
        "Hypertension means persistently high blood pressure. It can increase the risk of heart, kidney, brain, and blood vessel problems over time. Management should follow a clinician's plan and recorded readings should be reviewed in context.",
    ),
    (
        ["steps", "step count", "activity steps"],
        "Step count is an activity metric that estimates how many steps a person took, usually from a wearable or motion-tracking device. In KuboCare it is used as a mobility/activity signal, but a low value can also mean the device was not worn or did not sync.",
    ),
]


def _looks_like_resident_lookup(query: str) -> bool:
    if any(_contains_term(query, word) for word in FORCE_RAG_WORDS):
        return False
    if AGE_LOOKUP_RE.search(query) or ROOM_LOOKUP_RE.search(query):
        return True
    if not any(_contains_term(query, phrase) for phrase in SQL_LOOKUP_PHRASES):
        return False
    return _NAME_LOOKUP_RE.search(query) is not None


def _looks_like_generic_explanatory_query(query: str) -> bool:
    q = query.lower().strip()
    if not any(q.startswith(prefix) for prefix in FORCE_CHAT_PREFIXES):
        return False
    if _looks_like_resident_lookup(q):
        return False
    for hint in _GENERIC_EXPLANATION_SQL_BLOCKERS:
        if " " in hint:
            if hint in q:
                return False
        elif _contains_term(q, hint):
            return False
    return True


def _looks_like_general_clinical_education_query(query: str) -> bool:
    q = query.lower().strip()
    if not _has_general_clinical_term(q):
        return False
    if _looks_like_resident_lookup(q) or _POSSESSIVE_NAME_RE.search(q) or _has_named_metric_hint(q):
        return False
    for blocker in _GENERAL_CLINICAL_DATA_BLOCKERS:
        if " " in blocker:
            if blocker in q:
                return False
        elif _contains_term(q, blocker):
            return False
    return (
        any(q.startswith(prefix) for prefix in _GENERAL_CLINICAL_PREFIXES)
        or _looks_like_clinical_subject_question(q)
        or _looks_like_clinical_topic_phrase(q)
        or q.startswith(("when should ", "when to "))
    )


def _has_general_clinical_term(query: str) -> bool:
    return any(_contains_term(query, term) for term in _GENERAL_CLINICAL_TERMS)


def _starts_with_general_clinical_term(text: str) -> bool:
    return any(
        re.search(rf"^{re.escape(term)}\b", text, re.IGNORECASE)
        for term in sorted(_GENERAL_CLINICAL_TERMS, key=len, reverse=True)
    )


def _looks_like_clinical_subject_question(query: str) -> bool:
    for prefix in _GENERAL_CLINICAL_SUBJECT_PREFIXES:
        prefix_with_space = f"{prefix} "
        if query.startswith(prefix_with_space):
            return _starts_with_general_clinical_term(query[len(prefix_with_space):].strip())
    return False


def _looks_like_clinical_topic_phrase(query: str) -> bool:
    if not any(_contains_term(query, noun) for noun in _GENERAL_CLINICAL_TOPIC_NOUNS):
        return False

    if _starts_with_general_clinical_term(query):
        return True

    topic_pattern = "|".join(
        re.escape(noun)
        for noun in sorted(_GENERAL_CLINICAL_TOPIC_NOUNS, key=len, reverse=True)
    )
    return re.search(rf"\b(?:{topic_pattern})\s+(?:of|for|from|with|in)\b", query, re.IGNORECASE) is not None


def _looks_like_clear_sql_query(query: str) -> bool:
    q = query.lower().strip()
    if DEVICE_ID_RE.search(q):
        return True
    if AGE_LOOKUP_RE.search(q) or ROOM_LOOKUP_RE.search(q):
        return True
    if any(phrase in q for phrase in FORCE_SQL_PHRASES):
        return True
    if _looks_like_resident_lookup(q):
        return True
    return any(_contains_term(q, word) for word in FORCE_SQL_WORDS)


def _looks_like_unambiguous_documentation_query(query: str) -> bool:
    return any(_contains_term(query, word) for word in FORCE_RAG_UNAMBIGUOUS_WORDS)


def _looks_like_metric_concept_query(query: str) -> bool:
    return _METRIC_CONCEPT_RE.search(query) is not None


def _looks_like_kubocare_product_documentation_query(query: str) -> bool:
    q = query.lower().strip()
    if DEVICE_ID_RE.search(q):
        return False

    mentions_kubocare = "kubocare" in q or "kubo care" in q
    mentions_product_device = any(_contains_term(q, term) for term in ["device", "devices", "sensor", "sensors"])
    asks_product_detail = any(term in q for term in _KUBOCARE_PRODUCT_TERMS)
    asks_company_overview = re.search(
        r"\b(?:what\s+(?:is|does)|who\s+is|tell\s+me\s+about|explain)\b.*\b(?:kubocare|kubo\s+care)\b",
        q,
    ) is not None

    if mentions_kubocare and (asks_product_detail or asks_company_overview):
        return True

    # Follow-ups like "are the devices wearable?" should use product docs,
    # while telemetry questions such as "device status" stay in SQL.
    if mentions_product_device and any(term in q for term in ["wearable", "camera", "radar", "frequency", "fall detection"]):
        return True

    return False


def _metric_guidance_keys(query: str) -> list[str]:
    q = query.lower().strip()
    keys: list[str] = []
    if any(term in q for term in ["sleep quality", "sleep score", "sleep scores"]):
        keys.append("sleep_score")
    if any(term in q for term in ["sleep duration", "sleep time", "hours of sleep", "sleep hours"]):
        keys.append("sleep_duration")
    if any(_contains_term(q, term) for term in ["bp", "blood pressure"]):
        keys.append("bp")
    if any(_contains_term(q, term) for term in ["sugar", "glucose"]):
        keys.append("sugar")
    if any(term in q for term in ["step count", "steps", "activity"]):
        keys.append("steps")
    if any(term in q for term in ["all metrics", "other metrics", "health metrics", "vitals", "vital signs"]):
        keys = ["sleep_score", "sleep_duration", "bp", "sugar", "steps"]
    return list(dict.fromkeys(keys))


def _has_named_metric_hint(query: str) -> bool:
    q = query.lower().strip()
    if _POSSESSIVE_NAME_RE.search(q):
        return True
    non_name_fragments = {
        "what", "which", "who", "how", "many", "much", "is", "are", "was", "were",
        "the", "a", "an", "his", "her", "their", "current", "latest", "average",
        "avg", "mean", "good", "bad", "normal", "ideal", "high", "low",
    }

    def is_name_fragment(candidate: str) -> bool:
        return candidate not in non_name_fragments and candidate not in _METRIC_GUIDANCE_TRIGGERS

    metric_word = r"(?:sleep|bp|blood\s+pressure|sugar|glucose|steps?|step\s+count|activity)"
    named_metric_tail = (
        r"(?:current|latest|average|avg|mean)?\s*"
        r"(?:sleep\s+score|sleep\s+quality\s+score|sleep|bp|blood\s+pressure|"
        r"sugar|glucose|steps?|step\s+count|activity)"
    )
    named_match = re.search(rf"\b([a-z]+)(?:'s|s)?\s+{named_metric_tail}\b", q)
    if named_match and is_name_fragment(named_match.group(1)):
        return True
    named_match = re.search(rf"\b(?:is|are)\s+([a-z]+)\s+{metric_word}\b", q)
    if named_match and is_name_fragment(named_match.group(1)):
        return True
    named_match = re.search(rf"\b(?:for|of)\s+([a-z]+)\s+{metric_word}\b", q)
    if named_match and is_name_fragment(named_match.group(1)):
        return True
    named_match = re.search(rf"\b{metric_word}\s+(?:for|of)\s+([a-z]+(?:\s+[a-z]+){{0,2}})\b", q)
    if named_match:
        return True
    return False


def _looks_like_metric_guidance_query(query: str) -> bool:
    q = query.lower().strip()
    if not _metric_guidance_keys(q):
        return False
    if _has_named_metric_hint(q):
        return False
    for blocker in _METRIC_GUIDANCE_DATA_BLOCKERS:
        if " " in blocker:
            if blocker in q:
                return False
        elif _contains_term(q, blocker):
            return False
    return any(trigger in q for trigger in _METRIC_GUIDANCE_TRIGGERS)


def _metric_guidance_answer(query: str) -> str | None:
    if not _looks_like_metric_guidance_query(query):
        return None

    keys = _metric_guidance_keys(query)
    if not keys:
        return None

    lines = ["KuboCare metric guide:"]
    for key in keys:
        title, thresholds, note = _METRIC_BASELINES[key]
        lines.append(f"{title}:")
        for threshold in thresholds:
            lines.append(f"- {threshold}")
        lines.append(f"Note: {note}")
    lines.append("These are screening thresholds for review and prioritization, not a diagnosis or personalized medical advice.")
    return "\n".join(lines)


def _looks_like_care_guidance_query(query: str) -> bool:
    q = query.lower().strip()
    care_terms = [
        "care score", "priority score", "score in high priority", "high priority",
        "moderate priority", "routine priority", "care priority",
    ]
    has_score_number = re.search(r"\bscore\s+\d+\b", q) is not None
    has_care_term = any(term in q for term in care_terms) or has_score_number
    if not has_care_term:
        return False

    if q.startswith("why is ") and not has_score_number:
        return False

    for blocker in _CARE_GUIDANCE_DATA_BLOCKERS:
        if blocker in q and not has_score_number:
            return False

    return any(trigger in q for trigger in _CARE_GUIDANCE_TRIGGERS) or has_score_number


def _care_guidance_answer(query: str) -> str | None:
    if not _looks_like_care_guidance_query(query):
        return None

    q = query.lower().strip()
    lines = [
        "KuboCare care priority guide:",
        "Care score is a data-prioritization heuristic from recorded resident values, not a diagnosis.",
        "Higher score means more review signals are present.",
        "Priority bands:",
        "- High priority: score >= 9",
        "- Moderate priority: score 5-8",
        "- Routine priority: score 0-4",
    ]

    score_match = re.search(r"\bscore\s+(\d+)\b", q)
    if score_match:
        score = int(score_match.group(1))
        if score >= 9:
            band = "High priority"
        elif score >= 5:
            band = "Moderate priority"
        else:
            band = "Routine priority"
        lines.append(f"Score {score} falls in {band}.")
        if score >= 9:
            lines.append("For example, score 12 means several strong signals stacked together, so that resident should be reviewed before lower-priority residents.")

    lines.append("How points are added:")
    lines.extend(f"- {rule}" for rule in _CARE_SCORE_RULES)
    lines.append("Use the score to prioritize review and follow-up; clinical decisions should still follow the resident's care plan and professional judgment.")
    return "\n".join(lines)


def _clinical_concept_answer(query: str) -> str | None:
    q = query.lower().strip()
    if not any(q.startswith(prefix) for prefix in _GENERAL_CLINICAL_PREFIXES):
        return None
    if _looks_like_resident_lookup(q) or _POSSESSIVE_NAME_RE.search(q) or _has_named_metric_hint(q):
        return None
    for blocker in _GENERAL_CLINICAL_DATA_BLOCKERS:
        if " " in blocker:
            if blocker in q:
                return None
        elif _contains_term(q, blocker):
            return None
    for terms, answer in _CLINICAL_CONCEPT_ANSWERS:
        if any(_contains_term(q, term) for term in terms):
            return answer
    return None


def _format_chat_history(chat_history: list[dict] | None, limit: int = 3) -> str:
    if not chat_history:
        return ""

    recent_turns = chat_history[-limit:]
    return "\n".join(
        f"User: {turn.get('user', '')}\nAssistant: {turn.get('ai', '')}"
        for turn in recent_turns
    ).strip()


def classify_intent(query: str) -> str:
    q = query.lower().strip()

    if q in FORCE_CHAT_EXACT or any(_contains_term(q, phrase) for phrase in FORCE_CHAT_PHRASES) or q in ACKNOWLEDGEMENT_WORDS:
        return "CHAT"

    # Hard documentation phrases win first so "sleep mode" is not treated as a
    # resident sleep metric.
    if _looks_like_unambiguous_documentation_query(q):
        return "RAG"

    if _looks_like_kubocare_product_documentation_query(q):
        return "RAG"

    if DEVICE_ID_RE.search(q) or _has_named_metric_hint(q):
        return "SQL"

    if _looks_like_general_clinical_education_query(q):
        return "CHAT"

    if _looks_like_metric_guidance_query(q):
        return "CHAT"

    if _looks_like_care_guidance_query(q):
        return "CHAT"

    if _clinical_concept_answer(q):
        return "CHAT"

    if _looks_like_metric_concept_query(q):
        return "RAG"

    if _looks_like_generic_explanatory_query(q):
        return "CHAT"

    # Data questions win before generic "what is / who is" handling. This keeps
    # resident follow-ups such as "what are their ages?" in SQL.
    if _looks_like_clear_sql_query(q):
        return "SQL"

    if any(_contains_term(q, word) for word in FORCE_RAG_WORDS):
        return "RAG"

    if has_relevant_documentation(query, max_distance=_DOC_ROUTING_DISTANCE):
        return "RAG"

    if any(q.startswith(prefix) for prefix in FORCE_CHAT_PREFIXES):
        return "CHAT"

    # ChatGPT-like behavior: SQL and RAG are specialized routes; everything
    # else should remain a normal assistant conversation instead of failing.
    return "CHAT"


def route_query(
    query: str,
    original_query: str | None = None,
    chat_history: list[dict] | None = None,
    *,
    community_id: int,
) -> dict:
    raw_query = (original_query or query).strip()
    q_lower = raw_query.lower().strip()
    guidance_answer = _metric_guidance_answer(raw_query)
    if guidance_answer:
        return {
            "query": query,
            "plan": {"macro": "metric_guidance"},
            "answer": guidance_answer,
        }
    care_guidance_answer = _care_guidance_answer(raw_query)
    if care_guidance_answer:
        return {
            "query": query,
            "plan": {"macro": "care_score_guidance"},
            "answer": care_guidance_answer,
        }
    # Medical concept questions now route to LLM (CHAT) instead of hardcoded answers
    # for more comprehensive, ChatGPT-like responses with external medical knowledge

    intent = classify_intent(query)

    if intent == "CHAT":
        if q_lower in ACKNOWLEDGEMENT_WORDS:
            return {"query": query, "answer": "It was my pleasure to help. Please feel free to ask anything else."}
        if q_lower in GREETING_RESPONSES:
            return {"query": query, "answer": GREETING_RESPONSES[q_lower]}
        try:
            history_text = _format_chat_history(chat_history)
            chat_input = raw_query
            if history_text:
                chat_input = f"Recent Conversation:\n{history_text}\n\nCurrent User Message: {raw_query}"

            answer = ask_llm(
                chat_input,
                system_prompt=_GENERAL_CHAT_PROMPT,
                num_predict=220,
                temperature=LLM_CHAT_TEMPERATURE,
            )
            return {"query": query, "answer": answer}
        except Exception as e:
            logger.error(f"Chat response failed: {e}")
            return {
                "query": query,
                "error": str(e),
                "answer": "The language model is taking too long to respond. Please try again shortly.",
            }

    if intent == "SQL":
        logger.info("Routing to SQL...")
        res = handle_sql(query, community_id=community_id)
        if "error" in res and not any(_contains_term(query.lower(), word) for word in ["iot", "signal", "uptime"]):
            res["answer"] = "I couldn't find matches in the database. Please check the name or ID."
        return res

    logger.info("Routing to RAG...")
    return handle_rag(query)
