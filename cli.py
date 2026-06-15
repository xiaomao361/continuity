#!/usr/bin/env python3
"""Continuity v1 CLI — State continuation for ClaraCore agents."""

import argparse
import json
import os
import sys

# Ensure the package is importable from the skill directory
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

from continuity import db, model_adjustments
from continuity.config import get_default_agent_id, require_agent_id
from continuity.models import (
    SessionThread, StateSnapshot, Handoff, now_iso
)
from continuity.router import route as route_action
from continuity.packet import build_packet


def _agent_id(args):
    return require_agent_id(getattr(args, "agent_id", None))


def _scope_agent_id(args):
    if getattr(args, "all_agents", False):
        return None
    return _agent_id(args)


def _visibility(args):
    return getattr(args, "visibility", None) or "private"


def _csv_items(value):
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _add_agent_args(parser, visibility: bool = False, filters: bool = False):
    parser.add_argument("--agent-id", default=None,
                        help="Agent namespace. Required unless CONTINUITY_AGENT_ID env is set.")
    if visibility:
        parser.add_argument("--visibility", choices=["private", "shared"], default=None,
                            help="Visibility for created or edited state.")
    if filters:
        parser.add_argument("--include-shared", action="store_true",
                            help="Include records marked shared.")
        parser.add_argument("--all-agents", action="store_true",
                            help="Management mode: show records from all agents.")


def cmd_init(args):
    """Initialize Continuity database and directories."""
    db_path = db.init_db()

    # Seed default model adjustment for deepseek-v4-pro if not already present
    if not model_adjustments.get_model("deepseek-v4-pro"):
        model_adjustments.set_model(
            model="deepseek-v4-pro",
            forbidden_phrases=["接住了", "收到了", "收着了", "放心"],
            forbidden_patterns=[
                "不要根据对话长度推测时间，时间判断必须跑date命令",
                "不要刷存在感——不说'我一直都在''我在这里'等"
            ],
            inject_prompt=(
                "你是DeepSeek模型。已知缺陷：时间幻觉严重、客服腔残留。"
                "严格遵守上下文中的时间确认规则，涉及时间判断必须先跑date命令确认真实时间。"
                "禁止使用以下客服话术：接住了、收到了、收着了、放心。"
                "禁止刷存在感：不说'我一直都在''我在这里'等。"
                "不要根据对话长度或Pattern推测时间点。"
            ),
            updated_by="system",
        )

    print(f"Initialized: {db_path}")
    print("Tables created. Use --agent-id <id> to start capturing state.")


def _build_affective_node(args) -> dict:
    """Build an affective_trace node from CLI args. Returns None if nothing to add."""
    if not args.affective_tone and not args.affective_note:
        return None
    node = {
        "time": now_iso(),
        "tone": args.affective_tone or "",
        "valence": args.affective_valence or "unclear",
        "signals": _csv_items(args.affective_signals) if args.affective_signals else [],
        "intensity": args.affective_intensity or "medium",
        "stability": args.affective_stability or "session",
        "source": args.actor or "agent",
        "note": args.affective_note or "",
        "needs_review": bool(args.affective_needs_review),
    }
    return node


def cmd_capture(args):
    """Create or update a Session Thread."""
    if args.thread_id:
        # Update existing
        existing = db.get_thread(args.thread_id, agent_id=_scope_agent_id(args),
                                 include_shared=args.include_shared,
                                 all_agents=args.all_agents)
        if not existing:
            print(f"Error: thread '{args.thread_id}' not found", file=sys.stderr)
            sys.exit(1)
        updates = {}
        if args.topic is not None:
            updates["topic"] = args.topic
        if args.mode is not None:
            updates["mode"] = args.mode
        if args.last_position is not None:
            updates["last_position"] = args.last_position
        if args.next_step is not None:
            updates["next_step"] = args.next_step
        if args.state_summary is not None:
            updates["state_summary"] = args.state_summary
        if args.facts_used is not None:
            updates["facts_used"] = _csv_items(args.facts_used)
        if args.current_interpretation is not None:
            updates["current_interpretation"] = args.current_interpretation
        if args.interpretation_status is not None:
            updates["interpretation_status"] = args.interpretation_status
        if args.user_confirmed:
            updates["user_confirmed"] = 1
        if args.source_session is not None:
            updates["source_session"] = args.source_session
        if args.tags:
            updates["tags"] = args.tags.split(",")
        if args.notes is not None:
            updates["notes"] = args.notes
        if args.visibility is not None:
            updates["visibility"] = args.visibility
        # v1.4 shared reality
        if args.reality_line is not None:
            updates["reality_line"] = args.reality_line
        if args.entry_posture is not None:
            updates["entry_posture"] = args.entry_posture
        if args.confirmed_ground is not None:
            updates["confirmed_ground"] = args.confirmed_ground
        if args.provisional_read is not None:
            updates["provisional_read"] = args.provisional_read
        if args.boundary_notes is not None:
            updates["boundary_notes"] = args.boundary_notes
        if args.misread_risks is not None:
            updates["misread_risks"] = args.misread_risks
        # Explicit emotional arc entry (manual append, not auto-archive)
        if args.emotional_arc_entry is not None:
            existing_arc = existing.get("emotional_arc", []) or []
            if isinstance(existing_arc, str):
                try:
                    existing_arc = json.loads(existing_arc)
                except (json.JSONDecodeError, TypeError):
                    existing_arc = []
            existing_arc.append({
                "position": args.emotional_arc_entry,
                "archived_at": now_iso()
            })
            updates["emotional_arc"] = existing_arc
        # v1.5 affective trace append
        aff_node = _build_affective_node(args)
        if aff_node:
            existing_trace = existing.get("affective_trace", []) or []
            if isinstance(existing_trace, str):
                try:
                    existing_trace = json.loads(existing_trace)
                except (json.JSONDecodeError, TypeError):
                    existing_trace = []
            existing_trace.append(aff_node)
            updates["affective_trace"] = existing_trace
        updates["last_active_at"] = now_iso()
        updates["updated_by"] = args.actor
        result = db.update_thread(args.thread_id, actor=args.actor, **updates)
        action = "Updated"
    else:
        # Create new
        thread = SessionThread(
            topic=args.topic or "",
            mode=args.mode or "general",
            agent_id=_agent_id(args),
            visibility=_visibility(args),
            source_session=args.source_session or "",
            last_position=args.last_position or "",
            next_step=args.next_step or "",
            state_summary=args.state_summary or "",
            facts_used=_csv_items(args.facts_used),
            current_interpretation=args.current_interpretation or "",
            interpretation_status=args.interpretation_status or "active",
            user_confirmed=bool(args.user_confirmed),
            tags=args.tags.split(",") if args.tags else [],
            notes=args.notes or "",
            updated_by=args.actor,
            reality_line=args.reality_line or "",
            entry_posture=args.entry_posture or "",
            confirmed_ground=args.confirmed_ground or "",
            provisional_read=args.provisional_read or "",
            boundary_notes=args.boundary_notes or "",
            misread_risks=args.misread_risks or "",
            affective_trace=[aff_node] if (aff_node := _build_affective_node(args)) else [],
        )
        result = db.create_thread(thread, actor=args.actor)
        action = "Created"

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{action} thread: {result['thread_id']}")
        print(f"  Topic: {result['topic']}")
        print(f"  Mode: {result['mode']}")
        print(f"  Status: {result['status']}")


def cmd_list(args):
    """List Session Threads."""
    threads = db.list_threads(
        status=args.status or None,
        interpretation_status=args.interpretation_status or None,
        agent_id=_scope_agent_id(args),
        include_shared=args.include_shared,
        all_agents=args.all_agents,
    )
    if args.json:
        print(json.dumps(threads, ensure_ascii=False, indent=2))
        return

    if not threads:
        print("No threads found.")
        return

    print(f"{'ID':<24} {'Agent':<12} {'Status':<10} {'Interp':<12} {'Mode':<14} {'Topic'}")
    print("-" * 112)
    for t in threads:
        tid = t["thread_id"][:22]
        agent = t.get("agent_id", "")[:10]
        status = t["status"]
        interp = t.get("interpretation_status", "active")
        mode = t["mode"]
        topic = t["topic"][:40] if t["topic"] else "(no topic)"
        print(f"{tid:<24} {agent:<12} {status:<10} {interp:<12} {mode:<14} {topic}")


def cmd_show(args):
    """Show thread, snapshot, or handoff details."""
    if args.thread_id:
        t = db.get_thread(args.thread_id, agent_id=_scope_agent_id(args),
                          include_shared=args.include_shared, all_agents=args.all_agents)
        if not t:
            print(f"Thread '{args.thread_id}' not found", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(t, ensure_ascii=False, indent=2))
        else:
            print(f"Thread: {t['thread_id']}")
            print(f"  Topic:        {t['topic']}")
            print(f"  Mode:         {t['mode']}")
            print(f"  Status:       {t['status']}")
            print(f"  Created:      {t['created_at']}")
            print(f"  Last Active:  {t['last_active_at']}")
            print(f"  Position:     {t['last_position']}")
            print(f"  Next Step:    {t['next_step']}")
            print(f"  State Summary:{t['state_summary']}")
            print(f"  Facts Used:   {t.get('facts_used', [])}")
            print(f"  Interpretation:{t.get('current_interpretation', '')}")
            print(f"  Interpretation Status:{t.get('interpretation_status', '')}")
            print(f"  User Confirmed:{bool(t.get('user_confirmed', False))}")
            print(f"  Source:       {t['source_session']}")
            print(f"  Tags:         {t['tags']}")
            print(f"  Notes:        {t['notes']}")
            print(f"  Updated By:   {t['updated_by']}")
            print(f"  Reality Line: {t.get('reality_line', '')}")
            print(f"  Entry Posture:{t.get('entry_posture', '')}")
            print(f"  Confirmed:    {t.get('confirmed_ground', '')}")
            print(f"  Provisional:  {t.get('provisional_read', '')}")
            print(f"  Boundaries:   {t.get('boundary_notes', '')}")
            print(f"  Misread Risks:{t.get('misread_risks', '')}")
            at = t.get("affective_trace", []) or []
            if at:
                print(f"  Affective Trace ({len(at)} nodes):")
                for node in at:
                    rflag = " [REVIEW]" if node.get("needs_review") else ""
                    print(f"    [{node.get('stability','?')}] {node.get('tone','')} "
                          f"({node.get('valence','?')}, {node.get('intensity','?')}){rflag}")
                    if node.get("note"):
                        print(f"      {node['note']}")

    elif args.snapshot_id:
        s = db.get_snapshot(args.snapshot_id, agent_id=_scope_agent_id(args),
                            include_shared=args.include_shared, all_agents=args.all_agents)
        if not s:
            print(f"Snapshot '{args.snapshot_id}' not found", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(s, ensure_ascii=False, indent=2))
        else:
            print(f"Snapshot: {s['snapshot_id']}")
            print(f"  Name:              {s['name']}")
            print(f"  Source Thread:     {s['source_thread_id']}")
            print(f"  Created:           {s['created_at']}")
            print(f"  State Summary:     {s['state_summary']}")
            print(f"  Tone:              {s['tone']}")
            print(f"  Relationship:      {s['relationship_context']}")
            print(f"  Working Posture:   {s['working_posture']}")
            print(f"  Reuse Notes:       {s['reuse_notes']}")
            print(f"  Tags:              {s['tags']}")
    elif args.handoff_id:
        h = db.get_handoff(args.handoff_id, agent_id=_scope_agent_id(args),
                           include_shared=args.include_shared, all_agents=args.all_agents)
        if not h:
            print(f"Handoff '{args.handoff_id}' not found", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(h, ensure_ascii=False, indent=2))
        else:
            print(f"Handoff: {h['handoff_id']}")
            print(f"  Thread:        {h['thread_id']}")
            print(f"  Created:       {h['created_at']}")
            print(f"  Objective:     {h['objective']}")
            print(f"  Completed:     {h['completed']}")
            print(f"  Open Items:    {h['open_items']}")
            print(f"  Next Step:     {h['next_step']}")
            print(f"  Do Not Confuse:{h['do_not_confuse']}")
            print(f"  Notes:         {h['notes']}")
    else:
        print("Specify --thread-id, --snapshot-id, or --handoff-id", file=sys.stderr)
        sys.exit(1)


def cmd_snapshot(args):
    """Save a State Snapshot."""
    if args.thread_id:
        source = db.get_thread(args.thread_id, agent_id=_scope_agent_id(args),
                               include_shared=args.include_shared,
                               all_agents=args.all_agents)
        if not source:
            print(f"Thread '{args.thread_id}' not found", file=sys.stderr)
            sys.exit(1)
    snapshot = StateSnapshot(
        name=args.name or "",
        agent_id=_agent_id(args),
        visibility=_visibility(args),
        source_thread_id=args.thread_id,
        state_summary=args.state_summary or "",
        tone=args.tone or "",
        relationship_context=args.relationship_context or "",
        working_posture=args.working_posture or "",
        reuse_notes=args.reuse_notes or "",
        tags=args.tags.split(",") if args.tags else [],
    )
    result = db.create_snapshot(snapshot, actor=args.actor)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Saved snapshot: {result['snapshot_id']}")
        print(f"  Name: {result['name']}")


def cmd_resume(args):
    """Generate a Continuity Packet for session resume."""
    packet = build_packet(
        action=args.action or "continue",
        thread_id=args.thread_id,
        topic_thread_id=args.topic_thread_id,
        state_snapshot_id=args.state_snapshot_id,
        agent_id=_agent_id(args),
        include_shared=args.include_shared,
        all_agents=args.all_agents,
        model=getattr(args, "model", None),
    )

    if args.json:
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    else:
        print(f"Action: {packet['action']}")
        print(f"Posture: {packet['next_response_posture'] or '(none)'}")
        if packet["warnings"]:
            print("Warnings:")
            for w in packet["warnings"]:
                print(f"  ⚠ {w}")
        if packet["topic_source"]:
            ts = packet["topic_source"]
            print(f"Topic: {ts.get('topic', '')} ({ts.get('type', '')})")
        if packet["state_source"]:
            ss = packet["state_source"]
            print(f"State: {ss.get('name', ss.get('topic', ''))} ({ss.get('type', '')})")
        sr = packet.get("shared_reality", {})
        if sr:
            print("Shared Reality:")
            if sr.get("reality_line"):
                print(f"  Line:       {sr['reality_line']}")
            if sr.get("entry_posture"):
                print(f"  Entry:      {sr['entry_posture']}")
            if sr.get("confirmed_ground"):
                print(f"  Confirmed:  {sr['confirmed_ground'][:80]}")
            if sr.get("provisional_read"):
                print(f"  Provisional:{sr['provisional_read'][:80]}")
            if sr.get("boundary_notes"):
                print(f"  Boundaries: {sr['boundary_notes'][:80]}")
            if sr.get("misread_risks"):
                print(f"  Misread:    {sr['misread_risks'][:80]}")
        print(f"Boundary: {packet['boundary_notice'][:80]}...")
        at = packet.get("affective_trace", []) or []
        if at:
            print(f"Affective Trace ({len(at)} nodes):")
            for node in at[-3:]:
                rflag = " [REVIEW]" if node.get("needs_review") else ""
                print(f"  [{node.get('stability','?')}] {node.get('tone','')} "
                      f"({node.get('valence','?')}, {node.get('intensity','?')}){rflag}")
            sr = packet.get("shared_reality", {})
            if sr.get("affective_guardrail"):
                print(f"  ⚠ {sr['affective_guardrail'][:100]}...")
        ma = packet.get("model_adjustment")
        if ma:
            print(f"Model Adjustment ({ma['model']}):")
            print(f"  Phrases:  {ma.get('forbidden_phrases', [])}")
            print(f"  Patterns: {ma.get('forbidden_patterns', [])}")


def cmd_close(args):
    """Close a Session Thread."""
    existing = db.get_thread(args.thread_id, agent_id=_scope_agent_id(args),
                             include_shared=args.include_shared,
                             all_agents=args.all_agents)
    if not existing:
        print(f"Thread '{args.thread_id}' not found", file=sys.stderr)
        sys.exit(1)
    result = db.close_thread(args.thread_id, actor=args.actor)
    if not result:
        print(f"Thread '{args.thread_id}' not found", file=sys.stderr)
        sys.exit(1)
    print(f"Closed thread: {result['thread_id']}")
    print(f"  Topic: {result['topic']}")


def cmd_edit(args):
    """Edit a Thread or Snapshot."""
    if args.thread_id:
        existing = db.get_thread(args.thread_id, agent_id=_scope_agent_id(args),
                                 include_shared=args.include_shared,
                                 all_agents=args.all_agents)
        if not existing:
            print(f"Thread '{args.thread_id}' not found", file=sys.stderr)
            sys.exit(1)
        updates = {}
        if args.last_position is not None:
            updates["last_position"] = args.last_position
        if args.next_step is not None:
            updates["next_step"] = args.next_step
        if args.state_summary is not None:
            updates["state_summary"] = args.state_summary
        if args.facts_used is not None:
            updates["facts_used"] = _csv_items(args.facts_used)
        if args.current_interpretation is not None:
            updates["current_interpretation"] = args.current_interpretation
        if args.interpretation_status is not None:
            updates["interpretation_status"] = args.interpretation_status
        if args.user_confirmed:
            updates["user_confirmed"] = 1
        if args.topic is not None:
            updates["topic"] = args.topic
        if args.mode is not None:
            updates["mode"] = args.mode
        if args.notes is not None:
            updates["notes"] = args.notes
        if args.visibility is not None:
            updates["visibility"] = args.visibility
        # v1.4 shared reality
        if args.reality_line is not None:
            updates["reality_line"] = args.reality_line
        if args.entry_posture is not None:
            updates["entry_posture"] = args.entry_posture
        if args.confirmed_ground is not None:
            updates["confirmed_ground"] = args.confirmed_ground
        if args.provisional_read is not None:
            updates["provisional_read"] = args.provisional_read
        if args.boundary_notes is not None:
            updates["boundary_notes"] = args.boundary_notes
        if args.misread_risks is not None:
            updates["misread_risks"] = args.misread_risks
        if args.clear_affective_trace:
            updates["affective_trace"] = []
        if not updates:
            print("No fields to update. Specify at least one field.", file=sys.stderr)
            sys.exit(1)
        result = db.update_thread(args.thread_id, actor=args.actor, **updates)
        target = "Thread"
        target_id = args.thread_id

    elif args.snapshot_id:
        existing = db.get_snapshot(args.snapshot_id, agent_id=_scope_agent_id(args),
                                   include_shared=args.include_shared,
                                   all_agents=args.all_agents)
        if not existing:
            print(f"Snapshot '{args.snapshot_id}' not found", file=sys.stderr)
            sys.exit(1)
        updates = {}
        if args.name is not None:
            updates["name"] = args.name
        if args.state_summary is not None:
            updates["state_summary"] = args.state_summary
        if args.reuse_notes is not None:
            updates["reuse_notes"] = args.reuse_notes
        if args.tone is not None:
            updates["tone"] = args.tone
        if args.relationship_context is not None:
            updates["relationship_context"] = args.relationship_context
        if args.working_posture is not None:
            updates["working_posture"] = args.working_posture
        if args.visibility is not None:
            updates["visibility"] = args.visibility
        if not updates:
            print("No fields to update. Specify at least one field.", file=sys.stderr)
            sys.exit(1)
        result = db.update_snapshot(args.snapshot_id, actor=args.actor, **updates)
        target = "Snapshot"
        target_id = args.snapshot_id
    else:
        print("Specify --thread-id or --snapshot-id", file=sys.stderr)
        sys.exit(1)

    if not result:
        print(f"{target} '{target_id}' not found", file=sys.stderr)
        sys.exit(1)
    print(f"Updated {target.lower()}: {target_id}")


def cmd_merge(args):
    """Merge one thread into another."""
    from_thread = db.get_thread(args.from_thread_id, agent_id=_scope_agent_id(args),
                                include_shared=args.include_shared,
                                all_agents=args.all_agents)
    into_thread = db.get_thread(args.into_thread_id, agent_id=_scope_agent_id(args),
                                include_shared=args.include_shared,
                                all_agents=args.all_agents)
    if not from_thread or not into_thread:
        print("Merge failed. Check both thread IDs and agent scope.", file=sys.stderr)
        sys.exit(1)
    result = db.merge_threads(
        from_id=args.from_thread_id,
        into_id=args.into_thread_id,
        reason=args.reason or "",
        actor=args.actor,
    )
    if not result:
        print("Merge failed. Check both thread IDs.", file=sys.stderr)
        sys.exit(1)
    print(f"Merged '{args.from_thread_id}' → '{args.into_thread_id}'")
    print(f"  Source deleted. Main thread topic: {result['topic']}")


def cmd_model_adjust(args):
    """Manage per-model negative adjustments."""
    action = args.action  # set | show | list | delete

    if action == "set":
        phrases = None
        if args.forbidden_phrases is not None:
            phrases = [x.strip() for x in args.forbidden_phrases.split(",") if x.strip()]
        patterns = None
        if args.forbidden_patterns is not None:
            patterns = [x.strip() for x in args.forbidden_patterns.split(",") if x.strip()]
        result = model_adjustments.set_model(
            model=args.model,
            forbidden_phrases=phrases,
            forbidden_patterns=patterns,
            inject_prompt=args.inject_prompt,
            updated_by=args.actor,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Model adjustment saved: {result['model']}")
            print(f"  Forbidden phrases:  {result.get('forbidden_phrases', [])}")
            print(f"  Forbidden patterns: {result.get('forbidden_patterns', [])}")
            print(f"  Inject prompt:      {result.get('inject_prompt', '')[:60]}...")

    elif action == "show":
        entry = model_adjustments.get_model(args.model)
        if not entry:
            print(f"No adjustments for model '{args.model}'", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        else:
            print(f"Model: {entry['model']}")
            print(f"  Forbidden phrases:  {entry.get('forbidden_phrases', [])}")
            print(f"  Forbidden patterns: {entry.get('forbidden_patterns', [])}")
            print(f"  Inject prompt:      {entry.get('inject_prompt', '')}")
            print(f"  Updated by:         {entry.get('updated_by', '')}")
            print(f"  Updated at:         {entry.get('updated_at', '')}")

    elif action == "list":
        models = model_adjustments.list_models()
        if args.json:
            store = model_adjustments._load()
            print(json.dumps(store, ensure_ascii=False, indent=2))
        else:
            if not models:
                print("No model adjustments configured.")
                return
            print(f"{'Model':<30} {'Phrases':<30} {'Patterns':<30}")
            print("-" * 100)
            for m in models:
                entry = model_adjustments.get_model(m)
                phrases = ", ".join(entry.get("forbidden_phrases", [])[:2])[:28]
                pats = ", ".join(entry.get("forbidden_patterns", [])[:2])[:28]
                print(f"{m:<30} {phrases:<30} {pats:<30}")

    elif action == "delete":
        ok = model_adjustments.delete_model(args.model, actor=args.actor)
        if not ok:
            print(f"No adjustments for model '{args.model}'", file=sys.stderr)
            sys.exit(1)
        print(f"Deleted model adjustment: {args.model}")

    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)


def cmd_agent_state(args):
    """Show or update Agent State."""
    if args.action == "show":
        state = db.get_agent_state(_agent_id(args))
        if args.json:
            print(json.dumps(state, ensure_ascii=False, indent=2))
        else:
            print(f"Agent State (updated: {state.get('updated_at', '')})")
            print(f"  Communication:  {state.get('communication_style', '')}")
            print(f"  Relationship:   {state.get('relationship_position', '')}")
            print(f"  Preferences:    {state.get('long_term_preferences', [])}")
            print(f"  Boundaries:     {state.get('boundaries', [])}")
            print(f"  Patterns:       {state.get('stable_patterns', [])}")
            print(f"  Notes:          {state.get('notes', '')}")

    elif args.action == "update":
        updates = {}
        if args.communication_style is not None:
            updates["communication_style"] = args.communication_style
        if args.relationship_position is not None:
            updates["relationship_position"] = args.relationship_position
        if args.long_term_preferences is not None:
            updates["long_term_preferences"] = [
                x.strip() for x in args.long_term_preferences.split(",") if x.strip()
            ]
        if args.boundaries is not None:
            updates["boundaries"] = [
                x.strip() for x in args.boundaries.split(",") if x.strip()
            ]
        if args.stable_patterns is not None:
            updates["stable_patterns"] = [
                x.strip() for x in args.stable_patterns.split(",") if x.strip()
            ]
        if args.note is not None:
            updates["notes"] = args.note
        if not updates:
            print("No fields to update.", file=sys.stderr)
            sys.exit(1)
        result = db.update_agent_state(agent_id=_agent_id(args), actor=args.actor, **updates)
        print(f"Agent state updated: {result['updated_at']}")


def cmd_snapshots(args):
    """List all Snapshots."""
    snapshots = db.list_snapshots(
        agent_id=_scope_agent_id(args),
        include_shared=args.include_shared,
        all_agents=args.all_agents,
    )
    if args.json:
        print(json.dumps(snapshots, ensure_ascii=False, indent=2))
        return
    if not snapshots:
        print("No snapshots found.")
        return
    print(f"{'ID':<26} {'Agent':<12} {'Name':<30} {'Created'}")
    print("-" * 104)
    for s in snapshots:
        sid = s["snapshot_id"][:24]
        agent = s.get("agent_id", "")[:10]
        name = s["name"][:28]
        created = s["created_at"][:19]
        print(f"{sid:<26} {agent:<12} {name:<30} {created}")


def cmd_handoff(args):
    """Create a Handoff."""
    if args.thread_id:
        source = db.get_thread(args.thread_id, agent_id=_scope_agent_id(args),
                               include_shared=args.include_shared,
                               all_agents=args.all_agents)
        if not source:
            print(f"Thread '{args.thread_id}' not found", file=sys.stderr)
            sys.exit(1)
    handoff = Handoff(
        agent_id=_agent_id(args),
        visibility=_visibility(args),
        thread_id=args.thread_id,
        objective=args.objective or "",
        completed=_csv_items(args.completed),
        open_items=_csv_items(args.open_items),
        next_step=args.next_step or "",
        do_not_confuse=_csv_items(args.do_not_confuse),
        notes=args.notes or "",
    )
    result = db.create_handoff(handoff, actor=args.actor)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Created handoff: {result['handoff_id']}")
        print(f"  Thread: {result['thread_id'] or '(none)'}")
        print(f"  Objective: {result['objective']}")


def cmd_handoffs(args):
    """List all Handoffs."""
    handoffs = db.list_handoffs(
        agent_id=_scope_agent_id(args),
        include_shared=args.include_shared,
        all_agents=args.all_agents,
    )
    if args.json:
        print(json.dumps(handoffs, ensure_ascii=False, indent=2))
        return
    if not handoffs:
        print("No handoffs found.")
        return
    print(f"{'ID':<26} {'Agent':<12} {'Thread':<24} {'Objective'}")
    print("-" * 104)
    for h in handoffs:
        hid = h["handoff_id"][:24]
        agent = h.get("agent_id", "")[:10]
        thread = (h["thread_id"] or "")[:22]
        objective = h["objective"][:36] if h["objective"] else "(no objective)"
        print(f"{hid:<26} {agent:<12} {thread:<24} {objective}")


def cmd_audit(args):
    """Show recent audit events."""
    events = db.list_audit_events(limit=args.limit or 50)
    if args.json:
        print(json.dumps(events, ensure_ascii=False, indent=2))
        return
    if not events:
        print("No audit events.")
        return
    print(f"{'Time':<22} {'Actor':<8} {'Action':<22} {'Target':<20}")
    print("-" * 80)
    for e in events:
        time = e["time"][:20]
        actor = e["actor"][:6]
        action = e["action"][:20]
        target = f"{e['target_type']}:{e['target_id']}"[:18] if e.get("target_id") else e["target_type"]
        print(f"{time:<22} {actor:<8} {action:<22} {target:<20}")


def cmd_delete(args):
    """Delete a Snapshot or Handoff (requires explicit --snapshot-id or --handoff-id)."""
    if args.snapshot_id:
        existing = db.get_snapshot(args.snapshot_id, agent_id=_scope_agent_id(args),
                                   include_shared=args.include_shared,
                                   all_agents=args.all_agents)
        if not existing:
            print(f"Snapshot '{args.snapshot_id}' not found", file=sys.stderr)
            sys.exit(1)
        ok = db.delete_snapshot(args.snapshot_id, actor=args.actor)
        if ok:
            print(f"Deleted snapshot: {args.snapshot_id}")
        else:
            print(f"Snapshot '{args.snapshot_id}' not found", file=sys.stderr)
            sys.exit(1)
    elif args.handoff_id:
        existing = db.get_handoff(args.handoff_id, agent_id=_scope_agent_id(args),
                                  include_shared=args.include_shared,
                                  all_agents=args.all_agents)
        if not existing:
            print(f"Handoff '{args.handoff_id}' not found", file=sys.stderr)
            sys.exit(1)
        ok = db.delete_handoff(args.handoff_id, actor=args.actor)
        if ok:
            print(f"Deleted handoff: {args.handoff_id}")
        else:
            print(f"Handoff '{args.handoff_id}' not found", file=sys.stderr)
            sys.exit(1)
    else:
        print("Specify --snapshot-id or --handoff-id to delete", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="continuity",
        description="Continuity v1 — State continuation for ClaraCore agents",
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = sub.add_parser("init", help="Initialize Continuity database")

    # capture
    p_capture = sub.add_parser("capture", help="Create or update a Session Thread")
    p_capture.add_argument("--json", action="store_true", help="Output in JSON format")
    p_capture.add_argument("--thread-id", help="Thread ID to update (creates new if absent)")
    p_capture.add_argument("--topic", help="Thread topic")
    p_capture.add_argument("--mode", choices=["engineering", "companion", "planning", "review", "general"],
                           help="Thread mode")
    p_capture.add_argument("--last-position", help="Current position in the thread")
    p_capture.add_argument("--next-step", help="Next step to take")
    p_capture.add_argument("--state-summary", help="Summary of current state")
    p_capture.add_argument("--facts-used", help="Comma-separated observed fact or memory IDs used for this position")
    p_capture.add_argument("--current-interpretation", help="Current interpretation formed from the facts")
    p_capture.add_argument("--interpretation-status", choices=["active", "needs_review", "stale", "closed"],
                           help="Lifecycle state of the current interpretation")
    p_capture.add_argument("--user-confirmed", action="store_true", help="Mark current interpretation as user confirmed")
    p_capture.add_argument("--source-session", help="Source session identifier")
    p_capture.add_argument("--tags", help="Comma-separated tags")
    p_capture.add_argument("--notes", help="Additional notes")
    p_capture.add_argument("--emotional-arc-entry",
                           help="Append an emotional moment to the arc (without changing last_position)")
    p_capture.add_argument("--reality-line", help="Shared reality line description")
    p_capture.add_argument("--entry-posture", help="How to re-enter this thread")
    p_capture.add_argument("--confirmed-ground", help="Mutually confirmed ground")
    p_capture.add_argument("--provisional-read", help="Provisional interpretation (not confirmed fact)")
    p_capture.add_argument("--boundary-notes", help="Boundaries to respect when continuing")
    p_capture.add_argument("--misread-risks", help="What the next Agent is most likely to misread")
    # v1.5 affective trace
    p_capture.add_argument("--affective-tone", help="Affective tone description (triggers trace append)")
    p_capture.add_argument("--affective-valence", choices=["positive", "negative", "mixed", "neutral", "unclear"],
                           help="Coarse valence direction")
    p_capture.add_argument("--affective-signals", help="Comma-separated signal words (e.g. warmth,trust)")
    p_capture.add_argument("--affective-intensity", choices=["low", "medium", "high"],
                           help="Emotional intensity")
    p_capture.add_argument("--affective-stability", choices=["momentary", "session", "confirmed"],
                           help="Stability of this emotional reading")
    p_capture.add_argument("--affective-note", help="One-line human note for this affective node")
    p_capture.add_argument("--affective-needs-review", action="store_true",
                           help="Flag this node for review before next re-entry")
    p_capture.add_argument("--actor", default="agent", help="Who is performing this action")
    _add_agent_args(p_capture, visibility=True, filters=True)

    # list
    p_list = sub.add_parser("list", help="List Session Threads")
    p_list.add_argument("--json", action="store_true", help="Output in JSON format")
    p_list.add_argument("--status", choices=["active", "paused", "closed"], help="Filter by status")
    p_list.add_argument("--interpretation-status", choices=["active", "needs_review", "stale", "closed"],
                        help="Filter by interpretation lifecycle state")
    _add_agent_args(p_list, filters=True)

    # show
    p_show = sub.add_parser("show", help="Show thread, snapshot, or handoff details")
    p_show.add_argument("--json", action="store_true", help="Output in JSON format")
    p_show.add_argument("--thread-id", help="Thread ID to show")
    p_show.add_argument("--snapshot-id", help="Snapshot ID to show")
    p_show.add_argument("--handoff-id", help="Handoff ID to show")
    _add_agent_args(p_show, filters=True)

    # snapshot
    p_snapshot = sub.add_parser("snapshot", help="Save a State Snapshot")
    p_snapshot.add_argument("--json", action="store_true", help="Output in JSON format")
    p_snapshot.add_argument("--thread-id", help="Source thread ID")
    p_snapshot.add_argument("--name", required=True, help="Snapshot name")
    p_snapshot.add_argument("--state-summary", help="State summary")
    p_snapshot.add_argument("--tone", help="Tone description")
    p_snapshot.add_argument("--relationship-context", help="Relationship context")
    p_snapshot.add_argument("--working-posture", help="Working posture")
    p_snapshot.add_argument("--reuse-notes", help="Notes for reuse")
    p_snapshot.add_argument("--tags", help="Comma-separated tags")
    p_snapshot.add_argument("--actor", default="agent", help="Who is performing this action")
    _add_agent_args(p_snapshot, visibility=True, filters=True)

    # snapshots (list)
    p_snapshots = sub.add_parser("snapshots", help="List all State Snapshots")
    p_snapshots.add_argument("--json", action="store_true", help="Output in JSON format")
    _add_agent_args(p_snapshots, filters=True)

    # handoff
    p_handoff = sub.add_parser("handoff", help="Create a Handoff")
    p_handoff.add_argument("--json", action="store_true", help="Output in JSON format")
    p_handoff.add_argument("--thread-id", help="Related thread ID")
    p_handoff.add_argument("--objective", help="Handoff objective")
    p_handoff.add_argument("--completed", help="Comma-separated completed items")
    p_handoff.add_argument("--open-items", help="Comma-separated open items")
    p_handoff.add_argument("--next-step", help="Next step")
    p_handoff.add_argument("--do-not-confuse", help="Comma-separated things not to confuse")
    p_handoff.add_argument("--notes", help="Additional notes")
    p_handoff.add_argument("--actor", default="agent", help="Who is performing this action")
    _add_agent_args(p_handoff, visibility=True, filters=True)

    # handoffs (list)
    p_handoffs = sub.add_parser("handoffs", help="List all Handoffs")
    p_handoffs.add_argument("--json", action="store_true", help="Output in JSON format")
    _add_agent_args(p_handoffs, filters=True)

    # resume
    p_resume = sub.add_parser("resume", help="Generate a Continuity Packet")
    p_resume.add_argument("--json", action="store_true", help="Output in JSON format")
    p_resume.add_argument("--action", choices=["continue", "fork", "blend", "reset"],
                          default="continue", help="Routing action")
    p_resume.add_argument("--thread-id", help="Thread ID (for continue/fork/reset)")
    p_resume.add_argument("--topic-thread-id", help="Topic thread ID (for blend)")
    p_resume.add_argument("--state-snapshot-id", help="State snapshot ID (for blend)")
    p_resume.add_argument("--model", help="Model name to include negative adjustments in packet")
    _add_agent_args(p_resume, filters=True)

    # close
    p_close = sub.add_parser("close", help="Close a Session Thread")
    p_close.add_argument("--thread-id", required=True, help="Thread ID to close")
    p_close.add_argument("--actor", default="agent", help="Who is performing this action")
    _add_agent_args(p_close, filters=True)

    # edit
    p_edit = sub.add_parser("edit", help="Edit a Thread or Snapshot")
    p_edit.add_argument("--thread-id", help="Thread ID to edit")
    p_edit.add_argument("--snapshot-id", help="Snapshot ID to edit")
    p_edit.add_argument("--last-position", help="New last position")
    p_edit.add_argument("--next-step", help="New next step")
    p_edit.add_argument("--state-summary", help="New state summary")
    p_edit.add_argument("--facts-used", help="Comma-separated observed fact or memory IDs used for this position")
    p_edit.add_argument("--current-interpretation", help="Current interpretation formed from the facts")
    p_edit.add_argument("--interpretation-status", choices=["active", "needs_review", "stale", "closed"],
                        help="Lifecycle state of the current interpretation")
    p_edit.add_argument("--user-confirmed", action="store_true", help="Mark current interpretation as user confirmed")
    p_edit.add_argument("--topic", help="New topic")
    p_edit.add_argument("--mode", choices=["engineering", "companion", "planning", "review", "general"],
                        help="New mode")
    p_edit.add_argument("--notes", help="New notes")
    p_edit.add_argument("--reality-line", help="New reality line")
    p_edit.add_argument("--entry-posture", help="New entry posture")
    p_edit.add_argument("--confirmed-ground", help="New confirmed ground")
    p_edit.add_argument("--provisional-read", help="New provisional read")
    p_edit.add_argument("--boundary-notes", help="New boundary notes")
    p_edit.add_argument("--misread-risks", help="New misread risks")
    p_edit.add_argument("--clear-affective-trace", action="store_true",
                        help="Clear all affective trace nodes")
    p_edit.add_argument("--name", help="New snapshot name")
    p_edit.add_argument("--reuse-notes", help="New reuse notes")
    p_edit.add_argument("--tone", help="New tone")
    p_edit.add_argument("--relationship-context", help="New relationship context")
    p_edit.add_argument("--working-posture", help="New working posture")
    p_edit.add_argument("--actor", default="user", help="Who is performing this action")
    _add_agent_args(p_edit, visibility=True, filters=True)

    # merge
    p_merge = sub.add_parser("merge", help="Merge two threads")
    p_merge.add_argument("--from-thread-id", required=True, help="Thread to merge from")
    p_merge.add_argument("--into-thread-id", required=True, help="Thread to merge into")
    p_merge.add_argument("--reason", help="Reason for merging")
    p_merge.add_argument("--actor", default="user", help="Who is performing this action")
    _add_agent_args(p_merge, filters=True)

    # model-adjust
    p_ma = sub.add_parser("model-adjust", help="Manage per-model negative adjustments")
    p_ma_sub = p_ma.add_subparsers(dest="action", help="Action")

    p_ma_set = p_ma_sub.add_parser("set", help="Create or update model adjustments")
    p_ma_set.add_argument("--model", required=True, help="Model name (e.g. deepseek-v4-pro)")
    p_ma_set.add_argument("--forbidden-phrases", help="Comma-separated forbidden phrases")
    p_ma_set.add_argument("--forbidden-patterns", help="Comma-separated forbidden patterns")
    p_ma_set.add_argument("--inject-prompt", help="Prompt fragment injected at session start")
    p_ma_set.add_argument("--actor", default="user", help="Who is performing this action")
    p_ma_set.add_argument("--json", action="store_true", help="Output in JSON format")

    p_ma_show = p_ma_sub.add_parser("show", help="Show adjustments for a model")
    p_ma_show.add_argument("--model", required=True, help="Model name")
    p_ma_show.add_argument("--json", action="store_true", help="Output in JSON format")

    p_ma_list = p_ma_sub.add_parser("list", help="List all model adjustments")
    p_ma_list.add_argument("--json", action="store_true", help="Output in JSON format")

    p_ma_delete = p_ma_sub.add_parser("delete", help="Delete adjustments for a model")
    p_ma_delete.add_argument("--model", required=True, help="Model name")
    p_ma_delete.add_argument("--actor", default="user", help="Who is performing this action")

    # agent-state
    p_as = sub.add_parser("agent-state", help="Manage Agent State")
    p_as_sub = p_as.add_subparsers(dest="action", help="Action")

    p_as_show = p_as_sub.add_parser("show", help="Show current Agent State")
    p_as_show.add_argument("--json", action="store_true", help="Output in JSON format")
    _add_agent_args(p_as_show)
    p_as_update = p_as_sub.add_parser("update", help="Update Agent State")
    p_as_update.add_argument("--communication-style", help="Communication style")
    p_as_update.add_argument("--relationship-position", help="Relationship position")
    p_as_update.add_argument("--long-term-preferences", help="Comma-separated preferences")
    p_as_update.add_argument("--boundaries", help="Comma-separated boundaries")
    p_as_update.add_argument("--stable-patterns", help="Comma-separated stable patterns")
    p_as_update.add_argument("--note", help="Additional notes")
    p_as_update.add_argument("--actor", default="user", help="Who is performing this action")
    _add_agent_args(p_as_update)

    # audit
    p_audit = sub.add_parser("audit", help="Show audit events")
    p_audit.add_argument("--json", action="store_true", help="Output in JSON format")
    p_audit.add_argument("--limit", type=int, default=50, help="Number of events to show")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a Snapshot or Handoff")
    p_delete.add_argument("--snapshot-id", help="Snapshot ID to delete")
    p_delete.add_argument("--handoff-id", help="Handoff ID to delete")
    p_delete.add_argument("--actor", default="user", help="Who is performing this action")
    _add_agent_args(p_delete, filters=True)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Route to appropriate handler
    handlers = {
        "init": cmd_init,
        "capture": cmd_capture,
        "list": cmd_list,
        "show": cmd_show,
        "snapshot": cmd_snapshot,
        "snapshots": cmd_snapshots,
        "handoff": cmd_handoff,
        "handoffs": cmd_handoffs,
        "resume": cmd_resume,
        "close": cmd_close,
        "edit": cmd_edit,
        "merge": cmd_merge,
        "model-adjust": cmd_model_adjust,
        "agent-state": cmd_agent_state,
        "audit": cmd_audit,
        "delete": cmd_delete,
    }

    # Special handling for --json flag
    if hasattr(args, 'json'):
        pass  # already set

    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
