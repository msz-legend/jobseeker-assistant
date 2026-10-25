#!/usr/bin/env python3
"""Verify a rendered Chinese resume (DOCX) before it is submitted.

The submit-time gate of this repo's DOCX resume pipeline. Three layers,
degrading gracefully:

  1. text layer (always):        docx opens, text non-empty, no [PLACEHOLDER]
                                 tokens, spec sections present, mojibake flags
  2. pdf layer (--pdf):          export DOCX -> PDF via Word COM (MS Word 或
                                 WPS 的 COM) on Windows, or soffice elsewhere;
                                 then pypdf page count + text sanity checks
  3. page-limit layer (--pages): hard page budget from the template manifest
                                 (templates/cv/<name>/TEMPLATE.md)

Usage:
  python tools/verify_resume.py cv/main_x.docx --spec cv/main_x.json --pages 1 --pdf
  python tools/verify_resume.py cv/main_x.docx --allow-placeholders        # 草稿阶段

Exit codes: 0 = PASS (warnings allowed), 1 = FAIL, 1 usage errors included.
JSON report with --out; human-readable Chinese lines always printed.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import zipfile
from xml.etree import ElementTree as ET

from docx_text import extract_paragraphs, parse_docx, stats, suspicious_sequences

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


def _force_utf8(stream) -> None:
    try:
        if not stream or not getattr(stream, "encoding", ""):
            return
        if stream.encoding.lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


PLACEHOLDER_RE = re.compile(r"\[[A-Z0-9_]{3,}\]|\[示例(?:公司|岗位)[^\]]*\]")
MOBILE_RE = re.compile(r"1[3-9]\d{9}")


def _check_file(path: str) -> tuple:
    p = Path(path)
    if not p.is_file():
        return None, {"id": "file_missing", "level": "fail", "msg": f"文件不存在: {p}"}
    if p.suffix.lower() != ".docx":
        return None, {"id": "not_docx", "level": "fail", "msg": f"不是 .docx: {p.name}"}
    return p, None


def _parse_text(path: Path) -> tuple:
    try:
        paragraphs = extract_paragraphs(path)
    except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        return None, {"id": "unreadable_docx", "level": "fail", "msg": f"DOCX 打不开: {exc}"}
    body = "\n".join(paragraphs)
    if stats(paragraphs)["chars"] < 100:
        return paragraphs, {"id": "empty_docx", "level": "fail",
                            "msg": "正文过短（<100 字符），等于没写"}
    return paragraphs, None


def _placeholders(text: str) -> list[str]:
    return sorted(set(PLACEHOLDER_RE.findall(text)))[:5]


def _convert_pdf(docx: Path, out_pdf: Path) -> str | None:
    """Try MS Word, then WPS (常见国产), then LibreOffice. Return engine or None."""
    docx_abs = str(docx.resolve())
    pdf_abs = str(out_pdf.resolve())
    if os.name == "nt":
        for progid in ("Word.Application", "KWPS.Application"):
            script = (
                "$ErrorActionPreference='Stop';"
                f"$app=New-Object -ComObject {progid};"
                "$app.Visible=$false;"
                f"$doc=$app.Documents.Open('{docx_abs}');"
                f"$doc.SaveAs2('{pdf_abs}',17);"
                "$doc.Close();"
                "$app.Quit();"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode == 0 and Path(pdf_abs).is_file():
                return "word-com" if progid.startswith("Word") else "wps-com"
        return None
    for engine in (
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(out_pdf.parent), docx_abs],
        ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(out_pdf.parent), docx_abs],
    ):
        if shutil.which(engine[0]) is None:
            continue
        result = subprocess.run(engine, capture_output=True, text=True, timeout=180)
        if result.returncode == 0 and Path(pdf_abs).is_file():
            return engine[0]
    return None


def _pdf_checks(pdf_path: Path, pages_limit: int | None, checks: list) -> int | None:
    if PdfReader is None:
        checks.append({"id": "pypdf_missing", "level": "warn",
                       "msg": "pypdf 未安装，无法校验 PDF（pip install pypdf）"})
        return None
    try:
        reader = PdfReader(str(pdf_path))
        pages = len(reader.pages)
    except Exception as exc:  # noqa: BLE001 - 任何解析错误都当作校验失败材料
        checks.append({"id": "pdf_unreadable", "level": "fail", "msg": f"PDF 打不开: {exc}"})
        return None
    if pages == 0:
        checks.append({"id": "pdf_empty", "level": "fail", "msg": "PDF 0 页"})
        return pages
    if pages_limit and pages > pages_limit:
        checks.append({"id": "over_page_limit", "level": "fail",
                       "msg": f"页数 {pages} 超过限制 {pages_limit}"})
    text = ""
    try:
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # noqa: BLE001
        pass
    if len(text.strip()) < 100:
        checks.append({"id": "pdf_text_little", "level": "warn",
                       "msg": "PDF 提取文本过少：图片型或字体未内嵌，平台解析可能拿不到文字"})
    return pages


def verify(path: str, spec_path: str | None, pages_limit: int | None,
           want_pdf: bool, allow_placeholders: bool, keywords: list[str]) -> dict:
    checks: list[dict] = []
    clean_path, early = _check_file(path)
    if early:
        return _assemble(path, None, checks, [early])

    paragraphs, text_fail = _parse_text(clean_path)
    if text_fail:
        return _assemble(path, None, checks, [text_fail])

    body = "\n".join(paragraphs)

    ph = _placeholders(body)
    if ph and not allow_placeholders:
        checks.append({"id": "has_placeholders", "level": "fail",
                       "msg": "残留占位符: " + "、".join(ph) + "（草稿校验加 --allow-placeholders）"})
    elif ph:
        checks.append({"id": "placeholders_note", "level": "warn",
                       "msg": f"含占位符（已放行）: {len(ph)} 处"})

    for marker in suspicious_sequences(body):
        checks.append({"id": "suspicious_chars", "level": "warn", "msg": f"疑似乱码: {marker}"})

    spec = None
    if spec_path:
        try:
            spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            checks.append({"id": "spec_unreadable", "level": "fail", "msg": f"spec 打不开: {exc}"})
            return _assemble(path, None, checks, [])

    pdf_pages = None
    if want_pdf:
        pdf_path = Path(tempfile.gettempdir()) / (clean_path.stem + "_verify.pdf")
        try:
            if pdf_path.exists():
                pdf_path.unlink()
        except OSError:
            pass
        engine = _convert_pdf(clean_path, pdf_path)
        if engine is None:
            checks.append({"id": "no_pdf_engine", "level": "warn",
                           "msg": "找不到 Word / WPS / LibreOffice，跳过 PDF 层校验（文本层已通过）"})
        else:
            pdf_pages = _pdf_checks(pdf_path, pages_limit, checks)
            try:
                pdf_path.unlink()
            except OSError:
                pass

    elif pages_limit:
        checks.append({"id": "pages_skipped", "level": "warn",
                       "msg": "给了 --pages 但没给 --pdf，页数校验跳过"})

    if keywords:
        text_compact = re.sub(r"\s+", "", body)
        missing = [kw for kw in keywords if kw.replace(" ", "") not in text_compact]
        covered_pct = round(100 * (len(keywords) - len(missing)) / len(keywords), 1)
        if missing:
            checks.append({"id": "keywords_missing", "level": "fail",
                           "msg": f"关键词覆盖 {covered_pct}%，缺: {'、'.join(missing[:8])}"})
        elif covered_pct < 70:
            checks.append({"id": "keywords_partial", "level": "warn",
                           "msg": f"关键词覆盖 {covered_pct}%，命中率偏低"})

    if spec:
        expectations = _spec_expectations(spec)
        compact = re.sub(r"\s+", "", body)
        missing_titles = [t for t in expectations["titles"] if t not in compact]
        for title in missing_titles:
            checks.append({"id": "missing_section", "level": "fail",
                           "msg": f"spec 里声明的板块缺失: {title}"})
        name = expectations["name"]
        if name and name not in body:
            checks.append({"id": "name_missing", "level": "fail",
                           "msg": f"正文里找不到姓名 {name}（identity.name 拼错或漏渲染）"})
        if name and MOBILE_RE.search(name):
            checks.append({"id": "bad_name", "level": "warn", "msg": "姓名里出现手机号，spec 写串字段了"})

    return _assemble(path, pdf_pages, checks, [])


def _spec_expectations(spec: dict) -> dict:
    titles = []
    for section in spec.get("sections") or []:
        title = str(section.get("title") or "").strip()
        if title:
            titles.append(title)
    if spec.get("objective", {}).get("role"):
        titles.append(str(spec["objective"].get("label") or "求职意向"))
    name = str((spec.get("identity") or {}).get("name") or "").strip()
    return {"titles": titles, "name": name}


def _assemble(path: str, pdf_pages: int | None, checks: list, early: list) -> dict:
    all_checks = early + checks
    fails = [c for c in all_checks if c["level"] == "fail"]
    warns = [c for c in all_checks if c["level"] == "warn"]
    return {
        "file": str(path),
        "pages": pdf_pages,
        "failures": fails,
        "warnings": warns,
        "verdict": "FAIL" if fails else "PASS",
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        _force_utf8(stream)
    ap = argparse.ArgumentParser(description="Verify a rendered Chinese resume (DOCX).")
    ap.add_argument("file")
    ap.add_argument("--spec", help="生成该 DOCUMENT 的 JSON spec（用于板块/姓名核对）")
    ap.add_argument("--pages", type=int, help="页数硬上限（来自模板 manifest）")
    ap.add_argument("--pdf", action="store_true", help="尝试导出 PDF 后做页数/文字校验")
    ap.add_argument("--keywords", help="逗号分隔的 JD 关键词，检查覆盖率")
    ap.add_argument("--allow-placeholders", action="store_true", help="草稿阶段放行 [YOUR_...] 占位")
    ap.add_argument("--out", help="写入 JSON 报告")
    args = ap.parse_args()

    keywords = [k.strip() for k in (args.keywords or "").split(",") if k.strip()]
    report = verify(
        args.file, args.spec, args.pages, args.pdf, args.allow_placeholders, keywords
    )

    for fail in report["failures"]:
        print(f"[FAIL] {fail['msg']}")
    for warn in report["warnings"]:
        print(f"[WARN] {warn['msg']}")

    if not report["failures"] and not report["warnings"]:
        print("[PASS] 全部校验通过")
    else:
        print(f"verdict: {report['verdict']} (fail={len(report['failures'])}, warn={len(report['warnings'])})")

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
