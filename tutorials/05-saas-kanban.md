# Tutorial 5: SaaS Kanban

## Kanban Tutorial Series

> This is part 5 of a 5-part series building a production Kanban app.
> [View series overview](index.md)

| Part | Title | Status |
|------|-------|--------|
| 1 | Static Board UI | Complete |
| 2 | Persistent Boards | Complete |
| 3 | Drag-and-Drop | Complete |
| 4 | Personal Kanban | Complete |
| 5 | SaaS Kanban | **You are here** |

## This Tutorial

**What you'll build:** A multi-tenant SaaS Kanban app where each organization has isolated data, with multiple boards per tenant.

**Features covered:**
- Multi-tenant architecture with domain-based isolation
- Multiple Kanban boards per tenant (dashboard home page)
- Tenant model and automatic tenant assignment
- Platform admin for managing all tenants
- Tenant admin for managing organization users
- Tenant-scoped queries and data isolation
- Multi-file attachments with GCS

## Prerequisites

**Required:**
- PostgreSQL running locally
- Google OAuth credentials
- GCS bucket configured

> **Note:** Background jobs run in a thread pool by default (no Redis needed). For production with job persistence, configure `JOB_BACKEND=rq` and run Redis.

**Fresh start required** - This tutorial uses multi-tenant configuration.

```bash
feather new kanban-saas
```

You'll see interactive prompts:

```
Project Configuration

App Type
  Simple       - Static pages, no authentication
  Single-Tenant  - Authentication with role-based access
  Multi-Tenant   - Separate tenant accounts with isolation
  Select type [simple]:
```

Choose `multi-tenant`.

```
Database
  Type [none]:
```

Choose `postgresql`.

```
Database name [kanban_saas]:
```

Press Enter to accept `kanban_saas`.

```
Include cloud storage (GCS)? [y/N]:
```

Type `y` for GCS support.

```
Platform admin email:
```

Enter your company email (e.g., admin@yourcompany.com).

Then:
```bash
cd kanban-saas
source venv/bin/activate

feather db migrate -m "Initial migration"
feather db upgrade
python seeds.py
```

---

## Starting Point

> **For LLMs:** This section describes the current app state before this tutorial.

### What Multi-Tenant Scaffolding Includes

The multi-tenant scaffold adds:

```
kanban-saas/
├── models/
│   ├── user.py          # Has tenant_id and is_platform_admin
│   ├── tenant.py        # Tenant model
│   └── log.py           # Tenant-scoped errors
├── seeds.py             # Creates platform admin with tenant
└── config.py            # FEATHER_MULTI_TENANT = True
```

### Key Differences from Single-Tenant

| Aspect | Single-Tenant | Multi-Tenant |
|--------|---------------|--------------|
| User model | No `tenant_id` | Has `tenant_id` FK |
| Platform admin | No concept | `is_platform_admin` field |
| Tenant model | Doesn't exist | Full tenant management |
| Data isolation | User-scoped | Tenant-scoped |
| Admin panel | User management | + Tenant management |

### From Tutorial 4

We need the Kanban, Column, Card models and services from Tutorial 4, but modified for tenant-scoping instead of just user-scoping:

- **Kanban model** - Uses `TenantScopedMixin` instead of `user_id`
- **Column model** - Same as Tutorial 4 (scoped to kanban_id)
- **Card model** - Same as Tutorial 4
- **Attachment model** - New: separate model for multi-file support

---

## Build Steps

### Step 1: Create Tenant-Scoped Models

Create `models/kanban.py`:

```python
"""Kanban board model - tenant scoped."""

from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin, TenantScopedMixin


class Kanban(UUIDMixin, TimestampMixin, TenantScopedMixin, Model):
    """Kanban board owned by a tenant."""

    __tablename__ = "kanbans"

    title = db.Column(db.String(100), nullable=False, default="My Board")

    columns = db.relationship(
        "Column",
        backref="kanban",
        cascade="all, delete-orphan",
        order_by="Column.position"
    )

    def __repr__(self):
        return f"<Kanban {self.title}>"
```

Create `models/column.py`:

```python
"""Column model for Kanban board."""

from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin, OrderingMixin


class Column(UUIDMixin, TimestampMixin, OrderingMixin, Model):
    """Kanban column with position-based ordering."""

    __tablename__ = "columns"
    __ordering_scope__ = ["kanban_id"]  # Position scoped per board

    title = db.Column(db.String(100), nullable=False)
    kanban_id = db.Column(
        db.String(36),
        db.ForeignKey("kanbans.id"),
        nullable=False,
        index=True
    )

    cards = db.relationship(
        "Card",
        backref="column",
        cascade="all, delete-orphan",
        order_by="Card.position"
    )

    def __repr__(self):
        return f"<Column {self.title}>"
```

Create `models/card.py`:

```python
"""Card model for Kanban board."""

from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin, OrderingMixin


class Card(UUIDMixin, TimestampMixin, OrderingMixin, Model):
    """Kanban card."""

    __tablename__ = "cards"
    __ordering_scope__ = ["column_id"]

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    column_id = db.Column(
        db.String(36),
        db.ForeignKey("columns.id"),
        nullable=False
    )

    attachments = db.relationship(
        "Attachment",
        backref="card",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Card {self.title}>"
```

Create `models/attachment.py`:

```python
"""Attachment model for card files."""

from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin


class Attachment(UUIDMixin, TimestampMixin, Model):
    """File attachment on a card."""

    __tablename__ = "attachments"

    filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100))
    size = db.Column(db.Integer)
    storage_path = db.Column(db.String(500), nullable=False)
    card_id = db.Column(
        db.String(36),
        db.ForeignKey("cards.id"),
        nullable=False
    )

    def __repr__(self):
        return f"<Attachment {self.filename}>"
```

Update `models/__init__.py`:

```python
"""SQLAlchemy models - Auto-discovered by Feather."""

from feather.db import db, Model

# Import order matters for migrations - dependencies first
from models.tenant import Tenant
from models.user import User
from models.log import Log
from models.account import Account
from models.account_user import AccountUser
from models.kanban import Kanban
from models.column import Column
from models.card import Card
from models.attachment import Attachment
```

**Key change:** `TenantScopedMixin` on Kanban adds `tenant_id` field and `for_tenant()` query method. Columns and Cards get tenant isolation via their relationship to Kanban.

### Step 2: Run Migration

```bash
feather db migrate -m "Add kanbans, columns, cards, and attachments"
feather db upgrade
```

### Step 3: Create Tenant-Scoped Services

Create `services/kanban_service.py`:

```python
"""KanbanService - Tenant-scoped board operations."""

from feather import Service, get_current_tenant_id
from feather.exceptions import NotFoundError
from feather.auth import require_same_tenant
from models import Kanban


class KanbanService(Service):
    """Kanban board service - tenant-scoped operations."""

    def list_for_tenant(self) -> list[Kanban]:
        """List all boards for current tenant, newest first."""
        tenant_id = get_current_tenant_id()
        return Kanban.for_tenant(tenant_id).order_by(
            Kanban.created_at.desc()
        ).all()

    def get_by_id(self, id: str) -> Kanban:
        """Get board by ID, enforcing tenant isolation."""
        kanban = Kanban.query.get(id)
        if not kanban:
            raise NotFoundError("Kanban", id)
        require_same_tenant(kanban.tenant_id)
        return kanban

    def create(self, title: str = "My Board") -> Kanban:
        """Create a new board for current tenant."""
        tenant_id = get_current_tenant_id()
        kanban = Kanban(tenant_id=tenant_id, title=title)
        self.save(kanban)
        return kanban

    def delete(self, id: str) -> None:
        """Delete a board (must belong to current tenant)."""
        kanban = self.get_by_id(id)
        self.db.delete(kanban)
        self.db.commit()
```

Create `services/column_service.py`:

```python
"""ColumnService - Column operations with tenant isolation via kanban."""

from feather import Service
from feather.exceptions import NotFoundError
from feather.auth import require_same_tenant
from models import Column, Kanban


class ColumnService(Service):
    """Column service - operations scoped via kanban's tenant."""

    def list_for_kanban(self, kanban_id: str) -> list[Column]:
        """List all columns for a kanban board in order."""
        kanban = Kanban.query.get(kanban_id)
        if not kanban:
            raise NotFoundError("Kanban", kanban_id)
        require_same_tenant(kanban.tenant_id)
        return Column.query_ordered(kanban_id=kanban_id).all()

    def get_by_id(self, id: str) -> Column:
        """Get column by ID, enforcing tenant isolation via kanban."""
        column = Column.query.get(id)
        if not column:
            raise NotFoundError("Column", id)
        require_same_tenant(column.kanban.tenant_id)
        return column

    def create(self, kanban_id: str, title: str) -> Column:
        """Create a new column in a board."""
        kanban = Kanban.query.get(kanban_id)
        if not kanban:
            raise NotFoundError("Kanban", kanban_id)
        require_same_tenant(kanban.tenant_id)

        column = Column(kanban_id=kanban_id, title=title)
        column.insert_at_end()
        self.save(column)
        return column

    def delete(self, id: str) -> None:
        """Delete a column (must belong to current tenant's board)."""
        column = self.get_by_id(id)
        kanban_id = column.kanban_id
        self.db.delete(column)
        self.db.commit()
        Column.reorder_all(kanban_id=kanban_id)
        self.db.commit()
```

Create `services/card_service.py`:

```python
"""CardService - Card operations with tenant isolation."""

from feather import Service
from feather.exceptions import NotFoundError
from feather.auth import require_same_tenant
from models import Card, Column


class CardService(Service):
    """Card service with tenant isolation via columns and kanbans."""

    def get_by_id(self, id: str) -> Card:
        """Get card by ID, enforcing tenant isolation via kanban."""
        card = Card.query.get(id)
        if not card:
            raise NotFoundError("Card", id)
        require_same_tenant(card.column.kanban.tenant_id)
        return card

    def create(self, column_id: str, title: str) -> Card:
        """Create a card in a column (must be in current tenant)."""
        column = Column.query.get(column_id)
        if not column:
            raise NotFoundError("Column", column_id)
        require_same_tenant(column.kanban.tenant_id)

        card = Card(column_id=column_id, title=title)
        card.insert_at_end()
        self.save(card)
        return card

    def delete(self, id: str) -> None:
        """Delete a card (must belong to current tenant)."""
        card = self.get_by_id(id)
        column_id = card.column_id
        self.db.delete(card)
        self.db.commit()
        Card.reorder_all(column_id=column_id)
        self.db.commit()

    def move(self, card_id: str, to_column_id: str, to_position: int) -> Card:
        """Move a card to a new position."""
        card = self.get_by_id(card_id)

        # Verify target column is in same tenant
        to_column = Column.query.get(to_column_id)
        if not to_column:
            raise NotFoundError("Column", to_column_id)
        require_same_tenant(to_column.kanban.tenant_id)

        old_column_id = card.column_id

        if to_column_id != old_column_id:
            card.column_id = to_column_id
            max_pos = Card.get_max_position(column_id=to_column_id)
            card.position = max_pos + 1
            self.db.commit()
            Card.reorder_all(column_id=old_column_id)
            self.db.commit()

        card.move_to(to_position)
        self.db.commit()
        return card
```

Create `services/attachment_service.py`:

```python
"""AttachmentService - File upload handling with tenant isolation."""

from feather import Service, get_current_tenant_id
from feather.exceptions import NotFoundError, ValidationError
from feather.auth import require_same_tenant
from feather.storage import get_storage
from models import Attachment, Card
import uuid


class AttachmentService(Service):
    """Attachment service with GCS storage and tenant isolation."""

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_TYPES = {
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "application/pdf",
        "text/plain", "text/csv",
    }

    def upload(self, card_id: str, file) -> Attachment:
        """Upload a file attachment to a card."""
        card = Card.query.get(card_id)
        if not card:
            raise NotFoundError("Card", card_id)
        require_same_tenant(card.column.kanban.tenant_id)

        if not file or not file.filename:
            raise ValidationError("No file provided")

        content_type = file.content_type
        if content_type not in self.ALLOWED_TYPES:
            raise ValidationError(f"File type {content_type} not allowed")

        file_data = file.read()
        if len(file_data) > self.MAX_FILE_SIZE:
            raise ValidationError("File too large (max 10MB)")

        # Include tenant_id in storage path for isolation
        tenant_id = get_current_tenant_id()
        storage = get_storage()
        storage_path = f"tenants/{tenant_id}/attachments/{card_id}/{uuid.uuid4()}/{file.filename}"
        storage.upload(file_data, storage_path, content_type=content_type)

        attachment = Attachment(
            card_id=card_id,
            filename=file.filename,
            content_type=content_type,
            size=len(file_data),
            storage_path=storage_path
        )
        self.save(attachment)
        return attachment

    def get_url(self, attachment_id: str) -> str:
        """Get a signed URL for downloading an attachment."""
        attachment = Attachment.query.get(attachment_id)
        if not attachment:
            raise NotFoundError("Attachment", attachment_id)
        require_same_tenant(attachment.card.column.kanban.tenant_id)

        storage = get_storage()
        return storage.get_url(attachment.storage_path, expires_in=3600)

    def delete(self, attachment_id: str) -> None:
        """Delete an attachment."""
        attachment = Attachment.query.get(attachment_id)
        if not attachment:
            raise NotFoundError("Attachment", attachment_id)
        require_same_tenant(attachment.card.column.kanban.tenant_id)

        storage = get_storage()
        storage.delete(attachment.storage_path)

        self.db.delete(attachment)
        self.db.commit()
```

Update `services/__init__.py`:

```python
"""Business logic services - Auto-discovered by Feather."""

from services.kanban_service import KanbanService
from services.column_service import ColumnService
from services.card_service import CardService
from services.attachment_service import AttachmentService
```

**Key patterns:**
- `get_current_tenant_id()` - Gets tenant ID from current user
- `require_same_tenant(resource.tenant_id)` - Raises AuthorizationError if mismatch
- Tenant isolation flows: Kanban → Column → Card → Attachment
- Storage paths include tenant ID for GCS isolation

### Step 4: Create Routes

First, delete the scaffolded home page since our dashboard will replace it:

```bash
rm routes/pages/home.py
rm templates/pages/home.html
```

Create `routes/pages/dashboard.py`:

```python
"""Dashboard routes - shows all boards for current tenant."""

from flask import render_template, request, redirect, url_for
from flask_login import current_user
from feather import page, auth_required
from feather.services import inject
from services import KanbanService


@page.get("/")
@inject(KanbanService)
def home(kanban_service: KanbanService):
    """Render the tenant's dashboard with all boards.

    Note: Function must be named 'home' because Feather's OAuth callback
    redirects to 'page.home' after successful login.
    """
    # Show login page for unauthenticated users
    if not current_user.is_authenticated:
        return render_template("pages/login.html")

    # Redirect suspended users to pending page
    if not current_user.is_active:
        return redirect(url_for("page.pending"))

    kanbans = kanban_service.list_for_tenant()
    return render_template("pages/dashboard.html", kanbans=kanbans)


@page.post("/htmx/kanbans")
@auth_required
@inject(KanbanService)
def create_kanban(kanban_service: KanbanService):
    """Create a new board."""
    title = request.form.get("title", "").strip() or "My Board"
    kanban = kanban_service.create(title=title)
    return render_template("partials/kanban_card.html", kanban=kanban)


@page.delete("/htmx/kanbans/<kanban_id>")
@auth_required
@inject(KanbanService)
def delete_kanban(kanban_service: KanbanService, kanban_id: str):
    """Delete a board."""
    kanban_service.delete(kanban_id)
    return ""
```

Create `routes/pages/board.py`:

```python
"""Kanban board routes - tenant scoped."""

from flask import render_template, request
from feather import page, auth_required
from feather.services import inject
from services import KanbanService, ColumnService, CardService


@page.get("/kanban/<kanban_id>")
@auth_required
@inject(KanbanService, ColumnService)
def board(kanban_service: KanbanService, column_service: ColumnService, kanban_id: str):
    """Render a specific Kanban board."""
    kanban = kanban_service.get_by_id(kanban_id)
    columns = column_service.list_for_kanban(kanban_id)
    return render_template("pages/board.html", kanban=kanban, columns=columns)


@page.post("/htmx/kanbans/<kanban_id>/columns")
@auth_required
@inject(ColumnService)
def create_column(column_service: ColumnService, kanban_id: str):
    """Create a new column."""
    title = request.form.get("title", "").strip() or "New Column"
    column = column_service.create(kanban_id=kanban_id, title=title)
    return render_template("partials/column.html", column=column)


@page.delete("/htmx/columns/<column_id>")
@auth_required
@inject(ColumnService)
def delete_column(column_service: ColumnService, column_id: str):
    """Delete a column."""
    column_service.delete(column_id)
    return ""


@page.post("/htmx/columns/<column_id>/cards")
@auth_required
@inject(CardService)
def create_card(card_service: CardService, column_id: str):
    """Create a new card."""
    title = request.form.get("title", "").strip()
    if not title:
        return "", 400
    card = card_service.create(column_id=column_id, title=title)
    return render_template("partials/card.html", card=card)


@page.delete("/htmx/cards/<card_id>")
@auth_required
@inject(CardService)
def delete_card(card_service: CardService, card_id: str):
    """Delete a card."""
    card_service.delete(card_id)
    return ""
```

Create `routes/api/board.py`:

```python
"""API routes for Kanban board - tenant scoped."""

from flask import request
from feather import api, auth_required
from feather.services import inject
from services import CardService, AttachmentService


@api.post("/cards/move")
@auth_required
@inject(CardService)
def move_card(card_service: CardService):
    """Move a card to a new position."""
    data = request.get_json()
    card = card_service.move(
        card_id=data["cardId"],
        to_column_id=data["toColumnId"],
        to_position=data["toPosition"]
    )
    return {"success": True, "card": {"id": card.id, "position": card.position}}


@api.post("/cards/<card_id>/attachments")
@auth_required
@inject(AttachmentService)
def upload_attachment(attachment_service: AttachmentService, card_id: str):
    """Upload a file attachment."""
    file = request.files.get("file")
    attachment = attachment_service.upload(card_id=card_id, file=file)
    return {
        "success": True,
        "attachment": {
            "id": attachment.id,
            "filename": attachment.filename,
            "size": attachment.size
        }
    }


@api.get("/attachments/<attachment_id>/url")
@auth_required
@inject(AttachmentService)
def get_attachment_url(attachment_service: AttachmentService, attachment_id: str):
    """Get a signed download URL."""
    url = attachment_service.get_url(attachment_id)
    return {"url": url}


@api.delete("/attachments/<attachment_id>")
@auth_required
@inject(AttachmentService)
def delete_attachment(attachment_service: AttachmentService, attachment_id: str):
    """Delete an attachment."""
    attachment_service.delete(attachment_id)
    return {"success": True}
```

**Note:** Routes no longer pass `user_id` - tenant context is automatic!

### Step 5: Create Templates

Create `templates/pages/dashboard.html`:

```html
{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}{{ current_user.tenant.name }} - Dashboard{% endblock %}

{% block content %}
<div class="dashboard-container">
    <header class="dashboard-header">
        <div class="dashboard-header-left">
            <h1 class="dashboard-title">
                {{ icon("dashboard", size="lg") }}
                {{ current_user.tenant.name }}
            </h1>
        </div>
        <div class="dashboard-header-right">
            <button id="new-board-btn" class="btn-primary">
                {{ icon("add", size="sm") }} New Board
            </button>
            <div class="user-menu" data-island="user-menu">
                <button class="user-menu-trigger">
                    <img src="{{ current_user.profile_image_url or '/feather-static/favicon.svg' }}"
                         alt="{{ current_user.display_name }}"
                         class="user-avatar"
                         referrerpolicy="no-referrer">
                </button>
                <div class="user-menu-flyout hidden">
                    <div class="user-menu-header">
                        <span class="user-name">{{ current_user.display_name }}</span>
                        <span class="user-email">{{ current_user.email }}</span>
                        <span class="user-role">{{ current_user.role }}</span>
                    </div>
                    <hr class="user-menu-divider">
                    {% if current_user.is_admin %}
                    <a href="/admin/" class="user-menu-item">
                        {{ icon("admin_panel_settings", size="sm") }} Admin
                    </a>
                    {% endif %}
                    {% if current_user.is_platform_admin %}
                    <a href="/admin/tenants" class="user-menu-item">
                        {{ icon("domain", size="sm") }} Tenants
                    </a>
                    {% endif %}
                    {% if current_user.is_admin or current_user.is_platform_admin %}
                    <hr class="user-menu-divider">
                    {% endif %}
                    <a href="/auth/logout" class="user-menu-item">
                        {{ icon("logout", size="sm") }} Sign out
                    </a>
                </div>
            </div>
        </div>
    </header>

    <div id="kanban-grid" class="kanban-grid">
        {% for kanban in kanbans %}
            {% include "partials/kanban_card.html" %}
        {% else %}
            <div class="empty-state" id="empty-state">
                <span class="material-symbols-outlined text-6xl text-gray-300 mb-4">view_kanban</span>
                <p class="text-gray-500 mb-4">No boards yet</p>
                <button id="empty-state-btn" class="btn-primary">
                    {{ icon("add", size="sm") }} Create your first board
                </button>
            </div>
        {% endfor %}
    </div>
</div>
{% endblock %}

{% block scripts %}
{% if config.DEBUG %}
<script type="module" src="http://localhost:5173/static/js/dashboard.js"></script>
{% else %}
<script src="{{ url_for('static', filename='js/dashboard.js') }}"></script>
{% endif %}
{% endblock %}

{% block islands %}
{% if config.DEBUG %}
<script type="module" src="http://localhost:5173/static/islands/user-menu.js"></script>
{% else %}
<script src="{{ feather_asset('islands/user-menu') }}"></script>
{% endif %}
{% endblock %}
```

Create `templates/pages/login.html`:

```html
{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}Sign In{% endblock %}

{% block content %}
<div class="login-container">
    <div class="login-card">
        <div class="login-logo">
            <img src="/feather-static/favicon.svg" alt="Logo" class="login-logo-img">
        </div>
        <h1 class="login-title">Welcome</h1>
        <p class="login-subtitle">Sign in to access your boards</p>
        <a href="{{ url_for('google_auth.login') }}" class="btn-google">
            {{ icon("login", size="sm") }} Sign in with Google
        </a>
    </div>
</div>
{% endblock %}
```

Create `templates/partials/kanban_card.html`:

```html
<div class="kanban-card-item" id="kanban-{{ kanban.id }}">
    <a href="{{ url_for('page.board', kanban_id=kanban.id) }}" class="kanban-card-link">
        <div class="kanban-card-icon">
            <span class="material-symbols-outlined">view_kanban</span>
        </div>
        <div class="kanban-card-content">
            <h3 class="kanban-card-title">{{ kanban.title }}</h3>
            <p class="kanban-card-meta">
                {{ kanban.columns|length }} column{{ 's' if kanban.columns|length != 1 else '' }}
                &middot;
                Updated {{ (kanban.updated_at or kanban.created_at).strftime('%b %d') }}
            </p>
        </div>
    </a>
    <button class="kanban-card-delete btn-icon-subtle"
            hx-delete="/htmx/kanbans/{{ kanban.id }}"
            hx-target="#kanban-{{ kanban.id }}"
            hx-swap="outerHTML"
            hx-confirm="Delete this board? This cannot be undone.">
        <span class="material-symbols-outlined">delete</span>
    </button>
</div>
```

Create `templates/pages/board.html`:

```html
{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}{{ kanban.title }} - {{ current_user.tenant.name }}{% endblock %}

{% block content %}
<div class="kanban-container">
    <header class="kanban-header">
        <div class="kanban-header-left">
            <a href="{{ url_for('page.home') }}" class="back-link">
                {{ icon("arrow_back", size="sm") }}
            </a>
            <h1 class="kanban-title">
                {{ icon("view_kanban", size="lg") }}
                {{ kanban.title }}
            </h1>
        </div>
        <div class="kanban-header-right">
            <button id="add-column-btn" class="btn-primary" data-kanban-id="{{ kanban.id }}">
                {{ icon("add", size="sm") }} Add Column
            </button>
            <div class="user-menu" data-island="user-menu">
                <button class="user-menu-trigger">
                    <img src="{{ current_user.profile_image_url or '/feather-static/favicon.svg' }}"
                         alt="{{ current_user.display_name }}"
                         class="user-avatar"
                         referrerpolicy="no-referrer">
                </button>
                <div class="user-menu-flyout hidden">
                    <div class="user-menu-header">
                        <span class="user-name">{{ current_user.display_name }}</span>
                        <span class="user-email">{{ current_user.email }}</span>
                        <span class="user-role">{{ current_user.role }}</span>
                    </div>
                    <hr class="user-menu-divider">
                    {% if current_user.is_admin %}
                    <a href="/admin/" class="user-menu-item">
                        {{ icon("admin_panel_settings", size="sm") }} Admin
                    </a>
                    {% endif %}
                    {% if current_user.is_platform_admin %}
                    <a href="/admin/tenants" class="user-menu-item">
                        {{ icon("domain", size="sm") }} Tenants
                    </a>
                    {% endif %}
                    {% if current_user.is_admin or current_user.is_platform_admin %}
                    <hr class="user-menu-divider">
                    {% endif %}
                    <a href="/auth/logout" class="user-menu-item">
                        {{ icon("logout", size="sm") }} Sign out
                    </a>
                </div>
            </div>
        </div>
    </header>

    <div data-island="kanban-board" class="kanban-board-wrapper">
        <div id="kanban-board" class="kanban-board">
            {% for column in columns %}
                {% include "partials/column.html" %}
            {% else %}
                <div class="empty-board" id="empty-board">
                    <p>No columns yet. Click "Add Column" to get started!</p>
                </div>
            {% endfor %}
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
{% if config.DEBUG %}
<script type="module" src="http://localhost:5173/static/js/board.js"></script>
{% else %}
<script src="{{ url_for('static', filename='js/board.js') }}"></script>
{% endif %}
{% endblock %}

{% block islands %}
{% if config.DEBUG %}
<script type="module" src="http://localhost:5173/static/islands/kanban-board.js"></script>
<script type="module" src="http://localhost:5173/static/islands/user-menu.js"></script>
{% else %}
<script src="{{ feather_asset('islands/kanban-board') }}"></script>
<script src="{{ feather_asset('islands/user-menu') }}"></script>
{% endif %}
{% endblock %}
```

Create `templates/partials/column.html`:

```html
<div class="kanban-column" data-column-id="{{ column.id }}">
    <div class="column-header">
        <h3 class="column-title">{{ column.title }}</h3>
        <button class="btn-icon-danger"
                hx-delete="/htmx/columns/{{ column.id }}"
                hx-target="closest .kanban-column"
                hx-swap="outerHTML"
                hx-confirm="Delete this column and all its cards?">
            <span class="material-symbols-outlined text-sm">delete</span>
        </button>
    </div>

    <div class="column-cards" data-column-id="{{ column.id }}">
        {% for card in column.cards %}
            {% include "partials/card.html" %}
        {% endfor %}
        <p class="empty-column">No cards yet</p>
    </div>

    <div class="column-footer">
        <form hx-post="/htmx/columns/{{ column.id }}/cards"
              hx-target="previous .column-cards"
              hx-swap="beforeend"
              hx-on::after-request="this.reset()">
            <input type="text"
                   name="title"
                   placeholder="Add a card..."
                   class="input-card-title"
                   required>
        </form>
    </div>
</div>
```

Create `templates/partials/card.html`:

```html
<div class="kanban-card" data-card-id="{{ card.id }}">
    <div class="card-content">
        <span class="drag-handle material-symbols-outlined">drag_indicator</span>
        <div class="card-body">
            <p class="card-title">{{ card.title }}</p>
            {% if card.attachments %}
            <div class="card-attachments">
                <span class="material-symbols-outlined text-xs">attach_file</span>
                {{ card.attachments|length }}
            </div>
            {% endif %}
        </div>
        <button class="btn-icon-subtle"
                hx-delete="/htmx/cards/{{ card.id }}"
                hx-target="closest .kanban-card"
                hx-swap="outerHTML"
                hx-confirm="Delete this card?">
            <span class="material-symbols-outlined text-sm">close</span>
        </button>
    </div>
</div>
```

### Step 6: Create JavaScript

Create `static/js/dashboard.js`:

```javascript
/**
 * Dashboard page JavaScript
 * Handles the "New Board" button interaction
 */
document.addEventListener('DOMContentLoaded', () => {
    const newBoardBtn = document.getElementById('new-board-btn');
    const emptyStateBtn = document.getElementById('empty-state-btn');
    const kanbanGrid = document.getElementById('kanban-grid');

    function showNewBoardPrompt() {
        window.showPrompt({
            title: 'New Board',
            message: 'Enter a name for your board:',
            placeholder: 'Board name',
            defaultValue: 'My Board',
            confirmText: 'Create',
            onConfirm: (value) => {
                htmx.ajax('POST', '/htmx/kanbans', {
                    target: kanbanGrid,
                    swap: 'afterbegin',
                    values: { title: value }
                }).then(() => {
                    // Remove empty state if it exists
                    document.getElementById('empty-state')?.remove();
                });
            }
        });
    }

    // Both buttons trigger the same prompt
    if (newBoardBtn) {
        newBoardBtn.addEventListener('click', showNewBoardPrompt);
    }
    if (emptyStateBtn) {
        emptyStateBtn.addEventListener('click', showNewBoardPrompt);
    }
});
```

Create `static/js/board.js`:

```javascript
/**
 * Board page JavaScript
 * Handles the "Add Column" button interaction
 */
document.addEventListener('DOMContentLoaded', () => {
    const addColumnBtn = document.getElementById('add-column-btn');
    const kanbanBoard = document.getElementById('kanban-board');

    if (addColumnBtn) {
        const kanbanId = addColumnBtn.dataset.kanbanId;

        addColumnBtn.addEventListener('click', () => {
            window.showPrompt({
                title: 'Add Column',
                message: 'Enter the name for the new column:',
                placeholder: 'Column name',
                confirmText: 'Create',
                onConfirm: (value) => {
                    htmx.ajax('POST', `/htmx/kanbans/${kanbanId}/columns`, {
                        target: kanbanBoard,
                        swap: 'beforeend',
                        values: { title: value }
                    }).then(() => {
                        document.getElementById('empty-board')?.remove();
                    });
                }
            });
        });
    }
});
```

Create `static/islands/user-menu.js`:

```javascript
/**
 * User Menu Island
 * Handles the flyout menu for user profile
 */
class UserMenu {
    constructor(element) {
        this.element = element;
        this.trigger = element.querySelector('.user-menu-trigger');
        this.flyout = element.querySelector('.user-menu-flyout');

        if (this.trigger && this.flyout) {
            this.init();
        }
    }

    init() {
        // Toggle on click
        this.trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });

        // Close on click outside
        document.addEventListener('click', (e) => {
            if (!this.element.contains(e.target)) {
                this.close();
            }
        });

        // Close on ESC
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.close();
            }
        });
    }

    toggle() {
        this.flyout.classList.toggle('hidden');
    }

    close() {
        this.flyout.classList.add('hidden');
    }
}

// Initialize all user menus
document.querySelectorAll('[data-island="user-menu"]').forEach(el => {
    new UserMenu(el);
});

// Re-initialize after HTMX swaps
document.addEventListener('htmx:afterSwap', () => {
    document.querySelectorAll('[data-island="user-menu"]').forEach(el => {
        if (!el._userMenu) {
            el._userMenu = new UserMenu(el);
        }
    });
});
```

Create `static/islands/kanban-board.js`:

```javascript
/**
 * Kanban Board Island
 * Handles drag-and-drop functionality using Feather's island() helper
 */
island("kanban-board", {
  draggable: {
    items: ".kanban-card",
    zones: ".column-cards",
    handle: ".drag-handle",

    onDrop(item, zone, info, e) {
      // Optimistically keep the visual state, then sync with server
      this.optimistic(
        () => {}, // Visual update already done by drag-drop
        () => this.api.post("/api/cards/move", {
          cardId: info.itemId,
          toColumnId: info.toZoneId,
          toPosition: info.toIndex
        })
      ).catch(err => {
        console.error("Failed to move card:", err);
        // Reload to restore correct positions on error
        window.location.reload();
      });
    }
  }
});
```

### Step 7: Add CSS

Add to `static/css/app.css`:

```css
@layer components {
    /* ========================================
       Dashboard Layout
       ======================================== */
    .dashboard-container {
        @apply min-h-screen bg-gray-100 p-6;
    }

    .dashboard-header {
        @apply mb-6 flex items-center justify-between;
    }

    .dashboard-header-left {
        @apply flex items-center gap-4;
    }

    .dashboard-header-right {
        @apply flex items-center gap-3;
    }

    .dashboard-title {
        @apply text-2xl font-bold text-gray-900 flex items-center gap-2;
    }

    /* Board Grid */
    .kanban-grid {
        @apply grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4;
    }

    .kanban-card-item {
        @apply bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow relative;
    }

    .kanban-card-link {
        @apply flex items-start gap-4 p-4;
    }

    .kanban-card-icon {
        @apply w-12 h-12 bg-indigo-100 rounded-lg flex items-center justify-center flex-shrink-0;
    }

    .kanban-card-icon .material-symbols-outlined {
        @apply text-indigo-600 text-2xl;
    }

    .kanban-card-content {
        @apply flex-1 min-w-0;
    }

    .kanban-card-title {
        @apply font-semibold text-gray-900 truncate;
    }

    .kanban-card-meta {
        @apply text-sm text-gray-500 mt-1;
    }

    .kanban-card-delete {
        @apply absolute top-2 right-2 p-1 rounded hover:bg-red-50;
    }

    /* Empty State */
    .empty-state {
        @apply col-span-full flex flex-col items-center justify-center py-16 text-center;
    }

    /* ========================================
       Kanban Board Layout
       ======================================== */
    .kanban-container {
        @apply min-h-screen bg-gray-100 p-6;
    }

    .kanban-header {
        @apply mb-6 flex items-center justify-between;
    }

    .kanban-header-left {
        @apply flex items-center gap-4;
    }

    .kanban-header-right {
        @apply flex items-center gap-3;
    }

    .kanban-title {
        @apply text-2xl font-bold text-gray-900 flex items-center gap-2;
    }

    .back-link {
        @apply w-8 h-8 flex items-center justify-center rounded-lg
               text-gray-500 hover:text-gray-900 hover:bg-gray-200 transition-colors;
    }

    .kanban-board-wrapper {
        @apply overflow-x-auto;
    }

    .kanban-board {
        @apply flex gap-4 pb-4;
        min-height: 500px;
    }

    .empty-board {
        @apply flex items-center justify-center w-full text-gray-500;
    }

    /* ========================================
       Columns
       ======================================== */
    .kanban-column {
        @apply flex-shrink-0 w-72 bg-gray-200 rounded-lg p-3 flex flex-col;
    }

    .column-header {
        @apply flex items-center justify-between mb-3;
    }

    .column-title {
        @apply font-semibold text-gray-700;
    }

    .column-cards {
        @apply space-y-2 min-h-[100px] flex-1;
    }

    .column-footer {
        @apply mt-3 pt-3 border-t border-gray-300;
    }

    .empty-column {
        @apply text-sm text-gray-400 text-center py-4;
    }

    /* Hide "No cards yet" when cards exist */
    .column-cards:has(.kanban-card) .empty-column {
        @apply hidden;
    }

    /* ========================================
       Cards
       ======================================== */
    .kanban-card {
        @apply bg-white rounded-lg shadow-sm p-3 hover:shadow-md transition-shadow;
    }

    .card-content {
        @apply flex items-start gap-2;
    }

    .card-body {
        @apply flex-1 min-w-0;
    }

    .card-title {
        @apply text-sm text-gray-800;
    }

    .card-attachments {
        @apply flex items-center gap-1 text-xs text-gray-400 mt-1;
    }

    /* ========================================
       Drag and Drop
       ======================================== */
    .drag-handle {
        @apply text-gray-300 hover:text-gray-500 cursor-grab;
    }

    .kanban-card.dragging {
        @apply opacity-50 shadow-lg;
    }

    .column-cards.drag-over {
        @apply bg-gray-300 ring-1 ring-indigo-400 ring-inset;
    }

    .feather-drop-placeholder {
        @apply h-0.5 bg-indigo-400 rounded my-1;
    }

    /* ========================================
       Buttons
       ======================================== */
    .btn-primary {
        @apply inline-flex items-center gap-2 px-4 py-2
               bg-indigo-600 text-white rounded-lg
               hover:bg-indigo-700 transition-colors;
    }

    .btn-secondary {
        @apply inline-flex items-center gap-2 px-4 py-2
               bg-white text-gray-700 border border-gray-300 rounded-lg
               hover:bg-gray-50 transition-colors;
    }

    .btn-text {
        @apply text-sm text-gray-500 hover:text-gray-700;
    }

    .btn-icon-danger {
        @apply text-gray-400 hover:text-red-600 transition-colors;
    }

    .btn-icon-subtle {
        @apply text-gray-300 hover:text-red-600 transition-colors opacity-0;
    }

    /* Show delete button on hover */
    .kanban-card:hover .btn-icon-subtle,
    .kanban-card-item:hover .btn-icon-subtle {
        @apply opacity-100;
    }

    .input-card-title {
        @apply w-full px-3 py-2 text-sm bg-white border border-gray-300 rounded-lg
               focus:ring-2 focus:ring-indigo-500 focus:border-transparent;
    }

    /* ========================================
       User Menu
       ======================================== */
    .user-menu {
        @apply relative;
    }

    .user-menu-trigger {
        @apply flex items-center gap-2 p-1 rounded-full hover:bg-gray-200 transition-colors;
    }

    .user-avatar {
        @apply w-8 h-8 rounded-full;
    }

    .user-menu-flyout {
        @apply absolute right-0 top-full mt-2 w-64 bg-white rounded-lg shadow-lg
               border border-gray-200 py-2 z-50;
    }

    .user-menu-flyout.hidden {
        @apply hidden;
    }

    .user-menu-header {
        @apply px-4 py-2 flex flex-col;
    }

    .user-name {
        @apply font-semibold text-gray-900;
    }

    .user-email {
        @apply text-sm text-gray-500 truncate;
    }

    .user-role {
        @apply text-xs text-gray-400 capitalize mt-1;
    }

    .user-menu-divider {
        @apply my-2 border-gray-200;
    }

    .user-menu-item {
        @apply flex items-center gap-2 px-4 py-2 text-sm text-gray-700
               hover:bg-gray-100 transition-colors;
    }

    /* ========================================
       Login Page
       ======================================== */
    .login-container {
        @apply min-h-screen bg-gray-100 flex items-center justify-center p-6;
    }

    .login-card {
        @apply bg-white rounded-xl shadow-lg p-8 w-full max-w-sm text-center;
    }

    .login-logo {
        @apply mb-6;
    }

    .login-logo-img {
        @apply w-16 h-16 mx-auto;
    }

    .login-title {
        @apply text-2xl font-bold text-gray-900 mb-2;
    }

    .login-subtitle {
        @apply text-gray-500 mb-6;
    }

    .btn-google {
        @apply inline-flex items-center justify-center gap-2 w-full px-4 py-3
               bg-indigo-600 text-white rounded-lg font-medium
               hover:bg-indigo-700 transition-colors;
    }
}
```

### Step 8: Test Multi-Tenancy

Start the app:
```bash
feather dev
```

**Test as Platform Admin:**

1. Open http://localhost:5173
2. Sign in with your platform admin email
3. You'll see an empty dashboard (no boards yet)
4. Create a board using "New Board" button
5. Click the board to open it
6. Add columns and cards
7. Go to Admin → Tenants to manage tenants

**Test Tenant Isolation:**

1. Create a new tenant in Admin → Tenants:
   - Name: "Acme Corp"
   - Slug: "acme"
   - Domain: "acme.com"
   - Set to Active
2. In a private browser, sign in as a user from acme.com domain
3. They'll see a "Pending Approval" page (new users require approval)
4. **Promote to tenant admin:** As platform admin, go to Admin → Tenants → Acme Corp → Users
   - Find the user and set their role to "admin"
   - Click "Activate" to approve them
5. Now this user is the **tenant admin** for Acme Corp
6. The user can refresh and see their empty dashboard
7. Create boards - they're completely isolated from other tenants

**Test user approval as tenant admin:**

8. In another private browser, sign in as a second acme.com user
9. They'll see "Pending Approval" page
10. As the Acme tenant admin (first user), go to Admin → Users
11. Find the pending user and click "Activate"
12. The second user can now access the dashboard

> **Key point:** Platform admins create tenants and can do initial setup,
> but ongoing user approval is the responsibility of each tenant's admin.

**Admin Panel:**

| User Type | Can Access |
|-----------|------------|
| Tenant User | Own boards only |
| Tenant Admin | Admin → Users (approve/suspend users in own tenant) |
| Platform Admin | Admin → Tenants (create tenants, NOT approve users) |

> **Important:** Platform admins manage tenants, not users. Each tenant's
> admin is responsible for approving new users who sign up with that
> tenant's domain.

## Checkpoint

Your app should now have:
- Multi-tenant architecture with multiple boards per tenant
- Dashboard showing all boards
- Domain-based user assignment
- Tenant-isolated data
- Platform admin for tenant management
- Tenant admin for user management within tenant

**Files you created/modified:**
```
models/
├── __init__.py             # Updated exports
├── kanban.py               # TenantScopedMixin (new)
├── column.py               # kanban_id FK (new)
├── card.py                 # Card model (new)
└── attachment.py           # Attachment model (new)

services/
├── __init__.py             # Updated exports
├── kanban_service.py       # Tenant-scoped board CRUD (new)
├── column_service.py       # Via kanban tenant isolation (new)
├── card_service.py         # Via column/kanban isolation (new)
└── attachment_service.py   # GCS storage (new)

routes/
├── pages/
│   ├── home.py             # Deleted (replaced by dashboard.py)
│   ├── dashboard.py        # Board listing (new)
│   └── board.py            # Single board view (new)
└── api/
    └── board.py            # Move + attachments API (new)

templates/
├── pages/
│   ├── home.html           # Deleted (replaced by dashboard.html)
│   ├── login.html          # Login page with Google button (new)
│   ├── dashboard.html      # Board grid (new)
│   └── board.html          # Kanban board (new)
└── partials/
    ├── kanban_card.html    # Board card (new)
    ├── column.html         # Column partial (new)
    └── card.html           # Card partial (new)

static/
├── css/app.css             # Full CSS (updated)
├── js/
│   ├── dashboard.js        # New Board button (new)
│   └── board.js            # Add Column button (new)
└── islands/
    ├── kanban-board.js     # Drag-drop island (new)
    └── user-menu.js        # User menu flyout (new)

migrations/                 # Generated by feather db migrate
```

## What You Learned

- **Multi-tenant architecture** - Isolated data per organization
- **Multi-board support** - Each tenant can have many boards
- **`TenantScopedMixin`** - Adds tenant_id and for_tenant() query
- **`get_current_tenant_id()`** - Get tenant from current user
- **`require_same_tenant()`** - Enforce tenant isolation
- **Hierarchical isolation** - Tenant → Kanban → Column → Card → Attachment
- **Domain-based tenancy** - Users auto-assigned by email domain
- **Platform admin** - Cross-tenant management
- **Tenant admin** - Organization-level user management

## Series Complete!

You've built a production-ready SaaS Kanban application with:
- Server-rendered UI with Tailwind CSS
- HTMX for dynamic interactions
- Islands for drag-and-drop
- Google OAuth authentication
- Role-based access control
- File attachments with GCS
- Multi-tenant data isolation
- Multiple boards per tenant
- Admin panel for management

## Next Steps

Ideas to extend your Kanban app:
- **Card details modal** - Click to edit description, due dates, labels
- **Card comments** - Add discussion threads
- **Activity log** - Track all changes
- **Real-time updates** - WebSocket for live collaboration
- **Board templates** - Pre-built column layouts
- **API keys** - Third-party integrations
- **Mobile app** - React Native or Flutter client
