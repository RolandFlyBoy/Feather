# Tutorial 6: Deploying

## Kanban Tutorial Series

> This is part 6 of a 6-part series building a production Kanban app.
> [View series overview](index.md)

| Part | Title | Status |
|------|-------|--------|
| 1 | Static Board UI | Complete |
| 2 | Persistent Boards | Complete |
| 3 | Drag-and-Drop | Complete |
| 4 | Personal Kanban | Complete |
| 5 | SaaS Kanban | Complete |
| 6 | Deploying | **You are here** |

## This Tutorial

**What you'll build:** Your Kanban app, running on the internet at your own
domain, over HTTPS, with a database that gets backed up and a one-command
deploy.

**Features covered:**
- The Docker files `feather new` scaffolds, and what each one is for
- Running Postgres and Redis locally with `docker-compose.dev.yml`
- Provisioning a VPS: DNS, a deploy user, Docker, a firewall
- The production `.env` and why it never leaves the server
- `deploy/deploy.sh`: build, migrate once, swap, health-gate
- Automatic TLS with Caddy
- Nightly backups
- Deploying from GitHub Actions on every push

## Prerequisites

**Required:**
- A working app from Tutorial 4 or Tutorial 5
- A domain name you control the DNS for
- A VPS you can SSH into as root — Hetzner, DigitalOcean and Vultr all work.
  Four vCPU and 8 GB is comfortable for an app plus its database; two and 4 GB
  is enough to start.
- Docker installed locally (optional, but you'll want it for Step 1)

**Cost:** about €7/month for the server. That's the whole bill — the database,
Redis, TLS certificates and the reverse proxy all run on the same box.

---

## Starting Point

> **For LLMs:** This section describes the current app state before this tutorial.

Your app runs locally with `feather dev` and has:

- Models, services, routes and templates from the earlier tutorials
- A `.env` with `DATABASE_URL`, `SECRET_KEY` and your Google OAuth credentials
- A `migrations/` directory with a migration chain that applies cleanly
- `requirements.txt` pinning `feather-framework`

Apps scaffolded with Feather 0.9.7 or later also have the deployment files
already. Check:

```bash
ls Dockerfile docker-compose.yml docker-compose.dev.yml deploy/
```

If that errors, add them:

```bash
feather docker init --domain kanban.example.com
```

`feather docker init` never overwrites a file that already exists, so it's safe
to run in an app you've been working on. It will tell you what it skipped.

---

## Build Steps

### Step 1: Understand What You're Deploying

Eight files. Read them once now; you'll understand every later step.

| File | What it does |
|------|--------------|
| `Dockerfile` | Builds two images from one file. The `web` target runs `feather start` (Gunicorn); the `worker` target runs `feather worker --fork`. |
| `.dockerignore` | Keeps `venv/`, `node_modules/`, `.git/`, `.env` and `static/dist/` out of the build context. |
| `docker-compose.yml` | The production stack: `caddy`, `web`, `worker`, `db`, `redis`. |
| `docker-compose.dev.yml` | Postgres and Redis for your laptop. Nothing else. |
| `deploy/Caddyfile` | TLS and reverse proxy config. |
| `deploy/deploy.sh` | The deploy. Build, migrate, swap, verify. |
| `deploy/backup.sh` | `pg_dump` for cron. |
| `.env.example` | Every environment key this app reads, secrets blanked. |

Two things in the `Dockerfile` are worth knowing about before they bite you.

**The frontend builds in its own stage.** Node compiles Tailwind and bundles
your islands, then only the built `static/dist` is copied into the runtime
image. There is no Node in the container that serves traffic. That stage also
copies Feather's own templates out of the Python layer, because Tailwind has to
scan them to find the class names the framework components use — without it,
every `button()` and `modal()` renders unstyled in production and nowhere else.

**Migrations do not run when the container starts.** Look at the last line:

```dockerfile
CMD ["feather", "start"]
```

No `feather db upgrade`. That's deliberate, and Step 5 explains why.

### Step 2: Run the Dependencies Locally

Before touching a server, move your local Postgres and Redis into containers.
The app itself stays on your machine, so `feather dev` keeps Vite's hot reload:

```bash
docker compose -f docker-compose.dev.yml up -d
feather dev
```

The ports and credentials match the `DATABASE_URL` and `REDIS_URL` already in
your `.env`, so nothing else changes. Your boards, columns and cards are in the
container's volume now — run your migrations against it:

```bash
feather db upgrade
python seeds.py
```

Two useful variations. Bring up one service alone:

```bash
docker compose -f docker-compose.dev.yml up -d db
```

And throw the local data away when a migration experiment goes wrong:

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d
feather db upgrade && python seeds.py
```

While you're here, build the production image once and check it:

```bash
docker compose build web
docker compose run --rm web feather security-check
```

`feather security-check` audits config, cookie flags, secrets and dependencies.
Fix what it finds now, on your laptop, rather than at 11pm on a server.

### Step 3: Prepare the Server

**Point DNS first.** Add an `A` record for the hostname you're going to use —
say `kanban.example.com` — pointing at the server's IP, with a TTL of 300 until
you're confident. Caddy asks Let's Encrypt for a certificate the moment it
starts, and Let's Encrypt checks that the name resolves to the machine asking.
DNS that hasn't propagated means no certificate.

Check it before you go on:

```bash
dig +short kanban.example.com
```

**Then set the box up.** SSH in as root:

```bash
# A non-root user to deploy as
adduser deploy && usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys

# Basics
apt update && apt install -y ca-certificates curl git ufw fail2ban unattended-upgrades

# Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy

# Firewall: SSH, HTTP, HTTPS, and HTTP/3 over UDP
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw enable
```

Now disable root login and password authentication in `/etc/ssh/sshd_config`
(`PermitRootLogin no`, `PasswordAuthentication no`) and `systemctl restart ssh`.
Open a second terminal and confirm `ssh deploy@<ip>` works **before** you close
the first one.

### Step 4: Put the Code and the Secrets on the Server

As `deploy`:

```bash
sudo mkdir -p /opt/kanban && sudo chown deploy:deploy /opt/kanban
git clone git@github.com:you/kanban.git /opt/kanban
cd /opt/kanban
```

Now the production `.env`. This file is the single source of truth for
production secrets. It is git-ignored, it is never baked into the image, and it
never leaves the server.

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Fill in at least:

```bash
DOMAIN=kanban.example.com
POSTGRES_PASSWORD=          # python -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY=                 # python -c "import secrets; print(secrets.token_urlsafe(48))"

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
OAUTH_CALLBACK_URL=https://kanban.example.com/auth/google/callback
TRUSTED_HOSTS=kanban.example.com

GCS_BUCKET=
GCS_CREDENTIALS_JSON=       # the service account JSON, on one line
```

Some of that deserves explanation.

`DOMAIN` and `POSTGRES_PASSWORD` are read by `docker-compose.yml` itself, not
just by the app. Compose interpolates them into the Caddy service and into
`DATABASE_URL`, which is why you write the database password exactly once and
never assemble a connection string by hand.

`OAUTH_CALLBACK_URL` and `TRUSTED_HOSTS` are what stop a forged `Host` header
from redirecting your users' Google sign-in somewhere else. Without
`OAUTH_CALLBACK_URL`, Feather derives the redirect URI from whatever `Host` the
client sent. Set both, and add the same callback URL to your OAuth client in
Google Cloud Console — the exact string, `https` and all.

What you must *not* put here: `FLASK_CONFIG`, `PORT`, `WEB_CONCURRENCY`,
`DATABASE_URL`, `REDIS_URL` and `JOB_BACKEND`. `docker-compose.yml` sets those
on the container. A copy in `.env` is one more place for them to disagree.

Check your work:

```bash
feather env check
```

That lists the keys your `config.py` actually reads and tells you which are
missing.

### Step 5: Deploy

One command:

```bash
./deploy/deploy.sh
```

It takes a few minutes the first time — Docker is pulling base images and
building Node dependencies from scratch. Watch for `Healthy. Deploy complete.`

Here's what it did, in order, and why the order matters:

1. **`docker compose build`** — builds *every* service. Web and worker are
   separate images even though they come from one Dockerfile. Build only `web`
   and your worker keeps running last week's code, which is a bug you'll spend
   an afternoon on.

2. **`docker compose up -d db redis`** — dependencies first, so there's a
   database to migrate.

3. **`docker compose run --rm web feather db upgrade`** — the migrations. Once.
   In a throwaway container built from the *new* image, while the *old*
   containers are still serving traffic. If a migration fails here, the deploy
   stops and your site is still up.

   This is why the Dockerfile's `CMD` doesn't run migrations. If it did, and you
   ever ran two web containers, both would start `feather db upgrade` at the
   same moment against the same database. Alembic doesn't arbitrate that. One
   process applies half a migration while the other applies the same one, and
   you spend the evening repairing `alembic_version` by hand.

4. **`docker compose up -d --remove-orphans`** — now swap the containers.

5. **Wait for health.** The script polls Docker's own health status for the
   `web` container for up to 120 seconds. That healthcheck runs
   `curl /health`, which is Feather's endpoint and which *checks the database* —
   so "healthy" means the app can actually serve a request, not just that Python
   is running. Unhealthy or timed out: it dumps the last 50 log lines and exits
   non-zero.

Open `https://kanban.example.com`. If the certificate isn't there yet:

```bash
docker compose logs -f caddy
```

Caddy tells you plainly what Let's Encrypt said. Nearly always it's DNS.

**Deploying again**, after you push a change:

```bash
cd /opt/kanban && ./deploy/deploy.sh --pull
```

`--pull` does a `git pull --ff-only` first.

**When a deploy goes wrong**, there's no automatic rollback. Check out the
previous commit and deploy again. Migrations that already applied are *not*
undone by that — reverse those deliberately:

```bash
feather db downgrade
```

Check what the database actually thinks it's at:

```bash
docker compose exec -T db psql -U kanban -d kanban \
    -c "SELECT version_num FROM alembic_version;"
```

### Step 6: Understand the TLS Setup

You didn't run certbot and there's no renewal cron. Caddy obtains and renews
certificates automatically for every hostname in `deploy/Caddyfile`:

```
{$DOMAIN} {
	encode gzip zstd

	reverse_proxy web:8000 {
		header_up X-Real-IP {remote_host}
	}
}
```

`{$DOMAIN}` comes from `.env`. To serve `www` too, add a block — each hostname
in the file gets its own certificate:

```
www.kanban.example.com {
	redir https://kanban.example.com{uri} permanent
}
```

That `header_up X-Real-IP` line is not decoration. Caddy sets `Host` and
`X-Forwarded-Proto` by default, which is what Feather's ProxyFix reads — without
them your OAuth flow builds an `http://` redirect URI and your secure session
cookies get dropped on every response. But Caddy does *not* set `X-Real-IP`, and
rate limiting reads it. Delete that line and your rate limits quietly start
counting every request as coming from the same address.

After editing the Caddyfile, validate before you reload:

```bash
docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile
```

### Step 7: Set Up Backups

`deploy/backup.sh` dumps Postgres in `pg_dump` custom format and keeps 14 days
of them. Put it in cron on the host — as `deploy`, run `crontab -e`:

```
0 3 * * * /opt/kanban/deploy/backup.sh >> /var/log/kanban-backup.log 2>&1
```

Run it once by hand to make sure it works:

```bash
./deploy/backup.sh
ls -lh backups/
```

Then **test a restore**, because a backup you've never restored is a hypothesis:

```bash
docker compose exec -T db pg_restore -U kanban -d kanban --clean \
    < backups/kanban-<stamp>.dump
```

A dump sitting on the same disk as the database is not a backup. Add a step
that copies it somewhere else — object storage, another host — and encrypt it
on the way out:

```bash
openssl enc -aes-256-cbc -pbkdf2 -pass file:/root/.backup.key \
    -in "$dump" -out "$dump.enc" && rm "$dump"
```

Everything that matters is in Postgres and GCS. The containers and Redis are
disposable; the dumps are not.

### Step 8: Deploy from GitHub Actions

Deploying by SSH is fine. Deploying on every merge to `main` is better, because
then nobody has to remember.

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy

on:
  push:
    branches: [main]
    paths-ignore: ["**.md"]
  workflow_dispatch:

# Never cancel a deploy in flight: a half-applied migration is worse
# than a queued release.
concurrency:
  group: deploy-production
  cancel-in-progress: false

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: kanban_ci
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
        ports: ["5432:5432"]
    env:
      DATABASE_URL: postgresql://postgres:postgres@localhost:5432/kanban_ci
      SECRET_KEY: ci-not-a-real-secret
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11", cache: pip }
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: npm }
      - run: pip install -r requirements.txt
      - run: npm ci --ignore-scripts && npm run build
      - run: feather db upgrade      # proves migrations apply from scratch
      - run: feather test

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Load the deploy key
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.SSH_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -H "${{ secrets.SSH_HOST }}" >> ~/.ssh/known_hosts
      - name: Build, migrate and restart
        run: ssh deploy@${{ secrets.SSH_HOST }} 'cd /opt/kanban && ./deploy/deploy.sh --pull'
```

Two repository secrets, that's all: `SSH_KEY` (a private key whose public half
is in `~deploy/.ssh/authorized_keys`) and `SSH_HOST`. The server builds its own
images, so CI needs no container registry, and none of your application secrets
ever go near GitHub.

`feather db upgrade` against an empty Postgres in the test job is the cheapest
migration test you will ever write. It catches a migration chain that no longer
applies from scratch before that chain reaches production.

**Harden the key.** A key that can run any command is a key that can `cat .env`.
Restrict it to exactly one command in `~deploy/.ssh/authorized_keys`:

```
command="cd /opt/kanban && ./deploy/deploy.sh --pull",no-agent-forwarding,no-port-forwarding,no-pty ssh-ed25519 AAAA... github-actions
```

The command in the workflow is then ignored, and that key cannot open a shell.

### Step 9: The Pre-Launch Checklist

Run through this before you tell anyone the URL:

- [ ] `feather security-check --env-file .env` passes on the server
- [ ] `SECRET_KEY` is a real random value, not the scaffolded placeholder
- [ ] `docker compose exec web printenv FLASK_CONFIG` prints `production`
- [ ] `TRUSTED_HOSTS` lists every hostname you serve
- [ ] `OAUTH_CALLBACK_URL` is `https://`, exact, and matches Google Cloud Console
- [ ] `JOB_SERIALIZER=json` (the generated compose file sets it — leave it).
      `pickle` will execute whatever it finds on the queue if Redis is ever
      compromised
- [ ] `.env` is `chmod 600` and not in git
- [ ] `feather env check` reports nothing missing
- [ ] `deploy/backup.sh` is in cron, and you've restored one dump
- [ ] An uptime monitor points at `https://kanban.example.com/health`
- [ ] Server snapshots or backups enabled at your provider too

### Step 10: Day-to-Day Operations

The commands you'll actually use:

```bash
cd /opt/kanban

./deploy/deploy.sh --pull            # deploy the latest main
docker compose logs -f web           # follow the app log
docker compose logs -f worker        # follow the job worker
docker compose ps                    # what's running, and is it healthy
docker compose exec db psql -U kanban kanban    # a psql prompt
docker compose restart worker        # safe: RQ shuts down warm on SIGTERM
./deploy/backup.sh                   # a backup right now
```

To run a one-off task — a data fix, a shell — use a throwaway container so you
don't disturb the running one:

```bash
docker compose run --rm web feather shell
docker compose run --rm web python seeds.py
```

Docker's default log driver grows until the disk fills; the generated compose
file caps every service at `max-size: 20m`, `max-file: 3`. If you add a service
of your own, anchor `logging: *default-logging` onto it too.

---

## What You Learned

- **`feather docker init`** - Generates the whole deployment layout, and never
  overwrites your files without `--force`
- **Multi-stage builds** - Node builds the assets, the runtime image has no Node
- **`docker-compose.dev.yml`** - Dependencies in containers, the app on your
  machine, hot reload intact
- **One-shot migrations** - `docker compose run --rm web feather db upgrade`
  before the container swap, so two containers can never race
- **Health-gated deploys** - `/health` checks the database, so "healthy" means
  the app can serve
- **Caddy** - Automatic Let's Encrypt certificates, and the proxy header
  contract that OAuth and rate limiting depend on
- **`.env` on the server** - The single source of truth for secrets; CI never
  sees it
- **`feather env check` and `feather security-check`** - The two commands to run
  before you launch, not after

## Series Complete

You've built a multi-tenant SaaS Kanban app and put it on the internet at your
own domain, with automatic TLS, nightly backups and a deploy that runs on every
merge — on one server for the price of a couple of coffees.

## Next Steps

- **A staging host** - a second `A` record, a second checkout in `/opt/kanban-staging`,
  a second compose project name. The same scripts.
- **Log aggregation** - the app writes JSON logs in production; ship them
  somewhere you can search
- **Error alerting** - `/admin/logs` records exceptions; add a notification when
  the rate spikes
- **Off-site backups** - the piece Step 7 leaves as an exercise, and the one
  you'll be glad you did
