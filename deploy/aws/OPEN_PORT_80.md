# Open HTTP on AWS EC2 (required for the public app)

The stack can be **healthy on the server** while the browser **times out** — that means the EC2 **security group** is not allowing inbound TCP **80**.

## AWS Console (2 minutes)

1. **EC2** → **Instances** → select your instance (`18.61.68.82` or current public IP).
2. **Security** tab → click the **security group** link.
3. **Edit inbound rules** → **Add rule**:
   - **Type:** HTTP
   - **Port:** 80
   - **Source:** `0.0.0.0/0` (or your office IP for tighter security)
4. **Save rules**.

Optional: add **HTTPS / 443** if you terminate TLS on the instance later.

## Verify

From your laptop:

```powershell
curl.exe -m 10 http://18.61.68.82/api/v1/health/live
```

Expect JSON and HTTP 200, not a timeout.

## Temporary access without opening port 80

SSH tunnel (works while SSH is allowed):

```powershell
ssh -i "$env:USERPROFILE\.ssh\legalease-aws.pem" -L 8080:127.0.0.1:80 ubuntu@18.61.68.82
```

Then open **http://localhost:8080** in the browser.
