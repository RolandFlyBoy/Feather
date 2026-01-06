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
pip install -e .              # Install framework
feather test --framework      # Run framework tests
feather new testapp           # Test scaffolding
```

## Testing

- Run tests: `./venv/bin/pytest tests/ -v`
- Framework tests: `feather test --framework`
- Markers: `unit`, `integration`, `e2e`, `scaffolding`, `jobs`
