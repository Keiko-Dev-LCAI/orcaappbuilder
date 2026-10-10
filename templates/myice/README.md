# MyICE Template

A clean, fork-ready scaffold of a personal in-case-of-emergency (ICE) app for
the Lightchain AIVM. Clone it, fill in the placeholders below with **your own**
values, deploy, and you have a live MyICE-style app where the owner stores key
emergency info and contacts privately and can share a quick-access card — with
storage and payments routing to **your** contract and wallet, not anyone
else's.

Nothing in here is tied to the original author: no email, no socials, no real
name, no secrets. You bring your own.

## 1. Fill in these placeholders

Open `index.html` (and `sw.js`) and replace every placeholder with your own
value:

| Placeholder | What to put there |
|---|---|
| `YOUR_GH_USER/YOUR_REPO` | Your GitHub `user/repo` (Pages URL) |
| `your-domain.example` | Your app's public domain |
| `YOUR_MYICE_CONTRACT` | Address of the MyICEStore contract **you** deploy |
| `YOUR_PAYMENT_WALLET` | The wallet that collects any paid-feature fees (yours) |
| `YOUR_SERVER_URL` | Your backend URL (see below) — or remove the feature |

Tip: search the files for `YOUR_` and `your-domain` to find them all.

## 2. Deploy the contract

`MyICEStoreV2.sol` is the current on-chain storage contract (`MyICEStore.sol`
is the earlier version, included for reference). Deploy to Lightchain mainnet
(RPC `rpc.mainnet.lightchain.ai`, chainId 9200) from **your** wallet, then
paste the resulting address into `YOUR_MYICE_CONTRACT`. The deploying wallet is
the owner/admin.

## 3. Backend (optional)

This scaffold ships the **frontend + contract only**. The original app called a
small hosted backend for some helper features; that server was intentionally
left out. Stand up your own and point `YOUR_SERVER_URL` at it (in both
`index.html` and `sw.js`), or remove the features that call it. Emergency data
is encrypted client-side before it ever leaves the device.

## 4. Host it

Static site — any static host works (GitHub Pages, Cloudflare Pages, etc.).
Push the folder, point your domain at it, done.

## 5. Included

- `index.html` — the full app (scrubbed)
- `manifest.json`, `.nojekyll`, `_redirects`, `.gitignore`
- `sw.js` — service worker (scrubbed)
- `icon-192.png`, `icon-512.png`
- `MyICEStoreV2.sol`, `MyICEStore.sol`

## 6. Safety notes (read before you publish)

- This scaffold ships with **placeholders, not real values**. If you leave a
  `YOUR_...` placeholder in, that feature just won't point anywhere — it won't
  leak anyone's data.
- Never commit secrets (admin passwords, API keys, `.env`). The original app's
  server and secret files were intentionally left out of this template.
- Before you push, scan your own fork for your email / tokens if you'd rather
  stay anonymous — same habit, now it's your call.
