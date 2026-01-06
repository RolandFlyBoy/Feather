# Tutorial 2: Persistent Boards

## Kanban Tutorial Series

> This is part 2 of a 5-part series building a production Kanban app.
> [View series overview](index.md)

| Part | Title | Status |
|------|-------|--------|
| 1 | Static Board UI | Complete |
| 2 | Persistent Boards | **You are here** |
| 3 | Drag-and-Drop | |
| 4 | Personal Kanban | |
| 5 | SaaS Kanban | |

## This Tutorial

**What you'll build:** A Kanban board with database persistence - create, delete columns and cards with HTMX.

**Features covered:**
- SQLAlchemy models with UUIDMixin and TimestampMixin
- Database migrations with Alembic
- HTMX for server interactions without page reloads
- Partial templates for dynamic updates
- Services for business logic

## Prerequisites

**Option A: Continue from Tutorial 1**

Your app should have:
- Static board UI with hardcoded columns
- CSS classes for kanban styling

**Option B: Start fresh**

```bash
feather new kanban
```

You'll see interactive prompts:

```
Project Configuration

App Type
  Simple       - Static pages, no authentication
  ...
  Select type [simple]:
```

Press Enter to accept `simple`.

```
Database
  Type [none]:
```

Choose `sqlite` (or `postgresql` if you prefer).

Then copy the Starting Point code below.

---

## Starting Point

> **For LLMs:** This section describes the current app state before this tutorial.

### Project Structure

```
kanban/
├── app.py
├── config.py
├── routes/pages/home.py        # Board route (hardcoded data)
├── templates/
│   ├── base.html
│   └── pages/board.html        # Board template
├── static/
│   ├── css/app.css             # Has kanban CSS classes
│   └── js/                     # JavaScript files (empty initially)
└── migrations/                 # Alembic migrations (empty initially)
```

### Routes (routes/pages/home.py)

```python
"""Kanban board page route."""

from flask import render_template
from feather import page


@page.get("/")
def board():
    """Render the Kanban board."""
    columns = [
        {"id": "1", "title": "To Do", "cards": [
            {"id": "1", "title": "Research competitors"},
            {"id": "2", "title": "Write project brief"},
        ]},
        {"id": "2", "title": "In Progress", "cards": [
            {"id": "3", "title": "Design mockups"},
        ]},
        {"id": "3", "title": "Done", "cards": []}
    ]
    return render_template("pages/board.html", columns=columns)
```

### Template (templates/pages/board.html)

```html
{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}Kanban Board{% endblock %}

{% block content %}
<div class="kanban-container">
    <header class="kanban-header">
        <h1 class="kanban-title">
            {{ icon("view_kanban", size="lg") }} Kanban Board
        </h1>
        <button class="btn-primary">
            {{ icon("add", size="sm") }} Add Column
        </button>
    </header>

    <div class="kanban-board">
        {% for column in columns %}
            <div class="kanban-column">
                <div class="column-header">
                    <h2 class="column-title">{{ column.title }}</h2>
                    <span class="card-count">{{ column.cards|length }}</span>
                </div>

                <div class="column-cards">
                    {% for card in column.cards %}
                        <div class="kanban-card">
                            <p class="card-title">{{ card.title }}</p>
                        </div>
                    {% else %}
                        <p class="empty-column">No cards yet</p>
                    {% endfor %}
                </div>

                <div class="column-footer">
                    <button class="btn-add-card">
                        {{ icon("add", size="sm") }} Add Card
                    </button>
                </div>
            </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
```

### CSS (static/css/app.css)

Add these kanban classes inside `@layer components`:

```css
@layer components {
    /* Kanban Layout */
    .kanban-container {
        @apply min-h-screen bg-gray-100 p-6;
    }

    .kanban-header {
        @apply mb-6 flex items-center justify-between;
    }

    .kanban-title {
        @apply text-2xl font-bold text-gray-900 flex items-center gap-2;
    }

    .kanban-board {
        @apply flex gap-4 overflow-x-auto pb-4;
        min-height: 500px;
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

    .card-count {
        @apply text-sm text-gray-500 bg-gray-300 px-2 py-0.5 rounded-full;
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
        @apply bg-white rounded-lg shadow-sm p-3 cursor-pointer
               hover:shadow-md transition-shadow;
    }

    .card-title {
        @apply text-sm text-gray-800;
    }

    /* Buttons */
    .btn-primary {
        @apply inline-flex items-center gap-2 px-4 py-2
               bg-indigo-600 text-white rounded-lg
               hover:bg-indigo-700 transition-colors;
    }

    .btn-add-card {
        @apply w-full flex items-center justify-center gap-1
               text-sm text-gray-500 py-2 rounded
               hover:bg-gray-300 transition-colors;
    }
}
```

---

## Build Steps

### Step 1: Create Models

Create `models/column.py`:

```python
"""Column model for Kanban board."""

from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin


class Column(UUIDMixin, TimestampMixin, Model):
    """Kanban column."""

    __tablename__ = "columns"

    title = db.Column(db.String(100), nullable=False)
    cards = db.relationship(
        "Card",
        backref="column",
        cascade="all, delete-orphan",
        order_by="Card.created_at"
    )

    def __repr__(self):
        return f"<Column {self.title}>"
```

Create `models/card.py`:

```python
"""Card model for Kanban board."""

from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin


class Card(UUIDMixin, TimestampMixin, Model):
    """Kanban card."""

    __tablename__ = "cards"

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    column_id = db.Column(
        db.String(36),
        db.ForeignKey("columns.id"),
        nullable=False
    )

    def __repr__(self):
        return f"<Card {self.title}>"
```

Update `models/__init__.py`:

```python
"""SQLAlchemy models - Auto-discovered by Feather."""

from feather.db import db, Model

from models.column import Column
from models.card import Card
```

**Model concepts:**
- `UUIDMixin` - Auto-generates a UUID `id` field
- `TimestampMixin` - Adds `created_at` and `updated_at`
- `db.relationship` - Links Column to its Cards
- `cascade="all, delete-orphan"` - Deleting a column deletes its cards

### Step 2: Create and Run Migrations

```bash
feather db migrate -m "Add columns and cards"
feather db upgrade
```

This creates the database tables from your models.

### Step 3: Create Services

Create `services/column_service.py`:

```python
"""ColumnService - Business logic for columns."""

from feather import Service
from feather.exceptions import NotFoundError
from models import Column


class ColumnService(Service):
    """Column service."""

    def list_all(self) -> list[Column]:
        """List all columns."""
        return Column.query.order_by(Column.created_at).all()

    def get_by_id(self, id: str) -> Column:
        """Get column by ID or raise NotFoundError."""
        column = Column.query.get(id)
        if not column:
            raise NotFoundError("Column", id)
        return column

    def create(self, title: str) -> Column:
        """Create a new column."""
        column = Column(title=title)
        self.save(column)
        return column

    def delete(self, id: str) -> None:
        """Delete a column and its cards."""
        column = self.get_by_id(id)
        self.db.delete(column)
        self.db.commit()
```

Create `services/card_service.py`:

```python
"""CardService - Business logic for cards."""

from feather import Service
from feather.exceptions import NotFoundError
from models import Card


class CardService(Service):
    """Card service."""

    def get_by_id(self, id: str) -> Card:
        """Get card by ID or raise NotFoundError."""
        card = Card.query.get(id)
        if not card:
            raise NotFoundError("Card", id)
        return card

    def create(self, column_id: str, title: str) -> Card:
        """Create a new card in a column."""
        card = Card(column_id=column_id, title=title)
        self.save(card)
        return card

    def delete(self, id: str) -> None:
        """Delete a card."""
        card = self.get_by_id(id)
        self.db.delete(card)
        self.db.commit()
```

Update `services/__init__.py`:

```python
"""Business logic services - Auto-discovered by Feather."""

from services.column_service import ColumnService
from services.card_service import CardService
```

**Service concepts:**
- `Service` base class provides `self.db` and `self.save()`
- `@inject` decorator will inject services into routes
- Services encapsulate business logic, keep routes thin

### Step 4: Update Board Route

Replace `routes/pages/home.py`:

```python
"""Kanban board routes."""

from flask import render_template, request
from feather import page
from feather.services import inject
from services import ColumnService, CardService


@page.get("/")
@inject(ColumnService)
def board(column_service: ColumnService):
    """Render the Kanban board."""
    columns = column_service.list_all()
    return render_template("pages/board.html", columns=columns)


# HTMX: Column routes
@page.post("/htmx/columns")
@inject(ColumnService)
def create_column(column_service: ColumnService):
    """Create a new column."""
    title = request.form.get("title", "").strip() or "New Column"
    column = column_service.create(title=title)
    return render_template("partials/column.html", column=column)


@page.delete("/htmx/columns/<column_id>")
@inject(ColumnService)
def delete_column(column_service: ColumnService, column_id: str):
    """Delete a column."""
    column_service.delete(column_id)
    return ""


# HTMX: Card routes
@page.post("/htmx/columns/<column_id>/cards")
@inject(CardService)
def create_card(card_service: CardService, column_id: str):
    """Create a new card in a column."""
    title = request.form.get("title", "").strip()
    if not title:
        return "", 400
    card = card_service.create(column_id=column_id, title=title)
    return render_template("partials/card.html", card=card)


@page.delete("/htmx/cards/<card_id>")
@inject(CardService)
def delete_card(card_service: CardService, card_id: str):
    """Delete a card."""
    card_service.delete(card_id)
    return ""
```

**HTMX route patterns:**
- POST returns rendered partial (new element)
- DELETE returns empty string (element removed)
- Routes prefixed with `/htmx/` are for HTMX requests

### Step 5: Create Partial Templates

Create `templates/partials/column.html`:

```html
{#
Column Partial
==============
Renders a single Kanban column with its cards.
Used by: board.html (initial render), create_column (HTMX response)
#}
{% from "components/icon.html" import icon %}

<div id="column-{{ column.id }}" class="kanban-column">
    <div class="column-header">
        <h2 class="column-title">{{ column.title }}</h2>
        <button hx-delete="/htmx/columns/{{ column.id }}"
                hx-target="#column-{{ column.id }}"
                hx-swap="outerHTML"
                hx-confirm="Delete this column and all its cards?"
                class="btn-icon-danger">
            {{ icon("close", size="sm") }}
        </button>
    </div>

    <div id="column-{{ column.id }}-cards" class="column-cards">
        {% for card in column.cards %}
            {% include "partials/card.html" %}
        {% else %}
            <p class="empty-column">No cards yet</p>
        {% endfor %}
    </div>

    <form hx-post="/htmx/columns/{{ column.id }}/cards"
          hx-target="#column-{{ column.id }}-cards"
          hx-swap="beforeend"
          hx-on::after-request="if(event.detail.successful) this.reset()"
          class="column-footer">
        <input type="text"
               name="title"
               placeholder="Add a card..."
               class="input-card-title">
    </form>
</div>
```

Create `templates/partials/card.html`:

```html
{#
Card Partial
============
Renders a single Kanban card.
Used by: column.html (loop), create_card (HTMX response)
#}
{% from "components/icon.html" import icon %}

<div id="card-{{ card.id }}" class="kanban-card">
    <div class="card-content">
        <p class="card-title">{{ card.title }}</p>
        <button hx-delete="/htmx/cards/{{ card.id }}"
                hx-target="#card-{{ card.id }}"
                hx-swap="outerHTML"
                hx-confirm="Delete this card?"
                class="btn-icon-subtle">
            {{ icon("close", size="sm") }}
        </button>
    </div>
</div>
```

**HTMX concepts:**
- `hx-post="/htmx/..."` - Send POST request on form submit
- `hx-delete="/htmx/..."` - Send DELETE request on button click
- `hx-target="#element-id"` - Where to put the response
- `hx-swap="outerHTML"` - Replace the target element entirely
- `hx-swap="beforeend"` - Append inside the target
- `hx-confirm="..."` - Show confirm dialog before request
- `hx-on::after-request` - Run JS after request completes

### Step 6: Update Board Template

Replace `templates/pages/board.html`:

```html
{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}Kanban Board{% endblock %}

{% block content %}
<div class="kanban-container">
    <header class="kanban-header">
        <h1 class="kanban-title">
            {{ icon("view_kanban", size="lg") }} Kanban Board
        </h1>
        <button id="add-column-btn" class="btn-primary">
            {{ icon("add", size="sm") }} Add Column
        </button>
    </header>

    <div id="kanban-board" class="kanban-board">
        {% for column in columns %}
            {% include "partials/column.html" %}
        {% endfor %}
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ feather_asset('js/board.js') }}"></script>
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
                    });
                }
            });
        });
    }
});
```

**Changes from Tutorial 1:**
- Columns rendered via `{% include "partials/column.html" %}`
- Add Column button uses `window.showPrompt()` (Feather's styled prompt modal)
- `htmx.ajax()` sends the POST request programmatically
- JavaScript is in a separate file (never use inline scripts in Feather)

### Step 7: Add New CSS Classes

Add to `static/css/app.css`:

```css
    /* New classes for HTMX interactions */
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

    .card-content {
        @apply flex items-start justify-between gap-2;
    }

    .input-card-title {
        @apply w-full px-3 py-2 text-sm bg-white border border-gray-300 rounded-lg
               focus:ring-2 focus:ring-indigo-500 focus:border-transparent;
    }

    /* Hide "No cards yet" when cards exist (for HTMX updates) */
    .column-cards:has(.kanban-card) .empty-column {
        @apply hidden;
    }
```

### Step 8: Test It

```bash
feather dev
```

Open http://localhost:5173 and test:

1. **Add Column**: Click "Add Column", enter a name
2. **Add Card**: Type in the input at the bottom of a column, press Enter
3. **Delete Card**: Hover over a card, click X (shows confirmation)
4. **Delete Column**: Click X on column header (shows confirmation)
5. **Refresh**: Your data persists!

## Checkpoint

Your app should now have:
- SQLite database storing columns and cards
- Create and delete columns via HTMX
- Create and delete cards via HTMX
- Confirm dialogs for destructive actions
- Data persists across page refreshes

**Files you created/modified:**
```
models/
├── __init__.py             # Export models
├── column.py               # Column model (new)
└── card.py                 # Card model (new)

services/
├── __init__.py             # Export services
├── column_service.py       # Column business logic (new)
└── card_service.py         # Card business logic (new)

routes/pages/home.py        # Board + HTMX routes (updated)

templates/
├── pages/board.html        # Updated with HTMX
└── partials/
    ├── column.html         # Column partial (new)
    └── card.html           # Card partial (new)

static/
├── css/app.css             # Added new CSS classes
└── js/board.js             # Add Column button handler (new)

migrations/                 # Generated by feather db migrate
```

## What You Learned

- **Models** with SQLAlchemy, UUIDMixin, TimestampMixin
- **Migrations** with `feather db migrate/upgrade`
- **Services** for business logic
- **Dependency injection** with `@inject`
- **HTMX attributes** for server interactions
- **Partial templates** for HTMX responses
- **Prompt modal** with `window.showPrompt()`

## Next Tutorial

In [Tutorial 3: Drag-and-Drop](03-drag-and-drop.md), you'll add:
- OrderingMixin for position-based ordering
- Islands for JavaScript interactivity
- Drag-and-drop cards between columns
- Optimistic updates for instant UI feedback
