"""Tests for tools/salary_band.py - Chinese salary string parsing + floor verdict."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from salary_band import parse_band, parse_floor, verdict  # noqa: E402


class ParsingTests(unittest.TestCase):
    def assertBand(self, raw, **expected):
        band = parse_band(raw)
        for key, value in expected.items():
            self.assertEqual(band[key], value, msg=f"{raw!r} -> {key} ({band['reasons']})")
        return band

    def test_monthly_k_with_multiplier(self):
        band = self.assertBand("20-35K·15", period="monthly", months=15,
                               min_monthly=20000, max_monthly=35000,
                               max_annual=525000, ambiguous=False)
        self.assertFalse(band["ambiguous"])

    def test_monthly_wan_small_with_multiplier(self):
        self.assertBand("2.5-4万×14", period="monthly", months=14,
                        min_monthly=25000, max_monthly=40000, ambiguous=False)

    def test_bare_k_monthly(self):
        self.assertBand("15-25K", period="monthly", min_monthly=15000, max_monthly=25000)

    def test_wan_annual_when_ge_10(self):
        self.assertBand("20-35万", period="annual", min_annual=200000, max_annual=350000)

    def test_w_and_annual(self):
        self.assertBand("63w/年", period="annual", max_annual=630000, max_monthly=52500)

    def test_explicit_monthly_yuan(self):
        self.assertBand("薪资：8000-12000元/月，14薪", period="monthly", months=14,
                        min_monthly=8000, max_monthly=12000)

    def test_comma_thousands_monthly(self):
        self.assertBand("40,000/月", period="monthly", max_monthly=40000)

    def test_colloquial_w_small_monthly(self):
        self.assertBand("2-3w", period="monthly", min_monthly=20000, max_monthly=30000)

    def test_total_package_keyword_annual(self):
        self.assertBand("总包 30-50w", period="annual", max_annual=500000)

    def test_prefers_salary_span_over_unrelated_numbers(self):
        # 电话号码/日期不应抢走薪资段
        band = self.assertBand(
            "工作年限 3-5 年，薪资 20-35K·15，base 北京",
            period="monthly", max_monthly=35000,
        )
        self.assertEqual(band["months"], 15)

    def test_unparseable(self):
        band = parse_band("__ none __")
        self.assertFalse(band["parsed"])

    def test_suspicious_huge_monthly_flagged(self):
        band = self.assertBand("200-300K", period="monthly", ambiguous=True)


class FloorVerdictTests(unittest.TestCase):
    def test_floor_monthly_pass(self):
        band = parse_band("20-35K·15")
        floor = parse_floor("30K/月")
        out = verdict(band, floor)
        self.assertEqual(out["verdict"], "pass")
        self.assertGreater(out.get("headroom_pct", 0), 0)

    def test_floor_monthly_fail(self):
        band = parse_band("2.5-4万×14")
        floor = parse_floor("50000/月")
        out = verdict(band, floor)
        self.assertEqual(out["verdict"], "fail")
        self.assertGreater(out["gap_pct"], 0)

    def test_floor_gap_pct(self):
        band = parse_band("10-20K")
        floor = parse_floor("42000/月")
        out = verdict(band, floor)
        self.assertEqual(out["verdict"], "fail")
        self.assertGreater(out["gap_pct"], 50)

    def test_floor_annual_compare(self):
        band = parse_band("63w/年")
        out = verdict(band, {"min_monthly": 50000})
        self.assertEqual(out["verdict"], "pass")

    def test_floor_k_input(self):
        floor = parse_floor("42K")
        self.assertEqual(floor["min_monthly"], 42000)

    def test_floor_wan_input(self):
        floor = parse_floor("4.2万")
        self.assertEqual(floor["min_monthly"], 42000)

    def test_no_number_band_needs_review(self):
        band = parse_band("面议")
        self.assertEqual(band["ambiguous"], True)
        out = verdict(band, parse_floor("42K"))
        self.assertEqual(out["verdict"], "needs_review")


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        import subprocess
        tool = Path(__file__).resolve().parent.parent / "tools" / "salary_band.py"
        return subprocess.run(
            [sys.executable, str(tool), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )

    def test_cli_json_verdict(self):
        result = self.run_cli("20-35K·15", "--floor", "30K/月")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["verdict"], "pass")

    def test_cli_unparseable_exit_2(self):
        result = self.run_cli("面议面议面议")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
