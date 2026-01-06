"""
Permission Evaluation Logic
===========================

Evaluates user permissions based on role inheritance.

A user's effective permissions are the union of all permissions
from their role and all inherited roles.

Usage
-----
Check user permissions directly::

    from feather.auth import effective_permissions

    perms = effective_permissions(current_user.role)
    if 'resources.create' in perms or '*' in perms:
        # User can create resources
        pass

The @permission_required decorator uses this automatically::

    from feather.auth import permission_required

    @api.post('/resources')
    @permission_required('resources.create')
    def create_resource():
        pass
"""

from typing import Set

from feather.auth.roles import effective_roles
from feather.auth.permissions import ROLE_PERMISSIONS


def effective_permissions(role: str) -> Set[str]:
    """Get the set of effective permissions for a given role.

    Collects permissions from the user's role and all inherited roles.
    For example, an admin has "*" which grants all permissions.

    Args:
        role: The user's role string (e.g., "admin", "editor", "user").
              Defaults to "user" if None or empty.

    Returns:
        Set of permission strings the user has.

    Example::

        effective_permissions("admin")
        # {"*"}

        effective_permissions("editor")
        # {"resources.create", "resources.update", "resources.read"}

        effective_permissions("user")
        # {"resources.read"}
    """
    perms: Set[str] = set()

    for r in effective_roles(role):
        perms |= ROLE_PERMISSIONS.get(r, set())

    return perms
