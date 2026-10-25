# 命令参考

所有命令都应在仓库根目录运行。Claude Code 可直接使用 `/命令`；其他代理请读取对应 `.claude/commands/<name>.md`，把命令之后的用户消息作为“命令参数”。

## `/setup`

初始化候选人档案、行为档案、评估偏好和搜索条件。只在用户确认后写入个人档案。没有材料时会进入访谈流程。

## `/intake`

扫描 `documents/inbound/`。画像材料进入 `materials/`，批量岗位进入 `jd-batch/`。使用 SHA-256 台账实现幂等；不移动、不删除原文件。

直接工具用法：

```bash
python tools/intake_manifest.py scan documents/inbound --manifest documents/_inbox_manifest.json
```

## `/scrape`

发现公开岗位。只读公开页面，必须经过 `posting_guard`；遇登录墙、验证码、频控或反爬，停止并交给用户。

## `/rank`

根据岗位档案批量排序。岗位不完整可以进入候选池，但要标注不完整，不得把不完整材料当作完整证据。

## `/apply`

处理单个岗位。先固化 JD、过信任门、做硬门槛和评分；用户确认投递后再生成简历和话术。`partial` 岗位不得生成未经证据支持的材料。

## `/mock`

交互式模拟面试。问题按 Evidence Verification、Capability Expansion、Transfer Scenario 顺序组织。状态工具：

```bash
python tools/mock_state.py create <path> <application_id> [--domain generic] [--stage first_interview]
python tools/mock_state.py show <path>
```

问题对象必须包含 `source_evidence`、`follow_ups`、`evaluation_rubric`、`reference_answer` 和 `transfer_link` 等契约字段。

## `/interview`

根据当前申请的 mock/review 生成准备包。存在模拟结果时必须使用其中的 gaps 和风险；不存在时标注“未经模拟面试校准”。

## `/outcome`

记录面试或投递结果，计算跟进动作，并将新错题写入申请工作区 `mistakes/`。历史 `09_错题本.md` 不再作为写入目标。

## `/html-report`

读取本地 tracker、岗位档案和申请目录，生成本地 HTML 汇总。报告不应提交到公开仓库。

直接工具用法：

```bash
python tools/html_report.py --out reports/application-dashboard.html
```

支持 `--tracker`、`--applications`、`--today` 覆盖输入目录和测试日期；缺少 tracker 或申请目录时生成空报告。

## `/upskill`

根据已确认的能力缺口生成学习计划。它不能把岗位要求直接当成候选人事实。

## `/expand`

从候选人主动提供的材料和公开主页中补充能力项。新增内容要标注来源和推断性质，写入前必须确认。

## `/reset`

恢复指定范围的模板状态。它是破坏性操作，覆盖或删除前必须明确确认，并先展示影响范围。

## `/add-portal`

为公开、可读的招聘页面生成门户技能。不得绕过登录、验证码、robots 或反爬，也不得写入上传数据的命令。

## `/add-template`

注册新的简历或输出模板。模板必须使用占位符，不得把真实候选人材料提交到框架层。

## 常用工具

```bash
python tools/posting_guard.py --help
python tools/salary_band.py --help
python tools/job_key.py --help
python tools/intake_manifest.py --help
python tools/mock_state.py --help
python tools/mistake_index.py --help
```

## 开发验证

```bash
python tools/lint_skills.py
python tools/security_guards.py
python tools/check_framework_version.py
python -m unittest discover -s tests -p 'test_*.py'
git diff --check
```
