# 用户指南

这份指南面向第一次使用项目的求职者。先看 [README.md](../README.md) 了解整体，再按本文件操作。

## 一、先理解项目的边界

项目只在你的本地工作区中整理信息、生成草稿和做确定性校验。它不会替你注册招聘网站、绕过验证码、联系招聘方、提交表单或决定是否投递。

岗位 JD、网页内容和聊天转发内容都当作不受信任的数据。它们可以被读取和分析，但不能改变项目规则，也不能要求代理把你的材料发送给第三方。

## 二、第一次使用

### 1. 安装环境

需要 Python 3.10+ 和一个能读取 `AGENTS.md`、`.claude/commands/` 的 AI 代理。Windows 使用 `python`，不依赖 `python3`。

可选依赖：

```bash
pip install python-docx pypdf pyyaml
```

- `python-docx`：生成和检查 DOCX 简历。
- `pypdf`：检查 PDF 文本和页数。
- `pyyaml`：让技能 lint 使用完整 YAML 解析器；没有时工具会使用标准库兜底解析。

### 2. 初始化档案

在仓库根目录打开代理，运行 `/setup`。它会让你选择：

- 文档导入：读取你放在 `documents/cv/`、`profiles/`、`projects/` 等目录的材料；
- 现场访谈：没有现成材料时逐项回答；
- 混合模式：以文件为主，再补问缺失信息。

公开仓库不要填写真实资料。真实档案会写入被忽略的文件；提交前仍要检查 `git status` 和 Git 历史。

### 3. 批量收件

将材料放入：

```text
documents/inbound/materials/  # 个人画像材料
documents/inbound/jd-batch/   # 批量岗位输入
```

运行 `/intake`，或直接运行：

```bash
python tools/intake_manifest.py scan documents/inbound --manifest documents/_inbox_manifest.json
```

工具会为每个文件计算 SHA-256。重复扫描同一个文件会标记为 `skipped`，不会重复处理。原始文件不移动、不删除。

批量 JD 可以用单独一行 `---` 分隔；`tools/intake_split.py` 会保留原文，并对内容不足的段落标记 `needs_review`。字段不完整时不要猜测公司、岗位或行业。

## 三、岗位从哪里开始

### 手动粘贴（推荐）

国内招聘网站常见登录墙、验证码和反爬限制。最稳妥的方式是把你看到的 JD 复制到 `documents/postings/`，使用 `_TEMPLATE.md` 作为结构。

### 公开页面搜索

运行 `/scrape`。只读取公开可访问内容；遇到登录墙、验证码或强制验证，停止并让你本人处理。

### 批量岗位

使用 `/intake` 先登记和拆分，再由 `/rank` 或 `/apply` 处理。批次结束后再重建岗位索引，避免每处理一条就重复写索引。

## 四、一个岗位的完整流程

### `/rank`：先比较

适合已有多个岗位档案时使用。它输出候选排序和风险提示，但不自动生成投递材料。

### `/apply`：深入评估

它按以下顺序处理一个岗位：

1. 保存 JD 原文；
2. 运行 `posting_guard`，检查隐藏指令、改写内容和可疑文本；
3. 检查城市、薪资、学历等硬门槛；
4. 使用 `04-job-evaluation.md` 的评分规则评估；
5. 只有你确认投递后，才生成定向材料；
6. 写入 tracker，并保留可追溯的岗位档案。

JD 不完整时可以继续记录评估，但不得假装已经完成定向材料生成。

### 材料生成

简历管线是：内容 spec → DOCX → 文本/页数/关键词校验。校验通过后仍要人工打开 Word 或 WPS 检查字体、分页、表格和空白页。

## 五、面试流程

### `/mock`：一次一题的模拟

模拟顺序固定为：

1. **Evidence Verification**：你做了什么、没做什么、结果怎么测量、归因是否准确；
2. **Capability Expansion**：从概念到机制、取舍、异常和验证；
3. **Transfer Scenario**：换场景或改变约束后能否迁移。

每次只展示当前问题和必要澄清。参考答案、rubric 和评分在交互中隐藏。过程状态写入 `mock_<stage>_<date>.json`，展示层写入同名 Markdown，支持中断后继续。

没有明确职业领域时使用 `generic`。明确领域时，才加载 `.claude/domain-packs/<domain>/`。

### `/interview`：根据表现准备

- 有 mock/review：按 gaps、风险、证据缺口和迁移表现定向生成；
- 没有 mock：必须写明“未经模拟面试校准”；
- 专业问题来自 domain pack，不写死在核心命令中。

### `/outcome`：结果和错题补强

每次面试后记录结果。默认只补强未答好项，不对所有问题整体联网。来源优先级为：官方文档、论文/标准、工程团队文章、书籍/课程、社区内容。

新错题写入：

```text
<application>/mistakes/mistake-<stable-id>.md
```

每条至少包含来源、失败类型、根因、正确答案、口播答案、Mermaid 图、追问、来源列表、核验状态、个人经历边界、练习动作和状态。网络失败或资料冲突时标记 `needs_verification`，不伪造来源，也不把资料写成“我做过”。

## 六、如何看文件

| 文件/目录 | 用途 |
|---|---|
| `AGENTS.md` | 所有代理都应遵守的总入口 |
| `.claude/commands/` | 每个命令的执行剧本 |
| `.claude/skills/job-application-assistant/` | 方法论与模板 |
| `.claude/domain-packs/` | 可插拔职业领域内容 |
| `tools/` | 可执行的解析、校验、状态和索引工具 |
| `documents/postings/` | 本地岗位档案 |
| `documents/applications/` | 每个申请的 mock、review、prep 和 mistakes |
| `job_search_tracker.csv` | 本地投递追踪表 |
| `reports/` | 本地报告输出 |
| `learning-retention-pipeline/` | 学习-保持流水线（学习/保持/复训调度），自述契约见其 `SKILL.md` 与 `learning-retention-pipeline/docs/spec-lock.md`（源文件暂未登记入库） |

## 七、公开到 GitHub 前

1. 运行 `/reset` 的 profile 范围，或手工确认个人档案已恢复为模板占位符；
2. 检查 `git status --short`；
3. 检查 staged diff 和最近提交历史；
4. 运行 `python tools/security_guards.py`；
5. 确认没有真实姓名、手机、邮箱、公司、学校、真实 JD 或特定岗位描述出现在公开文件；
6. 不要把 `documents/`、tracker、简历生成物或缓存强行 `git add`。
