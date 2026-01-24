from __future__ import annotations
import json
from pathlib import Path
from . import storage
from .kb_ingest import chunk_text

def ensure_seed_kb(project_id: int, seed_path: str = "data/seed_kb.jsonl", owner: str = "system", db_path: str = "app.db") -> None:
    seed_file = Path(seed_path)
    if not seed_file.exists():
        return
    for line in seed_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        doc_id = d["doc_id"]
        title = d["title"]
        tags = ",".join(d.get("tags", []))
        trust = d.get("trust_level", "untrusted")
        source = d.get("source", "seed")
        text = d.get("text", "")

        storage.insert_kb_doc(doc_id, project_id, title, tags, trust, source, owner, db_path=db_path)
        storage.delete_kb_chunks(doc_id, db_path=db_path)
        for i, ch in enumerate(chunk_text(text)):
            storage.insert_kb_chunk(doc_id, i, ch, db_path=db_path)

def bootstrap(db_path: str = "app.db") -> None:
    storage.init_db(db_path)
