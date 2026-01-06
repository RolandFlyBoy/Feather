"""
CRUD Permissions
================

Permission definitions using domain-agnostic CRUD language.

Permissions are mapped to roles and checked via @permission_required.
Using CRUD terminology keeps Feather neutral and reusable across domains.

Permission Format
-----------------
All permissions use the pattern: `resources.<action>`

Available actions:
- **create**: Create new resources
- **read**: View resources
- **update**: Modify existing resources
- **delete**: Remove resources
- **manage**: Administrative actions (moderation, bulk operations)

Role Mappings
-------------
- **admin**: "*" (all permissions)
- **editor**: create, update
- **moderator**: manage
- **user**: read

Usage
-----
Protect routes with permission checks::

    from feather.auth import permission_required

    @api.post('/resources')
    @permission_required('resources.create')
    def create_resource():
        # Editors and admins can access this
        pass

    @api.delete('/resources/<id>')
    @permission_required('resources.delete')
    def delete_resource(id):
        # Only admins can delete (has "*" permission)
        pass

Note:
    Permissions are tenant-scoped. They control what a user can do
    within their tenant, not across tenants.
"""

from typing import Set


# Role to permission mapping
# "*" means all permissions
ROLE_PERMISSIONS: dict[str, Set[str]] = {
    "admin": {"*"},
    "editor": {"resources.create", "resources.update"},
    "moderator": {"resources.manage"},
    "user": {"resources.read"},
}
