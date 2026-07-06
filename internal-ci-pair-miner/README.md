# codehubswarm (internal-ci-pair-miner)

Cursor Agent Skill：从**内网 CodeHub**（GitLab、Gitea、Jenkins 等）挖掘 **fail→pass** CI 修复案例，**优先稳定性相关**，生成含 **修改前/后代码、diff、问题描述、分类** 的 **SQLite 修复知识库**，供其他 Agent 做稳定性代码修复。

流程借鉴 [BugSwarm](https://github.com/BugSwarm/bugswarm)，但面向内网平台并输出可查询数据库。

## 功能

- **Find → Filter → Enrich → Classify → Load DB** 流水线
- **P0 稳定性优先**（并发、超时、泄漏、网络容错等）；可选收录一般缺陷修复
- 每条案例：`code_before` / `code_after` / `unified_diff` / `problem_description` / `stability_category`
- 默认 SQLite：`pair-miner/data/stability_repair.db`
- `run_query.sh` 供下游修复 Agent 按类别、关键词检索历史修复

## 安装（Cursor）

```powershell
git clone https://github.com/Steven-T-2005/codehubswarm.git `
  "$env:USERPROFILE\.cursor\skills\internal-ci-pair-miner"
```

Linux / WSL：

```bash
git clone https://github.com/Steven-T-2005/codehubswarm.git \
  ~/.cursor/skills/internal-ci-pair-miner
```

重启 Cursor 或在对话中说：**「使用 internal-ci-pair-miner skill」**。

## 使用

1. 复制 `config.sample.yaml` → `pair-miner/config/codehub.yaml`（勿提交含 token 的文件）
2. 设置 `export CODEHUB_TOKEN=...`
3. 对 Agent 说：

```text
使用 internal-ci-pair-miner skill，从内网 CodeHub 仓库 group/project 挖掘稳定性相关的 fail→pass 修复案例，
生成 stability_repair.db，包含修改前后代码、diff、问题描述和 stability_category。
CodeHub 类型：GitLab，API：https://codehub.corp.internal
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `SKILL.md` | Agent 主指令（挖矿 + 建库 + 查询接口） |
| `config.sample.yaml` | 内网 API、稳定性关键词、数据库配置 |
| `pair-schema.json` | 修复案例 JSON schema（含 code_changes） |
| `reference.md` | 数据模型、DB 表、平台适配、分类 taxonomy |

## 与 BugSwarm 的区别

| BugSwarm | 本 Skill |
|----------|----------|
| 仅 GitHub + Travis/GHA | 内网 CodeHub 可配置 |
| JSON + MongoDB | **SQLite 修复知识库**（默认） |
| 通用缺陷 | **稳定性优先** + 一般缺陷可选 |
| 无 before/after 全文 | **per-file code_before / code_after** |
| 无下游查询契约 | **run_query.sh** 供修复 Agent 使用 |

## License

MIT
