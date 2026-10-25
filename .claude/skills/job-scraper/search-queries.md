---
framework_version: 1.0.0
---

# 搜索查询模板（/setup 维护；/scrape 消费）

占位符里是你要填的真实意图：类别词、城市词、站点偏好。保持 `[YOUR_*]`/`[EXCLUDE_*]` 大写风
（lint 可检出）。

## 站点清单（默认）

| 站点 | 域名 | 抓取方式 | 备注 |
|---|---|---|---|
| BOSS 直聘 | zhipin.com | WebSearch site: 兜底 + 贴原文 | 主战场；登录墙 |
| 猎聘 | liepin.com | WebSearch site: 兜底 + 贴原文 | 猎头多 |
| 拉勾 | lagou.com | WebSearch site: 兜底 | 技术岗 |
| 智联招聘 | zhaopin.com | WebSearch site: 兜底 | B 端/国央企 |
| 前程无忧 | 51job.com | WebSearch site: 兜底 | 覆盖面广 |
| 公司官网 | `<公司域名>/careers` | 升级链抓取（09） | 岗位最准，更新最快 |
| 脉脉 | maimai.cn | 内推链接 only | 帖子标 unverified |
| 牛客 | nowcoder.com | 内推链接 only | 校招/笔试回忆贴 |
| LinkedIn | linkedin.com | linkedin-search CLI | 外企/海外 |

## 查询类别（按 01 的意向岗位填）

### 类别：[PRIMARY_JOB_KEYWORD_1]（如：Go 后端）

```
site:zhipin.com "[PRIMARY_JOB_KEYWORD_1]" "[YOUR_CITY_WORD]"
site:liepin.com "[PRIMARY_JOB_KEYWORD_1]" "[YOUR_CITY_WORD]"
"[PRIMARY_JOB_KEYWORD_1]" "[YOUR_CITY_WORD]" 招聘 头条 -外包
```

### 类别：[SECONDARY_JOB_KEYWORD_2]

```
site:zhipin.com "[SECONDARY_JOB_KEYWORD_2]" "[YOUR_CITY_WORD]"
```

### 特化查询（校招/内推/方向限定，按需）

```
site:nowcoder.com "[PRIMARY_JOB_KEYWORD_1]" 校招 "[YOUR_CITY_WORD]"
"[COMPANY_WATCHLIST_WORD]" 招聘 "[PRIMARY_JOB_KEYWORD_1]"   ← watchlist 公司定向扫
```

## 城市/地域词

- 主战：`[YOUR_CITY_WORD]`（如「北京」「朝阳」双写）
- 扩展：`[YOUR_EXTENDED_CITY_WORDS]`（可空）

## 排除词（默认开启在 WebSearch 查询里，站点内筛选用 UI）

```
[EXCLUDE_KEYWORDS]   例：外包,驻场,劳务派遣,人寿保险,教育培训（按你自己的红线增删）
[NON_EXCLUDE_NOTE]   例如外包岗想看但不想投，别放这里，改为 /rank 的 cause 降档
```

## 试用期刷新节奏

- 常规轮：每 3-5 天一轮（Step 1 全类别）；闲时周更一次即可；
- 冲刺期：每日一轮，只跑 top 类别。
