# 会话交接

> 上一轮：2026-06-05。**F17 公网面试 Demo 模式**完成：`DEMO_MODE` 强制合成数据、数据导入页只读架构说明、公开样本数据清理、README/Secrets 模板更新。

## 当前已验证

- `bash init.sh` → 通过；当前公开样本 CSV=1，运营 CSV=0。脚本仍提示系统 Python 3.9.6 下依赖安装部分失败，这是既有本机环境问题；本轮验证使用 Codex bundled Python 3.12。
- `python -m pytest tests/ -q` → **69 passed**。
- `DEMO_MODE=true python -m pytest tests/ -q` → **69 passed**。
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
