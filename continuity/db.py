"""SQLite database layer for Continuity."""

import json
import os
import sqlite3
from typing import Optional

from .config import get_db_path, ensure_directories
from .models import (
    AgentState, SessionThread, StateSnapshot, Handoff,
    now_iso, gen_id,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_state (
    id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    communication_style TEXT DEFAULT '',
    relationship_position TEXT DEFAULT '',
    long_term_preferences TEXT DEFAULT '[]',
    boundaries TEXT DEFAULT '[]',
    stable_patterns TEXT DEFAULT '[]',
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS session_threads (
    thread_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    agent_id TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'private',
    topic TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'general',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    last_position TEXT DEFAULT '',
    next_step TEXT DEFAULT '',
    state_summary TEXT DEFAULT '',
    facts_used TEXT DEFAULT '[]',
    current_interpretation TEXT DEFAULT '',
    interpretation_status TEXT DEFAULT 'active',
    user_confirmed INTEGER DEFAULT 0,
    source_session TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    notes TEXT DEFAULT '',
    updated_by TEXT DEFAULT 'agent'
);

CREATE TABLE IF NOT EXISTS state_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    agent_id TEXT NOT NULL DEFAULT 'default',
    visibility TEXT NOT NULL DEFAULT 'private',
    name TEXT NOT NULL,
    source_thread_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    state_summary TEXT DEFAULT '',
    tone TEXT DEFAULT '',
    relationship_context TEXT DEFAULT '',
    working_posture TEXT DEFAULT '',
    reuse_notes TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    FOREIGN KEY (source_thread_id) REFERENCES session_threads(thread_id)
);

CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    agent_id TEXT NOT NULL DEFAULT 'default',
    visibility TEXT NOT NULL DEFAULT 'private',
    thread_id TEXT,
    created_at TEXT NOT NULL,
    objective TEXT DEFAULT '',
    completed TEXT DEFAULT '[]',
    open_items TEXT DEFAULT '[]',
    next_step TEXT DEFAULT '',
    do_not_confuse TEXT DEFAULT '[]',
    notes TEXT DEFAULT '',
    FOREIGN KEY (thread_id) REFERENCES session_threads(thread_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    time TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    details TEXT DEFAULT '{}'
);
"""


def _connect() -> sqlite3.Connection:
    ensure_directories()
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> str:
    """Create tables. Returns db path."""
    ensure_directories()
    conn = _connect()
    conn.executescript(SCHEMA)
    _migrate_schema(conn)
    conn.commit()
    db_path = get_db_path()
    conn.close()
    return db_path


def _table_columns(conn: sqlite3.Connection, table: str) -> set:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str,
                           ddl: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Keep old continuity.db files compatible with the current schema."""
    for table in ("session_threads", "state_snapshots", "handoffs"):
        _add_column_if_missing(
            conn, table, "agent_id", "agent_id TEXT NOT NULL DEFAULT 'default'"
        )
        _add_column_if_missing(
            conn, table, "visibility", "visibility TEXT NOT NULL DEFAULT 'private'"
        )
        conn.execute(
            f"UPDATE {table} SET agent_id = 'default' WHERE agent_id IS NULL OR agent_id = ''"
        )
    _add_column_if_missing(
        conn, "session_threads", "facts_used", "facts_used TEXT DEFAULT '[]'"
    )
    _add_column_if_missing(
        conn, "session_threads", "current_interpretation",
        "current_interpretation TEXT DEFAULT ''"
    )
    _add_column_if_missing(
        conn, "session_threads", "interpretation_status",
        "interpretation_status TEXT DEFAULT 'active'"
    )
    _add_column_if_missing(
        conn, "session_threads", "user_confirmed",
        "user_confirmed INTEGER DEFAULT 0"
    )


def _record_audit(conn: sqlite3.Connection, actor: str, action: str,
                  target_type: str, target_id: Optional[str] = None,
                  details: dict = None) -> None:
    conn.execute(
        """INSERT INTO audit_events (event_id, time, actor, action, target_type, target_id, details)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (gen_id("audit"), now_iso(), actor, action, target_type, target_id,
         json.dumps(details or {}, ensure_ascii=False))
    )


def _row_to_dict(row: sqlite3.Row) -> dict:
    if row is None:
        return None
    return dict(row)


def _deserialize_json_fields(data: dict, fields: list) -> dict:
    """Deserialize JSON string fields in a dict."""
    for f in fields:
        if f in data and isinstance(data[f], str):
            try:
                data[f] = json.loads(data[f])
            except (json.JSONDecodeError, TypeError):
                pass
    return data


# ── Agent State ──────────────────────────────────────────────

def ensure_agent_state(agent_id: str) -> None:
    conn = _connect()
    row = conn.execute("SELECT id FROM agent_state WHERE id = ?", (agent_id,)).fetchone()
    if not row:
        conn.execute(
            """INSERT OR IGNORE INTO agent_state (id, version, updated_at)
               VALUES (?, 1, ?)""",
            (agent_id, now_iso())
        )
        _record_audit(conn, "system", "init_agent_state", "agent_state", agent_id, {})
        conn.commit()
    conn.close()


def get_agent_state(agent_id: str) -> dict:
    ensure_agent_state(agent_id)
    conn = _connect()
    row = conn.execute("SELECT * FROM agent_state WHERE id = ?", (agent_id,)).fetchone()
    conn.close()
    result = _row_to_dict(row)
    if result:
        result = _deserialize_json_fields(result, [
            "long_term_preferences", "boundaries", "stable_patterns"
        ])
    return result


def update_agent_state(agent_id: str, actor: str = "user", **kwargs) -> dict:
    """Update agent_state fields. Only updates provided keys."""
    ensure_agent_state(agent_id)
    allowed = {
        "communication_style", "relationship_position",
        "long_term_preferences", "boundaries", "stable_patterns", "notes"
    }
    updates = {}
    for k, v in kwargs.items():
        if k in allowed:
            if isinstance(v, list):
                updates[k] = json.dumps(v, ensure_ascii=False)
            else:
                updates[k] = v
    if not updates:
        return get_agent_state(agent_id)

    updates["updated_at"] = now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [agent_id]

    conn = _connect()
    conn.execute(f"UPDATE agent_state SET {set_clause} WHERE id = ?", values)
    _record_audit(conn, actor, "update_agent_state", "agent_state", agent_id,
                  {"agent_id": agent_id, "updated_fields": list(kwargs.keys())})
    conn.commit()
    conn.close()
    return get_agent_state(agent_id)


# ── Session Threads ──────────────────────────────────────────

def create_thread(thread: SessionThread, actor: str = "agent") -> dict:
    conn = _connect()
    d = {
        "thread_id": thread.thread_id,
        "version": thread.version,
        "agent_id": thread.agent_id,
        "visibility": thread.visibility,
        "topic": thread.topic,
        "mode": thread.mode,
        "status": thread.status,
        "created_at": thread.created_at,
        "last_active_at": thread.last_active_at,
        "last_position": thread.last_position,
        "next_step": thread.next_step,
        "state_summary": thread.state_summary,
        "facts_used": json.dumps(thread.facts_used, ensure_ascii=False),
        "current_interpretation": thread.current_interpretation,
        "interpretation_status": thread.interpretation_status,
        "user_confirmed": int(thread.user_confirmed),
        "source_session": thread.source_session,
        "tags": json.dumps(thread.tags, ensure_ascii=False),
        "notes": thread.notes,
        "updated_by": thread.updated_by,
    }
    conn.execute(
        """INSERT INTO session_threads
           (thread_id, version, agent_id, visibility, topic, mode, status, created_at, last_active_at,
            last_position, next_step, state_summary, facts_used, current_interpretation,
            interpretation_status, user_confirmed, source_session, tags, notes, updated_by)
           VALUES (:thread_id, :version, :agent_id, :visibility, :topic, :mode, :status, :created_at, :last_active_at,
            :last_position, :next_step, :state_summary, :facts_used, :current_interpretation,
            :interpretation_status, :user_confirmed, :source_session, :tags, :notes, :updated_by)""",
        d
    )
    _record_audit(conn, actor, "create_thread", "session_thread", thread.thread_id,
                  {"agent_id": thread.agent_id, "visibility": thread.visibility})
    conn.commit()
    row = conn.execute("SELECT * FROM session_threads WHERE thread_id = ?",
                       (thread.thread_id,)).fetchone()
    conn.close()
    return _deserialize_json_fields(_row_to_dict(row), ["facts_used", "tags"])


def update_thread(thread_id: str, actor: str = "agent", **kwargs) -> Optional[dict]:
    if not get_thread(thread_id):
        return None

    allowed = {
        "topic", "mode", "status", "last_active_at", "last_position",
        "next_step", "state_summary", "facts_used", "current_interpretation",
        "interpretation_status", "user_confirmed", "source_session", "tags",
        "notes", "updated_by", "agent_id", "visibility"
    }
    updates = {}
    for k, v in kwargs.items():
        if k in allowed:
            if isinstance(v, list):
                updates[k] = json.dumps(v, ensure_ascii=False)
            else:
                updates[k] = v
    if not updates:
        return get_thread(thread_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [thread_id]

    conn = _connect()
    conn.execute(f"UPDATE session_threads SET {set_clause} WHERE thread_id = ?", values)
    _record_audit(conn, actor, "update_thread", "session_thread", thread_id,
                  {"updated_fields": list(kwargs.keys())})
    conn.commit()
    conn.close()
    return get_thread(thread_id)


def get_thread(thread_id: str, agent_id: Optional[str] = None,
               include_shared: bool = False, all_agents: bool = False) -> Optional[dict]:
    conn = _connect()
    if all_agents or agent_id is None:
        row = conn.execute("SELECT * FROM session_threads WHERE thread_id = ?",
                           (thread_id,)).fetchone()
    elif include_shared:
        row = conn.execute(
            """SELECT * FROM session_threads
               WHERE thread_id = ? AND (agent_id = ? OR visibility = 'shared')""",
            (thread_id, agent_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM session_threads WHERE thread_id = ? AND agent_id = ?",
            (thread_id, agent_id)
        ).fetchone()
    conn.close()
    result = _row_to_dict(row)
    return _deserialize_json_fields(result, ["facts_used", "tags"]) if result else None


def list_threads(status: Optional[str] = None, agent_id: Optional[str] = None,
                 include_shared: bool = False, all_agents: bool = False,
                 interpretation_status: Optional[str] = None) -> list:
    conn = _connect()
    clauses = []
    params = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if interpretation_status:
        clauses.append("interpretation_status = ?")
        params.append(interpretation_status)
    if not all_agents and agent_id:
        if include_shared:
            clauses.append("(agent_id = ? OR visibility = 'shared')")
            params.append(agent_id)
        else:
            clauses.append("agent_id = ?")
            params.append(agent_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM session_threads{where} ORDER BY last_active_at DESC",
        params
    ).fetchall()
    conn.close()
    return [_deserialize_json_fields(_row_to_dict(r), ["facts_used", "tags"]) for r in rows]


def close_thread(thread_id: str, actor: str = "agent") -> Optional[dict]:
    return update_thread(thread_id, actor, status="closed", last_active_at=now_iso())


def merge_threads(from_id: str, into_id: str, reason: str = "",
                  actor: str = "user") -> Optional[dict]:
    """Merge from_id into into_id. from_id becomes closed."""
    from_thread = get_thread(from_id)
    if not from_thread:
        return None
    main_thread = get_thread(into_id)
    if not main_thread:
        return None

    # Add merge note to main thread
    merge_note = f"[merged] Thread '{from_thread['topic']}'"
    if reason:
        merge_note += f" — {reason}"
    existing_notes = main_thread.get("notes", "")
    new_notes = f"{existing_notes}\n{merge_note}".strip() if existing_notes else merge_note

    conn = _connect()
    conn.execute(
        "UPDATE session_threads SET notes = ?, last_active_at = ? WHERE thread_id = ?",
        (new_notes, now_iso(), into_id)
    )
    conn.execute(
        "UPDATE session_threads SET status = 'closed' WHERE thread_id = ?",
        (from_id,)
    )
    _record_audit(conn, actor, "merge_threads", "session_thread", into_id,
                  {"from_id": from_id, "reason": reason})
    conn.commit()
    conn.close()
    return get_thread(into_id)


# ── State Snapshots ──────────────────────────────────────────

def create_snapshot(snapshot: StateSnapshot, actor: str = "agent") -> dict:
    conn = _connect()
    d = {
        "snapshot_id": snapshot.snapshot_id,
        "version": snapshot.version,
        "agent_id": snapshot.agent_id,
        "visibility": snapshot.visibility,
        "name": snapshot.name,
        "source_thread_id": snapshot.source_thread_id,
        "created_at": snapshot.created_at,
        "updated_at": snapshot.updated_at,
        "state_summary": snapshot.state_summary,
        "tone": snapshot.tone,
        "relationship_context": snapshot.relationship_context,
        "working_posture": snapshot.working_posture,
        "reuse_notes": snapshot.reuse_notes,
        "tags": json.dumps(snapshot.tags, ensure_ascii=False),
    }
    conn.execute(
        """INSERT INTO state_snapshots
           (snapshot_id, version, agent_id, visibility, name, source_thread_id, created_at, updated_at,
            state_summary, tone, relationship_context, working_posture, reuse_notes, tags)
           VALUES (:snapshot_id, :version, :agent_id, :visibility, :name, :source_thread_id, :created_at, :updated_at,
            :state_summary, :tone, :relationship_context, :working_posture, :reuse_notes, :tags)""",
        d
    )
    _record_audit(conn, actor, "create_snapshot", "state_snapshot", snapshot.snapshot_id,
                  {"agent_id": snapshot.agent_id, "visibility": snapshot.visibility})
    conn.commit()
    row = conn.execute("SELECT * FROM state_snapshots WHERE snapshot_id = ?",
                       (snapshot.snapshot_id,)).fetchone()
    conn.close()
    return _deserialize_json_fields(_row_to_dict(row), ["tags"])


def get_snapshot(snapshot_id: str, agent_id: Optional[str] = None,
                 include_shared: bool = False, all_agents: bool = False) -> Optional[dict]:
    conn = _connect()
    if all_agents or agent_id is None:
        row = conn.execute("SELECT * FROM state_snapshots WHERE snapshot_id = ?",
                           (snapshot_id,)).fetchone()
    elif include_shared:
        row = conn.execute(
            """SELECT * FROM state_snapshots
               WHERE snapshot_id = ? AND (agent_id = ? OR visibility = 'shared')""",
            (snapshot_id, agent_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM state_snapshots WHERE snapshot_id = ? AND agent_id = ?",
            (snapshot_id, agent_id)
        ).fetchone()
    conn.close()
    result = _row_to_dict(row)
    return _deserialize_json_fields(result, ["tags"]) if result else None


def list_snapshots(agent_id: Optional[str] = None, include_shared: bool = False,
                   all_agents: bool = False) -> list:
    conn = _connect()
    clauses = []
    params = []
    if not all_agents and agent_id:
        if include_shared:
            clauses.append("(agent_id = ? OR visibility = 'shared')")
            params.append(agent_id)
        else:
            clauses.append("agent_id = ?")
            params.append(agent_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM state_snapshots{where} ORDER BY created_at DESC",
        params
    ).fetchall()
    conn.close()
    return [_deserialize_json_fields(_row_to_dict(r), ["tags"]) for r in rows]


def update_snapshot(snapshot_id: str, actor: str = "user", **kwargs) -> Optional[dict]:
    if not get_snapshot(snapshot_id):
        return None

    allowed = {
        "name", "state_summary", "reuse_notes", "tone",
        "relationship_context", "working_posture", "tags", "agent_id", "visibility"
    }
    updates = {}
    for k, v in kwargs.items():
        if k in allowed:
            if isinstance(v, list):
                updates[k] = json.dumps(v, ensure_ascii=False)
            else:
                updates[k] = v
    if not updates:
        return get_snapshot(snapshot_id)

    updates["updated_at"] = now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [snapshot_id]

    conn = _connect()
    conn.execute(f"UPDATE state_snapshots SET {set_clause} WHERE snapshot_id = ?", values)
    _record_audit(conn, actor, "update_snapshot", "state_snapshot", snapshot_id,
                  {"updated_fields": list(kwargs.keys())})
    conn.commit()
    conn.close()
    return get_snapshot(snapshot_id)


def delete_snapshot(snapshot_id: str, actor: str = "user") -> bool:
    conn = _connect()
    existing = conn.execute(
        "SELECT snapshot_id FROM state_snapshots WHERE snapshot_id = ?",
        (snapshot_id,)
    ).fetchone()
    if not existing:
        conn.close()
        return False
    conn.execute("DELETE FROM state_snapshots WHERE snapshot_id = ?", (snapshot_id,))
    _record_audit(conn, actor, "delete_snapshot", "state_snapshot", snapshot_id)
    conn.commit()
    conn.close()
    return True


# ── Handoffs ─────────────────────────────────────────────────

def create_handoff(handoff: Handoff, actor: str = "agent") -> dict:
    conn = _connect()
    d = {
        "handoff_id": handoff.handoff_id,
        "version": handoff.version,
        "agent_id": handoff.agent_id,
        "visibility": handoff.visibility,
        "thread_id": handoff.thread_id,
        "created_at": handoff.created_at,
        "objective": handoff.objective,
        "completed": json.dumps(handoff.completed, ensure_ascii=False),
        "open_items": json.dumps(handoff.open_items, ensure_ascii=False),
        "next_step": handoff.next_step,
        "do_not_confuse": json.dumps(handoff.do_not_confuse, ensure_ascii=False),
        "notes": handoff.notes,
    }
    conn.execute(
        """INSERT INTO handoffs
           (handoff_id, version, agent_id, visibility, thread_id, created_at, objective, completed,
            open_items, next_step, do_not_confuse, notes)
           VALUES (:handoff_id, :version, :agent_id, :visibility, :thread_id, :created_at, :objective, :completed,
            :open_items, :next_step, :do_not_confuse, :notes)""",
        d
    )
    _record_audit(conn, actor, "create_handoff", "handoff", handoff.handoff_id,
                  {"agent_id": handoff.agent_id, "visibility": handoff.visibility})
    conn.commit()
    row = conn.execute("SELECT * FROM handoffs WHERE handoff_id = ?",
                       (handoff.handoff_id,)).fetchone()
    conn.close()
    return _deserialize_json_fields(_row_to_dict(row),
                                    ["completed", "open_items", "do_not_confuse"])


def get_handoff(handoff_id: str, agent_id: Optional[str] = None,
                include_shared: bool = False, all_agents: bool = False) -> Optional[dict]:
    conn = _connect()
    if all_agents or agent_id is None:
        row = conn.execute("SELECT * FROM handoffs WHERE handoff_id = ?",
                           (handoff_id,)).fetchone()
    elif include_shared:
        row = conn.execute(
            "SELECT * FROM handoffs WHERE handoff_id = ? AND (agent_id = ? OR visibility = 'shared')",
            (handoff_id, agent_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM handoffs WHERE handoff_id = ? AND agent_id = ?",
            (handoff_id, agent_id)
        ).fetchone()
    conn.close()
    result = _row_to_dict(row)
    return _deserialize_json_fields(result,
                                    ["completed", "open_items", "do_not_confuse"]) if result else None


def list_handoffs(agent_id: Optional[str] = None, include_shared: bool = False,
                  all_agents: bool = False) -> list:
    conn = _connect()
    clauses = []
    params = []
    if not all_agents and agent_id:
        if include_shared:
            clauses.append("(agent_id = ? OR visibility = 'shared')")
            params.append(agent_id)
        else:
            clauses.append("agent_id = ?")
            params.append(agent_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM handoffs{where} ORDER BY created_at DESC", params).fetchall()
    conn.close()
    return [_deserialize_json_fields(_row_to_dict(r),
                                     ["completed", "open_items", "do_not_confuse"]) for r in rows]


def delete_handoff(handoff_id: str, actor: str = "user") -> bool:
    conn = _connect()
    existing = conn.execute(
        "SELECT handoff_id FROM handoffs WHERE handoff_id = ?",
        (handoff_id,)
    ).fetchone()
    if not existing:
        conn.close()
        return False
    conn.execute("DELETE FROM handoffs WHERE handoff_id = ?", (handoff_id,))
    _record_audit(conn, actor, "delete_handoff", "handoff", handoff_id)
    conn.commit()
    conn.close()
    return True


# ── Audit ────────────────────────────────────────────────────

def list_audit_events(limit: int = 50) -> list:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM audit_events ORDER BY time DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [_deserialize_json_fields(_row_to_dict(r), ["details"]) for r in rows]
