# OrcaVault Template

A clean, fork-ready scaffold of an encrypted on-chain file-storage app for the
Lightchain AIVM. Clone it, fill in the placeholders below with **your own**
values, deploy, and you have a live OrcaVault-style app where users store and
share encrypted files on-chain, with an optional paid one-click relay for
larger transfers — all routing to **your** contracts and wallet, not anyone
else's.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own.

## 1. Fill in these placeholders

Open `index.html` and replace every placeholder with your own value:

| Placeholder | What to put there |
|---|---|
| `YOUR_GH_USER/YOUR_REPO` | Your GitHub `user/repo` (used for thumbnails + Pages URL) |
| `your-domain.example` | Your app's public domain |
| `YOUR_ORCAVAULT_CONTRACT` | Address of the OrcaVault V1 contract **you** deploy |
| `YOUR_ORCAVAULT_V2_CONTRACT` | Address of the OrcaVaultV2 contract (chunked uploads) |
| `YOUR_ORCAVAULT_V3_CONTRACT` | Address of the OrcaVaultV3 contract (relay + direct chunked) |
| `YOUR_SERVER_URL` | Your hosted relay URL for the large-file path — or leave as-is for client-side only |
| `YOUR_ADMIN_WALLET_1..3` | Wallets allowed to moderate (yours; reuse or remove extras) |

Tip: search the file for `YOUR_` and `your-domain` to find them all.

## 2. Deploy the contracts

`OrcaVaultV2.sol` and `OrcaVaultV3.sol` are the on-chain storage contracts
(V3 is current — relay + direct chunked uploads, no file-size limit). Deploy
to Lightchain mainnet (RPC `rpc.mainnet.lightchain.ai`, chainId 9200) from
**your** wallet, then paste the resulting addresses into the placeholders
above. The deploying wallet is the owner/admin.

## 3. Relay (optional, for large files)

Files store fully on-chain by design. Small files assemble client-side; the
one-click relay is only for larger transfers and is a separately hosted
service. Point `YOUR_SERVER_URL` at your own hosted relay if you want to run the
paid large-file path yourself, or the app still works for client-side-assembled
files without it.


## 4. Host it

Static site — any static host works (GitHub Pages, Cloudflare Pages, etc.).
Push the folder, point your domain at it, done.

## 5. Included

- `index.html` — the full app (scrubbed)
- `manifest.json`, `.nojekyll`, `_redirects`, `.gitignore`
- `icon-192.png`, `icon-512.png`
- `OrcaVaultV2.sol`, `OrcaVaultV3.sol`

## 6. Safety notes (read before you publish)

- This scaffold ships with **placeholders, not real values**. If you leave a
  `YOUR_...` placeholder in, that feature just won't point anywhere — it won't
  leak anyone's data.
- Never commit secrets (admin passwords, API keys, `.env`). The original app's
  relay/MCP server and secret files were intentionally left out of this
  template.
- Before you push, scan your own fork for your email / tokens if you'd rather
  stay anonymous — same habit, now it's your call.
