# Score Store

Web portal for sharing and viewing choir music scores. Flask + JSON filesystem storage.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export SECRET_KEY=change-me

python app.py
```

Open http://localhost:5000 — on first run the **setup wizard** prompts for admin password and storage path.

For automated/Docker deploy you can skip the wizard with environment variables (see below).

## Roles

| Role | Access |
|------|--------|
| **Maestro** | Desktop 3-column workspace, global library, user management, assign scores |
| **Singer** | Mobile-first library, upload own scores, manage folders in own library, concert viewer |
| **Choir** | Shared account; library layout overrides in browser localStorage only (server permissions in `policy.py`) |

Server authorization rules live in `policy.py`. Routes should call those helpers rather than checking roles inline.

## Environment

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session signing (required in production) |
| `BOOTSTRAP_MAESTRO_USER` | Optional: skip wizard; create maestro on first start |
| `BOOTSTRAP_MAESTRO_PASSWORD` | Optional: paired with `BOOTSTRAP_MAESTRO_USER` |
| `USE_HTTPS=1` | Set `SESSION_COOKIE_SECURE` for HTTPS deployments |
| `DATA_DIR` | Default storage path before wizard runs (default: `./data`) |
| `PORT` | HTTP port (default: 5000) |

Storage path chosen in the setup wizard is saved to `instance/config.json` and used on subsequent starts.

## HTTPS (self-signed)

Generate a certificate:

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=scorestore.local"
```

Run Flask behind **Caddy** or **nginx** terminating TLS. Set `USE_HTTPS=1`. Browsers will warn on first visit — accept the certificate once per device.

### Caddy example

```
scorestore.local {
  tls cert.pem key.pem
  reverse_proxy localhost:5000
}
```

## Docker (optional)

```bash
docker build -t score-store .
docker run -p 5000:5000 -v scorestore-data:/app/data \
  -e SECRET_KEY=... \
  -e BOOTSTRAP_MAESTRO_USER=admin \
  -e BOOTSTRAP_MAESTRO_PASSWORD=... \
  score-store
```

## Data layout

```
data/
  users.json                         # id, display_name, username, password, role
  libraries/_global.json             # library_id, display_name, folders, score_order, score_folders
  libraries/u-{slug}.json            # library_id, owner_id, display_name, …
  scores/s-{slug}/meta.json
  scores/s-{slug}/files/{slug}.ext   # readable on-disk names (YouTube aux entries have no file)
```

Entity IDs are readable slugs (whitespace → hyphens): user libraries use `u-{username}`, scores use `s-{title}`. Hash-style legacy IDs are rewritten on startup.

Mount `data/` as a volume in production.
