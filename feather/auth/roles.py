"""
Role Inheritance
================

Explicit role inheritance hierarchy for tenant-scoped authorization.

Roles represent a user's authority WITHIN their tenant. Role inheritance
means higher roles automatically include the permissions of lower roles.

Hierarchy
---------
- **admin**: Full tenant authority (includes editor, moderator, user)
- **editor**: Content creation/editing (includes user)
- **moderator**: Content moderation (includes user)
- **user**: Basic access (default role)

Usage
-----
Check if a user has sufficient role::

    from feather.auth import effective_roles

    user_roles = effective_roles(current_user.role)
    if 'editor' in user_roles:
        # User has editor permissions (or higher)
        pass

The @role_required decorator uses this automatically::

    from feather.auth import role_required

    @api.post('/resources')
    @role_required('editor')
    def create_resource():
        # Admins and editors can access this
        pass

Note:
    Roles are tenant-scoped. A tenant admin cannot access other tenants.
    Cross-tenant operations require is_platform_admin=True.
"""

from typing import Set


# Role inheritance hierarchy
# Each role includes itself and all roles it inherits from
ROLE_INHERITS: dict[str, Set[str]] = {
    "admin": {"admin", "editor", "moderator", "user"},
    "editor": {"editor", "user"},
    "moderator": {"moderator", "user"},
    "user": {"user"},
}


def effective_roles(role: str) -> Set[str]:
    """Get the set of effective roles for a given role.

    Returns all roles that the given role inherits, including itself.
    For example, an admin effectively has all roles.

    Args:
        role: The user's role string (e.g., "admin", "editor", "user").
              Defaults to "user" if None or empty.

    Returns:
        Set of role strings the user effectively has.

    Example::

        effective_roles("admin")   # {"admin", "editor", "moderator", "user"}
        effective_roles("editor")  # {"editor", "user"}
        effective_roles("user")    # {"user"}
        effective_roles(None)      # {"user"}
    """
    if not role:
        role = "user"

    # Return the inherited roles, or just the role itself if not in hierarchy
    return ROLE_INHERITS.get(role, {role})
