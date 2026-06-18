# TLS certificates for production nginx

Place your certificate files here before enabling HTTPS in `docker-compose.yml`:

- `cert.pem` — full chain (or server cert)
- `key.pem` — private key

Then uncomment in `docker-compose.yml`:

```yaml
ports:
  - "443:443"
volumes:
  - ./deploy/nginx/nginx-ssl.conf:/etc/nginx/conf.d/ssl.conf:ro
  - ./deploy/nginx/ssl:/etc/nginx/ssl:ro
```

Self-signed (dev only):

```powershell
openssl req -x509 -nodes -days 365 -newkey rsa:2048 `
  -keyout deploy/nginx/ssl/key.pem -out deploy/nginx/ssl/cert.pem `
  -subj "/CN=localhost"
```

Restart: `docker compose up -d nginx`
