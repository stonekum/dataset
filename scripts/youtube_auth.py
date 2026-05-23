"""一次性 YouTube OAuth 授权脚本。

在你自己的电脑上本地运行，获得 refresh_token，填入 secrets.toml 后即可让
Streamlit Cloud 永久拉取 YouTube Analytics 数据。

使用步骤：
  1. 安装依赖（只需一次）：
       pip install google-auth-oauthlib

  2. 在 Google Cloud Console 做准备：
       a. 前往 https://console.cloud.google.com/
       b. 创建项目（或复用现有项目）
       c. 搜索并启用 "YouTube Data API v3" 和 "YouTube Analytics API"
       d. 左侧 → APIs & Services → OAuth consent screen
          - User Type 选 External → 填 App name / User support email
          - Scopes 步骤：点 Add or Remove Scopes → 搜索 youtube.readonly + yt-analytics.readonly 勾上
          - Test users：添加你自己的 Gmail 邮箱
       e. 左侧 → Credentials → Create Credentials → OAuth client ID
          - Application type 选 Desktop app → 下载 JSON 文件
       f. 把下载的 JSON 文件放到本脚本同目录，改名为 client_secret.json

  3. 运行本脚本：
       python scripts/youtube_auth.py

  4. 浏览器会打开授权页面，选你的 YouTube 频道关联的 Google 账号 → 允许
     运行完成后，终端会打印 refresh_token

  5. 把以下内容填入 .streamlit/secrets.toml（或 Streamlit Cloud Secrets）：

       [youtube]
       client_id     = "从 client_secret.json 里的 client_id"
       client_secret = "从 client_secret.json 里的 client_secret"
       refresh_token = "脚本输出的 refresh_token"
"""

import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("缺少依赖，请先运行：pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

CLIENT_SECRET_FILE = Path(__file__).parent / "client_secret.json"
if not CLIENT_SECRET_FILE.exists():
    print(f"找不到 {CLIENT_SECRET_FILE}，请先把 OAuth client JSON 放到该路径。")
    sys.exit(1)

flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), scopes=SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

with open(CLIENT_SECRET_FILE) as f:
    secret_data = json.load(f)
web_or_installed = secret_data.get("web") or secret_data.get("installed", {})

output_toml = (
    "[youtube]\n"
    f'client_id     = "{web_or_installed.get("client_id", "")}"\n'
    f'client_secret = "{web_or_installed.get("client_secret", "")}"\n'
    f'refresh_token = "{creds.refresh_token}"\n'
)

# Tier 3.4：写到本地文件而非 stdout，避免 token 进入终端历史或 CI 日志
OUTPUT_PATH = Path(__file__).parent / ".youtube_token.toml"
OUTPUT_PATH.write_text(output_toml)
try:
    OUTPUT_PATH.chmod(0o600)  # 仅当前用户可读写
except (OSError, NotImplementedError):
    pass  # Windows 上 chmod 行为不同，忽略

print("\n" + "=" * 60)
print("✅ 授权成功！")
print("=" * 60)
print(f"凭证已写入：{OUTPUT_PATH}")
print()
print("下一步：把该文件内容整段复制到 .streamlit/secrets.toml")
print("（或 Streamlit Cloud → App Settings → Secrets）")
print()
print("⚠️  安全提示：")
print("   - .youtube_token.toml 已在 .gitignore 中，请勿手动提交到 git")
print("   - refresh_token 永久有效，泄露后必须到 Google Cloud Console 撤销")
print("   - 用完可以删除此文件")
print("=" * 60)
