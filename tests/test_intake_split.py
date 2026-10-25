import unittest

from tools.intake_split import split_segments


class IntakeSplitTests(unittest.TestCase):
    def test_splits_ten_segments_and_flags_weak_input(self):
        text = "\n---\n".join(f"Role {i}\nRequirement {i}" for i in range(10))
        segments = split_segments(text)
        self.assertEqual(len(segments), 10)
        self.assertEqual([item.ordinal for item in segments], list(range(1, 11)))
        self.assertFalse(any(item.needs_review for item in segments))

    def test_empty_and_weak_segments_are_safe(self):
        segments = split_segments("Title only\n---\n\n---\nAnother\nDetail")
        self.assertEqual([item.title for item in segments], ["Title only", "Another"])
        self.assertTrue(segments[0].needs_review)
        self.assertFalse(segments[1].needs_review)


if __name__ == "__main__":
    unittest.main()
