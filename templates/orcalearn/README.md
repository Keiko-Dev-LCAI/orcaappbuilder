# OrcaLearn Template

A clean, fork-ready scaffold of an AI homeschool / lesson-plan dApp powered by
the Lightchain AIVM. Clone it, fill in the placeholders below with **your own**
values, deploy, and you have a live OrcaLearn-style app where premium AI
payments go to **your** wallet and inference runs through **your** AIVM relay —
not anyone else's.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own wallet and your own server.

## How it's put together

- **Frontend** (`index.html`) — the full app. Static; host it anywhere.
- **Backend** (`server.py` + `aivm_client.py`) — a small relay that talks to
  the Lightchain AIVM. It signs inference jobs with a **service wallet you
  fund** and pays the tiny per-call LCAI job fee. The private key lives **only**
  in an environment variable — never in the code, never in git.

The free tier (starter templates + math quizzes) works with no backend at all.
The backend is only needed for the premium AI lesson/quiz generation.

## 1. Fill in these placeholders

Open `index.html` and replace every placeholder with your own value:

| Placeholder | What to put there |
|---|---|
| `YOUR_LCAI_WALLET` | The Lightchain wallet that should **receive** premium subscription payments (yours) |
| `YOUR_SERVER_URL` | The public URL of the backend you deploy in step 3 (no trailing slash) |
| `YOUR_WC_PROJECT_ID` | Your own WalletConnect project ID (free from cloud.walletconnect.com) |
| `your-domain.example` | Your app's public domain |

Tip: search the files for `YOUR_` and `your-domain` to find them all.

## 2. (Nothing to deploy on-chain)

OrcaLearn has no custom contract — premium access is a plain native-LCAI
payment to `YOUR_LCAI_WALLET`, verified by tx hash. The only on-chain piece is
the shared Lightchain AIVM JobRegistry, which is a public mainnet address
already baked in (`AIVM_JOB_REG`). You don't deploy anything.

## 3. Deploy the backend (for premium AI)

The backend is a plain Python HTTP server. On any host (Railway, Fly, a VPS):

1. Install deps: `pip install -r requirements.txt`
2. Set environment variables:
   - `LIGHTCHAIN_PRIVATE_KEY` — a Lightchain wallet **you** control and fund
     with a little native LCAI (it pays ~0.02 LCAI per AI call). **Never**
     commit this; set it only as an env var.
   - `CORS_ORIGINS` — your domain(s), comma-separated
     (e.g. `https://your-domain.example`).
   - `AIVM_MODEL_PRIMARY` *(optional)* — defaults to `llama3-8b`, the basic
     model. You can point it at another Lightchain model later; see the AIVM
     docs for the available model names.
3. Start it: `python3 server.py` (or let your host run the `Procfile`).
4. Put its public URL into `YOUR_SERVER_URL` in `index.html`.

## 4. Host the frontend

`index.html` is a static file — any static host works (GitHub Pages,
Cloudflare Pages, etc.). Push it, point your domain at it, done.

## 5. Included

- `index.html` — the full app (scrubbed)
- `server.py`, `aivm_client.py` — the AIVM relay backend (scrubbed)
- `requirements.txt`, `Procfile` — backend deploy helpers
- `manifest.json`, `icon-192.png`, `icon-512.png`
- `.nojekyll`, `.gitignore`

## 6. Safety notes (read before you publish)

- This scaffold ships with **placeholders, not real values**. If you leave a
  `YOUR_...` placeholder in, that feature just won't point anywhere — it won't
  leak anyone's data.
- The AI private key is **env-only**. Never hardcode it, never log it, never
  commit a `.env`. The `.gitignore` already excludes `.env`.
- Before you push, scan your own fork for your email / tokens if you'd rather
  stay anonymous — same habit, now it's your call.
