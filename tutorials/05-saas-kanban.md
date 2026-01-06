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

**What you'll build:** A multi-tenant SaaS Kanban app where each organization has isolated data.

**Features covered:**
- Multi-tenant architecture with domain-based isolation
- Tenant model and automatic tenant assignment
- Platform admin for managing all tenants
- Tenant admin for managing organization users
- Tenant-scoped queries and data isolation

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
│   └── error_log.py     # Tenant-scoped errors
├── seeds.py             # Creates platform admin
└── config.py            # FEATHER_MULTI_TENANT = True
```

### Tenant Model (models/tenant.py)

```python
from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin

class Tenant(UUIDMixin, TimestampMixin, Model):
    __tablename__ = "tenants"

    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    domain = db.Column(db.String(255), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=False)
    approved_at = db.Column(db.DateTime)

    users = db.relationship("User", backref="tenant")
```

### Multi-Tenant User Model (models/user.py)

```python
class User(UserMixin, UUIDMixin, TimestampMixin, Model):
    __tablename__ = "users"

    tenant_id = db.Column(db.String(36), db.ForeignKey("tenants.id"), nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    display_name = db.Column(db.String(100))
    profile_image_url = db.Column(db.String(500))
    google_id = db.Column(db.String(100), unique=True)
    active = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(50), default="user", nullable=False)
    is_platform_admin = db.Column(db.Boolean, default=False)

    @property
    def is_admin(self):
        return self.role == "admin"
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

We need the Column, Card, and Attachment models and services from Tutorial 4, but modified for tenant-scoping instead of just user-scoping.

---

## Build Steps

### Step 1: Create Tenant-Scoped Models

Create `models/column.py`:

```python
"""Column model for Kanban board - tenant scoped."""

from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin, OrderingMixin, TenantScopedMixin


class Column(UUIDMixin, TimestampMixin, OrderingMixin, TenantScopedMixin, Model):
    """Kanban column scoped to tenant."""

    __tablename__ = "columns"
    __ordering_scope__ = ["tenant_id"]

    title = db.Column(db.String(100), nullable=False)

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

from models.user import User
from models.tenant import Tenant
from models.error_log import ErrorLog
from models.column import Column
from models.card import Card
from models.attachment import Attachment
```

**Key change:** `TenantScopedMixin` adds `tenant_id` field and `for_tenant()` query method.

### Step 2: Run Migration

```bash
feather db migrate -m "Add columns, cards, and attachments"
feather db upgrade
```

### Step 3: Create Tenant-Scoped Services

Create `services/column_service.py`:

```python
"""ColumnService - Tenant-scoped column operations."""

from feather import Service, get_current_tenant_id
from feather.exceptions import NotFoundError
from feather.auth import require_same_tenant
from models import Column


class ColumnService(Service):
    """Column service - tenant-scoped operations."""

    def list_all(self) -> list[Column]:
        """List all columns for current tenant in order."""
        tenant_id = get_current_tenant_id()
        return Column.query_ordered(tenant_id=tenant_id).all()

    def get_by_id(self, id: str) -> Column:
        """Get column by ID, enforcing tenant isolation."""
        column = Column.query.get(id)
        if not column:
            raise NotFoundError("Column", id)
        require_same_tenant(column.tenant_id)
        return column

    def create(self, title: str) -> Column:
        """Create a new column for current tenant."""
        tenant_id = get_current_tenant_id()
        column = Column(tenant_id=tenant_id, title=title)
        column.insert_at_end()
        self.save(column)
        return column

    def delete(self, id: str) -> None:
        """Delete a column (must belong to current tenant)."""
        column = self.get_by_id(id)
        tenant_id = column.tenant_id
        self.db.delete(column)
        self.db.commit()
        Column.reorder_all(tenant_id=tenant_id)
        self.db.commit()
```

Create `services/card_service.py`:

```python
"""CardService - Card operations with tenant isolation."""

from feather import Service, get_current_tenant_id
from feather.exceptions import NotFoundError
from feather.auth import require_same_tenant
from models import Card, Column


class CardService(Service):
    """Card service with tenant isolation via columns."""

    def get_by_id(self, id: str) -> Card:
        """Get card by ID, enforcing tenant isolation via column."""
        card = Card.query.get(id)
        if not card:
            raise NotFoundError("Card", id)
        require_same_tenant(card.column.tenant_id)
        return card

    def create(self, column_id: str, title: str) -> Card:
        """Create a card in a column (must be in current tenant)."""
        column = Column.query.get(column_id)
        if not column:
            raise NotFoundError("Column", column_id)
        require_same_tenant(column.tenant_id)

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
        require_same_tenant(to_column.tenant_id)

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
        require_same_tenant(card.column.tenant_id)

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
        require_same_tenant(attachment.card.column.tenant_id)

        storage = get_storage()
        return storage.get_url(attachment.storage_path, expires_in=3600)

    def delete(self, attachment_id: str) -> None:
        """Delete an attachment."""
        attachment = Attachment.query.get(attachment_id)
        if not attachment:
            raise NotFoundError("Attachment", attachment_id)
        require_same_tenant(attachment.card.column.tenant_id)

        storage = get_storage()
        storage.delete(attachment.storage_path)

        self.db.delete(attachment)
        self.db.commit()
```

Update `services/__init__.py`:

```python
"""Business logic services - Auto-discovered by Feather."""

from services.column_service import ColumnService
from services.card_service import CardService
from services.attachment_service import AttachmentService
```

**Key patterns:**
- `get_current_tenant_id()` - Gets tenant ID from current user
- `require_same_tenant(resource.tenant_id)` - Raises AuthorizationError if mismatch
- Storage paths include tenant ID for GCS isolation

### Step 4: Create Routes

Create `routes/pages/board.py`:

```python
"""Kanban board routes - tenant scoped."""

from flask import render_template, request
from feather import page, auth_required
from feather.services import inject
from services import ColumnService, CardService


@page.get("/")
@auth_required
@inject(ColumnService)
def board(column_service: ColumnService):
    """Render the tenant's Kanban board."""
    columns = column_service.list_all()
    return render_template("pages/board.html", columns=columns)


@page.post("/htmx/columns")
@auth_required
@inject(ColumnService)
def create_column(column_service: ColumnService):
    """Create a new column."""
    title = request.form.get("title", "").strip() or "New Column"
    column = column_service.create(title=title)
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

Create `templates/pages/board.html`:

```html
{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}{{ current_user.tenant.name }} - Kanban{% endblock %}

{% block content %}
<div class="kanban-container">
    <header class="kanban-header">
        <div class="kanban-header-left">
            <h1 class="kanban-title">
                {{ icon("view_kanban", size="lg") }}
                {{ current_user.tenant.name }}
            </h1>
        </div>
        <div class="kanban-header-right">
            <button id="add-column-btn" class="btn-primary">
                {{ icon("add", size="sm") }} Add Column
            </button>
            {% if current_user.is_admin %}
            <a href="/admin/" class="btn-secondary">
                {{ icon("admin_panel_settings", size="sm") }} Admin
            </a>
            {% endif %}
            {% if current_user.is_platform_admin %}
            <a href="/admin/tenants" class="btn-secondary">
                {{ icon("domain", size="sm") }} Tenants
            </a>
            {% endif %}
            <div class="user-menu">
                <img src="{{ current_user.profile_image_url or '/feather-static/favicon.svg' }}"
                     alt="{{ current_user.display_name }}"
                     class="user-avatar">
                <span class="user-info">
                    <span class="user-name">{{ current_user.display_name }}</span>
                    <span class="user-role">{{ current_user.role }}</span>
                </span>
                <a href="/auth/logout" class="btn-text">Logout</a>
            </div>
        </div>
    </header>

    <div data-island="kanban-board" class="kanban-board-wrapper">
        <div id="kanban-board" class="kanban-board">
            {% for column in columns %}
                {% include "partials/column.html" %}
            {% else %}
                <div class="empty-board">
                    <p>No columns yet. Click "Add Column" to get started!</p>
                </div>
            {% endfor %}
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ feather_asset('js/board.js') }}"></script>
{% endblock %}

{% block islands %}
{% if config.DEBUG %}
<script type="module" src="http://localhost:5173/static/islands/kanban-board.js"></script>
{% else %}
<script src="{{ feather_asset('islands/kanban-board') }}"></script>
{% endif %}
{% endblock %}
```

Create `static/js/board.js`:

```javascript
/**
 * Board page JavaScript
 * Handles the "Add Column" button interaction
 */
document.addEventListener('DOMContentLoaded', () => {
    const addColumnBtn = document.getElementById('add-column-btn');

    if (addColumnBtn) {
        addColumnBtn.addEventListener('click', () => {
            window.showPrompt({
                title: 'Add Column',
                message: 'Enter the name for the new column:',
                placeholder: 'Column name',
                confirmText: 'Create',
                onConfirm: (value) => {
                    htmx.ajax('POST', '/htmx/columns', {
                        target: '#kanban-board',
                        swap: 'beforeend',
                        values: { title: value }
                    }).then(() => {
                        document.querySelector('.empty-board')?.remove();
                    });
                }
            });
        });
    }
});
```

Create the partials (same as Tutorial 4):
- `templates/partials/column.html`
- `templates/partials/card.html`

### Step 6: Add CSS

Add to `static/css/app.css` (complete CSS for all tutorials):

```css
@layer components {
    /* Kanban Layout */
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

    /* Columns */
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

    /* Cards */
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

    /* Drag-drop */
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

    /* Buttons */
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

    /* Show delete button when hovering card */
    .kanban-card:hover .btn-icon-subtle {
        @apply opacity-100;
    }

    /* Hide "No cards yet" when cards exist (for HTMX updates) */
    .column-cards:has(.kanban-card) .empty-column {
        @apply hidden;
    }

    .input-card-title {
        @apply w-full px-3 py-2 text-sm bg-white border border-gray-300 rounded-lg
               focus:ring-2 focus:ring-indigo-500 focus:border-transparent;
    }

    /* User Menu */
    .user-menu {
        @apply flex items-center gap-2 ml-2 pl-2 border-l border-gray-300;
    }

    .user-avatar {
        @apply w-8 h-8 rounded-full;
    }

    /* User info in header (multi-tenant) */
    .user-info {
        @apply flex flex-col text-right;
    }

    .user-name {
        @apply text-sm font-medium text-gray-900;
    }

    .user-role {
        @apply text-xs text-gray-500 capitalize;
    }
}
```

### Step 7: Create Kanban Island

Create `static/islands/kanban-board.js` (same as Tutorial 4).

### Step 8: Test Multi-Tenancy

Start the app:
```bash
feather dev
```

**Test as Platform Admin:**

1. Open http://localhost:5173
2. Sign in with your platform admin email
3. Go to Admin → Tenants
4. Create a tenant:
   - Name: "Acme Corp"
   - Slug: "acme"
   - Domain: "acme.com"
   - Admin email: someone@acme.com
5. The tenant starts as "pending" - approve it

**Test Tenant Isolation:**

1. Create columns/cards as platform admin
2. In a private browser, sign in as a user from acme.com domain
3. They should see an empty board (their own tenant's data)
4. Their data is completely isolated from the platform admin's data

**Admin Panel:**

| User Type | Can Access |
|-----------|------------|
| Tenant User | Own board only |
| Tenant Admin | Admin → Users (own tenant) |
| Platform Admin | Admin → Tenants (all tenants) |

## Checkpoint

Your app should now have:
- Multi-tenant architecture
- Domain-based user assignment
- Tenant-isolated data
- Platform admin for tenant management
- Tenant admin for user management within tenant

**Files you created/modified:**
```
models/
├── __init__.py             # Updated exports
├── user.py                 # Scaffolded with tenant_id, is_platform_admin
├── tenant.py               # Scaffolded tenant model
├── column.py               # TenantScopedMixin (new)
├── card.py                 # Card model (new)
└── attachment.py           # Attachment model (new)

services/
├── __init__.py             # Updated exports
├── column_service.py       # Uses get_current_tenant_id() (new)
├── card_service.py         # Uses require_same_tenant() (new)
└── attachment_service.py   # GCS storage (new)

routes/
├── pages/
│   └── board.py            # Tenant board view (new)
└── api/
    └── board.py            # Move + attachments API (new)

templates/
├── pages/
│   └── board.html          # Shows tenant name (new)
└── partials/
    ├── column.html         # Column partial (new)
    └── card.html           # Card partial (new)

static/
├── css/app.css             # Full CSS (updated)
├── js/
│   └── board.js            # Add Column button (new)
└── islands/
    └── kanban-board.js     # Drag-drop island (new)

migrations/                 # Generated by feather db migrate
```

## What You Learned

- **Multi-tenant architecture** - Isolated data per organization
- **`TenantScopedMixin`** - Adds tenant_id and for_tenant() query
- **`get_current_tenant_id()`** - Get tenant from current user
- **`require_same_tenant()`** - Enforce tenant isolation
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
