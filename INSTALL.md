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

测试时可以指向临时目录：

```bash
CONTINUITY_ROOT=/tmp/continuity-test conda run -n zhouwei python3 skills/continuity/cli.py init
```

## 卸载

```bash
rm -rf ~/.claracore/continuity/
```

不会修改仓库外的任何其他位置。
