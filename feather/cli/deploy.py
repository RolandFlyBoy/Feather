"""Feather deploy command - Generate deployment files for cloud platforms."""

import click
from pathlib import Path


@click.group()
def deploy():
    """Generate deployment files for cloud platforms.

    Currently supports:
    - render: Generate Dockerfile, render.yaml, and .dockerignore for Render.com
    """
    pass


@deploy.command()
@click.option("--name", "-n", help="Application name (defaults to current directory name)")
@click.option("--region", "-r", default="oregon", help="Render region (default: oregon)")
def render(name: str, region: str):
    """Generate deployment files for Render.com.

    Creates:
    - Dockerfile: Multi-stage build with Python, Node.js, and system deps
    - render.yaml: Blueprint for web service and database
    - .dockerignore: Standard ignores for efficient builds

    Example:
        feather deploy render
        feather deploy render --name myapp --region frankfurt
    """
    # Verify we're in a Feather project
    if not Path("app.py").exists():
        raise click.ClickException(
            "Not in a Feather project directory. "
            "Run this command from the root of your project (where app.py is)."
        )

    # Default name to current directory
    if not name:
        name = Path.cwd().name

    # Create deployment files
    _create_dockerfile()
    _create_render_yaml(name, region)
    _create_dockerignore()

    click.echo(click.style("✓ Created deployment files for Render:", fg="green"))
    click.echo(f"  - Dockerfile")
    click.echo(f"  - render.yaml")
    click.echo(f"  - .dockerignore")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Review and customize the generated files")
    click.echo("  2. Push your code to GitHub")
    click.echo("  3. Connect your repo in the Render dashboard")
    click.echo("  4. Or use: render blueprint apply")


def _create_dockerfile():
    """Create Dockerfile for Render deployment."""
    content = '''# Dockerfile for Feather App on Render
FROM python:3.11-slim

# Install system dependencies including Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \\
    ffmpeg \\
    libpq-dev \\
    gcc \\
    git \\
    curl \\
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \\
    && apt-get install -y nodejs \\
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \\
    && pip install --no-cache-dir git+https://github.com/RolandFlyBoy/Feather.git \\
    && pip install --no-cache-dir -r requirements.txt

# Install Node dependencies and build frontend
COPY package*.json ./
RUN npm install

# Copy application code
COPY . .

# Build Tailwind CSS
RUN npm run build

# Create logs directory
RUN mkdir -p logs

# Expose port
EXPOSE 10000

# Run migrations, seed if seeds.py exists, then start gunicorn
CMD ["sh", "-c", "feather db upgrade && (test -f seeds.py && python seeds.py || true) && gunicorn app:app --workers 2 --threads 4 --bind 0.0.0.0:10000"]
'''
    Path("Dockerfile").write_text(content)


def _create_render_yaml(name: str, region: str):
    """Create render.yaml blueprint for Render deployment."""
    # Map common region names to Render region codes
    region_map = {
        "oregon": "oregon",
        "ohio": "ohio",
        "virginia": "virginia",
        "frankfurt": "frankfurt",
        "singapore": "singapore",
    }
    render_region = region_map.get(region.lower(), region)

    content = f'''# Render.yaml - Feather App Deployment Configuration
# https://render.com/docs/blueprint-spec

services:
  - type: web
    name: {name}
    runtime: docker
    plan: starter
    region: {render_region}
    healthCheckPath: /api/health
    # Only Render-managed env vars here. Upload .env file in dashboard for the rest.
    envVars:
      - key: FLASK_CONFIG
        value: production
      - key: SECRET_KEY
        generateValue: true
      - key: DATABASE_URL
        fromDatabase:
          name: {name}-db
          property: connectionString

databases:
  - name: {name}-db
    plan: basic-256mb
    databaseName: {name.replace("-", "_")}
    postgresMajorVersion: 16
    region: {render_region}
'''
    Path("render.yaml").write_text(content)


def _create_dockerignore():
    """Create .dockerignore for efficient Docker builds."""
    content = '''# Python
venv/
__pycache__/
*.py[cod]
*.pyo
.pytest_cache/
.coverage
htmlcov/

# Node
node_modules/

# Git
.git/
.gitignore

# Environment and secrets
.env
.env.local
.env.*.local

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

# Build artifacts (will be regenerated)
static/dist/

# Tests (not needed in production)
tests/
'''
    Path(".dockerignore").write_text(content)

