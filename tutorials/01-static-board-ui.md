# Tutorial 1: Static Board UI

## Kanban Tutorial Series

> This is part 1 of a 5-part series building a production Kanban app.
> [View series overview](index.md)

| Part | Title | Status |
|------|-------|--------|
| 1 | Static Board UI | **You are here** |
| 2 | Persistent Boards | |
| 3 | Drag-and-Drop | |
| 4 | Personal Kanban | |
| 5 | SaaS Kanban | |

## This Tutorial

**What you'll build:** A static Kanban board UI with hardcoded columns and cards.

**Features covered:**
- Feather project scaffolding (minimal, no database)
- Jinja2 templates and template inheritance
- Component macros (icons)
- Tailwind CSS styling
- Vite hot module replacement

## Prerequisites

**Required:**
- Python 3.11+
- Feather CLI installed

**No database required** - this tutorial uses no persistence.

## Create the Project

```bash
feather new kanban
```

You'll see interactive prompts:

```
Project Configuration

App Type
  Simple       - Static pages, no authentication
  Single-tenant - One organization, user accounts
  Multi-tenant  - Multiple organizations (SaaS)

  Select type [simple]:
```

Press Enter to accept `simple` (the default).

```
Database
  Type [none]:
```

Press Enter to accept `none` (the default). We'll add a database in Tutorial 2.

Then start the dev server:

```bash
cd kanban
source venv/bin/activate
feather dev
```

Open http://localhost:5173 - you should see the welcome page.

---

## Build Steps

### Step 1: Understand the Project Structure

Your scaffolded project has:

```
kanban/
├── app.py                # Entry point
├── config.py             # Configuration
├── routes/
│   ├── api/              # API routes (empty for now)
│   └── pages/
│       └── home.py       # Home page route
├── templates/
│   ├── base.html         # Base template with Vite/HTMX
│   ├── components/       # For custom components
│   ├── partials/         # HTMX response fragments
│   └── pages/
│       └── home.html     # Home page template
├── static/
│   ├── css/app.css       # Tailwind entry point
│   ├── js/               # Shared JavaScript
│   └── islands/          # Interactive JS components
├── tests/                # Test files
├── package.json          # Vite + Tailwind deps
└── vite.config.js        # Vite configuration
```

**Key concepts:**
- `routes/pages/` → Page routes (auto-discovered)
- `routes/api/` → API routes (auto-discovered)
- `templates/pages/` → Full page templates
- `templates/partials/` → HTMX response fragments
- `static/css/app.css` → Tailwind styles with `@apply`

### Step 2: Create the Board Route

Replace `routes/pages/home.py`:

```python
"""Kanban board page route."""

from flask import render_template
from feather import page


@page.get("/")
def board():
    """Render the Kanban board."""
    # Hardcoded data for now - we'll add persistence in Tutorial 2
    columns = [
        {
            "id": "1",
            "title": "To Do",
            "cards": [
                {"id": "1", "title": "Research competitors"},
                {"id": "2", "title": "Write project brief"},
            ]
        },
        {
            "id": "2",
            "title": "In Progress",
            "cards": [
                {"id": "3", "title": "Design mockups"},
            ]
        },
        {
            "id": "3",
            "title": "Done",
            "cards": []
        }
    ]
    return render_template("pages/board.html", columns=columns)
```

### Step 3: Create the Board Template

Create `templates/pages/board.html`:

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

**Template concepts:**
- `{% extends "base.html" %}` - Inherit from base template
- `{% from "components/icon.html" import icon %}` - Import the icon macro
- `{{ icon("view_kanban") }}` - Render a Material Icon
- `{% for ... %}` - Loop through data
- `{% else %}` after for - Shown when list is empty

### Step 4: Add CSS Classes

Add to `static/css/app.css` (after the existing content):

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

**Why not inline Tailwind classes?**

Feather recommends CSS classes with `@apply` instead of inline Tailwind:
- Templates stay clean and readable
- Styles are reusable across templates
- Easier to maintain and refactor
- Clear separation of concerns

### Step 5: Run and View

If not already running:
```bash
feather dev
```

Open http://localhost:5173 - you should see your Kanban board!

**Try the hot reload:**
1. Change a column title in `home.py`
2. Watch the browser refresh automatically
3. Change a color in `app.css`
4. Watch the CSS update instantly (no refresh)

## Checkpoint

Your app should now have:
- A Kanban board with 3 columns
- Cards displayed in columns
- Styled with Tailwind CSS
- Material icons for visual elements

**The buttons don't work yet** - that's what we'll add in the next tutorial!

**Files you modified:**
```
routes/pages/home.py          # Board route with hardcoded data
templates/pages/board.html    # Board template (new file)
static/css/app.css            # Added Kanban CSS classes
```

## What You Learned

- **Project scaffolding** with `feather new`
- **Template inheritance** with `extends` and `block`
- **Component macros** with `from ... import`
- **Material icons** with the `icon` macro
- **Tailwind CSS** with `@apply` in CSS classes
- **Jinja2 loops** with `{% for %}` and `{% else %}`

## Next Tutorial

In [Tutorial 2: Persistent Boards](02-persistent-boards.md), you'll add:
- Database for persistence (SQLite or PostgreSQL)
- Models for columns and cards
- HTMX for adding and deleting without page reloads
- Server-side partials for dynamic updates
