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

## 存储

第一版使用 SQLite（`~/.claracore/continuity/continuity.db`），支持环境变量
`CONTINUITY_ROOT` 覆盖存储路径。

当前 Agent 可以通过 `CONTINUITY_AGENT_ID` 或命令参数 `--agent-id` 指定。默认
只读取自己的状态；需要读取显式共享状态时使用 `--include-shared`；人工管理总览
使用 `--all-agents`。

SQLite 选择原因：Thread/Snapshot/Handoff 需要查询、筛选、合并、关闭和审计，
SQL 比分散 JSON 文件更适合。

## 第一版命令

所有命令通过 CLI 使用：

```bash
conda run -n zhouwei python3 skills/continuity/cli.py <command>
```

| 命令 | 说明 |
|------|------|
| `init` | 初始化数据库和默认 Agent State |
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
