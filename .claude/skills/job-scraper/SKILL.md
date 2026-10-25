---
name: job-scraper
description: >-
  批量找岗位：门户 CLI（若装了）+ WebSearch site: 兜底，去重状态机管理 seen_jobs.json，
  内推线索只建链接不抓。/scrape 命令直接触发；不承担单岗位深度评估（那是 /rank 和 /apply 的事）。
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Write, Edit, Bash(python tools/scrape_state.py:*), Bash(python3 tools/scrape_state.py:*), Bash(python tools/job_key.py:*), Bash(python3 tools/job_key.py:*)
framework_version: 1.0.0
---

# 找岗（/scrape）

目标：把**岗位流**变成可评估的候选清单：候选发现 → 去重 → 与 archive/评估衔接。

主力渠道是三类：

1. **门户 CLI**（若已装）：`/add-portal` 生成或出厂 `linkedin-search`（外企）。
   发现方式：Glob `.agents/skills/*/SKILL.md`，读每个的域名（board hosts）与命令。
2. **WebSearch site: 兜底**（不依赖任何 CLI，中国主流门户的公开索引都以这类查询兜）。

**明令禁止我们自己去抓的**：BOSS 直聘 / 猎聘 / 拉勾 / 智联 / 51job / 脉脉 / 牛客的
登录墙内页——没有官方开放 API，翻页即违规风险。走「搜索命中 + 用户贴原文」

---

## Step 1: 生成候选

先读 `.claude/skills/job-scraper/search-queries.md`（/setup 维护：类别/城市词/排除词）。

### 1a. 门户 CLI 路线（装了的站点才走）

```bash
bun run .agents/skills/<portal>/cli/src/cli.ts search --query "<query>" --jobage 14 --limit 20 --format json > "%TEMP%\opencode\run_<portal>.json"
python tools/scrape_state.py store --results "%TEMP%\opencode\run_<portal>.json" --portal <portal>
```

- 每个站点一轮；错误（exit 1）记 stderr 提示，不重试超过 2 次（429 退避 30s）。
- 跑完 `python tools/scrape_state.py candidates --results` 看新候选。

### 1b. WebSearch site: 路线

对 search-queries 里每个 (类别 × 城市) 组合跑 1-2 个查询：

```
site:zhipin.com "<岗位词>" "<城市词>"
"<岗位词>" <城市词> 公司 招聘 -外包   ← 无 site 限定的补充查询
```

- 每条搜索结果抽：标题 / 公司 / 城市 / URL / 日期（能抽到的话）；
- 汇总成一个 JSON 数组（字段对齐 portal CLI 输出：id/title/company/location/date/url），
  写到临时目录后：

```bash
python tools/scrape_state.py store --results "%TEMP%\opencode\run_websearch.json" --portal websearch
```

- **job_key 保证去重**：同 URL、同公司+标题的变体在 store 时已合并;
- salary 原文能拿到就放在 title 尾部（后续 /rank 的 Salary Gate 用）。

## Step 2: 查看 & 修剪候选

```bash
python tools/scrape_state.py candidates --results 20
```

按 04 的 Hard Gates（城市/学历/年龄红线/作息）**由 orchestrator 直判，只报告不写状态**
（写回统一发生在 /rank）：

- 明显 fail 的在汇报里标「建议跳过（cause=location/salary/education…）」，不进 /rank。

## Step 3: 内推链接（Step 4.5，只建链接）

对保留的高分候选（≥60，交给 /rank 前顺手做）生成内推线索**链接清单**：

- `https://www.bing.com/search?q=site%3Amaimai.cn+"<公司>"+"<岗位>"`；
- `https://www.nowcoder.com/search?query="<公司>+<岗位>+内推>"`（type=post 过滤可加）；
- 官网：`<公司域名>/careers` 与 `site:<公司域名> 招聘`。

输出到聊天（或一个临时 md），**不抓内容**——那是用户手工浏览的入口。

## Step 4: 收尾

- `python tools/scrape_state.py history` 汇报本轮：新增 N 条、去重 M 条、站点分布；
- 提示：对 top 候选，去 `documents/postings/` 建 JD 档案（_TEMPLATE.md 复制），
  `jd_completeness: partial` 先立档；然后 `/rank`。archive/评估后用
  `python tools/posting_index.py` 重建索引。
- `job_scraper/seen_jobs.json` 中的候选若已关联 posting 文件，应携带 `posting_file`、`jd_completeness`、
  `evaluation_confidence`、`materials_allowed`；`rank_state.py` 会将这些字段投影给 scorer 并在写回时校验。
- 若只来自公开搜索结果、尚未有完整 JD 文件，默认 `jd_completeness: partial`，只能入榜评估，不能进入材料生成。

---

## 状态机（文件即状态）

- 状态文件：`.claude/skills/job-scraper/job_scraper/seen_jobs.json`（gitignore 保护）；
- key = `tools/job_key.py make-key "公司" "标题" [url]`（slug 规范化，同岗不同标题截断会合并）；
- 状态值：`new` → store 后默认；`candidates` 只吐 `new`；skipped/expired 写回由
  rank_state 统一管理（如果 /rank 与 /scrape 一起跑，tool 会保持一致性）。

## 与其他命令的分工

- /scrape 只到「有质量的新候选 + JD 档案材料就绪」；
- 批量评分 → /rank；单岗位全流程（生成简历/话术）→ /apply；
- 渠道结果（如拒信）→ /outcome（反馈给 /setup 校准）。
