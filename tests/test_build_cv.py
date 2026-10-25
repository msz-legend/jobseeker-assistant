"""Tests for tools/build_cv.py - DOCX rendering from a JSON content spec."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

# python-docx is optional; tests skip when absent rather than fail
try:
    from docx import Document  # noqa: F401

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

from build_cv import DEFAULT_STYLE, build  # noqa: E402
from docx_text import extract_paragraphs  # noqa: E402


SPEC = {
    "identity": {"name": "张三示例", "contact": "138-0000-0000 | z@example.com | 北京"},
    "objective": {"role": "Go 后端工程师", "city": "北京", "availability": "一个月内"},
    "sections": [
        {"title": "专业技能", "type": "bullets",
         "items": ["Go：三段生产项目，基础扎实", "MySQL：索引与分库分表经验"]},
        {"title": "工作经历", "type": "experience",
         "items": [{"header": "示例科技 · Go 后端工程师", "meta": "2020.07 – 至今 | 北京",
                    "bullets": ["主导网关重构，QPS 3k 升 15k，P99 延迟降 60%"]}]},
        {"title": "教育经历", "type": "simple",
         "items": ["示例大学 · 计算机科学与技术 · 本科 | 2016-2020"]},
    ],
}


def render(spec=SPEC, style=None):
    return build(json.loads(json.dumps(spec)), style or dict(DEFAULT_STYLE))


@unittest.skipUnless(HAS_DOCX, "python-docx not installed")
class RenderTests(unittest.TestCase):
    def test_built_doc_contains_expected_text(self):
        doc, build_stats = render()
        tmp = Path(tempfile.mkdtemp(prefix="build_cv_test_"))
        out = tmp / "main_test.docx"
        doc.save(str(out))
        paragraphs = extract_paragraphs(out)
        text = "\n".join(paragraphs)
        for needle in (
            "张三示例", "求职意向", "Go 后端工程师", "专业技能",
            "工作经历", "示例科技 · Go 后端工程师", "QPS 3k 升 15k", "教育经历",
        ):
            self.assertIn(needle, text, msg=f"missing {needle!r} in {paragraphs}")
        self.assertGreaterEqual(build_stats["paragraphs"], 8)

    def test_bold_lead_split(self):
        doc, _ = render()
        # 「Go：三段生产项目…」的主语 Go： 应被加粗
        bold_texts = []
        for p in doc.paragraphs:
            for run in p.runs:
                if run.bold and run.text:
                    bold_texts.append(run.text)
        self.assertTrue(any("Go：" in t for t in bold_texts), bold_texts)

    def test_zero_sections_rejected(self):
        with self.assertRaises(SystemExit):
            build({"identity": {"name": "x", "contact": "y"}, "sections": []}, dict(DEFAULT_STYLE))

    def test_empty_identity_rejected(self):
        with self.assertRaises(SystemExit):
            build({"identity": {}, "sections": []}, dict(DEFAULT_STYLE))


if __name__ == "__main__":
    unittest.main()
