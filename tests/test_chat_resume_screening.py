#!/usr/bin/env python3
"""Offline tests for the four screening filters added 2026-11-23.

Covers: explicit resume request / outsourcing / non-Beijing / algorithm role.
Uses the 14 real device samples captured from BOSS and Liepin.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from chat_resume_ladder import (  # noqa: E402
    detect_resume_request, infer_stack, is_explicit_request, load_config,
    pick_resume, screen_candidate,
)
from chat_resume_dispatch import build_entries_from_vision  # noqa: E402

CFG = load_config(names={
    "JAVA_RESUME": "JAVA-RESUME",
    "GO_RESUME": "GO-RESUME",
})
SAMPLES = json.loads(
    (ROOT / "documents" / "dispatch" / "sample_2026-11-23.json").read_text(encoding="utf-8")
)


class ExplicitRequestTests(unittest.TestCase):
    def test_explicit_asks(self):
        for msg in (
            "[附件简历] 我想要一份您的附件简历",
            "[简历] 我想要一份你的简历，你是否同意？",
            "请发一份简历给我",
            "简历发我一份",
        ):
            with self.subTest(msg=msg):
                self.assertTrue(is_explicit_request(msg, CFG))

    def test_sent_attachment_is_not_an_outstanding_request(self):
        text = "我想要一份您的附件简历，您是否同意\n您的附件简历 候选人-开... 已发送给Boss点击查看附件"
        self.assertFalse(is_explicit_request(text, CFG))

    def test_od_project_is_excluded_even_with_direct_request(self):
        item = {"org": "某科技公司甲", "role": "Golang", "city": "北京",
                "snippet": "字节OD项目在招，方便发一份简历看看吗？"}
        self.assertIn("outsourcing", [r["filter"] for r in screen_candidate(item, CFG)["reasons"]])

    def test_od_form_is_excluded_even_with_direct_request(self):
        item = {"org": "易宝软件", "role": "Golang", "city": "",
                "snippet": "非常符合我们字节项目，采用OD形式，方便发一份简历吗？"}
        self.assertIn("outsourcing", [r["filter"] for r in screen_candidate(item, CFG)["reasons"]])

    def test_stacks_without_java_go_or_python_are_not_filtered_out(self):
        # User rule 2026-11-26: language is no longer an eligibility gate.
        # It only selects the resume; no Java/Go/Python still passes.
        for role in ("架构师", "全栈工程师", "C/C++", "其他技术职位", ""):
            with self.subTest(role=role):
                item = {"org": "某科技公司", "role": role, "city": "北京",
                        "snippet": "方便发一份你的简历过来吗？"}
                result = screen_candidate(item, CFG)
                self.assertEqual(result["verdict"], "pass")
                self.assertNotIn("stack_required",
                                 [r["filter"] for r in result["reasons"]])
                self.assertEqual(result["reasons"], [])

    def test_java_go_or_python_stack_is_still_resolved(self):
        for role, stack in (("Java", "java"), ("Golang", "go"), ("Python", "python")):
            with self.subTest(role=role):
                item = {"org": "某科技公司", "role": role, "city": "北京",
                        "snippet": "方便发一份你的简历过来吗？"}
                result = screen_candidate(item, CFG)
                self.assertEqual(result["verdict"], "pass")
                self.assertEqual(infer_stack(role, CFG), stack)

    def test_non_explicit(self):
        for msg in (
            "[新招呼] 您好，我这边是猎头",
            "[简历] 您期望薪资多少呀",
            "[简历] 为了方便联系，你能把手机号发我吗？",
            "[未读] 这是我的简历，合适的话可以随时联系",
            "很希望与你进一步沟通，你是否愿意先了解一下",
        ):
            with self.subTest(msg=msg):
                self.assertFalse(is_explicit_request(msg, CFG))


class PythonStackRegressionTests(unittest.TestCase):
    """User rule 2026-11-25: Python is accepted and gets the GO resume."""

    def _tuyou_item(self) -> dict:
        return {
            "contact": "候选人辛",
            "platform": "boss",
            "org": "某游戏公司 | Python",
            "city": "",
            "role": "Python",
            "snippet": (
                "候选人辛\n某游戏公司 · 招聘者\n换电话\n换微信\n发简历\n不感兴趣\n"
                "查看详细分析\n已读\n您好，我在招聘平台看到您发布的岗位信息，"
                "仔细对照了岗位要求后发现自己过往的项目经历和技能储备都和需求高度契合，"
                "我对这个岗位的工作内容非常感兴趣，能否麻烦您先看一下我的简历做个初步的评估。\n"
                "18:43\n方便发一份简历过来吗？\n"
                "我想要一份您的附件简历，您是否同意\n拒绝\n同意\n回复消息"
            ),
        }

    def test_tuyou_game_card_request_passes_and_selects_go_resume(self):
        screened = screen_candidate(self._tuyou_item(), CFG)
        self.assertEqual(screened["verdict"], "pass")
        self.assertEqual(screened["reasons"], [])
        self.assertEqual(screened["request_source"], "card+text")

        passing, skipped = build_entries_from_vision([self._tuyou_item()], CFG)
        self.assertEqual(len(passing), 1)
        self.assertEqual(len(skipped), 0)
        self.assertEqual(passing[0]["stack"], "python")
        self.assertEqual(passing[0]["resume"], "GO-RESUME")
        self.assertFalse(passing[0]["approved"])

    def test_python_only_maps_to_go_resume(self):
        self.assertEqual(infer_stack("Python FastAPI", CFG), "python")
        self.assertEqual(pick_resume("Python FastAPI", CFG), "GO-RESUME")

    def test_java_wins_over_python_in_ladder(self):
        text = "Java 与 Python 都要"
        self.assertEqual(infer_stack(text, CFG), "java")
        self.assertEqual(pick_resume(text, CFG), "JAVA-RESUME")

    def test_go_wins_over_python_in_ladder(self):
        text = "Golang 和 Python 都要"
        self.assertEqual(infer_stack(text, CFG), "go")
        self.assertEqual(pick_resume(text, CFG), "GO-RESUME")


class FourFilterTests(unittest.TestCase):
    def test_meng_passes_request_but_blocked_by_algorithm(self):
        meng = next(s for s in SAMPLES if s["contact"] == "孟女士")
        result = screen_candidate(meng, CFG)
        filters = [r["filter"] for r in result["reasons"]]
        self.assertEqual(result["verdict"], "skip")
        self.assertIn("algorithm_role", filters)
        self.assertNotIn("explicit_request", filters)  # request WAS recognised

    def test_shi_blocked_by_outsourcing_not_by_request(self):
        shi = next(s for s in SAMPLES if s["contact"] == "石先生")
        filters = [r["filter"] for r in screen_candidate(shi, CFG)["reasons"]]
        self.assertIn("outsourcing", filters)
        self.assertNotIn("explicit_request", filters)

    def test_location_blocks_shanghai_and_shaanxi(self):
        for contact in ("韦先生", "向女士", "杨女士"):
            item = next(s for s in SAMPLES if s["contact"] == contact)
            filters = [r["filter"] for r in screen_candidate(item, CFG)["reasons"]]
            with self.subTest(contact=contact):
                self.assertIn("location", filters)

    def test_all_14_samples_yield_zero_pass(self):
        passing, skipped = build_entries_from_vision(SAMPLES, CFG)
        self.assertEqual(len(SAMPLES), 14)
        self.assertEqual(len(passing), 0)
        self.assertEqual(len(skipped), 14)

    def test_a_clean_local_request_passes_with_go_resume(self):
        item = {
            "platform": "boss", "contact": "张某", "org": "某公司",
            "city": "北京", "role": "Go后端",
            "snippet": "[附件简历] 我想要一份您的附件简历",
        }
        passing, skipped = build_entries_from_vision([item], CFG)
        self.assertEqual(len(passing), 1)
        self.assertEqual(len(skipped), 0)
        self.assertEqual(passing[0]["resume"], "GO-RESUME")
        self.assertFalse(passing[0]["approved"])  # human gate intact


class LocationAndOutsourcingRegressionTests(unittest.TestCase):
    """Regressions found in the 362-item full-list scan (2026-11-23).

    Non-Beijing city names often live in `org`, not `city`; the blocklist must
    cover city-level names (not only provinces). FESCO/德科 is an HR outsourcer.
    """

    def _filters(self, item):
        return [r["filter"] for r in screen_candidate(item, CFG)["reasons"]]

    def test_city_level_name_in_city_field_blocks(self):
        # 刘女士 · city="青岛" — only "山东" was in the list before.
        item = {
            "contact": "刘女士", "org": "合伙人·青岛基业百年...", "city": "青岛",
            "role": "", "snippet": "[简历]我想要一份你的简历，你是否同意?",
        }
        self.assertIn("location", self._filters(item))

    def test_city_in_org_field_blocks_when_city_empty(self):
        # 王女士/杨女士 — 深圳/杭州 in org, city field left empty.
        for org in ("HR·深圳市新凯来...", "招聘·莱恩(杭州)企..."):
            with self.subTest(org=org):
                item = {
                    "contact": "X", "org": org, "city": "", "role": "",
                    "snippet": "[简历]我想要一份你的简历，你是否同意?",
                }
                self.assertIn("location", self._filters(item))

    def test_fesco_outsourcer_blocks(self):
        item = {
            "contact": "候选人辛", "org": "某外包公司数字", "city": "", "role": "Java",
            "snippet": "[新招呼] 方便发一份您的简历...",
        }
        self.assertIn("outsourcing", self._filters(item))

    def test_beijing_in_org_still_passes_location(self):
        item = {
            "contact": "候选人戊", "org": "招聘方·北京懂车族...", "city": "", "role": "",
            "snippet": "[简历]我想要一份你的简历，你是否同意?",
        }
        self.assertNotIn("location", self._filters(item))

    def test_unknown_location_not_blocked(self):
        item = {
            "contact": "卫先生", "org": "项目经理·泰康之家", "city": "", "role": "",
            "snippet": "[简历]我想要一份你的简历，你是否同意?",
        }
        self.assertNotIn("location", self._filters(item))


class RequestSignalTests(unittest.TestCase):
    """Card OR text: either signal alone is enough to send a resume."""

    CARD = (
        "候选人戊\n某汽车公司 · HR\n"
        "我想要一份您的附件简历，您是否同意\n拒绝\n同意\n"
    )

    def _signals(self, snippet: str) -> dict:
        item = {
            "contact": "候选人戊", "org": "某汽车公司 | Java", "city": "北京",
            "role": "Java", "snippet": snippet,
        }
        screened = screen_candidate(item, CFG)
        return {
            "verdict": screened["verdict"],
            "filters": [r["filter"] for r in screened["reasons"]],
            "card": screened["request_card"],
            "text": screened["request_text"],
            "source": screened["request_source"],
        }

    def test_card_only_is_enough(self):
        # Card sentence with the answer buttons, and no text-shaped ask.
        signals = self._signals(
            "候选人戊\n某汽车公司 · HR\n您好，可以给您匹配最合适的岗位~\n"
            "我想要一份您的附件简历，您是否同意\n拒绝\n同意\n"
        )
        self.assertEqual(signals["source"], "card")
        self.assertTrue(signals["card"])
        self.assertFalse(signals["text"])
        self.assertNotIn("explicit_request", signals["filters"])
        self.assertEqual(signals["verdict"], "pass")

    def test_text_only_is_enough(self):
        signals = self._signals("方便发一份简历过来吗？")
        self.assertEqual(signals["source"], "text")
        self.assertFalse(signals["card"])
        self.assertTrue(signals["text"])
        self.assertNotIn("explicit_request", signals["filters"])

    def test_both_signals_are_traced(self):
        signals = self._signals(self.CARD + "方便发一份简历过来吗？\n")
        self.assertEqual(signals["source"], "card+text")
        self.assertTrue(signals["card"])
        self.assertTrue(signals["text"])

    def test_neither_signal_skips_without_sending(self):
        signals = self._signals("您好，可以给您匹配最合适的岗位~")
        self.assertIsNone(signals["source"])
        self.assertFalse(signals["card"])
        self.assertFalse(signals["text"])
        self.assertIn("explicit_request", signals["filters"])
        self.assertEqual(signals["verdict"], "skip")

    def test_card_sentence_without_buttons_is_not_a_card(self):
        # A plain text bubble quoting the sentence has no 同意/拒绝 buttons.
        signals = self._signals("我想要一份您的附件简历，您是否同意")
        self.assertFalse(signals["card"])

    def test_already_answered_card_is_not_an_outstanding_request(self):
        signals = self._signals(
            "候选人庚\n某科技公司乙 · Java\n对方已同意，您的附件简历已发送给对方\n"
            "点击预览附件简历\n"
        )
        self.assertIsNone(signals["source"])
        self.assertIn("explicit_request", signals["filters"])


    def test_pending_request_header_is_not_an_outstanding_request(self):
        # After a resume row is tapped, BOSS leaves the header as 请求中 while
        # the old card may still be visible. Re-running must not send again.
        signals = self._signals(
            "候选人辛\n某游戏公司 · 招聘者\n请求中\n"
            "我想要一份您的附件简历，您是否同意\n拒绝\n同意\n"
            "方便发一份简历过来吗？\n"
        )
        self.assertIsNone(signals["source"])
        self.assertFalse(signals["card"])
        self.assertFalse(signals["text"])
        self.assertIn("explicit_request", signals["filters"])


class TextPatternTests(unittest.TestCase):
    """Recruiter phrasings beyond the original narrow 发/要/想要 rules."""

    CARD = (
        "候选人戊\n某汽车公司 · HR\n"
        "我想要一份您的附件简历，您是否同意\n拒绝\n同意\n"
    )
    PHRASES = (
        "方便提供一份您的详细简历吗？",
        "方便同步一份最新简历吗",
        "辛苦发下简历",
        "请把您的简历发一下，谢谢~",
        "方便简历发一个么",
        "可以给我一份简历",
        "Hi，若匹配，期待获得您的简历～",
        "方便获取一份您的简历吗？",
        "投递一份简历过来",
    )
    NOISE = (
        "发简历", "附件简历", "点击预览附件简历", "点击查看附件简历",
        "换电话", "换微信", "不感兴趣", "查看详细分析",
    )

    def _signals(self, text):
        item = {"contact": "甲", "org": "甲公司 | Java", "city": "北京",
                "role": "Java", "snippet": text}
        return screen_candidate(item, CFG)

    def test_real_recruiter_phrases_are_text_hits(self):
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                screened = self._signals(phrase)
                self.assertEqual(screened["request_source"], "text", phrase)
                self.assertNotIn("explicit_request",
                                 [r["filter"] for r in screened["reasons"]])

    def test_ui_button_labels_are_not_text_hits(self):
        for label in self.NOISE:
            with self.subTest(label=label):
                signals = detect_resume_request(label, CFG)
                self.assertFalse(signals["hit"], label)
                self.assertIsNone(signals["source"], label)

    def test_candidate_self_recommendation_is_not_a_request(self):
        text = "方便的话先看一下我的简历"
        signals = detect_resume_request(text, CFG)
        self.assertFalse(signals["hit"])
        self.assertIsNone(signals["source"])

    def test_negative_only_vetoes_its_own_line(self):
        text = "我看过您的简历了，暂时不匹配\n方便提供一份您的详细简历吗？"
        signals = detect_resume_request(text, CFG)
        self.assertTrue(signals["hit"])
        self.assertEqual(signals["source"], "text")

    def test_terminal_sent_state_vetoes_every_line(self):
        text = "方便提供一份您的详细简历吗？\n对方已同意，您的附件简历已发送给对方"
        signals = detect_resume_request(text, CFG)
        self.assertFalse(signals["hit"])
        self.assertIsNone(signals["source"])

    def test_card_and_real_text_still_reported_as_both(self):
        text = self.CARD + "方便提供一份您的详细简历吗？\n"
        signals = detect_resume_request(text, CFG)
        self.assertEqual(signals["source"], "card+text")

    def test_card_sentence_alone_is_not_a_text_hit(self):
        # The card sentence belongs to the card channel; without buttons it is
        # not a card either. It must not silently become a text request.
        signals = detect_resume_request(
            "我想要一份您的附件简历，您是否同意", CFG)
        self.assertFalse(signals["card"])
        self.assertFalse(signals["text"])
        self.assertFalse(signals["hit"])


if __name__ == "__main__":
    unittest.main()
