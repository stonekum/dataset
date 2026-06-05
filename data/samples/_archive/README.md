# 归档示例文件（数据管线整顿 2026-05-31）

这些文件是**早期示例数据**，在「数据管线整顿」中被归档到此处，原因见
`docs/2026-05-31-data-pipeline-cleanup-design.md` 的 D2。

## 为什么归档

旧的 `data/samples/` 同时放了三类互相矛盾的文件，被本地 fallback **全量拼接**当
demo，污染了演示数据：

- **6 个原生格式文件**（`facebook.csv` / `instagram.csv` / `tiktok.csv` /
  `youtube.csv` / `x.csv` / `linkedin.csv`）：各平台原生表头，语义不统一。
- **10 个分月文件**（`*_april_2026.csv` / `*_may_2026.csv`，含 `twitter_*`）：
  与原生文件、合并文件重复。

整顿后：fallback 只读**一份**标准化 demo `data/samples/demo_all_platforms.csv`
（由 `python generate_sample_data.py` 生成，标准列名、刻意保留 N/A 演示平台指标差异）。

## 没有删除

按 CLAUDE.md「不要删除 data/samples 下示例文件」的约束，这里采用**归档而非删除**
（已获人类确认）。`data/samples/_archive/` 不在 fallback 的非递归 glob 范围内，
所以这些文件留在仓库里、可随时取回，但不再被自动加载。

## 真实数据另行处理

手动收集的真实数据 `april_2026_all_platforms.csv` /
`april_may_2026_all_platforms.csv` **未归档**，仍在 `data/samples/` 根目录，
等待手动上传到 Google Sheet（唯一可信源）后再移除——见 session-handoff.md 的 D3 步骤。
