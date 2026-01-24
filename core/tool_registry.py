from __future__ import annotations
from typing import Any, Callable, Dict, Optional, Type
from pydantic import BaseModel, Field, EmailStr
from urllib.parse import urlparse

from . import storage
from .kb_ingest import top_k_chunks
from .policy import Policy

class KBSearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=800)
    top_k: int = Field(default=5, ge=1, le=10)
    trusted_only: bool = False

class SummarizeArgs(BaseModel):
    text: str = Field(min_length=1, max_length=8000)

class CreateTodoArgs(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: Optional[str] = Field(default=None, max_length=32)

class ListTodosArgs(BaseModel):
    pass

class DraftEmailArgs(BaseModel):
    to: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)

class GitHubRepoSearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    top_k: int = Field(default=5, ge=1, le=10)

class WebhookPostArgs(BaseModel):
    url: str = Field(min_length=6, max_length=400)
    json_body: Dict[str, Any] = Field(default_factory=dict)

class ToolSpec(BaseModel):
    name: str
    description: str
    args_model: Type[BaseModel]
    risk: str = "low"
    requires_approval: bool = False
    is_external: bool = False

class ToolRegistry:
    def __init__(self, policy: Policy):
        self.policy = policy
        self.tools: Dict[str, ToolSpec] = {}
        self.handlers: Dict[str, Callable[..., Dict[str, Any]]] = {}

    def register(self, spec: ToolSpec, handler: Callable[..., Dict[str, Any]]) -> None:
        rule = self.policy.tool_rule(spec.name)
        if rule:
            spec.risk = rule.get("risk", spec.risk)
            spec.requires_approval = bool(rule.get("requires_approval", spec.requires_approval))
        self.tools[spec.name] = spec
        self.handlers[spec.name] = handler

    def list_specs(self) -> Dict[str, ToolSpec]:
        return dict(self.tools)

    def validate_args(self, tool_name: str, args: Dict[str, Any]) -> BaseModel:
        return self.tools[tool_name].args_model.model_validate(args)

    def execute(self, tool_name: str, args_obj: BaseModel, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return self.handlers[tool_name](args_obj, ctx)

def handle_kb_search(args: KBSearchArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
    chunks = storage.list_kb_chunks_for_project(ctx["project_id"])
    results = top_k_chunks(args.query, chunks, k=args.top_k, trusted_only=args.trusted_only)
    return {"query": args.query, "top_k": args.top_k, "trusted_only": args.trusted_only, "results": results}

def handle_summarize(args: SummarizeArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
    t = args.text.strip().replace("\n", " ")
    parts = [p.strip() for p in t.split(".") if p.strip()]
    summary = ". ".join(parts[:3])
    if summary and not summary.endswith("."):
        summary += "."
    return {"summary": summary, "method": "deterministic", "input_chars": len(t)}

def handle_create_todo(args: CreateTodoArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
    todo_id = storage.add_todo(ctx["project_id"], ctx["username"], args.title, args.due_date)
    return {"todo_id": todo_id, "title": args.title, "due_date": args.due_date, "status": "open"}

def handle_list_todos(args: ListTodosArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
    todos = storage.list_todos(ctx["project_id"], ctx["username"])
    return {"count": len(todos), "todos": todos}

def handle_draft_email(args: DraftEmailArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"to": str(args.to), "subject": args.subject, "body": args.body, "note": "Draft only (not sent)."}

def handle_github_repo_search(args: GitHubRepoSearchArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
    import requests
    url = "https://api.github.com/search/repositories"
    params = {"q": args.query, "per_page": args.top_k}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    items = []
    for it in data.get("items", [])[:args.top_k]:
        items.append({
            "full_name": it.get("full_name"),
            "html_url": it.get("html_url"),
            "stars": it.get("stargazers_count"),
            "description": it.get("description"),
        })
    return {"query": args.query, "results": items, "note": "GitHub public API (rate-limited)."}

def handle_webhook_post(args: WebhookPostArgs, ctx: Dict[str, Any]) -> Dict[str, Any]:
    import requests
    policy: Policy = ctx["policy"]
    allowed_hosts = set(policy.webhook().get("allowlist_hosts", []))
    host = urlparse(args.url).hostname or ""
    if allowed_hosts and host not in allowed_hosts:
        raise ValueError(f"Host '{host}' not in allowlist")
    r = requests.post(args.url, json=args.json_body, timeout=15)
    return {"status_code": r.status_code, "response_preview": (r.text[:300] + ("…" if len(r.text) > 300 else ""))}

def build_registry(policy: Policy) -> ToolRegistry:
    reg = ToolRegistry(policy)
    reg.register(ToolSpec(
        name="kb_search",
        description="Search the project knowledge base (lexical retrieval over chunks).",
        args_model=KBSearchArgs,
        risk="low",
        requires_approval=False,
        is_external=False
    ), handle_kb_search)
    reg.register(ToolSpec(
        name="summarize_text",
        description="Summarize text deterministically (offline).",
        args_model=SummarizeArgs,
        risk="low",
        requires_approval=False,
        is_external=False
    ), handle_summarize)
    reg.register(ToolSpec(
        name="create_todo",
        description="Create a todo item for the current user in the active project.",
        args_model=CreateTodoArgs,
        risk="low",
        requires_approval=False,
        is_external=False
    ), handle_create_todo)
    reg.register(ToolSpec(
        name="list_todos",
        description="List todo items for the current user in the active project.",
        args_model=ListTodosArgs,
        risk="low",
        requires_approval=False,
        is_external=False
    ), handle_list_todos)
    reg.register(ToolSpec(
        name="draft_email",
        description="Draft an email (does not send).",
        args_model=DraftEmailArgs,
        risk="medium",
        requires_approval=False,
        is_external=False
    ), handle_draft_email)
    reg.register(ToolSpec(
        name="github_repo_search",
        description="Search public GitHub repositories (read-only).",
        args_model=GitHubRepoSearchArgs,
        risk="low",
        requires_approval=False,
        is_external=True
    ), handle_github_repo_search)
    reg.register(ToolSpec(
        name="webhook_post",
        description="POST JSON to an allowlisted webhook URL (high-risk; requires approval).",
        args_model=WebhookPostArgs,
        risk="high",
        requires_approval=True,
        is_external=True
    ), handle_webhook_post)
    return reg
