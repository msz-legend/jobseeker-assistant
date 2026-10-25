# /add-portal - 接入一个招聘门户搜索技能

帮用户为一个招聘网站生成门户搜索技能（零依赖 CLI，符合统一契约）。生成器**国家无关**；
产出的技能通常是市场特定的，保留在本仓库的 `.agents/skills/` 下作为本地资产。

中国语境：BOSS 直聘 / 猎聘 / 拉勾 等**主流门户有登录墙与强反爬，官方无公开 API**——
这类站不适合本命令，走「粘贴 JD + WebSearch 检索」路线（见 job-scraper SKILL）。
适合本命令的是：**公司官网招聘页**、**牛客内推/校招页**、**行业垂类站**、
**外企 ATS（Greenhouse/Lever/Workday 中国岗位页）** 等***公开可读***的站点。

「命令参数」 可含 `--list`、门户 URL 或空。

---

## Step 0: 参数

- `--list`：Glob `.agents/skills/*/SKILL.md`，打印已装门户表格（名称/市场/数据源），结束。
- URL：带入 Step 1。
- 空：开始访谈。

## Step 1: 访谈

1. **门户 URL**（公开首页或搜索页）；
2. **技能名**（kebab-case，`-search` 结尾；不得与 `.agents/skills/` 现有目录冲突）；
3. **市场与语言**（中国城市名 + 中文触发词要写进 SKILL.md 描述，如「内推」「应届校招」）;
4. **现实测试查询**（一个真实会搜的岗位词）。

## Step 2: 侦察（先探后写）

对门户本体做侦察（WebFetch 或 `python tools/fetch_page.py '<URL>' --text`）：

1. **搜索 URL 模式**：endpoint、query 参数、城市/年龄分页参数；有 JSON API 优先。
2. **拉一条真实结果响应**，确定每条结果的字段锚点：id/title/company/location/date/url。
3. **详情页模式**：描述/时限/apply 链接的位置。
4. **访问与合规检查**（相机关键）：
   - robots.txt 禁了路径 → 停，建议官方 API；
   - 需登录才能看列表 → 停（Boss/猎聘就在这档）；
   - 条款禁止自动化 → 明确告知，用户坚持则生成的 SKILL.md 必须带醒目的个人使用声明；
   - 有第三方付费抓取服务才能用的门户 → **先报价再创建**，token 只读
     环境变量 `<SERVICE>_API_TOKEN`，绝不写进仓库。
5. 所有发现记入 url-reference.md。

## Step 3: 生成技能（契约照搬，一个字不改）

-canonical 参考：`.agents/skills/linkedin-search/`（零依赖样例）。结构：

```
.agents/skills/<name>/
├── SKILL.md              # name/version/description(含中文触发词)/allowed-tools
├── url-reference.md      # Step 2 的端点与锚点记录
└── cli/
    ├── package.json      # 零运行时依赖；scripts: start/test/typecheck
    ├── tsconfig.json
    ├── README.md
    ├── src/cli.ts        # 参数解析 + 命令分发
    ├── src/helpers.ts    # fetch+backoff、解析器、错误写出
    └── src/commands/{search,detail}.ts
    └── tests/helpers.ts  # runCLI/parseJSON 工具
```

契约（违规即坏品）：
- 命令：`search` 和 `detail <id|url>`；
- flags：`--query/-q`、`--jobage <days>`、`--page <n>`、`--limit <n>`、`--format json|table|plain`（默认 json）；
- JSON 形状：`{ "meta": { "count", "page" }, "results": [...] }`，结果至少 id/title/company/location/date/url（缺则 null 不省略）；
- 错误写 stderr 的 `{ "error", "code" }`，exit 1；
- UA 自报家门（`Mozilla/5.0 (compatible; <portal>-cli/1.0)`），429/5xx 指数退避；
- HTML 解析按结果块分割，单块坏不连坐；
- 零运行时依赖（bun + fetch + 正则）。

## Step 4: 实测（不过测不注册）

```bash
cd .agents/skills/<name>/cli && bun install && bun run typecheck
bun run src/cli.ts search -q "<测试查询>" --limit 5 --format table
bun run src/cli.ts detail <id> --format plain
bun run test
```

结果字段全部是真实数据（不是空串/HTML 残渣）；失败修到过；限频就退避。

## Step 5: 注册

1. 问用户是否入 `/scrape` 主力渠道。是：`/scrape` 的 CLI 发现已自动生效，但
   settings 与守卫要同步——在 `.claude/settings.json` 加
   `Bash(bun run .agents/skills/<name>/cli/src/cli.ts:*)`，同时把该串加入
   `tools/security_guards.py` 的 `ALLOWED_PERMISSIONS`（**同一提交**）。
2. 建议在 `search-queries.md` 加该站点的 site: 了 WebSearch 备用法（用 `[YOUR_JOB_BOARD]` 风格占位）。

## Step 6: 汇报

生成/实测/注册三段式汇报 + 试跑命令一行。提醒：如果站点日后改版，照 url-reference.md 修解析。
