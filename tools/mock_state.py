#!/usr/bin/env python3
"""Small, deterministic mock-interview state machine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SECTIONS = ("evidence_verification", "capability_expansion", "transfer_scenarios")
STATUSES = {"not_started", "in_progress", "completed"}


def new_state(application_id: str, domain: str = "generic", stage: str = "first_interview") -> dict:
    return {
        "schema_version": "1.0",
        "application_id": application_id,
        "domain": domain,
        "stage": stage,
        "source_files": [],
        "question_pool": {section: [] for section in SECTIONS},
        "session": {"status": "not_started", "current_section": SECTIONS[0], "current_question_id": None, "turns": []},
        "assessment": {"section_scores": {}, "strengths": [], "gaps": [], "mistakes": [], "next_actions": []},
    }


def validate(state: dict) -> None:
    if not isinstance(state, dict) or state.get("schema_version") != "1.0":
        raise ValueError("invalid mock state schema")
    session = state.get("session", {})
    if session.get("status") not in STATUSES:
        raise ValueError("invalid session status")
    if session.get("current_section") not in SECTIONS:
        raise ValueError("invalid current section")
    for section in SECTIONS:
        if not isinstance(state.get("question_pool", {}).get(section), list):
            raise ValueError(f"question_pool.{section} must be a list")
        for question in state["question_pool"][section]:
            for field in ("id", "section", "question", "source_evidence", "follow_ups", "evaluation_rubric", "reference_answer", "transfer_link"):
                if field not in question:
                    raise ValueError(f"question missing {field}")
            if question["section"] != section:
                raise ValueError("question section mismatch")


def load(path: Path) -> dict:
    state = json.loads(path.read_text(encoding="utf-8"))
    validate(state)
    return state


def save(path: Path, state: dict) -> None:
    validate(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_turn(state: dict, question_id: str, answer: str, verdict: str = "", followups: list[str] | None = None) -> dict:
    validate(state)
    known = {q["id"] for section in SECTIONS for q in state["question_pool"][section]}
    if question_id not in known:
        raise ValueError("unknown question id")
    state["session"]["status"] = "in_progress"
    state["session"]["current_question_id"] = question_id
    state["session"]["turns"].append({"question_id": question_id, "answer": answer, "verdict": verdict, "followups": followups or []})
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("path", type=Path)
    create.add_argument("application_id")
    create.add_argument("--domain", default="generic")
    create.add_argument("--stage", default="first_interview")
    show = sub.add_parser("show")
    show.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        save(args.path, new_state(args.application_id, args.domain, args.stage))
        print(args.path)
    else:
        state = load(args.path)
        print(json.dumps({"status": state["session"]["status"], "section": state["session"]["current_section"], "turns": len(state["session"]["turns"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
