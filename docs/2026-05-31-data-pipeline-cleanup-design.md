# 数据管线整顿 — 设计与修改清单

> 日期：2026-05-31
> 状态：设计已定（brainstorming 收敛），待逐项实施
> 背景：数据获取与计算方式混乱。经 3 个并行 subagent 审查取数/计算/呈现三层后，
> 用户拍板了 4 个关键方向，本文把方向落成可执行的修改清单。

---

## 一、已确认的设计决策

| # | 决策 | 选择 |
|---|---|---|
| 1 | 互动率分母（曝光基准） | 统一列 `exposure_base = COALESCE(reach, impressions)`，reach 优先 |
| 2 | 唯一可信源 | Google Sheet。`data/samples` 降级为纯 demo（仅无 Sheet 无上传时兜底） |
| 3 | 互动率汇总口径 | 曝光加权 `Σ互动 ÷ Σexposure_base × 100`，两视图统一；逐日趋势图仍按天算 |
| 4 | 空值呈现 | 显示 `N/A`（不显示 0），并标注每平台可用指标 |

### 核心范式转变
**从"NaN 填 0"改为"NaN 保留、呈现层显示 N/A"。** 这是 #2（互动率塌成 0）和
#4（平台列语义混乱）的共同根治点：只有保留 NaN，才能区分"这个平台没这个数据"
（NaN → N/A）和"真的是 0 互动"（0 → 0）。

### 平台 × 曝光基准落点
| 平台 | reach | impressions | exposure_base 实际用 |
|---|---|---|---|
| Facebook | ✅ | ❌ 废弃 | reach |
| Instagram | ✅ | ❌ 废弃 | reach |
| YouTube | ❌ | ✅ views | impressions(views) |
| TikTok | ❌ | ✅ video views | impressions |
| LinkedIn | ❌ | ✅ 主页访问量 | impressions |

---

## 二、修改清单（按文件，可逐项勾选）

### A. `utils/metrics.py` — 衍生指标核心

- [ ] **A1** `enrich_dataframe`：新增内部列 `exposure_base`
  ```python
  out["exposure_base"] = out["reach"].fillna(out["impressions"])
  ```
  放在 engagement_rate 计算之前。reach 优先，reach 为 NaN 时回落 impressions，
  两者皆 NaN → exposure_base = NaN。

- [ ] **A2** `engagement_rate` 改用 exposure_base 当分母，且**分母无效时结果为 NaN（不再 fillna(0)）**
  ```python
  interactions = (likes + comments + shares + saves)  # skipna 求和
  base = out["exposure_base"].replace(0, np.nan)
  out["engagement_rate"] = interactions / base * 100   # 不再 .fillna(0.0)
  ```
  删除现有的 L107-108 那段"reach 回落填 impressions"（被 exposure_base 取代）。

- [ ] **A3** `aggregate_by_period`：把 `reach` 和 `exposure_base` 加入聚合列表（求和）
  - 关键：exposure_base 必须**在日级算好后再 sum**（`Σexposure_base`），
    不能用 `Σreach.fillna(Σimpressions)`（跨天混合会算错）。
  - 互动率在聚合后重算：`Σinteractions / Σexposure_base`（"先聚合再相除"）。

- [ ] **A4** `follower_growth` 逻辑保持不变（源头列优先 + shift 兜底，已正确）。

### B. `utils/data_cleaner.py` — 清洗（范式转变核心）

- [ ] **B1** 数值列的 NaN **不再填 0**，保留 NaN。
  - 现状：`_INTERACTION_COLS` 把 likes/comments/shares/saves/impressions 的 NaN 填 0。
  - 改后：保留 NaN，让下游用 skipna 求和、让呈现层显示 N/A。
- [ ] **B2** 负值仍截断为 0（或按现有 `is_anomaly` 逻辑标记），这条不变。
- [ ] **B3** 确认 `reach` / `impressions` 的 NaN 绝对不被填 0（否则 exposure_base 永不为 NaN，
  互动率又会塌 0）。

### C. `utils/data_sources.py` — 数据源治理

- [ ] **C1** `get_active_dataframe` / `_resolve_source` 优先级明确为：
  `上传 session > Google Sheet > samples(仅 demo 兜底)`。
- [ ] **C2** `_LOCAL_FALLBACK_DIRS`：生产不再全量读 `data/samples`。
  仅当**既无 Sheet 也无上传**时，读**一份**干净的 demo 文件（见 D1）。
- [ ] **C3** `exposure_base` 是派生列，**不持久化到 Sheet**（每次 enrich 重算）。
  Sheet 只存原始 reach / impressions。`_SHEET_ALL_COLS` 维持现状（不加 exposure_base）。
- [ ] **C4**（可选）`load()` 读 Sheet 后，丢弃 date 无法解析的脏行已实现（self-heal），保留。

### D. `data/samples/` — 清理矛盾文件

- [ ] **D1** 只保留**一份**不矛盾的标准化 demo 文件（如重新生成
  `generate_sample_data.py` 输出一份 `demo_all_platforms.csv`，标准列名）。
- [ ] **D2** 删除/归档矛盾的原生格式文件（`facebook.csv` 等 6 个）和分月文件（10 个）。
  注意：CLAUDE.md 禁止删除 `data/samples/` 下示例文件——**需先与人确认**或改为归档到
  `data/samples/_archive/`。
- [ ] **D3** 手动收集的真实数据（`april_may_2026_all_platforms.csv` 等）：
  通过 Streamlit 上传 → 写回 Sheet（merge），然后从 samples 移除/归档。
  让真实数据只活在 Sheet（唯一可信源）。

### E. `pages/1_📊_运营视图.py` — 运营视图

- [ ] **E1** KPI 卡"平均互动率"：从 `engagement_rate.mean()`（日均）改为
  `Σ互动 ÷ Σexposure_base × 100`（曝光加权）。
- [ ] **E2** 排行表"平均互动率"：同 E1 改为曝光加权。
- [ ] **E3** 空值呈现：followers/互动率等为 NaN 时显示 `N/A`（不显示 0）。
- [ ] **E4** 平台可用指标标注（见 G）。
- [ ] **E5** 逐日互动率趋势折线图：**保持按天算**（这是趋势，日粒度合理，是例外）。

### F. `pages/2_📈_汇报视图.py` — 汇报视图

- [ ] **F1** 周期互动率分母从 `impressions` 改为 `exposure_base`（口径与运营视图一致）。
- [ ] **F2** 跨平台对比柱状图：指标选项把"曝光"明确为 exposure_base（或同时给 reach/impressions）。
- [ ] **F3** 空值/无上期 → 显示 `N/A` / `—`（部分已实现，统一一遍）。

### G. 呈现/标注（#4 语义澄清）

- [ ] **G1** Facebook 的 `likes` 实际是 `page_post_engagements`（综合互动，高估真实点赞）：
  UI 标注为"互动(综合)"或加 tooltip 说明，避免误读为纯点赞。
- [ ] **G2** `saves` 全平台无数据：呈现层显示 N/A（不显示 0）；
  或从默认 KPI 卡移除，仅在有数据时显示。
- [ ] **G3** 平台可用指标矩阵：在数据导入页或视图页某处展示"哪个平台有哪些指标"，
  让用户理解空列是平台限制而非数据丢失。
- [ ] **G4** TikTok 无日级时序（仅 today 一行）+ groupby().sum() 语义污染：
  接入前在 UI 标注"TikTok 仅当日快照"，避免误当时序；或暂不纳入趋势图。

### H. `tests/test_data_pipeline.py` — 回归测试

- [ ] **H1** `exposure_base` COALESCE：reach 优先、reach 空回落 impressions、皆空为 NaN。
- [ ] **H2** `engagement_rate` 用 exposure_base；分母 NaN/0 → 结果 NaN（**不塌 0**）。
- [ ] **H3** `clean` 不再把数值列 NaN 填 0（保留 NaN）；负值仍截断。
- [ ] **H4** 两视图口径一致：同一份数据，运营视图 KPI 与汇报视图周期互动率口径相同。
- [ ] **H5** 周期聚合：exposure_base 日级算好再 sum，互动率先聚合再相除。
- [ ] **H6** N/A 呈现：NaN 列在视图层渲染为 N/A 而非 0。

---

## 三、建议执行顺序

1. **计算层根基**（B → A）：先 data_cleaner 保留 NaN，再 metrics 加 exposure_base + 改互动率。配 H1/H2/H3。
2. **聚合**（A3）：aggregate_by_period 加 reach/exposure_base。配 H5。
3. **数据源**（C）：优先级 + samples 降级。
4. **视图口径统一**（E1/E2 + F1）：两视图改曝光加权。配 H4。
5. **呈现层 N/A**（E3 + F3 + G）：空值 N/A + 平台标注。配 H6。
6. **samples 清理 + 真实数据进 Sheet**（D）：需先确认 CLAUDE.md 的"禁删 samples"约束如何处理（归档 vs 删除）。
7. **全套验证**：`pytest tests/` + 4 页 AppTest + Streamlit Cloud 硬刷新核对。

---

## 四、注意事项 / 风险

- **CLAUDE.md 约束**：禁止删除 `data/samples/` 下示例文件。D2/D3 的清理需改为
  "归档到子目录"或先获人类明确同意，不能直接删。
- **范式转变影响面**：B1（NaN 不填 0）会波及所有假设"clean 后无 NaN"的下游代码。
  实施时要把每个消费数值列的地方都过一遍，确保 NaN 被正确处理（skipna / N/A 渲染）。
- **exposure_base 不持久化**：它是派生列，Sheet 只存 reach/impressions，每次 enrich 重算。
  好处是 Sheet 结构不变、不会有冗余不一致。
- **跨平台口径差异**：exposure_base 对 FB/IG 是"去重触达"、对 YT/TikTok 是"曝光次数"，
  语义不完全可比。这是各平台 API 现状下的最优折中，已被用户接受（决策 #1）。
- **TikTok / LinkedIn 未真正接入**：当前实际有数据的是 FB/IG/YouTube + 手动。
  整顿应让架构对所有平台干净，但优先保证已接入平台正确。
