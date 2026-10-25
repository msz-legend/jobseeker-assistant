# SETUP.md — 安装与入职指南（中国版）

本框架可以在 Claude Code 或其他能读取 `AGENTS.md` 和 Markdown 命令剧本的 AI 代理中运行。本文件讲安装、初始化和第一次试跑；完整流程看 `docs/USER_GUIDE.md`，命令参数看 `docs/COMMAND_REFERENCE.md`。

---

## 1. 前置条件

| 组件 | 必须? | 说明 |
|---|---|---|
| Python 3.10+ | ✅ | Windows 上用 `python` 命令（本框架不使用 `python3` 别名） |
| Claude Code | ✅ | 或任何能读 `AGENTS.md`/`CLAUDE.md` 的编码代理 |
| python-docx | 可选 | 简历 DOCX 渲染（`/apply` 步骤需要装） |
| pypdf | 可选 | 校验导出 PDF 的页数与文字（有它才能跑 PDF 级校验） |
| pyyaml | 可选 | `tools/lint_skills.py` 解析 frontmatter；无则用内置兜底解析 |
| Microsoft Word / LibreOffice | 可选 | 仅当目标渠道要 PDF 时用于 DOCX→PDF 导出；没有也能跑（文本级校验兜底） |
| Node(bun) | 可选 | 仅 `linkedin-search` 门户 CLI（外企/海外岗）需要 |

安装可选依赖：

```bash
pip install python-docx pypdf pyyaml
```

## 2. 安装

```bash
git clone <your-repo-url> job-search && cd job-search
```

公开仓库前别忘了检查隐私规则（见 `SECURITY.md` §5）：个人目录已全部 gitignore。

## 3. 首次运行

```bash
claude          # 在仓库目录打开
> /setup
```

`/setup` 有三条路径：

1. **文档导入** —— 把现有简历（DOCX / PDF / 图片均可）、领英或脉脉导出、项目说明放进
   `documents/cv/`、`documents/profiles/`、`documents/projects/`，`/setup` 自动读取抽取。
2. **现场访谈** —— 没有现成文档，Claude 会逐项问你（工作经历、项目、评分校准、渠道）。
3. **混合** —— 都可以。

配置要点（中国市场特有约定）：

- **期望薪资**：`[范围]K × [N] 薪`，并单独确认**底线月薪**——它会被写进
  01-candidate-profile.md，`/apply`、`/rank` 用 `tools/salary_band.py` 对它校验。
- **渠道清单**（Step 9 附近）：BOSS 直聘 / 猎聘 / 拉勾 / 智联招聘 / 前程无忧 / 公司官网 /
  脉脉（内推与人脸）/ 牛客（内推与笔试题）；外企与海外机会可加 LinkedIn（`/add-portal`）。
- **硬门槛**：城市 / 学历（统招要求）/ 年龄偏好 / 户口（offer 前确认）/ 政治面貌（体制内）。
- **语言**：默认中文输出；如你同时投外企，可要求 Claude 对外企岗位用英文简历管线，
  该情形属于 `/add-template` 的高级用法，默认不搭载。

## 4. 完整工作流

```text
/setup       初始化本地档案
/intake      扫描材料和批量 JD，记录幂等台账
/scrape      发现公开岗位（可选）
/rank        批量排序
/apply       单岗位评估、定向材料和记账
/mock        交互式模拟面试
/interview   消费 mock/review 生成准备包
/outcome     记录结果、跟进并补强错题
/html-report 生成本地 HTML 汇总（`python tools/html_report.py --out reports/application-dashboard.html`）
/upskill      根据缺口生成学习计划
/reset        恢复模板状态（破坏性操作，需确认）
```

不需要每次执行所有命令：已有岗位时可以直接从 `/apply` 开始；面试前可以直接运行 `/mock`。详细说明见 `docs/USER_GUIDE.md`。

## 5. 一次最小可用的会话（5 分钟试跑）

1. 打开 BOSS 直聘 App，找一个你不反感的岗位，把 JD 文本复制。
2. `documents/postings/` 里复制 `_TEMPLATE.md` 为 `<公司>_<岗位>.md`，把 JD 粘进「JD 原文」。
3. 对 Claude 说：`/apply`。它会跑信任门 → 硬门槛 → 评分 →（若你放行）生成定向简历 spec
   → 渲染 DOCX → 校验 → 生成打招呼话术 → 记 tracker。
4. 检查 `cv/main_<公司>_<岗位>.docx` 打开无误（Word / WPS 均可）。

## 6. 常见问题

- **我的机器没有 Word，能投吗？** 能。绝大多数国内渠道收 DOCX 或 PDF 均可；没有 Word 时
  `verify_resume.py` 会退化成文本级校验（页数校验跳过并提示）。
- **python3 没了？** Windows 上的标准解释器叫 `python`。框架所有文档与权限白名单都写 `python`。
- **BOSS / 猎聘能把 JD 抓下来吗？** 它们有登录墙与反爬，官方不开放。推荐把页面/App 聊天框
  里的 JD 复制粘贴（截图转文字也支持，注明「来源：截图转录」）。
- **我可以把经验数字填进工具吗？** 档案里的薪资底线等数字是你的个人数据（`01-candidate-profile.md`
  已在 `.gitignore` 内）。**要防泄露就别把真实数字提交**；公开仓库前
  用 `/reset` 或手工把 skills 01/04 还原成占位符。
