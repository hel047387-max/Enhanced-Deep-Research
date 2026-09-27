# Single-server deployment

This deployment runs exactly two services: a private, single-worker FastAPI container and a public Caddy container that serves the Vue PWA and terminates HTTPS. SQLite research, memory, checkpoint, owner, and session records share one persistent data volume. Model downloads use a separate persistent volume. Qdrant Cloud remains external.

## Prerequisites

- A Linux server with Docker Engine and the Compose plugin.
- A public DNS `A` or `AAAA` record pointing the application domain to the server.
- Inbound TCP ports 80 and 443, plus UDP 443 for HTTP/3.
- Provider credentials for the LLM, Tavily, Qdrant, and embedding service as required by your configuration.

Caddy obtains and renews the HTTPS certificate. Wait for DNS to resolve before starting it.

## Configure

From the repository root:

```bash
cp .env.example backend/.env
cp deploy/.env.example deploy/.env
```

Edit `deploy/.env` and set `APP_DOMAIN` to the public host name without a scheme. Edit `backend/.env` and set provider secrets. For production also set:

```dotenv
APP_BASE_URL=https://research.example.com
CORS_ORIGINS=https://research.example.com
AUTH_COOKIE_SECURE=true
CHECKPOINT_DB_PATH=/app/data/checkpoints.sqlite
```

The Compose file enforces the container checkpoint path even if the last line is omitted. Provider keys are read only by the API from `backend/.env`; they are never frontend build arguments. The file is optional during `docker compose config` validation, but the live API requires the configured provider keys.

## Start

```bash
docker compose --env-file deploy/.env up -d --build
docker compose --env-file deploy/.env ps
docker compose --env-file deploy/.env logs -f api web
```

Open `https://APP_DOMAIN`. On the first visit, create the **first owner** account. Registration then closes. After authentication, use **Install app** in the header when the browser offers PWA installation.

## Acceptance checks

```bash
curl -fsS https://research.example.com/health
docker compose --env-file deploy/.env ps
docker compose --env-file deploy/.env logs --tail=100 api web
```

Also verify these browser flows:

1. Start a research run and confirm SSE progress appears continuously.
2. Upload a small document and ask a cited RAG question.
3. Confirm a file larger than 50 MiB is rejected by the proxy.
4. Sign out and confirm research history and the literature library are no longer visible.
5. Restart both containers and confirm the owner account, research history, and document catalog still exist.

A normal **restart** preserves the named volumes:

```bash
docker compose --env-file deploy/.env restart
docker compose --env-file deploy/.env ps
```

## Backup SQLite

Create a consistent online **backup** through SQLite's backup API, then copy it to the host:

```bash
mkdir -p backups
docker compose --env-file deploy/.env exec -T api python -c "import sqlite3; source=sqlite3.connect('/app/data/checkpoints.sqlite'); target=sqlite3.connect('/app/data/checkpoints-backup.sqlite'); source.backup(target); target.close(); source.close()"
docker compose --env-file deploy/.env cp api:/app/data/checkpoints-backup.sqlite ./backups/checkpoints.sqlite
```

This file contains research data and the authentication tables. Back up Qdrant separately with the snapshot tools provided by your Qdrant service. Protect all backups as private data.

To restore SQLite, stop the API, keep the `research_data` volume, replace `/app/data/checkpoints.sqlite` with a verified backup, and start the API again. Do not overwrite a live database file.

## Reset the owner password

Run the interactive command against the same persistent volume:

```bash
docker compose --env-file deploy/.env run --rm api python -m deep_research.auth reset-password
```

The `reset-password` command asks twice, replaces the Argon2id hash, and revokes every existing session. It does not print or accept the password as a command-line argument.

## Status and logs

```bash
docker compose --env-file deploy/.env ps
docker compose --env-file deploy/.env logs --tail=200 api
docker compose --env-file deploy/.env logs --tail=200 web
```

Caddy forwards `/api/**` and `/health` without response buffering. The API has no published host port and runs one Uvicorn worker because SQLite and the in-process SSE publisher require a single instance.

## Upgrade and rollback

Back up SQLite before an upgrade, then rebuild:

```bash
git pull --ff-only
docker compose --env-file deploy/.env up -d --build
docker compose --env-file deploy/.env ps
```

For a **rollback**, keep all named volumes, check out the previous known-good commit or tag, and rebuild:

```bash
docker compose --env-file deploy/.env down
git checkout <known-good-tag>
docker compose --env-file deploy/.env up -d --build
```

Do not use `docker compose down -v`. Removing volumes deletes the SQLite database, including the auth tables, as well as cached models and Caddy state. A code rollback must preserve the SQLite schema and data; restore the backup only when the older release is known to support it.