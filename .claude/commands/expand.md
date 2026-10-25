# /expand - Competency Expansion from Documents and Online Presence

对档案做**纯增量**的能力补充：永不修改既有内容，只追加。改动点只有两处：`documents/linkedin/` → `documents/profiles/`（国内用脉脉领
英导出皆可）；GitHub 之外并列 Gitee/码云。

按步骤严格执行，不跳步。

---

## Step 0: 读现有档案

并行读（一次读入后不再重读）：

- `.claude/skills/job-application-assistant/01-candidate-profile.md`
- `.claude/skills/job-application-assistant/02-behavioral-profile.md`

## Step 1: 挖掘经历项

### 1a. documents/cv/
逐文件抽：课程、证书（发证方+时间）、工作责任句（工具/方法/成果）、独立项目、志愿/社团。

### 1b. documents/profiles/
领英/脉脉文档抽：Licenses & Certifications、技能与背书、志愿、项目、平台特有项。

### 1c. documents/diplomas/
成绩单抽：课程/模块、毕设题目、专业方向。

### 1d. documents/references/
推荐原文抽：推荐人用的能力措辞、提及的具体项目/工具/方法。

### 1e. GitHub / Gitee
读 01 里的 GitHub/Gitee 用户名 → 拉公开 profile 与 pin 仓库逐个读 README →
记录 name/description/主语言/topics/README 名字里的框架库；独立技术项目（原创实现，而非对他人仓库的浅层镜像或壳工程）
记录可验证能力与作品摘要：问题域、方法、成果和来源。具体专业词从选定 domain pack 读取；核心命令不预设职业或工具栈。


### 1f. 其他 URL
01 里出现过的其他 URL（个人站/博客/知乎/Kaggle/Scholar）：逐个 fetch，抽工具/方法/数据集/奖项。

## Step 2: Web 增强

对每个经历项，双管齐下：

- **A 直查**：具名工具/认证/课程直接搜官方大纲（中文课程用「课程大纲 你将学到」模式）；
- **B 推理**：不论 A 成败，都从描述推能力（问题域→所需方法→标准工具链）。

优先直查：具名慕课（Coursera/edX/极客时间/慕课网/中国大学 MOOC）、云认证（阿里云 ACE /
腾讯云 / AWS/GCP）、标准大纲的大学课、README 有技术名的仓库。
纯推理：无工具名的责任句、含混的项目描述、推荐信语言。

## Step 3: 能力图

去重分类：技术主栈 / 技术次栈 / 领域知识 / 方法与工程实践 / 软信号 / 独立项目与作品集。
每项记：名称 + 来源项 + 直查/推理标记。项目记：名称 + 一句摘要 + 来源。
已存在于 01/02 的内容剔除。

## Step 4: 用户确认

分组展示全部新增项 → `all` / `review` / `skip` / 指定跳组。等确认再写。

## Step 5: 写入（只追加）

- 01：独立项目进 Independent Projects（附来源注记 `（慕课 — 课程名）`、`（GitHub — repo）`）；
  技能进对应小节；领域知识进对应位置；
- 02：软信号进 Strongest Behaviors / How You Work Best，推断类一律标
  `*[Inferred — 推断值，复核后使用]*`。

## Step 6: 汇报

Added to 01 / added to 02 / 处理过的源 / 跳过的源 / 需人工复核项。中文输出。

---

## Design Principles

- 只添不删；来源可追溯（注记让未来重跑幂等）。
- A+B 双路并行；名为具名的认证一定查官方。
- 写前必经确认；行为推断必须带 inferred 标记。
- GitHub/Gitee 全量扫，不只 pin。
