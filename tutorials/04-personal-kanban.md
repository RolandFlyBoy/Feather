# Tutorial 4: Personal Kanban

## Kanban Tutorial Series

> This is part 4 of a 5-part series building a production Kanban app.
> [View series overview](index.md)

| Part | Title | Status |
|------|-------|--------|
| 1 | Static Board UI | Complete |
| 2 | Persistent Boards | Complete |
| 3 | Drag-and-Drop | Complete |
| 4 | Personal Kanban | **You are here** |
| 5 | SaaS Kanban | |

## This Tutorial

**What you'll build:** A personal Kanban app with multiple boards, authentication, file attachments, and PDF export.

**Features covered:**
- Multiple Kanban boards per user with dashboard home page
- Google OAuth authentication
- Role-based access control (admin, user, viewer)
- PDF attachments with Google Cloud Storage
- Admin panel for user management
- PDF export

## Prerequisites

### Required Credentials

Before starting, you'll need:

| Credential | Where to Get It | What You Need |
|------------|-----------------|---------------|
| **PostgreSQL** | `brew install postgresql` | Local database running |
| **Google OAuth** | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) | Client ID + Client Secret |
| **GCS Bucket** | [Google Cloud Console](https://console.cloud.google.com/storage/browser) | Bucket name |
| **GCS Service Account** | [IAM & Admin > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts) | JSON credentials |

#### Google OAuth Setup

1. Go to [Google Cloud Console > APIs & Credentials](https://console.cloud.google.com/apis/credentials)
2. Create OAuth 2.0 Client ID (Web application)
3. Add authorized redirect URI: `http://localhost:5173/auth/google/callback`
4. Copy the Client ID and Client Secret

#### GCS Setup (for attachments)

1. Create a bucket in [Cloud Storage](https://console.cloud.google.com/storage/browser)
2. Create a service account in [IAM > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
3. Grant "Storage Object Admin" role to the service account
4. Create a JSON key and copy the **entire JSON content** (you'll paste it in `.env`)

**Fresh start required** - This tutorial uses a different CLI configuration.

```bash
feather new kanban
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

Choose `single-tenant`.

```
Database
  Type [none]:
```

Choose `postgresql`.

```
Database name [kanban]:
```

Press Enter to accept `kanban`.

```
Include cloud storage (GCS)? [y/N]:
```

Type `y` for GCS support (needed for PDF attachments).

```
Admin email:
```

Enter your Gmail address (for the admin account).

Then:
```bash
cd kanban
source venv/bin/activate

# Run initial migration
feather db migrate -m "Initial migration"
feather db upgrade

# Create admin user
python seeds.py
```

Copy your credentials to `.env`:

```bash
# Google OAuth (from Cloud Console > Credentials)
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret

# Google Cloud Storage (bucket name + service account JSON on ONE line)
GCS_BUCKET=your-bucket-name
GCS_CREDENTIALS_JSON={"type":"service_account","project_id":"your-project","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"...@....iam.gserviceaccount.com","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token"}
```

> **Important:** The `GCS_CREDENTIALS_JSON` must be the complete JSON content on a single line. Copy from your downloaded service account key file and remove all line breaks.

---

## Starting Point

> **For LLMs:** This section describes the current app state before this tutorial.

### What the Scaffolded App Includes

After `feather new` with the options above, you have:

```
kanban/
├── models/
│   ├── __init__.py
│   ├── user.py             # User model with roles
│   └── error_log.py        # Error logging (we'll delete this)
├── services/
│   └── __init__.py
├── routes/
│   ├── api/
│   └── pages/
│       └── home.py
├── templates/
│   ├── base.html
│   └── pages/home.html
├── static/
│   ├── css/app.css
│   └── islands/
├── seeds.py                # Creates admin user
└── migrations/
```

### User Model (models/user.py)

The scaffolded User model includes authentication and role-based access:

```python
from flask_login import UserMixin
from feather.db import db, Model

class User(UserMixin, Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, ...)
    email = db.Column(db.String(255), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100))
    profile_image_url = db.Column(db.String(500))

    # Authorization
    active = db.Column(db.Boolean, default=False)  # Suspended until approved
    approved_at = db.Column(db.DateTime)
    role = db.Column(db.String(50), default="user", nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, ...)
    updated_at = db.Column(db.DateTime, ...)

    def is_active(self):
        return bool(self.active)

    @property
    def is_admin(self):
        return self.role == "admin"
```

### What We Need to Build

From Tutorial 3, we need:
- Column and Card models (with OrderingMixin)
- Services for columns and cards
- Board routes (HTMX and API)
- Templates and partials
- Kanban Island for drag-drop

Plus new features:
- **Kanban model** for multiple boards per user
- **Dashboard home page** showing all user's boards
- User ownership of boards
- **Role-based access** (admin, user, viewer)
- File attachments on cards
- PDF export
- Admin panel customization

---

## Build Steps

### Step 0: Clean Up Scaffolded Files

The scaffolded app includes demo files we'll replace. Delete them first:

```bash
rm routes/pages/home.py
rm templates/pages/home.html
rm models/error_log.py
rm static/islands/counter.js
```

Update `models/__init__.py` to remove the error_log import:

```python
"""SQLAlchemy models - Auto-discovered by Feather."""

from feather.db import db, Model

from models.user import User
```

### Step 1: Create Models

Create `models/kanban.py`:

```python
"""Kanban board model - each user can have multiple boards."""

from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin


class Kanban(UUIDMixin, TimestampMixin, Model):
    """Kanban board owned by a user."""

    __tablename__ = "kanbans"

    title = db.Column(db.String(100), nullable=False)
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    columns = db.relationship(
        "Column",
        backref="kanban",
        cascade="all, delete-orphan",
        order_by="Column.position"
    )
    user = db.relationship("User", backref="kanbans")

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
    __ordering_scope__ = ["kanban_id"]  # Position scoped per kanban

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
    """Kanban card with optional PDF attachment."""

    __tablename__ = "cards"
    __ordering_scope__ = ["column_id"]

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    column_id = db.Column(
        db.String(36),
        db.ForeignKey("columns.id"),
        nullable=False
    )
    # Single PDF attachment (simplified from multi-file)
    attachment_path = db.Column(db.String(500))

    def __repr__(self):
        return f"<Card {self.title}>"
```

Update `models/__init__.py` to add the new models:

```python
"""SQLAlchemy models - Auto-discovered by Feather."""

from feather.db import db, Model

from models.user import User
from models.kanban import Kanban
from models.column import Column
from models.card import Card
```

### Step 2: Run Migration

```bash
feather db migrate -m "Add kanbans, columns, and cards"
feather db upgrade
```

### Step 3: Create Services

Create `services/kanban_service.py`:

```python
"""KanbanService - Business logic for kanban boards."""

from feather import Service
from feather.exceptions import NotFoundError, AuthorizationError
from flask_login import current_user
from models import Kanban


class KanbanService(Service):
    """Kanban service - user-scoped operations."""

    def list_for_user(self, user_id: str) -> list[Kanban]:
        """List all kanbans for a user, newest first."""
        return Kanban.query.filter_by(user_id=user_id).order_by(
            Kanban.created_at.desc()
        ).all()

    def get_by_id(self, id: str, user_id: str) -> Kanban:
        """Get kanban by ID, ensuring user ownership."""
        kanban = Kanban.query.get(id)
        if not kanban:
            raise NotFoundError("Kanban", id)
        if kanban.user_id != user_id:
            raise AuthorizationError("You don't have access to this board")
        return kanban

    def create(self, user_id: str, title: str) -> Kanban:
        """Create a new kanban for a user."""
        if current_user.role == "viewer":
            raise AuthorizationError("Viewers cannot create boards")
        kanban = Kanban(user_id=user_id, title=title)
        self.save(kanban)
        return kanban

    def delete(self, id: str, user_id: str) -> None:
        """Delete a kanban (user must own it)."""
        if current_user.role == "viewer":
            raise AuthorizationError("Viewers cannot delete boards")
        kanban = self.get_by_id(id, user_id)
        self.db.delete(kanban)
        self.db.commit()
```

Create `services/column_service.py`:

```python
"""ColumnService - Business logic for columns."""

from feather import Service
from feather.exceptions import NotFoundError, AuthorizationError
from flask_login import current_user
from models import Column, Kanban


class ColumnService(Service):
    """Column service - kanban-scoped operations."""

    def list_for_kanban(self, kanban_id: str) -> list[Column]:
        """List all columns for a kanban in order."""
        return Column.query_ordered(kanban_id=kanban_id).all()

    def get_by_id(self, id: str, user_id: str) -> Column:
        """Get column by ID, ensuring user ownership via kanban."""
        column = Column.query.get(id)
        if not column:
            raise NotFoundError("Column", id)
        if column.kanban.user_id != user_id:
            raise AuthorizationError("You don't have access to this column")
        return column

    def create(self, kanban_id: str, user_id: str, title: str) -> Column:
        """Create a new column in a kanban (user must own kanban)."""
        if current_user.role == "viewer":
            raise AuthorizationError("Viewers cannot create columns")
        kanban = Kanban.query.get(kanban_id)
        if not kanban or kanban.user_id != user_id:
            raise AuthorizationError("You don't have access to this board")

        column = Column(kanban_id=kanban_id, title=title)
        column.insert_at_end()
        self.save(column)
        return column

    def delete(self, id: str, user_id: str) -> None:
        """Delete a column (user must own it via kanban)."""
        if current_user.role == "viewer":
            raise AuthorizationError("Viewers cannot delete columns")
        column = self.get_by_id(id, user_id)
        kanban_id = column.kanban_id
        self.db.delete(column)
        self.db.commit()
        Column.reorder_all(kanban_id=kanban_id)
        self.db.commit()
```

Create `services/card_service.py`:

```python
"""CardService - Business logic for cards."""

from feather import Service
from feather.exceptions import NotFoundError, AuthorizationError
from flask_login import current_user
from models import Card, Column


class CardService(Service):
    """Card service with attachment support."""

    def get_by_id(self, id: str, user_id: str) -> Card:
        """Get card by ID, ensuring user ownership via kanban."""
        card = Card.query.get(id)
        if not card:
            raise NotFoundError("Card", id)
        if card.column.kanban.user_id != user_id:
            raise AuthorizationError("You don't have access to this card")
        return card

    def create(self, column_id: str, user_id: str, title: str) -> Card:
        """Create a new card in a column (user must own kanban)."""
        if current_user.role == "viewer":
            raise AuthorizationError("Viewers cannot create cards")
        column = Column.query.get(column_id)
        if not column or column.kanban.user_id != user_id:
            raise AuthorizationError("You don't have access to this column")

        card = Card(column_id=column_id, title=title)
        card.insert_at_end()
        self.save(card)
        return card

    def delete(self, id: str, user_id: str) -> None:
        """Delete a card (user must own it via kanban)."""
        if current_user.role == "viewer":
            raise AuthorizationError("Viewers cannot delete cards")
        card = self.get_by_id(id, user_id)
        column_id = card.column_id
        self.db.delete(card)
        self.db.commit()
        Card.reorder_all(column_id=column_id)
        self.db.commit()

    def move(self, card_id: str, user_id: str, to_column_id: str, to_position: int) -> Card:
        """Move a card to a new position."""
        if current_user.role == "viewer":
            raise AuthorizationError("Viewers cannot move cards")
        card = self.get_by_id(card_id, user_id)

        # Verify target column ownership via kanban
        to_column = Column.query.get(to_column_id)
        if not to_column or to_column.kanban.user_id != user_id:
            raise AuthorizationError("You don't have access to the target column")

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

Update `services/__init__.py`:

```python
"""Business logic services - Auto-discovered by Feather."""

from services.kanban_service import KanbanService
from services.column_service import ColumnService
from services.card_service import CardService
```

### Step 4: Create Routes

Create `routes/pages/dashboard.py` for the home page and authentication:

```python
"""Dashboard routes - home page, login, and board management."""

from flask import render_template, request, redirect, url_for
from flask_login import current_user
from feather import page, auth_required, inject
from services import KanbanService


@page.get("/login")
def login():
    """Show login page for unauthenticated users."""
    if current_user.is_authenticated:
        return redirect(url_for("page.home"))
    return render_template("pages/login.html")


@page.get("/pending")
@auth_required
def pending():
    """Show pending approval page for suspended users."""
    if current_user.is_active:
        return redirect(url_for("page.home"))
    return render_template("pages/pending.html")


@page.get("/")
@auth_required
@inject(KanbanService)
def home(kanban_service: KanbanService):
    """Render the user's board dashboard."""
    # Redirect suspended users to pending page
    if not current_user.is_active:
        return redirect(url_for("page.pending"))

    kanbans = kanban_service.list_for_user(current_user.id)
    return render_template("pages/dashboard.html", kanbans=kanbans)


@page.post("/htmx/kanbans")
@auth_required
@inject(KanbanService)
def create_kanban(kanban_service: KanbanService):
    """Create a new kanban board."""
    title = request.form.get("title", "").strip() or "Untitled Board"
    kanban = kanban_service.create(user_id=current_user.id, title=title)
    return render_template("partials/kanban_card.html", kanban=kanban)


@page.delete("/htmx/kanbans/<kanban_id>")
@auth_required
@inject(KanbanService)
def delete_kanban(kanban_service: KanbanService, kanban_id: str):
    """Delete a kanban board."""
    kanban_service.delete(kanban_id, user_id=current_user.id)
    return ""
```

Create `routes/pages/board.py` for individual board views:

```python
"""Kanban board routes."""

from flask import render_template, request
from flask_login import current_user
from feather import page, auth_required, inject
from services import KanbanService, ColumnService, CardService


@page.get("/kanban/<kanban_id>")
@auth_required
@inject(KanbanService, ColumnService)
def board(kanban_service: KanbanService, column_service: ColumnService, kanban_id: str):
    """Render a specific Kanban board."""
    kanban = kanban_service.get_by_id(kanban_id, current_user.id)
    columns = column_service.list_for_kanban(kanban_id)
    return render_template("pages/board.html", kanban=kanban, columns=columns)


# HTMX: Column routes
@page.post("/htmx/kanbans/<kanban_id>/columns")
@auth_required
@inject(ColumnService)
def create_column(column_service: ColumnService, kanban_id: str):
    """Create a new column in a kanban."""
    title = request.form.get("title", "").strip() or "New Column"
    column = column_service.create(
        kanban_id=kanban_id,
        user_id=current_user.id,
        title=title
    )
    return render_template("partials/column.html", column=column, kanban=column.kanban)


@page.delete("/htmx/columns/<column_id>")
@auth_required
@inject(ColumnService)
def delete_column(column_service: ColumnService, column_id: str):
    """Delete a column."""
    column_service.delete(column_id, user_id=current_user.id)
    return ""


# HTMX: Card routes
@page.post("/htmx/columns/<column_id>/cards")
@auth_required
@inject(CardService)
def create_card(card_service: CardService, column_id: str):
    """Create a new card."""
    title = request.form.get("title", "").strip()
    if not title:
        return "", 400
    card = card_service.create(
        column_id=column_id,
        user_id=current_user.id,
        title=title
    )
    return render_template("partials/card.html", card=card)


@page.delete("/htmx/cards/<card_id>")
@auth_required
@inject(CardService)
def delete_card(card_service: CardService, card_id: str):
    """Delete a card."""
    card_service.delete(card_id, user_id=current_user.id)
    return ""
```

Create `routes/api/board.py`:

```python
"""API routes for Kanban board."""

from flask import request, send_file, render_template
from flask_login import current_user
from feather import api, auth_required, inject
from services import CardService, KanbanService
from io import BytesIO
from datetime import datetime


@api.post("/cards/move")
@auth_required
@inject(CardService)
def move_card(card_service: CardService):
    """Move a card to a new position."""
    data = request.get_json()
    card = card_service.move(
        card_id=data["cardId"],
        user_id=current_user.id,
        to_column_id=data["toColumnId"],
        to_position=data["toPosition"]
    )
    return {"success": True, "card": {"id": card.id, "position": card.position}}


# PDF Export - reportlab is a Feather core dependency
@api.get("/kanbans/<kanban_id>/export")
@auth_required
@inject(KanbanService)
def export_pdf(kanban_service: KanbanService, kanban_id: str):
    """Export a Kanban board to PDF (generated inline)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from models import Column, Card

    kanban = kanban_service.get_by_id(kanban_id, current_user.id)
    columns = Column.query_ordered(kanban_id=kanban_id).all()

    # Generate PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=20*mm,
        bottomMargin=20*mm,
        leftMargin=15*mm,
        rightMargin=15*mm
    )
    styles = getSampleStyleSheet()

    elements = [
        Paragraph(kanban.title, styles['Heading1']),
        Paragraph(f"Exported on {datetime.now().strftime('%B %d, %Y')}", styles['Normal']),
        Spacer(1, 20),
    ]

    for column in columns:
        elements.append(Paragraph(column.title, styles['Heading2']))
        cards = Card.query_ordered(column_id=column.id).all()
        if cards:
            card_data = [[card.title] for card in cards]
            table = Table(card_data, colWidths=[170*mm])
            table.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 1, colors.grey),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9FAFB')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#111827')),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('PADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("(No cards)", styles['Normal']))
        elements.append(Spacer(1, 15))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{kanban.title}.pdf'
    )


@api.post("/cards/<card_id>/attachment")
@auth_required
@inject(CardService)
def upload_attachment(card_service: CardService, card_id: str):
    """Upload a PDF attachment to a card."""
    from feather.storage import get_storage
    from feather.exceptions import ValidationError
    import uuid

    card = card_service.get_by_id(card_id, user_id=current_user.id)

    if 'file' not in request.files:
        raise ValidationError("No file provided")

    file = request.files['file']
    if not file.filename.lower().endswith('.pdf'):
        raise ValidationError("Only PDF files are allowed")

    # Delete old attachment if exists
    storage = get_storage()
    if card.attachment_path:
        storage.delete(card.attachment_path)

    # Upload new attachment
    filename = f"cards/{card_id}/{uuid.uuid4()}.pdf"
    storage.upload(file, filename, content_type='application/pdf')

    # Update card
    card.attachment_path = filename
    card_service.save(card)

    return {"success": True, "path": filename}


@api.delete("/cards/<card_id>/attachment")
@auth_required
@inject(CardService)
def delete_attachment(card_service: CardService, card_id: str):
    """Delete a card's PDF attachment."""
    from feather.storage import get_storage

    card = card_service.get_by_id(card_id, user_id=current_user.id)

    if card.attachment_path:
        storage = get_storage()
        storage.delete(card.attachment_path)
        card.attachment_path = None
        card_service.save(card)

    # Return the updated card partial (for HTMX swap)
    return render_template("partials/card.html", card=card)
```

### Step 5: Create Templates

Create `templates/pages/login.html` (shown to unauthenticated users):

```html
{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}Sign In{% endblock %}

{% block content %}
<div class="login-container">
    <div class="login-card">
        <h1 class="login-title">
            {{ icon("view_kanban", size="xl") }}
            Kanban
        </h1>
        <p class="login-subtitle">Organize your work with boards</p>
        <a href="/auth/google/login" class="login-button">
            {{ icon("login", size="sm") }} Sign in with Google
        </a>
    </div>
</div>
{% endblock %}
```

Create `templates/pages/pending.html` (shown to users awaiting approval):

```html
{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}Pending Approval{% endblock %}

{% block content %}
<div class="pending-container">
    <div class="pending-card">
        <span class="pending-icon text-yellow-500">{{ icon("hourglass_empty", size="xl") }}</span>
        <h1 class="pending-title">Account Pending Approval</h1>
        <p class="pending-message">
            Your account ({{ current_user.email }}) is awaiting admin approval.
            You'll receive access once approved.
        </p>
        <a href="/auth/logout" class="btn-secondary">
            {{ icon("logout", size="sm") }} Sign Out
        </a>
    </div>
</div>
{% endblock %}
```

Create `templates/pages/dashboard.html` (the home page):

```html
{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}My Boards{% endblock %}

{% block content %}
<div class="dashboard-container">
    <header class="dashboard-header">
        <div class="dashboard-header-left">
            <h1 class="dashboard-title">
                {{ icon("view_kanban", size="lg") }} My Boards
            </h1>
        </div>
        <div class="dashboard-header-right">
            {% if current_user.role != "viewer" %}
            <button id="add-kanban-btn" class="btn-primary">
                {{ icon("add", size="sm") }} New Board
            </button>
            {% endif %}
            {% if current_user.is_admin %}
            <a href="/admin/" class="btn-secondary">
                {{ icon("settings", size="sm") }} Admin
            </a>
            {% endif %}
            <div class="user-menu">
                <img src="{{ current_user.profile_image_url or '/feather-static/favicon.svg' }}"
                     alt="{{ current_user.display_name }}"
                     referrerpolicy="no-referrer"
                     class="user-avatar">
                <a href="/auth/logout" class="btn-text">Logout</a>
            </div>
        </div>
    </header>

    <div id="kanban-grid" class="kanban-grid">
        {% for kanban in kanbans %}
            {% include "partials/kanban_card.html" %}
        {% else %}
        <div class="empty-state">
            <p>{{ icon("dashboard", size="xl") }}</p>
            <p>No boards yet. {% if current_user.role != "viewer" %}Create your first board!{% endif %}</p>
        </div>
        {% endfor %}
    </div>
</div>

{% endblock %}

{% block scripts %}
{% if current_user.role != "viewer" %}
<script src="{{ feather_asset('js/dashboard.js') }}"></script>
{% endif %}
{% endblock %}
```

Create `static/js/dashboard.js`:

```javascript
/**
 * Dashboard page JavaScript
 * Handles the "New Board" button interaction
 */
document.addEventListener('DOMContentLoaded', () => {
    const addKanbanBtn = document.getElementById('add-kanban-btn');

    if (addKanbanBtn) {
        addKanbanBtn.addEventListener('click', () => {
            window.showPrompt({
                title: 'Create Board',
                message: 'Enter a name for your new board:',
                placeholder: 'Board name',
                confirmText: 'Create',
                onConfirm: (value) => {
                    htmx.ajax('POST', '/htmx/kanbans', {
                        target: '#kanban-grid',
                        swap: 'afterbegin',
                        values: { title: value }
                    }).then(() => {
                        document.querySelector('.empty-state')?.remove();
                    });
                }
            });
        });
    }
});
```

Create `templates/partials/kanban_card.html`:

```html
{% from "components/icon.html" import icon %}

<div id="kanban-{{ kanban.id }}" class="kanban-card">
    <a href="{{ url_for('page.board', kanban_id=kanban.id) }}" class="kanban-card-link">
        <h2 class="kanban-card-title">{{ kanban.title }}</h2>
        <p class="kanban-card-meta">
            {{ kanban.columns|length }} column{{ 's' if kanban.columns|length != 1 else '' }}
            · Updated {{ kanban.updated_at.strftime('%b %d') }}
        </p>
    </a>
    {% if current_user.role != "viewer" %}
    <button hx-delete="/htmx/kanbans/{{ kanban.id }}"
            hx-target="#kanban-{{ kanban.id }}"
            hx-swap="outerHTML"
            hx-confirm="Delete '{{ kanban.title }}' and all its cards?"
            class="kanban-card-delete">
        {{ icon("delete", size="sm") }}
    </button>
    {% endif %}
</div>
```

Create `templates/pages/board.html`:

```html
{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}{{ kanban.title }}{% endblock %}

{% block content %}
<div class="kanban-container">
    <header class="kanban-header">
        <div class="kanban-header-left">
            <a href="{{ url_for('page.home') }}" class="back-link">
                {{ icon("arrow_back", size="sm") }}
            </a>
            <h1 class="kanban-title">
                {{ icon("view_kanban", size="lg") }} {{ kanban.title }}
            </h1>
        </div>
        <div class="kanban-header-right">
            {% if current_user.role != "viewer" %}
            <button id="add-column-btn" class="btn-primary">
                {{ icon("add", size="sm") }} Add Column
            </button>
            {% endif %}
            {% if current_user.is_admin %}
            <a href="/admin/" class="btn-secondary">
                {{ icon("settings", size="sm") }} Admin
            </a>
            {% endif %}
            <div class="user-menu">
                <img src="{{ current_user.profile_image_url or '/feather-static/favicon.svg' }}"
                     alt="{{ current_user.display_name }}"
                     referrerpolicy="no-referrer"
                     class="user-avatar">
                <a href="/auth/logout" class="btn-text">Logout</a>
            </div>
        </div>
    </header>

    <div data-island="kanban-board" data-kanban-id="{{ kanban.id }}" class="kanban-board-wrapper">
        <div id="kanban-board" class="kanban-board">
            {% for column in columns %}
                {% include "partials/column.html" %}
            {% else %}
                <div class="empty-board">
                    <p>No columns yet. {% if current_user.role != "viewer" %}Click "Add Column" to get started!{% endif %}</p>
                </div>
            {% endfor %}
        </div>
    </div>
</div>

{% endblock %}

{% block scripts %}
{% if current_user.role != "viewer" %}
<script src="{{ feather_asset('js/board.js') }}"></script>
{% endif %}
{% endblock %}

{% block islands %}
{% if config.DEBUG %}
<script type="module" src="http://localhost:5173/static/islands/kanban-board.js"></script>
{% else %}
<script src="{{ feather_asset('islands/kanban-board') }}"></script>
{% endif %}
{% endblock %}
```

Create `templates/partials/column.html`:

```html
{% from "components/icon.html" import icon %}

<div id="column-{{ column.id }}" class="kanban-column">
    <div class="column-header">
        <h2 class="column-title">{{ column.title }}</h2>
        {% if current_user.role != "viewer" %}
        <button hx-delete="/htmx/columns/{{ column.id }}"
                hx-target="#column-{{ column.id }}"
                hx-swap="outerHTML"
                hx-confirm="Delete this column and all its cards?"
                class="btn-icon-danger">
            {{ icon("close", size="sm") }}
        </button>
        {% endif %}
    </div>

    <div id="column-{{ column.id }}-cards"
         class="column-cards"
         data-id="{{ column.id }}">
        {% for card in column.cards %}
            {% include "partials/card.html" %}
        {% else %}
            <p class="empty-column empty-placeholder">No cards yet</p>
        {% endfor %}
    </div>

    {% if current_user.role != "viewer" %}
    <form hx-post="/htmx/columns/{{ column.id }}/cards"
          hx-target="#column-{{ column.id }}-cards"
          hx-swap="beforeend"
          hx-on::after-request="if(event.detail.successful) { this.reset(); this.closest('.kanban-column').querySelector('.empty-placeholder')?.remove(); }"
          class="column-footer">
        <input type="text" name="title" placeholder="Add a card..." class="input-card-title bg-white">
    </form>
    {% endif %}
</div>
```

Create `templates/partials/card.html`:

```html
{% from "components/icon.html" import icon %}

<div id="card-{{ card.id }}"
     class="kanban-card"
     data-id="{{ card.id }}">
    <div class="card-content">
        {% if current_user.role != "viewer" %}
        <span class="drag-handle">
            {{ icon("drag_indicator", size="sm") }}
        </span>
        {% endif %}
        <div class="card-body">
            <p class="card-title">{{ card.title }}</p>
        </div>
        <div class="card-actions">
            {# PDF attachment icon - click to view or upload #}
            {% if card.attachment_path %}
            <button data-action="view-pdf" data-card-id="{{ card.id }}" class="card-pdf-icon has-pdf" title="View PDF">
                {{ icon("picture_as_pdf", size="sm") }}
            </button>
            {% elif current_user.role != "viewer" %}
            <button data-action="show-upload" data-card-id="{{ card.id }}" class="card-pdf-icon" title="Attach PDF">
                {{ icon("attach_file", size="sm") }}
            </button>
            {% endif %}
            {% if current_user.role != "viewer" %}
            <button hx-delete="/htmx/cards/{{ card.id }}"
                    hx-target="#card-{{ card.id }}"
                    hx-swap="outerHTML"
                    hx-confirm="Delete this card?"
                    class="btn-icon-subtle">
                {{ icon("close", size="sm") }}
            </button>
            {% endif %}
        </div>
    </div>
</div>
```

Create `templates/partials/pdf_viewer.html` for viewing PDF attachments:

```html
{% from "components/icon.html" import icon %}

<div class="modal-backdrop" data-action="close-pdf-viewer"></div>
<div class="pdf-viewer-modal">
    <div class="pdf-viewer-header">
        <h2 class="pdf-viewer-title">{{ card.title }}</h2>
        <div class="pdf-viewer-actions">
            {% if current_user.role != "viewer" %}
            <button data-action="replace-pdf" data-card-id="{{ card.id }}" class="btn-secondary btn-sm">
                {{ icon("upload", size="sm") }} Replace
            </button>
            <button hx-delete="/api/cards/{{ card.id }}/attachment"
                    hx-target="#card-{{ card.id }}"
                    hx-swap="outerHTML"
                    data-close-on-success="pdf-viewer"
                    class="btn-danger btn-sm">
                {{ icon("delete", size="sm") }} Delete
            </button>
            {% endif %}
            <button data-action="close-pdf-viewer" class="btn-icon-subtle visible">
                {{ icon("close", size="sm") }}
            </button>
        </div>
    </div>
    <div class="pdf-viewer-content">
        <iframe src="{{ pdf_url }}" class="pdf-iframe"></iframe>
    </div>
</div>
```

Create `templates/partials/upload_modal.html` for uploading PDFs:

```html
{% from "components/icon.html" import icon %}

<div class="modal-backdrop" data-action="close-upload-modal"></div>
<div class="modal-content upload-modal">
    <div class="modal-header">
        <h2 class="modal-title">Attach PDF to Card</h2>
        <button data-action="close-upload-modal" class="btn-icon-subtle visible">
            {{ icon("close", size="sm") }}
        </button>
    </div>
    <div class="modal-body">
        <form id="upload-form" data-card-id="{{ card_id }}" enctype="multipart/form-data">
            <input type="file" name="file" accept=".pdf" required class="file-input">
            <p class="upload-hint">PDF files only (max 10MB)</p>
            <div class="upload-actions">
                <button type="button" data-action="close-upload-modal" class="btn-secondary">Cancel</button>
                <button type="submit" class="btn-primary">
                    {{ icon("upload", size="sm") }} Upload
                </button>
            </div>
        </form>
    </div>
</div>
```

The upload form uses `data-card-id` to pass the card ID to JavaScript (handled in `board.js` below).

Add containers for the modals in `templates/pages/board.html` (before the closing `{% endblock content %}`):

```html
<!-- PDF viewer and upload modals -->
<div id="pdf-viewer-container"></div>
<div id="upload-modal-container"></div>
```

Create `static/js/board.js`:

```javascript
/**
 * Board page JavaScript
 * Handles Add Column button, PDF viewer, and upload modals using event delegation
 */
(function() {
    'use strict';

    // Helper functions for modals
    function viewPdf(cardId) {
        htmx.ajax('GET', `/htmx/cards/${cardId}/pdf`, {
            target: '#pdf-viewer-container',
            swap: 'innerHTML'
        });
    }

    function closePdfViewer() {
        document.getElementById('pdf-viewer-container').innerHTML = '';
    }

    function showUploadModal(cardId) {
        htmx.ajax('GET', `/htmx/cards/${cardId}/upload-modal`, {
            target: '#upload-modal-container',
            swap: 'innerHTML'
        });
    }

    function closeUploadModal() {
        document.getElementById('upload-modal-container').innerHTML = '';
    }

    // Event delegation for data-action handlers
    document.addEventListener('click', (e) => {
        const target = e.target.closest('[data-action]');
        if (!target) return;

        const action = target.dataset.action;
        const cardId = target.dataset.cardId;

        switch (action) {
            case 'view-pdf':
                viewPdf(cardId);
                break;
            case 'show-upload':
                showUploadModal(cardId);
                break;
            case 'close-pdf-viewer':
                closePdfViewer();
                break;
            case 'close-upload-modal':
                closeUploadModal();
                break;
            case 'replace-pdf':
                closePdfViewer();
                showUploadModal(cardId);
                break;
        }
    });

    // Close PDF viewer after successful HTMX delete
    document.body.addEventListener('htmx:afterRequest', (e) => {
        if (e.detail.successful && e.detail.elt?.dataset.closeOnSuccess === 'pdf-viewer') {
            closePdfViewer();
        }
    });

    // Upload form handler (attached when modal loads via HTMX)
    document.addEventListener('htmx:afterSwap', (e) => {
        const form = document.getElementById('upload-form');
        if (form && !form.dataset.handlerAttached) {
            form.dataset.handlerAttached = 'true';
            const cardId = form.dataset.cardId;

            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(form);

                try {
                    const res = await ApiUtility.upload(`/api/cards/${cardId}/attachment`, formData);
                    if (res.success) {
                        closeUploadModal();
                        htmx.ajax('GET', `/htmx/cards/${cardId}/refresh`, {
                            target: `#card-${cardId}`,
                            swap: 'outerHTML'
                        });
                    } else {
                        window.showToast(res.error?.message || 'Upload failed', 'error');
                    }
                } catch (err) {
                    window.showToast('Upload failed. Please try again.', 'error');
                }
            });
        }
    });

    // Add Column button handler
    document.addEventListener('DOMContentLoaded', () => {
        const boardWrapper = document.querySelector('[data-island="kanban-board"]');
        const kanbanId = boardWrapper?.dataset.kanbanId;

        const addColumnBtn = document.getElementById('add-column-btn');
        if (addColumnBtn && kanbanId) {
            addColumnBtn.addEventListener('click', () => {
                window.showPrompt({
                    title: 'Add Column',
                    message: 'Enter the name for the new column:',
                    placeholder: 'Column name',
                    confirmText: 'Create',
                    onConfirm: (value) => {
                        htmx.ajax('POST', `/htmx/kanbans/${kanbanId}/columns`, {
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
})();
```

Add the attachment HTMX routes to `routes/pages/board.py`:

```python
@page.get("/htmx/cards/<card_id>/pdf")
@auth_required
@inject(CardService)
def view_pdf(card_service: CardService, card_id: str):
    """Show PDF viewer modal."""
    from feather.storage import get_storage

    card = card_service.get_by_id(card_id, user_id=current_user.id)
    if not card.attachment_path:
        return "", 404

    storage = get_storage()
    pdf_url = storage.get_url(card.attachment_path, expires_in=3600)
    return render_template("partials/pdf_viewer.html", card=card, pdf_url=pdf_url)


@page.get("/htmx/cards/<card_id>/upload-modal")
@auth_required
def upload_modal(card_id: str):
    """Show upload modal."""
    return render_template("partials/upload_modal.html", card_id=card_id)


@page.get("/htmx/cards/<card_id>/refresh")
@auth_required
@inject(CardService)
def refresh_card(card_service: CardService, card_id: str):
    """Refresh a single card (after upload)."""
    card = card_service.get_by_id(card_id, user_id=current_user.id)
    return render_template("partials/card.html", card=card)
```

### Step 6: Add CSS

Add to `static/css/app.css`:

```css
@layer components {
    /* =====================
       Login Page
       ===================== */
    .login-container {
        @apply min-h-screen bg-gray-100 flex items-center justify-center p-6;
    }

    .login-card {
        @apply bg-white rounded-xl shadow-lg p-8 text-center max-w-sm w-full;
    }

    .login-title {
        @apply text-3xl font-bold text-gray-900 flex items-center justify-center gap-3 mb-2;
    }

    .login-subtitle {
        @apply text-gray-500 mb-6;
    }

    .login-button {
        @apply inline-flex items-center justify-center gap-2 w-full
               px-4 py-3 bg-indigo-600 text-white rounded-lg
               hover:bg-indigo-700 transition-colors font-medium;
    }

    /* =====================
       Pending Approval Page
       ===================== */
    .pending-container {
        @apply min-h-screen bg-gray-100 flex items-center justify-center p-6;
    }

    .pending-card {
        @apply bg-white rounded-xl shadow-lg p-8 text-center max-w-md w-full;
    }

    .pending-icon {
        @apply text-5xl mb-4 block;
    }

    .pending-title {
        @apply text-2xl font-bold text-gray-900 mb-2;
    }

    .pending-message {
        @apply text-gray-600 mb-6;
    }

    /* =====================
       Dashboard (Home Page)
       ===================== */
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

    /* Kanban Grid - 2 column layout */
    .kanban-grid {
        @apply grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl mx-auto;
    }

    /* Kanban Card (on dashboard) */
    .kanban-card {
        @apply relative bg-white rounded-lg shadow-sm border border-gray-200
               hover:shadow-md transition-shadow;
    }

    .kanban-card-link {
        @apply block p-6 pr-12;
    }

    .kanban-card-title {
        @apply text-lg font-semibold text-gray-900 mb-1;
    }

    .kanban-card-meta {
        @apply text-sm text-gray-500;
    }

    .kanban-card-delete {
        @apply absolute top-4 right-4 text-gray-300 hover:text-red-600
               opacity-0 transition-all;
    }

    .kanban-card:hover .kanban-card-delete {
        @apply opacity-100;
    }

    .empty-state {
        @apply col-span-2 text-center text-gray-500 py-12;
    }

    /* =====================
       Board Page
       ===================== */
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
        @apply text-gray-500 hover:text-gray-700 p-2 -ml-2;
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

    /* Modal */
    .modal-backdrop {
        @apply fixed inset-0 bg-black/50 z-40;
    }

    .modal-content {
        @apply fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2
               bg-white rounded-lg shadow-xl z-50 w-full max-w-lg max-h-[80vh] overflow-y-auto;
    }

    .modal-header {
        @apply flex items-center justify-between p-4 border-b border-gray-200;
    }

    .modal-title {
        @apply text-lg font-semibold text-gray-900;
    }

    .modal-body {
        @apply p-4;
    }

    /* Card Actions (PDF icon, delete) */
    .card-actions {
        @apply flex items-center gap-1;
    }

    .card-pdf-icon {
        @apply text-gray-300 hover:text-gray-500 transition-colors;
    }

    .card-pdf-icon.has-pdf {
        @apply text-red-400 hover:text-red-600;
    }

    /* PDF Viewer Modal */
    .pdf-viewer-modal {
        @apply fixed inset-4 md:inset-8 bg-white rounded-lg shadow-xl z-50
               flex flex-col;
    }

    .pdf-viewer-header {
        @apply flex items-center justify-between p-4 border-b border-gray-200;
    }

    .pdf-viewer-title {
        @apply text-lg font-semibold text-gray-900 truncate;
    }

    .pdf-viewer-actions {
        @apply flex items-center gap-2;
    }

    .pdf-viewer-content {
        @apply flex-1 min-h-0;
    }

    .pdf-iframe {
        @apply w-full h-full border-0;
    }

    /* Upload Modal */
    .upload-modal {
        @apply max-w-md;
    }

    .file-input {
        @apply w-full p-3 border border-gray-300 rounded-lg
               file:mr-4 file:py-2 file:px-4
               file:rounded-lg file:border-0
               file:text-sm file:font-semibold
               file:bg-indigo-50 file:text-indigo-700
               hover:file:bg-indigo-100;
    }

    .upload-hint {
        @apply text-sm text-gray-500 mt-2;
    }

    .upload-actions {
        @apply flex justify-end gap-2 mt-4;
    }

    /* Button variants */
    .btn-danger {
        @apply inline-flex items-center gap-2 px-4 py-2
               bg-red-600 text-white rounded-lg
               hover:bg-red-700 transition-colors;
    }

    .btn-sm {
        @apply text-sm px-3 py-1.5;
    }

    .btn-icon-subtle.visible {
        @apply opacity-100;
    }
}
```

### Step 7: Create Kanban Island

Create `static/islands/kanban-board.js`:

```javascript
/**
 * Kanban Board Island
 */
island("kanban-board", {
  draggable: {
    items: ".kanban-card",
    zones: ".column-cards",
    handle: ".drag-handle",

    onDrop(item, zone, info, e) {
      this.optimistic(
        () => {},
        () => this.api.post("/api/cards/move", {
          cardId: info.itemId,
          toColumnId: info.toZoneId,
          toPosition: info.toIndex
        })
      ).catch(err => {
        console.error("Failed to move card:", err);
        window.location.reload();
      });
    }
  }
});
```

### Step 8: Add PDF Export Button

The export route is already defined in `routes/api/board.py`. Add the export button to the board header in `templates/pages/board.html`:

```html
<div class="kanban-header-right">
    <a href="/api/kanbans/{{ kanban.id }}/export" class="btn-secondary">
        {{ icon("picture_as_pdf", size="sm") }} Export PDF
    </a>
    {% if current_user.role != "viewer" %}
    <button id="add-column-btn" class="btn-primary">
        {{ icon("add", size="sm") }} Add Column
    </button>
    {% endif %}
    <!-- ... rest of buttons ... -->
</div>
```

The export link points directly to our API route which generates the PDF inline and returns it as a download.

### Step 9: Configure OAuth Redirect

Update `.env` with your OAuth redirect URI:
```bash
# Make sure your Google OAuth credentials include this redirect URI:
# http://localhost:5173/auth/google/callback
```

### Step 10: Test It

Start the app:
```bash
feather dev
```

Open http://localhost:5173:

1. **Sign in with Google** - You'll be redirected to Google OAuth
2. **Create a board** - Click "New Board" on the dashboard
3. **Create columns and cards** - Add columns and cards to your board
4. **Create multiple boards** - Go back to dashboard and create more
5. **Access admin panel** - Click "Admin" to manage users (admin role only)
6. **Attach PDF to card** - Click the attach icon on a card to upload a PDF
7. **View PDF** - Click the PDF icon to view the attachment in a full-screen viewer
8. **Export to PDF** - Click "Export PDF" in the board header

**Test roles:**
- **Admin**: Full access + admin panel at `/admin/`
- **User**: Can create/edit boards, columns, cards, attach PDFs
- **Viewer**: Can only view boards and PDFs (no create/edit/delete buttons)

## Checkpoint

Your app should now have:
- Google OAuth authentication
- Dashboard showing all user's boards in a 2-column grid
- Multiple Kanban boards per user
- Three user roles (admin, user, viewer)
- Admin panel at `/admin/` (admin role only)
- All previous drag-drop functionality
- PDF attachments on cards with viewer modal
- PDF export (generated inline)

**Files you created/modified:**
```
models/
├── __init__.py             # Updated exports
├── user.py                 # Scaffolded with role field
├── kanban.py               # Board container (new)
├── column.py               # With kanban_id (new)
└── card.py                 # With attachment_path (new)

services/
├── __init__.py             # Updated exports
├── kanban_service.py       # Board CRUD (new)
├── column_service.py       # Kanban-scoped (new)
└── card_service.py         # With role checks (new)

routes/
├── pages/
│   ├── dashboard.py        # Home, login, pending (new)
│   └── board.py            # Board view + attachments (new)
└── api/
    └── board.py            # Move + export API (new)

templates/
├── pages/
│   ├── login.html          # Google OAuth login (new)
│   ├── pending.html        # Pending approval (new)
│   ├── dashboard.html      # Board grid (new)
│   └── board.html          # Kanban board (new)
└── partials/
    ├── kanban_card.html    # Board card on dashboard (new)
    ├── column.html         # With role checks (new)
    ├── card.html           # With PDF icon (new)
    ├── pdf_viewer.html     # PDF viewer modal (new)
    └── upload_modal.html   # Upload modal (new)

static/
├── css/app.css             # Full CSS (updated)
├── js/
│   ├── dashboard.js        # New Board button (new)
│   └── board.js            # Add Column + PDF handlers (new)
└── islands/
    └── kanban-board.js     # Drag-drop island (new)

migrations/                 # Generated by feather db migrate
```

## What You Learned

- **Multiple boards per user** with Kanban model hierarchy
- **Dashboard home page** with 2-column grid layout
- **Role-based access control** (admin, user, viewer)
- **`@auth_required`** decorator for protected routes
- **`current_user`** for accessing logged-in user and role
- **Kanban-scoped data** with `kanban_id` foreign keys
- **Google OAuth** configuration
- **File storage** with GCS for PDF attachments
- **Admin panel** access (admin role only)
- **PDF generation** with reportlab (inline)
- **Modal dialogs** for PDF viewing and upload

## Next Tutorial

In [Tutorial 5: SaaS Kanban](05-saas-kanban.md), you'll add:
- Multi-tenant architecture
- Domain-based tenant isolation
- Platform admin for managing tenants
- Tenant-scoped data and queries
