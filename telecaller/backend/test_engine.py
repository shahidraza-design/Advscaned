"""
test_engine.py — the safety net for the dialog engine.

    python test_engine.py        (no pytest needed)
    pytest test_engine.py        (also works)

The important tests are the boring ones: the agent must never go silent, never
book a demo after a Do-Not-Call request, never loop forever on an objection, and
never confuse a Bengali word for a Hindi one.
"""
from __future__ import annotations

import json
import sys

from dialog import DialogEngine, Session
from nlu import understand
from scripts import BUSINESS_DEFAULTS, LINES, OBJECTIONS, QUICK_REPLIES
from store import DEFAULT_KB, score_call

S = {**BUSINESS_DEFAULTS}
LEAD = {"id": "t1", "name": "Meera Nair", "company": "Sunrise Public School",
        "phone": "+919810000001", "language": "en"}


def new_call(lang: str = "en", lead: dict | None = None):
    lead = {**LEAD, **(lead or {}), "language": lang}
    sess = Session(call_id="test", lead=lead, settings=S, lang=lang)
    return sess, DialogEngine(S, DEFAULT_KB)


def run(lines: list[str], lang: str = "en"):
    sess, eng = new_call(lang)
    opening = eng.opening(sess)
    out = [opening]
    for text in lines:
        r = eng.respond(sess, text)
        out.append(r)
        if r.end_call:
            break
    return sess, eng, out


# --------------------------------------------------------------------- language
def test_every_line_exists_in_all_languages():
    for key, entry in LINES.items():
        for lang in ("en", "hi", "bn"):
            assert entry.get(lang, "").strip(), f"{key} missing {lang}"


def test_every_objection_has_a_reply():
    for key, obj in OBJECTIONS.items():
        for lang in ("en", "hi", "bn"):
            assert obj["reply"].get(lang, "").strip(), f"objection {key} missing {lang}"


def test_quick_replies_cover_every_stage():
    for stage in ("OPENING", "DISCOVERY", "PITCH", "CLOSE", "WRAP"):
        assert QUICK_REPLIES[stage]["en"], f"no chips for {stage}"


# -------------------------------------------------------------------------- NLU
def test_bengali_word_boundaries():
    # "থেকে" contains "কে"; before the boundary fix this fired the "who" intent
    assert understand("ক্লাস ৬ থেকে ১০").intent != "who"


def test_hindi_affirmation_and_price():
    u = understand("हाँ बोल रहा हूँ")
    assert u.intent == "affirm"
    assert understand("कितना लगेगा?").intent == "price"


def test_indic_digits_normalised():
    assert understand("প্রায় ৪০টা প্রশ্নপত্র").entities["papers_per_term"] == 40
    assert understand("करीब ४० पेपर").entities["papers_per_term"] == 40


def test_spoken_email():
    assert understand("priya at sunrise dot edu").entities["email"] == "priya@sunrise.edu"


def test_slot_parsing_is_not_a_count():
    assert "slot_raw" not in understand("প্রায় ৪০টা প্রশ্নপত্র").entities
    assert understand("tomorrow 4 pm works").entities["slot_raw"] == "tomorrow at 4 pm"
    assert understand("ठीक है, कल 4 बजे").entities["slot_raw"] == "कल 4 बजे"


def test_open_question_answer_is_not_noise():
    u = understand("classes 6 to 10, we type papers in Word")
    assert u.intent == "answer" and u.entities["classes"] == "6-10"


def test_dnc_beats_everything():
    u = understand("not interested, do not call me again")
    assert u.intent == "dnc"


def test_sentiment_signs():
    assert understand("this is great, very useful").sentiment > 0
    assert understand("this is annoying, waste of time").sentiment < 0


# ----------------------------------------------------------------------- dialog
def test_happy_path_books_a_demo():
    sess, eng, turns = run([
        "yes speaking", "classes 6 to 10, we type papers in Word",
        "about 40 papers a term", "ok, tomorrow 4 pm works"])
    assert turns[-1].end_call
    assert turns[-1].appointment["slot"] == "tomorrow at 4 pm"
    assert turns[-1].debug["outcome"] == "booked"
    assert sess.slots["classes"] == "6-10"


def test_never_silent_across_a_wide_matrix():
    utterances = [
        "yes", "no", "hello", "who is this", "I am busy", "call me later",
        "not interested", "how much", "send details", "we already have a tool",
        "I need to think", "can you hear me", "repeat that", "hmm", "",
        "we are a school with 900 students", "hindi me baat karo", "ok",
        "talk to a human", "wrong number", "do not call again", "tomorrow 5 pm",
        "class 8 science", "इसकी कीमत क्या है", "আমাদের স্কুলে ৬০০ ছাত্র",
    ]
    for text in utterances:
        for start in ("OPENING", "DISCOVERY", "PITCH", "CLOSE"):
            sess, eng = new_call()
            sess.stage = start
            reply = eng.respond(sess, text)
            assert reply.text.strip(), f"empty reply for {text!r} at {start}"
            assert len(reply.text.split()) < 120, f"runaway reply for {text!r} at {start}"


def test_dnc_is_honoured_and_never_books():
    sess, eng, turns = run(["yes", "please do not call me again"])
    assert turns[-1].dnc and turns[-1].end_call
    assert turns[-1].appointment is None
    assert turns[-1].debug["outcome"] == "dnc"


def test_wrong_number_exits():
    sess, eng, turns = run(["who is this", "wrong number"])
    assert turns[-1].end_call and turns[-1].debug["outcome"] == "wrong_number"


def test_objection_loop_terminates():
    sess, eng, turns = run(["yes", "I need to think", "I need to think",
                            "I need to think about it", "I really need to think"])
    assert len(turns) <= 8
    assert turns[-1].end_call or "email" in turns[-1].text.lower()


def test_busy_leads_to_a_callback_with_a_slot():
    sess, eng, turns = run(["yes", "I'm busy right now", "call me tomorrow at 11 am"])
    assert turns[-1].appointment == {"slot": "tomorrow at 11 am", "type": "callback",
                                    "source": "lead_chose"}


def test_language_switches_to_hindi_mid_call():
    sess, eng, turns = run(["हाँ बोल रहा हूँ", "क्लास 6 से 10"])
    assert turns[-1].lang == "hi"
    assert any("\u0900" <= ch <= "\u097F" for ch in turns[-1].text)


def test_bengali_call_stays_bengali():
    sess, eng, turns = run(["হ্যাঁ বলছি", "ক্লাস ৬ থেকে ১০, হাতে লিখি", "প্রায় ৪০টা প্রশ্নপত্র"],
                           lang="bn")
    assert turns[-1].lang == "bn"
    assert sess.slots["papers_per_term"] == 40


def test_email_followup_path():
    sess, eng, turns = run(["yes", "send me details", "priya at sunrise dot edu"])
    assert sess.slots["email"] == "priya@sunrise.edu"
    assert turns[-1].end_call


def test_one_question_per_turn():
    sess, eng, turns = run(["yes", "classes 6 to 10", "about 40 papers", "how much?"])
    for reply in turns:
        assert reply.text.count("?") <= 2, f"too many questions: {reply.text}"


# ------------------------------------------------------------------------ store
def test_score_bounds():
    assert 0 <= score_call({"outcome": "booked", "slots": {"classes": "6-10"},
                            "consent": True, "sentiment_series": [0.5]}, {}) <= 100
    assert score_call({"outcome": "dnc", "slots": {}, "sentiment_series": [-1]}, {}) == 0


def test_settings_have_all_languages_of_business_facts():
    for key in ("value_prop_hi", "value_prop_bn", "offer_hi", "offer_bn",
                "demo_slots_hi", "demo_slots_bn"):
        assert S.get(key), f"missing localised fact: {key}"


if __name__ == "__main__":
    failures = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  ✗ {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
