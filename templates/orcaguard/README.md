# OrcaGuard Template

A clean, fork-ready scaffold of a **crypto safety assistant** dApp — paste a
token contract, a URL, or a wallet address and get a plain-language risk read,
backed by a built-in knowledge base and the Lightchain AIVM. There's an
optional WalletConnect "wallet audit" that scans the connected wallet's tokens.
Clone it, fill in the placeholders below with **your own** values, deploy, and
you have a live OrcaGuard-style app running through **your** AIVM service
wallet — not anyone else's.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own wallet and your own server.

OrcaGuard is **free** — there is no payment, no paywall, no fee. The only
wallet the app ever touches on-chain is the AIVM service wallet that signs the
AI inference jobs (an env var you control).

## How it's put together

- **Frontend** (`index.html` + icons + `i18n-ui.js` + `manifest.json`) — the
  full app, multi-language, installable as a PWA. Static; host it anywhere. It
  talks to the backend URL you set (`YOUR_SERVER_URL`, or `window.GUARD_API`).
  WalletConnect (optional wallet-audit feature) needs your own project ID.
- **Backend** (`orcaguard-server.py` + `aivm_client.py`) — a small Python API
  that serves a curated safety knowledge base (known-good contracts, scam
  patterns, URL heuristics) and relays the harder questions to the Lightchain
  AIVM. The AIVM service wallet's private key lives **only** in an environment
  variable.

No user data is written to disk — lookups are stateless.

## 1. Fill in these placeholders

Search the files for `YOUR_` and `your-domain` and replace every one:

| Placeholder | Where | What to put there |
|---|---|---|
| `YOUR_SERVER_URL` | `index.html` | The public URL of the backend you deploy in step 3 (no trailing slash) |
| `YOUR_WC_PROJECT_ID` | `index.html` | Your own WalletConnect project ID (free from cloud.walletconnect.com) — only needed for the optional wallet-audit feature |
| `your-domain.example` | `index.html`, `manifest.json`, `i18n-ui.js` | Your app's public domain |

The AIVM key is set as a backend **environment variable** (step 3), not
hardcoded in the frontend.

## 2. (Nothing to deploy on-chain)

OrcaGuard has no custom contract and takes no payment. The only on-chain piece
is the shared Lightchain AIVM JobRegistry, a public mainnet address already
baked into `aivm_client.py`. You don't deploy anything.

## 3. Deploy the backend

The backend is a plain Python app (a `Procfile` is included). On any host
(Railway, Fly, a VPS):

1. Install deps: `pip install -r requirements.txt`
2. Set environment variables:
   - `LIGHTCHAIN_PRIVATE_KEY` — a Lightchain wallet **you** control and fund
     with a little native LCAI. It signs the AIVM inference jobs and pays the
     tiny per-job LCAI fee. **Never** commit this; set it only as an env var.
   - `CORS_ORIGINS` — your domain(s), comma-separated
     (e.g. `https://your-domain.example`).
   - `AIVM_MODEL_PRIMARY` *(optional)* — defaults to `llama3-8b`. Point it at
     another Lightchain model later; see the AIVM docs for model names.
   - `PORT` *(optional)* — defaults to `8186`.
3. Start it: `python3 orcaguard-server.py` (or let your host run the
   `Procfile`).
4. Put its public URL into `YOUR_SERVER_URL` in `index.html`.

## 4. Host the frontend

`index.html` is a static file — any static host works (GitHub Pages,
Cloudflare Pages, etc.). Push it, point your domain at it, done.

## 5. Included

- `index.html`, `i18n-ui.js`, `manifest.json`, `maintenance.html`, icons,
  `orca-mascot.png` — the frontend
- `orcaguard-server.py`, `aivm_client.py` — the backend (scrubbed)
- `requirements.txt`, `Procfile` — backend deploy helpers
- `.nojekyll`, `.gitignore`

## 6. Safety notes (read before you publish)

- This scaffold ships with **placeholders, not real values**. If you leave
  `YOUR_SERVER_URL` in, the frontend just won't reach a backend — it won't leak
  anyone's data.
- The AIVM private key is **env-only**. Never hardcode it, never log it, never
  commit a `.env`. The `.gitignore` already excludes `.env`.
- The safety knowledge base ships with publicly-known ecosystem facts only.
  Review and adjust it for your own audience before publishing.
- Before you push, scan your own fork for your email / tokens if you'd rather
  stay anonymous — same habit, now it's your call.
