#!/usr/bin/env python3
"""Chat-list resume dispatch — controlled, human-approved auto-send on an
Android device (BOSS / Liepin chat), driven by uiautomator UI trees.

Stages, deliberately separated:

    list    read-only. Dump the current UI tree (the app must already be on the
            chat-list page), group BOSS tv_name/tv_position/tv_msg fields into
            rows, run the four filters, and write a review queue with every
            item approved=false. Liepin self-drawn lists use --from-vision.
    verify  read-only on the device. Launch BOSS, rewind the chat list to the
            top, scroll, open each queued candidate's conversation, and re-run
            the four filters and the stack ladder on the FULL detail text —
            list snippets are truncated and hide signals (an outsourcing
            identity, a non-local city) that only appear inside the chat.
            Verdict + evidence go back into the queue; 发简历 is never touched.
    rescreen read-only. Re-run the current filters over a saved per-conversation
            JSONL evidence file (detail pages already opened), because rules can
            change after a long scan. Writes a fresh review queue; all approvals
            are reset so stale approvals cannot survive a rule change.
    recent  read-only. Keep only conversations whose list timestamp falls in a
            bounded recent window (default: 7 calendar days ending today) before
            review. The BOSS list uses labels relative to the capture date, so
            relative weekday/昨天 labels are resolved against --captured-on.
            Missing or ambiguous timestamps fail closed and are excluded.
    run     single scheduled-task entry point. Before scanning, it force-stops
            and relaunches BOSS, checks for login/risk pages, and only then opens
            the BOSS 全部 tab. It scans chat by chat, rescreens with the current
            rules, applies the recent window, auto-approves the passing items
            (explicitly authorised by the user for scheduled runs), then calls
            send. A scan that never sees the explicit 30-day bottom, a risk
            signal, or any device error stops the whole run before sending.
    review  human only for the separate list/verify/rescreen/recent stages: the
            user edits queue.json and sets approved=true on the exact items to
            send. This gate cannot be automated away; `run` is the deliberate
            exception authorised for unattended scheduled execution.
    send    writes to the device. Only items with approved=true, a verified
            detail page and a passing verdict are processed; each is checked
            against the on-screen contact name, the exact resume version is
            chosen in the picker, and the send is confirmed by a UI-tree signal.
            After the resume is confirmed, the configured follow-up message is
            typed through ADBKeyboard and sent; its failure is recorded but the
            resume stays marked sent to avoid a duplicate. A risk signal stops
            the whole run immediately and leaves screenshot + UI dump in
            evidence/.

No screenshot OCR: BOSS uses the UI tree, which carries the full text and is
more reliable; Liepin self-drawn lists are transcribed via --from-vision by an
agent/human. Screenshots are also taken as risk evidence.

Deliberate interaction pauses (navigation, picker, typing, between candidates)
are randomised by default; pass --no-humanize only for deterministic tests or
troubleshooting. Poll/confirmation loops keep their short fixed sleeps, and a
risk signal stops immediately without any extra pause.

Run from repo root:
    python tools/chat_resume_dispatch.py list
    python tools/chat_resume_dispatch.py verify --limit 3
    python tools/chat_resume_dispatch.py send --yes-i-reviewed
    python tools/chat_resume_dispatch.py --dump sample.xml list --out q.json

Stdlib only. Never hardcodes a device serial or a personal path.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

from chat_resume_ladder import (  # noqa: E402
    infer_stack, is_explicit_request, is_resume_request, load_config,
    load_names, pick_resume, screen_candidate,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE = ROOT / "documents" / "dispatch" / "queue.json"
DEFAULT_LEDGER = ROOT / "documents" / "dispatch" / "ledger.jsonl"
DEFAULT_EVIDENCE = ROOT / "documents" / "dispatch" / "evidence"
DEFAULT_FOLLOWUP_FILE = ROOT / "documents" / "dispatch" / "followup_message.txt"

SEND_FLAG = "--yes-i-reviewed"

# Deliberate interaction pauses are randomised so the device flow does not look
# like a machine gun. Poll/confirmation loops keep their short fixed sleeps;
# only human-visible navigation and decision points are humanised.
HUMANIZE_RANGES: dict[str, tuple[float, float]] = {
    "navigation": (0.6, 2.2),
    "launch": (1.4, 2.8),
    "back": (0.5, 1.1),
    "tab": (0.9, 1.8),
    "open": (1.1, 2.2),
    "swipe": (0.6, 1.3),
    "ime": (0.2, 0.6),
    "picker": (0.8, 2.0),
    "select": (0.7, 1.6),
    "send": (1.0, 3.0),
    "resume_to_followup": (2.0, 5.0),
    "between_candidates": (8.0, 20.0),
}


def human_pause(kind: str, *, enabled: bool = True,
                rng: random.Random | None = None) -> float:
    """Sleep for a bounded, deliberately random pause; return the delay.

    ``enabled=False`` is for deterministic tests/troubleshooting and performs
    no sleep. ``rng`` is injectable so tests can pin the sampled value.
    """
    if not enabled:
        return 0.0
    low, high = HUMANIZE_RANGES[kind]
    delay = (rng or random).uniform(low, high)
    time.sleep(delay)
    return delay

# ADBKeyboard is used only for the follow-up message: the built-in Android
# `input text` cannot type Chinese. Keep the keyboard install/IME switch local
# and restore the user's original IME in a finally block.
ADBKEYBOARD_PACKAGE = "com.android.adbkeyboard"
ADBKEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
ADBKEYBOARD_APK_URL = (
    "https://gh-proxy.com/https://github.com/senzhk/ADBKeyBoard/raw/master/ADBKeyboard.apk"
)
ADBKEYBOARD_INPUT_ACTION = "ADB_INPUT_B64"
BOSS_CHAT_INPUT_ID = "com.hpbr.bosszhipin:id/editText_with_scrollbar"

# Device navigation anchors for the verify stage (measured at 1080x2280).
# monkey only brings the app to the foreground and resumes its last screen,
# which may be a chat room — hence the back-out loop after launch.
BOSS_PKG = "com.hpbr.bosszhipin"
LIEPIN_PKG = "com.lietou.mishu"  # chat list is self-drawn: not verify-able yet
BOSS_MSG_TAB = (680, 2185)
BACK_KEY = 4
LAUNCH_SETTLE = 2.2
BACK_SETTLE = 0.6
TAB_SETTLE = 1.3
OPEN_SETTLE = 1.8
SWIPE_SETTLE = 0.7

# Risk signals: any of these in a UI tree means stop now, do not retry.
# Error codes must carry explicit error context. A bare `37` also matches chat
# timestamps like `18:37` or counts like `共 37 条`, which caused a false stop.
RISK_PATTERNS = [
    r"验证码",
    r"安全验证",
    r"滑动验证",
    r"人机校验",
    r"请完成验证",
    r"操作频繁",
    r"访问过于频繁",
    r"账号异常",
    r"(?:错误码|错误代码|错误编号|异常码|错误|异常|(?i:code))\s*[:：]?\s*(?:37|403|429|60001)\b",
]

TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
BOSS_ROW_FIELDS = ("tv_name", "tv_position", "tv_msg", "tv_time_v2")
# BOSS rows put name/position/message/time in separate nodes within ~80px;
# the next row starts ~228px below. Any larger gap starts a new row.
BOSS_ROW_Y_TOLERANCE = 120
_ZW = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)


class RiskSignal(RuntimeError):
    """A platform risk-control / human-verification signal was observed."""


class DeviceError(RuntimeError):
    """ADB failure, missing device, or an unexpected UI structure."""


def norm(value: str | None) -> str:
    """Strip zero-width chars seen in some App WebViews, then trim."""
    return (value or "").translate(_ZW).strip()


@dataclass
class Node:
    text: str
    desc: str
    cls: str
    resource_id: str
    clickable: bool
    checked: bool
    selected: bool
    bounds: tuple[int, int, int, int]

    @property
    def label(self) -> str:
        return self.desc or self.text

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def parse_dump(xml_text: str) -> list[Node]:
    """Parse a uiautomator XML dump into Node objects (stdlib only)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise DeviceError(f"invalid UI dump XML: {exc}") from exc

    nodes: list[Node] = []
    for element in root.iter("node"):
        bounds_match = _BOUNDS_RE.match(element.get("bounds", ""))
        bounds = (
            tuple(int(v) for v in bounds_match.groups())  # type: ignore[assignment]
            if bounds_match
            else (0, 0, 0, 0)
        )
        nodes.append(
            Node(
                text=norm(element.get("text")),
                desc=norm(element.get("content-desc")),
                cls=element.get("class", ""),
                resource_id=element.get("resource-id", ""),
                clickable=element.get("clickable") == "true",
                checked=element.get("checked") == "true",
                selected=element.get("selected") == "true",
                bounds=bounds,  # type: ignore[arg-type]
            )
        )
    return nodes


def find_nodes(
    nodes: list[Node],
    *,
    contains: str | None = None,
    exact: str | None = None,
    clickable: bool | None = None,
) -> list[Node]:
    out: list[Node] = []
    for node in nodes:
        label = node.label
        if contains is not None and contains not in label:
            continue
        if exact is not None and label != exact:
            continue
        if clickable is not None and node.clickable != clickable:
            continue
        out.append(node)
    return out


def sentinel_check(nodes: list[Node]) -> None:
    """Raise RiskSignal on any verification / rate-limit / error-code signal."""
    compiled = [re.compile(p) for p in RISK_PATTERNS]
    for node in nodes:
        for pattern in compiled:
            if pattern.search(node.label):
                raise RiskSignal(f"risk signal {pattern.pattern!r} in UI: {node.label[:120]!r}")


class Adb:
    """Thin, injectable subprocess wrapper. No state, no serial hardcoding."""

    def __init__(self, serial: str | None = None, dry_run: bool = False):
        self.serial = serial
        self.dry_run = dry_run
        self._prefix = ["adb"]
        if serial:
            self._prefix += ["-s", serial]

    def _run(self, args: list[str], *, check: bool = True) -> str:
        cmd = self._prefix + args
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if check and proc.returncode != 0:
            raise DeviceError(f"adb failed ({' '.join(cmd)}): {proc.stderr.strip()}")
        return proc.stdout

    @staticmethod
    def online_serials() -> list[str]:
        proc = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        return [
            line.split("\t", 1)[0]
            for line in proc.stdout.splitlines()
            if "\tdevice" in line
        ]

    def resolve_serial(self) -> str:
        if self.serial:
            return self.serial
        serials = self.online_serials()
        if not serials:
            raise DeviceError("no online adb device; connect the phone and retry")
        if len(serials) > 1:
            raise DeviceError(f"multiple devices online {serials}; pass --serial")
        self.serial = serials[0]
        self._prefix = ["adb", "-s", self.serial]
        return self.serial

    def dump(self) -> str:
        remote = "/sdcard/dsh_dispatch_window.xml"
        self._run(["shell", "uiautomator", "dump", remote])
        return self._run(["shell", "cat", remote])

    def tap(self, x: int, y: int) -> None:
        if self.dry_run:
            print(f"[dry-run] tap {x},{y}")
            return
        self._run(["shell", "input", "tap", str(x), str(y)])

    def keyevent(self, code: int) -> None:
        if self.dry_run:
            print(f"[dry-run] keyevent {code}")
            return
        self._run(["shell", "input", "keyevent", str(code)])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int) -> None:
        if self.dry_run:
            print(f"[dry-run] swipe {x1},{y1} -> {x2},{y2} ({ms}ms)")
            return
        self._run(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms)])

    def launch_app(self, package: str) -> None:
        """Bring an app to the foreground (monkey resumes its last screen)."""
        if self.dry_run:
            print(f"[dry-run] launch {package}")
            return
        self._run([
            "shell", "monkey", "-p", package,
            "-c", "android.intent.category.LAUNCHER", "1",
        ])

    def force_stop_app(self, package: str) -> None:
        """Kill an app before a fresh launch; used only by the run scan entry."""
        if self.dry_run:
            print(f"[dry-run] force-stop {package}")
            return
        self._run(["shell", "am", "force-stop", package])

    def screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        remote = "/sdcard/dsh_dispatch_evidence.png"
        self._run(["shell", "screencap", "-p", remote])
        proc = subprocess.run(
            self._prefix + ["pull", remote, str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            raise DeviceError(f"adb pull screenshot failed: {proc.stderr.strip()}")

    def save_dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dump(), encoding="utf-8")

    def current_ime(self) -> str:
        """Return the active IME, or 'null' when the device reports none."""
        if self.dry_run:
            return "com.example.ime"
        return self._run([
            "shell", "settings", "get", "secure", "default_input_method",
        ], check=False).strip()

    def is_package_installed(self, package: str) -> bool:
        """True when `adb shell pm list packages <package>` reports an exact hit."""
        if self.dry_run:
            return True
        out = self._run(["shell", "pm", "list", "packages", package], check=False)
        return any(line.strip() == f"package:{package}" for line in out.splitlines())

    def install_apk(self, path: Path) -> None:
        if self.dry_run:
            print(f"[dry-run] install {path}")
            return
        self._run(["install", "-r", str(path)])

    def enable_ime(self, ime: str) -> None:
        if self.dry_run:
            print(f"[dry-run] ime enable {ime}")
            return
        self._run(["shell", "ime", "enable", ime], check=False)

    def set_ime(self, ime: str) -> None:
        if self.dry_run:
            print(f"[dry-run] ime set {ime}")
            return
        self._run(["shell", "ime", "set", ime])

    def input_b64(self, text: str) -> None:
        """Type UTF-8 text through the ADBKeyboard broadcast interface."""
        if self.dry_run:
            print(f"[dry-run] input_b64 {text[:60]!r}")
            return
        payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
        self._run([
            "shell", "am", "broadcast", "-a", ADBKEYBOARD_INPUT_ACTION,
            "--es", "msg", payload,
        ])


# ---------------------------------------------------------------------------
# list stage
# ---------------------------------------------------------------------------

def _boss_chat_rows(nodes: list[Node]) -> list[dict[str, str]]:
    """Group BOSS's separate tv_name/tv_position/tv_msg nodes into rows."""
    fields: list[tuple[int, str, str]] = []
    for node in nodes:
        suffix = node.resource_id.rsplit("/", 1)[-1]
        if suffix in BOSS_ROW_FIELDS and node.label:
            fields.append((node.bounds[1], suffix, node.label))
    if not fields:
        return []
    fields.sort(key=lambda item: (item[0], item[1]))

    rows: list[dict[str, str]] = []
    current: dict[str, str] = {}
    anchor_y = fields[0][0]
    for y, suffix, label in fields:
        if y - anchor_y > BOSS_ROW_Y_TOLERANCE:
            if current:
                rows.append(current)
            current = {}
            anchor_y = y
        if suffix not in current or len(label) > len(current[suffix]):
            current[suffix] = label
    if current:
        rows.append(current)
    return [row for row in rows if "tv_name" in row
            and ("tv_msg" in row or "tv_position" in row)]


def _boss_raw_candidates(rows: list[dict[str, str]]) -> list[dict]:
    raw: list[dict] = []
    for row in rows:
        position = row.get("tv_position", "")
        role = position.rsplit("|", 1)[-1].strip() if "|" in position else ""
        raw.append({
            "platform": "boss",
            "contact": row.get("tv_name", ""),
            "org": position,
            "city": "",
            "role": role,
            "snippet": row.get("tv_msg", ""),
        })
    return raw


def _legacy_raw_candidates(nodes: list[Node], cfg: dict) -> list[dict]:
    """Older dumps carry one combined content-desc per row instead of tv_*. """
    raw: list[dict] = []
    for node in nodes:
        desc = norm(node.label)
        if not desc or len(desc) > 1500:
            continue
        if "上传" in desc or "预览" in desc or desc in (
            "发简历", "立即投递", "手机号", "微信号", "面试"
        ):
            continue
        lines = [line.strip() for line in desc.splitlines() if line.strip()]
        if not lines:
            continue
        has_time = any(TIME_RE.search(line) for line in lines)
        has_read = any(line in ("已读", "未读") for line in lines)
        wants = is_resume_request(desc, cfg)
        if not (has_time or has_read or wants):
            continue
        meaningful = [
            line for line in lines
            if not TIME_RE.fullmatch(line) and line not in ("已读", "未读")
        ]
        if not meaningful:
            continue
        raw.append({
            "contact": meaningful[0],
            "org": "",
            "city": "",
            "role": "",
            # Keep every meaningful line (not only the longest) so a stack
            # word such as "Java" is still visible to the resume selection.
            "snippet": " ".join(meaningful[1:]) or meaningful[0],
        })
    return raw


def _screen_raw_candidates(
    raw_items: list[dict], cfg: dict
) -> tuple[list[dict], list[dict]]:
    """Apply the same four filters and resume ladder as --from-vision."""
    passing: list[dict] = []
    skipped: list[dict] = []
    seen: set[str] = set()
    for raw in raw_items:
        result = screen_candidate(raw, cfg)
        if result["verdict"] != "pass":
            skipped.append(result)
            continue
        contact = result.get("contact", "")
        snippet = result.get("snippet", "")
        org = result.get("org", "")
        key_source = f"{contact}|{snippet}|{org}"
        key = hashlib.sha1(key_source.encode("utf-8")).hexdigest()[:12]
        if key in seen:
            continue
        seen.add(key)
        stack_text = f"{result.get('role', '')} {snippet} {org}"
        passing.append({
            "key": key,
            "platform": result.get("platform", ""),
            "contact": contact,
            "org": org,
            "city": result.get("city", ""),
            "role": result.get("role", ""),
            "snippet": snippet,
            "stack": infer_stack(stack_text, cfg),
            "resume": pick_resume(stack_text, cfg),
            "is_resume_request": True,
            "approved": False,
            "sent": False,
        })
    return passing, skipped


def extract_chat_entries(
    nodes: list[Node], cfg: dict
) -> tuple[list[dict], list[dict]]:
    """Turn a chat-list UI dump into (passing_entries, skipped_with_reasons).

    BOSS rows are grouped from their separate tv_* nodes; older combined
    content-desc rows still work as a fallback. Either way the exact same
    four filters and resume ladder as --from-vision are applied.
    """
    rows = _boss_chat_rows(nodes)
    raw_items = _boss_raw_candidates(rows) if rows else _legacy_raw_candidates(nodes, cfg)
    return _screen_raw_candidates(raw_items, cfg)


def write_queue(path: Path, entries: list[dict]) -> list[dict]:
    """Merge new candidates into an existing queue without touching approvals."""
    existing: list[dict] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DeviceError(f"queue {path} is not valid JSON: {exc}") from exc
        if not isinstance(existing, list):
            raise DeviceError(f"queue {path} must be a JSON list")

    by_key = {item.get("key"): item for item in existing}
    added = []
    for entry in entries:
        if entry["key"] in by_key:
            continue  # preserve human-filled approved / sent flags
        by_key[entry["key"]] = entry
        added.append(entry)

    merged = list(by_key.values())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def build_entries_from_vision(items: list[dict], cfg: dict) -> tuple[list[dict], list[dict]]:
    """Screen structured chat-list candidates (from visual reading of a screenshot).

    Returns (passing_entries, skipped_with_reasons). Only passing entries become
    review-queue candidates with approved=false.
    """
    passing: list[dict] = []
    skipped: list[dict] = []
    for raw in items:
        result = screen_candidate(raw, cfg)
        if result["verdict"] != "pass":
            skipped.append(result)
            continue
        contact = result.get("contact", "")
        snippet = result.get("snippet", "")
        key_source = f"{contact}|{snippet}|{result.get('org', '')}"
        key = hashlib.sha1(key_source.encode("utf-8")).hexdigest()[:12]
        stack_text = f"{snippet} {result.get('role', '')} {result.get('org', '')}"
        passing.append({
            "key": key,
            "contact": contact,
            "platform": result.get("platform", ""),
            "org": result.get("org", ""),
            "city": result.get("city", ""),
            "role": result.get("role", ""),
            "snippet": snippet,
            "stack": infer_stack(stack_text, cfg),
            "resume": pick_resume(stack_text, cfg),
            "is_resume_request": True,
            "approved": False,
            "sent": False,
        })
    return passing, skipped


def cmd_list(args: argparse.Namespace, cfg: dict) -> int:
    if getattr(args, "from_vision", None):
        items = json.loads(Path(args.from_vision).read_text(encoding="utf-8"))
        if not isinstance(items, list):
            raise DeviceError("--from-vision JSON must be a list of candidates")
        passing, skipped = build_entries_from_vision(items, cfg)
        added = write_queue(Path(args.out), passing)
        print(json.dumps({
            "source": "vision",
            "candidates_in": len(items),
            "passed_filters": len(passing),
            "skipped": len(skipped),
            "added_to_queue": len(added),
            "queue": str(args.out),
            "passing": passing,
            "skipped_detail": skipped,
        }, ensure_ascii=False, indent=2))
        return 0

    if args.dump:
        xml_text = Path(args.dump).read_text(encoding="utf-8")
    else:
        adb = Adb(args.serial)
        adb.resolve_serial()
        xml_text = adb.dump()

    nodes = parse_dump(xml_text)
    sentinel_check(nodes)
    # Guard: the list stage expects the conversation-list page. A detail page
    # exposes the 发简历 action and has no contact/preview rows; extracting from
    # it produces a junk queue with a whole message as "contact".
    if find_nodes(nodes, exact="发简历", clickable=True):
        raise DeviceError(
            "currently on a conversation detail page (发简历 button visible); "
            "go back to the chat-list page before running the list stage"
        )
    entries, skipped = extract_chat_entries(nodes, cfg)
    queue_path = Path(args.out)
    added = write_queue(queue_path, entries)

    print(json.dumps({
        "nodes": len(nodes),
        "entries_total": len(entries),
        "resume_requests": len(entries),
        "passed_filters": len(entries),
        "skipped": len(skipped),
        "added_to_queue": len(added),
        "queue": str(queue_path),
        "candidates": entries,
        "skipped_detail": skipped,
    }, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# verify stage (read-only: open the conversation, re-screen on the full text)
# ---------------------------------------------------------------------------

def _on_chat_list(nodes: list[Node]) -> bool:
    """True when the BOSS chat-list page is showing (its stable text anchors)."""
    joined = "\n".join(node.label for node in nodes if node.label)
    return "搜索联系人" in joined or ("聊天" in joined and "新招呼" in joined)


def rewind_boss_list(adb: Adb, *, max_screens: int,
                     humanize: bool = True,
                     rng: random.Random | None = None) -> None:
    """Move a retained greeting-list position to the top before scanning."""
    for _ in range(max_screens):
        before = parse_dump(adb.dump())
        sentinel_check(before)
        if not _on_chat_list(before):
            raise DeviceError("lost the BOSS chat list while rewinding")
        signature = [(n.resource_id, n.label, n.bounds) for n in before
                     if n.resource_id.endswith(("/tv_name", "/tv_position"))]
        adb.swipe(540, 650, 540, 1750, 600)
        human_pause("swipe", enabled=humanize, rng=rng)
        after = parse_dump(adb.dump())
        sentinel_check(after)
        if not _on_chat_list(after):
            raise DeviceError("lost the BOSS chat list while rewinding")
        current = [(n.resource_id, n.label, n.bounds) for n in after
                   if n.resource_id.endswith(("/tv_name", "/tv_position"))]
        if signature and signature == current:
            return
    raise DeviceError("could not establish the top of the BOSS greeting list")


def _org_fragment(org: str) -> str:
    """Reduce a list-style org label ("某社交平台 | Java") to its company token."""
    token = org.split("|", 1)[0].strip()
    return token or org.strip()


def open_boss_chat(
    adb: Adb, contact: str, *, org: str = "", max_screens: int = 45,
    humanize: bool = True, rng: random.Random | None = None,
) -> dict:
    """Launch BOSS, reach the chat list, scroll until a row for `contact` is
    visible, open that conversation, and collect its full detail text.

    Read-only aside from navigation. Returns {"found", "screen", "texts"}.
    Raises RiskSignal via sentinel_check when the UI shows a risk signal.
    When `org` is non-empty the opened detail must also mention that company,
    so two recruiters with the same display name cannot be confused.
    """
    adb.launch_app(BOSS_PKG)
    human_pause("launch", enabled=humanize, rng=rng)
    on_list = False
    for _ in range(6):
        nodes = parse_dump(adb.dump())
        sentinel_check(nodes)
        if _on_chat_list(nodes):
            on_list = True
            break
        adb.keyevent(BACK_KEY)
        human_pause("back", enabled=humanize, rng=rng)

    # Tap only when the bottom message tab is actually present, not on an
    # arbitrary detail or search page where its coordinates mean something else.
    nodes = parse_dump(adb.dump()) if not on_list else nodes
    sentinel_check(nodes)
    message_tabs = [n for n in nodes if n.resource_id.endswith("/tv_tab_3")
                    and n.label == "消息"]
    if message_tabs:
        adb.tap(*BOSS_MSG_TAB)
        human_pause("tab", enabled=humanize, rng=rng)
        nodes = parse_dump(adb.dump())
        sentinel_check(nodes)
        on_list = _on_chat_list(nodes)
    if not on_list:
        raise DeviceError("could not reach the BOSS chat list after launch")

    # The user directs the scan at the 全部 sub-tab (the 30-day conversation
    # window), not 新招呼: new-greeting rows are a subset and some requested
    # candidates only sit in 全部.
    nodes = parse_dump(adb.dump())
    sentinel_check(nodes)
    all_tab = [node for node in nodes if node.label == "全部"]
    if not all_tab:
        raise DeviceError("BOSS 全部 sub-tab not found")
    adb.tap(*all_tab[0].center)
    human_pause("tab", enabled=humanize, rng=rng)

    rewind_boss_list(adb, max_screens=max_screens, humanize=humanize, rng=rng)

    for screen in range(max_screens):
        nodes = parse_dump(adb.dump())
        sentinel_check(nodes)
        rows = find_nodes(nodes, contains=contact)
        # A name-bearing row (tv_name) beats a message-preview mention.
        named = [node for node in rows if "tv_name" in node.resource_id] or rows
        if named:
            adb.tap(*named[0].center)
            human_pause("open", enabled=humanize, rng=rng)
            detail = parse_dump(adb.dump())
            sentinel_check(detail)
            labels = [node.label for node in detail if node.label]
            # Identity lives in the header, not in recommended-job cards
            # further down the page: a wrong 某金融公司 chat still mentions
            # 某社交平台 in its recommendation feed, so restrict the check.
            identity_labels = labels[:8]
            expected_org = _org_fragment(org) if org else ""
            if not any(contact in label for label in identity_labels) or (
                expected_org and not any(expected_org in label for label in identity_labels)
            ):
                # Opened the wrong conversation (same display name or a
                # message-preview mention): back out and keep scrolling
                # instead of trusting the mismatch.
                adb.keyevent(BACK_KEY)
                human_pause("back", enabled=humanize, rng=rng)
                continue
            texts: list[str] = []
            for label in labels:
                if label not in texts:
                    texts.append(label)
            return {"found": True, "screen": screen, "texts": texts}
        adb.swipe(540, 1750, 540, 650, 600)
        human_pause("swipe", enabled=humanize, rng=rng)
    return {"found": False, "screen": max_screens, "texts": []}


def verify_one(adb: Adb, item: dict, cfg: dict, *, max_screens: int = 45,
               humanize: bool = True,
               rng: random.Random | None = None) -> dict:
    """Open one queued candidate's conversation and re-screen it against the
    full detail text. The list snippet is truncated and hides signals that
    only appear inside the chat (e.g. "这边是某外包公司", a non-local city).

    READ-ONLY on the device: navigation only, 发简历 is never touched. The
    returned dict is the updated queue entry; approved/sent are preserved, so
    the human review gate stays in charge of what gets sent.
    """
    contact = item.get("contact", "")
    updated = dict(item)
    updated["verified"] = True
    updated["verified_at"] = datetime.now().isoformat(timespec="seconds")

    location = open_boss_chat(
        adb, contact, org=item.get("org", ""), max_screens=max_screens,
        humanize=humanize, rng=rng,
    )
    if not location["found"]:
        updated["detail_found"] = False
        updated["detail_text"] = ""
        updated["verdict"] = "unverified"
        updated["verify_note"] = f"contact {contact!r} not located in the BOSS chat list"
        return updated

    detail_text = "\n".join(location["texts"])
    updated["detail_found"] = True
    updated["detail_text"] = detail_text
    # A successful verify supersedes any stale note from an earlier run.
    updated.pop("verify_note", None)

    combined_snippet = f"{item.get('snippet', '')}\n{detail_text}"
    combined_org = f"{item.get('org', '')}\n{detail_text}"
    combined_role = f"{item.get('role', '')}\n{detail_text}"
    screened = screen_candidate({
        "contact": contact,
        "org": combined_org,
        "city": item.get("city", ""),
        "role": combined_role,
        "snippet": combined_snippet,
    }, cfg)
    updated["verdict"] = screened["verdict"]
    updated["reasons"] = screened["reasons"]
    resume = pick_resume(f"{combined_role} {combined_snippet} {combined_org}", cfg)
    updated["resume_changed"] = resume != item.get("resume")
    updated["resume"] = resume
    updated["stack"] = infer_stack(f"{combined_role} {combined_snippet} {combined_org}", cfg)
    if screened["verdict"] == "skip":
        updated["skipped"] = True
        updated["skip_reason"] = "; ".join(r["detail"] for r in screened["reasons"])

    adb.keyevent(BACK_KEY)
    human_pause("back", enabled=humanize, rng=rng)
    return updated


def apply_verify_result(queue: list[dict], updated: dict) -> None:
    """Replace the queue entry whose key matches `updated`, in place."""
    for index, entry in enumerate(queue):
        if entry.get("key") == updated.get("key"):
            queue[index] = updated
            return


def _verify_targets(queue: list[dict]) -> tuple[list[dict], int]:
    """Candidates to verify and how many were paused.

    verify is BOSS-only for now (the Liepin chat list is self-drawn and cannot
    be navigated by UI tree), so non-BOSS entries are counted and skipped, not
    touched.
    """
    targets: list[dict] = []
    paused = 0
    for item in queue:
        if not item.get("is_resume_request") or item.get("sent") or item.get("skipped"):
            continue
        if item.get("platform", "boss") not in ("", "boss"):
            paused += 1
            continue
        targets.append(item)
    return targets, paused


def cmd_verify(args: argparse.Namespace, cfg: dict) -> int:
    queue_path = Path(args.queue)
    queue = load_queue(queue_path)
    targets, paused = _verify_targets(queue)
    if args.limit is not None:
        targets = targets[: max(0, args.limit)]
    if not targets:
        print(json.dumps({
            "verified": 0,
            "reason": "no candidates to verify",
            "platform_paused": paused,
        }, ensure_ascii=False))
        return 0

    adb = Adb(args.serial, dry_run=args.dry_run)
    adb.resolve_serial()
    evidence_dir = Path(args.evidence)
    humanize = not getattr(args, "no_humanize", False)
    results: list[dict] = []

    for index, item in enumerate(targets):
        try:
            updated = verify_one(
                adb, item, cfg, max_screens=args.max_screens, humanize=humanize
            )
        except RiskSignal as exc:
            evidence = save_evidence(adb, evidence_dir, "risk")
            print(json.dumps({
                "stopped": True,
                "reason": "risk signal",
                "detail": str(exc),
                "evidence": evidence,
                "processed": results,
                "remaining": len(targets) - len(results) - 1,
            }, ensure_ascii=False, indent=2))
            return 2
        except DeviceError as exc:
            print(json.dumps({
                "stopped": True,
                "reason": "device error",
                "detail": str(exc),
                "processed": results,
            }, ensure_ascii=False, indent=2))
            return 1

        apply_verify_result(queue, updated)
        # Save after every item so an interrupted run keeps its progress.
        queue_path.write_text(
            json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        append_ledger(Path(args.ledger), {
            "stage": "verify",
            "key": updated.get("key"),
            "contact": updated.get("contact"),
            "detail_found": updated.get("detail_found"),
            "verdict": updated.get("verdict"),
            "resume": updated.get("resume"),
            "resume_changed": updated.get("resume_changed"),
            "skipped": updated.get("skipped", False),
            "verified_at": updated.get("verified_at"),
        })
        results.append({
            "key": updated.get("key"),
            "contact": updated.get("contact"),
            "detail_found": updated.get("detail_found"),
            "verdict": updated.get("verdict"),
            "reasons": updated.get("reasons", []),
            "resume": updated.get("resume"),
            "resume_changed": updated.get("resume_changed"),
        })
        if index < len(targets) - 1:
            human_pause("between_candidates", enabled=humanize)

    print(json.dumps({
        "verified": len(results),
        "platform_paused": paused,
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# send stage
# ---------------------------------------------------------------------------

def load_queue(path: Path) -> list[dict]:
    if not path.exists():
        raise DeviceError(f"queue not found: {path}; run the list stage first")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise DeviceError(f"queue {path} must be a JSON list")
    return data


def approved_items(queue: list[dict]) -> list[dict]:
    return [
        item for item in queue
        if item.get("approved") is True and not item.get("sent")
        and not item.get("skipped") and item.get("verified") is True
        and item.get("detail_found") is True and item.get("verdict") == "pass"
        and item.get("recent_window") is True
    ]


def append_ledger(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def rescreen_evidence(records: list[dict], cfg: dict) -> tuple[list[dict], list[dict], dict]:
    """Re-apply current filters to saved per-conversation evidence records.

    `records` come from the read-only all-chat scan: each line has the list
    preview plus a detail-page excerpt. Rules may have changed since the scan,
    and the old report must never become a send queue without re-screening.
    Approval is always false in the result.
    """
    passing: list[dict] = []
    skipped: list[dict] = []
    ignored = 0
    duplicates = 0
    seen: set[str] = set()

    for line_no, record in enumerate(records, 1):
        if record.get("verdict") == "navigation_failed":
            ignored += 1
            continue
        contact = record.get("contact", "")
        org = record.get("org", "") or ""
        role = record.get("role", "") or ""
        list_snippet = record.get("list_snippet", "") or ""
        detail = record.get("detail_excerpt", "") or ""
        screened = screen_candidate({
            "platform": "boss",
            "contact": contact,
            "org": f"{org}\n{detail}",
            "city": record.get("city", "") or "",
            "role": f"{role}\n{detail}",
            "snippet": f"{list_snippet}\n{detail}",
        }, cfg)
        result = {
            "source_line": line_no,
            "source_verdict": record.get("verdict"),
            "contact": contact,
            "org": org,
            "role": role,
            "list_snippet": list_snippet,
            "verdict": screened["verdict"],
            "reasons": screened["reasons"],
            "request_card": screened.get("request_card", False),
            "request_text": screened.get("request_text", False),
            "request_source": screened.get("request_source"),
        }
        if screened["verdict"] != "pass":
            skipped.append(result)
            continue
        key_source = f"{contact}|{org}|{list_snippet}"
        key = hashlib.sha1(key_source.encode("utf-8")).hexdigest()[:12]
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        passing.append({
            **result,
            "key": key,
            "stack": infer_stack(f"{role}\n{list_snippet}\n{detail}", cfg),
            "resume": pick_resume(f"{role}\n{list_snippet}\n{detail}", cfg),
            "detail_excerpt": detail[:1000],
            "verified": True,
            "detail_found": True,
            "is_resume_request": True,
            "approved": False,
            "sent": False,
        })
    return passing, skipped, {"navigation_failed": ignored, "duplicates": duplicates}


_WEEKDAY_ZH = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
}
_MD_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})日")


def parse_list_time(label: str, captured_on: date) -> date | None:
    """Resolve a BOSS list timestamp to a date, relative to the capture date.

    BOSS renders same-day conversations as bare `HH:MM`, yesterday as
    `昨天 HH:MM`, the previous 2-6 days as `星期X`, and older ones as
    `M月D日`. Unknown labels return None so callers can fail closed.
    """
    text = norm(label)
    if not text:
        return None
    if TIME_RE.fullmatch(text) or text.startswith("刚刚"):
        return captured_on
    if text.startswith("昨天"):
        return captured_on - timedelta(days=1)
    if text.startswith("前天"):
        return captured_on - timedelta(days=2)
    if text.startswith("星期"):
        target = _WEEKDAY_ZH.get(text[2:3])
        if target is None:
            return None
        delta = (captured_on.weekday() - target) % 7
        if delta == 0:  # BOSS uses a bare time for today, not a weekday
            delta = 7
        return captured_on - timedelta(days=delta)
    match = _MD_DATE_RE.search(text)
    if match:
        month, day = int(match.group(1)), int(match.group(2))
        try:
            resolved = date(captured_on.year, month, day)
        except ValueError:
            return None
        if resolved > captured_on:
            try:
                resolved = date(captured_on.year - 1, month, day)
            except ValueError:
                return None
        return resolved
    return None


def load_list_times(paths: list[Path], captured_on: date) -> dict[tuple[str, str, str], list[date]]:
    """Extract (contact, org, snippet) -> parsed dates from saved BOSS dumps."""
    times: dict[tuple[str, str, str], list[date]] = {}
    for path in paths:
        rows = _boss_chat_rows(parse_dump(path.read_text(encoding="utf-8")))
        for row in rows:
            key = (
                row.get("tv_name", ""),
                row.get("tv_position", ""),
                row.get("tv_msg", ""),
            )
            resolved = parse_list_time(row.get("tv_time_v2", ""), captured_on)
            if resolved is None:
                continue
            values = times.setdefault(key, [])
            if resolved not in values:
                values.append(resolved)
    return times


def filter_recent_entries(
    entries: list[dict],
    times: dict[tuple[str, str, str], list[date]],
    *,
    as_of: date,
    captured_on: date,
    days: int = 7,
) -> tuple[list[dict], list[dict]]:
    """Keep conversations with activity inside an inclusive calendar window.

    The window is `[as_of - (days - 1), as_of]`. Missing timestamps fail closed:
    they are returned in the excluded list, never silently treated as recent.
    Approval and sent flags are always reset so a scope change cannot reuse a
    stale human decision.
    """
    if days < 1:
        raise DeviceError("--days must be at least 1")
    cutoff = as_of - timedelta(days=days - 1)
    included: list[dict] = []
    excluded: list[dict] = []
    window = {
        "as_of": as_of.isoformat(),
        "captured_on": captured_on.isoformat(),
        "days": days,
        "cutoff": cutoff.isoformat(),
    }
    for original in entries:
        item = dict(original)
        key = (
            item.get("contact", ""),
            item.get("org", "") or "",
            item.get("list_snippet", "") or item.get("snippet", "") or "",
        )
        candidates = times.get(key, [])
        last = max(candidates) if candidates else None
        item["approved"] = False
        item["sent"] = False
        item["recency_window"] = window
        item["list_time_dates"] = [value.isoformat() for value in candidates]
        if last is None:
            item["recency_reason"] = "time_unknown"
            excluded.append(item)
            continue
        item["last_activity_date"] = last.isoformat()
        if last < cutoff:
            item["recency_reason"] = "older_than_one_week"
            excluded.append(item)
            continue
        if last > as_of:
            item["recency_reason"] = "future_time"
            excluded.append(item)
            continue
        item["recent_window"] = True
        included.append(item)
    return included, excluded


def render_recent_markdown(
    entries: list[dict],
    excluded: list[dict],
    *,
    as_of: date,
    captured_on: date,
    days: int = 7,
) -> str:
    """Render the scoped, human-review-only checklist."""
    cutoff = as_of - timedelta(days=days - 1)
    groups: dict[tuple[str, str], list[dict]] = {}
    for entry in entries:
        identity = (entry.get("contact", ""), entry.get("org", "") or "")
        groups.setdefault(identity, []).append(entry)

    lines = [
        "# 近一周人工审核清单",
        "",
        f"- 时间窗口：{cutoff.isoformat()} 至 {as_of.isoformat()}（含两端，共 {days} 天）。",
        f"- 列表时间标签的捕获日期：{captured_on.isoformat()}。",
        f"- 通过条目：{len(entries)}；去重审查组：{len(groups)}；因时间排除：{len(excluded)}。",
        "- **这不是发送授权**：每条仍需人工核对对方身份、城市、外包/OD、语言栈和是否已发过简历。",
        "- 时间缺失或无法解析的会话一律排除；如需纳入，请人工核实后单独处理。",
        "",
    ]
    for (contact, org), items in groups.items():
        first = items[0]
        lines.extend([
            f"## {contact} | {org or '(公司未显示)'}",
            "",
            f"- 审查组条目数：{len(items)}",
            f"- 角色：{first.get('role', '') or '(未显示)'}",
            f"- 拟发简历：{first.get('resume', '') or '(未解析)'}",
            f"- 最近会话日期：{first.get('last_activity_date', '(未知)')}",
            f"- 索要信号：{_source_label(first.get('request_source'))}",
            f"- 列表摘要：{first.get('list_snippet', '') or '(空)'}",
            f"- 详情摘录：{(first.get('detail_excerpt', '') or '(空)')[:400]}",
            f"- 证据行号：{', '.join(str(i.get('source_line')) for i in items)}",
            "- 审核结论：□ 发  □ 不发   审核人：________   备注：________",
            "",
        ])
    if excluded:
        lines.extend(["## 因时间窗口排除", ""])
        for item in excluded:
            lines.append(
                f"- {item.get('contact', '(未知联系人)')} | "
                f"{item.get('org', '') or '(公司未显示)'}："
                f"{item.get('recency_reason', 'time_unknown')}"
            )
        lines.append("")
    return "\n".join(lines)


def render_review_markdown(entries: list[dict]) -> str:
    """Render a deduplicated human-review checklist from a rescreen queue."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for entry in entries:
        identity = (entry.get("contact", ""), entry.get("org", "") or "")
        groups.setdefault(identity, []).append(entry)

    lines = [
        "# 重筛后的人工审核清单",
        "",
        "- 数据来源：已保存的逐会话详情证据 + 当前筛选规则。",
        f"- 条目数：{len(entries)}；去重审查组：{len(groups)}。",
        "- **这不是发送授权**：每条仍需人工核对对方身份、城市、外包/OD、语言栈和是否已发过简历。",
        "- 只有把待发条目复制到发送队列并显式设置 `approved: true` 后，脚本才会考虑发送。",
        "",
    ]
    for (contact, org), items in groups.items():
        first = items[0]
        lines.extend([
            f"## {contact} | {org or '(公司未显示)'}",
            "",
            f"- 审查组条目数：{len(items)}",
            f"- 角色：{first.get('role', '') or '(未显示)'}",
            f"- 拟发简历：{first.get('resume', '') or '(未解析)'}",
            f"- 索要信号：{_source_label(first.get('request_source'))}",
            f"- 列表摘要：{first.get('list_snippet', '') or '(空)'}",
            f"- 详情摘录：{(first.get('detail_excerpt', '') or '(空)')[:400]}",
            f"- 证据行号：{', '.join(str(i.get('source_line')) for i in items)}",
            "- 审核结论：□ 发  □ 不发   审核人：________   备注：________",
            "",
        ])
    return "\n".join(lines)


def cmd_rescreen(args: argparse.Namespace, cfg: dict) -> int:
    source = Path(args.evidence)
    records = []
    for line_no, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise DeviceError(f"{source}:{line_no}: invalid JSON: {exc}") from exc

    passing, skipped, counts = rescreen_evidence(records, cfg)
    out = Path(args.out)
    if out.exists() and not args.overwrite:
        raise DeviceError(f"refusing to overwrite {out}; pass --overwrite explicitly")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(passing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_review_markdown(passing), encoding="utf-8")
    reason_counts: dict[str, int] = {}
    for item in skipped:
        for reason in item["reasons"]:
            name = reason.get("filter", "unknown")
            reason_counts[name] = reason_counts.get(name, 0) + 1
    print(json.dumps({
        "evidence": str(source),
        "records_in": len(records),
        "passing": len(passing),
        "skipped": len(skipped),
        "skip_reasons": reason_counts,
        **counts,
        "out": str(out),
        "report": str(args.report) if args.report else None,
        "approval_reset": True,
    }, ensure_ascii=False, indent=2))
    return 0


def _parse_iso_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DeviceError(f"{label} must be YYYY-MM-DD, got {value!r}") from exc


def resolve_scan_max_screens(value: object, cfg: dict) -> int:
    """Resolve the `run` scan cap: explicit CLI value first, then config.

    Default 5 is intentionally small (user rule 2026-11-25: only the first five
    screens): a run that reaches the cap is marked incomplete and never
    advances to sending.
    """
    raw = value if value is not None else cfg.get("scan", {}).get("max_screens", 5)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise DeviceError(f"scan.max_screens must be a positive integer, got {raw!r}")
    return raw


def cmd_recent(args: argparse.Namespace, cfg: dict) -> int:
    """Apply a recency window to an already screened queue (read-only)."""
    queue_path = Path(args.queue)
    entries = load_queue(queue_path)
    as_of = _parse_iso_date(args.as_of, "--as-of")
    captured_on = _parse_iso_date(args.captured_on, "--captured-on")
    dump_dir = Path(args.dump_dir)
    if not dump_dir.is_dir():
        raise DeviceError(f"dump directory not found: {dump_dir}")
    paths = sorted(dump_dir.glob("*.xml"))
    if not paths:
        raise DeviceError(f"no saved UI dumps found under {dump_dir}")

    times = load_list_times(paths, captured_on)
    included, excluded = filter_recent_entries(
        entries, times, as_of=as_of, captured_on=captured_on, days=args.days
    )
    out = Path(args.out)
    if out.exists() and not args.overwrite:
        raise DeviceError(f"refusing to overwrite {out}; pass --overwrite explicitly")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(included, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path = Path(args.report) if args.report else None
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            render_recent_markdown(
                included, excluded, as_of=as_of, captured_on=captured_on, days=args.days
            ),
            encoding="utf-8",
        )
    excluded_path = Path(args.excluded_out) if args.excluded_out else None
    if excluded_path:
        excluded_path.parent.mkdir(parents=True, exist_ok=True)
        excluded_path.write_text(
            json.dumps(excluded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({
        "queue": str(queue_path),
        "dump_dir": str(dump_dir),
        "dumps_read": len(paths),
        "as_of": as_of.isoformat(),
        "captured_on": captured_on.isoformat(),
        "days": args.days,
        "cutoff": (as_of - timedelta(days=args.days - 1)).isoformat(),
        "queue_in": len(entries),
        "recent": len(included),
        "excluded": len(excluded),
        "time_keys": len(times),
        "out": str(out),
        "report": str(report_path) if report_path else None,
        "excluded_out": str(excluded_path) if excluded_path else None,
        "approval_reset": True,
    }, ensure_ascii=False, indent=2))
    return 0


def save_evidence(adb: Adb, evidence_dir: Path, tag: str) -> dict:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    png = evidence_dir / f"{stamp}-{tag}.png"
    xml = evidence_dir / f"{stamp}-{tag}.xml"
    adb.screenshot(png)
    adb.save_dump(xml)
    return {"screenshot": str(png), "ui_dump": str(xml)}


def fetch_adb_keyboard_apk(destination: Path) -> Path:
    """Download the official ADBKeyboard APK to a local, gitignored path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(ADBKEYBOARD_APK_URL, str(destination))
    except Exception as exc:
        raise DeviceError(f"failed to download ADBKeyboard APK: {exc}") from exc
    if not destination.is_file() or destination.stat().st_size < 1000:
        raise DeviceError("downloaded ADBKeyboard APK is missing or too small")
    return destination


def load_followup_text(path: Path) -> str:
    """Load the post-resume message; never silently fall back to another text."""
    if not path.is_file():
        raise DeviceError(f"follow-up message file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise DeviceError(f"follow-up message file is empty: {path}")
    return text


def _chat_input(nodes: list[Node]) -> Node:
    matches = [
        node for node in nodes
        if node.resource_id.endswith(BOSS_CHAT_INPUT_ID)
        or (node.cls.endswith("EditText") and ("聊一聊" in node.label or "回复" in node.label))
    ]
    if len(matches) != 1:
        raise DeviceError(f"expected exactly one BOSS chat input, got {len(matches)}")
    return matches[0]


def _followup_visible(nodes: list[Node], signature: str, *, require_sent: bool) -> bool:
    editable = [n for n in nodes if n.cls.endswith("EditText")]
    typed_in_input = any(signature in norm(n.label) for n in editable)
    if require_sent:
        # After tapping 发送 the text must have left the input box and appeared
        # as a message bubble; a stale draft is not a sent message.
        return not typed_in_input and any(
            signature in norm(n.label) for n in nodes if n not in editable
        )
    # Before tapping 发送 we care only about the draft in the input box.
    return typed_in_input


def _followup_send_button(nodes: list[Node], chat_input: Node) -> Node:
    exact = find_nodes(nodes, exact="发送", clickable=True)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise DeviceError(
            f"expected exactly one follow-up '发送' button, got {len(exact)}; refusing to guess"
        )
    x1, y1, x2, y2 = chat_input.bounds
    icon = [
        node for node in nodes
        if node.clickable
        and node.cls.endswith("ImageView")
        and node.bounds[0] >= x2 - 20
        and node.bounds[1] >= y1 - 120
        and node.bounds[3] <= y2 + 60
    ]
    if len(icon) != 1:
        raise DeviceError(
            f"expected exactly one follow-up send button, got {len(icon)}; refusing to guess"
        )
    return icon[0]


FOLLOWUP_MAX_ATTEMPTS = 3


def _send_followup_once(
    adb: Adb, text: str, evidence_dir: Path, timeout: float,
    *, humanize: bool, rng: random.Random | None,
) -> dict:
    signature = norm(text)[:40]
    previous_ime: str | None = None
    try:
        nodes = parse_dump(adb.dump())
        sentinel_check(nodes)
        chat_input = _chat_input(nodes)
        adb.tap(*chat_input.center)
        time.sleep(0.2)

        previous_ime = adb.current_ime()
        if not adb.is_package_installed(ADBKEYBOARD_PACKAGE):
            apk_path = fetch_adb_keyboard_apk(Path(evidence_dir) / "ADBKeyboard.apk")
            adb.install_apk(apk_path)
        adb.enable_ime(ADBKEYBOARD_IME)
        adb.set_ime(ADBKEYBOARD_IME)
        human_pause("ime", enabled=humanize, rng=rng)
        adb.input_b64(text)

        deadline = time.monotonic() + timeout
        typed_nodes: list[Node] | None = None
        while time.monotonic() < deadline:
            time.sleep(0.2)
            typed_nodes = parse_dump(adb.dump())
            sentinel_check(typed_nodes)
            if _followup_visible(typed_nodes, signature, require_sent=False):
                break
        else:
            raise DeviceError("follow-up text was not visible in the input before send")
        if typed_nodes is None:
            raise DeviceError("no UI dump available after typing the follow-up message")

        button = _followup_send_button(typed_nodes, chat_input)
        adb.tap(*button.center)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.2)
            nodes = parse_dump(adb.dump())
            sentinel_check(nodes)
            if _followup_visible(nodes, signature, require_sent=True):
                return {
                    "followup_sent": True,
                    "followup_confirmed": True,
                    "followup_sent_at": datetime.now().isoformat(timespec="seconds"),
                }
        raise DeviceError("follow-up message was not confirmed in the chat")
    finally:
        if previous_ime and previous_ime not in ("null", "none", "None"):
            adb.set_ime(previous_ime)


def send_followup(
    adb: Adb, text: str, evidence_dir: Path, timeout: float,
    *, humanize: bool = True, rng: random.Random | None = None,
) -> dict:
    """Type and send the follow-up message after a confirmed resume send.

    Transient DeviceErrors are retried a bounded number of times. RiskSignal
    is never retried — it must stop the whole batch immediately. The resume
    send itself is never repeated from here.
    """
    if not norm(text)[:40]:
        raise DeviceError("empty follow-up message")
    last_error: DeviceError | None = None
    for attempt in range(1, FOLLOWUP_MAX_ATTEMPTS + 1):
        try:
            result = _send_followup_once(
                adb, text, evidence_dir, timeout, humanize=humanize, rng=rng,
            )
            result["followup_attempts"] = attempt
            return result
        except DeviceError as exc:
            last_error = exc
            if attempt < FOLLOWUP_MAX_ATTEMPTS:
                time.sleep(0.4)
                continue
            error = DeviceError(
                f"follow-up failed after {attempt} attempts: {last_error}"
            )
            error.followup_attempts = attempt
            raise error from last_error
    raise DeviceError("follow-up failed")  # unreachable; keeps type checkers happy


def _picker_name_node(nodes: list[Node], resume_name: str) -> Node:
    matches = [
        node for node in nodes
        if resume_name in node.label
        and (not node.resource_id or node.resource_id.endswith("/mResumeName"))
    ]
    if len(matches) != 1:
        raise DeviceError(
            f"resume picker: expected exactly one name label for {resume_name!r}, got {len(matches)}"
        )
    return matches[0]


def _picker_clickable_row(nodes: list[Node], name_node: Node) -> Node:
    if name_node.clickable:
        return name_node
    x, y = name_node.center
    rows = [
        node for node in nodes
        if node.clickable
        and node.bounds[0] <= x <= node.bounds[2]
        and node.bounds[1] <= y <= node.bounds[3]
    ]
    if len(rows) != 1:
        raise DeviceError(
            f"resume picker: expected exactly one clickable row for {name_node.label!r}, got {len(rows)}"
        )
    return rows[0]


def _picker_row(nodes: list[Node], resume_name: str) -> Node:
    # BOSS names the resume in a non-clickable mResumeName TextView and makes
    # the enclosing row clickable. Names may also carry a .pdf-like suffix.
    return _picker_clickable_row(nodes, _picker_name_node(nodes, resume_name))


def _verify_selection(nodes: list[Node], resume_name: str) -> bool:
    """True if the target row is marked selected; False if no node exposes state.

    Raises DeviceError when a *different* resume is selected, which would mean
    we are about to send the wrong version.
    """
    target_name = _picker_name_node(nodes, resume_name)
    target_row = _picker_clickable_row(nodes, target_name)
    for node in nodes:
        if (
            node is not target_row
            and node.clickable
            and (node.checked or node.selected)
            and resume_name not in node.label
        ):
            raise DeviceError(f"resume picker selected the wrong version: {node.label[:120]!r}")
    return bool(target_row.checked or target_row.selected)


def _resume_request_initiated(nodes: list[Node]) -> bool:
    """True when BOSS has accepted the resume tap and started the request.

    Live 2026-11-25 UI closes the picker immediately after the resume row is
    tapped and changes the header to 请求中; there is no selected-state row and
    no 立即投递 button in that flow. Older builds keep the picker open, so both
    shapes are supported.
    """
    labels = "\n".join(node.label for node in nodes)
    return any(token in labels for token in (
        "请求中", "附件简历请求已发送", "已发送给Boss", "这是我的简历",
    ))


def send_one(
    adb: Adb, item: dict, evidence_dir: Path, timeout: float, followup_text: str = "",
    *, humanize: bool = True, rng: random.Random | None = None,
) -> dict:
    """Send one approved item. Caller handles RiskSignal / DeviceError."""
    contact = item.get("contact", "")
    resume_name = item.get("resume", "")

    # 1. Confirm we are on the right conversation before touching anything.
    nodes = parse_dump(adb.dump())
    sentinel_check(nodes)
    if contact and not find_nodes(nodes, contains=contact):
        raise DeviceError(
            f"contact {contact!r} not visible on screen; open that conversation first"
        )

    if item.get("resume_already_sent"):
        # Recovery path: the resume tap already happened in an earlier run but
        # the batch stopped before the follow-up. Never tap 立即投递 again.
        labels = "\n".join(n.label for n in nodes)
        evidence = find_nodes(nodes, contains="已发送给Boss") or find_nodes(
            nodes, contains="附件简历请求已发送"
        )
        pending = bool(find_nodes(nodes, contains="请求中"))
        if not evidence and not pending:
            raise DeviceError(
                "resume_already_sent flag set but the screen does not confirm a resume request"
            )
        if evidence and resume_name and resume_name not in labels:
            # BOSS truncates long resume names in the delivered-resume message
            # ("候选人-开..."). On the recovery path the exact version comes from
            # the verified ledger; the UI only needs to prove that *a* resume
            # with the same candidate prefix was sent. Never tap send here.
            prefix = resume_name[:3]
            truncated = [
                node for node in evidence
                if prefix and prefix in node.label and "附件简历" in node.label
            ]
            if not truncated:
                raise DeviceError(
                    "resume_already_sent flag set but the screen does not confirm that exact version"
                )
        verified = True
        confirmed = True
    else:
        # 2. Open the resume picker.
        buttons = find_nodes(nodes, exact="发简历", clickable=True)
        if not buttons:
            # BOSS reports this header control as clickable=false even though it
            # is tappable; the exact label is unique enough to use as a fallback.
            buttons = find_nodes(nodes, exact="发简历")
        if not buttons:
            raise DeviceError("'发简历' button not found (structure mutated?)")
        adb.tap(*buttons[0].center)
        human_pause("picker", enabled=humanize, rng=rng)

        # 3. Pick the exact version. BOSS sometimes needs a moment (or a second
        # tap on the non-clickable header label) before the picker opens.
        nodes = parse_dump(adb.dump())
        sentinel_check(nodes)
        for attempt in range(8):
            try:
                _picker_name_node(nodes, resume_name)
                break
            except DeviceError:
                still_on_detail = bool(find_nodes(nodes, exact="发简历")) and not find_nodes(
                    nodes, contains="请选择要发送的简历"
                )
                if still_on_detail and attempt in (2, 5):
                    adb.tap(*buttons[0].center)
                time.sleep(0.4)
                nodes = parse_dump(adb.dump())
                sentinel_check(nodes)
        else:
            raise DeviceError(
                f"resume picker did not open for {resume_name!r} after tapping 发简历"
            )
        row = _picker_row(nodes, resume_name)
        adb.tap(*row.center)
        human_pause("select", enabled=humanize, rng=rng)

        # 4. Two live BOSS flows: older builds keep the picker open with a
        # selected row and 立即投递; newer builds close it and start the request
        # as soon as the resume row is tapped (header becomes 请求中). The new
        # flow can briefly show the detail page with 发简历 again before the
        # header flips, so poll before deciding that the old picker is still up.
        # Live 2026-11-26 showed the accepted-resume message arriving after
        # more than four seconds. Keep polling for up to 12 seconds before
        # failing closed; the row is tapped only once, so a slow UI cannot
        # cause a duplicate resume request.
        request_started = False
        old_picker_visible = False
        for attempt in range(30):
            nodes = parse_dump(adb.dump())
            sentinel_check(nodes)
            if _resume_request_initiated(nodes):
                request_started = True
                break
            try:
                _picker_name_node(nodes, resume_name)
                old_picker_visible = True
                break
            except DeviceError:
                if attempt < 29:
                    time.sleep(0.4)
        if request_started:
            verified = True
            confirmed = True
        else:
            if not old_picker_visible:
                raise DeviceError(
                    "resume request state could not be confirmed after selecting the version"
                )
            verified = _verify_selection(nodes, resume_name)
            if not verified:
                raise DeviceError("resume picker selection is not verifiable; refusing to send")

            # The irreversible tap (only in the picker-stays-open flow).
            send_buttons = find_nodes(nodes, contains="立即投递", clickable=True)
            if not send_buttons:
                # Some builds label it 发送; do not guess across an irreversible action.
                raise DeviceError("'立即投递' button not found; refusing to tap an unknown control")
            human_pause("send", enabled=humanize, rng=rng)
            adb.tap(*send_buttons[0].center)

            # Confirm the send by polling for the platform's own confirmation text.
            deadline = time.monotonic() + timeout
            confirmed = False
            while time.monotonic() < deadline:
                time.sleep(0.4)
                nodes = parse_dump(adb.dump())
                if _resume_request_initiated(nodes):
                    confirmed = True
                    break
                sentinel_check(nodes)

    result = {
        "key": item.get("key"),
        "contact": contact,
        "resume": resume_name,
        "selection_verified_by_ui": verified,
        "send_confirmed": confirmed,
        "sent_at": item.get("resume_sent_at") or datetime.now().isoformat(timespec="seconds"),
        "followup_sent": False,
        "followup_confirmed": False,
        "followup_pending": False,
        "followup_attempts": 0,
        "followup_error": None,
        "followup_skipped_reason": None,
    }

    # The follow-up text is only allowed after the platform confirmed the
    # resume send. Its failure must not cause a second resume send, so record
    # the error as data instead of raising DeviceError here. RiskSignal still
    # propagates to stop the whole batch.
    if not confirmed:
        result["followup_skipped_reason"] = "resume_send_unconfirmed"
    elif not followup_text:
        result["followup_skipped_reason"] = "no_followup_text_configured"
    else:
        human_pause("resume_to_followup", enabled=humanize, rng=rng)
        try:
            followup = send_followup(
                adb, followup_text, evidence_dir, timeout,
                humanize=humanize, rng=rng,
            )
            result.update(followup)
        except RiskSignal as exc:
            # The resume is already sent: record the risk signal on this item,
            # let cmd_send stop the batch, and keep `sent: true` to avoid a
            # duplicate resume if the operator retries.
            result["risk_signal"] = f"{type(exc).__name__}: {exc}"
            result["followup_error"] = result["risk_signal"]
        except DeviceError as exc:
            result["followup_error"] = f"{type(exc).__name__}: {exc}"
            result["followup_pending"] = True
            result["followup_attempts"] = getattr(exc, "followup_attempts", 0)
    return result


def cmd_send(args: argparse.Namespace, cfg: dict) -> int:
    if not args.yes_i_reviewed:
        print(
            f"refusing to send: review the queue and re-run with {SEND_FLAG}",
            file=sys.stderr,
        )
        return 1

    queue_path = Path(args.queue)
    queue = load_queue(queue_path)
    targets = approved_items(queue)
    if not targets:
        print(json.dumps({"sent": 0, "reason": "no approved unsent items"}, ensure_ascii=False))
        return 0

    try:
        followup_text = load_followup_text(Path(args.followup_file))
    except DeviceError as exc:
        print(json.dumps({
            "stopped": True,
            "reason": "device error",
            "detail": str(exc),
            "processed": [],
        }, ensure_ascii=False, indent=2))
        return 1

    adb = Adb(args.serial, dry_run=args.dry_run)
    adb.resolve_serial()
    evidence_dir = Path(args.evidence)
    humanize = not getattr(args, "no_humanize", False)
    results: list[dict] = []
    exit_code = 0

    for index, item in enumerate(targets):
        try:
            if getattr(args, "auto_open", False) and item.get("platform", "boss") == "boss":
                located = open_boss_chat(
                    adb, item.get("contact", ""), org=item.get("org", ""),
                    max_screens=getattr(args, "max_screens", 45),
                    humanize=humanize,
                )
                if not located.get("found"):
                    raise DeviceError(
                        f"contact {item.get('contact', '')!r} not found while auto-opening"
                    )
            result = send_one(
                adb, item, evidence_dir, args.timeout, followup_text,
                humanize=humanize,
            )
        except RiskSignal as exc:
            evidence = save_evidence(adb, evidence_dir, "risk")
            print(json.dumps({
                "stopped": True,
                "reason": "risk signal",
                "detail": str(exc),
                "evidence": evidence,
                "processed": results,
                "remaining": len(targets) - len(results) - 1,
            }, ensure_ascii=False, indent=2))
            return 2
        except DeviceError as exc:
            print(json.dumps({
                "stopped": True,
                "reason": "device error",
                "detail": str(exc),
                "processed": results,
            }, ensure_ascii=False, indent=2))
            return 1

        results.append(result)
        append_ledger(Path(args.ledger), result)
        for entry in queue:
            if entry.get("key") == item.get("key"):
                entry["sent"] = True
        queue_path.write_text(
            json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if not result["send_confirmed"]:
            exit_code = 3  # sent but unconfirmed: human must check
        if result.get("risk_signal"):
            # Risk appeared after the resume was already sent (follow-up text
            # stage). The item is irreversible, so keep it marked sent, record
            # evidence, and stop the whole batch.
            evidence = save_evidence(adb, evidence_dir, "risk_followup")
            print(json.dumps({
                "stopped": True,
                "reason": "risk signal after resume send",
                "detail": result["risk_signal"],
                "evidence": evidence,
                "processed": results,
                "remaining": len(targets) - len(results),
            }, ensure_ascii=False, indent=2))
            return 2
        if index < len(targets) - 1:
            human_pause("between_candidates", enabled=humanize)

    print(json.dumps({"sent": len(results), "results": results}, ensure_ascii=False, indent=2))
    return exit_code


# ---------------------------------------------------------------------------
# run stage: one scheduled-task entry point (scan -> rescreen -> recent -> send)
# ---------------------------------------------------------------------------

def _boss_rows_with_coords(nodes: list[Node]) -> list[dict]:
    """Like _boss_chat_rows but keep the tv_name center for safe tapping."""
    fields: list[tuple[int, str, str, tuple[int, int]]] = []
    for node in nodes:
        suffix = node.resource_id.rsplit("/", 1)[-1]
        if suffix in BOSS_ROW_FIELDS and node.label:
            fields.append((node.center[1], suffix, node.label, node.center))
    fields.sort(key=lambda item: (item[0], item[1]))
    rows: list[dict] = []
    for y, suffix, label, center in fields:
        if rows and y - rows[-1]["_y"] <= BOSS_ROW_Y_TOLERANCE:
            row = rows[-1]
            if suffix not in row or len(label) > len(row[suffix]):
                row[suffix] = label
            if suffix == "tv_name":
                row["_center"] = center
            row["_y"] = max(row["_y"], y)
        else:
            rows.append({"_y": y, suffix: label,
                         **({"_center": center} if suffix == "tv_name" else {})})
    return [row for row in rows if "tv_name" in row]


def is_conversation_row(row: dict) -> bool:
    """Exclude observed BOSS non-chat cards from the per-conversation scan."""
    name = row.get("tv_name", "")
    return not (("发布了新职位" in name and "Boss新发布" in row.get("tv_msg", ""))
                or name == "通知")


def _at_thirty_day_bottom(nodes: list[Node]) -> bool:
    """True only when BOSS explicitly says the 30-day list has ended."""
    return any("以上是30天内的联系人" in node.label for node in nodes if node.label)


def _restart_boss_for_scan(adb: Adb, *, humanize: bool = True,
                           rng: random.Random | None = None) -> None:
    """Force-stop and relaunch BOSS, failing closed on login or risk pages."""
    adb.force_stop_app(BOSS_PKG)
    human_pause("back", enabled=humanize, rng=rng)
    adb.launch_app(BOSS_PKG)
    human_pause("launch", enabled=humanize, rng=rng)
    # uiautomator is occasionally unavailable right after a cold relaunch.
    # Retry only the device dump, never a detected login/risk page.
    xml = ""
    for attempt in range(3):
        try:
            xml = adb.dump()
            break
        except DeviceError:
            if attempt == 2:
                raise
            time.sleep(0.5)
    nodes = parse_dump(xml)
    sentinel_check(nodes)
    labels = [node.label for node in nodes if node.label]
    joined = " ".join(labels)
    if any(token in joined for token in (
        "其他方式登录", "一键登录", "微信登录", "手机号登录",
    )):
        raise DeviceError("BOSS is logged out; scan stopped")


def _navigate_to_boss_all_tab(adb: Adb, *, max_screens: int,
                              humanize: bool = True,
                              rng: random.Random | None = None) -> None:
    """Bring BOSS to the 全部 sub-tab of the chat list after a clean restart."""
    _restart_boss_for_scan(adb, humanize=humanize, rng=rng)
    on_list = False
    nodes: list[Node] = []
    for _ in range(6):
        nodes = parse_dump(adb.dump())
        sentinel_check(nodes)
        if _on_chat_list(nodes):
            on_list = True
            break
        adb.keyevent(BACK_KEY)
        human_pause("back", enabled=humanize, rng=rng)
    if not on_list:
        nodes = parse_dump(adb.dump())
        sentinel_check(nodes)
        on_list = _on_chat_list(nodes)
    if not on_list:
        # A fresh monkey launch can land on the 职位 tab and back presses do not
        # switch bottom tabs. Tap the message tab before failing closed.
        adb.tap(*BOSS_MSG_TAB)
        human_pause("tab", enabled=humanize, rng=rng)
        nodes = parse_dump(adb.dump())
        sentinel_check(nodes)
        on_list = _on_chat_list(nodes)
        if not on_list:
            raise DeviceError("message tab tap did not land on the chat list")
    else:
        message_tabs = [node for node in nodes
                        if node.resource_id.endswith("/tv_tab_3") and node.label == "消息"]
        if message_tabs:
            adb.tap(*BOSS_MSG_TAB)
            human_pause("tab", enabled=humanize, rng=rng)
            nodes = parse_dump(adb.dump())
            sentinel_check(nodes)
            on_list = _on_chat_list(nodes)
        if not on_list:
            raise DeviceError("message tab tap did not land on the chat list")

    all_tabs = [node for node in nodes if node.label == "全部"]
    if not all_tabs:
        raise DeviceError("BOSS 全部 sub-tab not found")
    adb.tap(*all_tabs[0].center)
    human_pause("tab", enabled=humanize, rng=rng)
    nodes = parse_dump(adb.dump())
    sentinel_check(nodes)
    if not _on_chat_list(nodes):
        raise DeviceError("全部 sub-tab tap did not land on the chat list")


def _inline_send_key(contact: str, org: str, list_snippet: str) -> str:
    """Stable key matching `rescreen_evidence` for inline-send audit trails."""
    return hashlib.sha1(f"{contact}|{org}|{list_snippet}".encode("utf-8")).hexdigest()[:12]


def make_inline_sender(
    adb: Adb, *, evidence_dir: Path, ledger_path: Path, timeout: float,
    followup_text: str, humanize: bool = True,
    rng: random.Random | None = None, max_send: int = 0,
) -> Callable[[dict], dict | None]:
    """Build the per-conversation sender used by the run stage.

    The callback runs while the conversation detail page is already on screen;
    `send_one` therefore neither re-opens nor scrolls. Returning ``None`` means
    "quota exhausted / do not send"; a returned result means the irreversible
    resume tap has happened (even if UI confirmation is still pending).
    """
    remaining = max_send if max_send and max_send > 0 else None
    sent = 0

    def send(item: dict) -> dict | None:
        nonlocal sent
        if remaining is not None and sent >= remaining:
            return None
        result = send_one(
            adb, item, evidence_dir, timeout, followup_text,
            humanize=humanize, rng=rng,
        )
        sent += 1
        item["sent"] = True
        append_ledger(ledger_path, {"stage": "send", **result})
        return result

    return send


def scan_all_boss_chats(
    adb: Adb,
    cfg: dict,
    *,
    out_dir: Path,
    max_screens: int = 220,
    humanize: bool = True,
    rng: random.Random | None = None,
    window_cutoff: date | None = None,
    captured_on: date | None = None,
    sender: Callable[[dict], dict | None] | None = None,
) -> dict:
    """Open every BOSS 全部 conversation once; write JSONL evidence + XML dumps.

    Read-only by default. When ``sender`` is supplied, each eligible conversation
    is sent while its detail page is still open; the scan then returns to the
    list and opens the next row. Coverage is proven when BOSS shows the explicit
    30-day bottom text, or — because that text is unreachable on long lists —
    when an entire screen is provably older than ``window_cutoff`` (the list is
    ordered newest-first, so nothing further can be in scope). A stable screen is
    reported as incomplete and the run entry point refuses to send from it.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    details_path = out_dir / "details.jsonl"
    dump_dir = out_dir / "list_dumps"
    dump_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "scan_status.json"

    processed: set[tuple[str, str, str]] = set()
    if details_path.exists():
        for line in details_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("verdict") != "navigation_failed":
                processed.add((record.get("contact", ""), record.get("org", ""),
                               record.get("list_snippet", "")))

    _navigate_to_boss_all_tab(adb, max_screens=max_screens,
                              humanize=humanize, rng=rng)
    rewind_boss_list(adb, max_screens=max_screens,
                     humanize=humanize, rng=rng)

    passing = 0
    sent = 0
    prev_sig: tuple | None = None
    stable = 0
    opened = 0
    screens_scanned = 0
    completed = False
    window_done = False

    with details_path.open("a", encoding="utf-8") as sink:
        for screen in range(max_screens):
            xml = adb.dump()
            (dump_dir / f"page_{screen:03d}.xml").write_text(xml, encoding="utf-8")
            nodes = parse_dump(xml)
            sentinel_check(nodes)
            screens_scanned = screen + 1
            if _at_thirty_day_bottom(nodes):
                completed = True
            rows = _boss_rows_with_coords(nodes)
            pending = [
                row for row in rows
                if is_conversation_row(row)
                and (row.get("tv_name", ""), row.get("tv_position", ""),
                     row.get("tv_msg", "")) not in processed
            ]
            for row in pending:
                now_nodes = parse_dump(adb.dump())
                sentinel_check(now_nodes)
                now_rows = _boss_rows_with_coords(now_nodes)
                matches = [
                    candidate for candidate in now_rows
                    if (candidate.get("tv_name"), candidate.get("tv_position"))
                    == (row.get("tv_name"), row.get("tv_position"))
                ]
                if len(matches) > 1:
                    exact = [
                        candidate for candidate in matches
                        if candidate.get("tv_msg") == row.get("tv_msg")
                    ]
                    if len(exact) == 1:
                        matches = exact
                if len(matches) != 1:
                    # A live chat list can reorder while rows are being opened.
                    # Record the stale row and keep scanning instead of aborting.
                    record = {
                        "contact": row.get("tv_name", ""),
                        "org": row.get("tv_position", ""),
                        "role": "",
                        "list_snippet": row.get("tv_msg", ""),
                        "verdict": "navigation_failed",
                        "reasons": [{"filter": "navigation",
                                     "detail": "列表行在点击前消失或无法唯一匹配"}],
                        "resume": None,
                        "detail_excerpt": "",
                    }
                    sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                    sink.flush()
                    processed.add((row.get("tv_name", ""), row.get("tv_position", ""),
                                   row.get("tv_msg", "")))
                    continue
                adb.tap(*matches[0]["_center"])
                human_pause("open", enabled=humanize, rng=rng)
                detail_nodes = parse_dump(adb.dump())
                sentinel_check(detail_nodes)
                if _on_chat_list(detail_nodes):
                    raise DeviceError("conversation did not open; scan incomplete")
                detail_labels = [node.label for node in detail_nodes if node.label]
                detail = "\n".join(detail_labels)
                identity_labels = detail_labels[:8]
                expected_contact = row.get("tv_name", "")
                expected_org = _org_fragment(row.get("tv_position", ""))
                identity_ok = (
                    any(expected_contact in label for label in identity_labels)
                    and (not expected_org
                         or any(expected_org in label for label in identity_labels))
                )
                # Identity mismatch is a resume-sending stop condition, but for a
                # read-only scan it should be recorded and skipped so one stale
                # list row cannot abort coverage of the remaining conversations.
                if not identity_ok:
                    record = {
                        "contact": expected_contact,
                        "org": row.get("tv_position", ""),
                        "role": "",
                        "list_snippet": row.get("tv_msg", ""),
                        "verdict": "navigation_failed",
                        "reasons": [{"filter": "identity",
                                     "detail": "详情头部未同时确认联系人与公司"}],
                        "resume": None,
                        "detail_excerpt": detail[:500],
                    }
                    sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                    sink.flush()
                    processed.add((expected_contact, row.get("tv_position", ""),
                                   row.get("tv_msg", "")))
                    adb.keyevent(BACK_KEY)
                    human_pause("back", enabled=humanize, rng=rng)
                    returned = parse_dump(adb.dump())
                    sentinel_check(returned)
                    if not _on_chat_list(returned):
                        raise DeviceError("did not return to chat list after identity mismatch")
                    continue
                position = row.get("tv_position", "")
                role = position.rsplit("|", 1)[-1].strip() if "|" in position else ""
                item = {
                    "platform": "boss",
                    "contact": expected_contact,
                    "org": f"{position} {detail[:400]}",
                    "city": "",
                    "role": role,
                    "snippet": f'{row.get("tv_msg", "")}\n{detail}',
                }
                screened = screen_candidate(item, cfg)
                resume_name = pick_resume(f'{role}\n{item["snippet"]}', cfg) \
                    if screened["verdict"] == "pass" else None
                send_result: dict | None = None
                send_attempted = False
                send_skipped_reason = None
                if screened["verdict"] == "pass" and sender is not None:
                    if window_cutoff is None or captured_on is None:
                        send_skipped_reason = "recent_window_not_available"
                    else:
                        list_time = parse_list_time(
                            row.get("tv_time_v2", ""), captured_on,
                        )
                        in_window = (
                            list_time is not None
                            and list_time >= window_cutoff
                        )
                        if not in_window:
                            send_skipped_reason = "outside_recent_window"
                        else:
                            item.update({
                                "key": _inline_send_key(
                                    expected_contact, position,
                                    row.get("tv_msg", ""),
                                ),
                                "resume": resume_name,
                                "approved": True,
                                "sent": False,
                            })
                            send_attempted = True
                            send_result = sender(item)
                            if send_result is None:
                                send_skipped_reason = "max_send_reached"
                            else:
                                sent += 1
                record = {
                    "key": item.get("key") if send_attempted else None,
                    "contact": expected_contact,
                    "org": position,
                    "role": role,
                    "list_snippet": row.get("tv_msg", ""),
                    "verdict": screened["verdict"],
                    "reasons": screened["reasons"],
                    "request_card": screened.get("request_card", False),
                    "request_text": screened.get("request_text", False),
                    "request_source": screened.get("request_source"),
                    "resume": resume_name,
                    "detail_excerpt": detail[:2000],
                    "sent": send_result is not None,
                    "send_attempted": send_attempted,
                    "send_skipped_reason": send_skipped_reason,
                    "send_result": send_result,
                }
                if screened["verdict"] == "pass":
                    passing += 1
                processed.add((expected_contact, position, row.get("tv_msg", "")))
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                sink.flush()
                if send_result and send_result.get("risk_signal"):
                    # The resume may already be irreversible, but the follow-up
                    # stage saw a risk page. Persist this record first, then
                    # stop the whole run instead of opening another chat.
                    raise RiskSignal(str(send_result["risk_signal"]))
                opened += 1
                # A successful send can leave BOSS on a transient follow-up
                # screen. Give it two back presses before fail-closed; never
                # re-open the conversation (that could duplicate a send).
                for back_attempt in range(2):
                    adb.keyevent(BACK_KEY)
                    human_pause("back", enabled=humanize, rng=rng)
                    returned = parse_dump(adb.dump())
                    sentinel_check(returned)
                    if _on_chat_list(returned):
                        break
                else:
                    raise DeviceError(
                        "did not return to chat list after opening conversation"
                    )

            if window_cutoff is not None and captured_on is not None:
                # BOSS lists conversations newest-first: once every row on a
                # screen is older than the window, nothing below can be in
                # scope. Unknown/unparsable times keep scanning (fail closed).
                screen_dates = [
                    parse_list_time(row.get("tv_time_v2", ""), captured_on)
                    for row in rows if is_conversation_row(row)
                ]
                if screen_dates and all(
                    stamp is not None and stamp < window_cutoff
                    for stamp in screen_dates
                ):
                    window_done = True
                    break

            signature = tuple((node.resource_id, node.label) for node in nodes if node.label)
            if signature == prev_sig:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            prev_sig = signature
            if completed:
                break
            adb.swipe(540, 1750, 540, 650, 600)
            human_pause("swipe", enabled=humanize, rng=rng)

    if completed:
        stage, stop_reason = "completed", "bottom"
    elif window_done:
        stage, stop_reason = "completed_window", "window"
    else:
        stage, stop_reason = "incomplete", "screen_limit_or_stable"
    status = {
        "stage": stage,
        "stop_reason": stop_reason,
        "screens_scanned": screens_scanned,
        "processed": len(processed),
        "opened": opened,
        "passing": passing,
        "sent": sent,
        "details": str(details_path),
        "dump_dir": str(dump_dir),
    }
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return status


def _source_label(source: object) -> str:
    """Human-readable label for the detected resume-request signal."""
    labels = {
        "card": "平台卡片（含同意/拒绝）",
        "text": "文本索要",
        "card+text": "卡片 + 文本（两者都命中）",
    }
    return labels.get(str(source or ""), "(未记录)")


def _count_request_sources(entries: list[dict]) -> dict[str, int]:
    """Count how each entry's resume request was detected (card / text / both)."""
    counts: dict[str, int] = {}
    for entry in entries:
        source = entry.get("request_source") or "unknown"
        counts[source] = counts.get(source, 0) + 1
    return counts


def cmd_run(args: argparse.Namespace, cfg: dict) -> int:
    """One entry point for scheduled runs: scan, rescreen, scope, approve, send."""
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "run_summary.json"
    as_of = _parse_iso_date(args.as_of, "--as-of")
    captured_on = _parse_iso_date(args.captured_on, "--captured-on")
    max_screens = resolve_scan_max_screens(getattr(args, "max_screens", None), cfg)
    humanize = not getattr(args, "no_humanize", False)
    adb: Adb | None = None

    def write_summary(payload: dict) -> None:
        summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    try:
        adb = Adb(args.serial, dry_run=args.dry_run)
        adb.resolve_serial()
        followup_text = load_followup_text(Path(args.followup_file))
        sender = make_inline_sender(
            adb,
            evidence_dir=out_dir / "send_evidence",
            ledger_path=out_dir / "ledger.jsonl",
            timeout=args.timeout,
            followup_text=followup_text,
            humanize=humanize,
            max_send=args.max_send,
        )
        scan = scan_all_boss_chats(
            adb, cfg, out_dir=out_dir, max_screens=max_screens,
            humanize=humanize,
            window_cutoff=as_of - timedelta(days=args.days - 1),
            captured_on=captured_on,
            sender=sender,
        )
        scan_stage = scan.get("stage")
        coverage = None
        if scan_stage == "completed":
            coverage = "bottom"
        elif scan_stage == "completed_window":
            coverage = "window"
        elif (scan_stage == "incomplete"
              and scan.get("screens_scanned") == max_screens):
            # User rule 2026-11-25: only the configured first N screens are in
            # scope. Reaching that cap is a bounded coverage result, not a
            # device failure; a stable-list stop before the cap stays fail-closed.
            coverage = "screen_limit"
        else:
            write_summary({"stage": "scan_incomplete", "scan": scan,
                           "coverage": coverage,
                           "sent": 0,
                           "reason": scan.get("stop_reason") or "scan coverage unproven"})
            return 1

        details_path = Path(scan.get("details") or (out_dir / "details.jsonl"))
        records = [
            json.loads(line) for line in details_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        passing, skipped, counts = rescreen_evidence(records, cfg)
        rescreen_path = out_dir / "queue_rescreened.json"
        rescreen_path.write_text(json.dumps(passing, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        report_path = out_dir / "review_rescreened.md"
        report_path.write_text(render_review_markdown(passing), encoding="utf-8")

        dumps = sorted(Path(scan.get("dump_dir") or (out_dir / "list_dumps")).glob("*.xml"))
        times = load_list_times(dumps, captured_on)
        included, excluded = filter_recent_entries(
            passing, times, as_of=as_of, captured_on=captured_on, days=args.days,
        )
        recent_path = out_dir / "queue_recent.json"
        recent_path.write_text(json.dumps(included, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        excluded_path = out_dir / "queue_recent_excluded.json"
        excluded_path.write_text(json.dumps(excluded, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        recent_report = out_dir / "review_recent.md"
        recent_report.write_text(
            render_recent_markdown(included, excluded, as_of=as_of,
                                   captured_on=captured_on, days=args.days),
            encoding="utf-8",
        )

        targets = included[: args.max_send] if args.max_send and args.max_send > 0 else included
        sent_keys = {
            record.get("key") for record in records if record.get("sent")
        }
        for entry in included:
            entry["approved"] = entry.get("key") in sent_keys
            entry["sent"] = entry.get("key") in sent_keys
            entry["verified"] = True
            entry["detail_found"] = True
            entry["skipped"] = False
        run_queue = out_dir / "run_queue.json"
        run_queue.write_text(json.dumps(included, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

        sent_count = int(scan.get("sent", 0) or 0)
        summary = {
            "stage": "sent" if sent_count else "no_candidates",
            "scan": scan,
            "coverage": coverage,
            "rescreen": {"passing": len(passing), "skipped": len(skipped),
                         "request_sources": _count_request_sources(included),
                         **counts},
            "recent": {"included": len(included), "excluded": len(excluded),
                       "targets": len(targets)},
            "queue": str(run_queue),
            "ledger": str(out_dir / "ledger.jsonl"),
            "sent": sent_count,
        }
        write_summary(summary)
        return 0
    except RiskSignal as exc:
        evidence = save_evidence(adb, Path(args.out_dir) / "send_evidence", "risk") if adb else None
        write_summary({"stage": "risk", "detail": str(exc), "evidence": evidence, "sent": 0})
        return 2
    except DeviceError as exc:
        write_summary({"stage": "device_error", "detail": str(exc), "sent": 0})
        return 1


# ---------------------------------------------------------------------------

def cmd_followup(args: argparse.Namespace, cfg: dict) -> int:
    """Retry only the post-resume explanation message for confirmed sends.

    This command never taps 发简历 or 立即投递. It reopens each conversation by
    contact + org and uses send_one's resume_already_sent recovery branch, so
    a missing/duplicate resume send cannot be introduced here.
    """
    if not getattr(args, "yes_i_reviewed", False):
        print(
            "refusing to retry follow-up messages: re-run with --yes-i-reviewed",
            file=sys.stderr,
        )
        return 1

    ledger_path = Path(args.ledger)
    records: list[dict] = []
    if ledger_path.exists():
        for line_no, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise DeviceError(f"{ledger_path}:{line_no}: invalid JSON: {exc}") from exc
    confirmed_keys = {
        str(rec.get("key")) for rec in records if rec.get("followup_confirmed")
    }
    targets: list[dict] = []
    seen: set[str] = set()
    for rec in reversed(records):
        key = str(rec.get("key"))
        if key in seen or key in confirmed_keys or not rec.get("send_confirmed"):
            continue
        if not (rec.get("followup_pending") or rec.get("followup_error")
                or rec.get("resume_sent_at")):
            continue
        seen.add(key)
        targets.append(rec)
    targets.reverse()

    if not targets:
        print(json.dumps({"followup_sent": 0, "reason": "no pending follow-ups"},
                         ensure_ascii=False))
        return 0

    followup_text = load_followup_text(Path(args.followup_file))
    adb = Adb(getattr(args, "serial", None), dry_run=getattr(args, "dry_run", False))
    adb.resolve_serial()
    humanize = not getattr(args, "no_humanize", False)
    evidence_dir = Path(args.evidence)
    results: list[dict] = []
    try:
        for rec in targets:
            located = open_boss_chat(
                adb, rec.get("contact", ""), org=rec.get("org", ""),
                max_screens=getattr(args, "max_screens", 45), humanize=humanize,
            )
            if not located.get("found"):
                raise DeviceError(
                    f"contact {rec.get('contact', '')!r} not found while retrying follow-up"
                )
            item = {
                "key": rec.get("key"),
                "platform": rec.get("platform", "boss"),
                "contact": rec.get("contact", ""),
                "org": rec.get("org", ""),
                "resume": rec.get("resume", ""),
                "resume_already_sent": True,
                "resume_sent_at": rec.get("sent_at") or rec.get("resume_sent_at"),
            }
            try:
                result = send_one(
                    adb, item, evidence_dir, args.timeout, followup_text,
                    humanize=humanize,
                )
            except RiskSignal as exc:
                save_evidence(adb, evidence_dir, "followup_risk")
                print(json.dumps({
                    "stopped": True, "reason": "risk signal", "detail": str(exc),
                    "results": results,
                }, ensure_ascii=False, indent=2))
                return 2
            result["stage"] = "followup"
            append_ledger(ledger_path, result)
            results.append(result)
            if result.get("risk_signal"):
                save_evidence(adb, evidence_dir, "followup_risk")
                print(json.dumps({
                    "stopped": True, "reason": "risk signal",
                    "results": results,
                }, ensure_ascii=False, indent=2))
                return 2
    except DeviceError as exc:
        print(json.dumps({
            "stopped": True, "reason": "device error", "detail": str(exc),
            "results": results,
        }, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({
        "followup_sent": sum(1 for r in results if r.get("followup_confirmed")),
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=None, help="adb device serial (auto-detected if omitted)")
    parser.add_argument("--config", default=None, help="ladder config path")
    parser.add_argument("--names", default=None, help="personal resume-name mapping (default documents/dispatch/resume_names.json)")
    parser.add_argument(
        "--no-humanize", action="store_true",
        help="disable random human-like pauses (deterministic troubleshooting only)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="read chat list and build the review queue (read-only)")
    p_list.add_argument("--out", default=str(DEFAULT_QUEUE))
    p_list.add_argument("--dump", default=None, help="read a saved UI dump instead of the device")
    p_list.add_argument(
        "--from-vision", default=None,
        help="JSON file of structured candidates read from a chat-list screenshot "
             "(chat lists are WebView-drawn; uiautomator cannot read them)",
    )

    p_verify = sub.add_parser(
        "verify",
        help="open each queued candidate's conversation and re-screen on the "
             "full detail text (read-only; never taps 发简历)",
    )
    p_verify.add_argument("--queue", default=str(DEFAULT_QUEUE))
    p_verify.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    p_verify.add_argument("--evidence", default=str(DEFAULT_EVIDENCE))
    p_verify.add_argument(
        "--limit", type=int, default=None,
        help="verify at most N items this run (risk-control pacing)",
    )
    p_verify.add_argument("--max-screens", type=int, default=45)
    p_verify.add_argument("--dry-run", action="store_true")

    p_rescreen = sub.add_parser(
        "rescreen",
        help="re-apply current filters to saved per-conversation evidence JSONL",
    )
    p_rescreen.add_argument("--evidence", required=True)
    p_rescreen.add_argument("--out", required=True)
    p_rescreen.add_argument("--report", default=None, help="optional Markdown review checklist")
    p_rescreen.add_argument("--overwrite", action="store_true")

    p_recent = sub.add_parser(
        "recent",
        help="filter an already screened queue down to a recent message window",
    )
    p_recent.add_argument("--queue", required=True)
    p_recent.add_argument(
        "--dump-dir", required=True,
        help="directory of saved BOSS list XML dumps containing tv_time_v2 labels",
    )
    p_recent.add_argument("--as-of", required=True, help="window end date, YYYY-MM-DD")
    p_recent.add_argument(
        "--captured-on", required=True,
        help="date when the saved list dumps were captured; relative labels resolve against it",
    )
    p_recent.add_argument("--days", type=int, default=7)
    p_recent.add_argument("--out", required=True)
    p_recent.add_argument("--report", default=None)
    p_recent.add_argument("--excluded-out", default=None)
    p_recent.add_argument("--overwrite", action="store_true")

    p_run = sub.add_parser(
        "run",
        help="single scheduled-task entry point: scan, rescreen, scope, approve and send",
    )
    p_run.add_argument("--out-dir", required=True, help="directory for evidence and queues")
    p_run.add_argument("--as-of", default=date.today().isoformat(),
                       help="recent-window end date, YYYY-MM-DD (default: today)")
    p_run.add_argument("--captured-on", default=date.today().isoformat(),
                       help="date the fresh scan was captured, YYYY-MM-DD (default: today)")
    p_run.add_argument("--days", type=int, default=7)
    p_run.add_argument("--max-screens", type=int, default=None,
                       help="override config scan.max_screens (default 5 from config)")
    p_run.add_argument("--max-send", type=int, default=0,
                       help="send at most N candidates this run; 0 means no limit")
    p_run.add_argument("--followup-file", default=str(DEFAULT_FOLLOWUP_FILE))
    p_run.add_argument("--timeout", type=float, default=4.0)
    p_run.add_argument("--dry-run", action="store_true")

    p_followup = sub.add_parser(
        "followup",
        help="retry only missing explanation messages for confirmed resume sends",
    )
    p_followup.add_argument("--ledger", required=True)
    p_followup.add_argument("--evidence", default=str(DEFAULT_EVIDENCE))
    p_followup.add_argument("--followup-file", default=str(DEFAULT_FOLLOWUP_FILE))
    p_followup.add_argument("--timeout", type=float, default=4.0)
    p_followup.add_argument("--max-screens", type=int, default=45)
    p_followup.add_argument("--dry-run", action="store_true")
    p_followup.add_argument(
        "--yes-i-reviewed", action="store_true",
        help="required acknowledgement before sending any message",
    )

    p_send = sub.add_parser("send", help="send only approved items (writes to the device)")
    p_send.add_argument("--queue", default=str(DEFAULT_QUEUE))
    p_send.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    p_send.add_argument("--evidence", default=str(DEFAULT_EVIDENCE))
    p_send.add_argument(
        "--followup-file", default=str(DEFAULT_FOLLOWUP_FILE),
        help="UTF-8 message sent after each confirmed resume send",
    )
    p_send.add_argument("--timeout", type=float, default=4.0)
    p_send.add_argument(
        "--auto-open", action="store_true",
        help="navigate the BOSS list to each approved conversation before sending",
    )
    p_send.add_argument("--max-screens", type=int, default=45)
    p_send.add_argument("--dry-run", action="store_true")
    p_send.add_argument(
        "--yes-i-reviewed", action="store_true",
        help="required acknowledgement that the queue was human-reviewed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config, names=load_names(args.names))
    if args.command == "list":
        return cmd_list(args, cfg)
    if args.command == "verify":
        return cmd_verify(args, cfg)
    if args.command == "rescreen":
        return cmd_rescreen(args, cfg)
    if args.command == "recent":
        return cmd_recent(args, cfg)
    if args.command == "run":
        return cmd_run(args, cfg)
    if args.command == "followup":
        return cmd_followup(args, cfg)
    return cmd_send(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
