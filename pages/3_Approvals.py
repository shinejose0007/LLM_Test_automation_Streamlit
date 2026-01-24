import os
import streamlit as st
from dotenv import load_dotenv
import json

from core.policy import Policy
from core import storage
from core.tool_registry import build_registry
from core.rbac import can_use_tool
from core.safety import safe_json_dumps

load_dotenv()
st.set_page_config(page_title="Approvals", page_icon="🟡", layout="wide")

db_path = os.getenv("APP_DB_PATH", "app.db")
policy = Policy.load()
role_permissions = policy.rbac_permissions()
registry = build_registry(policy)

st.title("🟡 Approvals — High-risk actions")

if "auth" not in st.session_state or not st.session_state.auth.get("is_authed"):
    st.warning("Please login first.")
    st.stop()

username = st.session_state.auth["username"]
role = st.session_state.auth["role"]
project_id = int(st.session_state.auth["project_id"])

st.caption("High-risk tools (e.g., webhook_post) require an approval request. Admin can approve/deny, then execute.")

pending = storage.list_approvals(project_id, status="proposed", db_path=db_path)
st.subheader(f"Pending approvals ({len(pending)})")

if not pending:
    st.info("No pending approvals.")
else:
    for a in pending[:50]:
        with st.expander(f"#{a['id']} — {a['tool_name']} requested by {a['requested_by']} ({a['requested_role']})"):
            st.code(a["args_json"])
            if role != "Admin":
                st.warning("Admin role required to approve/deny.")
            else:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"Approve #{a['id']}"):
                        storage.decide_approval(a["id"], "approved", decided_by=username, notes="approved", db_path=db_path)
                        storage.log_event(project_id, username, role, "approval_decide", a["tool_name"], a["args_json"], safe_json_dumps({"status":"approved"}), "ok", db_path=db_path)
                        st.success("Approved.")
                        st.rerun()
                with col2:
                    if st.button(f"Deny #{a['id']}"):
                        storage.decide_approval(a["id"], "denied", decided_by=username, notes="denied", db_path=db_path)
                        storage.log_event(project_id, username, role, "approval_decide", a["tool_name"], a["args_json"], safe_json_dumps({"status":"denied"}), "ok", db_path=db_path)
                        st.success("Denied.")
                        st.rerun()

st.divider()
st.subheader("Execute approved actions")

approved = storage.list_approvals(project_id, status="approved", db_path=db_path)
if not approved:
    st.info("No approved actions to execute.")
else:
    ids = [a["id"] for a in approved]
    sel = st.selectbox("Select approved request", options=ids)
    a = storage.get_approval(int(sel), db_path=db_path)
    st.write("Tool:", a["tool_name"])
    st.code(a["args_json"])
    if st.button("Execute now"):
        tool_name = a["tool_name"]
        if tool_name not in registry.tools:
            st.error("Tool no longer available.")
        elif not can_use_tool(role, tool_name, role_permissions):
            st.error("Your role cannot execute this tool.")
        else:
            ctx = {"username": a["requested_by"], "role": a["requested_role"], "project_id": project_id, "policy": policy}
            try:
                args = json.loads(a["args_json"])
                args_obj = registry.validate_args(tool_name, args)
                result = registry.execute(tool_name, args_obj, ctx)
                storage.log_event(project_id, username, role, "approved_tool_exec", tool_name, a["args_json"], safe_json_dumps(result), "ok", db_path=db_path)
                storage.decide_approval(int(sel), "executed", decided_by=username, notes="executed", db_path=db_path)
                st.success("Executed.")
                st.json(result)
                st.rerun()
            except Exception as e:
                storage.log_event(project_id, username, role, "approved_tool_exec", tool_name, a["args_json"], None, "fail", notes=str(e)[:200], db_path=db_path)
                st.error(f"Execution failed: {str(e)[:200]}")
