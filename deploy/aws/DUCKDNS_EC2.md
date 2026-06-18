# DuckDNS + AWS EC2

## Runs when your laptop is off?

**Yes.** The app runs on **EC2 24/7** (Docker: api, web, nginx, postgres, redis). Your laptop is only for editing code and running `aws_update.ps1` to deploy. Users open **https://legalease.duckdns.org** anytime.

## What was fixed on the server

- `.env` URLs set to **`http://legalease.duckdns.org`** (not `https://` until you add TLS)
- **`FORCE_HTTPS=0`** so the API does not redirect to broken HTTPS
- Web image rebuilt with `NEXT_PUBLIC_API_URL=http://legalease.duckdns.org/api`
- Stack healthy on EC2 (`curl http://127.0.0.1/api/v1/health/live` → 200)

DNS already points to **18.61.68.82**.

## What you must do in AWS (one time)

Inbound **TCP port 80** is blocked from the internet. Open it:

1. AWS Console → **EC2** → **Instances** → select instance
2. **Security** → security group → **Edit inbound rules**
3. **Add rule:** Type **HTTP**, Port **80**, Source **0.0.0.0/0**
4. **Save**

Test from laptop:

```powershell
curl.exe http://legalease.duckdns.org/api/v1/health/live
```

Expect JSON `{"status":"ok",...}`.

## DuckDNS IP auto-update (optional)

At [duckdns.org](https://www.duckdns.org), copy your token, then on EC2:

```bash
echo 'DUCKDNS_TOKEN=YOUR_TOKEN' >> /opt/legalease/.env
bash /opt/legalease/deploy/aws/setup-duckdns.sh http://legalease.duckdns.org
```

## Enable HTTPS (Let's Encrypt)

1. Security group: add **HTTPS / 443** (in addition to HTTP / 80).
2. From laptop:

```powershell
.\scripts\enable_https_duckdns.ps1
```

Or on EC2:

```bash
bash /opt/legalease/deploy/aws/setup-https-duckdns.sh
```

Then use **https://legalease.duckdns.org**

## Re-run setup

```powershell
.\scripts\connect_duckdns_ec2.ps1
```
