import os
import streamlit as st
from dotenv import load_dotenv

from core.auth import register_user, login_user
from core import storage

load_dotenv()
st.set_page_config(page_title="Login / Register", page_icon="🔐", layout="wide")

db_path = os.getenv("APP_DB_PATH", "app.db")

st.title("🔐 Login / Register")

if "auth" not in st.session_state:
    st.session_state.auth = {"is_authed": False, "username": None, "role": None, "project_id": None}

tab1, tab2 = st.tabs(["Login", "Register"])

with tab1:
    st.subheader("Login")
    u = st.text_input("Username", key="login_user")
    p = st.text_input("Password", type="password", key="login_pass")
    if st.button("Sign in"):
        ok, msg, user = login_user(u, p, db_path=db_path)
        if ok:
            st.session_state.auth = {"is_authed": True, "username": user["username"], "role": user["role"], "project_id": None}
            projs = storage.list_projects_for_user(user["username"], db_path=db_path)
            if projs:
                st.session_state.auth["project_id"] = int(projs[0]["id"])
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

with tab2:
    st.subheader("Register")
    u = st.text_input("Choose username (min 3 chars)", key="reg_user")
    p = st.text_input("Choose password (min 6 chars)", type="password", key="reg_pass")
    org = st.text_input("Organization name (optional)", key="reg_org")
    if st.button("Create account"):
        ok, msg, _ = register_user(u, p, org, db_path=db_path)
        if ok:
            st.success(msg)
            st.info("Now switch to Login tab to sign in.")
        else:
            st.error(msg)

st.divider()
if st.session_state.auth.get("is_authed"):
    st.success(f"Signed in: {st.session_state.auth['username']} ({st.session_state.auth['role']})")
    projs = storage.list_projects_for_user(st.session_state.auth["username"], db_path=db_path)
    if projs:
        labels = [f"{p['org_name']} / {p['name']} (id={p['id']})" for p in projs]
        ids = [int(p["id"]) for p in projs]
        current = st.session_state.auth.get("project_id") or ids[0]
        idx = ids.index(current) if current in ids else 0
        sel = st.selectbox("Active project", options=ids, format_func=lambda x: labels[ids.index(x)], index=idx)
        st.session_state.auth["project_id"] = int(sel)

    if st.button("Sign out"):
        st.session_state.auth = {"is_authed": False, "username": None, "role": None, "project_id": None}
        st.rerun()
else:
    st.info("Not signed in.")
