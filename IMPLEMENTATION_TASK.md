# Continuity v1 开发任务书

本文档给 Claude 使用。目标是在 ClaraCore 中实现 Continuity v1，并由 Codex
后续验收。

## 目标

实现一个小型、可运行、可人工管理的状态续接系统。

Continuity 要解决的问题是：

```text
新 Session 开始时，Agent 应该从哪里、以什么状态继续？
```

它不是记忆系统，不负责 Memoria 的读写，也不依赖 Memoria 才能工作。

## 代码位置

请在当前目录继续开发这个独立 skill：

```text
skills/continuity/
  README.md
  DESIGN.md
  IMPLEMENTATION_TASK.md
  CONTEXT_PACK.md
  HANDOFF.md
  INSTALL.md
  USAGE.md
  cli.py
  continuity/
    __init__.py
    config.py
    db.py
    models.py
    router.py
    packet.py
```

运行数据默认放在：

```text
~/.claracore/continuity/
```

支持环境变量覆盖：

```text
CONTINUITY_ROOT=/path/to/test/root
CONTINUITY_AGENT_ID=codex
```

不要把运行数据写进仓库。

## 第一版范围

必须实现：

- 多条 Session Thread 并行存在
- 按 `agent_id` 隔离不同 Agent 的连续状态
- State Snapshot 保存和查看
- Agent State 读取和保守更新
- Continuity Router
- Continuity Packet 生成
- 人工管理命令
- SQLite 持久化
- 基础测试或可重复 smoke test

不要实现：

- Memoria 集成
- 自动全量对话导入
- 后台守护进程
- 复杂桌面 UI
- 大型 Agent 编排
- 自动跨 Session 情绪合并
- 缓存或热存储层

## 存储设计

第一版使用 SQLite。Continuity 的核心对象需要查询、筛选、合并、关闭和审计，
SQLite 更适合第一版。

不要使用分散 JSON 文件作为主存储。`--json` 只表示 CLI 输出格式。

第一版不需要缓存或热存储层。如果以后有性能或跨进程读取需求，再单独评估。

建议结构：

```text
~/.claracore/continuity/
  continuity.db
```

建议表：

```sql
CREATE TABLE agent_state (
    id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    communication_style TEXT DEFAULT '',
    relationship_position TEXT DEFAULT '',
    long_term_preferences TEXT DEFAULT '[]',
    boundaries TEXT DEFAULT '[]',
    stable_patterns TEXT DEFAULT '[]',
    notes TEXT DEFAULT ''
);

CREATE TABLE session_threads (
    thread_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    agent_id TEXT NOT NULL DEFAULT 'default',
    visibility TEXT NOT NULL DEFAULT 'private',
    topic TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'general',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    last_position TEXT DEFAULT '',
    next_step TEXT DEFAULT '',
    state_summary TEXT DEFAULT '',
    source_session TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    notes TEXT DEFAULT '',
    updated_by TEXT DEFAULT 'agent'
);

CREATE TABLE state_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    agent_id TEXT NOT NULL DEFAULT 'default',
    visibility TEXT NOT NULL DEFAULT 'private',
    name TEXT NOT NULL,
    source_thread_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    state_summary TEXT DEFAULT '',
    tone TEXT DEFAULT '',
    relationship_context TEXT DEFAULT '',
    working_posture TEXT DEFAULT '',
    reuse_notes TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    FOREIGN KEY (source_thread_id) REFERENCES session_threads(thread_id)
);

CREATE TABLE handoffs (
    handoff_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    agent_id TEXT NOT NULL DEFAULT 'default',
    visibility TEXT NOT NULL DEFAULT 'private',
    thread_id TEXT,
    created_at TEXT NOT NULL,
    objective TEXT DEFAULT '',
    completed TEXT DEFAULT '[]',
    open_items TEXT DEFAULT '[]',
    next_step TEXT DEFAULT '',
    do_not_confuse TEXT DEFAULT '[]',
    notes TEXT DEFAULT '',
    FOREIGN KEY (thread_id) REFERENCES session_threads(thread_id)
);

CREATE TABLE audit_events (
    event_id TEXT PRIMARY KEY,
    time TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    details TEXT DEFAULT '{}'
);
```

数组或结构化字段第一版可以用 JSON 字符串保存。

所有写入都必须记录 `audit_events`。

旧数据库如果缺少 `agent_id` 或 `visibility` 字段，初始化时要自动迁移。旧数据默认
归到 `agent_id=default`、`visibility=private`。

## 数据对象

### Agent State

`agent_state` 表保存一条默认记录，建议 id 使用 `default`：

```json
{
  "version": 1,
  "updated_at": "2026-06-12T00:00:00+08:00",
  "communication_style": "",
  "relationship_position": "",
  "long_term_preferences": [],
  "boundaries": [],
  "stable_patterns": [],
  "notes": ""
}
```

Agent State 更新要保守。命令可以支持更新，但不要让普通 Thread 更新自动覆盖它。

### Session Thread

`session_threads` 表：

```json
{
  "version": 1,
  "thread_id": "thread_xxx",
  "agent_id": "codex",
  "visibility": "private|shared",
  "topic": "",
  "mode": "engineering|companion|planning|review|general",
  "status": "active|paused|closed",
  "created_at": "",
  "last_active_at": "",
  "last_position": "",
  "next_step": "",
  "state_summary": "",
  "source_session": "",
  "tags": [],
  "notes": "",
  "updated_by": "agent|user|system"
}
```

### State Snapshot

`state_snapshots` 表：

```json
{
  "version": 1,
  "snapshot_id": "snapshot_xxx",
  "agent_id": "codex",
  "visibility": "private|shared",
  "name": "",
  "source_thread_id": "",
  "created_at": "",
  "state_summary": "",
  "tone": "",
  "relationship_context": "",
  "working_posture": "",
  "reuse_notes": "",
  "tags": []
}
```

Snapshot 只能新增或人工修改，不要自动覆盖旧 Snapshot。

### Handoff

`handoffs` 表：

```json
{
  "version": 1,
  "handoff_id": "handoff_xxx",
  "agent_id": "codex",
  "visibility": "private|shared",
  "thread_id": "",
  "created_at": "",
  "objective": "",
  "completed": [],
  "open_items": [],
  "next_step": "",
  "do_not_confuse": [],
  "notes": ""
}
```

### Continuity Packet

Packet 不一定要长期保存。`resume` 命令可以直接输出：

```json
{
  "version": 1,
  "action": "continue|fork|blend|reset",
  "topic_source": {...},
  "state_source": {...},
  "agent_state": {...},
  "thread": {...},
  "snapshot": {...},
  "warnings": [],
  "next_response_posture": ""
}
```

## CLI 命令

请实现以下命令。

### 初始化

```bash
python3 skills/continuity/cli.py init
```

创建目录、`continuity.db`、表结构和默认 `agent_state`。

### 创建或更新 Thread

```bash
python3 skills/continuity/cli.py capture \
  --topic "Continuity v1 design" \
  --mode engineering \
  --last-position "正在讨论写入和更新机制" \
  --next-step "实现 CLI 和管理入口" \
  --state-summary "清晰、收敛、产品设计状态" \
  --source-session "codex-2026-06-12"
```

支持 `--thread-id`。如果传入已有 thread id，则更新；否则创建新 Thread。

### 列表

```bash
python3 skills/continuity/cli.py list
python3 skills/continuity/cli.py list --status active
python3 skills/continuity/cli.py list --agent-id codex
python3 skills/continuity/cli.py list --agent-id codex --include-shared
python3 skills/continuity/cli.py list --all-agents
python3 skills/continuity/cli.py list --json
```

### 查看

```bash
python3 skills/continuity/cli.py show --thread-id thread_xxx
python3 skills/continuity/cli.py show --snapshot-id snapshot_xxx
```

### 保存 Snapshot

```bash
python3 skills/continuity/cli.py snapshot \
  --thread-id thread_xxx \
  --name "warm-focused-design-state" \
  --state-summary "亲近但清晰的设计讨论状态" \
  --tone "warm, direct" \
  --working-posture "focused design"
```

### Resume / Router

继续同一条线：

```bash
python3 skills/continuity/cli.py resume \
  --thread-id thread_xxx
```

混合话题和状态：

```bash
python3 skills/continuity/cli.py resume \
  --topic-thread-id thread_xxx \
  --state-snapshot-id snapshot_xxx \
  --action blend
```

输出 Continuity Packet。支持 `--json`。

### Handoff

```bash
python3 skills/continuity/cli.py handoff \
  --thread-id thread_xxx \
  --objective "交给未来 Session 继续" \
  --completed "已完成A,已完成B" \
  --open-items "待确认C" \
  --next-step "继续处理C"

python3 skills/continuity/cli.py handoffs
python3 skills/continuity/cli.py show --handoff-id handoff_xxx
```

### 关闭 Thread

```bash
python3 skills/continuity/cli.py close --thread-id thread_xxx
```

### 编辑

```bash
python3 skills/continuity/cli.py edit \
  --thread-id thread_xxx \
  --last-position "新的当前位置" \
  --next-step "新的下一步"
```

也支持编辑 Snapshot 的 `name`、`state_summary`、`reuse_notes`。

### 合并

```bash
python3 skills/continuity/cli.py merge \
  --from-thread-id thread_old \
  --into-thread-id thread_main \
  --reason "重复创建的同一条线"
```

合并后：

- 主 Thread 保留
- 被合并 Thread 状态改成 `closed`
- 主 Thread 增加一条 tags 或 notes 记录
- `audit_events` 记录合并动作

### Agent State

查看：

```bash
python3 skills/continuity/cli.py agent-state show
python3 skills/continuity/cli.py agent-state show --agent-id lara
```

保守更新：

```bash
python3 skills/continuity/cli.py agent-state update \
  --communication-style "直接、清楚、少术语" \
  --note "用户明确要求汇报结果用简单直白语言"
```

## 人工管理入口

第一版至少要有 CLI 管理能力。

如果实现简单 Web 管理页，也可以，但不是必须。不要为了 UI 拖慢第一版。

人工管理必须覆盖：

- 查看所有 Thread
- 按 Agent 过滤查看
- 管理模式查看所有 Agent 的状态
- 查看所有 Snapshot
- 查看 Thread 详情
- 编辑错误摘要
- 关闭旧线
- 合并重复线
- 标记 Snapshot
- 删除明显错误的 Snapshot 或 Handoff

删除操作需要记录 `audit_events`。

## Agent 自行更新规则

系统要允许 Agent 在对话过程中主动调用 `capture`、`snapshot`、`close`、`edit`。

Agent 可以主动更新的情况：

- 话题明显变了
- 一个阶段完成了
- 下一步已经明确
- 当前状态明显变化
- 继续不保存会造成下次断裂
- 某条旧线已经自然结束

Agent 不应自动做的事：

- 把一次临时情绪写入 Agent State
- 自动混合多个 Session 状态
- 覆盖旧 Snapshot
- 在用户没有要求时删除状态

## 验收标准

Codex 会按下面标准验收。

### 文件和结构

- `skills/continuity/` 存在
- CLI 可运行
- 运行数据默认写入 `~/.claracore/continuity/`
- 设置 `CONTINUITY_ROOT` 后可以写入临时目录
- 运行数据使用 `continuity.db`
- 支持 `CONTINUITY_AGENT_ID` 或 `--agent-id`
- 不产生仓库内运行数据

### 基本功能

必须能完成以下流程：

1. 初始化 Continuity
2. 创建两个 active Thread
3. 保存一个 Snapshot
4. `list` 能看到两条线
5. `resume --thread-id` 能生成 continue Packet
6. `resume --topic-thread-id ... --state-snapshot-id ... --action blend` 能生成 blend Packet
7. `edit` 能修改 Thread 摘要
8. `merge` 能关闭重复 Thread，并保留主 Thread
9. `close` 能关闭 Thread
10. `agent-state update` 能更新 Agent State
11. `audit_events` 表能看到写入记录
12. 两个不同 `agent_id` 创建的 Thread 默认互相不可见
13. `visibility=shared` 的 Thread 只有在 `--include-shared` 时才被其他 Agent 看到

### 安全边界

- 不调用 Memoria
- 不依赖网络
- 不写仓库外的非 Continuity 位置
- 不覆盖用户已有数据，除非命令明确指定
- Snapshot 默认新增，不覆盖
- 第一版不实现缓存或热存储
- 默认不跨 Agent 读取或更新状态

### 文档

需要补充或保持更新：

- `skills/continuity/README.md`
- `skills/continuity/DESIGN.md`
- `skills/continuity/IMPLEMENTATION_TASK.md`
- `skills/continuity/USAGE.md`
- `skills/continuity/INSTALL.md`

文档要写清楚：

- Continuity 和 Memoria 独立
- 多 Session 是第一版核心场景
- Agent 可以主动更新
- 用户可以人工管理

## Codex 验收命令建议

Codex 验收时会使用临时目录，类似：

```bash
CONTINUITY_ROOT=/tmp/continuity-smoke python3 skills/continuity/cli.py init
CONTINUITY_ROOT=/tmp/continuity-smoke python3 skills/continuity/cli.py capture --topic "A" --mode engineering --last-position "pos A" --next-step "next A" --state-summary "state A"
CONTINUITY_ROOT=/tmp/continuity-smoke python3 skills/continuity/cli.py capture --topic "B" --mode companion --last-position "pos B" --next-step "next B" --state-summary "state B"
CONTINUITY_ROOT=/tmp/continuity-smoke python3 skills/continuity/cli.py list --json
sqlite3 /tmp/continuity-smoke/continuity.db "select count(*) from session_threads;"
sqlite3 /tmp/continuity-smoke/continuity.db "select count(*) from audit_events;"
```

Claude 完成后，请在回复里给出：

- 改了哪些文件
- 实现了哪些命令
- 跑过哪些验证
- 是否有未完成项
