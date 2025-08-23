import logging
import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import get_use_proxy  # динамически получаем актуальное значение

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config.json")
PROXY_TEST_URL = "https://api.ipify.org?format=json"
RETRY_DELAY = 3  # секунд

_session: Optional[requests.Session] = None


def _check_proxy(proxies: Dict[str, str]) -> bool:
    """Проверяет доступность прокси по API IP-адреса."""
    try:
        response = requests.get(PROXY_TEST_URL, proxies=proxies, timeout=5)
        response.raise_for_status()
        logger.info(f"✅ Прокси успешно подключён. IP: {response.json().get('ip')}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Прокси не прошёл проверку: {e}")
        return False


def get_verified_proxy() -> Optional[Dict[str, str]]:
    """
    Загружает прокси из config.json, проверяет и возвращает словарь прокси.
    Ожидаемый формат: ip:port:user:pass
    """
    if not get_use_proxy():
        logger.info("🔓 Прокси отключён (use_proxy=False)")
        return None

    if not CONFIG_PATH.exists():
        raise FileNotFoundError("⚠️ Файл config.json не найден")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    raw = config.get("proxy", "").strip()
    if not raw:
        raise ValueError("⚠️ Прокси не указан в config.json")

    try:
        host, port, username, password = raw.split(":")
        proxy_url = f"socks5h://{username}:{password}@{host}:{port}"
        proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }
    except Exception as e:
        raise ValueError(f"❌ Неверный формат прокси: {raw}") from e

    if _check_proxy(proxies):
        return proxies

    logger.critical("🚫 Прокси включён, но не удалось подключиться после двух попыток")
    raise RuntimeError("Прокси включён, но не прошёл проверку")


def connect_with_retry():
    """
    Создаёт глобальную сессию requests с прокси и повторной попыткой при сбое.
    Заменяет методы requests.get/post/request глобально.
    """
    global _session

    if not get_use_proxy():
        logger.info("🔓 Прокси отключён — используется прямое соединение")
        return

    for attempt in range(2):
        try:
            proxies = get_verified_proxy()
            session = requests.Session()
            retry = Retry(
                total=3,
                backoff_factor=1.0,
                status_forcelist=[500, 502, 503, 504],
                allowed_methods=["GET", "POST"]
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            session.proxies.update(proxies)
            _session = session

            # Подменяем глобальные методы requests
            requests.request = session.request
            requests.get = session.get
            requests.post = session.post

            logger.info("🌐 Соединение через прокси успешно установлено")
            return
        except Exception as e:
            logger.error(f"❌ Ошибка подключения через прокси: {e}")
            if attempt == 0:
                logger.info("🔁 Повторная попытка подключения через 3 секунды…")
                time.sleep(RETRY_DELAY)
            else:
                logger.critical("🚫 Прокси включён, но не удалось установить соединение")
                raise RuntimeError("Ошибка подключения через прокси")
