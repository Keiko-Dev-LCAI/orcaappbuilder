# LightWeather Template

A clean, fork-ready scaffold of an **AI weather** dApp — a 7-day forecast with
severe-weather alerts, multi-language UI, an AI chat that explains the weather,
and an optional **premium subscription** paid in LCAI. Clone it, fill in the
placeholders below with **your own** values, deploy, and you have a live
LightWeather-style app where premium payments go to **your** wallet and
inference runs through **your** AIVM service wallet — not anyone else's.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own wallet and your own server.

The free tier (a limited number of AI actions) works out of the box. Premium
subscriptions unlock unlimited AI and send LCAI to your wallet.

## How it's put together

- **Frontend** (`index.html` + icons + `manifest.json`) — the full app,
  multi-language, installable as a PWA. Static; host it anywhere. It talks to
  the backend URL you set (`YOUR_SERVER_URL`, or `window.LIGHTWEATHER_API`).
  WalletConnect (for the premium wallet flow) needs your own project ID.
- **Backend** (`server.py` + `aivm_client.py`) — a small Python / Flask API
  that fetches weather data, relays AI explanations to the Lightchain AIVM, and
  verifies subscription payments by tx hash against the public Lightchain RPC.
  The AIVM service wallet's private key lives **only** in an environment
  variable.

Subscription state lives in a small SQLite DB on your own server (wallet +
expiry only — no personal data).

## 1. Fill in these placeholders

Search the files for `YOUR_` and `your-domain` and replace every one:

| Placeholder | Where | What to put there |
|---|---|---|
| `YOUR_SERVER_URL` | `index.html` | The public URL of the backend you deploy in step 3 (no trailing slash) |
| `YOUR_WC_PROJECT_ID` | `index.html` | Your own WalletConnect project ID (free from cloud.walletconnect.com) |
| `your-domain.example` | `index.html` | Your app's public domain (WalletConnect metadata) |

The receiving wallet and AIVM key are set as backend **environment variables**
(step 3), not hardcoded in the frontend.

## 2. (Nothing to deploy on-chain)

LightWeather has no custom contract — the subscription fee is a plain
native-LCAI payment to the wallet you set as `OWNER_WALLET`, verified by tx
hash against the public Lightchain RPC. The only on-chain piece is the shared
Lightchain AIVM JobRegistry, a public mainnet address already baked into
`aivm_client.py`. You don't deploy anything.

## 3. Deploy the backend

The backend is a plain Python / Flask app (a `Procfile` is included). On any
host (Railway, Fly, a VPS):

1. Install deps: `pip install -r requirements.txt`
2. Set environment variables:
   - `LIGHTCHAIN_PRIVATE_KEY` — a Lightchain wallet **you** control and fund
     with a little native LCAI. It signs the AIVM inference jobs and pays the
     tiny per-job LCAI fee. **Never** commit this; set it only as an env var.
   - `OWNER_WALLET` — the public Lightchain wallet that should **receive** the
     subscription fee (yours). Until this is set, premium payments report
     "not sent to the subscription address" and nothing breaks.
   - `WEATHERAPI_KEY` *(optional)* — a WeatherAPI.com key for richer forecast
     data. If omitted, the app falls back to the free Open-Meteo source.
   - `MONTHLY_PRICE_USD` *(optional)* — subscription price, defaults to `0.50`.
     The LCAI amount floats to this at pay time.
   - `PREMIUM_WHITELIST` *(optional)* — comma-separated wallet addresses that
     always get premium for free (handy for testing). Defaults to empty.
   - `AIVM_MODEL_PRIMARY` *(optional)* — defaults to `llama3-8b`. Point it at
     another Lightchain model later; see the AIVM docs for model names.
   - `DATA_DIR` *(optional)* — where the subscription DB is stored, defaults to
     `/app/data`.
3. Start it: `python3 server.py` (or let your host run the `Procfile`).
4. Put its public URL into `YOUR_SERVER_URL` in `index.html`.

## 4. Host the frontend

`index.html` is a static file — any static host works (GitHub Pages,
Cloudflare Pages, etc.). Push it, point your domain at it, done.

## 5. Included

- `index.html`, `manifest.json`, `maintenance.html`, icons — the frontend
- `server.py`, `aivm_client.py` — the backend (scrubbed)
- `requirements.txt`, `Procfile` — backend deploy helpers
- `.nojekyll`, `.gitignore`

## 6. Safety notes (read before you publish)

- This scaffold ships with **placeholders, not real values**. If you leave
  `YOUR_SERVER_URL` in, the frontend just won't reach a backend — it won't leak
  anyone's data.
- No private keys are hardcoded. The AIVM key and receiving wallet are
  **env-only**. Never commit a `.env`; the `.gitignore` already excludes it.
- Subscriber data (wallet + expiry) lives in `DATA_DIR` on your own server. The
  `.gitignore` excludes `data/` and `*.db` so you never commit it.
- Before you push, scan your own fork for your email / tokens if you'd rather
  stay anonymous — same habit, now it's your call.
