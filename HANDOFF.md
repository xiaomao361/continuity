# Handoff

Handoff 是给未来 Session 或另一个 Agent 的接力棒。

它应该是可执行的，不是叙事复盘。接手方应该能知道下一步怎么继续，而不需要重读整段对话。

## Template

```text
Objective
- ...

Repository / Workspace
- path:
- branch:
- important dirty changes:

Completed
- ...

Verified
- command:
- result:

Current Decision
- ...

Do Not Touch
- ...

Risks / Open Questions
- ...

Next Action
- ...
```

## Rules

- 优先写准确路径，不写模糊引用。
- 只有命令输出会影响下一步判断时，才摘录关键结果。
- 已验证事实和假设要分开。
- 用户已有的未提交改动要明确写出来。
- 不写 Agent 私有人格文件或私有记忆内容。
- 不负责 Memoria 的读取或写入；如果 Agent 自行用了记忆系统，只在必要时说明“使用过外部记忆”，不要把原始内容塞进 Handoff。

## Completion

Handoff 完成后，只更新 Continuity 里的 Thread / Snapshot / Handoff 状态。

是否读写 Memoria 由 Agent 自己决定，不属于 Continuity 的职责。
