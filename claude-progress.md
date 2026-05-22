# 进度日志

## 当前已验证状态

- 仓库根目录：social-media-dashboard/
- 标准启动路径：`bash init.sh`
- 标准验证路径：`streamlit run app.py --server.headless true`
- 当前最高优先级未完成功能：F05 - 运营视图页面
- 当前 blocker：无

## 会话记录

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
