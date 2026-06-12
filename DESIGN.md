# Continuity v1 Design

Continuity v1 是 ClaraCore 里的小型状态续接系统。

它解决的问题不是“记住过去发生过什么”，而是“新 Session 开始时，Agent 应该从
哪里、以什么状态继续”。

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

Memoria 负责记忆。Agent 自己决定什么时候读记忆、写记忆。

Continuity 负责状态续接。它保存和组装的是当前应该怎么继续，而不是长期事实库。

Continuity 不依赖 Memoria 才能工作。Agent 如果需要，也可以在使用 Continuity
Packet 前后自行调用 Memoria。

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
- `source_session`

多条线可以同时存在。比如工程讨论、陪伴聊天、长期规划、代码调试，都可以是不同
的 Session Thread。

`visibility` 默认为 `private`。只有标记为 `shared` 的线，才允许其他 Agent 在
显式请求 shared 状态时看到。

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

第一版不做：

- 全量对话自动导入
- 单一全局当前状态
- 自动跨 Session 情绪合并
- 复杂冲突解决
- 后台守护进程
- 复杂桌面 UI
- 大型 Agent 编排

第一版先证明：明确的多 Session 路由和状态保存，确实能改善续接质量。
