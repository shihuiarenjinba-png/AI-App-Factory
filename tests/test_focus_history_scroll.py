"""Focus history must show all saved sessions, not silently truncate at 30."""
import importlib.util
import inspect
from pathlib import Path
import unittest

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "focus-session-desk" / "main.py"
spec = importlib.util.spec_from_file_location("focus_history_product", PRODUCT)
focus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(focus)


class FocusHistoryScrollTests(unittest.TestCase):
    def test_history_rows_show_all_500_newest_first(self):
        document = focus.blank_document()
        for i in range(500):
            focus.record_completed_session(document, 1 + i % 50, "2026-10-30")
        rows = focus.history_rows(document)
        self.assertEqual(len(rows), 500)
        self.assertEqual(rows[0], ("2026-10-30", 50))
        self.assertEqual(rows[-1], ("2026-10-30", 1))
        self.assertEqual(focus.today_totals(document, "2026-10-30")[0], 500)

    def test_empty_and_legacy_documents(self):
        self.assertEqual(focus.history_rows(focus.blank_document()), [])
        legacy = focus.blank_document()
        del legacy["history"]
        self.assertEqual(focus.history_rows(legacy), [])

    def test_bilingual_scrollable_history_not_messagebox_truncated(self):
        for language in ("ja", "en"):
            for key in ("history", "history_date", "history_minutes", "close"):
                self.assertTrue(focus.WORDS[language][key])
        source = inspect.getsource(focus.Desk.show_history)
        self.assertIn("tk.Toplevel", source)
        self.assertIn("ttk.Treeview", source)
        self.assertIn("ttk.Scrollbar", source)
        self.assertNotIn("[:30]", source)


if __name__ == "__main__":
    unittest.main()
