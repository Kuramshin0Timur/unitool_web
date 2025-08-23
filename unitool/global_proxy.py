import logging
import requests
import json
from typing import Optional, Dict

from .config import get_use_proxy  # используем актуальное значение каждый раз

CONFIG_PATH = "config.json"
logger = logging.getLogger(__name__)


def load_proxy_from_config() -> Optional[Dict[str, str]]:
    """Загружает настройки SOCKS5 прокси из config.json и возвращает словарь для requests."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            raw = config.get("proxy", "").strip()

            if not raw:
                raise ValueError("Поле 'proxy' отсутствует или пустое")

            parts = raw.split(":")
            if len(parts) != 4:
                raise ValueError("Неверный формат прокси. Ожидается: ip:port:user:pass")

            host, port, user, password = parts
            proxy_url = f"socks5h://{user}:{password}@{host}:{port}"

            return {
                "http": proxy_url,
                "https": proxy_url,
            }

    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке прокси из config.json: {e}")
        return None


def check_proxy(proxy_dict: Dict[str, str]) -> bool:
    """Проверяет работоспособность переданного прокси."""
    try:
        response = requests.get("https://api.ipify.org", proxies=proxy_dict, timeout=10)
        response.raise_for_status()
        logger.info(f"✅ Прокси успешно подключён. Текущий IP: {response.text}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Прокси не работает: {e}")
        return False


def get_verified_proxy() -> Optional[Dict[str, str]]:
    """
    Возвращает рабочий прокси, если включён в настройках и работает.
    Если прокси включён, но не прошёл проверку — вызывает RuntimeError.
    Если прокси выключен — возвращает None.
    """
    if not get_use_proxy():
        logger.info("🔓 Прокси отключён — используется прямое подключение")
        return None

    for attempt in range(2):
        proxy = load_proxy_from_config()
        if proxy and check_proxy(proxy):
            return proxy
        if attempt == 0:
            logger.info("🔁 Первая попытка подключения через прокси не удалась. Пробуем ещё раз…")

    logger.critical("🚫 Прокси включён, но не удалось подключиться после двух попыток")
    raise RuntimeError("Прокси включён в настройках, но не удалось подключиться.")
