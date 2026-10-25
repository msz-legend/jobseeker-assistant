import csv
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "html_report.py"
FIELDS = [
    "date", "company", "sector", "role", "role_type", "channel", "status", "stage",
    "contact_person", "fit_rating", "notes", "cv_file", "greeting_file", "source", "deadline",
]


class HtmlReportTests(unittest.TestCase):
    def test_generates_self_contained_dashboard_from_tracker_and_applications(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracker = root / "tracker.csv"
            applications = root / "applications"
            applications.joinpath("腾讯_高级Agent").mkdir(parents=True)
            applications.joinpath("腾讯_高级Agent", "prep_一面.md").write_text("private content", encoding="utf-8")
            applications.joinpath("腾讯_高级Agent", "greeting.md").write_text("private greeting", encoding="utf-8")
            fields = [
                "date", "company", "sector", "role", "role_type", "channel", "status", "stage",
                "contact_person", "fit_rating", "notes", "cv_file", "greeting_file", "source", "deadline",
            ]
            with tracker.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "date": "2026-10-20", "company": "腾讯", "sector": "AI", "role": "高级 Agent",
                    "role_type": "研发", "channel": "BOSS直聘", "status": "interview", "stage": "一面",
                    "contact_person": "黄先生", "fit_rating": "79", "notes": "2026-10-20 已投递 | 2026-10-21 prep_一面 已生成",
                    "deadline": "2026-10-24",
                })
                writer.writerow({
                    "date": "2026-10-23", "company": "示例公司", "role": "示例岗位", "status": "drafted",
                })
                writer.writerow({
                    "date": "2026-10-22", "company": "Acme <script>", "role": "后端", "channel": "官网",
                    "status": "offer", "stage": "OC", "fit_rating": "88", "notes": "待确认",
                })
            output = root / "dashboard.html"
            proc = subprocess.run(
                [sys.executable, str(TOOL), "--tracker", str(tracker), "--applications", str(applications),
                 "--out", str(output), "--today", "2026-10-24"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            html = output.read_text(encoding="utf-8")
            self.assertIn("求职追踪仪表盘", html)
            self.assertIn("总申请数", html)
            self.assertIn("腾讯", html)
            self.assertIn("1", html)
            self.assertIn("跟进到期", html)
            self.assertIn("prep_一面.md", html)
            self.assertNotIn("private content", html)
            self.assertNotIn("<script>", html)
            self.assertIn("Acme &lt;script&gt;", html)
            self.assertIn("text/html; charset=utf-8", html)

    def test_handles_missing_inputs_and_rejects_invalid_tracker(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "empty.html"
            proc = subprocess.run(
                [sys.executable, str(TOOL), "--tracker", str(root / "missing.csv"),
                 "--applications", str(root / "missing-apps"), "--out", str(output), "--today", "2026-10-24"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("总申请数", output.read_text(encoding="utf-8"))

            invalid = root / "invalid.csv"
            invalid.write_text("not,csv\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(TOOL), "--tracker", str(invalid), "--out", str(root / "bad.html")],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("15 列", proc.stderr)

    def test_funnel_counts_background_check_stage(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracker = root / "tracker.csv"
            with tracker.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow({
                    "date": "2026-10-22", "company": "字节跳动", "role": "后端开发", "channel": "官网",
                    "status": "interview", "stage": "背调",
                })
                writer.writerow({
                    "date": "2026-10-23", "company": "示例公司", "role": "示例岗位", "status": "drafted",
                })
            output = root / "dashboard.html"
            proc = subprocess.run(
                [sys.executable, str(TOOL), "--tracker", str(tracker),
                 "--applications", str(root / "missing-apps"), "--out", str(output), "--today", "2026-10-24"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            html = output.read_text(encoding="utf-8")
            self.assertIn("<td>背调</td><td>1</td>", html)

    def test_funnel_aggregates_unknown_stage_into_other_row(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracker = root / "tracker.csv"
            with tracker.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow({
                    "date": "2026-10-22", "company": "历史公司", "role": "后端开发", "channel": "官网",
                    "status": "offer", "stage": "offer确认",
                })
            output = root / "dashboard.html"
            proc = subprocess.run(
                [sys.executable, str(TOOL), "--tracker", str(tracker),
                 "--applications", str(root / "missing-apps"), "--out", str(output), "--today", "2026-10-24"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            html = output.read_text(encoding="utf-8")
            self.assertIn("<tr><td>其他：offer确认</td><td>1</td></tr>", html)

    def test_funnel_renders_all_canonical_stages_with_zero_counts_for_placeholder_only_tracker(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracker = root / "tracker.csv"
            with tracker.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow({
                    "date": "2026-10-23", "company": "[示例公司]", "role": "示例岗位", "status": "drafted",
                })
            output = root / "dashboard.html"
            proc = subprocess.run(
                [sys.executable, str(TOOL), "--tracker", str(tracker),
                 "--applications", str(root / "missing-apps"), "--out", str(output), "--today", "2026-10-24"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            html = output.read_text(encoding="utf-8")
            for stage in ("笔试", "电话沟通", "一面", "二面", "三面", "HR面", "OC", "背调"):
                self.assertIn(f"<tr><td>{stage}</td><td>0</td></tr>", html)
            self.assertNotIn("其他：", html)
