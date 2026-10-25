# Jobseek Assistant — 中国求职辅助工作流

独立开发的自托管求职工作流系统：在「文件即状态」的方法论之上，按中国求职市场的实际形态重塑
**渠道、简历格式、薪资口径、面试阶段、跟进节奏、输出语言**。

这不是一个爬虫，也不是找工作外包：它是一套你（或你的 Claude Code / 其他 AI 编码代理）在你的仓库里
执行的**方法论与工具集**。所有个人数据留在本地，仓库永远是可分享的空白模板。

---

## 核心循环

```text
准备材料 → /intake → /scrape 或手动录入 JD → /rank → /apply
        → /mock → /interview → /outcome → /setup 校准
```

- `/intake` 负责收件和幂等台账，不移动原文件。
- `/apply` 负责单岗位信任门、硬门槛、评估和定向材料。
- `/mock` 是一次一题的交互式模拟，不是静态题单。
- `/interview` 消费 mock/review 结果；没有结果时明确标注未校准。
- `/outcome` 只补强未答好项，新错题进入申请工作区 `mistakes/`。

完整流程、示例和常见问题见 [docs/USER_GUIDE.md](docs/USER_GUIDE.md)，命令参数见 [docs/COMMAND_REFERENCE.md](docs/COMMAND_REFERENCE.md)。

---

## 核心设计

针对中国求职市场，本仓库做出以下设计选择：

| 维度 | 设计 |
|---|---|
| 简历管线 | **DOCX**（python-docx 渲染 JSON spec），可选导出 PDF |
| 薪资工具 | `tools/salary_band.py`：解析中文薪资区间和薪数 |
| 求职信 | 默认生成平台打招呼话术；JD 明确要求时才生成求职信 |
| 阶段词汇 | 笔试 / 电话沟通 / 一面 / 二面 / 三面 / HR面 / OC / 背调 |
| 渠道 | BOSS 直聘 / 猎聘 / 拉勾 / 智联 / 前程无忧 / 官网 / 脉脉 / 牛客；LinkedIn 仅外企 |
| 输出语言 | **默认中文** |
| 硬门槛 | 地点、薪资之外，增加学历、年龄线、户口和政治面貌等中国市场字段 |
| 运行环境 | Windows 友好：简历使用 DOCX，Python 即可跑通全流程 |

核心机制包括：posting_guard 信任门、`seen_jobs.json` 状态机（job_key / scrape_state / rank_state）、文件即状态、`framework_version` 标记、portal-skill 契约和安全模型。

---

## 快速开始

前置条件：Python 3.10+（Windows 用 `python`）以及能读取 `AGENTS.md` 的 AI 代理。可选依赖和初始化步骤见 [SETUP.md](SETUP.md)。

```bash
git clone https://github.com/msz-legend/jobseeker-assistant.git
cd jobseeker-assistant
python -m pip install python-docx pypdf pyyaml  # 可选
```

如果作为 Harness Skill 使用，把仓库中的 `SKILL.md` 放入 Harness 的 Skills 目录，再重新加载或重启 Harness。不同 Harness 版本的 Skills 目录可能不同，请以对应版本文档为准。

然后运行 `/setup` 初始化档案；有批量材料时先运行 `/intake`。公开仓库不应填写真实个人数据。

## 项目结构与文档入口

核心流程在 `.claude/commands/`，方法论在 `.claude/skills/`，可插拔职业内容在 `.claude/domain-packs/`，可执行规则在 `tools/`。个人材料和申请结果位于 `documents/`，默认被 gitignore。

- 上手教程：[docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- 命令参考：[docs/COMMAND_REFERENCE.md](docs/COMMAND_REFERENCE.md)
- 安装配置：[SETUP.md](SETUP.md)
- 安全模型：[SECURITY.md](SECURITY.md)
- 贡献规范：[CONTRIBUTING.md](CONTRIBUTING.md)

验证命令：

```bash
python tools/lint_skills.py
python tools/security_guards.py
python tools/check_framework_version.py
python -m unittest discover -s tests -p 'test_*.py'
```

## 使用约定

- 新 clone 保留档案模板；第一次 `/setup` 才创建本地个人档案。
- Claude Code 可直接执行斜杠命令；其他 agent 读取对应命令剧本，将用户消息中的命令正文作为参数。
- 国内招聘网站常有登录墙和反爬；优先粘贴 JD，遇验证立即停止，不绕过。
- 工具和命令都应在仓库根目录执行。

## 分享安全

投了哪些公司、HR 姓名、薪资历史、你的简历——全在 gitignore 里（`.gitignore` 的 `documents/**`、`job_search_tracker.csv` 等规则）。公开你的仓库前仍要人工检查 staged diff；`tools/security_guards.py` 只保证关键规则没有被删。

---

## 目录结构

```
├── AGENTS.md                 # 唯一规则入口（agent 中立，所有人/所有 runtime 读这里）
├── CLAUDE.md                 # Claude Code 转发页（@AGENTS.md 导入，零个人信息）
├── job_search_tracker.csv    # 追踪表（仅表头 + 1 行占位示例；已 gitignore）
├── .claude/
│   ├── commands/             # /setup /intake /apply /mock /interview /outcome …
│   ├── skills/               # 方法论和可复用模板
│   ├── domain-packs/         # generic + 可插拔职业领域包
│   ├── agents/               # 只读的岗位抓取、评分和审查代理
│   └── settings.json         # 权限白名单
├── .agents/skills/           # 门户搜索技能（linkedin-search 出厂；/add-portal 可增）
├── documents/
│   ├── inbound/              # materials/ 与 jd-batch/，原文件不移动
│   ├── postings/             # JD 档案；_index.md 自动生成
│   └── applications/         # mock / review / prep / mistakes 工作区
├── learning-retention-pipeline/ # 学习-保持流水线（独立子系统，规范以该目录内 SKILL.md 与 docs/spec-lock.md 为准；源文件暂未登记入库）
├── templates/cv/base/        # 简历渲染配置 base 模板（样式 JSON + TEMPLATE.md）
├── tools/                    # 全部 python 工具（posting_guard / salary_band / build_cv …）
├── tests/                    # 工具与流程测试
├── reports/                  # /html-report 输出（gitignore）
├── cv/                       # /apply 输出的定向简历（gitignore）
└── LICENSE                  # MIT 文本
```

## 许可

本项目基于 MIT License 发布，见 [LICENSE](LICENSE)。
