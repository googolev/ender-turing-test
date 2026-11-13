"""Who can do what. Change access rules here and nowhere else.

Roles are stored on the user; permissions are derived from the role on every
request, so a role change applies to sessions that already hold a token.
"""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


class Permission(StrEnum):
    USERS_READ = "users:read"  # list users and view any user
    USERS_MANAGE = "users:manage"  # create, edit, delete users; change role/status
    METRICS_READ = "metrics:read"
    ITEMS_ALL = "items:all"  # see and change other users' items
    SYSTEM_MANAGE = "system:manage"  # operational tools such as the test email


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.ADMIN: frozenset(Permission),  # every permission, including new ones
    UserRole.MANAGER: frozenset({Permission.USERS_READ, Permission.METRICS_READ}),
    UserRole.MEMBER: frozenset(),
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def permissions_for(role: UserRole) -> list[Permission]:
    return sorted(ROLE_PERMISSIONS[role])
