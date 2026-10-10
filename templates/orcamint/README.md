# OrcaMint Template

A clean, fork-ready scaffold of an NFT minting + marketplace app for the
Lightchain AIVM. Clone it, fill in the placeholders below with **your own**
values, deploy, and you have a live OrcaMint-style app where users mint NFTs,
list them, make and accept offers, and browse a gallery — with platform fees
routing to **your** wallet, not anyone else's.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own.

## 1. Fill in these placeholders

Open `index.html` and replace every placeholder with your own value:

| Placeholder | What to put there |
|---|---|
| `YOUR_GH_USER/YOUR_REPO` | Your GitHub `user/repo` (used for moderation raw links + Pages URL) |
| `your-domain.example` | Your app's public domain |
| `YOUR_ORCAMINT_CONTRACT` | Address of the OrcaMint NFT contract **you** deploy |
| `YOUR_MARKETPLACE_CONTRACT` | Address of the OrcaMintMarketplace contract **you** deploy |
| `YOUR_PLATFORM_WALLET` | The wallet that collects platform fees (yours) |
| `YOUR_ADMIN_WALLET_1..4` | Wallets allowed to moderate / own (yours; reuse or remove extras) |
| `YOUR_SERVER_URL` | Your backend/AIVM relay URL (see step 3) — or remove the feature |

Tip: search the file for `YOUR_` and `your-domain` to find them all.

## 2. Deploy the contracts

`OrcaMint.sol` is the NFT contract and `OrcaMintMarketplace.sol` is the
marketplace (list / offer / accept). Deploy both to Lightchain mainnet
(RPC `rpc.mainnet.lightchain.ai`, chainId 9200) from **your** wallet, then
paste the resulting addresses into the placeholders above. The deploying wallet
is the owner/admin.

## 3. Backend (optional)

Like the other Lightchain app templates, this scaffold ships the **frontend +
contracts only**. The original app called a small hosted backend for things
like AIVM image generation and a shared storage relay. Those are not included —
stand up your own service and point `YOUR_SERVER_URL` at it, or delete the
features that call it. The app's core mint/list/offer flow works directly
against your contracts without a backend.

## 4. Host it

Static site — any static host works (GitHub Pages, Cloudflare Pages, etc.).
Push the folder, point your domain at it, done.

## 5. Included

- `index.html` — the full app (scrubbed)
- `manifest.json`, `.nojekyll`, `.gitignore`
- `icon-192.png`, `icon-512.png`
- `OrcaMint.sol`, `OrcaMintMarketplace.sol`

## 6. Safety notes (read before you publish)

- This scaffold ships with **placeholders, not real values**. If you leave a
  `YOUR_...` placeholder in, that feature just won't point anywhere — it won't
  leak anyone's data.
- Never commit secrets (admin passwords, API keys, `.env`). The original app's
  server and secret files were intentionally left out of this template.
- Before you push, scan your own fork for your email / tokens if you'd rather
  stay anonymous — same habit, now it's your call.
