# Continuity Protocol

Continuity 是 ClaraCore 里的状态续接层。

它不替代 Memoria，也不负责记忆回召。Memoria 偏"记住什么"，Continuity
偏"这次应该怎么接上"。两者可以被同一个 Agent 一起使用，但系统职责应当相互独立。

Continuity 的核心目标是：在长对话、多 Session、上下文重建、Agent 切换时，让
Agent 能继续站在合适的位置，而不是只知道过去发生过什么。

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

当前 1.1 边界：

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
conda run -n zhouwei python3 skills/continuity/cli.py <command>
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
| `merge` | 合并两个 Thread |
| `agent-state` | 查看或更新 Agent State |
| `audit` | 查看审计事件 |
| `delete` | 删除 Snapshot 或 Handoff |

详细用法见 `USAGE.md`。

## Web 管理界面

```bash
conda run -n zhouwei python3 skills/continuity/server/app.py --port 8001
# 浏览器打开 http://127.0.0.1:8001
```

FastAPI + 中文 SPA 界面。Agent 下拉切换、per-agent 概览卡片、彩色标记、
状态/Agent/解释状态筛选、localStorage 持久化。所有操作通过 REST API，记录
audit_events。

管理界面支持两种视图：

- 指定 Agent：只看当前 Agent 的私有状态，可选择包含 shared 状态
- 查看全部 Agent：用于人工总览、排查和清理，不会创建空 Agent State

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
