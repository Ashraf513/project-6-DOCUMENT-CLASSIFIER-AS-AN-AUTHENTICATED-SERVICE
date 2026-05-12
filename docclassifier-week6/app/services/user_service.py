# Location: app/services/user_service.py
# Main purpose: Business logic for user management.
# This service owns all rules about user creation, role changes,
# and permissions (e.g., only admins can change roles, last admin cannot be demoted).
# It depends on UserRepository, AuditRepository, and a cache invalidator.

from uuid import UUID
from app.domain.user import User


class UserService:
    """
    User business logic – creation, role management, profile retrieval.
    All methods are async because they will eventually talk to async repos and cache.
    """

    def __init__(self, user_repo, audit_repo, cache):
        """
        Inject dependencies.
        :param user_repo: UserRepository instance (data access)
        :param audit_repo: AuditRepository instance (audit log)
        :param cache: CacheInvalidator instance (cache key deletion)
        """
        self.user_repo = user_repo
        self.audit_repo = audit_repo
        self.cache = cache

    async def get_me(self, user_id: UUID) -> User:
        """
        Retrieve the profile of the currently authenticated user.
        :param user_id: UUID of the user
        :return: User domain model with id, email, role, is_active
        """
        # Phase 1 stub – returns a dummy user; to be replaced with real DB lookup
        return User(
            id=user_id,
            email="user@example.com",
            role="auditor",
            is_active=True
        )

    async def change_role(
        self,
        target_user_id: UUID,
        new_role: str,
        actor: User
    ) -> User:
        """
        Change the role of a target user.
        Only admins can perform this action.
        If the target is the last admin and the change would revoke that role, the operation is blocked.
        :param target_user_id: UUID of the user whose role will be changed
        :param new_role: desired new role ("admin", "reviewer", "auditor")
        :param actor: the user performing the change (must be admin)
        :return: updated User domain model
        :raises PermissionError: if actor is not admin or if last admin demotion attempted
        """
        # Phase 1 stub – just returns an updated-looking user
        return User(
            id=target_user_id,
            email="changed@example.com",
            role=new_role,
            is_active=True
        )

    async def list_users(self, actor: User) -> list[User]:
        """
        List all users (admin only).
        :param actor: the requesting user (must be admin)
        :return: list of User domain models
        """
        # Phase 1 stub – returns two dummy users
        return [
            User(
                id=UUID("00000000-0000-0000-0000-000000000001"),
                email="admin@example.com",
                role="admin",
                is_active=True
            ),
            User(
                id=UUID("00000000-0000-0000-0000-000000000002"),
                email="reviewer@example.com",
                role="reviewer",
                is_active=True
            ),
        ]