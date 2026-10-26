"""Offline tests for application and website resolution; no real launches."""
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
        open_url.assert_called_once_with("https://www.youtube.com/")

    @patch("aurix.actions.desktop._launch_app", return_value=True)
    @patch("aurix.actions.desktop._find_installed_app", return_value=desktop.InstalledApp("WhatsApp", "appid", "WhatsApp.App"))
    @patch("aurix.actions.desktop._open_url")
    def test_explicit_app_wins_over_website(self, open_url, find_app, launch):
        result = desktop.handle_desktop_command("open WhatsApp app")
        self.assertIn("Opening installed application: WhatsApp", result)
        launch.assert_called_once()
        open_url.assert_not_called()

    @patch("aurix.actions.desktop._launch_app", return_value=True)
    @patch("aurix.actions.desktop._find_installed_app", return_value=desktop.InstalledApp("WhatsApp", "appid", "WhatsApp.App"))
    def test_action_response_uses_selected_spanish_language(self, find_app, launch):
        result = desktop.handle_desktop_command("open WhatsApp app", language="es-ES")
        self.assertIn("Abriendo la aplicación instalada", result)
        launch.assert_called_once()

    @patch("aurix.actions.desktop._find_installed_app", return_value=None)
    @patch("aurix.actions.desktop._open_url", return_value=True)
    def test_telugu_website_response_is_localized(self, open_url, _find_app):
        result = desktop.handle_desktop_command("వాట్సాప్ వెబ్‌సైట్ తెరువు", language="te-IN")
        self.assertRegex(result, r"[\u0C00-\u0C7F]")
        open_url.assert_called_once_with("https://web.whatsapp.com/")

    @patch("aurix.actions.desktop._open_url", return_value=True)
    def test_video_search_opens_youtube_results_directly(self, open_url):
        result = desktop.handle_desktop_command("play lofi hip hop on YouTube")
        self.assertIn("Searching YouTube", result)
        parsed = urlparse(open_url.call_args.args[0])
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
        self.assertIn("direct executable path", result)
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
        self.assertEqual(desktop._find_start_app_id("whatsapp"), ("WhatsApp", "WhatsApp.App"))

    def test_known_app_without_website_reports_not_found(self):
        with patch("aurix.actions.desktop._find_installed_app", return_value=None):
            result = desktop.handle_desktop_command("open unknownthing")
        self.assertIn("was not found", result)
        self.assertIn("No command was executed", result)

    @patch("aurix.actions.desktop._find_installed_app")
    @patch("aurix.actions.desktop._open_url", return_value=True)
    def test_jio_website_opens_in_default_browser(self, open_url, find_app):
        result = desktop.handle_desktop_command("open Jio website")
        self.assertIn("default browser", result)
        open_url.assert_called_once_with("https://www.jio.com/")
        find_app.assert_not_called()

    @patch("aurix.actions.desktop._find_installed_app")
    @patch("aurix.actions.desktop._open_url", return_value=True)
    def test_google_defaults_to_website(self, open_url, find_app):
        result = desktop.handle_desktop_command("open Google")
        self.assertIn("default browser", result)
        open_url.assert_called_once_with("https://www.google.com/")
        find_app.assert_not_called()

    @patch("aurix.actions.desktop._find_installed_app", return_value=desktop.InstalledApp("Chrome", "executable", "C:/Chrome/chrome.exe"))
    @patch("aurix.actions.desktop._launch_app", return_value=True)
    @patch("aurix.actions.desktop._open_url")
    def test_explicit_chrome_app_launches_installed_application(self, open_url, launch, _find_app):
        result = desktop.handle_desktop_command("open Chrome app")
        self.assertIn("Opening installed application: Chrome", result)
        launch.assert_called_once()
        open_url.assert_not_called()

    def test_unsafe_url_schemes_and_credentials_are_rejected(self):
        self.assertFalse(desktop._is_valid_web_url("javascript:alert(1)"))
        self.assertFalse(desktop._is_valid_web_url("file:///C:/Windows/win.ini"))
        self.assertFalse(desktop._is_valid_web_url("https://user:pass@example.com/"))
        self.assertTrue(desktop._is_valid_web_url("https://example.com/path"))

    @patch("aurix.actions.desktop._open_url")
    def test_unknown_bare_name_is_not_guessed_as_website(self, open_url):
        result = desktop.handle_desktop_command("open unknownproduct")
        self.assertIn("was not found", result)
        open_url.assert_not_called()

    @patch("aurix.actions.desktop.webbrowser.open_new_tab", return_value=True)
    def test_explicit_url_uses_default_browser(self, open_tab):
        result = desktop.handle_desktop_command("open https://example.com/path")
        self.assertIn("Opening the requested website", result)
        open_tab.assert_called_once_with("https://example.com/path")

    @patch("aurix.actions.desktop.webbrowser.open_new_tab")
    def test_invalid_scheme_never_calls_browser(self, open_tab):
        result = desktop.handle_desktop_command("open javascript:alert(1)")
        self.assertIn("invalid", result.lower())
        open_tab.assert_not_called()

    @patch("aurix.actions.desktop._find_installed_app", return_value=None)
    def test_explicit_app_when_missing_does_not_fall_back_to_website(self, find_app):
        result = desktop.handle_desktop_command("open Spotify app")
        self.assertIn("couldn't find Spotify installed", result)
        find_app.assert_called_once_with("spotify")

    @patch("aurix.actions.desktop._find_installed_app", side_effect=OSError("permission denied"))
    @patch("aurix.actions.desktop.subprocess.Popen")
    def test_discovery_failure_is_reported_without_shell(self, popen, _find_app):
        result = desktop.handle_desktop_command("open UnknownThing app")
        self.assertIn("couldn't open", result)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
