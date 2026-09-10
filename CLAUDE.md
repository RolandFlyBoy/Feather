# Feather Framework - Development Guide

Instructions for AI assistants developing the Feather framework.

## Critical Rules

These rules are **mandatory**. Violating them causes bugs, security issues, or poor UX.

### No Inline Styles or Scripts in Scaffolded Apps

- Never use inline Tailwind classes in templates
- Never use inline `<script>` blocks in templates
- Never use inline event handlers (`onclick`, `onchange`, etc.)
- Put CSS in `static/css/app.css` using `@apply`
- Put JS in `static/js/` (shared) or `static/islands/` (components)
- **Exception:** Framework templates in `feather/templates/` use inline styles to be self-contained

### No Native Browser Dialogs

- Never use `alert()` — use modal components
- Never use `confirm()` — use `hx-confirm` or custom modal
- Never use `prompt()` — use `window.showPrompt()`
- All modals must close with ESC key and have visible X button

### No Raw fetch()

- Always use `ApiUtility` from `/feather-static/api.js`
- It handles CSRF tokens, retry logic, and error handling automatically

### Progressive Enhancement Order

1. **Components** first (server-rendered Jinja2 macros)
2. **HTMX** for server interactions without page reload
3. **Islands** only when client-side state is truly needed
4. 90% of features should work with Components + HTMX

### Routes Thin, Services Fat

- Routes: validate input, call services, return response
- Services: all business logic, database operations, validation
- Never put complex logic in route handlers

### Always Protect Routes

- Use `@auth_required` on routes needing authentication
- Use `@admin_required` for admin-only routes
- `@auth_required` automatically blocks suspended users with 403

### Never Bypass Tenant Isolation

- Always filter queries by `tenant_id` in multi-tenant apps
- Use `get_current_tenant_id()` or `require_same_tenant()`
- Never trust user input for tenant identification

### Google Profile Images

- Always add `referrerpolicy="no-referrer"` to `<img>` tags with Google URLs

### Tests Drive Framework Fixes

- Never change test expectations to match broken framework behavior
- If a test fails, fix the framework code, not the test
- Document temporary workarounds with TODO comments

### Don't Commit Until Asked

- Never commit or push changes automatically
- Wait for explicit user instruction to commit
- Always run `feather test --framework` before committing
- Run `feather test --framework --clean` after testing to remove test artifacts

## Architecture

Feather is a Flask-based framework with server-first rendering:

- **Server rendering** via Jinja2 templates (default)
- **HTMX** for dynamic interactions returning HTML fragments
- **Islands** for complex client-side state (drag-drop, real-time)

### Three-Layer UI

| Layer | Use For |
|-------|---------|
| Components | Static UI (buttons, cards, forms) |
| HTMX | Server interactions (like/unlike, search, pagination) |
| Islands | Client state (drag-drop, audio players, games) |

### Two-Axis Authority Model

| Axis | Field | Scope |
|------|-------|-------|
| Tenant role | `user.role` | Within tenant (admin, editor, user) |
| Platform authority | `user.is_platform_admin` | Cross-tenant operations |

Key invariants:
- Every user has a non-null `tenant_id`
- `User.role` defaults to `"user"`, never null
- `User.is_admin` is a property derived from `role == "admin"`
- Tenant admins don't bypass tenant isolation

## Framework Structure

```
feather/
├── cli/              # CLI commands (new, dev, db, generate)
├── core/             # App class, discovery, helpers
├── db/               # SQLAlchemy setup, mixins
├── auth/             # OAuth, decorators, roles
├── services/         # Service base class
├── events/           # Event dispatcher
├── jobs/             # Sync, thread, and RQ backends
├── cache/            # Memory and Redis backends
├── storage/          # Local and GCS backends
├── exceptions/       # Exception hierarchy
├── serializers/      # JSON serialization
├── templates/        # Framework components and error pages
└── static/           # api.js, feather.js (served at /feather-static/)
```

### Scaffolded App Structure

```
myapp/
├── models/           # SQLAlchemy models (if database enabled)
├── services/         # Business logic (auto-discovered)
├── routes/
│   ├── api/          # JSON routes → /api/*
│   └── pages/        # HTML routes → /*
├── templates/
│   ├── components/   # Custom/override components
│   ├── partials/     # HTMX fragments
│   ├── pages/        # Full page templates
│   └── errors/       # Error page templates
├── static/
│   ├── css/          # Tailwind styles (app.css)
│   ├── js/           # Shared JavaScript
│   ├── islands/      # Interactive JS components
│   └── dist/         # Built assets (gitignored)
├── tests/            # Test files
├── migrations/       # Alembic migrations (if database enabled)
└── logs/             # Application logs
```

## Key Files to Modify

| Task | Location |
|------|----------|
| CLI commands | `feather/cli/` |
| Scaffolding | `feather/cli/new.py` |
| Core framework | `feather/core/app.py`, `feather/core/discovery.py` |
| Template helpers | `feather/core/helpers.py` |
| Database | `feather/db/__init__.py` |
| Exceptions | `feather/exceptions/__init__.py` |

## Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Models | PascalCase | `User`, `BlogPost` |
| Services | snake_case_service | `user_service.py` |
| Routes | snake_case | `users.py`, `blog_posts.py` |
| Islands | kebab-case | `like-button.js` |
| Templates | snake_case | `user_profile.html` |
| Database tables | snake_case plural | `users`, `blog_posts` |
| Components | snake_case | `button.html`, `card.html` |

## Development Commands

```bash
pip install -e ".[dev]"       # Install framework with test and lint tools
feather test --framework      # Run framework tests
feather new testapp           # Test scaffolding
```

Commands a generated app gets, worth knowing when changing the scaffold:

```bash
feather check                 # conventions, machine-checked; exit 1 on error
feather components            # every component macro and its real signature
feather security-check        # secrets, cookies, debug, dependency versions
feather env check             # env keys config.py reads vs what is set
feather docker init           # write the Docker deployment layout
```

`feather check` exists so the "Critical Rules" above are enforced rather than
merely stated. When you add a rule to this document, add a check for it.

## Releasing

Releases go to PyPI from GitHub Actions with trusted publishing: PyPI trusts
the `publish.yml` workflow in RolandFlyBoy/Feather (environment `pypi`), so
there is no API token anywhere. Set up once on PyPI on 2026-09-10.

1. Add the changes to `CHANGELOG.md` under "Unreleased" as you go.
2. Bump `version` in `pyproject.toml` and `__version__` in
   `feather/__init__.py` (they must match), move the changelog entry under
   the new version, commit ("Bump version to X.Y.Z").
3. `git tag vX.Y.Z && git push origin main vX.Y.Z`.
4. The workflow refuses a tag that does not match the version strings, runs
   the test suite, builds and `twine check`s the sdist and wheel, then
   uploads. Re-run from the Actions tab if the upload step fails.
5. Apps pin the release (`feather-framework==X.Y.Z` in their
   requirements.txt) and upgrade by bumping the pin.

## Lessons from apps in production (2026-09)

Things found while running OpenCVNGN and BRNR on Feather. Ticked items are
folded into the framework or the scaffold.

- [x] **htmx extensions load after htmx has processed the page.** The
      scaffold's `vendor.js` imported htmx (which initialises the document as
      soon as it runs) and then `await import()`ed the extension, so any
      element present at page load never initialised. Fixed in 0.9.6: after
      the extensions load, vendor.js re-triggers `htmx:afterProcessNode` on
      `[hx-ext]` and `[sse-connect]` elements.
- [x] **Flask-WTF CSRF tokens expire after an hour** on top of the session
      lifetime, so a form left open fails with a generic error.
      `WTF_CSRF_TIME_LIMIT = None` is the framework default since 0.9.6; the
      session bounds the token.
- [x] **Tests that hold one app context across requests from several test
      clients** all resolve to the first loaded user, because Flask-Login
      caches the user on `g` for the app context. The README's testing
      section documents this (0.9.7); seed inside a context, make requests
      outside it.
- [x] **The custom confirm modal must be looked up at event time.** The
      handler ran before the modal markup existed, so every `hx-confirm` fell
      through to the native dialog. Fixed in 0.9.6: the modal is resolved
      inside the `htmx:confirm` handler, and the admin layout no longer
      renders a second copy.
- [x] **The Tailwind `@source` must not be an absolute path.** The scaffold
      wrote the scaffolding machine's Feather install path into `app.css`, so
      in any image built elsewhere Tailwind emitted no CSS for framework
      components and they shipped unstyled. Fixed in 0.9.7 via the
      `.feather-templates` link.
- [x] Thread job backend and `job_timeout` (0.9.5).
- [x] Logout and the remember cookie (0.9.5).
- [x] **Flask-Limiter in the scaffold.** The framework's `@rate_limit` is
      per-process, so it does nothing useful across gunicorn workers. Since
      0.9.9 an app scaffolded with auth gets a `rate_limits.py` that runs
      Flask-Limiter (the optional `ratelimit` extra) over the OAuth login and
      callback routes and every admin POST route, with Redis storage from
      `RATELIMIT_STORAGE_URI` / `REDIS_URL` and a logged warning naming the
      multi-worker consequence when it falls back to memory. Both traps bit
      in production and both are now covered by
      `tests/scaffolding/test_rate_limits.py`: `limiter.limit(rule)(view)`
      only returns a wrapper, so unless it is assigned back
      (`app.view_functions[ep] = limiter.limit(rule)(view)`) nothing is
      enforced and the endpoint also drops out of the default limit; and the
      default limit otherwise counts static assets, so a page load of ten
      scripts and fonts earns a 429 unless `static` and `feather_static` are
      exempted through `limiter.request_filter`.

## Testing

```bash
feather test --framework              # Run all framework tests
feather test --framework -v           # Verbose output
feather test --framework -m unit      # Run only unit tests
feather test --framework --fast       # Skip slow tests (e2e, scaffolding)
feather test --framework --clean      # Remove test artifacts (venv, cache, etc.)
```

Markers: `unit`, `integration`, `e2e`, `scaffolding`, `jobs`, `api_contract`
