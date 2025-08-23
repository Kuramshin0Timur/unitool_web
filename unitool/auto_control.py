import logging
import requests
import json

from .sheets_client import safe_worksheet, load_reserve_tokens
from .config import CONFIG_SHEET_NAME, DATA_SHEET_NAME, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, get_use_proxy
from .proxy_handler import get_verified_proxy

logger = logging.getLogger(__name__)
logger.info(f"🔧 Прокси используется: {get_use_proxy()}")

# --- Сессия с учётом прокси ---
def get_session() -> requests.Session:
    if not get_use_proxy():
        logger.info("🔓 Прокси отключён — создаётся обычная сессия")
        return requests.Session()

    proxies = get_verified_proxy()
    if not proxies:
        raise RuntimeError("❌ Прокси включён, но не удалось подключиться")

    session = requests.Session()
    session.proxies.update(proxies)
    return session
