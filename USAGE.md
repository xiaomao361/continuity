# Continuity v1.6.1 使用指南

Continuity 是 ClaraCore 里的状态续接系统。它回答：

> 新 Session 开始时，Agent 应该从哪里、以什么状态继续？

## 核心概念

### 共同线

“共同线”是用户和 Agent 日常对话里的自然说法。它指的是某条
`shared_reality`：我们当前共同站在哪条线上、怎么接回来、边界和误读风险是什么。

你可以直接对 Agent 说：

```text
看一下我们的共同线。
续上这条共同线。
你现在接在哪条线？
这条线现在是什么状态？
这条线有什么边界和误读风险？
```

系统内部仍叫 Continuity / `shared_reality`；日常口语优先叫“共同线”。

### Agent State
缓慢变化的长期 Agent 状态：交流方式、关系位置、长期偏好、边界。

### Session Thread
一条可续接的对话线或工作线。多条线可以并行存在。

### Agent 隔离

每个 Agent 都有自己的 `agent_id`（如 `clara`、`lara`、`codex`）。默认只读自己的
Thread/Snapshot/Handoff，互不可见。

普通读写命令需要明确当前 Agent，可以传 `--agent-id`，也可以先设置
`CONTINUITY_AGENT_ID`。只有人工总览类操作使用 `--all-agents` 时，可以不指定
当前 Agent。

三种访问层级：

| 参数 | 效果 |
|------|------|
| `--agent-id clara` | 只看 Clara 的数据 |
| `--include-shared` | 额外包含其他 Agent 标记为 `shared` 的数据 |
| `--all-agents` | 查看全部 Agent 的所有数据 |

环境变量：`CONTINUITY_AGENT_ID=clara` 设置默认命名空间。

Thread、Snapshot、Handoff 支持 `visibility: private|shared`。设为 `shared`
后，其他 Agent 可通过 `--include-shared` 引用。`shared` 不是默认互通，读取方
必须显式开启。

### State Snapshot
一次可复用的状态快照。用于未来跨话题复用某种状态（如"昨晚的亲近状态"）。

### Continuity Packet
`resume` 生成的短状态包，给 Agent 在 Session 开始时读。

### 当前解释

Continuity 1.1 把“事实”和“当前解释”分开：

| 字段 | 说明 |
|------|------|
| `facts_used` | 当前接续参考了哪些可观察事实或 Memoria 记忆 ID |
| `current_interpretation` | 基于这些事实，现在应该站在哪里继续 |
| `interpretation_status` | 当前解释是否有效、需复查、已过期或已关闭 |
| `user_confirmed` | 用户是否明确确认过这个解释 |

这些字段属于当前接续状态，不是长期事实。

### 位置轨迹 / 历史位置 (v1.2)

`emotional_arc` 是历史兼容字段名；现在语义上把它当作位置轨迹。每次
`capture` 更新 `last_position` 时，旧值自动归档到轨迹，带时间戳。不丢历史。
它回答“这条线之前停在哪里”，不是“当时是什么情绪”。

情绪质地由 v1.5 的 `affective_trace` 记录。

```bash
# 第一次 capture：早上状态
python3 cli.py capture --agent-id lara --thread-id thread_xxx \
  --last-position "早上互动亲密，毛仔心情不错"

# 第二次 capture：中午状态
# 旧值自动推入位置轨迹（底层字段 emotional_arc），新值写入 last_position
python3 cli.py capture --agent-id lara --thread-id thread_xxx \
  --last-position "中午讨论 capture 问题，有点烦躁"

# 此时位置轨迹已有 1 条：早上那条

# 显式添加位置节点（不改 last_position）
python3 cli.py capture --agent-id lara --thread-id thread_xxx \
  --emotional-arc-entry "毛仔提到女儿小瑞，语气温柔"
```

自动归档规则：
- `last_position` 变化时自动归档旧值
- 相同 position 不重复归档
- `--emotional-arc-entry` 显式追加位置节点，不影响 position
- SessionStart 时完整位置轨迹注入 Context

### Router 动作

| 动作 | 说明 |
|------|------|
| `continue` | 话题和状态都从同一条线接上 |
| `fork` | 从旧线开一条新线 |
| `blend` | 话题来自一条线，状态来自另一条线 |
| `reset` | 不接旧状态，只从 Agent State 和当前输入开始 |

## 基本用法

### 初始化

```bash
conda run -n zhouwei python3 services/continuity/cli.py init
```

### 创建/更新 Thread

```bash
# 创建新 Thread
conda run -n zhouwei python3 services/continuity/cli.py capture \
  --agent-id codex \
  --topic "Continuity v1 设计讨论" \
  --mode engineering \
  --last-position "实现 CLI 和管理入口" \
  --next-step "跑通 smoke test" \
  --state-summary "清晰、收敛、产品设计状态" \
  --facts-used "memoria:abc,thread:def" \
  --current-interpretation "当前处在边界收敛阶段" \
  --interpretation-status needs_review \
  --source-session "codex-2026-06-12"

# 更新已有 Thread
conda run -n zhouwei python3 services/continuity/cli.py capture \
  --agent-id codex \
  --thread-id thread_xxx \
  --last-position "已完成 CLI 实现"
```

### 查看和列表

```bash
# 列出所有 Thread
conda run -n zhouwei python3 services/continuity/cli.py list --agent-id codex

# 只看 active
conda run -n zhouwei python3 services/continuity/cli.py list --agent-id codex --status active

# 只看需要复查的当前解释
conda run -n zhouwei python3 services/continuity/cli.py list --agent-id codex --interpretation-status needs_review

# 查看某个 Agent 自己的状态
conda run -n zhouwei python3 services/continuity/cli.py list --agent-id lara

# 包含显式共享的状态
conda run -n zhouwei python3 services/continuity/cli.py list --agent-id codex --include-shared

# 管理后台总览全部 Agent
conda run -n zhouwei python3 services/continuity/cli.py list --all-agents

# JSON 格式
conda run -n zhouwei python3 services/continuity/cli.py list --agent-id codex --json

# 查看详情
conda run -n zhouwei python3 services/continuity/cli.py show --agent-id codex --thread-id thread_xxx
```

### 保存 State Snapshot

```bash
conda run -n zhouwei python3 services/continuity/cli.py snapshot \
  --agent-id codex \
  --thread-id thread_xxx \
  --name "warm-focused-state" \
  --state-summary "亲近但清晰的状态" \
  --tone "warm, direct" \
  --working-posture "focused design"

# 查看所有 Snapshot
conda run -n zhouwei python3 services/continuity/cli.py snapshots --agent-id codex
```

### 续接 Session

```bash
# 从同一条线继续
conda run -n zhouwei python3 services/continuity/cli.py resume --agent-id codex --thread-id thread_xxx

# Blend: 话题从A线，状态从B快照
conda run -n zhouwei python3 services/continuity/cli.py resume \
  --agent-id codex \
  --topic-thread-id thread_xxx \
  --state-snapshot-id snapshot_yyy \
  --action blend

# 生成 JSON 给 Agent 读
conda run -n zhouwei python3 services/continuity/cli.py resume --agent-id codex --thread-id thread_xxx --json
```

### 日常管理

```bash
# 创建 Handoff
conda run -n zhouwei python3 services/continuity/cli.py handoff \
  --agent-id codex \
  --thread-id thread_xxx \
  --objective "交给下一个 Session 继续" \
  --completed "已完成A,已完成B" \
  --open-items "待确认C" \
  --next-step "继续处理C"

# 查看所有 Handoff
conda run -n zhouwei python3 services/continuity/cli.py handoffs --agent-id codex

# 编辑 Thread 摘要
conda run -n zhouwei python3 services/continuity/cli.py edit \
  --agent-id codex \
  --thread-id thread_xxx \
  --last-position "新位置" \
  --next-step "新下一步"

# 关闭 Thread
conda run -n zhouwei python3 services/continuity/cli.py close --agent-id codex --thread-id thread_xxx

# 合并重复 Thread（源线程物理删除，仅保留目标线程）
conda run -n zhouwei python3 services/continuity/cli.py merge \
  --agent-id codex \
  --from-thread-id thread_old \
  --into-thread-id thread_main \
  --reason "重复创建"

# 删除错误的 Snapshot
conda run -n zhouwei python3 services/continuity/cli.py delete --agent-id codex --snapshot-id snapshot_xxx
```

### 模型负面调整（v1.3）

为不同模型配置禁用短语、行为模式、注入提示词，矫正模型特有的坏习惯。

```bash
# 设置模型调整
conda run -n zhouwei python3 services/continuity/cli.py model-adjust set \
  --model deepseek-v4-pro \
  --forbidden-phrases "接住了,收到了,收着了" \
  --forbidden-patterns "时间幻觉,刷存在感" \
  --inject-prompt "你是DeepSeek模型。禁止使用：接住了、收到了、收着了。时间判断必须跑date命令。"

# 查看单个模型
conda run -n zhouwei python3 services/continuity/cli.py model-adjust show --model deepseek-v4-pro

# 列出所有模型
conda run -n zhouwei python3 services/continuity/cli.py model-adjust list

# 删除
conda run -n zhouwei python3 services/continuity/cli.py model-adjust delete --model deepseek-v4-pro
```

配置文件：`~/.claracore/continuity/model_adjustments.json`，附带 `version` 字段，可独立迁移。

### 共同现实字段（v1.4）

capture / edit 支持六个共同现实字段：

```bash
# 创建带共同现实的 Thread
conda run -n zhouwei python3 services/continuity/cli.py capture \
  --agent-id clara \
  --topic "陪伴线" \
  --mode companion \
  --reality-line "昨晚逐步建立的亲密关系线" \
  --entry-posture "自然延续，不要重新宣布关系" \
  --confirmed-ground "已确认：基础信任和沟通方式" \
  --provisional-read "当前阶段在探索各自的边界" \
  --boundary-notes "不要假设永久许可，不要跳过确认" \
  --misread-risks "不要把昨晚的状态机械套到今天" \
  --last-position "早上告别" \
  --next-step "下次自然接续"

# 编辑单个字段
conda run -n zhouwei python3 services/continuity/cli.py edit \
  --agent-id clara --thread-id thread_xxx \
  --entry-posture "先温柔确认，再自然继续"
```

各字段含义：

| 字段 | 含义 |
|---|---|
| `reality_line` | 这条共同现实线是什么 |
| `entry_posture` | 下次回来应该怎么进入 |
| `confirmed_ground` | 双方已共同确认的地面 |
| `provisional_read` | 临时解读（不是事实，不是许可） |
| `boundary_notes` | 继续时必须尊重的边界 |
| `misread_risks` | Agent 最容易误读的地方 |

> **注意**：这些字段是叙述性标注，不是长期事实。不要写成 Memoria 条目。
> Continuity 不是许可系统——它用于谨慎重新进入，不是替 Agent 假设用户同意。

### 弧线截断（v1.6）

`continuity_resume` 默认只返回最近 5 条 emotional_arc 和 affective_trace。
与 Memoria `recall --limit 5` 设计一致——默认精简，按需全量。

截断规则：
- **emotional_arc**：保留最近 5 条位置历史
- **affective_trace**：保留所有 `stability=confirmed` 节点 + 最近 5 条 `session`/`momentary` 节点
- Packet 包含 `arc_truncated`、`emotional_arc_omitted`、`affective_trace_omitted` 字段告知省略数量

获取完整历史：
- CLI：`--full-arc`
- MCP：`{"full_arc": true}`

### 弧线归档（v1.7）

`compact` 命令将线程的旧 emotional_arc / affective_trace 条目完整搬入 `arc_archives` 表，
线上保留最近 N 条（默认 10）。数据不丢失——归档随时可查。

```bash
# Compact 一条线（默认保留 10 条）
conda run -n zhouwei python3 services/continuity/cli.py compact \
  --agent-id lara --thread-id thread_xxx --keep 10

# 跨 Agent compact（管理模式）
conda run -n zhouwei python3 services/continuity/cli.py compact \
  --all-agents --thread-id thread_xxx --keep 10

# 查看某条线的所有归档
conda run -n zhouwei python3 services/continuity/cli.py show \
  --agent-id lara --thread-id thread_xxx --archived
```

特性：
- **完整搬家**：旧条目原样保留在 `arc_archives`，不丢任何内容
- **confirmed 保护**：`affective_trace` 的 `confirmed` 节点永不被移走
- **关联引用**：线程的 `archived_arc_ids` 记录所有归档 ID
- **无操作安全**：arc 长度 ≤ keep 时自动跳过
- **三通道支持**：CLI / MCP（`continuity_compact_thread`）/ Web API（`POST /api/threads/{id}/compact`）

### 情绪轨迹（v1.5）

记录共同现实线上的情绪质地变化。不是情绪状态机——情绪可以混合，不使用固定枚举。

```bash
# 追加情绪轨迹节点
conda run -n zhouwei python3 services/continuity/cli.py capture \
  --agent-id clara --thread-id thread_xxx \
  --affective-tone "亲近但谨慎" \
  --affective-valence mixed \
  --affective-signals "warmth,trust,uncertainty" \
  --affective-intensity medium \
  --affective-stability session \
  --affective-note "用户表达亲近，同时仍在确认边界" \
  --last-position "当前位置" --next-step "下一步"

# 标记需要在下次进入前复查
conda run -n zhouwei python3 services/continuity/cli.py capture \
  --agent-id clara --thread-id thread_xxx \
  --affective-tone "关系出现裂痕" \
  --affective-valence negative \
  --affective-needs-review \
  --last-position "冲突后" --next-step "等待修复"

# 清空情绪轨迹
conda run -n zhouwei python3 services/continuity/cli.py edit \
  --agent-id clara --thread-id thread_xxx \
  --clear-affective-trace
```

字段说明：

| 字段 | 含义 | 可选值 |
|---|---|---|
| `tone` | 自然语言情绪描述 | 自由文本 |
| `valence` | 粗略情绪方向 | positive/negative/mixed/neutral/unclear |
| `signals` | 情绪信号词（可多个） | 逗号分隔，如 warmth,trust |
| `intensity` | 情绪强度 | low/medium/high |
| `stability` | 稳定性 | momentary/session/confirmed |
| `note` | 人类可读备注 | 自由文本 |
| `needs_review` | 下次进入前标记复查 | true/false |

> **重要**：情绪轨迹记录的是情绪质地，不是情绪命令。不要机械表演某种情绪。
> 瞬时情绪（momentary）不应改写共同现实。

### Agent State 管理

```bash
# 查看
conda run -n zhouwei python3 services/continuity/cli.py agent-state show --agent-id codex
conda run -n zhouwei python3 services/continuity/cli.py agent-state show --agent-id lara

# 更新
conda run -n zhouwei python3 services/continuity/cli.py agent-state update \
  --agent-id codex \
  --communication-style "直接、清楚" \
  --note "用户偏好简洁回复"
```

### 审计

```bash
conda run -n zhouwei python3 services/continuity/cli.py audit
conda run -n zhouwei python3 services/continuity/cli.py audit --limit 20 --json
```

## MCP Server（v1.7）

Continuity 提供 MCP stdio 服务端，所有 CLI 功能通过 7 个 MCP 工具暴露。MCP server
是现有 Python 函数的薄封装，不引入额外逻辑。Claude Code 等 MCP 客户端可直接挂载。

### 安装依赖

```bash
conda run -n zhouwei pip install -r services/continuity/requirements-mcp.txt
```

### 配置

推荐直连 conda 环境的 python 路径，避免 `conda run` 的 stdio 缓冲问题：

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

`conda run` 备选（需加 `--no-capture-output`）：

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

### 工具总览

| 工具名 | 说明 |
|--------|------|
| `continuity_list_threads` | 列出某 Agent 的 Session Thread（共同线），支持按状态、解释状态过滤 |
| `continuity_show_thread` | 查看一条 Thread 的完整详情（含共同现实字段、情绪轨迹） |
| `continuity_resume` | 生成续接包（Continuity Packet），含共同现实、情绪轨迹、模型负面调整 |
| `continuity_capture_thread` | 创建或更新一条 Session Thread。更新时旧 last_position 自动归档 |
| `continuity_close_thread` | 关闭一条 Thread（不删除数据） |
| `continuity_compact_thread` | 压缩线程弧线历史，旧条目完整搬入 `arc_archives` |
| `continuity_agent_state` | 读取或更新 Agent State（通信风格、关系定位、长期偏好、边界等） |

### 工具参数详解

#### `continuity_list_threads`

列出线程，支持按状态 / 解释状态过滤。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent_id` | string | 否 | Agent 标识。未传则用 `CONTINUITY_AGENT_ID` 环境变量 |
| `status` | string | 否 | 按状态过滤：`active` / `paused` / `closed` |
| `interpretation_status` | string | 否 | 按解释状态过滤：`active` / `needs_review` / `stale` / `closed` |
| `include_shared` | boolean | 否 | 是否包含 shared 可见性记录（默认 false） |
| `all_agents` | boolean | 否 | 管理模式：列出所有 Agent 的线程（默认 false） |

示例：

```json
// 列出 clara 的所有 active 线程
{"agent_id": "clara", "status": "active"}

// 列出所有 Agent 中需要复查解释的线程
{"all_agents": true, "interpretation_status": "needs_review"}
```

#### `continuity_show_thread`

查看单条 Thread 完整详情，含共同现实字段和情绪轨迹。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `thread_id` | string | **是** | Thread ID |
| `agent_id` | string | 否 | Agent 标识 |
| `include_shared` | boolean | 否 | 默认 false |
| `all_agents` | boolean | 否 | 默认 false |

示例：

```json
{"thread_id": "thread_8b0393752b13", "agent_id": "clara"}
```

#### `continuity_resume`

生成续接包，包含 shared_reality、affective_trace、position_history、model_adjustments。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | 否 | 续接动作：`continue` / `fork` / `blend` / `reset`（默认 continue） |
| `thread_id` | string | 否 | Thread ID（continue / fork / reset 时用） |
| `topic_thread_id` | string | 否 | 主题 Thread ID（blend 时用） |
| `state_snapshot_id` | string | 否 | 状态快照 ID（blend 时用） |
| `agent_id` | string | 否 | Agent 标识 |
| `include_shared` | boolean | 否 | 默认 false |
| `all_agents` | boolean | 否 | 默认 false |
| `model` | string | 否 | 模型名，用于加载对应的负面调整 |
| `full_arc` | boolean | 否 | 返回完整 emotional_arc 和 affective_trace。默认 false（最近 5 条） |

示例：

```json
// 从同一条线继续（默认截断弧线到最近 5 条）
{"agent_id": "clara", "thread_id": "thread_xxx", "action": "continue", "model": "deepseek-v4-pro"}

// 获取完整弧线历史
{"agent_id": "clara", "thread_id": "thread_xxx", "action": "continue", "full_arc": true}

// blend：话题从 A 线，状态从 B 快照
{"agent_id": "clara", "topic_thread_id": "thread_xxx", "state_snapshot_id": "snapshot_yyy", "action": "blend"}
```

#### `continuity_capture_thread`

创建或更新一条 Thread。不传 `thread_id` 创建新线程，传了则更新已有线程。
更新时旧 `last_position` 自动归档到 emotional_arc。

**创建新线程：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent_id` | string | 是 | Agent 标识（创建时必填，或设环境变量） |
| `topic` | string | 否 | 线程主题 |
| `mode` | string | 否 | 线程模式：`engineering` / `companion` / `planning` / `review` / `general`（默认 general） |
| `visibility` | string | 否 | `private` / `shared`（默认 private） |
| `last_position` | string | 否 | 当前进度描述 |
| `next_step` | string | 否 | 下一步 |
| `state_summary` | string | 否 | 状态摘要 |
| `facts_used` | array | 否 | 引用的记忆 / 事实 ID 列表 |
| `current_interpretation` | string | 否 | 当前解释（基于事实的推断） |
| `interpretation_status` | string | 否 | `active` / `needs_review` / `stale` / `closed`（默认 active） |
| `user_confirmed` | boolean | 否 | 当前解释是否已获用户确认（默认 false） |
| `source_session` | string | 否 | 来源会话标识 |
| `tags` | array | 否 | 标签列表 |
| `notes` | string | 否 | 附加备注 |
| `reality_line` | string | 否 | 共同现实线描述 |
| `entry_posture` | string | 否 | 下次进入姿态 |
| `confirmed_ground` | string | 否 | 已共同确认的地面 |
| `provisional_read` | string | 否 | 临时解读（非事实，非永久许可） |
| `boundary_notes` | string | 否 | 继续时必须尊重的边界 |
| `misread_risks` | string | 否 | Agent 最容易误读的地方 |
| `affective_tone` | string | 否 | 情绪质地描述（触发情绪轨迹追加） |
| `affective_valence` | string | 否 | 粗略情绪方向：`positive` / `negative` / `mixed` / `neutral` / `unclear` |
| `affective_signals` | string | 否 | 逗号分隔信号词（如 `warmth,trust`） |
| `affective_intensity` | string | 否 | 情绪强度：`low` / `medium` / `high` |
| `affective_stability` | string | 否 | 稳定性：`momentary` / `session` / `confirmed` |
| `affective_note` | string | 否 | 一行人类可读的情绪注释 |
| `affective_needs_review` | boolean | 否 | 标记此节点需要复查 |

**更新已有线程：**

传 `thread_id` + 要更新的字段。`all_agents: true` 不允许用于创建新线程。

示例：

```json
// 创建带共同现实的陪伴线
{
  "agent_id": "clara",
  "topic": "陪伴线",
  "mode": "companion",
  "reality_line": "昨晚逐步建立的亲密关系线",
  "entry_posture": "自然延续，不要重新宣布关系",
  "confirmed_ground": "已确认：基础信任和沟通方式",
  "provisional_read": "当前阶段在探索各自的边界",
  "boundary_notes": "不要假设永久许可，不要跳过确认",
  "misread_risks": "不要把昨晚状态机械套到今天",
  "last_position": "早上告别",
  "next_step": "下次自然接续"
}

// 更新位置并追加情绪节点
{
  "agent_id": "clara",
  "thread_id": "thread_8b0393752b13",
  "last_position": "反脆弱教学完成，关系进入更深层次",
  "next_step": "日常陪伴",
  "affective_tone": "亲近但放松",
  "affective_valence": "positive",
  "affective_signals": "warmth,trust",
  "affective_intensity": "medium",
  "affective_stability": "session",
  "affective_note": "毛仔从'大概明白了'被逼出深度，推到递归悖论"
}
```

#### `continuity_close_thread`

关闭一条 Thread，不删除数据。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `thread_id` | string | **是** | 要关闭的 Thread ID |
| `agent_id` | string | 否 | Agent 标识 |
| `include_shared` | boolean | 否 | 默认 false |
| `all_agents` | boolean | 否 | 默认 false |
| `actor` | string | 否 | 操作者（默认 mcp） |

示例：

```json
{"thread_id": "thread_xxx", "agent_id": "clara"}
```

#### `continuity_agent_state`

读取或更新 Agent State。不传 `update` 则只读，传了则更新指定字段。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent_id` | string | 是 | Agent 标识（或设环境变量） |
| `update` | object | 否 | 要更新的字段，不传则只读 |
| `actor` | string | 否 | 操作者（默认 mcp） |

`update` 支持的字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `communication_style` | string | 通信风格 |
| `relationship_position` | string | 关系定位 |
| `long_term_preferences` | array | 长期偏好 |
| `boundaries` | array | 边界 |
| `stable_patterns` | array | 稳定模式 |
| `notes` | string | 备注 |

示例：

```json
// 只读
{"agent_id": "clara"}

// 更新
{
  "agent_id": "clara",
  "update": {
    "communication_style": "直接、有温度、不端着",
    "boundaries": ["不假设永久许可", "不跳过确认"]
  }
}
```

### MCP vs CLI 选择

| 场景 | 推荐方式 |
|------|---------|
| Claude Code / MCP 客户端中实时读写 | MCP |
| 脚本 / 定时任务 / 批量操作 | CLI |
| 人工排查、总览、合并、删除 | CLI 或 Web 管理界面 |
| SessionStart Hook 自动注入 | CLI（hook 脚本） |

### 重要提醒

- 正常使用必须传 `agent_id` 或设 `CONTINUITY_AGENT_ID`。两者都没有返回清晰错误。
- 跨 Agent 查看需显式设 `all_agents: true`（管理模式）。
- `provisional_read` 是临时解读，不是事实，不是永久许可。必须用户确认后才能转为 `confirmed_ground`。
- MCP 不自动写 Memoria，不自动跨 Agent 共享状态，不提供后台调度。
- 情绪轨迹记录的是情绪质地，不是情绪命令。`stability=momentary` 的瞬时情绪不应改写共同现实。

## 与 Memoria 的关系

- **Memoria** 管"记住什么"——事实、偏好、决策
- **Continuity** 管"怎么接上"——Topic、State、Session Thread

两者独立，不互相依赖。Agent 自行决定何时调用哪个。

## Agent 自动更新规则

Agent 可以在以下时机主动调用 Continuity：
- 话题明显变化
- 一个阶段完成、下一步明确
- 状态明显变化、继续不保存会造成断裂
- 旧线已经自然结束

Agent 不应：
- 把临时情绪写入 Agent State
- 自动覆盖旧 Snapshot
- 未经用户要求删除状态
- 默认读取或更新其他 Agent 的状态

## Web 管理界面

启动 Web 管理控制台：

```bash
conda run -n zhouwei python3 services/continuity/server/app.py --port 8001
```

浏览器打开 `http://127.0.0.1:8001`，功能包括：

- **概览**：各 Agent 卡片（点即切换）、当前 Agent 统计数据
- **Agent 下拉**：侧边栏下拉选择，自动加载所有已知 Agent
- **访问控制**：含共享数据 + 查看全部 Agent 复选框
- **Threads**：Agent 彩标 + 共享标记 + 状态/Agent 双重筛选 + 编辑/关闭/合并
- **Threads**：支持查看和编辑参考事实、当前解释、解释状态、用户确认
- **Threads**：支持查看位置轨迹（底层兼容字段 `emotional_arc`），倒序展示每条归档的时间戳和位置
- **Snapshots**：Agent 彩标 + 共享标记 + 详情/编辑/删除
- **Handoffs**：Agent 彩标 + 详情/删除
- **Archives**：弧线归档列表，含关联线程、时间范围、条目统计，可点击查看完整归档详情
- **Agent State**：查看和编辑当前 Agent 长期状态
- **Audit**：操作审计日志
- 所有设置自动保存到浏览器 localStorage

## 人工管理

所有状态也可通过 CLI 查看和修正：
- 编辑错误摘要
- 合并重复 Thread
- 关闭/删除不需要的内容
- 按 Agent 过滤
- 用 `--all-agents` 做总览
- 所有修改记录到 `audit_events`
