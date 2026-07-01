# internal-ci-pair-miner

Cursor Agent Skill：从**内部 CodeHub**（GitLab、Gitea、Jenkins 等）挖掘 **fail→pass** CI job pairs，流程借鉴 [BugSwarm](https://github.com/BugSwarm/bugswarm)。

## 功能

- Find → Filter → Classify 三阶段流水线（与 BugSwarm Miner 同思路）
- 平台无关：通过 `config/codehub.yaml` 适配 API
- 输出标准化 JSON pair schema
- 不依赖 GitHub / BugSwarm 官方代码

## 安装（Cursor）

### 方式 1：克隆到个人 skills 目录

```bash
git clone https://github.com/<YOUR_USER>/internal-ci-pair-miner.git \
  ~/.cursor/skills/internal-ci-pair-miner
```

Windows（PowerShell）：

```powershell
git clone https://github.com/<YOUR_USER>/internal-ci-pair-miner.git `
  "$env:USERPROFILE\.cursor\skills\internal-ci-pair-miner"
```

### 方式 2：作为项目 skill

```bash
git clone https://github.com/<YOUR_USER>/internal-ci-pair-miner.git \
  your-project/.cursor/skills/internal-ci-pair-miner
```

重启 Cursor 或在对话中说：**「使用 internal-ci-pair-miner skill」**。

## 使用

1. 复制 `config.sample.yaml` 为 `pair-miner/config/codehub.yaml`（勿提交含 token 的文件）
2. 对 agent 说：

```text
使用 internal-ci-pair-miner skill，对内部 CodeHub 仓库 group/project 挖掘 fail-pass pairs。
CodeHub 类型：GitLab，API 地址：https://codehub.internal
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `SKILL.md` | Agent 主指令 |
| `config.sample.yaml` | CodeHub / CI API 配置模板 |
| `pair-schema.json` | 输出 pair JSON schema |
| `reference.md` | GitLab/Jenkins 适配参考 |

## 与 BugSwarm 的区别

| BugSwarm | 本 Skill |
|----------|----------|
| 仅 GitHub + Travis/GHA | 可配置任意 CodeHub |
| 完整实现 | 指导 Agent 实现/适配 |
| 含 Reproducer | 挖矿为主，复现可选 |

## License

MIT
