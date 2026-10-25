---
company: "[公司名]"
role: "[岗位名]"
city: "[工作城市]"
channel: "[BOSS 直聘/官网/猎聘/内推/截图转录]"
url: "[JD 链接，没有则留空]"
salary_raw: "[薪资原文，如 20-35K×15]"
jd_completeness: full   # full=原文完整粘贴 | partial=转录/摘要
evaluation_confidence: ""  # high | low（partial 时为 low，/apply Step 0 写入）
materials_allowed: ""      # true | false（partial 时为 false，禁止进入材料生成）
posted_at: "[发布日期，未知留空]"
archived_at: "[归档日期 YYYY-MM-DD]"
status: inbox           # inbox | evaluated | applied | interview | offer | closed
fit: ""                 # /apply Step 1 / /rank 写入
tracker_row: ""         # /apply Step 6b 写入 date
---

<!-- ══════════════ 以下为 JD 原文，整段粘贴，不要转写不要总结 ══════════════ -->

[JD 原文粘贴区：岗位职责 / 任职要求 / 薪资福利 / 其他]

<!-- ══════════════ 原文结束。以下各节由命令写入，不要手改 ══════════════ -->

## 信任门（posting_guard）

<!-- /apply Step 0 运行 posting_guard 后粘贴 verdict 行 -->

## 评估（/apply Step 1 / /rank）

<!-- 粘贴四维评分表 + Gates + 红旗 + 总分与建议 -->

## 应用记录

<!-- /apply Step 6b：tracker 日期；/outcome 追加 `| <date> <事件>` -->
