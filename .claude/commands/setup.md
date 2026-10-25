# /setup - Candidate Profile Setup（中国版）

幂等：任何时候可以重跑，把已有个人数据当作「草稿读入」，改完再覆盖。产出文件全部中文，
涉及 CLI/字段名的地方保持 ASCII。破坏性变更（覆盖已有内容）必须先经用户确认。

「命令参数」 可为空，或含路径/提示词（如「用 documents/cv/ 里的简历」）。

---

## Step 0: 环境预检（一次性，输出到聊天即可）

1. `python --version`（需要 3.10+；Windows 用 `python`，`python3` 不存在）。
2. 可选依赖探测：`python -c "import docx"`（简历 DOCX 管线）、
   `python -c "import pypdf"`（PDF 校验）。缺哪个就告诉用户装哪个，
   **不要自己 pip install**。
3. 检查 `job_search_tracker.csv`、`documents/postings/` 是否存在；
   不存在时各创建骨架（tracker 只在确实没有时创建表头 + 示例行）。
   若 01/02 真实档案不存在，分别从同目录的 `.template.md` 复制为本地档案，再进入 Path A/B/C。
4. 运行 `python tools/posting_index.py` 若 postings 目录已有文件（重建 `_index.md`）。

## Step 1: 选择路径

- **Path A（文档导入）**：`documents/cv|profiles|diplomas|references|projects/` 有文件 →
  读入全部内容抽取数据。支持 DOCX（用 `tools/docx_text.py`）、PDF（pypdf）、图片（用户口头
  转述或贴文字）。邮件/脉脉导出在 profiles/。
- **Path B（现场访谈）**：没有文档 → 按下面 Step 3 的字段顺序逐项访谈。
  一次问 3-5 个问题，等回答再问下一组。
- **Path C（混合）**：文档为主 + 访谈补缺。

无论哪条路径，最终写盘内容必须经 Step 5 确认后落盘。

## Step 2: 读入现有框架状态

并行读：

- `.claude/skills/job-application-assistant/01-candidate-profile.md`（不存在时从同目录 `01-candidate-profile.template.md` 创建）
- `.claude/skills/job-application-assistant/02-behavioral-profile.md`（不存在时从同目录 `02-behavioral-profile.template.md` 创建）
- `.claude/skills/job-application-assistant/04-job-evaluation.md`
- `.claude/skills/job-scraper/search-queries.md`
- ~~`CLAUDE.md`~~ 不读——它只是转发页（`@AGENTS.md`），候选人事实只在 01

## Step 3: 档案构建字段（Path B 访谈顺序 / Path A 抽取映射）

以下每个字段写到 01-candidate-profile.md 对应小节；`[占位符]` 未取到就保留占位符。

### 3.1 基本信息
- 姓名/称呼、当前城市、可接受城市（主城/通勤圈/接受异地比率）
- 户籍地（涉及 offer 期户口或公积金迁移时才用）、政治面貌（仅投体制内/国企时问）
- 年龄段（出生年）——**默认静默收集**，用于 35 岁线偏好自检，不写进简历
- 工作年限、毕业时间（算年限用）

### 3.2 与薪资（必问，喂给 tools/salary_band.py）
- 期望月薪区间：`[X]-[Y]K`；薪数（×[N]）——如果以年薪报价，转算月薪
- **底线月薪 [SALARY_FLOOR_MONTHLY]**：低于这个数不需要看第二个字段
- 现薪口径（是否透露给 HR 的策略由 07 决定，这里只记事实）
- 总包意识：股票/期权/年终奖如何计入（你的判断口径写进 04 的 Value 维度注记）

### 3.3 目标岗位与不可谈判项
- 意向岗位（3 个以内）、相邻可投岗位
- 公司规模/类型偏好（大厂/中厂/外企/创业/国央企）：偏好 + 红线
- 硬拒绝清单：加班制（大小周/996）、通勤上限、出差比率、异地
- 学历门槛（用户自己的硬门槛 + 接受度：统招/专升本/非全）
- 语言（中文母语默认；英语能面试/邮件档）

### 3.4 工作/项目经历（Path A 从简历抽取 + 用户补口）
每段经历按 `动词 + 做了什么 + 量化结果` 抽取；拿不到数字的条目标
`⚠️ 无量化：面试前补` 而不是当场编数字。

### 3.5 能力与方法
按选定 domain pack 的字段记录可验证能力；核心档案只保留候选人的事实、边界和证据，不预设职业专属技能词。

### 3.6 个性化 04-job-evaluation.md
写以下占位符对应值（其余打分框架不动）：
- `[YOUR_PRIMARY_SKILLS]` / `[YOUR_SECONDARY_SKILLS]` / `[SKILLS_YOU_LACK]`
- 强/中/弱 经历匹配域三行
- `[YOUR_CAREER_GOAL_1..3]`、任务喜恶（energize/drain）
- 生活状态约束（Security/Flexibility/Development 三行）
- **✚ 中国化新字段**：`硬门槛清单`（从 3.3 归档成 Gate 表），用于 /apply Step 1 门控行为
- 若有历史投递结果，写 `## Calibration from Past Applications`（权重修正建议），
  没有则该节写 `<!-- /outcome 校准后自动生成 -->`

### 3.7 个性化 search-queries.md
- 站点清单按中国习惯确认：BOSS 直聘 / 猎聘 / 拉勾 / 智联 / 前程无忧 51job / 公司官网 /
  脉脉 / 牛客；外企机会加 LinkedIn。
- 查询类别（职能关键词）+ 城市词 + **排除词**（例如 `[EXCLUDE_KEYWORDS]`：外包/驻场/劳务，
  是否排除由用户拍板，默认不排除只标注）。写入 `search-queries.md` 的类别骨架里。

### 3.8 底线月薪落点
底线月薪只写 `01-candidate-profile.md` 的「底线月薪（工具用）」一行——/apply 和 /rank 直接读这里。
**不要写 `CLAUDE.md`**：它只是 Claude Code 的转发页（`@AGENTS.md`），写进去就是第二份档案，必然漂移。

## Step 4: 中国语言规则声明

每个写盘文件，顶部 frontmatter 之外第一行都是中文标题。占位符 token 保持英文大写
（`[YOUR_*]`），保证未来 /reset 脚本和 lint 工具能匹配。

## Step 5: 确认 + 写盘

把所有拟写内容按文件分组展示（01 / 02 / 04 / 06 / 07 / search-queries），**不含 CLAUDE.md**，
用户确认后用 Edit/Write 落盘。写完：

1. 重放 Step 0/4 自检。
2. 运行 `python tools/lint_skills.py` + `python tools/check_framework_version.py`。
3. 输出总结表：字段 → 文件 → 状态（已写/占位保留/用户稍后补）。
4. 提醒下一步：`/scrape`（找岗）、或手头有 JD 直接 `/apply`。

---

## Design Principles

- **不假谦逊，不吹嘘**：抽取与访谈产出遵循 `03-writing-style.md`；「精通」这种词出现时
  提醒用户降级到「熟悉/熟练」并给边界。
- **隐私优先**：所有个人数据只写上述已 gitignore 掉的文件之外的方法论文件；
  tracker、简历、档案材料永不入库（`SECURITY.md` 第 5 节）。
- **占位符完整性**：该用 `[YOUR_*]` 的一定用占位符，不留空白，让后续工具能检出。
- **幂等**：重跑不丢数据，覆盖前 diff 展示。
