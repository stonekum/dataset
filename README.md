# 海外社媒数据面板 (Pulse)

团队海外社交媒体运营数据的统一展示面板，覆盖 **Instagram / TikTok / YouTube / X / Facebook / LinkedIn** 六个平台。基于 Streamlit + pandas + plotly，单仓库部署到 Streamlit Community Cloud。

支持的数据接入方式（任选其一或组合）：

| 方式 | 适用场景 | 维护成本 |
|---|---|---|
| 📤 CSV 拖拽上传 | 临时看数 / 一次性分析 | 最低，无需配置 |
| ✍️ 手动录入 | 没有导出 API 的平台 | 最低 |
| ☁️ Google Sheets 持久化 | 跨 session / 跨设备数据共享 | 低（一次性 10 分钟配置） |
| 🔌 官方 API 拉取 | 每天自动化 | 中（每平台 15–60 分钟配置） |

---

## 目录

- [快速开始](#快速开始)
- [部署到 Streamlit Cloud](#部署到-streamlit-cloud)
- [⚠️ 安全：必须设为 Private](#️-安全必须设为-private)
- [数据接入指南](#数据接入指南)
  - [1. CSV 拖拽上传](#1-csv-拖拽上传)
  - [2. 手动录入](#2-手动录入)
  - [3. Google Sheets 持久化](#3-google-sheets-持久化推荐)
  - [4. YouTube Analytics API](#4-youtube-analytics-api最简单的-api-集成)
  - [5. Meta Graph API（FB + IG）](#5-meta-graph-apifb--ig)
  - [6. LinkedIn Marketing API](#6-linkedin-marketing-api)
  - [7. TikTok Business API](#7-tiktok-business-api)
- [Token 续期清单](#token-续期清单)
- [故障排查](#故障排查)
- [开发](#开发)
- [项目结构](#项目结构)

---

## 快速开始

### 本地运行（5 分钟）

```bash
# 1. 克隆
git clone git@github.com:stonekum/dataset.git
cd dataset

# 2. （可选）虚拟环境
python3 -m venv .venv && source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 生成示例数据（仓库已附带，可跳过）
python generate_sample_data.py

# 5. 启动
streamlit run app.py
```

浏览器自动打开 `http://localhost:8501`，能看到三个页面：
- **首页**：项目概览
- **📊 运营视图**：日常 KPI、趋势、平台排行
- **📈 汇报视图**：周/月/季度汇总 + 自动文字摘要 + 导出（PDF 汇报成品 / CSV / Markdown）
- **📤 数据导入**：上传 / 录入 / API 拉取 / Sheets 同步

---

## 部署到 Streamlit Cloud

1. 仓库推到 GitHub（公开或私有皆可）
2. 到 [share.streamlit.io](https://share.streamlit.io) → **New app**
3. 配置：
   - **Repository**：`<你的 GitHub>/dataset`
   - **Branch**：你要部署的分支（如 `main` 或 `claude/festive-hawking-irKB0`）
   - **Main file path**：`app.py`
   - **Python version**：3.11（推荐）
4. 点 **Deploy**，几分钟后就能拿到 URL

每次 `git push` 到部署分支，Streamlit Cloud 会自动重新部署（约 30 秒）。

---

## ⚠️ 安全：必须设为 Private

**默认 Streamlit Cloud app 是 Public** — 任何人拿到 URL 就能访问。这意味着：
- 你的全部社媒数据对公网可见
- 你配置的 API token 会被陌生人触发使用（消耗配额）
- Google Sheets「整表替换」按钮可被任何人点击清空你的历史数据

**部署完第一件事就是改 Private**：

1. 打开应用 → 右上角 **⋯** → **Settings**
2. 找到 **Sharing**
3. 选 **"Only specific people can view this app"**
4. 把你和团队成员的邮箱加进白名单 → **Save**

代码侧已经做了以下加固（无需你额外操作）：
- Meta access_token 走 `Authorization` header，不进 URL 日志
- API 错误信息不再回显原始响应体（防 token 碎片泄露）
- Sheets 「整表替换」需要手动输入 `REPLACE` 才能执行

### 访问口令（纵深防御，建议开启）

把「设为 Private」从一步纯人工操作升级为代码强制：在 Secrets 配置

```toml
[auth]
password = "你的团队共享口令"
```

配置后，进入任何页面前都要先输入该口令。**未配置时应用照常可用**（方便本地开发与示例数据演示），但每个页面顶部会常驻一条"未设口令"告警，提醒你别让面板裸奔。需要按人区分、可审计的登录时，可改用 Streamlit 原生 `st.login()`(OIDC)。

---

## 数据接入指南

### 1. CSV 拖拽上传

适合**临时分析**或**测试**。打开「📤 数据导入」→「📤 上传 CSV」标签 → 拖文件。

**支持的格式**（系统按表头指纹自动识别）：

| 来源 | 识别用关键列 |
|---|---|
| Metricool 统一导出 | `Account` + `Network` + `Date` |
| Instagram (Meta Business Suite) | `Date` + `Followers` + `Impressions` + `Reach` + `Likes` + `Comments` + `Shares` + `Saves` |
| TikTok Analytics | `Date` + `Followers` + `Video Views` + `Likes` + `Comments` + `Shares` |
| YouTube Studio | `Date` + `Subscribers` + `Views` + `Likes` + `Comments` |
| X Analytics | `Date` + `Followers` + `Impressions` + `Likes` + `Replies` + `Retweets` |
| Facebook (Meta Business Suite) | `Date` + `Page Followers` + `Impressions` + `Reach` + `Reactions` + `Comments` + `Shares` |
| LinkedIn Page Analytics | `Date` + `Total followers` + `Impressions` + `Reactions` + `Comments` + `Shares` |

**表头不匹配的文件**：系统不会跳过，会在「手动映射未识别的列」区块让你手动选择平台 + 把原始列名映射到标准字段。

⚠️ 上传数据存在 session 内存，**刷新页面或应用重启会丢失**。要持久化请配合 Google Sheets。

---

### 2. 手动录入

适合**没有导出功能或 API 的平台**。打开「📤 数据导入」→「✍️ 手动录入」标签。

在表格里逐行填写日期 + 平台 + 各项指标，点「提交」并入 session。仍然需要配合 Sheets 才能持久化。

---

### 3. Google Sheets 持久化（推荐）

让数据跨 session 持久化、跨设备共享的最佳方式。一次性设置约 10 分钟，之后运营同事可以在浏览器上传数据 → 写回 Sheets → 任何设备打开仪表盘都能看到。

#### 设置步骤

**3.1 创建 Sheet**

新建 Google Sheet，第一行表头用标准列名：
```
date | platform | followers | impressions | reach | likes | comments | shares | saves | posts_count
```

**3.2 创建 Google Cloud Service Account**

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)
2. 新建项目（或复用现有）
3. **APIs & Services → Library** → 启用 **Google Sheets API** 和 **Google Drive API**
4. **APIs & Services → Credentials → Create Credentials → Service Account**
5. 给 service account 命名（如 `sheets-bot`）→ Create
6. 创建后点进 service account → **Keys → Add Key → JSON** → 下载 JSON 文件

**3.3 给 Service Account 共享 Sheet 编辑权限**

打开 service account 的邮箱（形如 `sheets-bot@xxx.iam.gserviceaccount.com`），在你的 Google Sheet 右上角 **Share** 把这个邮箱加进去，权限选 **Editor**。

**3.4 填入 Streamlit Secrets**

把下面内容粘到 Streamlit Cloud → App Settings → **Secrets**（本地开发则写到 `.streamlit/secrets.toml`）：

```toml
[gsheets]
spreadsheet_url = "https://docs.google.com/spreadsheets/d/你的SheetID/edit"
worksheet_name = "data"   # 可选，默认第一个 tab

[gsheets.service_account]
# 把下载的 JSON 文件内容字段映射过来
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "sheets-bot@xxx.iam.gserviceaccount.com"
client_id = "..."
# 其他字段照抄 JSON
```

完整模板见 `.streamlit/secrets.toml.example`。

#### 使用

「📤 数据导入」→「☁️ Sheets 同步」标签：
- **🔀 增量合并**（推荐）：按 (platform, date) 合并，新值覆盖旧值
- **⚠️ 整表替换**：清空 Sheet 再写入（要输入 `REPLACE` 确认）

---

### 4. YouTube Analytics API（最简单的 API 集成）

15 分钟配置，refresh_token 永久有效，没有审核。

#### 4.1 Google Cloud Console

1. 复用 Sheets 用过的项目（或新建）
2. **APIs & Services → Library** → 启用 **YouTube Data API v3** + **YouTube Analytics API**
3. **OAuth consent screen** → User Type 选 **External** → 填 App name + 邮箱
4. Scopes 步骤跳过
5. **Test users** → 添加你的 YouTube 频道关联的 Gmail
6. **Credentials → Create Credentials → OAuth client ID**
7. Application type 选 **Desktop app** → Create
8. 弹窗里点 **Download JSON** → 改名 `client_secret.json` → 放到本地仓库的 `scripts/` 目录

#### 4.2 本地运行授权脚本

```bash
pip install google-auth-oauthlib
python3 scripts/youtube_auth.py
```

浏览器自动打开 → 用 YouTube 频道关联的 Google 账号登录 → 允许。

授权成功后，token 会写入 `scripts/.youtube_token.toml`（已 gitignore，chmod 600）。

#### 4.3 填入 Secrets

把 `scripts/.youtube_token.toml` 内容整段粘到 Streamlit Secrets：

```toml
[youtube]
client_id     = "...apps.googleusercontent.com"
client_secret = "GOCSPX-..."
refresh_token = "1//..."
```

#### 4.4 使用

「📤 数据导入」→「🔌 API 拉取」→「📺 YouTube」标签 → 选日期范围 → 「📡 拉取数据」。

> 注意 OAuth consent screen 还在 testing mode 时，refresh_token 每 7 天会失效。要永久有效需要把 App 提交 verification（不收费但要等审核）。

---

### 5. Meta Graph API（FB + IG）

中等难度，60 天 token 周期，需要 Business Page + IG 业务账号。

#### 前提

- 拥有 Facebook **Business Page**（不是个人主页）
- Instagram 账号已切换成 **Business / Creator** 并连接到该 FB Page
- 你是 Page 的管理员
- 已通过 Meta 的电话号码验证（开发者账号要求）

#### 5.1 创建 Meta App

1. [developers.facebook.com/apps](https://developers.facebook.com/apps) → **Create App**
2. Use case 选 **Other** → Next
3. App type 选 **Business** → Create
4. App Dashboard 记下 **App ID**（左上角数字）

#### 5.2 拿 Page Access Token

1. 打开 [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. 右上角 **Meta App** 下拉选你刚创建的 App
3. 点 **Generate Access Token**，勾选权限：
   - `pages_show_list`
   - `pages_read_engagement`
   - `read_insights`
   - `instagram_basic`
   - `instagram_manage_insights`
   - `business_management`
4. 弹窗授权 → 选你的 Page + IG 账号
5. 改请求为 `GET /me/accounts` → Submit
6. 在返回 JSON 里找到你的 Business Page，记下：
   - `id` → **Page ID**
   - `access_token` → 短期 Page Access Token
7. 改请求为 `GET /{PAGE_ID}?fields=instagram_business_account` → 返回 `instagram_business_account.id` → **IG User ID**

#### 5.3 换长期 Token（60 天）

App Dashboard → **App settings → Basic** → 找 **App secret**（点 Show 输密码查看）。

Graph API Explorer 里发：
```
GET /oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id=<APP_ID>
  &client_secret=<APP_SECRET>
  &fb_exchange_token=<短期 Page Token>
```

返回的 `access_token` 就是 60 天长期 token。

#### 5.4 填入 Secrets

```toml
[meta_graph]
page_access_token = "EAAxxxxxx..."   # 60 天有效
page_id           = "123456789"
ig_user_id        = "987654321"
app_id            = "111111111"      # 续期时用
```

#### 5.5 使用

「📤 数据导入」→「🔌 API 拉取」→「📘 Meta」标签 → 选日期 + 平台 → 拉取。

「🔍 验证 Token」按钮会显示过期日期（< 14 天会变黄/红）。

---

### 6. LinkedIn Marketing API

需要 App 审核，1–5 个工作日，仅支持 Company Page。

#### 6.1 创建 LinkedIn App

1. [linkedin.com/developers](https://www.linkedin.com/developers/) → **Create App**
2. 关联你的公司主页
3. **Products** 标签 → 申请 **Marketing Developer Platform**（**会走审核，1–5 个工作日**）

#### 6.2 拿 Access Token

审核通过后：
1. **Auth** 标签 → 确认 OAuth 2.0 scopes 含 `r_organization_social`
2. 走 OAuth 2.0 Authorization Code 流程拿 access_token
3. **organization_id**：你公司主页 URL 末尾的数字（如 `linkedin.com/company/12345678/`）

#### 6.3 填入 Secrets

```toml
[linkedin]
access_token    = "AQV..."   # 60 天有效
organization_id = "12345678"
```

#### 6.4 使用

「📤 数据导入」→「🔌 API 拉取」→「💼 LinkedIn」标签。

---

### 7. TikTok Business API

**⚠️ 有限制**：TikTok 有机内容的日粒度 API 支持很有限。本模块只能拉：
- 账号当日快照（粉丝/点赞总数）
- 近 20 条视频的互动按发布日聚合

历史每日粉丝/曝光变化仍需用 CSV 补充。

#### 7.1 准备

- TikTok 账号已升级为 **Business Account**
- [TikTok for Developers](https://developers.tiktok.com/) 创建 App
- 申请 `business.info.get` + `video.list` 权限

#### 7.2 获取 Token

走 TikTok OAuth 2.0 拿 access_token（24h）+ refresh_token（30天）。

#### 7.3 填入 Secrets

```toml
[tiktok]
access_token  = "act.xxx"   # 24 小时有效
refresh_token = "rft.xxx"   # 30 天有效
app_id        = "7xxx"
app_secret    = "xxx"
```

系统会自动用 refresh_token 续期 access_token。

---

## Token 续期清单

| 平台 | Token 类型 | 有效期 | 续期方式 |
|---|---|---|---|
| Google Sheets | Service Account JSON | 永久 | service account 不删就一直有效 |
| YouTube | refresh_token | 永久（除非撤销或 testing mode 满 7 天） | testing → published 申请审核 |
| Meta | Page Access Token (long-lived) | 60 天 | Graph API Explorer 重新走 `/oauth/access_token` 换 |
| LinkedIn | access_token | 60 天 | LinkedIn Developer Portal 重新授权 |
| TikTok | access_token | 24 小时 | refresh_token 自动续；refresh_token 30 天到期后需重新授权 |

**建议**：在日历里设提醒，Meta / LinkedIn 每 50 天提前续一次。

每个平台的「🔍 验证 Token」按钮可以即时检查当前 token 是否有效。

---

## 故障排查

### 数据为空

按优先级排查：
1. session 上传数据没了 → Streamlit 重启过；如果有 Sheets，到「Sheets 同步」点拉取
2. Sheets 配置错 → 检查 Service Account 邮箱是否有 Sheet 编辑权限
3. 本地 CSV 没放对 → `data/` 或 `data/samples/` 至少要有一个 CSV，且表头匹配

### API 拉取报错

- **"Token 无效"**：到对应平台「🔍 验证 Token」查到期时间，按上面的清单续期
- **"权限不足"**：LinkedIn 多见，确认 App 已通过 Marketing Developer Platform 审核
- **HTTP 429**：触发限流，等几分钟再试（base client 已含指数退避）
- **空数据**：确认时间范围内确实有发帖/活动

### Streamlit Cloud 部署失败

- **Failed to download the sources**：Streamlit Cloud 的 GitHub 授权过期 → Settings → Connections → Reconnect GitHub
- **Module not found**：requirements.txt 与代码 import 不同步 → 检查 `import` 语句对应的包是否在 requirements.txt
- **重启后用户数据丢失**：这是预期行为；session 不持久。请把数据写回 Sheets

### CSV 上传后视图没更新

- 上传后系统会自动切换数据源（看「📊 运营视图」hero 区的"数据源"标签）
- 若仍看到旧数据，检查浏览器缓存或硬刷新（Cmd+Shift+R / Ctrl+F5）

---

## 开发

### 跑测试

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

32 个核心数据流测试覆盖：CSV 识别、字段标准化、互动率/follower_growth 计算、API 基类继承。

### CI

`.github/workflows/ci.yml` 在每次 push 到 `main` 或 `claude/**` 分支时自动跑 pytest + Streamlit AppTest smoke。

### 加新平台 / 改字段

1. 标准字段定义在 `utils/data_loader.py` 的 `STANDARD_COLS` 上方注释表
2. 新平台 API 集成：继承 `utils.api_base.APISourceBase`，参考 `utils/youtube_api.py` 的结构
3. 改完跑 `pytest tests/` 确保没破现有逻辑

### 开发流程参考

详见 `CLAUDE.md`（项目规则、字段映射、衍生公式、完成定义）。Long-running coding agent workflow 用 `feature_list.json` + `claude-progress.md` 维护状态。

---

## 项目结构

```
dataset/
├── app.py                          # Streamlit 首页
├── generate_sample_data.py         # 示例数据生成器
├── init.sh                         # 一键环境检查
├── requirements.txt                # 运行依赖（版本锁定）
├── requirements-dev.txt            # 开发依赖（pytest）
├── pages/
│   ├── 1_📊_运营视图.py            # 日常运营 KPI / 趋势 / 排行
│   ├── 2_📈_汇报视图.py            # 周/月/季度汇总 + 导出
│   └── 3_📤_数据导入.py            # CSV / 手动录入 / API / Sheets 同步
├── utils/
│   ├── api_base.py                 # API 模块基类（统一 secrets / HTTP / 重试）
│   ├── data_loader.py              # CSV 读取 + 自动识别 + 标准化
│   ├── data_cleaner.py             # 数据清洗
│   ├── data_sources.py             # 数据源优先级（上传 > Sheets > 本地）
│   ├── linkedin_api.py             # LinkedIn Company Page
│   ├── logging.py                  # emit_warning / emit_error（Streamlit-aware）
│   ├── meta_graph.py               # Meta Graph API (FB + IG)
│   ├── metrics.py                  # 互动率 / follower_growth / 周期聚合
│   ├── tiktok_api.py               # TikTok Business API
│   ├── ui.py                       # 共享视觉组件 + PLATFORM_LABELS
│   └── youtube_api.py              # YouTube Analytics API
├── tests/
│   ├── conftest.py
│   └── test_data_pipeline.py       # 32 个核心数据流测试
├── scripts/
│   └── youtube_auth.py             # 一次性 YouTube OAuth 助手
├── data/
│   ├── samples/                    # 示例 CSV（已 commit）
│   └── *.csv                       # 真实数据（gitignore）
├── .streamlit/
│   ├── config.toml                 # 主题
│   ├── secrets.toml.example        # 凭据模板
│   └── secrets.toml                # 实际凭据（gitignore）
├── .github/workflows/ci.yml        # CI pipeline
├── CLAUDE.md                       # Agent 工作指令
├── feature_list.json               # 功能状态
└── claude-progress.md              # 会话进度日志
```

---

## 给 Claude Code 开发者

本项目设计用于 long-running coding agent 工作流。每次开工前：

1. 读 `CLAUDE.md`：项目规则、字段映射、衍生公式、完成定义
2. 跑 `bash init.sh`：环境检查 + 当前状态摘要
3. 查 `feature_list.json` + `claude-progress.md`：上轮已验证状态 + 下一步

写完功能后：
- 更新 `feature_list.json` 加 evidence
- 追加 `claude-progress.md`
- commit + push，保证下一轮 session 能 `bash init.sh` 重启

---

## License

内部使用，未公开发布。
