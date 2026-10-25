# /intake - Inbound Intake

批量入口：先读取 `documents/inbound/`，再调用 stdlib 工具记录 SHA-256 台账并按输入分组。原文件不移动、不删除。

命令参数可为空，或指定一个批量文本文件。岗位之间可用一行 `---` 分隔；每段至少保留标题和原文，字段不足的段标记为 `needs_review`，不猜测缺失事实。

流程：

1. 扫描 `materials/` 与 `jd-batch/`。
2. `python tools/intake_manifest.py scan documents/inbound --manifest documents/_inbox_manifest.json`。
3. 工具层：`python tools/intake_split.py` 的 `split_segments()` 负责可重复拆分；批次处理只在全部段落完成后重建一次索引。
4. 用 `tools/job_key.py` 去重，并在批次结束后只重建一次 postings 索引。
5. 报告新建、重复、需确认和失败；原始文件保持原位。

manifest 的 `status` 只允许 `raw | parsed | filed | skipped | failed`，同 SHA-256 重跑必须幂等为 `skipped`。
