"""LightStudio — anonymous AI creative studio relay.

Wallet-only. No account, no email, no phone. The user types a prompt, we
generate with Topview, show a watermarked/degraded PREVIEW for free, and only
release the clean file once an on-chain LCAI payment is verified.

Design:
  * Pay-after-preview + degrade-and-unlock. Same file, watermarked until paid.
  * Native LCAI transfer verify with replay protection.
  * Zero-log: prompts and outputs are held only in memory / a temp dir for the
    life of a job, then purged. Nothing about who-made-what is written to disk.
  * Topview is reached through its bundled scripts (TOPVIEW_SKILL_DIR), which
    handle auth, submit and polling. We just parse the result file.
  * AIVM text layer (optional): lyrics + prompt-enhancer run on-chain via the
    same Lightchain worker client Lightdocs uses. Off unless
    LIGHTCHAIN_PRIVATE_KEY is set. That key never leaves the server.

Users pay from their own wallet for image/video/voice/song MP3; we only verify.
Lyrics cost (~0.02 LCAI) is paid by the server AIVM wallet.
"""

import os
import re
import json
import time
import uuid
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import urllib.parse
import urllib.error

from flask import Flask, request, jsonify, send_file, Response, abort
from flask_cors import CORS

import aivm_client

# ── Config (all env-overridable; nothing sensitive hardcoded) ─────────────────
LCAI_RPC = os.environ.get("LCAI_RPC", "https://rpc.mainnet.lightchain.ai").strip()
LCAI_CHAIN_ID = int(os.environ.get("LCAI_CHAIN_ID", "9200"))

# Public receiving wallet for LCAI (native) payments. Set per deployment.
OWNER_WALLET = os.environ.get("OWNER_WALLET", "").strip().lower()
# Per-creation price in USD by modality. LCAI amount is derived from live
# price. All overridable via env.
PRICE_USD = {
    "image": float(os.environ.get("PRICE_USD_IMAGE", "0.10")),
    "video": float(os.environ.get("PRICE_USD_VIDEO", "0.20")),
    "voice": float(os.environ.get("PRICE_USD_VOICE", "0.05")),
    "edit": float(os.environ.get("PRICE_USD_EDIT", "0.10")),
    "animate": float(os.environ.get("PRICE_USD_ANIMATE", "0.20")),
}
# Song is its own product (lyrics free, MP3 paid). ~$0.06 → ~15 LCAI, matching
# the other song app; AIML's cost is ~$0.039/song so this always clears cost.
PRICE_USD["song"] = float(os.environ.get("PRICE_USD_SONG", "0.06"))

# Topview bundled scripts directory (video_gen.py, ai_image.py, text2voice.py).
TOPVIEW_SKILL_DIR = os.environ.get("TOPVIEW_SKILL_DIR", "").strip()
TOPVIEW_IMAGE_MODEL = os.environ.get("TOPVIEW_IMAGE_MODEL", "Seedream 4.0")
TOPVIEW_VIDEO_MODEL = os.environ.get("TOPVIEW_VIDEO_MODEL", "Seedance 1.0 Pro Fast")
TOPVIEW_VOICE_ID = os.environ.get("TOPVIEW_VOICE_ID", "voice-888")
# Cheapest image_edit model that clears $0.10 at ~$0.36/credit: Seedream 4.0
# is 0.15 credits (~$0.054) at 1K. Animate uses Seedance 1.0 Pro Fast i2v at
# 5s/720p = 0.35 credits (~$0.13), which clears the $0.20 sale price.
TOPVIEW_EDIT_MODEL = os.environ.get("TOPVIEW_EDIT_MODEL", "Seedream 4.0")
TOPVIEW_EDIT_RESOLUTION = os.environ.get("TOPVIEW_EDIT_RESOLUTION", "1K")
TOPVIEW_ANIMATE_MODEL = os.environ.get("TOPVIEW_ANIMATE_MODEL", "Seedance 1.0 Pro Fast")
TOPVIEW_ANIMATE_RESOLUTION = os.environ.get("TOPVIEW_ANIMATE_RESOLUTION", "720")
TOPVIEW_ANIMATE_DURATION = int(os.environ.get("TOPVIEW_ANIMATE_DURATION", "5"))
_UPLOAD_MAX_BYTES = 8 * 1024 * 1024
_UPLOAD_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_VOICE_EMOTIONS = ("neutral", "happy", "sad", "angry")
_VOICE_LANG_CODES = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "dutch": "nl", "russian": "ru",
    "japanese": "ja", "korean": "ko", "chinese": "zh-CN", "hindi": "hi",
    "arabic": "ar", "turkish": "tr", "polish": "pl", "swedish": "sv",
}

# ── Model tiers (user choice) ─────────────────────────────────────────────────
# Standard = cheap model, clears cost even on the priciest plan (~$0.36/credit).
# Premium  = the heavy model, priced to stay profitable too. Price is locked
# server-side per tier at generate time (stored on the job), so a client can't
# claim a premium result then pay the standard price at unlock.
TIERS = {
    "image": {
        "standard": {"label": "Standard", "model": TOPVIEW_IMAGE_MODEL,
                     "resolution": "2K", "usd": PRICE_USD["image"]},
        "premium":  {"label": "Premium",
                     "model": os.environ.get("TOPVIEW_IMAGE_MODEL_PREMIUM", "GPT Image 2"),
                     "resolution": "2K",
                     "usd": float(os.environ.get("PRICE_USD_IMAGE_PREMIUM", "1.00"))},
    },
    "video": {
        "standard": {"label": "Standard", "model": TOPVIEW_VIDEO_MODEL,
                     "resolution": "720", "duration": 5, "usd": PRICE_USD["video"]},
        "premium":  {"label": "Premium",
                     "model": os.environ.get("TOPVIEW_VIDEO_MODEL_PREMIUM", "Standard"),
                     "resolution": "720", "duration": 5,
                     "usd": float(os.environ.get("PRICE_USD_VIDEO_PREMIUM", "2.00"))},
    },
    "voice": {
        "standard": {"label": "Standard", "voice_id": TOPVIEW_VOICE_ID,
                     "usd": PRICE_USD["voice"]},
    },
    "edit": {
        "standard": {"label": "Standard", "model": TOPVIEW_EDIT_MODEL,
                     "resolution": TOPVIEW_EDIT_RESOLUTION,
                     "usd": PRICE_USD["edit"]},
    },
    "animate": {
        "standard": {"label": "Standard", "model": TOPVIEW_ANIMATE_MODEL,
                     "resolution": TOPVIEW_ANIMATE_RESOLUTION,
                     "duration": TOPVIEW_ANIMATE_DURATION,
                     "usd": PRICE_USD["animate"]},
    },
}


def get_tier(modality, tier):
    tiers = TIERS.get(modality) or {}
    return tiers.get(tier) or tiers.get("standard")

# Direct on-chain AIVM (Lightdocs client). Key is env-only; never log it.
AIVM_RELAY = os.environ.get("AIVM_RELAY", "").strip()  # unused; kept so old env is harmless
AIVM_READY = aivm_client.configured()

# ── Song generation (lyrics + MP3 on AIML API) ────────────────────────────────
# Lyrics are free to the user (AIML chat). The sung MP3 (MiniMax Music 2.0) is
# rendered only AFTER on-chain payment is verified, so that cost is never
# fronted. Needs AIML_API_KEY set on the server.
AIML_API_KEY = os.environ.get("AIML_API_KEY", "").strip()
AIML_MUSIC_MODEL = os.environ.get("AIML_MUSIC_MODEL", "minimax/music-2.0")
AIML_AUDIO_URL = os.environ.get("AIML_AUDIO_URL",
                                "https://api.aimlapi.com/v2/generate/audio")
AIML_CHAT_URL = os.environ.get("AIML_CHAT_URL",
                               "https://api.aimlapi.com/v1/chat/completions")
AIML_LYRICS_MODEL = os.environ.get("AIML_LYRICS_MODEL", "gpt-4o-mini")

JOB_TTL_SEC = int(os.environ.get("JOB_TTL_SEC", "3600"))  # purge jobs after 1h
_data_dir = os.environ.get("DATA_DIR", tempfile.gettempdir())
_jobs_dir = os.path.join(_data_dir, "lightstudio-jobs")
os.makedirs(_jobs_dir, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = _UPLOAD_MAX_BYTES + (1 * 1024 * 1024)
# CORS: allow the app's own domains. Set CORS_ORIGINS per deployment.
_cors_origins = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "*").split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": _cors_origins}})

_lcai_used_lock = threading.Lock()
_lcai_used = set()  # in-memory replay guard for native LCAI unlocks

# ── Job store (in-memory, TTL, zero-log) ──────────────────────────────────────
# jobId -> {modality, clean_path, preview_path, created, unlocked, token}
_jobs = {}
_jobs_lock = threading.Lock()
_voice_cache = {}  # lang -> (ts, voices)
_voice_cache_lock = threading.Lock()


def _purge_expired():
    now = time.time()
    with _jobs_lock:
        dead = [j for j, v in _jobs.items() if now - v["created"] > JOB_TTL_SEC]
        for j in dead:
            v = _jobs.pop(j, None)
            if v:
                shutil.rmtree(os.path.join(_jobs_dir, j), ignore_errors=True)


def norm_wallet(w):
    return (w or "").strip().lower()


# ── LCAI price ───────────────────────────────────────────────────────────────
_lcai_price_cache = {"price": 0.004, "ts": 0}


def get_lcai_price():
    global _lcai_price_cache
    now = time.time()
    if now - _lcai_price_cache["ts"] < 300:
        return _lcai_price_cache["price"]
    try:
        req = urllib.request.Request(
            "https://api.dexscreener.com/latest/dex/search?q=LCAI",
            headers={"User-Agent": "lightstudio"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        pairs = data.get("pairs") or []
        for p in pairs:
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


def lcai_required(modality):
    return lcai_from_usd(PRICE_USD.get(modality, 0.50))


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


# ── Animate auto-fit: letterbox the uploaded photo so NOTHING gets cropped ────
# Seedance 1.0 Pro Fast i2v rejects aspectRatio ([4000]) and emits 9:16. Pad
# every photo into 9:16 (never crop) so a wide shot stays fully in the frame
# the model actually produces — closest-ratio letterbox was cropped/restaged.
_ANIMATE_RATIO = ("9:16", 9 / 16)


def _edge_fill_color(im):
    """Sample the photo's border so a solid-background shot (e.g. the white
    orca) gets seamless matching padding. Falls back to white if ambiguous."""
    from PIL import Image
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    pts = []
    step_x = max(1, w // 20)
    step_y = max(1, h // 20)
    for x in range(0, w, step_x):
        pts.append(px[x, 0]); pts.append(px[x, h - 1])
    for y in range(0, h, step_y):
        pts.append(px[0, y]); pts.append(px[w - 1, y])
    if not pts:
        return (255, 255, 255)
    r = sum(p[0] for p in pts) // len(pts)
    g = sum(p[1] for p in pts) // len(pts)
    b = sum(p[2] for p in pts) // len(pts)
    # If the border isn't reasonably uniform, don't guess a tint — use white.
    var = sum((p[0] - r) ** 2 + (p[1] - g) ** 2 + (p[2] - b) ** 2 for p in pts)
    if var / len(pts) > 2400:  # noticeably busy edges
        return (255, 255, 255)
    return (r, g, b)


def _fit_photo_for_animate(src):
    """Resize-to-fit + pad the photo into 9:16 so the ENTIRE image stays in
    the frame Seedance i2v actually emits. Returns (padded_temp_path, ratio_str).
    Caller MUST delete the temp file. Never crops."""
    from PIL import Image
    im = Image.open(src)
    im = im.convert("RGB")
    w, h = im.size
    if w <= 0 or h <= 0:
        raise RuntimeError("Could not read the uploaded photo")
    photo_ratio = w / h
    ratio_str, ratio_val = _ANIMATE_RATIO
    # Target canvas: keep the photo's pixels, expand the short edge to 9:16.
    # This never shrinks the picture, only adds padding.
    if ratio_val >= photo_ratio:
        # need a WIDER canvas → pad left/right
        canvas_h = h
        canvas_w = max(w, int(round(h * ratio_val)))
    else:
        # need a TALLER canvas → pad top/bottom
        canvas_w = w
        canvas_h = max(h, int(round(w / ratio_val)))
    fill = _edge_fill_color(im)
    canvas = Image.new("RGB", (canvas_w, canvas_h), fill)
    off_x = (canvas_w - w) // 2
    off_y = (canvas_h - h) // 2
    canvas.paste(im, (off_x, off_y))
    fd, dst = tempfile.mkstemp(suffix=".png", prefix="animate_fit_")
    os.close(fd)
    canvas.save(dst, "PNG")
    return dst, ratio_str


# ── Topview generation (via bundled scripts) ──────────────────────────────────
def _run_topview(modality, prompt, opts, out_dir):
    """Generate with Topview, download the result into out_dir, return its path.

    Raises RuntimeError on failure (caller turns it into a clean error).
    """
    if not TOPVIEW_SKILL_DIR:
        raise RuntimeError("Topview is not configured on the server")
    env = dict(os.environ)  # TOPVIEW_API_KEY / TOPVIEW_UID passed through
    pad_tmp = None  # animate's padded working frame, cleaned up in finally

    if modality == "image":
        script = os.path.join(TOPVIEW_SKILL_DIR, "ai_image.py")
        cmd = ["python3", script, "run", "--type", "text2image",
               "--model", opts.get("model") or TOPVIEW_IMAGE_MODEL,
               "--prompt", prompt,
               "--aspect-ratio", opts.get("aspect_ratio", "1:1"),
               "--resolution", opts.get("resolution", "2K"),
               "--output-dir", out_dir, "-q"]
    elif modality == "video":
        script = os.path.join(TOPVIEW_SKILL_DIR, "video_gen.py")
        vmodel = opts.get("model") or TOPVIEW_VIDEO_MODEL
        # Seedance 1.0 Pro Fast (the Standard tier model) has no native audio;
        # --sound on → Topview 5000. Force sound off for no-audio models no matter
        # what the client sent, so a stray sound=on can never fail the job.
        no_audio = "Pro Fast" in vmodel or vmodel.startswith("Seedance 1.0")
        vsound = "off" if no_audio else (opts.get("sound") or "on")
        cmd = ["python3", script, "run", "--type", "t2v",
               "--model", vmodel,
               "--prompt", prompt,
               "--aspect-ratio", opts.get("aspect_ratio", "16:9"),
               "--resolution", str(opts.get("resolution", "720")),
               "--duration", str(opts.get("duration", 5)),
               "--count", "1",
               "--sound", vsound,
               "--output-dir", out_dir, "-q"]
    elif modality == "voice":
        script = os.path.join(TOPVIEW_SKILL_DIR, "text2voice.py")
        out_file = os.path.join(out_dir, "voice.mp3")
        cmd = ["python3", script, "run",
               "--text", prompt,
               "--voice-id", opts.get("voice_id") or TOPVIEW_VOICE_ID,
               "--output", out_file, "-q"]
        emotion = (opts.get("emotion") or "neutral").strip().lower()
        if emotion and emotion != "neutral":
            cmd.extend(["--emotion", emotion])
        try:
            speed = float(opts.get("speed") or 1.0)
        except (TypeError, ValueError):
            speed = 1.0
        speed = max(0.8, min(1.3, speed))
        if abs(speed - 1.0) > 0.01:
            cmd.extend(["--speed", f"{speed:.2f}"])
    elif modality == "edit":
        src = (opts.get("input_image") or "").strip()
        if not src or not os.path.isfile(src):
            raise RuntimeError("Upload a photo to edit")
        script = os.path.join(TOPVIEW_SKILL_DIR, "ai_image.py")
        cmd = ["python3", script, "run", "--type", "image_edit",
               "--model", opts.get("model") or TOPVIEW_EDIT_MODEL,
               "--prompt", prompt,
               "--aspect-ratio", opts.get("aspect_ratio") or "auto",
               "--resolution", opts.get("resolution") or TOPVIEW_EDIT_RESOLUTION,
               "--input-images", src,
               "--output-dir", out_dir, "-q"]
    elif modality == "animate":
        src = (opts.get("input_image") or "").strip()
        if not src or not os.path.isfile(src):
            raise RuntimeError("Upload a photo to animate")
        script = os.path.join(TOPVIEW_SKILL_DIR, "video_gen.py")
        amodel = opts.get("model") or TOPVIEW_ANIMATE_MODEL
        # Auto-fit: letterbox the photo into 9:16 (Seedance i2v's output
        # shape) so the WHOLE picture animates. pad_tmp is deleted in finally.
        pad_tmp, _fit_ratio = _fit_photo_for_animate(src)
        # Seedance 1.0 Pro Fast i2v rejects aspectRatio ([4000]); the padded
        # 9:16 first-frame carries the ratio ("by image").
        cmd = ["python3", script, "run", "--type", "i2v",
               "--model", amodel,
               "--prompt", prompt,
               "--first-frame", pad_tmp,
               "--resolution", str(opts.get("resolution") or TOPVIEW_ANIMATE_RESOLUTION),
               "--duration", str(opts.get("duration") or TOPVIEW_ANIMATE_DURATION),
               "--count", "1",
               "--sound", "off",
               "--output-dir", out_dir, "-q"]
    else:
        raise RuntimeError(f"Unknown modality: {modality}")

    try:
        subprocess.run(cmd, env=env, check=True, timeout=1200,
                       capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        # The real exception is at the END of a traceback, so surface the tail
        # (last meaningful line) instead of the header.
        raw = (e.stderr or e.stdout or "generation failed").strip()
        last = [ln for ln in raw.splitlines() if ln.strip()]
        msg = last[-1] if last else "generation failed"
        raise RuntimeError(msg[-400:])
    except subprocess.TimeoutExpired:
        raise RuntimeError("Generation timed out — try again")
    finally:
        # The padded animate frame is a temp working file — never persist it.
        if pad_tmp:
            try:
                os.remove(pad_tmp)
            except OSError:
                pass

    files = [os.path.join(out_dir, f) for f in os.listdir(out_dir)
             if not f.startswith("preview")]
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        raise RuntimeError("No output was produced")
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return files[0]


# ── Degrade: make the watermarked / low-res preview ───────────────────────────
WATERMARK_TEXT = os.environ.get("WATERMARK_TEXT", "LIGHTSTUDIO • PREVIEW")


def _degrade_image(src, dst):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(src).convert("RGBA")
    # downscale preview
    max_side = 640
    scale = min(1.0, max_side / max(im.size))
    if scale < 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)))
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(14, im.width // 18))
    except Exception:
        font = ImageFont.load_default()
    step = max(80, im.width // 3)
    for y in range(0, im.height + step, step):
        for x in range(-step, im.width + step, step):
            draw.text((x, y), WATERMARK_TEXT, fill=(255, 255, 255, 70), font=font)
    out = Image.alpha_composite(im, overlay).convert("RGB")
    out.save(dst, "JPEG", quality=70)


def _ffmpeg(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args,
                   check=True, timeout=600)


def _media_duration(path):
    """Seconds of a media file via ffprobe, or 0 on failure."""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            text=True, timeout=30)
        return max(0.0, float((out or "0").strip()))
    except Exception:
        return 0.0


def _trim_audio_bytes(mp3_bytes, seconds):
    """Cut/fade an MP3 to `seconds`. MiniMax has no duration field."""
    tmp_in = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp_out = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    try:
        tmp_in.write(mp3_bytes)
        tmp_in.close()
        tmp_out.close()
        fade = max(0.05, min(0.4, float(seconds) * 0.08))
        st = max(0.0, float(seconds) - fade)
        _ffmpeg(["-i", tmp_in.name, "-t", f"{seconds:.2f}",
                 "-af", f"afade=t=out:st={st:.2f}:d={fade:.2f}",
                 "-c:a", "libmp3lame", "-b:a", "192k", tmp_out.name])
        with open(tmp_out.name, "rb") as f:
            return f.read()
    finally:
        for p in (tmp_in.name, tmp_out.name):
            try:
                os.remove(p)
            except OSError:
                pass


def _degrade_video(src, dst):
    # low-res + tiled drawtext watermark
    vf = (f"scale=480:-2,"
          f"drawtext=text='{WATERMARK_TEXT}':fontcolor=white@0.5:fontsize=20:"
          f"x=mod(t*80\\,w):y=h/2")
    _ffmpeg(["-i", src, "-vf", vf, "-t", "30",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
             "-c:a", "aac", "-b:a", "96k", dst])


def _degrade_audio(src, dst):
    # trim to a short snippet + overlay a periodic watermark tone
    af = ("aevalsrc=0.12*sin(880*2*PI*t)*lt(mod(t\\,4)\\,0.25)[wm];"
          "[0:a][wm]amix=inputs=2:duration=first")
    _ffmpeg(["-i", src, "-t", "20",
             "-filter_complex", af, "-c:a", "libmp3lame", "-b:a", "128k", dst])


def _make_preview(modality, clean_path, out_dir):
    ext = {"image": ".jpg", "video": ".mp4", "voice": ".mp3",
           "edit": ".jpg", "song": ".mp3", "animate": ".mp4"}[modality]
    dst = os.path.join(out_dir, "preview" + ext)
    if modality in ("image", "edit"):
        _degrade_image(clean_path, dst)
    elif modality in ("video", "animate"):
        _degrade_video(clean_path, dst)
    elif modality in ("voice", "song"):
        _degrade_audio(clean_path, dst)
    return dst


# ── Optional AIVM prompt enhancer ─────────────────────────────────────────────
def _http_json(url, data=None, timeout=30):
    """GET or POST JSON. Treats 2xx (including 202) as success."""
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": "lightstudio"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            code = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        code = e.code
        if code >= 400:
            snippet = raw[:200].decode("utf-8", "replace") if raw else ""
            raise RuntimeError(f"AIVM HTTP {code}: {snippet}")
    if not raw:
        return code, {}
    return code, json.loads(raw)


_AIVM_INFRA = (
    "temporarily unavailable",
    "network or aivm issue",
    "replacement transaction underpriced",
    "-32000",
    "aivm timed out",
    "createsession reverted",
    "submitjob reverted",
    "no response from aivm",
)


def _is_aivm_infra(text):
    body = (text or "").strip().lower()
    if not body:
        return True
    return any(p in body for p in _AIVM_INFRA)


def aivm_chat(prompt, timeout=240):
    """Run one on-chain AIVM inference. Raises on failure."""
    if not AIVM_READY:
        raise RuntimeError("AIVM is not configured")
    txt = (aivm_client.infer(prompt, timeout=timeout) or "").strip()
    if _is_aivm_infra(txt):
        raise RuntimeError("Lyrics engine is busy — try again in a moment")
    return txt


def aivm_enhance(prompt):
    """Improve a creative prompt via Lightchain AIVM. Returns enhanced text,
    or the original prompt on any failure."""
    if not AIVM_READY:
        return prompt
    sys = ("Rewrite the user's creative brief into a vivid, detailed generation "
           "prompt. Keep their intent. Reply with ONLY the improved prompt.")
    try:
        txt = aivm_chat(f"{sys}\n\nBrief: {prompt}", timeout=120)
        return txt[:2000] if txt else prompt
    except Exception as e:
        print(f"[AIVM ERROR] {e}", flush=True)
        return prompt


# ── Song: lyrics (free, AIML chat) + MP3 (paid, AIML MiniMax) ─────────────────
_ROMANIZED = {"Chinese", "Japanese", "Korean", "Arabic", "Hindi", "Russian"}
_NO_NOTES = (
    "CRITICAL RULES:\n"
    "- Output ONLY the requested lyrics\n"
    "- NO intro, NO preamble, NO 'here are the lyrics' opening\n"
    "- NO notes, disclaimers, explanations, translations or commentary\n"
    "- NO text before or after the lyrics\n"
    "- Use section labels only: [Verse 1], [Chorus], [Bridge] etc."
)


# Seedance 1.0 Pro Fast (Video/Animate Standard) accepts these clip lengths.
ALLOWED_CLIP_SECONDS = (5, 10, 12)

def _clip_seconds(raw, default=5):
    """Whitelist 5/10/12s. Invalid or missing → default (usually 5)."""
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        n = None
    if n in ALLOWED_CLIP_SECONDS:
        return n
    try:
        d = int(default)
    except (TypeError, ValueError):
        d = 5
    return d if d in ALLOWED_CLIP_SECONDS else 5


def _fit_video_seconds(length):
    """Seconds to trim a MiniMax song so it fits a Video/Animate clip.

    Accepts the current pills (5/10/12s) and the old 6s 'fit video' value.
    """
    s = (length or "").strip().lower().replace(" ", "")
    return {
        "0:05": 5, "0.05": 5, "5s": 5, "5": 5,
        "0:06": 6, "0.06": 6, "6s": 6, "6": 6,
        "0:10": 10, "0.10": 10, "10s": 10, "10": 10,
        "0:12": 12, "0.12": 12, "12s": 12, "12": 12,
    }.get(s)


def _is_fit_video_length(length):
    return _fit_video_seconds(length) is not None


def _length_guide(length):
    secs = _fit_video_seconds(length)
    if secs:
        return (f"Write a TINY {secs}-second hook only: one short [Chorus] of 2–4 "
                "lines. No verses, no bridge, no outro.")
    try:
        mins = float((length or "2:00").replace(":", "."))
    except ValueError:
        mins = 2.0
    if mins <= 1.0:
        return "Write a SHORT song: Verse 1, Chorus only."
    if mins <= 1.5:
        return "Write a short song: Verse 1, Chorus, Verse 2."
    if mins <= 2.0:
        return "Write a standard song: Verse 1, Chorus, Verse 2, Chorus."
    if mins <= 2.5:
        return "Write a full song: Verse 1, Chorus, Verse 2, Chorus, Bridge, Chorus."
    if mins <= 3.0:
        return ("Write a longer song: Verse 1, Pre-Chorus, Chorus, Verse 2, "
                "Pre-Chorus, Chorus, Bridge, Chorus.")
    return ("Write a long song: Intro, Verse 1, Pre-Chorus, Chorus, Verse 2, "
            "Pre-Chorus, Chorus, Bridge, Chorus, Outro.")


def _build_lyrics_prompt(mode, prompt, genre, artist, language, length):
    if language and language != "English":
        if language in _ROMANIZED:
            lang_line = (f"Write in {language} using romanized/latin script only "
                         f"(e.g. pinyin for Chinese, romaji for Japanese). "
                         f"Do not use any non-latin characters.")
        else:
            lang_line = f"Write in {language}."
    else:
        lang_line = ""
    artist_line = f"in the style of {artist}" if artist else ""

    if mode == "own":
        return (f"Take these lyrics and restyle them {artist_line} in the {genre} "
                f"genre, keep the meaning intact. {lang_line}\n{_NO_NOTES}\n\n"
                f"Lyrics to restyle:\n{prompt}")

    return (
        f"Write original song lyrics {artist_line} in the {genre} genre about: "
        f"{prompt}. If the prompt contains section instructions in square brackets "
        f"like [Verse 1: monastery chanting] follow them exactly for that section "
        f"only. Do NOT print the bracket instructions in the output — only print the "
        f"section label like [Verse 1] followed by the lyrics. {lang_line}\n"
        f"{_length_guide(length)}\n{_NO_NOTES}"
    )


def _strip_fences(txt):
    t = (txt or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _aiml_chat(prompt, timeout=60):
    """One AIML chat completion. Key stays in env — never log it."""
    if not AIML_API_KEY:
        raise RuntimeError("Lyrics engine is not configured")
    body = json.dumps({
        "model": AIML_LYRICS_MODEL,
        "messages": [
            {"role": "system",
             "content": "You write original song lyrics only. No preamble."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.85,
        "max_tokens": 1200,
    }).encode()
    req = urllib.request.Request(
        AIML_CHAT_URL, data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {AIML_API_KEY}",
            # urllib's default UA is blocked by Cloudflare (error 1010).
            "User-Agent": "LightStudio/1.0 (lyrics; +https://your-domain.example)",
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        e.read()  # drain; do not log body (may include provider internals)
        raise RuntimeError(f"Lyrics engine HTTP {e.code}") from None
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Lyrics engine returned no text")
    msg = ((choices[0].get("message") or {}).get("content") or "").strip()
    txt = _strip_fences(msg)
    if not txt:
        raise RuntimeError("Lyrics engine returned empty text")
    return txt


def generate_lyrics(mode, prompt, genre, artist, language, length):
    """Write lyrics for free via AIML chat. Raises on failure."""
    if not AIML_API_KEY:
        raise RuntimeError("Lyrics engine is not configured")
    full = _build_lyrics_prompt(mode, prompt, genre, artist, language, length)
    txt = _aiml_chat(full, timeout=60)
    if not txt:
        raise RuntimeError("Lyrics generation failed — try again")
    return txt[:4000]


def generate_song(lyrics, genre, artist, language, length):
    """Render a sung MP3 from lyrics via AIML API (MiniMax Music 2.0).

    Returns raw mp3 bytes. Raises RuntimeError on failure. Mirrors the submit +
    poll flow the model requires.
    """
    if not AIML_API_KEY:
        raise RuntimeError("Song engine (AIML API key) is not configured")
    lang_style = f", sung in {language}" if language and language != "English" else ""
    length_style = f", duration {length}" if length else ""
    style = (f"{genre}, {artist} style{lang_style}{length_style}" if artist
             else f"{genre}{lang_style}{length_style}")
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {AIML_API_KEY}",
               # A real browser-style UA + Accept headers. The default
               # Python-urllib UA was tripping Cloudflare bot protection on
               # AIML's audio endpoint (HTTP 403, error code 1010). The lyrics
               # endpoint already sets a UA and works; the song submit/poll did
               # not, which is why songs 403'd while lyrics went through.
               "Accept": "application/json",
               "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/124.0.0.0 Safari/537.36")}

    body = json.dumps({"model": AIML_MUSIC_MODEL, "prompt": style,
                       "lyrics": (lyrics or "")[:3000]}).encode()
    req = urllib.request.Request(AIML_AUDIO_URL, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            sub = json.load(resp)
    except urllib.error.HTTPError as e:
        # Surface AIML's actual explanation (body), not just the status line.
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace").strip()[:400]
        except Exception:
            pass
        msg = f"Song submit failed: HTTP {e.code} {e.reason}"
        if detail:
            msg += f" — {detail}"
        raise RuntimeError(msg)
    except Exception as e:
        raise RuntimeError(f"Song submit failed: {str(e)[:160]}")
    gen_id = sub.get("id") or sub.get("generation_id")
    if not gen_id:
        raise RuntimeError("Song submit returned no id")

    audio_url = None
    poll_url = f"{AIML_AUDIO_URL}?generation_id={urllib.parse.quote(str(gen_id))}"
    for _ in range(48):  # ~4 min
        time.sleep(5)
        try:
            preq = urllib.request.Request(poll_url, headers=headers)
            with urllib.request.urlopen(preq, timeout=60) as presp:
                pdata = json.load(presp)
        except Exception:
            continue
        status = (pdata.get("status") or "").lower()
        if status in ("completed", "success"):
            af = pdata.get("audio_file") or {}
            audio_url = af.get("url") or pdata.get("audio_url") or pdata.get("url")
            break
        if status in ("failed", "error"):
            err = (pdata.get("error") or {})
            emsg = err.get("message") or err.get("name") or ""
            raise RuntimeError("Song generation failed at the provider"
                               + (f": {str(emsg)[:300]}" if emsg else ""))
    if not audio_url:
        raise RuntimeError("Song generation timed out — try again")

    try:
        # The finished-song download also needs a browser User-Agent — the
        # audio file host is behind Cloudflare too, so the default Python
        # urllib UA gets the same 1010 bot block (HTTP 403) that the submit
        # and poll requests were getting.
        areq = urllib.request.Request(audio_url, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "*/*"})
        with urllib.request.urlopen(areq, timeout=120) as aresp:
            raw = aresp.read()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace").strip()[:300]
        except Exception:
            pass
        msg = f"Could not fetch finished song: HTTP {e.code} {e.reason}"
        if detail:
            msg += f" — {detail}"
        raise RuntimeError(msg)
    except Exception as e:
        raise RuntimeError(f"Could not fetch finished song: {str(e)[:160]}")
    # MiniMax Music 2.0 has no duration parameter (full songs, typically ~1–2
    # min). For the "fit the video" pill we trim/fade to the clip length.
    fit_secs = _fit_video_seconds(length)
    if fit_secs:
        try:
            raw = _trim_audio_bytes(raw, float(fit_secs))
        except Exception as e:
            raise RuntimeError(f"Could not trim song to {fit_secs}s: {str(e)[:120]}")
    return raw


def _verify_payment(currency, wallet, tx_hash, job_usd):
    """Shared on-chain LCAI payment check for unlock + song. Returns (ok, error)."""
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
            return False, "Payment not sent to the studio wallet"
        value_lcai = int(tx.get("value", "0x0"), 16) / 1e18
        required = lcai_from_usd(job_usd)
        if value_lcai < required * 0.9:
            return False, (f"Insufficient LCAI. Need ~{required}, "
                           f"got {value_lcai:.2f}")
    except Exception as e:
        return False, str(e)[:200]
    with _lcai_used_lock:
        _lcai_used.add(tx_hash.lower())
    return True, None


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/api/config")
def api_config():
    price = get_lcai_price()
    modalities = {}
    for m in ("image", "video", "voice", "edit", "animate"):
        tiers_out = {}
        for tname, t in TIERS[m].items():
            tiers_out[tname] = {
                "label": t["label"],
                "usd": t["usd"],
                "lcai": lcai_from_usd(t["usd"]),
            }
        modalities[m] = tiers_out
    return jsonify({
        "chain_id": LCAI_CHAIN_ID,
        "lcai_rpc": LCAI_RPC,
        "lcai_price_usd": price,
        "owner_wallet": OWNER_WALLET,
        "modalities": modalities,
        "aivm_enhance": AIVM_READY,
        "song": {
            "enabled": bool(AIML_API_KEY),
            "usd": PRICE_USD["song"],
            "lcai": lcai_from_usd(PRICE_USD["song"]),
        },
        "voices": {
            "emotions": list(_VOICE_EMOTIONS),
            "speeds": [0.8, 1.0, 1.2],
            "default_voice_id": TOPVIEW_VOICE_ID,
            "languages": list(_VOICE_LANG_CODES.keys()),
        },
        "animate": {
            "enabled": True,
            "model": TOPVIEW_ANIMATE_MODEL,
            "resolution": TOPVIEW_ANIMATE_RESOLUTION,
            "duration": TOPVIEW_ANIMATE_DURATION,
        },
        "clip_seconds": list(ALLOWED_CLIP_SECONDS),
    })


@app.route("/api/enhance", methods=["POST"])
def api_enhance():
    data = request.json or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    return jsonify({"prompt": aivm_enhance(prompt)})


def _parse_generate_request():
    """JSON body, or multipart (edit photo upload). Never log the file."""
    ctype = (request.content_type or "")
    if "multipart/form-data" in ctype:
        modality = (request.form.get("modality") or "").strip()
        prompt = (request.form.get("prompt") or "").strip()
        tier = (request.form.get("tier") or "standard").strip().lower()
        try:
            opts = json.loads(request.form.get("options") or "{}")
        except Exception:
            opts = {}
        if not isinstance(opts, dict):
            opts = {}
        upload = request.files.get("image") or request.files.get("file")
        return modality, prompt, tier, opts, upload
    data = request.json or {}
    return ((data.get("modality") or "").strip(),
            (data.get("prompt") or "").strip(),
            (data.get("tier") or "standard").strip().lower(),
            data.get("options") or {},
            None)


def _save_upload_ephemeral(upload, dest_dir):
    """Write the photo for this job only. Caller must delete it afterwards."""
    if upload is None or not getattr(upload, "filename", None):
        raise RuntimeError("Upload a photo first")
    ext = os.path.splitext(upload.filename or "")[1].lower()
    if ext not in _UPLOAD_EXTS:
        raise RuntimeError("Photo must be JPG, PNG, or WebP")
    path = os.path.join(dest_dir, "upload" + ext)
    upload.save(path)
    try:
        if os.path.getsize(path) > _UPLOAD_MAX_BYTES:
            raise RuntimeError("Photo is too large (max 8 MB)")
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return path


@app.route("/api/generate", methods=["POST"])
def api_generate():
    _purge_expired()
    modality, prompt, tier, opts, upload = _parse_generate_request()
    if not isinstance(opts, dict):
        opts = {}
    if modality not in ("image", "video", "voice", "edit", "animate"):
        return jsonify({"error": "modality must be image, video, voice, edit or animate"}), 400
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    if modality == "edit" and upload is None:
        return jsonify({"error": "Upload a photo to edit"}), 400
    if modality == "animate" and upload is None:
        return jsonify({"error": "Upload a photo to animate"}), 400

    tinfo = get_tier(modality, tier)
    if not tinfo:
        return jsonify({"error": "invalid tier"}), 400
    # Server-authoritative: the chosen tier dictates model/resolution/duration
    # and the price. The client cannot override these. Voice speaker is an
    # input on the same paid tier, so keep the client's voice_id if present.
    client_voice = (opts.get("voice_id") or "").strip() if modality == "voice" else ""
    client_dur = opts.get("duration")
    for key in ("model", "resolution", "duration", "voice_id"):
        if key in tinfo:
            opts[key] = tinfo[key]
    if modality in ("video", "animate"):
        opts["duration"] = _clip_seconds(client_dur, tinfo.get("duration") or 5)
    if modality == "voice":
        if client_voice:
            opts["voice_id"] = client_voice
        elif (opts.get("voice_id") or "") in ("", "voice-888"):
            cat = _load_voices("en")
            if cat:
                opts["voice_id"] = cat[0]["id"]
        emo = (opts.get("emotion") or "neutral").strip().lower()
        opts["emotion"] = emo if emo in _VOICE_EMOTIONS else "neutral"
        try:
            opts["speed"] = max(0.8, min(1.3, float(opts.get("speed") or 1.0)))
        except (TypeError, ValueError):
            opts["speed"] = 1.0

    job_id = uuid.uuid4().hex
    out_dir = os.path.join(_jobs_dir, job_id)
    os.makedirs(out_dir, exist_ok=True)
    upload_path = None
    try:
        if modality in ("edit", "animate"):
            upload_path = _save_upload_ephemeral(upload, out_dir)
            opts["input_image"] = upload_path
        if opts.get("enhance"):
            prompt = aivm_enhance(prompt)
        clean = _run_topview(modality, prompt, opts, out_dir)
        preview = _make_preview(modality, clean, out_dir)
    except Exception as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        return jsonify({"error": str(e)[:300]}), 502
    finally:
        # Uploaded photos are other people's data: delete as soon as the job
        # has consumed them, success or fail. Generated output stays for TTL.
        if upload_path:
            try:
                os.remove(upload_path)
            except OSError:
                pass

    with _jobs_lock:
        _jobs[job_id] = {
            "modality": modality,
            "tier": tier,
            "usd": tinfo["usd"],
            "clean_path": clean,
            "preview_path": preview,
            "created": time.time(),
            "unlocked": False,
            "token": None,
        }
    return jsonify({
        "job_id": job_id,
        "modality": modality,
        "tier": tier,
        "preview_url": f"/preview/{job_id}",
        "price": {
            "usd": tinfo["usd"],
            "lcai": lcai_from_usd(tinfo["usd"]),
        },
    })


@app.route("/preview/<job_id>")
def serve_preview(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        abort(404)
    return send_file(job["preview_path"])


@app.route("/api/unlock", methods=["POST"])
def api_unlock():
    data = request.json or {}
    job_id = (data.get("job_id") or "").strip()
    currency = (data.get("currency") or "lcai").strip().lower()
    wallet = norm_wallet(data.get("wallet"))
    tx_hash = (data.get("tx_hash") or data.get("txHash") or "").strip()

    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found or expired"}), 404
    if not wallet or not tx_hash:
        return jsonify({"error": "wallet and tx_hash required"}), 400

    modality = job["modality"]
    job_usd = job.get("usd", PRICE_USD.get(modality, 0.50))

    ok, err = _verify_payment(currency, wallet, tx_hash, job_usd)
    if not ok:
        return jsonify({"error": err or "Payment could not be verified"}), 400

    token = uuid.uuid4().hex
    with _jobs_lock:
        job["unlocked"] = True
        job["token"] = token
    return jsonify({"unlocked": True, "file_url": f"/file/{job_id}?token={token}",
                    "paid_with": currency})


@app.route("/file/<job_id>")
def serve_file(job_id):
    token = request.args.get("token", "")
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        abort(404)
    if not job["unlocked"] or not token or token != job["token"]:
        abort(403)
    fname = {"image": "lightstudio.jpg", "video": "lightstudio.mp4",
             "voice": "lightstudio.mp3",
             "song": "lightstudio-song.mp3",
             "edit": "lightstudio-edit.jpg",
             "animate": "lightstudio-animate.mp4",
             "mix": "lightstudio-mix.mp4"}.get(job["modality"], "lightstudio.bin")
    return send_file(job["clean_path"], as_attachment=True, download_name=fname)


# ── Song routes ───────────────────────────────────────────────────────────────
@app.route("/api/lyrics", methods=["POST"])
def api_lyrics():
    """Start free lyrics (AIML chat). Returns 202 {job_id} — poll /api/lyrics/status."""
    data = request.json or {}
    mode = (data.get("mode") or "song").strip().lower()
    prompt = (data.get("prompt") or "").strip()
    genres = data.get("genres") or []
    if isinstance(genres, str):
        genres = [genres]
    genre = ", ".join([g for g in genres if g][:3]) or "pop"
    artist = (data.get("artist") or "").strip()
    language = (data.get("language") or "English").strip()
    length = (data.get("length") or "2:00").strip()
    if not prompt:
        return jsonify({"error": "Type a topic or your own lyrics first"}), 400
    if not AIML_API_KEY:
        return jsonify({"error": "Lyrics engine is not configured"}), 503
    _purge_expired()
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "modality": "lyrics",
            "status": "pending",
            "lyrics": "",
            "error": None,
            "created": time.time(),
            "unlocked": False,
            "token": None,
        }

    def _run():
        try:
            lyrics = generate_lyrics(mode, prompt, genre, artist, language, length)
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job:
                    job["status"] = "done"
                    job["lyrics"] = lyrics
        except Exception as e:
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job:
                    job["status"] = "error"
                    job["error"] = str(e)[:300]

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": job_id, "status": "pending"}), 202


@app.route("/api/lyrics/status")
def api_lyrics_status():
    job_id = (request.args.get("job_id") or "").strip()
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or job.get("modality") != "lyrics":
            return jsonify({"error": "job not found"}), 404
        out = {"status": job.get("status") or "pending"}
        if job.get("lyrics"):
            out["lyrics"] = job["lyrics"]
        if job.get("error"):
            out["error"] = job["error"]
    return jsonify(out)


@app.route("/api/song", methods=["POST"])
def api_song():
    """Render the paid MP3. Payment is verified BEFORE any AIML cost is spent."""
    _purge_expired()
    data = request.json or {}
    lyrics = (data.get("lyrics") or "").strip()
    genres = data.get("genres") or []
    if isinstance(genres, str):
        genres = [genres]
    genre = ", ".join([g for g in genres if g][:3]) or "pop"
    artist = (data.get("artist") or "").strip()
    language = (data.get("language") or "English").strip()
    length = (data.get("length") or "2:00").strip()
    currency = (data.get("currency") or "lcai").strip().lower()
    wallet = norm_wallet(data.get("wallet"))
    tx_hash = (data.get("tx_hash") or data.get("txHash") or "").strip()

    if not lyrics:
        return jsonify({"error": "No lyrics to sing — generate lyrics first"}), 400
    if not wallet or not tx_hash:
        return jsonify({"error": "wallet and tx_hash required"}), 400
    if not AIML_API_KEY:
        return jsonify({"error": "Song generation is not enabled on the server"}), 503

    # Verify payment FIRST so the AIML cost is never fronted.
    ok, err = _verify_payment(currency, wallet, tx_hash, PRICE_USD["song"])
    if not ok:
        return jsonify({"error": err or "Payment could not be verified"}), 400

    job_id = uuid.uuid4().hex
    out_dir = os.path.join(_jobs_dir, job_id)
    os.makedirs(out_dir, exist_ok=True)
    try:
        mp3 = generate_song(lyrics, genre, artist, language, length)
        clean = os.path.join(out_dir, "song.mp3")
        with open(clean, "wb") as f:
            f.write(mp3)
    except Exception as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        return jsonify({"error": str(e)[:300]}), 502

    token = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "modality": "song",
            "tier": "standard",
            "usd": PRICE_USD["song"],
            "clean_path": clean,
            "preview_path": clean,
            "created": time.time(),
            "unlocked": True,
            "token": token,
        }
    return jsonify({"song_url": f"/file/{job_id}?token={token}",
                    "paid_with": currency})


def _voice_lang_code(language):
    raw = (language or "en").strip()
    if not raw:
        return "en"
    mapped = _VOICE_LANG_CODES.get(raw.lower())
    if mapped:
        return mapped
    return raw


def _load_voices(lang_code):
    """Cached Topview voice catalog for one language. No demo URLs stored."""
    now = time.time()
    with _voice_cache_lock:
        hit = _voice_cache.get(lang_code)
        if hit and now - hit[0] < 3600:
            return hit[1]
    if not TOPVIEW_SKILL_DIR:
        return []
    script = os.path.join(TOPVIEW_SKILL_DIR, "voice.py")
    try:
        proc = subprocess.run(
            ["python3", script, "list", "--language", lang_code,
             "--size", "40", "--json", "-q"],
            capture_output=True, text=True, timeout=30, env=dict(os.environ))
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception:
        return []
    out = []
    for v in payload.get("data") or []:
        vid = (v.get("voiceId") or "").strip()
        if not vid:
            continue
        out.append({
            "id": vid,
            "name": (v.get("voiceName") or vid)[:80],
            "gender": v.get("gender") or "",
            "age": v.get("age") or "",
            "accent": v.get("accent") or "",
            "style": v.get("style") or "",
            "language": v.get("language") or lang_code,
        })
    with _voice_cache_lock:
        _voice_cache[lang_code] = (now, out)
    return out


@app.route("/api/voices")
def api_voices():
    lang = _voice_lang_code(request.args.get("language") or "en")
    voices = _load_voices(lang)
    return jsonify({"language": lang, "voices": voices,
                    "emotions": list(_VOICE_EMOTIONS),
                    "speeds": [0.8, 1.0, 1.2]})


def _unlocked_job(job_id, token, allowed):
    if not job_id or not token:
        return None
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        if not job.get("unlocked") or job.get("token") != token:
            return None
        if job.get("modality") not in allowed:
            return None
        path = job.get("clean_path")
        if not path or not os.path.isfile(path):
            return None
        return job


def _mux_audio_onto_video(video_path, audio_path, dest):
    """Replace (or add) the video's audio. Trim/fade audio if longer than clip."""
    vdur = _media_duration(video_path)
    adur = _media_duration(audio_path)
    if vdur <= 0:
        raise RuntimeError("Could not read video length")
    fade = min(0.4, max(0.05, vdur * 0.08))
    if adur > vdur + 0.05:
        st = max(0.0, vdur - fade)
        af = f"afade=t=out:st={st:.2f}:d={fade:.2f}"
        _ffmpeg(["-i", video_path, "-i", audio_path,
                 "-map", "0:v:0", "-map", "1:a:0",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                 "-af", af, "-t", f"{vdur:.3f}", dest])
    else:
        # Audio shorter or equal: let it end; remaining video is silent.
        _ffmpeg(["-i", video_path, "-i", audio_path,
                 "-map", "0:v:0", "-map", "1:a:0",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                 "-t", f"{vdur:.3f}", dest])


@app.route("/api/combine", methods=["POST"])
def api_combine():
    """Free mux of an unlocked video + unlocked song/voice. Never mux previews."""
    _purge_expired()
    data = request.json or {}
    vjob = _unlocked_job((data.get("video_job_id") or "").strip(),
                         (data.get("video_token") or "").strip(),
                         ("video", "animate"))
    ajob = _unlocked_job((data.get("audio_job_id") or "").strip(),
                         (data.get("audio_token") or "").strip(),
                         ("song", "voice"))
    if not vjob:
        return jsonify({"error": "Pay to unlock the video first"}), 403
    if not ajob:
        return jsonify({"error": "Pay to unlock the song or voice first"}), 403
    job_id = uuid.uuid4().hex
    out_dir = os.path.join(_jobs_dir, job_id)
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, "mix.mp4")
    try:
        _mux_audio_onto_video(vjob["clean_path"], ajob["clean_path"], dest)
    except Exception as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        return jsonify({"error": str(e)[:300]}), 502
    token = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "modality": "mix",
            "tier": "standard",
            "usd": 0,
            "clean_path": dest,
            "preview_path": dest,
            "created": time.time(),
            "unlocked": True,
            "token": token,
        }
    return jsonify({"file_url": f"/file/{job_id}?token={token}",
                    "job_id": job_id})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "topview": bool(TOPVIEW_SKILL_DIR),
                    "aivm": AIVM_READY})


@app.route("/")
def index():
    here = os.path.dirname(os.path.abspath(__file__))
    return send_file(os.path.join(here, "index.html"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8188"))
    app.run(host="0.0.0.0", port=port)
