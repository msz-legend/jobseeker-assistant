# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **`/dispatch-resume` 受控自动投递（Android 真机）**：`tools/chat_resume_dispatch.py`
  （list/send 两阶段 + 人工 approved 审核门 + 风控即停）+ `tools/chat_resume_ladder.py`
  （语言栈→简历版本纯函数）+ `config/resume_ladder.json`（有序阶梯 Java > Go > Python；
  Java→JAVA 简历，Go/Python→GO 简历；三者都未提供则兜底 GO 简历（2026-11-26 移除语言硬过滤））。
  设计见 `docs/superpowers/specs/2026-11-23-chat-resume-dispatch-design.md`。
  `AGENTS.md` §4 增加唯一例外条款（用户已授权改规则）。
- **`documents/dispatch/**` 个人数据忽略**（审核队列/台账/风控现场）。
- **`/dispatch-resume` 四层过滤 + 视觉识别输入**：早期首屏误判 BOSS/猎聘列表都是
  WebView 自绘；后续真机确认 **BOSS 列表 UI 树可读、仅猎聘自绘**。`list` 的
  `--from-vision` 接受猎聘截图转录的结构化候选；`config/resume_ladder.json` 增加
  明确索要/外包(猎头人力咨询)/仅北京/非算法岗四层过滤，被屏蔽条目附原因输出。
- **`/dispatch-resume` verify 阶段（只读核实）**：`verify` 子命令自动启动 BOSS、按
  联系人滚动定位并逐个打开候选会话，对**会话详情全文**重跑四层过滤与语言栈阶梯——
  列表摘要截断会掩盖只出现在聊天正文里的信号（如「这边是某外包公司」、异地城市）。
  结论与详情文本证据写回队列（`verified/detail_text/verdict/resume_changed`，判 skip
  则 `skipped+skip_reason`）；`approved/sent` 一律不动，发送仍走人工审核门。
  定位失败标 `unverified` 交人工；命中风控立即停并存证。全程不点「发简历」。
- **`/dispatch-resume` rescreen 阶段（规则变更后重筛）**：`rescreen` 读取已保存的逐会话
   JSONL 证据，按当前配置重跑四层过滤与语言栈阶梯，输出全新的未批准队列；所有
   `approved/sent` 重置，避免把旧扫描报告或旧 approval 当成发送授权。`--report`
   生成按联系人+公司去重的人工审核清单，明确标注“这不是发送授权”；`--overwrite`
   必须显式给出，避免覆盖审核队列。
- **`/dispatch-resume` recent 阶段（近一周范围）**：`recent` 从已保存的 BOSS 列表 XML dump 读取 `tv_time_v2`，以抓取日解析相对时间标签（裸 `HH:MM`/昨天/星期X/M月D日），只保留 `[as_of-(days-1), as_of]`（默认 7 天）内的会话；时间缺失或无法解析一律排除。输出独立未批准队列与“这不是发送授权”的人工审核清单；`send` 额外要求 `recent_window: true`，防止旧 approval 绕过近一周范围。
- **`/dispatch-resume` send 自动定位**：`--auto-open` 在发送前按联系人从 BOSS「全部」列表定位并打开会话，定位不到立即停；无需人工先把每个会话打开。人工审核与版本勾选校验保持不变。
- **`/dispatch-resume` 拟人化停顿**：设备交互的导航、打开会话、简历 picker、选版本、
  投递前、简历确认后到文案输入、候选人之间（8–20 秒）改为有界随机停顿，轮询确认
  仍用短固定间隔；命中风控立即停且不再停顿。新增全局 `--no-humanize` 供排障/测试。
- **`/dispatch-resume` 定时任务单一入口 `run`**：`tools/chat_resume_dispatch.py`
  新增 `run` 子命令，一条命令完成 BOSS「全部」逐会话扫描 → 当前规则 `rescreen`
  → 列表时间 `recent` → 通过条目自动 `approved:true` → `send --auto-open`（含
  ADBKeyboard 补充文案与拟人化停顿）。用户已明确授权定时任务自动批准，其他安全门
  不变；扫描覆盖须由「以上是30天内的联系人」或「整屏会话都早于近一周截止日」之一确认，
  否则停止且不发送；任一步命中风控/设备错误同样停止且不发送。`--max-send` 限制单次数量，
  `--out-dir` 保存全部证据/队列/摘要；旧
  `open_all_details.py` 仅作历史证据工具，不再作为流程入口。后续按用户要求改为
  **逐会话即时发送**（见下方 Added 条目）。
- **`/dispatch-resume` run 扫描前冷启动**：`run` 现在先 `force-stop com.hpbr.bosszhipin`
  再重新启动，检测到登录页或验证码/安全验证页立即停止；只有确认进入「消息 → 全部」
  才开始逐会话扫描。不清除 App 数据，其他手动子命令不增加重启行为。
- **`/dispatch-resume` 扫描屏数配置化**：`run` 默认扫描上限由 `config/resume_ladder.json`
  的 `scan.max_screens` 控制，默认 5 屏；`--max-screens N` 仍可显式覆盖，非法值立即报错。
  达到上限仍未确认扫描覆盖（30 天底部或整屏早于近一周截止日）仍判 `scan_incomplete`
  且不发送。
- **`/dispatch-resume` 卡片/文本 OR 判定与来源留痕**：对方索要简历可由 BOSS 平台卡片
  （“我想要一份您的附件简历，您是否同意”＋“拒绝/同意”）或文本动作命中，任一命中即
  进入后续筛选/发送；两者都未命中则不发送、不回复。`request_source` 记录 `card`/
  `text`/`card+text` 并写入 rescreen/recent/run 报告；已发送负样本优先于两者。
- **`/dispatch-resume` 按时间窗口提前结束扫描**：真机确认 BOSS 长列表上「以上是30天内的
  联系人」几乎不可达（120/90/15 屏均未出现），只靠该文案判定会让定时任务永远不发送。
  `scan_all_boss_chats()` 现接受 `window_cutoff`/`captured_on`：列表按最近消息倒序，
  **整屏所有会话都早于近一周截止日**即判定扫完（`stage=completed_window`,
  `stop_reason=window`）并允许进入发送阶段；任一行时间无法解析则继续扫描（fail closed），
  仍以 `incomplete` 结束且不发送。`scan_status.json` 新增 `stop_reason`
  （`bottom`/`window`/`screen_limit_or_stable`）。达到配置屏幕上限时 `cmd_run` 记为 `coverage=screen_limit`，按用户限定的前 N 屏继续处理；到达上限前稳定无变化仍 `incomplete` 且不发送。
- **`/dispatch-resume` 发送后补充文案**：简历确认后紧跟发送 `documents/dispatch/followup_message.txt`（gitignored，默认路径可覆盖）里的既定文案；中文经临时启用的 ADBKeyboard（`ADB_INPUT_B64`）输入，输入框内可见才点「发送」，发送后以 UI 确认为准并恢复原输入法；键盘缺失时自动下载安装。设备类失败最多重试 3 次，风控不重试；耗尽后写 `followup_pending`/`followup_attempts`/`followup_error` 与台账，条目仍标 `sent: true`，避免重试重复发简历；文案阶段命中风控也会先记台账/标 sent 再停批。
- **`/dispatch-resume` 文本索要正则补全与逐行判定**：新增提供/同步/给/获取/获得/投递/辛苦发/发一下/发一个等真实漏匹配句式；文本按行判定，UI 按钮行、本人自荐行与终端负样本不再产生误命中，卡片句需同时看到「同意/拒绝」才算卡片，`request_source` 仍区分 card/text/card+text。
- **`/dispatch-resume` 离职文案恢复子命令**：新增 `followup`，从 `ledger.jsonl` 找 `send_confirmed` 且未 `followup_confirmed` 的记录，按联系人+公司重新打开会话，只走 `resume_already_sent` 路径补发文案；绝不点「发简历」或「立即投递」，需 `--yes-i-reviewed`。
- **`/dispatch-resume` run 逐会话即时发送**：定时任务入口不再“扫完再批量 send”，而是在每条 BOSS 会话详情打开时立即执行四层过滤、近一周窗口、`--max-send` 名额判定；命中即在当前会话页发送简历与离职说明文案，返回列表后再打开下一条。`rescreen`/`recent` 扫描后仍生成审计报告但不再批量补发；`details.jsonl` 增加 `sent`/`send_attempted`/`send_skipped_reason`/`send_result`，`ledger.jsonl` 保留每条发送审计。手动 `send` 子命令不变。

### Fixed

- **`/dispatch-resume` run 扫描单条身份不一致不再中断全流程**：真机 `run` 扫描发现列表名与详情头部公司名不一致（例如列表显示代理/招聘公司名、详情头部为实际用人方），此前会作为设备错误停止，导致后续会话无法扫描；现在只读扫描会把该条记为 `navigation_failed` 并附身份原因，继续扫描其余会话。该记录不会进入发送队列；发送阶段仍要求 UI 身份确认，风控/登录错误仍立即停止。
- **`/dispatch-resume` run 扫描列表行消失不再中断全流程**：实时聊天列表可能在点击前重排或更新消息，此前精确三元组匹配失败会作为设备错误停止；现在按联系人和公司匹配，仍无法唯一匹配时记为 `navigation_failed` 并继续扫描。该记录同样不会进入发送队列，发送阶段仍逐条做 UI 身份确认。
- **`/dispatch-resume` 前 N 屏上限作为有界覆盖**：按用户规则只扫前 5 屏时，长列表往往到不了 30 天底部或整屏旧消息截止日；此前 `run` 会因此始终报 `scan_incomplete` 且永不发送。现在达到配置上限即视为 `coverage=screen_limit` 并继续重筛/近一周/发送；若在到达上限前连续两屏无变化，仍按覆盖未证实停止。
- **`/dispatch-resume` run 冷启动导航恢复**：真机发现 `force-stop` 后 monkey 会恢复到 BOSS 的「职位」tab，单纯 back 不会切到底部 tab；`_navigate_to_boss_all_tab()` 现在在 back 循环仍到不了聊天列表时回退点击底部「消息」tab，再确认进入「全部」子 tab，否则停止。避免定时任务刚启动就因页面状态误报设备错误。
- **语言栈硬过滤（用户规则 2026-11-25，当日追加 Python）**：`screen_candidate()` 第 5 层按 Java > Go > Python 有序阶梯选择简历；Java→JAVA，Go/Python→GO，三者都未明确则用 GO 兜底并放行（用户规则 2026-11-26 移除语言硬过滤）。Python-only 会话（真机案例：某游戏公司·Python 的卡片+文本索要）现在放行并选 GO 简历。历史结果需 `rescreen` 后重新进入 `recent`/人工审核。
- **`/dispatch-resume` 适配新版 BOSS 简历请求 UI**：真机发现点击简历版本行后会立即发起请求并关闭选择器，页面直接显示「请求中」，不再保留选中态或「立即投递」按钮；`send_one()` 现在检测 `请求中`/`附件简历请求已发送`/`已发送给Boss`/`这是我的简历` 任一状态，视为版本已选中且请求已发起，跳过旧 picker 校验与「立即投递」，继续发送离职说明文案；`resume_already_sent` 恢复路径也接受「请求中」。筛选负样本新增「请求中」「附件简历请求已发送」，避免重跑时对同一会话重复发简历。真机复跑又发现点选简历行后会短暂回到带「发简历」的详情页再变为「请求中」，`send_one()` 现在最多轮询 12 秒确认请求状态或旧 picker 仍可见，不再把慢速 UI 误判为失败；`followup` 恢复路径接受 BOSS 截断的「附件简历 候选人-开... 已发送给Boss」摘要（精确版本由台账审计），只补发文案、不重发简历。
- **简历发送安全门**：仅允许人工批准、已核实详情且筛选通过的未发送会话进入发送流程；无法从 UI 确认选中的简历版本时停止，不点击投递。筛选补充已发送附件和字节 OD 项目线索（含「字节项目，采用OD形式」这类拆开表述）；历史结果需要经过 `rescreen` 重筛与人工复核，不能自动视为发送许可。
- **`/dispatch-resume` verify 同名联系人防串号**：`open_boss_chat()` 现在会把队列里的公司名和打开后的详情页头部一起校验，两个同名联系人不再因为列表里同名而打开错人；推荐职位卡片里出现的公司名不算身份依据，不匹配即视为未核实并继续找，避免把错误会话当作审核依据。
- **`/dispatch-resume` verify 真机定位修复**：「新招呼」列表可能保留在底部位置，直接向下滑动看不到更早会话；`verify` 现在先把列表回卷到顶部再扫描，且只在 UI 树确认底部消息 tab 后点击、强制要求「新招呼」子 tab，无法确认顶部即失败停止而不是误入未知页面。成功核实会清掉上一次 `unverified` 遗留的 `verify_note`，避免审核时看到过期注释。
- **`/dispatch-resume` ADB list 路径补齐四层过滤**：此前默认 ADB dump 路径只用宽泛
  `is_resume_request` 识别、且把 BOSS 每行的 `tv_msg` 节点误当成联系人；现在按
  `tv_name/tv_position/tv_msg/tv_time_v2` 的 y 坐标分组还原会话，再统一走
  `screen_candidate()` 四层过滤与 `pick_resume()` 阶梯映射。`--dump` 离线读已存 XML
  行为一致；`--from-vision` 保留给猎聘自绘列表。已存 `scan-live-22.xml` 离线回归：
  1 条 pass（候选人乙·GO-Agent）、7 条带原因 skip，未发简历、未连设备。
- **`/dispatch-resume` 风控误报修复**：错误码正则原先把裸 `37` 当风控信号，真机列表中
  `18:37` 这类时间戳会误触发停机；现在 37/403/429/60001 必须带 `错误码/错误/异常/code`
  等上下文才命中，普通时间与「共 37 条」不再误停。

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
