# Single Owner PWA Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有单实例研究系统增加唯一所有者账户、统一 API 鉴权、可安装 PWA，以及 HTTPS 单机 Docker 部署。

**Architecture:** FastAPI 使用现有 SQLite 文件保存唯一 owner 和服务端会话，通过统一 `require_owner` 依赖保护研究、记忆和文献路由。Vue 在后端健康检查后进入认证门禁，所有业务请求通过统一 fetch 层携带 Cookie 和 CSRF；Caddy 在同一域名下提供前端并代理到单 worker FastAPI，现有研究数据和 Qdrant collection 不迁移。

**Tech Stack:** Python 3.11+、FastAPI、aiosqlite、argon2-cffi、pytest、Vue 3、TypeScript、Vitest、vite-plugin-pwa、Caddy、Docker Compose

**Spec:** `docs/superpowers/specs/2026-09-26-single-owner-pwa-auth-design.md`

## Global Constraints

- 只允许一个 `role='owner'` 用户；不实现多用户、角色、邮箱、OAuth 或在线找回密码。
- 不给现有 run、thread、checkpoint、archive、memory card 或 Qdrant payload 增加 `user_id`，不得迁移或删除已有业务数据。
- `/api/v1/research/**`、`/api/v1/memories/**`、`/api/v1/literature/**` 全部认证；`/health` 与规定的认证入口公开。
- 密码 12–128 个字符并使用 Argon2id；明文密码不得进入日志、SSE、错误详情或数据库。
- 会话令牌使用 `secrets.token_urlsafe(32)`；浏览器只在 HttpOnly Cookie 持有原始值，SQLite 只存 SHA-256 哈希；默认 7 天。
- 生产 Cookie 为 `__Host-research_session`，具有 Secure、HttpOnly、SameSite=Lax、Path=/；本地 HTTP 使用 `research_session_dev` 且 Secure=false。
- 已认证的 POST、PUT、PATCH、DELETE 请求必须通过 `X-CSRF-Token`；注册和登录因尚无会话而豁免。
- 登录限流按 IP 与 `username.strip().casefold()` 组合计算，15 分钟最多 5 次失败；登录成功清零。
- 前端不得把会话令牌放入 localStorage、sessionStorage 或 Vue 状态。
- Service Worker 只预缓存版本化静态资源与离线说明页；API、健康检查、SSE、上传和回答不进入运行时缓存。
- 生产只运行一个 FastAPI worker，API 容器不暴露公网端口。
- 保留工作区已有未提交修改；每个任务只暂存该任务列出的文件。

## Review Focus

- 并发首次注册：一个成功，一个返回 `403 registration_closed`，数据库只有一个 owner。
- 用户名边界：空白或超过 64 字符返回 422；合法值去除首尾空白。
- 会话撤销：到期、退出或重置密码后旧 Cookie 立即 401；SSE 只在握手时验证，已经建立的流不中途强停。
- CSRF 覆盖：研究 SSE、恢复、取消、multipart 上传、文献查询/回答/删除和退出缺失或错误 token 时均在调用业务逻辑前返回 403。
- 离线边界：API 永远不能由应用壳或离线页代答；网络失败保持失败，仅页面导航显示离线说明。

---

## File Map

- `backend/src/deep_research/auth/*`：认证模型、密码策略、限流、服务、依赖和 CLI。
- `backend/src/deep_research/persistence/auth_store.py`：SQLite owner/session 事务。
- `backend/src/deep_research/api/auth_routes.py`：认证 HTTP 接口和 Cookie。
- `frontend/src/api/http.ts`、`auth.ts`、`stores/auth.ts`：统一请求与认证状态。
- `frontend/src/components/AuthGate.vue`、`OwnerSetup.vue`、`LoginForm.vue`：认证 UI。
- `frontend/public/*`、`vite.config.ts`、`InstallPrompt.vue`：PWA 与安装入口。
- `backend/Dockerfile`、`frontend/Dockerfile`、`compose.yaml`、`deploy/Caddyfile`：单机 HTTPS 部署。

### Task 1: Authentication primitives, configuration, and rate limiting

**Files:**
- Create: `backend/src/deep_research/auth/__init__.py`
- Create: `backend/src/deep_research/auth/models.py`
- Create: `backend/src/deep_research/auth/passwords.py`
- Create: `backend/src/deep_research/auth/rate_limit.py`
- Modify: `backend/src/deep_research/config.py`
- Modify: `backend/pyproject.toml`
- Modify: `.env.example`
- Create: `backend/tests/unit/test_auth_primitives.py`
- Modify: `backend/tests/unit/test_config.py`

**Interfaces:**
- Produces frozen `UserRecord`, `SessionRecord`, `AuthContext`, `IssuedSession`.
- Produces `validate_password(password: str) -> None` and `Argon2PasswordHasher.hash/verify`.
- Produces `LoginRateLimiter.is_allowed(client_ip, username)`, `record_failure`, `clear` with injectable monotonic clock.
- Adds `app_base_url`, `auth_cookie_secure`, `auth_session_days`, `auth_login_attempts`, `auth_login_window_seconds` and computed cookie name/max-age settings.

- [ ] **Step 1: Write failing tests**

  Assert 11/129-character passwords fail and 12/128 pass; hashes start `$argon2id$`, verify only the correct password, and omit plaintext. Assert five failures block the sixth for 900 seconds, while another IP works and clear/expiry restores access. Assert local and secure cookie defaults plus 7-day and 5/900 defaults.

- [ ] **Step 2: Verify the tests fail**

  Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/unit/test_auth_primitives.py tests/unit/test_config.py -q`

  Expected: FAIL because the auth package, settings, and argon2 dependency are missing.

- [ ] **Step 3: Implement primitives and settings**

  Use `argon2.PasswordHasher(type=Type.ID, memory_cost=19456, time_cost=2, parallelism=1, hash_len=32, salt_len=16)`. Add `argon2-cffi` and document production auth variables in `.env.example`.

- [ ] **Step 4: Install and verify**

  Run: `cd backend; .\.venv\Scripts\python.exe -m pip install -e ".[dev,rag]"; .\.venv\Scripts\python.exe -m pytest tests/unit/test_auth_primitives.py tests/unit/test_config.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit**

  `git add .env.example backend/pyproject.toml backend/src/deep_research/config.py backend/src/deep_research/auth backend/tests/unit/test_auth_primitives.py backend/tests/unit/test_config.py`

  `git commit -m "feat: add authentication primitives"`

### Task 2: SQLite owner and session persistence

**Files:**
- Create: `backend/src/deep_research/persistence/auth_store.py`
- Create: `backend/tests/integration/test_auth_store.py`

**Interfaces:**
- Consumes Task 1 records.
- Produces `RegistrationClosed` and `AuthStore(database_path: Path)`.
- Produces async `initialize`, `registration_open`, `create_owner`, `find_owner_by_username`, `create_session`, `resolve_session`, `delete_session`, `replace_owner_password`.

- [ ] **Step 1: Write failing store tests**

  Verify schema/index creation beside an existing business table without modifying it; concurrent owner creation returns one owner and one `RegistrationClosed`; only token hashes are stored; expired sessions are removed; logout revokes one session; password replacement updates the hash and revokes all sessions atomically; foreign-key cascade works.

- [ ] **Step 2: Verify failure**

  Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/integration/test_auth_store.py -q`

- [ ] **Step 3: Implement the store**

  Create the exact `users`, `auth_sessions`, and `idx_auth_sessions_user_expiry` DDL from the spec. Use `BEGIN IMMEDIATE` for owner creation and password replacement, UTC ISO timestamps, the unique role constraint for races, and `PRAGMA foreign_keys=ON` on every connection. Update `last_seen_at` without extending fixed `expires_at`.

- [ ] **Step 4: Run persistence regressions**

  Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/integration/test_auth_store.py tests/integration/test_memory_store.py tests/integration/test_persistence.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit**

  `git add backend/src/deep_research/persistence/auth_store.py backend/tests/integration/test_auth_store.py`

  `git commit -m "feat: persist owner sessions"`

### Task 3: Authentication service and password reset CLI

**Files:**
- Create: `backend/src/deep_research/auth/service.py`
- Create: `backend/src/deep_research/auth/__main__.py`
- Create: `backend/tests/unit/test_auth_service.py`
- Create: `backend/tests/integration/test_auth_cli.py`

**Interfaces:**
- Produces `InvalidCredentials`, `LoginRateLimited` and `AuthService`.
- Produces async `register(username, password) -> IssuedSession`, `login(username, password, client_ip) -> IssuedSession`, `authenticate(raw_token) -> AuthContext | None`, `logout(raw_token)` and `reset_password(new_password)`.
- Produces `hash_session_token(raw_token) -> str` using SHA-256 hex.

- [ ] **Step 1: Write failing service and CLI tests**

  Assert registration trims a 1–64 character username, creates a session, never persists the raw token, and rejects a second owner. Unknown user and wrong password share `InvalidCredentials`; limiter and success reset work; expiry/logout/reset revoke old access. CLI reads two values through `getpass`, accepts no password argument, updates the hash, and never prints it.

- [ ] **Step 2: Verify failure**

  Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/unit/test_auth_service.py tests/integration/test_auth_cli.py -q`

- [ ] **Step 3: Implement service and CLI**

  Inject UTC and token factories for tests. Keep username matching exact after trim; casefold only the limiter key. `python -m deep_research.auth reset-password` opens the configured SQLite file and invalidates sessions after a matching double prompt.

- [ ] **Step 4: Verify**

  Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/unit/test_auth_service.py tests/integration/test_auth_cli.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit**

  `git add backend/src/deep_research/auth/service.py backend/src/deep_research/auth/__main__.py backend/tests/unit/test_auth_service.py backend/tests/integration/test_auth_cli.py`

  `git commit -m "feat: add owner authentication service"`

### Task 4: FastAPI authentication routes and route protection

**Files:**
- Create: `backend/src/deep_research/auth/dependencies.py`
- Create: `backend/src/deep_research/api/auth_routes.py`
- Modify: `backend/src/deep_research/api/main.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/integration/test_auth_api.py`
- Modify: `backend/tests/integration/test_api.py`
- Modify: `backend/tests/integration/test_literature_api.py`

**Interfaces:**
- Produces `get_auth_service(request) -> AuthService` and `require_owner(request) -> AuthContext`.
- Produces `AuthStatusResponse{registration_open, authenticated}` and `AuthSessionResponse{user_id, username, role, csrf_token}`.
- Public: GET `/api/v1/auth/status`, POST `/api/v1/auth/register`, POST `/api/v1/auth/login`.
- Authenticated: GET `/api/v1/auth/me`, POST `/api/v1/auth/logout`.

- [ ] **Step 1: Write failing API tests**

  Test status transitions, local/production Cookie flags, no token in JSON, duplicate registration 403, generic invalid-login 401, sixth-attempt 429 with Retry-After, and public health/auth endpoints. Parameterize all research/memory/literature routes to return 401 without Cookie. Verify every unsafe route rejects missing/wrong CSRF before its fake runs; correct CSRF permits representative SSE, memory, upload, delete and logout flows; old Cookie fails after logout/reset.

- [ ] **Step 2: Verify failure**

  Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/integration/test_auth_api.py tests/integration/test_api.py tests/integration/test_literature_api.py -q`

- [ ] **Step 3: Implement API wiring**

  Add `auth_service: AuthService | None = None` to `create_app`. Production lifespan initializes `AuthStore` before injected or production runtime branches. Include research, memory and literature routers with `Depends(require_owner)`; keep health and public auth outside. Use constant-time CSRF comparison for authenticated unsafe methods and allow `X-CSRF-Token` in CORS. Validate before opening SSE; do not revalidate an established stream.

- [ ] **Step 4: Preserve existing tests deliberately**

  General `api_app` overrides `require_owner` with a fixed context; auth tests do not. Update the approved endpoint test to include memory/auth routes without weakening protection tests.

- [ ] **Step 5: Run focused and full backend tests**

  Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/integration/test_auth_api.py tests/integration/test_api.py tests/integration/test_literature_api.py -q; .\.venv\Scripts\python.exe -m pytest -q`

  Expected: PASS.

- [ ] **Step 6: Commit**

  `git add backend/src/deep_research/auth/dependencies.py backend/src/deep_research/api/auth_routes.py backend/src/deep_research/api/main.py backend/tests/conftest.py backend/tests/integration/test_auth_api.py backend/tests/integration/test_api.py backend/tests/integration/test_literature_api.py`

  `git commit -m "feat: protect business APIs with owner sessions"`

### Task 5: Frontend authenticated transport and session state

**Files:**
- Create: `frontend/src/api/http.ts` and `frontend/src/api/http.test.ts`
- Create: `frontend/src/api/auth.ts` and `frontend/src/api/auth.test.ts`
- Create: `frontend/src/stores/auth.ts` and `frontend/src/stores/auth.test.ts`
- Modify: `frontend/src/api/research.ts` and `frontend/src/api/research.test.ts`
- Modify: `frontend/src/api/literature.ts`
- Create: `frontend/src/api/literature.test.ts`

**Interfaces:**
- Produces `ApiError`, `apiFetch`, `setCsrfToken` and `setUnauthorizedHandler`.
- Produces auth API functions and singleton `useAuthStore()` with states `checking | setup | login | authenticated`.
- Existing research/literature function signatures remain stable.

- [ ] **Step 1: Write failing transport/store tests**

  Assert `credentials:'same-origin'`, CSRF only on unsafe requests, no forced Content-Type for FormData, sanitized errors, and one 401 callback. Status must route to setup/login/authenticated; restored auth calls `/me`; logout/401 clear owner and CSRF; no browser storage is used.

- [ ] **Step 2: Write failing client migration tests**

  Prove all research, memory and literature operations use `apiFetch`, unsafe calls receive CSRF, and multipart boundaries remain browser-generated.

- [ ] **Step 3: Verify failure**

  Run: `cd frontend; npm run test:run -- src/api/http.test.ts src/api/auth.test.ts src/stores/auth.test.ts src/api/research.test.ts src/api/literature.test.ts`

- [ ] **Step 4: Implement and migrate**

  Move current error sanitization into `http.ts` and do not auto-retry unsafe calls. Re-export `ApiError` from `research.ts` if current imports require it. Store CSRF only, never the HttpOnly Cookie.

- [ ] **Step 5: Verify**

  Run: `cd frontend; npm run test:run -- src/api src/stores`

  Expected: PASS.

- [ ] **Step 6: Commit**

  `git add frontend/src/api frontend/src/stores/auth.ts frontend/src/stores/auth.test.ts`

  `git commit -m "feat: centralize authenticated frontend requests"`

### Task 6: Authentication gate, setup/login forms, and logout

**Files:**
- Create: `frontend/src/components/AuthGate.vue` and test
- Create: `frontend/src/components/OwnerSetup.vue` and test
- Create: `frontend/src/components/LoginForm.vue` and test
- Modify: `frontend/src/RootApp.vue`, `RootApp.test.ts`, `App.vue`, `App.test.ts`, `style.css`

**Interfaces:**
- Produces `RootApp -> AuthGate -> App` and a visible logout action.

- [ ] **Step 1: Write failing component tests**

  Backend loading remains first. Then open registration shows setup, closed/unauthenticated shows login, and authenticated mounts App. Invalid username/password boundaries and password mismatch are blocked. Login errors stay generic. Logout and simulated 401 unmount research/history/literature and return to login.

- [ ] **Step 2: Verify failure**

  Run: `cd frontend; npm run test:run -- src/RootApp.test.ts src/App.test.ts src/components/AuthGate.test.ts src/components/OwnerSetup.test.ts src/components/LoginForm.test.ts`

- [ ] **Step 3: Implement UI**

  `AuthGate` calls initialize once and renders exactly one screen. Add autocomplete values, accessible errors, disabled submit state, and logout in the existing header.

- [ ] **Step 4: Run component and full frontend tests**

  Run: `cd frontend; npm run test:run -- src/RootApp.test.ts src/App.test.ts src/components/AuthGate.test.ts src/components/OwnerSetup.test.ts src/components/LoginForm.test.ts; npm run test:run`

  Expected: PASS.

- [ ] **Step 5: Commit**

  `git add frontend/src/components/AuthGate.vue frontend/src/components/AuthGate.test.ts frontend/src/components/OwnerSetup.vue frontend/src/components/OwnerSetup.test.ts frontend/src/components/LoginForm.vue frontend/src/components/LoginForm.test.ts frontend/src/RootApp.vue frontend/src/RootApp.test.ts frontend/src/App.vue frontend/src/App.test.ts frontend/src/style.css`

  `git commit -m "feat: add owner setup and login gate"`

### Task 7: Installable PWA with static-only offline behavior

**Files:**
- Modify: `frontend/package.json`, `package-lock.json`, `vite.config.ts`, `src/vite-config.test.ts`, `index.html`, `src/env.d.ts`, `src/App.vue`
- Create: `frontend/pwa-assets.config.ts`
- Create: `frontend/public/favicon.svg`, `offline.html` and generated 192/512/maskable/apple PNGs
- Create: `frontend/src/components/InstallPrompt.vue` and test

**Interfaces:**
- Manifest uses `start_url:'/'`, `scope:'/'`, `display:'standalone'` and required icons.
- Workbox uses `navigateFallback:'/offline.html'`, denylist `[/^\/api\//, /^\/health$/]` and `runtimeCaching:[]`.

- [ ] **Step 1: Write failing PWA tests**

  Assert manifest fields/icons, denylist, empty runtime caching and offline fallback. Install button is hidden without `beforeinstallprompt`, shown after it, invokes prompt once, and hides after completion or `appinstalled`.

- [ ] **Step 2: Verify failure**

  Run: `cd frontend; npm run test:run -- src/vite-config.test.ts src/components/InstallPrompt.test.ts`

- [ ] **Step 3: Add dependencies and assets**

  Add `vite-plugin-pwa` and `@vite-pwa/assets-generator`. Add `generate:pwa-assets` using `minimal-2023` and commit generated PNGs from `favicon.svg`.

- [ ] **Step 4: Configure PWA**

  Use `generateSW` and `registerType:'autoUpdate'`. Precache build assets and offline page only; add no CacheFirst, NetworkFirst, BackgroundSync or API runtime rule. Place install prompt in authenticated header.

- [ ] **Step 5: Verify tests/assets/build**

  Run: `cd frontend; npm run generate:pwa-assets; npm run test:run -- src/vite-config.test.ts src/components/InstallPrompt.test.ts; npm run build`

  Expected: PASS and output includes manifest, service worker, 192/512 and distinct maskable icon.

- [ ] **Step 6: Commit**

  `git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/vite-config.test.ts frontend/index.html frontend/src/env.d.ts frontend/pwa-assets.config.ts frontend/public frontend/src/components/InstallPrompt.vue frontend/src/components/InstallPrompt.test.ts frontend/src/App.vue`

  `git commit -m "feat: make the research UI installable"`

### Task 8: Single-server Docker, HTTPS proxy, and operations docs

**Files:**
- Create: `backend/Dockerfile`, `backend/.dockerignore`, `frontend/Dockerfile`, `frontend/.dockerignore`
- Create: `deploy/Caddyfile`, `deploy/.env.example`, `compose.yaml`
- Create: `docs/deployment.md`
- Create: `backend/tests/acceptance/test_deployment_assets.py`
- Modify: `README.md`

**Interfaces:**
- Produces public `web` on 80/443 and private `api:8000` with persistent `/app/data` and `/models`.
- API runs `uvicorn deep_research.api.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=*`.

- [ ] **Step 1: Write failing deployment contract tests**

  Assert exactly web/api services, no API host port, data/model volumes, checkpoint and HF cache paths, and one worker. Caddy must proxy API/health, set `flush_interval -1`, cap bodies at 50 MiB, and otherwise serve SPA files. Docs must cover backup, first owner, persistence restart, password reset, logs/status, and rollback without deleting auth tables.

- [ ] **Step 2: Verify failure**

  Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/acceptance/test_deployment_assets.py -q`

- [ ] **Step 3: Implement images and Compose**

  Use `python:3.11-slim` with `.[rag]`. Build Vue with Node and copy dist into `caddy:2-alpine`. Keep API private. Caddy receives `APP_DOMAIN`; provider keys come only from `backend/.env` and never frontend build args.

- [ ] **Step 4: Write deployment and recovery docs**

  Include `docker compose --env-file deploy/.env up -d --build`, DNS/HTTPS prerequisites, SQLite backup, registration, PWA install, SSE/upload checks, reset-password, restart persistence and rollback preserving SQLite/model/Qdrant.

- [ ] **Step 5: Verify configuration**

  Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/acceptance/test_deployment_assets.py tests/acceptance/test_readme_commands.py -q`

  Run: `docker compose --env-file deploy/.env.example config`

  Expected: PASS; two services and no published API port.

- [ ] **Step 6: Commit**

  `git add backend/Dockerfile backend/.dockerignore frontend/Dockerfile frontend/.dockerignore deploy compose.yaml docs/deployment.md backend/tests/acceptance/test_deployment_assets.py README.md`

  `git commit -m "feat: add single-server HTTPS deployment"`

### Task 9: End-to-end regression and release evidence

**Files:**
- Create: `docs/superpowers/verification/2026-09-27-single-owner-pwa-auth.md`
- Modify earlier task files only when a failing gate exposes a concrete defect.

**Interfaces:**
- Produces a reproducible record of commands, results and pending live checks.

- [ ] **Step 1: Run backend gates**

  Run: `cd backend; .\.venv\Scripts\python.exe -m ruff check src tests; .\.venv\Scripts\python.exe -m pytest -q`

- [ ] **Step 2: Run frontend gates**

  Run: `cd frontend; npm run test:run; npm run build`

- [ ] **Step 3: Build and inspect containers**

  Run: `docker compose --env-file deploy/.env.example build; docker compose --env-file deploy/.env.example config`

  Expected: images build and Compose confirms one API worker behind Web. Without real secrets/domain, mark live HTTPS, provider, restart persistence and installed-PWA checks pending rather than claiming success.

- [ ] **Step 4: Record evidence and inspect staged data**

  Save exact results. Confirm no raw token, password, `.env`, model cache, SQLite database or provider key is staged.

- [ ] **Step 5: Commit**

  `git add docs/superpowers/verification/2026-09-27-single-owner-pwa-auth.md`

  `git commit -m "test: verify owner PWA deployment"`
