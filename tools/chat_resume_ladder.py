#!/usr/bin/env python3
"""Language-stack → resume-version ladder (pure functions, stdlib only).

No ADB, no file I/O beyond loading the JSON config. Kept separate from the
device driver so all decision logic can be unit-tested offline.

Config contract: config/resume_ladder.json (see that file for the schema).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "resume_ladder.json"
DEFAULT_NAMES = (
    Path(__file__).resolve().parent.parent
    / "documents" / "dispatch" / "resume_names.json"
)
_PLACEHOLDER_RE = re.compile(r"%([A-Z_]+)%")


def load_names(path: str | Path | None = None) -> dict[str, str]:
    """Load personal resume-name mapping (gitignored). Missing file → empty map,
    so public config/tests work; the dispatch stage fails loudly if a needed
    key is unresolved before it touches the device.
    """
    names_path = Path(path) if path else DEFAULT_NAMES
    if not names_path.exists():
        return {}
    with open(names_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"resume names must be a JSON object: {names_path}")
    return {str(k): str(v) for k, v in data.items()}


def _resolve(value: str, names: dict[str, str]) -> str:
    """Replace %KEY% placeholders with personal mapping values."""
    def sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in names:
            raise ValueError(
                f"resume name placeholder {key!r} unresolved; add it to "
                f"documents/dispatch/resume_names.json"
            )
        return names[key]
    return _PLACEHOLDER_RE.sub(sub, value)


def load_config(
    path: str | Path | None = None,
    names: dict[str, str] | None = None,
) -> dict:
    """Load the ladder config, resolving %KEY% resume placeholders.

    `names` comes from the gitignored personal mapping; pass an explicit dict
    in tests. If omitted entirely, an empty map is used (offline unit tests
    that only check stack/request logic set their own names).
    """
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    with open(cfg_path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    for key in ("rules", "fallback", "resume_request_patterns"):
        if key not in cfg:
            raise ValueError(f"resume ladder config missing key: {key!r}")
    if "resume" not in cfg["fallback"]:
        raise ValueError("resume ladder config fallback missing 'resume'")
    for rule in cfg["rules"]:
        if "patterns" not in rule or "resume" not in rule:
            raise ValueError(f"invalid ladder rule: {rule!r}")
    resolved_names = names if names is not None else load_names()
    cfg["fallback"]["resume"] = _resolve(cfg["fallback"]["resume"], resolved_names)
    for rule in cfg["rules"]:
        rule["resume"] = _resolve(rule["resume"], resolved_names)
    return cfg


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def _line_matches(text: str, patterns: list[re.Pattern]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _eligible_text_lines(text: str, cfg: dict,
                         *, excluded: list[re.Pattern] | None = None) -> list[str]:
    """Lines that can contain a recruiter's plain-text resume ask.

    UI chrome (`发简历`, `同意`, …), the candidate's own self-introduction and
    old 'already sent / received' messages are not requests. Negatives apply
    only to their own line: one stale line must not veto a later real ask.
    Terminal states (请求中 / 已发送) are handled separately for the whole
    conversation.
    """
    negatives = _compile(cfg.get("resume_request_negative_patterns", []))
    ignore = _compile(cfg.get("resume_request_ignore_patterns", []))
    self_patterns = _compile(cfg.get("resume_request_self_patterns", []))
    excluded = excluded or []
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _line_matches(line, ignore) or _line_matches(line, self_patterns):
            continue
        if _line_matches(line, negatives) or _line_matches(line, excluded):
            continue
        lines.append(line)
    return lines


def is_resume_request(text: str, cfg: dict) -> bool:
    """True if any eligible line asks the candidate to send a resume."""
    if not text:
        return False
    terminal = _compile(cfg.get("resume_request_terminal_negative_patterns", []))
    if _line_matches(text, terminal):
        return False
    positives = _compile(cfg["resume_request_patterns"])
    return any(_line_matches(line, positives)
               for line in _eligible_text_lines(text, cfg))


def is_explicit_request(text: str, cfg: dict) -> bool:
    """True only for an explicit 'send me your resume' ask from the recruiter.

    Stricter than is_resume_request: requires an action verb aimed at the
    resume, not merely the word 'resume' or a platform [简历] badge. Negative
    lines are skipped individually; terminal states veto the whole text.
    """
    if not text:
        return False
    terminal = _compile(cfg.get("resume_request_terminal_negative_patterns", []))
    if _line_matches(text, terminal):
        return False
    actions = _compile(cfg.get("explicit_request_patterns", []))
    return any(_line_matches(line, actions)
               for line in _eligible_text_lines(text, cfg))


def _match_any(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def detect_resume_request(text: str, cfg: dict) -> dict:
    """Detect a resume request from either the platform card or the text.

    BOSS renders the recruiter's resume request as a card:

        我想要一份您的附件简历，您是否同意
        拒绝
        同意

    so a card hit needs both the card sentence and the two answer buttons —
    the buttons are what distinguish the card from a plain text message that
    happens to quote the same sentence. Text hits use the explicit-request
    patterns. The two signals are OR-ed; negatives (already sent / received)
    win over both.

    Returns {"card": bool, "text": bool, "hit": bool, "source": str | None}
    where source is "card", "text", "card+text", or None.
    """
    if not text:
        return {"card": False, "text": False, "hit": False, "source": None}

    # Terminal states (resume request already answered / in flight) veto the
    # whole conversation. Ordinary negatives only veto their own line.
    terminal = _compile(cfg.get("resume_request_terminal_negative_patterns", []))
    if _line_matches(text, terminal):
        return {"card": False, "text": False, "hit": False, "source": None}

    card_patterns = _compile(cfg.get("resume_request_card_patterns", []))
    buttons = cfg.get("resume_request_card_buttons", ["同意", "拒绝"])
    card = bool(card_patterns) and any(p.search(text) for p in card_patterns)
    card = card and all(button in text for button in buttons)

    # The card sentence is rendered as a UI line; without its buttons it is a
    # quoted bubble, not a request. Either way it must not double-count as a
    # text hit. UI chrome and the candidate's own self-introduction lines are
    # excluded too; negatives are applied line by line.
    card_quotes = _compile(cfg.get("resume_request_card_quote_patterns", []))
    actions = _compile(cfg.get("explicit_request_patterns", []))
    text_lines = _eligible_text_lines(text, cfg, excluded=card_quotes)
    text_hit = any(_line_matches(line, actions) for line in text_lines)

    if card and text_hit:
        source = "card+text"
    elif card:
        source = "card"
    elif text_hit:
        source = "text"
    else:
        source = None
    return {"card": card, "text": text_hit, "hit": source is not None, "source": source}


def screen_candidate(item: dict, cfg: dict) -> dict:
    """Apply the four hard filters to a structured chat-list candidate.

    Expected item keys: contact, org (identity+company), city, role, snippet.
    Returns the item with `verdict` (pass/skip) and `reasons` list. Never raises
    on missing keys — absent fields are treated as unknown and, for the
    exclusion filters, as pass-through (the human is still the final gate).
    """
    reasons: list[dict] = []

    org = f"{item.get('org', '')} {item.get('company', '')}".strip()
    city = item.get("city", "") or ""
    role = item.get("role", "") or ""
    snippet = item.get("snippet", "") or ""

    # 1. resume request: platform card OR explicit text, either one is enough
    signals = detect_resume_request(snippet, cfg)
    if not signals["hit"]:
        reasons.append({"filter": "explicit_request",
                        "detail": "非明确索要简历（卡片与文本均未命中）"})

    # 2. outsourcing / headhunter (identity or company)
    hit = _match_any(f"{org} {snippet}", cfg.get("outsourcing_patterns", []))
    if not hit:
        hit = _match_any(snippet, cfg.get("outsourcing_project_patterns", []))
    if hit:
        reasons.append({"filter": "outsourcing", "detail": f"外包/猎头/人力关键词: {hit}"})

    # 3. non-Beijing. City info is often in `org` (e.g. "HR·深圳市新凯来")
    #    while `city` is empty, so scan the combined identity text. A local
    #    "北京" anchor anywhere in that text wins; otherwise any explicit
    #    non-local province/city blocks. Unknown location stays pass-through.
    local = cfg.get("local_city", "北京")
    location_text = f"{city} {org}".strip()
    if location_text and local not in location_text:
        hit_city = _match_any(location_text, cfg.get("non_beijing_patterns", []))
        if hit_city:
            reasons.append({"filter": "location", "detail": f"异地: {hit_city}"})

    # 4. algorithm/model-training role
    hit_role = _match_any(role, cfg.get("non_local_role_patterns", []))
    if hit_role:
        reasons.append({"filter": "algorithm_role", "detail": f"算法/模型训练岗不匹配: {hit_role}"})

    # 5. Language stack is selection metadata only (user rule 2026-11-26).
    #    It never blocks a conversation: Java/Go/Python pick their resume and
    #    anything else uses the fallback resume. Keep it on the result for
    #    reports and for the resume ladder.
    stack_text = f"{role} {snippet} {org}".strip()
    stack = infer_stack(stack_text, cfg)

    verdict = "pass" if not reasons else "skip"
    return {**item, "verdict": verdict, "reasons": reasons,
            "stack": stack,
            "request_card": signals["card"], "request_text": signals["text"],
            "request_source": signals["source"]}


def infer_stack(text: str, cfg: dict) -> str | None:
    """Return the id of the first matching stack rule, or None."""
    if not text:
        return None
    for rule in cfg["rules"]:
        if any(p.search(text) for p in _compile(rule["patterns"])):
            return rule["id"]
    return None


def pick_resume(text: str, cfg: dict) -> str:
    """Pick the exact resume version name for a message/JD snippet.

    First matching rule wins; if no stack is stated, use the fallback.
    User rule 2026-11-26: Java → JAVA resume, Go/Python → GO resume; no stated
    stack still uses the GO fallback for display/selection (it is no longer
    filtered out).
    """
    stack = infer_stack(text, cfg)
    if stack:
        for rule in cfg["rules"]:
            if rule["id"] == stack:
                return rule["resume"]
    return cfg["fallback"]["resume"]


def describe(text: str, cfg: dict) -> dict:
    """Convenience: stack + resume + whether the text asks for a resume."""
    return {
        "stack": infer_stack(text, cfg),
        "resume": pick_resume(text, cfg),
        "is_resume_request": is_resume_request(text, cfg),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("text", help="message / JD snippet to classify")
    ap.add_argument("--config", default=None)
    ap.add_argument("--names", default=None, help="personal resume-name mapping JSON")
    args = ap.parse_args()
    cfg = load_config(args.config, names=load_names(args.names))
    print(json.dumps(describe(args.text, cfg), ensure_ascii=False, indent=2))
