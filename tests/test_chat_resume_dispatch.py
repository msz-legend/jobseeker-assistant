#!/usr/bin/env python3
"""Offline unit tests for the chat-resume dispatch decision logic.

No device, no network. Run from repo root:
    python -m unittest tests.test_chat_resume_dispatch -v
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from chat_resume_dispatch import (  # noqa: E402
    BOSS_MSG_TAB,
    BOSS_PKG,
    DEFAULT_FOLLOWUP_FILE,
    DeviceError,
    RiskSignal,
    scan_all_boss_chats,
    _inline_send_key,
    _verify_targets,
    apply_verify_result,
    cmd_send,
    cmd_run,
    cmd_followup,
    _at_thirty_day_bottom,
    _navigate_to_boss_all_tab,
    _restart_boss_for_scan,
    resolve_scan_max_screens,
    extract_chat_entries,
    fetch_adb_keyboard_apk,
    find_nodes,
    load_followup_text,
    make_inline_sender,
    human_pause,
    norm,
    open_boss_chat,
    parse_dump,
    build_parser,
    send_followup,
    send_one,
    sentinel_check,
    verify_one,
    write_queue,
    approved_items,
    cmd_rescreen,
    cmd_send,
    render_review_markdown,
    rescreen_evidence,
    send_one,
    parse_list_time,
    load_list_times,
    filter_recent_entries,
    render_recent_markdown,
)
from chat_resume_ladder import (  # noqa: E402
    infer_stack, is_resume_request, load_config, load_names, pick_resume,
)

JAVA = "JAVA-RESUME-NAME"
GO = "GO-RESUME-NAME"
_NAMES = {"JAVA_RESUME": JAVA, "GO_RESUME": GO}
CFG = load_config(names=_NAMES)


class SendSafetyTests(unittest.TestCase):
    def test_only_recent_items_are_eligible(self):
        good = {"approved": True, "verified": True, "detail_found": True,
                "verdict": "pass", "recent_window": True}
        self.assertEqual(approved_items([good]), [good])
        old = {k: v for k, v in good.items() if k != "recent_window"}
        self.assertEqual(approved_items([old]), [])

    def test_only_reviewed_verified_and_passing_items_are_eligible(self):
        good = {"approved": True, "verified": True, "detail_found": True, "verdict": "pass",
                "recent_window": True}
        queue = [good, {**good, "skipped": True}, {**good, "verified": False},
                 {**good, "detail_found": False}, {**good, "verdict": "skip"},
                 {**good, "sent": True}, {**good, "approved": False}]
        self.assertEqual(approved_items(queue), [good])

    def test_unverified_picker_selection_never_taps_submit(self):
        def doc(*nodes):
            return '<hierarchy>' + ''.join(nodes) + '</hierarchy>'
        def node(text, bounds, selected='false'):
            return f'<node text="{text}" clickable="true" selected="{selected}" bounds="{bounds}" />'
        class FakeAdb:
            def __init__(self):
                self.dumps = iter([
                    doc(node('候选人乙', '[0,0][100,100]'), node('发简历', '[100,0][200,100]')),
                    doc(node('GO-RESUME-NAME', '[0,100][100,200]')),
                    doc(node('GO-RESUME-NAME', '[0,100][100,200]'), node('立即投递', '[0,200][100,300]')),
                ])
                self.taps = []
            def dump(self): return next(self.dumps, '<hierarchy />')
            def tap(self, x, y): self.taps.append((x, y))
        adb = FakeAdb()
        with mock.patch('chat_resume_dispatch.time.sleep'):
            with self.assertRaises(DeviceError):
                send_one(adb, {'contact': '候选人乙', 'resume': GO}, Path('.'), 0.1)
        self.assertNotIn((50, 250), adb.taps)


class SendNavigationTests(unittest.TestCase):
    def _args(self, queue: Path, ledger: Path, followup_file: Path):
        return argparse.Namespace(
            yes_i_reviewed=True, serial="TEST", dry_run=True,
            queue=str(queue), ledger=str(ledger), evidence=".",
            timeout=0.1, auto_open=True, max_screens=7,
            followup_file=str(followup_file),
        )

    @staticmethod
    def _followup_file(td: Path) -> Path:
        path = Path(td) / "followup_message.txt"
        path.write_text(FOLLOWUP_TEXT, encoding="utf-8")
        return path

    def test_auto_open_locates_contact_before_sending(self):
        with tempfile.TemporaryDirectory() as td:
            queue_path = Path(td) / "queue.json"
            item = {"key": "k1", "contact": "甲", "org": "甲公司 | Java", "platform": "boss",
                    "approved": True, "verified": True, "detail_found": True,
                    "verdict": "pass", "recent_window": True, "sent": False, "resume": GO}
            queue_path.write_text(json.dumps([item], ensure_ascii=False), encoding="utf-8")
            args = self._args(queue_path, Path(td) / "ledger.jsonl",
                              self._followup_file(Path(td)))
            with mock.patch("chat_resume_dispatch.Adb"), \
                 mock.patch("chat_resume_dispatch.open_boss_chat",
                            return_value={"found": True, "screen": 1, "texts": ["甲"]}) as open_chat, \
                 mock.patch("chat_resume_dispatch.send_one",
                            return_value={"key": "k1", "send_confirmed": True}) as send, \
                 mock.patch("chat_resume_dispatch.append_ledger"):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_send(args, CFG), 0)
            open_chat.assert_called_once()
            self.assertEqual(open_chat.call_args.kwargs["org"], "甲公司 | Java")
            self.assertEqual(open_chat.call_args.kwargs["max_screens"], 7)
            send.assert_called_once()
            self.assertTrue(json.loads(queue_path.read_text(encoding="utf-8"))[0]["sent"])

    def test_auto_open_stop_when_contact_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            queue_path = Path(td) / "queue.json"
            item = {"key": "k1", "contact": "甲", "platform": "boss",
                    "approved": True, "verified": True, "detail_found": True,
                    "verdict": "pass", "recent_window": True, "sent": False, "resume": GO}
            queue_path.write_text(json.dumps([item], ensure_ascii=False), encoding="utf-8")
            args = self._args(queue_path, Path(td) / "ledger.jsonl",
                              self._followup_file(Path(td)))
            with mock.patch("chat_resume_dispatch.Adb"), \
                 mock.patch("chat_resume_dispatch.open_boss_chat",
                            return_value={"found": False, "screen": 7, "texts": []}), \
                 mock.patch("chat_resume_dispatch.send_one") as send:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_send(args, CFG), 1)
            send.assert_not_called()
            self.assertFalse(json.loads(queue_path.read_text(encoding="utf-8"))[0]["sent"])

    def test_followup_risk_after_resume_is_recorded_then_stops_batch(self):
        # The resume is already irreversible. A risk signal while typing the
        # follow-up must still mark this item sent (so a retry cannot resend),
        # append the ledger, save evidence, and stop the batch.
        with tempfile.TemporaryDirectory() as td:
            queue_path = Path(td) / "queue.json"
            item = {"key": "k1", "contact": "甲", "platform": "boss",
                    "approved": True, "verified": True, "detail_found": True,
                    "verdict": "pass", "recent_window": True, "sent": False, "resume": GO}
            queue_path.write_text(json.dumps([item], ensure_ascii=False), encoding="utf-8")
            args = self._args(queue_path, Path(td) / "ledger.jsonl",
                              self._followup_file(Path(td)))
            result = {"key": "k1", "send_confirmed": True,
                      "followup_sent": False,
                      "risk_signal": "RiskSignal: 请完成验证",
                      "followup_error": "RiskSignal: 请完成验证"}
            with mock.patch("chat_resume_dispatch.Adb"), \
                 mock.patch("chat_resume_dispatch.open_boss_chat",
                            return_value={"found": True, "screen": 1, "texts": ["甲"]}), \
                 mock.patch("chat_resume_dispatch.send_one", return_value=result), \
                 mock.patch("chat_resume_dispatch.append_ledger") as ledger, \
                 mock.patch("chat_resume_dispatch.save_evidence",
                            return_value={"png": "a.png", "dump": "a.xml"}) as evidence:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_send(args, CFG), 2)
            ledger.assert_called_once()
            evidence.assert_called_once()
            self.assertTrue(json.loads(queue_path.read_text(encoding="utf-8"))[0]["sent"])


class RescreenEvidenceTests(unittest.TestCase):
    def test_review_markdown_deduplicates_and_keeps_approval_unset(self):
        entries = [
            {"contact": "甲", "org": "甲公司", "role": "Java", "resume": JAVA,
             "list_snippet": "我想要一份简历", "detail_excerpt": "Java", "source_line": 1},
            {"contact": "甲", "org": "甲公司", "role": "Java", "resume": JAVA,
             "list_snippet": "我想要一份简历", "detail_excerpt": "Java", "source_line": 9},
            {"contact": "乙", "org": "乙公司", "role": "Golang", "resume": GO,
             "list_snippet": "发一份简历", "detail_excerpt": "Go", "source_line": 2},
        ]
        report = render_review_markdown(entries)
        self.assertIn("去重审查组：2", report)
        self.assertIn("证据行号：1, 9", report)
        self.assertIn("这不是发送授权", report)

    def test_reapplies_current_rules_and_ignores_failed_navigation(self):
        records = [
            {"contact": "甲", "org": "甲公司", "role": "Java",
             "list_snippet": "我想要一份您的附件简历", "detail_excerpt": "岗位要求 Java",
             "verdict": "pass"},
            {"contact": "甲", "org": "甲公司", "role": "Java",
             "list_snippet": "我想要一份您的附件简历", "detail_excerpt": "岗位要求 Java",
             "verdict": "pass"},
            {"contact": "乙", "org": "乙公司", "role": "Golang",
             "list_snippet": "我想要一份您的附件简历",
             "detail_excerpt": "您的附件简历 候选人-开... 已发送给Boss", "verdict": "pass"},
            {"contact": "丙", "org": "某科技公司甲", "role": "Golang",
             "list_snippet": "字节OD项目，方便发份简历吗？", "detail_excerpt": "",
             "verdict": "pass"},
            {"contact": "丁", "verdict": "navigation_failed"},
        ]
        passing, skipped, counts = rescreen_evidence(records, CFG)
        self.assertEqual([item["contact"] for item in passing], ["甲"])
        self.assertEqual(passing[0]["resume"], JAVA)
        self.assertFalse(passing[0]["approved"])
        self.assertTrue(passing[0]["verified"])
        self.assertTrue(passing[0]["detail_found"])
        self.assertEqual(counts, {"navigation_failed": 1, "duplicates": 1})
        by_contact = {item["contact"]: item for item in skipped}
        self.assertIn("explicit_request", [r["filter"] for r in by_contact["乙"]["reasons"]])
        self.assertIn("outsourcing", [r["filter"] for r in by_contact["丙"]["reasons"]])

    def test_rescreen_carries_request_source(self):
        records = [
            {"contact": "甲", "org": "甲公司", "role": "Java",
             "list_snippet": "您好，可以给您匹配岗位~",
             "detail_excerpt": ("我想要一份您的附件简历，您是否同意\n拒绝\n同意\n"
                                "岗位要求 Java"),
             "verdict": "pass"},
            {"contact": "乙", "org": "乙公司", "role": "Golang",
             "list_snippet": "方便发一份你的简历过来吗？",
             "detail_excerpt": "Golang 后端", "verdict": "pass"},
        ]
        passing, _, _ = rescreen_evidence(records, CFG)
        by_contact = {item["contact"]: item for item in passing}
        self.assertEqual(by_contact["甲"]["request_source"], "card")
        self.assertTrue(by_contact["甲"]["request_card"])
        self.assertEqual(by_contact["乙"]["request_source"], "text")
        self.assertFalse(by_contact["乙"]["request_card"])

    def test_rescreen_command_writes_fresh_unapproved_queue(self):
        records = [
            {"contact": "甲", "org": "甲公司", "role": "Golang",
             "list_snippet": "方便发一份你的简历过来吗？", "detail_excerpt": "Golang 后端",
             "verdict": "pass", "approved": True},
        ]
        with tempfile.TemporaryDirectory() as td:
            evidence = Path(td) / "evidence.jsonl"
            out = Path(td) / "queue.json"
            evidence.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records),
                                encoding="utf-8")
            args = argparse.Namespace(evidence=str(evidence), out=str(out),
                                      report=None, overwrite=False)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_rescreen(args, CFG), 0)
            queue = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(queue), 1)
            self.assertFalse(queue[0]["approved"])
            self.assertFalse(queue[0]["sent"])
            self.assertEqual(queue[0]["verdict"], "pass")

    def test_rescreen_keeps_conversations_without_java_or_go(self):
        # User rule 2026-11-26: language is no longer an eligibility gate.
        records = [
            {"contact": "甲", "org": "甲公司", "role": "架构师",
             "list_snippet": "方便发一份你的简历过来吗？", "detail_excerpt": "岗位是架构师",
             "verdict": "pass"},
            {"contact": "乙", "org": "乙公司", "role": "Java",
             "list_snippet": "方便发一份你的简历过来吗？", "detail_excerpt": "岗位要求 Java",
             "verdict": "pass"},
        ]
        passing, skipped, _ = rescreen_evidence(records, CFG)
        self.assertEqual([item["contact"] for item in passing], ["甲", "乙"])
        self.assertEqual(skipped, [])
        self.assertIsNone(passing[0]["stack"])
        self.assertEqual(passing[0]["resume"], GO)


class LadderTests(unittest.TestCase):
    def test_placeholders_are_resolved_from_personal_mapping(self):
        self.assertEqual(pick_resume("Java spring", CFG), JAVA)
        self.assertEqual(pick_resume("Golang", CFG), GO)
        self.assertEqual(pick_resume("Python FastAPI", CFG), GO)  # python maps to GO

    def test_unresolved_placeholder_fails_loudly(self):
        with self.assertRaises(ValueError):
            load_config(names={})

    def test_java_stack(self):
        self.assertEqual(infer_stack("要求Java / Spring Boot经验", CFG), "java")
        self.assertEqual(pick_resume("熟悉Java和Spring", CFG), JAVA)

    def test_go_stack(self):
        self.assertEqual(infer_stack("Golang后端, 熟悉go微服务", CFG), "go")
        self.assertEqual(pick_resume("岗位要求Golang", CFG), GO)

    def test_no_stack_returns_null_stack_but_keeps_fallback_name(self):
        # pick_resume keeps its GO fallback name so old code paths stay safe,
        # but the stack itself is None and screening filters it out (user rule
        # 2026-11-25: Java, Go or Python must be stated).
        self.assertIsNone(infer_stack("扎实的Rust工程能力", CFG))
        self.assertEqual(pick_resume("扎实的Rust工程能力", CFG), GO)
        self.assertEqual(pick_resume("", CFG), GO)

    def test_python_stack(self):
        self.assertEqual(infer_stack("Python FastAPI", CFG), "python")
        self.assertEqual(pick_resume("岗位要求Python", CFG), GO)

    def test_java_wins_when_both_stated(self):
        # First matching rule wins (ordered ladder).
        self.assertEqual(pick_resume("Java 和 Go 都要", CFG), JAVA)
        self.assertEqual(pick_resume("Java 和 Python 都要", CFG), JAVA)

    def test_go_wins_over_python(self):
        self.assertEqual(pick_resume("Golang 和 Python 都要", CFG), GO)

    def test_case_insensitive(self):
        self.assertEqual(pick_resume("JAVA spring", CFG), JAVA)
        self.assertEqual(pick_resume("GOLANG", CFG), GO)


class RequestDetectionTests(unittest.TestCase):
    def test_positive(self):
        for msg in (
            "方便发一份简历吗？",
            "请把简历发我看看",
            "简历发我一份",
        ):
            with self.subTest(msg=msg):
                self.assertTrue(is_resume_request(msg, CFG))

    def test_negative_wins(self):
        for msg in (
            "我已经发过简历了",
            "收到你的简历了",
            "我看过简历了，稍后回复",
            "方便的话先看一下我的简历",  # candidate's own self-recommendation, not a request
        ):
            with self.subTest(msg=msg):
                self.assertFalse(is_resume_request(msg, CFG))

    def test_irrelevant(self):
        self.assertFalse(is_resume_request("你好，在吗", CFG))
        self.assertFalse(is_resume_request("", CFG))


class UiParsingTests(unittest.TestCase):
    SAMPLE = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
    <hierarchy rotation="0">
      <node index="0" text="" content-desc="候选人辛" clickable="true" checked="false" selected="false" bounds="[432,69][648,147]"/>
      <node index="1" text="" content-desc="11:31&#10;已读&#10;方便发份简历吗" clickable="true" checked="false" selected="false" bounds="[0,666][1080,1467]"/>
      <node index="2" text="" content-desc="{java_resume}&#10;2026-11-02 22:11:40上传" clickable="true" checked="true" selected="false" bounds="[48,1254][1032,1530]"/>
      <node index="3" text="" content-desc="{go_resume}&#10;2026-11-02 22:11:34上传" clickable="true" checked="false" selected="false" bounds="[48,1530][1032,1806]"/>
      <node index="4" text="" content-desc="立即投递" clickable="true" checked="false" selected="false" bounds="[84,1878][996,2022]"/>
    </hierarchy>""".format(java_resume=JAVA, go_resume=GO)

    def test_parse_and_find(self):
        nodes = parse_dump(self.SAMPLE)
        self.assertEqual(len(nodes), 5)
        self.assertEqual(find_nodes(nodes, exact="立即投递", clickable=True)[0].center, (540, 1950))
        self.assertEqual(norm("您\u200b好"), "您好")

    def test_extract_entries(self):
        nodes = parse_dump(self.SAMPLE)
        entries, skipped = extract_chat_entries(nodes, CFG)
        # Language is no longer a gate. This legacy content-desc row is
        # request-shaped, so it now passes and selects the fallback resume.
        self.assertEqual(len(entries), 1)
        self.assertEqual(skipped, [])
        self.assertEqual(entries[0]["contact"], "方便发份简历吗")
        self.assertIsNone(entries[0]["stack"])
        self.assertEqual(entries[0]["resume"], GO)


class AdbListScreeningTests(unittest.TestCase):
    """The ADB dump path must screen grouped BOSS rows like --from-vision."""

    @staticmethod
    def _node(rid: str, text: str, y: int) -> str:
        return (
            f"<node index='0' text='{text}' content-desc='' resource-id='{rid}' "
            f"class='android.widget.TextView' clickable='false' "
            f"checked='false' selected='false' bounds='[0,{y}][1000,{y + 40}]'/>"
        )

    @classmethod
    def _row(cls, y: int, name: str, position: str, msg: str) -> str:
        base = "com.hpbr.bosszhipin:id/"
        return "".join([
            cls._node(base + "tv_name", name, y),
            cls._node(base + "tv_position", position, y + 6),
            cls._node(base + "tv_msg", msg, y + 79),
            cls._node(base + "tv_time_v2", "11月2日", y + 83),
        ])

    def test_boss_dump_rows_are_grouped_and_four_filtered(self):
        xml = (
            "<hierarchy>"
            + self._row(300, "候选人乙", "某科技公司甲 | Golang", "方便发一份你的简历过来吗？")
            + self._row(528, "候选人壬", "某外包公司（字节项目） | Java", "简历可以发我一份")
            + self._row(756, "王女士", "青岛某某科技 | Java", "我想要一份你的简历")
            + self._row(984, "刘先生", "某某科技 | 算法工程师", "方便发一份你的简历吗？")
            + self._row(1212, "赵女士", "某某科技 | Java", "看过你的简历了，稍后回复")
            + "</hierarchy>"
        )
        passing, skipped = extract_chat_entries(parse_dump(xml), CFG)

        self.assertEqual([e["contact"] for e in passing], ["候选人乙"])
        self.assertEqual(passing[0]["org"], "某科技公司甲 | Golang")
        self.assertEqual(passing[0]["role"], "Golang")
        self.assertEqual(passing[0]["resume"], GO)
        self.assertTrue(passing[0]["platform"] == "boss")
        self.assertFalse(passing[0]["approved"])
        self.assertFalse(passing[0]["sent"])

        reasons = {r["filter"] for item in skipped for r in item["reasons"]}
        self.assertEqual(
            reasons,
            {"explicit_request", "outsourcing", "location", "algorithm_role"},
        )

    def test_boss_row_without_java_go_or_python_is_not_filtered(self):
        # User rule 2026-11-26: language only selects the resume, never gates.
        xml = (
            "<hierarchy>"
            + self._row(300, "甲", "某科技公司 | Rust", "方便发一份你的简历过来吗？")
            + self._row(528, "乙", "另一家公司 | Java", "方便发一份你的简历过来吗？")
            + "</hierarchy>"
        )
        passing, skipped = extract_chat_entries(parse_dump(xml), CFG)
        self.assertEqual([e["contact"] for e in passing], ["甲", "乙"])
        self.assertEqual(skipped, [])
        self.assertIsNone(passing[0]["stack"])
        self.assertEqual(passing[0]["resume"], GO)

    def test_verified_stack_is_backfilled_on_the_list_entry(self):
        # The list path used to hardcode stack=None even for a Golang row.
        xml = (
            "<hierarchy>"
            + self._row(300, "候选人乙", "某科技公司甲 | Golang", "方便发一份你的简历过来吗？")
            + "</hierarchy>"
        )
        passing, _ = extract_chat_entries(parse_dump(xml), CFG)
        self.assertEqual(passing[0]["stack"], "go")


class QueueTests(unittest.TestCase):
    def test_preserves_human_approval_on_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            path.write_text(
                '[{"key":"abc","contact":"A","snippet":"s","approved":true,"sent":false}]',
                encoding="utf-8",
            )
            new = [{
                "key": "abc", "contact": "A", "snippet": "s",
                "approved": False, "sent": False,
            }, {
                "key": "def", "contact": "B", "snippet": "t",
                "approved": False, "sent": False,
            }]
            added = write_queue(path, new)
            self.assertEqual([e["key"] for e in added], ["def"])
            data = __import__("json").loads(path.read_text(encoding="utf-8"))
            self.assertTrue(data[0]["approved"])


class SentinelTests(unittest.TestCase):
    def test_captcha_stops(self):
        nodes = parse_dump(
            "<hierarchy><node text='请完成验证' content-desc='' clickable='false' "
            "checked='false' selected='false' bounds='[0,0][1,1]'/></hierarchy>"
        )
        with self.assertRaises(RiskSignal):
            sentinel_check(nodes)

    def test_error_code_stops(self):
        nodes = parse_dump(
            "<hierarchy><node text='错误码 403' content-desc='' clickable='false' "
            "checked='false' selected='false' bounds='[0,0][1,1]'/></hierarchy>"
        )
        with self.assertRaises(RiskSignal):
            sentinel_check(nodes)

    def test_clock_time_does_not_trigger_risk(self):
        nodes = parse_dump(
            "<hierarchy><node text='18:37' content-desc='' clickable='false' "
            "checked='false' selected='false' bounds='[0,0][1,1]'/></hierarchy>"
        )
        sentinel_check(nodes)  # a timestamp, not error code 37

    def test_plain_number_37_does_not_trigger_risk(self):
        nodes = parse_dump(
            "<hierarchy><node text='共 37 条联系人' content-desc='' clickable='false' "
            "checked='false' selected='false' bounds='[0,0][1,1]'/></hierarchy>"
        )
        sentinel_check(nodes)

    def test_error_code_37_stops(self):
        nodes = parse_dump(
            "<hierarchy><node text='错误码：37' content-desc='' clickable='false' "
            "checked='false' selected='false' bounds='[0,0][1,1]'/></hierarchy>"
        )
        with self.assertRaises(RiskSignal):
            sentinel_check(nodes)

    def test_clean_tree_passes(self):
        nodes = parse_dump(
            "<hierarchy><node text='候选人辛' content-desc='' clickable='true' "
            "checked='false' selected='false' bounds='[0,0][1,1]'/></hierarchy>"
        )
        sentinel_check(nodes)  # no raise


class VerifyStageTests(unittest.TestCase):
    """Offline tests for the verify stage: a FakeAdb replays canned dumps."""

    # -- fixtures ----------------------------------------------------------

    @staticmethod
    def _node(text="", rid="", clickable="false", bounds="[0,0][1,1]"):
        return (
            f"<node index='0' text='{text}' content-desc='' resource-id='{rid}' "
            f"class='android.widget.TextView' clickable='{clickable}' "
            f"checked='false' selected='false' bounds='{bounds}'/>"
        )

    @classmethod
    def _doc(cls, *nodes):
        return (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            "<hierarchy rotation='0'>" + "".join(nodes) + "</hierarchy>"
        )

    def _list_page(self, *names):
        rows = [
            self._node(text=name, rid="com.hpbr.bosszhipin:id/tv_name",
                       clickable="true", bounds="[40,300][300,380]")
            for name in names
        ]
        return self._doc(
            self._node(text="搜索联系人"),
            self._node(text="聊天"),
            self._node(text="全部", bounds="[60,379][144,436]"),
            self._node(text="新招呼", bounds="[192,379][318,436]"),
            *rows,
        )

    def _detail_page(self, contact, *lines):
        return self._doc(self._node(text=contact), *lines)

    def setUp(self):
        self._sleep = mock.patch("chat_resume_dispatch.time.sleep")
        self._sleep.start()
        self._rewind = mock.patch("chat_resume_dispatch.rewind_boss_list")
        self._rewind.start()
        self.addCleanup(self._rewind.stop)
        self.addCleanup(self._sleep.stop)

    class FakeAdb:
        """Offline Adb stand-in: replays canned dumps in order, records input."""

        def __init__(self, dumps):
            self._dumps = list(dumps)
            self._last = ""
            self.taps = []
            self.swipes = []
            self.keyevents = []
            self.launched = []
            self.dry_run = False
            self.serial = "fake"

        def resolve_serial(self):
            return self.serial

        def dump(self):
            if self._dumps:
                self._last = self._dumps.pop(0)
            return self._last

        def tap(self, x, y):
            self.taps.append((x, y))

        def swipe(self, x1, y1, x2, y2, ms):
            self.swipes.append((x1, y1, x2, y2, ms))

        def keyevent(self, code):
            self.keyevents.append(code)

        def launch_app(self, package):
            self.launched.append(package)

    # -- tests -------------------------------------------------------------

    def test_verify_skips_outsourcing_identity_hidden_in_detail(self):
        # 候选人壬's list snippet looked clean; only the chat body reveals 某外包公司.
        # dump sequence: back-out probe, greeting-tab find, screen-0 list, detail.
        dumps = [
            self._list_page("候选人壬"),
            self._list_page("候选人壬"),
            self._list_page("候选人壬"),
            self._doc(
                self._node(text="候选人壬"),
                self._node(text="这边是某外包公司，目前做的是字节项目"),
                self._node(text="简历可以发我一份，合适可以帮你推荐哈~"),
            ),
        ]
        item = {
            "key": "dai", "contact": "候选人壬", "org": "", "city": "",
            "role": "Java", "snippet": "[新招呼] 简历可以发我一份，...",
            "resume": JAVA, "approved": False, "sent": False,
            "is_resume_request": True,
        }
        adb = self.FakeAdb(dumps)
        updated = verify_one(adb, item, CFG)
        self.assertTrue(updated["verified"])
        self.assertTrue(updated["detail_found"])
        self.assertEqual(updated["verdict"], "skip")
        self.assertTrue(updated["skipped"])
        self.assertIn("外包", updated["skip_reason"])
        # outsourcing skip must not flip the resume or touch the review gate
        self.assertEqual(updated["resume"], JAVA)
        self.assertFalse(updated["resume_changed"])
        self.assertFalse(updated["approved"])
        self.assertFalse(updated["sent"])
        self.assertEqual(adb.launched, [BOSS_PKG])
        self.assertIn(4, adb.keyevents)  # backed out of the conversation

    def test_verify_passes_and_never_taps_send(self):
        dumps = [
            self._list_page("候选人乙"),
            self._list_page("候选人乙"),
            self._list_page("候选人乙"),
            self._doc(
                self._node(text="候选人乙"),
                self._node(text="某科技公司甲"),
                self._node(text="Kaon.io·FlowGPT AIGC内容平台"),
                self._node(text="方便发一份你的简历过来吗？"),
                self._node(text="发简历"),
            ),
        ]
        item = {
            "key": "zhang", "contact": "候选人乙", "org": "某科技公司甲",
            "city": "", "role": "Gol...",
            "snippet": "[新招呼] 方便发一份你的简历过...",
            "resume": GO, "approved": False, "sent": False,
            "is_resume_request": True,
        }
        adb = self.FakeAdb(dumps)
        updated = verify_one(adb, item, CFG)
        self.assertEqual(updated["verdict"], "pass")
        self.assertNotIn("skipped", updated)
        self.assertEqual(updated["resume"], GO)
        # Read-only on the device: exactly the 消息 tab + 全部 sub-tab +
        # the chat row, nothing else.
        self.assertEqual(
            adb.taps,
            [(102, 407), (170, 340)],  # 全部 sub-tab and chat row
        )

    def test_open_boss_chat_taps_all_sub_tab(self):
        # User direction (2026-11-24): scan the 全部 sub-tab, NOT 新招呼.
        list_page = self._list_page("候选人乙")
        dumps = [list_page, list_page, list_page,
                 self._detail_page("候选人乙", "方便发一份你的简历过来吗？")]
        adb = self.FakeAdb(dumps)
        location = open_boss_chat(adb, "候选人乙", max_screens=1)
        self.assertTrue(location["found"])
        self.assertIn((102, 407), adb.taps)  # 全部 sub-tab center
        self.assertNotIn((255, 407), adb.taps)  # 新招呼 must not be tapped

    def test_open_boss_chat_fails_closed_without_all_sub_tab(self):
        list_page = self._doc(
            self._node(text="搜索联系人"),
            self._node(text="聊天"),
            self._node(text="新招呼", bounds="[192,379][318,436]"),
        )
        adb = self.FakeAdb([list_page])
        with self.assertRaises(DeviceError):
            open_boss_chat(adb, "候选人乙", max_screens=1)

    def test_open_boss_chat_uses_live_greeting_bounds(self):
        # BOSS renders the 消息 sub-tabs in two layouts ([60,379][144,436]
        # etc.). The code must tap the *live* dump bounds of 全部, never a
        # hardcoded coordinate.
        list_page = self._doc(
            self._node(text="搜索联系人、公司、聊天记录", rid="et_input"),
            self._node(text="聊天"),
            self._node(text="全部", bounds="[192,379][318,436]"),
            self._node(text="候选人乙", rid="com.hpbr.bosszhipin:id/tv_name",
                       clickable="true", bounds="[249,2013][405,2078]"),
        )
        detail = self._detail_page("候选人乙", "方便发一份你的简历过来吗？")
        adb = self.FakeAdb([list_page, list_page, list_page, detail])
        location = open_boss_chat(adb, "候选人乙", max_screens=1)
        self.assertTrue(location["found"])
        self.assertIn((255, 407), adb.taps)  # live 全部 center
        self.assertNotIn((102, 407), adb.taps)  # stale coordinate must go

    def test_rewind_moves_retained_bottom_to_top(self):
        self._rewind.stop()
        from chat_resume_dispatch import rewind_boss_list
        bottom = self._list_page("底部联系人")
        top = self._list_page("顶部联系人")
        adb = self.FakeAdb([bottom, top, top, top])
        rewind_boss_list(adb, max_screens=3)
        self.assertEqual(adb.swipes, [(540, 650, 540, 1750, 600)] * 2)

    def test_rewind_fails_closed_if_top_not_established(self):
        self._rewind.stop()
        from chat_resume_dispatch import rewind_boss_list
        adb = self.FakeAdb([self._list_page("一"), self._list_page("二")])
        with self.assertRaises(DeviceError):
            rewind_boss_list(adb, max_screens=1)

    def test_verify_reinfers_resume_from_detail(self):
        dumps = [
            self._list_page("刘先生"),
            self._list_page("刘先生"),
            self._list_page("刘先生"),
            self._doc(
                self._node(text="刘先生"),
                self._node(text="我们这边是Java微服务，看一下你的简历吧"),
            ),
        ]
        item = {
            "key": "liu", "contact": "刘先生", "org": "", "city": "",
            "role": "", "snippet": "[简历]我想要一份你的简历，你是否同意?",
            "resume": GO, "approved": False, "sent": False,
            "is_resume_request": True,
        }
        updated = verify_one(self.FakeAdb(dumps), item, CFG)
        self.assertEqual(updated["verdict"], "pass")
        self.assertTrue(updated["resume_changed"])
        self.assertEqual(updated["resume"], JAVA)

    def test_verify_backs_out_of_a_wrong_row_and_keeps_scrolling(self):
        list_page = self._list_page("候选人乙")
        wrong_detail = self._doc(self._node(text="王女士"), self._node(text="你好"))
        right_detail = self._doc(
            self._node(text="候选人乙"),
            self._node(text="某科技公司甲"),
            self._node(text="方便发一份你的简历过来吗？"),
        )
        dumps = [list_page, list_page, list_page, wrong_detail, list_page, right_detail]
        item = {
            "key": "zhang", "contact": "候选人乙", "org": "某科技公司甲",
            "city": "", "role": "Gol...", "snippet": "方便发一份你的简历过...",
            "resume": GO, "approved": False, "sent": False,
            "is_resume_request": True,
        }
        adb = self.FakeAdb(dumps)
        updated = verify_one(adb, item, CFG)
        self.assertTrue(updated["detail_found"])
        self.assertIn("方便发一份你的简历过来吗", updated["detail_text"])
        # one BACK to escape the wrong conversation + one to leave the right one
        self.assertEqual(adb.keyevents.count(4), 2)

    def test_verify_rejects_same_name_wrong_org(self):
        # Real-device run 2026-11-25: two recruiters both display 候选人丙. The
        # list row said 某社交平台, but the opened detail was 某金融公司. verify must
        # not screen the wrong conversation as if it were the queued one.
        list_page = self._list_page("候选人丙")
        wrong_detail = self._doc(
            self._node(text="候选人丙"),
            self._node(text="某金融公司 · 招聘专员"),
            *(self._node(text=f"推荐职位{i}") for i in range(6)),
            self._node(text="某社交平台"),  # recommendation card, not the header
        )
        dumps = [list_page, list_page, list_page, wrong_detail]
        item = {
            "key": "wang", "contact": "候选人丙", "org": "某社交平台 | Java",
            "city": "", "role": "Java",
            "snippet": "我想要一份您的附件简历，您是否同意",
            "resume": JAVA, "approved": False, "sent": False,
            "is_resume_request": True,
        }
        updated = verify_one(self.FakeAdb(dumps), item, CFG, max_screens=1)
        self.assertFalse(updated["detail_found"])
        self.assertEqual(updated["verdict"], "unverified")
        self.assertNotIn("skipped", updated)
        self.assertEqual(updated["resume"], JAVA)

    def test_verify_marks_unverified_when_contact_not_found(self):
        dumps = [self._list_page("别人"), self._list_page("别人")]
        item = {
            "key": "ghost", "contact": "赵六", "org": "", "city": "",
            "role": "", "snippet": "[简历]我想要一份你的简历，你是否同意?",
            "resume": GO, "approved": False, "sent": False,
            "is_resume_request": True,
        }
        updated = verify_one(self.FakeAdb(dumps), item, CFG, max_screens=2)
        self.assertFalse(updated["detail_found"])
        self.assertEqual(updated["verdict"], "unverified")
        self.assertNotIn("skipped", updated)
        self.assertNotIn("skip_reason", updated)
        self.assertEqual(updated["resume"], GO)  # untouched for the human
        self.assertEqual(updated["approved"], False)

    def test_verify_success_clears_stale_unverified_note(self):
        # A previous run may have left `verify_note` from an unverified result.
        # Once the chat is found and passes, that stale note must not survive
        # into human review.
        dumps = [
            self._list_page("候选人乙"),
            self._list_page("候选人乙"),
            self._list_page("候选人乙"),
            self._detail_page("候选人乙", "方便发一份你的简历过来吗？"),
        ]
        item = {
            "key": "zhang", "contact": "候选人乙", "org": "",
            "city": "", "role": "Gol...", "snippet": "方便发一份你的简历过...",
            "resume": GO, "approved": False, "sent": False,
            "is_resume_request": True,
            "verified": True, "detail_found": False, "verdict": "unverified",
            "verify_note": "contact '候选人乙' not located in the BOSS chat list",
        }
        updated = verify_one(self.FakeAdb(dumps), item, CFG)
        self.assertTrue(updated["detail_found"])
        self.assertEqual(updated["verdict"], "pass")
        self.assertNotIn("verify_note", updated)

    def test_verify_raises_risk_signal_from_detail(self):
        dumps = [
            self._list_page("候选人乙"),
            self._list_page("候选人乙"),
            self._list_page("候选人乙"),
            self._doc(self._node(text="候选人乙"), self._node(text="请完成验证")),
        ]
        item = {"key": "z", "contact": "候选人乙", "snippet": "方便发一份你的简历过...",
                "resume": GO, "approved": False, "sent": False,
                "is_resume_request": True}
        with self.assertRaises(RiskSignal):
            verify_one(self.FakeAdb(dumps), item, CFG)

    def test_open_boss_chat_backs_out_of_resumed_chat_room(self):
        chat_room = self._doc(self._node(text="候选人乙"), self._node(text="发简历"))
        dumps = [chat_room, self._list_page("候选人乙")]
        adb = self.FakeAdb(dumps)
        location = open_boss_chat(adb, "候选人乙", max_screens=1)
        self.assertTrue(location["found"])
        self.assertEqual(adb.keyevents, [4])  # one back-out, then the list

    def test_open_boss_chat_recovers_when_monkey_resumes_jobs_tab(self):
        # Real-device run 2 failure: monkey resumed BOSS on the 职位 tab; the
        # back-loop never sees chat-list anchors and must fall back to tapping
        # the 消息 tab instead of raising DeviceError.
        jobs = self._doc(
            self._node(text="职位"), self._node(text="推荐"),
            self._node(text="消息", rid="com.hpbr.bosszhipin:id/tv_tab_3"), self._node(text="我的"),
        )
        dumps = [jobs] * 7 + [
            self._list_page("候选人乙"),
            self._list_page("候选人乙"),
            self._list_page("候选人乙"),
            self._doc(self._node(text="候选人乙"),
                      self._node(text="方便发一份你的简历过来吗？")),
        ]
        adb = self.FakeAdb(dumps)
        location = open_boss_chat(adb, "候选人乙", max_screens=1)
        self.assertTrue(location["found"])
        self.assertIn(BOSS_MSG_TAB, adb.taps)  # the recovery tap

    def test_open_boss_chat_still_raises_when_tab_tap_lands_nowhere(self):
        jobs = self._doc(self._node(text="职位"), self._node(text="推荐"))
        adb = self.FakeAdb([jobs])
        with self.assertRaises(DeviceError):
            open_boss_chat(adb, "候选人乙", max_screens=1)

    def test_apply_verify_result_preserves_review_gate(self):
        queue = [{"key": "z", "contact": "候选人乙", "approved": True, "sent": False}]
        updated = {"key": "z", "contact": "候选人乙", "verdict": "pass",
                   "approved": True, "sent": False}
        apply_verify_result(queue, updated)
        self.assertEqual(queue[0]["verdict"], "pass")
        self.assertTrue(queue[0]["approved"])
        self.assertFalse(queue[0]["sent"])

    def test_verify_targets_are_boss_only(self):
        queue = [
            {"key": "boss1", "is_resume_request": True, "platform": "boss"},
            {"key": "lp1", "is_resume_request": True, "platform": "liepin"},
            {"key": "noplat", "is_resume_request": True},
            {"key": "skipped", "is_resume_request": True, "skipped": True},
            {"key": "sent", "is_resume_request": True, "sent": True},
            {"key": "notreq", "is_resume_request": False},
        ]
        targets, paused = _verify_targets(queue)
        self.assertEqual([t["key"] for t in targets], ["boss1", "noplat"])
        self.assertEqual(paused, 1)


class RecencyTests(unittest.TestCase):
    def test_parse_list_time_relative_to_capture_date(self):
        captured = date(2026, 11, 24)  # Tuesday
        self.assertEqual(parse_list_time("19:48", captured), captured)
        self.assertEqual(parse_list_time("昨天 23:49", captured), date(2026, 11, 23))
        self.assertEqual(parse_list_time("星期三", captured), date(2026, 11, 18))
        self.assertEqual(parse_list_time("星期四 10:22", captured), date(2026, 11, 19))
        self.assertEqual(parse_list_time("星期日", captured), date(2026, 11, 22))
        self.assertEqual(parse_list_time("11月11日", captured), date(2026, 11, 11))
        self.assertEqual(parse_list_time("12月31日", captured), date(2025, 12, 31))
        self.assertIsNone(parse_list_time("未知", captured))

    def test_load_list_times_joins_rows_from_saved_dumps(self):
        base = "com.hpbr.bosszhipin:id/"
        def node(suffix, text, y):
            return (f"<node text='{text}' content-desc='' resource-id='{base}{suffix}' "
                    f"bounds='[0,{y}][1000,{y + 40}]' clickable='false' checked='false' selected='false'/>")
        xml = "<hierarchy>" + "".join([
            node("tv_name", "甲", 300), node("tv_position", "甲公司 | Java", 306),
            node("tv_msg", "发一份简历", 379), node("tv_time_v2", "昨天 10:45", 383),
            node("tv_name", "乙", 528), node("tv_position", "乙公司 | Golang", 534),
            node("tv_msg", "我想要一份你的简历", 607), node("tv_time_v2", "11月11日", 611),
        ]) + "</hierarchy>"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "page_000.xml"
            path.write_text(xml, encoding="utf-8")
            times = load_list_times([path], date(2026, 11, 24))
        self.assertEqual(times[("甲", "甲公司 | Java", "发一份简历")], [date(2026, 11, 23)])
        self.assertEqual(times[("乙", "乙公司 | Golang", "我想要一份你的简历")], [date(2026, 11, 11)])

    def test_filter_recent_entries_uses_inclusive_seven_calendar_days(self):
        def entry(name, org, snippet, **extra):
            return {"contact": name, "org": org, "list_snippet": snippet,
                    "approved": False, "sent": False, **extra}
        entries = [
            entry("甲", "甲公司 | Java", "发一份简历"),
            entry("乙", "乙公司 | Golang", "我想要一份你的简历"),
            entry("丙", "丙公司 | Java", "简历可以发我一份"),
        ]
        times = {
            ("甲", "甲公司 | Java", "发一份简历"): [date(2026, 11, 19)],  # boundary
            ("乙", "乙公司 | Golang", "我想要一份你的简历"): [date(2026, 11, 18)],  # stale
            ("丙", "丙公司 | Java", "简历可以发我一份"): [],  # unknown
        }
        included, excluded = filter_recent_entries(
            entries, times, as_of=date(2026, 11, 25), captured_on=date(2026, 11, 24), days=7,
        )
        self.assertEqual([item["contact"] for item in included], ["甲"])
        self.assertEqual(included[0]["last_activity_date"], "2026-11-19")
        self.assertTrue(included[0]["recent_window"])
        self.assertFalse(included[0]["approved"])
        self.assertFalse(included[0]["sent"])
        self.assertEqual([item["contact"] for item in excluded], ["乙", "丙"])
        self.assertEqual(excluded[0]["recency_reason"], "older_than_one_week")
        self.assertEqual(excluded[1]["recency_reason"], "time_unknown")

    def test_recent_report_is_not_an_authorization(self):
        report = render_recent_markdown(
            [{"contact": "甲", "org": "甲公司", "list_snippet": "发一份简历",
              "resume": JAVA, "last_activity_date": "2026-11-19", "source_line": 1}],
            [{"contact": "乙", "recency_reason": "older_than_one_week"}],
            as_of=date(2026, 11, 25), captured_on=date(2026, 11, 24), days=7,
        )
        self.assertIn("近一周人工审核清单", report)
        self.assertIn("2026-11-19", report)
        self.assertIn("这不是发送授权", report)
        self.assertIn("乙", report)


FOLLOWUP_TEXT = (
    "提前和您说一下最近一次离职原因：任职期间需求交付正常、产出达转正标准；"
    "后团队组织架构与业务方向调整，岗位保留但方向和个人发展不匹配。"
    "离职前已拿到一家公司正式 offer、计划无缝入职，因此主动提出离职（无补偿）；"
    "办完离职后对方 HC 收缩、名额撤回，于是进入空档期继续找机会。"
)


class FollowUpMessageTests(unittest.TestCase):
    """Offline proof that the post-resume message is safe and observable."""

    class FakeAdb:
        def __init__(self, dumps, *, package_installed=True, original_ime="com.example.ime"):
            self.dumps = list(dumps)
            self.taps: list[tuple[int, int]] = []
            self.inputs: list[str] = []
            self.installed_paths: list[str] = []
            self.ime_calls: list[str] = []
            self.current = original_ime
            self._package_installed = package_installed
            self._last_dump = "<hierarchy/>"

        def dump(self):
            if not self.dumps:
                return self._last_dump
            self._last_dump = self.dumps.pop(0)
            return self._last_dump

        def tap(self, x, y):
            self.taps.append((x, y))

        def current_ime(self):
            return self.current

        def is_package_installed(self, package):
            return self._package_installed

        def install_apk(self, path):
            self.installed_paths.append(str(path))

        def enable_ime(self, ime):
            self.ime_calls.append(f"enable:{ime}")

        def set_ime(self, ime):
            self.current = ime
            self.ime_calls.append(f"set:{ime}")

        def input_b64(self, text):
            self.inputs.append(text)

    @staticmethod
    def _node(rid="", cls="android.widget.TextView", text="", clickable=False,
              checked=False, selected=False, bounds="[0,0][0,0]"):
        return (
            f'<node resource-id="{rid}" class="{cls}" text="{text}" '
            f'content-desc="" clickable="{str(clickable).lower()}" '
            f'checked="{str(checked).lower()}" selected="{str(selected).lower()}" '
            f'bounds="{bounds}"/>'
        )

    @classmethod
    def _doc(cls, *nodes):
        return "<hierarchy>" + "".join(nodes) + "</hierarchy>"

    def _resume_dumps(self, *, confirmed=True, typed_visible=True):
        resume_page = self._doc(
            self._node(text="甲"),
            self._node(text="发简历", clickable=False, bounds="[600,300][700,350]"),
        )
        picker = self._doc(
            self._node(text=GO, clickable=True, bounds="[100,500][500,560]"),
        )
        selected = self._doc(
            self._node(text=GO, clickable=True, checked=True, bounds="[100,500][500,560]"),
            self._node(text="立即投递", clickable=True, bounds="[100,700][500,760]"),
        )
        confirmation = self._doc(
            self._node(text="这是我的简历" if confirmed else "已提交，等待对方查看"),
        )
        chat_input = self._doc(
            self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                       "android.widget.EditText", "和Ta聊一聊~",
                       bounds="[147,2150][825,2208]"),
        )
        typed = self._doc(
            self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                       "android.widget.EditText", FOLLOWUP_TEXT if typed_visible else "和Ta聊一聊~",
                       bounds="[147,2150][825,2208]"),
            self._node(text="发送", clickable=True, bounds="[948,2148][1032,2208]"),
        )
        sent = self._doc(
            self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                       "android.widget.EditText", "和Ta聊一聊~",
                       bounds="[147,2150][825,2208]"),
            self._node(text=FOLLOWUP_TEXT),
        )
        dumps = [resume_page, picker, selected, confirmation]
        if confirmed:
            dumps.extend([chat_input, typed, sent])
            if not typed_visible:
                dumps.append(typed)
        return dumps

    def _item(self):
        return {"key": "k1", "contact": "甲", "resume": GO,
                "approved": True, "verified": True, "detail_found": True,
                "verdict": "pass", "recent_window": True, "sent": False}

    def _resume_dumps_with_parent_picker(self, *, confirmed=True, typed_visible=True):
        dumps = self._resume_dumps(confirmed=confirmed, typed_visible=typed_visible)

        def picker(selected_go=False):
            return self._doc(
                self._node(rid="com.hpbr.bosszhipin:id/linearLayout5",
                           cls="android.view.ViewGroup", text="", clickable=True,
                           checked=selected_go, bounds="[60,1513][1020,1805]"),
                self._node(rid="com.hpbr.bosszhipin:id/mResumeName",
                           text=f"{GO}-Harness.pdf", bounds="[207,1561][894,1689]"),
                self._node(rid="com.hpbr.bosszhipin:id/linearLayout5",
                           cls="android.view.ViewGroup", text="", clickable=True,
                           checked=False, bounds="[60,1808][1020,2100]"),
                self._node(rid="com.hpbr.bosszhipin:id/mResumeName",
                           text=f"{JAVA}-Harness.pdf", bounds="[207,1856][894,1984]"),
                *([self._node(text="立即投递", clickable=True, bounds="[100,700][500,760]")]
                  if selected_go else []),
            )

        dumps[1] = picker(selected_go=False)
        dumps[2] = picker(selected_go=True)
        return dumps

    def test_picker_uses_clickable_parent_and_suffixed_resume_name(self):
        adb = self.FakeAdb(self._resume_dumps_with_parent_picker())
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, self._item(), Path("."), 0.1, followup_text=FOLLOWUP_TEXT)
        self.assertTrue(result["selection_verified_by_ui"])
        self.assertTrue(result["send_confirmed"])
        self.assertIn((540, 1659), adb.taps)

    def test_already_sent_resume_only_sends_followup(self):
        already_sent = self._doc(
            self._node(text="甲"),
            self._node(text="已发送给Boss点击查看附件"),
            self._node(text=f"{GO}-Harness.pdf"),
            self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                       "android.widget.EditText", "和Ta聊一聊~",
                       bounds="[147,2150][825,2208]"),
        )
        adb = self.FakeAdb([
            already_sent,
            self._doc(
                self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                           "android.widget.EditText", "和Ta聊一聊~",
                           bounds="[147,2150][825,2208]"),
            ),
            self._doc(
                self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                           "android.widget.EditText", FOLLOWUP_TEXT,
                           bounds="[147,2150][825,2208]"),
                self._node(text="发送", clickable=True, bounds="[948,2148][1032,2208]"),
            ),
            self._doc(
                self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                           "android.widget.EditText", "和Ta聊一聊~",
                           bounds="[147,2150][825,2208]"),
                self._node(text=FOLLOWUP_TEXT),
            ),
        ])
        item = {**self._item(), "resume_already_sent": True,
                "resume_sent_at": "2026-11-25T08:24:00"}
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, item, Path("."), 0.1, followup_text=FOLLOWUP_TEXT)
        self.assertTrue(result["send_confirmed"])
        self.assertTrue(result["followup_confirmed"])
        self.assertEqual(result["sent_at"], "2026-11-25T08:24:00")
        self.assertNotIn((675, 325), adb.taps)
        self.assertEqual(adb.inputs, [FOLLOWUP_TEXT])

    def test_already_sent_resume_accepts_boss_truncated_summary(self):
        # Live 2026-11-26: BOSS truncates the resume name to "候选人-开..." in
        # the delivered-resume system message. The ledger carries the exact
        # version; the UI only needs to prove a resume request was sent.
        already_sent = self._doc(
            self._node(text="甲"),
            self._node(text="您的附件简历 候选人-开... 已发送给Boss点击查看附件"),
            self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                       "android.widget.EditText", "和Ta聊一聊~",
                       bounds="[147,2150][825,2208]"),
        )
        adb = self.FakeAdb([
            already_sent,
            self._doc(
                self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                           "android.widget.EditText", "和Ta聊一聊~",
                           bounds="[147,2150][825,2208]"),
            ),
            self._doc(
                self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                           "android.widget.EditText", FOLLOWUP_TEXT,
                           bounds="[147,2150][825,2208]"),
                self._node(text="发送", clickable=True, bounds="[948,2148][1032,2208]"),
            ),
            self._doc(
                self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                           "android.widget.EditText", "和Ta聊一聊~",
                           bounds="[147,2150][825,2208]"),
                self._node(text=FOLLOWUP_TEXT),
            ),
        ])
        item = {**self._item(), "resume": "候选人-开发工程师-GO-Agent",
                "resume_already_sent": True,
                "resume_sent_at": "2026-11-26T07:43:00"}
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, item, Path("."), 0.1, followup_text=FOLLOWUP_TEXT)
        self.assertTrue(result["send_confirmed"])
        self.assertTrue(result["followup_confirmed"])
        self.assertEqual(adb.inputs, [FOLLOWUP_TEXT])

    def test_selecting_resume_directly_starts_request_without_immediately_deliver_button(self):
        # 2026-11-25 live BOSS UI: tapping the resume row closes the picker and
        # flips the header to 请求中. There is no selected-state row to verify and
        # no 立即投递 button to tap; the request has already been initiated.
        after_select = self._doc(
            self._node(text="甲"),
            self._node(text="请求中", bounds="[621,336][729,385]"),
        )
        dumps = self._resume_dumps_with_parent_picker()
        dumps[2] = after_select
        del dumps[3]  # no separate confirmation screen in this live flow
        adb = self.FakeAdb(dumps)
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, self._item(), Path("."), 0.1, followup_text=FOLLOWUP_TEXT)
        self.assertTrue(result["selection_verified_by_ui"])
        self.assertTrue(result["send_confirmed"])
        self.assertTrue(result["followup_confirmed"])
        self.assertEqual(adb.taps.count((540, 1659)), 1)  # GO row tapped once
        self.assertNotIn((300, 730), adb.taps)  # no 立即投递 tap

    def test_selecting_resume_waits_for_request_state_before_verifying_picker(self):
        # Live 2026-11-25 run: after tapping the GO row the picker closed, but
        # the header briefly still showed 发简历 before changing to 请求中.
        # Treating that transient frame as the old picker flow raised
        # "expected exactly one name label ... got 0" and aborted the run.
        transient_detail = self._doc(
            self._node(text="甲"),
            self._node(text="发简历", clickable=False, bounds="[621,336][729,385]"),
        )
        request_started = self._doc(
            self._node(text="甲"),
            self._node(text="请求中", bounds="[621,336][729,385]"),
        )
        dumps = self._resume_dumps_with_parent_picker()
        dumps[2] = transient_detail
        dumps.insert(3, request_started)
        del dumps[4]  # no separate old-flow confirmation screen
        adb = self.FakeAdb(dumps)
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, self._item(), Path("."), 0.1, followup_text=FOLLOWUP_TEXT)
        self.assertTrue(result["selection_verified_by_ui"])
        self.assertTrue(result["send_confirmed"])
        self.assertTrue(result["followup_confirmed"])
        self.assertEqual(adb.taps.count((540, 1659)), 1)
        self.assertNotIn((300, 730), adb.taps)

    def test_selecting_resume_waits_for_slow_request_confirmation(self):
        # Live 2026-11-26 run: the resume was accepted, but the
        # "已发送给Boss" message appeared after the original 10 x 0.4s window.
        transient_detail = self._doc(
            self._node(text="甲"),
            self._node(text="发简历", clickable=False, bounds="[621,336][729,385]"),
        )
        request_started = self._doc(
            self._node(text="甲"),
            self._node(text="您的附件简历 候选人-开... 已发送给Boss点击查看附件"),
        )
        dumps = self._resume_dumps_with_parent_picker()
        dumps[2] = transient_detail
        dumps[3:4] = [transient_detail] * 11 + [request_started]
        adb = self.FakeAdb(dumps)
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, self._item(), Path("."), 0.1, followup_text=FOLLOWUP_TEXT)
        self.assertTrue(result["selection_verified_by_ui"])
        self.assertTrue(result["send_confirmed"])
        self.assertTrue(result["followup_confirmed"])
        self.assertEqual(adb.taps.count((540, 1659)), 1)
        self.assertNotIn((300, 730), adb.taps)

    def test_already_sent_resume_accepts_pending_request_state(self):
        pending = self._doc(
            self._node(text="甲"),
            self._node(text="请求中", bounds="[621,336][729,385]"),
            self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                       "android.widget.EditText", "和Ta聊一聊~",
                       bounds="[147,2150][825,2208]"),
        )
        adb = self.FakeAdb([
            pending,
            self._doc(self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                 "android.widget.EditText", "和Ta聊一聊~",
                                 bounds="[147,2150][825,2208]")),
            self._doc(self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                 "android.widget.EditText", FOLLOWUP_TEXT,
                                 bounds="[147,2150][825,2208]"),
                      self._node(text="发送", clickable=True, bounds="[948,2148][1032,2208]")),
            self._doc(self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                 "android.widget.EditText", "和Ta聊一聊~",
                                 bounds="[147,2150][825,2208]"),
                      self._node(text=FOLLOWUP_TEXT)),
        ])
        item = {**self._item(), "resume_already_sent": True,
                "resume_sent_at": "2026-11-25T21:40:00"}
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, item, Path("."), 0.1, followup_text=FOLLOWUP_TEXT)
        self.assertTrue(result["send_confirmed"])
        self.assertTrue(result["followup_confirmed"])
        self.assertEqual(result["sent_at"], "2026-11-25T21:40:00")
        self.assertEqual(adb.inputs, [FOLLOWUP_TEXT])

    def test_followup_is_sent_only_after_confirmed_resume(self):
        adb = self.FakeAdb(self._resume_dumps())
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, self._item(), Path("."), 0.1, followup_text=FOLLOWUP_TEXT)
        self.assertTrue(result["send_confirmed"])
        self.assertTrue(result["followup_sent"])
        self.assertTrue(result["followup_confirmed"])
        self.assertEqual(adb.inputs, [FOLLOWUP_TEXT])
        self.assertIn((990, 2178), adb.taps)
        self.assertEqual(adb.ime_calls[-1], "set:com.example.ime")

    def test_unconfirmed_resume_skips_followup(self):
        adb = self.FakeAdb(self._resume_dumps(confirmed=False))
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, self._item(), Path("."), 0.0, followup_text=FOLLOWUP_TEXT)
        self.assertFalse(result["send_confirmed"])
        self.assertFalse(result["followup_sent"])
        self.assertEqual(adb.inputs, [])

    def test_followup_not_visible_before_send_does_not_tap_send(self):
        adb = self.FakeAdb(self._resume_dumps(typed_visible=False))
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, self._item(), Path("."), 0.1, followup_text=FOLLOWUP_TEXT)
        self.assertTrue(result["send_confirmed"])
        self.assertFalse(result["followup_sent"])
        self.assertIn("not visible", result["followup_error"])
        self.assertNotIn((948, 2148), adb.taps)
        self.assertEqual(adb.ime_calls[-1], "set:com.example.ime")

    def test_followup_send_button_can_be_icon_when_adbkeyboard_is_active(self):
        adb = self.FakeAdb([
            self._doc(
                self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                           "android.widget.EditText", "和Ta聊一聊~",
                           bounds="[147,2150][825,2208]"),
            ),
            self._doc(
                self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                           "android.widget.EditText", FOLLOWUP_TEXT,
                           bounds="[147,1822][825,2171]"),
                self._node(cls="android.widget.ImageView", clickable=True,
                           bounds="[948,2087][1032,2171]"),
            ),
            self._doc(
                self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                           "android.widget.EditText", "和Ta聊一聊~",
                           bounds="[147,2150][825,2208]"),
                self._node(text=FOLLOWUP_TEXT),
            ),
        ])
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_followup(adb, FOLLOWUP_TEXT, Path("."), 0.1)
        self.assertTrue(result["followup_confirmed"])
        self.assertIn((990, 2129), adb.taps)

    def test_missing_keyboard_is_installed_and_ime_is_restored(self):
        adb = self.FakeAdb([
            self._doc(self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                 "android.widget.EditText", "和Ta聊一聊~",
                                 bounds="[147,2150][825,2208]")),
            self._doc(self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                 "android.widget.EditText", FOLLOWUP_TEXT,
                                 bounds="[147,2150][825,2208]"),
                      self._node(text="发送", clickable=True, bounds="[948,2148][1032,2208]")),
            self._doc(self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                 "android.widget.EditText", "和Ta聊一聊~",
                                 bounds="[147,2150][825,2208]"),
                      self._node(text=FOLLOWUP_TEXT)),
        ])
        adb._package_installed = False
        apk = Path("fake-keyboard.apk")
        with mock.patch("chat_resume_dispatch.fetch_adb_keyboard_apk", return_value=apk) as fetch, \
             mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_followup(adb, FOLLOWUP_TEXT, Path("."), 0.1)
        self.assertTrue(result["followup_sent"])
        fetch.assert_called_once()
        self.assertEqual(adb.installed_paths, [str(apk)])
        self.assertIn("set:com.android.adbkeyboard/.AdbIME", adb.ime_calls)
        self.assertEqual(adb.ime_calls[-1], "set:com.example.ime")

    def test_followup_risk_still_marks_resume_sent_and_stops_batch(self):
        dumps = self._resume_dumps()
        dumps[4] = self._doc(
            self._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                       "android.widget.EditText", "和Ta聊一聊~",
                       bounds="[147,2150][825,2208]"),
            self._node(text="请完成验证"),
        )
        adb = self.FakeAdb(dumps)
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, self._item(), Path("."), 0.1, followup_text=FOLLOWUP_TEXT)
        self.assertTrue(result["send_confirmed"])
        self.assertFalse(result["followup_sent"])
        self.assertIn("risk_signal", result)
        self.assertEqual(adb.inputs, [])

    def test_missing_followup_file_refuses_before_any_device_action(self):
        with tempfile.TemporaryDirectory() as td:
            queue_path = Path(td) / "queue.json"
            queue_path.write_text(json.dumps([self._item()], ensure_ascii=False), encoding="utf-8")
            args = argparse.Namespace(
                yes_i_reviewed=True, serial="TEST", dry_run=True,
                queue=str(queue_path), ledger=str(Path(td) / "ledger.jsonl"),
                evidence=".", timeout=0.1, auto_open=False, max_screens=7,
                followup_file=str(Path(td) / "missing.txt"),
            )
            with mock.patch("chat_resume_dispatch.Adb") as adb_cls, \
                 mock.patch("chat_resume_dispatch.send_one") as send:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_send(args, CFG), 1)
            adb_cls.assert_not_called()
            send.assert_not_called()


class HumanizeTests(unittest.TestCase):
    class FixedRng:
        def __init__(self, value: float):
            self.value = value
            self.ranges: list[tuple[float, float]] = []

        def uniform(self, low: float, high: float) -> float:
            self.ranges.append((low, high))
            return self.value

    def test_human_pause_sleeps_within_range_and_can_be_disabled(self):
        rng = self.FixedRng(1.4)
        with mock.patch("chat_resume_dispatch.time.sleep") as sleep:
            delay = human_pause("navigation", rng=rng)
        self.assertEqual(delay, 1.4)
        sleep.assert_called_once_with(1.4)
        self.assertIn((0.6, 2.2), rng.ranges)

        with mock.patch("chat_resume_dispatch.time.sleep") as sleep:
            delay = human_pause("navigation", enabled=False, rng=self.FixedRng(1.4))
        self.assertEqual(delay, 0.0)
        sleep.assert_not_called()

    def test_no_humanize_flag_is_available(self):
        args = build_parser().parse_args(["--no-humanize", "send"])
        self.assertTrue(args.no_humanize)

    def test_send_one_humanizes_gap_before_followup(self):
        helper = FollowUpMessageTests()
        adb = FollowUpMessageTests.FakeAdb(helper._resume_dumps())
        with mock.patch("chat_resume_dispatch.time.sleep"), \
             mock.patch("chat_resume_dispatch.human_pause", wraps=human_pause) as pause:
            result = send_one(adb, helper._item(), Path("."), 0.1,
                              followup_text=FOLLOWUP_TEXT, humanize=True)
        self.assertTrue(result["send_confirmed"])
        self.assertTrue(result["followup_sent"])
        kinds = [call.args[0] for call in pause.call_args_list]
        self.assertIn("resume_to_followup", kinds)

    def test_cmd_send_pauses_between_candidates_but_not_after_risk_signal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            queue_path = root / "queue.json"
            followup_path = root / "followup.txt"
            followup_path.write_text(FOLLOWUP_TEXT, encoding="utf-8")
            queue_path.write_text(json.dumps([
                {"key": "k1", "contact": "甲", "org": "甲公司 | Java", "resume": JAVA,
                 "approved": True, "verified": True, "detail_found": True,
                 "verdict": "pass", "recent_window": True, "sent": False},
                {"key": "k2", "contact": "乙", "org": "乙公司 | Java", "resume": JAVA,
                 "approved": True, "verified": True, "detail_found": True,
                 "verdict": "pass", "recent_window": True, "sent": False},
            ], ensure_ascii=False), encoding="utf-8")
            args = argparse.Namespace(
                yes_i_reviewed=True, serial="TEST", dry_run=False,
                queue=str(queue_path), ledger=str(root / "ledger.jsonl"),
                evidence=str(root / "evidence"), timeout=0.1, auto_open=False,
                max_screens=45, followup_file=str(followup_path), no_humanize=False,
            )
            send_results = [
                {"send_confirmed": True, "sent_at": "t1", "resume": JAVA, "contact": "甲"},
                {"send_confirmed": True, "sent_at": "t2", "resume": JAVA, "contact": "乙",
                 "risk_signal": "verification required"},
            ]
            with mock.patch("chat_resume_dispatch.Adb"), \
                 mock.patch("chat_resume_dispatch.send_one", side_effect=send_results), \
                 mock.patch("chat_resume_dispatch.append_ledger"), \
                 mock.patch("chat_resume_dispatch.save_evidence", return_value="evidence.json"), \
                 mock.patch("chat_resume_dispatch.human_pause") as pause:
                with redirect_stdout(io.StringIO()):
                    code = cmd_send(args, CFG)
        self.assertEqual(code, 2)
        kinds = [call.args[0] for call in pause.call_args_list]
        self.assertEqual(kinds, ["between_candidates"])


class RunRestartInitializationTests(unittest.TestCase):
    """run must force-stop BOSS, relaunch it, and fail closed on login/risk."""

    @staticmethod
    def _doc(*texts):
        nodes = []
        for text in texts:
            nodes.append(
                "<node index='0' text='{}' content-desc='' resource-id='' "
                "class='android.widget.TextView' clickable='false' checked='false' "
                "selected='false' bounds='[0,0][1,1]'/>".format(text)
            )
        return (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            "<hierarchy rotation='0'>" + "".join(nodes) + "</hierarchy>"
        )

    class FakeAdb:
        def __init__(self, dumps):
            self._dumps = list(dumps)
            self.force_stopped = []
            self.launched = []
            self.keyevents = []
            self.taps = []
            self.dry_run = False

        def dump(self):
            return self._dumps.pop(0)

        def force_stop_app(self, package):
            self.force_stopped.append(package)

        def launch_app(self, package):
            self.launched.append(package)

        def keyevent(self, code):
            self.keyevents.append(code)

        def tap(self, x, y):
            self.taps.append((x, y))

    def test_run_restart_force_stops_then_relaunches_boss(self):
        adb = self.FakeAdb([self._doc("搜索联系人", "聊天", "全部")])
        with mock.patch("chat_resume_dispatch.time.sleep"):
            _restart_boss_for_scan(adb, humanize=False)
        self.assertEqual(adb.force_stopped, [BOSS_PKG])
        self.assertEqual(adb.launched, [BOSS_PKG])

    def test_run_navigation_recovers_from_jobs_tab_after_relaunch(self):
        jobs = self._doc("Golang", "Java", "职位", "发现", "消息", "我的")
        chat = (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            "<hierarchy rotation='0'>"
            "<node text='搜索联系人' content-desc='' resource-id='' class='' "
            "clickable='false' checked='false' selected='false' bounds='[0,0][1,1]'/>"
            "<node text='消息' content-desc='' resource-id='com.hpbr.bosszhipin:id/tv_tab_3' "
            "class='' clickable='true' checked='false' selected='false' bounds='[600,2100][760,2200]'/>"
            "<node text='全部' content-desc='' resource-id='' class='' "
            "clickable='true' checked='false' selected='false' bounds='[60,379][144,436]'/>"
            "</hierarchy>"
        )
        # 1 restart probe, 6 back-loop dumps, fallback re-dump, tab dump, all-tab dump.
        adb = self.FakeAdb([jobs] + [jobs] * 6 + [jobs, chat, chat])
        with mock.patch("chat_resume_dispatch.time.sleep"):
            _navigate_to_boss_all_tab(adb, max_screens=1, humanize=False)
        self.assertIn(BOSS_MSG_TAB, adb.taps)
        self.assertIn((102, 407), adb.taps)

    def test_run_restart_retries_transient_dump_failure_after_relaunch(self):
        class FlakyAdb(self.FakeAdb):
            def __init__(self, documents):
                super().__init__(documents)
                self.attempts = 0

            def dump(self):
                self.attempts += 1
                if self.attempts < 3:
                    raise DeviceError("adb failed (uiautomator not ready)")
                return super().dump()

        adb = FlakyAdb([self._doc("搜索联系人", "聊天", "全部")])
        with mock.patch("chat_resume_dispatch.time.sleep"):
            _restart_boss_for_scan(adb, humanize=False)
        self.assertEqual(adb.attempts, 3)

    def test_run_restart_still_raises_when_dump_keeps_failing(self):
        class BrokenAdb(self.FakeAdb):
            def __init__(self):
                super().__init__([])
                self.attempts = 0

            def dump(self):
                self.attempts += 1
                raise DeviceError("adb failed")

        adb = BrokenAdb()
        with mock.patch("chat_resume_dispatch.time.sleep"):
            with self.assertRaisesRegex(DeviceError, "adb failed"):
                _restart_boss_for_scan(adb, humanize=False)
        self.assertEqual(adb.attempts, 3)

    def test_run_restart_stops_on_login_screen(self):
        adb = self.FakeAdb([self._doc("其他方式登录", "一键登录", "微信登录")])
        with mock.patch("chat_resume_dispatch.time.sleep"):
            with self.assertRaisesRegex(DeviceError, "logged out"):
                _restart_boss_for_scan(adb, humanize=False)
        self.assertEqual(adb.force_stopped, [BOSS_PKG])
        self.assertEqual(adb.launched, [BOSS_PKG])

    def test_run_restart_stops_on_security_verification(self):
        adb = self.FakeAdb([self._doc("易盾验证码", "请完成安全验证")])
        with mock.patch("chat_resume_dispatch.time.sleep"):
            with self.assertRaises(RiskSignal):
                _restart_boss_for_scan(adb, humanize=False)


class ScanScreenConfigTests(unittest.TestCase):
    def test_config_defaults_to_five_screens(self):
        # User rule 2026-11-25: only the first five screens are scanned.
        self.assertEqual(resolve_scan_max_screens(None, {}), 5)
        self.assertEqual(resolve_scan_max_screens(None, {"scan": {"max_screens": 5}}), 5)
        self.assertEqual(CFG["scan"]["max_screens"], 5)

    def test_command_line_overrides_config(self):
        cfg = {"scan": {"max_screens": 5}}
        self.assertEqual(resolve_scan_max_screens(42, cfg), 42)

    def test_invalid_config_is_rejected(self):
        for value in (0, -1, "many", True):
            with self.subTest(value=value), self.assertRaises(DeviceError):
                resolve_scan_max_screens(None, {"scan": {"max_screens": value}})


class RunEntrypointTests(unittest.TestCase):
    def _args(self, out: Path, *, max_send: int = 0) -> argparse.Namespace:
        followup = Path(out).parent / "followup.txt"
        followup.write_text(FOLLOWUP_TEXT, encoding="utf-8")
        return argparse.Namespace(
            serial="TEST", dry_run=False, as_of="2026-11-25",
            captured_on="2026-11-24", days=7, max_screens=None,
            max_send=max_send, out_dir=str(out), timeout=1.0,
            followup_file=str(followup), no_humanize=True,
        )

    @staticmethod
    def _entry(key: str, contact: str) -> dict:
        return {
            "key": key, "contact": contact, "org": f"{contact}公司 | Java",
            "role": "Java", "snippet": "我想要一份你的简历",
            "resume": JAVA, "stack": "java", "verified": True,
            "detail_found": True, "verdict": "pass", "recent_window": True,
            "approved": False, "sent": False,
        }

    def test_run_wires_inline_sender_and_does_not_batch_send_after_scan(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "run"
            out.mkdir()
            (out / "details.jsonl").write_text(
                json.dumps({"contact": "甲", "org": "甲公司 | Java",
                            "list_snippet": "我想要一份你的简历", "verdict": "pass",
                            "key": "k1", "sent": True},
                           ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            args = self._args(out)
            included = [self._entry("k1", "甲")]
            inline_sender = mock.Mock(return_value={"send_confirmed": True})

            def scan_side_effect(*_args, **kwargs):
                kwargs["sender"](self._entry("k1", "甲"))
                return {"stage": "completed", "screens_scanned": 2,
                        "processed": 1, "sent": 1}

            with mock.patch("chat_resume_dispatch.Adb") as adb_cls, \
                 mock.patch("chat_resume_dispatch.make_inline_sender",
                            return_value=inline_sender) as sender_factory, \
                 mock.patch("chat_resume_dispatch.scan_all_boss_chats",
                            side_effect=scan_side_effect) as scan, \
                 mock.patch("chat_resume_dispatch.rescreen_evidence",
                            return_value=(included, [], {})) as rescreen, \
                 mock.patch("chat_resume_dispatch.load_list_times", return_value={}), \
                 mock.patch("chat_resume_dispatch.filter_recent_entries",
                            return_value=(included, [])), \
                 mock.patch("chat_resume_dispatch.cmd_send") as batch_send:
                with redirect_stdout(io.StringIO()):
                    code = cmd_run(args, CFG)
            self.assertEqual(code, 0)
            adb_cls.assert_called_once()
            scan.assert_called_once()
            self.assertIs(scan.call_args.kwargs["sender"], inline_sender)
            sender_factory.assert_called_once()
            inline_sender.assert_called_once()
            rescreen.assert_called_once()
            batch_send.assert_not_called()
            self.assertTrue((out / "run_queue.json").exists())
            self.assertTrue((out / "run_summary.json").exists())
            queued = json.loads((out / "run_queue.json").read_text(encoding="utf-8"))
            self.assertTrue(queued[0]["approved"])
            self.assertTrue(queued[0]["sent"])

    def test_run_does_not_send_when_scan_is_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "run"
            out.mkdir()
            args = self._args(out)
            with mock.patch("chat_resume_dispatch.Adb"), \
                 mock.patch("chat_resume_dispatch.make_inline_sender") as sender_factory, \
                 mock.patch("chat_resume_dispatch.scan_all_boss_chats",
                            return_value={"stage": "incomplete", "screens_scanned": 4,
                                          "processed": 7}), \
                 mock.patch("chat_resume_dispatch.rescreen_evidence") as rescreen, \
                 mock.patch("chat_resume_dispatch.cmd_send") as send:
                with redirect_stdout(io.StringIO()):
                    code = cmd_run(args, CFG)
            self.assertEqual(code, 1)
            sender_factory.assert_called_once()
            rescreen.assert_not_called()
            send.assert_not_called()
            summary = json.loads((out / "run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["stage"], "scan_incomplete")

    def test_run_treats_screen_limit_as_bounded_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "run"
            out.mkdir()
            (out / "details.jsonl").write_text("{}\n", encoding="utf-8")
            args = self._args(out)
            included = [self._entry("k1", "甲")]
            with mock.patch("chat_resume_dispatch.Adb"), \
                 mock.patch("chat_resume_dispatch.make_inline_sender") as sender_factory, \
                 mock.patch("chat_resume_dispatch.scan_all_boss_chats",
                            return_value={"stage": "incomplete", "screens_scanned": 5,
                                          "stop_reason": "screen_limit_or_stable",
                                          "processed": 1}), \
                 mock.patch("chat_resume_dispatch.rescreen_evidence",
                            return_value=(included, [], {})), \
                 mock.patch("chat_resume_dispatch.load_list_times", return_value={}), \
                 mock.patch("chat_resume_dispatch.filter_recent_entries",
                            return_value=(included, [])), \
                 mock.patch("chat_resume_dispatch.cmd_send") as send:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_run(args, CFG), 0)
            send.assert_not_called()
            summary = json.loads((out / "run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["coverage"], "screen_limit")

    def test_run_respects_max_send_limit(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "run"
            out.mkdir()
            (out / "details.jsonl").write_text("{}\n", encoding="utf-8")
            args = self._args(out, max_send=1)
            included = [self._entry("k1", "甲"), self._entry("k2", "乙")]

            def scan_side_effect(*_args, **kwargs):
                kwargs["sender"](included[0])
                with (out / "details.jsonl").open("a", encoding="utf-8") as sink:
                    sink.write(json.dumps({"key": "k1", "sent": True},
                                          ensure_ascii=False) + "\n")
                kwargs["sender"](included[1])
                return {"stage": "completed", "screens_scanned": 2, "processed": 2}

            with mock.patch("chat_resume_dispatch.Adb"), \
                 mock.patch("chat_resume_dispatch.send_one", side_effect=[
                     {"send_confirmed": True, "contact": "甲"},
                     {"send_confirmed": True, "contact": "乙"},
                 ]) as send_one_mock, \
                 mock.patch("chat_resume_dispatch.append_ledger") as ledger, \
                 mock.patch("chat_resume_dispatch.scan_all_boss_chats",
                            side_effect=scan_side_effect), \
                 mock.patch("chat_resume_dispatch.rescreen_evidence",
                            return_value=(included, [], {})), \
                 mock.patch("chat_resume_dispatch.load_list_times", return_value={}), \
                 mock.patch("chat_resume_dispatch.filter_recent_entries",
                            return_value=(included, [])):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_run(args, CFG), 0)
            send_one_mock.assert_called_once()
            ledger.assert_called_once()
            queued = json.loads((out / "run_queue.json").read_text(encoding="utf-8"))
            self.assertEqual([item["approved"] for item in queued], [True, False])

    def test_run_uses_configured_scan_limit_and_cli_override(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "run"
            out.mkdir()
            (out / "details.jsonl").write_text("{}\n", encoding="utf-8")
            args = self._args(out)
            included = [self._entry("k1", "甲")]
            cfg = dict(CFG)
            cfg["scan"] = {"max_screens": 15}
            with mock.patch("chat_resume_dispatch.Adb"), \
                 mock.patch("chat_resume_dispatch.make_inline_sender") as sender_factory, \
                 mock.patch("chat_resume_dispatch.scan_all_boss_chats",
                            return_value={"stage": "completed"}) as scan, \
                 mock.patch("chat_resume_dispatch.rescreen_evidence",
                            return_value=(included, [], {})), \
                 mock.patch("chat_resume_dispatch.load_list_times", return_value={}), \
                 mock.patch("chat_resume_dispatch.filter_recent_entries",
                            return_value=(included, [])), \
                 mock.patch("chat_resume_dispatch.cmd_send") as send:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_run(args, cfg), 0)
            self.assertEqual(scan.call_args.kwargs["max_screens"], 15)
            sender_factory.assert_called_once()
            send.assert_not_called()

            args.max_screens = 42
            with mock.patch("chat_resume_dispatch.Adb"), \
                 mock.patch("chat_resume_dispatch.make_inline_sender") as sender_factory, \
                 mock.patch("chat_resume_dispatch.scan_all_boss_chats",
                            return_value={"stage": "completed"}) as scan, \
                 mock.patch("chat_resume_dispatch.rescreen_evidence",
                            return_value=(included, [], {})), \
                 mock.patch("chat_resume_dispatch.load_list_times", return_value={}), \
                 mock.patch("chat_resume_dispatch.filter_recent_entries",
                            return_value=(included, [])), \
                 mock.patch("chat_resume_dispatch.cmd_send") as send:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_run(args, cfg), 0)
            self.assertEqual(scan.call_args.kwargs["max_screens"], 42)
            sender_factory.assert_called_once()
            send.assert_not_called()

    def test_bottom_anchor_is_detected(self):
        xml = (
            '<hierarchy><node text="以上是30天内的联系人" resource-id="" '
            'class="android.widget.TextView" package="" content-desc="" '
            'checkable="false" checked="false" clickable="false" enabled="true" '
            'focusable="false" focused="false" scrollable="false" '
            'long-clickable="false" password="false" selected="false" '
            'bounds="[0,0][1,1]" /></hierarchy>'
        )
        self.assertTrue(_at_thirty_day_bottom(parse_dump(xml)))

    def test_scan_records_identity_mismatch_and_continues(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "scan"
            out.mkdir()

            def node(text: str, rid: str = "", y: int = 100, x: int = 100) -> str:
                return (
                    f'<node text="{text}" resource-id="{rid}" '
                    'class="android.widget.TextView" package="com.hpbr.bosszhipin" '
                    'content-desc="" checkable="false" checked="false" '
                    'clickable="false" enabled="true" focusable="false" '
                    'focused="false" scrollable="false" long-clickable="false" '
                    'password="false" selected="false" '
                    f'bounds="[{x},{y}][{x + 100},{y + 40}]" />'
                )

            list_xml = "<hierarchy>" + "".join([
                node("搜索联系人", y=100),
                node("聊天", y=150),
                node("周女士", "com.hpbr.bosszhipin:id/tv_name", y=1000),
                node("猎户星 | 架构师", "com.hpbr.bosszhipin:id/tv_position", y=1050),
                node("方便发一份简历", "com.hpbr.bosszhipin:id/tv_msg", y=1100),
                node("11:52", "com.hpbr.bosszhipin:id/tv_time_v2", y=1100, x=800),
                node("以上是30天内的联系人", y=1200),
            ]) + "</hierarchy>"
            detail_xml = "<hierarchy>" + "".join([
                node("周女士", y=100),
                node("猎头顾问", y=150),
                node("某中型人工智能通用世界模型公司", y=200),
            ]) + "</hierarchy>"
            dumps = iter([
                list_xml,          # initial screen
                list_xml,          # row re-validation
                detail_xml,        # wrong org in detail header
                list_xml,          # back to list
                list_xml,          # bottom screen
            ])

            class ScanAdb:
                def dump(self) -> str:
                    return next(dumps)

                def tap(self, x: int, y: int) -> None:
                    pass

                def keyevent(self, code: int) -> None:
                    pass

                def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int) -> None:
                    pass

            with mock.patch("chat_resume_dispatch._navigate_to_boss_all_tab"), \
                 mock.patch("chat_resume_dispatch.rewind_boss_list"), \
                 mock.patch("chat_resume_dispatch.time.sleep"):
                status = scan_all_boss_chats(
                    ScanAdb(), CFG, out_dir=out, max_screens=2, humanize=False,
                )
            self.assertEqual(status["stage"], "completed")
            records = [json.loads(line) for line in
                       (out / "details.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["verdict"], "navigation_failed")
            self.assertEqual(records[0]["reasons"][0]["filter"], "identity")

    def test_scan_skips_row_that_disappears_before_tap(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "scan"
            out.mkdir()

            def node(text: str, rid: str = "", y: int = 100, x: int = 100) -> str:
                return (
                    f'<node text="{text}" resource-id="{rid}" '
                    'class="android.widget.TextView" package="com.hpbr.bosszhipin" '
                    'content-desc="" checkable="false" checked="false" '
                    'clickable="false" enabled="true" focusable="false" '
                    'focused="false" scrollable="false" long-clickable="false" '
                    'password="false" selected="false" '
                    f'bounds="[{x},{y}][{x + 100},{y + 40}]" />'
                )

            list_xml = "<hierarchy>" + "".join([
                node("搜索联系人", y=100),
                node("聊天", y=150),
                node("周女士", "com.hpbr.bosszhipin:id/tv_name", y=1000),
                node("猎户星 | 架构师", "com.hpbr.bosszhipin:id/tv_position", y=1050),
                node("方便发一份简历", "com.hpbr.bosszhipin:id/tv_msg", y=1100),
                node("11:52", "com.hpbr.bosszhipin:id/tv_time_v2", y=1100, x=800),
                node("以上是30天内的联系人", y=1200),
            ]) + "</hierarchy>"
            bottom_xml = "<hierarchy>" + "".join([
                node("搜索联系人", y=100),
                node("聊天", y=150),
                node("以上是30天内的联系人", y=1200),
            ]) + "</hierarchy>"
            dumps = iter([list_xml, bottom_xml])

            class ScanAdb:
                def dump(self) -> str:
                    return next(dumps)

                def tap(self, x: int, y: int) -> None:
                    pass

                def keyevent(self, code: int) -> None:
                    pass

                def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int) -> None:
                    pass

            with mock.patch("chat_resume_dispatch._navigate_to_boss_all_tab"), \
                 mock.patch("chat_resume_dispatch.rewind_boss_list"), \
                 mock.patch("chat_resume_dispatch.time.sleep"):
                status = scan_all_boss_chats(
                    ScanAdb(), CFG, out_dir=out, max_screens=1, humanize=False,
                )
            self.assertEqual(status["stage"], "completed")
            records = [json.loads(line) for line in
                       (out / "details.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["verdict"], "navigation_failed")
            self.assertEqual(records[0]["reasons"][0]["filter"], "navigation")

    def test_run_subcommand_is_registered(self):
        args = build_parser().parse_args([
            "run", "--out-dir", str(ROOT / "tmp-run"),
            "--as-of", "2026-11-25", "--captured-on", "2026-11-25",
        ])
        self.assertEqual(args.command, "run")
        self.assertEqual(args.days, 7)
        self.assertEqual(args.max_send, 0)
        self.assertIsNone(args.max_screens)


class InlineSendTests(unittest.TestCase):
    """run must send each eligible conversation while its detail page is open."""

    @staticmethod
    def _node(text: str, rid: str = "", y: int = 100, x: int = 100) -> str:
        return (
            f'<node text="{text}" resource-id="{rid}" '
            'class="android.widget.TextView" package="com.hpbr.bosszhipin" '
            'content-desc="" checkable="false" checked="false" clickable="false" '
            'enabled="true" focusable="false" focused="false" scrollable="false" '
            'long-clickable="false" password="false" selected="false" '
            f'bounds="[{x},{y}][{x + 100},{y + 40}]" />'
        )

    @classmethod
    def _list_xml(cls, rows: list[tuple[str, str, str, str]]) -> str:
        parts = [cls._node("搜索联系人", y=100), cls._node("聊天", y=150)]
        y = 1000
        for name, org, msg, time_label in rows:
            parts.extend([
                cls._node(name, "com.hpbr.bosszhipin:id/tv_name", y=y),
                cls._node(org, "com.hpbr.bosszhipin:id/tv_position", y=y + 50),
                cls._node(msg, "com.hpbr.bosszhipin:id/tv_msg", y=y + 100),
                cls._node(time_label, "com.hpbr.bosszhipin:id/tv_time_v2",
                          y=y + 100, x=800),
            ])
            y += 300
        return "<hierarchy>" + "".join(parts) + "</hierarchy>"

    @classmethod
    def _detail_xml(cls, name: str, org: str, msg: str) -> str:
        return "<hierarchy>" + "".join([
            cls._node(name, y=100),
            cls._node(org, y=150),
            cls._node(msg, y=200),
        ]) + "</hierarchy>"

    @staticmethod
    def _scan_adb(dumps):
        queue = iter(dumps)

        class ScanAdb:
            def dump(self) -> str:
                return next(queue)

            def tap(self, x: int, y: int) -> None:
                pass

            def keyevent(self, code: int) -> None:
                pass

            def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int) -> None:
                pass

        return ScanAdb()

    def test_scan_sends_each_eligible_row_and_skips_stale_rows(self):
        recent_rows = [
            ("甲先生", "甲公司 | Java", "方便发一份简历吗", "昨天 10:22"),
            ("乙女士", "乙公司 | Golang", "方便发一份简历吗", "昨天 10:23"),
        ]
        old_rows = [("丙先生", "丙公司 | Java", "方便发一份简历吗", "11月10日")]
        list_xml = self._list_xml(recent_rows)
        old_xml = self._list_xml(old_rows)
        detail1 = self._detail_xml(*recent_rows[0][:3])
        detail2 = self._detail_xml(*recent_rows[1][:3])
        detail3 = self._detail_xml(*old_rows[0][:3])
        adb = self._scan_adb([
            list_xml, list_xml, detail1, list_xml,
            list_xml, detail2, list_xml,
            old_xml, old_xml, detail3, old_xml,
        ])
        calls = []

        def sender(item: dict) -> dict:
            calls.append(item["key"])
            return {"send_confirmed": True, "contact": item["contact"]}

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "scan"
            with mock.patch("chat_resume_dispatch._navigate_to_boss_all_tab"), \
                 mock.patch("chat_resume_dispatch.rewind_boss_list"), \
                 mock.patch("chat_resume_dispatch.time.sleep"):
                status = scan_all_boss_chats(
                    adb, CFG, out_dir=out, max_screens=3, humanize=False,
                    window_cutoff=date(2026, 11, 19),
                    captured_on=date(2026, 11, 24), sender=sender,
                )
            records = [json.loads(line) for line in
                       (out / "details.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(status["stage"], "completed_window")
        self.assertEqual(calls, [
            _inline_send_key("甲先生", "甲公司 | Java", "方便发一份简历吗"),
            _inline_send_key("乙女士", "乙公司 | Golang", "方便发一份简历吗"),
        ])
        self.assertEqual([record["sent"] for record in records], [True, True, False])
        self.assertEqual(records[2]["send_skipped_reason"], "outside_recent_window")

    def test_scan_retries_back_after_inline_send_before_failing(self):
        row = ("甲先生", "甲公司 | Java", "方便发一份简历吗", "昨天 10:22")
        list_xml = self._list_xml([row])
        detail = self._detail_xml(*row[:3])
        sends = []

        class RecordingAdb:
            def __init__(self):
                self.dumps = iter([list_xml, list_xml, detail,
                                   detail, list_xml])
                self.back_count = 0

            def dump(self) -> str:
                return next(self.dumps)

            def tap(self, x: int, y: int) -> None:
                pass

            def keyevent(self, code: int) -> None:
                self.back_count += 1

            def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int) -> None:
                pass

        adb = RecordingAdb()
        with tempfile.TemporaryDirectory() as td:
            with mock.patch("chat_resume_dispatch._navigate_to_boss_all_tab"), \
                 mock.patch("chat_resume_dispatch.rewind_boss_list"), \
                 mock.patch("chat_resume_dispatch.time.sleep"):
                status = scan_all_boss_chats(
                    adb, CFG, out_dir=Path(td), max_screens=1, humanize=False,
                    window_cutoff=date(2026, 11, 19),
                    captured_on=date(2026, 11, 24),
                    sender=lambda item: sends.append(item["key"]) or {
                        "send_confirmed": True,
                    },
                )
        self.assertEqual(len(sends), 1)
        self.assertEqual(adb.back_count, 2)
        self.assertEqual(status["processed"], 1)

    def test_scan_stops_when_followup_reports_a_risk_signal(self):
        list_xml = self._list_xml([
            ("甲先生", "甲公司 | Java", "方便发一份简历吗", "昨天 10:22"),
        ])
        detail = self._detail_xml("甲先生", "甲公司 | Java", "方便发一份简历吗")
        adb = self._scan_adb([list_xml, list_xml, detail, list_xml])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "scan"
            with mock.patch("chat_resume_dispatch._navigate_to_boss_all_tab"), \
                 mock.patch("chat_resume_dispatch.rewind_boss_list"), \
                 mock.patch("chat_resume_dispatch.time.sleep"):
                with self.assertRaises(RiskSignal):
                    scan_all_boss_chats(
                        adb, CFG, out_dir=out, max_screens=2, humanize=False,
                        window_cutoff=date(2026, 11, 19),
                        captured_on=date(2026, 11, 24),
                        sender=lambda item: {"send_confirmed": True,
                                             "risk_signal": "verification required"},
                    )
            records = [json.loads(line) for line in
                       (out / "details.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["sent"])
        self.assertEqual(
            records[0]["key"],
            _inline_send_key("甲先生", "甲公司 | Java", "方便发一份简历吗"),
        )

    def test_scan_does_not_send_when_recent_window_is_unreadable(self):
        no_time = self._list_xml([
            ("甲先生", "甲公司 | Java", "方便发一份简历吗", ""),
        ])
        detail = self._detail_xml("甲先生", "甲公司 | Java", "方便发一份简历吗")
        adb = self._scan_adb([no_time, no_time, detail, no_time, no_time])
        sender = mock.Mock(return_value={"send_confirmed": True})
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "scan"
            with mock.patch("chat_resume_dispatch._navigate_to_boss_all_tab"), \
                 mock.patch("chat_resume_dispatch.rewind_boss_list"), \
                 mock.patch("chat_resume_dispatch.time.sleep"):
                scan_all_boss_chats(
                    adb, CFG, out_dir=out, max_screens=2, humanize=False,
                    window_cutoff=date(2026, 11, 19),
                    captured_on=date(2026, 11, 24), sender=sender,
                )
            records = [json.loads(line) for line in
                       (out / "details.jsonl").read_text(encoding="utf-8").splitlines()]
        sender.assert_not_called()
        self.assertFalse(records[0]["sent"])
        self.assertFalse(records[0]["send_attempted"])
        self.assertEqual(records[0]["send_skipped_reason"], "outside_recent_window")

    def test_inline_sender_enforces_quota_and_writes_audit_ledger(self):
        item = {"key": "k1", "contact": "甲", "resume": JAVA, "sent": False}
        ledger_path = Path("unused-ledger.jsonl")
        sender = make_inline_sender(
            object(), evidence_dir=Path("unused"), ledger_path=ledger_path,
            timeout=0.1, followup_text=FOLLOWUP_TEXT, humanize=False, max_send=1,
        )
        with mock.patch("chat_resume_dispatch.send_one", return_value={
            "key": "k1", "send_confirmed": True,
        }) as send_one_mock, \
             mock.patch("chat_resume_dispatch.append_ledger") as append:
            first = sender(dict(item))
            second = sender(dict(item))
        self.assertTrue(first["send_confirmed"])
        self.assertIsNone(second)
        send_one_mock.assert_called_once()
        append.assert_called_once()


class WindowStopTests(unittest.TestCase):
    """The 30-day bottom text is unreachable on long lists, so the scan may stop
    once a whole screen is provably older than the review window."""

    @staticmethod
    def _node(text: str, rid: str = "", y: int = 100, x: int = 100) -> str:
        return (
            f'<node text="{text}" resource-id="{rid}" '
            'class="android.widget.TextView" package="com.hpbr.bosszhipin" '
            'content-desc="" checkable="false" checked="false" '
            'clickable="false" enabled="true" focusable="false" '
            'focused="false" scrollable="false" long-clickable="false" '
            'password="false" selected="false" '
            f'bounds="[{x},{y}][{x + 100},{y + 40}]" />'
        )

    @classmethod
    def _list_xml(cls, name: str, org: str, msg: str, time_label: str) -> str:
        return "<hierarchy>" + "".join([
            cls._node("搜索联系人", y=100),
            cls._node("聊天", y=150),
            cls._node(name, "com.hpbr.bosszhipin:id/tv_name", y=1000),
            cls._node(org, "com.hpbr.bosszhipin:id/tv_position", y=1050),
            cls._node(msg, "com.hpbr.bosszhipin:id/tv_msg", y=1100),
            cls._node(time_label, "com.hpbr.bosszhipin:id/tv_time_v2", y=1100, x=800),
        ]) + "</hierarchy>"

    @classmethod
    def _detail_xml(cls, name: str, org: str, msg: str) -> str:
        return "<hierarchy>" + "".join([
            cls._node(name, y=100),
            cls._node(org, y=150),
            cls._node(msg, y=200),
        ]) + "</hierarchy>"

    @staticmethod
    def _scan_adb(dumps):
        queue = iter(dumps)

        class ScanAdb:
            def dump(self) -> str:
                return next(queue)

            def tap(self, x: int, y: int) -> None:
                pass

            def keyevent(self, code: int) -> None:
                pass

            def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int) -> None:
                pass

        return ScanAdb()

    def test_scan_stops_at_window_boundary_without_30_day_bottom(self):
        old_list = self._list_xml("甲先生", "甲公司 | Java", "方便发一份简历吗", "11月10日")
        detail = self._detail_xml("甲先生", "甲公司 | Java", "方便发一份简历吗")
        adb = self._scan_adb([old_list, old_list, detail, old_list])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "scan"
            with mock.patch("chat_resume_dispatch._navigate_to_boss_all_tab"), \
                 mock.patch("chat_resume_dispatch.rewind_boss_list"), \
                 mock.patch("chat_resume_dispatch.time.sleep"):
                status = scan_all_boss_chats(
                    adb, CFG, out_dir=out, max_screens=10, humanize=False,
                    window_cutoff=date(2026, 11, 19), captured_on=date(2026, 11, 24),
                )
        self.assertEqual(status["stage"], "completed_window")
        self.assertEqual(status["stop_reason"], "window")
        self.assertEqual(status["screens_scanned"], 1)

    def test_scan_keeps_scanning_while_a_screen_has_recent_rows(self):
        recent_list = self._list_xml("乙女士", "乙公司 | Golang", "发一份简历", "昨天 10:22")
        recent_detail = self._detail_xml("乙女士", "乙公司 | Golang", "发一份简历")
        old_list = self._list_xml("甲先生", "甲公司 | Java", "方便发一份简历吗", "11月10日")
        old_detail = self._detail_xml("甲先生", "甲公司 | Java", "方便发一份简历吗")
        adb = self._scan_adb([
            recent_list, recent_list, recent_detail, recent_list,  # screen 0: recent
            old_list, old_list, old_detail, old_list,              # screen 1: old
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "scan"
            with mock.patch("chat_resume_dispatch._navigate_to_boss_all_tab"), \
                 mock.patch("chat_resume_dispatch.rewind_boss_list"), \
                 mock.patch("chat_resume_dispatch.time.sleep"):
                status = scan_all_boss_chats(
                    adb, CFG, out_dir=out, max_screens=10, humanize=False,
                    window_cutoff=date(2026, 11, 19), captured_on=date(2026, 11, 24),
                )
        self.assertEqual(status["stage"], "completed_window")
        self.assertEqual(status["screens_scanned"], 2)

    def test_scan_does_not_stop_when_list_time_is_unreadable(self):
        no_time = "<hierarchy>" + "".join([
            self._node("搜索联系人", y=100),
            self._node("聊天", y=150),
            self._node("甲先生", "com.hpbr.bosszhipin:id/tv_name", y=1000),
            self._node("甲公司 | Java", "com.hpbr.bosszhipin:id/tv_position", y=1050),
            self._node("方便发一份简历吗", "com.hpbr.bosszhipin:id/tv_msg", y=1100),
        ]) + "</hierarchy>"
        detail = self._detail_xml("甲先生", "甲公司 | Java", "方便发一份简历吗")
        adb = self._scan_adb([
            no_time, no_time, detail, no_time,
            no_time, no_time, no_time, no_time,
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "scan"
            with mock.patch("chat_resume_dispatch._navigate_to_boss_all_tab"), \
                 mock.patch("chat_resume_dispatch.rewind_boss_list"), \
                 mock.patch("chat_resume_dispatch.time.sleep"):
                status = scan_all_boss_chats(
                    adb, CFG, out_dir=out, max_screens=4, humanize=False,
                    window_cutoff=date(2026, 11, 19), captured_on=date(2026, 11, 24),
                )
        self.assertEqual(status["stage"], "incomplete")
        self.assertEqual(status["stop_reason"], "screen_limit_or_stable")

    def test_run_sends_when_scan_completed_by_window(self):
        candidate = {
            "contact": "甲先生", "org": "甲公司 | Java", "role": "Java",
            "list_snippet": "方便发一份简历吗", "verdict": "pass", "reasons": [],
            "key": "k1", "stack": "java", "resume": "JAVA-RESUME-NAME",
            "approved": False, "sent": False,
        }
        inline_sender = mock.Mock(return_value={"send_confirmed": True})

        def scan_side_effect(*_args, **kwargs):
            kwargs["sender"](candidate)
            with (out / "details.jsonl").open("a", encoding="utf-8") as sink:
                sink.write(json.dumps({"key": "k1", "sent": True},
                                      ensure_ascii=False) + "\n")
            return {"stage": "completed_window", "stop_reason": "window", "sent": 1}

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "run"
            out.mkdir(parents=True, exist_ok=True)
            (out / "details.jsonl").write_text("{}\n", encoding="utf-8")
            args = mock.Mock(
                out_dir=str(out), serial=None, dry_run=True, as_of="2026-11-25",
                captured_on="2026-11-25", days=7, max_screens=None, max_send=0,
                followup_file=str(ROOT / "documents" / "dispatch" / "followup_message.txt"),
                timeout=4.0, no_humanize=True,
            )
            with mock.patch("chat_resume_dispatch.Adb"), \
                 mock.patch("chat_resume_dispatch.make_inline_sender",
                            return_value=inline_sender), \
                 mock.patch("chat_resume_dispatch.scan_all_boss_chats",
                            side_effect=scan_side_effect), \
                 mock.patch("chat_resume_dispatch.rescreen_evidence",
                            return_value=([candidate], [], {})), \
                 mock.patch("chat_resume_dispatch.load_list_times", return_value={}), \
                 mock.patch("chat_resume_dispatch.filter_recent_entries",
                            return_value=([candidate], [])), \
                 mock.patch("chat_resume_dispatch.cmd_send") as send:
                with redirect_stdout(io.StringIO()):
                    code = cmd_run(args, CFG)
            self.assertEqual(code, 0)
            inline_sender.assert_called_once()
            send.assert_not_called()
            queued = json.loads((out / "run_queue.json").read_text(encoding="utf-8"))
            self.assertTrue(queued[0]["approved"])
            self.assertTrue(queued[0]["sent"])


class FollowUpReliabilityTests(unittest.TestCase):
    """Transient follow-up failures retry; terminal risks do not."""

    class _FlakyAdb(FollowUpMessageTests.FakeAdb):
        def __init__(self, dumps, *, failures_before_success=1):
            super().__init__(dumps)
            self.failures_before_success = failures_before_success
            self.input_b64_calls = 0

        def input_b64(self, text):
            self.input_b64_calls += 1
            if self.input_b64_calls <= self.failures_before_success:
                # Simulate a transient ADBKeyboard broadcast failure. A silent
                # no-op would look identical to a successful broadcast to the
                # real Adb wrapper, so the retry path must see an error.
                raise DeviceError("simulated ADBKeyboard broadcast failure")
            super().input_b64(text)

    def test_transient_followup_failure_is_retried(self):
        item = FollowUpMessageTests()._item()
        ready = FollowUpMessageTests._doc(
            FollowUpMessageTests._node(text="甲"),
            FollowUpMessageTests._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                       "android.widget.EditText", "和Ta聊一聊~",
                                       bounds="[147,2150][825,2208]"),
        )
        typed = FollowUpMessageTests._doc(
            FollowUpMessageTests._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                       "android.widget.EditText", FOLLOWUP_TEXT,
                                       bounds="[147,2150][825,2208]"),
            FollowUpMessageTests._node(text="发送", clickable=True,
                                       bounds="[948,2148][1032,2208]"),
        )
        sent = FollowUpMessageTests._doc(
            FollowUpMessageTests._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                       "android.widget.EditText", "和Ta聊一聊~",
                                       bounds="[147,2150][825,2208]"),
            FollowUpMessageTests._node(text=FOLLOWUP_TEXT),
        )
        # Two attempts: first never gets text into the box, second succeeds.
        dumps = [ready, ready, ready, typed, typed, sent]
        adb = self._FlakyAdb(dumps, failures_before_success=1)
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_followup(adb, FOLLOWUP_TEXT, Path("."), 0.1)
        self.assertTrue(result["followup_confirmed"])
        self.assertEqual(result["followup_attempts"], 2)

    def test_exhausted_followup_retries_are_recorded_as_pending(self):
        ready = FollowUpMessageTests._doc(
            FollowUpMessageTests._node(text="甲"),
            FollowUpMessageTests._node(text="请求中"),
            FollowUpMessageTests._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                       "android.widget.EditText", "和Ta聊一聊~",
                                       bounds="[147,2150][825,2208]"),
        )
        adb = FollowUpMessageTests.FakeAdb([ready] * 12)
        with mock.patch("chat_resume_dispatch.time.sleep"):
            result = send_one(adb, {"key": "k2", "contact": "甲", "resume": GO,
                                    "resume_already_sent": True,
                                    "resume_sent_at": "2026-11-25T22:00:00"},
                              Path("."), 0.05, followup_text=FOLLOWUP_TEXT)
        self.assertFalse(result["followup_confirmed"])
        self.assertTrue(result["followup_pending"])
        self.assertEqual(result["followup_attempts"], 3)
        self.assertIn("follow-up", result["followup_error"])

    def test_risk_signal_stops_without_retrying_followup(self):
        ready = FollowUpMessageTests._doc(
            FollowUpMessageTests._node(text="验证码"),
            FollowUpMessageTests._node("com.hpbr.bosszhipin:id/editText_with_scrollbar",
                                       "android.widget.EditText", "和Ta聊一聊~",
                                       bounds="[147,2150][825,2208]"),
        )
        adb = FollowUpMessageTests.FakeAdb([ready] * 5)
        with mock.patch("chat_resume_dispatch.time.sleep"):
            with self.assertRaises(RiskSignal):
                send_followup(adb, FOLLOWUP_TEXT, Path("."), 0.1)
        # The risk page is consumed once; a retry would ask for another dump.
        self.assertEqual(len(adb.inputs), 0)

    def test_followup_recovery_only_sends_the_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            ledger = tmp / "ledger.jsonl"
            ledger.write_text(json.dumps({
                "stage": "send", "key": "k3", "contact": "甲",
                "org": "甲公司 | Java", "resume": GO,
                "send_confirmed": True, "followup_confirmed": False,
                "followup_pending": True, "sent_at": "2026-11-25T22:00:00",
            }) + "\n", encoding="utf-8")
            args = argparse.Namespace(
                ledger=str(ledger), queue=str(tmp / "queue.json"),
                evidence=str(tmp / "evidence"), followup_file=str(DEFAULT_FOLLOWUP_FILE),
                timeout=0.1, max_screens=5, dry_run=False, yes_i_reviewed=True,
            )
            adb = mock.MagicMock()
            item = {"key": "k3", "contact": "甲", "org": "甲公司 | Java",
                    "resume": GO, "resume_already_sent": True,
                    "resume_sent_at": "2026-11-25T22:00:00"}
            with mock.patch("chat_resume_dispatch.Adb", return_value=adb), \
                 mock.patch("chat_resume_dispatch.open_boss_chat",
                            return_value={"found": True}), \
                 mock.patch("chat_resume_dispatch.send_one",
                            return_value={"followup_confirmed": True,
                                          "followup_sent": True}) as send:
                with redirect_stdout(io.StringIO()):
                    code = cmd_followup(args, CFG)
            self.assertEqual(code, 0)
            send.assert_called_once()
            passed = send.call_args.args[1]
            self.assertTrue(passed["resume_already_sent"])
            self.assertNotIn("发简历", passed)


if __name__ == "__main__":
    unittest.main()
