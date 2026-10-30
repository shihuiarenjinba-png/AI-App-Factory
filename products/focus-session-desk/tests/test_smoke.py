import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import (
    FocusTimer, add_task, blank_document, delete_task, find_task, load_document,
    move_task, new_task, rename_task, save_document, toggle_task,
    validate_document, validate_minutes, initial_window_geometry, FOCUS_PRESETS
)


class FocusDeskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.json"
        self.data = blank_document()

    def test_window_geometry_keeps_1024x768_controls_above_taskbar(self):
        self.assertEqual(initial_window_geometry(1024, 768), "940x620+42+20")
        self.assertEqual(initial_window_geometry(1280, 720), "940x620+170+20")
        self.assertEqual(initial_window_geometry(1920, 1080), "940x620+490+20")
        for width, height in ((800, 600), (1024, 600), (True, 768)):
            with self.subTest(width=width, height=height):
                with self.assertRaises(ValueError):
                    initial_window_geometry(width, height)

    def test_completed_session_disk_failure_does_not_create_phantom_history(self):
        from unittest.mock import patch
        from main import persist_completed_session, today_totals
        save_document(self.path, self.data)
        before = self.path.read_bytes()
        with patch("main.save_document", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                persist_completed_session(self.data, self.path, 25, "2026-10-30")
        self.assertEqual(today_totals(self.data, "2026-10-30"), (0, 0))
        self.assertEqual(self.path.read_bytes(), before)
        persisted = persist_completed_session(self.data, self.path, 25, "2026-10-30")
        self.assertEqual(today_totals(persisted, "2026-10-30"), (1, 25))
        self.assertEqual(today_totals(self.data, "2026-10-30"), (0, 0))
        self.assertEqual(load_document(self.path)[0]["history"], persisted["history"])

    def test_finished_timer_retries_without_double_counting(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from main import Desk
        now = [100.0]
        desk = Desk.__new__(Desk)
        desk.data = blank_document()
        desk.path = self.path
        desk.timer = FocusTimer(1, clock=lambda: now[0])
        desk.timer.start()
        desk._completion_pending = False
        desk._completion_retry_after = 0.0
        desk._completion_error_shown = False
        desk.words = lambda key: key
        labels = []
        fake = SimpleNamespace(configure=lambda **kwargs: labels.append(kwargs))
        desk.clock_label = desk.timer_state = desk.status = fake
        desk.root = SimpleNamespace(after=lambda *args: None)
        refreshed = []
        desk.refresh = lambda: refreshed.append(True)
        now[0] += 61
        with patch("main.save_document", side_effect=OSError("disk full")), \
             patch("main.messagebox.showerror") as error, \
             patch("main.messagebox.showinfo") as info:
            desk.tick()
            self.assertTrue(desk._completion_pending)
            self.assertEqual(desk.data["history"], [])
            self.assertEqual(error.call_count, 1)
            info.assert_not_called()
        # An immediate timer tick does not hammer the disk or repeat the dialog.
        with patch("main.save_document", side_effect=AssertionError("retry too early")):
            desk.tick()
        desk._completion_retry_after = 0.0
        with patch("main.messagebox.showinfo") as info:
            desk.tick()
            info.assert_called_once()
        self.assertFalse(desk._completion_pending)
        self.assertEqual(len(desk.data["history"]), 1)
        self.assertEqual(len(load_document(self.path)[0]["history"]), 1)
        desk.tick()
        self.assertEqual(len(desk.data["history"]), 1)
        self.assertEqual(len(refreshed), 1)

    def test_close_refuses_to_lose_unsaved_finished_session(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from main import Desk
        desk = Desk.__new__(Desk)
        desk.data = blank_document()
        desk.path = self.path
        desk.timer = FocusTimer(25)
        desk.timer.state = "finished"
        desk._completion_pending = True
        desk.words = lambda key: key
        destroyed = []
        desk.root = SimpleNamespace(destroy=lambda: destroyed.append(True))
        desk.save = lambda: None
        with patch("main.save_document", side_effect=OSError("disk full")), \
             patch("main.messagebox.showerror") as error:
            desk.close()
            error.assert_called_once()
        self.assertEqual(destroyed, [])
        self.assertTrue(desk._completion_pending)
        desk.close()
        self.assertEqual(destroyed, [True])
        self.assertEqual(len(load_document(self.path)[0]["history"]), 1)

    def test_completed_history_roundtrip_and_daily_totals(self):
        from main import record_completed_session, today_totals
        record_completed_session(self.data, 25, "2026-10-30")
        record_completed_session(self.data, 50, "2026-10-30")
        record_completed_session(self.data, 25, "2026-10-29")
        self.assertEqual(today_totals(self.data, "2026-10-30"), (2, 75))
        self.assertEqual(today_totals(self.data, "2026-10-29"), (1, 25))
        save_document(self.path, self.data)
        restored, recovered = load_document(self.path)
        self.assertFalse(recovered)
        self.assertEqual(restored["history"], self.data["history"])

    def test_legacy_schema_one_loads_without_losing_tasks(self):
        add_task(self.data, "Keep me")
        legacy = dict(self.data)
        legacy.pop("history")
        self.path.write_text(json.dumps(legacy), encoding="utf-8")
        restored, recovered = load_document(self.path)
        self.assertFalse(recovered)
        self.assertEqual(restored["tasks"], legacy["tasks"])
        self.assertEqual(restored["history"], [])
        save_document(self.path, restored)
        self.assertEqual(load_document(self.path)[0]["tasks"], legacy["tasks"])

    def test_invalid_history_rejected_and_backup_recovers(self):
        from main import record_completed_session
        record_completed_session(self.data, 25, "2026-10-30")
        save_document(self.path, self.data)
        save_document(self.path, self.data)
        bad = dict(self.data)
        bad["history"] = [dict(self.data["history"][0], day="2026-02-30")]
        self.path.write_text(json.dumps(bad), encoding="utf-8")
        restored, recovered = load_document(self.path)
        self.assertTrue(recovered)
        self.assertEqual(restored["history"], self.data["history"])
        bad["history"] = self.data["history"] * 2
        with self.assertRaises(ValueError):
            validate_document(bad)

    def test_history_bounded_and_never_counts_unfinished_timer(self):
        from main import record_completed_session, today_totals, MAX_HISTORY
        timer = FocusTimer(25, clock=lambda: 100.0)
        timer.start()
        timer.pause()
        self.assertEqual(today_totals(self.data, "2026-10-30"), (0, 0))
        for _ in range(MAX_HISTORY + 1):
            record_completed_session(self.data, 1, "2026-10-30")
        self.assertEqual(len(self.data["history"]), MAX_HISTORY)
        self.assertEqual(today_totals(self.data, "2026-10-30"), (MAX_HISTORY, MAX_HISTORY))

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

    def test_one_click_focus_presets_and_active_session_guard(self):
        from main import Desk
        self.assertEqual(FOCUS_PRESETS, (25, 50))
        values = []

        class MinutesVar:
            def set(self, value):
                values.append(value)

        desk = Desk.__new__(Desk)
        desk.timer = FocusTimer(25, clock=lambda: 10.0)
        desk.minutes_var = MinutesVar()

        def action(fn):
            try:
                fn()
            except ValueError:
                return False
            return True

        desk.action = action
        self.assertTrue(desk.start_preset(50))
        self.assertEqual(desk.timer.minutes, 50)
        self.assertEqual(desk.timer.state, "running")
        self.assertEqual(values, ["50"])
        self.assertFalse(desk.start_preset(25))
        self.assertEqual(desk.timer.minutes, 50)
        self.assertEqual(values, ["50"])
        desk.timer.reset()
        self.assertTrue(desk.start_preset(25))
        self.assertEqual(desk.timer.minutes, 25)
        self.assertEqual(values, ["50", "25"])
        with self.assertRaisesRegex(ValueError, "Unsupported focus preset"):
            desk.start_preset(15)

    def test_preset_buttons_have_bilingual_labels(self):
        from main import WORDS
        for lang in ("ja", "en"):
            self.assertTrue(WORDS[lang]["preset_25"])
            self.assertTrue(WORDS[lang]["preset_50"])

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
            self.assertEqual(set(app.preset_buttons), {25, 50})
            for button in app.preset_buttons.values():
                self.assertTrue(button.winfo_exists())
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
