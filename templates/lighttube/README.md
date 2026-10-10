# LightTube Template

A clean, fork-ready scaffold of an on-chain video app for the Lightchain AIVM.
Clone it, fill in the placeholders below with **your own** values, deploy, and
you have a live LightTube-style app that routes payments and moderation to
**your** wallet — not anyone else's.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own.

## 1. Fill in these placeholders

Open `index.html` and replace every placeholder with your own value:

| Placeholder | What to put there |
|---|---|
| `YOUR_GH_USER/YOUR_REPO` | Your GitHub `user/repo` (used for thumbnails + moderation raw links) |
| `YOUR_GH_USER` / `YOUR_REPO` | Same, where they appear separately (e.g. the Pages URL) |
| `your-domain.example` | Your app's public domain |
| `YOUR_LIGHTTUBE_V2_CONTRACT` | Address of the LightTubeV2 contract **you** deploy |
| `YOUR_LIGHTTUBE_V3_CONTRACT` | Address of the LightTubeV3 contract **you** deploy |
| `YOUR_SERVER_URL` | Your backend/relay URL for uploads + moderation — or remove the feature |
| `YOUR_ADMIN_WALLET_1` | A wallet allowed to moderate (yours) |
| `YOUR_ADMIN_WALLET_2` | A second moderator wallet (optional — reuse or remove) |

Tip: search the file for `YOUR_` and `your-domain` to find them all.

## 2. Deploy the contracts

`LightTube.sol`, `LightTubeV2.sol`, `LightTubeV3.sol` are the on-chain video
contracts. Deploy them to Lightchain mainnet (RPC `rpc.mainnet.lightchain.ai`,
chainId 9200) from **your** wallet, then paste the resulting addresses into the
V2/V3 placeholders above. The deploying wallet is the owner/admin.

## 3. Host it

Static site — any static host works (GitHub Pages, Cloudflare Pages, etc.).
Push the folder, point your domain at it, done. Videos store fully on-chain by
design; uploads route through a backend relay — point `YOUR_SERVER_URL` at your own hosted service.

## 4. Included

- `index.html` — the full app (scrubbed)
- `manifest.json`, `.nojekyll`, `.gitignore`
- `icon-192.png`, `icon-512.png`
- `LightTube.sol`, `LightTubeV2.sol`, `LightTubeV3.sol`

## 5. Safety notes (read before you publish)

- This scaffold ships with **placeholders, not real values**. If you leave a
  `YOUR_...` placeholder in, that feature just won't point anywhere — it won't
  leak anyone's data.
- Never commit secrets (admin passwords, API keys, `.env`). The original app's
  secret files were intentionally left out of this template.
- Before you push, scan your own fork for your email / tokens if you'd rather
  stay anonymous — same habit, now it's your call.
