"""
dialog.py — the conversation policy. This is the part that makes it a *telecaller*
and not a chatbot.

What it does on every turn
  • tracks a call stage (OPENING → DISCOVERY → PITCH → CLOSE → WRAP) with a goal
  • enforces discipline: one question per turn, a word budget per stage,
    never pitching before permission, never arguing with an objection
  • qualifies the lead (role, classes, volume, current process, timeline, email)
    and books a concrete slot — the only thing a telecaller is actually paid for
  • handles interruption/barge-in, "say that again", unclear audio, frustration
  • respects compliance: DNC, wrong number, consent, max objection attempts
  • degrades gracefully — if understanding confidence is low it asks a short
    clarifying question instead of guessing

Language: English / Hindi / Bengali, switched mid-call by script detection or on
request ("hindi mein baat kariye"). Replies get longer/shorter depending on the
lead's own turn length and sentiment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from nlu import Understanding, understand
from scripts import HINTS, LINES, OBJECTIONS, QUICK_REPLIES

STAGES = ["OPENING", "DISCOVERY", "PITCH", "CLOSE", "WRAP"]
WORD_BUDGET = {"OPENING": 42, "DISCOVERY": 38, "PITCH": 95, "CLOSE": 48, "WRAP": 45}

DEVANAGARI = re.compile(r"[\u0900-\u097F]")
BENGALI = re.compile(r"[\u0980-\u09FF]")


def line(key: str, lang: str, **ctx) -> str:
    entry = LINES.get(key, {})
    text = entry.get(lang) or entry.get("en") or ""
    return text.format(**ctx) if ctx else text


def detect_language(text: str) -> str | None:
    if BENGALI.search(text or ""):
        return "bn"
    if DEVANAGARI.search(text or ""):
        return "hi"
    return None


@dataclass
class Session:
    call_id: str
    lead: dict
    settings: dict
    lang: str = "en"
    stage: str = "OPENING"
    slots: dict = field(default_factory=dict)
    appointment: dict | None = None
    consent: bool = False
    dnc: bool = False
    end_call: bool = False
    last_agent_text: str = ""
    last_question: str = ""
    objections: int = 0
    clarify: int = 0
    discovery_i: int = 0
    turns: int = 0
    sentiment: list[float] = field(default_factory=list)
    barge_ins: int = 0
    asked_email: bool = False
    last_objection: str = ""
    pending: str = ""        # "" | "email" | "slot" | "reason"
    used_lines: list[str] = field(default_factory=list)


@dataclass
class Reply:
    text: str
    lang: str
    stage: str
    goal: str
    understanding: Understanding | None = None
    chips: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    end_call: bool = False
    transfer: bool = False
    dnc: bool = False
    appointment: dict | None = None
    slots: dict = field(default_factory=dict)
    consent: bool = False
    debug: dict = field(default_factory=dict)

    def as_dict(self, session: Session) -> dict:
        u = self.understanding
        return {
            "text": self.text,
            "language": self.lang,
            "stage": self.stage,
            "goal": self.goal,
            "chips": self.chips,
            "actions": self.actions,
            "end_call": self.end_call,
            "transfer": self.transfer,
            "dnc": self.dnc,
            "appointment": self.appointment,
            "slots": self.slots,
            "consent": self.consent,
            "understanding": {
                "intent": u.intent if u else None,
                "confidence": u.confidence if u else None,
                "sentiment": u.sentiment if u else 0.0,
                "entities": u.entities if u else {},
                "ranked": u.all_intents if u else [],
                "is_question": u.is_question if u else False,
            } if u else None,
            "debug": self.debug,
            "turns": session.turns,
            "barge_ins": session.barge_ins,
        }


class DialogEngine:
    """Deterministic, explainable, offline-capable. No API key required."""

    def __init__(self, settings: dict, kb: list[dict] | None = None):
        self.s = settings
        self.kb = kb or []

    # ------------------------------------------------------------------ helpers
    def _ctx(self, session: Session) -> dict:
        lang = session.lang
        slots = (session.settings.get(f"demo_slots_{lang}")
                 or session.settings.get("demo_slots")
                 or ["tomorrow at 4 pm", "Friday at 11 am"])
        return {
            "agent": self.s.get("agent_name", "Aarohi"),
            "company": self.s.get("company", "Advscaned"),
            "product": self.s.get("product", "QPaper AI"),
            "name": (session.lead.get("name") or "there").split()[0],
            "value_prop": self.s.get(f"value_prop_{lang}") or self.s.get("value_prop", ""),
            "offer": self.s.get(f"offer_{lang}") or self.s.get("offer", "a quick demo"),
            "slot1": slots[0],
            "slot2": slots[1] if len(slots) > 1 else slots[0],
            "email": session.slots.get("email", ""),
            "slot": (session.appointment or {}).get("slot", ""),
        }

    def _say(self, session: Session, key_or_text: str, is_key: bool = True) -> str:
        text = line(key_or_text, session.lang, **self._ctx(session)) if is_key else key_or_text
        budget = WORD_BUDGET.get(session.stage, 60)
        if len(text.split()) > budget * 1.6:
            text = " ".join(text.split()[: int(budget * 1.6)]) + "…"
        session.last_agent_text = text
        return text

    def _chips(self, session: Session) -> list[str]:
        rows = QUICK_REPLIES.get("WRAP" if session.end_call else session.stage, {})
        return rows.get(session.lang) or rows.get("en") or []

    def _goal(self, session: Session) -> str:
        return {
            "OPENING": "Confirm you're speaking to the right person and earn 30 seconds.",
            "DISCOVERY": "Qualify: role, classes, paper volume, current process.",
            "PITCH": "Connect one benefit to what they just told you.",
            "CLOSE": "Book a concrete 15-minute demo slot.",
            "WRAP": "Confirm the next step in one line, then end politely.",
        }.get(session.stage, "")

    # ------------------------------------------------------------------ opening
    def opening(self, session: Session) -> Reply:
        session.stage = "OPENING"
        text = f"{self._say(session, 'greeting')} {self._say(session, 'permission')}"
        session.last_agent_text = text
        session.asked_email = False
        return Reply(text=text, lang=session.lang, stage="OPENING", goal=self._goal(session),
                     chips=self._chips(session), debug={"policy": "scripted opening"})

    # -------------------------------------------------------------------- respond
    def respond(self, session: Session, user_text: str, interrupted: bool = False) -> Reply:
        session.turns += 1
        if interrupted:
            session.barge_ins += 1

        # 1 — language. Script detection switches the call politely.
        switched = False
        detected = detect_language(user_text)
        if detected and detected != session.lang and detected in self.s.get("languages", ["en"]):
            session.lang = detected
            switched = True
        wants_switch = re.search(r"(hindi|हिंदी|हिन्दी|bengali|bangla|বাংলায়|english)", user_text or "", re.I)
        if wants_switch and session.turns > 1:
            w = wants_switch.group(1).lower()
            new_lang = ("bn" if w.startswith(("beng", "bangla", "বাংল"))
                        else "hi" if w.startswith(("hin", "हिं")) else "en")
            switched = new_lang != session.lang
            session.lang = new_lang

        u = understand(user_text)
        session.sentiment.append(u.sentiment)
        session.slots.update({k: v for k, v in u.entities.items() if k not in {"slot_raw"}})

        # 2 — compliance and hard stops first. Always.
        if u.intent == "dnc":
            session.dnc = True
            session.end_call = True
            session.stage = "WRAP"
            return self._finish(session, u, "dnc_close", "dnc")

        if u.intent == "wrong_number":
            session.end_call = True
            session.stage = "WRAP"
            return self._finish(session, u, "wrong_number_close", "wrong_number")

        if u.intent == "human":
            text = self._say(session, "human_transfer")
            session.end_call = bool(self.s.get("human_transfer_number"))
            return Reply(text=text, lang=session.lang, stage=session.stage,
                         goal=self._goal(session), understanding=u,
                         chips=self._chips(session), transfer=True,
                         actions=[{"type": "transfer", "to": self.s.get("human_transfer_number", "")}],
                         end_call=session.end_call,
                         debug={"policy": "human handoff requested"})

        if u.intent == "audio_check":
            return Reply(text=self._say(session, "audio_ok"), lang=session.lang,
                         stage=session.stage, goal=self._goal(session), understanding=u,
                         chips=self._chips(session),
                         debug={"policy": "audio check → reassure, keep going"})

        if u.intent == "repeat":
            text = f"{self._say(session, 'repeat_ack')} {session.last_agent_text}".strip()
            return Reply(text=text, lang=session.lang, stage=session.stage,
                         goal=self._goal(session), understanding=u,
                         chips=self._chips(session), debug={"policy": "re-said last turn"})

        if u.intent == "neg_sentiment" and u.sentiment <= -0.5:
            session.end_call = True
            session.stage = "WRAP"
            return self._finish(session, u, "not_interested_close", "not_interested")

        # 3 — pending email capture must beat "unclear": an email is often just
        #     a string of letters and dots to a keyword matcher.
        if session.pending == "email":
            if u.entities.get("email"):
                email = u.entities["email"]
                session.stage = "WRAP"
                session.end_call = True
                return self._finish(session, u, "followup_email_ack", "connected",
                                    actions=[{"type": "send_email", "to": email}],
                                    extra_debug="email captured → follow-up queued")
            if u.intent in {"deny", "not_interested"}:
                session.end_call = True
                session.stage = "WRAP"
                return self._finish(session, u, "not_interested_close", "not_interested")
            if u.intent in {"repeat", "busy"}:
                return self._plain(session, u, self._say(session, "callback_confirm"),
                                   debug="email not given → callback noted")

        # 4 — unclear / silence. Ask, don't guess.
        if u.intent == "unclear" and not u.substantial:
            session.clarify += 1
            if session.clarify >= 3:
                session.end_call = True
                session.stage = "WRAP"
                return self._finish(session, u, "not_interested_close", "no_response",
                                    extra_debug="3 unclear turns → graceful exit")
            text = self._say(session, "unclear")
            return Reply(text=text, lang=session.lang, stage=session.stage,
                         goal=self._goal(session), understanding=u,
                         chips=self._chips(session),
                         debug={"policy": "low confidence → clarify", "confidence": u.confidence})
        session.clarify = 0

        # 4b — two clearly negative turns in a row: stop selling, leave the door open
        if len(session.sentiment) >= 2 and all(v <= -0.7 for v in session.sentiment[-2:]) \
                and session.stage in {"OPENING", "DISCOVERY", "PITCH"}:
            session.end_call = True
            session.stage = "WRAP"
            return self._finish(session, u, "not_interested_close", "not_interested",
                                extra_debug="two negative turns → polite exit")

        # 5 — stage machine
        handler = getattr(self, f"_stage_{session.stage.lower()}", self._stage_opening)
        reply = handler(session, u, user_text)
        if switched and session.turns > 1:
            reply.text = f'{line("lang_switch", session.lang)} {reply.text}'
        return reply

    # ---------------------------------------------------------------- the stages
    def _stage_opening(self, session: Session, u: Understanding, text: str) -> Reply:
        if u.intent in {"who", "what_about"}:
            key = "who_is_this" if u.intent == "who" else "purpose_short"
            reply = f"{self._say(session, key)} {self._say(session, 'permission')}"
            return self._plain(session, u, reply, debug="identity/purpose question answered")

        if u.intent in {"busy", "callback"}:
            slot = u.entities.get("slot_raw")
            if slot:
                session.appointment = {"slot": slot, "type": "callback"}
                session.stage = "WRAP"
                session.end_call = True
                return self._finish(session, u, "callback_confirm", "callback",
                                    extra_debug="callback booked from opening")
            session.pending = "slot"
            session.stage = "CLOSE"
            reply = f"{self._say(session, 'busy_ack')} {self._say(session, 'close_2')}"
            return self._plain(session, u, reply, debug="busy → ask for a slot")

        if u.intent in {"not_interested", "deny"}:
            if u.intent == "deny" and session.turns <= 1:
                reply = self._say(session, "purpose") + " " + self._say(session, "ack_then") + " " + self._say(session, "close_2")
                session.stage = "CLOSE"
                return self._plain(session, u, reply, debug="soft no at opening → one reframe")
            session.end_call = True
            session.stage = "WRAP"
            return self._finish(session, u, "not_interested_close", "not_interested")

        if u.intent in {"greeting", "affirm", "interest", "answer"} or u.confidence >= 0.5:
            session.consent = True
            session.stage = "DISCOVERY"
            reply = self._say(session, "purpose") + " " + self._discovery_question(session)
            return self._plain(session, u, reply,
                               debug="permission granted → purpose → discovery")

        # default: restate permission, shorter
        session.stage = "DISCOVERY"
        reply = self._say(session, "purpose") + " " + self._discovery_question(session)
        return self._plain(session, u, reply, debug="no clear signal → advance softly")

    def _stage_discovery(self, session: Session, u: Understanding, text: str) -> Reply:
        if u.intent in {"dnc", "not_interested"}:
            if u.intent == "not_interested" and session.objections < 1:
                return self._objection(session, u, "think")
            session.end_call = True
            session.stage = "WRAP"
            return self._finish(session, u, "not_interested_close", "not_interested")

        if u.intent in {"busy", "callback"}:
            slot = u.entities.get("slot_raw")
            if slot:
                session.appointment = {"slot": slot, "type": "callback"}
                session.stage = "WRAP"
                session.end_call = True
                return self._finish(session, u, "callback_confirm", "callback",
                                    extra_debug="callback booked during discovery")
            session.pending = "slot"
            session.stage = "CLOSE"
            return self._plain(session, u,
                               f"{self._say(session, 'busy_ack')} {self._say(session, 'close_2')}",
                               debug="busy during discovery → ask for slot")

        if u.intent in {"price", "price_objection", "have_vendor", "trust", "no_budget",
                        "send_info", "think"}:
            obj = {"price": "price", "price_objection": "price", "have_vendor": "have_vendor",
                   "send_info": "send_info", "think": "think"}.get(u.intent, "think")
            return self._objection(session, u, obj)

        if u.intent in {"features", "what_about"}:
            answer = self._answer_from_kb(text) or line("pitch_small", session.lang, **self._ctx(session))
            session.stage = "PITCH"
            reply = f"{answer} {self._discovery_question(session)}"
            return self._plain(session, u, reply, debug="feature question → KB answer → re-qualify")

        # normal qualifying answer → harvest what we heard, then next probe
        session.discovery_i += 1
        max_q = int(self.s.get("max_discovery_questions", 2))
        if session.discovery_i >= max_q:
            session.stage = "PITCH"
            ack = self._say(session, "ack_then")
            big = (session.slots.get("papers_per_term", 0) or 0) >= 25 or \
                  session.slots.get("role", "") in {"Principal", "Director", "Vice Principal", "Trustee"}
            pitch = self._say(session, "pitch_big" if big else "pitch_small")
            reply = f"{ack} {pitch} {self._say(session, 'close_1')}"
            session.stage = "CLOSE"
            return self._plain(session, u, reply,
                               debug="qualified enough → tailored pitch → close")
        ack = "answer_ack" if u.intent == "answer" else "ack_then"
        return self._plain(session, u, self._say(session, ack) + " " + self._discovery_question(session),
                           debug="discovery continues")

    def _stage_pitch(self, session: Session, u: Understanding, text: str) -> Reply:
        if u.intent in {"interest", "affirm", "demo", "greeting"}:
            session.stage = "CLOSE"
            reply = self._say(session, "close_1")
            return self._plain(session, u, reply, debug="interest → close")
        return self._stage_close(session, u, text)

    def _stage_close(self, session: Session, u: Understanding, text: str) -> Reply:
        # a slot was named explicitly → book it
        if u.entities.get("slot_raw") and u.intent in {"affirm", "demo", "interest", "callback",
                                                       "greeting", "answer"}:
            slot = u.entities["slot_raw"]
            kind = "callback" if session.pending == "slot" else "demo"
            session.appointment = {"slot": slot, "type": kind, "source": "lead_chose"}
            session.stage = "WRAP"
            session.end_call = True
            return self._finish(session, u, "booked", "booked",
                                actions=[{"type": "calendar", "slot": slot},
                                         {"type": "whatsapp", "to": session.lead.get("phone", "")}])

        if u.intent in {"affirm", "demo", "interest"}:
            slot = (session.settings.get("demo_slots") or ["tomorrow at 4 pm"])[0]
            session.appointment = {"slot": slot, "type": "demo", "source": "default_offer"}
            session.stage = "WRAP"
            session.end_call = True
            return self._finish(session, u, "booked", "booked",
                                actions=[{"type": "calendar", "slot": slot}])

        if u.intent in {"deny", "think", "price", "price_objection", "have_vendor", "no_budget",
                        "no_time", "not_interested", "send_info", "already_tried"}:
            obj = {"deny": "think", "no_time": "no_time", "not_interested": "think",
                   "price_objection": "price", "already_tried": "already_tried"}.get(u.intent, u.intent)
            return self._objection(session, u, obj)

        if u.intent in {"busy", "callback"}:
            slot = u.entities.get("slot_raw")
            session.stage = "WRAP"
            session.end_call = True
            if slot:
                session.appointment = {"slot": slot, "type": "callback"}
                return self._finish(session, u, "callback_confirm", "callback")
            session.pending = "slot"
            return self._plain(session, u, self._say(session, "close_2"), debug="needs a slot")

        if u.intent == "features":
            answer = self._answer_from_kb(text) or self._say(session, "pitch_small")
            return self._plain(session, u, f"{answer} {self._say(session, 'close_1')}",
                               debug="answer + re-close")

        return self._plain(session, u, self._say(session, "close_2"),
                           debug="unclear at close → binary choice again")

    def _stage_wrap(self, session: Session, u: Understanding, text: str) -> Reply:
        if u.intent == "thanks":
            session.end_call = True
            return self._finish(session, u, "thanks", session.appointment and "booked" or "connected")
        if u.intent in {"deny", "not_interested"}:
            session.end_call = True
            return self._finish(session, u, "not_interested_close", "not_interested")
        session.end_call = True
        return self._finish(session, u, "thanks", session.appointment and "booked" or "connected")

    # ------------------------------------------------------------------ objections
    def _objection(self, session: Session, u: Understanding, key: str) -> Reply:
        session.objections += 1
        repeated = getattr(session, "last_objection", None) == key
        session.last_objection = key
        obj = OBJECTIONS.get(key) or OBJECTIONS["think"]

        # the same wall twice means the reframe didn't land — change the ask
        if repeated and key != "send_info":
            session.pending = "email"
            session.stage = "CLOSE"
            softening = {
                "en": "I hear you — I won't keep pushing the same point. Can I just email a one-page summary so you have it on record?",
                "hi": "समझ गई — उसी बात पर ज़ोर नहीं दूँगी। एक पेज का सार ईमेल कर दूँ, रिकॉर्ड के लिए?",
                "bn": "বুঝেছি — একই কথা চাপ দেব না। এক পাতার সারসংক্ষেপ মেইল করি, রেকর্ডের জন্য?",
            }
            return self._plain(session, u, softening.get(session.lang, softening["en"]),
                               debug="same objection twice → switch to soft close",
                               actions=[{"type": "ask_email"}])
        reply = obj["reply"].get(session.lang) or obj["reply"]["en"]

        if key == "send_info":
            session.pending = "email"
            session.asked_email = True
            return self._plain(session, u, reply, debug="objection: send info → capture email",
                               actions=[{"type": "ask_email"}])

        if session.objections >= 3:
            session.stage = "WRAP"
            session.end_call = True
            tail = line("callback_confirm", session.lang, **self._ctx(session)) if session.appointment \
                else line("not_interested_close", session.lang, **self._ctx(session))
            return self._finish(session, u, f"{reply} {tail}", "not_interested", is_key=False,
                                extra_debug="3 objections → polite exit")

        session.stage = "CLOSE"
        reply = f"{reply} {self._say(session, 'close_1')}"
        return self._plain(session, u, reply, debug=f"objection '{obj['label']}' → reframe → re-close")

    # --------------------------------------------------------------- construction
    def _discovery_question(self, session: Session) -> str:
        i = min(session.discovery_i, 2)
        return self._say(session, f"discovery_{i + 1}")

    def _answer_from_kb(self, text: str) -> str | None:
        """Lexical retrieval over the FAQ — free, instant, no embeddings server."""
        q = set(re.findall(r"\w+", (text or "").lower()))
        best, best_score = None, 0.0
        for row in self.kb:
            kws = set(re.findall(r"\w+", (row.get("question", "") + " " + row.get("answer", "")).lower()))
            if not kws:
                continue
            score = len(q & kws) / (len(q) ** 0.5 + 1)
            if score > best_score:
                best, best_score = row, score
        return best["answer"] if best and best_score >= 0.6 else None

    def _plain(self, session: Session, u: Understanding, text: str, debug: str = "",
               actions: list | None = None) -> Reply:
        session.last_agent_text = text
        return Reply(text=text, lang=session.lang, stage=session.stage,
                     goal=self._goal(session), understanding=u, chips=self._chips(session),
                     actions=actions or [], appointment=session.appointment,
                     slots=session.slots, consent=session.consent,
                     end_call=session.end_call, dnc=session.dnc,
                     debug={"policy": debug, "hint": HINTS.get(session.stage, "")})

    def _finish(self, session: Session, u: Understanding, key_or_text: str, outcome: str,
                is_key: bool = True, actions: list | None = None, extra_debug: str = "") -> Reply:
        text = self._say(session, key_or_text) if is_key else key_or_text
        session.last_agent_text = text
        return Reply(text=text, lang=session.lang, stage="WRAP", goal=self._goal(session),
                     understanding=u, chips=QUICK_REPLIES["WRAP"].get(session.lang, []),
                     actions=actions or [], end_call=True, transfer=False,
                     dnc=session.dnc, appointment=session.appointment, slots=session.slots,
                     consent=session.consent,
                     debug={"policy": extra_debug or f"closed as {outcome}", "outcome": outcome,
                            "hint": HINTS["WRAP"]})
