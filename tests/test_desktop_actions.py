"""Offline tests for dynamic app discovery, fallbacks, and safe command routing."""
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from aurix.actions import desktop


class TestDesktopActions(unittest.TestCase):
    @patch("aurix.actions.desktop._find_installed_app", return_value=None)
    @patch("aurix.actions.desktop._open_url", return_value=True)
    def test_site_fallback_opens_website_when_app_missing(self, open_url, find_app):
        result = desktop.handle_desktop_command("open youtube")
        self.assertIn("YouTube", result)
        self.assertIn("couldn't find the installed desktop app", result)
        open_url.assert_called_once_with("https://www.youtube.com/")

    @patch("aurix.actions.desktop._launch_app", return_value=True)
    @patch("aurix.actions.desktop._find_installed_app", return_value=desktop.InstalledApp("WhatsApp", "appid", "WhatsApp.App"))
    @patch("aurix.actions.desktop._open_url")
    def test_installed_app_wins_over_website_fallback(self, open_url, find_app, launch):
        result = desktop.handle_desktop_command("open WhatsApp")
        self.assertIn("Opening installed application: WhatsApp", result)
        launch.assert_called_once()
        open_url.assert_not_called()

    @patch("aurix.actions.desktop._launch_app", return_value=True)
    @patch("aurix.actions.desktop._find_installed_app", return_value=desktop.InstalledApp("WhatsApp", "appid", "WhatsApp.App"))
    def test_action_response_uses_selected_spanish_language(self, find_app, launch):
        result = desktop.handle_desktop_command("open WhatsApp", language="es-ES")
        self.assertIn("Abriendo la aplicación instalada", result)
        launch.assert_called_once()

    @patch("aurix.actions.desktop._open_url", return_value=True)
    def test_telugu_action_response_is_localized(self, open_url):
        result = desktop.handle_desktop_command("వాట్సాప్ తెరువు", language="te-IN")
        self.assertIn("వెబ్", result) if "వెబ్" in result else self.assertIn("బ్రౌజర్", result)

    @patch("aurix.actions.desktop._open_url", return_value=True)
    def test_video_search_opens_youtube_results_directly(self, open_url):
        result = desktop.handle_desktop_command("play lofi hip hop on YouTube")
        self.assertIn("Searching YouTube", result)
        url = open_url.call_args.args[0]
        parsed = urlparse(url)
        self.assertEqual(parsed.hostname, "www.youtube.com")
        self.assertEqual(parsed.path, "/results")
        self.assertEqual(parse_qs(parsed.query)["search_query"], ["lofi hip hop"])

    @patch("aurix.actions.desktop.webbrowser.open_new_tab", return_value=True)
    def test_open_browser_uses_default_browser(self, open_tab):
        result = desktop.handle_desktop_command("open browser")
        self.assertIn("default browser", result)
        open_tab.assert_called_once_with("about:blank")

    @patch("aurix.actions.desktop.subprocess.Popen")
    @patch("aurix.actions.desktop._find_installed_app")
    def test_direct_executable_command_is_rejected(self, find_app, popen):
        result = desktop.handle_desktop_command("open cmd.exe")
        self.assertIn("won't launch a direct executable path", result)
        find_app.assert_not_called()
        popen.assert_not_called()

    def test_regular_conversation_is_not_a_desktop_action(self):
        self.assertIsNone(desktop.handle_desktop_command("Explain machine learning"))

    def test_spanish_open_command_is_parsed(self):
        self.assertEqual(desktop.parse_open_request("abre WhatsApp"), "WhatsApp")

    def test_telugu_open_command_is_parsed(self):
        self.assertEqual(desktop.parse_open_request("వాట్సాప్ తెరువు"), "whatsapp")

    @patch("aurix.actions.desktop._windows_start_apps", return_value=(("WhatsApp", "WhatsApp.App"),))
    def test_dynamic_start_app_inventory(self, _apps):
        self.assertEqual(
            desktop._find_start_app_id("whatsapp"),
            ("WhatsApp", "WhatsApp.App"),
        )

    def test_known_app_without_website_reports_not_found(self):
        with patch("aurix.actions.desktop._find_installed_app", return_value=None):
            result = desktop.handle_desktop_command("open an app that does not exist")
        self.assertIn("was not found", result)
        self.assertIn("No command was executed", result)


if __name__ == "__main__":
    unittest.main()
