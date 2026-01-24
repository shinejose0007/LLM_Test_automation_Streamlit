import os
import streamlit as st
from dotenv import load_dotenv
import pandas as pd

from core import storage

load_dotenv()
st.set_page_config(page_title="Observability", page_icon="📊", layout="wide")

db_path = os.getenv("APP_DB_PATH", "app.db")

st.title("📊 Observability — metrics counters & export")
st.caption("Lightweight observability: counters stored in SQLite, export as CSV or Prometheus-like text.")

metrics = storage.get_metrics(db_path=db_path)
if not metrics:
    st.info("No metrics yet. Use the chatbot to generate activity.")
else:
    df = pd.DataFrame([{"metric": k, "value": v} for k, v in sorted(metrics.items())])
    st.dataframe(df, use_container_width=True)
    st.download_button("Download metrics CSV", data=df.to_csv(index=False).encode("utf-8"),
                       file_name="metrics.csv", mime="text/csv")

    prom = "\n".join([f"{k} {v}" for k, v in sorted(metrics.items())])
    with st.expander("Prometheus-style text"):
        st.code(prom)
