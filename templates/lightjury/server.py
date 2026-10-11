"""LightJury — relay/backend for the AI jury (relationship category, v1 slice).

Flow (pay-first):
  1. /api/precheck   free safety screen. If it trips, we surface help and never
                     reach the pay step. No charge, ever, for a crisis.
  2. user pays $1    in LCAI (native) from their own wallet.
  3. /api/dispute    we re-screen for safety, verify the on-chain payment, then
                     start the 5-juror deliberation in the background. 202 +job_id.
  4. /api/dispute/status  poll. Honest progress while the real panel deliberates
                     (minutes — AIVM calls are serialized on-chain). Then the
                     verdict: plain-English + legalese.

Nothing about who-disputed-what is written to disk. Jobs live in memory with a
TTL and are purged. The AIVM private key is env-only and never logged.

Uses a native LCAI transfer verify + the direct on-chain AIVM client.
Wallet-only, no account, no email.
"""

import json
import os
import threading
import time
import urllib.request
import uuid

from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS

import aivm_client
import jury
import rulepacks
import extract

# ── Config (all env-overridable; no secrets hardcoded) ────────────────────────
LCAI_RPC = os.environ.get("LCAI_RPC", "https://rpc.mainnet.lightchain.ai").strip()
LCAI_CHAIN_ID = int(os.environ.get("LCAI_CHAIN_ID", "9200"))

# Public receiving wallets (set per deployment — public addresses only).
OWNER_WALLET = os.environ.get("OWNER_WALLET", "").strip().lower()

# $1 per verdict. LCAI amount floats to $1 at pay time.
VERDICT_USD = float(os.environ.get("VERDICT_USD", "1.00"))

JOB_TTL_SEC = int(os.environ.get("JOB_TTL_SEC", "3600"))
AIVM_READY = aivm_client.configured()

_data_dir = os.environ.get("DATA_DIR", "/tmp")
os.makedirs(_data_dir, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = extract.MAX_BYTES + (1024 * 1024)  # upload cap
_cors_origins = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "*").split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": _cors_origins}})

_lcai_used_lock = threading.Lock()
_lcai_used = set()

# jobId -> {status, progress, verdict, error, created, paid_with}
_jobs = {}
_jobs_lock = threading.Lock()


def _purge_expired():
    now = time.time()
    with _jobs_lock:
        dead = [j for j, v in _jobs.items() if now - v["created"] > JOB_TTL_SEC]
        for j in dead:
            _jobs.pop(j, None)


def norm_wallet(w):
    return (w or "").strip().lower()


# ── LCAI price (reused portfolio pattern) ─────────────────────────────────────
_lcai_price_cache = {"price": 0.004, "ts": 0}


def get_lcai_price():
    global _lcai_price_cache
    now = time.time()
    if now - _lcai_price_cache["ts"] < 300:
        return _lcai_price_cache["price"]
    try:
        req = urllib.request.Request(
            "https://api.dexscreener.com/latest/dex/search?q=LCAI",
            headers={"User-Agent": "lightjury"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        for p in data.get("pairs") or []:
            base = (p.get("baseToken") or {}).get("symbol", "").upper()
            price = p.get("priceUsd")
            if base == "LCAI" and price:
                _lcai_price_cache = {"price": float(price), "ts": now}
                return _lcai_price_cache["price"]
    except Exception:
        pass
    _lcai_price_cache["ts"] = now
    return _lcai_price_cache["price"]


def lcai_from_usd(usd):
    price = get_lcai_price()
    return round(usd / price, 2) if price else 0.0


def lightchain_rpc(method, params, timeout=15):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    req = urllib.request.Request(
        LCAI_RPC, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.load(resp)
    if out.get("error"):
        raise RuntimeError(out["error"])
    return out.get("result")


def _verify_payment(currency, wallet, tx_hash):
    """Confirm an on-chain $1 payment to the app wallet. Returns (ok, error)."""
    # native LCAI
    if not OWNER_WALLET:
        return False, "LCAI payments are not enabled"
    with _lcai_used_lock:
        if tx_hash.lower() in _lcai_used:
            return False, "This payment has already been used"
    try:
        tx = lightchain_rpc("eth_getTransactionByHash", [tx_hash])
        if not tx or not tx.get("to"):
            return False, "Transaction not found"
        if norm_wallet(tx.get("from")) != wallet:
            return False, "Transaction not from this wallet"
        if norm_wallet(tx.get("to")) != OWNER_WALLET:
            return False, "Payment not sent to the LightJury wallet"
        value_lcai = int(tx.get("value", "0x0"), 16) / 1e18
        required = lcai_from_usd(VERDICT_USD)
        if value_lcai < required * 0.9:
            return False, f"Insufficient LCAI. Need ~{required}, got {value_lcai:.2f}"
    except Exception as e:
        return False, str(e)[:200]
    with _lcai_used_lock:
        _lcai_used.add(tx_hash.lower())
    return True, None


MAX_DOCS = 6
MAX_DOC_TEXT = 60_000


def _clean_documents(raw):
    """Normalize the documents array from a request into [{name,text}]."""
    out = []
    if not isinstance(raw, list):
        return out
    for d in raw[:MAX_DOCS]:
        if not isinstance(d, dict):
            continue
        name = (str(d.get("name") or "document")).strip()[:160] or "document"
        text = (str(d.get("text") or "")).strip()[:MAX_DOC_TEXT]
        if text:
            out.append({"name": name, "text": text})
    return out


def _case_from_request(data):
    return {
        "category": (data.get("category") or "relationship").strip().lower(),
        "relationship": (data.get("relationship") or "").strip()[:300],
        "situation": (data.get("situation") or "").strip()[:6000],
        "other_side": (data.get("other_side") or "").strip()[:3000],
        "outcome": (data.get("outcome") or "").strip()[:1000],
        "user_rules": (data.get("user_rules") or "").strip()[:20000],
        "documents": _clean_documents(data.get("documents")),
    }


def _case_text(case):
    doc_text = " ".join(d.get("text", "") for d in case.get("documents", []))
    return " ".join([case.get("relationship", ""), case.get("situation", ""),
                     case.get("other_side", ""), case.get("outcome", ""),
                     case.get("user_rules", ""), doc_text])


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/api/config")
def api_config():
    price = get_lcai_price()
    return jsonify({
        "chain_id": LCAI_CHAIN_ID,
        "lcai_rpc": LCAI_RPC,
        "lcai_price_usd": price,
        "owner_wallet": OWNER_WALLET,
        "verdict": {
            "usd": VERDICT_USD,
            "lcai": lcai_from_usd(VERDICT_USD),
        },
        "jury_ready": AIVM_READY,
        "panel_size": jury.PANEL_SIZE,
        "categories": [
            {"id": d, "label": rulepacks.RULE_PACKS[d]["label"],
             "needs_rules": bool(rulepacks.RULE_PACKS[d].get("user_rules"))}
            for d in rulepacks.all_domains()
        ],
        "uploads": {
            "enabled": True,
            "accept": sorted(extract.ALLOWED_EXT),
            "max_files": MAX_DOCS,
            "max_mb": extract.MAX_BYTES // (1024 * 1024),
        },
    })


@app.route("/api/precheck", methods=["POST"])
def api_precheck():
    """Free safety screen — runs BEFORE the pay step. No charge ever if it trips."""
    data = request.json or {}
    case = _case_from_request(data)
    if not case["situation"]:
        return jsonify({"error": "Tell us what happened first"}), 400
    flagged, info = jury.screen_for_safety(_case_text(case))
    if flagged:
        return jsonify(info)
    return jsonify({"flagged": False, "clear": True})


@app.route("/api/dispute", methods=["POST"])
def api_dispute():
    """Pay-first: screen -> verify $1 -> start the 5-juror deliberation."""
    _purge_expired()
    data = request.json or {}
    case = _case_from_request(data)
    currency = (data.get("currency") or "lcai").strip().lower()
    wallet = norm_wallet(data.get("wallet"))
    tx_hash = (data.get("tx_hash") or data.get("txHash") or "").strip()

    if not case["situation"]:
        return jsonify({"error": "Tell us what happened first"}), 400
    if not AIVM_READY:
        return jsonify({"error": "The jury engine is not configured on the server"}), 503

    # Safety screen BEFORE touching payment — never bill a crisis.
    flagged, info = jury.screen_for_safety(_case_text(case))
    if flagged:
        return jsonify(info), 200

    if not wallet or not tx_hash:
        return jsonify({"error": "wallet and tx_hash required"}), 400

    ok, err = _verify_payment(currency, wallet, tx_hash)
    if not ok:
        return jsonify({"error": err or "Payment could not be verified"}), 400

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "deliberating",
            "progress": {"done": 0, "total": jury.PANEL_SIZE, "note": "the jury is convening"},
            "verdict": None,
            "error": None,
            "created": time.time(),
            "paid_with": currency,
        }

    def _progress(done, total, note):
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["progress"] = {"done": done, "total": total, "note": note}

    def _run():
        try:
            panel = jury.deliberate(case, progress_cb=_progress)
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job:
                    job["status"] = "done"
                    job["verdict"] = {
                        "verdict": panel["verdict"],
                        "verdict_label": panel["verdict_label"],
                        "agree_count": panel["agree_count"],
                        "panel_size": panel["panel_size"],
                        "confidence": panel["confidence"],
                        "distinct_workers": panel.get("distinct_workers", 0),
                        "plain": panel["opinion"]["plain"],
                        "legalese": panel["opinion"]["legalese"],
                        "jurors": [
                            {"favored": v["favored"], "headline": v["headline"],
                             "reasoning": v["reasoning"], "confidence": v["confidence"],
                             "citations": v.get("citations", [])}
                            for v in panel["votes"]
                        ],
                    }
        except Exception as e:
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job:
                    job["status"] = "error"
                    job["error"] = str(e)[:300]

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": job_id, "status": "deliberating",
                    "panel_size": jury.PANEL_SIZE}), 202


@app.route("/api/dispute/status")
def api_dispute_status():
    job_id = (request.args.get("job_id") or "").strip()
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"error": "job not found or expired"}), 404
        out = {"status": job["status"], "progress": job["progress"]}
        if job.get("verdict"):
            out["verdict"] = job["verdict"]
        if job.get("error"):
            out["error"] = job["error"]
    return jsonify(out)


@app.route("/api/extract", methods=["POST"])
def api_extract():
    """Extract text from an uploaded evidence document, locally. No file is kept.

    Accepts a multipart 'file'. Returns {name, text, chars}. Images are refused —
    the jury is text-only in v1.
    """
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file received"}), 400
    if not extract.allowed(f.filename):
        return jsonify({"error": "Unsupported file type. Use PDF, Word (.docx), "
                                 "or a text file."}), 415
    try:
        data = f.read()
        text = extract.extract_text(f.filename, data)
    except extract.ExtractError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Could not read that file: {str(e)[:120]}"}), 400
    return jsonify({"name": f.filename[:160], "text": text, "chars": len(text)})


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "jury_ready": AIVM_READY})


@app.route("/")
def index():
    here = os.path.dirname(os.path.abspath(__file__))
    idx = os.path.join(here, "index.html")
    if os.path.exists(idx):
        return send_file(idx)
    return jsonify({"service": "lightjury", "ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
