# Context Pack

Context Pack 是继续一个 Session 前需要读取的最小状态包。

它应该足够短，能让 Agent 在行动前快速进入状态；也要足够具体，避免重新发现已经确定的事情。

## When To Create One

在这些情况下创建：

- 任务跨多个 Session
- 上下文接近上限
- 另一个 Agent 要继续
- 项目暂停后未来可能恢复
- 用户要求保存或续接某个状态
- 需要把一个 Session 的话题和另一个 Session 的状态组合起来

普通短任务不需要创建。

## Inputs

只使用相关输入：

- 当前用户目标
- 选中的 Session Thread
- 选中的 State Snapshot
- Agent State
- 上一个 Handoff，如果有
- 当前工作区、路径、分支、重要改动
- 已知阻碍或用户决定

## Shape

```text
Goal
- The current objective in one or two sentences.

Current State
- What is already done.
- What is verified.
- What remains open.

Working Context
- Files, commands, decisions, and constraints needed for the next step.

Boundaries
- What should not be changed.
- User-owned or unrelated dirty worktree changes.
- Agent-private areas that should stay private.

Next Step
- The next concrete action.
```

## Boundary

Context Pack 属于 Continuity。它只负责“这次怎么接上”。

它不负责 Memoria 的读取或写入。Agent 如果需要外部记忆，可以在使用 Continuity Packet 前后自行调用 Memoria。

## Writeback

Context Pack 使用后，可以更新 Continuity 中的：

- Session Thread
- State Snapshot
- Handoff
- Agent State

不要把临时聊天、完整原文或一次性情绪写成长期状态。
