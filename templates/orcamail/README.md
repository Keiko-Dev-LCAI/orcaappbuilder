# OrcaMail Template

A clean, fork-ready scaffold of a wallet-to-wallet messaging app for the
Lightchain AIVM. Clone it, fill in the placeholders below with **your own**
values, deploy, and you have a live OrcaMail-style app where users send
messages wallet-to-wallet and keep their own on-chain inbox — all against
**your** contract, not anyone else's.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own.

## 1. Fill in these placeholders

Open `index.html` and replace every placeholder with your own value:

| Placeholder | What to put there |
|---|---|
| `YOUR_GH_USER/YOUR_REPO` | Your GitHub `user/repo` (Pages URL) |
| `your-domain.example` | Your app's public domain |
| `YOUR_ORCAMAIL_CONTRACT` | Address of the OrcaMail v2 contract **you** deploy |

Tip: search the file for `YOUR_` and `your-domain` to find them all.

## 2. Deploy the contract

`OrcaMail_v2.sol` is the on-chain messaging contract. Deploy it to Lightchain
mainnet (RPC `rpc.mainnet.lightchain.ai`, chainId 9200) from **your** wallet,
then paste the resulting address into `YOUR_ORCAMAIL_CONTRACT` above. The
deploying wallet is the owner/admin.

## 3. Host it

Static site — any static host works (GitHub Pages, Cloudflare Pages, etc.).
Push the folder, point your domain at it, done. The core wallet-to-wallet
messaging runs directly against your contract with no backend.

## 4. Included

- `index.html` — the full app (scrubbed)
- `.nojekyll`, `.gitignore`
- `icon.png`
- `OrcaMail_v2.sol`

> The original app also had an optional email-bridge backend (SMTP) and an AIVM
> helper. Those server files — and their credentials — were intentionally left
> out of this template. Stand up your own if you want those extras; the
> messaging core doesn't need them.

## 5. Safety notes (read before you publish)

- This scaffold ships with **placeholders, not real values**. If you leave a
  `YOUR_...` placeholder in, that feature just won't point anywhere — it won't
  leak anyone's data.
- Never commit secrets (SMTP passwords, API keys, `.env`). The original app's
  credential files were intentionally left out of this template.
- Before you push, scan your own fork for your email / tokens if you'd rather
  stay anonymous — same habit, now it's your call.
