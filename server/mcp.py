#!/usr/bin/env python3
"""Continuity MCP Server — 常驻进程，stdio transport

共同线 MCP 入口。每个 MCP tool 直接映射到 continuity 包的对应函数。

使用方式:
    python server/mcp.py
    # Claude Code settings.json（推荐直连 conda 环境 python）:
    # { "mcpServers": { "continuity": {
    #     "command": "/Users/zhouwei/miniconda3/envs/zhouwei/bin/python3",
    #     "args": ["/path/to/server/mcp.py"],
    #     "env": { "CONTINUITY_AGENT_ID": "codex" }
    # }}}
    # 备用：conda run --no-capture-output -n zhouwei python server/mcp.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent
sys.path = [
    path for path in sys.path
    if path and Path(path).resolve() != SERVER_DIR
]
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from continuity import db, packet as packet_mod
from continuity.config import get_default_agent_id
from continuity.models import SessionThread, now_iso

server = Server("continuity", version="1.6.0")

# ── Helpers ────────────────────────────────────────────────────

VALID_MODES = ["engineering", "companion", "planning", "review", "general"]
VALID_STATUSES = ["active", "paused", "closed"]
VALID_INTERPRETATION_STATUSES = ["active", "needs_review", "stale", "closed"]
VALID_VISIBILITIES = ["private", "shared"]
VALID_RESUME_ACTIONS = ["continue", "fork", "blend", "reset"]
AGENT_STATE_FIELDS = [
    "communication_style", "relationship_position",
    "long_term_preferences", "boundaries", "stable_patterns", "notes",
]


def _json(result) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


def _error(message: str, **extra) -> str:
    return _json({"error": message, **extra})


def _resolve_agent_id(arguments: dict) -> str | None:
    """Resolve agent_id: explicit arg > env var > None."""
    explicit = (arguments.get("agent_id") or "").strip()
    if explicit:
        return explicit
    return get_default_agent_id()


def _require_agent_id(arguments: dict) -> str:
    """Resolve agent_id or raise clear error."""
    agent_id = _resolve_agent_id(arguments)
    if not agent_id:
        raise ValueError(
            "agent_id required. Pass agent_id or set CONTINUITY_AGENT_ID env var."
        )
    return agent_id


def _scope(arguments: dict) -> dict:
    """Build scope dict for db calls."""
    all_agents = bool(arguments.get("all_agents", False))
    include_shared = bool(arguments.get("include_shared", False))
    if all_agents:
        return {"agent_id": None, "all_agents": True, "include_shared": False}
    agent_id = _require_agent_id(arguments)
    return {"agent_id": agent_id, "all_agents": False, "include_shared": include_shared}


def _validate_choice(value: str, allowed: list[str], field_name: str) -> None:
    if value is not None and value not in allowed:
        raise ValueError(
            f"{field_name} must be one of {allowed}, got '{value}'"
        )


def _require_existing_thread(thread_id: str, scope: dict) -> dict:
    """Fetch thread in scope or raise clear error."""
    thread = db.get_thread(thread_id, **scope)
    if not thread:
        agent_info = scope.get("agent_id") or "all"
        raise ValueError(
            f"thread '{thread_id}' not found (agent={agent_info}, "
            f"all_agents={scope['all_agents']}, include_shared={scope['include_shared']})"
        )
    return thread


def _build_affective_node(arguments: dict) -> dict | None:
    """Build an affective_trace node from MCP args. Returns None if nothing to add."""
    tone = arguments.get("affective_tone")
    note = arguments.get("affective_note")
    if not tone and not note:
        return None
    return {
        "time": now_iso(),
        "tone": tone or "",
        "valence": arguments.get("affective_valence", "unclear"),
        "signals": _csv_list(arguments.get("affective_signals", "")),
        "intensity": arguments.get("affective_intensity", "medium"),
        "stability": arguments.get("affective_stability", "session"),
        "source": arguments.get("actor", "mcp"),
        "note": note or "",
        "needs_review": bool(arguments.get("affective_needs_review", False)),
    }


def _csv_list(value) -> list[str]:
    """Parse comma-separated string or pass through list."""
    if isinstance(value, list):
        return value
    if not value:
        return []
    return [x.strip() for x in str(value).split(",") if x.strip()]


# ── Tool definitions ───────────────────────────────────────────

_TOOLS = [
    Tool(
        name="continuity_list_threads",
        description="列出某 Agent 的 Session Thread（共同线）。支持按状态、解释状态过滤。",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent 标识。未传则使用 CONTINUITY_AGENT_ID 环境变量",
                },
                "status": {
                    "type": "string",
                    "enum": VALID_STATUSES,
                    "description": "按状态过滤：active / paused / closed",
                },
                "interpretation_status": {
                    "type": "string",
                    "enum": VALID_INTERPRETATION_STATUSES,
                    "description": "按解释状态过滤：active / needs_review / stale / closed",
                },
                "include_shared": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否包含 shared 可见性的记录",
                },
                "all_agents": {
                    "type": "boolean",
                    "default": False,
                    "description": "管理模式：列出所有 Agent 的线程",
                },
            },
        },
    ),
    Tool(
        name="continuity_show_thread",
        description="查看一条 Session Thread 的完整详情（含共同现实字段、情绪轨迹）。",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Thread ID"},
                "agent_id": {"type": "string", "description": "Agent 标识"},
                "include_shared": {"type": "boolean", "default": False},
                "all_agents": {"type": "boolean", "default": False},
            },
            "required": ["thread_id"],
        },
    ),
    Tool(
        name="continuity_resume",
        description="生成续接包（Continuity Packet）。包含共同现实、情绪轨迹、模型负面调整。",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": VALID_RESUME_ACTIONS,
                    "default": "continue",
                    "description": "续接动作：continue / fork / blend / reset",
                },
                "thread_id": {"type": "string", "description": "Thread ID（continue/fork/reset 时使用）"},
                "topic_thread_id": {"type": "string", "description": "主题 Thread ID（blend 时使用）"},
                "state_snapshot_id": {"type": "string", "description": "状态快照 ID（blend 时使用）"},
                "agent_id": {"type": "string", "description": "Agent 标识"},
                "include_shared": {"type": "boolean", "default": False},
                "all_agents": {"type": "boolean", "default": False},
                "model": {"type": "string", "description": "模型名，用于加载对应的负面调整"},
                "full_arc": {
                    "type": "boolean",
                    "default": False,
                    "description": "返回完整 emotional_arc 和 affective_trace。默认 false（最近 5 条）",
                },
            },
        },
    ),
    Tool(
        name="continuity_capture_thread",
        description="创建或更新一条 Session Thread（共同线）。更新时旧 last_position 自动归档到 emotional_arc。",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent 标识"},
                "thread_id": {
                    "type": "string",
                    "description": "Thread ID。留空则创建新线程",
                },
                "visibility": {
                    "type": "string",
                    "enum": VALID_VISIBILITIES,
                    "default": "private",
                },
                "topic": {"type": "string", "description": "线程主题"},
                "mode": {
                    "type": "string",
                    "enum": VALID_MODES,
                    "default": "general",
                    "description": "线程模式",
                },
                "last_position": {"type": "string", "description": "当前进度描述"},
                "next_step": {"type": "string", "description": "下一步"},
                "state_summary": {"type": "string", "description": "状态摘要"},
                "facts_used": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "引用的记忆/事实 ID 列表",
                },
                "current_interpretation": {"type": "string", "description": "当前解释（基于事实的推断）"},
                "interpretation_status": {
                    "type": "string",
                    "enum": VALID_INTERPRETATION_STATUSES,
                    "default": "active",
                },
                "user_confirmed": {
                    "type": "boolean",
                    "default": False,
                    "description": "当前解释是否已获用户确认",
                },
                "source_session": {"type": "string", "description": "来源会话标识"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "标签列表"},
                "notes": {"type": "string", "description": "附加备注"},
                "reality_line": {"type": "string", "description": "共同现实线描述"},
                "entry_posture": {"type": "string", "description": "下次进入姿态"},
                "confirmed_ground": {"type": "string", "description": "已共同确认的地面"},
                "provisional_read": {"type": "string", "description": "临时解读（非事实，非永久许可）"},
                "boundary_notes": {"type": "string", "description": "继续时必须尊重的边界"},
                "misread_risks": {"type": "string", "description": "Agent 最容易误读的地方"},
                "actor": {"type": "string", "default": "mcp", "description": "操作者"},
                "include_shared": {"type": "boolean", "default": False},
                "all_agents": {"type": "boolean", "default": False},
                # v1.6 affective trace
                "affective_tone": {"type": "string", "description": "情绪质地描述（触发情绪轨迹追加）"},
                "affective_valence": {
                    "type": "string",
                    "enum": ["positive", "negative", "mixed", "neutral", "unclear"],
                    "description": "粗略情绪方向",
                },
                "affective_signals": {"type": "string", "description": "逗号分隔信号词（如 warmth,trust）"},
                "affective_intensity": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "情绪强度",
                },
                "affective_stability": {
                    "type": "string",
                    "enum": ["momentary", "session", "confirmed"],
                    "description": "情绪稳定性",
                },
                "affective_note": {"type": "string", "description": "一行人类可读的情绪注释"},
                "affective_needs_review": {
                    "type": "boolean",
                    "default": False,
                    "description": "标记此节点需要复查",
                },
            },
        },
    ),
    Tool(
        name="continuity_close_thread",
        description="关闭一条 Session Thread（共同线）。不会删除数据。",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "要关闭的 Thread ID"},
                "agent_id": {"type": "string", "description": "Agent 标识"},
                "include_shared": {"type": "boolean", "default": False},
                "all_agents": {"type": "boolean", "default": False},
                "actor": {"type": "string", "default": "mcp"},
            },
            "required": ["thread_id"],
        },
    ),
    Tool(
        name="continuity_agent_state",
        description="读取或更新 Agent State（通信风格、关系定位、长期偏好、边界等）。",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent 标识"},
                "update": {
                    "type": "object",
                    "description": "要更新的字段。不传则只读。",
                    "properties": {
                        "communication_style": {"type": "string"},
                        "relationship_position": {"type": "string"},
                        "long_term_preferences": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "boundaries": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "stable_patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "notes": {"type": "string"},
                    },
                },
                "actor": {"type": "string", "default": "mcp"},
            },
        },
    ),
]

_TOOL_MAP = {t.name: t for t in _TOOLS}


# ── Tool handlers ──────────────────────────────────────────────

@server.list_tools()
async def handle_list_tools():
    return _TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    try:
        if name == "continuity_list_threads":
            scope = _scope(arguments)
            threads = db.list_threads(
                status=arguments.get("status"),
                interpretation_status=arguments.get("interpretation_status"),
                **scope,
            )
            return [TextContent(type="text", text=_json(threads))]

        elif name == "continuity_show_thread":
            thread_id = arguments["thread_id"]
            scope = _scope(arguments)
            thread = _require_existing_thread(thread_id, scope)
            return [TextContent(type="text", text=_json(thread))]

        elif name == "continuity_resume":
            agent_id = _require_agent_id(arguments)
            action = arguments.get("action", "continue")
            _validate_choice(action, VALID_RESUME_ACTIONS, "action")
            packet = packet_mod.build_packet(
                action=action,
                thread_id=arguments.get("thread_id"),
                topic_thread_id=arguments.get("topic_thread_id"),
                state_snapshot_id=arguments.get("state_snapshot_id"),
                agent_id=agent_id,
                include_shared=bool(arguments.get("include_shared", False)),
                all_agents=bool(arguments.get("all_agents", False)),
                model=arguments.get("model"),
                full_arc=bool(arguments.get("full_arc", False)),
            )
            return [TextContent(type="text", text=_json(packet))]

        elif name == "continuity_capture_thread":
            scope = _scope(arguments)
            agent_id = scope["agent_id"]
            thread_id = arguments.get("thread_id") or None

            # Creating a new thread always requires a specific agent_id.
            # all_agents=true is for read/management only — reject on create.
            if not thread_id:
                if arguments.get("all_agents"):
                    raise ValueError(
                        "cannot create a thread with all_agents=true. "
                        "Creating a thread requires a specific agent_id."
                    )
                if not agent_id:
                    raise ValueError(
                        "agent_id required to create a thread. "
                        "Pass agent_id or set CONTINUITY_AGENT_ID env var."
                    )

            if thread_id:
                # Update existing — check scope
                _require_existing_thread(thread_id, scope)
                updates = {}
                str_fields = [
                    "topic", "mode", "last_position", "next_step",
                    "state_summary", "current_interpretation",
                    "interpretation_status", "source_session", "notes",
                    "visibility", "reality_line", "entry_posture",
                    "confirmed_ground", "provisional_read",
                    "boundary_notes", "misread_risks",
                ]
                for f in str_fields:
                    if f in arguments and arguments[f] is not None:
                        updates[f] = arguments[f]
                if "facts_used" in arguments and arguments["facts_used"] is not None:
                    updates["facts_used"] = _csv_list(arguments["facts_used"])
                if "tags" in arguments and arguments["tags"] is not None:
                    updates["tags"] = _csv_list(arguments["tags"])
                if arguments.get("user_confirmed"):
                    updates["user_confirmed"] = 1

                # Validate choices
                if "mode" in updates:
                    _validate_choice(updates["mode"], VALID_MODES, "mode")
                if "interpretation_status" in updates:
                    _validate_choice(updates["interpretation_status"],
                                     VALID_INTERPRETATION_STATUSES,
                                     "interpretation_status")
                if "visibility" in updates:
                    _validate_choice(updates["visibility"], VALID_VISIBILITIES,
                                     "visibility")

                # Affective trace append
                aff_node = _build_affective_node(arguments)
                if aff_node:
                    existing = db.get_thread(thread_id)
                    existing_trace = (existing.get("affective_trace") or []) if existing else []
                    if isinstance(existing_trace, str):
                        try:
                            existing_trace = json.loads(existing_trace)
                        except (json.JSONDecodeError, TypeError):
                            existing_trace = []
                    existing_trace.append(aff_node)
                    updates["affective_trace"] = existing_trace

                updates["last_active_at"] = now_iso()
                updates["updated_by"] = arguments.get("actor", "mcp")
                result = db.update_thread(thread_id, actor=arguments.get("actor", "mcp"),
                                          **updates)
                if not result:
                    raise ValueError(f"Failed to update thread '{thread_id}'")
            else:
                # Create new
                mode = arguments.get("mode", "general")
                _validate_choice(mode, VALID_MODES, "mode")
                visibility = arguments.get("visibility", "private")
                _validate_choice(visibility, VALID_VISIBILITIES, "visibility")
                interp_status = arguments.get("interpretation_status", "active")
                _validate_choice(interp_status, VALID_INTERPRETATION_STATUSES,
                                 "interpretation_status")

                aff_node = _build_affective_node(arguments)
                thread = SessionThread(
                    topic=arguments.get("topic", ""),
                    mode=mode,
                    agent_id=agent_id,
                    visibility=visibility,
                    source_session=arguments.get("source_session", ""),
                    last_position=arguments.get("last_position", ""),
                    next_step=arguments.get("next_step", ""),
                    state_summary=arguments.get("state_summary", ""),
                    facts_used=_csv_list(arguments.get("facts_used")),
                    current_interpretation=arguments.get("current_interpretation", ""),
                    interpretation_status=interp_status,
                    user_confirmed=bool(arguments.get("user_confirmed", False)),
                    tags=_csv_list(arguments.get("tags")),
                    notes=arguments.get("notes", ""),
                    updated_by=arguments.get("actor", "mcp"),
                    reality_line=arguments.get("reality_line", ""),
                    entry_posture=arguments.get("entry_posture", ""),
                    confirmed_ground=arguments.get("confirmed_ground", ""),
                    provisional_read=arguments.get("provisional_read", ""),
                    boundary_notes=arguments.get("boundary_notes", ""),
                    misread_risks=arguments.get("misread_risks", ""),
                    affective_trace=[aff_node] if aff_node else [],
                )
                result = db.create_thread(thread, actor=arguments.get("actor", "mcp"))

            return [TextContent(type="text", text=_json(result))]

        elif name == "continuity_close_thread":
            thread_id = arguments["thread_id"]
            scope = _scope(arguments)
            _require_existing_thread(thread_id, scope)
            result = db.close_thread(thread_id, actor=arguments.get("actor", "mcp"))
            if not result:
                raise ValueError(f"Failed to close thread '{thread_id}'")
            return [TextContent(type="text", text=_json(result))]

        elif name == "continuity_agent_state":
            agent_id = _require_agent_id(arguments)
            update = arguments.get("update") or {}
            actor = arguments.get("actor", "mcp")
            if update:
                # Filter to allowed fields
                filtered = {}
                for k in AGENT_STATE_FIELDS:
                    if k in update and update[k] is not None:
                        filtered[k] = update[k]
                if filtered:
                    result = db.update_agent_state(agent_id, actor=actor, **filtered)
                else:
                    result = db.get_agent_state(agent_id)
            else:
                result = db.get_agent_state(agent_id)
            return [TextContent(type="text", text=_json(result))]

        else:
            return [TextContent(type="text",
                                text=_error(f"unknown tool: {name}"))]

    except ValueError as e:
        return [TextContent(type="text", text=_error(str(e)))]
    except Exception as e:
        return [TextContent(type="text",
                            text=_error(f"internal error: {type(e).__name__}: {e}"))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
