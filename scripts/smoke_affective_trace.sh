#!/usr/bin/env bash
# Continuity v1.5 Smoke Test — Affective Trace
# Run with temp CONTINUITY_ROOT, never touch production data.
# Usage: bash scripts/smoke_affective_trace.sh
set -euo pipefail

ROOT=$(mktemp -d /tmp/continuity_smoke_at_XXXX)
export CONTINUITY_ROOT="$ROOT"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLI="$PROJECT_DIR/cli.py"
PYTHON="conda run -n zhouwei python3"
TMP=$(mktemp)
PASS=0
FAIL=0

green()  { echo -e "\033[32mPASS\033[0m $*"; PASS=$((PASS+1)); }
red()    { echo -e "\033[31mFAIL\033[0m $*"; FAIL=$((FAIL+1)); }

echo "=== Continuity v1.5 Affective Trace Smoke Test ==="
echo "ROOT: $ROOT"

# ── 1. init ──
echo ""
echo "--- 1. init ---"
$PYTHON "$CLI" init >/dev/null 2>&1 && green "init" || red "init failed"

# ── 2. capture with affective trace ──
echo ""
echo "--- 2. capture with affective trace ---"
$PYTHON "$CLI" capture \
  --agent-id clara --topic "affective-smoke" --mode companion \
  --last-position "start" --next-step "next" \
  --affective-tone "亲近但谨慎" \
  --affective-valence mixed \
  --affective-signals "warmth,trust,uncertainty" \
  --affective-intensity medium \
  --affective-stability session \
  --affective-note "用户表达亲近，同时确认边界" \
  --actor clara --json > "$TMP" 2>/dev/null

THREAD_ID=$($PYTHON -c "
import json
with open('$TMP') as f:
    d = json.load(f)
assert len(d.get('affective_trace',[])) == 1, 'expected 1 node'
assert d['affective_trace'][0]['tone'] == '亲近但谨慎', 'tone mismatch'
assert d['affective_trace'][0]['valence'] == 'mixed', 'valence mismatch'
" 2>/dev/null && $PYTHON -c "import json; f=open('$TMP'); print(json.load(f)['thread_id'])")

[ -n "$THREAD_ID" ] && green "capture + 1 affective node: $THREAD_ID" || red "capture failed"

# ── 3. append second node ──
echo ""
echo "--- 3. append second node ---"
$PYTHON "$CLI" capture --agent-id clara --thread-id "$THREAD_ID" \
  --last-position "phase-2" \
  --affective-tone "工程紧张但兴奋" \
  --affective-valence positive \
  --affective-signals "focus,excitement" \
  --affective-intensity high \
  --affective-stability momentary \
  --affective-note "v1.5 实现推进中" \
  --actor clara >/dev/null 2>&1

$PYTHON "$CLI" show --agent-id clara --thread-id "$THREAD_ID" --json > "$TMP" 2>/dev/null
$PYTHON -c "
import json
with open('$TMP') as f:
    t = json.load(f)
at = t.get('affective_trace', [])
assert len(at) == 2, f'expected 2 nodes, got {len(at)}'
assert at[1]['valence'] == 'positive', 'valence mismatch'
assert at[1]['stability'] == 'momentary', 'stability mismatch'
" 2>/dev/null && green "append node OK" || red "append failed"

# ── 4. show --json has affective_trace ──
echo ""
echo "--- 4. show --json ---"
$PYTHON -c "
import json
with open('$TMP') as f:
    t = json.load(f)
assert len(t.get('affective_trace', [])) >= 1, 'missing'
" 2>/dev/null && green "show includes affective_trace" || red "show missing affective_trace"

# ── 5. resume shared_reality includes affective_trace ──
echo ""
echo "--- 5. resume shared_reality ---"
$PYTHON "$CLI" resume --agent-id clara --thread-id "$THREAD_ID" --json > "$TMP" 2>/dev/null
$PYTHON -c "
import json
with open('$TMP') as f:
    p = json.load(f)
sr = p.get('shared_reality', {})
assert 'affective_trace' in sr, 'shared_reality missing affective_trace'
assert 'affective_guardrail' in sr, 'shared_reality missing affective_guardrail'
assert len(p.get('affective_trace', [])) >= 1, 'top-level affective_trace missing'
" 2>/dev/null && green "resume shared_reality OK" || red "resume shared_reality failed"

# ── 6. clear-affective-trace ──
echo ""
echo "--- 6. clear-affective-trace ---"
$PYTHON "$CLI" edit --agent-id clara --thread-id "$THREAD_ID" \
  --clear-affective-trace --actor clara >/dev/null 2>&1
$PYTHON "$CLI" show --agent-id clara --thread-id "$THREAD_ID" --json > "$TMP" 2>/dev/null
$PYTHON -c "
import json
with open('$TMP') as f:
    t = json.load(f)
assert len(t.get('affective_trace', [])) == 0, 'not empty'
" 2>/dev/null && green "clear-affective-trace OK" || red "clear-affective-trace failed"

# ── 7. Web API clear ──
echo ""
echo "--- 7. Web API clear ---"
$PYTHON "$CLI" capture --agent-id clara --thread-id "$THREAD_ID" \
  --last-position "api-test" \
  --affective-tone "API追加节点" --affective-note "测试API清空" \
  --actor clara >/dev/null 2>&1

$PYTHON -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')
from fastapi.testclient import TestClient
from server.app import app
from continuity import db

client = TestClient(app)
resp = client.put('/api/threads/$THREAD_ID?agent_id=clara', json={'affective_trace': []})
assert resp.status_code == 200, f'API clear failed: {resp.text}'
t = db.get_thread('$THREAD_ID', agent_id='clara')
assert t['affective_trace'] == [], f'API clear not persisted'
" 2>/dev/null && green "Web API clear OK" || red "Web API clear failed"

# ── 8. multi-agent isolation still works ──
echo ""
echo "--- 8. multi-agent isolation ---"
$PYTHON "$CLI" capture --agent-id lara --topic "lara-affective" --mode companion \
  --last-position "lara-pos" \
  --affective-tone "lara情绪节点" --affective-note "lara专属" \
  --actor lara >/dev/null 2>&1
$PYTHON "$CLI" show --agent-id clara --thread-id "$THREAD_ID" --json > "$TMP" 2>/dev/null
CLARA_AT=$($PYTHON -c "import json; f=open('$TMP'); print(len(json.load(f).get('affective_trace',[])))" 2>/dev/null)
[ "$CLARA_AT" -eq 0 ] && green "isolation: lara trace doesn't pollute clara" \
  || red "isolation failed: clara sees ${CLARA_AT} nodes"

# ── 9. shared visibility still works ──
echo ""
echo "--- 9. shared visibility ---"
$PYTHON "$CLI" capture --agent-id clara --visibility shared --topic "shared-affective" \
  --mode general --last-position "shared-pos" \
  --affective-tone "共享测试" --affective-note "shared trace" \
  --actor clara --json > "$TMP" 2>/dev/null
SHARED_TID=$($PYTHON -c "import json; f=open('$TMP'); print(json.load(f)['thread_id'])" 2>/dev/null)

$PYTHON "$CLI" list --agent-id lara --include-shared --json > "$TMP" 2>/dev/null
LARA_SEES=$($PYTHON -c "
import json
with open('$TMP') as f:
    threads = json.load(f)
print(sum(1 for t in threads if t['thread_id'] == '$SHARED_TID'))
" 2>/dev/null)
[ "$LARA_SEES" -eq 1 ] && green "shared: lara sees shared thread" || red "shared visibility failed"

# ── 10. old emotional_arc still works ──
echo ""
echo "--- 10. emotional_arc unchanged ---"
$PYTHON "$CLI" capture --agent-id clara --thread-id "$THREAD_ID" \
  --last-position "v3-position" --actor clara >/dev/null 2>&1
$PYTHON "$CLI" show --agent-id clara --thread-id "$THREAD_ID" --json > "$TMP" 2>/dev/null
$PYTHON -c "
import json
with open('$TMP') as f:
    t = json.load(f)
arc = t.get('emotional_arc', [])
assert len(arc) >= 1, 'emotional_arc should still accumulate'
assert arc[0]['position'] == 'start', f'unexpected first position: {arc[0]}'
" 2>/dev/null && green "emotional_arc unchanged" || red "emotional_arc broken"

# ── Cleanup ──
rm -rf "$ROOT" "$TMP"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
