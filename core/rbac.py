from __future__ import annotations
import hashlib
import secrets
from typing import Dict, Tuple

def pbkdf2_hash(password: str, salt_hex: str, rounds: int = 150_000) -> str:
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return dk.hex()

def make_password_hash(password: str) -> Tuple[str, str]:
    salt = secrets.token_hex(16)
    return pbkdf2_hash(password, salt), salt

def verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    return secrets.compare_digest(pbkdf2_hash(password, salt_hex), password_hash)

def can_use_tool(role: str, tool_name: str, role_permissions: Dict[str, list]) -> bool:
    perms = set(role_permissions.get(role, []))
    return ("*" in perms) or (tool_name in perms)
