import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import (
    FocusTimer, add_task, blank_document, delete_task, find_task, load_document,
    move_task, new_task, rename_task, save_document, toggle_task,
    validate_document, validate_minutes
)


class FocusDeskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.json"
        self.data = blank_document()

    def test_initial_state_and_roundtrip(self):
        self.assertEqual(self.data["tasks"], [])
        save_document(self.path, self.data)
        self.assertEqual(load_document(self.path), (self.data, False))

    def test_task_crud_and_order(self):
        a = add_task(self.data, "Plan research")
        b = add_task(self.data, "Write report")
        rename_task(self.data, a, "Research plan")
        toggle_task(self.data, b)
        self.assertTrue(move_task(self.data, b, -1))
        self.assertEqual(self.data["tasks"][0]["id"], b)
        self.assertTrue(self.data["tasks"][0]["done"])
        self.assertEqual(self.data["tasks"][1]["title"], "Research plan")
        delete_task(self.data, a)
        self.assertEqual(len(self.data["tasks"]), 1)
        self.assertEqual(find_task(self.data, b), 0)

    def test_empty_and_invalid_task(self):
        for title in ("", "  ", "x" * 181, "bad\nname", "broken" + chr(0xD800)):
            with self.subTest(title=repr(title)):
                with self.assertRaises(ValueError):
                    new_task(title)
        with self.assertRaises(ValueError):
            delete_task(self.data, "missing")

    def test_task_limit(self):
        for i in range(200):
            add_task(self.data, str(i))
        with self.assertRaisesRegex(ValueError, "Maximum"):
            add_task(self.data, "overflow")

    def test_move_boundaries(self):
        a = add_task(self.data, "First")
        self.assertFalse(move_task(self.data, a, -1))
        self.assertFalse(move_task(self.data, a, 1))

    def test_invalid_duration(self):
        for value in (0, 181, True, 3.5, "25", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_minutes(value)

    def test_timer_pause_resume(self):
        now = [100.0]
        timer = FocusTimer(1, clock=lambda: now[0])
        timer.start()
        now[0] += 12.4
        timer.pause()
        self.assertAlmostEqual(timer.remaining, 47.6)
        now[0] += 1000
        self.assertAlmostEqual(timer.tick(), 47.6)
        timer.resume()
        now[0] += 47.7
        timer.tick()
        self.assertEqual(timer.state, "finished")
        self.assertEqual(timer.remaining, 0)

    def test_timer_reset_and_validation(self):
        now = [0.0]
        timer = FocusTimer(2, clock=lambda: now[0])
        timer.start()
        with self.assertRaises(ValueError):
            timer.set_minutes(3)
        timer.reset()
        timer.set_minutes(3)
        self.assertEqual(timer.display(), "03:00")
        with self.assertRaises(ValueError):
            timer.pause()

    def test_interrupted_session_reloads_without_countdown(self):
        self.data["session"] = "interrupted"
        save_document(self.path, self.data)
        restored, recovered = load_document(self.path)
        self.assertFalse(recovered)
        self.assertEqual(restored["session"], "interrupted")
        timer = FocusTimer(restored["minutes"])
        self.assertEqual(timer.state, "idle")
        self.assertEqual(timer.display(), "25:00")

    def test_backup_recovery(self):
        add_task(self.data, "Original")
        save_document(self.path, self.data)
        add_task(self.data, "Latest")
        save_document(self.path, self.data)
        self.path.write_text("{damaged", encoding="utf-8")
        restored, recovered = load_document(self.path)
        self.assertTrue(recovered)
        self.assertEqual(len(restored["tasks"]), 1)

    def test_invalid_state_and_duplicate_keys(self):
        self.path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cannot be read"):
            load_document(self.path)
        self.path.write_text(json.dumps({"schema": 2}), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_document(self.path)

    def test_bad_surrogate_and_duplicate_task_ids(self):
        ident = add_task(self.data, "Normal")
        self.data["tasks"].append(dict(self.data["tasks"][0]))
        with self.assertRaises(ValueError):
            validate_document(self.data)
        self.data["tasks"].pop()
        rename_task(self.data, ident, "Safe")
        self.data["tasks"][0]["title"] = "bad" + chr(0xD800)
        with self.assertRaises(ValueError):
            save_document(self.path, self.data)

    def test_corrupt_file_no_silent_reset(self):
        self.path.write_text("not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_document(self.path)
        self.assertEqual(self.path.read_text(), "not json")

    def test_atomic_write_failure_preserves_original(self):
        from unittest.mock import patch
        save_document(self.path, self.data)
        before = self.path.read_bytes()
        add_task(self.data, "Change")
        with patch("main.os.replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                save_document(self.path, self.data)
        self.assertEqual(self.path.read_bytes(), before)

    def test_deep_json_rejected(self):
        self.path.write_text("[" * 5000 + "0" + "]" * 5000, encoding="utf-8")
        with self.assertRaises(ValueError):
            load_document(self.path)

    def test_gui_build_uses_existing_timer_frame(self):
        """Prevent the headless-invisible Tkinter NameError at first launch."""
        import ast
        import inspect
        import textwrap
        from main import Desk
        tree = ast.parse(textwrap.dedent(inspect.getsource(Desk.build)))
        self.assertFalse(
            [node for node in ast.walk(tree)
             if isinstance(node, ast.Name) and node.id == "timer_area"],
            "Desk.build must use self.timer_area, not an undefined local timer_area",
        )

    def test_gui_first_launch_or_headless_static_fallback(self):
        """Construct widgets when DISPLAY exists; otherwise check static safety."""
        import tkinter as tk
        from main import Desk
        try:
            root = tk.Tk()
        except tk.TclError:
            # Factory's deterministic headless runner rejects skipped tests.
            # This fallback does NOT constitute graphical QA.
            import ast
            import inspect
            import textwrap
            tree = ast.parse(textwrap.dedent(inspect.getsource(Desk.build)))
            self.assertFalse([n for n in ast.walk(tree)
                              if isinstance(n, ast.Name) and n.id == "timer_area"])
            return
        try:
            app = Desk(root, path=self.path)
            self.assertEqual(app.timer_state.winfo_exists(), 1)
            self.assertEqual(app.timer_area.winfo_exists(), 1)
        finally:
            root.destroy()

    def test_english_japanese_labels_exist(self):
        from main import WORDS
        self.assertEqual(set(WORDS["en"]), set(WORDS["ja"]))
        self.assertTrue(WORDS["ja"]["name"])
        self.assertTrue(WORDS["en"]["name"])


    def test_disk_failure_rolls_back_task_timer_and_language(self):
        """The visible model must not claim an edit that was not saved."""
        from unittest.mock import patch
        from main import Desk

        class FakeVar:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        desk = Desk.__new__(Desk)
        desk.data = blank_document()
        desk.lang = "ja"
        desk.timer = FocusTimer(25, clock=lambda: 10.0)
        desk.entry_var = FakeVar("typed task")
        desk.minutes_var = FakeVar("25")
        desk.words = lambda key: "Action failed"
        desk.relabel = lambda: None
        desk.refresh = lambda: None

        def fail_save():
            raise OSError("disk full")

        desk.save = fail_save

        def change_all():
            add_task(desk.data, "unsaved task")
            desk.timer.start()
            desk.lang = "en"
            desk.entry_var.set("")

        with patch("main.messagebox.showerror") as error:
            self.assertFalse(desk.action(change_all))
            error.assert_called_once()
        self.assertEqual(desk.data, blank_document())
        self.assertEqual(desk.timer.state, "idle")
        self.assertEqual(desk.timer.remaining, 25 * 60)
        self.assertEqual(desk.lang, "ja")
        self.assertEqual(desk.entry_var.get(), "typed task")
        self.assertEqual(desk.minutes_var.get(), "25")

    def test_successful_action_saves_and_refreshes(self):
        from main import Desk

        class FakeVar:
            def get(self):
                return "25"

        desk = Desk.__new__(Desk)
        desk.data = blank_document()
        desk.lang = "ja"
        desk.timer = FocusTimer(25)
        desk.entry_var = FakeVar()
        desk.minutes_var = FakeVar()
        events = []
        desk.save = lambda: events.append("save")
        desk.refresh = lambda: events.append("refresh")
        self.assertTrue(desk.action(lambda: add_task(desk.data, "Saved")))
        self.assertEqual(events, ["save", "refresh"])
        self.assertEqual(len(desk.data["tasks"]), 1)



if __name__ == "__main__":
    unittest.main()
