from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_POLICY_PATH = Path("config/policy.json")

class Policy:
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw

    @staticmethod
    def load(path: Path = DEFAULT_POLICY_PATH) -> "Policy":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Policy(raw)

    def tool_rule(self, tool_name: str) -> Dict[str, Any]:
        return dict(self.raw.get("tools", {}).get(tool_name, {}))

    def rbac_permissions(self) -> Dict[str, Any]:
        return dict(self.raw.get("rbac", {}).get("role_permissions", {}))

    def privacy(self) -> Dict[str, Any]:
        return dict(self.raw.get("privacy", {}))

    def rag(self) -> Dict[str, Any]:
        return dict(self.raw.get("rag", {}))

    def webhook(self) -> Dict[str, Any]:
        return dict(self.raw.get("webhook", {}))

    def is_external_llm_enabled_default(self) -> bool:
        return bool(self.privacy().get("enable_external_llm_default", False))

    def data_minimization_default(self) -> bool:
        return bool(self.privacy().get("data_minimization_default", True))

    def cite_only_default(self) -> bool:
        return bool(self.rag().get("cite_only_default", False))

    def trusted_doc_required_default(self) -> bool:
        return bool(self.rag().get("trusted_doc_required_default", False))
