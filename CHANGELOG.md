# Changelog

Releases are tags (`vX.Y.Z`) published to PyPI by `.github/workflows/publish.yml`
(trusted publishing, no tokens). See "Releasing" in CLAUDE.md.

## Unreleased

## 0.9.7 (2026-09-10) — Docker deployment, Render removed, machine-checkable conventions

Additive for apps on 0.9.6. One manual step is needed to fix a bug that
silently stripped framework styles from production images; see "Upgrade
notes".

Deployment

- **`feather deploy render` is gone.** Both apps this framework was built
  alongside left Render for a single VPS running Docker Compose, and the
  command only ever wrote files. Your existing `Dockerfile` and `render.yaml`
  are yours and keep working.
- **`feather docker init`** writes a complete deployment: a multi-stage
  `Dockerfile` (non-root, no Node in the runtime image, container
  healthcheck), `.dockerignore`, a production `docker-compose.yml` with Caddy,
  Postgres and Valkey, a `docker-compose.dev.yml` that runs only the
  dependencies so `feather dev` keeps Vite's hot reload, `deploy/Caddyfile`,
  `deploy/deploy.sh`, `deploy/backup.sh` and `.env.example`. `feather new`
  scaffolds the same set. Nothing is overwritten without `--force`.
- Migrations deliberately do not run in the container command. Two web
  containers starting at once would race on `feather db upgrade`, so
  `deploy/deploy.sh` runs them once against the new image before swapping
  containers, then waits on Docker's own health status.
- **`feather start`** honours `PORT` and `WEB_CONCURRENCY`, takes
  `--graceful-timeout` and `--max-requests`, runs the security audit first,
  and replaces its own process with gunicorn so signals reach it directly.
- **`feather env check`** lists the environment keys the project's
  `config.py` reads and reports which are missing. Both production apps had
  written this by hand.
- **`feather worker`** takes `--simple` / `--fork` instead of guessing from
  the operating system.

Fixed

- **Framework component styles were missing from every production image.**
  The scaffold wrote the absolute path of the machine's Feather installation
  into `static/css/app.css` as a Tailwind `@source`. That path does not exist
  in a container, so Tailwind silently emitted no CSS for any framework
  component: buttons, modals, toasts and dropdowns shipped unstyled. The
  generated CSS now scans a project-relative `.feather-templates`, which
  `feather dev` and `feather build` point at the installed package and the
  Dockerfile copies in as a real directory. **Existing apps must fix this by
  hand: see "Upgrade notes".**
- Generated healthchecks pointed at a scaffolded route that only proved the
  process was listening. They now use the framework's `/health`, which checks
  the database.

Conventions and AI assistance

- **`feather check`** turns the rules a scaffolded app's guidance states in
  prose into checks that pass or point at a file and line: no inline scripts,
  styles, event handlers or Tailwind utilities in templates; no `alert`,
  `confirm`, `prompt` or raw `fetch` in JavaScript; routes that declare their
  access; tenant filtering on tenant-scoped models; islands that are actually
  mounted; Google avatars carrying `referrerpolicy`. It exits non-zero on an
  error, so it works as a pre-commit hook or a CI step, and `--json` feeds
  tooling.
- **`feather components`** lists every component macro with its real
  signature and import line, parsed from the macros themselves. The README's
  hand-maintained list had drifted; there are 14, not the 7 to 11 documented.
  `--markdown` writes a reference an assistant can read.
- Scaffolded apps get an `AGENTS.md`, the vendor-neutral name other tools look
  for, with the same content as `CLAUDE.md` and generated alongside it so the
  two cannot drift, plus a `.claude/settings.json` pre-approving the read-only
  commands an assistant needs to check its work.
- The framework ships `py.typed`, so type checkers use its annotations.

Documentation

- The README's Render sections are replaced by "Deploying with Docker",
  covering the generated files, the local loop, a first VPS deploy, how
  migrations run, TLS, backups, continuous deployment and a production
  checklist. A new tutorial walks the same ground end to end.
- Corrected against the code: the health endpoints are the framework's
  `/health`, `/health/live` and `/health/ready`, not the scaffolded
  `/api/health`; the component list; the serializer examples, which showed a
  style the generator does not emit; the dark-mode toggle markup; the test
  fixture example, which recommended holding one application context across
  requests and so resolved every request to the first user loaded; Python 3.11
  rather than 3.10; and the scaffolded test filenames.
- The tutorials no longer break when followed. They deleted a model file that
  does not exist, rewrote a package to drop models that scaffolded services
  import, imported a module that was never generated, showed prompts the CLI
  does not ask, and gated a feature on a role the admin panel cannot assign.

Upgrade notes

- **Every existing app should apply the Tailwind fix**, or framework
  component styles are missing from any image built on a machine other than
  the one that ran `feather new`. In `static/css/app.css`, replace the
  absolute `@source "/…/feather/templates/**/*.html"` line with:

  ```css
  @source "../../.feather-templates/**/*.html";
  ```

  then add `.feather-templates` to `.gitignore` and `.dockerignore`. Running
  `feather build` recreates the link.
- To adopt the new deployment layout, run `feather docker init` in the
  project root. It skips files you already have.
- Pin the framework in `requirements.txt` (`feather-framework==0.9.7`) if you
  do not already.

## 0.9.6 (2026-09-10) — security and correctness

Drop-in for apps on 0.9.5. Two behaviour changes are called out under
"Upgrade notes" below; everything else is a fix.

Security

- `?next=` on the Google OAuth routes rejected `//`, `/\`, newlines and
  carriage returns, but not tabs or other control characters. Browsers strip
  those before resolving a URL, so `?next=/%09/evil.com` became `//evil.com`
  and sent the user off-site straight after login. Any whitespace or control
  character is now refused anywhere in the value, and the value must parse
  with no scheme and no host.
- `@platform_admin_required` did not check whether the account was active, so
  suspending a platform admin left their cross-tenant access intact. It now
  raises `AccountSuspendedError` / `AccountPendingError` like the other
  decorators.
- `@rate_limit` keyed its buckets on the raw `X-Forwarded-For` header, which a
  client can set freely to reset its own limit. It now uses
  `request.remote_addr`, which ProxyFix already resolves from the trusted hop.
- The in-memory rate-limit store never pruned itself and grew for the life of
  the process. It now sweeps expired keys.
- `LocalStorage` joined caller-supplied paths onto the upload directory with no
  normalisation, so `../` segments and absolute paths escaped it for upload,
  download, delete, exists and url. Every path is now resolved and must stay
  inside the upload directory.
- Uploads live under `static/`, where Flask serves them with a content type
  taken from the extension, so an uploaded `.html` or `.svg` ran script on the
  application's own origin. Script-capable extensions are now refused by
  default. See `STORAGE_BLOCKED_EXTENSIONS` below.
- Serializers with no explicit `Meta.fields` auto-discovered every column,
  including `google_refresh_token` and `password_hash`. Columns matching
  `*token*`, `*secret*`, `password*`, `*api_key*` and `*private_key*` are now
  skipped unless listed explicitly.
- `cache_response` keyed only on the query string, so on an authenticated route
  the first visitor's rendered page was served to everyone. The key now
  includes the logged-in user and the `HX-Request` header.
- The Google refresh token was kept in the Flask session, which is signed but
  not encrypted, so it travelled in the cookie. It is now read from the user
  model's `google_refresh_token` column when one exists.
- `feather platform-admin <email>` built a Python script by interpolating the
  email into source and running it, so a crafted address could execute
  arbitrary code. Arguments now travel through the environment.
- `ApiUtility` attached the site's CSRF token to every request, including
  cross-origin ones. It now attaches it only to same-origin requests.
- Sign-in log lines masked no email addresses despite `mask_email` existing;
  they do now. Outbound calls to Google gained a 10-second timeout.
- An incoming `X-Request-ID` was reflected into logs and response headers
  unvalidated. It must now match `[A-Za-z0-9._-]{1,128}` or a fresh id is used.

Fixed

- `@job(...).enqueue()` raised `TypeError: got an unexpected keyword argument
  'job_timeout'` on the sync backend, which is the default, so every decorated
  job failed in development. 0.9.5 fixed this for the thread backend only.
- The thread backend's job timeout waited for the job to finish anyway, so a
  one-second timeout on a three-second job returned after three seconds and
  never freed the worker. Delayed and concurrency-queued jobs could not be
  cancelled because they were marked started before they waited.
  `enqueue_at()` raised on a timezone-aware datetime.
- An `ImportError` inside a `models/`, `services/` or `routes/` module was
  printed and swallowed: the routes silently vanished, or authentication was
  silently disabled, and the app started green. Startup now fails with the
  module name and traceback. Set `FEATHER_LENIENT_DISCOVERY` to restore the
  old behaviour.
- Values in `.env` never reached the built-in configuration, because it read
  the environment at import time and `.env` was loaded later. An app with no
  `config.py` of its own kept the development secret key and could not start
  in production. Relatedly, `FLASK_CONFIG=production` failed outright without
  a project `config.py`; the documented shorthands now fall back to the
  built-in classes.
- `abort(403)`, 405 and CSRF failures returned HTML on API routes, so
  `ApiUtility` threw while parsing the response. All `HTTPException`s now use
  the standard JSON envelope for API requests.
- Error responses carried a freshly generated request id rather than the one
  in the `X-Request-ID` header, so logs and response bodies could not be
  correlated.
- Every line written through `app.logger` was emitted twice, because Flask's
  default handler stayed attached alongside the framework's.
- Island scripts in debug mode were hard-coded to `localhost:5173`, so
  `feather dev --no-vite` served broken scripts. The URL comes from
  `VITE_DEV_SERVER`, and built assets are used when Vite is not running.
- `showPrompt` captured its modal elements when the script loaded, so it threw
  if the script came before the markup. It now resolves them at call time.
- `feather db` subcommands buffered Alembic's output and discarded it, which
  hid the reason a migration failed. They stream it now.
- Startup logs a warning when neither `FLASK_ENV` nor `FLASK_CONFIG` is set
  and the development configuration is chosen by default. In a container that
  silently meant a dev secret key, no security headers and insecure cookies.
- `htmx_redirect`, `htmx_refresh`, `with_trigger`, `AccountPendingError`,
  `AccountSuspendedError` and `RateLimitError` are exported from `feather`
  instead of requiring deep imports.

Scaffolded apps

- The multi-tenant admin panel showed every tenant's error logs, including
  request paths, user ids and stack traces, to any tenant admin. The
  multi-tenant rewrite scoped users and statistics but never the log queries.
  Both are now tenant-scoped; platform admins still see everything, including
  rows with no tenant from unauthenticated errors. **Existing multi-tenant
  apps must patch this by hand: see "Upgrade notes".**
- The admin panel's email tool could send to any address from the app's
  verified sender. Recipients are now restricted to users the admin
  administers.
- `static/js/vendor.js` was only generated for apps with authentication, but
  every app's `base.html` loads it and `vite.config.js` builds it, so `feather
  build` failed and htmx was undefined for simple apps.
- `hx-confirm` fell through to the browser's own dialog, because `app.js`
  looked the modal up before `base.html` rendered it. The lookup now happens
  when the event fires, and the admin layout no longer renders a second copy
  of the modal.
- Generated `.env` set `FLASK_DEBUG=1` alongside the thread job backend, a
  combination that silently kills background jobs. Apps with jobs now ship
  with the reloader off.
- Generated configuration now sets `REMEMBER_COOKIE_SECURE` (per environment),
  `REMEMBER_COOKIE_HTTPONLY`, `REMEMBER_COOKIE_SAMESITE`,
  `WTF_CSRF_TIME_LIMIT = None`, `SESSION_PROTECTION = "basic"` in development
  and `JOB_SERIALIZER=json`, and warns in production when RQ points at a
  password-less remote Redis.
- The unused `feather new --template` option is gone.

Dependency floors raised for published advisories: flask 3.1.3, werkzeug
3.1.5, authlib 1.6.5, requests 2.32.4, weasyprint 70. jinja2 3.1.6 and urllib3
2.5.0 are now direct pins rather than whatever a transitive resolve picked.

New

- `feather security-check` audits a deployment: secret strength, debug and
  environment settings, cookie flags, CSRF, job serializer, unauthenticated
  Redis, `OAUTH_CALLBACK_URL`, `TRUSTED_HOSTS`, security headers, `.env` in
  `.gitignore`, and installed dependency versions. Exits non-zero on any
  failure and takes `--json` for CI. Works against a running project or, with
  `--env-file`, against an environment file alone.
- `TRUSTED_HOSTS` is honoured (Flask 3.1), and `FEATHER_PROXY_FIX` /
  `FEATHER_PROXY_FIX_NUM` make the proxy handling explicit. Without them the
  OAuth redirect URI and every external URL derive from a client-supplied Host
  header on any host that is not behind a normalising proxy.
- `feather --version` and `feather new` check PyPI once (2-second timeout,
  silent when offline) and mention a newer release. `FEATHER_NO_UPDATE_CHECK=1`
  turns it off.
- The framework's own test suite no longer shares one SQLite file across
  runs, which was causing sporadic "table already exists" and "readonly
  database" errors unrelated to the test being run. Full suite: 1211 tests.
- Continuous integration: `.github/workflows/test.yml` runs the suite on every
  push and pull request across Python 3.11, 3.12 and 3.13, with the full
  scaffolding and end-to-end suites nightly. Previously tests ran only on a
  release tag, after the version had already been bumped.

Upgrade notes

- The Google refresh token is no longer written to the session. Apps that want
  token refresh need a `google_refresh_token` column on their user model;
  without one, refresh is skipped rather than failing. Sessions written by
  0.9.5 keep working, and the stored value is used once and then dropped.
- `cache_response` now varies on the current user by default. Pass
  `vary_on_user=False` on genuinely public pages to restore the old key.
- `LocalStorage.upload` refuses `html`, `htm`, `svg`, `xhtml`, `xml`, `js`,
  `mjs`, `php` and `phtml`. Set `STORAGE_ALLOWED_EXTENSIONS` to an allow-list
  (which wins over the block list) or replace `STORAGE_BLOCKED_EXTENSIONS` to
  permit any of them.
- Suspending a platform admin now actually removes their access.
- Discovery is strict: a broken `models/`, `services/` or `routes/` module now
  stops the app instead of disappearing. Set `FEATHER_LENIENT_DISCOVERY=1` if
  an app relies on the old behaviour.
- Job functions cannot have parameters named `timeout`, `retry`,
  `concurrency`, `delay` or `queue_name`; those names are reserved by the
  enqueue call. This was already true on the thread backend.
- **Existing multi-tenant apps** carry the admin log leak in their own
  `services/admin_service.py`. In `get_logs()`, directly after
  `query = Log.query`, and in `get_log_stats()`, directly after the
  `base_query` assignment, add:

  ```python
  tenant_id = self._get_tenant_id()
  if tenant_id:
      query = query.filter(Log.tenant_id == tenant_id)
  ```

  using `base_query` in the second case. `_get_tenant_id()` returns `None` for
  platform admins, which is what keeps rows with no tenant visible to them.
  Apps using the admin email tool should add the matching recipient check.

New configuration keys

| Key | Default | Purpose |
|-----|---------|---------|
| `TRUSTED_HOSTS` | unset | Hostnames this app answers to. A foreign `Host` header gets 400. |
| `FEATHER_PROXY_FIX` | `True` | Install ProxyFix. Turn off when nothing normalises forwarded headers. |
| `FEATHER_PROXY_FIX_NUM` | `1` | Trusted proxy hops. |
| `WTF_CSRF_TIME_LIMIT` | `None` | The session bounds the token. Flask-WTF's one-hour default broke long-open forms. |
| `FEATHER_LENIENT_DISCOVERY` | `False` | Warn and continue on a broken module instead of failing. |
| `VITE_DEV_SERVER` | `http://localhost:5173` | Where debug-mode island scripts are served from. |
| `STORAGE_BLOCKED_EXTENSIONS` | script-capable types | Extensions `LocalStorage.upload` refuses. Setting it replaces the list. |
| `STORAGE_ALLOWED_EXTENSIONS` | unset | Allow-list; wins over the block list. |
| `FEATHER_NO_UPDATE_CHECK` | unset | Skip the PyPI version check in the CLI. |

## 0.9.5 (2026-09-10)

First release published through GitHub Actions. Everything below came out of
running OpenCVNGN on the framework in production.

Security
- `?next` on the Google OAuth routes only accepts site-relative paths.
- Logout clears the whole session and, since 0.9.5, does so before
  `logout_user()` so the remember-me cookie is actually deleted (previously
  the next request signed the user straight back in).
- `/health` no longer echoes database error text.
- Cookie flags on the session and remember cookies; configurable
  `FEATHER_PERMISSIONS_POLICY` (default denied camera/microphone, which broke
  in-browser recording).
- Google sign-in requires a verified email; emails are masked in logs.
- Local storage backend is contained to its upload directory; GCS signed URLs
  default to 15 minutes (V4).

Jobs
- `JOB_SERIALIZER=json` for RQ (opt-in; pickle payloads are code execution
  for anyone who can reach Redis).
- Thread backend accepts `job_timeout` (what `@job(timeout=...)` passes)
  instead of forwarding it to the job function.

Other
- `.env` is loaded from the current working directory, not the framework's.
