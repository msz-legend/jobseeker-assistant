# Template: base（默认中文简历模板）

- **Type:** CV
- **渲染器:** `tools/build_cv.py`（python-docx，无外部二进制依赖）
- **Source extension:** `.json`（内容 spec，由 /apply Step 2 依照 05-cv-drafting.md 生成）
- **样式文件:** `style.json`（本目录；字体/字号/页边距全部集中在这里）
- **Page limit:** 1 页（≤5 年经验）；>5 年经验可 2 页，manifest 改 `pages_target`
- **Fonts:** 微软雅黑（标题）/宋体（正文），Windows 系统字体；macOS 回落苹方/PingFang 需在 style.json 改
- **Spec 示例:** `spec.example.json`（占位符齐全，/setup 与 /apply 直接复制改写）

## 版式规则（渲染器已实现，草案人不用手工编译）

- 页面 A4；页边距上/下 1.6cm、左右 1.5cm；正文 10.5pt，行距 ≈1.15，紧凑但可读
- 姓名居中 18pt 微软雅黑加粗；联系方式一行 9pt 居中灰色
- 板块标题 12pt 加粗 + 下划横线（pBdr），前 8pt / 后 2pt 间距
- 经历条目：公司·职位（11pt 加粗）+ 日期/城市右对齐（tab stop 至内容宽度右缘）
- 每条经历/项目 = 动作 + 量化结果；bullet 主语（`Go：`、`主导…：`）自动加粗
- 禁止：照片（除非渠道硬要求）、表格嵌套、彩色多栏、页眉页脚
- 弹性排布：1 页版（≤5 年经验）砍掉「证书与奖项」；2 页版允许 项目经历扩到 4 条

## Known pitfalls

- 内容超出页数时 build 不报错——`/apply` Step 5 必须跑 `verify_resume.py --pdf --pages N` 才发现
- `pages_target` 只存在于 meta，渲染器不读；页数约束走 manifest + verify
- WPS 打开正常，Word 打开正常；在线预览（BOSS/猎聘）用 PDF 导出后再投
