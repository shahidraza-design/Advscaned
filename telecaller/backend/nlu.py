"""
nlu.py — the understanding layer. Pure Python, zero models, zero cost.

Four things happen on every customer turn:
  1. intent    — what did they mean? English + Hindi + Bengali + romanised Hindi,
                 scored longest-phrase-first with span masking and boundary checks
                 (so Bengali "থেকে" can never fire the "কে" intent).
  2. entities  — email (including "priya at sunrise dot edu"), phone, class range,
                 paper volume, subject, role, current process, timeline, slot.
  3. sentiment — -1.0 (angry) … +1.0 (happy), negation + intensifier aware.
  4. meta      — is it a question, how long was it, was it just an acknowledgement.

Crucially it also knows when *not* to classify: an open question like "which
classes do you handle?" is answered with "classes 6 to 10, we type in Word",
which has no intent keyword at all — that is a valid **answer**, not noise.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- vocabularies
INTENT_PHRASES: dict[str, list[str]] = {
    "affirm": [
        "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "correct", "right", "speaking",
        "this is he", "this is she", "go ahead", "tell me", "of course",
        "haan", "han", "ha ji", "ji haan", "bilkul", "theek hai", "thik hai", "ha", "hmm",
        "हाँ", "हां", "जी हाँ", "जी हां", "बिलकुल", "ठीक है", "बोलिए", "हाँ बोल रहा", "हाँ बोल रही",
        "হ্যাঁ", "হ্যা", "ঠিক আছে", "বলুন", "বলছি", "আচ্ছা",
    ],
    "deny": [
        "no", "nope", "not really", "no thanks", "nahi", "nahin", "na", "na ji",
        "नहीं", "ना", "না", "না না", "not now",
    ],
    "who": [
        "who is this", "who are you", "who is calling", "kaun", "koun", "kaun bol raha",
        "कौन बोल", "कौन है", "कोई और", "কে বলছেন", "কে আপনি",
    ],
    "what_about": [
        "what is this about", "what is this", "what do you want", "kya hai", "kis bare me",
        "kya baat", "क्या बात", "किस बारे", "क्या है", "কী নিয়ে", "কি ব্যাপার", "কী বলতে চান",
    ],
    "busy": [
        "busy", "in a meeting", "driving", "i am at work", "in class", "not a good time",
        "baad me", "abhi busy", "vyast", "व्यस्त", "बाद में", "अभी नहीं", "मीटिंग में",
        "ব্যস্ত", "এখন নয়", "মিটিং",
    ],
    "callback": [
        "call me later", "call back", "call me tomorrow", "after 5", "in the evening",
        "baad me call", "फिर कॉल", "बाद में कॉल", "कल कॉल", "पরে ফোন", "কাল ফোন", "পরে ফোন",
    ],
    "wrong_number": [
        "wrong number", "not me", "no one by that name", "galat number", "koi nahi",
        "गलत नंबर", "ভুল নম্বর", "এখানে কেউ নেই",
    ],
    "dnc": [
        "do not call", "dont call", "don t call", "remove my number", "stop calling",
        "unsubscribe", "block my number", "dnc", "mat karo", "phone mat", "do not call again",
        "नंबर हटा", "मत करो", "फोन मत", "दोबारा मत", "फोन करना बंद",
        "ফোন করবেন না", "নম্বর সরিয়ে", "আর ফোন করবেন না", "ফোন করবেন না",
    ],
    "not_interested": [
        "not interested", "no interest", "we dont need", "we don t need", "dont need",
        "not required", "nahi chahiye", "zarurat nahi", "no requirement",
        "दिलचस्पी नहीं", "ज़रूरत नहीं", "जरूरत नहीं", "नहीं चाहिए", "इंटरेस्ट नहीं",
        "আগ্রহ নেই", "দরকার নেই", "চাই না",
    ],
    "price_objection": [
        "expensive", "too costly", "costly", "too much money", "too pricey", "out of budget",
        "mehnga", "bahut mehnga", "zyada paisa", "महंगा", "बहुत ज़्यादा", "ज़्यादा पैसा",
        "बजट नहीं", "দামি", "বেশি দাম", "খুব বেশি", "বাজেট নেই",
    ],
    "price": [
        "price", "pricing", "cost", "how much", "charges", "fees", "fee", "rate",
        "how much does it cost", "what is the price", "kitna", "kitne ka", "paisa", "kharche",
        "कितना", "कितने का", "कितना पैसा", "कीमत", "दाम", "खर्च", "शुल्क", "कितना लगेगा",
        "কত টাকা", "দাম", "খরচ", "রেট",
    ],
    "have_vendor": [
        "already have", "we use", "we already", "existing software", "we have a system",
        "our own", "own system", "in house", "in-house", "already using",
        "pehle se", "apna system", "already using", "पहले से", "हमारे पास", "अपना सिस्टम",
        "আগেই আছে", "আমাদের আছে", "নিজেদের",
    ],
    "send_info": [
        "send me", "send details", "email me", "whatsapp me", "brochure", "pdf",
        "share details", "mail karo", "bhej do", "भेज दीजिए", "ईमेल कर", "डिटेल भेज", "भेज दें",
        "পাঠিয়ে দিন", "মেইল করুন", "ডিটেইল পাঠান",
    ],
    "think": [
        "think about it", "need to think", "let me think", "discuss with", "check with",
        "sochna", "soch ke", "baad me batata", "सोचना", "सोच कर", "सोच के बताता",
        "ভেবে", "বুঝে নেব", "ভেবে দেখি",
    ],
    "human": [
        "talk to a human", "real person", "manager", "supervisor", "your senior",
        "talk to someone", "insan", "manager se", "इंसान", "मैनेजर", "सीनियर",
        "সত্যিকারের লোক", "ম্যানেজার",
    ],
    "audio_check": [
        "can you hear me", "are you there", "hello are you there", "am i audible",
        "sun rahe ho", "सुन रहे हो", "आवाज़ आ रही है", "শুনতে পাচ্ছেন", "শুনছেন",
    ],
    "repeat": [
        "repeat", "say again", "come again", "didnt get", "didn t catch", "pardon",
        "kya kaha", "samajh nahi", "फिर बोलिए", "समझ नहीं", "क्या कहा", "दोहराइए",
        "আবার বলুন", "বুঝলাম না",
    ],
    "demo": [
        "demo", "trial", "pilot", "schedule", "book a", "show me", "dikhao", "dikha do",
        "zoom", "google meet", "डेमो", "दिखा दीजिए", "ডেমো", "দেখান",
    ],
    "features": [
        "how does it work", "how it works", "features", "kaise kaam", "does it support",
        "can it", "diagram", "equation", "formula", "hindi", "bengali", "word file",
        "pdf", "ocr", "scan", "कैसे काम", "क्या ये", "ডায়াগ্রাম", "কীভাবে কাজ", "কী কী আছে",
    ],
    "interest": [
        "interested", "tell me more", "sounds good", "sounds useful", "go on",
        "achha", "batao", "aur batao", "अच्छा", "बताइए", "आगे बताइए", "दिलचस्पी है",
        "ভালো লাগছে", "বলুন আর",
    ],
    "greeting": [
        "hello", "hi", "hey", "namaste", "namaskar", "good morning", "good evening",
        "नमस्ते", "नमस्कार", "নমস্কার", "হ্যালো",
    ],
    "thanks": ["thank you", "thanks", "dhanyavad", "shukriya", "धन्यवाद", "शुक्रिया",
               "ধন্যবাদ"],
    "neg_sentiment": [
        "annoying", "irritating", "waste of time", "bakwas", "faltu", "stop it",
        "why are you calling", "बकवास", "फ़ालतू", "फालतू", "परेशान", "मत करो",
        "বাজে", "বিরক্ত", "ফালতু",
    ],
}

# Short acknowledgements must never outvote a real signal ("I'm busy" ≠ "yes").
WEAK_PHRASES = {
    "yes", "ok", "okay", "sure", "right", "correct", "ha", "hmm", "hi", "hey", "tell me",
    "haan", "han", "na", "no", "nahi", "हाँ", "हां", "ना", "নমস্কার", "হ্যালো",
    "ঠিক আছে", "আচ্ছা", "বলুন", "বলছি", "अच्छा", "achha", "अच्छा", "नमस्ते", "নমস্কার",
    "hello", "greeting", "thank you", "thanks", "ধন্যবাদ", "धन्यवाद",
}

NEGATIVE_WORDS = {
    "no", "not", "dont", "never", "cant", "cannot", "stop", "bad", "waste", "annoying",
    "irritating", "expensive", "problem", "issue", "worst", "angry", "frustrated", "busy",
    "bakwas", "faltu", "nahi", "mat", "pareshan", "गलत", "महंगा", "परेशान", "बकवास",
    "समस्या", "खराप", "খারাপ", "বিরক্ত", "দামি", "ব্যস্ত",
}
POSITIVE_WORDS = {
    "good", "great", "nice", "useful", "helpful", "interesting", "interested", "perfect",
    "excellent", "thanks", "thank", "yes", "sure", "ok", "okay", "achha", "badhiya",
    "बढ़िया", "अच्छा", "धन्यवाद", "ভালো", "দারুণ", "ধন্যবাদ", "ঠিক",
}
INTENSIFIERS = {"very", "really", "too", "so", "extremely", "bahut", "bohot", "बहुत",
                "खूप", "খুব"}

ROLE_WORDS = {
    "principal": "Principal", "प्रिंसिपल": "Principal", "প্রিন্সিপাল": "Principal",
    "vice principal": "Vice Principal", "director": "Director", "डायरेक्टर": "Director",
    "owner": "Owner", "trustee": "Trustee", "headmaster": "Headmaster",
    "headmistress": "Headmistress", "coordinator": "Coordinator", "कोऑर्डिनेटर": "Coordinator",
    "teacher": "Teacher", "शिक्षक": "Teacher", "শিক্ষক": "Teacher", "admin": "Admin",
    "secretary": "Secretary", "manager": "Manager", "correspondent": "Correspondent",
}
SUBJECT_WORDS = {
    "maths": "Maths", "math": "Maths", "mathematics": "Maths", "गणित": "Maths", "অঙ্ক": "Maths",
    "science": "Science", "विज्ञान": "Science", "বিজ্ঞান": "Science",
    "physics": "Physics", "chemistry": "Chemistry", "biology": "Biology",
    "english": "English", "hindi": "Hindi", "bengali": "Bengali", "bangla": "Bengali",
    "history": "History", "geography": "Geography", "computer": "Computer",
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
PHONE_RE = re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b")
CLASS_RANGE_RE = re.compile(
    r"(?:class|classes|grade|क्लास|कक्षा|শ্রেণি|ক্লাস)\s*(\d{1,2})"
    r"(?:\s*(?:to|se|से|থেকে|থেকে|-|–|and)\s*(\d{1,2}))?", re.I)
VOLUME_RE = re.compile(
    r"\b(\d{1,4})\s*(?:টা|টি|ta|पेपर|पर्चे|প্রশ্নপত্র|প্রশ্ন)?\s*"
    r"(?:papers?|questions?|sets?|पेपर|पर्चे|প্রশ্নপত্র|প্রশ্ন)", re.I)
TIME_RE = re.compile(
    r"\b(tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"kal|parso|aaj|सोमवार|मंगलवार|बुधवार|गुरुवार|शुक्रवार|शनिवार|रविवार|कल|आज|परसों|"
    r"সোমবার|মঙ্গলবার|বুধবার|বৃহস্পতিবার|শুক্রবার|শনিবার|রবিবার|কাল|আজ|পরশু)\b"
    r"|\b(\d{1,2})\s*(?::\s*\d{2})?\s*(am|pm|baje|bje|o clock|बजे|টায়|টোয়)\b", re.I)

DIGITS = str.maketrans("०१२३४५६७८९০১২৩৪৫৬৭৮৯", "01234567890123456789")


DAY_RE = re.compile(
    r"\b(tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"kal|parso|aaj|सोमवार|मंगलवार|बुधवार|गुरुवार|शुक्रवार|शनिवार|रविवार|कल|आज|परसों|"
    r"সোমবার|মঙ্গলবার|বুধবার|বৃহস্পতিবার|শুক্রবার|শনিবার|রবিবার|কাল|আজ|পরশু)\b", re.I)
CLOCK_RE = re.compile(
    r"(?<!\d)(\d{1,2})(?::(\d{2}))?\s*"
    r"(am|pm|a\.m|p\.m|baje|bje|o clock|बजे|টায়|টোয়|টা|টে)(?![a-z])", re.I)


def _slot_phrase(text: str) -> str | None:
    """Turn "ok tomorrow 4 pm works" into "tomorrow at 4 pm" — a bookable slot."""
    day = DAY_RE.search(text)
    clock = CLOCK_RE.search(text)
    if clock:
        # "৪০টা প্রশ্নপত্র" is a count, not a time — validate the hour
        hour = int(clock.group(1).translate(DIGITS))
        limit = 23 if clock.group(2) else 12
        if hour > limit or hour == 0:
            clock = None
    if day and clock:
        time = clock.group(0).strip()
        joiner = " at " if time.isascii() else " "
        return f"{day.group(0)}{joiner}{time}".strip()
    if day:
        return day.group(0)
    if clock:
        return clock.group(0)
    return None


@dataclass
class Understanding:
    intent: str
    confidence: float
    score: float = 0.0
    all_intents: list[tuple[str, float]] = field(default_factory=list)
    entities: dict = field(default_factory=dict)
    sentiment: float = 0.0
    is_question: bool = False
    words: int = 0
    substantial: bool = False


def normalise(text: str) -> str:
    text = (text or "").lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"http\S+", " ", text)
    text = re.sub(r"[^\w\s@.'\u0900-\u097F\u0980-\u09FF]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_letter(ch: str) -> bool:
    return ch.isalnum() or ch == "_" or "\u0900" <= ch <= "\u09FF"


def _find(phrase: str, hay: str) -> tuple[int, int] | None:
    """Boundary-aware search that also respects Indic combining marks.

    Without this, Bengali "থেকে" would match the word "কে" (who) and Hindi
    "क्लास" answers would classify as greetings.
    """
    start = 0
    while True:
        i = hay.find(phrase, start)
        if i < 0:
            return None
        before = hay[i - 1] if i > 0 else " "
        end = i + len(phrase)
        after = hay[end] if end < len(hay) else " "
        if not _is_letter(before) and not _is_letter(after):
            return i, end
        start = i + 1


def classify_intents(text: str) -> tuple[str, float, float, list[tuple[str, float]]]:
    hay = " " + normalise(text) + " "
    pairs = [(p, intent) for intent, phrases in INTENT_PHRASES.items() for p in phrases]
    pairs.sort(key=lambda x: (len(x[0].split()), len(x[0])), reverse=True)

    scores: dict[str, float] = {}
    for phrase, intent in pairs:
        span = _find(phrase, hay)
        if not span:
            continue
        words = len(phrase.split())
        weight = 0.7 if phrase in WEAK_PHRASES else 1.0 + 0.5 * (words - 1)
        scores[intent] = scores.get(intent, 0.0) + weight
        hay = hay[: span[0]] + " " * (span[1] - span[0]) + hay[span[1]:]

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked:
        return "unclear", 0.0, 0.0, []
    best, best_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    confidence = min(1.0, best_score / 1.8) * (0.75 if second >= best_score else 1.0)
    return best, round(confidence, 2), round(best_score, 2), ranked[:4]


def extract_entities(text: str) -> dict:
    raw = text or ""
    low = normalise(raw)
    ascii_digits = (raw or "").translate(DIGITS)
    ascii_low = normalise(ascii_digits)
    out: dict = {}

    # spoken email: "priya at sunrise dot edu" / "priya@gmail . com"
    spoken = re.sub(r"\s+(?:at|@)\s+", "@", raw, flags=re.I)
    spoken = re.sub(r"\s+(?:dot|\.)\s+", ".", spoken, flags=re.I)
    spoken = re.sub(r"\s*@\s*", "@", spoken)
    email = EMAIL_RE.search(spoken) or EMAIL_RE.search(raw)
    if email:
        out["email"] = email.group(0).lower().strip(".,")

    digits_only = re.sub(r"[\s\-()]", "", ascii_digits)
    phone = PHONE_RE.search(digits_only) or PHONE_RE.search(ascii_digits)
    if phone:
        out["phone"] = re.sub(r"\D", "", phone.group(0))[-10:]

    m = CLASS_RANGE_RE.search(ascii_digits)
    if m:
        lo, hi = m.group(1), m.group(2)
        out["classes"] = f"{lo}-{hi}" if hi else lo

    m = VOLUME_RE.search(ascii_digits)
    if m:
        out["papers_per_term"] = int(m.group(1))

    slot = _slot_phrase(low)   # keep the customer's own script in the slot label
    if slot:
        out["slot_raw"] = slot

    for word, label in ROLE_WORDS.items():
        if _find(word, " " + low + " "):
            out.setdefault("role", label)
            break
    for word, label in SUBJECT_WORDS.items():
        if _find(word, " " + low + " "):
            out.setdefault("subject", label)
            break

    if re.search(r"(by hand|handwrit|typed in word|ms word|excel|word me|पेन से|हाथ से|हाथों से|হাতে)", low):
        out["current_process"] = "manual typing"
    if re.search(r"(before exam|next term|this session|exam season|परीक्षा|এক্সাম|পরীক্ষা)", low):
        out.setdefault("timeline", "before next exams")
    if re.search(r"(coaching|institute|academy|कोचिंग|কোচিং)", low):
        out["org_type"] = "coaching institute"
    elif re.search(r"(school|स्कूल|স্কুল)", low):
        out["org_type"] = "school"
    return out


def sentiment_of(text: str) -> float:
    tokens = normalise(text).split()
    if not tokens:
        return 0.0
    score = 0.0
    for i, tok in enumerate(tokens):
        clean = tok.strip(".'")
        val = 0.0
        if clean in POSITIVE_WORDS:
            val = 1.0
        elif clean in NEGATIVE_WORDS:
            val = -1.0
        if val and i and tokens[i - 1] in INTENSIFIERS:
            val *= 1.5
        if val and i and tokens[i - 1] in {"not", "dont", "never", "nahi", "mat", "नहीं", "না"}:
            val *= -0.8
        score += val
    scale = max(2.0, len(tokens) / 3)
    return max(-1.0, min(1.0, round(score / scale, 2)))


def understand(text: str) -> Understanding:
    intent, conf, score, ranked = classify_intents(text)
    ents = extract_entities(text)
    words = len((text or "").split())
    substantial = words >= 3 or bool(ents)

    # a genuine open-question answer has no intent keyword — that is fine
    if intent == "unclear" and substantial:
        intent = "answer"

    return Understanding(
        intent=intent,
        confidence=conf,
        score=score,
        all_intents=ranked,
        entities=ents,
        sentiment=sentiment_of(text),
        is_question=bool(re.search(
            r"\?|\b(kya|kaise|kitna|kab|kahan|what|how|why|when|can you|do you|"
            r"क्या|कैसे|कितना|कब|কী|কীভাবে|কত|কখন)\b", (text or "").lower())),
        words=words,
        substantial=substantial,
    )
