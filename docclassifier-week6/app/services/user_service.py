# Location: app/services/user_service.py
# Main purpose: Business logic for user management.
# This service owns all rules about user creation, role changes,
# and permissions (e.g., only admins can change roles, last admin cannot be demoted).
# It depends on UserRepository, AuditRepository, and a cache invalidator.

from datetime import datetime, timezone

from app.domain.user import User, Role, UserCreate, UserRoleUpdate


class UserService:
    """
    User business logic - creation, role management, profile retrieval.
    All methods are async because they will eventually talk to async repos and cache.
    """

    def __init__(self, user_repo, audit_repo, cache):
        """
        :param user_repo: UserRepository instance (data access)
        :param audit_repo: AuditRepository instance (audit log)
        :param cache: CacheInvalidator instance (cache key deletion)
        """
        self.user_repo = user_repo
        self.audit_repo = audit_repo
        self.cache = cache

    async def get_me(self, user_id: str) -> User:
        """
        Retrieve the profile of the currently authenticated user.
        :raises NotFound: if no user with this id exists
        """
        # Phase 1 stub
        return User(
            id=user_id,
            email="user@example.com",
            role=Role.auditor,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    async def get_by_id(self, user_id: str) -> User:
        """
        Retrieve a user by id. Used by Casbin enforcement and admin views.
        :raises NotFound: if no user with this id exists
        """
        # Phase 1 stub
        return User(
            id=user_id,
            email="someone@example.com",
            role=Role.reviewer,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    async def create_user(self, data: UserCreate, actor: User) -> User:
        """
        Create a new user. Admin-only.
        Phase 2 will:
          1. Check actor.role == Role.admin
          2. Hash data.password (passlib / fastapi-users PasswordHelper)
          3. Insert via user_repo
          4. Write audit log
        :raises PermissionDenied: if actor is not an admin
        """
        # Phase 1 stub - returns a dummy user reflecting the input
        return User(
            id="00000000-0000-0000-0000-000000000099",
            email=data.email,
            role=data.role,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    async def change_role(
        self,
        target_user_id: str,
        update: UserRoleUpdate,
        actor: User,
    ) -> User:
        """
        Change the role of a target user.
        Only admins can perform this action.
        If the target is the last admin and the change would revoke that role,
        the operation is blocked.
        :raises PermissionDenied: if actor is not admin
        :raises LastAdminError: if this would demote the last admin
        :raises NotFound: if target_user_id does not exist
        """
        # Phase 1 stub
        return User(
            id=target_user_id,
            email="changed@example.com",
            role=update.role,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    async def list_users(
        self,
        actor: User,
        skip: int = 0,
        limit: int = 20,
    ) -> list[User]:
        """
        List users (admin only).
        :raises PermissionDenied: if actor is not admin
        """
        # Phase 1 stub
        now = datetime.now(timezone.utc)
        return [
            User(
                id="00000000-0000-0000-0000-000000000001",
                email="admin@example.com",
                role=Role.admin,
                is_active=True,
                created_at=now,
            ),
            User(
                id="00000000-0000-0000-0000-000000000002",
                email="reviewer@example.com",
                role=Role.reviewer,
                is_active=True,
                created_at=now,
            ),
        ]
