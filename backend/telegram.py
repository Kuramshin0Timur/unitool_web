
from venv import logger
import requests

from backend.setting import get_user_settings


def send_telegram_message(message, chat_id=None, bot_token=None, user_id=None):
    """Безопасная отправка сообщения в Telegram"""
    try:
        if user_id and (not chat_id or not bot_token):
            settings = get_user_settings(user_id)
            chat_id = chat_id or settings.get('telegram_chat_id')
            bot_token = bot_token or settings.get('telegram_bot_token')

        if not chat_id or not bot_token:
            logger.debug("Telegram не настроен — пропуск отправки")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }

        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True

    except Exception as e:
        logger.warning(f"Telegram сообщение не отправлено: {e}")
        return False

