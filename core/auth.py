from __future__ import annotations
from typing import Optional, Tuple
from . import storage
from .rbac import make_password_hash, verify_password

def register_user(username: str, password: str, org_name: str, db_path: str = "app.db") -> Tuple[bool, str, int]:
    username = (username or "").strip()
    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters.", -1
    if storage.get_user(username, db_path=db_path):
        return False, "Username already exists.", -1
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters.", -1

    org_name = (org_name or "").strip() or f"{username}-org"
    role = "Admin" if storage.user_count(db_path=db_path) == 0 else "Researcher"

    ph, salt = make_password_hash(password)
    storage.upsert_user(username, ph, salt, role, db_path=db_path)

    org_id = storage.get_or_create_org(org_name, db_path=db_path)
    storage.add_membership(username, org_id, "owner", db_path=db_path)
    project_id = storage.create_project(org_id, "default", db_path=db_path)
    return True, f"Registered. Role: {role}.", project_id

def login_user(username: str, password: str, db_path: str = "app.db") -> Tuple[bool, str, Optional[dict]]:
    user = storage.get_user((username or "").strip(), db_path=db_path)
    if not user:
        return False, "User not found.", None
    if not verify_password(password or "", user["password_hash"], user["salt"]):
        return False, "Invalid password.", None
    return True, "Logged in.", user
