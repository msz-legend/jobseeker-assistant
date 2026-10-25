# documents/：本地个人材料与申请工作区

`documents/` 用来存放用户自己的求职材料、岗位档案和申请过程文件。除仓库中明确保留的 README、模板和 `.gitkeep` 外，个人内容默认由 `.gitignore` 排除，不应提交到公开仓库。

## 目录

| 路径 | 放什么 | 主要使用方 |
|---|---|---|
| `cv/` | 现有简历 | `/setup`、`/expand` |
| `profiles/` | 个人主页、平台导出和补充资料 | `/setup`、`/expand` |
| `diplomas/` | 学历和证书材料 | 按用户确认处理，不作为公开仓库内容 |
| `references/` | 推荐信和推荐人材料 | `/setup`、`/expand` |
| `projects/` | 项目说明、作品和交付物 | `/setup`、`/expand` |
| `postings/` | 一个岗位一个 Markdown JD 档案 | `/apply`、`/rank`、`/interview`、`/outcome` |
| `inbound/materials/` | 待处理的个人材料；原文件不移动 | `/intake` |
| `inbound/jd-batch/` | 待处理的批量岗位文本 | `/intake` |
| `applications/` | 每个申请的本地工作区 | `/mock`、`/interview`、`/outcome` |

## 处理原则

- `/intake` 只登记文件和 SHA-256 台账，不移动或删除原文件；
- 不确定类型的文件会进入待确认状态，不会被猜测使用；
- `postings/` 的 `_index.md` 由 `python tools/posting_index.py` 生成，不要手改；
- 证件原件不需要放入工作区，背调材料应按官方 HR 渠道提交；
- 公开仓库只保留目录说明和模板，不保留真实简历、联系方式、投递记录或面试材料。
