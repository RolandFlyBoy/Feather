<h1 align="center">
  <img src="https://raw.githubusercontent.com/RolandFlyBoy/Feather/main/feather/static/favicon.svg" alt="" width="64" height="64" style="vertical-align: middle;">
  Feather
</h1>

### What is Feather?

Feather is a full-stack web framework built on proven technologies: **Flask** for the backend, **Tailwind CSS** for styling, **HTMX** for dynamic interactions, and **vanilla JavaScript** for complex client-side behavior.

Built with and optimized for [Claude Code](https://claude.ai/code), though it works with any AI coding assistant. Each project includes a `CLAUDE.md` that gives AI assistants the context they need to follow framework conventions.

### What's Included

Feather provides production-ready infrastructure so you can focus on your application:

| Feature | Options |
|---------|---------|
| **Authentication** | Google OAuth with session management, approval workflow |
| **User Management** | Admin panel for approvals, roles, suspension |
| **Multi-Tenancy** | Domain-based or individual tenants (B2B+B2C) |
| **Background Jobs** | Thread pool with concurrency control, or RQ (Redis) |
| **Caching** | Memory or Redis |
| **File Storage** | Local filesystem or Google Cloud Storage |
| **Email** | Resend for transactional emails |
| **Rate Limiting** | In-memory (or Redis for distributed) |
| **Events** | Pub/sub with sync and async listeners |
| **Error Logging** | Database-backed, tenant-scoped |
| **Health Checks** | `/health`, `/health/live`, `/health/ready` |
| **Request Tracking** | Unique request IDs, JSON logging |

All features are optional and can be enabled during project creation or added later.

### Why Feather?

Python has a long history in web development. Flask and Django powered countless applications through the 2010s. Then the SPA revolution happened—React, Vue, Angular—and suddenly "modern" web development meant writing Python APIs that served JSON to JavaScript frontends.

That split created a gap. Python developers who wanted full-stack productivity had two choices: adopt the JavaScript ecosystem entirely, or stick with Django's monolithic approach that hadn't evolved much for the new era. Meanwhile, Ruby developers had Rails with Hotwire, PHP developers had Laravel with Livewire—both frameworks that embraced server-rendering while adding modern interactivity.

Feather fills that gap for Python. It's a full-stack framework that gives you authentication, admin panels, file storage, background jobs, and a component system out of the box. The frontend uses server-rendered HTML enhanced with HTMX and small JavaScript islands—no virtual DOM, no hydration, no "use client" confusion.

**How other frameworks approach this:**

- **Rails** and **Laravel** pioneered the batteries-included philosophy. They handle auth, database migrations, background jobs, and asset compilation in one cohesive package. Feather takes the same approach but uses Python and modern tooling (Vite 7, Tailwind CSS, HTMX).

- **Next.js** brought React to the server with excellent developer experience. But you're still managing React's complexity—state management, hydration mismatches, deciding what runs where. Feather sidesteps this by keeping JavaScript minimal and optional.

- **Django** remains powerful but feels heavyweight for many projects. Its template language is limiting, the admin is rigid, and adding modern frontend tooling requires significant configuration.

The real unlock is combining good conventions with AI assistance. Feather's predictable patterns—where files go, how services work, what components look like—mean you can describe what you want and get working code. A feature that might take a day of wiring up authentication, writing migrations, building UI, and handling edge cases can be done in a focused session.

Feather is opinionated about its defaults: Google OAuth for auth, Tailwind for styling, PostgreSQL for production data. These choices reduce decision fatigue and let you ship faster. That said, the abstractions are designed to be extensible—the storage backend interface works with local files or GCS, the job queue can run in-process or on Redis, and you can swap in other providers as your needs evolve.

### How the Frontend Works

Feather uses a three-layer approach to building UIs, each solving a different problem:

**Components** are server-rendered Jinja2 macros—similar to Rails view components, Laravel Blade components, or React Server Components. They're reusable pieces of UI (buttons, cards, modals) that render to HTML on the server. No JavaScript, no hydration, just HTML and CSS. You use them like `{{ button("Save", variant="primary") }}`.

**HTMX** handles server interactions without page reloads. If you've used Hotwire/Turbo in Rails or Livewire in Laravel, it's the same idea. Click a button, HTMX makes an HTTP request, the server returns HTML, HTMX swaps it into the page. It replaces most of what you'd use React + fetch for—forms, search, pagination, like buttons—without writing JavaScript. Think of it as server-side rendering with surgical DOM updates.

**Islands** are small JavaScript components for genuinely interactive UI that needs client-side state. The name comes from Astro's Islands Architecture—most of the page is static HTML, with small "islands" of interactivity. Use them for things like drag-and-drop, audio players, or real-time updates where round-tripping to the server would feel sluggish. They're similar to writing a small React component, but without React's runtime overhead.

The mental model: start with Components for everything static, reach for HTMX when you need server data without a page reload, and only use Islands when you genuinely need client-side state. In practice, 90% of features can be built with just Components and HTMX.

---

## Getting Started

### Prerequisites

**Core requirements (all apps):**

- **Python 3.10+** — the runtime
- **Node.js 22+** — for Vite 7 (build tooling) and Tailwind CSS
- **pipx** — for installing the Feather CLI globally

**Simple apps** (no auth, prototypes, internal tools):

- **SQLite** — works out of the box, no setup required

**Production apps** (auth, multi-tenant, background jobs):

- **PostgreSQL** — required for multi-tenant apps, recommended for anything with auth
- **Google Cloud credentials** — for OAuth (free tier works fine)
- **Redis** (optional) — for distributed caching and persistent job queues
- **Google Cloud Storage** (optional) — for file uploads in production
- **Resend** (optional) — for transactional emails

### Installation

**From PyPI (recommended):**
```bash
pip install feather-framework
```

**Or with pipx (isolated environment):**
```bash
brew install pipx && pipx ensurepath  # if you don't have pipx
pipx install feather-framework
```

**For development (contributing to Feather):**
```bash
git clone https://github.com/RolandFlyBoy/Feather.git
cd Feather
pipx install -e .
feather test --framework  # run framework tests
```

This installs the `feather` CLI. You can now run `feather new` from any directory.

### Quick Start

#### 1. Create a New Project

```bash
feather new myapp
```

You'll be prompted for app type first:

| App Type | Database | Auth | Description |
|----------|----------|------|-------------|
| `simple` (default) | Ask (default: none) | No | Static pages, minimal setup |
| `single-tenant` | Ask (default: SQLite) | Yes | One organization, user accounts |
| `multi-tenant` | PostgreSQL (required) | Yes | Multiple organizations (SaaS) |

During scaffolding, you'll be asked about optional features:

- **Background jobs** — available for all app types, runs in a thread pool by default (no Redis required)
- **Caching** — memory cache for development, optionally Redis for production
- **File storage** — local filesystem for development, optionally GCS for production
- **Email** — Resend for transactional emails (authenticated apps only)
- **Admin email** — for authenticated apps, this creates your initial admin user
- **User profile fields** — optional `display_name` and `profile_image_url` fields (authenticated apps)

#### 2. Initialize and Run

```bash
cd myapp
source venv/bin/activate

# Set up database (migrations are manual so you can review models first)
feather db migrate -m "Initial migration"
feather db upgrade
python seeds.py  # Creates admin user if auth enabled

# Start dev server
feather dev
```

Open http://localhost:5173 — Vite handles frontend assets with HMR, Flask runs on port 5000 behind the proxy. CSS and JS changes are instant; template and Python changes trigger a reload.

**Note:** If using background jobs with the thread backend, set `FLASK_DEBUG=0` in `.env`. The Flask reloader kills background threads on file changes. Use `JOB_BACKEND=sync` during development if you need debug mode.

Every Feather project includes a `CLAUDE.md` guide that helps AI assistants understand the framework's patterns and conventions. It's a starting point—add your own project-specific context, domain rules, or coding preferences as your app grows.

### Project Structure

```
myapp/
├── app.py                    # Entry point
├── config.py                 # Configuration classes
├── seeds.py                  # Initial data (if auth enabled)
├── .env                      # Environment variables
├── package.json              # Node dependencies (Vite, Tailwind)
├── vite.config.js            # Build configuration
├── models/                   # SQLAlchemy models (auto-discovered)
├── services/                 # Business logic (auto-discovered)
├── routes/
│   ├── api/                  # API routes → /api/*
│   └── pages/                # Page routes → /*
├── templates/
│   ├── base.html             # Base layout with HTMX/Vite
│   ├── components/           # Custom/override components
│   ├── partials/             # HTMX response fragments
│   └── pages/                # Full page templates
├── static/
│   ├── css/app.css           # Tailwind entry point
│   ├── js/app.js             # Shared JavaScript
│   └── islands/              # Interactive JS components
├── tests/                    # Test files
└── migrations/               # Alembic migrations
```

**Framework-provided** (served from `/feather-static/`, auto-update with Feather upgrades):
- Components: `button`, `card`, `modal`, `input`, `alert`, `icon`, `dropdown`
- JS: `api.js` (CSRF-aware fetch), `feather.js` (Islands runtime)

Override any component by creating your own version in `templates/components/`.

---

## UI Architecture

The concepts are explained in [How the Frontend Works](#how-the-frontend-works). This section is a quick reference.

### Components

```html
{% from "components/button.html" import button %}
{% from "components/icon.html" import icon %}

{{ button("Save", type="submit") }}
{{ button("Delete", variant="danger", icon=icon("delete", size="sm")) }}
```

**Available:** `button`, `card`, `modal`, `input`, `textarea`, `alert`, `icon`, `dropdown`, `confirm_modal`, `prompt_modal`, `toast`

### HTMX

```html
<button hx-post="/api/posts/123/like" hx-swap="outerHTML">Like (5)</button>
```

```python
@api.post("/posts/<post_id>/like")
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.toggle_like(current_user)
    return render_template("partials/like_button.html", post=post, liked=True)
```

**Cross-element updates** — use `HX-Trigger` header to fire events that other elements listen for:
```python
response = make_response(render_template('partials/todo.html', todo=todo))
response.headers['HX-Trigger'] = 'todosUpdated'
return response
```

```html
<div hx-get="/htmx/stats" hx-trigger="load, todosUpdated from:body">
```

**Built-in modals:** `hx-confirm="Delete?"` for confirmations, `window.showPrompt({...})` for input.

### Islands

```javascript
island("counter", {
  persist: true,
  state: { count: 0 },
  actions: {
    increment() { this.state.count++; },
    decrement() { this.state.count--; }
  },
  render(state) {
    return { ".count": state.count };
  }
});
```

```html
<div data-island="counter">
    <button data-action="decrement">-</button>
    <span class="count">0</span>
    <button data-action="increment">+</button>
</div>
```

**Optimistic updates:**
```javascript
await this.optimistic(
  () => { this.state.liked = true; },  // Instant UI update
  () => api.post(`/posts/${this.data.id}/like`)  // Rolls back on failure
);
```

**Drag-drop:** Built-in via `draggable` config — see [CLAUDE.md](CLAUDE.md) for full API.

### Icons

[Google Material Icons](https://fonts.google.com/icons): `{{ icon("home") }}`, `{{ icon("settings", size="lg") }}`

Sizes: `sm` (18px), `md` (24px), `lg` (36px), `xl` (48px)

---

## Backend

### Routes

Routes handle HTTP requests. Feather auto-discovers routes in `routes/api/` and `routes/pages/`.

```python
# routes/api/users.py
from feather import api, auth_required, inject
from services import UserService

@api.get('/users')
@inject(UserService)
def list_users(user_service):
    return {'users': user_service.list_all()}

@api.post('/users')
@auth_required
@inject(UserService)
def create_user(user_service, email: str, username: str):
    user = user_service.create(email=email, username=username)
    return {'user': user}, 201
```

**Route prefixes:**
- `routes/api/*.py` → `/api/*`
- `routes/pages/*.py` → `/*`

### Models

Models define your database schema using SQLAlchemy with helpful mixins:

```python
# models/post.py
from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin

class Post(UUIDMixin, TimestampMixin, SoftDeleteMixin, Model):
    __tablename__ = 'posts'

    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text)
    author_id = db.Column(db.String(36), db.ForeignKey('users.id'))
```

**Mixins:**
| Mixin | Provides |
|-------|----------|
| `UUIDMixin` | `id` (auto-generated UUID) |
| `TimestampMixin` | `created_at`, `updated_at` |
| `SoftDeleteMixin` | `soft_delete()`, `restore()`, `query_active()` |
| `OrderingMixin` | `move_to()`, `move_above()`, `query_ordered()` |
| `TenantScopedMixin` | `tenant_id`, `for_tenant()` |

**OrderingMixin** for drag-drop:
```python
class Card(UUIDMixin, TimestampMixin, OrderingMixin, Model):
    __tablename__ = 'cards'
    __ordering_scope__ = ['column_id']  # Position is per-column

    title = db.Column(db.String(200))
    column_id = db.Column(db.String(36), db.ForeignKey('columns.id'))

# Reorder
card.move_to(0)           # Move to top
card.move_above(other)    # Move above another card
Card.query_ordered(column_id=col.id).all()
```

### Schema Design: Separating Users, Accounts, and Subscriptions

A common mistake when building SaaS apps is putting everything on the User model—subscription status, quotas, assets, preferences. This creates problems:

- **Family/team sharing impossible** — subscriptions are locked to one person
- **Profile switching breaks** — can't have separate preferences per context
- **Billing gets messy** — hard to transfer subscriptions or handle corporate accounts

**The better pattern:** separate authentication (User) from content ownership (Account) from billing (Subscription).

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐
│  User   │────▶│ AccountUser │◀────│   Account   │
│ (auth)  │     │   (role)    │     │  (content)  │
└─────────┘     └─────────────┘     └──────┬──────┘
                                           │
                                    ┌──────▼──────┐
                                    │Subscription │
                                    │  (billing)  │
                                    └─────────────┘
```

**User** — authentication identity only:
```python
class User(UserMixin, Model):
    email = db.Column(db.String(255), unique=True)  # OAuth identity
    stripe_customer_id = db.Column(db.String(255))  # For billing portal
    # NO subscription_status, NO quota, NO content here
```

**Account** — where content and quotas live (like Netflix profiles):
```python
class Account(Model):
    name = db.Column(db.String(100))               # "Family", "Work", etc.
    owner_user_id = db.Column(db.ForeignKey("users.id"))
    quota = db.Column(db.Integer, default=0)       # Usage limits here
    # Projects, documents, assets belong to Account, not User
```

**AccountUser** — many-to-many with roles:
```python
class AccountUser(Model):
    user_id = db.Column(db.ForeignKey("users.id"), primary_key=True)
    account_id = db.Column(db.ForeignKey("accounts.id"), primary_key=True)
    role = db.Column(db.String(20))  # "admin", "member", "child"
```

**Subscription** — billing state attached to Account:
```python
class Subscription(Model):
    account_id = db.Column(db.ForeignKey("accounts.id"))
    stripe_subscription_id = db.Column(db.String(255))
    status = db.Column(db.String(50))  # "active", "canceled", etc.
    tier_name = db.Column(db.String(50))  # "Basic", "Pro", "Enterprise"
```

**Benefits:**
- One user can access multiple accounts (personal + work)
- Multiple users can share one account (family plan)
- Subscriptions transfer cleanly when ownership changes
- Content queries are scoped to Account, not scattered across Users
- Easy to add team features later without schema changes

**When to use this pattern:** Any app with subscriptions, quotas, shared resources, or where users might want separate "workspaces" or "profiles."

### Services

Services contain business logic. Keep routes thin, services fat.

```python
# services/user_service.py
from feather import Service, transactional
from feather.exceptions import ValidationError, ConflictError
from feather.db import paginate
from models import User

class UserService(Service):
    @transactional  # Auto-commits on success, rollbacks on exception
    def create(self, email: str, username: str) -> User:
        if not email or '@' not in email:
            raise ValidationError('Valid email required', field='email')

        if User.query.filter_by(email=email).first():
            raise ConflictError('Email already registered')

        user = User(email=email, username=username)
        self.db.add(user)
        return user

    def list_paginated(self, page: int = 1, per_page: int = 20):
        query = User.query.order_by(User.created_at.desc())
        return paginate(query, page=page, per_page=per_page)
```

**Singleton services** for expensive initialization:
```python
from feather.services import singleton, Service

@singleton
class CacheService(Service):
    def __init__(self):
        super().__init__()
        self.cache = {}  # Shared across all requests
```

### Exceptions

Exception classes that automatically convert to JSON responses:

```python
from feather.exceptions import (
    ValidationError,        # 400 - Invalid input
    AuthenticationError,    # 401 - Not logged in
    AuthorizationError,     # 403 - No permission
    AccountPendingError,    # 403 - Account awaiting approval (redirects to /account/pending)
    AccountSuspendedError,  # 403 - Account suspended (redirects to /account/suspended)
    NotFoundError,          # 404 - Resource not found
    ConflictError,          # 409 - Already exists
)

# Throws:
raise ValidationError('Email is required', field='email')

# Returns:
# {"success": false, "error": {"code": "VALIDATION_ERROR", "message": "Email is required"}}
```

**Account status exceptions:** `AccountPendingError` and `AccountSuspendedError` inherit from `AuthorizationError` but trigger redirects to dedicated status pages instead of generic 403 errors. They're raised automatically by `@auth_required` based on the user's `active` and `approved_at` fields.

---

## Features

### Authentication

Feather takes a security-first approach: new users are created in **suspended state** and require admin approval before they can access the app. This prevents unauthorized access and gives you explicit control over who uses your application.

**Why suspended by default?**
- Prevents drive-by signups from consuming resources
- Gives admins visibility into who's requesting access
- Works well for internal tools, B2B apps, and invite-only products
- Aligns with zero-trust principles

**To auto-approve users**, modify the OAuth callback in `routes/pages/auth.py`:
```python
# Change this:
user = User(email=email, tenant_id=tenant.id, active=False)

# To this:
user = User(email=email, tenant_id=tenant.id, active=True)
```

Or for domain-based auto-approval (e.g., auto-approve `@yourcompany.com`):
```python
auto_approve = email.endswith('@yourcompany.com')
user = User(email=email, tenant_id=tenant.id, active=auto_approve)
```

Google OAuth with Flask-Login session management.

**Configuration:**
```bash
# .env
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret

# Session settings (optional)
SESSION_LIFETIME_DAYS=7        # Default: 7
REMEMBER_COOKIE_DAYS=365       # Default: 365
SESSION_PROTECTION=strong      # Options: None, basic, strong
```

**Setup:**
1. Create credentials at [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Add redirect URI: `http://localhost:5173/auth/google/callback` (dev) or your production URL
3. Add credentials to `.env`
4. Run `python seeds.py` to create your admin user

**Seeds** (`seeds.py`) populate initial data in your database. The scaffolded version creates your admin user with the email you provided during `feather new`. Extend it for your own initial data:

```python
# seeds.py
def seed():
    # Admin user (scaffolded)
    admin = User(email=ADMIN_EMAIL, role="admin", active=True)
    db.session.add(admin)

    # Add your seed data here
    default_categories = ["General", "Support", "Billing"]
    for name in default_categories:
        db.session.add(Category(name=name))

    db.session.commit()
```

Run seeds anytime with `python seeds.py` or `feather db seed`. The scaffolded seed is idempotent—it updates existing users rather than creating duplicates.

**Routes:**
| Route | Description |
|-------|-------------|
| `/auth/google/login` | Start OAuth flow |
| `/auth/google/callback` | OAuth callback (automatic) |
| `/auth/logout` | End session |

**Usage:**
```html
<a href="/auth/google/login">Sign in with Google</a>
<a href="/auth/logout">Sign out</a>
```

**Auth decorators:**
```python
from feather import auth_required, admin_required, role_required, login_only
from feather.auth import permission_required, platform_admin_required

@api.get('/me')
@auth_required  # Any authenticated + approved user
def get_profile():
    return {'user': current_user.to_dict()}

@page.get('/account/pending')
@login_only  # Authenticated but may be pending/suspended
def account_pending():
    return render_template('pages/account/pending.html')

@api.delete('/users/<id>')
@admin_required  # Tenant admin (role="admin")
def delete_user(id):
    pass

@api.post('/articles')
@role_required('editor')  # Specific role (admin inherits all)
def create_article():
    pass

@api.post('/tenants')
@platform_admin_required  # Cross-tenant operations
def create_tenant():
    pass
```

**Roles** — these defaults cover most apps, but you can add, remove, or rename them:

| Role | Purpose | Inherits |
|------|---------|----------|
| `user` | Basic access (default for new users) | — |
| `editor` | Content creation | `user` |
| `moderator` | Content moderation | `user` |
| `admin` | Tenant administration | all roles |

Roles inherit permissions: `@role_required('editor')` allows both editors and admins.

**To customize roles**, edit the hierarchy in `feather/auth/roles.py`:
```python
# Add a new role
ROLE_INHERITS = {
    "admin": {"admin", "editor", "moderator", "reviewer", "user"},
    "editor": {"editor", "user"},
    "moderator": {"moderator", "user"},
    "reviewer": {"reviewer", "user"},  # New role
    "user": {"user"},
}
```

Then use it in routes: `@role_required('reviewer')`. The User model's `role` field is a simple string—no migration needed when adding roles.

**Permissions** — CRUD-based access control that maps to roles:

| Permission | Who Has It | Use Case |
|------------|------------|----------|
| `resources.read` | all roles | View data |
| `resources.create` | editor, admin | Create content |
| `resources.update` | editor, admin | Edit content |
| `resources.manage` | moderator, admin | Moderation actions |
| `resources.delete` | admin only | Delete content |
| `*` | admin only | All permissions |

```python
from feather.auth import permission_required

@api.get('/articles')
@permission_required('resources.read')  # All authenticated users
def list_articles():
    pass

@api.post('/articles')
@permission_required('resources.create')  # Editors and admins
def create_article():
    pass

@api.delete('/articles/<id>')
@permission_required('resources.delete')  # Admins only
def delete_article(id):
    pass
```

**When to use which:**
- `@auth_required` — any logged-in, approved user
- `@login_only` — authenticated but may be pending/suspended (for status pages, account setup)
- `@role_required('editor')` — check by role name (with inheritance)
- `@permission_required('resources.create')` — check by action (more semantic)
- `@admin_required` — shorthand for `@role_required('admin')`

Permissions are defined in `feather/auth/permissions.py` and can be extended like roles.

#### Approval Workflow Pages

When users are pending approval or suspended, they're automatically redirected to dedicated pages instead of seeing generic error messages:

| State | Redirect | Description |
|-------|----------|-------------|
| Pending | `/account/pending` | New user awaiting admin approval |
| Suspended | `/account/suspended` | Previously approved, now deactivated |

These pages are scaffolded with friendly messages and logout buttons. They use `@login_only` so users remain authenticated while seeing their account status.

**Customizing the flow:** Edit the templates in `templates/pages/account/` to match your branding and add contact information.

#### Post-Login Callback

For B2B+B2C apps that need custom account setup logic after OAuth:

```bash
# .env
FEATHER_POST_LOGIN_CALLBACK=myapp.auth:handle_login
```

```python
# myapp/auth.py
def handle_login(user, token):
    """Called after OAuth login with user and token.

    Args:
        user: The User model instance
        token: OAuth token dict (access_token, refresh_token, etc.)

    Returns:
        Redirect URL string, or None for default behavior
    """
    if not user.account_id:
        # New user needs account setup
        return '/onboarding/select-plan'
    return None  # Default redirect to home
```

Use this for creating Account/Membership records, assigning tenants to public email users, or custom onboarding flows.

### Admin Panel

Most frameworks leave you to build your own admin interface—user management, analytics, error tracking. That's typically days of work before you ship any actual features. Feather includes a production-ready admin panel out of the box.

**What's included:**

| Feature | Description |
|---------|-------------|
| **User Management** | List, search, paginate users with HTMX-powered UI |
| **User Approval** | Approve pending signups, suspend bad actors |
| **Role Assignment** | Change user roles (user → editor → admin) |
| **Analytics Dashboard** | User growth charts with Chart.js, time range filters |
| **Error Logging** | Database-backed error logs with stack traces, tenant-scoped |
| **Tenant Management** | Create/manage tenants, assign admins (multi-tenant only) |

**Enable:**
```bash
feather new myapp
# Choose "single-tenant" or "multi-tenant" app type
```

**Access:** `/admin/` — requires `role="admin"` or `is_platform_admin=True`

**Pages:**
| Page | Route | Description |
|------|-------|-------------|
| Users | `/admin/users` | Searchable user list with pagination |
| User Detail | `/admin/users/<id>` | Profile card, role dropdown, approve/suspend buttons |
| Analytics | `/admin/analytics` | User growth chart with 7d/30d/90d/1y filters |
| Error Logs | `/admin/logs` | Filterable error list (4xx/5xx, searchable) |
| Tenants | `/admin/tenants` | Tenant list with status filters (multi-tenant only) |

**User states:**
- **Pending Approval** — new signup, never approved (`active=False`, `approved_at=None`)
- **Active** — approved and can access the app (`active=True`)
- **Suspended** — was active, now blocked (`active=False`, `approved_at` set)

#### Extending the Admin Panel

The admin is scaffolded into your app as regular routes and templates—not hidden in the framework. You own the code and can modify it freely.

**Files you can customize:**
```
routes/pages/admin.py           # Admin routes and HTMX endpoints
services/admin_service.py       # User queries, analytics data
templates/pages/admin/          # Full page templates
templates/partials/admin/       # HTMX response fragments
static/css/app.css              # Admin CSS classes (admin-header, etc.)
```

**Adding a new admin page:**

1. Add a route in `routes/pages/admin.py`:
```python
@page.get('/admin/reports')
@admin_required
def admin_reports():
    reports = ReportService().get_recent()
    return render_template('pages/admin/reports.html', reports=reports)
```

2. Create the template `templates/pages/admin/reports.html`:
```jinja2
{% extends "pages/admin/base.html" %}
{% block admin_content %}
<h1>Reports</h1>
<!-- Your content here -->
{% endblock %}
```

3. Add navigation in `templates/pages/admin/base.html`:
```jinja2
<a href="{{ url_for('page.admin_reports') }}"
   class="admin-nav-item {{ 'active' if active_page == 'reports' }}">
    Reports
</a>
```

**Adding HTMX interactions** (like the user search):
```python
@page.get('/admin/htmx/reports/filter')
@admin_required
def htmx_filter_reports():
    status = request.args.get('status')
    reports = ReportService().filter_by_status(status)
    return render_template('partials/admin/reports_table.html', reports=reports)
```

The admin uses the same three-layer architecture as the rest of your app: server-rendered templates, HTMX for interactions, and Islands only where needed (the analytics chart).

### Multi-Tenancy

Multi-tenancy is one of the hardest problems in SaaS development. You need to:
- Isolate data so Company A never sees Company B's data
- Handle authentication across organizational boundaries
- Manage two levels of admin (company admins vs. platform operators)
- Scope every database query to the current tenant
- Prevent cross-tenant access even from malicious or buggy code

Most teams spend weeks building this infrastructure. Feather provides production-ready multi-tenancy out of the box.

**Enable:**
```bash
feather new myapp
# Choose "multi-tenant" app type
```

#### How It Works

Feather uses **domain-based tenant isolation**. When a user signs in with `bob@acme.com`:

1. Feather extracts the domain (`acme.com`)
2. Looks up the tenant with that domain
3. Assigns the user to that tenant
4. All subsequent queries are scoped to that tenant

```
User signs in → Domain extracted → Tenant matched → Data scoped
bob@acme.com → acme.com → Acme Corp tenant → Only sees Acme data
```

**Public email domains:** By default, Gmail, Outlook, Yahoo, and other consumer email providers are blocked—users must sign in with their work email. For B2B+B2C apps that need to support both corporate and individual users:

```bash
# .env
FEATHER_ALLOW_PUBLIC_EMAILS=true
```

When enabled, users with public emails (Gmail, etc.) are created with `tenant_id=None`. Use the post-login callback to handle account/tenant creation for these users.

#### Two-Axis Authority Model

Feather separates **tenant authority** (what you can do within your organization) from **platform authority** (cross-organization operator power):

| Axis | Field | Scope | Example |
|------|-------|-------|---------|
| **Tenant Role** | `user.role` | Within one tenant | "admin", "editor", "user" |
| **Platform Authority** | `user.is_platform_admin` | Across all tenants | True/False |

This means:
- A **Tenant Admin** (`role="admin"`) can manage users within their organization, but can't see other tenants
- A **Platform Admin** (`is_platform_admin=True`) can create tenants, view all users, and operate across organizational boundaries

**Key design principle:** Tenant admins do NOT automatically bypass tenant isolation. An admin at Acme Corp cannot access data from Beta Inc—that requires explicit platform admin privileges.

#### Admin Levels Explained

**Tenant Admin** — manages one organization:
- Approve/suspend users in their tenant
- Change user roles within their tenant
- View error logs scoped to their tenant
- Cannot see other tenants or their data

**Platform Admin** — operates the entire platform:
- Create new tenants and assign domains
- Approve/suspend tenants
- View all users across all tenants
- Access platform-wide analytics and logs
- For security, can only be granted via CLI (not web UI)

```bash
# Grant platform admin (requires server access)
feather platform-admin admin@example.com

# Revoke platform admin
feather platform-admin admin@example.com --revoke
```

#### Admin Pages (Multi-Tenant Mode)

| Page | Route | Who Can Access | Description |
|------|-------|----------------|-------------|
| Users | `/admin/users` | Tenant Admin | Users in current tenant |
| User Detail | `/admin/users/<id>` | Tenant Admin | Approve/suspend, change roles |
| Error Logs | `/admin/logs` | Tenant Admin | Errors scoped to tenant |
| **Tenants** | `/admin/tenants` | Platform Admin only | All tenants, create new |
| **Tenant Detail** | `/admin/tenants/<id>` | Platform Admin only | Tenant info, users, approve/suspend |

#### Data Isolation

Feather enforces tenant isolation at multiple layers:

**1. Route layer** — `get_current_tenant_id()` returns the authenticated user's tenant:
```python
from feather import get_current_tenant_id

@api.get('/projects')
@auth_required
def list_projects():
    tenant_id = get_current_tenant_id()
    return Project.query.filter_by(tenant_id=tenant_id).all()
```

**2. Service layer** — `require_same_tenant()` guards against cross-tenant access:
```python
from feather.auth import require_same_tenant

def get_project_or_404(project_id):
    project = Project.query.get_or_404(project_id)
    require_same_tenant(project.tenant_id)  # Raises 403 if mismatch
    return project
```

**3. Model layer** — `TenantScopedMixin` adds tenant_id and scoped queries:
```python
from feather.db.mixins import TenantScopedMixin

class Project(UUIDMixin, TenantScopedMixin, Model):
    __tablename__ = 'projects'
    name = db.Column(db.String(100))

# Query only this tenant's projects
projects = Project.for_tenant(tenant_id).all()
```

**Hard boundary:** `require_same_tenant()` is a hard stop—even tenant admins cannot bypass it. Cross-tenant operations require platform admin routes with explicit `@platform_admin_required` decorators.

#### Tenant Model

The scaffolded Tenant model supports both B2B (domain-based) and B2C (individual) patterns:

```python
class Tenant(Model):
    slug = db.Column(db.String(64), unique=True, nullable=False)
    domain = db.Column(db.String(255), nullable=True)  # Nullable for B2C
    name = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(50), nullable=True)     # "company", "individual", etc.
    status = db.Column(db.String(20), default="pending")
```

- **B2B tenants:** Set `domain` to auto-assign users by email (e.g., `@acme.com` → Acme tenant)
- **B2C tenants:** Leave `domain` as `None`, create individually via post-login callback
- **type field:** Classify tenants for billing, features, or reporting

#### Tenant Lifecycle

1. **Platform admin creates tenant** via `/admin/tenants`:
   - Sets tenant name, slug, and optionally email domain
   - Creates initial tenant admin (auto-approved)
   - Tenant starts in pending state

2. **Platform admin approves tenant** — tenant becomes active

3. **Users sign up** with matching email domain:
   - Auto-assigned to tenant
   - Created in suspended state (pending approval)

4. **Tenant admin approves users** via `/admin/users`

This flow ensures both platform-level and tenant-level approval gates.

### Background Jobs

Many web apps need to do work outside the request cycle - sending emails, processing uploads, calling external APIs. Feather provides three job backends, each designed for different goals:

#### Choosing the Right Backend

The choice isn't about "development vs production" - all three work in production. It's about what you're trying to achieve:

| Goal | Backend | Trade-off |
|------|---------|-----------|
| **Simplicity** - No infrastructure, no complexity | `sync` | Blocks the request |
| **Speed** - Return fast, process later | `thread` | Jobs lost on restart |
| **Reliability** - Never lose a job, even if server crashes | `rq` | Requires Redis + workers |

**Sync** is for when blocking the request is acceptable. You might use this for:
- Simple apps where job execution is fast enough
- Debugging job logic (errors appear in the request)
- Apps where infrastructure simplicity matters more than response time

**Thread** is for when you need fast responses without infrastructure. Jobs run in a thread pool managed by Python. You'd choose this when:
- You want sub-second response times
- You don't want to run Redis
- Jobs are "fire and forget" (losing some on crash is acceptable)
- You need concurrency control for memory-intensive tasks (ML, transcription)

**RQ** is for when reliability is critical. Jobs are persisted to Redis before acknowledgement. Choose this when:
- Losing a job would cause real problems (payments, notifications)
- You need job visibility (retry failed jobs, see job history)
- You're running multiple servers (distributed workers)
- You need scheduled/recurring tasks

#### Configuration

```bash
# .env

# Sync - blocks request, no background processing
JOB_BACKEND=sync

# Thread (default) - background threads, no infrastructure
JOB_BACKEND=thread
JOB_MAX_WORKERS=4              # Thread pool size
# JOB_ENABLE_MONITORING=true   # Enable psutil resource tracking

# RQ - Redis workers with persistence
JOB_BACKEND=rq
REDIS_URL=redis://localhost:6379/0
```

**Important for development:** When using the `thread` backend, set `FLASK_DEBUG=0` in your `.env` file. Flask's auto-reloader restarts the process on every file change, which kills any running background threads. Your jobs will be terminated mid-execution whenever you save a file.

**Define a job:**
```python
from feather import job

@job
def send_welcome_email(user_id, email):
    # Runs in background thread
    send_email(email, 'Welcome!', render_template('emails/welcome.html'))
```

**Enqueue:**
```python
@api.post('/users')
@inject(UserService)
def create_user(user_service, email: str):
    user = user_service.create(email=email)
    send_welcome_email.enqueue(user.id, user.email)  # Returns immediately
    return {'user': user.to_dict()}, 201

# With delay (seconds)
send_welcome_email.enqueue(user.id, user.email, delay=60)  # Run in 60 seconds
```

#### Concurrency Control

Limit concurrent executions to prevent resource exhaustion - essential for memory-intensive tasks like ML inference:

```python
@job(concurrency=2)  # Max 2 concurrent executions
def transcribe_audio(file_path):
    """Whisper transcription - memory intensive."""
    result = whisper.transcribe(file_path)
    return result['text']

@job(concurrency=1)  # Singleton - only 1 at a time
def rebuild_search_index():
    """Expensive operation - run exclusively."""
    pass
```

**How it works:**
- Jobs wait in a queue when the concurrency limit is reached
- First-in-first-out (FIFO) ordering within each task type
- Different tasks have independent limits

**Use cases:**
- Audio/video transcription (Whisper) - high memory footprint
- ML model inference - GPU/memory constrained
- External API calls - rate limited by provider
- Database-heavy operations - connection pool limits

#### Retry Logic

Automatically retry failed jobs with exponential backoff:

```python
@job(retry=3)  # Retry up to 3 times
def call_external_api(data):
    # Backoff: 2s, 4s, 8s between retries
    response = requests.post('https://api.example.com', json=data)
    response.raise_for_status()

@job(concurrency=2, retry=2)  # Combined with concurrency
def transcribe_with_retry(video_id):
    # Max 2 concurrent, retry twice on failure
    pass
```

#### Resource Monitoring

Enable psutil to capture memory/CPU metrics on job failures:

```bash
# .env
JOB_ENABLE_MONITORING=true
```

```bash
pip install psutil  # Optional dependency
```

When a job fails, error logs include:
```
Memory Mb: 256.5
Memory Percent: 3.2%
Cpu Percent: 45.0%
Thread Count: 8
```

#### Scheduled Tasks

For recurring jobs on a schedule (cron-style or interval-based), use the RQ backend with rq-scheduler:

```python
from feather import scheduled

@scheduled(cron='0 9 * * *')  # Every day at 9 AM
def daily_digest():
    send_daily_digest_emails()

@scheduled(interval=3600)  # Every hour
def cleanup_temp_files():
    delete_old_temp_files()
```

#### RQ Worker Setup

When using the RQ backend for persistent job queues:

```bash
# Install RQ
pip install rq

# Start a worker (in a separate terminal or process)
rq worker --url redis://localhost:6379/0

# For scheduled jobs
pip install rq-scheduler
rqscheduler --url redis://localhost:6379/0
```

### Caching

Response and function caching with automatic invalidation.

**Configuration:**
```bash
# .env
CACHE_BACKEND=memory   # In-memory (single process, resets on restart)
# or
CACHE_BACKEND=redis    # Redis (shared across processes, persistent)
CACHE_URL=redis://localhost:6379/0
CACHE_DEFAULT_TTL=300  # Default TTL in seconds
```

**Cache function results:**
```python
from feather import cached

@cached(ttl=60)  # Cache for 60 seconds
def get_user_stats(user_id):
    # Expensive database query
    return calculate_stats(user_id)

# Results are cached by function arguments
stats = get_user_stats(123)  # First call: executes function
stats = get_user_stats(123)  # Second call: returns cached result

# Invalidate when data changes
get_user_stats.invalidate(user_id=123)
```

**Cache route responses:**
```python
from feather import cache_response

@api.get('/products')
@cache_response(ttl=300)  # Cache for 5 minutes
def list_products():
    return {'products': Product.query.all()}

# Custom cache key using URL params
@api.get('/users/<user_id>')
@cache_response(ttl=60, key='user:{user_id}')
def get_user(user_id):
    return {'user': User.query.get(user_id)}

# Skip cache conditionally
@api.get('/dashboard')
@cache_response(ttl=300, unless=lambda: current_user.is_admin)
def dashboard():
    return {'stats': get_stats()}
```

**Direct cache access:**
```python
from feather import get_cache

cache = get_cache()
cache.set('key', {'data': 'value'}, ttl=60)
value = cache.get('key')  # Returns None if expired/missing
cache.delete('key')
```

### File Storage

Unified file handling with local filesystem or Google Cloud Storage.

**Configuration:**
```bash
# .env
STORAGE_BACKEND=local   # Saves to ./uploads/ directory

# or Google Cloud Storage
STORAGE_BACKEND=gcs
GCS_BUCKET=my-bucket

# GCS credentials (choose one):
# Option 1: Inline JSON (recommended for deployment - single line)
GCS_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"..."}

# Option 2: File path (local development)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Option 3: Default credentials (GCE/GKE or gcloud auth application-default login)
# No extra config needed
```

**Usage:**
```python
from feather.storage import get_storage

storage = get_storage()

# Upload a file
url = storage.upload(file, 'uploads/photo.jpg', content_type='image/jpeg')

# Download file contents
data = storage.download('uploads/photo.jpg')

# Get URL (local returns path, GCS returns signed URL)
url = storage.get_url('uploads/photo.jpg', expires_in=3600)  # 1 hour expiry

# Check existence and delete
if storage.exists('uploads/photo.jpg'):
    storage.delete('uploads/photo.jpg')
```

**In a route:**
```python
from flask import request
from feather.storage import get_storage

@api.post('/upload')
@auth_required
def upload_file():
    file = request.files['image']
    storage = get_storage()
    url = storage.upload(file, f'uploads/{current_user.id}/{file.filename}')
    return {'url': url}
```

### Email

Transactional email using Resend. Available for authenticated apps (single-tenant or multi-tenant).

**Configuration:**
```bash
# .env
RESEND_API_KEY=re_xxxx                    # Get from https://resend.com/api-keys
RESEND_FROM_EMAIL=noreply@yourdomain.com  # Must be verified in Resend
```

**Usage:**
```python
from services.email_service import EmailService

email_service = EmailService()

# Send plain text email
result = email_service.send(
    to="user@example.com",
    subject="Welcome!",
    body="Thanks for signing up."
)

# Send HTML email
result = email_service.send(
    to="user@example.com",
    subject="Your Report",
    body="<h1>Monthly Report</h1><p>...</p>",
    html=True
)

# Return response with toast notification
response = make_response(render_template("partials/email_sent.html"))
if result["success"]:
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": result["message"], "type": "success"}})
else:
    response.headers["HX-Trigger"] = json.dumps({"showToast": {"message": result["error"], "type": "error"}})
```

**Admin Tools:** When email is enabled, the admin panel includes a "Send Email" form at `/admin/tools` with user search dropdown.

### Events

Pub/sub pattern for decoupling application components.

**Define an event:**
```python
from feather.events import Event

class UserCreatedEvent(Event):
    def __init__(self, user_id: str, email: str):
        super().__init__(user_id=user_id)
        self.email = email
```

**Listen for events:**
```python
from feather.events import listen

# Synchronous listener (runs in request thread)
@listen(UserCreatedEvent)
def send_welcome_email(event):
    send_email(event.email, 'Welcome!')

# Async listener (runs in background thread pool)
@listen(UserCreatedEvent, async_=True)
def track_signup_analytics(event):
    # Doesn't block the response
    analytics.track('signup', user_id=event.user_id)
```

**Dispatch events:**
```python
from feather.events import dispatch

@transactional
def create_user(self, email: str):
    user = User(email=email)
    self.db.add(user)
    # Dispatch after the transaction commits
    dispatch(UserCreatedEvent(user_id=user.id, email=user.email))
    return user
```

Async listeners run in a ThreadPoolExecutor (4 workers). Use for non-critical tasks like analytics, logging, or notifications.

### PDF Generation

Generate PDF documents with reportlab (included in Feather):

**Basic usage:**
```python
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table
from reportlab.lib.styles import getSampleStyleSheet

def generate_report(data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    elements = [
        Paragraph("Report Title", styles['Heading1']),
        Table(data),
    ]

    doc.build(elements)
    buffer.seek(0)
    return buffer
```

**With file storage:**
```python
from feather.storage import get_storage

@api.get('/reports/<id>/pdf')
@auth_required
def download_report(id):
    pdf_buffer = generate_report(get_data(id))

    # Save to storage
    storage = get_storage()
    filename = f'reports/{id}.pdf'
    storage.upload(pdf_buffer, filename, content_type='application/pdf')

    # Return download URL
    url = storage.get_url(filename, expires_in=3600)
    return {'url': url}
```

**With background jobs:**
```python
from feather import job

@job
def generate_report_async(report_id, user_id):
    pdf_buffer = generate_report(get_data(report_id))
    storage = get_storage()
    filename = f'reports/{user_id}/{report_id}.pdf'
    storage.upload(pdf_buffer, filename, content_type='application/pdf')
    return {'filename': filename}

# Enqueue and poll for completion
result = generate_report_async.enqueue(report_id, user_id)
```

### Rate Limiting

Protect routes from abuse with configurable limits.

**Usage:**
```python
from feather.auth import rate_limit

# 5 login attempts per minute per IP
@api.post('/login')
@rate_limit(5, 60)
def login():
    pass

# 100 API calls per minute per authenticated user
@api.get('/search')
@rate_limit(100, 60, key='user')
def search():
    pass

# Strict: limit by both IP and user
@api.post('/expensive')
@rate_limit(10, 3600, key='ip+user')
def expensive_operation():
    pass

# Custom error message
@api.post('/comments')
@rate_limit(10, 3600, message='You can only post 10 comments per hour')
def create_comment():
    pass
```

**Options:**
| Parameter | Description | Default |
|-----------|-------------|---------|
| `limit` | Max requests in period | required |
| `period` | Time window (seconds) | 60 |
| `key` | Rate limit by `'ip'`, `'user'`, or `'ip+user'` | `'ip'` |
| `message` | Custom error message | "Rate limit exceeded" |

**Note:** Uses in-memory tracking. For multi-process deployments (Gunicorn workers), use Redis-based rate limiting.

### Serializers

Convert model objects to JSON with automatic snake_case to camelCase conversion.

**Basic usage:**
```python
from feather.serializers import Serializer

class UserSerializer(Serializer):
    fields = ['id', 'email', 'created_at']

# Serialize
user = User.query.first()
data = UserSerializer().serialize(user)
# {'id': '...', 'email': '...', 'createdAt': '2024-01-15T10:30:00Z'}

# Serialize multiple
users = User.query.all()
data = UserSerializer().serialize_many(users)
```

**Field types:**
```python
from feather.serializers import (
    Serializer, StringField, IntegerField, FloatField,
    BooleanField, DateTimeField, MethodField, NestedField
)

class UserSerializer(Serializer):
    fields = ['id', 'email', 'status', 'balance', 'created_at', 'full_name', 'posts']

    status = StringField()                          # Coerce to string
    balance = FloatField()                          # Coerce to float
    created_at = DateTimeField(format='%Y-%m-%d')   # Custom date format
    full_name = MethodField()                       # Computed field
    posts = NestedField(PostSerializer, many=True)  # Nested objects

    def get_full_name(self, obj, context=None):
        return f"{obj.first_name} {obj.last_name}"
```

**Available field types:**
| Field | Description |
|-------|-------------|
| `StringField()` | Coerce to string |
| `IntegerField()` | Coerce to integer |
| `FloatField()` | Coerce to float |
| `BooleanField()` | Coerce to boolean |
| `DateTimeField(format=None)` | Format datetime (default: ISO 8601) |
| `NestedField(serializer, many=False)` | Nested object/collection |
| `MethodField()` | Computed via `get_<field_name>()` method |

### Request Tracking

Unique request IDs and structured logging for debugging and observability.

**Configuration:**
```bash
# .env
LOG_LEVEL=INFO        # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT=json       # Enable JSON logging (auto-enabled when FLASK_ENV=production)
```

**Usage:**
```python
from feather import get_request_id

@api.get('/users')
def list_users():
    # Trace requests across services
    app.logger.info(f"Listing users [{get_request_id()}]")
    return {'users': [...]}
```

**How it works:**
- Unique ID per request (UUID)
- Uses incoming `X-Request-ID` header if present (for distributed tracing)
- Added to response headers automatically
- Available via `get_request_id()` or `g.request_id`

**JSON log format:**
```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "level": "INFO",
  "message": "Listing users",
  "request_id": "abc-123-def",
  "logger": "myapp.routes"
}
```

### Health Checks

Health endpoints for load balancer routing, Kubernetes probes, and monitoring systems.

Feather provides three endpoints out of the box:

| Endpoint | Purpose | What It Checks |
|----------|---------|----------------|
| `/health` | Full health check | Database connectivity, app running |
| `/health/live` | Liveness probe | App process is alive (always 200 if responding) |
| `/health/ready` | Readiness probe | App can serve traffic (database connected) |

**Liveness vs Readiness:**
- **Liveness** answers "is the process alive?" — if this fails, the container should be restarted
- **Readiness** answers "can it handle requests?" — if this fails, stop sending traffic but don't restart

Example: your app is running but the database is down. Liveness passes (process is alive), readiness fails (can't serve requests). The load balancer stops routing to this instance while it recovers.

**Response format:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "checks": {
    "database": "ok"
  }
}
```

Returns `200 OK` when healthy, `503 Service Unavailable` when unhealthy.

**Load balancer configuration (AWS ALB, GCP, etc.):**
- Health check path: `/health`
- Healthy threshold: 2
- Unhealthy threshold: 3
- Interval: 30 seconds

**Kubernetes:**
```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

**Render, Railway, Fly.io:** These platforms auto-detect `/health` endpoints. No configuration needed—just deploy and they'll use it.

### Error Logging

Automatic error capture with tenant scoping for multi-tenant apps.

**How it works:**
- Errors are automatically logged to the database with stack traces
- Each error is associated with the current user and tenant
- Tenant admins see only their tenant's errors
- Platform admins see all errors

**View errors:** Navigate to `/admin/logs` in the admin panel.

**ErrorLog model:**
```python
class ErrorLog(Model):
    error_type    # NotFoundError, ValidationError, etc.
    message       # Error message
    path          # Request path
    method        # HTTP method
    user_id       # User who triggered it (if authenticated)
    tenant_id     # Tenant scope
    stack_trace   # Full traceback (for 500 errors)
    created_at    # When it occurred
```

---

## Testing

Feather scaffolds a working test setup so you can start testing immediately. No configuration needed—just write tests and run them.

### What's Included

When you run `feather new myapp`, you get:

```
tests/
├── conftest.py          # Fixtures: client, csrf_client, db setup
├── test_health.py       # Health endpoint tests (working example)
└── test_auth.py         # Auth flow tests (if auth enabled)
```

These aren't placeholder files—they're real tests that pass out of the box. Use them as patterns for your own tests.

### Running Tests

```bash
feather test                       # Run all tests
feather test -v                    # Verbose output
feather test -p tests/test_api.py  # Specific file
feather test -- -k "test_user"     # Filter by test name
feather test --no-coverage         # Skip coverage report
```

### Fixtures

The scaffolded `conftest.py` provides two test clients:

| Fixture | Use For | CSRF Handling |
|---------|---------|---------------|
| `client` | GET requests, public endpoints | Not needed |
| `csrf_client` | POST/PUT/DELETE requests | Automatic |

```python
def test_public_page(client):
    """GET requests use the basic client."""
    response = client.get('/health')
    assert response.status_code == 200

def test_create_item(csrf_client):
    """POST/PUT/DELETE use csrf_client - CSRF token is automatic."""
    response = csrf_client.post('/api/items', json={'name': 'Test'})
    assert response.status_code == 201
```

**Why two clients?** Feather enables CSRF protection by default. The `csrf_client` fixture automatically fetches and includes the CSRF token, so your tests don't need to handle it manually.

### Testing Patterns

**Route tests** — test HTTP behavior:
```python
def test_list_items_requires_auth(client):
    response = client.get('/api/items')
    assert response.status_code == 401

def test_list_items_when_authenticated(csrf_client, authenticated_user):
    response = csrf_client.get('/api/items')
    assert response.status_code == 200
    assert 'items' in response.json
```

**Service tests** — test business logic directly:
```python
from services import ItemService
from feather.exceptions import ValidationError
import pytest

def test_create_item_validates_name(app):
    with app.app_context():
        service = ItemService()
        with pytest.raises(ValidationError):
            service.create(name='')  # Empty name should fail

def test_create_item_success(app):
    with app.app_context():
        service = ItemService()
        item = service.create(name='Valid Name')
        assert item.id is not None
```

**Model tests** — test data layer:
```python
def test_item_defaults(app):
    with app.app_context():
        item = Item(name='Test')
        db.session.add(item)
        db.session.commit()

        assert item.id is not None
        assert item.created_at is not None
```

### Adding Test Fixtures

Extend `conftest.py` for common test data:

```python
# tests/conftest.py
import pytest
from models import User, Item

@pytest.fixture
def authenticated_user(app):
    """Create and login a test user."""
    with app.app_context():
        user = User(email='test@example.com', active=True)
        db.session.add(user)
        db.session.commit()

        with app.test_client() as client:
            # Simulate login (adjust based on your auth setup)
            with client.session_transaction() as sess:
                sess['_user_id'] = user.id
            yield client

@pytest.fixture
def sample_items(app):
    """Create sample items for testing."""
    with app.app_context():
        items = [Item(name=f'Item {i}') for i in range(3)]
        db.session.add_all(items)
        db.session.commit()
        return items
```

### Test Database

Tests run against a separate test database (automatically configured). Each test gets a fresh database state:

1. **Before each test:** Tables are created
2. **After each test:** Transaction is rolled back (fast cleanup)

This means tests are isolated—one test can't affect another.

### Framework Tests (Contributors)

If you're contributing to Feather itself (not building an app), run the framework test suite:

```bash
feather test --framework           # Full suite
feather test -f --fast             # Skip slow tests
feather test -f -m unit            # Run by marker
feather test -f --clean            # Remove test artifacts
```

**Markers:**
| Marker | What It Tests |
|--------|---------------|
| `unit` | Pure functions, no I/O |
| `integration` | Database, services |
| `e2e` | Full request/response cycles |
| `scaffolding` | `feather new` output |
| `jobs` | Background job system |
| `api_contract` | API response formats |

Most app developers won't need these—they're for testing the framework code in `feather/`.

---

## Reference

### CLI Reference

```bash
# Project Commands
feather new <name>              # Create project (interactive)
feather new <name> --no-prompt  # Use minimal defaults
feather dev                     # Dev server with Vite HMR (port 5173)
feather dev --no-vite           # Flask only (port 5000)
feather build                   # Build assets for production
feather start                   # Start production server (Gunicorn)
feather start --workers 8       # Multiple workers
feather start --worker-class gevent  # Async workers

# Development Commands
feather routes                  # List all registered routes
feather shell                   # Python shell with app context

# Testing (App)
feather test                    # Run project tests
feather test -v                 # Verbose output
feather test --no-coverage      # Skip coverage report
feather test -p tests/test_api.py  # Test specific file
feather test -- -k "test_user"  # Pass args to pytest

# Testing (Framework Contributors)
feather test --framework        # Run all framework tests
feather test -f -m unit         # Run by marker
feather test -f --fast          # Skip slow tests
feather test -f --list-markers  # Show available markers
feather test -f --clean         # Clean test artifacts

# Database Commands
feather db init                 # Initialize migrations directory
feather db migrate -m "msg"     # Generate migration from model changes
feather db upgrade              # Apply pending migrations
feather db downgrade            # Revert last migration
feather db seed                 # Run seeds.py

# Code Generation
feather generate model Post title:string content:text
feather generate model Post --soft-delete   # Add SoftDeleteMixin
feather generate model Card --ordered       # Add OrderingMixin
feather generate service PostService
feather generate island like-button
feather generate route users --model User   # API CRUD routes
feather generate route dashboard --page     # Page route with template
feather generate serializer UserSerializer id email

# Job Queue Management (thread backend)
feather jobs status             # Show queue status and counts
feather jobs list               # List all jobs
feather jobs list --status failed    # Filter by status
feather jobs list --stuck       # Show jobs running too long
feather jobs info <job_id>      # Show job details
feather jobs failed             # List failed/timed-out jobs
feather jobs retry <job_id>     # Re-queue a failed job
feather jobs clear              # Clear job history

# Administration (multi-tenant)
feather platform-admin <email>          # Grant platform admin
feather platform-admin <email> --revoke # Revoke platform admin
```

### Configuration

The scaffolded `config.py` includes sensible defaults:

```python
# config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/myapp')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session cookies (for OAuth)
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False   # Allow HTTP
    SESSION_PROTECTION = "basic"    # Relaxed for Vite proxy

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True    # HTTPS only
    SESSION_PROTECTION = "strong"   # Strict session protection
```

Environment variables (`.env`):

```bash
# Required
SECRET_KEY=your-production-secret-key
DATABASE_URL=postgresql://user:pass@localhost/myapp

# Authentication
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
SESSION_LIFETIME_DAYS=7           # Session expiry (default: 7)

# Multi-tenancy
FEATHER_MULTI_TENANT=true              # Enable multi-tenant mode
FEATHER_ALLOW_PUBLIC_EMAILS=true       # Allow Gmail, Outlook, etc. (B2B+B2C)
FEATHER_POST_LOGIN_CALLBACK=myapp.auth:handle_login  # Custom post-OAuth logic

# Storage
STORAGE_BACKEND=local             # 'local' or 'gcs'
GCS_BUCKET=my-bucket              # Required for gcs backend

# Caching
CACHE_BACKEND=memory              # 'memory' or 'redis'
CACHE_URL=redis://localhost:6379/0

# Background Jobs
JOB_BACKEND=thread                # 'sync', 'thread', or 'rq'
JOB_MAX_WORKERS=4                 # Thread pool size (thread backend)
REDIS_URL=redis://localhost:6379/0  # Required for rq backend

# Logging
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json                   # Enable JSON logs (auto in production)
```

---

## Production

### Dependencies

Feather bundles all dependencies (Flask, SQLAlchemy, Alembic, Authlib, psycopg2, Gunicorn, etc.) - scaffolded apps don't need their own `requirements.txt`.

```bash
# For deployment, just install Feather
pip install feather-framework
```

### DEBUG Mode Behavior

Understanding DEBUG mode is crucial for production:

| Setting | Asset Loading | Description |
|---------|--------------|-------------|
| `DEBUG=True` | Vite dev server (`localhost:5173`) | Hot reload, no build needed |
| `DEBUG=False` | Built assets from `static/dist/` | Requires `feather build` first |

**Common issue:** Unstyled pages in production happen when:
1. `DEBUG=False` but `feather build` wasn't run
2. The `static/dist/` directory is missing or outdated

**Solution:** Always run `feather build` before deploying.

### Configuration Shorthand

You can use shorthand config names with `FLASK_CONFIG`:

```bash
# These are equivalent:
FLASK_CONFIG=production
FLASK_CONFIG=ProductionConfig
FLASK_CONFIG=prod
```

Supported shorthands: `development`/`dev`, `production`/`prod`, `testing`/`test`

### Deploying to Render

Render is a popular platform for deploying web applications. Feather includes a CLI command to generate all the files you need.

#### Step 1: Generate Deployment Files

```bash
feather deploy render
```

This creates three files:

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build with Python 3.11, Node.js 22 (for Vite 7), and system deps |
| `render.yaml` | Blueprint defining your web service and PostgreSQL database |
| `.dockerignore` | Excludes venv, node_modules, .env, tests from the build |

**Options:**
```bash
feather deploy render --name myapp      # Custom app name (default: directory name)
feather deploy render --region frankfurt # Deploy to Frankfurt (default: oregon)
```

Available regions: `oregon`, `ohio`, `virginia`, `frankfurt`, `singapore`

#### Step 2: Review Generated Files

The generated `render.yaml` creates:
- A **web service** running your Feather app with Gunicorn
- A **PostgreSQL database** (basic-256mb plan)
- Auto-generated `SECRET_KEY` for session security
- `DATABASE_URL` automatically linked to the database

```yaml
# render.yaml (generated)
services:
  - type: web
    name: myapp
    runtime: docker
    healthCheckPath: /api/health
    envVars:
      - key: FLASK_CONFIG
        value: production
      - key: SECRET_KEY
        generateValue: true
      - key: DATABASE_URL
        fromDatabase:
          name: myapp-db
          property: connectionString
```

#### Step 3: Upload Environment Variables

**Important:** The generated blueprint only includes Render-managed variables. You must upload your production `.env` file manually for:

- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (for OAuth)
- `RESEND_API_KEY` (for email)
- `GCS_BUCKET` and `GCS_CREDENTIALS_JSON` (for file storage)
- Any other app-specific secrets

**To upload your .env:**
1. Go to your service in the Render dashboard
2. Click **Environment** in the left sidebar
3. Click **Add from .env file**
4. Upload your production `.env` (not your development one!)

**Tip:** Create a separate `.env.production` file with production values:
```bash
# .env.production (example)
GOOGLE_CLIENT_ID=your-prod-client-id
GOOGLE_CLIENT_SECRET=your-prod-secret
RESEND_API_KEY=re_xxxx
RESEND_FROM_EMAIL=noreply@yourdomain.com
```

#### Step 4: Update Google OAuth Redirect URI

Before deploying, add your Render URL to Google Cloud Console:

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Edit your OAuth client
3. Add authorized redirect URI: `https://myapp.onrender.com/auth/google/callback`

#### Step 5: Deploy

**Option A: Connect via GitHub (recommended)**
1. Push your code to GitHub (including the generated files)
2. Go to [Render Dashboard](https://dashboard.render.com/)
3. Click **New** → **Blueprint**
4. Connect your GitHub repo
5. Render auto-detects `render.yaml` and deploys

**Option B: Use Render CLI**
```bash
# Install Render CLI
brew install render-cli  # macOS
# or
pip install render-cli

# Deploy the blueprint
render blueprint apply
```

#### Step 6: Run Database Migrations

The Dockerfile automatically runs `feather db upgrade` on startup. For the first deploy, you may need to manually run seeds:

```bash
# SSH into your Render service or use the shell
python seeds.py
```

Or the Dockerfile handles this too—it runs `seeds.py` if the file exists.

#### Tips and Gotchas

**1. Health check timing**
Render waits for `/api/health` to return 200 before routing traffic. If your app takes time to start (database migrations, large models), increase the health check grace period in the dashboard.

**2. Database connections**
The free PostgreSQL plan has connection limits. If you see "too many connections" errors, reduce Gunicorn workers or add connection pooling.

**3. Automatic deploys**
By default, Render auto-deploys when you push to your main branch. Disable this in settings if you prefer manual deploys.

**4. Logs**
View logs in the Render dashboard or CLI:
```bash
render logs --service myapp
```

**5. Custom domains**
Add your domain in the Render dashboard → Settings → Custom Domains. Render handles SSL certificates automatically.

**6. Cost optimization**
- Start with the free tier for testing
- Upgrade to Starter ($7/mo) for production (faster deploys, more resources)
- The database free tier expires after 90 days—upgrade before that

### Health Check Endpoint

Feather provides `/api/health` (or `/health`) for deployment platforms:

```bash
curl https://myapp.onrender.com/api/health
# {"status": "healthy", "timestamp": "...", "checks": {"database": "ok"}}
```

Use this as your health check path in Render, Fly.io, AWS, etc.

### Deployment

These are starter templates to get you running quickly. Every production environment is different—you'll need to adjust these based on your infrastructure, scaling requirements, and security policies.

**What stays the same:**
- `feather build` compiles Tailwind CSS and bundles JavaScript
- `gunicorn app:app` runs the production server
- Environment variables configure the app (SECRET_KEY, DATABASE_URL, etc.)

**What you'll customize:**
- Worker count and type based on your traffic patterns
- Database connection pooling for your expected load
- Health check endpoints for your orchestration platform
- SSL/TLS termination (usually handled by your load balancer)
- Logging and monitoring integration

#### Render

```yaml
# render.yaml
services:
  - type: web
    name: myapp
    env: python
    buildCommand: pip install feather-framework && npm install && feather build
    startCommand: gunicorn app:app
    envVars:
      - key: SECRET_KEY
        generateValue: true
      - key: DATABASE_URL
        fromDatabase:
          name: myapp-db
          property: connectionString

databases:
  - name: myapp-db
    plan: free  # Upgrade for production
```

#### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Feather (includes all Python deps)
RUN pip install feather-framework

# Install Node deps for Tailwind/Vite
COPY package.json package-lock.json ./
RUN npm install

COPY . .
RUN feather build

ENV FLASK_DEBUG=0
EXPOSE 8000

# Adjust workers based on container resources
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "app:app"]
```

#### Fly.io

```toml
# fly.toml
app = "myapp"
primary_region = "ord"

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  FLASK_DEBUG = "0"

[http_service]
  internal_port = 8000
  force_https = true

[[services.http_checks]]
  path = "/health"
  interval = "30s"
  timeout = "5s"
```

#### Production Checklist

Before going live:

- [ ] Set a strong `SECRET_KEY` (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] Use a managed database (not SQLite)
- [ ] Enable HTTPS (most platforms handle this automatically)
- [ ] Configure health checks for your load balancer
- [ ] Set up log aggregation (the app outputs JSON logs in production)
- [ ] Test the `/health` endpoint returns 200
- [ ] Review environment variables for sensitive data

---

## Troubleshooting

**Tail logs in a second terminal:** `tail -f logs/app.log` — shows detailed Flask output.

**Flask won't start:** Run `python app.py` directly to see the full traceback.

**Port in use:**
```bash
lsof -ti:5000 | xargs kill -9  # Flask
lsof -ti:5173 | xargs kill -9  # Vite
```

---

## Tutorials

Step-by-step guides for building complete applications with Feather. Each tutorial builds on the previous one, covering every major feature.

**[Kanban Tutorial Series](tutorials/index.md)** - Build a production-ready Kanban board:

| Part | Title | Features Covered |
|------|-------|------------------|
| 1 | [Static Board UI](tutorials/01-static-board-ui.md) | Templates, Components, Tailwind |
| 2 | [Persistent Boards](tutorials/02-persistent-boards.md) | Models, HTMX, Partials |
| 3 | [Drag-and-Drop](tutorials/03-drag-and-drop.md) | Islands, OrderingMixin, Optimistic Updates |
| 4 | [Personal Kanban](tutorials/04-personal-kanban.md) | Auth, Admin, GCS Storage, Jobs |
| 5 | [SaaS Kanban](tutorials/05-saas-kanban.md) | Multi-tenancy, Platform Admin |

---

## License

MIT
