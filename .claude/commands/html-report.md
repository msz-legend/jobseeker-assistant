# /html-report - 求职追踪仪表盘

从 `job_search_tracker.csv` 与 `documents/applications/` 归档生成一个自包含 HTML 仪表盘。
单文件、无外部依赖、直接浏览器打开。输出中文界面。

## Step 0: 解析参数

- 无参数 → 输出到 `reports/application-dashboard.html`（目录不存在则创建）
- 传路径参数 → 写到该路径
- `--open` → 写完提示用户手动打开（Claude 不直接起浏览器）

## Step 1: 读取数据

1. **`job_search_tracker.csv`** —— 主数据源。解析 15 列：
   `date,company,sector,role,role_type,channel,status,stage,contact_person,fit_rating,notes,cv_file,greeting_file,source,deadline`
   - 早于 15 列 schema 的旧行：缺列当空串，不丢行；
   - `status` 枚举：drafted / applied / followup / interview / offer / accepted / rejected / withdrawn；
   - `stage` 枚举：笔试 / 电话沟通 / 一面 / 二面 / 三面 / HR面 / OC / 背调；
   - 第一行是占位示例行（company=[示例公司]）→ 跳过。
2. **`documents/applications/`** —— 列出每个 `<公司>_<岗位>/` 归档目录及其文件名
   （prep_*.md、greeting 等），只列文件名，不读内容。

## Step 2: 报告内容（硬性要求）

- **概览卡**：总申请数 / 在面试 stage 数 / offer 数 / 被拒数 / 近 7 天新增；
- **漏斗表**（stage 枚举为准）：申请 → 笔试 → 一面 → 二面 → 三面 → HR面 → OC → offer；
  每格是「当前处于该 stage 的数量 + 历史经过该 stage 的数量」；
- **渠道效能表**：渠道 × 状态矩阵（BOSS / 官网 / 猎聘 / 内推 …），找出转化率最高的渠道；
- **跟进到期清单**：按 outcome.md 的阈值（BOSS 5-7 天、邮件 10 天）算出「今天该跟进 / 已超期」；
- **公司明细列表**：每行 company / role / status / stage / fit_rating / 最近动作（notes 末条）/ 归档文件数；
- **隐私提示页脚**：明细含个人信息，报告文件位于 reports/（gitignored），勿传播。

## Step 3: 生成规则

- 单文件 HTML，内联 CSS（系统字体栈，中文界面），无 JS/无网络资源；
- 网格用简单表格；配色至少给 status level：in-flight 蓝 / offer 绿 / rejected 红 / neutral 灰；
- 不要从归档文件外泄内容到 HTML，只列文件名与计数；
- 写完打印绝对路径与行数摘要。
