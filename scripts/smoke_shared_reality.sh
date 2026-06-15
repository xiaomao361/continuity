#!/usr/bin/env bash
# Continuity v1.4 Smoke Test — Shared Reality
# Run with temp CONTINUITY_ROOT, never touch production data.
# Usage: bash scripts/smoke_shared_reality.sh
set -euo pipefail

ROOT=$(mktemp -d /tmp/continuity_smoke_XXXX)
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

echo "=== Continuity v1.4 Smoke Test ==="
echo "ROOT: $ROOT"
echo "CLI:  $CLI"

# ── 1. init ──
echo ""
echo "--- 1. init ---"
$PYTHON "$CLI" init >/dev/null 2>&1 && green "init" || red "init failed"

# ── 2. capture with shared reality fields ──
echo ""
echo "--- 2. capture with shared reality ---"
$PYTHON "$CLI" capture \
  --agent-id clara --topic "smoke-test" --mode companion \
  --reality-line "一条正在建立的信任关系" \
  --entry-posture "自然延续，不重新声明" \
  --confirmed-ground "已确认：基础信任和沟通方式" \
  --provisional-read "当前阶段：探索各自的边界" \
  --boundary-notes "不要假设永久许可，不要跳过确认" \
  --misread-risks "不要把昨晚状态机械套到今天" \
  --last-position "first-position-v1" \
  --next-step "continue-exploring" \
  --actor clara --json > "$TMP" 2>/dev/null

THREAD_ID=$($PYTHON -c "
import json
with open('$TMP') as f:
    d = json.load(f)
print(d['thread_id'])
" 2>/dev/null)

[ -n "$THREAD_ID" ] && green "capture created $THREAD_ID" || red "capture failed"

# ── 3. verify shared reality fields ──
echo ""
echo "--- 3. verify shared reality fields ---"
$PYTHON "$CLI" show --agent-id clara --thread-id "$THREAD_ID" --json > "$TMP" 2>/dev/null
$PYTHON -c "
import json
with open('$TMP') as f:
    t = json.load(f)
assert t['reality_line'] == '一条正在建立的信任关系', 'reality_line mismatch'
assert t['entry_posture'] == '自然延续，不重新声明', 'entry_posture mismatch'
assert t['confirmed_ground'] == '已确认：基础信任和沟通方式', 'confirmed_ground mismatch'
assert '探索' in t['provisional_read'], 'provisional_read mismatch'
assert '永久许可' in t['boundary_notes'], 'boundary_notes mismatch'
assert '机械' in t['misread_risks'], 'misread_risks mismatch'
print('OK')
" 2>/dev/null && green "shared reality fields OK" || red "shared reality fields mismatch"

# ── 4. Web API edit should persist shared reality fields ──
echo ""
echo "--- 4. Web API edit shared reality ---"
$PYTHON -c "
import json
import os
import sys
sys.path.insert(0, '$PROJECT_DIR')
from fastapi.testclient import TestClient
from server.app import app
from continuity import db

client = TestClient(app)
resp = client.put('/api/threads/$THREAD_ID?agent_id=clara', json={
    'reality_line': 'API更新后的共同现实线',
    'entry_posture': 'API更新后的进入姿态',
    'confirmed_ground': 'API确认地面',
    'provisional_read': 'API临时解读',
    'boundary_notes': 'API边界',
    'misread_risks': 'API误读风险',
})
assert resp.status_code == 200, resp.text
t = db.get_thread('$THREAD_ID', agent_id='clara')
assert t['reality_line'] == 'API更新后的共同现实线', 'api reality_line not persisted'
assert t['entry_posture'] == 'API更新后的进入姿态', 'api entry_posture not persisted'
assert t['confirmed_ground'] == 'API确认地面', 'api confirmed_ground not persisted'
assert t['provisional_read'] == 'API临时解读', 'api provisional_read not persisted'
assert t['boundary_notes'] == 'API边界', 'api boundary_notes not persisted'
assert t['misread_risks'] == 'API误读风险', 'api misread_risks not persisted'
print('OK')
" 2>/dev/null && green "Web API shared reality edit OK" || red "Web API shared reality edit failed"

# ── 5. update last_position → emotional_arc ──
echo ""
echo "--- 5. emotional_arc auto-archive ---"
$PYTHON "$CLI" capture --agent-id clara --thread-id "$THREAD_ID" \
  --last-position "second-position-v2" --actor clara >/dev/null 2>&1
$PYTHON "$CLI" show --agent-id clara --thread-id "$THREAD_ID" --json > "$TMP" 2>/dev/null
$PYTHON -c "
import json
with open('$TMP') as f:
    t = json.load(f)
arc = t.get('emotional_arc', [])
assert len(arc) >= 1, 'emotional_arc empty'
assert arc[0]['position'] == 'first-position-v1', f'expected first-position-v1, got {arc[0].get(\"position\")}'
print(f'{len(arc)} entries, first={arc[0][\"position\"]}')
" 2>/dev/null && green "emotional_arc OK" || red "emotional_arc failed"

# ── 6. resume with shared_reality ──
echo ""
echo "--- 6. resume shared_reality ---"
$PYTHON "$CLI" resume --agent-id clara --thread-id "$THREAD_ID" --json > "$TMP" 2>/dev/null
$PYTHON -c "
import json
with open('$TMP') as f:
    p = json.load(f)
assert p['version'] == 2, 'packet version != 2'
sr = p.get('shared_reality', {})
assert 'reality_line' in sr, 'shared_reality missing reality_line'
assert 'entry_posture' in sr, 'shared_reality missing entry_posture'
assert 'confirmed_ground' in sr, 'shared_reality missing confirmed_ground'
assert 'position_history' in sr, 'shared_reality missing position_history'
assert 'emotional_arc' in sr, 'legacy emotional_arc missing'
assert 'position_history' in p, 'top-level position_history missing'
print('OK')
" 2>/dev/null && green "resume shared_reality OK" || red "resume shared_reality failed"

# ── 7. model-adjust set ──
echo ""
echo "--- 7. model-adjust ---"
$PYTHON "$CLI" model-adjust set --model deepseek-v4-pro \
  --forbidden-phrases "接住了,收到了" \
  --forbidden-patterns "时间幻觉" \
  --inject-prompt "你是DeepSeek。禁止：接住了、收到了。" \
  --actor clara >/dev/null 2>&1
$PYTHON "$CLI" model-adjust show --model deepseek-v4-pro --json > "$TMP" 2>/dev/null
$PYTHON -c "
import json
with open('$TMP') as f:
    m = json.load(f)
assert m['model'] == 'deepseek-v4-pro', 'model mismatch'
assert '接住了' in m['forbidden_phrases'], 'phrases mismatch'
print('OK')
" 2>/dev/null && green "model-adjust set/show OK" || red "model-adjust failed"

# ── 8. resume --model with model_adjustment ──
echo ""
echo "--- 8. resume --model ---"
$PYTHON "$CLI" resume --agent-id clara --thread-id "$THREAD_ID" \
  --model deepseek-v4-pro --json > "$TMP" 2>/dev/null
$PYTHON -c "
import json
with open('$TMP') as f:
    p = json.load(f)
ma = p.get('model_adjustment')
assert ma is not None, 'model_adjustment missing'
assert ma['model'] == 'deepseek-v4-pro', 'model_adjustment model mismatch'
assert '接住了' in ma['forbidden_phrases'], 'model_adjustment phrases mismatch'
print('OK')
" 2>/dev/null && green "resume --model OK" || red "resume --model failed"

# ── 9. multi-agent isolation ──
echo ""
echo "--- 9. multi-agent isolation ---"
$PYTHON "$CLI" capture --agent-id lara --topic "lara-private" --mode companion \
  --last-position "lara-pos" --next-step "lara-next" --actor lara >/dev/null 2>&1
$PYTHON "$CLI" list --agent-id clara --json > "$TMP" 2>/dev/null
CLARA_COUNT=$($PYTHON -c "import json; f=open('$TMP'); print(len(json.load(f)))" 2>/dev/null)
$PYTHON "$CLI" list --agent-id lara --json > "$TMP" 2>/dev/null
LARA_COUNT=$($PYTHON -c "import json; f=open('$TMP'); print(len(json.load(f)))" 2>/dev/null)
[ "$CLARA_COUNT" -ge 1 ] && [ "$LARA_COUNT" -ge 1 ] \
  && green "isolation: clara=$CLARA_COUNT threads, lara=$LARA_COUNT threads" \
  || red "isolation failed: clara=$CLARA_COUNT, lara=$LARA_COUNT"

# ── 10. shared visibility ──
echo ""
echo "--- 10. shared visibility ---"
$PYTHON "$CLI" capture --agent-id clara --visibility shared --topic "shared-topic" \
  --mode general --last-position "shared-pos" --next-step "shared-next" --actor clara \
  --json > "$TMP" 2>/dev/null
SHARED_TID=$($PYTHON -c "
import json
with open('$TMP') as f:
    d = json.load(f)
print(d['thread_id'])
" 2>/dev/null)
$PYTHON "$CLI" list --agent-id lara --include-shared --json > "$TMP" 2>/dev/null
LARA_SEES=$($PYTHON -c "
import json
with open('$TMP') as f:
    threads = json.load(f)
count = sum(1 for t in threads if t['thread_id'] == '$SHARED_TID')
print(count)
" 2>/dev/null)
[ "$LARA_SEES" -eq 1 ] && green "shared: lara sees shared thread" || red "shared: lara cannot see shared thread ($LARA_SEES)"

# ── Cleanup ──
rm -rf "$ROOT" "$TMP"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
