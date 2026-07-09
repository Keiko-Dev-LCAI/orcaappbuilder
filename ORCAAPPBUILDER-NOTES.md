# OrcaAppBuilder — session notes (2026-07-09)

**Live:** https://orcaappbuilder.win  
**Local:** `~/Desktop/Orca Apps/web/orcaapp/`  
**Frontend repo:** Keiko-Dev-LCAI/orcaappbuilder · **35f8b2f**  
**Server repo:** Keiko-Dev-LCAI/orcaappbuilder-server · **3155b76**  
**Railway:** https://web-production-aaaba.up.railway.app  
**Service worker:** `orca-shell-v6`

## What changed (session 152)

- App-first UX — describe → plan → build here (not Lightchain-first)
- Build: beginner plain English, audience picker, draft auto-save, sticky Walk Me Through
- AI: no lightchain.io / Lightnode as step 1; chat shows 1–2 min wait; no Agent-class dump on vague asks
- PiecePay customer spec: `PiecePay-Customer-Spec.docx` (local only — do not git push)

## Customer save / resume

| Method | Scope |
|--------|--------|
| Build auto-draft (`orcaapp_build_draft`) | Same browser/device — description + plan restore on return |
| My Projects → Save to Project | Same browser/device — named project with build plan |
| First save (no projects yet) | **2026-07-09:** Save to Project opens prefilled new-project form + stores plan on Save |
| Not available yet | Cloud account / cross-device sync |

Tell users: hard refresh (`Ctrl+Shift+R`) after deploy; wait up to 2 minutes for AI.

## PiecePay quick facts

- 2 workshops, ~270 operators, 6 shift leaders
- Leaders enter good + NG at end of shift (operators no phones)
- Oracle: material IN/OUT barcodes (invoicing) — commission + NG is the gap
- Admin: Excel twice/month, admin-only corrections, 100+ SKU rates

## Revert backups

```bash
cd ~/Desktop/Orca\ Apps/web/orcaapp
cp index.html.bak-2026-07-09-appfirst index.html    # before app-first branding
cp index.html.bak-2026-07-09-thinking index.html    # before chat thinking fix
cp index.html.bak-2026-07-09-sticky index.html      # before sticky bar
cp index.html.bak-2026-07-09-nourls index.html        # before no-lightchain-urls
```