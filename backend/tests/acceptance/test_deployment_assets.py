from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).parents[3]


def _service_block(compose: str, name: str) -> str:
    services = compose.split("services:\n", 1)[1].split("\nvolumes:", 1)[0]
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)",
        services,
    )
    assert match is not None
    return match.group("body")


def test_compose_exposes_only_web_and_persists_api_state() -> None:
    compose = (_ROOT / "compose.yaml").read_text(encoding="utf-8")
    services = compose.split("services:\n", 1)[1].split("\nvolumes:", 1)[0]
    assert set(re.findall(r"(?m)^  ([a-z][a-z0-9_-]*):$", services)) == {
        "api",
        "web",
    }
    api = _service_block(compose, "api")
    web = _service_block(compose, "web")

    assert "ports:" not in api
    assert '"8000"' in api
    assert "research_data:/app/data" in api
    assert "model_cache:/models" in api
    assert "CHECKPOINT_DB_PATH: /app/data/checkpoints.sqlite" in api
    assert "HF_HOME: /models/huggingface" in api
    assert '"80:80"' in web and '"443:443"' in web
    assert "caddy_data:/data" in web and "caddy_config:/config" in web


def test_api_image_runs_one_proxy_aware_worker_and_web_builds_the_pwa() -> None:
    backend = (_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    frontend = (_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")

    assert "python:3.11-slim" in backend
    assert 'pip install --no-cache-dir ".[rag]"' in backend
    assert '"--workers", "1"' in backend
    assert '"--proxy-headers"' in backend
    assert '"--forwarded-allow-ips", "*"' in backend
    assert "npm ci" in frontend and "npm run build" in frontend
    assert "caddy:2-alpine" in frontend
    assert "COPY --from=build /app/dist /srv" in frontend


def test_caddy_streams_api_and_serves_spa_without_caching_api() -> None:
    caddy = (_ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    assert "{$APP_DOMAIN}" in caddy
    assert "max_size 50MiB" in caddy
    assert "handle /api/*" in caddy
    assert "handle /health" in caddy
    assert caddy.count("reverse_proxy api:8000") == 2
    assert caddy.count("flush_interval -1") == 2
    assert "try_files {path} /index.html" in caddy
    assert "file_server" in caddy


def test_deployment_docs_cover_operations_and_safe_rollback() -> None:
    docs = (_ROOT / "docs" / "deployment.md").read_text(encoding="utf-8").lower()
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")

    for phrase in [
        "docker compose --env-file deploy/.env up -d --build",
        "first owner",
        "install app",
        "backup",
        "reset-password",
        "docker compose --env-file deploy/.env ps",
        "docker compose --env-file deploy/.env logs",
        "restart",
        "rollback",
        "do not use `docker compose down -v`",
        "auth tables",
    ]:
        assert phrase in docs
    assert "docs/deployment.md" in readme