# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-25

### Added

- **DOCX 简历管线**：`tools/build_cv.py`（python-docx 渲染内容 spec → 中文简历 DOCX）、
  `tools/docx_text.py`（零依赖 DOCX 文本抽取）、`tools/verify_resume.py`
  （文本级校验 + 可选 Word COM / LibreOffice 转 PDF 后页数与文字校验）。
- **`tools/salary_band.py`**：解析中文薪资表述（`20-35K×15`、`2.5-4万×14`、`63w/年`）
  并按候选人底线（读自 01 简历档案字段，绝不硬编码）给出 pass / fail / needs_review。
- **打招呼话术工作流**：`06-greeting-templates.md`。打招呼是默认动作；正式求职信
  仅在 JD 明确要求或外企机会时生成。
- **中国面试阶段词汇与跟进阈值**：笔试 / 电话沟通 / 一面 / 二面 / 三面 / HR面 / OC / 背调，
  写入 `/interview`、`/outcome` 与 tracker 的 `stage` 列；BOSS 站内信 5–7 天、
  邮件 10 天、猎头按约定。
- **岗位 JD 档案体系**：`documents/postings/`（`_TEMPLATE.md` + `_index.md` via
  `tools/posting_index.py`），JD 原文粘贴优先，评估/改简历/面试定向都以原文为准。
- **`/intake` 通用收件箱**：SHA-256 幂等台账工具与申请工作区 README，
  处理只记台账、不移动原文件。
- **`/mock` 交互式模拟面试**：一次一题的交互式模拟与 mock 状态机、
  错题索引生成器及对应单元测试。
- **generic 与 software-engineering 可插拔 domain pack**：领域专业问题按包加载，
  无匹配包时回落 generic。
- **`/interview`**：消费 mock/review 结果按缺口定向生成准备包；
  无结果时显式标注「未经模拟面试校准」。
- **`/outcome`**：记录结果与跟进、补强未答好项；新错题写入申请工作区 `mistakes/`，
  错题索引生成器统计 recurrence，历史错题本保留为归档。
- **`AGENTS.md` 升为唯一规则入口**（agent 中立）：锚定目录、单一事实来源表、
  只在仓库内读写、硬边界、约定、备份、版本校验。`CLAUDE.md` 降为零个人信息的
  转发页（`@AGENTS.md` 导入）。候选人档案唯一源为 `01-candidate-profile.md`（不入库），
  `/setup`、`/apply`、`/rank`、`/reset`、`salary_band.py` 全部只读这一处。
- **`/html-report`（`tools/html_report.py`）**：申请漏斗与汇总 HTML 看板。
- **学习-保持流水线（LRP）子系统接入**：README 目录树、`docs/USER_GUIDE.md` 与
  AGENTS §1 单一事实来源表各留指针，指向 `learning-retention-pipeline/SKILL.md` 与
  `docs/spec-lock.md`；规范内容以 LRP 自述为准，不复制副本。
- **`tools/backup_docs.ps1`**：`documents/` 是唯一副本且不入库，此脚本打包到
  `%USERPROFILE%\Backup\jobseeker-assistant`（用户主目录下，脚本默认值为单一事实来源，
  可用 `-Dest` 覆盖），保留最新 10 份。
- **公开文档体系**：重写 README、SETUP、SECURITY 和贡献说明，补充从初始化到投递、
  模拟面试、复盘的完整使用流程；新增 `docs/USER_GUIDE.md` 与
  `docs/COMMAND_REFERENCE.md`，统一 `/intake`、`/mock`、`/interview`、`/outcome` 的公开用法。
- **测试**：`tests/` 覆盖 salary_band / docx_text / build_cv / job_key / scrape_state /
  posting_guard / robots_check / lint_skills / html_report 等。

### Changed

- 所有问卷、评估、话术、面试准备、跟进的用户可见输出默认中文。
- 渠道词汇：BOSS 直聘 / 猎聘 / 拉勾 / 智联 / 前程无忧 51job / 公司官网招聘页 /
  脉脉 / 牛客；`linkedin-search` 保留用于外企与海外机会（零依赖、通用国家）。
  内推线索生成改为 Bing 站内检索 + 牛客搜索 + 官网检索链接（只建链接、从不抓取）。
- Windows 友好：`python`（非 `python3`）约定、固定临时目录约定，简历管线以 DOCX 为准，
  不依赖任何排版引擎。
- `/add-template` 面向 DOCX/其他 CLI 工具链。
- tracker 列改动：`greeting_file` 取代求职信文件列，新增 `stage` 列。
- **评分规则落成可查的硬约束（04 方法论）**：
  - §2.1 Must-have 矩阵：评分前逐条映射 JD「必须项」，四态（命中 / 部分命中 / 缺失 /
    无法判断），缺失再分硬缺与软缺；加分项不得抵消必须项缺失。
  - §2.2 封顶规则：硬缺 1 条 → 技术栈≤60、总分≤69；硬缺 ≥2 条或核心能力整条缺失 →
    技术栈≤45、总分≤59；仅软缺不封顶，但须写出映射依据。
  - §2.3 超配与形态错配：年限高于 JD 上限不是加分项，经验维度不得进 61-85，
    强制输出 `超配风险` 行 + 必答问题「是否接受该岗位的职级与薪资定位？」；
    配套结构化标签 `overqualified_risk` / `role_shape_mismatch` / `salary_mismatch_risk`。
  - §2.4 评估置信度：`partial` → `evaluation_confidence: low`、`materials_allowed: false`。
  - §六 四行强制审计字段：必须项映射 / 封顶触发 / 超配风险 / 风险评估置信度；
    缺任一行视为评估未完成。
  - `_TEMPLATE.md` 新增 `evaluation_confidence` 与 `materials_allowed` 两个字段。
- **partial 语义贯流**：`/apply` Step 0 收尾检查禁止残余 `partial` 进 Step 2
  （定向简历 / 打招呼语；用户坚持投递时须记录缺失项与放行理由，且禁止做软缺映射）；
  `/rank` Step 5 中 `partial` 候选照常进榜但标 `⚠️JD不完整` 且不计入 Top3 推荐；
  `/scrape` 收尾给出 `partial` 的客观判定——必备字段 8 项，缺 ≥2 判 partial、
  缺 1 判 full 但标注、缺 ≥4 拒绝评估；截图转录/转载一律 partial。
- 核心命令改用职业中立的三阶段命名；`$ARGUMENTS` 改为通用「命令参数」，
  `SKILL.md` frontmatter 的 `allowed-tools` 作为可移植字段保留（未知键对其他 runtime 无害）。
- 仓库外的个人目录冻结为历史归档：工作流不读、不写、不比对。
- 框架版本演进至 1.5.5（AGENTS.md）。

### Fixed

- `tools/html_report.py` 对 stdout/stderr 强制 UTF-8，修复 Windows（cp936）下
  测试断言因中文 stderr 解码失败而误报。
- html_report 漏斗阶段词表与 canonical 八枚举对齐；STAGES 外的阶段（含历史
  `offer确认`）聚合进「其他」行，不再静默消失。
- 面试阶段词表书写形态统一（HR 与「面」之间的空格去掉）。
- `tools/backup_docs.ps1` 默认目的地改为运行时求值的
  `%USERPROFILE%\Backup\jobseeker-assistant`（不写死固定盘符，文档描述以脚本默认值为准）。
- 补齐归档中缺失的 `一面模拟_团队Leader视角_2026-10-16.md`，
  `documents/interview/` 文件集对齐。
- 去本机化：文档与工具不再依赖写死的本机路径。

### Fallback（设计取舍，不修）

- `salary_band` 按区间**上限**判 pass —— BOSS 等平台常见「按区间下限压价」，但上限达标
  即说明薪资天花板够，不因此改判；下限低于底线只在评估表里做风险提示。
- 硬门槛**不设年限上限** Gate —— 「2-5 年」在国内常是弹性表述，机械判死会误伤资历强的
  候选人；改由 §2.3 超配规则处理（不 fail，但输出风险与必答问题）。
- **不回填既有 posting 的历史分数**，新规则只对之后跑 /rank、/apply 的岗位生效，
  保证历史评估前后可比。
