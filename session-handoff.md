# 会话交接

> 最新一轮：2026-07-13。**F17 review 修复全部验证通过并提交**。过程：定位并修复了
> 阻断两轮会话的权限分类器故障（`~/.claude/settings.json` env 块指向失效中转站
> `ai.prism.uno`，用户手动删除后即时恢复）→ 4 处修复静态复核 + 新增 2 条回归测试
> （首页文案跟随 demo 开关、走真实 AppTest.secrets 路径；架构页统计实取断言）→
> 全套验证：pytest 双模式 71 passed、红-绿闭环、init.sh、headless smoke health=ok
> 4 路由 200、Browser 双模式含真实 secrets.toml AttrDict 路径。F17 状态：done。
> 无遗留 blocker。详见 claude-progress.md Session 006。
>
> 上一轮：2026-07-11。**F17 code review 修复（未验证，下一会话必须先跑测试）**：
> 修了 4 处——(1) `utils/demo.py` 用 `isinstance(x, dict)` 判断 `st.secrets` 区段，
> 但 Streamlit `AttrDict` 是 Mapping 非 dict 子类，导致 `[demo] enabled=true` 走
> Secrets 配置时 demo 模式静默不开启（Cloud 部署主路径！），改用 `Mapping` 判断并
> 加回归测试；(2) `app.py` masthead "Public demo · Synthetic data" 标签与 lead
> standfirst 合成数据文案无条件渲染，生产模式下误标，改为按 `demo_mode` 条件渲染；
> (3) secrets.toml.example 的 `[demo] enabled` 默认从 true 改 false（防生产复制模板
> 被锁进 demo）；(4) pages/3 demo 架构页 540/6/90 硬编码统计改为实取。
> **⚠️ 本轮因权限分类器故障无法执行任何命令，pytest / AppTest / smoke 全部未跑。**
> 下一会话开工第一步：`python -m pytest tests/ -q`（normal + `DEMO_MODE=true`），
> 失败则先修再做别的。改动均未提交。
>
> 上上轮：2026-06-05。**F17 公网面试 Demo 模式**完成：`DEMO_MODE` 强制合成数据、数据导入页只读架构说明、公开样本数据清理、README/Secrets 模板更新。

## 当前已验证

- `bash init.sh` → 通过；当前公开样本 CSV=1，运营 CSV=0。脚本仍提示系统 Python 3.9.6 下依赖安装部分失败，这是既有本机环境问题；本轮验证使用仓库 `.venv`（Python 3.11.15, uv）。
- `.venv/bin/python -m pytest tests/ -q` → **71 passed**（2026-07-13，含 2 条新回归测试）。
- `DEMO_MODE=true .venv/bin/python -m pytest tests/ -q` → **71 passed**。
- 红-绿验证：临时回退 utils/demo.py Mapping→dict，AttrDict 回归 + 首页文案回归两条测试如期失败，恢复后转绿。
- Browser 双模式（2026-07-13）：生产模式首页无合成数据误标、显示「日常运营 · 月度汇报」；真实 `.streamlit/secrets.toml` `[demo] enabled=true`（无环境变量）→ demo 生效，架构页统计 540/6/90 实取（临时 secrets.toml 验证后已删除）。
- `python -m json.tool feature_list.json` → 通过。
- `DEMO_MODE=true streamlit run app.py --server.headless true --server.port 8567` → health `ok`；`/`、`/运营视图`、`/汇报视图`、`/数据导入` 均 HTTP 200。
- Browser 视觉检查：`/数据导入` 显示 `PUBLIC DEMO` / `Synthetic dataset` 只读说明页；app-level file input=0；未出现真实 API 拉取、Sheets 写回、手动提交等动作入口。

## 当前数据边界

- Public demo 开关：环境变量 `DEMO_MODE=true`，或 Streamlit Secrets:

  ```toml
  [demo]
  enabled = true
  ```

- demo 模式下 `get_active_dataframe()` 只返回 `data/samples/demo_all_platforms.csv`，label 为 `"Demo data"`。
- demo 模式不会读取上传 session、本地 `data/*.csv`、Google Sheets、API Secrets 或平台 API。
- `data/samples/` 公开跟踪文件只剩 `.gitkeep` 与 `demo_all_platforms.csv`；`.gitignore` 只允许该 demo CSV 被提交。

## 本轮改动文件

- 新增：`utils/demo.py`
- 改动：`utils/data_sources.py`、`utils/auth.py`、`pages/3_📤_数据导入.py`、`app.py`
- 文档/状态：`README.md`、`.streamlit/secrets.toml.example`、`feature_list.json`、`claude-progress.md`、`session-handoff.md`
- 数据清理：移除已跟踪的 `data/samples/_archive/` 与 `data/samples/april_2026_all_platforms.csv`、`data/samples/april_may_2026_all_platforms.csv`
- 测试：`tests/test_data_pipeline.py` 新增 `TestPublicDemoMode` 4 条，并让旧的 auth/fallback 测试显式运行在非 demo 模式

## 注意事项

- 公网 Streamlit Cloud demo 部署时只需要填 `[demo] enabled=true`；不要填真实 Sheets/API Secrets。
- 生产模式仍保留上传、手动录入、Sheets、API 能力；若用于真实数据，必须设为 Private 并配置 `[auth] password`。
- 系统自带 Python 是 3.9.6，不满足项目 Python 3.10+ 与 pandas 3 要求；本轮测试用 `/Users/aston/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`。

## 常用命令

- 初始化：`bash init.sh`
- 测试：`/Users/aston/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m pytest tests/ -q`
- Demo 测试：`DEMO_MODE=true /Users/aston/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m pytest tests/ -q`
- Demo 启动：`DEMO_MODE=true /Users/aston/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m streamlit run app.py`
