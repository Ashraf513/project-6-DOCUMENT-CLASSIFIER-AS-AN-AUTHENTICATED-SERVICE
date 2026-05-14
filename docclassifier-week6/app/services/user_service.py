# Location: app/services/user_service.py
# Business logic: user creation, role changes, profile.
# All methods own transaction boundaries and cache invalidation.

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user import User, Role, UserCreate, UserRoleUpdate
from app.repositories.user_repo import UserRepo
from app.repositories.audit_repo import AuditRepo
from app.infra.cache import CacheInvalidator, USERS_LIST_KEY, user_me_key
from app.infra.security import hash_password
from app.services.exceptions import PermissionDenied, NotFound, LastAdminError


class UserService:
    """
    Handles user-related business logic.
    - Only admins can create / change roles.
    - The last admin cannot be demoted.
    - Role changes are audited and cached data is invalidated.
    """

    def __init__(self, db: AsyncSession, cache: CacheInvalidator):
        self.db = db
        self.cache = cache
        self.user_repo  = UserRepo(db)
        self.audit_repo = AuditRepo(db)

    async def get_me(self, user_id: str) -> User:
        async with self.db.begin():
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise NotFound("User not found")
            return user

    async def get_by_id(self, user_id: str) -> User:
        return await self.get_me(user_id)

    async def create_user(self, data: UserCreate, actor: User) -> User:
        if actor.role != Role.admin:
            raise PermissionDenied("Only admins can create users")

        hashed = hash_password(data.password.get_secret_value())

        async with self.db.begin():
            user = await self.user_repo.create(data, hashed_credential=hashed)
            await self.audit_repo.create(
                actor_id=actor.id,
                action="user_create",
                target=f"user:{user.id}",
                details={"email": str(data.email), "role": data.role.value},
            )

        await self.cache.delete(USERS_LIST_KEY)
        return user

    async def change_role(
        self,
        target_user_id: str,
        update: UserRoleUpdate,
        actor: User,
    ) -> User:
        if actor.role != Role.admin:
            raise PermissionDenied("Only admins can change roles")

        async with self.db.begin():
            target = await self.user_repo.get_by_id(target_user_id)
            if not target:
                raise NotFound("Target user not found")

            if target.role == Role.admin and update.role != Role.admin:
                admin_count = await self.user_repo.count_by_role(Role.admin)
                if admin_count == 1:
                    raise LastAdminError("Cannot demote the last admin")

            updated = await self.user_repo.update_role(target_user_id, update.role)
            await self.audit_repo.create(
                actor_id=actor.id,
                action="role_change",
                target=f"user:{target_user_id}",
                details={
                    "old_role": target.role.value,
                    "new_role": update.role.value,
                },
            )

        await self.cache.delete(user_me_key(target_user_id))
        await self.cache.delete(USERS_LIST_KEY)
        return updated

    async def list_users(
        self,
        actor: User,
        skip: int = 0,
        limit: int = 20,
    ) -> list[User]:
        if actor.role != Role.admin:
            raise PermissionDenied("Only admins can list users")
        async with self.db.begin():
            return await self.user_repo.list_all(limit=limit, offset=skip)
