# Telecaller Voice Agent — free, local, multilingual

An outbound calling agent you can actually run today, with **no paid API keys**:
it opens the call, qualifies the lead, handles objections, books a demo slot,
records the outcome in a CRM, and reports its own KPIs.

Works three ways off the same engine:

| Channel | What you need | Cost |
|---|---|---|
| **Browser console** (default) | nothing — open the page and press *Start call* | ₹0 |
| **Real phone calls** | a Twilio number + its free trial credit | ₹0 during trial |
| **Your own telephony / app** | POST to `/api/calls/*` from any client | ₹0 |

Speech in the browser uses the OS/browser engine (Web Speech API). The brain, the
policy, the CRM and the analytics are all local Python. Optional add-ons (a local
LLM, local TTS, Whisper) are listed near the bottom.

---

## Quick start

```bash
cd telecaller/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn app:app --host 0.0.0.0 --port 8000
# open http://localhost:8000/app
```

Four demo leads are seeded on first run (English, Hindi and Bengali). Pick one,
press **Start call**, and either type what the customer says or use the mic.
Allow microphone access once; Chrome/Edge have the best free speech engines.

Three things worth trying first:

1. Call **Meera Nair** (English) and answer honestly — watch the stage advance and
   the qualification panel fill up, then refuse once ("how much does it cost?") and
   see the objection reframe.
2. Call **Sujata Das** and answer in Bengali ("হ্যাঁ বলছি", "ক্লাস ৬ থেকে ১০") — the
   call switches language and the pitch switches with it.
3. Say **"do not call me again"** to anyone — the call stops, the lead is flagged
   DNC and the record shows why.

Run the tests (no pytest needed):

```bash
python test_engine.py      # 23 checks: NLU, compliance, dialog, scoring
```

---

## What makes it a *telecaller* and not a chatbot

`dialog.py` is a sales policy, not a prompt. Every turn it knows the stage, the
goal of that stage, and the one thing it is trying to achieve next.

```
OPENING ──► DISCOVERY ──► PITCH ──► CLOSE ──► WRAP
confirm       qualify       tailor     book      confirm
identity      (role,        benefit    a slot    next step
+ consent     classes,      to what
              volume)       they said
```

Guardrails built into the policy:

* **One question per turn**, and a word budget per stage — it cannot ramble.
* **Never pitches before permission.** A "no" at the opening ends the call.
* **Acknowledge → reframe → ask.** It never argues with an objection.
* **The same objection twice changes the ask** (soft email close) instead of looping.
* **Two clearly negative turns in a row → polite exit.** No chasing.
* **DNC / wrong number / "talk to a human"** are handled before anything else.
* **Low understanding confidence → a short clarifying question**, never a guess.
* **Barge-in aware**: interrupting the agent stops it and switches the turn.

Every agent turn returns the policy reason that produced it (`debug.policy`), so
a supervisor can see *why* the agent said what it said.

## Multilingual

* English, Hindi and Bengali scripts, plus romanised Hinglish ("kitna", "baad me").
* The call **switches language mid-conversation** when the customer's script
  changes, with a one-line bridge ("जी, हिंदी में बात करते हैं।").
* Business facts are localised too, so a Hindi call doesn't suddenly speak English.
* Numerals in Devanagari/Bengali (४०, ৪০) are normalised before parsing.

The whole script lives in `scripts.py` — every sentence in three languages, plus
the objection library and the quick replies. A non-developer can rewrite the
offer without touching code.

## Understanding (no model, no cost)

`nlu.py` is ~400 lines of deliberate, explainable rules:

* **Intent** — 70+ phrase lists scored longest-first, with span masking, so
  "not interested" can never also fire "interested".
* **Script-safe boundaries** — Bengali "থেকে" does not fire the word "কে" (*who*).
* **Entities** — email (including "priya at sunrise dot edu"), phone, class range,
  papers-per-term, subject, role, current process, timeline, and a bookable slot
  ("kal 4 baje" → "कल 4 बजे").
* **Sentiment** — negations and intensifiers included ("very useful" > "useful").
* **Knows when not to classify** — an answer like "classes 6 to 10, we type papers
  in Word" is an *answer*, not noise, even though it matches no intent keyword.

Typical latency: **< 1 ms per turn**. That is why the agent feels instant.

## The console

* Stage timeline with the live objective for each stage.
* Intent + confidence, ranked alternatives, sentiment gauge.
* Live qualification panel (role, classes, volume, process, email, appointment).
* Live coaching line, talk ratio, barge-in counter.
* Compliance panel: consent, recording notice, DNC state.
* Leads table with consent/DNC flags, CSV import/export, one-click call.
* Dashboard: connect rate, booking rate, average score, sentiment, outcomes,
  languages, and every call's summary + next action.

## CRM and analytics

`store.py` keeps plain JSON files in `telecaller/data/` — human readable,
git-diffable, no database to run.

* Every call stores its full transcript, stage timeline, slots, sentiment series,
  appointment, outcome, talk ratio and a **0–100 lead score**.
* Each finished call gets a **summary** and a **next action** ("Send calendar
  invite for tomorrow at 4 pm + WhatsApp confirmation").
* CSV export for both leads and calls.
* Swap `store.py` for Postgres/Supabase later; nothing else touches storage.

---

## Real phone calls with Twilio (free trial credit)

1. Buy/claim a number in the Twilio console (trial credit covers testing).
2. Set the number's **Voice → A call comes in** webhook to
   `https://<your-public-host>/twilio/voice` (POST).
3. Expose your laptop with any tunnel, e.g. `cloudflared tunnel --url http://localhost:8000`.
4. Optional: pass a lead with `?lead_id=<id>` so the agent calls the right person
   with the right language.

The bridge uses `<Gather input="speech">` for listening and `<Say>` for speaking,
and the *same* `DialogEngine` writes the words — the phone agent and the browser
agent are one agent. No paid STT/TTS vendor is required for a working call.

For production telephony you would swap `<Gather>` for Twilio **Media Streams**
(WebSocket audio) and stream a local ASR/TTS — see the roadmap.

## Optional: your own LLM (still free if it runs locally)

Settings → *Optional AI brain*:

| Provider | Base URL | Model | Cost |
|---|---|---|---|
| Ollama (local) | `http://localhost:11434/v1` | `llama3.1` / `qwen2.5` | free |
| LM Studio / vLLM / llama.cpp | your server | your model | free |
| Groq free tier | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` | free tier |
| Google AI Studio | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.0-flash` | free tier |
| OpenAI / OpenRouter | their URL | their model | paid / free models |

Deliberate split: **the model talks, the state machine decides**. The LLM only
improves free-form answers, post-call extraction and the coaching line; it can
never invent a price, skip consent, or lose the close. If the endpoint is down,
the call continues on the deterministic engine without a hiccup.

## Optional: local TTS for more natural audio

```bash
sudo apt install espeak-ng        # instantly recognised by /api/tts
# or a neural voice, fully offline:
#   pip install piper-tts && download an Indic .onnx voice
```
The browser channel falls back to the built-in `SpeechSynthesis` voice when no
local engine is installed, so nothing breaks without it.

---

## API

| Method & path | Purpose |
|---|---|
| `POST /api/calls/start` | Start a call for a lead → opening line, stage, chips |
| `POST /api/calls/{id}/turn` | Send one customer utterance → reply, policy, coach, slots |
| `POST /api/calls/{id}/hangup` | End manually and finalise the record |
| `POST /api/simulate` | Run a whole scripted call headlessly (tests, script tuning) |
| `GET /api/dashboard` | KPIs + recent calls + leads + settings in one call |
| `GET/PUT /api/settings` | Agent personality, offer, LLM config |
| `GET/PUT /api/kb` | FAQ the agent is allowed to quote |
| `GET/POST/PATCH/DELETE /api/leads` | Calling list, DNC and consent flags |
| `POST /api/leads/import`, `GET /api/leads/export.csv` | CSV in / out |
| `GET /api/calls`, `/api/calls/{id}`, `/api/calls/export.csv` | Records |
| `POST /api/tts` | Local speech (if espeak/piper installed) |
| `POST /twilio/voice`, `/twilio/turn/{id}` | TwiML phone bridge |

`POST /api/simulate` is the fastest way to tune the script:

```bash
curl -s localhost:8000/api/simulate -H 'content-type: application/json' -d '{
  "lead": {"name": "Meera", "company": "Sunrise School"},
  "lines": ["yes speaking", "classes 6 to 10", "40 papers a term",
            "how much does it cost", "ok, tomorrow 4 pm works"]}' | python -m json.tool
```

## Compliance notes

Built in: Do-Not-Call honouring, wrong-number exit, consent flag per lead,
recording notice, human handoff, and a polite exit after repeated objections.
You still own the legal side in your jurisdiction — in India that means TRAI's
UCC regulations (no calls before 9 am / after 9 pm, DND registry checks, and
consent for recordings). The settings expose `calling_hours` for that reason; a
production deployment should enforce it and scrub numbers against the DND list
before dialling.

## Deployment & security

The server is deliberately one command and one port, but before putting it on the
public internet:

* **There is no login.** Anyone who can reach the port can read leads and start
  calls. Keep it on localhost/LAN, or put it behind your own auth (basic auth at
  a reverse proxy, or a session middleware).
* LLM API keys are stored server-side in `telecaller/data/settings.json` and are
  never sent back to the browser — but that file is plain JSON, so treat the
  machine as a secret store.
* `telecaller/data/` is gitignored on purpose; it contains customer phone numbers.
* Set `TELECALLER_DATA=/var/lib/telecaller` to keep runtime data outside the repo.
* `calling_hours` in settings is informational — enforce it in your dialler, along
  with a DND scrrub, before dialling at scale.

## Free stack, at a glance

| Layer | Default (free) | Upgrade path |
|---|---|---|
| Speech → text | browser Web Speech API / Twilio `<Gather>` | faster-whisper, Vosk, Deepgram credits |
| Understanding | rule-based NLU (`nlu.py`) | LLM function-calling for long tail |
| Policy | deterministic stage machine (`dialog.py`) | same, kept as the guardrail |
| Text → speech | browser `SpeechSynthesis` / Twilio `<Say>` | Piper, Coqui XTTS, ElevenLabs |
| Telephony | browser + Twilio trial | Exotel/Plivo/Knowlarity SIP |
| Storage | JSON files | Postgres / Supabase |
| Hosting | your laptop | any free-tier container |

## Roadmap (in rough order of impact)

1. **Streaming ASR + TTS over WebRTC** (Pipecat or LiveKit) → sub-400 ms turn latency.
2. **Whisper.cpp / faster-whisper** locally for noisy phone audio and Hinglish code-mixing.
3. **Indic neural voices** — Piper or XTTS Hindi/Bengali models, sentence-streamed.
4. **Real calendar + WhatsApp** actions (Cal.com API, WhatsApp Cloud API free tier).
5. **DND scrub + calling-hours enforcement** before dialling, and a call-quality QA pass.
6. **A/B script testing** using `/api/simulate` against persona scripts before a live campaign.

## Files

```
telecaller/
├── backend/
│   ├── app.py          FastAPI server, Twilio bridge, TTS, demo seeding
│   ├── dialog.py       call policy: stages, objections, booking, compliance
│   ├── nlu.py          intents, entities, sentiment — 3 scripts, no models
│   ├── scripts.py      every sentence in en/hi/bn + objection library
│   ├── llm.py          optional OpenAI-compatible brain + offline summaries
│   ├── store.py        JSON CRM, call scoring, KPIs, CSV
│   ├── test_engine.py  23 regression tests
│   └── requirements.txt
├── frontend/           console (no build step, no framework)
└── data/               generated JSON: settings, leads, calls, knowledge
```
