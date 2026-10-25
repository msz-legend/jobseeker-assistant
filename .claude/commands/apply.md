# /apply - Targeted Application（中国版投递流）

针对**一个岗位**跑完整流程：JD 固化 → 岗位信任门 → 硬门槛 → 评分 → 定向简历 (DOCX) →
打招呼话术（默认）/求职信（例外） → 校验 → 记账。全程输出中文。

入参来源（跨 runtime 约定）：本文件中的「命令参数」指**当前用户消息中、命令名之后的原文**。
支持斜杠命令的 runtime 将其注入为命令参数；不支持的 runtime 必须把用户消息正文按同一规则传入。
空参数才进入交互模式。不要把「命令参数」当作需要原样输入的文字。
- 空 → 使用 `documents/postings/_index.md` 里最新的 `inbox` JD；
- `<公司> <岗位>` → 消费对应 JD 文件；
- 一个 JD 文本/路径 → 先走 Step 0 固化。

并行读（Step 2 起需要）：01/02/03/04 + 05-cv-drafting.md + 06-greeting-templates.md +
08-application-forms.md + templates/cv/base/TEMPLATE.md。临时目录约定：
Windows `%TEMP%\opencode`，macOS/Linux 用系统临时目录下的可写子目录（`$TMPDIR` 或 `/tmp`）；**任何中间产物不写进仓库**。

---

## Step 0: JD 固化 + posting_guard 信任门

1. 建 `documents/postings/<公司>_<岗位>.md`（从 `_TEMPLATE.md` 复制）。
   `/ \ : * ? " < > |` → `-`，空格 → `_`。
2. **JD 原文原样粘贴**（BOSS 聊天 / 官网 / 猎聘 / 微信转发转录 / 截图转录都行）。
   截图转录或转载文案在 frontmatter 里写 `jd_completeness: partial` + 备注「来源：截图转录」。
3. 原文存进 frontmatter 可捕捉到的字段：salary_raw、city、source、url。
4. **信任门**：
   ```bash
   python tools/posting_guard.py --in <jdfile.md> --text --json
   ```
   - verdict 行原样保留；如果一致段落 → 按提示处理（二次确认段落或终止）。
   - 从没见过 JD 得分誊写规则被用来抬分——guard 出 `suspicious` 就在评估报告里降权。
5. 运行 `python tools/salary_band.py "<salary_raw>" --floor "<底线月薪>K"`（底线从
   `01-candidate-profile.md` 的「底线月薪（工具用）」读），把 JSON verdict 存入 JD 文件 frontmatter 附近评估区。
6. **收尾检查**：`jd_completeness: partial` → frontmatter 写 `evaluation_confidence: low` +
   `materials_allowed: false`，**只能继续评估和记录用户决定，禁止进入材料生成**（Step 2–5）。
   先把「缺失字段清单」列给用户，补齐原文后改回 `full`。用户明确说「partial 也投」时，
   只记录缺失项与放行理由；不得解除 `materials_allowed: false`，也**禁止做 04 §2.1 的软缺映射**。

⛔ 硬门槛预检（在评分前 quickly 过一遍 04 的 Hard Gates；任何 fail → 停，
JD frontmatter `status: evaluated` + 拒因，tracker 不建行）：
城市不匹配 / 薪资 verdict=fail（gap > 15% 时也不建议投，除非附近期现金流豁免口径）/ 学历
硬门槛 / 年龄线明示 / 工作许可。**fail 不代表永远不投**——展示理由，用户明确说「仍要投」才放行。

## Step 1: 评分（04-job-evaluation.md 全流程）

- 按四维权重 30/25/15/30 打分（栈匹配/经验职级/领域/价值）， heavies 见 04；
- 评估输出打印成中文表格：维度 / 得分 / 依据 1 句话；
- 隐性红旗列表（薪资倒挂、JD 复制粘贴痕迹、一人多岗已看到、公司近况（官网/新闻））；
- `fit_rating` 写入 tracker 的 rating 逻辑沿用 04 阈值（≥75 强推 / 60-74 投 / 45-59 备选 /
  <45 不投）；
- **更新 JD 文件**：frontmatter `status: evaluated`、`fit: <score>`；
- `python tools/posting_index.py`（重建索引）。

用户拍板「投 / 不投」。不投 → 停（归档已足够）。投 → 继续。

## Step 2: 写定简历内容 spec

按 `05-cv-drafting.md` 生成 `cv/main_<公司>_<岗位>.json`：

- 从 01 档案取内容（one source of truth；不得引用 JD 替你写的“预期经历”）；
- 找到最匹配的 3-5 条经历/项目 bullets；按 05 的裁剪规则排布 sections；
- `meta.pages_target` 来自模板 manifest（≤5 年经验 1 页）；
- JD 的**核心硬技能关键词**记录在 spec 里（不渲染，供 verify 使用）：写在
  `meta.keywords`，逗号分隔 ≤8 个；
- spec 是存放 personal 决策的处所，**允许带真实内容已 gitignore**（cv/main_*.*）。

## Step 3: 打招呼话术（默认）与求职信（例外）

- 按 `06-greeting-templates.md` 生成 3 行打招呼语，从 spec 的 bullets 里挑钩子；
- BOSS 平台字段文案（个人优势 100-200 字模板）按 `08-application-forms.md` 生成；
- 正式求职信：**只有** JD 明确要求 attach 求职信 / 外企英文求职信时才生成（邮件正文格式，
  ≤400 字）。默认不生成，生成时用英文或中文按岗位语言。
- 展示全部候选话术，用户可选改。

## Step 4: 外部审查（application-reviewer agent）

Dispatch `application-reviewer`（`.claude/agents/` 定义，无写权限），feed 它：
spec + JD 摘要 + 01/02/03/04 路径。返回 findings 列表（诚实的三档：must-fix / nice /
ok）。按 must-fix 修订 spec；nice 微调自定。

## Step 5: 渲染 + 校验循环

```bash
python tools/build_cv.py cv/main_<公司>_<岗位>.json -o cv/main_<公司>_<岗位>.docx --style templates/cv/base/style.json
python tools/verify_resume.py cv/main_<公司>_<岗位>.docx --spec cv/main_<公司>_<岗位>.json --pages <N> --keywords "<jd keywords>"
```

- FAIL 项逐条修 spec → 重跑 build → 重跑 verify，直到 PASS；
- `--pdf` 在「渠道要 PDF」时加（Word/WPS/LibreOffice 任一可用就行；否则提示文本层已过）；
- 超页数砍法：按 05 的裁剪顺序（先砍需 edge 的经历 → 次高频技能行 → 最后横砍 bullet 非首句）；
- 校验通过后提醒**人工打开 DOCX** 目检（字体回退 / 表格走形 / 空白页）——渲染器不能替代眼睛。

## Step 6: 提交前 checklist（用户确认）

- [ ] 简历联系信息与 BOSS 在线简历一致（特别是城市与手机号）
- [ ] 期望薪资：平台字段 / 招呼语 / 简历 三处口径一致（来自 3.2 期望区间）
- [ ] 打招呼语首条 ≤3 行，钩子 1 个数字
- [ ] PDF 版（如渠道要求）页数 = manifest 限制
- [ ] 无截图转录痕迹（错误术语、错字）

## Step 6b: 记账

1. `job_search_tracker.csv` 追加一行（15 列）：
   `date,company,sector,role,role_type,channel,status,stage,contact_person,fit_rating,notes,cv_file,greeting_file,source,deadline`
   - status=`applied`；stage 留空（无面试）；cv_file 绝对路径或仓库相对路径；
   - greeting_file 仅在保存了话术文件时填；
   - notes 里写：打招呼日期 + 关键话术结论一句话。
2. JD 文件 frontmatter → `status: applied`，`fit` 已有，tracker_row 填 date；
3. 重跑 `python tools/posting_index.py`；
4. 提示 follow-up 节奏（/outcome 的渠道阈值）：BOSS 站内信 5-7 天 / 邮件 10 天 / 猎头按约定。

---

## Design Principles

- **JD 优先**：JD 原文是唯一事实源；截图转录 / 转载标记 partial，且评估时降权。
- **信签层分单**：contents（简历/话术）单一来源 01 档案；JD 只影响裁剪与关键词。
- **底线不可谈判**：薪资 verdict 是工具算的，agent 不替你妥协。
- **校验闭环**：build → verify 循环以 PASS 为投递前置条件。
- **平台优先**：BOSS/猎聘的站内回复优先于邮件；话术分渠道。
