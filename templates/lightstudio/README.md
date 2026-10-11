# LightStudio Template

A clean, fork-ready scaffold of an anonymous, wallet-only AI creative studio
(image / video / voice / song) powered by Topview for generation and the
Lightchain AIVM for the optional text layer. Users see a free watermarked
preview and pay in **native LCAI** to unlock the clean file — paid to **your**
wallet.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets, no KEIKO rail. You bring your own wallet, your own Topview
account, and your own server.

## How it's put together

- **Frontend** (`index.html`, `how.html`, `ethers-6.13.2.umd.min.js`,
  `lcai-symbol.svg`) — the full app. Static; host it anywhere.
- **Backend** (`server.py` + `aivm_client.py`) — a relay that drives Topview
  generation, serves previews, verifies the on-chain LCAI payment, and releases
  the clean file. The optional AIVM text layer (lyric / prompt enhancer) signs
  jobs with a **service wallet you fund**. All keys live **only** in env vars.

## 1. Fill in these placeholders

Search `index.html` for `YOUR_` and `your-domain`:

| Placeholder | What to put there |
|---|---|
| `YOUR_SERVER_URL` | The public URL of the backend you deploy (no trailing slash) |
| `your-domain.example` | Your app's public domain |

## 2. Deploy the backend

A Flask app (Dockerfile + `Procfile` included).

1. Install deps: `pip install -r requirements.txt`
2. Set environment variables:
   - `OWNER_WALLET` — the Lightchain wallet that **receives** unlock payments (yours).
   - `TOPVIEW_SKILL_DIR` — path to your own Topview skill/scripts install
     (handles Topview auth + generation). You need your own Topview account.
   - `AIML_API_KEY` *(optional)* — enables the song/MP3 feature.
   - `LIGHTCHAIN_PRIVATE_KEY` *(optional)* — a wallet **you** fund, only needed
     for the AIVM lyric/prompt-enhancer layer (~0.02 LCAI per call). **Never**
     commit this.
   - `CORS_ORIGINS` — your domain(s), comma-separated.
   - `AIVM_MODEL_PRIMARY` *(optional)* — defaults to the basic model; change later.
3. Deploy (Railway/Fly/VPS/Docker) and put its public URL into `YOUR_SERVER_URL`.

## 3. Host the frontend

`index.html` is static — any static host works (GitHub Pages, Cloudflare Pages).

## 4. Included

- `index.html`, `how.html` — the app (scrubbed)
- `ethers-6.13.2.umd.min.js`, `lcai-symbol.svg` — frontend assets
- `server.py`, `aivm_client.py` — the backend relay (scrubbed, LCAI-only)
- `requirements.txt`, `Procfile`, `Dockerfile` — deploy helpers
- `.nojekyll`, `.gitignore`

## 5. Safety notes (read before you publish)

- Ships with **placeholders, not real values**. A leftover `YOUR_...` just means
  that feature points nowhere — it won't leak anyone's data.
- All keys (Topview, AIML, the AIVM private key) are **env-only**. Never
  hardcode them, never log them, never commit a `.env` (already in `.gitignore`).
- Scan your own fork for your email / tokens before pushing if you want to stay
  anonymous.
