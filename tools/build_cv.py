#!/usr/bin/env python3
"""Render a Chinese resume (个人简历) DOCX from a JSON content spec.

The rendering target is DOCX-first: 网申表单 / BOSS / 猎聘 / email pipelines
accept DOCX or PDF-from-DOCX, and heavy typesetting toolchains are mostly
absent on Chinese job seekers' machines, so this tool renders DOCX directly with
python-docx:

    python tools/build_cv.py cv/main_<公司>_<岗位>.json -o cv/main_<公司>_<岗位>.docx

Spec schema (see templates/cv/base/spec.example.json for a fillable example):

{
  "meta":   {"output": "cv/main_x_y.docx"},               # output path fallback
  "identity": {"name": "", "contact": "①|②|③", "lines": ["GitHub: ..."]},
  "objective": {"role": "", "city": "", "availability": ""},   # 求职意向 (optional)
  "sections": [
    {"title": "专业技能", "type": "bullets",     "items": ["Go：一句话", ...]},
    {"title": "工作经历", "type": "experience",  "items": [{"header": "公司 · 职位",
                                                            "meta": "2020.07– 至今 | 北京",
                                                            "bullets": ["带量化数字的条目"]}]},
    {"title": "项目经历", "type": "projects",    "items": [同 experience]},
    {"title": "教育经历", "type": "simple",      "items": ["学校 · 专业 · 学历 | 年份"]}
  ]
}

Style is driven by a style JSON (see templates/cv/base/style.json):
name/head font 微软雅黑, body font 宋体, A4, compact spacing - the defaults ship
with --style templates/cv/base/style.json and are overridable per template.

Requires: python-docx (pip install python-docx). Exit codes: 0 built, 1 usage/env error.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
except ImportError:  # pragma: no cover - env guard
    Document = None


def _force_utf8_stdout() -> None:
    try:
        if not sys.stdout.encoding or sys.stdout.encoding.lower().replace("-", "") != "utf8":
            sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


DEFAULT_STYLE = {
    "name_font": "微软雅黑",
    "head_font": "微软雅黑",
    "body_font": "宋体",
    "name_size": 18.0,
    "head_size": 12.0,
    "subhead_size": 11.0,
    "body_size": 10.5,
    "small_size": 9.0,
    "margins_cm": [1.6, 1.5, 1.6, 1.5],  # top, bottom, left, right
    "page_cm": [21.0, 29.7],  # A4
    "head_space_before_pt": 8.0,
    "head_space_after_pt": 2.0,
    "bullet_space_after_pt": 1.5,
    "item_space_after_pt": 4.0,
    "accent_color": "404040",  # meta/日期用色；正文纯黑
}

SECTION_TYPES = {"bullets", "experience", "projects", "simple"}

LEAD_SPLIT_MAX = 16  # bullets "主：xxx" 粗体主语最大长度，超过视为普通句子


def _die(msg: str) -> "None":
    print(f"build_cv: {msg}", file=sys.stderr)
    sys.exit(1)


def _set_run(run, style: dict, font_key: str, size_key: str, bold=False, color=None, italic=False):
    name = style[font_key]
    run.font.name = name
    run.font.size = Pt(style[size_key])
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    # 中文字形必须显式设置 eastAsia，否则 Word 回落到默认 Calibri
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:eastAsia"), name)


def _para(doc, after: float, before: float = 0.0, align=None, line=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(after)
    pf.space_before = Pt(before)
    if align is not None:
        p.alignment = align
    if line is not None:
        pf.line_spacing = line
    return p


def _bottom_border(p, color: str):
    ppr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), color)
    pbdr.append(bottom)
    ppr.append(pbdr)


def _content_width_cm(style: dict) -> float:
    page_w, _, left, right, _top, _bottom = (
        style["page_cm"][0], style["page_cm"][1], style["margins_cm"][2],
        style["margins_cm"][3], style["margins_cm"][0], style["margins_cm"][1],
    )
    return page_w - left - right


def _identity(doc, spec: dict, style: dict) -> None:
    identity = spec.get("identity") or {}
    name = (identity.get("name") or "").strip()
    contact = (identity.get("contact") or "").strip()
    lines = identity.get("lines") or []
    if not name and not contact and not lines:
        _die("identity.name / contact 全空，简历无法开头")

    p = _para(doc, after=2.0, align=WD_ALIGN_PARAGRAPH.CENTER)
    run = p.add_run(name or "[YOUR_NAME]")
    _set_run(run, style, "name_font", "name_size", bold=True)

    if contact:
        cp = _para(doc, after=6.0, align=WD_ALIGN_PARAGRAPH.CENTER, line=1.05)
        crun = cp.add_run(contact)
        _set_run(crun, style, "body_font", "small_size", color="595959")

    for line in lines:
        lp = _para(doc, after=2.0, align=WD_ALIGN_PARAGRAPH.CENTER, line=1.05)
        lrun = lp.add_run(str(line))
        _set_run(lrun, style, "body_font", "small_size", color="595959")


def _objective(doc, spec: dict, style: dict) -> None:
    obj = spec.get("objective") or {}
    role = (obj.get("role") or "").strip()
    if not role:
        return
    city = (obj.get("city") or "").strip()
    avail = (obj.get("availability") or "").strip()
    parts = [x for x in (role, city, avail) if x]
    label = (obj.get("label") or "求职意向").strip()
    p = _para(doc, after=6.0, before=6.0, align=WD_ALIGN_PARAGRAPH.CENTER, line=1.05)
    lab = p.add_run(f"{label}：")
    _set_run(lab, style, "body_font", "body_size", bold=True)
    body = p.add_run(" ｜ ".join(parts))
    _set_run(body, style, "body_font", "body_size")


def _bullets(doc, parent, items, style: dict, indent: float) -> list[int]:
    counts = []
    for raw in items:
        item = str(raw).strip()
        lead, rest = item, ""
        if "：" in item and not item.startswith("："):
            candidate = item.split("：", 1)
            if len(candidate[0]) <= LEAD_SPLIT_MAX:
                lead, rest = candidate[0], candidate[1]
        p = _para(parent, after=style["bullet_space_after_pt"], align=WD_ALIGN_PARAGRAPH.LEFT, line=1.15)
        pf = p.paragraph_format
        pf.left_indent = Cm(indent)
        bullet_run = p.add_run("• ")
        _set_run(bullet_run, style, "body_font", "body_size", color=style["accent_color"])
        if rest:
            lead_run = p.add_run(f"{lead}：")
            _set_run(lead_run, style, "body_font", "body_size", bold=True)
            text_run = p.add_run(rest)
            _set_run(text_run, style, "body_font", "body_size")
        else:
            text_run = p.add_run(lead)
            _set_run(text_run, style, "body_font", "body_size")
        counts.append(1)
    return counts


def _item_cards(doc, items, style: dict) -> None:
    """experience / projects 卡片：header + 右对齐 meta（tab stop）+ bullets。"""
    content_w = Cm(_content_width_cm(style) - 0.3)
    for item in items:
        header = str(item.get("header") or "").strip()
        meta = str(item.get("meta") or "").strip()
        if not header and not meta:
            continue
        p = _para(doc, after=1.0, before=style["item_space_after_pt"], line=1.1)
        pf = p.paragraph_format
        pf.tab_stops.add_tab_stop(content_w, WD_TAB_ALIGNMENT.RIGHT)
        if header:
            hrun = p.add_run(header)
            _set_run(hrun, style, "head_font", "subhead_size", bold=True)
        if meta:
            tab = p.add_run("\t" if header else "")
            _set_run(tab, style, "body_font", "small_size")
            mrun = p.add_run(meta)
            _set_run(mrun, style, "body_font", "small_size", color=style["accent_color"])
        _bullets(doc, doc, item.get("bullets") or [], style, indent=0.45)


def _section(doc, section: dict, style: dict) -> int:
    title = str(section.get("title") or "").strip()
    kind = str(section.get("type") or "bullets").strip()
    items = section.get("items") or []
    if not title or kind not in SECTION_TYPES or not items:
        return 0

    if doc.paragraphs:  # 分节间距
        doc.paragraphs[-1].paragraph_format.space_after = Pt(4.0)
    hp = _para(doc, after=style["head_space_after_pt"], before=style["head_space_before_pt"], line=1.0)
    hrun = hp.add_run(title)
    _set_run(hrun, style, "head_font", "head_size", bold=True)
    _bottom_border(hp, style["accent_color"])

    if kind in ("bullets",):
        _bullets(doc, doc, items, style, indent=0.45)
    elif kind in ("experience", "projects"):
        _item_cards(doc, items, style)
    else:  # simple
        for raw in items:
            line = str(raw).strip()
            if not line:
                continue
            lp = _para(doc, after=1.5, line=1.15)
            pf = lp.paragraph_format
            pf.left_indent = Cm(0.45)
            bullet_run = lp.add_run("• ")
            _set_run(bullet_run, style, "body_font", "body_size", color=style["accent_color"])
            lrun = lp.add_run(line)
            _set_run(lrun, style, "body_font", "body_size")
    return len(items)


def build(spec: dict, style: dict) -> ("Document", dict):
    if Document is None:
        _die("需要 python-docx：pip install python-docx")

    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(style["page_cm"][0])
    section.page_height = Cm(style["page_cm"][1])
    section.top_margin = Cm(style["margins_cm"][0])
    section.bottom_margin = Cm(style["margins_cm"][1])
    section.left_margin = Cm(style["margins_cm"][2])
    section.right_margin = Cm(style["margins_cm"][3])

    normal = doc.styles["Normal"]
    normal.font.name = style["body_font"]
    normal.font.size = Pt(style["body_size"])
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), style["body_font"])
    rfonts.set(qn("w:hAnsi"), style["body_font"])
    rfonts.set(qn("w:eastAsia"), style["body_font"])

    _identity(doc, spec, style)
    _objective(doc, spec, style)

    rendered = 0
    for entry in spec.get("sections") or []:
        rendered += _section(doc, entry, style)

    if rendered == 0:
        _die("spec.sections 为空或全部类型无效（需要 bullets/experience/projects/simple）")
    stats = {"items": rendered, "paragraphs": len(doc.paragraphs)}
    return doc, stats


def load_json(path: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        _die(f"无法读取 {path}: {exc}")
    except json.JSONDecodeError as exc:
        _die(f"{path} 不是有效 JSON: {exc}")
    return None


def main() -> int:
    _force_utf8_stdout()
    ap = argparse.ArgumentParser(description="Render a JSON resume spec to a Chinese-format DOCX.")
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", help="输出 .docx 路径（缺省用 spec.meta.output）")
    ap.add_argument("--style", default=None, help="style.json 路径；缺省用内置 DEFAULT_STYLE")
    args = ap.parse_args()

    spec = load_json(args.spec)
    style = dict(DEFAULT_STYLE)
    if args.style:
        override = load_json(args.style)
        if not isinstance(override, dict):
            _die(f"{args.style} 不是 JSON 对象")
        unknown = set(override) - set(DEFAULT_STYLE)
        if unknown:
            print(f"style 未知字段（忽略）: {', '.join(sorted(unknown))}", file=sys.stderr)
        style.update({k: v for k, v in override.items() if k in DEFAULT_STYLE})

    out = args.out or (spec.get("meta") or {}).get("output")
    if isinstance(out, dict):
        out = out.get("output")
    if not out or not str(out).strip():
        _die("缺输出路径：用 -o 或 spec.meta.output")
    out_path = Path(out)
    if out_path.suffix.lower() != ".docx":
        _die(f"输出必须是 .docx（得到 {out_path.name}）")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc, stats = build(spec, style)
    try:
        doc.save(str(out_path))
    except OSError as exc:
        _die(f"写不进 {out_path}: {exc}（文件被 Word/WPS 打开着？）")

    print(f"built {out_path} ({stats['items']} content items, {stats['paragraphs']} paragraphs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
