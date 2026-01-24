from __future__ import annotations
import re
from typing import Dict

def extract_intent(text: str) -> Dict[str, str]:
    t = (text or "").strip()
    low = t.lower()

    if any(k in low for k in ["list my todos", "list todos", "show my tasks"]):
        intent = "list_todos"
    elif any(k in low for k in ["todo", "task", "remind", "to-do", "add task"]):
        intent = "create_todo"
    elif any(k in low for k in ["search", "find", "lookup", "knowledge base", "kb", "evidence"]):
        intent = "kb_search"
    elif any(k in low for k in ["summarize", "summary", "tl;dr"]):
        intent = "summarize_text"
    elif "github" in low:
        intent = "github_repo_search"
    elif "email" in low:
        intent = "draft_email"
    else:
        intent = "general"

    entities = re.findall(r"\b[A-Z][a-zA-Z0-9_-]{2,}\b", t)
    return {"intent": intent, "entities": ", ".join(entities[:12]), "snippet": t[:240]}

def minimize_for_llm(user_text: str) -> str:
    d = extract_intent(user_text)
    return f"Intent: {d['intent']}\nEntities: {d['entities']}\nUser snippet: {d['snippet']}"
