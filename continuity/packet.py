"""Continuity Packet assembly."""

from typing import Optional

from . import db, model_adjustments
from .router import route as route_action


def build_packet(
    action: str = "continue",
    thread_id: Optional[str] = None,
    topic_thread_id: Optional[str] = None,
    state_snapshot_id: Optional[str] = None,
    agent_id: str = "default",
    include_shared: bool = False,
    all_agents: bool = False,
    model: Optional[str] = None,
    full_arc: bool = False,
) -> dict:
    """Build a full Continuity Packet for an agent to read at session start.

    full_arc=False (default): truncate emotional_arc and affective_trace to
    last 5 entries. Confirmed affective nodes are always kept. Pass
    full_arc=True to get the complete history.
    """

    agent_state = db.get_agent_state(agent_id)

    # Route
    routing = route_action(
        action=action,
        thread_id=thread_id,
        topic_thread_id=topic_thread_id,
        state_snapshot_id=state_snapshot_id,
        agent_id=agent_id,
        include_shared=include_shared,
        all_agents=all_agents,
    )

    # Load full objects
    thread = None
    snapshot = None

    if thread_id:
        thread = db.get_thread(thread_id, agent_id=agent_id,
                               include_shared=include_shared, all_agents=all_agents)
    elif topic_thread_id:
        thread = db.get_thread(topic_thread_id, agent_id=agent_id,
                               include_shared=include_shared, all_agents=all_agents)

    if state_snapshot_id:
        snapshot = db.get_snapshot(state_snapshot_id, agent_id=agent_id,
                                   include_shared=include_shared, all_agents=all_agents)

    # Build next_response_posture
    posture_parts = []
    if snapshot and snapshot.get("tone"):
        posture_parts.append(f"Tone: {snapshot['tone']}")
    if snapshot and snapshot.get("working_posture"):
        posture_parts.append(f"Posture: {snapshot['working_posture']}")
    if agent_state and agent_state.get("communication_style"):
        posture_parts.append(f"Style: {agent_state['communication_style']}")
    if not posture_parts and thread and thread.get("state_summary"):
        posture_parts.append(f"From thread: {thread['state_summary']}")

    next_response_posture = " | ".join(posture_parts) if posture_parts else ""
    facts_used = []
    current_interpretation = ""
    interpretation_status = ""
    user_confirmed = False
    emotional_arc = []
    if thread:
        facts_used = thread.get("facts_used", []) or []
        current_interpretation = thread.get("current_interpretation", "") or ""
        interpretation_status = thread.get("interpretation_status", "") or ""
        user_confirmed = bool(thread.get("user_confirmed", False))
        emotional_arc = thread.get("emotional_arc", []) or []

    # v1.6: arc truncation — default to last 5, like memoria recall --limit 5
    arc_truncated = False
    omitted_emotional = 0
    omitted_affective = 0

    if not full_arc:
        if len(emotional_arc) > 5:
            omitted_emotional = len(emotional_arc) - 5
            emotional_arc = emotional_arc[-5:]
            arc_truncated = True

    # Deduplicate warnings
    seen = set()
    unique_warnings = []
    for w in routing["warnings"]:
        if w not in seen:
            seen.add(w)
            unique_warnings.append(w)

    # v1.4 shared reality section
    shared_reality = {}
    affective_trace_full = thread.get("affective_trace", []) or [] if thread else []
    affective_trace = list(affective_trace_full)  # copy before possibly mutating
    if thread:
        for key in ("reality_line", "entry_posture", "confirmed_ground",
                     "provisional_read", "boundary_notes", "misread_risks"):
            val = thread.get(key, "")
            if val:
                shared_reality[key] = val
        if emotional_arc:
            shared_reality["position_history"] = emotional_arc
            # Backward-compatible legacy name. The content is position history,
            # not affective trace.
            shared_reality["emotional_arc"] = emotional_arc
        # v1.5 affective trace — truncate when full_arc=False
        if affective_trace:
            if not full_arc and len(affective_trace) > 5:
                # Keep all confirmed nodes + last 5 session/momentary nodes
                confirmed = [n for n in affective_trace if n.get("stability") == "confirmed"]
                transient = [n for n in affective_trace if n.get("stability") != "confirmed"]
                kept_transient = transient[-5:] if len(transient) > 5 else transient
                affective_trace = confirmed + kept_transient
                omitted_affective = len(affective_trace_full) - len(affective_trace)
                arc_truncated = True
            shared_reality["affective_trace"] = affective_trace
            # Guardrail: trace records texture, not commands
            shared_reality["affective_guardrail"] = (
                "Affective trace records emotional texture, not emotional commands. "
                "Do not perform a mood mechanically. Use it to understand how the "
                "shared reality has felt, and re-enter carefully."
            )

    # v1.4 model adjustment (only when --model is passed)
    model_adjustment = None
    if model:
        entry = model_adjustments.get_model(model)
        if entry:
            model_adjustment = {
                "model": entry["model"],
                "forbidden_phrases": entry.get("forbidden_phrases", []),
                "forbidden_patterns": entry.get("forbidden_patterns", []),
                "inject_prompt": entry.get("inject_prompt", ""),
            }
        else:
            unique_warnings.append(
                f"No model adjustments found for '{model}'. Run 'model-adjust set --model {model}' to configure."
            )

    packet = {
        "version": 2,
        "agent_id": agent_id,
        "action": action,
        "topic_source": routing["topic_source"],
        "state_source": routing["state_source"],
        "agent_state": agent_state,
        "thread": thread,
        "snapshot": snapshot,
        "shared_reality": shared_reality,
        "facts_used": facts_used,
        "current_interpretation": current_interpretation,
        "interpretation_status": interpretation_status,
        "user_confirmed": user_confirmed,
        "emotional_arc": emotional_arc,
        "position_history": emotional_arc,
        "affective_trace": affective_trace,
        "arc_truncated": arc_truncated,
        "emotional_arc_omitted": omitted_emotional,
        "affective_trace_omitted": omitted_affective,
        "arc_truncation_notice": (
            f"Arc truncated: {omitted_emotional} position(s) and "
            f"{omitted_affective} affective node(s) omitted. "
            f"Use --full-arc (CLI) or full_arc:true (MCP) to get complete history."
        ) if arc_truncated else "",
        "boundary_notice": (
            "Continuity describes the shared reality position for this session. "
            "It is not durable fact and not automatic consent. "
            "Use it to re-enter carefully, not to assume permission."
        ),
        "warnings": unique_warnings,
        "next_response_posture": next_response_posture,
        "model_adjustment": model_adjustment,
    }

    return packet
