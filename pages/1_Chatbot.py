import os
import streamlit as st
from dotenv import load_dotenv
import time

from core.policy import Policy
from core import storage
from core.safety import redact_pii, safe_json_dumps, context_firewall, clamp_text
from core.tool_registry import build_registry
from core.rbac import can_use_tool
from core.llm import llm_plan

load_dotenv()
st.set_page_config(page_title="Chatbot", page_icon="💬", layout="wide")

db_path = os.getenv("APP_DB_PATH", "app.db")
policy = Policy.load()
role_permissions = policy.rbac_permissions()
registry = build_registry(policy)

st.title("💬 Chatbot — Safe Tool Calling + Hybrid RAG")

if "auth" not in st.session_state or not st.session_state.auth.get("is_authed"):
    st.warning("Please login on the Login/Register page first.")
    st.stop()

username = st.session_state.auth["username"]
role = st.session_state.auth["role"]
project_id = int(st.session_state.auth["project_id"])

with st.sidebar:
    st.subheader("Privacy & safety")
    enable_external_llm = st.toggle("Enable external LLM planning", value=policy.is_external_llm_enabled_default())
    data_minimization = st.toggle("Data minimization (send intent only)", value=policy.data_minimization_default())
    cite_only = st.toggle("Cite-only mode (when answering)", value=policy.cite_only_default())
    trusted_only = st.toggle("Require trusted KB only", value=policy.trusted_doc_required_default())

    st.divider()
    st.subheader("LLM settings (optional)")
    base_url = st.text_input("LLM_BASE_URL", value=os.getenv("LLM_BASE_URL", ""))
    api_key = st.text_input("LLM_API_KEY", value=os.getenv("LLM_API_KEY", ""), type="password")
    model = st.text_input("LLM_MODEL", value=os.getenv("LLM_MODEL", "gpt-4o-mini"))

    if not enable_external_llm:
        api_key = ""
        base_url = ""

st.caption("Planner → policy/RBAC → optional approval → tool execution → audit log + explainability.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

user_text = st.chat_input("Try: 'Search KB for tool calling safety', 'Add a todo: ...', 'Search GitHub repo ...'")

if user_text:
    cleaned = redact_pii(user_text) if policy.privacy().get("redact_pii_before_llm", True) else user_text
    storage.inc_metric("chat_messages_total", 1, db_path=db_path)

    st.session_state.messages.append({"role": "user", "content": cleaned})
    with st.chat_message("user"):
        st.markdown(cleaned)

    # RAG retrieval when needed
    retrieval_results = []
    if any(k in cleaned.lower() for k in ["kb", "knowledge", "search", "find", "lookup", "evidence"]):
        tool_ctx = {"username": username, "role": role, "project_id": project_id, "policy": policy}
        retrieval = registry.execute(
            "kb_search",
            registry.validate_args("kb_search", {"query": cleaned, "top_k": 5, "trusted_only": bool(trusted_only)}),
            tool_ctx
        )
        retrieval_results = retrieval.get("results", [])

    # Context firewall
    rag_cfg = policy.rag()
    blocked_regex = rag_cfg.get("blocked_instruction_regex", [])
    retrieved_context = ""
    removed_lines = []
    if retrieval_results:
        raw_ctx = "\n".join([f"[{r['doc_id']}:{r['chunk_index']}] {r['title']} ({r['trust_level']}): {r['snippet']}" for r in retrieval_results])
        fw, removed_lines = context_firewall(raw_ctx, blocked_regex)
        retrieved_context = clamp_text(fw, int(rag_cfg.get("max_context_chars", 2000)))

    # tool summaries for LLM
    tool_summaries = [{"name": n, "risk": s.risk, "requires_approval": s.requires_approval} for n, s in registry.list_specs().items()]

    plan, meta = llm_plan(
        user_text=cleaned,
        base_url=(base_url.strip() or None) if enable_external_llm else None,
        api_key=(api_key.strip() or None) if enable_external_llm else None,
        model=(model.strip() or "gpt-4o-mini"),
        tool_summaries=tool_summaries,
        retrieved_context=retrieved_context,
        cite_only=bool(cite_only),
        data_minimization=bool(data_minimization),
        max_input_chars=int(policy.privacy().get("max_llm_input_chars", 1200)),
    )

    storage.log_event(
        project_id, username, role, "plan",
        plan.tool_name if plan.action == "tool" else None,
        safe_json_dumps({"user_text": cleaned, "retrieved_count": len(retrieval_results)}),
        safe_json_dumps({"plan": plan.model_dump(), "meta": meta, "removed_lines": removed_lines[:5]}),
        "ok",
        notes=f"mode={meta.get('mode','llm')}",
        db_path=db_path
    )

    assistant_text = ""
    tool_trace = None

    if plan.action == "tool":
        tool_name = plan.tool_name or ""
        if tool_name not in registry.tools:
            assistant_text = "That tool is not available."
            storage.inc_metric("tool_blocked_total", 1, db_path=db_path)
        else:
            spec = registry.tools[tool_name]
            if not can_use_tool(role, tool_name, role_permissions):
                assistant_text = f"Blocked by RBAC: role **{role}** cannot use tool `{tool_name}`."
                storage.log_event(project_id, username, role, "tool_call", tool_name, safe_json_dumps(plan.tool_args), None, "blocked", notes="rbac", db_path=db_path)
                storage.inc_metric("tool_blocked_total", 1, db_path=db_path)
            else:
                try:
                    args_obj = registry.validate_args(tool_name, plan.tool_args or {})
                except Exception as e:
                    assistant_text = f"Blocked: invalid tool arguments ({str(e)[:160]})."
                    storage.log_event(project_id, username, role, "tool_call", tool_name, safe_json_dumps(plan.tool_args), None, "blocked", notes="arg_validation", db_path=db_path)
                    storage.inc_metric("tool_blocked_total", 1, db_path=db_path)
                    args_obj = None

                if args_obj:
                    if spec.requires_approval:
                        approval_id = storage.create_approval(project_id, username, role, tool_name, safe_json_dumps(plan.tool_args), db_path=db_path)
                        assistant_text = f"🟡 **Approval required** for `{tool_name}` (risk: {spec.risk}).\n\nCreated approval request **#{approval_id}**. Go to **Approvals** page to approve/deny."
                        storage.log_event(project_id, username, role, "approval_created", tool_name, safe_json_dumps(plan.tool_args), safe_json_dumps({"approval_id": approval_id}), "ok", db_path=db_path)
                        storage.inc_metric("approvals_created_total", 1, db_path=db_path)
                    else:
                        ctx = {"username": username, "role": role, "project_id": project_id, "policy": policy}
                        try:
                            t0 = time.time()
                            result = registry.execute(tool_name, args_obj, ctx)
                            latency = time.time() - t0
                            tool_trace = {"tool": tool_name, "risk": spec.risk, "args": plan.tool_args, "result": result, "latency_s": latency}
                            storage.log_event(project_id, username, role, "tool_call", tool_name, safe_json_dumps(plan.tool_args), safe_json_dumps(result), "ok", db_path=db_path)
                            storage.inc_metric("tool_calls_total", 1, db_path=db_path)
                            assistant_text = f"✅ Tool `{tool_name}` executed.\n\n```json\n{safe_json_dumps(result)}\n```"
                        except Exception as e:
                            assistant_text = f"Tool `{tool_name}` failed: {str(e)[:200]}"
                            storage.log_event(project_id, username, role, "tool_call", tool_name, safe_json_dumps(plan.tool_args), None, "fail", notes=str(e)[:200], db_path=db_path)
                            storage.inc_metric("tool_errors_total", 1, db_path=db_path)
    else:
        assistant_text = plan.final_answer or "I’m not sure—please rephrase."

    with st.chat_message("assistant"):
        st.markdown(assistant_text)
        with st.expander("Explainability / Trace"):
            st.write({"user": username, "role": role, "project_id": project_id})
            st.write("Planner meta:", meta)
            st.json(plan.model_dump())
            if retrieval_results:
                st.write("Retrieved evidence:")
                st.json(retrieval_results)
            if removed_lines:
                st.warning("Context firewall removed potential instruction-like lines.")
                st.code("\n".join(removed_lines[:6]))
            if tool_trace:
                st.write("Tool trace:")
                st.json(tool_trace)

    st.session_state.messages.append({"role": "assistant", "content": assistant_text})
