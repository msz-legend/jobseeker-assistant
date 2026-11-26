# 对话简历投递（受控自动发送）— 设计文档 (Design Spec)

- 日期：2026-11-23
- 状态：**已批准，实现中**（用户在会话中明确授权改规则 + Android 真机自动发送）
- 关联请求：查看聊天列表 → 识别索要简历的岗位 → 列举 → 人工审核 → 按语言栈要求优先级发送对应简历
- 授权记录：用户显式选择「要自动化平台发送」「Android 手机真机」「授权改规则，按自动发送做」；随后口头规则「如果没有 Java 和 GO，默认发 GO」

---

## 1. 目标与边界

把「读聊天列表 → 识别索要简历 → 人工审核 → 选简历版本 → 自动投递」做成仓库内自包含的脚本，在用户本人 Android 真机、本人已登录的招聘 App 上运行。

- **只做**：读取 UI 树、识别候选、人工勾选后逐个打开会话点「发简历」→ 选附件简历 → 点「立即投递」、记录台账。
- **不做**：注册、填真实表单、绕验证码、高频批量、伪装 Web/H5 打招呼路线。
- **不可撤回动作的唯一闸门**：只有审核清单里 `approved: true` 的条目才会被发送。

## 2. 与既有决策的关系

`docs/superpowers/specs/2026-11-10-android-collector-design.md` §4 曾把打招呼/发送「整体排除」，并写明「若将来要收，需先改规则并同步 CHANGELOG + framework_version，属另一需求」。本 spec 就是那个「另一需求」：用户已授权，按 §6 改规则后放行。

## 3. 架构

```
规范层   .claude/commands/dispatch-resume.md       唯一工作流定义
         .claude/skills/job-application-assistant/SKILL.md  命令表加指针
代码层   tools/chat_resume_dispatch.py             主脚本（stdlib + adb 子进程）
         tools/chat_resume_ladder.py               语言栈→简历版本映射（纯函数）
配置层   config/resume_ladder.json                 有序阶梯 + 占位符（可入库，无姓名）
         documents/dispatch/resume_names.json      个人简历名映射（%KEY%→真实名，gitignored）
数据层   documents/dispatch/queue.json             候选清单（人工勾选 approved）
         documents/dispatch/ledger.jsonl           投递台账（追加写）
         documents/dispatch/evidence/              风控现场截图 + UI dump（gitignored）
规则层   AGENTS.md / CHANGELOG.md / framework_version
```

## 4. 工作流（list / verify / rescreen / recent / run / send / review）

### 4.1 `list`（只读，不动设备状态）

**真机实测修正（2026-11-24）**：BOSS 消息列表 UI 树可读
（`tv_name` / `tv_position` / `tv_msg` / `tv_time_v2`，每条会话拆成 4 个独立节点），
因此 `list` 默认走 ADB UI dump：按 y 坐标把字段节点还原成行，再过四层过滤。
猎聘消息列表是 WebView 自绘，`uiautomator dump` 读不到文本，保留视觉转录子模式。
两条路径共用同一个 `screen_candidate()`，过滤行为一致。

- 默认 / `--dump <xml>`（BOSS 主路径）：ADB dump 当前消息列表，分组还原会话 →
  四层过滤 → 写队列；`--dump` 可离线读已存 XML。
- `--from-vision <json>`（仅猎聘自绘列表）：截图 → agent 视觉读图转录为结构化候选
  （`platform/contact/org/city/role/snippet`）→ 四层过滤 → 写队列。

```bash
python tools/chat_resume_dispatch.py list --out documents/dispatch/queue.json
python tools/chat_resume_dispatch.py list --dump saved.xml --out documents/dispatch/queue.json
python tools/chat_resume_dispatch.py list --from-vision candidates.json \
  --out documents/dispatch/queue.json
```

四层硬过滤（`screen_candidate()`，配置 `config/resume_ladder.json`）：
1. **明确索要（卡片或文本任一命中）**：BOSS 平台卡片（“我想要一份您的附件简历，您是否同意”＋“拒绝/同意”）或文本索要动作词（“我想要一份简历”“发我一份简历”等）任一命中即可；已发送/已同意/已收到等负样本优先，`request_source` 记录 `card`/`text`/`card+text`。`[新招呼]`、问薪资、要手机号、`[简历]` 标签本身都不算。
2. **外包**：身份或公司含 `猎头/外包/人力/人才/咨询/顾问/hrm/招聘经理/rpo/劳务派遣` → 屏蔽。
3. **异地**：city 明确非北京 → 屏蔽（档案硬门槛：仅北京）。
4. **算法岗**：role 含 `算法/模型训练/机器学习/NLP/CV` → 屏蔽（档案：纯算法岗不匹配）。
5. **语言栈只选简历**：按 Java > Go > Python 推断版本；Java→JAVA，Go/Python→GO；没有语言栈不屏蔽，按兜底 GO 发送（用户规则 2026-11-26）。

每条候选按语言栈阶梯推断 `resume` 版本（Java→JAVA-Agent，Go/Python→GO-Agent，优先级 Java > Go > Python）；`fallback.resume` 是无语言栈会话的简历兜底（GO），不再作为过滤条件。通过的条目写队列，`approved: false`；
被屏蔽的连同原因在 `skipped_detail` 输出。重跑只追加新 key，不覆盖人工已填审批。

### 4.2 `verify`（只读，逐条打开会话）

列表摘要会截断关键信息；`verify` 自动打开每个候选会话，以详情全文重跑四层过滤和语言栈阶梯，写回 `verified/detail_text/verdict/resume/request_source`，从不点「发简历」。猎聘列表自绘，当前暂停。

### 4.3 `rescreen`（只读，规则变更后重筛旧证据）

规则变化后，旧扫描报告不能作为发送授权。`rescreen` 读取 `open_all_details.jsonl` 这类已保存的逐会话证据，按**当前**配置重筛并输出一个全新队列：`approved/sent` 全部重置为 `false`；已有输出文件必须显式 `--overwrite` 才能覆盖。

```bash
python tools/chat_resume_dispatch.py rescreen \
  --evidence documents/dispatch/evidence/verify/open_all_details.jsonl \
  --out documents/dispatch/evidence/verify/queue_rescreened.json \
  --report documents/dispatch/evidence/verify/review_candidates_rescreened.md
```

`--report` 只用于人工审核：按联系人+公司去重，列出条目数、证据行号和待勾选栏，不携带任何授权含义。

### 4.4 `recent`（只读，近一周范围）

用户要求“只处理近一周的消息会话”时，在 `rescreen` 之后运行：`recent` 从已保存的
BOSS 列表 XML dump 中按 `(contact, org, list_snippet)` 读取 `tv_time_v2`，把抓取日作为
相对标签基准（裸 `HH:MM`=抓取日、昨天/前天、星期X 取最近一次早于抓取日的对应星期、
`M月D日` 补全年份），仅保留 `[as_of-(days-1), as_of]`，默认 7 天且含两端。
时间缺失或无法解析的条目 fail-closed 排除；输出队列的 `approved/sent` 仍为 `false`，
并写入 `recent_window: true` / `last_activity_date` 作为发送安全门的证据。报告明确标注“这不是发送授权”。

```bash
python tools/chat_resume_dispatch.py recent \
  --queue documents/dispatch/evidence/verify/queue_rescreened.json \
  --dump-dir documents/dispatch/evidence/verify/scan_all \
  --as-of 2026-11-25 --captured-on 2026-11-24 --days 7 \
  --out documents/dispatch/evidence/verify/queue_recent.json \
  --report documents/dispatch/evidence/verify/review_recent.md \
  --excluded-out documents/dispatch/evidence/verify/queue_recent_excluded.json
```

### 4.5 `run`（定时任务单一入口，自动批准并发送）

用户明确授权定时任务绕过逐条人工勾选后，`run` 把全部阶段串成一条命令：

```bash
python tools/chat_resume_dispatch.py run \
  --out-dir documents/dispatch/evidence/verify/run_20261125_100000 \
  --days 7 --max-send 0
```

流程：启动扫描前 `force-stop com.hpbr.bosszhipin` 并重新启动，登录页或
验证码/安全验证页立即停止；确认进入 BOSS「全部」后**逐会话打开并当场判定**：
四层过滤 + 近一周窗口 + `--max-send` 名额，命中就在此刻调用 `send_one` 发送
对应简历与离职说明文案（含版本 UI 校验、拟人化停顿、风控即停），返回列表后再打开
下一条；不命中只写 `details.jsonl` 并跳过。扫描结束后仍生成 `rescreen` / `recent`
审计报告，但不再调用 `send --auto-open` 批量补发。强制关闭仅发生在 `run` 扫描入口，
不清除 App 数据，也不影响其他手动子命令。

安全边界与手动四阶段完全一致：四层过滤、同名同公司身份校验、近一周窗口、
BOSS-only、ADBKeyboard 文案、风控即停。`run` 只增加“自动批准通过筛选的新候选”
这一项授权。`--max-send N` 限制单次数量（0=不限制），`--no-humanize` 供排障。
每条发送结果写入 `details.jsonl` 的 `sent`/`send_attempted`/`send_skipped_reason`/
`send_result` 与 `ledger.jsonl`；离职说明阶段命中风控时先落盘该条记录，再中止本轮，
不会继续打开后续会话。
扫描覆盖由两条依据之一确认：(a) 看到「以上是30天内的联系人」(`stop_reason=bottom`)；
(b) **整屏会话都早于近一周截止日** (`stage=completed_window`, `stop_reason=window`)——
BOSS 列表按最近消息倒序，更早的会话不可能落在窗口内，且真机确认该底部文案在长列表上
几乎不可达（120/90/15 屏均未出现），只依赖 (a) 会让定时任务永远不发送。任一行时间
无法解析时继续扫描（fail closed），只看到稳定屏幕或任一步风控/设备错误都停止且不发送，
只保留证据与 `run_summary.json`。扫描屏数默认 5 屏（用户规则 2026-11-25），来自
`config/resume_ladder.json` 的 `scan.max_screens`；`--max-screens N` 可显式覆盖。达到该上限被视为用户限定范围内的有界覆盖（`coverage=screen_limit`），可继续重筛、近一周过滤与发送；若在到达上限前连续两屏无变化，则仍判 `scan_incomplete`（`stop_reason=screen_limit_or_stable`）且不发送。

旧 `documents/dispatch/evidence/verify/open_all_details.py` 的扫描核心已迁入主脚本，
该文件只作为历史证据工具，不再作为流程入口。

### 4.6 `send`（写设备，危险）

```bash
python tools/chat_resume_dispatch.py send --queue documents/dispatch/queue.json --auto-open
```

1. 读 `queue.json`，只取 `approved: true && !sent && verified && detail_found && verdict == "pass" && recent_window == true` 的条目；近一周范围未确认的旧条目不会进入发送集。
2. `--auto-open` 时先在 BOSS「全部」列表按联系人定位并打开会话；定位失败即停；不加时要求会话已在屏幕上。
3. 逐条：
   a. 风控预检 `sentinel.check()`（见 §5）。
   b. 按 `contact` 定位会话（要求当前已在对话页；脚本用 UI 树文本匹配联系人，找不到就停并报错，不盲点）。
   c. 点「发简历」→ 解析简历选择器 UI 树 → 按 `resume` 版本名精确匹配并点选（支持简历名带 `-Harness.pdf` 后缀、可点击父行承载 mResumeName 的 UI）。
   d. 兼容两种 BOSS UI：
      - 旧版：选择器保留选中态，读 UI 树 checked 状态二次校验后点「立即投递」→ 等「这是我的简历」确认；
      - 新版：点简历行后立即发起请求并关闭选择器，页面出现 `请求中`/`附件简历请求已发送`/`已发送给Boss`/`这是我的简历` 任一状态即视为版本已选中且请求已发起，跳过「立即投递」与二次校验，直接进入文案阶段；状态最多轮询 12 秒，慢速 UI 不误判失败，简历行只点一次。
      脚本只在旧版流程中点「立即投递」；无法确认选中版本或请求状态时停止，不盲点。
   e. `resume_already_sent` 恢复条目接受「请求中」或 BOSS 截断的「附件简历 候选人-开... 已发送给Boss」摘要；同时要求候选人姓名前缀与附件简历证据，精确版本由台账审计，避免重复点选简历行。
    f. 简历确认后，紧跟发送 `documents/dispatch/followup_message.txt` 的补充文案：
       中文经临时启用的 ADBKeyboard（`ADB_INPUT_B64` 广播）输入；输入框内确认文案可见
       才点「发送」；发送后以 UI 确认（文案离开输入框且出现在消息流）为准；
       完成后恢复原输入法。仅设备类失败最多重试 3 次；风控/验证码绝不重试。仍失败时
       记 `followup_pending: true`、`followup_attempts`、`followup_error`，条目仍标
       `sent: true`，避免重试时重复发简历。
    g. `followup` 恢复子命令只补未确认离职文案：从 `ledger.jsonl` 找 `send_confirmed`
       且未 `followup_confirmed` 的记录，按联系人+公司重新打开会话，以
       `resume_already_sent` 恢复路径补发；绝不点「发简历」或「立即投递」；
       `--yes-i-reviewed` 前不会写设备。
   h. 追加 `ledger.jsonl`，标记该 key 已投递。
   i. 有意交互（导航、打开会话、picker、选版本、投递前、简历确认后到文案输入、
       候选人之间）使用有界随机拟人化停顿；轮询确认仍用短固定 sleep，命中风控
       立即停止且不再停顿。全局 `--no-humanize` 只用于确定性测试/排障。
4. 任何一步命中风控 → 立即停，剩余条目不处理，截图+UI dump 落 `evidence/`。
   若风控出现在简历已确认后的文案阶段，该条仍先标 `sent: true` 并记台账，再停批。

### 4.7 审核门

`queue.json` 是人工审核界面：用户把要投的条目 `approved` 改成 `true`。脚本默认全部 `false`。`send` 对 `approved != true` 的条目一律跳过并在输出里列出原因。

## 5. 风控（sentinel）

UI 树 `content-desc`/`text` 命中任一信号即抛 `HumanInterventionRequired`：

- 验证码 / 安全验证 / 滑动验证 / 人机校验 / 请完成验证
- 错误码 `37` / `403` / `429` / `60001`（平台风控常见）
- 结构突变：发简历按钮或简历选择器在预期位置找不到

命中后：截图 `evidence/<timestamp>.png` + UI dump `evidence/<timestamp>.xml`，退出码 2，不重试。

## 6. 规则改动

- `AGENTS.md` §4：把「不代投递」改为「检索/评估/材料生成默认不代投递；**受控自动投递例外**：仅 `/dispatch-resume` 在人工勾选 approved 后、于本人设备执行，且命中风控即停」。
- `CHANGELOG.md` Unreleased：记 Added 条目。
- `framework_version`：1.5.5 → 1.6.0（`AGENTS.md` + 所有改动的 skill .md frontmatter 同步）。
- `tools/security_guards.py`：ALLOWED_PERMISSIONS 与 ALLOWED_SKILL_TOOLS 加新脚本命令。
- `.claude/settings.json`：permissions.allow 加新脚本命令。
- `.gitignore`：`documents/dispatch/**` 加入个人数据忽略。

## 7. 测试

纯离线单测（`tests/test_chat_resume_dispatch.py`），不连设备：

- 索要简历双信号（`RequestSignalTests`）：仅卡片、仅文本、两者同时命中、两者都不命中
  四类；卡片句缺「同意/拒绝」不算卡片；已同意/已发送不算未处理请求。
- 阶梯映射：Java→JAVA 版、Go/Python→GO 版（优先级 Java > Go > Python）、无明确 Java/Go/Python→兜底 GO 简历（不再过滤，用户规则 2026-11-26）。
- 审核门：`approved:true` 才入 send 集；已投递不重复。
- 风控信号：各信号命中即抛异常且不继续。
- UI 树解析：给定 fixture XML 能正确抽取会话条目；BOSS 4 字段节点按 y 分组后
  再过四层过滤（`AdbListScreeningTests`）。
- 重筛与发送安全：`rescreen` 按当前规则重筛旧证据且重置审批，并透传 `request_source`；`approved` 但仍
  `unverified`/未通过过滤的条目不得进入 send；简历选择器勾选态无法确认时不投递。
- 发送后文案：文案文件缺失/为空时不做任何设备动作；简历确认后才发文案；
  输入框不可见时不点「发送」且恢复输入法；ADBKeyboard 缺失时先安装；文案发送
  以 UI 确认为准；设备类失败最多重试 3 次，风控不重试；耗尽后写
  `followup_pending`/`followup_attempts`/`followup_error`；`followup` 恢复子命令
  只补文案不重发简历，且尊重 `--yes-i-reviewed`；文案阶段风控先记台账/标 sent 再停批。
- 文本索要正则：真实漏匹配句式（提供/同步/给/获取/获得/投递/辛苦发/发一下/发一个）命中；
  UI 按钮行、本人自荐行、终端负样本按行忽略；卡片句缺「同意/拒绝」不算独立文本命中；
  `card`/`text`/`card+text` 来源仍正确。
- 简历请求 UI 双流程：旧版保留选中态时验证 checked 后点「立即投递」；新版点简历行即
  进入「请求中」并关闭 picker，跳过 `_verify_selection`/「立即投递」直接发文案；
  `resume_already_sent` 恢复路径接受「请求中」或 BOSS 截断的「附件简历 候选人-开... 已发送给Boss」摘要（候选人姓名前缀 + 附件简历证据，精确版本由台账审计）；
  「请求中」/「附件简历请求已发送」作为负样本，重跑不得重复发简历；点选简历行后的
  瞬态详情页（ picker 已关闭但 header 尚未变为「请求中」）必须通过最多 12 秒轮询确认请求状态，
  不得误判为旧 picker 流程并中止。
- 近一周范围：`parse_list_time` 相对抓取日解析 BOSS 时间标签；`filter_recent_entries`
  按含两端的 7 天窗口保留条目，时间缺失/过期/未来 fail-closed；`recent` 报告明确不是发送授权；
  `send` 必须额外看到 `recent_window: true`。
- 拟人化停顿：`human_pause` 的有界随机值与 `--no-humanize` 关闭路径；`send_one`
  在简历确认后到文案输入之间停顿；`cmd_send` 只在非风控结束的候选人之间停顿，
  文案阶段风控停批后不再插入候选人间隔。
- 单一入口 `run`：扫描（默认前 5 屏，配置 `scan.max_screens` 可覆盖）时**逐会话打开并
  当场判定**四层过滤、近一周窗口与 `--max-send` 名额；命中即在当前会话页调用
  `send_one` 发送简历与文案，返回列表后再打开下一条；扫描后仅生成 `rescreen`/`recent`
  报告，不批量调用 `send`。覆盖可由 30 天底部、整屏早于截止日或达到配置屏幕上限确认，
  到达上限前稳定无变化时不发送；`--max-send` 只发送前 N 条；发送结果写
  `details.jsonl`/`ledger.jsonl`，风控先落盘再停批；`request_sources` 计数写入 summary；
  `run` 子命令与默认参数可解析。

## 8. 明确不做

- 不做截图 OCR：BOSS 用 UI 树已够用且更稳；猎聘自绘列表只做人工/agent 视觉转录，
  不引入 OCR 依赖。截图同时用于风控留证。
- 不写死设备 serial / 个人路径（自包含约束）。
- 不改外部 Hermes 定时任务或 `android-job-bridge`。
