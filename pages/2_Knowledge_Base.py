import os
import streamlit as st
from dotenv import load_dotenv
import uuid
from pypdf import PdfReader

from core.policy import Policy
from core import storage
from core.kb_ingest import chunk_text
from core.safety import redact_pii, safe_json_dumps

load_dotenv()
st.set_page_config(page_title="Knowledge Base", page_icon="📚", layout="wide")

db_path = os.getenv("APP_DB_PATH", "app.db")
policy = Policy.load()

st.title("📚 Knowledge Base — Ingestion + Retrieval")
st.caption("Upload text or PDF → chunking → stored per-project. Trust level affects RAG filtering.")

if "auth" not in st.session_state or not st.session_state.auth.get("is_authed"):
    st.warning("Please login first.")
    st.stop()

username = st.session_state.auth["username"]
role = st.session_state.auth["role"]
project_id = int(st.session_state.auth["project_id"])

with st.expander("➕ Add document (text)"):
    title = st.text_input("Title", key="kb_title")
    tags = st.text_input("Tags (comma-separated)", value="notes", key="kb_tags")
    trust = st.selectbox("Trust level", ["trusted", "untrusted"], index=0, key="kb_trust")
    text = st.text_area("Text", height=200, key="kb_text")
    if st.button("Save text doc"):
        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        t = redact_pii(text) if policy.privacy().get("redact_pii_before_llm", True) else text
        storage.insert_kb_doc(doc_id, project_id, title.strip() or "Untitled", tags.strip(), trust, "manual", username, db_path=db_path)
        storage.delete_kb_chunks(doc_id, db_path=db_path)
        for i, ch in enumerate(chunk_text(t)):
            storage.insert_kb_chunk(doc_id, i, ch, db_path=db_path)
        storage.log_event(project_id, username, role, "kb_insert", "kb_doc", safe_json_dumps({"doc_id": doc_id, "title": title, "trust": trust}), None, "ok", db_path=db_path)
        st.success(f"Saved document {doc_id}")

with st.expander("📄 Add document (PDF upload)"):
    pdf = st.file_uploader("Upload PDF", type=["pdf"])
    title_pdf = st.text_input("Title for PDF", key="pdf_title")
    tags_pdf = st.text_input("Tags for PDF", value="pdf", key="pdf_tags")
    trust_pdf = st.selectbox("Trust level (PDF)", ["trusted", "untrusted"], index=1, key="pdf_trust")
    if st.button("Ingest PDF") and pdf is not None:
        try:
            reader = PdfReader(pdf)
            pages = []
            for p in reader.pages[:60]:
                pages.append(p.extract_text() or "")
            full = "\n".join(pages).strip()
            if not full:
                st.error("Could not extract text from this PDF.")
            else:
                doc_id = f"doc-{uuid.uuid4().hex[:8]}"
                t = redact_pii(full) if policy.privacy().get("redact_pii_before_llm", True) else full
                storage.insert_kb_doc(doc_id, project_id, title_pdf.strip() or "PDF Document", tags_pdf.strip(), trust_pdf, "pdf_upload", username, db_path=db_path)
                storage.delete_kb_chunks(doc_id, db_path=db_path)
                for i, ch in enumerate(chunk_text(t)):
                    storage.insert_kb_chunk(doc_id, i, ch, db_path=db_path)
                storage.log_event(project_id, username, role, "kb_insert", "kb_pdf", safe_json_dumps({"doc_id": doc_id, "pages": len(reader.pages)}), None, "ok", db_path=db_path)
                st.success(f"Ingested PDF into document {doc_id}")
        except Exception as e:
            st.error(f"PDF ingest failed: {str(e)[:200]}")

st.divider()
st.subheader("Documents in this project")
docs = storage.list_kb_docs(project_id, db_path=db_path)
for d in docs[:100]:
    with st.expander(f"{d['doc_id']} — {d['title']} ({d['trust_level']})"):
        st.write("Tags:", d["tags"])
        st.write("Source:", d["source"], "| Owner:", d["owner"])
