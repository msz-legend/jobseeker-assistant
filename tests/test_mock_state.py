import tempfile
import unittest
from pathlib import Path

from tools import mock_state


class MockStateTests(unittest.TestCase):
    def test_create_validate_and_resume_turn(self):
        state = mock_state.new_state("example-application")
        state["question_pool"]["evidence_verification"].append({
            "id": "evidence-001", "section": "evidence_verification", "question": "What changed?",
            "source_evidence": {"file": "example.md", "heading": "Experience", "excerpt": "redacted"},
            "follow_ups": [], "evaluation_rubric": {"pass": [], "warning": [], "fail": []},
            "reference_answer": "hidden", "transfer_link": "",
        })
        mock_state.add_turn(state, "evidence-001", "A bounded answer")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mock.json"
            mock_state.save(path, state)
            loaded = mock_state.load(path)
        self.assertEqual(loaded["session"]["status"], "in_progress")
        self.assertEqual(loaded["session"]["turns"][0]["answer"], "A bounded answer")

    def test_rejects_missing_question_contract(self):
        state = mock_state.new_state("example")
        state["question_pool"]["evidence_verification"].append({"id": "bad"})
        with self.assertRaises(ValueError):
            mock_state.validate(state)


if __name__ == "__main__":
    unittest.main()
