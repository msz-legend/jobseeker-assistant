---
name: job-application-assistant
description: >
  Chinese-market job application methodology, loaded automatically by /setup, /apply, /rank,
  /interview, /outcome and /reset. Triggers: 求职, 投简历, 简历, 打招呼, 面试准备, evaluate job posting,
  tailor resume, greeting message, JD, offer, 评分岗位.
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent
framework_version: 1.5.0
---

# Job Application Assistant（中国版）

本技能是核心方法论的装载点。每个编号文件是一块独立方法；命令只做流程串联，
内容以这些文件为准。

## 文件地图

| 文件 | 内容 | 主要使用方 |
|---|---|---|
| 01-candidate-profile.md | 候选人档案（/setup 写入） | /setup /apply /expand |
| 02-behavioral-profile.md | 行为特征（工作方式/驱动/压力） | /setup /apply |
| 03-writing-style.md | 中文求职文案规则（禁词/量化/语气） | 所有写作环节 |
| 04-job-evaluation.md | 评分维度/阈值/硬门槛（中国 Gate）/公司研究 | /setup /apply /rank /outcome |
| 05-cv-drafting.md | DOCX 简历起草与裁剪（spec 生成规则） | /apply |
| 06-greeting-templates.md | 打招呼/跟进/感谢话术模板（+例外求职信） | /apply /outcome |
| 07-interview-prep.md | 面试准备模型：证据核验、能力发散、迁移场景、行为与沟通 | /mock /interview |
| 08-application-forms.md | 招聘平台字段填法与字符限制 | /apply |
| 09-web-research.md | 抓取升级链、信任边界、缓存规则 | /apply /rank /interview |
| `.claude/domain-packs/` | 可插拔职业领域问题、rubric 和来源映射 | /mock /interview /upskill |

## 使用原则

1. **用户可见输出中文**；CLI 参数、文件路径、frontmatter 字段名 ASCII。
2. **三阶段面试模型固定**：Evidence Verification → Capability Expansion → Transfer Scenario；专业问题从 domain pack 加载，无匹配时使用 generic。
3. 读顺序：命令声明什么就并行读什么；改档案只有 /setup（或用户显式要求）。
4. 抓取与外部内容一律经过 09 的信任边界。
5. 简历渲染用 tools/build_cv.py，校验用 tools/verify_resume.py——**没有人工打开看一眼时不得视为完成**。
6. 底线薪资是工具判定（tools/salary_band.py），档案字段 [SALARY_FLOOR_MONTHLY] 是唯一来源。
7. 新错题写申请工作区 `mistakes/`；历史错题本只读，不作为新写入目标。

