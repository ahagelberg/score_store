"""User account persistence."""

from __future__ import annotations

import shutil

import constants as c
import paths
from json_io.json_store import JsonStore
from models.user import MaestroUser, User, user_from_dict
from scope import maestro_data_scope
from services import password as password_service

SUB_ACCOUNT_CHOIR_SORT_RANK = 0
SUB_ACCOUNT_SINGER_SORT_RANK = 1


def _sub_account_sort_key(user: User) -> tuple[int, str, str]:
    role_rank = SUB_ACCOUNT_CHOIR_SORT_RANK if user.is_choir() else SUB_ACCOUNT_SINGER_SORT_RANK
    label = (user.display_name or user.username).casefold()
    return (role_rank, label, user.username)


class UserRepository:
    """Load and save user accounts from main and maestro-scoped JSON files."""

    def load_main(self) -> list[User]:
        return [user_from_dict(entry) for entry in JsonStore.read_list(paths.USERS_PATH)]

    def save_main(self, users: list[User]) -> None:
        JsonStore.write_list(paths.USERS_PATH, [user.to_dict() for user in users])

    def load_sub_accounts(self, maestro_username: str) -> list[User]:
        uname = maestro_username.strip().lower()
        return [
            user_from_dict(entry, maestro_username=uname)
            for entry in JsonStore.read_list(paths.maestro_users_path(uname))
        ]

    def save_sub_accounts(self, maestro_username: str, users: list[User]) -> None:
        JsonStore.write_list(
            paths.maestro_users_path(maestro_username),
            [user.to_dict() for user in users],
        )

    def all_usernames(self, exclude_username: str | None = None) -> set[str]:
        names = {user.username for user in self.load_main()}
        for maestro in self.maestro_accounts():
            names.update(user.username for user in self.load_sub_accounts(maestro.username))
        if exclude_username:
            names.discard(exclude_username.strip().lower())
        return names

    def load_all(self) -> list[User]:
        users = list(self.load_main())
        for maestro in self.maestro_accounts():
            users.extend(self.load_sub_accounts(maestro.username))
        return users

    def save_all(self, users: list[User]) -> None:
        main: list[User] = []
        by_maestro: dict[str, list[User]] = {}
        for user in users:
            if user.is_sub_account():
                by_maestro.setdefault(user.maestro_username, []).append(user)
            else:
                main.append(user)
        self.save_main(main)
        for maestro in main:
            if not isinstance(maestro, MaestroUser):
                continue
            if maestro.username not in by_maestro:
                continue
            self.save_sub_accounts(maestro.username, by_maestro[maestro.username])

    def get_from_main(self, username: str) -> User | None:
        uname = username.strip().lower()
        for user in self.load_main():
            if user.username == uname:
                return user
        return None

    def get_by_username(self, username: str) -> User | None:
        uname = username.strip().lower()
        user = self.get_from_main(uname)
        if user:
            return user
        for maestro in self.maestro_accounts():
            for sub in self.load_sub_accounts(maestro.username):
                if sub.username == uname:
                    return sub
        return None

    def get_by_id(self, user_id: str) -> User | None:
        return self.get_by_username(user_id)

    def maestro_accounts(self) -> list[MaestroUser]:
        return [user for user in self.load_main() if isinstance(user, MaestroUser)]

    def sub_accounts_for_maestro(self, maestro_username: str) -> list[User]:
        maestro = self.get_by_username(maestro_username)
        if not isinstance(maestro, MaestroUser):
            return []
        users = [
            user for user in self.load_sub_accounts(maestro.username) if user.is_sub_account()
        ]
        return sorted(users, key=_sub_account_sort_key)

    def upsert(self, user: User) -> None:
        if user.is_sub_account():
            maestro = self.get_by_username(user.maestro_username)
            if not isinstance(maestro, MaestroUser):
                raise ValueError("Sub-account requires a maestro owner")
            users = self.load_sub_accounts(maestro.username)
            for index, entry in enumerate(users):
                if entry.username == user.username:
                    users[index] = user
                    self.save_sub_accounts(maestro.username, users)
                    return
            users.append(user)
            self.save_sub_accounts(maestro.username, users)
            return
        if not user.is_main_account():
            raise ValueError("Unknown role")
        users = self.load_main()
        for index, entry in enumerate(users):
            if entry.username == user.username:
                users[index] = user
                self.save_main(users)
                return
        users.append(user)
        self.save_main(users)

    def remove(self, username: str) -> bool:
        uname = username.strip().lower()
        users = self.load_main()
        filtered = [user for user in users if user.username != uname]
        if len(filtered) != len(users):
            self.save_main(filtered)
            return True
        for maestro in self.maestro_accounts():
            subs = self.load_sub_accounts(maestro.username)
            filtered = [user for user in subs if user.username != uname]
            if len(filtered) != len(subs):
                self.save_sub_accounts(maestro.username, filtered)
                return True
        return False

    def maestro_folder_username(self, user: User) -> str:
        if isinstance(user, MaestroUser):
            return user.username
        if user.is_sub_account():
            owner = self.get_by_username(user.maestro_username)
            if not isinstance(owner, MaestroUser):
                raise ValueError("User has no owning maestro")
            return owner.username
        raise ValueError("User has no maestro folder")

    def maestro_account_username(self, user: User) -> str:
        if isinstance(user, MaestroUser):
            return user.username
        if user.is_sub_account():
            if not user.maestro_username:
                raise ValueError("User has no owning maestro")
            return user.maestro_username
        raise ValueError("Not a maestro account")

    def create_sub_account(
        self,
        display_name: str,
        username: str,
        password: str,
        role: str,
        maestro_username: str,
        secret: str,
        *,
        ensure_library,
    ) -> User:
        if role not in c.SUB_ACCOUNT_ROLES:
            raise ValueError("Invalid role")
        uname = username.strip().lower()
        if not uname:
            raise ValueError("Username is required")
        if self.get_by_username(uname):
            raise ValueError("Username taken")
        maestro = self.get_by_username(maestro_username)
        if not isinstance(maestro, MaestroUser):
            raise ValueError("Maestro not found")
        user = user_from_dict({
            "display_name": display_name.strip() or uname,
            "username": uname,
            "role": role,
        }, maestro_username=maestro.username)
        password_service.set_password(user, password, secret)
        with maestro_data_scope(maestro.username):
            self.upsert(user)
            ensure_library(uname)
        return user

    def delete_maestro(self, maestro_username: str, *, delete_user_fn) -> None:
        user = self.get_by_username(maestro_username)
        if not isinstance(user, MaestroUser):
            raise ValueError("Maestro not found")
        uname = user.username
        from scope import activate_maestro_data, current_maestro_data
        prev = current_maestro_data()
        try:
            activate_maestro_data(uname)
            for sub in list(self.sub_accounts_for_maestro(uname)):
                delete_user_fn(sub.username)
        finally:
            activate_maestro_data(prev)
        self.save_main([entry for entry in self.load_main() if entry.username != uname])
        folder = paths.maestro_data_dir(uname)
        if folder.exists():
            shutil.rmtree(folder)
