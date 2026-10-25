import tempfile
import unittest
from pathlib import Path

from tools import mistake_index


class MistakeIndexTests(unittest.TestCase):
    def test_recurrence_and_quick_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "a" / "mistakes" / "mistake-gap.md"
            second = root / "b" / "mistakes" / "mistake-gap.md"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            body = """## Mistake: gap
- `domain`: generic
- `competency`: planning
- `failure_type`: reasoning_gap
- `status`: open
- `spoken_answer`: bounded answer
- `diagram`: ```mermaid\nflowchart LR\nA-->B\n```
"""
            first.write_text(body, encoding="utf-8")
            second.write_text(body, encoding="utf-8")
            output = root / "index.md"
            mistake_index.build(root, output)
            text = output.read_text(encoding="utf-8")
            self.assertIn("| gap | generic | planning | reasoning_gap | open | 2 |", text)
            self.assertIn("full_entry", text)


if __name__ == "__main__":
    unittest.main()
