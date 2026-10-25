# Implementation Plan: 通用求职框架与模拟面试链路

## Overview
按交接文档 §9 的 P1–P8 顺序，新增通用收件、领域包、交互式模拟面试、错题补强与可执行校验，并保持个人材料与历史错题归档不迁移。

## Architecture Decisions
- 核心命令只描述通用流程；专业内容通过 `.claude/domain-packs/<domain>/` 注入。
- 个人工作区动态定位；公开模板只使用脱敏示例。
- 错题使用岗位工作区 `mistakes/`，全局索引只做可重建的引用与速记卡。
- 规则优先落到 stdlib 工具和 unittest，可测试的状态机不依赖模型输出。

## Task List

### Phase 1: P1–P2 基础入口
- [ ] P1 目录骨架、gitignore 例外、README
- [ ] P2 根 README 与 documents README 更新

### Phase 2: P3–P4 数据与领域基础
- [ ] P3 intake manifest、批量拆分、测试
- [ ] P4 generic/software-engineering domain packs

### Phase 3: P5–P7 面试与复盘链路
- [ ] P5 mock state、命令、测试
- [ ] P6 interview 接入 mock
- [ ] P7 mistake index、outcome 接入、测试

### Phase 4: P8 收尾
- [ ] P8 版本、命令/技能文档、隐私扫描、全量回归、提交与用户级安装

## Verification Checkpoints
- P1/P2: security guards + lint
- P3/P5/P7: 新增单元测试 + 全量 unittest
- P8: lint_skills.py、security_guards.py、check_framework_version.py、全量 unittest、git diff 检查、隐私/岗位专属词扫描

## Risks
- 既有个人文件在工作区存在但被 gitignore；公开新增文件不得引用其真实值。
- 受保护规则文件只能局部 patch。
- `security_guards.py` 的 allowlist 需要与新命令/工具权限同步，不能绕过校验。
