#!/usr/bin/env python3
"""Generate a self-contained local HTML dashboard for job applications."""
from __future__ import annotations

import argparse
import csv
import html
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

FIELDS = [
    "date", "company", "sector", "role", "role_type", "channel", "status", "stage",
    "contact_person", "fit_rating", "notes", "cv_file", "greeting_file", "source", "deadline",
]
STAGES = ("笔试", "电话沟通", "一面", "二面", "三面", "HR面", "OC", "背调")
STATUSES = ("drafted", "applied", "followup", "interview", "offer", "accepted", "rejected", "withdrawn")


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if not stream.encoding or stream.encoding.lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


def parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def load_tracker(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return []
        missing = [field for field in FIELDS if field not in reader.fieldnames]
        if missing:
            raise ValueError(f"tracker 缺少 15 列字段: {', '.join(missing)}")
        rows = []
        for row in reader:
            normalized = {field: str(row.get(field) or "") for field in FIELDS}
            if normalized["company"] == "[示例公司]":
                continue
            rows.append(normalized)
        return rows


def application_files(root: Path) -> dict[str, list[str]]:
    if not root.is_dir():
        return {}
    return {
        directory.name: sorted(path.name for path in directory.iterdir() if path.is_file())
        for directory in sorted(root.iterdir()) if directory.is_dir()
    }


def application_file_count(files: dict[str, list[str]], company: str, role: str) -> int:
    """Match dynamic application IDs without assuming one naming convention."""
    def norm(value: str) -> str:
        return "".join(ch.casefold() for ch in value if ch.isalnum())

    company_key, role_key = norm(company), norm(role)
    count = 0
    for application_id, names in files.items():
        key = norm(application_id)
        if (company_key and company_key in key) or (role_key and role_key in key):
            count += len(names)
    return count


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def last_note(value: str) -> str:
    return value.split("|")[-1].strip() if value else ""


def followups(rows: list[dict[str, str]], today: date) -> list[dict[str, str]]:
    result = []
    for row in rows:
        if row["status"] in {"rejected", "withdrawn", "accepted"}:
            continue
        sent = parse_date(row["date"])
        if not sent:
            continue
        days = 5 if row["channel"] in {"BOSS直聘", "BOSS 直聘", "内推", "脉脉", "牛客"} else 10
        due = sent + timedelta(days=days)
        if today >= due:
            result.append({"company": row["company"], "role": row["role"], "due": due.isoformat(), "overdue": today > due})
    return result


def render(rows: list[dict[str, str]], files: dict[str, list[str]], today: date) -> str:
    status_counts = Counter(row["status"] for row in rows)
    stage_current = Counter(row["stage"] for row in rows if row["stage"])
    recent = 0
    for row in rows:
        row_date = parse_date(row["date"])
        if row_date and today - row_date <= timedelta(days=7):
            recent += 1
    pending = followups(rows, today)
    channel_status = Counter((row["channel"] or "未填写", row["status"] or "未填写") for row in rows)

    stage_rows = "".join(
        f"<tr><td>{esc(stage)}</td><td>{stage_current.get(stage, 0)}</td></tr>" for stage in STAGES
    )
    unknown = sorted(stage for stage in stage_current if stage not in STAGES)
    if unknown:
        other_count = sum(stage_current[stage] for stage in unknown)
        stage_rows += f"<tr><td>其他：{esc('、'.join(unknown))}</td><td>{other_count}</td></tr>"
    channel_rows = "".join(
        f"<tr><td>{esc(channel)}</td><td>{esc(status)}</td><td>{count}</td></tr>"
        for (channel, status), count in sorted(channel_status.items())
    ) or '<tr><td colspan="3">暂无数据</td></tr>'
    followup_rows = "".join(
        f"<tr><td>{esc(item['company'])}</td><td>{esc(item['role'])}</td><td>{item['due']}</td><td>{'已超期' if item['overdue'] else '今天跟进'}</td></tr>"
        for item in pending
    ) or '<tr><td colspan="4">暂无到期跟进</td></tr>'
    detail_rows = "".join(
        f"<tr><td>{esc(row['company'])}</td><td>{esc(row['role'])}</td><td>{esc(row['status'])}</td>"
        f"<td>{esc(row['stage'])}</td><td>{esc(row['fit_rating'])}</td><td>{esc(last_note(row['notes']))}</td>"
        f"<td>{application_file_count(files, row['company'], row['role'])}</td></tr>"
        for row in rows
    ) or '<tr><td colspan="7">暂无申请记录</td></tr>'
    archive_rows = "".join(
        f"<li>{esc(application_id)}：{', '.join(esc(name) for name in names)}</li>"
        for application_id, names in files.items()
    ) or "<li>暂无申请归档</li>"

    cards = "".join(
        f'<div class="card"><div class="label">{esc(label)}</div><div class="value">{value}</div></div>'
        for label, value in (
            ("总申请数", len(rows)),
            ("当前面试数", status_counts.get("interview", 0)),
            ("Offer 数", status_counts.get("offer", 0)),
            ("被拒数", status_counts.get("rejected", 0)),
            ("近 7 天新增", recent),
        )
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<title>求职追踪仪表盘</title><style>
body{{font-family:system-ui,'Microsoft YaHei',sans-serif;color:#202124;background:#f6f7f9;margin:0;padding:24px}}
h1{{margin-top:0}} .cards{{display:flex;gap:12px;flex-wrap:wrap}} .card{{background:white;border-radius:10px;padding:16px 22px;min-width:120px;box-shadow:0 1px 4px #0001}} .label{{color:#667085;font-size:13px}} .value{{font-size:28px;font-weight:700;margin-top:6px}}
section{{background:white;border-radius:10px;padding:18px;margin-top:18px;box-shadow:0 1px 4px #0001}} table{{border-collapse:collapse;width:100%}} th,td{{border-bottom:1px solid #eaecf0;text-align:left;padding:9px 8px;font-size:14px}} th{{background:#f9fafb}} .muted{{color:#667085;font-size:13px}}
</style></head><body><h1>求职追踪仪表盘</h1><p class="muted">生成日期：{today.isoformat()}；数据来自本地 tracker 和申请工作区。</p>
<div class="cards">{cards}</div>
<section><h2>漏斗阶段</h2><table><tr><th>阶段</th><th>当前数量</th></tr>{stage_rows}</table></section>
<section><h2>渠道效能</h2><table><tr><th>渠道</th><th>状态</th><th>数量</th></tr>{channel_rows}</table></section>
<section><h2>跟进到期清单</h2><table><tr><th>公司</th><th>岗位</th><th>应跟进日</th><th>状态</th></tr>{followup_rows}</table></section>
<section><h2>公司明细</h2><table><tr><th>公司</th><th>岗位</th><th>状态</th><th>阶段</th><th>匹配度</th><th>最近动作</th><th>归档文件数</th></tr>{detail_rows}</table></section>
<section><h2>申请归档文件</h2><ul>{archive_rows}</ul></section>
<footer class="muted">明细可能包含个人求职信息。本报告位于本地 reports/，不要提交或传播。</footer></body></html>
"""


def main() -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracker", type=Path, default=Path("job_search_tracker.csv"))
    parser.add_argument("--applications", type=Path, default=Path("documents/applications"))
    parser.add_argument("--out", type=Path, default=Path("reports/application-dashboard.html"))
    parser.add_argument("--today", type=parse_date, default=date.today())
    args = parser.parse_args()
    try:
        rows = load_tracker(args.tracker)
    except (OSError, ValueError) as exc:
        print(f"html_report: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    content = render(rows, application_files(args.applications), args.today or date.today())
    args.out.write_text(content, encoding="utf-8")
    print(f"wrote {args.out.resolve()} ({len(content.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
