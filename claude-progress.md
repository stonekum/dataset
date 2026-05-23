# 进度日志

## 当前已验证状态

- 仓库根目录：social-media-dashboard/
- 标准启动路径：`bash init.sh`
- 标准验证路径：`streamlit run app.py --server.headless true`
- 当前最高优先级未完成功能：**全部 F01-F10 已完成**（F07 PDF 为 deferred 降级方案）
- 当前 blocker：无

## 会话记录

### Session 002 — F10 Google Sheets 框架（in_progress）

- 日期：2026-05-22
- 背景：用户已开好 Google Sheet，但 Google Cloud service account 还要等 payment method 处理；先把代码框架做完，等凭据到位填 Secrets 即可上线
- 已完成：
  - `utils/data_sources.py` 全面实装 `GoogleSheetsSource`：
    - `_client()` / `_open_worksheet()`：从 `st.secrets["gsheets"]` 读 `spreadsheet_url`（或 `spreadsheet_id`）+ `worksheet_name`（可选）+ `service_account` dict；用 `google.oauth2.service_account.Credentials.from_service_account_info` + `gspread.authorize` 建立连接
    - `load()`：读 worksheet 全部行，通过 `_ensure_standard_shape` 映射到标准列（Sheet 表头约定使用标准列名）
    - `write(df)`：把 DataFrame 整表替换写回（清表 → 写表头 → 写值；日期 ISO 化、NaN → 空串）
    - `is_gsheets_configured()`：UI 判断是否显示同步入口
    - `_try_load_gsheets()`：用 `BaseException` 兜底（含 cryptography 的 Rust `PanicException` 这类非 Exception 异常），失败回落本地 CSV 并显示 warning
  - 数据源优先级链更新为：**上传 > Google Sheets（若配置）> 本地 data/ > 本地 data/samples/**
  - `pages/3_📤_数据导入.py` 新增 "☁️ Google Sheets 同步" 区块：
    - 未配置 secrets 时：显示 info + "如何启用" expander（4 步设置指引）
    - 已配置 secrets 时：显示 "⬆️ 写回 Sheets" + "🔄 拉取最新" 两个按钮
  - `requirements.txt` 新增 `gspread==6.2.1`、`google-auth==2.53.0`
  - 新增 `.streamlit/secrets.toml.example`：完整凭据模板（已 gitignore 实际 `secrets.toml`）
  - `README.md` 新增 "Google Sheets 持久化（可选，F10）" 章节
- 运行过的验证：
  - AppTest 未配置：上传页 info "尚未配置 Google Sheets 凭据"；其他三页正常
  - AppTest 配置假凭据（structurally valid but invalid private_key）：上传页显示 2 个同步按钮；运营视图 `_try_load_gsheets` 触发 cryptography PanicException → `BaseException` 捕获 → warning "已回落到本地数据" → source caption 仍为 "本地 CSV (data/samples)"，无 exception
  - `streamlit run app.py` 四个路由全 HTTP 200，日志无 error
- 待用户处理：在 Google Cloud Console 完成 payment method + service account 创建（创建项目/API/账号均免费），把 JSON 内容填进 `.streamlit/secrets.toml`（或 Streamlit Cloud Secrets）

### Session 001 — F09 Streamlit 上传入口 + 数据源抽象层

- 日期：2026-05-22
- 背景：Metricool 报告需付费；用户决定先做 Streamlit 上传入口让运营同事无需碰仓库即可使用，同时把数据来源抽象出来为下一步 Google Sheets 持久化铺路
- 已完成：
  - 重构 `utils/data_loader.py`：`load_csv` 现在接受 `str | Path | IO[bytes|str]`（对 Streamlit `UploadedFile` 透明），新增 `load_uploaded_files()` 处理多文件 + 去重合并
  - 新增 `utils/data_sources.py`：定义 `DataSource` 协议 + 三个实现（`LocalCSVSource` / `UploadedFilesSource` / `GoogleSheetsSource` 占位）；统一入口 `get_active_dataframe()` 按"上传 > 本地 data/ > 本地 data/samples > 未来 gsheet"优先级解析；clean → enrich 经过 `@st.cache_data` 缓存（用 fingerprint 做缓存键）
  - 新增 `pages/3_📤_数据导入.py`：拖拽上传 + 当前数据状态卡（行数/平台数/日期范围）+ 支持格式说明 + 一键清除回落 + F10 路线说明
  - 改写 `pages/1_📊_运营视图.py` 和 `pages/2_📈_汇报视图.py`：用 `get_active_dataframe()` 替换原本 hardcoded 的 `load_all_data('data/samples')`；在页面顶部显示数据源标签
- 运行过的验证：
  - 4 个文件 + utils 模块全部 `python -m py_compile` 通过
  - AppTest 默认状态：三个页面都无 exception；运营/汇报视图 caption 显示 "本地 CSV (data/samples)"
  - AppTest 注入 session_state 上传数据：caption 切换为 "本次上传"，运营视图 metric 数从 24（6 平台）降到 4（1 平台），证明数据源切换驱动了所有下游
  - 上传逻辑独立测试：构造 FakeUpload(file-like + .name) 跑 `load_uploaded_files` 上传 3 个平台 → 270 行合并、平台识别正确；不可识别表头的坏文件被跳过并发出中文警告
  - 端到端：`streamlit run app.py` 四个路由（`/` `/运营视图` `/汇报视图` `/数据导入`）全 HTTP 200，日志无 error
- 提交记录：见 git log
- 更新过的文件：
  - 新增：`utils/data_sources.py`、`pages/3_📤_数据导入.py`
  - 改：`utils/data_loader.py`（load_csv 接受 IO + 新增 load_uploaded_files）、`pages/1_📊_运营视图.py`、`pages/2_📈_汇报视图.py`、`feature_list.json`（新增 F09 done + F10 not_started）、本文件
- 已知风险/未解决：
  - 上传数据当前仅在 session 内存（Streamlit 默认行为），刷新即丢；这是有意为之，跨 session 持久化留给 F10
  - GoogleSheetsSource 是占位类，调用 `.load()` 会抛 `NotImplementedError`，但优先级链中只有显式启用才会调用它
  - 上传页用 FakeUpload 测过 `load_uploaded_files`，但实际 `st.file_uploader` 的 `UploadedFile` 接口在某些边缘场景下行为可能不同；真实运营使用前建议人工跑一次端到端
- 下一步最佳动作：实现 F10 GoogleSheetsSource（gspread + service account + Streamlit Secrets），让团队能跨 session 共享数据；同时考虑给上传入口加"同步到 Sheets"勾选项

### Session 001 — F08 Streamlit Cloud 部署配置

- 日期：2026-05-22
- 本轮目标：完成 F08
- 已完成：
  - 把 `requirements.txt` 从 `>=` 改为 `==` 精确锁定：streamlit==1.57.0、pandas==3.0.3、plotly==6.7.0、altair==6.1.0、openpyxl==3.1.5
  - 检查代码无绝对路径，所有 `data/samples` 读取均相对路径
  - 重写 `README.md`：本地运行步骤（含可选 venv）、`bash init.sh` 一键检查、数据更新流程（澄清 gitignore 行为）、Streamlit Cloud 部署完整步骤、常见问题（中文字体、CSV BOM、空数据）、刷新过的项目结构（含 generate_sample_data.py、各文件归属功能）
- 运行过的验证：
  - `pip install -r requirements.txt` → 退出码 0
  - 5 个包 `__version__` 与 requirements.txt 完全一致
  - `streamlit run app.py --server.headless true` + curl 三个路由 → 全部 HTTP 200
  - 日志无 error/exception/traceback
- 提交记录：见 git log
- 更新过的文件：`requirements.txt`、`README.md`、`feature_list.json`、本文件
- 已知风险：无 — 项目当前已具备开箱部署能力
- 下一步最佳动作：所有计划内功能已交付；可选后续工作：
  1. F07 真正的 PDF（推荐 reportlab + plotly+kaleido）
  2. 接入真实 Metricool 导出做生产数据验证
  3. 把 `posts_count` 加入示例数据生成器（当前 NaN，KPI 卡的"时段发帖数"始终是 0）
  4. 加 CI / pytest 把当前临时验证脚本固化下来

### Session 001 — F07 报告导出（PDF 降级为 CSV/Markdown）

- 日期：2026-05-22
- 本轮目标：在 F07 acceptance criteria 与 CLAUDE.md "不引入需 API key 依赖"约束之间做选型，最终交付一个可用的导出方案
- 用户决策：将 PDF 导出降级为 CSV + Markdown 下载，PDF 实现推迟
- 已完成：
  - 在汇报视图末尾新增 "📥 导出报告" 区块，两个 `st.download_button`：
    - CSV：周期 × 平台聚合（含曝光/总互动/各互动/粉丝净增/期末粉丝/互动率），UTF-8 BOM 前缀便于 Excel 中文显示
    - Markdown：含自动摘要 + 各平台数据表，可直接粘贴飞书/Notion
  - 文件名：`social_report_<YYYYMM>` 月度 / `<YYYYQn>` 季度
  - 修复 `strftime("%q")` 在 Linux glibc 不支持的问题（手算季度号代替）
- 运行过的验证：
  - AppTest 月度与季度模式：5 个 subheader（含 "📥 导出报告"），无 exception
  - AppTest 季度 + 切换柱状图指标：无 exception
  - 端到端：`/汇报视图` HTTP 200，日志无 error
- 提交记录：见 git log
- 更新过的文件：`pages/2_📈_汇报视图.py`（追加导出区块 + 修复 %q）、`feature_list.json`（F07 标 deferred 含降级说明）、本文件
- 已知风险/未解决：
  - **F07 acceptance criteria 字面（PDF 文件）未满足，仅交付替代方案**。后续若需要真正 PDF，推荐 reportlab + plotly.write_image(kaleido)
- 下一步最佳动作：F08 部署配置 — 检查 requirements.txt 版本锁定、路径相对化、补完 README 部署步骤、确认本地与云端行为一致

### Session 001 — F06 汇报视图页面

- 日期：2026-05-22
- 本轮目标：完成 F06
- 已完成：
  - 重写 `pages/2_📈_汇报视图.py`：
    - 侧边栏：周期切换（月度/季度）+ "排除未结束周期"复选框（默认 True 避免环比失真）
    - 主区域：最近完整周期的 4 个 KPI（总曝光、总互动、净增粉丝、平均互动率，带环比 delta）；自动生成的 Markdown 摘要（含亮点平台）；跨平台对比柱状图（可切 4 个指标）；按日粉丝增长曲线
    - 复用 `metrics.aggregate_by_period` 做 W/M/Q 聚合，复用 `calculate_period_change` 算环比
- 运行过的验证：
  - AppTest 默认状态：无 exception；4 个 subheader；4 个 KPI（总曝光 13,807,110 +2.5%、总互动 850,731 -0.8%、净增 18,791 +2.6%、平均互动率 6.16%）；摘要 markdown 生成
  - AppTest 交互：radio→季度 显示 "2026-Q1 季度汇总"；checkbox→False 切回 "2026-05 月度汇总"；柱状图 4 个对比指标切换无异常
  - 端到端：`/` `/运营视图` `/汇报视图` HTTP 200，日志无 error
- 提交记录：见 git log
- 更新过的文件：`pages/2_📈_汇报视图.py`（替换骨架）、`feature_list.json`、本文件
- 已知风险：
  - "Q" 显示用了 strftime 的 `%q`（pandas 支持但不是所有平台 strftime 都支持）；如果云端报错可降级为手算季度号
  - 文字摘要目前是模板化，不是 LLM 生成；要"更智能"的摘要可以未来接入小型 LLM 调用（CLAUDE.md 禁止 API key 依赖，所以维持模板化是合理选择）
- 下一步最佳动作：F07 PDF 导出。由于这是 Streamlit Cloud 部署且 CLAUDE.md 禁止外部 API，建议用 reportlab 或类似纯 Python 库；或者用 Streamlit 的 download_button + html→pdf（如 WeasyPrint）。需要先与用户确认实现路径

### Session 001 — F05 运营视图页面

- 日期：2026-05-22
- 本轮目标：完成 F05
- 已完成：
  - 重写 `pages/1_📊_运营视图.py`：
    - 数据流：`load_all_data → clean → enrich_dataframe`，结果用 `@st.cache_data` 缓存
    - 侧边栏：平台多选筛选器（默认全选）+ 日期范围（默认全时段）
    - 主区域：6 平台 KPI 卡片（粉丝最新值、平均互动率、时段粉丝净增、时段发帖数）；plotly 互动率折线图（按平台分色）；按总互动量降序的排行表
    - 空状态保护：无数据时 `st.warning + st.stop()`，筛选条件过严时同样保护
- 运行过的验证：
  - `AppTest` 默认状态：无 exception；3 个 subheader、24 个 metric（6×4）、1 个 dataframe（6 行）、0 warning
  - `AppTest` 筛选交互：multiselect 设为 `['instagram']` → metrics=4，dataframe=(1,5)，证明筛选器对所有下游组件生效
  - 端到端：`streamlit run app.py --server.headless true` → `/` `/运营视图` `/汇报视图` 都 HTTP 200，日志无 error/exception
- 提交记录：见 git log
- 更新过的文件：`pages/1_📊_运营视图.py`（替换骨架）、`feature_list.json`、本文件
- 已知风险：
  - 示例数据的 `posts_count` 全 NaN（生成器未写入），KPI 卡的"时段发帖数"会显示 0；真实数据接入后应有值
  - "排行表"目前是按平台聚合，而 CLAUDE.md F05 描述里说"内容表现排行表"——严格来说应该是按 post 维度。当前样本数据无 post 粒度，按平台聚合是合理近似；后续如果接入 post 级 CSV，需要扩展 data_loader 以保留 post id 并改这里的聚合维度
- 下一步最佳动作：实现 F06（汇报视图），月度/季度聚合、跨平台对比柱状图、粉丝增长曲线、自动文字摘要

### Session 001 — F04 数据清洗与衍生指标计算模块

- 日期：2026-05-22
- 本轮目标：完成 F04
- 已完成：
  - 新增 `utils/metrics.py`：
    - 标量函数：`calculate_engagement_rate` / `calculate_follower_growth` / `calculate_follower_growth_rate` / `calculate_period_change`
    - 所有比率均通过 `_safe_div` 保护除零、NaN、None，统一返回 0.0
    - DataFrame 级 `enrich_dataframe(df)`：向量化追加 engagement_rate / follower_growth / follower_growth_rate
    - `aggregate_by_period(df, period)`：W/M/Q 三种周期聚合，自动适配 pandas ≥2.2 的 ME/QE 频率别名
  - 新增 `utils/data_cleaner.py`：
    - 负数截断为 0（保留 NaN）
    - 互动列 NaN 填 0；followers 的 NaN 保留（保留语义信息）
    - 增加 `is_anomaly` bool 列标记原始数据异常的行（负数或 followers 缺失）
- 运行过的验证：
  - F04 验收命令 `calculate_engagement_rate(100, 50, 10, 5, 1000)` → 16.5 ✅
  - 标量函数全套断言：除零、None、NaN 都返回 0.0
  - 端到端：`load_all_data → clean → enrich_dataframe` 在 540 行样本上跑通，首日 follower_growth=0 符合预期
  - 月度聚合后 instagram MoM 计算正确（最后一月数据不完整下出现负 MoM，是预期行为）
  - 周度聚合最近 4 周数据合理
  - cleaner 单元测试：负数行截断 + is_anomaly 标记，互动列 NaN 填 0
- 提交记录：见 git log
- 更新过的文件：`utils/metrics.py`（新增）、`utils/data_cleaner.py`（新增）、`feature_list.json`、本文件
- 已知风险：
  - `aggregate_by_period` 在不完整周/月（如 2026-02 只有 7 天、2026-05 只有 21 天）下会输出"未满周期"的聚合值；F06 在做汇报视图时如果对比"上月 vs 本月"，需要要么排除不完整周期、要么显式标注
  - 标量函数返回的是 Python float，DataFrame 级别返回 float64 Series，二者一致
- 下一步最佳动作：实现 F05（运营视图页面），用 `data_loader + cleaner + metrics` 链路串通数据，渲染 KPI 卡片、趋势折线图、排行表、平台筛选器、日期范围选择器

### Session 001 — F03 数据加载与来源自动识别模块

- 日期：2026-05-22
- 本轮目标：完成 F03
- 已完成：
  - 新增 `utils/data_loader.py`，提供 `load_csv(path)` 和 `load_all_data(directory)` 两个公共函数
  - **来源识别**：按表头列集合作为指纹判定。Metricool 优先（Account/Network/Date 三列同时存在），否则匹配六个平台原生导出指纹（取交集最大者）
  - **字段映射**：完整覆盖 CLAUDE.md "各平台字段映射表"和 Metricool（Network 列 → 标准 platform 名，twitter/x 都映到 'x'）
  - **类型标准化**：date → datetime64，platform → str，所有数值列 → float64（统一便于 concat / 后续衍生计算）
  - **缺失列**：补 NaN 不报错（如 YouTube 没有 shares/saves，保留 float64 列）
  - **错误降级**：空文件、只有表头、无法识别表头、不规则列数、不存在目录都被捕获并发出中文警告，不抛异常
  - **警告路由**：在真正的 Streamlit runtime 中走 `st.warning`，CLI / 单元测试中走 `logging.warning`（用 `streamlit.runtime.exists()` 判定）
  - 同平台同日期重复行（Metricool 与原生重叠时）按 `(platform, date)` 去重保留最后一条
- 运行过的验证：
  - F03 验证命令 `python -c "from utils.data_loader import load_all_data; df = load_all_data('data/samples'); print(df.columns.tolist()); print(len(df))"` → 标准 10 列，540 行
  - 各平台行数均为 90，dtypes 干净（datetime64 / str / float64）
  - 构造 Metricool 格式 CSV → 3 行 3 个平台映射正确（含 Twitter→x）
  - 5 个边界情况脚本测试 → 每个都有合适的中文警告，主流程返回空 DataFrame 或仅跳过该文件
- 提交记录：见 git log
- 更新过的文件：`utils/data_loader.py`（新增）、`feature_list.json`、本文件
- 已知风险：
  - 当前没有真实 Metricool 导出样本，Metricool 路径仅由人工构造的样本验证；接入真实数据时若字段名有差异需要更新 `_METRICOOL_COLUMN_MAP`
  - 平台指纹基于"必须出现的列子集"匹配，如果未来某平台的导出新增/删除列可能需要调整指纹
- 下一步最佳动作：实现 F04（`utils/data_cleaner.py` + `utils/metrics.py`），计算 engagement_rate / follower_growth / follower_growth_rate / wow_change / mom_change，处理除零和异常值

### Session 001 — F02 示例数据生成器

- 日期：2026-05-22
- 本轮目标：完成 F02
- 已完成：
  - 新增 `generate_sample_data.py`，可重跑（固定 seed=20260522），覆盖式写入 `data/samples/{instagram,tiktok,youtube,x,facebook,linkedin}.csv`
  - 每个 CSV 90 行（2026-02-21 → 2026-05-21），表头沿用各平台**原生导出格式**（非标准字段名），为 F03 data_loader 的"按表头识别来源"逻辑准备
  - 粉丝数模拟带 5% 取关噪声，整体递增；互动数按粉丝→曝光→各互动率链路生成，区间符合各平台行业经验
- 运行过的验证：
  - `python generate_sample_data.py` → 6 个 CSV 生成成功
  - `ls data/samples/*.csv | wc -l` → 6
  - `wc -l data/samples/*.csv` → 每个 91（1 header + 90 data）
  - 自定义 Python 校验脚本：日期连续无缺口、所有数值非负、粉丝净增 +3.6%~+14.9%
- 提交记录：见 git log
- 更新过的文件：`generate_sample_data.py`（新增）、`data/samples/*.csv`（6 个新文件）、`feature_list.json`、本文件
- 已知风险：示例数据是合成数据，趋势单调向上无明显季节性；后续真实数据接入后视图应能优雅处理粉丝下降的情况
- 下一步最佳动作：实现 F03（`utils/data_loader.py`），按表头识别 6 个平台原生格式并映射到 CLAUDE.md 标准字段命名；处理 Metricool 统一格式（如有）以及缺失列/空文件/格式错误

### Session 001 — F01 项目初始化与基础框架

- 日期：2026-05-22
- 本轮目标：完成 F01
- 已完成：
  - 将 `app.py` 从占位页改写为正式首页：自定义页面标题（"海外社媒数据面板"）、图标（🌏）、宽布局；展示项目简介、平台覆盖、数据状态摘要
  - 将子页面按 CLAUDE.md 规范重命名：
    - `pages/1_operations.py` → `pages/1_📊_运营视图.py`
    - `pages/2_reports.py` → `pages/2_📈_汇报视图.py`
  - 两个子页面补全骨架结构（保留 F05/F06 待实现的提示，附禁用态筛选器），保证首页和子页面在 Streamlit 多页面导航中正确显示
- 运行过的验证：
  - `bash init.sh` → 全部 6 步通过
  - `pip install -r requirements.txt` → 成功
  - `streamlit run app.py --server.headless true` → server 启动成功，`/_stcore/health` 返回 `ok`，日志无 error/exception
  - `curl http://localhost:8501/` → HTTP 200
  - `curl http://localhost:8501/运营视图` → HTTP 200
  - `curl http://localhost:8501/汇报视图` → HTTP 200
  - `python -m py_compile` 三个脚本 → OK
  - `streamlit.testing.v1.AppTest` 跑三个脚本 → 都无 exception，各自的 title 正确（"🌏 海外社媒数据面板"、"📊 运营视图"、"📈 汇报视图"）
- 已记录证据：本文件 + `feature_list.json` 中 F01.evidence
- 提交记录：见 git log
- 更新过的文件或工件：
  - `app.py`（重写）
  - `pages/1_📊_运营视图.py`（重命名 + 内容增强）
  - `pages/2_📈_汇报视图.py`（重命名 + 内容增强）
  - `feature_list.json`（F01 标记为 done）
  - `claude-progress.md`（本文件）
- 已知风险或未解决问题：
  - `data/samples/` 当前为空，下一步 F02 需要生成示例 CSV，否则 F03+ 的数据流验证会受阻
- 下一步最佳动作：实现 F02（示例数据生成器），按 CLAUDE.md 中"各平台字段映射表"和"标准字段命名"生成六个平台 90 天的 CSV

---

## 2026-05-24：Tier 1/2/3 优化全部完成

### 上下文
多轮开发后用户要求全面优化。三层共 14 项，分 3 个 commit 推送（按计划文件 `staged-kindling-puppy.md`）。

### Tier 1（commit ebad1d9）
- 数据导入页 11 个区块 → 4 个 tab（CSV / 手动录入 / API / Sheets），API tab 内嵌套 4 个平台子 tab
- PLATFORM_LABELS 从 3 处去重到 utils/ui.py
- 删 altair / openpyxl 未用依赖
- 新增 utils/api_base.py（APIConfigError/APIError/APISourceBase）；4 个 API 模块 errors 全部继承基类；HTTP 调用走统一 `_request` 含 429/5xx 重试

### Tier 2（commit 211d301）
- 汇报视图 4 个 st.metric → kpi-panel HTML 卡片
- 新 utils/logging.py 含 emit_warning/emit_error；4 个 API 模块 logger.warning 全替换
- get_active_dataframe 缓存 key 拼 DataFrame 内容 hash（pd.util.hash_pandas_object），同名 CSV 不再误命中
- STANDARD_COLS 上方加详细字段语义表（每列+各平台差异）
- tests/test_data_pipeline.py 20 个测试全过；requirements-dev.txt 加 pytest

### Tier 3（commit 待推送）
- ui.py 所有 0.7x rem 字体提到 0.78+ 通过 WCAG AA
- app.py sidebar_state collapsed → auto，与其他页一致
- .github/workflows/ci.yml 加 pytest + Streamlit smoke
- scripts/youtube_auth.py 把 refresh_token 写到 .youtube_token.toml（gitignore）而非 stdout
- .gitignore 加 client_secret*.json / .youtube_token.toml / .pytest_cache
- feature_list.json 同步 F14/F15/T1/T2/T3

### 验证证据
- `python -m pytest tests/ -v` → 20 passed
- `AppTest` 4 个页面 → 全无 exception
- `python -m json.tool feature_list.json` → 通过

### 下一步建议
- 等 Streamlit Cloud 自动部署，手动验证 tab 切换、KPI 卡渲染、字体可读性
- GitHub Actions CI 首次跑（由本次 push 触发）
- 后续可考虑：CI 加缓存层、覆盖率统计、依赖 Dependabot
