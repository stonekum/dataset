# 海外社媒数据面板

团队海外社交媒体运营数据的统一展示面板，支持六个平台（Instagram、TikTok、YouTube、X、Facebook、LinkedIn）。

## 快速开始

### 本地运行

```bash
# 1. 克隆仓库
git clone <repo-url>
cd social-media-dashboard

# 2. 安装依赖
pip install -r requirements.txt

# 3. 生成示例数据（首次运行）
python generate_sample_data.py

# 4. 启动面板
streamlit run app.py
```

### 更新数据

1. 从 Metricool 导出本周数据（CSV 格式）
2. 将 CSV 文件放入 `data/` 目录
3. 刷新浏览器页面，数据自动更新

如果使用平台原生 Analytics 导出的 CSV，同样放入 `data/` 目录即可，系统会自动识别来源并统一格式。

## 部署到 Streamlit Cloud

1. 将本仓库推送到 GitHub
2. 访问 [share.streamlit.io](https://share.streamlit.io)
3. 选择仓库，主文件填写 `app.py`
4. 点击 Deploy

后续更新数据：将新 CSV 放入 `data/` 目录，commit 并 push 到 GitHub，Streamlit Cloud 自动重新部署。

## 面板页面

- **首页**：项目概览和数据总览
- **运营视图**：日常运营数据，含 KPI 卡片、趋势图、内容排行
- **汇报视图**：月度/季度汇总，含跨平台对比、增长曲线、PDF 导出

## 数据来源

- **Metricool**（推荐）：一站式连接六个平台，导出统一格式 CSV
- **各平台原生 Analytics**：作为补充数据源

## 项目结构

```
social-media-dashboard/
├── app.py                  # Streamlit 主入口
├── pages/                  # 子页面
├── utils/                  # 数据处理模块
├── data/                   # 数据目录
│   └── samples/            # 示例数据
├── .streamlit/             # Streamlit 配置
├── CLAUDE.md               # AI Agent 工作指令
├── feature_list.json       # 功能追踪
└── claude-progress.md      # 开发进度日志
```

## 给 Claude Code 开发者

本项目使用 Harness Engineering 方法管理 AI Agent 工作流。开始工作前请：

1. 阅读 `CLAUDE.md`
2. 运行 `bash init.sh`
3. 查看 `feature_list.json` 确认当前优先任务
