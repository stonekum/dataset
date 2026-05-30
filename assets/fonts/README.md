# 内置字体

## WenQuanYiZenHei.ttf（文泉驿正黑）

- 用途：汇报视图 PDF 导出（`utils/pdf_report.py`）的字形嵌入。
- 为什么自带：reportlab 的 `TTFont` 只支持 TrueType(glyf) 轮廓字体，且其内置的
  CID 字体（STSong-Light）不嵌入字形、依赖查看器自带 Adobe 字体包，很多查看器会
  渲染成空白。嵌入一个真实 TrueType 字体可保证本地与 Streamlit Cloud 都正确显示。
- 为什么选它：单个 TTF 同时覆盖**拉丁字母 + 数字 + 中日韩**——汇报里既有中文标签
  又有大量数字/英文平台名，需要一个字体全包。（纯 CJK 回落字体如 Droid Sans
  Fallback 缺拉丁/数字字形，数字会变空白。）
- 导出 PDF 时 reportlab 只子集化实际用到的字形，输出文件很小（~十几 KB）。
- 许可证：GPL v3 + 字体嵌入例外（Font Embedding Exception），明确允许嵌入文档与
  再分发。
