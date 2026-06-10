# Score Store

Web portal for sharing and viewing choir music scores. Flask + JSON filesystem storage with a platform **admin** layer above per-maestro sites.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export SECRET_KEY=change-me

python app.py
```

Open http://localhost:5000 — on first run the **setup wizard** creates the platform admin account and storage path.

For automated/Docker deploy you can skip the wizard with environment variables (see below).

## Roles

| Role | Access |
|------|--------|
| **Admin** | Platform oversight: create/edit/delete maestro accounts, browse any maestro's libraries (read-only) |
| **Maestro** | Own branded mini-site: global library, sub-account management, score upload/assign, appearance editor |
| **Singer** | Personal library, upload own scores, manage folders, concert viewer |
| **Choir** | Shared account; library layout overrides in browser localStorage only (server permissions in `policy.py`) |

Everyone signs in at the same `/login` URL. Branding (`theme.css`, logotype, site title) applies after login once the user's maestro scope is known.

Server authorization rules live in `policy.py`. Routes should call those helpers rather than checking roles inline.

## Environment

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session signing (required in production) |
| `BOOTSTRAP_ADMIN_USER` | Optional: skip wizard; create platform admin on first start |
| `BOOTSTRAP_ADMIN_PASSWORD` | Optional: paired with `BOOTSTRAP_ADMIN_USER` |
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
  -e BOOTSTRAP_ADMIN_USER=admin \
  -e BOOTSTRAP_ADMIN_PASSWORD=... \
  score-store
```

## Data layout

```
data/
  users.json                    # all accounts (admin, maestro, singer, choir)
  {maestro-username}/           # one folder per maestro account
    config.json                 # site_title, logotype path (no colors)
    theme.css                   # maestro branding overrides
    assets/                     # logotype image(s)
    libraries/_global.json
    libraries/u-{slug}.json
    scores/s-{slug}/meta.json
    scores/s-{slug}/files/...
```

- **Admin** has no data folder.
- **Maestro** owns `data/{username}/`.
- **Singer / choir** have `maestro_id` pointing at the owning maestro user id; they inherit that maestro's folder.

### Maestro theming

`config.json` holds non-style settings only. Colors and layout branding live in `theme.css` as CSS custom properties. Platform `style.css` defines defaults; maestro `theme.css` may override variables such as:

- `--color-primary`
- `--color-primary-hover`
- `--color-bg`
- `--color-accent-bg`

See `templates/maestro_theme_template.css` for a starter file created with each new maestro.

Mount `data/` as a volume in production.
