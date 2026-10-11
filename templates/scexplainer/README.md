# Smart Contract Explainer Template

A clean, fork-ready scaffold of an AI smart-contract explainer dApp powered by
the Lightchain AIVM. Paste a contract address or source, and the app explains
what it does and flags risks — with inference running through **your** AIVM
relay and paid access gated by a contract **you** deploy.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own wallet, contract, and server.

## How it's put together

- **Frontend** (`index.html`) — the full app. Static; host it anywhere.
- **Backend** (`server.py`) — a relay that runs the LLM analysis through the
  Lightchain AIVM. It signs inference jobs with a **service wallet you fund**
  and pays the tiny per-call LCAI fee. The private key lives **only** in an
  environment variable — never in the code, never in git.
- **Contract** (`ContractExplainerAccess_v2.sol`) — gates paid access on-chain.

## 1. Fill in these placeholders

Search `index.html` and `server.py` for `YOUR_` and `your-domain` and replace:

| Placeholder | What to put there |
|---|---|
| `YOUR_SCE_CONTRACT` | Address of the `ContractExplainerAccess_v2` contract **you** deploy |
| `YOUR_SERVER_URL` | The public URL of the backend you deploy (no trailing slash) |
| `your-domain.example` | Your app's public domain |

## 2. Deploy the access contract

Deploy `ContractExplainerAccess_v2.sol` to Lightchain mainnet (RPC
`rpc.mainnet.lightchain.ai`, chainId 9200) from **your** wallet, then paste the
address into `YOUR_SCE_CONTRACT` (frontend) and set `ACCESS_CONTRACT` (backend
env). The deploying wallet is the owner.

## 3. Deploy the backend

A plain Python HTTP server (Dockerfile + `railway.toml` + `Procfile` included).

1. Install deps: `pip install -r requirements.txt`
2. Set environment variables:
   - `LIGHTCHAIN_PRIVATE_KEY` — a Lightchain wallet **you** control and fund
     with a little native LCAI (~0.02 LCAI per analysis). **Never** commit this.
   - `ACCESS_CONTRACT` — your deployed access-contract address.
   - `CORS_ORIGINS` — your domain(s), comma-separated.
   - `ETHERSCAN_KEY` *(optional)* — enables Ethereum explorer lookups.
   - `AIVM_MODEL_PRIMARY` *(optional)* — the Lightchain model to use; the app
     ships on the basic model and you can change it later.
3. Deploy (Railway/Fly/VPS/Docker). Put its public URL into `YOUR_SERVER_URL`.

## 4. Host the frontend

`index.html` is static — any static host works (GitHub Pages, Cloudflare Pages).

## 5. Included

- `index.html` — the full app (scrubbed)
- `server.py` — the AIVM relay backend (scrubbed)
- `ContractExplainerAccess_v2.sol` — the paid-access contract
- `requirements.txt`, `Procfile`, `Dockerfile`, `railway.toml` — deploy helpers
- `known-logos/` — token logos used in the UI
- `.nojekyll`, `.gitignore`

## 6. Safety notes (read before you publish)

- Ships with **placeholders, not real values**. A leftover `YOUR_...` just means
  that feature points nowhere — it won't leak anyone's data.
- The AI private key and any API keys are **env-only**. Never hardcode them,
  never log them, never commit a `.env` (already in `.gitignore`).
- Scan your own fork for your email / tokens before pushing if you want to stay
  anonymous.
