from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings

from notifications.telegram import send_telegram_message

CONFIGURED = {
    "TELEGRAM_BOT_TOKEN": "123:secret",
    "TELEGRAM_CHAT_ID": "-1001",
}


@override_settings(**CONFIGURED)
class SendTelegramMessageTests(SimpleTestCase):
    @patch("notifications.telegram.requests.post")
    def test_sends_message_to_configured_chat(self, mock_post):
        result = send_telegram_message("hello")

        self.assertTrue(result)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(
            args[0], "https://api.telegram.org/bot123:secret/sendMessage"
        )
        self.assertEqual(
            kwargs["json"], {"chat_id": "-1001", "text": "hello"}
        )

    @override_settings(TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")
    @patch("notifications.telegram.requests.post")
    def test_not_configured_skips_request(self, mock_post):
        with self.assertLogs("notifications.telegram", level="WARNING"):
            result = send_telegram_message("hello")

        self.assertFalse(result)
        mock_post.assert_not_called()

    @patch("notifications.telegram.requests.post")
    def test_connection_error_returns_false(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("boom")

        with self.assertLogs("notifications.telegram", level="ERROR"):
            result = send_telegram_message("hello")

        self.assertFalse(result)

    @patch("notifications.telegram.requests.post")
    def test_http_error_returns_false(self, mock_post):
        mock_post.return_value.raise_for_status.side_effect = (
            requests.HTTPError("403")
        )

        with self.assertLogs("notifications.telegram", level="ERROR"):
            result = send_telegram_message("hello")

        self.assertFalse(result)

    @patch("notifications.telegram.requests.post")
    def test_error_log_does_not_contain_token(self, mock_post):
        mock_post.side_effect = requests.ConnectionError(
            "https://api.telegram.org/bot123:secret/sendMessage failed"
        )

        with self.assertLogs(
            "notifications.telegram", level="ERROR"
        ) as logs:
            send_telegram_message("hello")

        self.assertNotIn("123:secret", "".join(logs.output))
