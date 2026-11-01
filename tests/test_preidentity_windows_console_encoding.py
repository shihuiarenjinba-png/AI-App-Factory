"""Windows cp1252/ASCII consoles must not break Japanese APP EXE receipts."""
import io
import json
import unittest
from unittest.mock import patch
from tools.build_windows_exe import main


class ConsoleEncodingTests(unittest.TestCase):
    def test_japanese_display_name_prints_on_ascii_console(self):
        result = {"display_name": "個人事業帳簿ローカル", "status": "EXE_QA_UNSIGNED",
                  "source_sha": "a" * 40}
        output = io.BytesIO()
        writer = io.TextIOWrapper(output, encoding="ascii", errors="strict")
        with patch("tools.build_windows_exe.build_exe", return_value=result), patch("sys.stdout", writer):
            self.assertEqual(main(["--slug", "jp-freelance-ledger", "--expected-sha",
                                   "a" * 40, "--output", "unused"]), 0)
            writer.flush()
        self.assertEqual(json.loads(output.getvalue().decode("ascii")), result)


if __name__ == "__main__": unittest.main()
