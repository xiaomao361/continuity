# Continuity v1 安装

## 依赖

- Python 3.10+
- SQLite3（Python 内置，无需额外安装）
- FastAPI + Uvicorn（Web 管理界面需要）
- ClaraCore 仓库

安装 Web 依赖：

```bash
conda run -n zhouwei pip install fastapi uvicorn
```

## 安装步骤

```bash
# 确认在 ClaraCore 目录
cd ~/Documents/ClaraCore

# 验证 CLI 可运行
conda run -n zhouwei python3 skills/continuity/cli.py --help

# 初始化 Continuity 数据库
conda run -n zhouwei python3 skills/continuity/cli.py init
```

初始化后在 `~/.claracore/continuity/` 创建 `continuity.db`。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CONTINUITY_ROOT` | 数据库目录 | `~/.claracore/continuity/` |
| `CONTINUITY_AGENT_ID` | Agent 命名空间 | `default` |

每个 Agent 用不同 `CONTINUITY_AGENT_ID` 隔离数据（如 `clara`、`lara`、`codex`）。
Agent State 按 `agent_id` 分别存储，Thread/Snapshot/Handoff 默认只读自己的数据。

测试时可以指向临时目录：

```bash
CONTINUITY_ROOT=/tmp/continuity-test CONTINUITY_AGENT_ID=test conda run -n zhouwei python3 skills/continuity/cli.py init
```

## SessionStart Hook（可选）

自动注入当前 Agent 的 Thread 列表到 Claude Code 上下文：

```json
// ~/.claude/settings.json
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

Hook 脚本在 ClaraCore 已配置，其他 Agent 按需添加。

## 卸载

```bash
rm -rf ~/.claracore/continuity/
```

不会修改仓库外的任何其他位置。
