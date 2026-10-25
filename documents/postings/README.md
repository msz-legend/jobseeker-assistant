# 岗位 JD 档案

这里保存本地岗位档案，一个岗位一个 Markdown 文件：

```text
documents/postings/<company>_<role>.md
```

## 创建岗位档案

复制 `_TEMPLATE.md`，把 JD 原文完整粘贴到文件中。来源可以是招聘平台复制文本、官网文本、聊天转发或截图转录，但截图、摘要和转录必须在 frontmatter 标记：

```yaml
jd_completeness: partial
evaluation_confidence: low
materials_allowed: false
```

`partial` 岗位可以评估和入池，但不能直接生成正式投递材料。

## 处理与状态

- `inbox`：刚录入，尚未完成评估；
- `evaluated`：已经完成门槛和评分；
- `applied`：用户确认并记录了投递；
- `interview` / `offer` / `closed`：由工作流推进的后续状态。

`/rank` 和 `/apply` 读取 frontmatter 中的 `salary_raw`、`city`、`source`、`url`、`jd_completeness` 等字段。岗位原文是后续评估、材料裁剪和面试准备的事实来源，不要只把 JD 留在聊天记录里。

索引由以下命令生成，不要手改：

```bash
python tools/posting_index.py
```
