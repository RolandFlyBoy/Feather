"""feather platform-admin - Manage platform admin users."""

import os
import subprocess
import sys
from pathlib import Path

import click

#: Environment variables carrying the arguments into the child process.
#: The email is NEVER interpolated into the source we execute: an address
#: containing quotes would otherwise break out of the string literal and run
#: as code with full database access.
EMAIL_ENV_VAR = "FEATHER_PLATFORM_ADMIN_EMAIL"
ACTION_ENV_VAR = "FEATHER_PLATFORM_ADMIN_ACTION"


def _child_source() -> str:
    """Return the script run inside the app's process.

    It is a constant string: every value it works with is read from the
    environment at runtime.
    """
    return f'''
import os

from app import app  # noqa: F401  (imports the app so models are registered)
from feather.db import db

email = os.environ[{EMAIL_ENV_VAR!r}]
action = os.environ[{ACTION_ENV_VAR!r}]

# Find User model dynamically
User = None
for model in db.Model.__subclasses__():
    if model.__name__ == "User":
        User = model
        break

if not User:
    print("ERROR: No User model found")
    raise SystemExit(1)

user = User.query.filter_by(email=email).first()
if not user:
    print("ERROR: User '%s' not found" % email)
    raise SystemExit(1)

if not hasattr(user, "is_platform_admin"):
    print("ERROR: User model does not have is_platform_admin field")
    raise SystemExit(1)

if action == "revoke":
    if not user.is_platform_admin:
        print("User '%s' is not a platform admin" % email)
        raise SystemExit(0)
    user.is_platform_admin = False
    db.session.commit()
    print("SUCCESS: Revoked platform admin from %s" % email)
else:
    if user.is_platform_admin:
        print("User '%s' is already a platform admin" % email)
        raise SystemExit(0)
    user.is_platform_admin = True
    db.session.commit()
    print("SUCCESS: Granted platform admin to %s" % email)
'''


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

    action = "revoke" if revoke else "grant"

    env = {
        **os.environ,
        EMAIL_ENV_VAR: email,
        ACTION_ENV_VAR: action,
    }

    result = subprocess.run(
        [sys.executable, "-c", _child_source()],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
        env=env,
    )

    # Parse output
    output = result.stdout.strip() or result.stderr.strip()

    if "ERROR:" in output:
        raise click.ClickException(output.replace("ERROR: ", ""))
    elif "SUCCESS:" in output:
        click.echo(click.style(output.replace("SUCCESS: ", ""), fg="green"))
    else:
        click.echo(output)
