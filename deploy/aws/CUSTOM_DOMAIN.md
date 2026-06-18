# Option B — Custom domain on AWS EC2

Use a domain you own (e.g. `app.yourfirm.com`) as the **permanent** LegalEase URL. The app stays on EC2 24/7; your laptop can be off.

**Server IP:** `18.61.68.82` (check EC2 console if it changed after stop/start).

---

## Step 1 — Buy or use a domain

Register anywhere (GoDaddy, Namecheap, Cloudflare Registrar, Route 53, etc.). You only need one hostname, for example:

- `app.yourdomain.com` (subdomain), or  
- `yourdomain.com` (apex / root)

---

## Step 2 — DNS: point the domain to EC2

In your registrar’s **DNS** panel, add:

| Type | Name / Host | Value | TTL |
|------|-------------|--------|-----|
| **A** | `app` (for `app.yourdomain.com`) | `18.61.68.82` | 300–3600 |
| **A** | `@` (for apex `yourdomain.com`) | `18.61.68.82` | 300–3600 |

**Cloudflare users:** set the record to the same IP. For first setup use **DNS only** (grey cloud) until HTTP works; then you can enable the orange cloud for CDN + free HTTPS.

Wait **5–30 minutes**, then check:

```powershell
nslookup app.yourdomain.com
```

It should show `18.61.68.82`.

---

## Step 3 — Open ports on AWS (required)

EC2 → your instance → **Security group** → **Edit inbound rules**:

| Type | Port | Source |
|------|------|--------|
| HTTP | 80 | `0.0.0.0/0` |
| HTTPS | 443 | `0.0.0.0/0` (needed for TLS) |

Save. Test from your laptop:

```powershell
curl.exe -m 10 http://18.61.68.82/api/v1/health/live
```

You must get JSON, not a timeout.

---

## Step 4 — Stop the temporary Cloudflare quick tunnel (optional)

On EC2, so traffic uses your domain directly:

```bash
sudo systemctl stop cloudflared-legalease
sudo systemctl disable cloudflared-legalease
```

---

## Step 5 — Configure the app for your domain

SSH in:

```powershell
ssh -i "$env:USERPROFILE\.ssh\legalease-aws.pem" ubuntu@18.61.68.82
```

Run go-live with **your** URL (HTTP first):

```bash
cd /opt/legalease
bash deploy/aws/ec2-go-live.sh http://app.yourdomain.com
```

Replace `app.yourdomain.com` with your real hostname.

That script sets `PUBLIC_APP_URL`, `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL`, rebuilds **web**, and restarts the stack.

**Permanent link (HTTP):** `http://app.yourdomain.com`

---

## Step 6 — HTTPS (recommended for production)

Browsers and Stripe work better with `https://`.

### A) Cloudflare proxy (easiest)

1. DNS **A** → `18.61.68.82`, proxy **on** (orange cloud).
2. **SSL/TLS** → **Flexible** (visitor HTTPS → Cloudflare → HTTP to EC2 on port 80).
3. Re-run go-live with **https**:

   ```bash
   bash deploy/aws/ec2-go-live.sh https://app.yourdomain.com
   ```

**Permanent link:** `https://app.yourdomain.com`

### B) Let’s Encrypt on the server

```bash
cd /opt/legalease
sudo apt-get update && sudo apt-get install -y certbot
# Free port 80 briefly for standalone challenge:
docker compose -f docker-compose.yml -f deploy/aws/docker-compose.override.yml stop nginx
sudo certbot certonly --standalone -d app.yourdomain.com --agree-tos -m your@email.com --non-interactive
sudo cp /etc/letsencrypt/live/app.yourdomain.com/fullchain.pem deploy/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/app.yourdomain.com/privkey.pem deploy/nginx/ssl/key.pem
sudo chown ubuntu:ubuntu deploy/nginx/ssl/*.pem
```

Enable SSL nginx (edit `deploy/aws/docker-compose.override.yml` to use profile `ssl` and service `nginx-ssl`, or follow `DEPLOY.md` TLS section), then:

```bash
bash deploy/aws/ec2-go-live.sh https://app.yourdomain.com
docker compose -f docker-compose.yml -f deploy/aws/docker-compose.override.yml --profile ssl up -d
```

Renewal: `sudo certbot renew` (add a cron job).

---

## Step 7 — Verify

```powershell
curl.exe https://app.yourdomain.com/api/v1/health/live
```

Open `https://app.yourdomain.com` in the browser; sign up / login should hit the same host (no CORS errors).

---

## From Windows (re-run after code updates)

```powershell
.\scripts\aws_go_live.ps1 -VmIp 18.61.68.82 -PublicUrl "https://app.yourdomain.com"
```

(Add `-PublicUrl` support if missing — check script; currently passes as second arg to ec2-go-live.sh)

Let me check aws_go_live.ps1 for PublicUrl param - yes it has PublicUrl param.

---

## Local laptop vs domain

- **Domain** → EC2 only.  
- **Local dev** → still `.\run_backend.ps1` + `.\run_web.ps1` and `http://localhost:3000` with your laptop `.env` unchanged.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| DNS not resolving | Wait longer; check A record IP |
| Timeout on domain | Security group port 80/443 |
| Page loads, API fails | Re-run `ec2-go-live.sh` with exact URL (no trailing `/`) |
| CORS error | `CORS_ORIGINS` must match browser URL (`https://app...`) |
| Still opens trycloudflare | Stop `cloudflared-legalease` service |
