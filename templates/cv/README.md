# 简历模板

每个子目录代表一个可复用的简历模板。当前仓库提供 `base/` 中文模板；新增模板可通过 `/add-template` 注册。

## 模板结构

```text
templates/cv/<name>/
├── TEMPLATE.md        # 页数、样式和限制说明
├── style.json         # build_cv.py 的字体、字号、边距等覆盖
└── spec.example.json  # 内容 spec 示例，只放占位符
```

`/apply` 生成的真实简历 spec 和 DOCX 会写入仓库根目录的 `cv/`，该目录默认被 `.gitignore` 排除。模板目录本身只能放占位符和公开规则，不要把真实候选人经历、联系方式或公司定向内容写进来。

直接使用工具时，典型流程是：

```bash
python tools/build_cv.py cv/main_<company>_<role>.json \
  -o cv/main_<company>_<role>.docx \
  --style templates/cv/base/style.json

python tools/verify_resume.py cv/main_<company>_<role>.docx \
  --spec cv/main_<company>_<role>.json
```
