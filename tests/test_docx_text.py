"""Tests for tools/docx_text.py - zero-dependency DOCX text extraction."""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from docx_text import extract_paragraphs, extract_text, parse_docx, stats, suspicious_sequences  # noqa: E402

MINIMAL_DOCX_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>姓名:{name}</w:t></w:r><w:r><w:tab/><w:t>电话:{phone}</w:t></w:r></w:p>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>教育经历</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>本科</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
    <w:p><w:r><w:t></w:t></w:r></w:p>
  </w:body>
</w:document>
"""


def make_docx(path: Path, body: str | None = None):
    if body is None:
        body = MINIMAL_DOCX_XML.replace("{name}", "示例").replace("{phone}", "13800000000")
    with zipfile.ZipFile(path, "w") as zf:
        empty = ""
        zf.writestr(
            "[Content_Types].xml",
            "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
        )
        zf.writestr("word/document.xml", body)
        zf.writestr("docProps/core.xml", empty)
    return path


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="docx_text_test_"))
        self.docx = make_docx(self.tmp / "sample.docx")

    def test_paragraph_and_table_reading_order(self):
        paragraphs = extract_paragraphs(self.docx)
        self.assertEqual(paragraphs[0], "姓名:示例\t电话:13800000000")
        self.assertIn("教育经历\t本科", paragraphs)
        self.assertEqual(len(paragraphs), 3)

    def test_stats_counts_cjk(self):
        s = stats(parse_docx(self.docx)["paragraphs"])
        self.assertGreater(s["cjk_chars"], 3)
        self.assertGreater(s["chars"], 10)

    def test_extract_text_joins(self):
        text = extract_text(self.docx)
        self.assertIn("姓名:示例", text)
        self.assertIn("教育经历", text)

    def test_empty_doc_becomes_error(self):
        empty = make_docx(self.tmp / "empty.docx",
                          body="<w:document xmlns:w='http://schemas.openxmlformats.org/"
                               "wordprocessingml/2006/main'><w:body></w:body></w:document>")
        data = parse_docx(empty)
        self.assertEqual(data["paragraphs"], [])

    def test_missing_body_part_raises(self):
        with zipfile.ZipFile(self.tmp / "broken.docx", "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
        with self.assertRaises(KeyError):
            parse_docx(self.tmp / "broken.docx")

    def test_suspicious_sequences_flags_replacement_char(self):
        found = suspicious_sequences("正常\uFFFD文字")
        self.assertTrue(any("替换字符" in f for f in found))


if __name__ == "__main__":
    unittest.main()
