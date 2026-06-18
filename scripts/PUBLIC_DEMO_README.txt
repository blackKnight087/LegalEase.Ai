Zero-budget public demo - last run notes
=====================================

1. Run: .\scripts\start_public_demo.ps1
2. In a NEW terminal (keep it open):
   cloudflared tunnel --url http://127.0.0.1:3000
3. Copy the https://....trycloudflare.com URL from cloudflared output.
4. Run:
   .\scripts\configure_tunnel_env.ps1 -TunnelUrl "https://YOUR-URL.trycloudflare.com"
5. Restart backend: .\run_backend.ps1
6. Test: .\scripts\verify_public_demo.ps1 -PublicUrl "https://YOUR-URL.trycloudflare.com"
7. Open that URL on your phone (mobile data) and try register + chat.

Example tunnel URL from setup (expires when cloudflared stops):
https://aerial-diving-ooo-therapist.trycloudflare.com

Your .env was updated with PUBLIC_APP_URL and CORS_ORIGINS for that host.
Restart the backend after any URL change.

Full guide: docs\DEPLOY_ZERO_BUDGET.md
