"""
store.py — tiny, dependency-free persistence.

Everything is plain JSON on disk, so the whole CRM is human-readable, git-friendly
and trivially re-exportable. Swap this file for Postgres later; nothing else in the
app touches storage directly.

  data/settings.json   agent personality, business facts, LLM + telephony keys
  data/leads.json      the calling list (with DNC + consent flags)
  data/calls.json      one record per call: transcript, outcome, appointment, KPIs
  data/knowledge.json  product FAQ the agent may quote (feeds retrieval)
"""
from __future__ import annotations

import csv
import io
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from scripts import BUSINESS_DEFAULTS

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(path)


class Store:
    def __init__(self, root: str | Path = "data"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.leads_path = self.root / "leads.json"
        self.calls_path = self.root / "calls.json"
        self.settings_path = self.root / "settings.json"
        self.kb_path = self.root / "knowledge.json"
        if not self.settings_path.exists():
            _write(self.settings_path, BUSINESS_DEFAULTS)
        if not self.kb_path.exists():
            _write(self.kb_path, DEFAULT_KB)
        if not self.leads_path.exists():
            _write(self.leads_path, [])
        if not self.calls_path.exists():
            _write(self.calls_path, [])

    # ------------------------------------------------------------- settings
    def settings(self) -> dict:
        s = {**BUSINESS_DEFAULTS, **_read(self.settings_path, {})}
        # never leak secrets to the browser
        return s

    def save_settings(self, patch: dict) -> dict:
        with _LOCK:
            cur = {**BUSINESS_DEFAULTS, **_read(self.settings_path, {})}
            for k, v in patch.items():
                if k in BUSINESS_DEFAULTS:
                    cur[k] = v
            _write(self.settings_path, cur)
            return cur

    def public_settings(self) -> dict:
        s = self.settings()
        s["llm_api_key_set"] = bool(s.get("llm_api_key"))
        s.pop("llm_api_key", None)
        return s

    # ----------------------------------------------------------------- leads
    def leads(self) -> list[dict]:
        return _read(self.leads_path, [])

    def lead(self, lead_id: str) -> dict | None:
        return next((l for l in self.leads() if l["id"] == lead_id), None)

    def add_lead(self, lead: dict) -> dict:
        with _LOCK:
            leads = self.leads()
            new = {
                "id": uuid.uuid4().hex[:10],
                "name": (lead.get("name") or "there").strip(),
                "phone": (lead.get("phone") or "").strip(),
                "company": (lead.get("company") or "").strip(),
                "role": (lead.get("role") or "").strip(),
                "language": lead.get("language") or "en",
                "notes": lead.get("notes") or "",
                "status": "new",           # new | calling | connected | booked | callback | dnc | wrong
                "dnc": bool(lead.get("dnc", False)),
                "consent": bool(lead.get("consent", False)),
                "attempts": 0,
                "last_call": None,
                "score": 0,
                "created": _now(),
            }
            leads.append(new)
            _write(self.leads_path, leads)
            return new

    def update_lead(self, lead_id: str, patch: dict) -> dict | None:
        with _LOCK:
            leads = self.leads()
            for i, l in enumerate(leads):
                if l["id"] == lead_id:
                    leads[i] = {**l, **{k: v for k, v in patch.items() if k != "id"}}
                    _write(self.leads_path, leads)
                    return leads[i]
        return None

    def delete_lead(self, lead_id: str) -> bool:
        with _LOCK:
            leads = self.leads()
            kept = [l for l in leads if l["id"] != lead_id]
            _write(self.leads_path, kept)
            return len(kept) != len(leads)

    def import_leads_csv(self, text: str, language: str = "en") -> list[dict]:
        reader = csv.DictReader(io.StringIO(text))
        out = []
        for row in reader:
            low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not low.get("phone"):
                continue
            out.append(self.add_lead({
                "name": low.get("name") or "there",
                "phone": low["phone"],
                "company": low.get("company") or low.get("school") or "",
                "role": low.get("role") or "",
                "language": low.get("language") or language,
                "notes": low.get("notes") or "",
                "consent": low.get("consent", "").lower() in {"1", "yes", "true"},
            }))
        return out

    def leads_csv(self) -> str:
        buf = io.StringIO()
        fields = ["id", "name", "phone", "company", "role", "language", "status",
                  "dnc", "consent", "attempts", "score", "last_call"]
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for l in self.leads():
            w.writerow(l)
        return buf.getvalue()

    # ----------------------------------------------------------------- calls
    def calls(self) -> list[dict]:
        return _read(self.calls_path, [])

    def call(self, call_id: str) -> dict | None:
        return next((c for c in self.calls() if c["id"] == call_id), None)

    def start_call(self, lead: dict, channel: str = "browser", script: str = "default") -> dict:
        with _LOCK:
            calls = self.calls()
            call = {
                "id": uuid.uuid4().hex[:10],
                "lead_id": lead.get("id"),
                "lead_name": lead.get("name"),
                "company": lead.get("company", ""),
                "phone": lead.get("phone", ""),
                "channel": channel,
                "script": script,
                "language": lead.get("language", "en"),
                "started_at": _now(),
                "ended_at": None,
                "duration_s": 0,
                "outcome": "in_progress",
                "stage": "OPENING",
                "appointment": None,
                "slots": {},
                "consent": False,
                "dnc": False,
                "sentiment_series": [],
                "transcript": [],
                "agent_words": 0,
                "lead_words": 0,
                "interruptions": 0,
                "score": 0,
                "next_action": "",
            }
            calls.append(call)
            _write(self.calls_path, calls)
        self.update_lead(lead["id"], {"status": "calling", "last_call": _now(),
                                      "attempts": (lead.get("attempts") or 0) + 1})
        return call

    def append_event(self, call_id: str, event: dict) -> dict | None:
        with _LOCK:
            calls = self.calls()
            for i, c in enumerate(calls):
                if c["id"] == call_id:
                    c["transcript"].append({"ts": _now(), **event})
                    if event.get("role") == "agent":
                        c["agent_words"] += len(str(event.get("text", "")).split())
                    elif event.get("role") == "lead":
                        c["lead_words"] += len(str(event.get("text", "")).split())
                        if event.get("sentiment") is not None:
                            c["sentiment_series"].append(event["sentiment"])
                    if event.get("stage"):
                        c["stage"] = event["stage"]
                    if event.get("interruption"):
                        c["interruptions"] += 1
                    _write(self.calls_path, calls)
                    return calls[i]
        return None

    def finish_call(self, call_id: str, patch: dict) -> dict | None:
        with _LOCK:
            calls = self.calls()
            for i, c in enumerate(calls):
                if c["id"] == call_id:
                    ended = _now()
                    start = datetime.fromisoformat(c["started_at"])
                    dur = max(0, int((datetime.fromisoformat(ended) - start).total_seconds()))
                    upd = {**patch, "ended_at": ended,
                           "duration_s": patch.get("duration_s") or dur}
                    upd["talk_ratio"] = round(
                        upd.get("agent_words", c["agent_words"]) /
                        max(1, (upd.get("agent_words", c["agent_words"]) +
                                upd.get("lead_words", c["lead_words"]))), 2)
                    upd["score"] = score_call(upd, c)
                    calls[i] = {**c, **upd}
                    _write(self.calls_path, calls)
                    finished = calls[i]
                    break
            else:
                return None
        if finished.get("lead_id"):
            status_map = {
                "booked": "booked", "callback": "callback", "not_interested": "connected",
                "dnc": "dnc", "wrong_number": "wrong", "connected": "connected",
            }
            self.update_lead(finished["lead_id"], {
                "status": status_map.get(finished["outcome"], "connected"),
                "dnc": finished.get("dnc", False) or finished.get("outcome") == "dnc",
                "score": finished.get("score", 0),
            })
        return finished

    def calls_csv(self) -> str:
        buf = io.StringIO()
        fields = ["id", "lead_name", "company", "phone", "language", "channel", "started_at",
                  "duration_s", "outcome", "stage", "appointment", "consent", "dnc",
                  "score", "interruptions", "talk_ratio", "next_action"]
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for c in self.calls():
            row = {**c, "appointment": json.dumps(c.get("appointment") or {}, ensure_ascii=False)}
            w.writerow(row)
        return buf.getvalue()

    # ------------------------------------------------------------- knowledge
    def kb(self) -> list[dict]:
        return _read(self.kb_path, [])

    def save_kb(self, rows: list[dict]) -> list[dict]:
        with _LOCK:
            _write(self.kb_path, rows)
            return rows

    # ------------------------------------------------------------------- kpis
    def kpis(self) -> dict:
        calls = [c for c in self.calls() if c["outcome"] != "in_progress"]
        leads = self.leads()
        connected = [c for c in calls if c["outcome"] not in {"no_answer", "failed"}]
        booked = [c for c in calls if c["outcome"] == "booked"]
        senti = [s for c in calls for s in c.get("sentiment_series", [])]
        return {
            "leads": len(leads),
            "calls": len(calls),
            "connected": len(connected),
            "connect_rate": round(len(connected) / max(1, len(calls)) * 100),
            "appointments": len(booked),
            "booking_rate": round(len(booked) / max(1, len(connected)) * 100),
            "avg_duration_s": round(sum(c.get("duration_s", 0) for c in calls) / max(1, len(calls))),
            "avg_sentiment": round(sum(senti) / len(senti), 2) if senti else 0,
            "dnc": len([l for l in leads if l.get("dnc")]),
            "avg_score": round(sum(c.get("score", 0) for c in calls) / max(1, len(calls))),
            "by_language": _count(calls, "language"),
            "by_outcome": _count(calls, "outcome"),
        }


def _count(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[str(r.get(key) or "—")] = out.get(str(r.get(key) or "—"), 0) + 1
    return out


def score_call(call: dict, previous: dict) -> int:
    """0-100 lead quality score, computed the same way an SDR would eyeball it."""
    pts = 0
    slots = call.get("slots") or previous.get("slots") or {}
    if call.get("outcome") == "booked":
        pts += 55
    elif call.get("outcome") == "callback":
        pts += 25
    if slots.get("classes"):
        pts += 10
    if slots.get("papers_per_term"):
        pts += 8
    if slots.get("role", "").lower() in {"principal", "director", "owner", "trustee", "vice principal"}:
        pts += 12
    if slots.get("email"):
        pts += 8
    if call.get("consent"):
        pts += 5
    senti = call.get("sentiment_series") or previous.get("sentiment_series") or []
    if senti:
        pts += int(max(-10, min(12, sum(senti) / len(senti) * 12)))
    if call.get("duration_s", 0) and call["duration_s"] > 90:
        pts += 5
    if call.get("outcome") in {"dnc", "not_interested"}:
        pts -= 25
    return max(0, min(100, pts))


DEFAULT_KB = [
    {"id": "kb1", "question": "How does it work?",
     "answer": "A teacher photographs the chapter. The app finds every question, and attaches the diagram, formula or table that belongs to it. The teacher ticks what they want and exports a Word or PDF paper."},
    {"id": "kb2", "question": "Which languages are supported?",
     "answer": "The interface and the generated paper work in English, Hindi and Bengali; OCR runs in whatever language packs are installed, so mixed Hindi-English chapters work too."},
    {"id": "kb3", "question": "Does it work offline?",
     "answer": "Yes. The whole pipeline can run on a single laptop with no internet, which is why schools with weak connectivity use it."},
    {"id": "kb4", "question": "What about diagrams and equations?",
     "answer": "Diagrams, tables and formulas are cropped from the page and placed next to the question they belong to; equations are converted to real Word equations, not pictures."},
    {"id": "kb5", "question": "Pricing?",
     "answer": "The two-week pilot is free — one subject, one class. After that it is an annual per-school licence; exact pricing depends on student count and is shared on the demo."},
    {"id": "kb6", "question": "Is student data stored?",
     "answer": "No student data is needed. Only the textbook page images are processed, they stay on the school's machine or the school's server, and any document can be deleted on request."},
]
