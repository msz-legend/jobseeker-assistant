#!/usr/bin/env python3
"""Extract text from a .docx file. Zero dependencies (zipfile + ElementTree).

docx is a zip of XML parts; the main body lives in word/document.xml. This
module walks the body in reading order: paragraphs become text lines, tables
become rows of cell texts joined with tabs. Good enough for verification
(section titles present, no placeholder tokens, keyword coverage) and for
letting the agent read a rendered resume without opening Word.

Usage:
  python tools/docx_text.py <file.docx>            # plain text to stdout
  python tools/docx_text.py <file.docx> --json     # {"lines": [...], "stats": {...}}
  python tools/docx_text.py <file.docx> --json --out report.json

As a library:
  from docx_text import extract_paragraphs, extract_text, parse_docx
"""

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

NS = {"w": MAIN_NS}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _para_text(p: ET.Element) -> str:
    parts = []
    for node in p.iter():
        if _local(node.tag) == "t" and node.text:
            parts.append(node.text)
        elif _local(node.tag) == "tab":
            parts.append("\t")
    return "".join(parts)


def _table_rows(tbl: ET.Element) -> list[str]:
    rows = []
    for tr in tbl.findall(f"{{{MAIN_NS}}}tr"):
        cells = []
        for tc in tr.findall(f"{{{MAIN_NS}}}tc"):
            cell = " ".join(_para_text(p) for p in tc.findall(f".//{{{MAIN_NS}}}p"))
            cells.append(cell.strip())
        rows.append("\t".join(cells))
    return rows


def parse_docx(path):
    """Return {paragraphs: [str], tables: [[str], ...]} in body reading order.

    Raises FileNotFoundError / zipfile.BadZipFile / KeyError on malformed files.
    """
    with zipfile.ZipFile(path) as zf:
        try:
            xml = zf.read("word/document.xml")
        except KeyError:
            raise KeyError("word/document.xml missing - not a Word body docx?")
    root = ET.fromstring(xml)
    body = root.find(f"{{{MAIN_NS}}}body")
    if body is None:
        raise KeyError("document body missing")

    paragraphs: list[str] = []
    tables: list[str] = []
    for child in body:
        kind = _local(child.tag)
        if kind == "p":
            paragraphs.append(_para_text(child))
        elif kind == "tbl":
            rows = _table_rows(child)
            tables.append(rows)
            for row in rows:
                paragraphs.append(row)

    return {"paragraphs": paragraphs, "tables": tables}


def extract_paragraphs(path) -> list[str]:
    return parse_docx(path)["paragraphs"]


def extract_text(path) -> str:
    return "\n".join(extract_paragraphs(path))


WHITESPACE = re.compile(r"\s+")


def stats(paragraphs: list[str]) -> dict:
    text = "\n".join(paragraphs)
    compact = WHITESPACE.sub("", text)
    cjk = sum(1 for ch in compact if "\u4e00" <= ch <= "\u9fff")
    return {
        "lines": sum(1 for p in paragraphs if p.strip()),
        "chars": len(compact),
        "cjk_chars": cjk,
    }


def suspicious_sequences(text: str) -> list[str]:
    """Common mojibake markers worth surfacing, not a gate by themselves."""
    markers = [
        ("\u00c3", "拉丁扩展乱码 (Ã)"),
        ("\u2014\u20ac", "UTF-8 被按 Latin-1 解码的痕迹 (â€)"),
        ("\ufffd", "替换字符 (�)"),
    ]
    found = []
    for needle, label in markers:
        if needle in text:
            found.append(label)
    # 连续制表/全角空格堆积：复制粘贴 JD 常见，不算错，但值得提示
    wide = WHITESPACE.sub("", text)
    for ch in set(wide):
        if unicodedata.category(ch) == "Zs" and ch not in " \u3000":
            found.append(f"罕见空白字符 U+{ord(ch):04X}")
    return found[:5]


def main() -> int:
    try:
        if sys.stdout and getattr(sys.stdout, "encoding", "").lower().replace("-", "") != "utf8":
            sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(description="Extract text from a .docx (zero dependency).")
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true", help="emit a JSON object instead of text")
    ap.add_argument("--out", help="write output (text or JSON) to this file")
    args = ap.parse_args()

    try:
        data = parse_docx(args.file)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        if args.json:
            payload = {"file": args.file, "error": str(exc)}
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
            print(text)
        else:
            print(f"docx_text: cannot read {args.file}: {exc}", file=sys.stderr)
        return 1

    paragraphs = data["paragraphs"]
    if args.json:
        payload = {
            "file": str(args.file),
            "stats": stats(paragraphs),
            "suspicious": suspicious_sequences("\n".join(paragraphs)),
            "lines": paragraphs,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)
        return 0

    text = "\n".join(paragraphs)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
