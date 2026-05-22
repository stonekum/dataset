# 海外社媒数据面板

团队海外社交媒体运营数据的统一展示面板，支持六个平台（Instagram、TikTok、YouTube、X、Facebook、LinkedIn）。基于 Streamlit + pandas + plotly，单仓库部署到 Streamlit Community Cloud。

## 快速开始

### 本地运行

```bash
# 1. 克隆仓库
git clone <repo-url>
cd social-media-dashboard

# 2. （可选）创建虚拟环境
python3 -m venv .venv && source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 生成示例数据（首次运行；仓库已附带，无需也可跳过）
python generate_sample_data.py

# 5. 启动面板
streamlit run app.py
```

或者一键运行环境检查：

```bash
bash init.sh
```

### 更新数据

1. 从 Metricool 或各平台原生 Analytics 导出 CSV
2. 将 CSV 文件放入 `data/` 目录（**注意：`data/` 下的 CSV 默认 gitignore，不会被提交**；仅 `data/samples/` 下的示例 CSV 会进入版本控制）
3. 刷新浏览器页面，Streamlit `@st.cache_data` 会在源文件改变时自动重载

字段映射规则、各平台原生导出字段对照表见 `CLAUDE.md`。

## 部署到 Streamlit Community Cloud

### 准备

- 已有 GitHub 仓库托管本项目
- Streamlit 账号已绑定 GitHub（首次访问 [share.streamlit.io](https://share.streamlit.io) 时授权）

### 步骤

1. 把本仓库推送到 GitHub（公开或私有皆可）
2. 在 [share.streamlit.io](https://share.streamlit.io) 点击 **New app**
3. 配置：
   - **Repository**：`<your-github>/social-media-dashboard`
   - **Branch**：`main`（或你部署用的分支）
   - **Main file path**：`app.py`
   - **Python version**：3.10 或 3.11（默认即可）
4. 点击 **Deploy**

云端会读取 `requirements.txt`（已用 `==` 锁定版本）+ `.streamlit/config.toml`（主题），与本地行为一致。

### 更新数据后的部署流程

- 真实运营数据：在本地把 CSV 放进 `data/`，本地运行验证后，**不要把 CSV 提交到 git**（已 gitignore）；生产数据应该通过 Streamlit Cloud 的 Secrets 或挂载方式注入，或者在 fork 的私有仓库里手工 commit（仍受 gitignore 保护，需要临时移除规则）
- 示例数据更新：修改 `generate_sample_data.py` 后重跑、提交 `data/samples/*.csv`，push，Streamlit Cloud 自动重新部署

### 常见问题

- **图表中文乱码**：Streamlit Cloud 默认无中文字体，已在主题配置使用 `sans serif` 字体族，可在浏览器侧渲染中文，无需额外字体包
- **CSV 中文乱码（Excel 打开导出文件）**：报告下载的 CSV 已附加 UTF-8 BOM，Excel 能直接识别
- **数据为空**：检查 `data/` 与 `data/samples/` 至少有一个目录包含 CSV，且表头能匹配 `utils/data_loader.py` 中的指纹（六平台原生 + Metricool 统一格式）

## 面板页面

- **首页 (`app.py`)**：项目概览、数据状态摘要、平台覆盖
- **📊 运营视图 (`pages/1_📊_运营视图.py`)**：日常运营 KPI 卡片、互动率趋势折线图、平台表现排行表；侧边栏含平台多选 + 日期范围
- **📈 汇报视图 (`pages/2_📈_汇报视图.py`)**：月度/季度汇总、自动文字摘要、跨平台对比柱状图、粉丝增长曲线；底部提供 CSV/Markdown 报告下载（PDF 导出已推迟，见 `feature_list.json` 的 F07）
- **📤 数据导入 (`pages/3_📤_数据导入.py`)**：拖拽上传 CSV（无需碰仓库），可选写回 Google Sheets 实现跨 session 持久化

## Google Sheets 持久化（可选，F10）

运营同事无需碰仓库即可更新数据：在「📤 数据导入」页上传 CSV → 点「写回 Google Sheets」→ 任何设备打开仪表盘都能看到。

### 一次性设置

1. 新建 Google Sheet，第一行表头使用标准列名：
   `date | platform | followers | impressions | reach | likes | comments | shares | saves | posts_count`
2. 到 [Google Cloud Console](https://console.cloud.google.com/) 新建项目，启用 **Google Sheets API** 与 **Google Drive API**，创建 Service Account 并生成 JSON 密钥（**全程免费**）
3. 把 Sheet 共享给 Service Account 邮箱（`xxx@xxx.iam.gserviceaccount.com`），权限选「编辑者」
4. 填写 Secrets：
   - 本地：复制 `.streamlit/secrets.toml.example` 为 `.streamlit/secrets.toml`（已 gitignore），填入 Sheet URL + Service Account JSON 内容
   - Streamlit Cloud：到 App Settings → Secrets 粘贴同样内容

未配置 Secrets 时该功能不可见，应用仍正常运行（数据源回落到本地 CSV）。

## 数据来源

- **Metricool**（推荐）：一站式连接六个平台，导出统一格式 CSV（含 Account/Network/Date 列）
- **各平台原生 Analytics**：作为补充数据源；表头不同，由 `utils/data_loader.py` 自动识别并映射

## 项目结构

```
social-media-dashboard/
├── app.py                          # Streamlit 主入口（首页）
├── generate_sample_data.py         # F02 示例数据生成器（可重跑、固定 seed）
├── init.sh                         # 一键环境初始化与状态检查
├── requirements.txt                # 依赖（版本锁定）
├── pages/
│   ├── 1_📊_运营视图.py
│   ├── 2_📈_汇报视图.py
│   └── 3_📤_数据导入.py            # F09 拖拽上传 + F10 Google Sheets 同步入口
├── utils/
│   ├── data_loader.py              # F03 CSV 读取与来源自动识别
│   ├── data_cleaner.py             # F04 数据清洗（负值截断、缺失填充、异常标记）
│   ├── metrics.py                  # F04 衍生指标（互动率、粉丝增长、周/月环比、周期聚合）
│   └── data_sources.py             # F09/F10 数据源抽象（上传/Sheets/本地优先级）
├── data/
│   ├── samples/                    # 示例 CSV（已提交，6 个平台 × 90 天）
│   └── *.csv                       # 真实运营数据（gitignore）
├── .streamlit/
│   ├── config.toml                 # 主题与服务器配置
│   ├── secrets.toml.example        # Google Sheets 凭据模板（复制为 secrets.toml 使用）
│   └── secrets.toml                # 实际凭据（gitignore）
├── CLAUDE.md                       # AI Agent 工作指令（字段映射表、公式、规则）
├── feature_list.json               # 功能状态唯一事实来源
├── claude-progress.md              # 会话进度日志
└── session-handoff.md              # 会话交接摘要
```

## 给 Claude Code 开发者

本项目使用 Harness Engineering 方法管理 AI Agent 工作流。开始工作前请：

1. 阅读 `CLAUDE.md`（项目规则、字段映射、衍生公式、完成定义）
2. 运行 `bash init.sh`（环境检查 + 当前状态摘要）
3. 查看 `feature_list.json` 与 `claude-progress.md` 确认上一轮已验证状态和下一步
