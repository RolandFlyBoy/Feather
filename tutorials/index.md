# Kanban Tutorial Series

Build a production-ready Kanban board application while learning every major Feather feature.

## What You'll Build

A fully-featured Kanban board with:
- Drag-and-drop cards between columns
- Google OAuth authentication
- Role-based access control
- File attachments (GCS)
- PDF export
- Multi-tenant SaaS architecture
- A one-command deploy to your own domain, over HTTPS

## Series Overview

| Part | Title | What You'll Learn |
|------|-------|-------------------|
| 1 | [Static Board UI](01-static-board-ui.md) | Templates, Components, Tailwind CSS |
| 2 | [Persistent Boards](02-persistent-boards.md) | Models, HTMX, Partials |
| 3 | [Drag-and-Drop](03-drag-and-drop.md) | Islands, OrderingMixin, Optimistic Updates |
| 4 | [Personal Kanban](04-personal-kanban.md) | Auth, Admin Panel, GCS Storage, PDF Export |
| 5 | [SaaS Kanban](05-saas-kanban.md) | Multi-tenancy, Platform Admin |
| 6 | [Deploying](06-deploying.md) | Docker, Caddy, VPS setup, backups, CI/CD |

## How to Use These Tutorials

### For Human Readers

Follow the tutorials in order. Each builds on the previous, introducing new concepts incrementally. The code is explained as you go.

### For LLM-Assisted Building

Each tutorial includes a **Starting Point** section that describes the complete state of the app at the beginning of that tutorial. When working with an LLM:

1. Run `feather new kanban` with the options listed in the tutorial
2. Copy the entire tutorial into your LLM context
3. The Starting Point section gives the LLM full context of existing code
4. Ask the LLM to implement the Build Steps

### Starting Fresh at Any Tutorial

You don't need to complete previous tutorials. Each tutorial's Prerequisites section shows how to start fresh with the right CLI options, then copy the Starting Point code.

## CLI Options by Tutorial

| Tutorial | Database | Auth | Tenant | Jobs | Cache | Storage |
|----------|----------|------|--------|------|-------|---------|
| 1 | none | - | - | default | - | - |
| 2 | sqlite | - | - | default | - | - |
| 3 | (continues from Tutorial 2) | | | | | |
| 4 | postgresql | yes | single | yes | no | yes |
| 5 | postgresql | yes | multi | yes | no | yes |
| 6 | (deploys the app from Tutorial 4 or 5) | | | | | |

## Prerequisites

- Python 3.11+
- Feather CLI installed (`pip install -e .` from Feather repo, or `pipx install feather-framework`)
- For Tutorials 4-5: PostgreSQL running locally
- For Tutorials 4-5: Google OAuth and GCS credentials
- For Tutorial 6: a domain you control the DNS for, and a VPS you can SSH into

## Time Estimate

Each tutorial takes approximately 30-60 minutes to complete manually, or 10-15 minutes with LLM assistance.

---

Ready? Start with [Tutorial 1: Static Board UI](01-static-board-ui.md).
