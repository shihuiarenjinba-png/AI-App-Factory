"""Headless regression: a finished but unsaved session cannot be replaced."""
import importlib.util
from pathlib import Path
import unittest


PRODUCT = Path(__file__).resolve().parents[1] / "products" / "focus-session-desk" / "main.py"
spec = importlib.util.spec_from_file_location("focus_pending_guard_product", PRODUCT)
focus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(focus)


class FakeLabel:
    def __init__(self):
        self.text = None

    def configure(self, **kwargs):
        self.text = kwargs["text"]


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class PendingCompletionGuardTests(unittest.TestCase):
    def test_pending_completion_blocks_edits_and_preserves_duration(self):
        desk = focus.Desk.__new__(focus.Desk)
        desk.data = focus.blank_document()
        desk.lang = "ja"
        desk.timer = focus.FocusTimer(25, clock=lambda: 100.0)
        desk.timer.state = "finished"
        desk.timer.remaining = 0.0
        desk._completion_pending = True
        desk.status = FakeLabel()
        desk.entry_var = FakeVar("Do not discard")
        desk.minutes_var = FakeVar("50")
        events = []
        desk.save = lambda: events.append("save")
        desk.refresh = lambda: events.append("refresh")
        desk.words = lambda key: focus.WORDS[desk.lang][key]

        self.assertFalse(desk.action(lambda: desk.timer.reset()))
        self.assertFalse(desk.action(lambda: desk.timer.set_minutes(50)))
        self.assertFalse(desk.action(lambda: focus.add_task(desk.data, "unsaved")))
        self.assertFalse(desk.action(lambda: setattr(desk, "lang", "en")))
        self.assertEqual(desk.timer.minutes, 25)
        self.assertEqual(desk.timer.state, "finished")
        self.assertEqual(desk.data["tasks"], [])
        self.assertEqual(desk.lang, "ja")
        self.assertEqual(events, [])
        self.assertEqual(desk.status.text, focus.WORDS["ja"]["completion_unsaved"])

        # The retry loop clears this flag only after a durable save.
        desk._completion_pending = False
        self.assertTrue(desk.action(lambda: focus.add_task(desk.data, "saved")))
        self.assertEqual([t["title"] for t in desk.data["tasks"]], ["saved"])
        self.assertEqual(events, ["save", "refresh"])

    def test_pending_warning_is_localized(self):
        for language in ("ja", "en"):
            self.assertTrue(focus.WORDS[language]["completion_unsaved"])


if __name__ == "__main__":
    unittest.main()
