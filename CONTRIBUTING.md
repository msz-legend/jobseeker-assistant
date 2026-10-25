# Contributing（中国版贡献指南）

本仓库是一套**独立开发的自托管求职工作流系统**，面向中国大陆求职市场承载渠道适配、
话术模板、薪资口径与阶段词汇等本地化定制。动笔前先读 `AGENTS.md`（唯一规则入口）
与 `README.md`。

## 文档规则

- 面向使用者的教程和说明使用中文，命令、路径、字段名保持可复制。
- 新增流程必须同步更新 README、`docs/USER_GUIDE.md` 或 `docs/COMMAND_REFERENCE.md`，避免只改命令剧本。
- 公开示例只使用占位符，不包含真实姓名、联系方式、公司、学校、岗位描述或投递记录。
- Markdown 改动后运行 lint、安全校验、框架版本校验和全量测试。


- ✅ 中国市场的通用改进（渠道适配、话术模板、薪资口径、阶段词汇）——不绑定任何单一候选人
- ✅ 健壮性修复，带失败用例（先在 master 上复现，再提交修复 + 测试）
- ✅ 工具改进（tools/ 下的 python 工具，零额外依赖优先）
- ❌ 任何候选人个人数据（简历、评分表、真实 STAR、投递记录）——发布前检查与 `security_guards.py` 会报告
- ❌ 有真实姓名公司信息的例子

## 每个新文件都要

- 说明书 / 技能 / 命令：frontmatter 带 `framework_version`（`tools/check_framework_version.py` 检查）
- 用户可见文案中文；CLI 参数、字段名、文件名 ASCII
- 命令文件以 `# /<name>` 开头（`tools/lint_skills.py` 检查）
- SKILL.md frontmatter 有可解析 YAML + `name`/`description`

## 跑一下再提交

```bash
python tools/lint_skills.py
python tools/check_framework_version.py
python tools/security_guards.py
python -m unittest discover -s tests -v
```

## 不要做的事

- 别复制本仓库后把个人数据带进去再公开。见 SECURITY.md 的「公开前动作清单」。
