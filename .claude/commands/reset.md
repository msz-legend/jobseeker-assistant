# /reset - Reset Candidate Profile Data（回到空白模板）

破坏性命令：把候选人的技能文件与材料目录重置回空白模板。三档范围：`profile`（档案类技能文件）、`documents`
（用户材料目录）、`all`。**任何删除前都要 Step 2 的显式确认（输入大写 RESET）**。

对 「命令参数」 空时先问范围（profile / documents / all）再继续。

---

## Step 1: 展示将清除的内容

### profile 范围

读取并报告以下文件现在的状态（有内容 / 已空白）：

- `.claude/skills/job-application-assistant/01-candidate-profile.md` —— 替换为空白模板
- `.claude/skills/job-application-assistant/02-behavioral-profile.md` —— 替换为空白模板
- `.claude/skills/job-application-assistant/04-job-evaluation.md` —— 只清个性化值
  （match areas / goals / 喜恶任务 / 生活约束 / Hard Gates 表 / Calibration 节）；
  评分框架（维度/权重/阈值/Gate 定义）保留
- `.claude/skills/job-application-assistant/06-greeting-templates.md` —— 只清「我的常用底稿」
  小节（如有）；模板与方法保留
- `.claude/skills/job-application-assistant/07-interview-prep.md` —— 只清 `## 我的三句式自我介绍`
  与 `## Ready-Made STAR Examples`（含用户 STAR 实例）；框架保留
- `.claude/skills/job-scraper/search-queries.md` —— 恢复占位符（岗位词/城市词/排除词/站点偏好）
- ~~`CLAUDE.md` 候选人区块~~ 已废止——它只剩 `@AGENTS.md` 转发页，零个人信息，`/reset` 无需处理

所有替换保留文件 top 的 `framework_version` frontmatter（检查工具需要它）。

### documents 范围

列出 `documents/{cv,profiles,diplomas,references,projects,postings,applications}/`
全部非 `.gitkeep` 文件（含嵌套与隐藏文件）。`documents/README.md` 不删。
若 postings/ 有文件，额外提示将同时删除各岗位档案（JD 原文不可再恢复）。

## Step 2: 确认

> **此操作不可撤销。输入 `RESET`（全大写）确认，其他输入取消。**

## Step 3: 执行

- profile：按 Step 1 列表逐文件写回模板版本（模板即本仓库出厂内容——直接从 skill 文件里的
  占位符重构，或从 `documents/postings/_TEMPLATE.md` 类比地重建结构）。
- documents：删除用户文件，保留目录、`.gitkeep`、README。然后重建骨架：
  - `documents/postings/_index.md`：跑 `python tools/posting_index.py`（空目录生成空索引）
  - `job_search_tracker.csv`：**不自动删**。询问用户是否重置为表头 + 示例行（默认否）。
- 删除 `company_research/*.json` 缓存（profile 校准时重建），询问后执行。

## Step 4: 汇报

列出实际清除 / 保留清单 + 下一步（`/setup` 重跑）。重申：git 历史不在此流程内，
公开仓库前按 SECURITY.md 的动作清单处理。
