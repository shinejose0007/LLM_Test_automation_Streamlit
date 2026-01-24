import os
import streamlit as st
from dotenv import load_dotenv

from core import storage

load_dotenv()
st.set_page_config(page_title="DSR Workspace", page_icon="🧩", layout="wide")

db_path = os.getenv("APP_DB_PATH", "app.db")

st.title("🧩 Design Science Research Workspace")
st.caption("Capture requirements, design decisions, evaluation plan, and partner feedback per project.")

if "auth" not in st.session_state or not st.session_state.auth.get("is_authed"):
    st.warning("Please login first.")
    st.stop()

username = st.session_state.auth["username"]
role = st.session_state.auth["role"]
project_id = int(st.session_state.auth["project_id"])

tab1, tab2, tab3, tab4 = st.tabs(["Requirements", "Design Decisions", "Evaluation Plan", "Partner Feedback"])

with tab1:
    st.subheader("Add requirement")
    title = st.text_input("Title", key="req_title")
    desc = st.text_area("Description", height=120, key="req_desc")
    if st.button("Save requirement"):
        storage.add_requirement(project_id, title.strip() or "Untitled", desc.strip(), username, db_path=db_path)
        storage.log_event(project_id, username, role, "dsr_requirement_add", None, None, None, "ok", db_path=db_path)
        st.success("Saved.")
        st.rerun()
    st.divider()
    for r in storage.list_requirements(project_id, db_path=db_path)[:50]:
        with st.expander(f"#{r['id']} — {r['title']}"):
            st.write(r["description"])

with tab2:
    st.subheader("Add design decision")
    title = st.text_input("Decision title", key="dec_title")
    decision = st.text_area("Decision", height=100, key="dec_dec")
    rationale = st.text_area("Rationale", height=100, key="dec_rat")
    if st.button("Save decision"):
        storage.add_decision(project_id, title.strip() or "Untitled", decision.strip(), rationale.strip(), username, db_path=db_path)
        storage.log_event(project_id, username, role, "dsr_decision_add", None, None, None, "ok", db_path=db_path)
        st.success("Saved.")
        st.rerun()
    st.divider()
    for d in storage.list_decisions(project_id, db_path=db_path)[:50]:
        with st.expander(f"#{d['id']} — {d['title']}"):
            st.write("Decision:", d["decision"])
            st.write("Rationale:", d["rationale"])

with tab3:
    st.subheader("Evaluation plan")
    current = storage.get_eval_plan(project_id, db_path=db_path)
    plan_text = st.text_area("Plan", height=220, value=(current["plan"] if current else ""), key="eval_plan")
    if st.button("Save plan"):
        storage.upsert_eval_plan(project_id, plan_text.strip(), username, db_path=db_path)
        storage.log_event(project_id, username, role, "dsr_evalplan_upsert", None, None, None, "ok", db_path=db_path)
        st.success("Saved.")
        st.rerun()

with tab4:
    st.subheader("Partner feedback")
    partner = st.text_input("Partner name", key="fb_partner")
    fb = st.text_area("Feedback", height=160, key="fb_text")
    if st.button("Save feedback"):
        storage.add_feedback(project_id, partner.strip() or "Partner", fb.strip(), username, db_path=db_path)
        storage.log_event(project_id, username, role, "dsr_feedback_add", None, None, None, "ok", db_path=db_path)
        st.success("Saved.")
        st.rerun()
    st.divider()
    for f in storage.list_feedback(project_id, db_path=db_path)[:50]:
        with st.expander(f"#{f['id']} — {f['partner_name']}"):
            st.write(f["feedback"])
