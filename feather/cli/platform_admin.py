"""feather platform-admin - Manage platform admin users."""

import subprocess
import sys
from pathlib import Path

import click


@click.command(name="platform-admin")
@click.argument("email")
@click.option("--revoke", is_flag=True, help="Revoke platform admin instead of granting")
def platform_admin(email: str, revoke: bool):
    """Grant or revoke platform admin status for a user.

    This command requires server/CLI access for security - platform admin
    privileges cannot be granted through the web interface.

    \b
    Examples:
      feather platform-admin admin@example.com           Grant admin
      feather platform-admin admin@example.com --revoke  Revoke admin
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    # Run the actual command via Flask shell context
    action = "revoke" if revoke else "grant"
    script = f'''
from feather.db import db

# Find User model dynamically
User = None
for model in db.Model.__subclasses__():
    if model.__name__ == "User":
        User = model
        break

if not User:
    print("ERROR: No User model found")
    exit(1)

user = User.query.filter_by(email="{email}").first()
if not user:
    print("ERROR: User '{email}' not found")
    exit(1)

if not hasattr(user, "is_platform_admin"):
    print("ERROR: User model does not have is_platform_admin field")
    exit(1)

if "{action}" == "revoke":
    if not user.is_platform_admin:
        print("User '{email}' is not a platform admin")
        exit(0)
    user.is_platform_admin = False
    db.session.commit()
    print("SUCCESS: Revoked platform admin from {email}")
else:
    if user.is_platform_admin:
        print("User '{email}' is already a platform admin")
        exit(0)
    user.is_platform_admin = True
    db.session.commit()
    print("SUCCESS: Granted platform admin to {email}")
'''

    result = subprocess.run(
        [sys.executable, "-c", f"from app import app; exec('''{script}''')"],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )

    # Parse output
    output = result.stdout.strip() or result.stderr.strip()

    if "ERROR:" in output:
        raise click.ClickException(output.replace("ERROR: ", ""))
    elif "SUCCESS:" in output:
        click.echo(click.style(output.replace("SUCCESS: ", ""), fg="green"))
    else:
        click.echo(output)
