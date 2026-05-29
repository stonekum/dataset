# 会话交接

> 上一轮：2026-05-29。Editorial 视觉方案已落到 Streamlit；上一轮 /code-review 找到的 10 个 bug 用户表态"晚点再弄"，未修复。

## 当前已验证

- 视觉系统：编辑式 briefing 风格已生效于 4 个页面（app/运营/汇报/数据导入）
  - 字体：Fraunces + Noto Serif SC + JetBrains Mono（通过 `@import` 引入）
  - 调色：暖米色纸面 + 深墨海军蓝 + 烧土红 + 森林绿 + 暖灰 + 赭石 + 紫
  - 装饰：纸面 SVG 噪点 overlay + 双线规则 + 印章序号 + italic 强调 + 虚线 KPI 分隔
- 数据流：完全未动；`get_active_dataframe` 链路保持不变
- F01-F06、F08、F09：done
- F07：deferred
- F10：in_progress（仍在等用户的 GCP service account 凭据）

## 本轮改动

- 修改：`.streamlit/config.toml`、`utils/ui.py`、`app.py`
- 新增：`design/operations-mockup.html`（上一轮纯 HTML 视觉探索）、
  `.claude/launch.json`（让 Claude Preview 能起 dashboard server）
- 未动：`pages/1_📊_运营视图.py`、`pages/2_📈_汇报视图.py`、`pages/3_📤_数据导入.py`
  — 它们继续用 `inject_page_styles()` + 一套保留的 CSS class 名（`kpi-panel` /
  `kpi-grid` / `kpi-item` / `ki-label/value/delta` / `soft-card`），样式被
  重新着色但 DOM 结构没改

## 仍损坏或未验证

- **上一轮 /code-review 的 10 个 bug 全部未修**（用户明示"晚点再弄"）：
  - `scripts/scheduled_pull.py:111` — `_esc` 不转义换行 → secrets.toml 非法 →
    定时任务静默 no-op（最严重，部署前必须先修）
  - `utils/youtube_api.py:148` / `utils/linkedin_api.py:148` —
    follower_growth 算了被 `_ensure_standard_shape` 丢弃
  - `utils/linkedin_api.py:135` — `A or B + C` 优先级 bug
  - `utils/data_cleaner.py:52` — followers 被负值截零
  - `utils/data_loader.py:295` — 部分日期 NaT 静默丢
  - `utils/data_loader.py:281` — Metricool 未知 Network → platform=''
  - `pages/2_📈_汇报视图.py:185` — 上期为 0 时 delta 显示 0%
  - `pages/3_📤_数据导入.py:595` — Sheets replace 失败不清 confirm token
  - `scripts/scheduled_pull.py:222` — `mode='merge'` 形参待核对
- **真机部署字体回退未验证**：Streamlit Cloud (Linux) 上 Noto Serif SC 与
  Songti SC 的 fallback 行为待真机看一次
- **F10 端到端未跑通**：仍缺 GCP service account 凭据

## 下一步最佳动作

按优先级：

1. **修 `_esc` 换行 bug**（`scripts/scheduled_pull.py:111`）→ 它直接拦住 GitHub
   Actions 的定时拉取，是部署链路上的第一根刺
2. 一起修 follower_growth 被丢、LinkedIn 优先级、`mode='merge'` 三处 API 集成 bug
3. 把 GitHub Repo Secrets 填完（参见
   `~/.claude/projects/.../memory/repo-location.md` 列表）
4. 手动触发一次 Scheduled API Data Pull 看日志确认
5. F10 端到端验证（写回 Sheet → 拉取 Sheet → 切换 caption），把 F10 → done
6. 真机部署后看字体回退是否需要 CSS 微调

可选后续：

- 把运营/汇报视图的 plotly 折线图加上 mockup 里那种"今天"高亮带 + italic 注释
  marker，进一步靠近 mockup chart
- F07 真 PDF（reportlab + plotly+kaleido）

## 命令

- 启动命令：`bash init.sh`
- 验证命令：`.venv/bin/streamlit run app.py --server.headless true`
  - 注意：本地用 uv 创了 `.venv`（Python 3.11.15）才能装 streamlit==1.57.0；
    系统 Python 是 3.9 装不上
- 视觉预览：`.claude/launch.json` 已配置；Claude Preview 直接 `preview_start dashboard` 即可
- AppTest 4 页面：
  `.venv/bin/python -c "from streamlit.testing.v1 import AppTest; [print(p, AppTest.from_file(p, default_timeout=30).run().exception) for p in ['app.py','pages/1_📊_运营视图.py','pages/2_📈_汇报视图.py','pages/3_📤_数据导入.py']]"`
- 重新生成示例数据：`python generate_sample_data.py`
