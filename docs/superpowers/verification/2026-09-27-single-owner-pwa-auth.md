# Single-owner authentication and PWA verification

Date: 2026-09-27

Branch: `feature/single-owner-pwa-auth`

Verified implementation commit before this record: `ba225d8`

Base commit: `4463a4a24492f2ca3222b1e66cd7c3b50319ea14`

## Environment

- Windows PowerShell
- Python 3.13.5 using the existing project virtual environment
- Node.js v24.15.0
- npm 11.12.1
- Docker CLI unavailable on this workstation

## Backend gates

```powershell
cd backend
D:\科研助手\enhanced-deep-research\backend\.venv\Scripts\python.exe -m ruff check src tests
D:\科研助手\enhanced-deep-research\backend\.venv\Scripts\python.exe -m pytest -q
```

Results:

- Ruff: `All checks passed!`
- Pytest: `303 passed in 53.43s`

The test run prints the existing Windows native import warning `0xc0000139` while Docling imports `semchunk -> mpire -> win32api`. The dependency catches it, all tests complete, and pytest exits successfully. The same warning was present before this feature branch.

## Frontend gates

```powershell
cd frontend
npm run test:run
npm run build
```

Results:

- Vitest: `17` files and `61` tests passed.
- TypeScript and Vite production build passed.
- PWA build generated `manifest.webmanifest`, `registerSW.js`, `sw.js`, and the Workbox bundle.
- Workbox precache contains 13 unique static entries and no API response cache rule.
- Output includes the offline page plus 192, 512, maskable 512, and Apple touch icons.
- The ordinary and maskable 512 icons have distinct SHA-256 hashes.

## Review remediation

Final code review findings were reproduced with regression tests and fixed:

- PWA navigation now uses `NetworkOnly` and falls back to the precached offline page only after a failed page navigation. `/api`, `/api/**`, and `/health` are excluded. The generated worker has no default `NavigationRoute`.
- Login tracking is bounded with LRU eviction, retains exact per-identity expiry, and adds an independent IP-wide attempt limit without globally rejecting new identities.
- Closed registration is checked before password hashing, while the SQLite uniqueness constraint still protects the first-owner race.
- Unknown users run a dummy Argon2 verification for valid-length passwords.
- Registration and login parse credential types explicitly, never echo rejected password values, map blank usernames to stable client errors, and reject out-of-policy login passwords before Argon2 verification.
- An independent final review approved the corrected implementation with no remaining concrete defects.

## Deployment asset checks

```powershell
cd backend
D:\科研助手\enhanced-deep-research\backend\.venv\Scripts\python.exe -m pytest tests/acceptance/test_deployment_assets.py tests/acceptance/test_readme_commands.py -q
D:\科研助手\enhanced-deep-research\backend\.venv\Scripts\python.exe -c "from pathlib import Path; import yaml; data=yaml.safe_load(Path('..\\compose.yaml').read_text(encoding='utf-8')); assert set(data['services']) == {'api','web'}; assert 'ports' not in data['services']['api']"
```

Results:

- Deployment and README acceptance: `6 passed`.
- Compose YAML parsed successfully with exactly `api` and `web` services.
- The API has no published host port, uses one Uvicorn worker, and mounts persistent data/model volumes.
- Caddy is the only public service and maps ports 80/443.

The following commands could not be run because `docker` is not installed on this workstation:

```bash
docker compose --env-file deploy/.env.example build
docker compose --env-file deploy/.env.example config
```

They remain required on the deployment host before release.

## Repository and secret inspection

Commands:

```powershell
git status --short
git diff --cached --name-only
git ls-files
git grep -En 'sk-[A-Za-z0-9_-]{20,}|(LLM|TAVILY|QDRANT|EMBED)_API_KEY=[^[:space:]]+'
```

Results:

- Implementation files were clean after commit `ba225d8`; only this verification record remained to commit.
- No files were staged.
- No tracked runtime `.env`, SQLite/database file, data directory, Hugging Face/model cache, or provider key was found.
- Raw session tokens are stored only in HttpOnly Cookies at runtime; persisted sessions contain SHA-256 token hashes.
- Passwords are accepted only through request bodies or interactive hidden prompts and are persisted as Argon2id hashes.

## Pending live checks

These require a real domain, provider credentials, Docker host, browser, and persistent volumes:

1. Build both container images and run `docker compose config`.
2. Confirm Caddy obtains a valid HTTPS certificate for the production domain.
3. Create the first owner in a new browser and confirm registration closes.
4. Run live LLM/Tavily research and Qdrant/embedding document flows.
5. Verify long SSE streaming and the 50 MiB upload boundary through Caddy.
6. Install the PWA from the browser and launch it from the desktop icon.
7. Restart both containers and confirm owner, sessions, research history, RAG catalog, and model caches persist.
8. Perform a backup, password reset, and volume-preserving rollback rehearsal.
