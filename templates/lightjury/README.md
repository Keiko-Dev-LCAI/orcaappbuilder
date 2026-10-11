# LightJury Template

A clean, fork-ready scaffold of an AI dispute / verdict dApp — someone states
their side, pays a flat fee, and a **panel of five genuinely independent AI
jurors** deliberates on the Lightchain AIVM and returns a reasoned verdict.
Clone it, fill in the placeholders below with **your own** values, deploy, and
you have a live LightJury-style app where the verdict fee goes to **your**
wallet and inference runs through **your** AIVM service wallet — not anyone
else's.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own wallet and your own server.

## How it's put together

- **Frontend** (`index.html` + `ethers-6.13.2.umd.min.js` + `lcai-symbol.svg`)
  — the full app. Static; host it anywhere. It talks to the backend URL you
  set (`YOUR_SERVER_URL`, or `window.LIGHTJURY_API`).
- **Backend** (`server.py` + `jury.py` + `aivm_client.py` + `rulepacks.py` +
  `retrieve.py` + `extract.py`) — verifies the on-chain payment, runs a free
  safety pre-check, then convenes **five independent jurors**, each a distinct
  on-chain AIVM job (never one model wearing five hats). The AIVM service
  wallet's private key lives **only** in an environment variable.

Verdicts are advisory, not binding. No dispute content is written to disk —
jobs live in memory with a TTL and are purged.

## 1. Fill in these placeholders

Search the files for `YOUR_` and replace every one:

| Placeholder | Where | What to put there |
|---|---|---|
| `YOUR_SERVER_URL` | `index.html` | The public URL of the backend you deploy in step 3 (no trailing slash) |

The receiving wallet and AIVM key are set as backend **environment variables**
(step 3), not hardcoded in the frontend.

## 2. (Nothing to deploy on-chain)

LightJury has no custom contract — the verdict fee is a plain native-LCAI
payment to the wallet you set as `OWNER_WALLET`, verified by tx hash against the
public Lightchain RPC. The only on-chain piece is the shared Lightchain AIVM
JobRegistry, a public mainnet address already baked into `aivm_client.py`. You
don't deploy anything.

## 3. Deploy the backend

The backend is a plain Python / Flask app (a `Dockerfile` and `Procfile` are
included). On any host (Railway, Fly, a VPS):

1. Install deps: `pip install -r requirements.txt`
2. Set environment variables:
   - `LIGHTCHAIN_PRIVATE_KEY` — a Lightchain wallet **you** control and fund
     with a little native LCAI. It signs the jurors' AIVM jobs and pays the
     tiny per-job LCAI fee (one verdict = five jobs). **Never** commit this;
     set it only as an env var.
   - `OWNER_WALLET` — the public Lightchain wallet that should **receive** the
     verdict fee (yours).
   - `CORS_ORIGINS` — your domain(s), comma-separated
     (e.g. `https://your-domain.example`).
   - `VERDICT_USD` *(optional)* — the fee in USD, defaults to `1.00`. The LCAI
     amount floats to this at pay time.
   - `AIVM_MODEL_PRIMARY` *(optional)* — defaults to `llama3-8b`. Point it at
     another Lightchain model later; see the AIVM docs for model names.
   - `DATA_DIR` *(optional)* — scratch dir for replay-protection state,
     defaults to `/tmp`.
3. Start it: `python3 server.py` (or let your host run the `Procfile` /
   `Dockerfile`).
4. Put its public URL into `YOUR_SERVER_URL` in `index.html`.

A verdict calls the AIVM five times and is serialized on-chain, so it honestly
takes a few minutes — the UI tells users to keep the tab open.

## 4. Host the frontend

`index.html` is a static file — any static host works (GitHub Pages,
Cloudflare Pages, etc.). Push it, point your domain at it, done.

## 5. Included

- `index.html`, `ethers-6.13.2.umd.min.js`, `lcai-symbol.svg` — the frontend
- `server.py`, `jury.py`, `aivm_client.py`, `rulepacks.py`, `retrieve.py`,
  `extract.py` — the backend (scrubbed)
- `requirements.txt`, `Procfile`, `Dockerfile` — backend deploy helpers
- `.nojekyll`, `.gitignore`

## 6. Safety notes (read before you publish)

- This scaffold ships with **placeholders, not real values**. If you leave
  `YOUR_SERVER_URL` in, the frontend just won't reach a backend — it won't leak
  anyone's data.
- The AIVM private key is **env-only**. Never hardcode it, never log it, never
  commit a `.env`. The `.gitignore` already excludes `.env`.
- Payment verification is read-only against the public RPC. If `OWNER_WALLET`
  isn't set, LCAI payments simply report "not enabled" — nothing breaks.
- Before you push, scan your own fork for your email / tokens if you'd rather
  stay anonymous — same habit, now it's your call.
