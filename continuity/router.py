"""Continuity Router — decide how to resume."""

from typing import Optional

from . import db


def route(
    action: str = "continue",
    thread_id: Optional[str] = None,
    topic_thread_id: Optional[str] = None,
    state_snapshot_id: Optional[str] = None,
    agent_id: str = "default",
    include_shared: bool = False,
    all_agents: bool = False,
) -> dict:
    """Route to the right sources based on action type.

    Returns a dict with topic_source, state_source, and any warnings.
    """
    topic_source = None
    state_source = None
    warnings = []

    if action == "continue":
        if not thread_id:
            return {"topic_source": None, "state_source": None,
                    "warnings": ["continue action requires --thread-id"]}

        thread = db.get_thread(thread_id, agent_id=agent_id,
                               include_shared=include_shared, all_agents=all_agents)
        if not thread:
            return {"topic_source": None, "state_source": None,
                    "warnings": [f"Thread '{thread_id}' not found"]}

        topic_source = {
            "type": "thread",
            "thread_id": thread["thread_id"],
            "topic": thread["topic"],
            "last_position": thread["last_position"],
            "next_step": thread["next_step"],
            "state_summary": thread["state_summary"],
        }
        state_source = topic_source  # Same source for both

        if thread["status"] == "closed":
            warnings.append(f"Thread '{thread['topic']}' is closed — continuing may be unexpected")

    elif action == "fork":
        if not thread_id:
            return {"topic_source": None, "state_source": None,
                    "warnings": ["fork action requires --thread-id"]}

        thread = db.get_thread(thread_id, agent_id=agent_id,
                               include_shared=include_shared, all_agents=all_agents)
        if not thread:
            return {"topic_source": None, "state_source": None,
                    "warnings": [f"Thread '{thread_id}' not found"]}

        topic_source = {
            "type": "thread",
            "thread_id": thread["thread_id"],
            "topic": thread["topic"],
            "last_position": thread["last_position"],
            "next_step": thread["next_step"],
            "state_summary": thread["state_summary"],
            "fork_note": "This is a FORK — a new thread will be created for this session."
        }
        state_source = topic_source
        warnings.append("Fork action: start a new thread after resuming.")

    elif action == "blend":
        if not topic_thread_id:
            warnings.append("blend action: missing --topic-thread-id")
        if not state_snapshot_id:
            warnings.append("blend action: missing --state-snapshot-id")

        if topic_thread_id:
            topic_thread = db.get_thread(topic_thread_id, agent_id=agent_id,
                                         include_shared=include_shared, all_agents=all_agents)
            if topic_thread:
                topic_source = {
                    "type": "thread",
                    "thread_id": topic_thread["thread_id"],
                    "topic": topic_thread["topic"],
                    "last_position": topic_thread["last_position"],
                    "next_step": topic_thread["next_step"],
                    "state_summary": topic_thread["state_summary"],
                }
            else:
                warnings.append(f"Topic thread '{topic_thread_id}' not found")

        if state_snapshot_id:
            snapshot = db.get_snapshot(state_snapshot_id, agent_id=agent_id,
                                       include_shared=include_shared, all_agents=all_agents)
            if snapshot:
                state_source = {
                    "type": "snapshot",
                    "snapshot_id": snapshot["snapshot_id"],
                    "name": snapshot["name"],
                    "state_summary": snapshot["state_summary"],
                    "tone": snapshot["tone"],
                    "relationship_context": snapshot["relationship_context"],
                    "working_posture": snapshot["working_posture"],
                }
            else:
                warnings.append(f"State snapshot '{state_snapshot_id}' not found")

        if topic_source and state_source:
            warnings.append(
                "BLEND: topic context from thread, state feel from snapshot. "
                "Do NOT mix the snapshot's original topic content into current topic."
            )

    elif action == "reset":
        if not thread_id:
            topic_source = None
            state_source = None
            warnings.append("Reset: starting fresh. No thread or snapshot context loaded.")
        else:
            # reset from a specific thread — keep topic awareness but reset state
            thread = db.get_thread(thread_id, agent_id=agent_id,
                                   include_shared=include_shared, all_agents=all_agents)
            if thread:
                topic_source = {
                    "type": "thread",
                    "thread_id": thread["thread_id"],
                    "topic": thread["topic"],
                    "last_position": thread["last_position"],
                    "next_step": thread["next_step"],
                    "state_summary": thread["state_summary"],
                }
                state_source = None
                warnings.append(f"Reset: continuing topic '{thread['topic']}' with fresh state.")
            else:
                warnings.append(f"Thread '{thread_id}' not found")

    else:
        warnings.append(f"Unknown action '{action}' — defaulting to reset")
        topic_source = None
        state_source = None

    return {
        "topic_source": topic_source,
        "state_source": state_source,
        "warnings": warnings,
    }
