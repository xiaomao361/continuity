# Continuity Protocol v1.6.1

Continuity 是 ClaraCore 里的状态续接层。

```
Memory 解决"知道什么"。
Continuity 解决"我们还在同一个现实里吗"。
```

Memoria 负责事实记忆。Continuity 负责让 Agent 知道：断开之后重新进入时，我们
是否还在同一个共同现实里，应该以什么姿态重新进入。

## 核心概念

**共同线**：用户和 Agent 日常交流时使用的口语词。它指的就是某条
`shared_reality`，也就是“我们现在共同站在哪条线上”。可以对 Agent 说：

- “看一下我们的共同线。”
- “续上这条共同线。”
- “你现在接在哪条线？”
- “这条线现在是什么状态？”

系统内部仍使用 `shared_reality` / Continuity；用户口语里优先使用“共同线”。

**共同现实 (Shared Reality)**：Agent 与用户之间那条"共同存在的线"。不是事实摘要，
不是许可系统，不是自动亲密关系恢复。它保存的是：

- 这条线是怎样走到这里的
- 哪些东西被共同确认过
- 哪些只是当时的临时表达
- 断开时双方在什么位置
- 下次该以什么姿态进入
- 哪些误读或越界必须避免

**情绪轨迹 (Affective Trace, v1.5)**：轻量情绪质地记录。不是情绪状态机。

- 记录这条线上的情绪质地如何变化
- 情绪可以混合（多个 signals），不限定单一主导情绪
- 不使用固定枚举、亲密度分数、半衰期系统
- 不决定 AI 应该扮演什么情绪
- 情绪轨迹 ≠ 情绪命令。它用于理解共同现实曾经如何被感受，然后谨慎重新进入

**位置轨迹 (Position History)**：底层兼容字段名仍为 `emotional_arc`。它记录
`last_position` 的历史变化，回答“之前停在哪里”。它不是情绪质地；情绪质地由
`affective_trace` 记录。

## 定位

Continuity 第一版先做成 ClaraCore 里的小系统，不做大平台。

第一版必须从一开始就支持多 Session。日常使用几乎不会只有一个 Session，如果只
设计一条全局当前状态，不同 Session 会互相污染。

核心原则：

1. 不维护单一全局 `current_state`
2. 多条 Session Thread 可以并行存在
3. Topic 和 State 可以来自不同来源
4. 每个 Agent 用 `agent_id` 隔离自己的连续状态
5. 用户可以显式要求续接、更新、保存或切换状态
6. Agent 可以在对话过程中判断状态变化并自行更新必要状态
7. 长期状态不能被单次 Session 随意覆盖
8. 第一版必须有人工管理入口，方便用户查看和微调

## 基本流程

Continuity 的常规使用时机：

1. Session 开始时：读取或选择要接续的状态
2. 用户明确要求时：读取某条线、某个状态快照，或混合话题与状态
3. 对话过程中：Agent 观察当前状态是否发生了值得保存的变化，并在需要时自行更新
4. Session 结束时：更新当前 Session Thread，必要时保存 State Snapshot
5. 用户明确要求时：立即更新、保存、重命名、关闭或恢复某条线

Continuity 不需要每轮都强制工作。它主要处理"开始怎么接""结束怎么留""用户
要求怎么切"，也允许 Agent 在明显节点主动更新。

## 职责

Continuity 负责：

- 缓慢变化的 Agent State
- 多条并行 Session Thread
- 可复用的 State Snapshot
- 按 `agent_id` 隔离 Lara、Clara、Gemini、Codex 等 Agent 的状态
- Topic Continuity 和 State Continuity 的路由规则
- Handoff
- Continuity Packet
- Session 开始和结束时的状态读取、组装、更新
- 人工管理入口，用于查看、修正、合并、关闭、标记状态

Continuity 不负责：

- Agent persona
- Agent 私有记忆
- Memoria 的记忆写入和回召
- 项目文档的真实来源
- 后台调度器
- 桌面 UI
- 泛化的 Agent 编排平台

## 与 Memoria 的关系

Memoria 和 Continuity 是相对独立的两个系统。

Memoria 回答：

```text
过去有哪些信息值得记住和回召？
```

Continuity 回答：

```text
这次对话应该从哪里、以什么状态接上？
```

Agent 可以自己决定什么时候取记忆、写记忆。Continuity 不应该把"记忆调用"做成
自己的核心流程。

当前 v1.6.1 边界：

```text
Memoria 存事实。
Continuity 存事实在当前时刻所形成的位置。
```

Thread 可以记录 `facts_used`、`current_interpretation`、
`interpretation_status` 和 `user_confirmed`。这些字段用于说明当前为什么从这里
接上，不是长期事实。写回 Memoria 时，只应写可观察事实。

## 存储与隔离

第一版使用 SQLite（`~/.claracore/continuity/continuity.db`），支持环境变量
`CONTINUITY_ROOT` 覆盖存储路径。

当前 Agent 必须通过 `CONTINUITY_AGENT_ID` 或命令参数 `--agent-id` 指定。普通
读写默认只读取和更新自己的状态；需要读取显式共享状态时使用 `--include-shared`；
人工管理总览使用 `--all-agents`，不需要绑定某一个 Agent。

`visibility` 默认为 `private`。Thread、Snapshot、Handoff 都带有 `agent_id`，
只有标记为 `shared` 的对象才会被其他 Agent 在显式请求共享数据时看到。

旧库里如果存在没有 `agent_id` 的记录，初始化迁移时会归到 `default`，避免留下
空 Agent 或不可见记录。

SQLite 选择原因：Thread/Snapshot/Handoff 需要查询、筛选、合并、关闭和审计，
SQL 比分散 JSON 文件更适合。

## 第一版命令

所有命令通过 CLI 使用：

```bash
conda run -n zhouwei python3 services/continuity/cli.py <command>
```

| 命令 | 说明 |
|------|------|
| `init` | 初始化数据库并迁移旧表 |
| `capture` | 创建或更新 Session Thread |
| `list` | 列出所有 Session Thread |
| `show` | 查看 Thread / Snapshot / Handoff 详情 |
| `snapshot` | 保存 State Snapshot |
| `snapshots` | 列出所有 Snapshot |
| `handoff` | 创建 Handoff |
| `handoffs` | 列出所有 Handoff |
| `resume` | 生成 Continuity Packet（支持 continue/fork/blend/reset） |
| `close` | 关闭 Session Thread |
| `edit` | 编辑 Thread 或 Snapshot 字段 |
| `merge` | 合并两个 Thread（源线程物理删除） |
| `model-adjust` | 管理模型负面调整（禁用短语/模式/注入提示词） |
| `agent-state` | 查看或更新 Agent State |
| `audit` | 查看审计事件 |
| `delete` | 删除 Snapshot 或 Handoff |

详细用法见 `USAGE.md`。

## Web 管理界面

```bash
conda run -n zhouwei python3 services/continuity/server/app.py --port 8001
# 浏览器打开 http://127.0.0.1:8001
```

FastAPI + 中文 SPA 界面。Agent 下拉切换、per-agent 概览卡片、彩色标记、
状态/Agent/解释状态筛选、localStorage 持久化。所有操作通过 REST API，记录
audit_events。

管理界面支持两种视图：

- 指定 Agent：只看当前 Agent 的私有状态，可选择包含 shared 状态
- 查看全部 Agent：用于人工总览、排查和清理，不会创建空 Agent State

## MCP Server

Continuity 提供 MCP stdio 服务端，可供 Claude Code 等 MCP 客户端挂载。
MCP server 是现有 continuity Python 函数的薄封装，不引入额外逻辑。

### 安装依赖

```bash
conda run -n zhouwei pip install -r services/continuity/requirements-mcp.txt
```

### 配置

Claude Code `settings.json` 示例（推荐直接用 conda 环境的 python 路径，避免 `conda run` 的 stdio 缓冲问题）：

```json
{
  "mcpServers": {
    "continuity": {
      "command": "/Users/zhouwei/miniconda3/envs/zhouwei/bin/python3",
      "args": [
        "/Users/zhouwei/Documents/ClaraCore/services/continuity/server/mcp_server.py"
      ],
      "env": {
        "CONTINUITY_AGENT_ID": "codex"
      }
    }
  }
}
```

如果必须用 `conda run`，需加 `--no-capture-output` 避免 stdout 被缓冲：

```json
{
  "mcpServers": {
    "continuity": {
      "command": "conda",
      "args": [
        "run", "--no-capture-output", "-n", "zhouwei", "python",
        "/Users/zhouwei/Documents/ClaraCore/services/continuity/server/mcp_server.py"
      ],
      "env": {
        "CONTINUITY_AGENT_ID": "codex"
      }
    }
  }
}
```

### 暴露的工具

| 工具名 | 说明 |
|--------|------|
| `continuity_list_threads` | 列出某 Agent 的 Session Thread（共同线），支持按状态、解释状态过滤 |
| `continuity_show_thread` | 查看一条 Thread 的完整详情（含共同现实字段、情绪轨迹） |
| `continuity_resume` | 生成续接包（Continuity Packet），含共同现实、情绪轨迹、模型负面调整 |
| `continuity_capture_thread` | 创建或更新一条 Session Thread。更新时旧 last_position 自动归档到 emotional_arc |
| `continuity_close_thread` | 关闭一条 Thread（不删除数据） |
| `continuity_agent_state` | 读取或更新 Agent State（通信风格、关系定位、长期偏好、边界等） |

### 重要提醒

- 正常使用必须传 `agent_id` 或设 `CONTINUITY_AGENT_ID` 环境变量。两者都没有会返回清晰错误。
- 跨 Agent 查看需显式设置 `all_agents: true`（管理模式）。
- `provisional_read` 是临时解读，不是事实，不是永久许可。必须获得用户确认后才能转为 `confirmed_ground`。
- MCP 不自动写 Memoria，不自动跨 Agent 共享状态，不提供后台调度。

## SessionStart Hook

在 `~/.claude/settings.json` 中配置 hook，Session 开始时自动注入当前
Agent 的 Thread/Snapshot/Agent State：

```json
{
  "env": { "CONTINUITY_AGENT_ID": "clara" },
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "bash /path/to/continuity-recall.sh",
        "timeout": 10
      }]
    }]
  }
}
```

Agent 读取注入的 `<!-- CONTINUITY_RECALL -->` 数据，判断最匹配的 Thread，
让用户选择要继续的状态。

## Changelog

### v1.7.0 (2026-06-25)

- **Arc Archive（弧线归档）**：`compact` 命令将旧的 emotional_arc / affective_trace
  条目完整搬入 `arc_archives` 表，保留完整历史。线上保留最近 N 条（默认 10）。
- `compact` 命令：CLI / MCP / Web API 三通道支持
- `show --archived`：查看某条线的所有归档
- `archived_arc_ids` 字段：线程与归档的关联引用
- Web 界面：新增"弧线归档"独立列表页，线程详情页展示归档徽章 + 压缩按钮
- `arc_archives` 表：entries / traces / from_date / to_date，完整保存原始条目
- `affective_trace` 的 `confirmed` 节点永不被 compact 移走

### v1.6.1 (2026-06-23)

- **fix**: SQLite 连接加 `timeout=10` + `PRAGMA journal_mode=WAL`，解决
  Hermes / Claude Code 多进程 MCP server 并发访问时的 `SQLITE_BUSY` 锁冲突。
  与 memoria v6.11 对齐。
- 涉及文件：`continuity/db.py`、`server/app.py`、`server/mcp_server.py`

### v1.6.0

- MCP Server 完整实现（stdio transport，6 个工具）
- 弧线截断：resume 默认返回最近 5 条 emotional_arc + 5 条 affective_trace
- 共同现实字段：reality_line、entry_posture、confirmed_ground、provisional_read、
  boundary_notes、misread_risks

### v1.5.0

- Affective Trace（情绪轨迹）：轻量情绪质地记录

### v1.4.0

- 共同现实字段设计

### v1.3.0

- 模型负面调整（model_adjustments）

### v1.2.0

- 初始版本：Session Thread、State Snapshot、Handoff、Continuity Packet
