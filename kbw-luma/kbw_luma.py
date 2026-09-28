#!/usr/bin/env python3
"""Find Korea Blockchain Week side events on Luma and register for them.

Usage:
  python kbw_luma.py list   [filters]
  python kbw_luma.py apply  [filters] [--go]
  python kbw_luma.py whoami

Auth: set LUMA_SESSION to the value of the `luma.auth-session-key` cookie
from a browser where you're logged in to luma.com.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

API = "https://api.lu.ma"
SEOUL = ZoneInfo("Asia/Seoul")
DEFAULT_CALENDARS = ["koreablockchainweek", "kbw2026"]
OUT_DIR = Path(__file__).parent / "out"

SOCIAL_FIELDS = {
    "twitter": "twitter",
    "linkedin": "linkedin",
    "telegram": "telegram",
    "github": "github",
    "instagram": "instagram",
    "youtube": "youtube",
    "url": "website",
}
FREE_TEXT_TYPES = {"text", "long-text", "dropdown", "select", "multi-select"}


class Luma:
    def __init__(self, session_key: str | None):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
            "Accept": "application/json",
            "Origin": "https://luma.com",
            "Referer": "https://luma.com/",
            "x-luma-client-type": "luma-web",
            "x-luma-timezone": "Asia/Seoul",
        })
        self.authed = bool(session_key)
        if session_key:
            self.s.cookies.set("luma.auth-session-key", session_key, domain=".lu.ma")
            self.s.headers["x-luma-auth-session"] = session_key

    def get(self, path: str, **params):
        r = self.s.get(API + path, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict):
        return self.s.post(API + path, json=body, timeout=30)

    def calendar_id(self, slug: str) -> str | None:
        try:
            d = self.get("/url", url=slug)
        except requests.HTTPError:
            return None
        if d.get("kind") != "calendar":
            return None
        return d["data"]["calendar"]["api_id"]

    def calendar_events(self, cal_id: str) -> list[dict]:
        out, cursor = [], None
        while True:
            params = {"calendar_api_id": cal_id, "period": "future", "pagination_limit": 50}
            if cursor:
                params["pagination_cursor"] = cursor
            d = self.get("/calendar/get-items", **params)
            out += d.get("entries", [])
            cursor = d.get("next_cursor")
            if not d.get("has_more") or not cursor:
                return out

    def event(self, event_api_id: str) -> dict:
        return self.get("/event/get", event_api_id=event_api_id)


# ---------------------------------------------------------------- discovery

def discover(luma: Luma, slugs: list[str]) -> list[dict]:
    seen, events = set(), []
    for slug in slugs:
        cal = slug if slug.startswith("cal-") else luma.calendar_id(slug)
        if not cal:
            print(f"! calendar '{slug}' not found, skipping", file=sys.stderr)
            continue
        for entry in luma.calendar_events(cal):
            ev = entry["event"]
            key = ev.get("api_id") or entry["api_id"]
            if key in seen:
                continue
            seen.add(key)
            external = entry.get("platform") == "external"
            events.append({
                "api_id": None if external else ev["api_id"],
                "external": external,
                "name": ev["name"],
                "url": ev["url"] if external else f"https://luma.com/{ev['url']}",
                "start_at": ev["start_at"],
                "guest_count": entry.get("guest_count"),
                "ticket_info": entry.get("ticket_info") or {},
                "waitlist_active": entry.get("waitlist_active"),
                "status": (entry.get("guest_info") or {}).get("approval_status"),
            })
    events.sort(key=lambda e: e["start_at"])
    return events


def local_start(e: dict) -> datetime:
    return datetime.fromisoformat(e["start_at"].replace("Z", "+00:00")).astimezone(SEOUL)


def apply_filters(events: list[dict], args) -> list[dict]:
    out = []
    for e in events:
        start = local_start(e)
        if args.date and start.strftime("%Y-%m-%d") not in args.date:
            continue
        if args.match and not any(re.search(m, e["name"], re.I) for m in args.match):
            continue
        if args.exclude and any(re.search(x, e["name"], re.I) for x in args.exclude):
            continue
        if args.free_only and not (e["ticket_info"].get("is_free") or e["ticket_info"].get("price") is None):
            continue
        out.append(e)
    return out


def print_events(events: list[dict]):
    for i, e in enumerate(events, 1):
        t = e["ticket_info"]
        tags = []
        if t.get("require_approval"):
            tags.append("approval")
        if t.get("is_sold_out"):
            tags.append("sold out")
        if not t.get("is_free", True):
            tags.append("paid")
        if e.get("external"):
            tags.append("external site")
        if e.get("status"):
            tags.append(f"you: {e['status']}")
        start = local_start(e).strftime("%a %m/%d %H:%M")
        print(f"{i:3}. {start}  {e['name'][:70]}")
        print(f"      {e['url']}  guests={e['guest_count']}  {' | '.join(tags)}")


# ------------------------------------------------------------------ answers

def closest_option(answer, options: list[str]):
    if isinstance(answer, list):
        return [o for a in answer if (o := closest_option(a, options))]
    if answer in options:
        return answer
    m = difflib.get_close_matches(str(answer), options, n=1, cutoff=0.0)
    return m[0] if m else None


# Fallbacks for common free-text questions, tried after the profile's own `answers`.
BUILTIN_PATTERNS = [
    (r"phone|mobile|휴대|전화|연락처", "phone_number"),
    (r"e-?mail|이메일", "email"),
    (r"telegram|텔레그램", "telegram"),
    (r"twitter|\bx\b.*(handle|account|username)|트위터", "twitter"),
    (r"linkedin|링크드인", "linkedin"),
    (r"github|깃허브", "github"),
    (r"(job|your) title|직책|직함|position", "job_title"),
    (r"company|organi[sz]ation|소속|회사", "company"),
    (r"website|portfolio|웹사이트", "website"),
    (r"full name|your name|성함|이름", "name"),
]


def override_for(label: str, profile: dict):
    for pattern, answer in (profile.get("answers") or {}).items():
        if re.search(pattern, label, re.I):
            return answer
    for pattern, field in BUILTIN_PATTERNS:
        if re.search(pattern, label, re.I) and profile.get(field):
            return profile[field]
    return None


def answer_question(q: dict, profile: dict):
    """Return an answer value for a question, or None if we can't answer it."""
    qt, label = q["question_type"], q.get("label", "")
    if qt == "company":
        return {"company": profile.get("company") or None, "job_title": profile.get("job_title") or None}
    if qt == "phone-number":
        return profile.get("phone_number") or None
    if qt == "agree-check":
        return True
    if qt == "terms":
        terms = q.get("terms") or {}
        return profile.get("name") if terms.get("collect_signature") else True
    if qt in SOCIAL_FIELDS:
        return override_for(label, profile) or profile.get(SOCIAL_FIELDS[qt]) or None
    if qt in FREE_TEXT_TYPES:
        ans = override_for(label, profile)
        if ans is None:
            return None
        return coerce_choice(q, ans)
    return None


def coerce_choice(q: dict, ans):
    qt = q["question_type"]
    opts = q.get("options") or []
    if qt == "multi-select" or (qt == "select" and q.get("multiple")):
        return closest_option(ans if isinstance(ans, list) else [ans], opts) or None
    if qt in ("dropdown", "select"):
        return closest_option(ans, opts)
    return ans


def build_answer(q: dict, value) -> dict:
    a = {"label": q["label"], "question_id": q["id"], "question_type": q["question_type"], "value": value}
    if q["question_type"] == "select" and q.get("multiple"):
        a["multiple"] = True
    if q["question_type"] == "text" and q.get("multiline"):
        a["multiline"] = True
    return a


def ai_answers(event: dict, questions: list[dict], profile: dict) -> dict:
    """Ask Claude to answer the questions we couldn't fill from the profile."""
    try:
        import anthropic
        from pydantic import BaseModel
    except ImportError:
        return {}

    class Answer(BaseModel):
        question_id: str
        answer: str | list[str]

    class Answers(BaseModel):
        answers: list[Answer]

    about = {k: v for k, v in profile.items() if k not in ("answers", "eth_address", "solana_address")}
    qs = [{"question_id": q["id"], "label": q["label"], "type": q["question_type"],
           "required": q.get("required"), "options": q.get("options")} for q in questions]
    prompt = (
        "You are filling out a Luma event registration form on behalf of the person below. "
        "Answer each question truthfully and concisely based only on their profile; do not invent "
        "credentials, employers or achievements. Answer in the same language as the question. "
        "For questions with options, answer with the option text exactly (a list of options for "
        "multi-select). Keep free-text answers to 1-3 sentences.\n\n"
        f"Event: {event['event']['name']}\n\n"
        f"Profile:\n{json.dumps(about, ensure_ascii=False, indent=2)}\n\n"
        f"Questions:\n{json.dumps(qs, ensure_ascii=False, indent=2)}"
    )
    client = anthropic.Anthropic()
    try:
        resp = client.messages.parse(
            model="claude-opus-5",
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
            output_format=Answers,
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
    except anthropic.APIError as e:
        print(f"    ! Claude error: {e}", file=sys.stderr)
        return {}
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        return {}
    by_id = {q["id"]: q for q in questions}
    return {a.question_id: coerce_choice(by_id[a.question_id], a.answer)
            for a in resp.parsed_output.answers if a.question_id in by_id}


# ------------------------------------------------------------- registration

def pick_ticket(ev: dict):
    """Return (ticket_type_to_selection, reason_if_unregistrable)."""
    tickets = [t for t in ev.get("ticket_types") or [] if not t.get("is_hidden") and not t.get("is_disabled")]
    if not tickets:
        return {}, None  # events without ticket types register with an empty selection
    free = [t for t in tickets if t.get("type") == "free" or (not t.get("cents") and not t.get("min_cents"))]
    free = [t for t in free if not t.get("ethereum_token_requirements") and not t.get("membership_restriction")]
    if not free:
        return None, "paid or token-gated tickets only"
    t = free[0]
    return {t["api_id"]: {"count": 1, "amount": 0}}, None


def plan_registration(ev: dict, profile: dict, use_ai: bool):
    """Build the /event/register payload. Returns (payload, problems)."""
    problems = []
    selection, reason = pick_ticket(ev)
    if reason:
        return None, [reason]
    if ev.get("eth_address_requirement") == "required":
        problems.append("requires a verified ETH wallet")
    if ev.get("solana_address_requirement") == "required":
        problems.append("requires a verified Solana wallet")
    if ev.get("phone_number_requirement") == "required" and not profile.get("phone_number"):
        problems.append("requires a phone number")

    questions = ev.get("registration_questions") or []
    prefilled = ev.get("prefilled_answers") or {}
    values, missing = {}, []
    for q in questions:
        if q["id"] in prefilled and prefilled[q["id"]] is not None:
            pf = prefilled[q["id"]]
            values[q["id"]] = pf.get("value") if isinstance(pf, dict) else pf
            continue
        v = answer_question(q, profile)
        if v in (None, "", []):
            missing.append(q)
        else:
            values[q["id"]] = v

    if missing and use_ai:
        values.update({k: v for k, v in ai_answers(ev, missing, profile).items() if v not in (None, "", [])})
        missing = [q for q in missing if q["id"] not in values]
    for q in missing:
        if q.get("required"):
            problems.append(f"no answer for required question: {q['label']!r}")

    sold_out = ev.get("sold_out")
    payload = {
        "name": profile.get("name"),
        "first_name": profile.get("first_name"),
        "last_name": profile.get("last_name"),
        "email": profile.get("email"),
        "event_api_id": ev["api_id"],
        "for_waitlist": bool(sold_out and ev.get("waitlist_active")),
        "payment_method": None,
        "payment_currency": None,
        "registration_answers": [build_answer(q, values[q["id"]]) for q in questions if q["id"] in values],
        "coupon_code": None,
        "token_gate_info": None,
        "eth_address_info": None,
        "phone_number": profile.get("phone_number") or None,
        "solana_address_info": None,
        "expected_amount_cents": 0,
        "expected_amount_tax": 0,
        "currency": None,
        "event_invite_api_id": None,
        "ticket_type_to_selection": selection,
        "solana_address": None,
        "solana_wallet_type": None,
        "opened_from": None,
    }
    if sold_out and not ev.get("waitlist_active"):
        problems.append("sold out, no waitlist")
    return payload, problems


def already_registered(ev: dict) -> str | None:
    gd = ev.get("guest_data") or {}
    return gd.get("approval_status") if gd else None


# ---------------------------------------------------------------- commands

def load_profile(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        sys.exit(f"Profile {p} not found. Copy profile.example.yaml to profile.yaml and fill it in.")
    return yaml.safe_load(p.read_text()) or {}


def cmd_list(luma: Luma, args):
    events = apply_filters(discover(luma, args.calendar), args)
    print_events(events)
    print(f"\n{len(events)} events")


def cmd_whoami(luma: Luma, args):
    if not luma.authed:
        sys.exit("LUMA_SESSION is not set.")
    try:
        u = luma.get("/user")
    except requests.HTTPError as e:
        sys.exit(f"Not signed in ({e}). Refresh your LUMA_SESSION cookie.")
    user = u.get("user", u)
    print(f"Signed in as {user.get('name')} <{user.get('email')}>")


def cmd_apply(luma: Luma, args):
    if args.go and not luma.authed:
        sys.exit("Set LUMA_SESSION first (see README).")
    profile = load_profile(args.profile)
    use_ai = not args.no_ai and bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    events = apply_filters(discover(luma, args.calendar), args)
    if args.limit:
        events = events[: args.limit]
    mode = "SUBMITTING" if args.go else "DRY RUN (add --go to actually register)"
    print(f"{mode}: {len(events)} events, AI answers {'on' if use_ai else 'off'}\n")

    OUT_DIR.mkdir(exist_ok=True)
    results = []
    for e in events:
        print(f"• {local_start(e).strftime('%m/%d %H:%M')}  {e['name'][:70]}\n  {e['url']}")
        if e["external"]:
            print("  → not a Luma event, register on the external site")
            results.append({**e, "result": "manual", "detail": ["external site"]})
            continue
        ev = luma.event(e["api_id"])
        status = already_registered(ev)
        if status:
            print(f"  = already registered ({status})")
            results.append({**e, "result": "already", "detail": status})
            continue
        payload, problems = plan_registration(ev, profile, use_ai)
        if problems:
            for p in problems:
                print(f"  ! {p}")
            print("  → skipped, register manually")
            results.append({**e, "result": "manual", "detail": problems})
            continue
        for a in payload["registration_answers"]:
            print(f"    {a['label'][:60]!r}: {json.dumps(a['value'], ensure_ascii=False)[:80]}")
        if payload["for_waitlist"]:
            print("    (joining waitlist)")
        if not args.go:
            results.append({**e, "result": "dry-run", "payload": payload})
            continue
        r = luma.post("/event/register", payload)
        try:
            body = r.json()
        except ValueError:
            body = {"raw": r.text[:500]}
        if r.ok:
            st = body.get("status") or body.get("approval_status") or "ok"
            print(f"  ✓ registered ({st})")
            results.append({**e, "result": "registered", "detail": body})
        else:
            print(f"  ✗ HTTP {r.status_code}: {body.get('message', body)}")
            results.append({**e, "result": "error", "detail": body, "payload": payload})
        time.sleep(args.delay)

    out = OUT_DIR / f"results-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    counts = {}
    for r in results:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    print(f"\nDone: {counts}\nLog: {out}")
    manual = [r for r in results if r["result"] in ("manual", "error")]
    if manual:
        print("\nRegister these by hand:")
        for r in manual:
            print(f"  {r['url']}  {r['name'][:60]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "apply", "whoami"):
        p = sub.add_parser(name)
        p.add_argument("--calendar", action="append", help="Luma calendar slug or cal- id (repeatable)")
        p.add_argument("--date", action="append", help="only events on this Seoul date, YYYY-MM-DD (repeatable)")
        p.add_argument("--match", action="append", help="only events whose name matches this regex (repeatable)")
        p.add_argument("--exclude", action="append", help="skip events whose name matches this regex (repeatable)")
        p.add_argument("--free-only", action="store_true", help="skip events with paid tickets")
        if name == "apply":
            p.add_argument("--go", action="store_true", help="actually submit registrations")
            p.add_argument("--profile", default=str(Path(__file__).parent / "profile.yaml"))
            p.add_argument("--no-ai", action="store_true", help="don't use Claude for unanswered questions")
            p.add_argument("--delay", type=float, default=4.0, help="seconds between registrations")
            p.add_argument("--limit", type=int, help="stop after N events")
    args = ap.parse_args()
    args.calendar = args.calendar or DEFAULT_CALENDARS

    luma = Luma(os.environ.get("LUMA_SESSION"))
    {"list": cmd_list, "apply": cmd_apply, "whoami": cmd_whoami}[args.cmd](luma, args)


if __name__ == "__main__":
    main()
