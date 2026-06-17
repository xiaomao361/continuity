#!/usr/bin/env python3
"""Smoke test for Continuity MCP server against a temporary root.

Tests MCP via raw JSON-RPC over stdio subprocess — no mcp client library needed.

Usage:
    conda run -n zhouwei python3 server/test_mcp_smoke.py
"""

import json
import os
import sys
import tempfile
import subprocess
import shutil
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = SKILL_DIR / "server"
MCP_SERVER = SERVER_DIR / "mcp.py"
TMP_ROOT = Path(tempfile.mkdtemp(prefix="continuity-mcp-smoke-"))

# Use direct Python binary from conda env — conda run buffers stdio
PYTHON_BIN = os.path.expanduser("~/miniconda3/envs/zhouwei/bin/python3")

passed = 0
failed = 0


def check(description, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {description} {detail}")
    else:
        failed += 1
        print(f"  ✗ {description} {detail}")
    return condition


class McpClient:
    """Minimal MCP JSON-RPC client over subprocess stdio."""

    def __init__(self, env):
        self.proc = subprocess.Popen(
            [PYTHON_BIN, str(MCP_SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        self._next_id = 1

    def _send(self, method, params=None):
        msg = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            msg["params"] = params
        payload = json.dumps(msg) + "\n"
        self.proc.stdin.write(payload)
        self.proc.stdin.flush()
        self._next_id += 1
        return self._read_response()

    def _read_response(self):
        line = self.proc.stdout.readline()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"error": f"parse error: {line[:200]}"}

    def _notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        payload = json.dumps(msg) + "\n"
        self.proc.stdin.write(payload)
        self.proc.stdin.flush()

    def initialize(self):
        result = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smoke-test", "version": "1.0"},
        })
        if result and "result" in result:
            # Send initialized notification
            self._notify("notifications/initialized")
        return result

    def list_tools(self):
        return self._send("tools/list")

    def call_tool(self, name, arguments):
        return self._send("tools/call", {"name": name, "arguments": arguments})

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def setup():
    """Init a temp continuity root."""
    env = os.environ.copy()
    env["CONTINUITY_ROOT"] = str(TMP_ROOT)
    env["CONTINUITY_AGENT_ID"] = "codex"

    result = subprocess.run(
        ["conda", "run", "-n", "zhouwei", "python3",
         str(SKILL_DIR / "cli.py"), "init"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    print(f"[init] {result.stdout.strip()}")
    if result.returncode != 0:
        print(f"[init] FAIL: {result.stderr}")
        return None
    return env


def test_positive(env):
    global passed, failed
    print("── Positive flow ──")

    client = McpClient(env)

    # Initialize
    init_resp = client.initialize()
    check("initialize", init_resp and "result" in init_resp,
          f"server={init_resp.get('result',{}).get('serverInfo',{}).get('name','?')} "
          f"v{init_resp.get('result',{}).get('serverInfo',{}).get('version','?')}")

    # Test 1: list tools
    tools_resp = client.list_tools()
    tools = tools_resp.get("result", {}).get("tools", [])
    tool_names = [t["name"] for t in tools]
    expected = [
        "continuity_list_threads",
        "continuity_show_thread",
        "continuity_resume",
        "continuity_capture_thread",
        "continuity_close_thread",
        "continuity_agent_state",
    ]
    ok = all(n in tool_names for n in expected)
    check("list_tools", ok, f"→ {len(tools)} tools: {tool_names}")

    if not ok:
        client.close()
        return

    # Test 2: capture_thread (create)
    create_args = {
        "agent_id": "codex",
        "topic": "Continuity MCP smoke",
        "mode": "planning",
        "last_position": "正在验证共同线 MCP 服务",
        "next_step": "确认 MCP 工具能生成续接包",
        "state_summary": "这是临时测试线，不写入真实库",
        "reality_line": "continuity-mcp-smoke",
        "entry_posture": "谨慎接续，不把状态当事实",
        "confirmed_ground": "Memoria 存事实，Continuity 存当前位置",
        "provisional_read": "MCP 可以作为共同线的标准入口",
        "boundary_notes": "默认按 agent 隔离",
        "misread_risks": "不要把 shared 当成默认共享",
    }
    create_resp = client.call_tool("continuity_capture_thread", create_args)
    create_text = create_resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    data = json.loads(create_text)
    thread_id = data.get("thread_id")
    check("capture_thread (create)", bool(thread_id and thread_id.startswith("thread_")),
          f"thread_id={thread_id}")

    # Test 3: list_threads
    list_resp = client.call_tool("continuity_list_threads", {"agent_id": "codex"})
    list_text = list_resp.get("result", {}).get("content", [{}])[0].get("text", "[]")
    threads = json.loads(list_text)
    found = any(t["thread_id"] == thread_id for t in threads)
    check("list_threads", found, f"→ {len(threads)} threads, found created")

    # Test 4: show_thread
    show_resp = client.call_tool("continuity_show_thread",
                                  {"thread_id": thread_id, "agent_id": "codex"})
    show_text = show_resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    thread = json.loads(show_text)
    ok = (thread.get("topic") == "Continuity MCP smoke"
          and thread.get("reality_line") == "continuity-mcp-smoke")
    check("show_thread", ok,
          f"topic={thread.get('topic','')}, reality_line={thread.get('reality_line','')}")

    # Test 5: resume
    resume_resp = client.call_tool("continuity_resume", {
        "thread_id": thread_id,
        "agent_id": "codex",
        "model": "test-model",
    })
    resume_text = resume_resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    packet = json.loads(resume_text)
    sr = packet.get("shared_reality", {})
    has_reality = bool(sr.get("reality_line"))
    check("resume", has_reality,
          f"action={packet.get('action','?')}, sr_keys={list(sr.keys())[:4]}")

    # Test 6: capture_thread (update)
    update_resp = client.call_tool("continuity_capture_thread", {
        "thread_id": thread_id,
        "agent_id": "codex",
        "last_position": "更新后的位置：MCP 续接包验证通过",
        "next_step": "跑缺失 agent_id 的负向用例",
    })
    update_text = update_resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    updated = json.loads(update_text)
    ok = (updated.get("last_position") == "更新后的位置：MCP 续接包验证通过"
          and updated.get("next_step") == "跑缺失 agent_id 的负向用例")
    check("capture_thread (update)", ok,
          f"position={updated.get('last_position','')[:30]}")

    # Test 7: close_thread
    close_resp = client.call_tool("continuity_close_thread",
                                   {"thread_id": thread_id, "agent_id": "codex"})
    close_text = close_resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    closed = json.loads(close_text)
    check("close_thread", closed.get("status") == "closed",
          f"status={closed.get('status','?')}")

    # Test 8: agent_state (read)
    as_resp = client.call_tool("continuity_agent_state", {"agent_id": "codex"})
    as_text = as_resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    agent_state = json.loads(as_text)
    check("agent_state (read)", "communication_style" in agent_state,
          f"id={agent_state.get('id','?')}")

    # Test 9: agent_state (update)
    as_up_resp = client.call_tool("continuity_agent_state", {
        "agent_id": "codex",
        "update": {"communication_style": "caveman-compressed"},
    })
    as_up_text = as_up_resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    updated_as = json.loads(as_up_text)
    check("agent_state (update)",
          updated_as.get("communication_style") == "caveman-compressed",
          f"style={updated_as.get('communication_style','?')}")

    # Test 10: list_threads with all_agents (management mode, no agent required)
    all_resp = client.call_tool("continuity_list_threads", {"all_agents": True})
    all_text = all_resp.get("result", {}).get("content", [{}])[0].get("text", "[]")
    all_threads = json.loads(all_text)
    check("list_threads (all_agents)", isinstance(all_threads, list),
          f"→ {len(all_threads)} threads across all agents")

    client.close()


def test_negative(env):
    global passed, failed
    print("── Negative case ──")

    no_agent_env = env.copy()
    del no_agent_env["CONTINUITY_AGENT_ID"]

    client = McpClient(no_agent_env)
    init_resp = client.initialize()
    check("neg: initialize", init_resp and "result" in init_resp, "")

    neg_resp = client.call_tool("continuity_list_threads", {})
    neg_text = neg_resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    data = json.loads(neg_text)
    has_error = "error" in data
    mentions_agent = has_error and "agent_id" in data.get("error", "").lower()
    check("neg: missing agent_id",
          has_error and mentions_agent,
          f"→ error: {data.get('error','')[:80]}")

    client.close()


def test_cli(env):
    global passed, failed
    print("── CLI compatibility ──")

    result = subprocess.run(
        ["conda", "run", "-n", "zhouwei", "python3",
         str(SKILL_DIR / "cli.py"), "list", "--agent-id", "codex", "--json"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    try:
        threads = json.loads(result.stdout)
        ok = isinstance(threads, list)
        check("CLI list still works", ok, f"→ {len(threads)} threads")
    except json.JSONDecodeError:
        check("CLI list still works", False, f"stdout: {result.stdout[:100]}")


def main():
    global passed, failed
    print("=" * 60)
    print("Continuity MCP Smoke Test")
    print(f"Temp root: {TMP_ROOT}")
    print(f"MCP server: {MCP_SERVER}")
    print("=" * 60)

    env = setup()
    if not env:
        print("FAIL: Could not init temp DB")
        sys.exit(1)

    print()
    test_positive(env)
    print()
    test_negative(env)
    print()
    test_cli(env)

    # Cleanup
    shutil.rmtree(TMP_ROOT, ignore_errors=True)
    print(f"\nCleaned up: {TMP_ROOT}")

    print(f"\n{'✓ All passed' if failed == 0 else f'✗ {failed} failures'}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
