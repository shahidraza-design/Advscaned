"""
llm.py — OPTIONAL bring-your-own brain.

The agent works fully without this file. If you switch it on in Settings, any
**OpenAI-compatible** endpoint can take over the free-form answers while the
deterministic policy in dialog.py still owns the call structure (that split is
deliberate: the model talks, the state machine decides what to do next — so a bad
generation can never lose the sale, break compliance, or invent a price).

Works with, for free:
  • Ollama on your own laptop      base_url http://localhost:11434/v1 , model llama3.1
  • Groq free tier                 base_url https://api.groq.com/openai/v1 , model llama-3.3-70b-versatile
  • OpenRouter free models         base_url https://openrouter.ai/api/v1
  • Google AI Studio (free tier)   base_url https://generativelanguage.googleapis.com/v1beta/openai
  • LM Studio / vLLM / llama.cpp   any local OpenAI-compatible server
Nothing here is required to run a call.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

TIMEOUT = 6.0


def _chat(settings: dict, messages: list[dict], max_tokens: int = 220,
          temperature: float = 0.5) -> str | None:
    provider = (settings.get("llm_provider") or "off").lower()
    if provider == "off":
        return None
    base = (settings.get("llm_base_url") or "").rstrip("/")
    if not base:
        return None
    url = base + "/chat/completions"
    body = json.dumps({
        "model": settings.get("llm_model") or "llama3.1",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }).encode()
    headers = {"Content-Type": "application/json"}
    if settings.get("llm_api_key"):
        headers["Authorization"] = f"Bearer {settings['llm_api_key']}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode())
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError, OSError):
        return None


SYSTEM_TELECALLER = (
    "You are {agent}, a warm, concise outbound telecaller for {company}. You speak {lang_name}.\n"
    "Hard rules:\n"
    "- Maximum 2 short sentences. This is a phone call, not an email.\n"
    "- Never invent prices, discounts, customers, or features. If unsure, offer a demo.\n"
    "- Never argue. Acknowledge, then reframe in one clause.\n"
    "- End almost every turn with exactly one question.\n"
    "- Never mention that you are an AI language model.\n"
    "Facts you may use:\n{facts}"
)

LANG_NAME = {"en": "Indian English", "hi": "Hindi (Devanagari)", "bn": "Bengali"}


def answer(settings: dict, kb: list[dict], lang: str, stage: str, question: str,
           history: list[dict]) -> str | None:
    """Free-form answer for a question the scripted policy didn't cover."""
    if (settings.get("llm_provider") or "off") == "off":
        return None
    facts = "\n".join(f"- {k['question']} {k['answer']}" for k in kb[:8])
    facts += (f"\n- Company: {settings.get('company')}\n- Product: {settings.get('product')}"
              f"\n- Offer: {settings.get('offer')}\n- Value: {settings.get('value_prop')}")
    sysmsg = SYSTEM_TELECALLER.format(
        agent=settings.get("agent_name", "Aarohi"), company=settings.get("company", ""),
        lang_name=LANG_NAME.get(lang, "English"), facts=facts)
    msgs = [{"role": "system", "content": sysmsg}]
    for turn in history[-6:]:
        role = "assistant" if turn.get("role") == "agent" else "user"
        msgs.append({"role": role, "content": str(turn.get("text", ""))[:600]})
    msgs.append({"role": "user", "content": f"Stage: {stage}. The customer said: {question}\n"
                                            f"Reply as {settings.get('agent_name', 'Aarohi')} in "
                                            f"{LANG_NAME.get(lang, 'English')}."})
    out = _chat(settings, msgs)
    if not out:
        return None
    out = re.sub(r"^(assistant|agent)\s*:\s*", "", out.strip(), flags=re.I)
    # hard guardrail: one question, phone-length
    sentences = re.split(r"(?<=[.!?।])\s+", out)
    return " ".join(sentences[:2]).strip()[:320] or None


def extract(settings: dict, transcript: list[dict]) -> dict:
    """Structured qualification from the transcript; regex fallback when offline."""
    if (settings.get("llm_provider") or "off") == "off":
        return {}
    convo = "\n".join(f"{t.get('role')}: {t.get('text')}" for t in transcript[-20:])
    prompt = ("Extract sales-qualification fields from this call. Reply with ONLY JSON with keys "
              "role, classes, papers_per_term, current_process, timeline, email, objection, "
              "next_action, summary. Use null when unknown.\n\n" + convo)
    out = _chat(settings, [{"role": "user", "content": prompt}], max_tokens=300, temperature=0)
    if not out:
        return {}
    m = re.search(r"\{.*\}", out, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def coach(settings: dict, stage: str, last_lead: str, slots: dict) -> str | None:
    """One-line live nudge for the human watching the call."""
    if (settings.get("llm_provider") or "off") == "off":
        return None
    prompt = (f"Stage: {stage}. Known: {json.dumps(slots, ensure_ascii=False)}. "
              f"Lead said: '{last_lead}'. In max 12 words, what should the telecaller do next?")
    return _chat(settings, [{"role": "user", "content": prompt}], max_tokens=40, temperature=0.2)


def summarize_offline(transcript: list[dict], slots: dict) -> str:
    """No-model fallback so CRM notes are never empty — and actually readable."""
    bits = []
    if slots.get("role"):
        bits.append(slots["role"])
    if slots.get("org_type"):
        bits.append(slots["org_type"])
    if slots.get("classes"):
        bits.append(f"classes {slots['classes']}")
    if slots.get("papers_per_term"):
        bits.append(f"~{slots['papers_per_term']} papers/term")
    if slots.get("current_process"):
        bits.append(slots["current_process"])
    if slots.get("timeline"):
        bits.append(slots["timeline"])
    if slots.get("email"):
        bits.append(f"email {slots['email']}")

    # the most informative customer line, not a run-on of every utterance
    lead_lines = [t["text"].strip() for t in transcript if t.get("role") == "lead"
                  and len(t.get("text", "").split()) >= 3]
    quote = max(lead_lines, key=len)[:150] if lead_lines else ""
    head = " · ".join(bits) if bits else "little qualification captured"
    return f"{head}. Heard: “{quote}”" if quote else head + "."
