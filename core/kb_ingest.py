from __future__ import annotations
from typing import List
import re

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    t = re.sub(r"\s+", " ", t)
    chunks = []
    i = 0
    while i < len(t):
        chunks.append(t[i:i+chunk_size])
        i += max(1, chunk_size - overlap)
    return chunks

def score_lexical(query: str, text: str) -> float:
    q = (query or "").lower().strip()
    terms = [w for w in re.findall(r"[a-zA-Z0-9_]+", q) if len(w) >= 3]
    if not terms:
        return 0.0
    low = (text or "").lower()
    return float(sum(low.count(t) for t in terms))

def top_k_chunks(query: str, chunks: List[dict], k: int = 5, trusted_only: bool = False) -> List[dict]:
    scored = []
    for c in chunks:
        if trusted_only and c.get("trust_level") != "trusted":
            continue
        s = score_lexical(query, c.get("text", ""))
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for s, c in scored[:max(1, k)]:
        out.append({
            "doc_id": c.get("doc_id"),
            "title": c.get("title"),
            "trust_level": c.get("trust_level"),
            "tags": c.get("tags"),
            "chunk_index": c.get("chunk_index"),
            "score": float(s),
            "snippet": (c.get("text","")[:260] + ("…" if len(c.get("text","")) > 260 else "")),
        })
    return out
