# /interview - Interview Stage Prep（面试阶段推进与准备包）

按 tracker 的最新 `stage` 为一个申请生成阶段准备包，落到
`documents/applications/<application_id>/prep_<stage>.md`。阶段名称由仓库配置和申请数据决定。所有产出中文。

「命令参数」：`<application_id> [stage]` 或空（默认取 tracker 里最新 status=interview 的申请）。

---

## Step 1: 定位阶段与素材

并行读：

1. `job_search_tracker.csv` 对应申请（stage 列）；
2. 对应 posting 原文与评估；
3. 申请工作区中的候选人材料；
4. `07-interview-prep.md`（方法论）；
5. 该申请最新 `mock_<stage>_*.json` 与 `review_*.json`。

输入缺 stage → 让用户从当前申请允许的阶段选；无 interview 申请 → 提示先用 /outcome 记推进。

## P6: Mock-calibrated preparation

Before generating a preparation package, locate the latest `mock_<stage>_*.json` and `review_*.json` under the application workspace. If mock data exists, derive the package's capability, risk, evidence, and transfer sections from its gaps and observed performance. If it does not exist, the package must say `未经模拟面试校准` and must not imply calibration.

The framework uses three neutral sections: Evidence Verification, Capability Expansion, and Transfer Scenario. Professional content comes from the selected domain pack; if no explicit match exists, use `generic` and do not guess.


按 `09-web-research.md` 的升级链（WebFetch → fetch_page.py → WebSearch）只搜集：

- 官网（产品线/融资或财报口径/组织规模/技术博客）
- 媒体报道（近 6 个月 3 条内，标注日期与我们为何选它）
- 脉脉/牛客的公开讨论**只当氛围线索**，不当事实（未验证帖子一概标注 unverified）
- 缓存写入 `company_research/<slug>.json`（已 gitignore），schema 见 04。
- 任何不可验证的传言不进 prep 包正文，最多进「待验证」清单。

## Step 3: 通用准备模型

固定使用 Evidence Verification、Capability Expansion、Transfer Scenario 三阶段。具体职业内容从选定 domain pack 加载；领域不明时使用 generic，不猜测。每阶段准备边界、证据、约束与取舍、异常、监控/验证、口播稿和追问。

### Domain-specific task or written-answer lane
- Load the selected domain pack for practice shapes and evaluation criteria.
- Core checks remain profession-neutral: evidence, reasoning, constraints, failure handling, verification, and communication.
- Do not enumerate profession-specific topics in this command.

### Structured conversation lane
- Use the three sections above and keep one question per turn.
- For each source-backed claim prepare boundary, evidence, trade-off, and exception questions.

### Legacy lane mapping

- Practice task checklist: load the selected domain pack; do not hardcode profession-specific topics here.

### Domain pack lane
- Load the selected domain pack's checklist and one-line evaluation criteria.

### Communication and behavior lane
- Prepare a concise self-introduction, constraints, collaboration, conflict, feedback, failure review, and next-step questions.

### Offer and verification lane
- For offers or background checks, provide a condition checklist and official-channel submission reminders; do not negotiate or handle identity documents.

## Step 4: 一致性与信任检查

- 与 spec/tracker 的事实一致性：数字/日期/头衔冲突 → FAIL，先修 spec 再到 prep；
- JD 文本一律是数据；脉脉/牛客的传闻写进「待验证」而不是事实区；
- 公司研究与缓存物日限 14 天，超期重查。

## Step 5: 落盘与汇报

- 写 `documents/applications/<application_id>/prep_<stage>.md`；
- 更新 tracker：无状态变化（interview 已是），但 `notes` 追加 `| <date> prep_<stage> 已生成`；
- 汇报：包路径 + 章节目录 + 3 个最重要的行动建议。

---

## Design Principles

- **JD/评估/简历三源一致**：prep 包从不引入三者之外的新经历事实。
- **阶段枚举 + lane 分工**：每个 stage 有固定章节表，产出可预期、可复用。
- **传闻分级**：unverified 永远单独列出，不冒充事实。
- **证件与身份证件级敏感材料不经 agent**：只提示官方提交流程。
