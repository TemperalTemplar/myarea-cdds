# MyArea CDDS

Course Development & Distribution System — part of the MyArea platform.

CDDS is a sovereign course authoring and federation platform. Build course packages, publish them, and share them with trusted LMS nodes via token-based federation. Once a package is issued it belongs to the recipient permanently — no recalls, no kill switches.

## Ports

- App: `8961` / `https://cdds.wrds361.com`

## Quick Install

```bash
# 1. Clone
git clone git@github.com:TemperalTemplar/myarea-cdds.git
cd myarea-cdds

# 2. Environment
cp .env.example .env
nano .env   # fill in SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD, SERVICE_API_KEY

# 3. Shared network (if not exists)
docker network create myarea_shared_net

# 4. Build and start
make up

# 5. Create tables
make create-tables

# 6. Init migrations
make db-init
make db-stamp

# 7. Connect to shared network
make connect-network
```

## Environment Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask secret key |
| `POSTGRES_PASSWORD` | Database password |
| `REDIS_PASSWORD` | Redis password |
| `SERVICE_API_KEY` | Must match myarea-ai |
| `OIDC_CLIENT_ID` | Authentik client ID |
| `OIDC_CLIENT_SECRET` | Authentik client secret |
| `OIDC_DISCOVERY_URL` | Authentik discovery URL |
| `OIDC_REDIRECT_URI` | `https://cdds.wrds361.com/auth/oidc/callback` |
| `HTTP_PORT` | Host port (default 8961) |
| `MYAREA_AI_URL` | Notification service URL |
| `SITE_URL` | Public URL of this node |
| `NODE_NAME` | Identity name for federation |

## Federation API

Remote LMS nodes authenticate with a Bearer token issued by the CDDS admin.

| Endpoint | Description |
|---|---|
| `POST /federation/handshake` | LMS introduces itself (no token needed) |
| `GET /federation/catalog` | Browse published courses |
| `GET /federation/catalog/<uuid>` | Single course metadata |
| `GET /federation/pull/<uuid>` | Download .cdpkg package |

## .cdpkg Format

A `.cdpkg` is a zip file containing:
```
manifest.json     — course metadata + module index
signature.txt     — SHA-256 of manifest + node identity
modules/
  01-title.md     — module content (Markdown)
  02-title.md
  ...
```

Once issued, a `.cdpkg` belongs to the recipient. The originating node has no further claim.

## Making a User Admin

```bash
docker compose exec web python -c "
from app import create_app, db
from app.models import User
app = create_app()
with app.app_context():
    u = User.query.filter_by(username='your_username').first()
    u.is_admin = True
    db.session.commit()
    print('Done.')
"
```
