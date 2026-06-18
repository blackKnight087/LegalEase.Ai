# Free permanent public link (AWS EC2, laptop off)

Two **$0** options. Pick one.

| Method | Example URL | Port 80 on AWS? | Stays same after reboot? |
|--------|-------------|-----------------|---------------------------|
| **A — Cloudflare named tunnel + FreeDNS** | `https://legalease.mooo.com` | **No** | **Yes** |
| **B — FreeDNS A record → EC2 IP** | `http://legalease.mooo.com` | **Yes** | **Yes** (while IP unchanged) |

**Recommended: Method A** (works even if security group blocks port 80).

---

## Method A — Stable HTTPS (recommended)

### 1. Free hostname (FreeDNS)

1. Register: [https://freedns.afraid.org](https://freedns.afraid.org)
2. **Subdomains** → pick a free zone (e.g. `mooo.com`, `us.kg`)
3. Create host, e.g. **`legalease`** → full name: **`legalease.mooo.com`**
4. **Do not** set the A record yet — you need the tunnel CNAME first (step 4).

### 2. Cloudflare account (one-time)

On your **laptop** (browser login once):

```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel login
```

Complete login in the browser.

### 3. Create named tunnel (laptop or EC2)

```powershell
cloudflared tunnel create legalease-aws
cloudflared tunnel list
```

Copy the **tunnel ID** (UUID). Your CNAME target is:

```text
<TUNNEL_ID>.cfargotunnel.com
```

### 4. FreeDNS → CNAME to tunnel

In FreeDNS, for `legalease.mooo.com`:

| Type | Destination |
|------|-------------|
| **CNAME** | `<TUNNEL_ID>.cfargotunnel.com` |

Wait 5–30 minutes. Test: `nslookup legalease.mooo.com`

### 5. Install tunnel config on EC2

Copy credentials from laptop to server:

```powershell
scp -i "$env:USERPROFILE\.ssh\legalease-aws.pem" -r "$env:USERPROFILE\.cloudflared" ubuntu@18.61.68.82:~/.cloudflared
```

On **EC2** (SSH), create config — nginx listens on **80**:

```bash
sudo mkdir -p /etc/cloudflared
sudo tee /etc/cloudflared/config.yml <<'EOF'
tunnel: legalease-aws
credentials-file: /home/ubuntu/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: legalease.mooo.com
    service: http://127.0.0.1:80
  - service: http_status:404
EOF
```

Replace `<TUNNEL_ID>` and `legalease.mooo.com` with yours.

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl stop cloudflared-legalease   # disable old quick tunnel
```

### 6. Point the app at your hostname

```bash
cd /opt/legalease
bash deploy/aws/ec2-go-live.sh https://legalease.mooo.com
```

**Permanent link:** `https://legalease.mooo.com`  
(Laptop off; runs 24/7 on EC2.)

---

## Method B — Direct to EC2 IP (simpler DNS, needs port 80)

1. FreeDNS: **A record** `legalease.mooo.com` → `18.61.68.82`
2. AWS security group: open **HTTP 80** ([OPEN_PORT_80.md](./OPEN_PORT_80.md))
3. EC2:

```bash
sudo systemctl stop cloudflared-legalease
cd /opt/legalease
bash deploy/aws/ec2-go-live.sh http://legalease.mooo.com
```

**Permanent link:** `http://legalease.mooo.com`

---

## What you have today (not permanent)

`https://….trycloudflare.com` — free but the name **can change** when the quick tunnel restarts.

---

## After setup

Save the URL in `scripts/STABLE_PUBLIC_URL.txt` on your laptop. Re-deploy code:

```powershell
.\scripts\aws_go_live.ps1 -VmIp 18.61.68.82 -PublicUrl "https://legalease.mooo.com"
```
