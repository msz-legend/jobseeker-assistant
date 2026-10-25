# /outcome - Record Outcomes and Follow-up（结果与跟进记账）

把每一次结果（回信 / 拒信 / 推进 stage / offer / 放弃）写进 `job_search_tracker.csv` 与
`documents/postings/`，并按渠道阈值给出跟进提醒。用户可见输出全部中文。

「命令参数」：`<公司> <结果描述>` 或空（交互模式）。

---

## Step 0: 唤起上下文

并行读：

1. `job_search_tracker.csv`（按公司名找到对应行；无行 → 提示先补投递记录再记结果）
2. `documents/postings/<公司>_<岗位>.md`
3. `.claude/commands/outcome.md` 的阈值表（本文件）更新 frontmatter `status`。

## Step 1: 记录哪类结果

问用户或从 「命令参数」 解析：

| 结果 | tracker `status` | 额外动作 |
|---|---|---|
| 无回复，已跟进过 | `followup` | 给出下次跟进日期 |
| 无回复，达放弃阈值 | `rejected`（备注：无回） | 归档 |
| 对方明确拒绝 | `rejected` | 问拒因（如实记录，为 /setup 校准供数据） |
| 推进到面试某阶段 | `interview` | **stage 列**必须写（词汇表见下） |
| 拿到 offer（未定） | `offer` | 触发 /interview 的 OC lane |
| 拒 offer | `rejected`（offer declined） | 记原因 |
| 接 offer | `accepted` | 归档，tracker 保留为 records |
| 本人撤回 | `withdrawn` | 归档 |

**stage 词汇表**（写进 stage 列，只允许这些值）：

```
笔试 / 电话沟通 / 一面 / 二面 / 三面 / HR面 / OC / 背调
```

（途中加一面交叉面就写 `二面`，备注注明"交叉面"。）

## Step 2: 更新 tracker 行

- 只改写本公司的行；`date` 仍是**投递日**；新进展写 `notes` 追加式（`| <date> <事件>`）；
- `stage` 列只放最新阶段；历史阶段在 notes；
- `contact_person` 有 HR/猎头称呼就写（姓+职务，如「王 HR」）；
- 每次改动后跑 `python tools/posting_index.py`（JD 状态同步）。

## Step 3: 跟进阈值（渠道感知，写候选的下一次动作）

| 渠道 | 无回复阈值 | 动作 |
|---|---|---|
| BOSS 直聘站内信 | 5-7 天 | 一条新消息：报最新进展或新钩子；再等 5 天未回 → 归档 |
| 公司官网/邮箱投递 | 10 天 | 	  一封跟进邮件；再等 10 天 → 归档 |
| 猎头 | 按约定 | 先与猎头确认在手时间；到期未回 → 下次跟进 |
| 内推（脉脉/牛客/同事） | 5 天 | 先跟内推人确认是否在手 |
| 招聘平台投递箱 | 10 天 | 视为无回，转站内信/邮件 |

跟进话术直接引用 `06-greeting-templates.md` 的「跟进」模板（不重写）。

## Step 4B. Mistake reinforcement

默认只处理模拟或真实复盘中未答好、答错、答糊或被追问暴露边界的问题，不整体联网。按 `official → paper_or_standard → engineering_blog → book_or_course → community` 分级检索，每条最多 3 个来源；网络失败、资料冲突或候选人经历无法核验时写 `needs_verification`，不伪造 URL，不把资料写成个人经历。

为每个新错题写入申请工作区的 `mistakes/mistake-<stable-id>.md`，使用通用英文 schema 字段，中文填写正文，并生成一个 Mermaid 主图。更新 `documents/applications/00_interview_mistake_index.md` 的 recurrence、status、速记卡和完整条目链接。`documents/interview/一面/09_错题本.md` 是历史归档，不再写入。


当出现以下情况，提示用户「可以跑 `/setup` 做校准」：

- 连续 3 个同类岗位在同一 gate 被拒（分数错位）；
- 期望薪资区间连续 3 次低于市场反馈；
- 某个维度（如年龄线）反复成为拒绝主要原因。

校准表写在 04 的 `## Calibration from Past Applications`（有则更新，无则建）。

## Step 4B. Mistake reinforcement


复盘写完后，**把每个未答好项抽成一条通用错题条目**，写进申请工作区的 `mistakes/`，不写历史归档。

**为什么单独成文件**：复盘是按场次组织的，但下一轮要复习的是按知识点组织的。同一个知识点可能在多家公司的面试里反复出现，翻三份复盘不如翻一份错题本。

**每条使用 canonical schema**：`source`、`failure_type`、`root_cause`、`correct_answer`、`spoken_answer`、`diagram`、`follow_up_questions`、`sources`、`verification_status`、`personal_experience_boundary`、`practice_action`、`status`。

**状态机**：存储使用 `open | reviewing | memorized`；展示层可映射为红/黄/绿，不把展示符号写入 canonical schema。面试前集中复习 `open` 和 `reviewing`。

**纪律**：
- 每个未答好项按 `failure_type` 分类；知识、推理、表达、证据、经历边界和决策质量均可记录，不限于某一职业。

- 同一条在连续两个同类型岗位重复出现 → 触发 `/setup` 校准。
- 补强材料写完后，**回填一条指向它的链接**，不要让错题和补强材料变成两份漂移的副本。

## Step 5: 汇报

中文表格列出：更新行 / 下次动作与日期 / 校准触发情况。**不要**把 HR 姓名、公司名等任何
tracker 内容渲染到将被分享的输出里而不提醒（tracker 本身已 gitignore）。

---

## Design Principles

- **一行一个申请，notes 追加**：历史不被覆盖，审计可回溯。
- **词汇表枚举**：stage 列只写枚举值，让 /html-report 能统计漏斗。
- **阈值是工具不是感觉**：渠道阈值表落在这里，超期即提示归档，不内耗。
