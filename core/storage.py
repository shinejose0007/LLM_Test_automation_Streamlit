from __future__ import annotations
import os
import sqlite3
import time
from typing import List, Optional, Dict
import hashlib

DEFAULT_DB_PATH = os.getenv("APP_DB_PATH", "app.db")

def get_conn(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_conn(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")

    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    cur = conn.execute("SELECT COUNT(*) as c FROM schema_version")
    if int(cur.fetchone()["c"]) == 0:
        conn.execute("INSERT INTO schema_version(version) VALUES(1)")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
      username TEXT PRIMARY KEY,
      password_hash TEXT NOT NULL,
      salt TEXT NOT NULL,
      role TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS orgs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      created_at INTEGER NOT NULL
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS projects (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      org_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      UNIQUE(org_id, name)
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS memberships (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL,
      org_id INTEGER NOT NULL,
      role_in_org TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      UNIQUE(username, org_id)
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS kb_docs (
      doc_id TEXT PRIMARY KEY,
      project_id INTEGER NOT NULL,
      title TEXT NOT NULL,
      tags TEXT NOT NULL,
      trust_level TEXT NOT NULL,
      source TEXT NOT NULL,
      owner TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS kb_chunks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      doc_id TEXT NOT NULL,
      chunk_index INTEGER NOT NULL,
      text TEXT NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS todos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL,
      username TEXT NOT NULL,
      title TEXT NOT NULL,
      due_date TEXT,
      status TEXT NOT NULL DEFAULT 'open',
      created_at INTEGER NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS approvals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL,
      requested_by TEXT NOT NULL,
      requested_role TEXT NOT NULL,
      tool_name TEXT NOT NULL,
      args_json TEXT NOT NULL,
      status TEXT NOT NULL, -- proposed/approved/denied/executed
      created_at INTEGER NOT NULL,
      decided_at INTEGER,
      decided_by TEXT,
      decision_notes TEXT
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      project_id INTEGER NOT NULL,
      username TEXT NOT NULL,
      role TEXT NOT NULL,
      event_type TEXT NOT NULL,
      tool_name TEXT,
      request_json TEXT,
      result_json TEXT,
      outcome TEXT NOT NULL,
      notes TEXT,
      prev_hash TEXT,
      this_hash TEXT
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
      key TEXT PRIMARY KEY,
      value INTEGER NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS dsr_requirements (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL,
      title TEXT NOT NULL,
      description TEXT NOT NULL,
      created_by TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS dsr_decisions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL,
      title TEXT NOT NULL,
      decision TEXT NOT NULL,
      rationale TEXT NOT NULL,
      created_by TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS dsr_evaluation_plan (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL,
      plan TEXT NOT NULL,
      created_by TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS dsr_feedback (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL,
      partner_name TEXT NOT NULL,
      feedback TEXT NOT NULL,
      created_by TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    """)

    conn.commit()
    conn.close()

# --- users ---
def upsert_user(username: str, password_hash: str, salt: str, role: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_conn(db_path)
    conn.execute(
        "INSERT INTO users(username,password_hash,salt,role,created_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash, salt=excluded.salt, role=excluded.role",
        (username, password_hash, salt, role, int(time.time()))
    )
    conn.commit()
    conn.close()

def get_user(username: str, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT * FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def user_count(db_path: str = DEFAULT_DB_PATH) -> int:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT COUNT(*) as c FROM users")
    n = int(cur.fetchone()["c"])
    conn.close()
    return n

# --- org/projects ---
def get_or_create_org(name: str, db_path: str = DEFAULT_DB_PATH) -> int:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT id FROM orgs WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        org_id = int(row["id"])
    else:
        cur = conn.execute("INSERT INTO orgs(name,created_at) VALUES(?,?)", (name, int(time.time())))
        org_id = int(cur.lastrowid)
        conn.commit()
    conn.close()
    return org_id

def create_project(org_id: int, name: str, db_path: str = DEFAULT_DB_PATH) -> int:
    conn = get_conn(db_path)
    conn.execute("INSERT OR IGNORE INTO projects(org_id,name,created_at) VALUES(?,?,?)", (org_id, name, int(time.time())))
    conn.commit()
    cur = conn.execute("SELECT id FROM projects WHERE org_id=? AND name=?", (org_id, name))
    pid = int(cur.fetchone()["id"])
    conn.close()
    return pid

def add_membership(username: str, org_id: int, role_in_org: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_conn(db_path)
    conn.execute("INSERT OR IGNORE INTO memberships(username,org_id,role_in_org,created_at) VALUES(?,?,?,?)",
                 (username, org_id, role_in_org, int(time.time())))
    conn.commit()
    conn.close()

def list_projects_for_user(username: str, db_path: str = DEFAULT_DB_PATH) -> List[dict]:
    conn = get_conn(db_path)
    cur = conn.execute("""
      SELECT p.id, p.name, o.name as org_name
      FROM memberships m
      JOIN orgs o ON o.id=m.org_id
      JOIN projects p ON p.org_id=o.id
      WHERE m.username=?
      ORDER BY o.name, p.name
    """, (username,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# --- KB ---
def insert_kb_doc(doc_id: str, project_id: int, title: str, tags_csv: str, trust_level: str, source: str, owner: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_conn(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO kb_docs(doc_id,project_id,title,tags,trust_level,source,owner,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (doc_id, project_id, title, tags_csv, trust_level, source, owner, int(time.time()))
    )
    conn.commit()
    conn.close()

def delete_kb_chunks(doc_id: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_conn(db_path)
    conn.execute("DELETE FROM kb_chunks WHERE doc_id=?", (doc_id,))
    conn.commit()
    conn.close()

def insert_kb_chunk(doc_id: str, chunk_index: int, text: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_conn(db_path)
    conn.execute("INSERT INTO kb_chunks(doc_id,chunk_index,text) VALUES(?,?,?)", (doc_id, chunk_index, text))
    conn.commit()
    conn.close()

def list_kb_docs(project_id: int, db_path: str = DEFAULT_DB_PATH) -> List[dict]:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT * FROM kb_docs WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def list_kb_chunks_for_project(project_id: int, db_path: str = DEFAULT_DB_PATH) -> List[dict]:
    conn = get_conn(db_path)
    cur = conn.execute("""
      SELECT d.doc_id, d.title, d.tags, d.trust_level, c.chunk_index, c.text
      FROM kb_docs d JOIN kb_chunks c ON c.doc_id=d.doc_id
      WHERE d.project_id=?
    """, (project_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# --- Todos ---
def add_todo(project_id: int, username: str, title: str, due_date: Optional[str], db_path: str = DEFAULT_DB_PATH) -> int:
    conn = get_conn(db_path)
    cur = conn.execute(
        "INSERT INTO todos(project_id,username,title,due_date,status,created_at) VALUES(?,?,?,?,?,?)",
        (project_id, username, title, due_date, "open", int(time.time()))
    )
    todo_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return todo_id

def list_todos(project_id: int, username: str, db_path: str = DEFAULT_DB_PATH) -> List[dict]:
    conn = get_conn(db_path)
    cur = conn.execute(
        "SELECT * FROM todos WHERE project_id=? AND username=? ORDER BY created_at DESC",
        (project_id, username)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# --- approvals ---
def create_approval(project_id: int, requested_by: str, requested_role: str, tool_name: str, args_json: str, db_path: str = DEFAULT_DB_PATH) -> int:
    conn = get_conn(db_path)
    cur = conn.execute("""
      INSERT INTO approvals(project_id,requested_by,requested_role,tool_name,args_json,status,created_at)
      VALUES(?,?,?,?,?,'proposed',?)
    """, (project_id, requested_by, requested_role, tool_name, args_json, int(time.time())))
    aid = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return aid

def list_approvals(project_id: int, status: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> List[dict]:
    conn = get_conn(db_path)
    if status:
        cur = conn.execute("SELECT * FROM approvals WHERE project_id=? AND status=? ORDER BY created_at DESC", (project_id, status))
    else:
        cur = conn.execute("SELECT * FROM approvals WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_approval(approval_id: int, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def decide_approval(approval_id: int, status: str, decided_by: str, notes: str = "", db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_conn(db_path)
    conn.execute("""
      UPDATE approvals
      SET status=?, decided_at=?, decided_by=?, decision_notes=?
      WHERE id=?
    """, (status, int(time.time()), decided_by, notes, approval_id))
    conn.commit()
    conn.close()

# --- audit logs (hash chain) ---
def _hash_log(prev_hash: str, payload: str) -> str:
    h = hashlib.sha256()
    h.update((prev_hash or "").encode("utf-8"))
    h.update(payload.encode("utf-8"))
    return h.hexdigest()

def log_event(
    project_id: int,
    username: str,
    role: str,
    event_type: str,
    tool_name: Optional[str],
    request_json: Optional[str],
    result_json: Optional[str],
    outcome: str,
    notes: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT this_hash FROM audit_logs WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,))
    row = cur.fetchone()
    prev_hash = (row["this_hash"] if row else "") or ""
    payload = f"{int(time.time())}|{project_id}|{username}|{role}|{event_type}|{tool_name or ''}|{request_json or ''}|{result_json or ''}|{outcome}|{notes or ''}"
    this_hash = _hash_log(prev_hash, payload)
    conn.execute(
        "INSERT INTO audit_logs(ts,project_id,username,role,event_type,tool_name,request_json,result_json,outcome,notes,prev_hash,this_hash) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (int(time.time()), project_id, username, role, event_type, tool_name, request_json, result_json, outcome, notes, prev_hash, this_hash)
    )
    conn.commit()
    conn.close()

def list_logs(project_id: int, limit: int = 200, db_path: str = DEFAULT_DB_PATH) -> List[dict]:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT * FROM audit_logs WHERE project_id=? ORDER BY id DESC LIMIT ?", (project_id, limit))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def purge_old_logs(project_id: int, retention_days: int, db_path: str = DEFAULT_DB_PATH) -> int:
    cutoff = int(time.time()) - int(retention_days) * 86400
    conn = get_conn(db_path)
    cur = conn.execute("DELETE FROM audit_logs WHERE project_id=? AND ts < ?", (project_id, cutoff))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return int(deleted or 0)

# --- metrics ---
def inc_metric(key: str, delta: int = 1, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_conn(db_path)
    conn.execute("INSERT INTO metrics(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=value+?",
                 (key, delta, delta))
    conn.commit()
    conn.close()

def get_metrics(db_path: str = DEFAULT_DB_PATH) -> Dict[str, int]:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT key,value FROM metrics")
    d = {r["key"]: int(r["value"]) for r in cur.fetchall()}
    conn.close()
    return d

# --- DSR ---
def add_requirement(project_id: int, title: str, description: str, created_by: str, db_path: str = DEFAULT_DB_PATH) -> int:
    conn = get_conn(db_path)
    cur = conn.execute("INSERT INTO dsr_requirements(project_id,title,description,created_by,created_at) VALUES(?,?,?,?,?)",
                       (project_id, title, description, created_by, int(time.time())))
    rid = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return rid

def list_requirements(project_id: int, db_path: str = DEFAULT_DB_PATH) -> List[dict]:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT * FROM dsr_requirements WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def add_decision(project_id: int, title: str, decision: str, rationale: str, created_by: str, db_path: str = DEFAULT_DB_PATH) -> int:
    conn = get_conn(db_path)
    cur = conn.execute("INSERT INTO dsr_decisions(project_id,title,decision,rationale,created_by,created_at) VALUES(?,?,?,?,?,?)",
                       (project_id, title, decision, rationale, created_by, int(time.time())))
    did = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return did

def list_decisions(project_id: int, db_path: str = DEFAULT_DB_PATH) -> List[dict]:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT * FROM dsr_decisions WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def upsert_eval_plan(project_id: int, plan: str, created_by: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_conn(db_path)
    conn.execute("DELETE FROM dsr_evaluation_plan WHERE project_id=?", (project_id,))
    conn.execute("INSERT INTO dsr_evaluation_plan(project_id,plan,created_by,created_at) VALUES(?,?,?,?)",
                 (project_id, plan, created_by, int(time.time())))
    conn.commit()
    conn.close()

def get_eval_plan(project_id: int, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT * FROM dsr_evaluation_plan WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def add_feedback(project_id: int, partner_name: str, feedback: str, created_by: str, db_path: str = DEFAULT_DB_PATH) -> int:
    conn = get_conn(db_path)
    cur = conn.execute("INSERT INTO dsr_feedback(project_id,partner_name,feedback,created_by,created_at) VALUES(?,?,?,?,?)",
                       (project_id, partner_name, feedback, created_by, int(time.time())))
    fid = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return fid

def list_feedback(project_id: int, db_path: str = DEFAULT_DB_PATH) -> List[dict]:
    conn = get_conn(db_path)
    cur = conn.execute("SELECT * FROM dsr_feedback WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
