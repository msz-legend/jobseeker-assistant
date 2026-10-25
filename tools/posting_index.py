#!/usr/bin/env python3
"""Build documents/postings/_index.md from the frontmatter of every posting file.

Why this exists
---------------
`documents/postings/` used to be a scratch inbox: paste a .txt, evaluate it,
delete it. That works when one posting is in flight. It fails the moment six
are: the JD text ends up scattered across chat logs, screenshots, and the
tracker's notes column, and every later step (/apply, /interview, /outcome)
has to ask the user for facts the workspace already had.

So a posting is now a single durable file with structured frontmatter, and
this script is the only thing that reads them all. The index is generated,
never hand-edited: a stale hand-written table is worse than no table.

Design notes
------------
* stdlib only, no PyYAML. The frontmatter we write is a flat map of scalars;
  anything richer belongs in the body, not the header.
* Missing frontmatter is not an error. A plain .txt or a bare .md still gets
  indexed, with warnings, because refusing to index it would recreate the
  original problem (posting exists, nobody can find it).
* Output is deterministic: sort order is (status rank, fit desc, company).

Usage:
  python3 tools/posting_index.py
  python3 tools/posting_index.py --root documents/postings --stdout
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

STATUS_ORDER = {
    "interview": 0,
    "applied": 1,
    "evaluated": 2,
    "inbox": 3,
    "offer": 4,
    "rejected": 5,
    "archived": 6,
}

STATUS_LABEL = {
    "interview": "🟡 面试中",
    "applied": "🔵 已投递",
    "evaluated": "⚪ 已评估",
    "inbox": "📥 待评估",
    "offer": "🟢 Offer",
    "rejected": "🔴 结束",
    "archived": "⚫ 归档",
}

SKIP = {"_index.md", "_TEMPLATE.md", "README.md", ".gitkeep"}

FM_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.DOTALL)


def parse_front_matter(text):
    """Return (meta, body, has_front_matter). Flat key: value only."""
    m = FM_RE.match(text)
    if not m:
        return {}, text, False
    meta = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        meta[key.strip().lower()] = value
    return meta, text[m.end():], True


def read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def as_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def collect(root):
    entries = []
    if not os.path.isdir(root):
        return entries
    for name in sorted(os.listdir(root)):
        if name in SKIP or name.startswith("."):
            continue
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        text = read_text(path)
        meta, body, has_fm = parse_front_matter(text)
        stem = os.path.splitext(name)[0]
        company = meta.get("company") or ""
        role = meta.get("role") or ""
        status = (meta.get("status") or "inbox").strip().lower()
        if status not in STATUS_ORDER:
            status = "inbox"
        entry = {
            "file": name,
            "company": company,
            "role": role,
            "city": meta.get("city", ""),
            "salary": meta.get("salary_raw", ""),
            "fit": as_int(meta.get("fit")),
            "status": status,
            "updated": meta.get("updated") or meta.get("captured_at") or "",
            "source": meta.get("source", ""),
            "has_fm": has_fm,
            "body_len": len(body.strip()),
            "warnings": [],
        }
        if not has_fm:
            entry["warnings"].append("无 frontmatter")
        if not company or not role:
            entry["warnings"].append("缺 company/role（文件名：%s）" % stem)
        if entry["body_len"] < 80:
            entry["warnings"].append("JD 正文过短或为空")
        if not entry["updated"]:
            entry["warnings"].append("缺 captured_at")
        completeness = (meta.get("jd_completeness") or "").strip().lower()
        if completeness and completeness != "full":
            entry["warnings"].append("JD 非原文（%s），需补全" % completeness)
        entries.append(entry)
    entries.sort(
        key=lambda e: (
            STATUS_ORDER[e["status"]],
            -(e["fit"] if e["fit"] is not None else -1),
            e["company"],
        )
    )
    return entries


def render(entries):
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 岗位 JD 索引",
        "",
        "> **本文件由 `tools/posting_index.py` 生成，不要手改。**",
        "> 新增或修改岗位 = 改 `documents/postings/<公司>_<岗位>.md` 的 frontmatter，然后重跑脚本。",
        "> 生成时间：%s ｜ 共 %d 条" % (now, len(entries)),
        "",
    ]
    if not entries:
        lines.append("_目录为空。从 `_TEMPLATE.md` 复制一份开始。_")
        return "\n".join(lines) + "\n"

    lines += [
        "| 状态 | 公司 | 岗位 | 城市 | 薪资 | 匹配 | 更新 | 文件 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in entries:
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | `%s` |"
            % (
                STATUS_LABEL.get(e["status"], e["status"]),
                e["company"] or "—",
                e["role"] or "—",
                e["city"] or "—",
                e["salary"] or "—",
                e["fit"] if e["fit"] is not None else "—",
                e["updated"] or "—",
                e["file"],
            )
        )

    warn = [e for e in entries if e["warnings"]]
    if warn:
        lines += ["", "## 需要处理", ""]
        for e in warn:
            lines.append("- `%s`：%s" % (e["file"], "；".join(e["warnings"])))

    counts = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    summary = " ｜ ".join(
        "%s %d" % (STATUS_LABEL.get(s, s), counts[s])
        for s in sorted(counts, key=lambda s: STATUS_ORDER[s])
    )
    lines += ["", "---", "", "**分布**：%s" % summary, ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Build the posting index.")
    ap.add_argument("--root", default=os.path.join("documents", "postings"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    entries = collect(args.root)
    text = render(entries)

    if args.stdout:
        sys.stdout.write(text)
        return 0

    out = args.out or os.path.join(args.root, "_index.md")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    sys.stdout.write("indexed %d postings -> %s\n" % (len(entries), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
