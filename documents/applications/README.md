# 申请工作区

每个岗位申请使用一个本地目录：

```text
documents/applications/<application_id>/
```

`application_id` 由输入岗位和申请信息决定，核心命令不会把公司或职业写死。

## 常见文件

```text
<application_id>/
├── application.yaml              # 申请元数据（可选）
├── mock_<stage>_<date>.json      # 模拟面试状态
├── mock_<stage>_<date>.md        # 模拟面试展示稿（可选）
├── review_<stage>_<date>.json    # 面试复盘（可选）
├── review_<stage>_<date>.md      # 面试复盘展示稿（可选）
└── mistakes/                     # 本次申请暴露出的可复用缺口
```

这些文件属于本地个人工作区，默认不进入 Git。`/mock` 保存问题、回答和状态；`/interview` 读取最新 mock/review 生成准备包；`/outcome` 记录结果并把未答好项整理进 `mistakes/`。

没有模拟结果时，面试准备必须明确标注“未经模拟面试校准”，不能假装已经完成校准。
