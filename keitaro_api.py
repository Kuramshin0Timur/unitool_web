import logging
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

def fetch_keitaro_report(api_key, domain, interval="today"):
    """
    Получает отчет из Keitaro.
    Считает лиды по формуле Spend / CPA.
    Берёт CPC и UCPC из Keitaro.
    Группировка только по sub_id_9 (название адсета).
    """
    logger = logging.getLogger(__name__)
    url = f"https://{domain}/admin_api/v1/report/build"
    headers = {"Api-Key": api_key, "Content-Type": "application/json"}

    metrics = ["ucpc", "cpc", "conversions", "cost", "cpa"]
    limit = 250
    offset = 0
    all_rows = []

    try:
        while True:
            payload = {
                "range": {"interval": interval, "timezone": "Europe/Moscow"},
                "metrics": metrics,
                "grouping": ["sub_id_9"],   # 🚨 только имя адсета
                "filters": [],
                "sort": [{"name": "ucpc", "order": "desc"}],
                "limit": limit,
                "offset": offset
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            report = response.json()

            rows = report.get("rows", [])
            if not rows:
                break

            for row in rows:
                cost = float(row.get("cost", 0) or 0)
                cpa = float(row.get("cpa", 0) or 0)
                cpc = float(row.get("cpc", 0) or 0)

                leads = round(cost / cpa) if cpa > 0 and cost > 0 else 0
                row["leads"] = leads
                row["cpc"] = cpc

            all_rows.extend(rows)

            if len(rows) < limit:
                break
            offset += limit

        return {"rows": all_rows}

    except Exception as e:
        logger.error(f"Ошибка при запросе отчета Keitaro: {e}")
        return {"rows": []}
def get_keitaro_streams(base_url, api_key, campaign_id):
    """
    Получение потоков Keitaro с автоподстановкой схемы и пути API.
    
    base_url: домен трекера (с https:// или без), например:
              "tracker.mydomain.com" или "https://tracker.mydomain.com/admin_api/v1"
    api_key: API key
    campaign_id: ID кампании или "all"
    """
    # Убираем пробелы и лишние слэши
    base_url = base_url.strip().rstrip("/")

    # Если нет схемы — добавляем https://
    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url

    # Если нет пути /admin_api/v1 — добавляем
    if "/admin_api/v1" not in base_url:
        base_url = base_url.rstrip("/") + "/admin_api/v1"

    headers = {
        "Api-Key": api_key,
        "Content-Type": "application/json"
    }

    try:
        if campaign_id == "all":
            # Получаем все кампании
            campaigns_url = f"{base_url}/campaigns"
            campaigns_resp = requests.get(campaigns_url, headers=headers)
            campaigns_resp.raise_for_status()
            campaigns = campaigns_resp.json()

            all_streams = {}
            return all_streams
        else:
            # Потоки по одной кампании
            streams_url = f"{base_url}/campaigns/{campaign_id}/streams"
            resp = requests.get(streams_url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except requests.HTTPError as e:
        if e.response.status_code == 404:
            print(f"Ошибка 404: Не найдено. Проверь, что ID кампании {campaign_id} существует и API-ключ имеет доступ.")
        else:
            print(f"HTTP ошибка: {e}")
        return None
    except requests.RequestException as e:
        print(f"Ошибка при запросе потоков Keitaro: {e}")
        return None

def update_keitaro_stream_weight(api_key, domain, stream_id, new_weight):
    """Обновляет вес потока в Keitaro - исправленная версия"""
    try:
        url = f"https://{domain}/admin_api/v1/streams/{stream_id}"
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        
        payload = {"weight": int(new_weight)}
        
        response = requests.put(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        return result
        
    except Exception as e:
        logger.error(f"Ошибка обновления веса потока {stream_id}: {e}")
        return None
def analyze_stream_performance(api_key, domain, campaign_id=None, interval="today"):
    """Анализирует производительность потоков кампании - исправленная версия"""
    try:
        url = f"https://{domain}/admin_api/v1/report/build"
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        
        # Базовый payload для анализа потоков
        payload = {
            "range": {"interval": interval, "timezone": "Europe/Moscow"},
            "metrics": ["conversions", "revenue", "cost", "roi", "epc", "clicks"],
            "grouping": ["stream_id", "campaign_id"],
            "limit": 1000
        }
        
        # Добавляем фильтр по кампании если указана
        if campaign_id and campaign_id != 'all':
            try:
                campaign_id_int = int(campaign_id)
                payload["filters"] = [{
                    "name": "campaign_id", 
                    "operator": "EQUALS", 
                    "expression": str(campaign_id_int)
                }]
            except ValueError:
                logger.error(f"Неверный ID кампании для фильтра: {campaign_id}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        report = response.json()
        return report.get('rows', [])
        
    except Exception as e:
        logger.error(f"Ошибка анализа производительности потоков: {e}")
        return []
