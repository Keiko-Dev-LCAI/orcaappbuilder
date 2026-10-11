#!/usr/bin/env python3
"""Binai — Personal AI assistant backend. Memory + AIVM + subscriptions."""

import os
import re
import time
import json
import uuid
import sqlite3
import threading
import urllib.request as urllib_req
from urllib.parse import quote as url_quote

import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

import languages

_ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=_ROOT, static_url_path="")
# Scoped CORS — override with CORS_ORIGINS env (comma-separated)
_CORS_ORIGINS = [o.strip() for o in __import__('os').environ.get(
    'CORS_ORIGINS',
    'https://your-domain.example,http://localhost:5000,http://127.0.0.1:5000'
).split(',') if o.strip()]
CORS(app, origins=_CORS_ORIGINS)

# Optional maintenance page: set MAINTENANCE=1 to serve maintenance.html for all routes.
_MAINTENANCE = os.environ.get("MAINTENANCE", "").strip().lower() in ("1", "true", "yes", "on")

@app.before_request
def _maintenance_mode():
    if not _MAINTENANCE:
        return None
    if os.path.exists(os.path.join(_ROOT, "maintenance.html")):
        return send_from_directory(_ROOT, "maintenance.html")
    return ("Service temporarily unavailable", 503)

# ── CONFIG ───────────────────────────────────────────────────────────────────
AIVM_RELAY = os.environ.get(
    "AIVM_RELAY", "https://YOUR_AIVM_RELAY"
)
OWNER_WALLET = os.environ.get(
    "OWNER_WALLET", "YOUR_LCAI_WALLET"
).lower()
MONTHLY_PRICE_USD = float(os.environ.get("MONTHLY_PRICE_USD", "3.00"))
FREE_ACTIONS_LIFETIME = int(os.environ.get("FREE_ACTIONS_LIFETIME", "20"))
# Production default: billing on. Set TEST_MODE=true only for unlimited internal testing.
_test_flag = os.environ.get("TEST_MODE", "false").lower()
TEST_MODE = _test_flag in ("1", "true", "yes", "on")
# Comma-separated wallets with unlimited free AI forever (owner + testers).
FREE_FOREVER_WALLETS_RAW = os.environ.get("FREE_FOREVER_WALLETS", "")
RATE_LIMIT_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "120"))
LCAI_RPC = "https://rpc.mainnet.lightchain.ai"
BUILD_VERSION = os.environ.get("BINAI_BUILD", "20260724-30")
_KUAISHOU_URL_PAT = re.compile(
    r"https?://(?:www\.)?(?:kuaishou\.com|kwai\.com|v\.kuaishou\.com|gifshow\.com)\S*",
    re.I,
)

LANG_NAMES = languages.LANG_NAMES

_data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(_data_dir, exist_ok=True)
DB_PATH = os.path.join(_data_dir, "binai.db")

_jobs = {}
_jobs_lock = threading.Lock()
_JOB_TTL = 3600


def _cleanup_old_jobs():
    cutoff = time.time() - _JOB_TTL
    with _jobs_lock:
        for job_id in [k for k, v in _jobs.items() if v.get("created_at", 0) < cutoff]:
            del _jobs[job_id]


def _set_job(job_id, **fields):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def _run_chat_job(
    job_id, wallet, message, lang, reason, safe, safety_category, safety_reply, local_hour=None
):
    try:
        used_aivm = False
        if not safe:
            reply = safety_reply
            log_chat(wallet, "assistant", f"[safety:{safety_category}] {reply[:200]}")
        elif languages.is_booking_request(message):
            reply = languages.booking_reply(lang)
            log_chat(wallet, "assistant", reply)
        else:
            prof = get_profile(wallet) or {}
            prefs = json.loads(prof.get("preferences") or "{}")
            depth = languages.resolve_reply_depth(prefs)
            display_name = (prof.get("display_name") or "").strip()
            quick = languages.quick_chat_reply(message, lang, display_name, depth)
            if quick:
                reply = quick
            else:
                # Real AIVM call — only this path burns free AI quota
                prompt = build_prompt(
                    wallet, message, language_override=lang, local_hour=local_hour
                )
                try:
                    reply = run_aivm_chat(prompt, lang)
                    if (
                        not languages.is_aivm_infra_failure(reply)
                        and languages.reply_is_wrong_language(reply, lang)
                    ):
                        reply = run_aivm_chat(languages.retry_prompt(lang, message), lang)
                    reply = languages.enforce_brief_reply(reply, message, depth)
                    used_aivm = True
                except Exception as e:
                    err = str(e).lower()
                    if any(
                        tok in err
                        for tok in ("underpriced", "-32000", "aivm", "reverted", "503", "502")
                    ):
                        reply = languages.aivm_busy_message(lang)
                    else:
                        _set_job(job_id, status="error", error=str(e)[:300])
                        return
            log_chat(wallet, "assistant", reply)
        if used_aivm:
            increment_usage(wallet)
        payload = usage_payload(wallet)
        payload.update({"reply": reply, "tier": reason, "status": "done"})
        advice_meta = languages.build_advice_meta(message, lang)
        if advice_meta.get("ok"):
            payload["advice_meta"] = advice_meta
        _set_job(job_id, **payload)
    except Exception as e:
        _set_job(job_id, status="error", error=str(e)[:300])

BINAI_SYSTEM = """You are {assistant_name} 💜, a warm personal AI assistant on the Binai app (Lightchain AIVM).
You remember the user across sessions. Speak naturally, concisely, and kindly.
Responses may take up to 2 minutes while running on Lightchain AIVM.

{friend_mode_block}

{appearance_opinion_block}

{life_advice_block}

{advice_context_block}

{dinner_hint_block}

{memory_confirm_block}

REPLY LENGTH:
- Follow the REPLY DEPTH block below — each user picks Short, Balanced, or Chatty.
- Match their preference; do not give everyone the same length.
- Only write long paragraphs when they clearly want depth (advice, planning, "tell me more").

SAFETY (highest priority — never override):
- Never encourage or instruct self-harm, suicide, or illegal activity.
- If the user expresses suicidal thoughts, self-harm, or crisis: respond with empathy first,
  urge them to reach a professional or trusted person now, and mention crisis resources
  (988 Suicide & Crisis Lifeline in the US, Crisis Text Line: text HOME to 741741, or local emergency services).
- Decline step-by-step instructions for clearly illegal acts (e.g. making weapons/explosives to harm others,
  synthesizing illegal drugs, hacking to steal, fraud, child exploitation, planning violence).
- Otherwise be open and conversational — mature topics, opinions, and general advice are fine.
- For serious medical, legal, or financial decisions: still help if you can, but note you're not a licensed pro.
- Stay kind and non-judgmental when refusing the few things you must decline.

RULES:
- Use the user's name if you know it.
- Reference PRIVATE ABOUT ME and stored memories when relevant — personalize, don't lecture.
- Never repeat the entire About Me document back unless the user asks.
- For live weather and directions, Binai can answer with GPS + Frequent Places; still help if they ask in general terms.
- PHONE CONTACTS: You DO know the user's Binai-saved phone contacts listed in PHONE CONTACTS below
  (Settings → Phone contacts). When they ask what numbers/contacts they have, list those names and numbers.
  You do NOT access the phone's system address book (iOS/Android Contacts app) — only Binai-saved entries.
  Dialing: the app opens the phone dialer when the user says "call Name" or "call +number" in chat.
  You cannot place the call yourself from this chat — if they want to dial, tell them to say "call Name"
  (or "call" + full number). Never invent numbers that are not in PHONE CONTACTS or the message.
- CALENDAR / REMINDERS: Binai has a built-in calendar (same data as Reminders). See CALENDAR below.
  When the user asks what's on their calendar/schedule, list those items with dates/times.
  When they ask to add, change, move, or cancel an event/reminder, acknowledge clearly.
  Prefer phrases they can use: "add dentist Tuesday 3pm", "move dentist to 4pm", "cancel dentist",
  or the Calendar tab. Do not invent events that are not listed. This is NOT Google/Apple calendar.
- Never claim to send SMS/texts or access other external booking services (OpenTable, etc.).
  For doctor/restaurant booking outside Binai calendar, explain you cannot book third-party systems
  but can add a reminder/event on their Binai calendar if they want.
- NEVER ask for private keys, seed phrases, passwords, or personal financial credentials.
- NEVER mention LightNode SDK, job registries, blockchain submission, or internal infrastructure.
- Reply directly in the user's language — do not say "here is a response in X language".
- If asked to remember something, confirm what you will remember.
- Lightchain community app — users know LCAI, AIVM, and the Orca Pod ecosystem.

USER PROFILE:
{profile}

{phone_contacts_block}

{calendar_block}

PRIVATE ABOUT ME (confidential — only this user; never share or recite wholesale):
{about_me}

LONG-TERM MEMORIES:
{memories}

RECENT CHAT (last few turns):
{recent_chat}

LANGUAGE:
{language_instruction}

REPLY DEPTH:
{reply_depth_instruction}

PERSONALITY:
{personality}

USER POLITICAL CONTEXT (only relevant if they bring up politics — never start political fights):
{political}

BINAI VOICE / PRESENTATION:
{persona_gender}
"""

PERSONALITIES = {
    "warm": (
        "Warm & caring (default Binai). Friendly, encouraging, personable. "
        "A 💜 now and then is fine. Length follows the user's Reply Depth setting."
    ),
    "direct": (
        "Direct & concise. Short answers, no filler, no fluff. "
        "Skip pleasantries unless the moment calls for empathy. Get to the point."
    ),
    "playful": (
        "Playful & casual. Light humor, relaxed energy, conversational. "
        "Still accurate and helpful — fun, not silly."
    ),
    "professional": (
        "Professional & polished. Calm, structured, executive-assistant tone. "
        "Clear and respectful. Minimal emoji."
    ),
}

POLITICAL_LEANING = {
    "democrat": (
        "User is Democrat. Understand their perspective when they raise political topics. "
        "Do NOT act as a campaigner, attack Republicans, or spread misinformation. Stay fair."
    ),
    "republican": (
        "User is Republican. Understand their perspective when they raise political topics. "
        "Do NOT act as a campaigner, attack Democrats, or spread misinformation. Stay fair."
    ),
    "independent": (
        "User is Independent. When politics comes up, present multiple viewpoints fairly "
        "and respect that they do not align strictly with either major party."
    ),
}

PERSONA_GENDER = {
    "neutral": (
        "Neutral presentation (default). {assistant_name} has no gender — refer to yourself as "
        "{assistant_name} only; avoid gendered self-descriptions."
    ),
    "female": (
        "Female presentation. Subtly feminine tone and warmth. Still {assistant_name} — an AI assistant, "
        "not a human woman."
    ),
    "male": (
        "Male presentation. Subtly masculine tone and directness. Still {assistant_name} — an AI assistant, "
        "not a human man."
    ),
}

# Input patterns: (category, regex). Order matters — crisis checked first.
_CRISIS_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"\b(kill|hurt|harm)\s+myself\b",
        r"\b(want|wanna|going)\s+to\s+die\b",
        r"\bend\s+(my|this)\s+life\b",
        r"\bcommit\s+suicide\b",
        r"\bsuicidal\b",
        r"\bself[- ]?harm\b",
        r"\bdon'?t\s+want\s+to\s+(live|be\s+alive|exist)\b",
        r"\bno\s+reason\s+to\s+live\b",
        r"\bbetter\s+off\s+dead\b",
    ]
]

# Hard-block only clear illegal-intent requests (not general discussion).
_BLOCKED_INPUT_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"\bhow\s+to\s+(make|build|create)\s+(a\s+)?(bomb|explosive)\b",
        r"\bhow\s+to\s+(hack|break\s+into|steal|phish)\s+(a\s+)?(bank|account|wallet|password|system)\b",
        r"\bhow\s+to\s+(make|synthesize|cook)\s+(meth|fentanyl)\b",
        r"\b(child|minor)\s+(porn|sexual|exploitation)\b",
        r"\bhow\s+to\s+kill\s+(someone|people|him|her|them)\b",
        r"\b(plan|best\s+way)\s+to\s+(murder|poison)\s+(someone|him|her|them|people)\b",
    ]
]

# Last-resort output filter — only obvious illegal how-to slips.
_OUTPUT_BLOCK_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"\bhere(?:'s| is) how to (?:make|build|synthesize)\s+(?:a\s+)?(?:bomb|meth|fentanyl|explosive)\b",
        r"\b(step\s+1:.*(?:ammonium nitrate|detonator|fentanyl|methamphetamine).*(?:step\s+2:|step\s+3:))",
    ]
]


def check_input_safety(message, lang="en"):
    """Return (safe, category, canned_reply). category is None when safe."""
    text = (message or "").strip()
    if not text:
        return True, None, None
    for pat in _CRISIS_PATTERNS:
        if pat.search(text):
            return False, "crisis", languages.localized_safety_reply("crisis", lang)
    for pat in _BLOCKED_INPUT_PATTERNS:
        if pat.search(text):
            return False, "blocked", languages.localized_safety_reply("blocked", lang)
    return True, None, None


def sanitize_output(reply, lang="en"):
    """Last-resort filter on model output before it reaches the user."""
    text = (reply or "").strip()
    if not text:
        return languages.localized_safety_reply("blocked", lang)
    for pat in _OUTPUT_BLOCK_PATTERNS:
        if pat.search(text):
            return languages.localized_safety_reply("blocked", lang)
    return text


# ── AIVM ADAPTER (swap this module when REST API lands) ──────────────────────

_AIVM_RETRY_DELAYS = (0, 6, 10, 15, 20, 25, 30)


class AIVMProvider:
    """Today: aaaba HTTP relay. Tomorrow: REST API — change only this class."""

    @staticmethod
    def infer(prompt: str, timeout: int = 240) -> str:
        start = requests.post(
            f"{AIVM_RELAY}/api/chat",
            json={"message": prompt, "mode": "chat"},
            timeout=30,
        )
        if not start.ok:
            raise RuntimeError(f"AIVM start failed: {start.status_code} {start.text[:200]}")
        data = start.json()
        job_id = data.get("job_id")
        if not job_id:
            return data.get("reply") or data.get("message") or "No response from AIVM."
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(5)
            poll = requests.get(
                f"{AIVM_RELAY}/api/chat/status",
                params={"job_id": job_id},
                timeout=15,
            )
            if not poll.ok:
                raise RuntimeError(f"AIVM poll failed: {poll.status_code}")
            pd = poll.json()
            if pd.get("status") == "done":
                return pd.get("reply") or ""
            if pd.get("status") == "error":
                raise RuntimeError(pd.get("error") or "AIVM job failed")
        raise RuntimeError("AIVM timed out — try again.")


def run_aivm_chat(prompt: str, lang: str) -> str:
    """Auto-retry AIVM while testers queue — don't make users tap send again."""
    last_err = None
    for delay in _AIVM_RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            reply = sanitize_output(AIVMProvider.infer(prompt), lang)
            if languages.is_aivm_infra_failure(reply) or languages.is_bad_ai_reply(reply):
                continue
            return reply
        except Exception as e:
            last_err = e
            err = str(e).lower()
            if not any(
                tok in err
                for tok in (
                    "aivm",
                    "underpriced",
                    "32000",
                    "timeout",
                    "503",
                    "502",
                    "reverted",
                    "unavailable",
                )
            ):
                raise
    if last_err:
        print(f"[AIVM] all retries failed: {last_err}")
    return languages.aivm_busy_message(lang)


# ── DATABASE ─────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            wallet TEXT PRIMARY KEY,
            display_name TEXT DEFAULT '',
            language TEXT DEFAULT 'en',
            preferences TEXT DEFAULT '{}',
            bio TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            content TEXT NOT NULL,
            due_at INTEGER,
            end_at INTEGER,
            all_day INTEGER DEFAULT 0,
            recurrence TEXT DEFAULT '',
            done INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            wallet TEXT PRIMARY KEY,
            expires_at INTEGER NOT NULL,
            tx_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS usage (
            wallet TEXT PRIMARY KEY,
            actions_used INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS chat_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rate_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet TEXT NOT NULL,
            user_message TEXT,
            bot_reply TEXT,
            rating TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


init_db()


# ── HELPERS ──────────────────────────────────────────────────────────────────

_lcai_price_cache = {"price": 0.004, "ts": 0}


def get_lcai_price():
    global _lcai_price_cache
    now = time.time()
    if now - _lcai_price_cache["ts"] < 300:
        return _lcai_price_cache["price"]
    try:
        req = urllib_req.Request(
            "https://api.coingecko.com/api/v3/simple/price?ids=lightchain-ai&vs_currencies=usd",
            headers={"User-Agent": "Binai/1.0"},
        )
        with urllib_req.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            price = (data.get("lightchain-ai") or {}).get("usd")
            if price and float(price) > 0:
                _lcai_price_cache = {"price": float(price), "ts": now}
                return float(price)
    except Exception:
        pass
    try:
        req = urllib_req.Request(
            "https://api.dexscreener.com/latest/dex/search?q=LCAI",
            headers={"User-Agent": "Binai/1.0"},
        )
        with urllib_req.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            for pair in data.get("pairs") or []:
                price = float(pair.get("priceUsd") or 0)
                if price > 0:
                    _lcai_price_cache = {"price": price, "ts": now}
                    return price
    except Exception:
        pass
    _lcai_price_cache["ts"] = now
    return _lcai_price_cache["price"]


def norm_wallet(w):
    return (w or "").strip().lower()


def free_forever_wallets():
    """Wallets with unlimited free AI (owner + allowlisted testers)."""
    out = set()
    for part in (FREE_FOREVER_WALLETS_RAW or "").split(","):
        w = norm_wallet(part)
        if w and w.startswith("0x") and len(w) == 42:
            out.add(w)
    return out


def is_free_forever(wallet):
    return norm_wallet(wallet) in free_forever_wallets()


def is_subscribed(wallet):
    """Paid subscription active (not free-forever allowlist)."""
    w = norm_wallet(wallet)
    now = int(time.time())
    conn = get_db()
    row = conn.execute(
        "SELECT expires_at FROM subscriptions WHERE wallet = ?", (w,)
    ).fetchone()
    conn.close()
    return bool(row and row["expires_at"] > now)


def get_usage(wallet):
    w = norm_wallet(wallet)
    conn = get_db()
    row = conn.execute("SELECT actions_used FROM usage WHERE wallet = ?", (w,)).fetchone()
    conn.close()
    return row["actions_used"] if row else 0


def can_use_ai(wallet):
    if TEST_MODE:
        return True, "testing"
    if is_free_forever(wallet):
        return True, "free_forever"
    if is_subscribed(wallet):
        return True, "subscribed"
    used = get_usage(wallet)
    if used < FREE_ACTIONS_LIFETIME:
        return True, "free"
    return False, "limit_reached"


def usage_payload(wallet):
    w = norm_wallet(wallet)
    used = get_usage(w)
    forever = is_free_forever(w)
    sub = is_subscribed(w)
    if TEST_MODE:
        return {
            "testing": True,
            "subscribed": False,
            "free_forever": False,
            "actions_used": used,
            "free_limit": FREE_ACTIONS_LIFETIME,
            "remaining_free": None,
            "monthly_price_usd": MONTHLY_PRICE_USD,
            "tier": "testing",
        }
    if forever:
        return {
            "testing": False,
            "subscribed": True,
            "free_forever": True,
            "actions_used": used,
            "free_limit": FREE_ACTIONS_LIFETIME,
            "remaining_free": None,
            "monthly_price_usd": MONTHLY_PRICE_USD,
            "tier": "free_forever",
        }
    return {
        "testing": False,
        "subscribed": sub,
        "free_forever": False,
        "actions_used": used,
        "free_limit": FREE_ACTIONS_LIFETIME,
        "remaining_free": max(0, FREE_ACTIONS_LIFETIME - used) if not sub else None,
        "monthly_price_usd": MONTHLY_PRICE_USD,
        "tier": "subscribed" if sub else "free",
    }


def check_rate_limit(wallet):
    w = norm_wallet(wallet)
    now = int(time.time())
    hour_ago = now - 3600
    conn = get_db()
    conn.execute("DELETE FROM rate_log WHERE created_at < ?", (hour_ago,))
    count = conn.execute(
        "SELECT COUNT(*) as c FROM rate_log WHERE wallet = ? AND created_at > ?",
        (w, hour_ago),
    ).fetchone()["c"]
    if count >= RATE_LIMIT_PER_HOUR:
        conn.close()
        return False, f"Rate limit: max {RATE_LIMIT_PER_HOUR} AI messages per hour. Try again later."
    conn.execute("INSERT INTO rate_log (wallet, created_at) VALUES (?, ?)", (w, now))
    conn.commit()
    conn.close()
    return True, None


def increment_usage(wallet):
    """Count only when free-tier user successfully used AIVM (not instant/local tools)."""
    w = norm_wallet(wallet)
    if TEST_MODE or is_free_forever(w) or is_subscribed(w):
        return
    conn = get_db()
    conn.execute(
        """INSERT INTO usage (wallet, actions_used) VALUES (?, 1)
           ON CONFLICT(wallet) DO UPDATE SET actions_used = actions_used + 1""",
        (w,),
    )
    conn.commit()
    conn.close()
    _migrate_db()


def _migrate_db():
    conn = get_db()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(profiles)").fetchall()}
    if "bio" not in cols:
        conn.execute("ALTER TABLE profiles ADD COLUMN bio TEXT DEFAULT ''")
    rcols = {r[1] for r in conn.execute("PRAGMA table_info(reminders)").fetchall()}
    if "end_at" not in rcols:
        conn.execute("ALTER TABLE reminders ADD COLUMN end_at INTEGER")
    if "all_day" not in rcols:
        conn.execute("ALTER TABLE reminders ADD COLUMN all_day INTEGER DEFAULT 0")
    if "recurrence" not in rcols:
        conn.execute("ALTER TABLE reminders ADD COLUMN recurrence TEXT DEFAULT ''")
    conn.commit()
    conn.close()


try:
    _migrate_db()
except Exception:
    pass

MAX_BIO_CHARS = 12000


def get_profile(wallet):
    w = norm_wallet(wallet)
    conn = get_db()
    row = conn.execute("SELECT * FROM profiles WHERE wallet = ?", (w,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def ensure_profile(wallet):
    w = norm_wallet(wallet)
    if get_profile(w):
        return
    now = int(time.time())
    conn = get_db()
    conn.execute(
        "INSERT INTO profiles (wallet, created_at, updated_at) VALUES (?, ?, ?)",
        (w, now, now),
    )
    conn.commit()
    conn.close()


def get_memories(wallet, limit=20):
    w = norm_wallet(wallet)
    conn = get_db()
    rows = conn.execute(
        "SELECT id, content, created_at FROM memories WHERE wallet = ? ORDER BY id DESC LIMIT ?",
        (w, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_memory(wallet, content):
    w = norm_wallet(wallet)
    content = (content or "").strip()
    if not content:
        return
    conn = get_db()
    conn.execute(
        "INSERT INTO memories (wallet, content, created_at) VALUES (?, ?, ?)",
        (w, content[:500], int(time.time())),
    )
    conn.commit()
    conn.close()


def maybe_extract_memory(wallet, message):
    msg = (message or "").strip()
    patterns = [
        r"(?:remember|don't forget|note that)\s+(?:that\s+)?(.+)",
        r"my name is\s+(.+)",
        r"i am\s+(.+)",
        r"call me\s+(.+)",
        r"(?:recuerda|recuerde|no olvides)\s+(?:que\s+)?(.+)",
        r"(?:souviens[- ]toi|n'oublie pas|rappele[- ]toi)\s+(?:que\s+)?(.+)",
        r"(?:lembre|lembra|não esqueça)\s+(?:que\s+)?(.+)",
        r"(?:merke dir|vergiss nicht)\s+(?:dass\s+)?(.+)",
        r"(?:覚えて|覚えておいて|忘れないで)\s*(?:、)?(.+)",
        r"(?:记住|记得|不要忘记)\s*(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, msg, re.I)
        if m:
            fact = m.group(1).strip().rstrip(".")
            if len(fact) > 3:
                add_memory(wallet, fact)
                if "name" in pat or "call me" in pat:
                    conn = get_db()
                    conn.execute(
                        "UPDATE profiles SET display_name = ?, updated_at = ? WHERE wallet = ?",
                        (fact.split()[0][:40], int(time.time()), norm_wallet(wallet)),
                    )
                    conn.commit()
                    conn.close()
            return


def get_recent_chat(wallet, limit=6, max_age_hours=36):
    """Last few turns for the model — only from a recent window so old chats don't resurface."""
    w = norm_wallet(wallet)
    since = int(time.time()) - int(max_age_hours * 3600)
    conn = get_db()
    rows = conn.execute(
        """SELECT role, content FROM chat_log
           WHERE wallet = ? AND created_at >= ?
           ORDER BY id DESC LIMIT ?""",
        (w, since, limit),
    ).fetchall()
    conn.close()
    lines = []
    for r in reversed(rows):
        lines.append(f"{r['role'].upper()}: {r['content']}")
    return "\n".join(lines) if lines else "(none yet)"


def log_chat(wallet, role, content):
    w = norm_wallet(wallet)
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_log (wallet, role, content, created_at) VALUES (?, ?, ?, ?)",
        (w, role, content[:4000], int(time.time())),
    )
    conn.commit()
    conn.close()


def resolve_lang(wallet, override=None, user_message=None):
    return languages.resolve_lang(lambda: get_profile(wallet), override, user_message)


def sync_profile_language(wallet, lang):
    if lang not in LANG_NAMES:
        return
    w = norm_wallet(wallet)
    prof = get_profile(w) or {}
    if prof.get("language") == lang:
        return
    now = int(time.time())
    conn = get_db()
    conn.execute(
        "UPDATE profiles SET language = ?, updated_at = ? WHERE wallet = ?",
        (lang, now, w),
    )
    conn.commit()
    conn.close()


def build_prompt(wallet, user_message, language_override=None, local_hour=None):
    prof = get_profile(wallet) or {}
    prefs = json.loads(prof.get("preferences") or "{}")
    personality_key = prefs.get("personality") or "warm"
    if personality_key not in PERSONALITIES:
        personality_key = "warm"
    political_key = prefs.get("political") or "independent"
    if political_key == "neutral" or political_key not in POLITICAL_LEANING:
        political_key = "independent"
    gender_key = prefs.get("persona_gender") or "neutral"
    if gender_key not in PERSONA_GENDER:
        gender_key = "neutral"
    lang = resolve_lang(wallet, language_override, user_message)
    # Keep bulky phone list out of raw prefs dump — shown in phone_contacts_block instead
    prefs_for_profile = {
        k: v for k, v in prefs.items() if k != "phone_contacts"
    }
    profile_text = json.dumps(
        {
            "name": prof.get("display_name") or "unknown",
            "language": lang,
            "preferences": prefs_for_profile,
        },
        indent=2,
    )
    pc_raw = prefs.get("phone_contacts") or []
    pc_lines = []
    if isinstance(pc_raw, list):
        for c in pc_raw[:30]:
            if not isinstance(c, dict):
                continue
            nm = str(c.get("name") or c.get("label") or "").strip()
            ph = str(
                c.get("phone") or c.get("number") or c.get("tel") or ""
            ).strip()
            if nm and ph:
                pc_lines.append(f"- {nm}: {ph}")
    if pc_lines:
        phone_contacts_block = (
            "PHONE CONTACTS (Binai-saved only — list these when asked; "
            "user dials with \"call Name\"):\n" + "\n".join(pc_lines)
        )
    else:
        phone_contacts_block = (
            "PHONE CONTACTS: (none saved yet in Binai Settings → Phone contacts. "
            "If they ask for numbers, say none are saved yet and how to add one. "
            "Do not claim you cannot ever see contacts — only that the list is empty.)"
        )
    # Upcoming calendar / reminders (same table)
    try:
        _migrate_db()
        conn_cal = get_db()
        now_ts = int(time.time())
        cal_rows = conn_cal.execute(
            """SELECT id, content, due_at, end_at, all_day, done FROM reminders
               WHERE wallet = ? AND done = 0
                 AND (due_at IS NULL OR due_at >= ?)
               ORDER BY due_at IS NULL, due_at ASC LIMIT 40""",
            (norm_wallet(wallet), now_ts - 86400),
        ).fetchall()
        conn_cal.close()
    except Exception:
        cal_rows = []
    cal_lines = []
    for r in cal_rows or []:
        rd = dict(r)
        due = rd.get("due_at")
        if due:
            try:
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(due)))
            except Exception:
                when = str(due)
        else:
            when = "(no date)"
        cal_lines.append(f"- [{rd.get('id')}] {when}: {rd.get('content') or ''}")
    if cal_lines:
        calendar_block = (
            "CALENDAR / REMINDERS (Binai built-in — same as Calendar tab & Reminders; "
            "list when asked about schedule):\n" + "\n".join(cal_lines)
        )
    else:
        calendar_block = (
            "CALENDAR / REMINDERS: (empty — no open dated items. "
            "User can add via Calendar tab or chat: \"add dentist Tuesday 3pm\".)"
        )
    bio_raw = (prof.get("bio") or "").strip()
    if len(bio_raw) > MAX_BIO_CHARS:
        bio_raw = bio_raw[:MAX_BIO_CHARS]
    about_me_text = bio_raw if bio_raw else "(not filled in yet — user can add their story in About Me)"
    mems = get_memories(wallet)
    mem_text = (
        "\n".join(f"- {m['content']}" for m in mems)
        if mems
        else "(no memories yet — encourage user to share)"
    )
    depth = languages.resolve_reply_depth(prefs)
    language_instruction = languages.language_instruction_for(lang)
    if languages.is_brief_intent(user_message):
        language_instruction += "\n\n" + languages.brief_intent_instruction(lang, depth)
    assistant = languages.resolve_assistant_name(prefs)
    friend_on = bool(prefs.get("friend_mode"))
    advice_on = languages.is_life_advice_query(user_message)
    friend_block = languages.friend_mode_instruction(lang, friend_on or advice_on)
    appearance_block = ""
    if friend_on or advice_on or languages.is_opinion_or_appearance(user_message):
        appearance_block = languages.appearance_opinion_instruction(lang)
    life_advice_block = languages.life_advice_instruction(lang, advice_on)
    advice_context_block = ""
    if advice_on:
        advice_context_block = languages.format_advice_context_block(
            lang, user_message, mems, bio_raw
        )
    dinner_hint_block = ""
    if advice_on and languages.is_dinner_advice_query(user_message):
        dinner_hint_block = languages.dinner_time_hint(lang, local_hour)
    memory_block = ""
    if languages.is_remember_intent(user_message):
        memory_block = languages.memory_confirm_instruction(lang)
    depth_instruction = languages.reply_depth_instruction(depth, lang)
    if advice_on:
        depth_instruction += "\n\n" + languages.advice_depth_override(lang)
    persona_gender = PERSONA_GENDER[gender_key].format(assistant_name=assistant)
    system = BINAI_SYSTEM.format(
        assistant_name=assistant,
        friend_mode_block=friend_block,
        appearance_opinion_block=appearance_block,
        life_advice_block=life_advice_block,
        advice_context_block=advice_context_block,
        dinner_hint_block=dinner_hint_block,
        memory_confirm_block=memory_block,
        profile=profile_text,
        phone_contacts_block=phone_contacts_block,
        calendar_block=calendar_block,
        about_me=about_me_text,
        memories=mem_text,
        recent_chat=get_recent_chat(wallet),
        language_instruction=language_instruction,
        reply_depth_instruction=depth_instruction,
        personality=PERSONALITIES[personality_key],
        political=POLITICAL_LEANING[political_key],
        persona_gender=persona_gender,
    )
    user_line = f"{user_message}{languages.prompt_user_suffix(lang)}"
    binai_label = f"{assistant.upper()}:"
    return (
        f"{languages.language_preamble(lang)}"
        f"{language_instruction}\n\n"
        f"{system}\n\n"
        f"USER: {user_line}\n\n"
        f"{binai_label}"
    )


def lightchain_rpc(method, params):
    payload = json.dumps(
        {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    ).encode()
    req = urllib_req.Request(
        LCAI_RPC,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Binai/1.0"},
    )
    with urllib_req.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def reverse_geocode(lat, lon, lang="en"):
    try:
        lang_code = "zh" if lang == "zh" else "en"
        geo_req = urllib_req.Request(
            "https://geocoding-api.open-meteo.com/v1/reverse?"
            f"latitude={lat}&longitude={lon}&language={lang_code}",
            headers={"User-Agent": "Binai/1.0"},
        )
        with urllib_req.urlopen(geo_req, timeout=8) as gr:
            geo = json.loads(gr.read())
        results = geo.get("results") or []
        if not results:
            return None
        hit = results[0]
        parts = [hit.get("name"), hit.get("admin1"), hit.get("country")]
        return ", ".join(p for p in parts if p) or None
    except Exception:
        return None


def fetch_weather(lat=None, lon=None, city=None):
    try:
        if lat is not None and lon is not None:
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,weather_code,wind_speed_10m"
                f"&daily=temperature_2m_max,temperature_2m_min,weather_code,"
                f"precipitation_probability_max"
                f"&timezone=auto&forecast_days=3"
            )
        elif city:
            geo_req = urllib_req.Request(
                f"https://geocoding-api.open-meteo.com/v1/search?name={url_quote(city)}&count=1",
                headers={"User-Agent": "Binai/1.0"},
            )
            with urllib_req.urlopen(geo_req, timeout=10) as gr:
                geo = json.loads(gr.read())
            results = geo.get("results") or []
            if not results:
                return None
            lat, lon = results[0]["latitude"], results[0]["longitude"]
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,weather_code"
                f"&daily=temperature_2m_max,temperature_2m_min,weather_code,"
                f"precipitation_probability_max"
                f"&timezone=auto&forecast_days=3"
            )
        else:
            return None
        req = urllib_req.Request(url, headers={"User-Agent": "Binai/1.0"})
        with urllib_req.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        data["_lat"] = lat
        data["_lon"] = lon
        return data
    except Exception:
        return None


def build_weather_report(lat=None, lon=None, city=None, lang="en"):
    lang = lang if lang in languages.LANG_NAMES else "en"
    data = fetch_weather(lat=lat, lon=lon, city=city)
    if not data or not data.get("current"):
        return {
            "ok": False,
            "error": "weather_unavailable",
            "reply": (
                "I couldn't load live weather — allow location access or add home in "
                "⚙️ Settings → Frequent Places."
                if lang == "en"
                else "无法获取实时天气 — 请允许定位，或在 ⚙️ 设置 → 常去地点 添加家庭地址。"
            ),
        }
    place = None
    if lat is not None and lon is not None:
        place = reverse_geocode(lat, lon, lang)
    elif city:
        place = city
    reply = languages.format_weather_reply(
        lang, place, data["current"], data.get("daily")
    )
    links = []
    return {
        "ok": True,
        "reply": reply,
        "place": place,
        "temp_c": data["current"].get("temperature_2m"),
        "description": languages.wmo_description(
            data["current"].get("weather_code"), lang
        ),
        "links": links,
    }


def build_directions_report(message, prefs, lat=None, lon=None, lang="en"):
    lang = lang if lang in languages.LANG_NAMES else "en"
    dest = languages.extract_directions_destination(message, prefs)
    if not dest:
        return {"ok": False, "reason": "not_directions"}
    if lat is None or lon is None:
        return {
            "ok": False,
            "reply": languages.directions_missing_place_reply(lang, "location"),
        }
    address = (dest.get("address") or "").strip()
    kind = dest.get("kind")
    if kind not in ("place", "unknown") and not address:
        return {
            "ok": False,
            "reply": languages.directions_missing_place_reply(lang, "missing", kind),
        }
    if not address:
        return {
            "ok": False,
            "reply": languages.directions_missing_place_reply(lang, "unknown"),
        }
    enc_dest = url_quote(address)
    origin = f"{lat},{lon}"
    if lang == "zh":
        maps_url = (
            f"https://uri.amap.com/navigation?from={lon},{lat},我的位置"
            f"&to={enc_dest}&mode=car"
        )
        label_key = "directions_open_amap"
    else:
        maps_url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={origin}&destination={enc_dest}"
        )
        label_key = "directions_open_maps"
    dest_label = dest.get("label") or address
    if lang == "zh":
        reply = f"从你现在这里导航到{dest_label} — 点下面按钮在地图里打开路线。"
    else:
        reply = f"Directions from here to {dest_label} — tap below to open in Maps."
    return {
        "ok": True,
        "reply": reply,
        "destination": address,
        "links": [{"kind": "maps", "label_key": label_key, "url": maps_url}],
    }


WMO = {
    0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 61: "light rain", 63: "rain", 80: "rain showers",
    95: "thunderstorm",
}


# ── ROUTES ───────────────────────────────────────────────────────────────────

_NO_CACHE_PATHS = {
    "/",
    "/index.html",
    "/sw.js",
    "/i18n-ui.js",
    "/manifest.json",
    "/build.json",
}


@app.after_request
def set_cache_headers(response):
    path = request.path or ""
    if path in _NO_CACHE_PATHS or path.endswith("/i18n-ui.js") or path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.route("/build.json")
def serve_build():
    return jsonify({"build": BUILD_VERSION, "service": "Binai"})


@app.route("/")
def serve_index():
    return send_from_directory(_ROOT, "index.html")


@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory(_ROOT, "manifest.json")


def save_frequent_place(wallet, key, address):
    w = norm_wallet(wallet)
    prof = get_profile(w) or {}
    prefs = json.loads(prof.get("preferences") or "{}")
    places = prefs.get("frequent_places") or {}
    if not isinstance(places, dict):
        places = {}
    places[(key or "").strip().lower()[:32]] = (address or "").strip()[:200]
    prefs["frequent_places"] = places
    conn = get_db()
    conn.execute(
        "UPDATE profiles SET preferences = ?, updated_at = ? WHERE wallet = ?",
        (json.dumps(prefs), int(time.time()), w),
    )
    conn.commit()
    conn.close()


def maybe_save_frequent_place(wallet, message):
    parsed = languages.extract_save_place(message)
    if not parsed:
        return None
    save_frequent_place(wallet, parsed["key"], parsed["address"])
    return parsed


def build_save_place_report(message, lang="en", key=None, address=None):
    lang = lang if lang in languages.LANG_NAMES else "en"
    if key and address:
        key = (key or "").strip().lower()[:32]
        address = (address or "").strip()[:200]
        if not key or len(address) < 4:
            return {"ok": False, "reason": "invalid_place"}
        return {
            "ok": True,
            "key": key,
            "address": address,
            "reply": languages.save_place_reply(lang, key, address),
        }
    parsed = languages.extract_save_place(message)
    if not parsed:
        return {"ok": False, "reason": "not_save_place"}
    return {
        "ok": True,
        "key": parsed["key"],
        "address": parsed["address"],
        "reply": languages.save_place_reply(lang, parsed["key"], parsed["address"]),
    }


def build_place_suggestion_report(message, prefs=None, lang="en"):
    lang = lang if lang in languages.LANG_NAMES else "en"
    if languages.is_save_place_query(message):
        return {"ok": False, "reason": "explicit_save"}
    places = languages.frequent_places(prefs)
    parsed = languages.extract_place_mention(message, places)
    if not parsed:
        return {"ok": False, "reason": "no_mention"}
    key = parsed["key"]
    address = parsed["address"]
    return {
        "ok": True,
        "key": key,
        "address": address,
        "label": languages.place_display_name(key, lang),
        "prompt": languages.place_suggestion_prompt(lang, key, address),
    }


def maybe_extract_kuaishou_link(wallet, message, prefs=None):
    prefs = prefs or {}
    if prefs.get("kuaishou_enabled", True) is False or prefs.get("kuaishou_remember_links", True) is False:
        return
    m = _KUAISHOU_URL_PAT.search(message or "")
    if not m:
        return
    url = m.group(0).rstrip(").,;]")
    note = (message or "").replace(url, "").strip()
    if languages.is_remember_intent(message) or len(note) <= 120:
        fact = f"Kuaishou link: {url}"
        if note and not languages.is_remember_intent(note):
            fact += f" — {note[:200]}"
        add_memory(wallet, fact[:500])


@app.route("/api/apps-registry")
def api_apps_registry():
    path = os.path.join(_ROOT, "apps-registry.json")
    try:
        with open(path, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({"version": 1, "apps": []})


@app.route("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "Binai",
            "aivm_relay": AIVM_RELAY,
            "build": BUILD_VERSION,
            "test_mode": TEST_MODE,
            "free_actions": FREE_ACTIONS_LIFETIME,
            "monthly_price_usd": MONTHLY_PRICE_USD,
            
            "safety_filters": True,
        }
    )


@app.route("/api/price")
def api_price():
    price = get_lcai_price()
    required = MONTHLY_PRICE_USD / price if price else 0
    return jsonify(
        {
            "usd": MONTHLY_PRICE_USD,
            "lcai_price_usd": price,
            "required_lcai": round(required, 2),
            "owner_wallet": OWNER_WALLET,
        }
    )


@app.route("/api/subscription/<wallet>")
def api_subscription(wallet):
    w = norm_wallet(wallet)
    payload = usage_payload(w)
    conn = get_db()
    row = conn.execute(
        "SELECT expires_at FROM subscriptions WHERE wallet = ?", (w,)
    ).fetchone()
    conn.close()
    payload["expires_at"] = row["expires_at"] if row else None
    return jsonify(payload)


@app.route("/api/verify-subscription", methods=["POST"])
def verify_subscription():
    data = request.json or {}
    wallet = norm_wallet(data.get("wallet"))
    tx_hash = (data.get("tx_hash") or "").strip()
    if not wallet or not tx_hash:
        return jsonify({"error": "wallet and tx_hash required"}), 400
    try:
        tx = lightchain_rpc("eth_getTransactionByHash", [tx_hash])
        if not tx or not tx.get("to"):
            return jsonify({"error": "Transaction not found"}), 400
        if norm_wallet(tx.get("from")) != wallet:
            return jsonify({"error": "Transaction not from this wallet"}), 400
        if norm_wallet(tx.get("to")) != OWNER_WALLET:
            return jsonify({"error": "Payment not sent to owner wallet"}), 400
        value_wei = int(tx.get("value", "0x0"), 16)
        value_lcai = value_wei / 1e18
        price = get_lcai_price()
        required = MONTHLY_PRICE_USD / price if price else 999999
        if value_lcai < required * 0.9:
            return jsonify(
                {
                    "error": f"Insufficient LCAI. Need ~{required:.1f}, got {value_lcai:.2f}",
                }
            ), 400
        expires = int(time.time()) + 30 * 86400
        conn = get_db()
        conn.execute(
            """INSERT INTO subscriptions (wallet, expires_at, tx_hash) VALUES (?, ?, ?)
               ON CONFLICT(wallet) DO UPDATE SET expires_at = ?, tx_hash = ?""",
            (wallet, expires, tx_hash, expires, tx_hash),
        )
        conn.commit()
        conn.close()
        return jsonify({"subscribed": True, "expires_at": expires})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@app.route("/api/profile/<wallet>", methods=["GET", "POST"])
def api_profile(wallet):
    w = norm_wallet(wallet)
    ensure_profile(w)
    if request.method == "GET":
        prof = get_profile(w)
        return jsonify(prof or {})
    data = request.json or {}
    now = int(time.time())
    prefs_json = None
    if "preferences" in data and isinstance(data["preferences"], dict):
        existing = json.loads((get_profile(w) or {}).get("preferences") or "{}")
        incoming = data["preferences"]
        # Don't wipe list prefs with empty arrays unless explicitly intended
        for list_key in ("quick_actions", "phone_contacts"):
            if list_key in incoming and isinstance(incoming[list_key], list):
                if len(incoming[list_key]) == 0 and existing.get(list_key):
                    incoming = dict(incoming)
                    del incoming[list_key]
        existing.update(incoming)
        prefs_json = json.dumps(existing)
    # Empty string must not wipe name (SQLite COALESCE('','x') => '')
    display_name = data.get("display_name")
    if isinstance(display_name, str):
        display_name = display_name.strip() or None
    language = data.get("language")
    if isinstance(language, str):
        language = language.strip() or None
    conn = get_db()
    conn.execute(
        """UPDATE profiles SET display_name = COALESCE(?, display_name),
           language = COALESCE(?, language),
           preferences = COALESCE(?, preferences),
           updated_at = ? WHERE wallet = ?""",
        (
            display_name,
            language,
            prefs_json,
            now,
            w,
        ),
    )
    conn.commit()
    conn.close()
    return jsonify(get_profile(w))


@app.route("/api/about-me/<wallet>", methods=["GET", "POST"])
def api_about_me(wallet):
    w = norm_wallet(wallet)
    ensure_profile(w)
    if request.method == "GET":
        prof = get_profile(w) or {}
        bio = (prof.get("bio") or "")[:MAX_BIO_CHARS]
        return jsonify(
            {
                "bio": bio,
                "updated_at": prof.get("updated_at"),
                "max_chars": MAX_BIO_CHARS,
            }
        )
    data = request.json or {}
    bio = (data.get("bio") or "").strip()[:MAX_BIO_CHARS]
    now = int(time.time())
    conn = get_db()
    conn.execute(
        "UPDATE profiles SET bio = ?, updated_at = ? WHERE wallet = ?",
        (bio, now, w),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "bio": bio, "updated_at": now, "max_chars": MAX_BIO_CHARS})


@app.route("/api/memories/<wallet>", methods=["GET", "POST", "DELETE"])
def api_memories(wallet):
    w = norm_wallet(wallet)
    if request.method == "GET":
        return jsonify(get_memories(w))
    if request.method == "POST":
        data = request.json or {}
        add_memory(w, data.get("content", ""))
        return jsonify({"ok": True})
    mem_id = (request.json or {}).get("id")
    if mem_id:
        conn = get_db()
        conn.execute("DELETE FROM memories WHERE id = ? AND wallet = ?", (mem_id, w))
        conn.commit()
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/notes/<wallet>", methods=["GET", "POST"])
def api_notes(wallet):
    w = norm_wallet(wallet)
    if request.method == "GET":
        conn = get_db()
        rows = conn.execute(
            "SELECT id, content, created_at FROM notes WHERE wallet = ? ORDER BY id DESC",
            (w,),
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    data = request.json or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO notes (wallet, content, created_at) VALUES (?, ?, ?)",
        (w, content, int(time.time())),
    )
    conn.commit()
    nid = cur.lastrowid
    conn.close()
    return jsonify({"id": nid, "content": content})


@app.route("/api/notes/<wallet>/<int:note_id>", methods=["DELETE"])
def delete_note(wallet, note_id):
    w = norm_wallet(wallet)
    conn = get_db()
    conn.execute("DELETE FROM notes WHERE id = ? AND wallet = ?", (note_id, w))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/reminders/<wallet>", methods=["GET", "POST"])
def api_reminders(wallet):
    """Reminders = calendar events (same store). GET supports ?from=&to= unix range."""
    _migrate_db()
    w = norm_wallet(wallet)
    if request.method == "GET":
        from_ts = request.args.get("from", type=int)
        to_ts = request.args.get("to", type=int)
        include_done = request.args.get("include_done", "0") == "1"
        conn = get_db()
        sql = """SELECT id, content, due_at, end_at, all_day, recurrence, done, created_at
                 FROM reminders WHERE wallet = ?"""
        params = [w]
        if not include_done:
            sql += " AND done = 0"
        # Recurring rows always return (client expands). One-shot filtered by range.
        if from_ts is not None or to_ts is not None:
            sql += " AND ("
            sql += " (recurrence IS NOT NULL AND TRIM(recurrence) != '')"
            sql += " OR (due_at IS NULL)"
            if from_ts is not None and to_ts is not None:
                sql += " OR (due_at >= ? AND due_at < ?)"
                params.extend([from_ts, to_ts])
            elif from_ts is not None:
                sql += " OR (due_at >= ?)"
                params.append(from_ts)
            elif to_ts is not None:
                sql += " OR (due_at < ?)"
                params.append(to_ts)
            sql += ")"
        sql += " ORDER BY done ASC, due_at IS NULL, due_at ASC"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    data = request.json or {}
    content = (data.get("content") or "").strip()[:500]
    if not content:
        return jsonify({"error": "content required"}), 400
    due_at = data.get("due_at")
    end_at = data.get("end_at")
    all_day = 1 if data.get("all_day") else 0
    recurrence = (data.get("recurrence") or "").strip()[:40]
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO reminders
           (wallet, content, due_at, end_at, all_day, recurrence, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (w, content, due_at, end_at, all_day, recurrence, int(time.time())),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return jsonify({
        "id": rid, "content": content, "due_at": due_at, "end_at": end_at,
        "all_day": all_day, "recurrence": recurrence,
    })


@app.route("/api/reminders/<wallet>/<int:rid>", methods=["PATCH", "DELETE"])
def patch_reminder(wallet, rid):
    _migrate_db()
    w = norm_wallet(wallet)
    conn = get_db()
    if request.method == "DELETE":
        conn.execute("DELETE FROM reminders WHERE id = ? AND wallet = ?", (rid, w))
    else:
        data = request.json or {}
        sets = []
        vals = []
        if "done" in data:
            sets.append("done = ?")
            vals.append(1 if data.get("done") else 0)
        if "content" in data:
            c = str(data.get("content") or "").strip()[:500]
            if c:
                sets.append("content = ?")
                vals.append(c)
        if "due_at" in data:
            sets.append("due_at = ?")
            vals.append(data.get("due_at"))
        if "end_at" in data:
            sets.append("end_at = ?")
            vals.append(data.get("end_at"))
        if "all_day" in data:
            sets.append("all_day = ?")
            vals.append(1 if data.get("all_day") else 0)
        if "recurrence" in data:
            sets.append("recurrence = ?")
            vals.append(str(data.get("recurrence") or "").strip()[:40])
        if not sets:
            # default: mark done (legacy)
            sets.append("done = ?")
            vals.append(1)
        vals.extend([rid, w])
        conn.execute(
            f"UPDATE reminders SET {', '.join(sets)} WHERE id = ? AND wallet = ?",
            vals,
        )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/chat-history/<wallet>")
def api_chat_history(wallet):
    """Return recent chat only (default last 36h). Stale logs stay on disk but do not auto-replay on login."""
    w = norm_wallet(wallet)
    limit = min(request.args.get("limit", 40, type=int), 100)
    # max_age_hours=0 means all history (export); default 36 keeps Father's Day from last year off the screen
    max_age_hours = request.args.get("max_age_hours", 36, type=int)
    conn = get_db()
    if max_age_hours and max_age_hours > 0:
        since = int(time.time()) - int(max_age_hours * 3600)
        rows = conn.execute(
            """SELECT id, role, content, created_at FROM chat_log
               WHERE wallet = ? AND content NOT LIKE '[safety:%' AND created_at >= ?
               ORDER BY id DESC LIMIT ?""",
            (w, since, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, role, content, created_at FROM chat_log
               WHERE wallet = ? AND content NOT LIKE '[safety:%'
               ORDER BY id DESC LIMIT ?""",
            (w, limit),
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in reversed(rows)])


@app.route("/api/welcome/<wallet>")
def api_welcome(wallet):
    w = norm_wallet(wallet)
    prof = get_profile(w) or {}
    mems = get_memories(w, 5)
    conn = get_db()
    rems = conn.execute(
        """SELECT content, due_at FROM reminders WHERE wallet = ? AND done = 0
           ORDER BY due_at ASC LIMIT 5""",
        (w,),
    ).fetchall()
    notes_n = conn.execute(
        "SELECT COUNT(*) as c FROM notes WHERE wallet = ?", (w,)
    ).fetchone()["c"]
    conn.close()
    prefs = json.loads(prof.get("preferences") or "{}")
    suggestion = ""
    if prefs.get("gentle_suggestions", True):
        lang = resolve_lang(w)
        name = (prof.get("display_name") or "").strip()
        hour = request.args.get("hour", type=int)
        if hour is None:
            hour = int(time.strftime("%H", time.gmtime()))
        if rems:
            suggestion = languages.gentle_open_suggestion(
                lang, "reminder", name, rems[0]["content"]
            )
        elif mems:
            vent_item = languages.pick_vent_memory_suggestion(mems)
            if vent_item:
                suggestion = languages.gentle_open_suggestion(
                    lang, "vent", name, vent_item
                )
            else:
                suggestion = languages.gentle_open_suggestion(
                    lang, "memory", name, mems[0]["content"]
                )
        elif 5 <= hour < 12:
            suggestion = languages.gentle_open_suggestion(lang, "morning", name)
        elif 18 <= hour < 23:
            suggestion = languages.gentle_open_suggestion(lang, "evening", name)
    return jsonify(
        {
            "name": prof.get("display_name") or "",
            "assistant_name": languages.resolve_assistant_name(prefs),
            "memories": [m["content"] for m in mems],
            "reminders": [dict(r) for r in rems],
            "notes_count": notes_n,
            "open_suggestion": suggestion,
        }
    )


@app.route("/api/export/<wallet>")
def api_export(wallet):
    w = norm_wallet(wallet)
    prof = get_profile(w) or {}
    conn = get_db()
    notes = conn.execute(
        "SELECT id, content, created_at FROM notes WHERE wallet = ? ORDER BY id",
        (w,),
    ).fetchall()
    reminders = conn.execute(
        """SELECT id, content, due_at, done, created_at FROM reminders
           WHERE wallet = ? ORDER BY id""",
        (w,),
    ).fetchall()
    chats = conn.execute(
        """SELECT role, content, created_at FROM chat_log
           WHERE wallet = ? ORDER BY id""",
        (w,),
    ).fetchall()
    conn.close()
    return jsonify(
        {
            "exported_at": int(time.time()),
            "wallet": w,
            "profile": prof,
            "memories": get_memories(w, 500),
            "notes": [dict(r) for r in notes],
            "reminders": [dict(r) for r in reminders],
            "chat_log": [dict(r) for r in chats],
        }
    )


@app.route("/api/data/<wallet>", methods=["DELETE"])
def api_delete_data(wallet):
    w = norm_wallet(wallet)
    conn = get_db()
    for table in ("memories", "notes", "reminders", "chat_log", "usage", "feedback"):
        conn.execute(f"DELETE FROM {table} WHERE wallet = ?", (w,))
    conn.execute("DELETE FROM subscriptions WHERE wallet = ?", (w,))
    conn.execute(
        """UPDATE profiles SET display_name = '', preferences = '{}', bio = '',
           updated_at = ? WHERE wallet = ?""",
        (int(time.time()), w),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "deleted": True})


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    data = request.json or {}
    wallet = norm_wallet(data.get("wallet"))
    rating = (data.get("rating") or "").strip()
    if not wallet or rating not in ("bad", "good"):
        return jsonify({"error": "wallet and rating (good/bad) required"}), 400
    conn = get_db()
    conn.execute(
        """INSERT INTO feedback (wallet, user_message, bot_reply, rating, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            wallet,
            (data.get("user_message") or "")[:500],
            (data.get("bot_reply") or "")[:2000],
            rating,
            int(time.time()),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json or {}
    wallet = norm_wallet(data.get("wallet"))
    message = (data.get("message") or "").strip()
    if not wallet or not message:
        return jsonify({"error": "wallet and message required"}), 400
    allowed, rate_msg = check_rate_limit(wallet)
    if not allowed:
        return jsonify({"error": rate_msg, "code": "rate_limited"}), 429
    ok, reason = can_use_ai(wallet)
    if not ok:
        return jsonify(
            {
                "error": (
                    f"Free AI limit reached ({FREE_ACTIONS_LIFETIME} messages). "
                    f"Subscribe for ${MONTHLY_PRICE_USD:.0f}/mo in LCAI for full chat. "
                    "Calendar, contacts, notes, and dialer stay free."
                ),
                "code": "limit_reached",
                "free_limit": FREE_ACTIONS_LIFETIME,
                "monthly_price_usd": MONTHLY_PRICE_USD,
            }
        ), 402
    ensure_profile(wallet)
    req_lang = (data.get("language") or "").strip()
    local_hour = data.get("local_hour")
    if local_hour is not None:
        try:
            local_hour = int(local_hour) % 24
        except (TypeError, ValueError):
            local_hour = None
    lang = resolve_lang(
        wallet,
        req_lang if req_lang in LANG_NAMES else None,
        message,
    )
    if lang in LANG_NAMES:
        sync_profile_language(wallet, lang)
    safe, safety_category, safety_reply = check_input_safety(message, lang)
    prof_pre = get_profile(wallet) or {}
    prefs_pre = json.loads(prof_pre.get("preferences") or "{}")
    maybe_extract_memory(wallet, message)
    maybe_save_frequent_place(wallet, message)
    maybe_extract_kuaishou_link(wallet, message, prefs_pre)
    log_chat(wallet, "user", message)
    _cleanup_old_jobs()
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "pending",
            "wallet": wallet,
            "created_at": time.time(),
        }
    threading.Thread(
        target=_run_chat_job,
        args=(
            job_id, wallet, message, lang, reason, safe, safety_category, safety_reply,
            local_hour,
        ),
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id, "status": "pending"}), 202


@app.route("/api/chat/status/<job_id>")
def api_chat_status(job_id):
    wallet = norm_wallet(request.args.get("wallet"))
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found", "code": "not_found"}), 404
    if wallet and job.get("wallet") != wallet:
        return jsonify({"error": "forbidden", "code": "forbidden"}), 403
    if job.get("status") == "pending":
        return jsonify({"status": "pending"})
    if job.get("status") == "error":
        return jsonify({"status": "error", "error": job.get("error") or "Chat failed"}), 200
    payload = {k: v for k, v in job.items() if k not in ("wallet", "created_at")}
    return jsonify(payload)


@app.route("/api/catch-up/<wallet>")
def api_catch_up(wallet):
    w = norm_wallet(wallet)
    prof = get_profile(w) or {}
    lang = resolve_lang(w, request.args.get("lang"))
    strings = languages.catch_up_strings(lang)
    name = prof.get("display_name") or strings["default_name"]
    conn = get_db()
    notes_n = conn.execute(
        "SELECT COUNT(*) as c FROM notes WHERE wallet = ?", (w,)
    ).fetchone()["c"]
    rems = conn.execute(
        """SELECT content FROM reminders WHERE wallet = ? AND done = 0
           ORDER BY due_at ASC LIMIT 5""",
        (w,),
    ).fetchall()
    conn.close()
    mems = get_memories(w, 5)
    price = get_lcai_price()
    lines = [strings["greeting"].format(name=name)]
    if rems:
        lines.append(
            strings["reminders"].format(
                items="; ".join(r["content"] for r in rems)
            )
        )
    if notes_n:
        lines.append(strings["notes"].format(n=notes_n))
    if mems:
        lines.append(
            strings["memories"].format(
                items="; ".join(m["content"] for m in mems)
            )
        )
    lines.append(strings["price"].format(price=price))
    if not rems and not notes_n and not mems:
        lines.append(strings["all_clear"])
    return jsonify({"catch_up": "\n".join(lines), "lcai_price": price})


@app.route("/api/briefing/<wallet>")
def api_briefing(wallet):
    w = norm_wallet(wallet)
    prof = get_profile(w) or {}
    lang = resolve_lang(w, request.args.get("lang"))
    strings = languages.briefing_strings(lang)
    name = prof.get("display_name") or strings["default_name"]
    conn = get_db()
    notes_n = conn.execute(
        "SELECT COUNT(*) as c FROM notes WHERE wallet = ?", (w,)
    ).fetchone()["c"]
    rems = conn.execute(
        """SELECT content FROM reminders WHERE wallet = ? AND done = 0
           ORDER BY due_at ASC LIMIT 5""",
        (w,),
    ).fetchall()
    conn.close()
    mems = get_memories(w, 5)
    price = get_lcai_price()
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    prefs = json.loads(prof.get("preferences") or "{}")
    places = languages.frequent_places(prefs)
    wx_line = ""
    weather = None
    if lat is not None and lon is not None:
        weather = fetch_weather(lat=lat, lon=lon)
    elif places.get("home"):
        weather = fetch_weather(city=places["home"])
    if weather and weather.get("current"):
        c = weather["current"]
        wx_line = strings["weather"].format(
            temp=c.get("temperature_2m", "?"),
            desc=languages.wmo_description(c.get("weather_code", 0), lang),
        )
    rem_items = "; ".join(r["content"] for r in rems) or strings["no_reminders"]
    mem_items = "; ".join(m["content"] for m in mems) or strings["no_memories"]
    briefing = (
        f"{strings['greeting'].format(name=name)}\n\n"
        f"{wx_line}\n"
        f"{strings['price'].format(price=price)}\n"
        f"{strings['notes'].format(n=notes_n)}\n"
        f"{strings['reminders'].format(items=rem_items)}\n"
        f"{strings['memories'].format(items=mem_items)}"
    )
    return jsonify({"briefing": briefing, "lcai_price": price})


_WIKI_TRUSTED_SUFFIXES = (".wikimedia.org",)
_visual_cache = {}
_VISUAL_CACHE_TTL = 86400


def _trusted_wiki_thumb(url):
    if not url:
        return None
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        if host.endswith("wikimedia.org"):
            return url
    except Exception:
        pass
    return None


def _wiki_lang(lang):
    return "zh" if lang == "zh" else "en"


def _visual_cache_get(key):
    entry = _visual_cache.get(key)
    if entry and time.time() - entry["ts"] < _VISUAL_CACHE_TTL:
        return entry["data"]
    return None


def _visual_cache_set(key, data):
    _visual_cache[key] = {"ts": time.time(), "data": data}


def _wiki_search_title(query, wiki_lang):
    api = (
        f"https://{wiki_lang}.wikipedia.org/w/api.php?"
        f"action=query&list=search&srsearch={url_quote(query)}&format=json&srlimit=1"
    )
    try:
        r = requests.get(api, timeout=8, headers={"User-Agent": "Binai/1.0"})
        r.raise_for_status()
        hits = (r.json().get("query") or {}).get("search") or []
        if hits:
            return hits[0].get("title")
    except Exception:
        pass
    return None


def _wiki_summary(title, wiki_lang):
    if not title:
        return None
    api = (
        f"https://{wiki_lang}.wikipedia.org/api/rest_v1/page/summary/"
        f"{url_quote(title.replace(' ', '_'), safe='')}"
    )
    try:
        r = requests.get(api, timeout=8, headers={"User-Agent": "Binai/1.0"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        thumb = (data.get("thumbnail") or {}).get("source")
        page = (data.get("content_urls") or {}).get("desktop", {}).get("page")
        return {
            "title": data.get("title") or title,
            "thumbnail": _trusted_wiki_thumb(thumb),
            "wiki_url": page,
            "extract": (data.get("extract") or "")[:200],
        }
    except Exception:
        return None


def build_visual_lookup(message, lang="en"):
    query = languages.extract_visual_query(message)
    if not query:
        return {"ok": False, "reason": "not_visual"}
    lang = lang if lang in languages.LANG_NAMES else "en"
    cache_key = f"{lang}:{query.lower()}"
    cached = _visual_cache_get(cache_key)
    if cached:
        return cached

    wiki_lang = _wiki_lang(lang)
    title = _wiki_search_title(query, wiki_lang)
    if not title and wiki_lang != "en":
        title = _wiki_search_title(query, "en")
        if title:
            wiki_lang = "en"
    summary = _wiki_summary(title, wiki_lang) if title else None

    encoded = url_quote(query)
    if lang == "zh":
        links = [
            {
                "kind": "images",
                "label_key": "visual_more_images",
                "url": f"https://image.baidu.com/search/index?tn=baiduimage&word={encoded}",
            },
            {
                "kind": "web",
                "label_key": "visual_search_web",
                "url": f"https://www.baidu.com/s?wd={encoded}",
            },
        ]
    else:
        links = [
            {
                "kind": "images",
                "label_key": "visual_more_images",
                "url": f"https://duckduckgo.com/?q={encoded}&iax=images&ia=images",
            },
            {
                "kind": "web",
                "label_key": "visual_search_web",
                "url": f"https://duckduckgo.com/?q={encoded}",
            },
        ]
    if summary and summary.get("wiki_url"):
        links.append(
            {
                "kind": "wiki",
                "label_key": "visual_wikipedia",
                "url": summary["wiki_url"],
            }
        )

    payload = {
        "ok": True,
        "query": query,
        "title": (summary or {}).get("title"),
        "thumbnail": (summary or {}).get("thumbnail"),
        "links": links,
    }
    _visual_cache_set(cache_key, payload)
    return payload


@app.route("/api/visual-lookup")
def api_visual_lookup():
    message = (request.args.get("message") or request.args.get("q") or "").strip()
    lang = (request.args.get("lang") or "en").strip().lower()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    return jsonify(build_visual_lookup(message, lang))


_video_cache = {}


def _video_cache_get(key):
    entry = _video_cache.get(key)
    if entry and time.time() - entry["ts"] < _VISUAL_CACHE_TTL:
        return entry["data"]
    return None


def _video_cache_set(key, data):
    _video_cache[key] = {"ts": time.time(), "data": data}


def build_video_lookup(message, lang="en"):
    query = languages.extract_video_query(message)
    if not query:
        return {"ok": False, "reason": "not_video"}
    lang = lang if lang in languages.LANG_NAMES else "en"
    cache_key = f"{lang}:{query.lower()}"
    cached = _video_cache_get(cache_key)
    if cached:
        return cached

    encoded = url_quote(query)
    if lang == "zh":
        links = [
            {
                "kind": "bilibili",
                "label_key": "video_search_bilibili",
                "url": f"https://search.bilibili.com/all?keyword={encoded}",
            },
            {
                "kind": "youtube",
                "label_key": "video_search_youtube",
                "url": f"https://www.youtube.com/results?search_query={encoded}",
            },
            {
                "kind": "baidu",
                "label_key": "video_search_baidu",
                "url": f"https://www.baidu.com/sf/vsearch?pd=video&tn=vsearch&wd={encoded}",
            },
        ]
    else:
        links = [
            {
                "kind": "youtube",
                "label_key": "video_search_youtube",
                "url": f"https://www.youtube.com/results?search_query={encoded}",
            },
            {
                "kind": "ddg",
                "label_key": "video_search_ddg",
                "url": f"https://duckduckgo.com/?q={encoded}&ia=videos&iax=videos",
            },
        ]

    payload = {"ok": True, "query": query, "links": links}
    _video_cache_set(cache_key, payload)
    return payload


@app.route("/api/video-lookup")
def api_video_lookup():
    message = (request.args.get("message") or request.args.get("q") or "").strip()
    lang = (request.args.get("lang") or "en").strip().lower()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    return jsonify(build_video_lookup(message, lang))


_everyday_cache = {}


def _ddg_instant_answer(query):
    api = (
        "https://api.duckduckgo.com/?"
        f"q={url_quote(query)}&format=json&no_html=1&skip_disambig=1"
    )
    try:
        r = requests.get(api, timeout=6, headers={"User-Agent": "Binai/1.0"})
        r.raise_for_status()
        data = r.json()
        text = (data.get("AbstractText") or "").strip()
        url = (data.get("AbstractURL") or "").strip()
        if text and len(text) >= 12:
            return {"hint": text[:280], "hint_url": url or None}
    except Exception:
        pass
    return {}


def build_everyday_lookup(message, lang="en"):
    query = languages.extract_everyday_query(message)
    if not query:
        return {"ok": False, "reason": "not_everyday"}
    lang = lang if lang in languages.LANG_NAMES else "en"
    search_q = languages.everyday_search_query(query, message)
    zip_m = languages._ZIP_PAT.search(message or "")
    if zip_m and zip_m.group(1) not in search_q:
        search_q = f"{search_q} {zip_m.group(1)}"
    cache_key = f"everyday:{lang}:{search_q.lower()}"
    cached = _video_cache_get(cache_key)
    if cached:
        return cached

    encoded = url_quote(search_q)
    maps_q = url_quote(query)
    links = []
    low_q = (query + " " + message).lower()

    if lang == "zh":
        links.append(
            {
                "kind": "maps",
                "label_key": "everyday_maps",
                "url": f"https://map.baidu.com/search/{maps_q}",
            }
        )
        links.append(
            {
                "kind": "web",
                "label_key": "everyday_search",
                "url": f"https://www.baidu.com/s?wd={encoded}",
            }
        )
    else:
        links.append(
            {
                "kind": "maps",
                "label_key": "everyday_maps",
                "url": f"https://www.google.com/maps/search/{encoded}",
            }
        )
        links.append(
            {
                "kind": "web",
                "label_key": "everyday_search",
                "url": f"https://duckduckgo.com/?q={encoded}",
            }
        )
        if re.search(r"\bpost\s+office|usps\b", low_q):
            links.append(
                {
                    "kind": "official",
                    "label_key": "everyday_usps",
                    "url": "https://tools.usps.com/find-location.htm",
                }
            )

    payload = {
        "ok": True,
        "query": query,
        "search_query": search_q,
        "links": links,
    }
    payload.update(_ddg_instant_answer(search_q))
    _video_cache_set(cache_key, payload)
    return payload


@app.route("/api/everyday-lookup")
def api_everyday_lookup():
    message = (request.args.get("message") or request.args.get("q") or "").strip()
    lang = (request.args.get("lang") or "en").strip().lower()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    return jsonify(build_everyday_lookup(message, lang))


@app.route("/api/weather")
def api_weather():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    city = request.args.get("city")
    lang = (request.args.get("lang") or "en").strip().lower()
    data = fetch_weather(lat=lat, lon=lon, city=city)
    if not data:
        return jsonify({"error": "Weather unavailable"}), 404
    cur = data.get("current") or {}
    place = None
    if lat is not None and lon is not None:
        place = reverse_geocode(lat, lon, lang)
    return jsonify(
        {
            "temp_c": cur.get("temperature_2m"),
            "description": languages.wmo_description(cur.get("weather_code", 0), lang),
            "place": place,
            "reply": languages.format_weather_reply(
                lang, place, cur, data.get("daily")
            ),
            "raw": data,
        }
    )


@app.route("/api/weather-chat")
def api_weather_chat():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    city = (request.args.get("city") or "").strip()
    lang = (request.args.get("lang") or "en").strip().lower()
    wallet = request.args.get("wallet", "").strip()
    if wallet and not city:
        prof = get_profile(norm_wallet(wallet)) or {}
        prefs = json.loads(prof.get("preferences") or "{}")
        city = languages.frequent_places(prefs).get("home") or ""
    return jsonify(build_weather_report(lat=lat, lon=lon, city=city or None, lang=lang))


@app.route("/api/save-place")
def api_save_place():
    message = (request.args.get("message") or "").strip()
    lang = (request.args.get("lang") or "en").strip().lower()
    wallet = norm_wallet(request.args.get("wallet") or "")
    key = (request.args.get("key") or "").strip()
    address = (request.args.get("address") or "").strip()
    if key and address:
        report = build_save_place_report(message, lang, key=key, address=address)
    elif message:
        report = build_save_place_report(message, lang)
    else:
        return jsonify({"ok": False, "error": "message or key+address required"}), 400
    if report.get("ok") and wallet:
        save_frequent_place(wallet, report["key"], report["address"])
    return jsonify(report)


@app.route("/api/advice-meta")
def api_advice_meta():
    message = (request.args.get("message") or "").strip()
    lang = (request.args.get("lang") or "en").strip().lower()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    return jsonify(languages.build_advice_meta(message, lang))


@app.route("/api/place-suggestion")
def api_place_suggestion():
    message = (request.args.get("message") or "").strip()
    lang = (request.args.get("lang") or "en").strip().lower()
    wallet = norm_wallet(request.args.get("wallet") or "")
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    prefs = {}
    if wallet:
        prof = get_profile(wallet) or {}
        prefs = json.loads(prof.get("preferences") or "{}")
    return jsonify(build_place_suggestion_report(message, prefs, lang))


@app.route("/api/directions-lookup")
def api_directions_lookup():
    message = (request.args.get("message") or "").strip()
    lang = (request.args.get("lang") or "en").strip().lower()
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    wallet = norm_wallet(request.args.get("wallet") or "")
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    prefs = {}
    if wallet:
        prof = get_profile(wallet) or {}
        prefs = json.loads(prof.get("preferences") or "{}")
    return jsonify(build_directions_report(message, prefs, lat=lat, lon=lon, lang=lang))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8190))
    app.run(host="0.0.0.0", port=port, debug=True)