"""Continuity Web API - FastAPI"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
import json

from continuity import db, model_adjustments
from continuity.config import get_default_agent_id
from continuity.models import now_iso

app = FastAPI(title="Continuity", version="1.4")

STATIC_DIR = Path(__file__).parent / "static"


def _agent_scope(agent_id: str = None, include_shared: bool = False,
                 all_agents: bool = False) -> dict:
    resolved = agent_id or get_default_agent_id()
    if not resolved and not all_agents:
        raise HTTPException(status_code=400,
                            detail="agent_id required. Set CONTINUITY_AGENT_ID env or pass ?agent_id=xxx")
    return {
        "agent_id": resolved or "",
        "include_shared": include_shared,
        "all_agents": all_agents,
    }


def _require_agent_id(agent_id: str = None) -> str:
    resolved = agent_id or get_default_agent_id()
    if not resolved:
        raise HTTPException(status_code=400,
                            detail="agent_id required. Set CONTINUITY_AGENT_ID env or pass ?agent_id=xxx")
    return resolved


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# ── Dashboard ──────────────────────────────────────────────

@app.get("/api/dashboard")
async def dashboard(
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    scope = _agent_scope(agent_id, include_shared, all_agents)
    threads = db.list_threads(**scope)
    snapshots = db.list_snapshots(**scope)
    handoffs = db.list_handoffs(**scope)
    agent_state = None if scope["all_agents"] else db.get_agent_state(scope["agent_id"])

    # Per-agent thread counts
    import sqlite3
    from continuity.config import get_db_path
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    per_agent_rows = conn.execute(
        "SELECT agent_id, COUNT(*) as cnt, SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active_cnt FROM session_threads GROUP BY agent_id"
    ).fetchall()
    per_agent = [{"agent_id": r["agent_id"], "total": r["cnt"], "active": r["active_cnt"]} for r in per_agent_rows]
    conn.close()

    return {
        "threads": {
            "total": len(threads),
            "active": sum(1 for t in threads if t["status"] == "active"),
            "paused": sum(1 for t in threads if t["status"] == "paused"),
            "closed": sum(1 for t in threads if t["status"] == "closed"),
        },
        "snapshots": len(snapshots),
        "handoffs": len(handoffs),
        "agent_state_updated": agent_state.get("updated_at", "") if agent_state else "",
        "recent_threads": threads[:5],
        "recent_audit": db.list_audit_events(limit=5),
        "per_agent": per_agent,
    }


# ── Agents ─────────────────────────────────────────────────

@app.get("/api/agents")
async def list_agents():
    """Return all known agent IDs and their thread/snapshot/handoff counts."""
    import sqlite3
    from continuity.config import get_db_path
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row

    # Collect agents from threads
    thread_agents = conn.execute(
        "SELECT agent_id, COUNT(*) as cnt FROM session_threads GROUP BY agent_id"
    ).fetchall()
    snapshot_agents = conn.execute(
        "SELECT agent_id, COUNT(*) as cnt FROM state_snapshots GROUP BY agent_id"
    ).fetchall()
    handoff_agents = conn.execute(
        "SELECT agent_id, COUNT(*) as cnt FROM handoffs GROUP BY agent_id"
    ).fetchall()

    agent_map = {}
    for row in thread_agents:
        agent_map[row["agent_id"]] = {"threads": row["cnt"], "snapshots": 0, "handoffs": 0}
    for row in snapshot_agents:
        if row["agent_id"] not in agent_map:
            agent_map[row["agent_id"]] = {"threads": 0, "snapshots": 0, "handoffs": 0}
        agent_map[row["agent_id"]]["snapshots"] = row["cnt"]
    for row in handoff_agents:
        if row["agent_id"] not in agent_map:
            agent_map[row["agent_id"]] = {"threads": 0, "snapshots": 0, "handoffs": 0}
        agent_map[row["agent_id"]]["handoffs"] = row["cnt"]

    conn.close()

    agents = [
        {"agent_id": aid, "threads": v["threads"], "snapshots": v["snapshots"], "handoffs": v["handoffs"]}
        for aid, v in sorted(agent_map.items())
    ]
    return {"agents": agents, "count": len(agents)}


# ── Threads ────────────────────────────────────────────────

@app.get("/api/threads")
async def list_threads(
    status: str = Query(default=None),
    interpretation_status: str = Query(default=None),
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    return {
        "threads": db.list_threads(
            status=status or None,
            interpretation_status=interpretation_status or None,
            **_agent_scope(agent_id, include_shared, all_agents),
        )
    }


@app.get("/api/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    t = db.get_thread(thread_id, **_agent_scope(agent_id, include_shared, all_agents))
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t


@app.put("/api/threads/{thread_id}")
async def update_thread(
    thread_id: str,
    body: dict,
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    scope = _agent_scope(agent_id, include_shared, all_agents)
    if not db.get_thread(thread_id, **scope):
        raise HTTPException(status_code=404, detail="Thread not found")
    allowed = {
        "topic", "mode", "status", "last_position", "next_step", "state_summary",
        "current_interpretation", "interpretation_status", "user_confirmed",
        "notes", "visibility", "emotional_arc",
        "reality_line", "entry_posture", "confirmed_ground",
        "provisional_read", "boundary_notes", "misread_risks",
    }
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if "tags" in body and isinstance(body["tags"], list):
        updates["tags"] = body["tags"]
    if "facts_used" in body and isinstance(body["facts_used"], list):
        updates["facts_used"] = body["facts_used"]
    updates["updated_by"] = "user"
    updates["last_active_at"] = now_iso()
    result = db.update_thread(thread_id, actor="user", **updates)
    if not result:
        raise HTTPException(status_code=404, detail="Thread not found")
    return result


@app.post("/api/threads/{thread_id}/close")
async def close_thread(
    thread_id: str,
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    if not db.get_thread(thread_id, **_agent_scope(agent_id, include_shared, all_agents)):
        raise HTTPException(status_code=404, detail="Thread not found")
    result = db.close_thread(thread_id, actor="user")
    if not result:
        raise HTTPException(status_code=404, detail="Thread not found")
    return result


@app.post("/api/threads/merge")
async def merge_threads(
    body: dict,
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    from_id = body.get("from_id")
    into_id = body.get("into_id")
    reason = body.get("reason", "")
    if not from_id or not into_id:
        raise HTTPException(status_code=400, detail="from_id and into_id required")
    scope = _agent_scope(agent_id, include_shared, all_agents)
    if not db.get_thread(from_id, **scope) or not db.get_thread(into_id, **scope):
        raise HTTPException(status_code=400, detail="Merge failed — check thread IDs and agent scope")
    result = db.merge_threads(from_id, into_id, reason, actor="user")
    if not result:
        raise HTTPException(status_code=400, detail="Merge failed — check thread IDs")
    return result


# ── Model Adjustments ──────────────────────────────────────

@app.get("/api/model-adjustments")
async def list_model_adjustments():
    store = model_adjustments._load()
    return store


@app.get("/api/model-adjustments/{model}")
async def get_model_adjustment(model: str):
    entry = model_adjustments.get_model(model)
    if not entry:
        raise HTTPException(status_code=404, detail=f"No adjustments for model '{model}'")
    return entry


@app.post("/api/model-adjustments/{model}")
async def set_model_adjustment(model: str, body: dict):
    result = model_adjustments.set_model(
        model=model,
        forbidden_phrases=body.get("forbidden_phrases"),
        forbidden_patterns=body.get("forbidden_patterns"),
        inject_prompt=body.get("inject_prompt"),
        updated_by=body.get("updated_by", "user"),
    )
    return result


@app.delete("/api/model-adjustments/{model}")
async def delete_model_adjustment(model: str):
    ok = model_adjustments.delete_model(model)
    if not ok:
        raise HTTPException(status_code=404, detail=f"No adjustments for model '{model}'")
    return {"deleted": model}


# ── Snapshots ──────────────────────────────────────────────

@app.get("/api/snapshots")
async def list_snapshots(
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    return {"snapshots": db.list_snapshots(**_agent_scope(agent_id, include_shared, all_agents))}


@app.get("/api/snapshots/{snapshot_id}")
async def get_snapshot(
    snapshot_id: str,
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    s = db.get_snapshot(snapshot_id, **_agent_scope(agent_id, include_shared, all_agents))
    if not s:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return s


@app.put("/api/snapshots/{snapshot_id}")
async def update_snapshot(
    snapshot_id: str,
    body: dict,
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    scope = _agent_scope(agent_id, include_shared, all_agents)
    if not db.get_snapshot(snapshot_id, **scope):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    allowed = {"name", "state_summary", "reuse_notes", "tone", "relationship_context", "working_posture", "visibility"}
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if "tags" in body and isinstance(body["tags"], list):
        updates["tags"] = body["tags"]
    result = db.update_snapshot(snapshot_id, actor="user", **updates)
    if not result:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return result


@app.delete("/api/snapshots/{snapshot_id}")
async def delete_snapshot(
    snapshot_id: str,
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    if not db.get_snapshot(snapshot_id, **_agent_scope(agent_id, include_shared, all_agents)):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    ok = db.delete_snapshot(snapshot_id, actor="user")
    if not ok:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"deleted": True}


# ── Handoffs ───────────────────────────────────────────────

@app.get("/api/handoffs")
async def list_handoffs(
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    return {"handoffs": db.list_handoffs(**_agent_scope(agent_id, include_shared, all_agents))}


@app.get("/api/handoffs/{handoff_id}")
async def get_handoff(
    handoff_id: str,
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    h = db.get_handoff(handoff_id, **_agent_scope(agent_id, include_shared, all_agents))
    if not h:
        raise HTTPException(status_code=404, detail="Handoff not found")
    return h


@app.delete("/api/handoffs/{handoff_id}")
async def delete_handoff(
    handoff_id: str,
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    if not db.get_handoff(handoff_id, **_agent_scope(agent_id, include_shared, all_agents)):
        raise HTTPException(status_code=404, detail="Handoff not found")
    ok = db.delete_handoff(handoff_id, actor="user")
    if not ok:
        raise HTTPException(status_code=404, detail="Handoff not found")
    return {"deleted": True}


# ── Agent State ────────────────────────────────────────────

@app.get("/api/agent-state")
async def get_agent_state(agent_id: str = Query(default=None)):
    return db.get_agent_state(_require_agent_id(agent_id))


@app.put("/api/agent-state")
async def update_agent_state(body: dict, agent_id: str = Query(default=None)):
    allowed = {"communication_style", "relationship_position", "notes"}
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if "long_term_preferences" in body and isinstance(body["long_term_preferences"], list):
        updates["long_term_preferences"] = body["long_term_preferences"]
    if "boundaries" in body and isinstance(body["boundaries"], list):
        updates["boundaries"] = body["boundaries"]
    if "stable_patterns" in body and isinstance(body["stable_patterns"], list):
        updates["stable_patterns"] = body["stable_patterns"]
    return db.update_agent_state(agent_id=_require_agent_id(agent_id), actor="user", **updates)


# ── Audit ──────────────────────────────────────────────────

@app.get("/api/audit")
async def list_audit(limit: int = Query(default=50, le=200)):
    return {"events": db.list_audit_events(limit=limit)}


def main():
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
