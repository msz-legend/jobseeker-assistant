# /add-template - 注册自定义简历模板（DOCX/其他 CLI 工具链时代）

把用户自己的简历模板注册进框架：模板文件收进 `templates/cv/<name>/`，样式记入 manifest，
构造一次真实小样验证渲染，然后把「激活块」写进 `05-cv-drafting.md`，让 `/apply` 后续都用它。

出厂模板 `templates/cv/base/`（微软雅黑/宋体）基于 `tools/build_cv.py` 渲染。本命令支持两类：

1. **渲染器模板**（默认路线）：只需提供 `style.json`（字体/字号/边距配色）+ `spec.example.json`
   ——渲染逻辑复用 build_cv.py；
2. **异构工具链模板**：任何能从 CLI 产出 DOCX/PDF 的工具（WPS 模板宏、Typst、其他渲染脚本）
   ——manifest 里写清楚渲染命令，`/apply` 改用你的命令。

「命令参数」 可含 `--list` / `--use <name>` / 模板路径或空。

---

## Step 0: 参数模式

- `--list`：Glob `templates/**/TEMPLATE.md`，表格输出（name / type / 渲染器 / 字体 / active）。
- `--use <name>`：Switch 模式（见 Step 4 替代路径：读 manifest 元数据后直达 Step 4）。
  `--use default` 摘掉激活块，回到出厂 base 模板。
- 文件路径/@提及 → 备注册内容；空 → 开始访谈。

## Step 1: 类型与来源

问用户（可跳过已知的）：

1. **类型**：CV 简历模板（求职信在本仓库极少正式生成，暂不支持独立求职信模板；有需要时
   走异构工具链路线在 Step 2 说明）。
2. **来源**：现有 DOCX（提供视觉风格参照，需手工转成 style.json）、style.json 草稿、
   某编辑器模板（WPS/Word 的 .docx 样式集）、或另一工具链的 source 文件。

## Step 2: 捕捉样式元数据

从 DOCX 参照推断（页面大小/边距/标题字号/正文字号/字体）→ 设置渲染器无法继承的默认：
- **name**：kebab-case（`dark-horse`、`hr-friendly`）；不与 templates/ 冲突；
- **页边距 & 版式**：默认 A4；页数上限 1（≤5 年经验）/ 2（5 年以上）；
- **字体**：微软雅黑/宋体之外，常见候选：黑体（无衬线风）、楷体（人文风）；线上预览
  （BOSS/猎聘）不过内嵌字体的 DOCX 容易走形——提示用户导 PDF 投递；
- **页数上限**（来自 manifest：`Page limit: N`）；
- **渲染命令**（异构工具链）：完整 CLI，`<file>` 占位输出 basename；
  输出必须落到 `/apply` 读得到的路径（-o 参数或 stdout 重定向到文件）；
  可重定向中间产物的工具链就进 `build/` 子目录，确保失败不留 stale 产物；
- **已知坑**：哪些内容长度/字符会破坏这个模板。

## Step 3: 存储

写 `templates/cv/<name>/`：

1. **渲染器模板**：
   - `style.json` —— 从 Step 2 元数据落成 build_cv 样式字段（name_font/head_font/body_font/…）；
   - `spec.example.json` —— 从 `base/spec.example.json` 复制，按新样式微调；
   - `TEMPLATE.md` —— manifest（见下）;
2. **异构工具链模板**：
   - 源文件及其 assets 存进来（全部个人数据替换为 `[PLACEHOLDER]`）；
   - `TEMPLATE.md` 里**渲染命令**完整可复制，含 build 目录规则（中间文件进 `build/`，隐喻的
     失败不留 stale 产物）。

TEMPLATE.md 格式（机器与 agent 都读）:

```markdown
# Template: <name>

- **Type:** CV
- **渲染器:** build_cv.py | <other>（display label）
- **Source extension:** .style.json | .tex | .typ | ...
- **Page limit:** <N> page(s)
- **Fonts:** <主字体>（bundled in fonts/ | 系统字体）
- **Spec 示例:** spec.example.json

## 渲染命令

    <完整可复制命令>

## 样式规则

- <规则 1>

## Known pitfalls

- <坑与解法，或 "none recorded">
```

## Step 4: 验证渲染（MANDATORY）

1. 复制 spec.example.json 到临时目录（Windows `%TEMP%\opencode`，macOS/Linux
   在系统临时目录下建可写子目录，如 `$TMPDIR` 或 `/tmp` 下的一个），把占位符填成 dummy 数据（1 名 + 1 段经历 + 3 bullets 起步）；
2. 渲染器模板：
   ```bash
   python tools/build_cv.py <scratch_spec.json> -o <scratch_out.docx> --style templates/cv/<name>/style.json
   ```
   异构工具链：跑 manifest 里的渲染命令（`<file>` → scratch 文件名）。
3. 然后：
   ```bash
   python tools/verify_resume.py <scratch_out.docx> --spec <scratch_spec.json> --pdf --pages <N> --allow-placeholders
   ```
   失败逐条修（字体缺失/页超限/样式字段拼写），直到 PASS；环境没有 PDF 引擎则
   文本层 PASS 即可放行（verify 会标 WARN 提示 degraded）。
4. 清理 scratch 文件。

不过验证不激活。

## Step 5: 激活（managed block）

在 `05-cv-drafting.md` 的 H1 之后插入/替换：

```markdown
<!-- BEGIN ACTIVE-TEMPLATE (managed by /add-template - do not edit by hand) -->
> **Active template override: `<name>`**
>
> 以下与出厂指引冲突时以本块为准；结构性建议（裁剪/页数预算/砍 bullet 顺序）仍有效。
>
> - **Template manifest:** `templates/cv/<name>/TEMPLATE.md` —— 起草先读它
> - **样式:** 渲染器模板用 `--style templates/cv/<name>/style.json`；异构工具链用上面的渲染命令
> - **Page limit:** exactly <N> page(s)（`/apply` Step 5 --pages 用这个数）
> - **Output file:** `cv/main_<公司>_<岗位>.docx`
<!-- END ACTIVE-TEMPLATE -->
```

- 每个 guidance 文件**只允许一个** managed block；换模板 = 整块替换，不叠罗汉。
- `--use default` = 整块删除。
- 块外不碰任何字。

## Step 6: 汇报

> **模板 `<name>` 已注册并激活。**
> - 文件：`templates/cv/<name>/`（manifest/样式/示例）
> - 验证：渲染 + verify_resume（<N> 页限制）
> - `/apply` 之后默认用该模板。
>
> 后续：`/add-template --list` 查看；`--use <name>` 切换；`--use default` 回出厂。

---

## Design Principles

- 注册幂等：重名提示更新而非复制。
- 模板永远占位符化，可共享可提交。
- 验证是硬门槛：没渲染过的模板不会留到 /apply 中途爆炸。
- 激活是一个 managed block 的增量，框架文字不重写。
