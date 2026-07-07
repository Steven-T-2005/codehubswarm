# codehubswarm — CodeHub Stability Fix Miner

Cursor Agent Skill：**clone 即用**，从 **内网 CodeHub MR/CR** 抓取稳定性相关代码修复，写入 skill 目录内的 `data/dfr_repair.db`。

## 目录结构

```
internal-ci-pair-miner/
├── SKILL.md                 # Agent 指令
├── config.sample.yaml       # 配置模板
├── run_fetch_crs.sh         # 抓取
├── run_query.sh             # 查询
├── scripts/
│   ├── fetch_codehub_crs.py
│   └── query_db.py
├── data/                    # 数据库（运行后生成）
└── output/codehub/          # JSON 导出（运行后生成）
```

## 安装

```powershell
git clone https://github.com/Steven-T-2005/codehubswarm.git `
  "$env:USERPROFILE\.cursor\skills\internal-ci-pair-miner"
```

Linux / WSL：

```bash
git clone https://github.com/Steven-T-2005/codehubswarm.git \
  ~/.cursor/skills/internal-ci-pair-miner
```

**依赖**：Python 3.8+，无需 pip 安装额外包。

## 使用

```bash
cd ~/.cursor/skills/internal-ci-pair-miner   # 或你的 clone 路径

export CODEHUB_TOKEN='...'
export CODEHUB_PROJECT='OpenSourceCenter_CR/openharmony/filemanagement_app_file_service'

chmod +x run_fetch_crs.sh run_query.sh
./run_fetch_crs.sh
```

查询：

```bash
./run_query.sh --stability-class jserror
./run_query.sh --case-id <id> --format json
```

## 稳定性类别

`appfreeze` | `jserror` | `jsleak` | `memoryleak`（默认抓取这四类）

## 对 Agent 说

```text
使用 internal-ci-pair-miner skill，从 CodeHub 抓取稳定性 MR，
运行 run_fetch_crs.sh，生成 data/dfr_repair.db。
```

## License

MIT
