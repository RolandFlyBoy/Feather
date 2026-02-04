# Tutorial 3: Drag-and-Drop

## Kanban Tutorial Series

> This is part 3 of a 5-part series building a production Kanban app.
> [View series overview](index.md)

| Part | Title | Status |
|------|-------|--------|
| 1 | Static Board UI | Complete |
| 2 | Persistent Boards | Complete |
| 3 | Drag-and-Drop | **You are here** |
| 4 | Personal Kanban | |
| 5 | SaaS Kanban | |

## This Tutorial

**What you'll build:** Drag-and-drop cards between columns with optimistic updates.

**Features covered:**
- OrderingMixin for position-based ordering
- Islands for client-side JavaScript
- Built-in drag-drop support
- Optimistic updates with rollback
- API routes for JSON interactions

## Prerequisites

**Option A: Continue from Tutorial 2**

Your app should have:
- SQLite database with Column and Card models
- HTMX routes for create/delete operations
- Partial templates for columns and cards

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
├── models/
│   ├── __init__.py
│   ├── column.py
│   └── card.py
├── services/
│   ├── __init__.py
│   ├── column_service.py
│   └── card_service.py
├── routes/pages/home.py
├── templates/
│   ├── pages/board.html
│   └── partials/
│       ├── column.html
│       └── card.html
├── static/
│   ├── css/app.css
│   └── js/board.js           # Add Column button handler
└── migrations/
```

### Models

**models/column.py:**
```python
from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin

class Column(UUIDMixin, TimestampMixin, Model):
    __tablename__ = "columns"
    title = db.Column(db.String(100), nullable=False)
    cards = db.relationship("Card", backref="column", cascade="all, delete-orphan",
                            order_by="Card.created_at")
```

**models/card.py:**
```python
from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin

class Card(UUIDMixin, TimestampMixin, Model):
    __tablename__ = "cards"
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    column_id = db.Column(db.String(36), db.ForeignKey("columns.id"), nullable=False)
```

### Services

**services/column_service.py:**
```python
from feather import Service
from feather.exceptions import NotFoundError
from models import Column

class ColumnService(Service):
    def list_all(self) -> list[Column]:
        return Column.query.order_by(Column.created_at).all()

    def get_by_id(self, id: str) -> Column:
        column = Column.query.get(id)
        if not column:
            raise NotFoundError("Column", id)
        return column

    def create(self, title: str) -> Column:
        column = Column(title=title)
        self.save(column)
        return column

    def delete(self, id: str) -> None:
        column = self.get_by_id(id)
        self.db.delete(column)
        self.db.commit()
```

**services/card_service.py:**
```python
from feather import Service
from feather.exceptions import NotFoundError
from models import Card

class CardService(Service):
    def get_by_id(self, id: str) -> Card:
        card = Card.query.get(id)
        if not card:
            raise NotFoundError("Card", id)
        return card

    def create(self, column_id: str, title: str) -> Card:
        card = Card(column_id=column_id, title=title)
        self.save(card)
        return card

    def delete(self, id: str) -> None:
        card = self.get_by_id(id)
        self.db.delete(card)
        self.db.commit()
```

### Routes (routes/pages/home.py)

```python
from flask import render_template, request
from feather import page
from feather.services import inject
from services import ColumnService, CardService

@page.get("/")
@inject(ColumnService)
def board(column_service: ColumnService):
    columns = column_service.list_all()
    return render_template("pages/board.html", columns=columns)

@page.post("/htmx/columns")
@inject(ColumnService)
def create_column(column_service: ColumnService):
    title = request.form.get("title", "").strip() or "New Column"
    column = column_service.create(title=title)
    return render_template("partials/column.html", column=column)

@page.delete("/htmx/columns/<column_id>")
@inject(ColumnService)
def delete_column(column_service: ColumnService, column_id: str):
    column_service.delete(column_id)
    return ""

@page.post("/htmx/columns/<column_id>/cards")
@inject(CardService)
def create_card(card_service: CardService, column_id: str):
    title = request.form.get("title", "").strip()
    if not title:
        return "", 400
    card = card_service.create(column_id=column_id, title=title)
    return render_template("partials/card.html", card=card)

@page.delete("/htmx/cards/<card_id>")
@inject(CardService)
def delete_card(card_service: CardService, card_id: str):
    card_service.delete(card_id)
    return ""
```

### Templates

**templates/pages/board.html:**
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
        <div class="kanban-header-right">
            <button id="add-column-btn" class="btn-primary">
                {{ icon("add", size="sm") }} Add Column
            </button>
            <button data-toggle-dark-mode class="dark-mode-toggle" title="Toggle dark mode">
                <span class="material-symbols-outlined icon-light">bedtime</span>
                <span class="material-symbols-outlined icon-dark">sunny</span>
            </button>
        </div>
    </header>

    <div id="kanban-board" class="kanban-board">
        {% for column in columns %}
            {% include "partials/column.html" %}
        {% endfor %}
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
```

**static/js/board.js:**
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

**templates/partials/column.html:**
```html
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
        <input type="text" name="title" placeholder="Add a card..." class="input-card-title">
    </form>
</div>
```

**templates/partials/card.html:**
```html
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

### CSS (static/css/app.css)

Contains cumulative CSS from Tutorials 1 and 2:

```css
@layer components {
    /* Dark Mode Toggle */
    .dark-mode-toggle {
        @apply p-2 rounded-lg text-gray-500 hover:bg-gray-200
               dark:text-gray-400 dark:hover:bg-gray-700 transition-colors;
    }

    .dark-mode-toggle .icon-light {
        @apply dark:hidden;
    }

    .dark-mode-toggle .icon-dark {
        @apply hidden dark:inline;
    }

    /* Kanban Layout */
    .kanban-container {
        @apply min-h-screen bg-gray-100 dark:bg-gray-900 p-6;
    }

    .kanban-header {
        @apply mb-6 flex items-center justify-between;
    }

    .kanban-header-right {
        @apply flex items-center gap-3;
    }

    .kanban-title {
        @apply text-2xl font-bold text-gray-900 dark:text-gray-100
               flex items-center gap-2;
    }

    .kanban-board {
        @apply flex gap-4 overflow-x-auto pb-4;
        min-height: 500px;
    }

    /* Columns */
    .kanban-column {
        @apply flex-shrink-0 w-72 bg-gray-200 dark:bg-gray-800
               rounded-lg p-3 flex flex-col;
    }

    .column-header {
        @apply flex items-center justify-between mb-3;
    }

    .column-title {
        @apply font-semibold text-gray-700 dark:text-gray-300;
    }

    .card-count {
        @apply text-sm text-gray-500 dark:text-gray-400
               bg-gray-300 dark:bg-gray-700 px-2 py-0.5 rounded-full;
    }

    .column-cards {
        @apply space-y-2 min-h-[100px] flex-1;
    }

    .column-footer {
        @apply mt-3 pt-3 border-t border-gray-300 dark:border-gray-600;
    }

    .empty-column {
        @apply text-sm text-gray-400 dark:text-gray-500 text-center py-4;
    }

    /* Cards */
    .kanban-card {
        @apply bg-white dark:bg-gray-700 rounded-lg shadow-sm p-3
               cursor-pointer hover:shadow-md transition-shadow;
    }

    .card-title {
        @apply text-sm text-gray-800 dark:text-gray-200;
    }

    .card-content {
        @apply flex items-start justify-between gap-2;
    }

    /* Buttons */
    .btn-primary {
        @apply inline-flex items-center gap-2 px-4 py-2
               bg-indigo-600 text-white rounded-lg
               hover:bg-indigo-700 transition-colors;
    }

    .btn-add-card {
        @apply w-full flex items-center justify-center gap-1
               text-sm text-gray-500 dark:text-gray-400 py-2 rounded
               hover:bg-gray-300 dark:hover:bg-gray-700 transition-colors;
    }

    .btn-icon-danger {
        @apply text-gray-400 dark:text-gray-500
               hover:text-red-600 dark:hover:text-red-400 transition-colors;
    }

    .btn-icon-subtle {
        @apply text-gray-300 dark:text-gray-600
               hover:text-red-600 dark:hover:text-red-400
               transition-colors opacity-0;
    }

    /* Show delete button when hovering card */
    .kanban-card:hover .btn-icon-subtle {
        @apply opacity-100;
    }

    /* Hide "No cards yet" when cards exist (for HTMX updates) */
    .column-cards:has(.kanban-card) .empty-column {
        @apply hidden;
    }

    /* Inputs */
    .input-card-title {
        @apply w-full px-3 py-2 text-sm bg-white dark:bg-gray-700
               border border-gray-300 dark:border-gray-600 rounded-lg
               dark:text-gray-100 dark:placeholder-gray-400
               focus:ring-2 focus:ring-indigo-500 focus:border-transparent;
    }
}
```

---

## Build Steps

### Step 1: Add OrderingMixin to Models

OrderingMixin adds a `position` field and methods for reordering.

Update `models/column.py`:

```python
"""Column model for Kanban board."""

from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin, OrderingMixin


class Column(UUIDMixin, TimestampMixin, OrderingMixin, Model):
    """Kanban column with position-based ordering."""

    __tablename__ = "columns"

    title = db.Column(db.String(100), nullable=False)
    cards = db.relationship(
        "Card",
        backref="column",
        cascade="all, delete-orphan",
        order_by="Card.position"  # Changed from created_at
    )

    def __repr__(self):
        return f"<Column {self.title}>"
```

Update `models/card.py`:

```python
"""Card model for Kanban board."""

from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin, OrderingMixin


class Card(UUIDMixin, TimestampMixin, OrderingMixin, Model):
    """Kanban card with position scoped per column."""

    __tablename__ = "cards"
    __ordering_scope__ = ["column_id"]  # Position is unique per column

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

**OrderingMixin provides:**
- `position` column (integer)
- `insert_at_end()` - Set position to max + 1
- `move_to(n)` - Move to position n, shifting others
- `query_ordered()` - Query items sorted by position
- `reorder_all()` - Fix gaps in positions
- `get_max_position()` - Get highest position

**`__ordering_scope__`** makes position unique per column (card positions restart at 0 for each column).

### Step 2: Run Migration

```bash
feather db migrate -m "Add position to columns and cards"
feather db upgrade
```

### Step 3: Update Services

Update `services/column_service.py`:

```python
"""ColumnService - Business logic for columns."""

from feather import Service
from feather.exceptions import NotFoundError
from models import Column


class ColumnService(Service):
    """Column service."""

    def list_all(self) -> list[Column]:
        """List all columns in order."""
        return Column.query_ordered().all()  # Changed to use ordering

    def get_by_id(self, id: str) -> Column:
        """Get column by ID or raise NotFoundError."""
        column = Column.query.get(id)
        if not column:
            raise NotFoundError("Column", id)
        return column

    def create(self, title: str) -> Column:
        """Create a new column at the end."""
        column = Column(title=title)
        column.insert_at_end()  # Add at end
        self.save(column)
        return column

    def delete(self, id: str) -> None:
        """Delete a column and its cards."""
        column = self.get_by_id(id)
        self.db.delete(column)
        self.db.commit()
        # Reorder remaining columns
        Column.reorder_all()
        self.db.commit()
```

Update `services/card_service.py`:

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
        """Create a new card at the end of a column."""
        card = Card(column_id=column_id, title=title)
        card.insert_at_end()  # Add at end of column
        self.save(card)
        return card

    def delete(self, id: str) -> None:
        """Delete a card and reorder remaining cards."""
        card = self.get_by_id(id)
        column_id = card.column_id
        self.db.delete(card)
        self.db.commit()
        # Reorder remaining cards in the column
        Card.reorder_all(column_id=column_id)
        self.db.commit()

    def move(self, card_id: str, to_column_id: str, to_position: int) -> Card:
        """Move a card to a new position, possibly in a different column."""
        card = self.get_by_id(card_id)
        old_column_id = card.column_id

        # If moving to a different column
        if to_column_id != old_column_id:
            # Update column first
            card.column_id = to_column_id
            # Set position at end temporarily
            max_pos = Card.get_max_position(column_id=to_column_id)
            card.position = max_pos + 1
            self.db.commit()

            # Reorder old column
            Card.reorder_all(column_id=old_column_id)
            self.db.commit()

        # Move to specific position in target column
        card.move_to(to_position)
        self.db.commit()

        return card
```

### Step 4: Add API Route for Card Movement

Create `routes/api/board.py`:

```python
"""API routes for Kanban board."""

from flask import request
from feather import api
from feather.services import inject
from services import CardService


@api.post("/cards/move")
@inject(CardService)
def move_card(card_service: CardService):
    """Move a card to a new position."""
    data = request.get_json()
    card = card_service.move(
        card_id=data["cardId"],
        to_column_id=data["toColumnId"],
        to_position=data["toPosition"]
    )
    return {
        "success": True,
        "card": {"id": card.id, "position": card.position}
    }
```

**API vs HTMX routes:**
- HTMX routes return HTML partials
- API routes return JSON
- Drag-drop uses API (position data, not new HTML)

### Step 5: Create the Kanban Island

Create `static/islands/kanban-board.js`:

```javascript
/**
 * Kanban Board Island
 *
 * Handles drag-and-drop of cards between columns with optimistic updates.
 */
island("kanban-board", {
  draggable: {
    items: ".kanban-card",           // What can be dragged
    zones: ".column-cards",          // Where items can be dropped
    handle: ".drag-handle",          // Restrict drag to this element

    onDrop(item, zone, info, e) {
      // DOM is already moved by the drag-drop system
      // Now persist to server with optimistic update

      this.optimistic(
        // Optimistic: DOM already updated, nothing extra to do
        () => {},
        // API call to persist the change
        () => this.api.post("/api/cards/move", {
          cardId: info.itemId,
          toColumnId: info.toZoneId,
          toPosition: info.toIndex
        })
      ).catch(err => {
        console.error("Failed to move card:", err);
        // On failure, reload to get correct state
        window.location.reload();
      });
    }
  }
});
```

**Island concepts:**
- `island("name", config)` - Define an island
- `draggable` - Built-in drag-drop configuration
- `items` - CSS selector for draggable items
- `zones` - CSS selector for drop zones
- `handle` - Optional drag handle selector
- `onDrop` - Called after item is dropped
- `info` contains: `itemId`, `fromIndex`, `toIndex`, `fromZoneId`, `toZoneId`
- `this.optimistic()` - Optimistic update with rollback on failure
- `this.api` - Built-in API helper with CSRF

### Step 6: Update Card Partial with Drag Handle

Update `templates/partials/card.html`:

```html
{#
Card Partial
============
Renders a single Kanban card (draggable).
#}
{% from "components/icon.html" import icon %}

<div id="card-{{ card.id }}"
     class="kanban-card"
     data-id="{{ card.id }}">
    <div class="card-content">
        <span class="drag-handle">
            {{ icon("drag_indicator", size="sm") }}
        </span>
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

**Changes:**
- Added `data-id="{{ card.id }}"` - Islands uses this to identify items
- Added drag handle with `drag_indicator` icon

### Step 7: Update Column Partial

Update `templates/partials/column.html`:

```html
{#
Column Partial
==============
Renders a single Kanban column with its cards.
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

    <!-- Cards container (drop zone) - needs data-id for Islands -->
    <div id="column-{{ column.id }}-cards"
         class="column-cards"
         data-id="{{ column.id }}">
        {% for card in column.cards %}
            {% include "partials/card.html" %}
        {% else %}
            <p class="empty-column empty-placeholder">No cards yet</p>
        {% endfor %}
    </div>

    <form hx-post="/htmx/columns/{{ column.id }}/cards"
          hx-target="#column-{{ column.id }}-cards"
          hx-swap="beforeend"
          hx-on::after-request="if(event.detail.successful) { this.reset(); this.closest('.kanban-column').querySelector('.empty-placeholder')?.remove(); }"
          class="column-footer">
        <input type="text"
               name="title"
               placeholder="Add a card..."
               class="input-card-title">
    </form>
</div>
```

**Changes:**
- Added `data-id="{{ column.id }}"` to `.column-cards` - Islands uses this for drop zones
- Added `empty-placeholder` class to remove "No cards yet" when adding a card
- Updated `hx-on::after-request` to remove the placeholder

### Step 8: Update Board Template

Update `templates/pages/board.html`:

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
        <div class="kanban-header-right">
            <button id="add-column-btn" class="btn-primary">
                {{ icon("add", size="sm") }} Add Column
            </button>
            <button data-toggle-dark-mode class="dark-mode-toggle" title="Toggle dark mode">
                <span class="material-symbols-outlined icon-light">bedtime</span>
                <span class="material-symbols-outlined icon-dark">sunny</span>
            </button>
        </div>
    </header>

    <!-- Add data-island to enable the kanban-board island -->
    <div data-island="kanban-board" class="kanban-board-wrapper">
        <div id="kanban-board" class="kanban-board">
            {% for column in columns %}
                {% include "partials/column.html" %}
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
{% else %}
<script src="{{ feather_asset('islands/kanban-board') }}"></script>
{% endif %}
{% endblock %}
```

**Changes:**
- Wrapped board in `data-island="kanban-board"` div
- Added `{% block islands %}` to load the island script
- Debug mode loads from Vite dev server (HMR), production loads built asset
- Note: `board.js` is already included via `{% block scripts %}` from Tutorial 2

### Step 9: Add Drag-Drop CSS

> **Note:** The scaffolded `app.css` already includes base `.dragging`, `.drag-over`, and `.feather-drop-placeholder` styles. The CSS below adds Kanban-specific overrides (`.kanban-card.dragging`, `.column-cards.drag-over`) that take precedence. Add these styles inside the existing `@layer components { }` block, after the card/button styles.

Add to `static/css/app.css`:

```css
    /* Drag handle */
    .drag-handle {
        @apply text-gray-300 dark:text-gray-600
               hover:text-gray-500 dark:hover:text-gray-400 cursor-grab;
    }

    /* Dragging state (added by Islands) */
    .kanban-card.dragging {
        @apply opacity-50 shadow-lg;
    }

    /* Drop zone hover state (added by Islands) */
    .column-cards.drag-over {
        @apply bg-gray-300 dark:bg-gray-700 ring-1 ring-indigo-400 ring-inset;
    }

    /* Drop placeholder (added by Islands) */
    .feather-drop-placeholder {
        @apply h-0.5 bg-indigo-400 rounded my-1;
    }

    /* Board wrapper for island */
    .kanban-board-wrapper {
        @apply overflow-x-auto;
    }
```

**CSS classes added automatically by Islands:**
- `.dragging` - Added to item being dragged
- `.drag-over` - Added to zone being dragged over
- `.feather-drop-placeholder` - Visual indicator for drop position

### Step 10: Test It

```bash
feather dev
```

Open http://localhost:5173 and test:

1. **Drag a card** - Grab the 6-dot handle and drag
2. **Reorder within column** - Drop above or below other cards
3. **Move to another column** - Drag to a different column
4. **Optimistic updates** - Card moves instantly, persists in background
5. **Refresh** - Positions are saved!

## Checkpoint

Your app should now have:
- Position-based ordering for columns and cards
- Drag-and-drop cards between columns
- Visual feedback during drag (opacity, placeholder)
- Optimistic updates (instant UI, background persist)
- Rollback on server failure

**Files you created/modified:**
```
models/
├── column.py               # Added OrderingMixin (updated)
└── card.py                 # Added OrderingMixin + scope (updated)

services/
├── column_service.py       # Added ordering methods (updated)
└── card_service.py         # Added move() method (updated)

routes/
├── pages/home.py           # HTMX routes (unchanged)
└── api/board.py            # API route for move (new)

templates/
├── pages/board.html        # Added island wrapper (updated)
└── partials/
    ├── column.html         # Added data-id (updated)
    └── card.html           # Added drag handle, data-id (updated)

static/
├── css/app.css             # Added drag-drop styles (updated)
└── islands/
    └── kanban-board.js     # Drag-drop island (new)

migrations/                 # Generated by feather db migrate
```

## What You Learned

- **OrderingMixin** for position-based sorting
- **`__ordering_scope__`** for per-parent positions
- **Islands** for client-side JavaScript
- **Built-in drag-drop** with `draggable` config
- **Optimistic updates** with `this.optimistic()`
- **API routes** returning JSON
- **Debug vs production** island loading

## Next Tutorial

In [Tutorial 4: Personal Kanban](04-personal-kanban.md), you'll add:
- Google OAuth authentication
- Role-based access control (admin, viewer)
- File attachments with Google Cloud Storage
- PDF export with background jobs
- Admin panel for user management
