#!/usr/bin/env python3
"""
Answer Agent — a tiny server that answers one question at a time using the
Lightchain AIVM, and pays per answer. Nothing runs while nobody is asking.

Deploy this whole folder to Railway. Set ONE environment variable:
    LIGHTCHAIN_PRIVATE_KEY = the private key of the wallet that pays for answers

Optional environment variables:
    AGENT_SYSTEM    = one line describing your agent's job / personality
    DAILY_LCAI_CAP  = max LCAI to spend per day (default 25) — a safety brake
    RATE_PER_MIN    = max questions per visitor per minute (default 4)
    RATE_PER_DAY    = max questions per visitor per day (default 40)

Your key stays in Railway's environment. It is never shown on the page and
is never written into the downloaded copy.
"""
import json, os, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

import aivm_client

PORT = int(os.environ.get("PORT", "8000"))
HERE = os.path.dirname(os.path.abspath(__file__))

AGENT_SYSTEM = os.environ.get(
    "AGENT_SYSTEM",
    "You are a friendly, concise assistant. Answer the question clearly in plain language."
).strip()
DAILY_LCAI_CAP  = float(os.environ.get("DAILY_LCAI_CAP", "25"))
RATE_PER_MIN    = int(os.environ.get("RATE_PER_MIN", "4"))
RATE_PER_DAY    = int(os.environ.get("RATE_PER_DAY", "40"))
LCAI_PER_ANSWER = 0.02  # flat per-call cost on Lightchain

STATIC = {
    "/": "index.html", "/index.html": "index.html",
    "/manifest.json": "manifest.json",
    "/icon-192.png": "icon-192.png", "/icon-512.png": "icon-512.png",
}
CTYPE = {".html": "text/html; charset=utf-8", ".json": "application/json", ".png": "image/png"}

_lock = threading.Lock()
_hits = {}                      # ip -> [timestamps]
_spent_day = {"day": "", "lcai": 0.0}


def _today():
    return time.strftime("%Y-%m-%d")


def _rate_ok(ip):
    now = time.time()
    with _lock:
        hist = [t for t in _hits.get(ip, []) if now - t < 86400]
        if len([t for t in hist if now - t < 60]) >= RATE_PER_MIN or len(hist) >= RATE_PER_DAY:
            _hits[ip] = hist
            return False
        hist.append(now)
        _hits[ip] = hist
        return True


def _budget_ok():
    with _lock:
        if _spent_day["day"] != _today():
            _spent_day["day"] = _today()
            _spent_day["lcai"] = 0.0
        return _spent_day["lcai"] + LCAI_PER_ANSWER <= DAILY_LCAI_CAP


def _charge():
    with _lock:
        _spent_day["lcai"] += LCAI_PER_ANSWER


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep logs quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        fname = STATIC.get(urlparse(self.path).path)
        if not fname:
            self._send(404, {"error": "not found"}); return
        full = os.path.join(HERE, fname)
        if not os.path.exists(full):
            self._send(404, {"error": "missing file"}); return
        with open(full, "rb") as fh:
            data = fh.read()
        self._send(200, data, CTYPE.get(os.path.splitext(fname)[1], "application/octet-stream"))

    def do_POST(self):
        if urlparse(self.path).path != "/ask":
            self._send(404, {"error": "not found"}); return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._send(400, {"error": "bad request"}); return
        question = (payload.get("question") or "").strip()[:2000]
        if not question:
            self._send(400, {"error": "Please type a question."}); return
        if not aivm_client.configured():
            self._send(503, {"error": "This agent isn't connected to the AI yet. The owner needs to set LIGHTCHAIN_PRIVATE_KEY."}); return
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        if not _rate_ok(ip):
            self._send(429, {"error": "You're asking a lot — give it a minute and try again."}); return
        if not _budget_ok():
            self._send(429, {"error": "This agent has hit its spending cap for today. Try again tomorrow."}); return
        prompt = f"{AGENT_SYSTEM}\n\nQuestion: {question}\n\nAnswer:"
        try:
            answer = aivm_client.infer(prompt)
            _charge()
            self._send(200, {"answer": answer})
        except Exception:
            self._send(502, {"error": "The AI is busy right now — give it a moment and try again."})


if __name__ == "__main__":
    print(f"Answer Agent starting on port {PORT}…")
    print("  AI:", "Lightchain AIVM (connected)" if aivm_client.configured()
          else "NOT CONNECTED — set LIGHTCHAIN_PRIVATE_KEY")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
