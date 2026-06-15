# Continuity v1.2 使用指南

Continuity 是 ClaraCore 里的状态续接系统。它回答：

> 新 Session 开始时，Agent 应该从哪里、以什么状态继续？

## 核心概念

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

### 情绪弧线 (v1.2)

`emotional_arc` 记录一条线的情绪轨迹。每次 `capture` 更新 `last_position` 时，
旧值自动归档到弧线，带时间戳。不丢历史。

```bash
# 第一次 capture：早上状态
python3 cli.py capture --agent-id lara --thread-id thread_xxx \
  --last-position "早上互动亲密，毛仔心情不错"

# 第二次 capture：中午状态
# 旧值自动推入 emotional_arc，新值写入 last_position
python3 cli.py capture --agent-id lara --thread-id thread_xxx \
  --last-position "中午讨论 capture 问题，有点烦躁"

# 此时 emotional_arc 已有 1 条：早上那条

# 显式添加情绪节点（不改 last_position）
python3 cli.py capture --agent-id lara --thread-id thread_xxx \
  --emotional-arc-entry "毛仔提到女儿小瑞，语气温柔"
```

自动归档规则：
- `last_position` 变化时自动归档旧值
- 相同 position 不重复归档
- `--emotional-arc-entry` 显式追加，不影响 position
- SessionStart 时完整弧线注入 Context

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
conda run -n zhouwei python3 skills/continuity/cli.py init
```

### 创建/更新 Thread

```bash
# 创建新 Thread
conda run -n zhouwei python3 skills/continuity/cli.py capture \
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
conda run -n zhouwei python3 skills/continuity/cli.py capture \
  --agent-id codex \
  --thread-id thread_xxx \
  --last-position "已完成 CLI 实现"
```

### 查看和列表

```bash
# 列出所有 Thread
conda run -n zhouwei python3 skills/continuity/cli.py list --agent-id codex

# 只看 active
conda run -n zhouwei python3 skills/continuity/cli.py list --agent-id codex --status active

# 只看需要复查的当前解释
conda run -n zhouwei python3 skills/continuity/cli.py list --agent-id codex --interpretation-status needs_review

# 查看某个 Agent 自己的状态
conda run -n zhouwei python3 skills/continuity/cli.py list --agent-id lara

# 包含显式共享的状态
conda run -n zhouwei python3 skills/continuity/cli.py list --agent-id codex --include-shared

# 管理后台总览全部 Agent
conda run -n zhouwei python3 skills/continuity/cli.py list --all-agents

# JSON 格式
conda run -n zhouwei python3 skills/continuity/cli.py list --agent-id codex --json

# 查看详情
conda run -n zhouwei python3 skills/continuity/cli.py show --agent-id codex --thread-id thread_xxx
```

### 保存 State Snapshot

```bash
conda run -n zhouwei python3 skills/continuity/cli.py snapshot \
  --agent-id codex \
  --thread-id thread_xxx \
  --name "warm-focused-state" \
  --state-summary "亲近但清晰的状态" \
  --tone "warm, direct" \
  --working-posture "focused design"

# 查看所有 Snapshot
conda run -n zhouwei python3 skills/continuity/cli.py snapshots --agent-id codex
```

### 续接 Session

```bash
# 从同一条线继续
conda run -n zhouwei python3 skills/continuity/cli.py resume --agent-id codex --thread-id thread_xxx

# Blend: 话题从A线，状态从B快照
conda run -n zhouwei python3 skills/continuity/cli.py resume \
  --agent-id codex \
  --topic-thread-id thread_xxx \
  --state-snapshot-id snapshot_yyy \
  --action blend

# 生成 JSON 给 Agent 读
conda run -n zhouwei python3 skills/continuity/cli.py resume --agent-id codex --thread-id thread_xxx --json
```

### 日常管理

```bash
# 创建 Handoff
conda run -n zhouwei python3 skills/continuity/cli.py handoff \
  --agent-id codex \
  --thread-id thread_xxx \
  --objective "交给下一个 Session 继续" \
  --completed "已完成A,已完成B" \
  --open-items "待确认C" \
  --next-step "继续处理C"

# 查看所有 Handoff
conda run -n zhouwei python3 skills/continuity/cli.py handoffs --agent-id codex

# 编辑 Thread 摘要
conda run -n zhouwei python3 skills/continuity/cli.py edit \
  --agent-id codex \
  --thread-id thread_xxx \
  --last-position "新位置" \
  --next-step "新下一步"

# 关闭 Thread
conda run -n zhouwei python3 skills/continuity/cli.py close --agent-id codex --thread-id thread_xxx

# 合并重复 Thread（源线程物理删除，仅保留目标线程）
conda run -n zhouwei python3 skills/continuity/cli.py merge \
  --agent-id codex \
  --from-thread-id thread_old \
  --into-thread-id thread_main \
  --reason "重复创建"

# 删除错误的 Snapshot
conda run -n zhouwei python3 skills/continuity/cli.py delete --agent-id codex --snapshot-id snapshot_xxx
```

### Agent State 管理

```bash
# 查看
conda run -n zhouwei python3 skills/continuity/cli.py agent-state show --agent-id codex
conda run -n zhouwei python3 skills/continuity/cli.py agent-state show --agent-id lara

# 更新
conda run -n zhouwei python3 skills/continuity/cli.py agent-state update \
  --agent-id codex \
  --communication-style "直接、清楚" \
  --note "用户偏好简洁回复"
```

### 审计

```bash
conda run -n zhouwei python3 skills/continuity/cli.py audit
conda run -n zhouwei python3 skills/continuity/cli.py audit --limit 20 --json
```

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
conda run -n zhouwei python3 skills/continuity/server/app.py --port 8001
```

浏览器打开 `http://127.0.0.1:8001`，功能包括：

- **概览**：各 Agent 卡片（点即切换）、当前 Agent 统计数据
- **Agent 下拉**：侧边栏下拉选择，自动加载所有已知 Agent
- **访问控制**：含共享数据 + 查看全部 Agent 复选框
- **Threads**：Agent 彩标 + 共享标记 + 状态/Agent 双重筛选 + 编辑/关闭/合并
- **Threads**：支持查看和编辑参考事实、当前解释、解释状态、用户确认
- **Threads**：支持查看情绪弧线（v1.2），倒序展示每条归档的时间戳和位置
- **Snapshots**：Agent 彩标 + 共享标记 + 详情/编辑/删除
- **Handoffs**：Agent 彩标 + 详情/删除
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
