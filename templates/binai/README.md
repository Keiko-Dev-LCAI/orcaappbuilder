# Binai Template

A clean, fork-ready scaffold of a personal AI assistant dApp — chat that
remembers you, notes, reminders and a simple paid subscription — powered by the
Lightchain AIVM. Clone it, fill in the placeholders below with **your own**
values, deploy, and you have a live Binai-style app where premium AI payments
go to **your** wallet and inference runs through **your** AIVM relay — not
anyone else's.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own wallet and your own server.

## How it's put together

- **Frontend** (`index.html`) — the full app. Static; host it anywhere. It
  talks to the backend it's served from (or set `window.BINAI_API`).
- **Backend** (`server.py`) — a small API that stores each user's memory/notes
  and relays premium chat to a **separate AIVM inference service** you point it
  at (`AIVM_RELAY`). Subscription payments are plain native-LCAI transfers to a
  wallet **you** control, verified by tx hash.

The free tier (a limited number of AI actions) works out of the box. Paid
subscriptions unlock unlimited use and send LCAI to your wallet.

## 1. Fill in these placeholders

Search the files for `YOUR_` and `your-domain` and replace every one:

| Placeholder | Where | What to put there |
|---|---|---|
| `YOUR_LCAI_WALLET` | `server.py` (`OWNER_WALLET`) | The Lightchain wallet that should **receive** subscription payments (yours) |
| `YOUR_AIVM_RELAY` | `server.py` (`AIVM_RELAY`) | The base URL of your AIVM inference service (the backend calls `{AIVM_RELAY}/api/chat`) |
| `YOUR_WC_PROJECT_ID` | `index.html` | Your own WalletConnect project ID (free from cloud.walletconnect.com) |
| `your-domain.example` | both | Your app's public domain |

## 2. (Nothing to deploy on-chain)

Binai has no custom contract — premium access is a native-LCAI payment to
`YOUR_LCAI_WALLET`, verified by tx hash against the public Lightchain RPC
(`rpc.mainnet.lightchain.ai`, already baked in). You don't deploy anything.

## 3. Deploy the backend

The backend is a plain Python / Flask app. On any host (Railway, Fly, a VPS):

1. Install deps: `pip install -r requirements.txt`
2. Set environment variables:
   - `AIVM_RELAY` — the base URL of the AIVM inference service premium chat is
     relayed to (replaces `YOUR_AIVM_RELAY`).
   - `OWNER_WALLET` — the Lightchain wallet that receives subscription payments
     (replaces `YOUR_LCAI_WALLET`).
   - `CORS_ORIGINS` — your domain(s), comma-separated
     (e.g. `https://your-domain.example`).
   - `MONTHLY_PRICE_USD` *(optional)* — subscription price, defaults to `3.00`.
   - `FREE_ACTIONS_LIFETIME` *(optional)* — free AI actions before paywall,
     defaults to `20`.
   - `DATA_DIR` *(optional)* — where user memory/notes are stored, defaults to
     a local `data/` folder.
3. Start it: `python3 server.py` (or let your host run the `Procfile`).
4. Serve `index.html` from the same origin, or set `window.BINAI_API` to the
   backend's public URL.

## 4. Host the frontend

`index.html` is a static file — any static host works (GitHub Pages,
Cloudflare Pages, etc.). Push it, point your domain at it, done.

## 5. Included

- `index.html` — the full app (scrubbed)
- `server.py` — the API + AIVM relay backend (scrubbed)
- `requirements.txt`, `Procfile` — backend deploy helpers
- `manifest.json`, `sw.js`, `i18n-ui.js`, `languages.py`, icons
- `.nojekyll`, `.gitignore`

## 6. Safety notes (read before you publish)

- This scaffold ships with **placeholders, not real values**. If you leave a
  `YOUR_...` placeholder in, that feature just won't point anywhere — it won't
  leak anyone's data.
- No private keys are hardcoded. Payment verification is read-only against the
  public RPC. Never commit a `.env`; the `.gitignore` already excludes it.
- User data (memory/notes) lives in `DATA_DIR` on your own server. The
  `.gitignore` excludes `data/` and `*.db` so you never commit it.
- Before you push, scan your own fork for your email / tokens if you'd rather
  stay anonymous — same habit, now it's your call.
