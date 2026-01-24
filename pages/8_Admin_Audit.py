import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from core import storage

load_dotenv()
st.set_page_config(page_title="Admin & Audit", page_icon="🛡️", layout="wide")

db_path = os.getenv("APP_DB_PATH", "app.db")
retention_days = int(os.getenv("APP_LOG_RETENTION_DAYS", "30"))

st.title("🛡️ Admin & Audit — logs, retention, roles, projects")

if "auth" not in st.session_state or not st.session_state.auth.get("is_authed"):
    st.warning("Please login first.")
    st.stop()

username = st.session_state.auth["username"]
role = st.session_state.auth["role"]
project_id = int(st.session_state.auth["project_id"])

if role != "Admin":
    st.error("Admin role required.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Audit logs", "Retention", "Users & Projects"])

with tab1:
    logs = storage.list_logs(project_id, limit=500, db_path=db_path)
    df = pd.DataFrame(logs)
    if df.empty:
        st.info("No logs yet.")
    else:
        df["ts_readable"] = pd.to_datetime(df["ts"], unit="s")
        st.dataframe(df[["id","ts_readable","username","role","event_type","tool_name","outcome","notes","prev_hash","this_hash"]],
                     use_container_width=True)
        st.download_button("Download logs CSV", data=df.to_csv(index=False).encode("utf-8"),
                           file_name="audit_logs.csv", mime="text/csv")
        st.info("Hash chain provides tamper-evidence: each log includes prev_hash → this_hash.")

with tab2:
    st.write(f"Retention days: **{retention_days}** (env APP_LOG_RETENTION_DAYS)")
    if st.button("Purge old logs"):
        deleted = storage.purge_old_logs(project_id, retention_days, db_path=db_path)
        storage.log_event(project_id, username, role, "purge_logs", None, None, str(deleted), "ok", db_path=db_path)
        st.success(f"Deleted {deleted} logs.")
        st.rerun()

with tab3:
    st.subheader("Update user role")
    u = st.text_input("Username to update")
    new_role = st.selectbox("Role", ["Admin","Researcher","Viewer"], index=1)
    if st.button("Update role"):
        user = storage.get_user(u.strip(), db_path=db_path)
        if not user:
            st.error("User not found")
        else:
            storage.upsert_user(user["username"], user["password_hash"], user["salt"], new_role, db_path=db_path)
            storage.log_event(project_id, username, role, "user_role_update", None, u, new_role, "ok", db_path=db_path)
            st.success("Updated role.")

    st.divider()
    st.subheader("Create a new project in an org")
    org_name = st.text_input("Org name (existing or new)", value="demo-org")
    proj_name = st.text_input("Project name", value="project-1")
    if st.button("Create project"):
        org_id = storage.get_or_create_org(org_name.strip(), db_path=db_path)
        pid = storage.create_project(org_id, proj_name.strip(), db_path=db_path)
        storage.add_membership(username, org_id, "owner", db_path=db_path)
        storage.log_event(project_id, username, role, "project_create", None, org_name, str(pid), "ok", db_path=db_path)
        st.success(f"Created project id={pid}. Go to Login/Register to select it.")
