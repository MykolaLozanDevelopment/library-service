import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_message(text):
    """Send a text message to the notifications chat.

    Returns True on success. Never raises: a failed notification must not
    break the request that triggered it.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        logger.warning("Telegram is not configured, message not sent.")
        return False

    try:
        response = requests.post(
            SEND_MESSAGE_URL.format(token=token),
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        # Do not log the exception text: it contains the URL with the token.
        logger.error(
            "Failed to send Telegram message: %s", type(exc).__name__
        )
        return False
    return True
