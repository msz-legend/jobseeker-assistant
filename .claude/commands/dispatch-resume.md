# /dispatch-resume - 对话简历受控投递（Android 真机）

> ⚠ 这是**唯一**被允许自动化发送简历的通道：仅在本人 Android 真机、本人已登录的
> 招聘 App 上运行。手动四阶段必须经过人工审核勾选才会发送；定时任务走 `run`
> 单一入口时，用户已明确授权自动批准通过四层过滤与近一周范围的候选。命中风控立即停。
> 设计依据：`docs/superpowers/specs/2026-11-23-chat-resume-dispatch-design.md`。

把「读聊天列表 → 识别索要简历的岗位 → 逐条打开会话核实 → 人工审核 → 按语言栈优先级
发送对应简历」拆成四个手动阶段，外加一个供定时任务调用的 `run` 单一入口。脚本：`tools/chat_resume_dispatch.py`；
阶梯配置：`config/resume_ladder.json`。

前置条件：手机 USB 连接、`adb devices` 能看到设备、招聘 App 已登录、人在场；
`documents/dispatch/resume_names.json` 已填好平台上附件简历的精确名称（含姓名的个人文件，不入库）。

阶梯配置 `config/resume_ladder.json` 里用 `%JAVA_RESUME%` / `%GO_RESUME%` 占位符，
运行时由 `resume_names.json` 解析成真实简历名——这样仓库里没有个人信息。

---

## Step 1: 采集与列举（只读）

先把 App 停在**消息列表页**（不是对话详情页）。BOSS 列表 UI 树可读
（`tv_name` / `tv_position` / `tv_msg` / `tv_time_v2`），`list` 默认走 ADB UI dump：
按 y 坐标把 4 个字段节点还原成一行会话，再过四层过滤。

BOSS（默认路径，真机或已存 dump）：

```bash
python tools/chat_resume_dispatch.py list --out documents/dispatch/queue.json
python tools/chat_resume_dispatch.py list --dump saved.xml --out documents/dispatch/queue.json
```

**猎聘的消息列表是 WebView 自绘，`uiautomator dump` 读不到文本**，只能走
"截图 + 视觉识别"：截屏并 pull → agent 逐条转录成结构化 JSON
（`platform/contact/org/city/role/snippet`）→ 用 `--from-vision` 交给脚本过**同一套
四层过滤**：

```bash
python tools/chat_resume_dispatch.py list --from-vision <结构化.json> \
  --out documents/dispatch/queue.json
```

**四层硬过滤**（配置在 `config/resume_ladder.json`，`screen_candidate()` 实现）：
- 明确索要：**卡片或文本任一命中即算**（`detect_resume_request()`）——
  - 卡片：出现索要简历卡片句式（`我想要一份您的附件简历，您是否同意`）**且**
    同时出现卡片的两个按钮 `同意` / `拒绝`；两者齐备才判为卡片命中，
    避免把普通文本气泡误当卡片；
  - 文本：`explicit_request_patterns` 命中索要动作词（`方便发一份简历过来吗`）；
  - 命中来源写入 `request_source`（`card` / `text` / `card+text`），随
    `details.jsonl`、`queue_*.json`、审核清单与 `run_summary.json` 的
    `request_sources` 一起留痕；
  - 两者都未命中 → 不发送、不回复；`[新招呼]`、问薪资、要手机号、`[简历]`
    标签本身都**不算**；「对方已同意，您的附件简历已发送给对方」属已发送，
    负样本优先，不会重复发送。
- 外包：身份/公司含 `猎头/外包/人力/人才/咨询/顾问/hrm/招聘经理/rpo/劳务派遣` → 屏蔽。
- 异地：city 明确非北京 → 屏蔽（仅北京，档案硬门槛）。
- 算法岗：role 含 `算法/模型训练/机器学习/NLP/CV` → 屏蔽（档案：纯算法岗不匹配）。
- 语言栈：按有序阶梯 Java > Go > Python 推断；Java → JAVA 简历，Go/Python → GO 简历；
  三者都没提到 → 兜底 GO 简历，不再屏蔽（用户规则 2026-11-26）。

被屏蔽的条目及原因在输出的 `skipped_detail` 里列出，便于复核。通过的条目写入队列，
`approved: false`。重跑只追加新条目，**不会覆盖你已填的 approved**。

把输出里的 `candidates` 用中文列给用户看：联系人、消息摘要、推断技术栈、拟发简历版本。

## Step 2: 逐条打开会话核实（只读，BOSS）

列表摘要被截断，外包/异地信号常常只出现在聊天正文里（真机案例：列表 `org` 为空，
打开会话才看到「这边是某外包公司，做字节项目」）。verify 阶段把这一步固化：

```bash
python tools/chat_resume_dispatch.py verify --queue documents/dispatch/queue.json --limit 3
```

- 自动启动 BOSS → 回到消息列表 → 按联系人名滚动定位 → 点进会话 → dump 详情全文；
- 对「列表摘要 + 详情全文」重跑四层过滤，并按 Java > Go > Python 阶梯重推断简历版本
  （Java→JAVA，Go/Python→GO；无明确栈直接屏蔽，`pick_resume()` 的 GO 兜底仅供显示，不放行会话）；
- 结论写回队列：`verified/detail_text/verdict/reasons/resume(_changed)`，判 skip 则
  `skipped: true + skip_reason`；定位不到标 `unverified` 交人工；
- **只读**：全程不点「发简历」，`approved/sent` 一律不动；
- 每条处理完写盘 + 记台账，中断不丢进度；`--limit` 控制单次条数（防批量触发风控）；
- 命中验证码/风控错误码：立即停、截图+dump 落 evidence/，退出码 2。

把每条的核实结论（命中/屏蔽原因、语言栈证据、简历版本是否变化）用中文列给用户复核。

## Step 3: 人工审核（不可跳过）

规则或配置变化后，旧扫描结果不能直接当发送授权。用 `rescreen` 把已保存的逐会话证据
（`open_all_details.jsonl`）按当前规则重筛，生成全新的未批准队列：

```bash
python tools/chat_resume_dispatch.py rescreen \
  --evidence documents/dispatch/evidence/verify/open_all_details.jsonl \
  --out documents/dispatch/evidence/verify/queue_rescreened.json \
  --report documents/dispatch/evidence/verify/review_candidates_rescreened.md
```

`rescreen` 只读、不会连设备，也不会沿用旧 approval（输出全部 `approved: false`）；
`--report` 生成按联系人+公司去重的人工审核清单，明确标注“不是发送授权”；
目标文件已存在时必须显式加 `--overwrite`。

用户必须亲自编辑待发送队列，把要投的条目 `approved` 改成 `true`。
脚本默认全 `false`；任何 `approved != true` 的条目在 send 阶段一律跳过。

若只处理近一周会话，在 `rescreen` 之后再加只读 `recent`：从已保存的 BOSS 列表
XML dump 中读取 `tv_time_v2`，相对截图/抓取当天解析 `昨天/星期X/日期`，只保留
`[as_of-(days-1), as_of]`（默认 7 天，含两端）内的会话。时间缺失或无法解析的
条目一律排除，不默认算近期；生成独立审核清单，并重置所有 approval。

```bash
python tools/chat_resume_dispatch.py recent \
  --queue documents/dispatch/evidence/verify/queue_rescreened.json \
  --dump-dir documents/dispatch/evidence/verify/scan_all \
  --as-of 2026-11-25 --captured-on 2026-11-24 --days 7 \
  --out documents/dispatch/evidence/verify/queue_recent.json \
  --report documents/dispatch/evidence/verify/review_recent.md \
  --excluded-out documents/dispatch/evidence/verify/queue_recent_excluded.json
```

`recent` 不连设备、不点「发简历」；`--report` 明确标注“这不是发送授权”，
`--out` 中所有条目仍是 `approved: false`。发送时还要求条目带 `recent_window: true`，
旧队列或缺时间证据的条目不会绕过近一周范围。

向用户明确：`send` 会真实发送简历给对方、不可撤回；只有勾选的条目会发。

## Step 4: 发送（写设备，按条目逐个）

```bash
python tools/chat_resume_dispatch.py send --yes-i-reviewed --auto-open
```

设备交互默认带随机拟人化停顿（导航、打开会话、简历 picker、选版本、投递前、
简历确认后到文案输入、候选人之间 8–20 秒）；轮询确认仍用短固定间隔，命中风控
立即停止且不停顿。排查时可加全局 `--no-humanize` 关闭随机停顿。

- 只处理 `approved: true && !sent && verified && detail_found && verdict == "pass" && recent_window == true` 的条目；
  `recent_window` 由 `recent` 阶段写入；未生成近期队列的旧条目不会发送；
- `--auto-open` 会先在 BOSS「全部」列表中按联系人定位并打开会话；定位不到立即停；
  不加该参数时，要求人工先把目标会话打开在屏幕上；
- 每条先校验联系人是否在屏幕上（不在就停，不盲点），点「发简历」→ 按版本名精确
  匹配（支持姓名带 `-Harness.pdf` 后缀、mResumeName 的父行才是可点击行）；
  旧版 picker 保留选中态时二次校验勾选 → 点「立即投递」→ 等平台确认消息；
  新版点简历行即发起请求并关闭 picker，看到「请求中」/「附件简历请求已发送」/
  「已发送给Boss」/「这是我的简历」即视为已选中并请求已发起，跳过「立即投递」；
  请求状态最多轮询 12 秒，慢速 UI 不误判失败，简历行只点一次；
  无法确认版本或请求状态时停，不盲点；
- 简历确认后，紧跟发送 `documents/dispatch/followup_message.txt` 里的补充文案
  （默认路径；中文经临时启用的 ADBKeyboard 以 base64 广播输入，发送后恢复原输入法；
  文案可见才点「发送」，发送后以 UI 确认为准）。仅设备类失败最多重试 3 次；
  风控/验证码不重试。耗尽后写 `followup_pending: true`、`followup_attempts`、
  `followup_error` 和台账，该条仍标 `sent: true`，避免重试时重复发简历；
- 只补离职文案、不重发简历时用 `followup` 恢复子命令：
  ```bash
  python tools/chat_resume_dispatch.py followup \
    --ledger documents/dispatch/evidence/verify/ledger.jsonl \
    --yes-i-reviewed
  ```
  它从台账中找已确认发送但文案未确认的条目，按联系人+公司重新打开会话，只走
  `resume_already_sent` 恢复路径；绝不点「发简历」或「立即投递」；已发送证据接受
  「请求中」或 BOSS 截断的「附件简历 候选人-开... 已发送给Boss」摘要（候选人姓名前缀 +
  附件简历证据，精确版本由台账审计）；
- 成功写 `documents/dispatch/ledger.jsonl` 并把该条目标记 `sent: true`；
- 命中验证码/风控错误码/结构突变：**立即停**，截图 + UI dump 落
  `documents/dispatch/evidence/`，退出码 2，剩余条目不处理。若风控出现在
  简历已确认后的文案阶段，该条仍先标 `sent: true` 并记台账，再停批。

退出码：0 全部成功；1 设备/结构错误；2 命中风控；3 已投递但未收到确认（需人工核对）。

可用 `--dry-run` 预演（只打印点击坐标，不真点）。

## Step 5: 定时任务单一入口 `run`（自动批准并发送）

```bash
python tools/chat_resume_dispatch.py run \
  --out-dir documents/dispatch/evidence/verify/run_$(date +%Y%m%d_%H%M%S) \
  --days 7
```

`run` 是定时任务的**唯一入口**，串行完成：先强制关闭并重新启动 BOSS，检查
登录/验证码页面并确认进入「消息 → 全部」→ BOSS「全部」**逐会话打开并当场判定**
（四层过滤 + 近一周窗口 + `--max-send` 名额）→ 命中就当场发送对应简历和离职说明
文案 → 返回列表打开下一条；不命中只记录并跳过。扫描结束后仍生成当前规则
`rescreen` / 列表时间 `recent` 审计报告，但**不再批量调用** `send`。
用户已明确授权定时任务自动批准，因此不需要人工逐条勾选；其余安全门保持不变：
四层过滤、同名同公司身份校验、近一周窗口、BOSS-only、ADBKeyboard 文案、
版本勾选 UI 校验、拟人化停顿、风控即停。

- 发送顺序严格为“打开会话 → 判定 → 发送 → 返回列表 → 下一条”；离职说明阶段
  命中风控时先落盘该条审计记录，再立即中止本轮，不会继续打开后续会话；
- 扫描覆盖由两条依据之一确认：看到「以上是30天内的联系人」；或**整屏会话都早于
  近一周截止日**（列表按最近消息倒序，故更早的会话不可能在范围内），记为
  `stage=completed_window` / `stop_reason=window`。任一行时间无法解析则继续扫描且
  **不发送**该行；到达配置屏幕上限时按用户限定的前 N 屏记为 `coverage=screen_limit`，
  到达上限前连续两屏无变化仍以 `incomplete` 结束并**不发送**；扫描屏数由
  `config/resume_ladder.json` 的 `scan.max_screens` 控制，默认 5，
  `--max-screens N` 可临时覆盖；
- `--max-send N` 限制单次发送数量（默认 0=不限制），`--no-humanize` 供排障；
- 所有产物写入 `--out-dir`：`details.jsonl`（含 `sent`/`send_attempted`/
  `send_skipped_reason`/`send_result`）、`list_dumps/`、`queue_rescreened.json`、
  `queue_recent.json`、`run_queue.json`、`run_summary.json`、`ledger.jsonl`；
- 退出码：0 完成（可能 `no_candidates`）；1 设备/结构错误或覆盖未证实；2 风控；
  3 已投递未确认（沿用 send_one 语义）。

旧脚本 `documents/dispatch/evidence/verify/open_all_details.py` 仅作为历史证据工具，
不再作为流程入口。

## 约束

- 不批量高频：一次 send 只处理人工勾选的条目，逐条确认。
- 不绕验证码、不注册、不填表单、不做 Web/H5 打招呼路线。
- `documents/dispatch/**` 含个人数据，已 gitignore，不入库。
- 发的是平台上已上传的附件简历版本，不是本地 DOCX；在线简历会随附件一起被对方收到。
