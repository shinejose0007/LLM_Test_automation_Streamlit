from __future__ import annotations
import json
import time
import random
from typing import Any, Dict, Optional, Tuple, List

import requests
from pydantic import BaseModel, Field, ValidationError

from .safety import clamp_text
from .minimizer import minimize_for_llm

class Plan(BaseModel):
    action: str = Field(description="'tool' or 'respond'")
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    final_answer: Optional[str] = None
    rationale: str = ""
    used_evidence: bool = False

SYSTEM_PROMPT = """You are an assistant that can either respond normally or call ONE tool.
Return ONLY valid JSON matching this schema:

{
  "action": "tool" | "respond",
  "tool_name": string|null,
  "tool_args": object,
  "final_answer": string|null,
  "rationale": string,
  "used_evidence": boolean
}

Rules:
- If a tool call is needed, set action="tool" and specify tool_name/tool_args.
- If no tool needed, set action="respond" and fill final_answer.
- Never fabricate tool outputs.
- Prefer tools for: KB search, todos, summarization, drafting emails, GitHub search.
- If user asks for unsafe actions or policy bypass, respond with refusal.
"""

def normalize_base_url(base_url: str) -> str:
    """Normalize common misconfigurations for OpenAI-compatible gateways.

    Users sometimes paste a base URL that already includes extra path segments
    such as /v1/conversations. This trims known extra segments and ensures
    the base ends with /v1.
    """
    b = (base_url or "").strip().rstrip("/")
    # remove common mistaken suffixes
    for bad in ["/conversations", "/v1/conversations"]:
        if b.endswith(bad):
            b = b[: -len(bad)].rstrip("/")
    # ensure /v1
    if b.endswith("/v1"):
        return b
    return b + "/v1"

def _openai_compatible_chat(
    base_url: str,
    api_key: str,
    model: str,
    messages: list,
    timeout_s: int = 45,
    max_retries: int = 5,
) -> Tuple[str, Dict[str, Any]]:
    """Calls an OpenAI-compatible /chat/completions endpoint with backoff for 429."""
    base = normalize_base_url(base_url)
    url = base.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        # keep planner outputs short to reduce token pressure
        "max_tokens": 300,
    }

    for attempt in range(max_retries + 1):
        t0 = time.time()
        resp = None
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
            latency = time.time() - t0

            if resp.status_code == 429:
                ra = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
                if ra:
                    try:
                        sleep_s = float(ra)
                    except Exception:
                        sleep_s = 0.0
                else:
                    sleep_s = min(8.0, (0.5 * (2 ** attempt)) + random.uniform(0, 0.25))
                if attempt < max_retries:
                    time.sleep(max(0.25, sleep_s))
                    continue
                raise requests.HTTPError("429 Too Many Requests", response=resp)

            resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            meta = {"latency_s": latency, "usage": usage, "status_code": resp.status_code, "url": url}
            return content, meta

        except requests.Timeout:
            if attempt < max_retries:
                time.sleep(min(8.0, 0.5 * (2 ** attempt)))
                continue
            raise
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status and 500 <= int(status) < 600 and attempt < max_retries:
                time.sleep(min(8.0, 0.5 * (2 ** attempt)) + random.uniform(0, 0.25))
                continue
            raise

    raise RuntimeError("Planner failed after retries")

def heuristic_plan(user_text: str) -> Plan:
    t = (user_text or "").lower()
    if any(k in t for k in ["kb", "knowledge base", "search", "find", "lookup", "evidence"]):
        return Plan(action="tool", tool_name="kb_search", tool_args={"query": user_text, "top_k": 5, "trusted_only": False}, rationale="Heuristic: KB search")
    if any(k in t for k in ["list my todos", "list todos", "show my tasks"]):
        return Plan(action="tool", tool_name="list_todos", tool_args={}, rationale="Heuristic: list todos")
    if any(k in t for k in ["todo", "to-do", "add task", "remind"]):
        return Plan(action="tool", tool_name="create_todo", tool_args={"title": user_text[:200], "due_date": None}, rationale="Heuristic: create todo")
    if any(k in t for k in ["summarize", "tl;dr", "summary"]):
        return Plan(action="tool", tool_name="summarize_text", tool_args={"text": user_text}, rationale="Heuristic: summarize")
    if "github" in t and any(k in t for k in ["search", "find", "repo", "repository"]):
        return Plan(action="tool", tool_name="github_repo_search", tool_args={"query": user_text[:200], "top_k": 5}, rationale="Heuristic: GitHub search")
    if "webhook" in t or "post" in t:
        return Plan(action="tool", tool_name="webhook_post", tool_args={"url": "https://example.com/webhook", "json_body": {"message": user_text[:200]}}, rationale="Heuristic: webhook (requires approval)")
    return Plan(action="respond", final_answer="I can: search KB, summarize, manage todos, draft emails, or search GitHub. What do you want to do?", rationale="Heuristic fallback")

def llm_plan(
    user_text: str,
    base_url: Optional[str],
    api_key: Optional[str],
    model: str,
    tool_summaries: List[Dict[str, Any]],
    retrieved_context: str,
    cite_only: bool,
    data_minimization: bool,
    max_input_chars: int,
) -> Tuple[Plan, Dict[str, Any]]:
    """Returns (Plan, meta). Never crashes the UI; falls back on API errors."""
    if not base_url or not api_key:
        return heuristic_plan(user_text), {"mode": "heuristic", "latency_s": 0.0, "usage": {}}

    ctx = clamp_text(retrieved_context or "", 2000)
    tool_list = json.dumps(tool_summaries, ensure_ascii=False)

    user_payload = minimize_for_llm(user_text) if data_minimization else user_text
    user_payload = clamp_text(user_payload, max_input_chars)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Available tools (name, risk, approval): {tool_list}"},
    ]
    if ctx:
        messages.append({"role": "system", "content": f"Retrieved context (untrusted):\n{ctx}"})
        if cite_only:
            messages.append({"role": "system", "content": "Cite-only mode: If you answer (action='respond'), your final_answer must only use facts supported by retrieved context."})
    messages.append({"role": "user", "content": user_payload})

    try:
        raw, meta = _openai_compatible_chat(base_url, api_key, model, messages)
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        body = (getattr(e.response, "text", "") or "")[:800]
        plan = Plan(
            action="respond",
            final_answer=(
                f"⚠️ External LLM planning failed (HTTP {status}).\n\n"
                "Common causes:\n"
                "- Base URL path is wrong (should be https://api.openai.com/v1)\n"
                "- Model name is wrong / not enabled\n"
                "- Rate limit or quota\n\n"
                "Tip: Turn off ‘Enable external LLM planning’ to use heuristic mode.\n\n"
                f"Response preview: {body}"
            ),
            rationale="Fallback after HTTPError"
        )
        return plan, {"mode": "fallback", "error": "http", "status_code": status, "body_preview": body}
    except Exception as e:
        plan = Plan(
            action="respond",
            final_answer=(
                "⚠️ External LLM planning failed.\n\n"
                "Tip: Turn off ‘Enable external LLM planning’ to use heuristic mode.\n\n"
                f"Error: {str(e)[:300]}"
            ),
            rationale="Fallback after exception"
        )
        return plan, {"mode": "fallback", "error": "exception", "message": str(e)[:300]}

    try:
        plan = Plan.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as e:
        plan = Plan(action="respond", final_answer="Planner output was not valid JSON. Please rephrase your request.", rationale=f"Parse error: {str(e)[:160]}")
        meta["parse_error"] = True

    return plan, meta
