# CLAUDE.md — 海外社媒数据面板项目

本仓库是一个面向长时运行 coding agent 工作流的项目。目标不是尽可能快地产出代码，而是让每一轮会话结束后，下一个会话仍然能无猜测地继续工作。

## 项目概述

为海外社媒运营团队搭建一个 Streamlit 数据面板，汇总展示六个平台（Instagram、TikTok、YouTube、X/Twitter、Facebook、LinkedIn）的运营数据，服务于两类受众：日常运营团队和管理层汇报。

## 技术栈

- **语言**: Python 3.10+
- **框架**: Streamlit
- **数据处理**: pandas
- **可视化**: plotly, altair（Streamlit 原生支持）
- **数据源**: CSV 文件（来自 Metricool 导出 + 各平台原生 Analytics 导出）
- **部署**: Streamlit Community Cloud（连接 GitHub 仓库）

## 开工流程

写代码前先做这些事：

1. 用 `pwd` 确认当前目录。
2. 读取 `claude-progress.md`，了解最新已验证状态和下一步。
3. 读取 `feature_list.json`，选择优先级最高的未完成功能。
4. 用 `git log --oneline -5` 看最近提交。
5. 运行 `bash init.sh`。
6. 在开始新功能前，先跑必需的 smoke test 或端到端验证。

如果基础验证一开始就失败，先修基础状态，不要在坏的起点上继续叠新功能。

## 工作规则

- **一次只做一个功能。** 对照 `feature_list.json` 中优先级最高的未完成项。
- **不要因为"代码已经写了"就把功能标记为完成。** 必须通过验证。
- **除非为了消除当前 blocker 的窄范围修复，否则不要扩大到其他功能。**
- **实现过程中不要悄悄改弱验证规则。**
- **优先依赖仓库里的持久化文件，而不是聊天记录。**

## 项目结构

```
social-media-dashboard/
├── CLAUDE.md                  # 本文件 - Agent 行为指令
├── feature_list.json          # 功能状态唯一事实来源
├── claude-progress.md         # 会话进度和当前已验证状态
├── session-handoff.md         # 会话交接摘要
├── init.sh                    # 统一的启动与验证入口
├── requirements.txt           # Python 依赖
├── app.py                     # Streamlit 主入口
├── .streamlit/
│   └── config.toml            # Streamlit 主题配置
├── data/
│   ├── samples/               # 示例 CSV 文件（用于开发和测试）
│   └── *.csv                  # 实际运营数据（gitignore）
├── utils/
│   ├── __init__.py
│   ├── data_loader.py         # CSV 读取与来源自动识别
│   ├── data_cleaner.py        # 清洗、标准化、缺失值处理
│   └── metrics.py             # 衍生指标计算（互动率、增长率等）
└── pages/
    ├── 1_📊_运营视图.py        # 运营团队日常数据页
    └── 2_📈_汇报视图.py        # 管理层月度/季度汇报页
```

## 数据规范

### CSV 来源识别规则

数据来自两个渠道，通过表头字段自动判断来源：

1. **Metricool 导出**: 统一格式，包含 `Account`、`Network`、`Date` 等字段
2. **平台原生导出**: 各平台字段不同，需按平台映射

### 标准化字段命名

所有外部数据经过 `data_loader.py` 处理后，统一映射为以下字段：

| 标准字段名 | 类型 | 说明 |
|---|---|---|
| `date` | date | 数据日期 |
| `platform` | str | 平台名（instagram/tiktok/youtube/x/facebook/linkedin） |
| `followers` | int | 当日粉丝/订阅数 |
| `impressions` | int | 曝光量 |
| `reach` | int | 触达人数 |
| `likes` | int | 点赞数 |
| `comments` | int | 评论数 |
| `shares` | int | 转发/分享数 |
| `saves` | int | 保存/收藏数 |
| `posts_count` | int | 发帖数 |
| `engagement_rate` | float | 互动率（计算字段） |
| `follower_growth` | int | 粉丝净增量（计算字段） |
| `follower_growth_rate` | float | 粉丝增长率（计算字段） |

### 各平台字段映射表

Claude Code 在实现 `data_loader.py` 时，需要对照以下映射关系。如果实际导出的 CSV 表头与此处不符，以实际表头为准，但输出必须符合上面的标准字段命名。

**Instagram (Meta Business Suite 导出)**:
- `Date` → `date`
- `Followers` → `followers`
- `Impressions` → `impressions`
- `Reach` → `reach`
- `Likes` → `likes`
- `Comments` → `comments`
- `Shares` → `shares`
- `Saves` → `saves`

**TikTok Analytics 导出**:
- `Date` → `date`
- `Followers` → `followers`
- `Video Views` → `impressions`
- `Likes` → `likes`
- `Comments` → `comments`
- `Shares` → `shares`

**YouTube Studio 导出**:
- `Date` → `date`
- `Subscribers` → `followers`
- `Views` → `impressions`
- `Likes` → `likes`
- `Comments` → `comments`

**X Analytics 导出**:
- `Date` → `date`
- `Followers` → `followers`
- `Impressions` → `impressions`
- `Likes` → `likes`
- `Replies` → `comments`
- `Retweets` → `shares`

**Facebook (Meta Business Suite 导出)**:
- `Date` → `date`
- `Page Followers` → `followers`
- `Impressions` → `impressions`
- `Reach` → `reach`
- `Reactions` → `likes`
- `Comments` → `comments`
- `Shares` → `shares`

**LinkedIn Page Analytics 导出**:
- `Date` → `date`
- `Total followers` → `followers`
- `Impressions` → `impressions`
- `Reactions` → `likes`
- `Comments` → `comments`
- `Shares` → `shares`

## 衍生指标计算公式

```python
engagement_rate = (likes + comments + shares + saves) / impressions * 100
follower_growth = followers_today - followers_yesterday
follower_growth_rate = follower_growth / followers_yesterday * 100
wow_change = (this_week_metric - last_week_metric) / last_week_metric * 100  # 周环比
mom_change = (this_month_metric - last_month_metric) / last_month_metric * 100  # 月环比
```

处理除零情况：当分母为 0 时，结果设为 0.0，不要抛异常。

## 代码风格

- 函数和变量命名用 snake_case
- 文件内注释用中文
- commit message 用英文，格式: `feat: add csv parser for metricool`、`fix: handle missing date column`
- 每个模块顶部写一行 docstring 说明该模块的职责
- 不要使用 `print()` 做调试，用 `st.warning()` 或 `logging`

## 完成定义

一个功能只有在以下条件都满足时才算完成：

- 目标行为已经实现
- 要求的验证真的跑过（`streamlit run app.py` 能正常启动，数据正确显示）
- 用示例 CSV 数据测试过，无报错
- 证据记录在 `feature_list.json` 或 `claude-progress.md`
- 仓库仍然能按标准启动路径重新开始工作

## 收尾

结束会话前：

1. 更新 `claude-progress.md`
2. 更新 `feature_list.json`
3. 记录仍未解决的风险或 blocker
4. 在工作处于安全状态后，用清晰的 commit message 提交
5. 保证下一轮会话可以直接运行 `bash init.sh`

## 禁止事项

- 不要修改 `CLAUDE.md` 本身（除非人类明确要求）
- 不要删除或重命名 `data/samples/` 下的示例文件
- 不要引入需要 API key 才能运行的外部服务依赖
- 不要把 `data/*.csv`（实际运营数据）提交到 git
- 不要在没跑过 `streamlit run app.py` 验证的情况下标记功能为完成
