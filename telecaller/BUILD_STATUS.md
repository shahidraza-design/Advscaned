# Build status & what's needed before selling

_Written 31 Oct 2026. This is an honest engineering assessment of `telecaller/`,
not marketing copy._

## The one-paragraph version

The **conversation brain is real and production-shaped**: a deterministic call
policy, a 3-language NLU, objection handling, qualification, slot booking,
compliance gates, call scoring and a test suite. The **infrastructure around it is
demo-grade**: JSON files, no login, no dialler, no call recording, no real-time
audio streaming, and the follow-up actions it promises (WhatsApp, calendar,
email) are recorded but not executed. So: **demoable to a school tomorrow,
sellable as a done-for-you pilot in ~6–8 weeks, sellable as a self-serve product
in ~4–6 months.**

---

## 1. How a call works today

### Browser channel (what runs right now, free)

```
you speak / type
      │
      ▼
Web Speech API (browser)  ──►  POST /api/calls/{id}/turn  {text, interrupted}
                                          │
                                          ▼
                          ┌───────────────────────────────┐
                          │ nlu.understand()              │  intent, entities,
                          │ ~0.5 ms, no model             │  sentiment, slot
                          └───────────────┬───────────────┘
                                          ▼
                          ┌───────────────────────────────┐
                          │ dialog.DialogEngine.respond()  │  stage policy,
                          │ OPEN→DISCOVER→PITCH→CLOSE→WRAP │  objections, booking,
                          │ compliance gates first         │  word budget
                          └───────────────┬───────────────┘
                                          ▼
                     reply text + stage + policy + slots + actions + coach
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    ▼                                           ▼
        browser speechSynthesis                       store.py (JSON CRM)
        (or /api/tts if espeak/piper)                 transcript, score, summary,
                                                      next action, KPIs
```

Barge-in: if recognition returns a result while the agent is speaking, the
browser cancels speech and the turn is sent with `interrupted: true`.

### Phone channel (Twilio, trial credit)

```
inbound/outbound PSTN call
      │
      ▼
POST /twilio/voice  ──►  TwiML <Gather input="speech"> + <Say>
      │                            ▲
      ▼                            │
POST /twilio/turn/{call_id} ───────┘   same DialogEngine, same CRM
```

Turn-taking is TwiML-based: the customer speaks, `<Gather>` closes the turn,
the engine answers, `<Gather>` reopens. No audio streaming, so no true barge-in
and roughly 1.5–3 s of dead air per turn.

### What a real call looks like

1. **OPENING** — "Hi, this is Aarohi from Advscaned. Am I speaking with Meera?
   I'll take just thirty seconds — is now a good time?" Handles *who is this*,
   *busy*, *not interested*, *wrong number*, *do not call*.
2. **DISCOVERY** — two qualifying questions: classes/papers today, then volume.
   Extracts role, class range, papers per term, current process, timeline.
3. **PITCH** — picks the big-school or small-school benefit and ties it to the
   number it just heard.
4. **CLOSE** — two concrete slots, books whichever the customer names, or takes
   an email for a follow-up.
5. **WRAP** — confirms the next step in one line and ends.

Every turn is logged with the policy reason (`debug.policy`), intent confidence
and sentiment. The finished call gets a 0–100 score, a summary, and a next action.

---

## 2. What is built (and verified)

| Area | Status | Where |
|---|---|---|
| Stage machine with per-stage goal + word budget + one-question rule | ✅ | `backend/dialog.py` |
| Objection library (price, vendor, budget, time, "send info", "already tried") + repeat guard | ✅ | `dialog.py`, `scripts.py` |
| Qualification → adaptive pitch → booking → callback → email capture | ✅ | `dialog.py` |
| DNC, wrong number, consent, human-handoff flag, negative-sentiment exit | ✅ | `dialog.py` |
| Intent + entity + sentiment NLU, en/hi/bn + Hinglish, Indic numerals, spoken emails, slot phrasing | ✅ | `backend/nlu.py` |
| Mid-call language switching with a bridge line | ✅ | `dialog.py` |
| Script layer: every sentence in 3 languages, editable without code | ✅ | `backend/scripts.py` |
| Browser voice loop, barge-in, hands-free mode, typing fallback | ✅ | `frontend/app.js` |
| Twilio TwiML phone bridge | ✅ (basic) | `app.py` |
| CRM: leads, DNC/consent flags, transcripts, scoring, summary, next action | ✅ | `backend/store.py` |
| KPIs + dashboard + CSV import/export | ✅ | `app.py`, `frontend` |
| Editable knowledge base used for FAQ answers | ✅ (lexical retrieval) | `store.py`, `dialog.py` |
| Optional OpenAI-compatible LLM (Ollama/Groq/Gemini) for free-form answers, extraction, coaching | ✅ (off by default) | `backend/llm.py` |
| Regression tests: 23 checks incl. "never silent", "DNC never books", "no objection loop" | ✅ | `backend/test_engine.py` |
| Local TTS hook (espeak/Piper) | ✅ code, ⚠️ not installed in this sandbox | `POST /api/tts` |
| Docs, run script, auto-seeded demo leads | ✅ | `README.md`, `run.sh` |

**Verified now:** 23/23 tests pass; a full 5-turn English, Hindi and Bengali call
books a demo and persists a scored record; `/api/calls/export.csv`, `/api/dashboard`,
lead import/export and the Twilio TwiML render all respond correctly.

---

## 3. What it cannot do today

| Capability | Reality |
|---|---|
| True real-time phone audio | ❌ no streaming; TwiML turns only, ~1.5–3 s latency |
| Barge-in on the phone | ❌ (works in the browser only) |
| Voicemail / answering-machine detection | ❌ |
| Gatekeeper handling ("principal is not available") | ❌ receptionist is treated as the lead |
| Outbound dialler, retries, attempt caps, campaign scheduling | ❌ calls are started by hand |
| Enforced calling hours | ❌ setting exists, nothing enforces it |
| DND/NCPR scrubbing | ❌ |
| Call recording (audio) | ❌ text transcript only |
| Sending the promised email / WhatsApp / calendar invite | ❌ actions are emitted, never executed |
| Login, roles, multi-tenancy, audit log | ❌ |
| Twilio webhook signature validation | ❌ anyone who can reach the URL can start calls |
| Callback queue / no-show tracking | ❌ callback is only a note |
| Native review of Hindi/Bengali sales copy | ⚠️ written by me, needs a native salesperson |
| Natural Indic voices | ⚠️ browser/Twilio voices only, average quality |
| Robust ASR for Hinglish / noisy phone lines | ⚠️ browser STT weak; Twilio `phone_call` decent |
| Long-tail natural language | ⚠️ rule-based NLU covers the sales conversation, not open chat |

---

## 4. Before you sell to a business — blockers

### A. Legal & compliance (India) — these are hard blockers, not nice-to-haves

| Requirement | Why it matters | Status |
|---|---|---|
| **DLT / Principal-Entity registration** on a carrier portal | mandatory before any commercial outbound calling | ❌ not started |
| **140-series CLI** for promotional calls | calling from a normal 10-digit number is a direct violation | ❌ |
| **NCPR/DND scrub before every campaign** | DND registration overrides prior engagement | ❌ |
| **9 AM–9 PM IST hard gate, enforced in code** | calls outside the window are per-se violations | ❌ (setting unused) |
| **Consent with timestamp + purpose** (DPDP Act 2023) | explicit, purpose-specific consent required | ⚠️ boolean + note only |
| **Opt-out honoured across the whole system** | DNC flag exists per lead, no global suppression list | ⚠️ |
| **Call recording consent + retention policy + erasure** | DPDP data-minimisation and erasure duties | ❌ |
| **DPA / sub-processor list** for your customers | schools will ask before signing | ❌ |
| **Grievance officer / complaint handling** | TRAI complaints escalate fast | ❌ |

Sources: TRAI TCCCPR 2018 + 2025 amendments (140-series, DLT, 9am–9pm, DND scrub);
DPDP Act 2023 (consent, purpose limitation, erasure). Penalties run to lakhs and
number blocking. Get a lawyer to confirm your exact obligations — this table is
engineering reading, not legal advice.

**Practical consequence:** you cannot cold-call schools from your own mobile
number today, even with a perfect agent. For demos, call yourself, your team, or
someone who has explicitly agreed.

### B. Voice & telephony quality — what makes it feel human

1. **Streaming audio (WebRTC / Twilio Media Streams)** with VAD and endpointing →
   sub-400 ms turns and real barge-in. This is the single biggest quality jump.
2. **Better ASR for Indian speech** — streaming Whisper (local), Deepgram, or a
   Sarvam/AI4Bharat model. Hinglish code-mixing is the hard case.
3. **Neural Indic TTS** — Piper (free, local) or a hosted voice. Browser voices
   for Bengali are missing on many devices.
4. **Read-back confirmation** for critical data: "so that's 4 pm tomorrow, and
   p-r-i-y-a at sunrise dot edu — right?" Numbers and emails are misheard most.
5. **Voicemail + AMD** so the agent doesn't pitch a machine.
6. **Gatekeeper branch**: "I'll hold for the principal" → different mini-script.

### C. Product / operations

* **Dialler + campaign runner**: queues, concurrency limits, retry ladder
  (ring-no-answer vs busy vs hung-up), max 3 attempts/day, dedupe, E.164
  validation, global DNC suppression list, per-day caps.
* **Calling-hours + holiday calendar enforced in code**, with a hard stop.
* **Recording + transcript search + QA workflow**: listen, tag, flag, coach.
* **Human handoff that actually transfers** (warm transfer via Twilio `<Dial>`).
* **Callback scheduler** (a note is not a callback).
* **Show-up tracking**: did the demo actually happen? Needs calendar integration.

### D. Integrations that make the booked meeting real

The current close says "I'll send the meeting link on WhatsApp" — nothing sends
it. Before a pilot you need at minimum:

* Google Calendar / Cal.com booking + invite email,
* WhatsApp Cloud API or an SMS fallback,
* email (SMTP/SES) with the one-pager,
* a webhook out to the customer's CRM (Zoho/HubSpot are what Indian schools'
  sales teams actually use).

Until then, a human must action every "next action" — which is fine for a
done-for-you pilot but must be stated.

### E. Security, data, multi-tenancy

* login + roles (agent, supervisor, admin), per-tenant data isolation,
* Twilio signature validation, rate limiting, idempotency keys,
* encryption at rest for transcripts (they contain names, phone numbers, emails),
* audit log, retention job, "delete this lead/call" endpoint,
* Postgres instead of JSON; sessions that survive a restart,
* HTTPS, secrets in a manager (not `settings.json`),
* structured logs + metrics + error tracking.

### F. Commercial readiness

* pricing model (per booked demo vs per seat vs per minute) and a cost model,
* pilot agreement, DPA, SLA/support terms,
* onboarding: upload leads, pick language, approve script, set calling window,
* a security-questionnaire answer sheet (schools and their trusts ask),
* success metrics + an ROI one-pager ("a 40-paper term × 2 hours per paper"),
* reference script per segment (K-12 vs coaching vs college) — the same script
  will not work for all three,
* native review of Hindi/Bengali copy and of agent name/voice for the region.

---

## 5. Effort to get to each milestone

Rough, assuming 1–2 engineers and that DLT/carrier paperwork runs in parallel.

| Milestone | Work | Time |
|---|---|---|
| **Credible demo** | today (browser only, your own numbers) | done |
| **Compliant single-customer pilot** | auth + Postgres, signature validation, DND scrub, 9–9 hard gate, recording + consent records, read-back confirmation, calendar/WhatsApp/email actions, dialler with retries | **6–8 weeks** |
| **Real-time voice** | Media Streams/WebRTC, streaming ASR, neural TTS, VAD/endpointing, barge-in, latency tuning | **3–5 weeks** (can run in parallel) |
| **Pilot with 1–2 schools** | 200–500 real calls, script iteration, QA reviews, metric baselines | **4–6 weeks** |
| **Self-serve product** | multi-tenant, billing/metering, self-onboarding, SOC2-lite controls, support process | **4–6 months total** |

**Definition of done for "sellable pilot":** a school's coordinator can be called
between 10am and 7pm from a 140-series number, the call is recorded with consent,
the lead is DND-scrubbed first, the demo invite lands in their calendar and on
WhatsApp within a minute, the transcript and recording are reviewable, and every
call's outcome is in the dashboard with a cost figure attached.

---

## 6. Variable cost per call (order of magnitude)

| Component | Free option | Paid option (verify current rates) |
|---|---|---|
| Telephony | — | Twilio India ≈ ₹4–9/min; domestic carriers (Exotel/Plivo) ≈ ₹0.5–1.5/min |
| ASR | browser / Vosk / local Whisper | cloud streaming ≈ ₹1–3/min |
| TTS | browser / Piper (local) | neural Indic ≈ ₹2–8/min |
| LLM | Ollama / Groq / Gemini free tiers | ≈ ₹0–1 per call |
| Hosting | laptop / free tier | VPS ₹500–2,000/month |
| Compliance | — | DLT + 140-series header: few thousand ₹ one-time |

A 2-minute conversation lands around **₹10–40 in variable cost** on the cheap
path. At a 5–10% booking rate that is **₹200–800 per booked demo** — which is the
number to compare against a human SDR's cost per meeting.

---

## 7. What I would do next, in order

1. **Decide the commercial shape.** Done-for-you pilot (fastest revenue, honest
   given the gaps) vs self-serve SaaS (needs everything in §B–§E).
2. **Start DLT registration now** — it gates real outbound calling and takes time.
3. **Harden the pilot path** (§4A/§4D/§4E-list): auth, Postgres, signature
   validation, DND + calling window, recording + consent, real calendar/WhatsApp/
   email actions.
4. **Instrument and measure** on 100–200 calls before touching the voice stack:
   connect → qualified → booked → showed, objection mix, cost per booking.
5. **Then** upgrade audio to streaming ASR/TTS with barge-in — it improves
   conversion, but only after you can measure conversion.
6. **Iterate the script per segment** (K-12 / coaching / college) using
   `/api/simulate` offline, then A/B on live calls.

---

## 8. Risks worth naming

* **Compliance risk is existential**, not cosmetic: one complaint can blacklist a
  number block. Automate the gates before scaling.
* **Rule-based NLU has a ceiling.** It is excellent inside the sales script and
  weak outside it; collect real utterances and expand, or add LLM fallback with
  strict output validation.
* **LLM path can hallucinate** prices/features. Current design keeps the policy in
  charge and the LLM only decorates, but free-form answers still need review.
* **Voice quality is the product** for a phone agent. Average audio will cap
  conversion no matter how good the policy is.
* **Schools buy slowly** (trusts, committees, academic calendars). A pilot may
  take a term to prove itself; plan cash accordingly.
