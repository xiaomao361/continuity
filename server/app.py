"""Continuity Web API - FastAPI"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
import json

from continuity import db
from continuity.config import get_default_agent_id
from continuity.models import now_iso

app = FastAPI(title="Continuity", version="1.0")

STATIC_DIR = Path(__file__).parent / "static"


def _agent_scope(agent_id: str = None, include_shared: bool = False,
                 all_agents: bool = False) -> dict:
    return {
        "agent_id": agent_id or get_default_agent_id(),
        "include_shared": include_shared,
        "all_agents": all_agents,
    }


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
    agent_state = db.get_agent_state(scope["agent_id"])
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
    }


# ── Threads ────────────────────────────────────────────────

@app.get("/api/threads")
async def list_threads(
    status: str = Query(default=None),
    agent_id: str = Query(default=None),
    include_shared: bool = Query(default=False),
    all_agents: bool = Query(default=False),
):
    return {"threads": db.list_threads(status=status or None, **_agent_scope(agent_id, include_shared, all_agents))}


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
    allowed = {"topic", "mode", "status", "last_position", "next_step", "state_summary", "notes", "visibility"}
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if "tags" in body and isinstance(body["tags"], list):
        updates["tags"] = body["tags"]
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
    return db.get_agent_state(agent_id or get_default_agent_id())


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
    return db.update_agent_state(agent_id=agent_id or get_default_agent_id(), actor="user", **updates)


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
