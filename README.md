# Advscaned

Two independent, free-and-open-source projects in one repository.

## 1. `telecaller/` — Telecaller voice agent  ← new

An outbound calling agent that runs on your laptop with **no paid API keys**:
it opens the call, qualifies the lead, handles objections, books a demo, and
reports its own KPIs. English, Hindi and Bengali, with mid-call language switching.

* Works in the **browser** (free), over **real phone calls** via Twilio trial
  credit, or as an **API** your own app can drive.
* Deterministic call policy (OPENING → DISCOVERY → PITCH → CLOSE → WRAP) with a
  per-stage goal, a word budget and a one-question rule — plus DNC, consent,
  wrong-number and human-handoff compliance.
* Optional local LLM (Ollama / any OpenAI-compatible endpoint) improves free-form
  answers, extraction and coaching, but the state machine always stays in charge.
* CRM + analytics included: lead scoring, call summaries, next actions, CSV
  export, live coaching panel.

```bash
cd telecaller/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000
# open http://localhost:8000/app
```

Full documentation, API reference, Twilio setup and the free-stack table:
**[`telecaller/README.md`](telecaller/README.md)**

## 2. `qpaper-backend.zip` — Question Paper Builder backend

Photo of a textbook page → question "packages" (question + its diagrams/formulas)
→ teacher ticks questions → editable Word or PDF. FastAPI + DocLayout-YOLO +
Tesseract + pix2tex + pandoc. Unzip it and read the README inside; it has its own
setup instructions.

---

Both projects are self-contained: separate dependencies, separate data
directories, nothing shared but the repository.
