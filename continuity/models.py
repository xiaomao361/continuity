"""Data models for Continuity objects."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import json


def now_iso() -> str:
    """Return current time in ISO 8601 with timezone."""
    return datetime.now(timezone.utc).isoformat()


def gen_id(prefix: str) -> str:
    """Generate a unique ID with prefix."""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class AgentState:
    id: str = "default"
    version: int = 1
    updated_at: str = field(default_factory=now_iso)
    communication_style: str = ""
    relationship_position: str = ""
    long_term_preferences: list = field(default_factory=list)
    boundaries: list = field(default_factory=list)
    stable_patterns: list = field(default_factory=list)
    notes: str = ""


@dataclass
class SessionThread:
    thread_id: str = field(default_factory=lambda: gen_id("thread"))
    version: int = 1
    agent_id: str = "default"
    visibility: str = "private"
    topic: str = ""
    mode: str = "general"
    status: str = "active"
    created_at: str = field(default_factory=now_iso)
    last_active_at: str = field(default_factory=now_iso)
    last_position: str = ""
    next_step: str = ""
    state_summary: str = ""
    facts_used: list = field(default_factory=list)
    current_interpretation: str = ""
    interpretation_status: str = "active"
    user_confirmed: bool = False
    source_session: str = ""
    tags: list = field(default_factory=list)
    notes: str = ""
    updated_by: str = "agent"
    emotional_arc: list = field(default_factory=list)
    # v1.4 shared reality fields
    reality_line: str = ""
    entry_posture: str = ""
    confirmed_ground: str = ""
    provisional_read: str = ""
    boundary_notes: str = ""
    misread_risks: str = ""
    # v1.5 affective trace — emotional texture, not emotional commands
    affective_trace: list = field(default_factory=list)


@dataclass
class StateSnapshot:
    snapshot_id: str = field(default_factory=lambda: gen_id("snapshot"))
    version: int = 1
    agent_id: str = "default"
    visibility: str = "private"
    name: str = ""
    source_thread_id: Optional[str] = None
    created_at: str = field(default_factory=now_iso)
    updated_at: Optional[str] = None
    state_summary: str = ""
    tone: str = ""
    relationship_context: str = ""
    working_posture: str = ""
    reuse_notes: str = ""
    tags: list = field(default_factory=list)


@dataclass
class Handoff:
    handoff_id: str = field(default_factory=lambda: gen_id("handoff"))
    version: int = 1
    agent_id: str = "default"
    visibility: str = "private"
    thread_id: Optional[str] = None
    created_at: str = field(default_factory=now_iso)
    objective: str = ""
    completed: list = field(default_factory=list)
    open_items: list = field(default_factory=list)
    next_step: str = ""
    do_not_confuse: list = field(default_factory=list)
    notes: str = ""


@dataclass
class ContinuityPacket:
    version: int = 1
    action: str = "continue"
    topic_source: Optional[dict] = None
    state_source: Optional[dict] = None
    agent_state: Optional[dict] = None
    thread: Optional[dict] = None
    snapshot: Optional[dict] = None
    warnings: list = field(default_factory=list)
    next_response_posture: str = ""
