"""File bodies for Feather's Docker deployment layout.

``feather new`` writes these files into a fresh project and ``feather docker
init`` writes the same set into an existing one, so the text lives here
exactly once.

The layout is one host running everything under ``docker compose``: Caddy
terminates TLS, ``web`` runs gunicorn, ``worker`` runs the RQ worker,
``db`` is Postgres and ``redis`` is Valkey. It is the layout the two
production Feather apps converged on after leaving a PaaS.

Substitution is deliberately ``str.replace`` and not ``str.format``: the
compose files, the Caddyfile and the deploy script are full of literal
braces (``${POSTGRES_PASSWORD}``, ``{$DOMAIN}``, ``{{.State.Health.Status}}``)
that ``format`` would try to interpret.
"""

import re
from pathlib import Path
from typing import Optional

#: The health endpoint every generated healthcheck points at. Feather
#: registers it in ``feather/core/health.py`` and it verifies the database,
#: unlike a route that only proves the process is listening.
HEALTH_PATH = "/health"

#: Container port. Matches ``feather start``'s default so ``docker run`` and
#: a bare ``feather start`` behave the same.
DEFAULT_PORT = 8000

#: Written into the project root, pointing at the installed Feather package's
#: templates so Tailwind can scan them. See ``feather/cli/_templates_link.py``.
TEMPLATES_LINK = ".feather-templates"

#: Keys docker-compose.yml sets on the container itself. They belong in
#: compose, not in the env file, and ``feather env check`` knows it.
COMPOSE_PROVIDED_KEYS = (
    "FLASK_CONFIG",
    "PORT",
    "WEB_CONCURRENCY",
    "DATABASE_URL",
    "REDIS_URL",
    "JOB_BACKEND",
    "JOB_SERIALIZER",
)

#: Keys docker-compose.yml reads from the *host* .env for interpolation.
COMPOSE_HOST_KEYS = ("DOMAIN", "POSTGRES_PASSWORD")


class DockerFile:
    """One generated file: where it goes, what is in it, and its mode."""

    def __init__(self, path: str, content: str, executable: bool = False):
        self.path = path
        self.content = content
        self.executable = executable

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<DockerFile {self.path}>"


def slugify(name: str) -> str:
    """Return a name usable as a Postgres role, database and compose project.

    Lowercase, ``[a-z0-9_]`` only, never starting with a digit.
    """
    slug = re.sub(r"[^a-z0-9_]+", "_", str(name).strip().lower()).strip("_")
    if not slug:
        slug = "app"
    if slug[0].isdigit():
        slug = f"app_{slug}"
    return slug


def _fill(text: str, **values) -> str:
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


# =============================================================================
# Dockerfile
# =============================================================================

_DOCKERFILE_HEAD = '''# =============================================================================
# {app_name} image.
#
#   docker build --target web    .   gunicorn (the default target)
{worker_build_comment}#
# Built by deploy/deploy.sh; `docker compose build` builds every target the
# compose file names.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Python base, shared by every runtime target.
# Pin the digest when you want byte-for-byte reproducible builds:
#   FROM python:3.11-slim@sha256:...
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PIP_NO_CACHE_DIR=1 \\
    PIP_DISABLE_PIP_VERSION_CHECK=1

# curl: the HEALTHCHECK below. The pango/gdk-pixbuf set: WeasyPrint, which
# Feather imports wherever an app renders PDFs. Drop them if yours never will.
RUN apt-get update && apt-get install -y --no-install-recommends \\
    curl \\
    libpango-1.0-0 \\
    libpangocairo-1.0-0 \\
    libgdk-pixbuf-2.0-0 \\
    libffi8 \\
    shared-mime-info \\
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN useradd --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Feather is installed on its own layer because the frontend stage copies its
# templates out of this image: Tailwind scans them for the class names the
# framework components use. Without that copy those styles are missing from
# the production CSS and every framework component renders unstyled.
COPY requirements.txt ./
RUN pip install "$(grep '^feather-framework' requirements.txt)"

# -----------------------------------------------------------------------------
# Stage 2: frontend build (Vite + Tailwind). No Node in the runtime image.
# -----------------------------------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build

# Commit package-lock.json: `npm ci` then installs exactly the locked tree.
# --ignore-scripts blocks install hooks, the cheapest supply-chain hardening
# there is. Without a lockfile this falls back to `npm install`.
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then \\
        npm ci --ignore-scripts; \\
    else \\
        npm install --no-audit --no-fund --ignore-scripts; \\
    fi

COPY vite.config.js ./
COPY static ./static
COPY templates ./templates
# Feather's own templates, from the Python base stage (there is no Python
# here). static/css/app.css lists this directory as a Tailwind @source.
COPY --from=base /usr/local/lib/python3.11/site-packages/feather/templates ./{templates_link}
RUN npm run build
'''

_DOCKERFILE_WORKER = '''
# -----------------------------------------------------------------------------
# Stage 3: worker target - background jobs (RQ).
# -----------------------------------------------------------------------------
FROM base AS worker

RUN pip install -r requirements.txt

COPY --chown=app:app . .
RUN mkdir -p logs && chown app:app logs

USER app

ENV FLASK_CONFIG=production \\
    JOB_BACKEND=rq

# --fork: one forked process per job, so a job that leaks or crashes cannot
# take the worker with it. `feather worker` defaults to SimpleWorker only on
# macOS, where fork() is unsafe; in Linux containers forking is the right mode.
CMD ["feather", "worker", "--fork"]
'''

_DOCKERFILE_WEB = '''
# -----------------------------------------------------------------------------
# Stage {web_stage_number}: web target. Last, so an untargeted build produces the web image.
# -----------------------------------------------------------------------------
FROM base AS web

RUN pip install -r requirements.txt

COPY --chown=app:app . .
COPY --from=frontend --chown=app:app /build/static/dist ./static/dist
RUN mkdir -p logs && chown app:app logs

USER app

# Compose overrides these; the defaults keep a plain `docker run` usable.
# `feather start` reads PORT and WEB_CONCURRENCY.
ENV PORT={port} \\
    WEB_CONCURRENCY=2 \\
    FLASK_CONFIG=production

EXPOSE {port}

# Container-level health, so deploy/deploy.sh can wait on Docker's own health
# status instead of guessing how long boot takes. {health_path} is Feather's
# own endpoint and it checks the database, so a container with a broken
# DATABASE_URL reports unhealthy instead of silently serving 500s.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \\
    CMD curl -fsS "http://127.0.0.1:${PORT}{health_path}" || exit 1

# Migrations deliberately do NOT run here: two web containers starting at once
# would race on `feather db upgrade`. deploy/deploy.sh runs them exactly once,
# against the new image, before swapping containers.
CMD ["feather", "start"]
'''


def render_dockerfile(app_name: str, *, worker: bool = True, port: int = DEFAULT_PORT) -> str:
    """Return the multi-stage Dockerfile body."""
    head = _fill(
        _DOCKERFILE_HEAD,
        app_name=app_name,
        templates_link=TEMPLATES_LINK,
        worker_build_comment=(
            "#   docker build --target worker .   background job worker\n" if worker else ""
        ),
    )
    body = head
    if worker:
        body += _DOCKERFILE_WORKER
    body += _fill(
        _DOCKERFILE_WEB,
        web_stage_number=4 if worker else 3,
        port=port,
        health_path=HEALTH_PATH,
    )
    return body


# =============================================================================
# .dockerignore
# =============================================================================

_DOCKERIGNORE = """# Python
venv/
env/
.venv/
__pycache__/
*.py[cod]
*.pyo
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/

# Node
node_modules/

# Git
.git/
.gitignore
.github/

# Environment and secrets - compose passes .env in at run time; it must
# never be baked into an image that gets pushed to a registry.
.env
.env.local
.env.*.local
prod.env

# Logs
logs/
*.log

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Build artifacts - the frontend stage rebuilds these
static/dist/

# Local storage backend
static/uploads/

# Tests (not needed in production)
tests/

# Symlink to the installed Feather package's templates. The frontend stage
# COPYs a real directory here from the base image; a host symlink pointing
# into venv/ would break the build.
{templates_link}
"""


def render_dockerignore() -> str:
    """Return the .dockerignore body."""
    return _fill(_DOCKERIGNORE, templates_link=TEMPLATES_LINK)


# =============================================================================
# docker-compose.yml (production)
# =============================================================================

_COMPOSE_HEAD = """# Production compose for {app_name}.
#
# Everything runs on one host. Only Caddy is exposed to the internet;
# Postgres and Redis are reachable only on the internal compose network.
#
# Secrets live in ./.env, which is never committed. Compose reads that file
# for the ${...} substitutions below, so POSTGRES_PASSWORD is written once.
# Start from .env.example.
#
#   Deploy:  ./deploy/deploy.sh
#   Backup:  ./deploy/backup.sh   (from cron)

name: {app_slug}

# Docker's json-file log driver grows until the disk fills. Cap it once here
# and anchor it onto every service.
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "20m"
    max-file: "3"

services:
  caddy:
    image: caddy:2
    restart: unless-stopped
    logging: *default-logging
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    environment:
      DOMAIN: ${DOMAIN:?set DOMAIN in .env}
    depends_on:
      - web

  web:
    build:
      context: .
      target: web
    restart: unless-stopped
    logging: *default-logging
    env_file: .env
    environment:
      FLASK_CONFIG: production
      PORT: {port}
      WEB_CONCURRENCY: 2
{job_env}{web_extra_env}    expose:
      - "{port}"
{web_depends}"""

_COMPOSE_WORKER = """
  worker:
    build:
      context: .
      target: worker
    restart: unless-stopped
    logging: *default-logging
    env_file: .env
    environment:
      FLASK_CONFIG: production
{job_env}{web_extra_env}{web_depends}"""

_COMPOSE_DB = """
  db:
    image: postgres:16
    restart: unless-stopped
    logging: *default-logging
    environment:
      POSTGRES_DB: {app_slug}
      POSTGRES_USER: {app_slug}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U {app_slug} -d {app_slug}"]
      interval: 10s
      timeout: 5s
      retries: 5
"""

_COMPOSE_REDIS = """
  # noeviction matters: RQ keeps job payloads in Redis, and evicting them
  # under memory pressure silently drops queued jobs.
  redis:
    image: valkey/valkey:8
    restart: unless-stopped
    logging: *default-logging
    command: valkey-server --maxmemory-policy noeviction --appendonly yes
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
"""


def _compose_service_env(database: bool, redis: bool, app_slug: str) -> str:
    lines = ""
    if database:
        lines += (
            "      DATABASE_URL: postgresql://{slug}:${{POSTGRES_PASSWORD}}@db:5432/{slug}\n"
        ).format(slug=app_slug)
    if redis:
        lines += "      REDIS_URL: redis://redis:6379/0\n"
    return lines


#: Both the web container (which enqueues) and the worker (which consumes)
#: have to name the same backend and the same serializer. Setting them only
#: on the worker was the easy misconfiguration: web would fall back to
#: config.py's default (the in-process thread backend) and the jobs it
#: "queued" would never reach the worker at all.
_JOB_ENV = """      JOB_BACKEND: rq
      # The producer and the worker MUST agree. json refuses to unpickle
      # arbitrary objects off Redis; see `feather security-check`.
      JOB_SERIALIZER: json
"""


def _compose_depends(database: bool, redis: bool) -> str:
    if not database and not redis:
        return ""
    block = "    depends_on:\n"
    if database:
        block += "      db:\n        condition: service_healthy\n"
    if redis:
        block += "      redis:\n        condition: service_healthy\n"
    return block


def render_compose(
    app_name: str,
    app_slug: str,
    *,
    database: bool = True,
    redis: bool = True,
    worker: bool = True,
    port: int = DEFAULT_PORT,
) -> str:
    """Return the production docker-compose.yml body."""
    extra_env = _compose_service_env(database, redis, app_slug)
    depends = _compose_depends(database, redis)
    job_env = _JOB_ENV if worker else ""

    body = _fill(
        _COMPOSE_HEAD,
        app_name=app_name,
        app_slug=app_slug,
        port=port,
        job_env=job_env,
        web_extra_env=extra_env,
        web_depends=depends,
    )
    if worker:
        body += _fill(
            _COMPOSE_WORKER, job_env=job_env, web_extra_env=extra_env, web_depends=depends
        )
    if database:
        body += _fill(_COMPOSE_DB, app_slug=app_slug)
    if redis:
        body += _COMPOSE_REDIS

    volumes = []
    if database:
        volumes.append("pgdata")
    if redis:
        volumes.append("redisdata")
    volumes += ["caddy_data", "caddy_config"]
    body += "\nvolumes:\n" + "".join(f"  {name}:\n" for name in volumes)
    return body


# =============================================================================
# docker-compose.dev.yml
# =============================================================================

_COMPOSE_DEV = """# Local dependencies only: Postgres and Redis on localhost.
#
# The app itself stays on the host so `feather dev` keeps Vite's hot reload:
#
#   docker compose -f docker-compose.dev.yml up -d
#   feather dev
#
# Start only what you need - `... up -d db` brings up Postgres alone. The
# ports and credentials match the DATABASE_URL and REDIS_URL in .env.

name: {app_slug}_dev

services:
  db:
    image: postgres:16
    restart: unless-stopped
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: {app_slug}
      POSTGRES_USER: {app_slug}
      POSTGRES_PASSWORD: {app_slug}
    volumes:
      - pgdata_dev:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U {app_slug}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: valkey/valkey:8
    restart: unless-stopped
    ports:
      - "6379:6379"
    command: valkey-server --maxmemory-policy noeviction

volumes:
  pgdata_dev:
"""


def render_compose_dev(app_slug: str) -> str:
    """Return the development docker-compose.dev.yml body."""
    return _fill(_COMPOSE_DEV, app_slug=app_slug)


# =============================================================================
# deploy/Caddyfile
# =============================================================================

_CADDYFILE = """# Caddy config for {app_name}.
#
# Caddy obtains and renews Let's Encrypt certificates automatically for every
# hostname in this file. DNS must point at this server first, or issuance
# fails and the site stays on the internal HTTP listener.
#
# {$DOMAIN} is read from the environment; docker-compose.yml passes DOMAIN
# through from ./.env.
#
# Header contract with the app (do not remove):
#   X-Forwarded-Proto / Host - Caddy sets these by default and Feather's
#     ProxyFix reads them. Without them Google OAuth builds an http://
#     redirect_uri and secure session cookies are dropped.
#   X-Real-IP - set below. Rate limiting and any geo logic read it.
#
# Health: {health_path} is Feather's own endpoint and it checks the database.
# Point any external uptime monitor at https://$DOMAIN{health_path}.

{$DOMAIN} {
	encode gzip zstd

	reverse_proxy web:{port} {
		header_up X-Real-IP {remote_host}
	}
}

# Redirect the apex to www (or the other way round). Uncomment and set both
# names; a certificate is issued for each hostname that appears here.
#
# www.example.com {
# 	redir https://example.com{uri} permanent
# }
"""


def render_caddyfile(app_name: str, *, port: int = DEFAULT_PORT) -> str:
    """Return the deploy/Caddyfile body."""
    return _fill(_CADDYFILE, app_name=app_name, port=port, health_path=HEALTH_PATH)


# =============================================================================
# deploy/deploy.sh
# =============================================================================

_DEPLOY_SH = """#!/usr/bin/env bash
# Deploy the current checkout of {app_name}.
#
# Usage: ./deploy/deploy.sh [--pull]
#   --pull   git pull --ff-only before building
#
# Order matters: build first, migrate once against the new image, then swap
# containers. Migrations never run inside a long-lived container, so two
# containers can never race on `feather db upgrade`.

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--pull" ]]; then
    git pull --ff-only
fi

echo "==> Building images"
# Build every service: web and worker are separate images even though they
# share a Dockerfile, and building only web leaves the worker on stale code.
docker compose build
{dependency_step}{migrate_step}
echo "==> Restarting services"
docker compose up -d --remove-orphans

echo "==> Waiting for the web container to report healthy"
# The image HEALTHCHECK hits {health_path}, which checks the database, so
# "healthy" means the app can actually serve requests.
for _ in $(seq 1 60); do
    status="$(docker inspect --format '{{.State.Health.Status}}' \\
        "$(docker compose ps -q web)" 2>/dev/null || echo starting)"
    case "$status" in
        healthy)
            echo "==> Healthy. Deploy complete."
            docker image prune -f > /dev/null
            exit 0
            ;;
        unhealthy)
            echo "!! Web container reported unhealthy" >&2
            docker compose logs --tail 50 web >&2
            exit 1
            ;;
    esac
    sleep 2
done

echo "!! Web container did not become healthy within 120s" >&2
docker compose logs --tail 50 web >&2
exit 1
"""


def render_deploy_sh(
    app_name: str, *, database: bool = True, redis: bool = True
) -> str:
    """Return the deploy/deploy.sh body."""
    services = " ".join(s for s, on in (("db", database), ("redis", redis)) if on)
    dependency_step = ""
    if services:
        dependency_step = (
            f'\necho "==> Starting {services.replace(" ", " and ")}"\n'
            f"docker compose up -d {services}\n"
        )
    migrate_step = ""
    if database:
        migrate_step = (
            '\necho "==> Running migrations (one-shot)"\n'
            "docker compose run --rm web feather db upgrade\n"
        )
    return _fill(
        _DEPLOY_SH,
        app_name=app_name,
        dependency_step=dependency_step,
        migrate_step=migrate_step,
        health_path=HEALTH_PATH,
    )


# =============================================================================
# deploy/backup.sh
# =============================================================================

_BACKUP_SH = """#!/usr/bin/env bash
# Nightly database backup for {app_name}. Run it from cron on the host:
#
#   0 3 * * * /opt/{app_slug}/deploy/backup.sh >> /var/log/{app_slug}-backup.log 2>&1
#
# Dumps in pg_dump custom format (compressed, restorable table by table) and
# keeps BACKUP_KEEP_DAYS of them locally. Copy them off this machine as well:
# a backup on the same disk as the database is not a backup.
#
# Restore:  docker compose exec -T db pg_restore -U {app_slug} -d {app_slug} --clean < dump

set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump="$BACKUP_DIR/{app_slug}-$stamp.dump"

mkdir -p "$BACKUP_DIR"

echo "==> Dumping the database to $dump"
docker compose exec -T db pg_dump -U {app_slug} -d {app_slug} --format=custom > "$dump"

echo "==> Pruning dumps older than $BACKUP_KEEP_DAYS days"
find "$BACKUP_DIR" -name '{app_slug}-*.dump' -mtime "+$BACKUP_KEEP_DAYS" -delete

echo "==> Done: $dump ($(du -h "$dump" | cut -f1))"
"""

_BACKUP_SH_NO_DB = """#!/usr/bin/env bash
# {app_name} has no database service in docker-compose.yml, so there is
# nothing to dump. Add a `db` service and replace this script with a
# pg_dump run (see the Feather README, "Deploying with Docker").

set -euo pipefail

echo "No database service is configured for {app_name}; nothing to back up." >&2
exit 0
"""


def render_backup_sh(app_name: str, app_slug: str, *, database: bool = True) -> str:
    """Return the deploy/backup.sh body."""
    template = _BACKUP_SH if database else _BACKUP_SH_NO_DB
    return _fill(template, app_name=app_name, app_slug=app_slug)


# =============================================================================
# .env.example
# =============================================================================


def _blank_secret_values(env_text: str) -> str:
    """Return the .env body with anything that looks like a secret emptied."""
    secret_marker = re.compile(
        r"(SECRET|PASSWORD|TOKEN|_KEY|APIKEY|CREDENTIAL|DSN)", re.IGNORECASE
    )
    out = []
    for line in env_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key in COMPOSE_PROVIDED_KEYS:
            out.append(f"# {key}=   # supplied by docker-compose.yml")
        elif secret_marker.search(key):
            out.append(f"{key}=")
        else:
            out.append(f"{key}={value}")
    return "\n".join(out) + "\n"


_ENV_EXAMPLE_HEADER = """# {app_name} - environment template.
#
#   cp .env.example .env    then fill in the blanks
#
# .env is git-ignored and never baked into the image; docker-compose.yml
# passes it into the containers with `env_file: .env` and also reads
# DOMAIN and POSTGRES_PASSWORD from it for its own ${...} interpolation.
#
# `feather env check` reports which of these keys your config.py actually
# reads and which are missing. `feather security-check --env-file .env`
# audits the values.
#
# These keys are set by docker-compose.yml on the container and should NOT
# be repeated here: {compose_provided}

# --- Required by docker-compose.yml (host side) ------------------------------
# The hostname Caddy issues a certificate for. DNS must already point here.
DOMAIN={domain}
# Postgres superuser password for the db service. Generate one:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
POSTGRES_PASSWORD=

# --- Required behind a reverse proxy -----------------------------------------
# Flask trusts the forwarded Host header, so a poisoned Host can rewrite
# absolute URLs and password-reset links. Comma-separated allow-list.
TRUSTED_HOSTS={domain}
# Absolute OAuth redirect URI. Without it the callback is built from the
# request Host, which the client controls. Must match the URI registered in
# the Google Cloud console exactly. Leave empty if this app has no OAuth.
OAUTH_CALLBACK_URL=https://{domain}/auth/google/callback

"""

_ENV_EXAMPLE_APP_HEADER = "# --- Application ------------------------------------------------------------\n"

_ENV_EXAMPLE_FALLBACK = """# --- Application ------------------------------------------------------------
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=
FLASK_DEBUG=0
"""


def render_env_example(
    app_name: str,
    *,
    base_env: Optional[str] = None,
    domain: str = "example.com",
    database: bool = True,
) -> str:
    """Return the .env.example body.

    ``base_env`` is the project's own ``.env`` (or the body ``feather new``
    is about to write); its keys are carried over with secret-looking values
    blanked so the example lists exactly what this app reads.
    """
    header = _fill(
        _ENV_EXAMPLE_HEADER,
        app_name=app_name,
        domain=domain or "example.com",
        compose_provided=", ".join(COMPOSE_PROVIDED_KEYS),
    )
    if not database:
        header = header.replace(
            "# Postgres superuser password for the db service. Generate one:\n"
            '#   python -c "import secrets; print(secrets.token_urlsafe(32))"\n'
            "POSTGRES_PASSWORD=\n",
            "# (No database service in docker-compose.yml, so no POSTGRES_PASSWORD.)\n",
        )

    if base_env and base_env.strip():
        body = _ENV_EXAMPLE_APP_HEADER + _blank_secret_values(base_env).lstrip("\n")
    else:
        body = _ENV_EXAMPLE_FALLBACK
    return header + body


# =============================================================================
# The file set
# =============================================================================


def docker_files(
    app_name: str,
    *,
    app_slug: Optional[str] = None,
    database: bool = True,
    redis: bool = True,
    worker: bool = True,
    domain: Optional[str] = None,
    base_env: Optional[str] = None,
    port: int = DEFAULT_PORT,
) -> list:
    """Return every Docker deployment file as a list of :class:`DockerFile`.

    Args:
        app_name: Human-readable application name (used in comments).
        app_slug: Postgres role/database and compose project name. Derived
            from ``app_name`` when omitted.
        database: Include a Postgres service and the migration step.
        redis: Include a Valkey service and REDIS_URL.
        worker: Include the ``worker`` build target and compose service.
        domain: Default value written into .env.example's ``DOMAIN``.
        base_env: The project's ``.env`` body, used to seed ``.env.example``.
        port: Container port for the web service.
    """
    slug = app_slug or slugify(app_name)
    return [
        DockerFile("Dockerfile", render_dockerfile(app_name, worker=worker, port=port)),
        DockerFile(".dockerignore", render_dockerignore()),
        DockerFile(
            "docker-compose.yml",
            render_compose(
                app_name, slug, database=database, redis=redis, worker=worker, port=port
            ),
        ),
        DockerFile("docker-compose.dev.yml", render_compose_dev(slug)),
        DockerFile("deploy/Caddyfile", render_caddyfile(app_name, port=port)),
        DockerFile(
            "deploy/deploy.sh",
            render_deploy_sh(app_name, database=database, redis=redis),
            executable=True,
        ),
        DockerFile(
            "deploy/backup.sh",
            render_backup_sh(app_name, slug, database=database),
            executable=True,
        ),
        DockerFile(
            ".env.example",
            render_env_example(
                app_name, base_env=base_env, domain=domain or "example.com", database=database
            ),
        ),
    ]


def write_docker_files(project_path: Path, files: list, force: bool = False) -> list:
    """Write the given files under ``project_path``.

    Never overwrites unless ``force``. Returns ``(path, action)`` pairs where
    action is ``"written"``, ``"overwritten"`` or ``"skipped"``.
    """
    results = []
    for item in files:
        target = project_path / item.path
        if target.exists() and not force:
            results.append((item.path, "skipped"))
            continue
        action = "overwritten" if target.exists() else "written"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content)
        if item.executable:
            target.chmod(0o755)
        results.append((item.path, action))
    return results
