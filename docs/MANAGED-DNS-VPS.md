# Managed DNS-over-HTTPS (DoH) deployment

This branch is an independent encrypted DNS management service. It **does not** modify
HTTPS traffic, intercept TLS, install a root CA, or unlock third-party paid features.

## Architecture

- **Management server (FastAPI, deployable on Vercel):** admin authentication, MongoDB
  devices, expiry, blocklists, one-time profile links, and authenticated policy API.
- **Ubuntu VPS (FastAPI DoH gateway):** RFC 8484 GET and POST at
  `https://dns.example.com/dns-query/<device-token>`. Uses DNS wire format,
  applies per-device blocking, and forwards allowed queries to a trusted DoH upstream.
- **iPhone:** opens `*.mobileconfig` in Safari, then installs the DNS settings
  profile in Settings > General > VPN & Device Management. No VPN app or Root CA
  is required. Network or device policy may override manual DNS settings.

The iOS profile uses `com.apple.dnsSettings.managed` with DNSProtocol HTTPS.
Individual download and DNS endpoint URLs contain a bearer-like device secret.
Do not publish them, embed them in screenshots, or include them in access logs.

## 1. Management backend environment (Vercel)

Continue using the existing mandatory environment variables:
`MONGODB_URI`, `MONGODB_DATABASE`, `SUPERADMIN_EMAIL`,
`SUPERADMIN_PASSWORD_HASH`, and `ALLOWED_HOSTS`. Add:

```dotenv
DNS_PUBLIC_ORIGIN=https://dns.example.com
DNS_GATEWAY_API_TOKEN=REPLACE_WITH_SAME_RANDOM_SECRET_USED_ON_VPS
```

Generate the 64-character secret locally using
`python3 -c "import secrets; print(secrets.token_hex(32))"`.
Configure MongoDB Atlas network access appropriately for Vercel egress.
Set the platform environment variables privately. Do **not** commit your .env.

Deploy this branch to Vercel as a preview first, and set its hostname in
`ALLOWED_HOSTS`. If the DNS gateway points to the production backend while
only preview has these API routes, policy lookup will fail.

New routes:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/dns/dashboard` | DNS admin UI (requires an existing logged-in admin session to use APIs) |
| POST | `/api/admin/dns/devices` | Create device; returns secret profile URL only once |
| GET | `/api/admin/dns/devices` | List devices, no secrets |
| PUT | `/api/admin/dns/devices/{id}` | Change expiry, label, blocklist |
| POST | `/api/admin/dns/devices/{id}/revoke` | Revoke device |
| GET | `/dns/profiles/{secret}.mobileconfig` | Download profile (secret URL) |
| POST | `/api/internal/dns/policy` | VPS-only lookup, server bearer authentication |

Log into the existing admin page first, then open `/dns/dashboard`.
Store the returned profile URL securely. This application deliberately does
not store recoverable device tokens; to restore a lost profile link, revoke the
device and create a new profile.

## 2. VPS setup (Ubuntu 24.04)

```bash
sudo apt update
sudo apt install -y git python3-venv nginx certbot python3-certbot-nginx
sudo adduser --system --group --no-create-home doh
sudo mkdir -p /opt
cd /opt
sudo git clone https://github.com/vuthanhluan206/locketgoldmanager.git
cd locketgoldmanager
sudo git checkout feature/vps-doh-device-manager
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r vps/requirements.txt
sudo cp vps/managed-doh.env.example /etc/managed-doh.env
sudo nano /etc/managed-doh.env
sudo chown root:root /etc/managed-doh.env
sudo chmod 600 /etc/managed-doh.env
sudo cp vps/doh-gateway.service /etc/systemd/system/managed-doh.service
sudo systemctl daemon-reload
sudo systemctl enable --now managed-doh
sudo systemctl status managed-doh
```

Set `MANAGER_API_ORIGIN=https://your-management-domain` and the **same**
`DNS_GATEWAY_API_TOKEN` as Vercel. Keep DoH upstream separate from this server.
The VPS queries the policy API using HTTPS and caches results for ~30s to
avoid sending each DNS question to MongoDB.

**Important:** If the existing repository is already cloned at /opt, do not
blindly clone again. Instead create a separate working copy or fetch and
check out the feature branch. Never overwrite a production .env.

## 3. DNS hostname and TLS

Create an A record `dns.example.com` pointing to the public VPS IPv4.
Replace the hostname in `vps/nginx-doh.conf`, then:

```bash
sudo cp vps/nginx-doh.conf /etc/nginx/sites-available/managed-doh
sudo ln -s /etc/nginx/sites-available/managed-doh /etc/nginx/sites-enabled/managed-doh
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d dns.example.com
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

Check Certbot's generated TLS server config. For DoH paths, **disable Nginx
access logging** because the device secret is in the URL. Ensure HTTPS requests
are served, HTTP redirects to HTTPS, and only ports 80/443 are public.
The DoH process listens only on `127.0.0.1:8053`.

To inspect without printing secrets:

```bash
sudo journalctl -u managed-doh -n 80 --no-pager
curl -fsS http://127.0.0.1:8053/healthz
```

## 4. iPhone

1. Log into the DNS dashboard on the management domain.
2. Create a device and copy the one-time private download link.
3. Open the link in Safari on that iPhone.
4. Go to Settings > General > VPN & Device Management, install downloaded profile.
5. Verify DNS policy with a domain you control. Test both Wi-Fi and cellular.

There is no Root CA trust switch for this setup: a public TLS certificate
already establishes trust in your DNS server.

## 5. Failure and expiry behavior

- A revoked/expired device continues to receive **ordinary upstream DNS**
  with no customized blocking; expiry removes **managed DNS policy** but
  does not forcibly disconnect Internet. If backend is unavailable and policy
  is uncached, the same default applies.
- Policy refresh is at most ~30 seconds under ordinary traffic; this is
  near-real-time, not a push stream.
- Download links expire for profile retrieval when the device expires.
- Changing the blocklist/expiry does not require reinstalling a profile.
- The service does not redirect Locket/RevenueCat HTTPS requests and cannot
  modify authenticated application subscriptions.

## Production hardening

The gateway is a reference implementation. Before running at scale:
restrict API origins and outbound traffic, monitor abuse, prefer domain
allowlists in upstream policy, set edge rate limits (requests/s and bytes/s),
enforce Nginx body limits, configure backups, consider token rotation, and
run integration tests against the actual device firmware and network.
Keep application logs free of DNS token paths and query content.
