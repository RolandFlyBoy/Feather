# Feather 0.9.5 → 0.9.8: end-to-end improvement plan

Written 2026-09-10 from a read-only review of the framework, the scaffold, the
docs, and the two production apps (BRNR, OpenCVNGN). Nothing in the repo was
changed. Every finding below has a file:line reference that was checked.

## Status (2026-09-10)

All three releases are implemented and committed locally. Nothing has been
tagged or pushed; the PyPI publish is triggered by pushing a `vX.Y.Z` tag, so
that step is still yours.

| Release | Commit | Suite | What it covers |
|---------|--------|-------|----------------|
| 0.9.6 | `8d341cb` | 1211 passed | Phases 0, 1, 2: CI, security, core correctness |
| 0.9.7 | `bfe8817` | 1410 passed | Phases 3, 4, 5: Docker, Render removal, `feather check`, docs |
| 0.9.8 | `01a0a31` | 1584 passed | Phase 6: extras, one auth decorator, per-app backends, scaffold restructure |
| 0.9.9 | pending | 1603 passed | Flask-Limiter in the scaffold, closing the last production lesson |

Decisions taken: Flask-Limiter is adopted in the scaffold (0.9.9); docs stay
in the README, which is also the PyPI long description; extras shipped in
0.9.8; the multi-tenant log leak needed no hand-patch, because OpenCVNGN's
logs page is platform-admin-only and BRNR is single-tenant.

Every item in CLAUDE.md's "Lessons from apps in production" list is now
ticked.

Two things found while implementing that were not in the original review:

- The scaffold's template files were missing from the built wheel, so a
  `feather new` from a PyPI install would have failed. setuptools' `**` glob
  also skips dotfiles, which would have produced projects with no `.env` or
  `.gitignore`. Both fixed and covered by a test that builds a wheel.
- A scaffolded app with email but no authentication could not start: it
  imported a service module that was only written when auth was also enabled.

## Guiding constraints

- **Existing apps must not break.** BRNR pins 0.9.0, OpenCVNGN pins 0.9.5.
  Apps only move when they bump the pin, so the framework can change freely
  as long as each release has a written upgrade note and drop-in fixes ship
  separately from behaviour changes.
- **Ship in three releases**, smallest and safest first:
  - **0.9.6** – security and correctness patches only. Drop-in.
  - **0.9.7** – Render removed, Docker scaffold, scaffold restructure,
    `feather check`, docs rewrite. Additive; one migration note.
  - **0.9.8** – dependency extras, unified auth decorators, per-app
    backend registry, typing. The only release with intentional breaks.
- **Tests drive fixes.** Every defect gets a failing test first. CI on
  every push is Phase 0 because nothing else is safe without it.

---

## Phase 0 – Safety net (do first, ~1 day)

| # | Task | Why |
|---|------|-----|
| 0.1 | Add `.github/workflows/test.yml`: run `pytest -m "not e2e and not scaffolding"` on push/PR, full suite nightly. `publish.yml` only tests on a tag, after the version bump. | No CI today. |
| 0.2 | Add a scaffolding test that runs `feather new --no-prompt` **and** `npm ci && npx vite build` on the result. | Would have caught the missing `vendor.js` and the absolute `@source` path. |
| 0.3 | Add a scaffolding test for each app type (simple, single-tenant, multi-tenant) that boots the app and hits `/`, `/health`, `/admin` (401/403 expected). | Currently `--no-prompt` only tests the minimal path. |
| 0.4 | Record the current `feather test --framework` baseline (count, duration) in CHANGELOG "Unreleased". | Know what "green" means before touching anything. |
| 0.6 | **Fixed during 0.9.6**: the suite failed intermittently ("table already exists", "no such table", "readonly database") because everything falling back to the default `DATABASE_URL` shared `instance/app.db`. `tests/conftest.py` now pins a private in-memory database for the whole run. Full suite: 1211 passed. | Release gate depends on it. |
| 0.5 | Fix `feather --version` drift: warn when the installed CLI is older than PyPI latest. `feather new` pins whatever CLI version is installed (`new.py:4204`); this machine has 0.9.0 installed against a 0.9.5 repo. | Silent old scaffolds. |

---

## Phase 1 – Security (release as 0.9.6, ~2–3 days)

### Fix now (framework)

| Sev | Finding | Where | Fix | Breaks apps? |
|-----|---------|-------|-----|--------------|
| High | `_safe_next` rejects `\n`, `\r`, `//`, `/\` but not `\t`. `?next=/%09/evil.com` passes and browsers strip the tab, giving `//evil.com` after login. | `feather/auth/google.py:113-125` | Reject any control/whitespace char; additionally require `urlsplit(v).netloc == "" and scheme == ""`. Add test. | No |
| Med | `platform_admin_required` never checks `is_active`; a suspended platform admin keeps cross-tenant power. | `feather/auth/decorators.py:385-395` | Add the active check (mirror `auth_required`). | No |
| Med | `rate_limit` reads raw `X-Forwarded-For`; `cleanup()` is never called so the dict grows forever; per-process so useless under 2 gunicorn workers. | `feather/auth/decorators.py:444, 529-541` | Use `request.remote_addr` (ProxyFix already resolves it), prune on each call, document the limitation, add optional Redis storage. | No |
| Med | Host-header poisoning: `ProxyFix(x_host=1)` unconditional plus `request.host` used for the OAuth `redirect_uri`. Safe behind Caddy/Render, not safe on a bare VPS or tunnel. | `feather/core/app.py:183-188`, `feather/auth/google.py:293-298` | Add `TRUSTED_HOSTS` config (Flask 3.1); `FEATHER_PROXY_FIX` opt-out; warn in production when `OAUTH_CALLBACK_URL` is unset. Keep ProxyFix default on. | No if defaults kept |
| Med | LocalStorage: `upload_path / path` with no normalisation; `../x` and absolute paths escape for upload, download and delete. Uploads are served from `static/` with extension-derived content type (`.html`/`.svg` on app origin). | `feather/storage/local.py:83,124,149,176,192` | `resolve()` and `is_relative_to()` check, reject absolute paths, allow-list extensions or serve with `Content-Disposition: attachment`. | No |
| Med | Google refresh token stored in the signed (not encrypted) session cookie; auto-serialised by any serializer without explicit `Meta.fields`. | `feather/auth/google.py:630-657`, `feather/serializers/base.py:382-384` | Keep only access token/expiry in session; serializer skips columns matching `*token*`, `*secret*`, `password*` unless listed. | No |
| Low | Full emails logged in eight places although `mask_email` exists. | `google.py:500-626` | Use `mask_email`. | No |
| Low | Client-controlled `X-Request-ID` reflected unvalidated into logs and headers. | `feather/core/middleware.py:73-76` | Validate `^[\w.-]{1,128}$`, else regenerate. | No |
| Low | No timeout on token refresh HTTP call. | `google.py:726` | `timeout=10`. | No |
| Low | `cache_response` defaults to `vary_on=["query"]`; on an authenticated route the first user's page is served to all. | `feather/cache/decorators.py:246-256` | Auto-add the user key when authenticated. | No |
| Low | `ApiUtility` sends the CSRF token to every URL including cross-origin. | `feather/static/api.js:96-101,307` | Same-origin only. | No |
| Low | `platform-admin` CLI interpolates the email into Python source run via `exec`. | `feather/cli/platform_admin.py:29-69` | Pass via argv/env. | No |
| Low | Logout over GET (logout CSRF). | `feather/auth/routes.py:62` | Keep GET for compat this release; POST-only in 0.9.8 (scaffold already POSTs). | 0.9.8 only |

### Fix now (scaffold; existing apps patch by hand)

| Sev | Finding | Where | Fix |
|-----|---------|-------|-----|
| High | Multi-tenant admin `get_logs` / `get_log_stats` never filter by `tenant_id`; the multi-tenant rewrite scopes users and stats but not logs. Tenant admins see every tenant's request paths, messages, user ids and stack traces. The Log model docstring claims otherwise. | `new.py:5589-5641`, route `:5176-5197` | Filter by tenant in both methods; store `tenant_id` NULL for unauthenticated 5xx and show those to platform admins only. **Notify BRNR/OpenCVNGN owners to patch `services/admin_service.py`** (only matters for multi-tenant apps). |
| Med | Scaffolded `config.py` sets `SESSION_COOKIE_*` but no `REMEMBER_COOKIE_SECURE/HTTPONLY/SAMESITE`; every login is `remember=True` for 365 days. | `new.py:3648-3653, 3747-3753` | Emit the three flags, or make the scaffold config subclass `feather.core.config.Config` so framework defaults flow through. |
| Med | Scaffold `.env` leaves RQ on pickle with an unauthenticated `redis://` URL. | `new.py:3841` | Scaffold default `JOB_SERIALIZER=json`; refuse unauthenticated Redis in production config. Framework default stays pickle (existing enqueued jobs). |
| Low | Scaffolded `send_email` lets any tenant admin mail any address from the verified sender, unrate-limited. | `new.py:5212-5233` | Restrict recipients to tenant users. |
| Low | If `FLASK_CONFIG` is unset in a container the scaffold falls back to `DevelopmentConfig`: dev secret accepted, headers off, cookies insecure. Only `render.yaml` used to set it. | `feather/core/config.py:144-149`, `app.py:175` | Warn loudly at startup when the dev config is chosen with no environment given; Dockerfile sets `FLASK_CONFIG=production` (Phase 3). |

### Dependency floors (pyproject.toml)

| Package | Now | Raise to | Reason |
|---------|-----|----------|--------|
| authlib | >=1.6.0 | >=1.6.5 | 2025 JWS/JWT fixes; Authlib verifies the OIDC id_token |
| werkzeug | >=3.1.0 | >=3.1.5 | CVE-2025-66221, CVE-2026-21860 |
| flask | >=3.1.0 | >=3.1.3 | CVE-2026-27205 |
| requests | >=2.32.0 | >=2.32.4 | CVE-2024-47081 netrc leak |
| weasyprint | >=63.0 | >=70 | SSRF fixes (CVE-2025-68616, CVE-2026-55073) |
| jinja2, urllib3 | unpinned | >=3.1.6, >=2.5.0 | sandbox escape / known fixes |

Verify each against the advisory database before bumping (numbers came from web
search on 2026-09-10). Consider `psycopg[binary]` 3.x in 0.9.8.

### New: `feather security-check`

One command, run by CI and by the Docker `CMD` before gunicorn. Fails on: dev
`SECRET_KEY`, `DEBUG` on with no `FLASK_CONFIG`, missing secure cookie flags,
`JOB_SERIALIZER=pickle` with unauthenticated Redis, missing
`OAUTH_CALLBACK_URL`/`TRUSTED_HOSTS` in production, `FEATHER_SECURITY_HEADERS`
off, dependency versions below the floors above. Also prints what it checked
so an AI agent can read the result.

### Keep (verified good, do not regress)

Authlib state/nonce handling, verified-email requirement, users created
suspended with `role="user"`, no client mass-assignment of role/tenant,
`session.clear()` before `logout_user()`, dev-secret refusal outside debug,
global CSRF covering HTMX and JSON, real CSP with `frame-ancestors 'none'`,
health endpoint hiding driver errors, autoescaped templates, JSON (not
pickle) cache backend, GCS signed URL sanitising.

---

## Phase 2 – Core correctness (also 0.9.6, ~2 days)

All reproduced in a scratch venv by the core reviewer unless marked.

| # | Defect | Where | Fix |
|---|--------|-------|-----|
| 2.1 | `@job` on the default **sync** backend forwards `job_timeout=None` into the user function: `TypeError`, job marked FAILED. 0.9.5 fixed only the thread backend. Every dev app hits this. | `feather/jobs/__init__.py:335`, `jobs/sync.py:61-93` | Strip framework kwargs in `SyncQueue.enqueue`; add a `@job(...).enqueue` test per backend. |
| 2.2 | Built-in `Config` reads `os.environ` at import, but `load_dotenv` runs later in `Feather.__init__`; with `.env` and no project `config.py`, `SECRET_KEY` stays the dev default and production raises. | `feather/core/config.py:23-90`, `app.py:169` | Load dotenv before config import, or read env lazily. |
| 2.3 | `FLASK_CONFIG=production` with no project `config.py` raises "Could not load config class". | `config.py:173-196` | Fall back to built-in classes for the documented shorthands. |
| 2.4 | Thread backend timeout waits for the job anyway (`with ThreadPoolExecutor` joins on exit); cancel of a delayed job is impossible because status is STARTED before the wait; `enqueue_at` with an aware datetime raises. | `jobs/thread.py:287-296, 466-473, 504-522`, `jobs/base.py:179` | Dedicated thread + `join(timeout)`; stay QUEUED until run; check CANCELED before execute; tz-aware arithmetic. |
| 2.5 | Error JSON carries a fresh `uuid4()` as `request_id`, not the `X-Request-ID` header value; logs and bodies never correlate. | `error_handlers.py:142, 242`, `middleware.py:76` | Reuse `g.request_id`. |
| 2.6 | `abort(403)`, 405 and Flask-WTF CSRF 400 on `/api/*` return HTML, so `api.js` `.json()` throws. Only 404/500/`FeatherException` are JSON. | `error_handlers.py:212-269` | One `HTTPException` handler using a single `_is_api_request()`. |
| 2.7 | `setup_logging` leaves Flask's default handler on `app.logger`; every line logged twice. | `middleware.py:232-234` | Remove the default handler. |
| 2.8 | `ImportError` inside a routes/models/services module is printed and swallowed; routes vanish silently, auth silently disabled. Worst possible behaviour for an AI agent. | `discovery.py:42-43, 78-79, 139-140`, `app.py:410-413` | Re-raise with a clear message; `FEATHER_LENIENT_DISCOVERY=1` to opt out. |
| 2.9 | Debug-mode island URLs hard-coded to `localhost:5173`; `feather dev --no-vite` gives broken islands. | `helpers.py:146-148` | `VITE_DEV_SERVER` config with fallback to `/static/islands/`. |
| 2.10 | `prompt-modal.js` captures its DOM at load; throws if the script precedes the markup (same class as the confirm-modal lesson). | `feather/static/prompt-modal.js:14-17` | Look up lazily. |
| 2.11 | `feather db *` shells to `flask db` with `capture_output=True`, hiding Alembic output and errors. | `cli/db.py:52-63` | Stream output. |
| 2.12 | Dead code and stale references: stub decorators `core/decorators.py:404-433`, `feather/__init__.py:106` cites a non-existent `feather_framework.md`, `csrf_exempt` mutates `csrf._exempt_views` at request time, dead `--template` flag on `feather new` (`new.py:57`), "not yet implemented" comments on working async listeners (`events/dispatcher.py:101,226`). | various | Delete/correct. |

Also add `__all__` exports for `htmx_redirect`, `with_trigger`,
`AccountSuspendedError`, `RateLimitError` so agents do not have to guess deep
import paths.

---

## Phase 3 – Remove Render, make Docker first-class (0.9.7, ~4–5 days)

Both production apps already left Render for Hetzner (BRNR Aug 2026, OpenCVNGN
Sep 2026). Render is only in `feather deploy render` and the docs; nothing in
core depends on it.

### 3.1 Remove Render

| Location | Action |
|----------|--------|
| `feather/cli/deploy.py` (whole file) | Replace with `feather docker init` (below). Keep the `.dockerignore` body and the "not in a project" guard. |
| `feather/cli/__init__.py:10, 40, 139` | Re-register the new command; fix help text. |
| `feather/cache/redis.py:9, 24`, `feather/core/app.py:184`, `tests/integration/test_app_init.py:154` | Docstring/comment wording only. |
| README `1206-1229` (render.yaml worker), `1728`, `1832`, `2202-2340` (Deploying to Render), `2342-2351`, `2369-2405` | Delete or rewrite (see Phase 5). |
| CHANGELOG "Unreleased" | "Removed `feather deploy render`; added `feather docker init`." |

### 3.2 Fix the one thing that blocks Docker for every scaffolded app

`new.py:651-657` bakes the **absolute path** of the installed Feather package
into `static/css/app.css` as a Tailwind `@source`. BRNR still ships
`/Users/roland/...` and so its production CSS silently lacks every framework
component class. OpenCVNGN wrote a `scripts/feather-templates.mjs` symlink
script plus a `COPY --from=base` Dockerfile step to work around it.

Fix: `feather build` and `feather dev` create (or refresh) a
`.feather-templates` symlink to the installed package's templates; `app.css`
uses `@source "../../.feather-templates/**/*.html"`; `.gitignore` and
`.dockerignore` list it. Dockerfile copies the templates into place. Add the
scaffolding test from 0.2 that asserts no absolute path in `app.css`.

### 3.3 What `feather new` scaffolds (and `feather docker init` adds to an existing app)

Modelled on OpenCVNGN's image and BRNR's compose file, which are the mature
halves of each app.

| File | Content |
|------|---------|
| `Dockerfile` | Multi-stage: `base` (python:3.11-slim, non-root `app` user, `feather-framework==<version>` on its own layer), `frontend` (node:22-alpine, `npm ci --ignore-scripts`, copies framework templates from `base`, `npm run build`), `web` (source + `static/dist`, `HEALTHCHECK` on `/health`, `ENV PORT=8000 WEB_CONCURRENCY=2 FLASK_CONFIG=production`, `CMD ["feather", "start"]`). `worker` target only when jobs enabled, `CMD ["feather", "worker"]`. **No migrations in CMD** (they race with more than one container). |
| `.dockerignore` | OpenCVNGN's list. |
| `docker-compose.yml` | Production: `caddy`, `web`, optional `worker`, `db` (postgres:16), `redis` (valkey:8, `noeviction`, AOF) when cache/jobs selected. Healthchecks, `depends_on: condition: service_healthy`, json-file log cap, `env_file: .env`, `DATABASE_URL`/`REDIS_URL` interpolated from `${POSTGRES_PASSWORD}`. |
| `docker-compose.dev.yml` | `db` + `redis` only. `feather dev` stays on the host with Vite HMR, which is what both authors actually do. |
| `deploy/Caddyfile` | TLS, gzip, `reverse_proxy web:8000` with `X-Real-IP`, apex → www, `${DOMAIN}` placeholder. |
| `deploy/deploy.sh` | BRNR's script: build, `up -d db redis`, `docker compose run --rm web feather db upgrade`, `up -d --remove-orphans`, wait on Docker health status (OpenCVNGN's approach), prune. |
| `deploy/backup.sh` | Nightly `pg_dump` with optional off-site copy. |
| `.github/workflows/deploy.yml` | Test job with Postgres/Valkey service containers, `feather db upgrade` from scratch, pytest; deploy job over SSH with a forced-command key. Two secrets, commented. |
| `.env.example` | The source of truth both apps lacked (OpenCVNGN wrote `env-check.py` because there was none). Marks which keys compose provides. |
| `CLAUDE.md` (scaffolded) | Short "Deployment" section pointing at the above. |

`feather docker init [--force] [--worker] [--domain]` writes the same files
into an existing app and never overwrites without `--force`.

### 3.4 Framework changes the apps exposed

- `feather start` (`cli/build.py:60-140`) honours `PORT`, `WEB_CONCURRENCY`,
  adds `--graceful-timeout`, `--max-requests`, runs `feather security-check`
  first, `exec`s gunicorn so it is PID 1.
- `feather worker` (`cli/worker.py:86`) picks `SimpleWorker` only on macOS;
  add `--simple` flag, JSON serializer respect, app-context-per-job (what
  OpenCVNGN's `AppContextWorker` does by hand).
- `feather env check [file]`: lists env keys referenced by `config.py`, reports
  which are missing from `.env`/a container. Replaces OpenCVNGN's
  `env-check.py` and hard-coded `REQUIRED_VARS`.
- Scaffolded `/api/health` returns `{"status":"ok"}` with no DB check
  (`new.py:4753-4791`); the framework's `/health` checks the DB. Drop the
  scaffold route and point compose/Caddy at `/health`.
- Scaffolded `requirements.txt` pins `feather-framework==<version>`
  (`new.py:4203-4215` is currently unpinned; both apps pin by hand).

### 3.5 Migration note for existing apps (goes in CHANGELOG and README)

> 0.9.7 removes `feather deploy render`. Your existing `Dockerfile`/`render.yaml`
> are yours and keep working. Run `feather docker init` to adopt the new
> layout; it will not overwrite existing files without `--force`. Replace the
> absolute `@source` line in `static/css/app.css` with
> `@source "../../.feather-templates/**/*.html"` and add `.feather-templates`
> to `.gitignore`; without this, framework component styles are missing from
> images built anywhere but the machine that ran `feather new`.

---

## Phase 4 – Scaffold and AI-readiness (0.9.7, ~5–6 days)

### 4.1 Scaffold bugs (fix regardless of restructure)

| # | Bug | Where |
|---|-----|-------|
| 4.1.1 | `static/js/vendor.js` is only written for auth apps but `base.html` loads it and `vite.config.js` lists it as an input. Simple apps have no htmx and `feather build` fails. Tutorials 1–3 are therefore broken. | `new.py:2693-2716`, `:1980`, `:629` |
| 4.1.2 | Confirm modal resolved at script load; `app.js` runs as a classic script before `{{ confirm_modal() }}`, so `hx-confirm` on non-admin pages falls to native `confirm()` in production. `admin.js` does it right; base has a duplicate `#confirm-modal` on admin pages. | `new.py:1755, 1996, 2003, 6291` |
| 4.1.3 | `.env` writes `FLASK_DEBUG=1` while default job backend is `thread`, the combination README warns kills jobs. | `new.py:3707, 3803` |
| 4.1.4 | htmx extensions imported with `await import()` after htmx initialised; no re-process afterwards. SSE not bundled at all. | `new.py:2722-2726` |
| 4.1.5 | `WTF_CSRF_TIME_LIMIT` never set; Flask-WTF's 1-hour default fails long forms. | `feather/core/app.py:195` |
| 4.1.6 | Scaffolded templates violate the scaffold's own CLAUDE.md rules (inline Tailwind everywhere, `style=` at `:2013`, `:6859`). | `new.py:2210-2330`, admin templates |
| 4.1.7 | echarts (~1 MB) in the vendor bundle for every page; only `/admin/analytics` uses it. | `new.py:546-566` |
| 4.1.8 | `feather db init` fails on scaffolded apps (migrations dir already exists); `feather generate model` never updates `models/__init__.py`; `generate serializer` uses a `Meta` style the README does not document. | `cli/db.py:16`, `cli/generate.py:118-121, 485` |
| 4.1.9 | Lessons list in CLAUDE.md: the two Flask-Limiter items do not apply to the framework (Flask-Limiter is not a dependency; `rate_limit` is the in-process limiter). Either adopt Flask-Limiter properly in the scaffold with the re-registration and static-exempt fixes, or move those two items to app-level docs. | `feather/auth/decorators.py:403-577` |

### 4.2 Restructure the generator

`new.py` is 7,467 lines of string literals with f-string escaping, duplicated
SVGs and CSS, and conditional logic by concatenation. Move to
`feather/scaffold/` with real files (`base/`, `db/`, `auth/`, `multi_tenant/`,
`email/`, `docker/` overlays) rendered by Jinja2, and a manifest mapping
options to overlays. `new.py` shrinks to prompting plus copy. Existing
scaffolding tests keep working because `_create_project_files` already takes
an options dict. Do this **before** the Docker files land so they are written
once, as files. Add `--yes`/explicit option flags so agents and CI can
scaffold an auth app without a TTY.

### 4.3 AI-readiness

| Item | What |
|------|------|
| `feather check` | Machine-checks the CLAUDE.md rules: inline `<script>`, `onclick=`, `alert(`/`confirm(`/`prompt(`, raw `fetch(`, inline Tailwind in templates, `@page`/`@api` routes with no auth decorator, queries on `TenantScopedMixin` models without a tenant filter, orphan islands, strict discovery (imports every module and fails loudly). Runs in CI and pre-commit. |
| Component catalogue | `feather components` prints every macro signature from `feather/templates/components/`; scaffold writes `docs/components.md`. The real list has 14 macros; README documents 7–11. Replace `templates/components/README.md` (currently a Tailwind Plus how-to). |
| `AGENTS.md` | Generated alongside `CLAUDE.md` for non-Claude tools. `feather upgrade-guide` regenerates both after a framework bump. |
| `.claude/settings.json` | Allow-list `feather test`, `feather check`, `feather routes`, `pytest`. |
| `feather routes --json`, `feather test --fast` | Structured output and a sub-2-second loop for agents. |
| `TenantScopedMixin` default filtering | `Model.query` auto-filtered by the current tenant so the Phase 1 log-leak class cannot recur in generated services. |
| Typing | Ship `py.typed`; type `paginate`, `to_dict`, `JobResult`, `@inject`. |
| Scaffolded CLAUDE.md | Add `csrf_client`, `feather_asset`, `with_trigger`/`htmx_redirect`, `TenantScopedMixin`, jobs/cache/storage APIs; link the local component catalogue, not GitHub. |

---

## Phase 5 – Documentation (0.9.7, ~3 days)

### 5.1 README fixes (verified wrong today)

- Python "3.10+" (`:75`) vs `requires-python >=3.11`.
- Test fixture example (`:1935-1950`) recommends holding one app context
  across clients, the exact anti-pattern in the lessons list.
- "After each test the transaction is rolled back" (`:1970`); conftest drops
  all tables.
- Scaffolded test file names (`:1860`), dark-mode CSS classes that no scaffold
  file defines (`:293-303`), `/api/health` attributed to the framework
  (`:2260`), config sample differs from generated config (`:2100-2120`),
  `feather db init` documented but unusable (`:2058`), component list gaps.

### 5.2 Structure

Keep the single README (it is also the PyPI long description) but add a
configuration reference and an upgrading section. The config reference is new:
`OAUTH_CALLBACK_URL`, `FEATHER_PRE_REGISTER_CALLBACK`, `REMEMBER_COOKIE_DAYS`,
`JOB_SERIALIZER`, `FEATHER_PERMISSIONS_POLICY`, `WTF_CSRF_EXEMPT_VIEWS`,
`TRUSTED_HOSTS` exist only in code or the changelog today.

### 5.3 New deployment docs

A README "Deploying with Docker" section and `tutorials/06-deploying.md` walking the BRNR path:
VPS bootstrap (ufw, Docker, `deploy` user), DNS, first `deploy.sh`, GitHub
Actions secrets, backups, uptime check. Delete the Render and Fly sections.

### 5.4 Tutorials (all five checked against the code)

- **T4 breaks app startup**: deletes `models/error_log.py` (file is `log.py`)
  and rewrites `models/__init__.py` dropping `Log`, `Account`, `AccountUser`,
  which `admin_service.py` and `seeds.py` import.
- **T5 imports `models.account_user`**, which does not exist (`account.py`).
- **T4/T5 `feather new` transcripts** show prompts that do not exist and omit
  five that do (jobs, auto-approve, Redis, email, display_name).
- **T4 `viewer` role** cannot be assigned from the admin panel or `roles.py`.
- **T2 "continue from T1"** is impossible: a no-database scaffold has no
  models, migrations or `DATABASE_URL`.
- T4/T5 delete `home.py` but leave `tests/test_home.py`.
- No tutorial uses `feather generate`.

### 5.5 CHANGELOG

Backfill 0.9.0–0.9.4 from git history so an upgrade guide is possible.

---

## Phase 6 – Larger refactors (0.9.8)

| # | Change | Risk to apps |
|---|--------|--------------|
| 6.1 | Optional extras: `feather-framework[pdf,gcs,postgres,redis,email,test]`. Today weasyprint, google-cloud-storage, psycopg2-binary, redis, rq, resend, pytest are hard deps of every app. Scaffold pins the extras it enabled. | Medium: apps pinning the bare name must add extras. |
| 6.2 | Unify the two `auth_required`s (`core/decorators.py:154` vs `auth/decorators.py:86`): same name, different suspension behaviour depending on import path. Make the core one an alias of the tenancy-aware one. | Low |
| 6.3 | Per-app backend registry (`app.extensions["feather"]`) replacing module singletons for queue, cache, dispatcher, manifest, rate limiter. `get_queue()`/`get_cache()` stay as facades. | Low |
| 6.4 | One config path: backends stop re-reading `os.environ` with duplicated fallbacks (`jobs/__init__.py:173-194`, `cache/__init__.py:134-147`). | Low |
| 6.5 | `@job` `retry`/`concurrency` honoured on RQ; uniform `JobQueue.enqueue` signature. | Low |
| 6.6 | Logout POST-only; `__Host-` cookie prefixes; `psycopg` 3. | Low–Med, documented |
| 6.7 | Consistent error codes (`NOT_FOUND` vs `VALIDATION_ERROR` naming) — contract-tested, so 0.9.8 only. | Med |

---

## Release sequence

| Release | Contents | Upgrade note |
|---------|----------|--------------|
| **0.9.6** | Phase 0 CI, Phase 1 security, Phase 2 correctness, dependency floors, `feather security-check`. | Drop-in. Multi-tenant apps patch `admin_service.get_logs`. |
| **0.9.7** | Phase 3 Docker + Render removal, Phase 4 scaffold restructure and `feather check`, Phase 5 docs. | `feather docker init`; fix `@source` path; pin version. |
| **0.9.8** | Phase 6. | Extras in `requirements.txt`; auth decorator alias; logout POST. |

Rough effort: 0.9.6 about a week, 0.9.7 about three weeks, 0.9.8 two weeks.
Each phase ends with `feather test --framework` green, `--clean`, changelog
entry, and a smoke test of BRNR and OpenCVNGN against the release candidate
before tagging (both are the regression suite for real usage).

## Decisions taken (2026-09-10)

1. Flask-Limiter is adopted in the scaffold, with the re-registration and
   static-exempt fixes from the lessons list (0.9.7).
2. Docs stay in the GitHub README, which is also the PyPI long description.
   No separate docs site; the README sections are rewritten in place.
3. Dependency extras (6.1) ship in 0.9.8.
4. The multi-tenant log leak is patched by hand in OpenCVNGN (the only
   multi-tenant app on Hetzner) ahead of 0.9.6.
