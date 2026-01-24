import os
import streamlit as st
from dotenv import load_dotenv

from core.bootstrap import bootstrap, ensure_seed_kb
from core.policy import Policy
from core import storage

st.set_page_config(page_title="LLM Task Automation Lab v2", page_icon="🤖", layout="wide")
load_dotenv()

db_path = os.getenv("APP_DB_PATH", "app.db")
bootstrap(db_path=db_path)
policy = Policy.load()

if "auth" not in st.session_state:
    st.session_state.auth = {"is_authed": False, "username": None, "role": None, "project_id": None}

st.title("🤖 LLM Task Automation Lab — v2")

if not st.session_state.auth["is_authed"]:
    st.warning("Please open **Login/Register** (left sidebar) to create an account and sign in.")
    st.stop()

if not st.session_state.auth.get("project_id"):
    projs = storage.list_projects_for_user(st.session_state.auth["username"], db_path=db_path)
    if projs:
        st.session_state.auth["project_id"] = int(projs[0]["id"])

ensure_seed_kb(project_id=int(st.session_state.auth["project_id"]), seed_path="data/seed_kb.jsonl", owner="system", db_path=db_path)

st.markdown(
"""
✅ You are logged in.

Use the sidebar pages:

- **Chatbot**
- **Knowledge Base**
- **Approvals**
- **Benchmarking**
- **Attack Lab**
- **DSR Workspace**
- **Observability**
- **Admin & Audit**
"""
)
