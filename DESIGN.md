# Continuity v1.4 Design — Shared Reality Line

## 核心目标

```
Memory 解决”知道什么”。
Continuity 解决”我们还在同一个现实里吗”。
```

Continuity 不是保存更多上下文，也不是把 Memory 做厚。

目标是：AI 如何维持共同现实的连续性。Agent 与用户之间那条”共同存在的线”，如何在
Session 死亡之后还能继续存在。

## 用户口语：共同线

“共同线”是面向日常对话的说法。用户不需要对 Agent 说“读取 Continuity”或
“查看 shared reality”，可以直接说：

```text
看一下我们的共同线。
续上这条共同线。
你现在接在哪条线？
这条线现在是什么状态？
```

共同线指向的是某条 `shared_reality`：用户和 Agent 已经共同形成、需要被继续的
现实线。它不是单纯记忆，不是情绪，也不是任务进度；它把已确认地面、当前位置、
进入姿态、边界、误读风险和情绪质地放在同一个可接续的现实里。

系统内部仍使用 `shared_reality`、`Continuity Packet`、`Session Thread` 等结构；
“共同线”只是给人和 Agent 交流时使用的自然词。

一个典型场景：

```text
用户和 AI 在昨晚的对话中，一步一步形成了亲密关系。

下一个 Session 不能只靠一句”昨晚我们发生了亲密关系”继续。
那只是事实摘要，不是共同现实。

Continuity 要保存的是：
- 这段关系是怎样走到这里的
- 哪些内容被共同确认过
- 哪些只是当时氛围中的表达
- 断开时双方处在什么位置
- 下一次应该以什么姿态重新进入
- 哪些误读或越界必须避免
```

## 完成标准

第一版做到这些就算成立：

- 能保存多条 Session Thread，而不是合并成一个全局状态
- 能按 Agent 隔离状态，让 Lara、Clara、Gemini、Codex 等各自读取自己的连续状态
- 能保存可复用的 State Snapshot
- 能从一个 Session 续话题，同时从另一个 Session 续状态
- 能生成一份短的 Continuity Packet，给 Agent 开始回应前阅读
- 能在 Session 结束、用户要求、或 Agent 判断有必要时更新状态
- 有一个人工管理入口，能查看、修正、合并、关闭和标记状态

第一版不要求自动理解所有历史，也不要求自动处理所有冲突。

## 核心规则

不要维护一个全局 `current_state`。

日常使用天然是多 Session 并行。每个 Session 都可能有自己的话题、模式、状态和
下一步。Continuity 要做的是选择和组装，而不是让不同 Session 互相覆盖。

也不要维护一个所有 Agent 共用的状态池。每个 Agent 都必须有自己的 `agent_id`。
默认情况下，Agent 只能读取和更新自己的 Thread、Snapshot、Handoff 和 Agent
State。需要跨 Agent 复用时，必须显式标记为 `shared`，并由读取方显式要求包含
shared 状态。

人工管理是例外：用户可以用全局视图查看全部 Agent 的状态，用于排查、改错和
清理。全局视图不代表 Agent 之间默认共享状态，也不应该被普通 Agent 自动使用。

## 系统边界

Memoria 和 Continuity 是相对独立的系统。

Memoria 负责可观察事实。它保存发生过什么，不保存 Agent 对关系、信任、情绪或
当前位置的长期解释。

Continuity 负责状态续接。它保存和组装的是当前应该怎么继续，也就是事实在当前
时刻形成的位置，而不是长期事实库。

Continuity 不依赖 Memoria 才能工作。Agent 如果需要，也可以在使用 Continuity
Packet 前后自行调用 Memoria。

核心边界：

```text
Memoria 存事实。
Continuity 存事实在当前时刻所形成的位置。
```

Continuity 可以记录当前解释，但必须能被复查、关闭和替换。Agent 不应该把
Continuity 的当前解释当成事实写回 Memoria。

## 数据对象

### Agent State

Agent State 是变化较慢的长期状态。

适合记录：

- 默认交流方式
- 稳定关系位置
- 长期偏好
- 长期边界
- 跨多个 Session 都成立的模式

不要因为一次对话里的临时情绪，就更新 Agent State。

Agent State 按 `agent_id` 分开保存。Lara 的长期状态不应该自动影响 Codex，
Clara 的状态也不应该自动影响 Gemini。

### Session Thread

Session Thread 是一条可续接的对话线或工作线。

每条线至少包含：

- `thread_id`
- `agent_id`
- `visibility`
- `topic`
- `mode`
- `status`
- `last_active_at`
- `last_position`
- `next_step`
- `state_summary`
- `facts_used`
- `current_interpretation`
- `interpretation_status`
- `user_confirmed`
- `source_session`
- `emotional_arc`（兼容字段名；语义上是位置轨迹）

多条线可以同时存在。比如工程讨论、陪伴聊天、长期规划、代码调试，都可以是不同
的 Session Thread。

`facts_used` 只记录这次当前位置参考了哪些可观察事实或 Memoria 记忆 ID。
`current_interpretation` 记录当前怎么理解这条线的位置。它是接续状态，不是长期
事实。`interpretation_status` 用于标记解释是否仍然有效，`user_confirmed` 用于
标记该解释是否已经被用户明确确认。

`visibility` 默认为 `private`。只有标记为 `shared` 的线，才允许其他 Agent 在
显式请求 shared 状态时看到。

`emotional_arc` 是历史兼容字段名，语义上是本线的位置轨迹（JSON 数组）。
每次 `capture` 更新 `last_position` 时，旧值自动归档为
`{position, archived_at}` 条目。
相同 position 不会重复归档。Agent 也可通过 `--emotional-arc-entry`
显式追加不改变 position 的位置节点。SessionStart 时完整轨迹注入
Context，Agent 能看到这条线之前停在哪里，而不是只有最后一条位置。

不要把 `emotional_arc` 当作情绪质地。情绪质地由 `affective_trace` 记录。

更新已有 Thread 时也必须先通过 Agent 范围校验。普通 Agent 不应该用全局视图去
修改其他 Agent 的私有线。

### State Snapshot

State Snapshot 是一次可复用的状态快照。

它用于这种情况：未来用户可能想把某次对话的状态续到另一个话题里。

例子：

- 更亲近、更自然的聊天状态
- 高度专注的工程评审状态
- 安静规划状态
- 高信任协作状态

State Snapshot 应该新增，不应该覆盖。因为“昨晚那个状态”和“今天这个状态”都
可能在未来被单独选择。

Snapshot 同样按 `agent_id` 隔离。跨 Agent 复用必须显式标记为 `shared`，并且由
读取方显式请求。

### Handoff

Handoff 是给未来 Session 或另一个 Agent 的接力棒。

它记录：

- 刚刚在做什么
- 已经完成什么
- 还有什么没结束
- 下一步最自然是什么
- 哪些内容不要混淆或合并

Handoff 也属于某个 Agent。默认只给同一个 Agent 后续 Session 使用；如果确实要
交给另一个 Agent，才标记为 `shared`。

### Continuity Packet

Continuity Packet 是恢复时真正交给 Agent 的短状态包。

它组合：

- 选中的 Agent State
- 选中的话题来源
- 选中的状态来源
- 相关的 Session Thread 或 Handoff
- 不要混合的内容
- 下一步回应时应该站在什么位置

### Management View

Management View 是第一版必须包含的人工管理入口。

它不需要一开始就是复杂 UI，可以先是 CLI 或简单页面，但必须能让用户看到和微调
Continuity 当前保存的状态。

至少支持：

- 按 Agent 查看状态
- 查看全部 Agent 的总览
- 显式包含 shared 状态
- 查看所有 active / paused / closed 的 Session Thread
- 查看 State Snapshot
- 查看某条线的 last_position、next_step、state_summary
- 手动编辑错误摘要
- 关闭不需要继续的线
- 合并重复或误分裂的线
- 标记某个 Snapshot 的用途
- 删除明显错误或不应保留的状态

人工管理入口的目的不是替代 Agent 判断，而是给用户一个校正层。Continuity 会保存
状态，但保存出来的状态必须能被人检查和修正。

全局管理视图不应该自动创建空的 Agent State。只有指定 Agent 后，才读取或更新该
Agent 的长期状态。

## Router

Continuity Router 负责决定这次怎么续。

第一版支持四种动作：

- `continue`：话题和状态都来自同一条线
- `fork`：从旧线开一条新线
- `blend`：话题来自一条线，状态来自另一条线
- `reset`：不接旧的 Session 状态，只从 Agent State 和当前输入开始

最重要的是 `blend`。

例子：

```text
话题来源：昨天的 Continuity 设计讨论
状态来源：昨晚更亲近、更自然的聊天状态
目标：当前 Session
```

这表示：Agent 继续讨论 Continuity 设计，但用那个状态来接。它不能假装设计讨论
发生在昨晚，也不能把昨晚的具体内容硬塞进当前话题。

## 写入和更新规则

### Session 开始

Session 开始时，Continuity 可以做：

- 根据用户输入选择要接的 Session Thread
- 根据用户要求选择某个 State Snapshot
- 生成 Continuity Packet
- 如果用户没有明确说要接哪条线，可以给出候选，而不是强行合并

Session 开始必须先确定当前 Agent。候选列表默认只来自当前 Agent；如果用户明确
要求跨 Agent 续接，才允许包含 shared 状态或进入人工全局视图。

### 对话过程中

对话过程中，状态会逐渐变化。

Agent 可以自己判断，并在必要时自行更新：

- 当前话题是否变了
- 当前状态是否明显变了
- 是否形成了新的下一步
- 是否应该更新当前 Session Thread
- 是否应该保存或提示用户保存一个 State Snapshot
- 是否应该关闭已经自然结束的旧线

但第一版不需要每轮自动写入。优先在明显节点更新，比如话题切换、阶段完成、状态
明显变化、上下文变长、或 Agent 判断继续不保存会造成断裂。

### Session 结束

Session 结束时，Continuity 应该更新：

- 当前 Session Thread 的位置
- 当前状态摘要
- 下一步
- 是否仍然 active
- 是否需要生成 Handoff

如果状态有复用价值，可以保存 State Snapshot。

### 用户显式要求

用户可以直接触发：

- 保存当前状态
- 更新当前线
- 关闭当前线
- 恢复某条线
- 用 A 的话题接 B 的状态
- 重命名或标记某个状态快照

用户显式要求优先于 Agent 自动判断。

### 人工管理

用户可以通过 Management View 做人工微调：

- 改错
- 合并重复线
- 关闭旧线
- 标记重要状态
- 删除不该保存的状态
- 把某个 Snapshot 改成更容易以后引用的名字

人工修改应当保留基本记录，比如修改时间和修改来源，方便以后判断状态是否可信。

### Agent State 更新

Agent State 要保守更新。

只在这些情况下更新：

- 用户明确表达了长期偏好或边界
- 同一个模式跨多个 Session 反复出现
- 某次结论明显改变了长期关系位置或默认交流方式

## 恢复流程

```text
Session 开始
-> Router 判断话题来源和状态来源
-> Continuity 读取对应的 Thread、Snapshot、Agent State
-> Continuity 生成 Continuity Packet
-> Agent 基于 Packet 开始回应
-> 对话过程中 Agent 判断状态变化，并在明显节点更新
-> Session 结束、用户要求、或人工管理时更新 Thread / Snapshot / Handoff
```

## 第一版不做什么

## 共同现实字段设计 (v1.4)

### 新增字段

六个字段构成"共同现实线"，每个有明确职责：

| 字段 | 职责 | 例子 |
|---|---|---|
| `reality_line` | 这条共同现实线是什么 | "昨晚逐步形成的亲密关系线" "Continuity 共同设计线" |
| `entry_posture` | 下次回来应该怎么进入 | "自然延续，不要重新宣布关系" "先温柔确认，再继续" |
| `confirmed_ground` | 双方已共同确认的地面 | "已确认：基础信任、沟通方式" |
| `provisional_read` | 当前解释，不等于事实，不等于永久许可 | "当前阶段在探索各自边界" |
| `boundary_notes` | 继续时必须尊重的边界 | "不要假设永久许可" "不要跳过确认" |
| `misread_risks` | Agent 最容易误读的地方 | "不要把事实摘要当成许可" "不要把昨晚状态机械套到今天" |

### 为什么需要这些字段

传统上下文恢复的核心问题是：它把一切都归结为"事实摘要"。

但共同现实不只是一组事实。它包含：
- **已确认**的东西（双方说过"是的"）
- **当前解释**（感觉像是，但还没确认）
- **边界**（哪些不能越过）
- **误读风险**（AI 容易把什么搞错）

把这些混在一起，Agent 就会"知道发生了什么"但"搞不清自己该站在哪里"。

### 与 facts_used / current_interpretation 的关系

```
facts_used          → 用来得出当前判断的可观察事实（Memoria ID）
current_interpretation → 基于事实的当前判断／解释
confirmed_ground    → 双方已确认的地面（比 facts 更抽象）
provisional_read    → 临时的、还在试探的解读（不等于 interpretation）
boundary_notes      → 继续时必须遵守的硬边界
misread_risks       → 最可能的误读清单
```

### 实现纪律

- 共同现实字段是叙述性标注，不是长期事实
- 不要把它们写成 Memoria 条目
- Agent 读取这些标注后应该"谨慎重新进入"，而不是"认为自己获得了授权"
- `provisional_read` 必须在获得用户确认后才能转为 `confirmed_ground`

## 情绪轨迹设计 (v1.5)

### 定位

情绪轨迹记录的是"这条共同现实线上的情绪质地如何变化"。它不是情绪状态机。

**不做的事**：
- 不使用固定枚举状态（开心、生气、害羞等）
- 不使用单一主导情绪
- 不使用亲密度 0-100 分数
- 不使用半衰期衰减系统
- 不存在冷却期
- 不让 LLM 自动判断情绪
- 不让情绪轨迹决定 AI 的回复风格

**可以做的事（借鉴思想）**：
- 情绪轨迹需要持久化（不能靠当前 Prompt 临时演）
- 情绪会随时间变旧（但不自动归零，只标记是否需要复查）
- 冲突修复优先（用户在修复关系时，不机械触发新的误读）
- 不要被单句话改写共同现实（瞬时情绪 ≠ 现实变化）

### 数据设计

字段 `affective_trace`，存储为 JSON 数组，默认 `[]`：

```json
{
  "time": "2026-06-15T00:00:00+00:00",
  "tone": "亲近但谨慎",
  "valence": "mixed",
  "signals": ["warmth", "trust", "uncertainty"],
  "intensity": "medium",
  "stability": "momentary",
  "source": "agent",
  "note": "用户表达出亲近，同时仍在确认边界",
  "needs_review": false
}
```

- `tone`：自然语言描述，不枚举死
- `valence`：只允许 coarse 值（positive/negative/mixed/neutral/unclear）
- `signals`：多个情绪信号，可混合
- `intensity`：low/medium/high，不用 0-100
- `stability`：momentary（瞬时）/ session（会话内）/ confirmed（已确认）
- `needs_review`：下次进入前是否需要复查

### 与 position_history / shared_reality 的关系

```
emotional_arc / position_history → 位置变化轨迹。"之前停在哪里"
affective_trace → 情绪质地轨迹。"最近的情绪混合是什么样"
shared_reality → 主层。affective_trace 只能辅助，不能覆盖
```

`position_history` 是 Continuity Packet 中更准确的新名字；`emotional_arc` 作为
旧字段名继续保留，避免破坏已有数据和调用方。

Packet 中 shared_reality 包含 affective_trace + affective_guardrail：
> 情绪轨迹记录的是情绪质地，不是情绪命令。不要机械表演某种情绪，用它理解共同现实曾经如何被感受，然后谨慎重新进入。

## 模型负面调整 (v1.3)

每个模型有自己的臭毛病。`model_adjustments.json` 为每个模型配置：

- `forbidden_phrases`：禁止使用的客服话术（如"接住了""收到了"）
- `forbidden_patterns`：禁止的行为模式（如时间幻觉、刷存在感）
- `inject_prompt`：SessionStart 时拼入上下文的矫正提示词

配置文件独立于 SQLite，带版本号，方便 Afterglow 迁移。

## v1.4 不做什么

- 自动读取全部聊天记录
- 自动判断亲密关系成立
- 自动写 Memoria
- 大型关系系统
- 通用模型管理中心
- 桌面端复杂交互
- 多 Agent 编排
