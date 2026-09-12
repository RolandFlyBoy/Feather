<h1 align="center">
  <img src="https://raw.githubusercontent.com/RolandFlyBoy/Feather/main/feather/static/favicon.svg" alt="" width="64" height="64" style="vertical-align: middle;">
  Feather
</h1>

<p align="center">
  <strong>A Python web framework built for AI-assisted development.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/feather-framework/"><img alt="PyPI" src="https://img.shields.io/pypi/v/feather-framework?color=2563eb"></a>
  <a href="https://pypi.org/project/feather-framework/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/feather-framework?color=2563eb"></a>
  <a href="https://github.com/RolandFlyBoy/Feather/actions/workflows/test.yml"><img alt="Tests" src="https://github.com/RolandFlyBoy/Feather/actions/workflows/test.yml/badge.svg"></a>
  <a href="https://github.com/RolandFlyBoy/Feather/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-2563eb"></a>
</p>

<p align="center">
  <a href="https://docs.featherframework.org"><strong>Documentation</strong></a> &nbsp;·&nbsp;
  <a href="https://www.featherframework.org"><strong>Website</strong></a> &nbsp;·&nbsp;
  <a href="https://docs.featherframework.org/quickstart"><strong>Quickstart</strong></a> &nbsp;·&nbsp;
  <a href="https://docs.featherframework.org/tutorials/index"><strong>Tutorial</strong></a>
</p>

---

Flask handles the backend, Tailwind CSS the styling, HTMX the interactions that need the
server, and vanilla JavaScript the few that need the browser. Authentication, an admin
panel, background jobs, multi-tenancy and deployment are already written.

Every generated project carries a `CLAUDE.md` and an identical `AGENTS.md` describing the
conventions, and `feather check` enforces thirteen of them, reporting a file, a line and a
fix for each problem. An assistant writing a feature has somewhere to put each file and a
rule set to write it against, and you get a command that says whether it followed them.

## Install

```bash
pip install feather-framework
feather new myapp
cd myapp && feather dev
```

Requires Python 3.11+ and Node.js 22+.

## What's included

Every feature is optional, enabled when you create the project or added later.

| | |
| --- | --- |
| **Authentication** | Google OAuth, approval workflows, roles and permissions |
| **Admin panel** | User approvals, role changes, analytics and error logs |
| **Multi-tenancy** | Tenants by email domain, isolated at route, service and model layers |
| **Background jobs** | Thread pool with concurrency limits, or RQ on Redis |
| **Caching** | Function and response caching, memory or Redis |
| **File storage** | One interface over local files and Google Cloud Storage |
| **Email** | Transactional email through Resend |
| **Dark mode** | Cookie-persisted toggle on every page, including the admin |
| **Security headers** | CSP, HSTS and the rest, applied in production |
| **Rate limiting** | A decorator, or Flask-Limiter with Redis across workers |
| **Events** | Pub/sub with synchronous and background listeners |
| **Error logging** | Database-backed, tenant-scoped, with stack traces |
| **Health checks** | `/health`, `/health/live` and `/health/ready` |
| **Request tracking** | A unique ID per request, in headers and every log line |

## The frontend, in three layers

Start with **components** for anything static. Reach for **HTMX** when you need server data
without a page reload. Use **islands** only when state has to live in the browser. Most
features never get past the first two.

Read more in [How the frontend works](https://docs.featherframework.org/ui/overview).

## Documentation

Everything lives at **[docs.featherframework.org](https://docs.featherframework.org)**.

| | |
| --- | --- |
| [Quickstart](https://docs.featherframework.org/quickstart) | Scaffold a project and get the dev server running |
| [Kanban tutorial](https://docs.featherframework.org/tutorials/index) | Six parts, from a static page to a deployed SaaS, with the prompts to use |
| [Working with AI assistants](https://docs.featherframework.org/ai-assistants) | How the conventions and `feather check` fit together |
| [CLI reference](https://docs.featherframework.org/reference/cli) | Every command, grouped by what you are doing |
| [Configuration](https://docs.featherframework.org/reference/configuration) | Every key Feather reads, with its default |
| [Deployment](https://docs.featherframework.org/deployment/docker) | Docker and Caddy on one server, with automatic HTTPS |
| [Upgrading](https://docs.featherframework.org/reference/upgrading) | What to check when you bump the pin |

The tutorials are also in this repository, under [`tutorials/`](tutorials/), with every
code block written out.

## Contributing

```bash
git clone https://github.com/RolandFlyBoy/Feather.git
cd Feather
pipx install -e .
feather test --framework
```

The docs site is built from [`docs/`](docs/) in this repository, so a change to the
framework and a change to its documentation belong in the same pull request.

Bug reports from real applications are the most useful thing you can send.
[Open an issue](https://github.com/RolandFlyBoy/Feather/issues).

## License

MIT. See [LICENSE](LICENSE).
