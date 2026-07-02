"""Repository for AppUser model."""
from __future__ import annotations
import hashlib
from datetime import date
from typing import List, Optional
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import AppUser
from state_quant_engine.repositories.base_repository import BaseRepository


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


class UserRepository(BaseRepository[AppUser]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AppUser)

    def get_by_username(self, username: str) -> Optional[AppUser]:
        return self._session.query(AppUser).filter(
            AppUser.username == username
        ).first()

    def verify(self, username: str, password: str) -> Optional[AppUser]:
        user = self.get_by_username(username)
        if user and user.password_hash == hash_password(password):
            return user
        return None

    def create_user(self, username: str, password: str, is_admin: bool = False) -> AppUser:
        user = AppUser(
            username=username,
            password_hash=hash_password(password),
            is_admin=is_admin,
            created_at=date.today(),
        )
        return self.add(user)

    def change_password(self, username: str, new_password: str) -> bool:
        user = self.get_by_username(username)
        if user:
            user.password_hash = hash_password(new_password)
            self._session.commit()
            return True
        return False

    def seed_admin(self) -> AppUser:
        """Create default admin user if no users exist."""
        if self._session.query(AppUser).count() == 0:
            return self.create_user("admin", "sqe@2024", is_admin=True)
        return self.get_by_username("admin")
