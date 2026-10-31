"""
app.py — the telecaller server.

    python -m uvicorn app:app --host 0.0.0.0 --port 8000
    open http://localhost:8000/app

Browser calling (free, no keys) is the default channel. The same engine also
answers real phone calls through Twilio (free trial credit) — see /twilio/voice.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import llm
from dialog import DialogEngine, Session
from scripts import QUICK_REPLIES
from store import Store

DATA = Path(os.getenv("TELECALLER_DATA", Path(__file__).parent.parent / "data"))
FRONTEND = Path(__file__).parent.parent / "frontend"

store = Store(DATA)

DEMO_LEADS = [
    {"name": "Meera Nair", "phone": "+919810000001", "company": "Sunrise Public School",
     "role": "Principal", "language": "en", "notes": "K-12, 1400 students", "consent": True},
    {"name": "Rakesh Verma", "phone": "+919810000002", "company": "Green Valley Academy",
     "role": "Director", "language": "hi", "notes": "CBSE, 3 branches", "consent": True},
    {"name": "Sujata Das", "phone": "+919810000003", "company": "Nabadwip High School",
     "role": "Headmistress", "language": "bn", "notes": "WBBSE, Bengali medium", "consent": True},
    {"name": "Imran Sheikh", "phone": "+919810000004", "company": "City Coaching Centre",
     "role": "Owner", "language": "en", "notes": "JEE/NEET coaching", "consent": True},
]


def seed_leads() -> int:
    existing = {l["phone"] for l in store.leads()}
    added = [store.add_lead(d) for d in DEMO_LEADS if d["phone"] not in existing]
    return len(added)


def _startup_seed():
    """A fresh clone should open on a usable console, not an empty table."""
    if not store.leads():
        seed_leads()


@asynccontextmanager
async def lifespan(_: FastAPI):
    _startup_seed()
    yield


app = FastAPI(title="Advscaned Telecaller — free voice agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SESSIONS: dict[str, Session] = {}
TWILIO: dict[str, str] = {}          # twilio CallSid -> our call_id


def engine() -> DialogEngine:
    return DialogEngine(store.settings(), store.kb())


def _session(call_id: str) -> Session:
    if call_id in SESSIONS:
        return SESSIONS[call_id]
    call = store.call(call_id)
    if not call:
        raise HTTPException(404, "call not found")
    lead = store.lead(call["lead_id"]) or {"id": call["lead_id"], "name": call["lead_name"],
                                           "language": call["language"], "phone": call["phone"]}
    s = Session(call_id=call_id, lead=lead, settings=store.settings(), lang=call["language"])
    for ev in call.get("transcript", []):
        if ev.get("slots"):
            s.slots.update(ev["slots"])
        if ev.get("sentiment") is not None:
            s.sentiment.append(ev["sentiment"])
    SESSIONS[call_id] = s
    return s


# --------------------------------------------------------------------- meta & UI
@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version,
            "llm": store.settings().get("llm_provider", "off"),
            "channels": ["browser", "twilio"],
            "engine": "deterministic policy + optional local LLM",
            "tts": _tts_available()}


@app.get("/")
def root():
    return RedirectResponse("/app/")


@app.get("/app", include_in_schema=False)
def app_redirect():
    return RedirectResponse("/app/")


@app.get("/api/quick_replies")
def quick_replies(lang: str = "en"):
    return {stage: (rows.get(lang) or rows.get("en")) for stage, rows in QUICK_REPLIES.items()}


# ------------------------------------------------------------------- settings / KB
@app.get("/api/settings")
def get_settings():
    return store.public_settings()


@app.put("/api/settings")
def put_settings(patch: dict = Body(...)):
    store.save_settings(patch)
    return store.public_settings()


@app.get("/api/kb")
def get_kb():
    return store.kb()


@app.put("/api/kb")
def put_kb(rows: list[dict] = Body(...)):
    return store.save_kb(rows)


# -------------------------------------------------------------------------- leads
class LeadIn(BaseModel):
    name: str = "there"
    phone: str = ""
    company: str = ""
    role: str = ""
    language: str = "en"
    notes: str = ""
    consent: bool = False


@app.get("/api/leads")
def list_leads():
    return store.leads()


@app.post("/api/leads")
def create_lead(lead: LeadIn):
    return store.add_lead(lead.model_dump())


@app.patch("/api/leads/{lead_id}")
def patch_lead(lead_id: str, patch: dict = Body(...)):
    out = store.update_lead(lead_id, patch)
    if not out:
        raise HTTPException(404, "lead not found")
    return out


@app.delete("/api/leads/{lead_id}")
def remove_lead(lead_id: str):
    if not store.delete_lead(lead_id):
        raise HTTPException(404, "lead not found")
    return {"deleted": lead_id}


@app.post("/api/leads/import")
async def import_leads(file: UploadFile | None = File(None), csv_text: str = Body(None, embed=True),
                       language: str = "en"):
    text = csv_text
    if file is not None:
        text = (await file.read()).decode("utf-8", "ignore")
    if not text:
        raise HTTPException(400, "send a CSV file or csv_text")
    return store.import_leads_csv(text, language)


@app.get("/api/leads/export.csv", response_class=PlainTextResponse)
def export_leads():
    return Response(store.leads_csv(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=leads.csv"})


# -------------------------------------------------------------------------- calls
class StartCall(BaseModel):
    lead_id: str
    channel: str = "browser"


@app.post("/api/calls/start")
def start_call(body: StartCall):
    lead = store.lead(body.lead_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    if lead.get("dnc"):
        raise HTTPException(409, "this lead is on the Do-Not-Call list")
    call = store.start_call(lead, channel=body.channel)
    sess = Session(call_id=call["id"], lead=lead, settings=store.settings(),
                   lang=lead.get("language", "en"))
    SESSIONS[call["id"]] = sess
    eng = engine()
    reply = eng.opening(sess)
    payload = reply.as_dict(sess)
    payload["call_id"] = call["id"]
    payload["lead"] = {"id": lead["id"], "name": lead["name"], "company": lead.get("company"),
                       "phone": lead.get("phone"), "language": lead.get("language")}
    payload["compliance"] = {
        "recording_notice": store.settings().get("record_notice", ""),
        "consent_required": not lead.get("consent", False),
        "dnc": bool(lead.get("dnc")),
    }
    store.append_event(call["id"], {"role": "agent", "text": reply.text, "stage": "OPENING",
                                    "policy": reply.debug.get("policy", ""), "slots": sess.slots})
    return payload


class TurnIn(BaseModel):
    text: str = ""
    interrupted: bool = False


@app.post("/api/calls/{call_id}/turn")
def take_turn(call_id: str, body: TurnIn):
    sess = _session(call_id)
    eng = engine()
    reply = eng.respond(sess, body.text, interrupted=body.interrupted)
    store.append_event(call_id, {
        "role": "lead", "text": body.text, "stage": sess.stage,
        "intent": reply.understanding.intent if reply.understanding else None,
        "confidence": reply.understanding.confidence if reply.understanding else None,
        "sentiment": reply.understanding.sentiment if reply.understanding else 0.0,
        "interruption": body.interrupted, "slots": sess.slots,
    })
    store.append_event(call_id, {"role": "agent", "text": reply.text, "stage": sess.stage,
                                 "policy": reply.debug.get("policy", ""), "slots": sess.slots})

    payload = reply.as_dict(sess)
    payload["call_id"] = call_id
    payload["coach"] = _coach(sess, body.text, reply)
    if reply.end_call:
        payload["final"] = store.finish_call(call_id, {
            "outcome": (reply.debug.get("outcome") if reply.debug else None) or "connected",
            "appointment": reply.appointment, "slots": sess.slots,
            "consent": sess.consent, "dnc": sess.dnc,
            "next_action": _next_action(sess, reply),
            "summary": llm.summarize_offline(store.call(call_id)["transcript"], sess.slots),
        })
        SESSIONS.pop(call_id, None)
    return payload


def _coach(sess: Session, lead_text: str, reply) -> dict:
    s = store.settings()
    hint = llm.coach(s, sess.stage, lead_text, sess.slots)
    u = reply.understanding
    objective = {
        "OPENING": "Earn 30 seconds — confirm identity, ask permission.",
        "DISCOVERY": "Get role, classes and paper volume. One question at a time.",
        "PITCH": "Tie it to their class size; keep it under 20 seconds.",
        "CLOSE": "Two specific slots. Don't ask 'if' — ask 'which'.",
        "WRAP": "Confirm next step in one sentence and end.",
    }.get(sess.stage, "")
    return {"suggestion": hint or objective, "objective": objective,
            "sentiment": u.sentiment if u else 0.0,
            "confidence": u.confidence if u else 0.0,
            "slots_captured": len([v for v in sess.slots.values() if v]),
            "talk_ratio_note": "Keep the lead talking more than you."}


def _next_action(sess: Session, reply=None) -> str:
    appointment = (reply.appointment if reply else None) or (sess.appointment if sess else None)
    if appointment:
        return f"Send calendar invite for {reply.appointment.get('slot')} + WhatsApp confirmation"
    if sess.slots.get("email"):
        return f"Email one-pager + 90s demo video to {sess.slots['email']}"
    if sess.dnc:
        return "Removed from list — do not contact again"
    return "Retry in 3 days with a different angle"


class HangupIn(BaseModel):
    outcome: str = "connected"
    reason: str = ""


@app.post("/api/calls/{call_id}/hangup")
def hangup(call_id: str, body: HangupIn | None = None):
    body = body or HangupIn()
    sess = SESSIONS.pop(call_id, None)
    call = store.call(call_id)
    if not call:
        raise HTTPException(404, "call not found")
    final = store.finish_call(call_id, {
        "outcome": body.outcome,
        "appointment": sess.appointment if sess else call.get("appointment"),
        "slots": sess.slots if sess else call.get("slots", {}),
        "dnc": bool(sess.dnc) if sess else call.get("dnc", False),
        "next_action": _next_action(sess) if sess else "",
        "summary": llm.summarize_offline(call["transcript"], (sess.slots if sess else call.get("slots", {}))),
    })
    return final


@app.get("/api/calls")
def list_calls(limit: int = 100):
    return list(reversed(store.calls()))[:limit]


@app.get("/api/calls/export.csv")
def export_calls():
    return Response(store.calls_csv(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=calls.csv"})


@app.get("/api/calls/{call_id}")
def get_call(call_id: str):
    call = store.call(call_id)
    if not call:
        raise HTTPException(404, "call not found")
    return call


@app.get("/api/kpis")
def kpis():
    return store.kpis()


@app.get("/api/dashboard")
def dashboard():
    """Everything the dashboard needs in one round-trip."""
    calls = list(reversed(store.calls()))[:20]
    return {
        "kpis": store.kpis(),
        "recent_calls": [{
            "id": c["id"], "lead_name": c["lead_name"], "company": c.get("company", ""),
            "language": c["language"], "outcome": c["outcome"], "duration_s": c["duration_s"],
            "score": c.get("score", 0), "started_at": c["started_at"],
            "appointment": c.get("appointment"), "summary": c.get("summary", ""),
        } for c in calls],
        "leads": store.leads(),
        "settings": store.public_settings(),
    }


# --------------------------------------------------------------- batch simulator
class SimulateIn(BaseModel):
    lead: dict = {"name": "Meera Nair", "company": "Sunrise Public School", "role": "Principal"}
    lines: list[str] = ["yes speaking", "classes 6 to 10, we type papers in Word",
                        "about 40 papers a term", "how much does it cost?",
                        "ok send me details", "priya@sunrise.edu"]
    language: str = "en"


@app.post("/api/simulate")
def simulate(body: SimulateIn):
    """Run a whole call headlessly — used by tests and by the script tuner."""
    lead = {"id": "sim", "name": body.lead.get("name", "there"),
            "phone": body.lead.get("phone", ""), "company": body.lead.get("company", ""),
            "language": body.language}
    sess = Session(call_id="sim-" + uuid.uuid4().hex[:6], lead=lead,
                   settings=store.settings(), lang=body.language)
    eng = engine()
    turns = [{"role": "agent", **eng.opening(sess).as_dict(sess)}]
    for text in body.lines:
        r = eng.respond(sess, text)
        turns.append({"role": "lead", "text": text, "understanding": {
            "intent": r.understanding.intent if r.understanding else None,
            "sentiment": r.understanding.sentiment if r.understanding else 0}})
        turns.append({"role": "agent", **r.as_dict(sess)})
        if r.end_call:
            break
    return {"turns": turns, "slots": sess.slots, "appointment": sess.appointment,
            "end_call": sess.end_call, "dnc": sess.dnc}


# ---------------------------------------------------------------------- TTS (free)
def _tts_available() -> str | None:
    if shutil.which("piper"):
        return "piper"
    if shutil.which("espeak-ng"):
        return "espeak-ng"
    if shutil.which("espeak"):
        return "espeak"
    return None


class TTSIn(BaseModel):
    text: str
    language: str = "en"


@app.post("/api/tts")
def tts(body: TTSIn):
    """Free local speech for the browser channel. If no local engine is installed the
    frontend silently falls back to the browser's own SpeechSynthesis voice."""
    tool = _tts_available()
    if not tool:
        raise HTTPException(501, "no local TTS installed (apt install espeak-ng)")
    voice = {"en": "en-in", "hi": "hi", "bn": "bn"}.get(body.language, "en")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name
    cmd = ([tool, "-v", voice, "-s", "165", "-w", out, body.text[:900]] if tool != "piper"
           else [tool, "--output_file", out])
    try:
        subprocess.run(cmd, check=True, timeout=20, capture_output=True)
        return FileResponse(out, media_type="audio/wav", filename="line.wav")
    except (subprocess.SubprocessError, OSError) as exc:
        raise HTTPException(500, f"tts failed: {exc}") from exc


# ------------------------------------------------------- Twilio phone-call bridge
TWILIO_LANG = {"en": "en-IN", "hi": "hi-IN", "bn": "bn-IN"}


def _twiml(body: str) -> HTMLResponse:
    return HTMLResponse(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>',
                        media_type="application/xml")


def _gather_twiml(text: str, lang: str, call_id: str) -> HTMLResponse:
    voice_lang = TWILIO_LANG.get(lang, "en-IN")
    speak = (text.replace("&", "and").replace("<", "").replace(">", ""))
    action = f"/twilio/turn/{call_id}"
    body = (f'<Gather input="speech" speechTimeout="auto" language="{voice_lang}" '
            f'action="{action}" method="POST" speechModel="phone_call" enhanced="true">'
            f'<Say voice="Polly.Aditi" language="{voice_lang}">{speak}</Say></Gather>'
            f'<Say voice="Polly.Aditi" language="{voice_lang}">Sorry, I did not catch that. Goodbye.</Say>')
    return _twiml(body)


@app.post("/twilio/voice")
async def twilio_voice(request: Request, lead_id: str | None = None):
    """Point a Twilio number's Voice webhook here to make real phone calls.

    TwiML <Gather input="speech"> does the listening, <Say> does the talking, and
    the same DialogEngine writes the words — so the phone call and the browser
    call are the same agent. Twilio trial credit covers testing; no paid STT/TTS
    vendor is needed.
    """
    form = await request.form()
    lead = store.lead(lead_id) if lead_id else None
    if not lead:
        leads = [l for l in store.leads() if not l.get("dnc") and l.get("phone")]
        if not leads:
            return _twiml("<Say>No leads with a phone number are available. Goodbye.</Say>")
        lead = leads[0]
    call = store.start_call(lead, channel="twilio")
    sess = Session(call_id=call["id"], lead=lead, settings=store.settings(),
                   lang=lead.get("language", "en"))
    SESSIONS[call["id"]] = sess
    sid = str(form.get("CallSid", ""))
    if sid:
        TWILIO[sid] = call["id"]
    reply = engine().opening(sess)
    store.append_event(call["id"], {"role": "agent", "text": reply.text, "stage": "OPENING"})
    return _gather_twiml(reply.text, sess.lang, call["id"])


@app.post("/twilio/turn/{call_id}")
async def twilio_turn(call_id: str, request: Request):
    form = await request.form()
    heard = str(form.get("SpeechResult") or "").strip()
    sess = _session(call_id)
    eng = engine()
    if not heard:
        sess.clarify += 1
        if sess.clarify >= 2:
            store.finish_call(call_id, {"outcome": "no_response", "next_action": "Retry later"})
            return _twiml("<Say>I could not hear you. I will try again another time. Goodbye.</Say><Hangup/>")
        return _gather_twiml("Sorry, I did not catch that. Could you say it again?", sess.lang, call_id)

    reply = eng.respond(sess, heard)
    store.append_event(call_id, {"role": "lead", "text": heard, "stage": sess.stage,
                                 "intent": reply.understanding.intent,
                                 "sentiment": reply.understanding.sentiment,
                                 "slots": sess.slots})
    store.append_event(call_id, {"role": "agent", "text": reply.text, "stage": sess.stage})
    if reply.end_call:
        store.finish_call(call_id, {
            "outcome": (reply.debug or {}).get("outcome", "connected"),
            "appointment": reply.appointment, "slots": sess.slots, "dnc": sess.dnc,
            "next_action": _next_action(sess, reply),
            "summary": llm.summarize_offline(store.call(call_id)["transcript"], sess.slots)})
        SESSIONS.pop(call_id, None)
        return _twiml(f'<Say voice="Polly.Aditi" language="{TWILIO_LANG.get(sess.lang)}">'
                      f'{reply.text}</Say><Hangup/>')
    return _gather_twiml(reply.text, sess.lang, call_id)


# ------------------------------------------------------------------------ demo data
@app.post("/api/seed_demo")
def seed_demo():
    return {"added": seed_leads(), "leads": store.leads()}


# ---------------------------------------------------------------------- static app
if FRONTEND.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND), html=True), name="app")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
