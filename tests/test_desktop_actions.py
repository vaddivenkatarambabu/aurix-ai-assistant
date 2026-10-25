"""Offline tests for safe desktop action routing."""

import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from aurix.actions.desktop import handle_desktop_command


class TestDesktopActions(unittest.TestCase):
    @patch(
        "aurix.actions.desktop.webbrowser.open_new_tab",
        return_value=True,
    )
    def test_open_youtube(self, open_tab):
        result = handle_desktop_command("open youtube")

        self.assertIn("YouTube", result)
        open_tab.assert_called_once_with("https://www.youtube.com/")

    @patch(
        "aurix.actions.desktop.webbrowser.open_new_tab",
        return_value=True,
    )
    def test_open_browser(self, open_tab):
        result = handle_desktop_command("open browser")

        self.assertIn("browser", result)
        open_tab.assert_called_once_with("about:blank")

    @patch(
        "aurix.actions.desktop.webbrowser.open_new_tab",
        return_value=True,
    )
    def test_search_query_is_url_encoded(self, open_tab):
        result = handle_desktop_command("search for python & powershell")

        self.assertIn("Google", result)

        opened_url = open_tab.call_args.args[0]
        parsed = urlparse(opened_url)

        self.assertEqual(parsed.hostname, "www.google.com")
        self.assertEqual(
            parse_qs(parsed.query)["q"][0],
            "python & powershell",
        )

    @patch("aurix.actions.desktop.subprocess.Popen")
    def test_unknown_application_is_not_executed(self, popen):
        result = handle_desktop_command("open cmd.exe")

        self.assertIn("won't execute arbitrary system commands", result)
        popen.assert_not_called()

    def test_normal_question_goes_to_ai(self):
        result = handle_desktop_command("Explain what machine learning is.")

        self.assertIsNone(result)

    @unittest.skipUnless(os.name == "nt", "Windows-specific app launcher")
    def test_open_notepad_uses_safe_process_arguments(self):
        fake_executable = r"C:\Windows\System32\notepad.exe"

        with (
            patch(
                "aurix.actions.desktop.shutil.which",
                return_value=fake_executable,
            ),
            patch("aurix.actions.desktop.subprocess.Popen") as popen,
        ):
            result = handle_desktop_command("open notepad")

        self.assertIn("Notepad", result)
        popen.assert_called_once_with(
            [fake_executable],
            shell=False,
        )


if __name__ == "__main__":
    unittest.main()
