import logging
import requests
from typing import Any, Dict, Optional

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .global_proxy import get_verified_proxy
from .config import get_use_proxy  # получаем актуальное значение из config.json

logger = logging.getLogger(__name__)

API_VERSION = "v18.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"
DEFAULT_TIMEOUT = 10
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.0
STATUS_FORCELIST = [500, 502, 503, 504]

_SESSION: Optional[requests.Session] = None


def _make_session() -> requests.Session:
    """Создаёт сессию requests с повторами и прокси, если включено."""
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=STATUS_FORCELIST,
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    if get_use_proxy():
        proxy = get_verified_proxy()
        if proxy:
            session.proxies.update(proxy)
            logger.info("🌐 Используется прокси для подключения к Facebook API")
        else:
            logger.critical("❌ Прокси включён, но не удалось подключиться — выполнение остановлено")
            raise RuntimeError("Прокси включён, но не удалось подключиться.")
    else:
        logger.info("🔓 Прокси отключён — используется прямое соединение")

    return session


def refresh_session() -> None:
    """Создаёт глобальную сессию заново."""
    global _SESSION
    _SESSION = _make_session()
    logger.info("🔄 Сессия Facebook API успешно обновлена")


def _ensure_session() -> None:
    """Гарантирует, что сессия инициализирована."""
    global _SESSION
    if _SESSION is None:
        refresh_session()


def _graph_request(
    object_id: str,
    token: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    fields: Optional[str] = None
) -> Dict[str, Any]:
    """Выполняет запрос к Graph API Facebook."""
    _ensure_session()

    url = f"{BASE_URL}/{object_id}"
    req_params = {"access_token": token}
    if params:
        req_params.update(params)
    if fields:
        req_params["fields"] = fields

    try:
        if method.upper() == "GET":
            resp = _SESSION.get(url, params=req_params, timeout=DEFAULT_TIMEOUT)
        else:
            resp = _SESSION.post(url, params=req_params, data=data or {}, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка запроса к Graph API ({method}) для объекта {object_id}: {e}")
        return {"error": str(e)}
    except ValueError as e:
        logger.error(f"⚠️ Некорректный JSON-ответ от Graph API для объекта {object_id}: {e}")
        return {"error": "Некорректный JSON-ответ от сервера"}


# === Методы управления кампаниями и адсетами ===

def pause_campaign(campaign_id: str, token: str) -> Dict[str, Any]:
    return _graph_request(campaign_id, token, method="POST", data={"status": "PAUSED"})


def resume_campaign(campaign_id: str, token: str) -> Dict[str, Any]:
    return _graph_request(campaign_id, token, method="POST", data={"status": "ACTIVE"})


def pause_adset(adset_id: str, token: str) -> Dict[str, Any]:
    return _graph_request(adset_id, token, method="POST", data={"status": "PAUSED"})


def resume_adset(adset_id: str, token: str) -> Dict[str, Any]:
    return _graph_request(adset_id, token, method="POST", data={"status": "ACTIVE"})


def get_adset_budget(adset_id: str, token: str) -> Dict[str, Any]:
    return _graph_request(adset_id, token, method="GET", fields="daily_budget,lifetime_budget")


def update_adset_budget(
    adset_id: str,
    token: str,
    *,
    daily_budget: Optional[int] = None,
    lifetime_budget: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if daily_budget is not None:
        payload["daily_budget"] = str(daily_budget)
    if lifetime_budget is not None:
        payload["lifetime_budget"] = str(lifetime_budget)
        if start_time:
            payload["start_time"] = start_time
        if end_time:
            payload["end_time"] = end_time

    if not payload:
        msg = "⚠️ Не указаны параметры бюджета для обновления"
        logger.warning(msg)
        return {"error": msg}

    return _graph_request(adset_id, token, method="POST", data=payload)
