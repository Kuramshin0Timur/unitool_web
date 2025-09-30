
import logging
import time
from typing import Any, Dict, List

import requests
from datetime import datetime, timedelta
from backend.campaign import get_user_campaigns
from backend.geo_config import extract_geo_from_name, get_user_geo_rules
from backend.keitaro import sync_keitaro
from database import get_db_connection, lock

logger = logging.getLogger(__name__)
def get_user_adsets(user_id: int) -> List[Dict[str, Any]]:
    """
    Возвращает список адсетов пользователя с актуальными метриками.
    Добавляем фильтрацию по времени для избежания устаревших данных.
    """
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Фильтруем данные за последние 24 часа
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            cursor.execute("""
                SELECT 
                    id, user_id, name, adset_id, campaign_id, 
                    COALESCE(effective_status, status, 'UNKNOWN') as status,
                    account_id, token, budget, geo, ucpc, cpc, cpm, spend, cpa, leads, 
                    king, effective_status, ad_name, manual_pause,
                    auto_budget_increase, auto_budget_decrease,
                    max_budget, min_budget, budget_increase_step, budget_decrease_step,
                    created_at, updated_at
                FROM adsets 
                WHERE user_id = ? AND updated_at > ? 
                ORDER BY updated_at DESC
            """, (user_id, cutoff_time))
            
            adsets = []
            for row in cursor.fetchall():
                adset = dict(row)
                # Нормализуем данные
                adset['status'] = str(adset.get('status', 'UNKNOWN')).strip().upper()
                
                # Заполняем нулями отсутствующие числовые значения
                numeric_fields = ['ucpc', 'cpc', 'cpm', 'spend', 'cpa', 'leads', 'budget']
                for field in numeric_fields:
                    adset[field] = float(adset.get(field, 0) or 0)
                
                adsets.append(adset)
            
            return adsets

def add_user_adset(user_id: int, data: Dict[str, Any]):
   
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
            INSERT OR REPLACE INTO adsets (
                user_id, name, adset_id, ucpc, cpc, cpm, spend, cpa, status, geo, token, 
                leads, manual_pause, king, effective_status, ad_name, budget,
                campaign_id, account_id, auto_budget_increase, auto_budget_decrease,
                max_budget, min_budget, budget_increase_step, budget_decrease_step
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                data.get('name', ''),
                data.get('adset_id', ''),
                data.get('ucpc', 0),
                data.get('cpc', 0),
                data.get('cpm', 0), 
                data.get('spend', 0),
                data.get('cpa', 0),
                data.get('status', 'PAUSED'),
                data.get('geo', 'N/A'),
                data.get('token', ''),
                data.get('leads', 0),
                data.get('manual_pause', 0),
                data.get('king', 'Facebook'),
                data.get('effective_status', ''),
                data.get('ad_name', ''),
                data.get('budget', 0),
                data.get('campaign_id', ''),
                data.get('account_id', ''),
                data.get('auto_budget_increase', 0),
                data.get('auto_budget_decrease', 0),
                data.get('max_budget', 0),
                data.get('min_budget', 0),
                data.get('budget_increase_step', 1.2),
                data.get('budget_decrease_step', 0.8)
            ))
            
            conn.commit()


def update_user_adset_status(user_id: int, adset_id: str, status: str):
   
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE adsets SET status = ? 
            WHERE user_id = ? AND adset_id = ?
            """, (status, user_id, adset_id))
            conn.commit()


def fetch_facebook_adset_insights(adset_id, access_token, date_preset="today"):
    """
    Получает метрики для конкретного адсета: CPM, CPC, Spend, Impressions
    """
    url = f"https://graph.facebook.com/v18.0/{adset_id}/insights"
    params = {
        "fields": "impressions,spend,cpm,cpc",
        "date_preset": date_preset,
        "access_token": access_token,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", [])
    return data[0] if data else {}

def fetch_facebook_adsets(account_id, access_token, fields=None):
    """
    Получает список адсетов (только метаданные, без метрик).
    """
    if fields is None:
        fields = "id,name,campaign_id,daily_budget,status,effective_status"

    url = f"https://graph.facebook.com/v18.0/act_{account_id}/adsets"
    params = {
        "fields": fields,
        "access_token": access_token,
        "limit": 1000,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("data", [])

import json
import time
import logging
import requests

logger = logging.getLogger(__name__)

class FacebookAPI:
    BASE_URL = "https://graph.facebook.com/v18.0"

    def __init__(self, access_token: str):
        self.session = requests.Session()
        self.access_token = access_token

    def fetch_adsets(self, account_id: str, fields=None, limit=500):
        """
        Получение всех адсетов аккаунта с пагинацией
        """
        if fields is None:
            fields = "id,name,campaign_id,daily_budget,status,effective_status"

        url = f"{self.BASE_URL}/act_{account_id}/adsets"
        params = {
            "fields": fields,
            "access_token": self.access_token,
            "limit": limit,
        }

        all_adsets = []
        while url:
            resp = self.session.get(url, params=params, timeout=30)
            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                logger.error(f"Ошибка получения адсетов: {e}, ответ={resp.text}")
                break

            data = resp.json()
            all_adsets.extend(data.get("data", []))
            url = data.get("paging", {}).get("next")
            params = None  # после первой итерации параметры не нужны

        logger.info(f"✅ Получено {len(all_adsets)} адсетов из {account_id}")
        return all_adsets

    def fetch_adsets_insights_batch(self, adset_ids, fields=None, pause=1.0):
        """
        Получение метрик для группы адсетов через batch-запрос
        """
        if fields is None:
            fields = "impressions,clicks,spend,cpm,cpc"

        batch = []
        for adset_id in adset_ids:
            batch.append({
                "method": "GET",
                "relative_url": f"{adset_id}/insights?fields={fields}&limit=1"
            })

        url = self.BASE_URL
        params = {"access_token": self.access_token}
        resp = self.session.post(url, params=params, json={"batch": batch}, timeout=60)

        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            logger.error(f"Ошибка batch-запроса: {e}, ответ={resp.text}")
            return {}

        results = {}
        for adset_id, item in zip(adset_ids, resp.json()):
            if "body" in item:
                try:
                    body = json.loads(item["body"])
                    if isinstance(body, dict) and "data" in body and body["data"]:
                        results[adset_id] = body["data"][0]
                    else:
                        logger.warning(f"⚠️ Нет данных в инсайтах для адсета {adset_id}")
                        results[adset_id] = {}
                except Exception as e:
                    logger.error(f"Ошибка парсинга batch-ответа {adset_id}: {e}")

        time.sleep(pause)  # пауза для снижения лимитов API
        return results


def refresh_adsets_internal(user_id, account_id, token):
    """
    Ускоренная версия: качаем все адсеты + метрики батчами
    """
    fb = FacebookAPI(token)
    adsets = fb.fetch_adsets(account_id)

    adset_ids = [a["id"] for a in adsets]
    insights = {}

    for i in range(0, len(adset_ids), 50):  # Facebook batch ограничен 50
        batch_ids = adset_ids[i:i + 50]
        part = fb.fetch_adsets_insights_batch(batch_ids)
        insights.update(part)

    for adset in adsets:
        adset_id = adset["id"]
        if adset_id in insights:
            adset.update(insights[adset_id])

    logger.info(f"🎯 Обновлено {len(adsets)} адсетов для пользователя {user_id}")
    return adsets
def refresh_adsets_metrics_only(user_id: int):
    """
    Быстрое обновление только метрик без полной перезагрузки адсетов.
    Использует batch-запросы для эффективности и избежания лимитов API.
    """
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()

            # 1. Получаем все уникальные токены и связанные с ними adset_id
            cursor.execute("""
                SELECT token, group_concat(adset_id) as adset_ids
                FROM adsets
                WHERE user_id = ? AND token != '' AND adset_id != '' AMDAND status = 'ACTIVE'
                GROUP BY token
            """, (user_id,))
            
            adsets_by_token = cursor.fetchall()
            
            if not adsets_by_token:
                logger.info("Не найдено адсетов для обновления метрик.")
                return 0

            all_insights = {}
            total_adsets_to_update = 0

            # 2. Обрабатываем адсеты для каждого токена отдельно
            for row in adsets_by_token:
                token = row['token']
                adset_ids = row['adset_ids'].split(',')
                total_adsets_to_update += len(adset_ids)
                
                fb_api = FacebookAPI(token)
                
                # 3. Делаем batch-запросы чанками по 50
                for i in range(0, len(adset_ids), 50):
                    batch_ids = adset_ids[i:i + 50]
                    try:
                        # Получаем метрики для пакета адсетов
                        insights_batch = fb_api.fetch_adsets_insights_batch(batch_ids)
                        all_insights.update(insights_batch)
                        logger.info(f"Получены метрики для {len(insights_batch)} адсетов.")
                    except Exception as e:
                        logger.error(f"Ошибка batch-запроса метрик: {e}")
                        continue
            
            if not all_insights:
                logger.warning("Не удалось получить метрики ни для одного адсета.")
                return 0

            # 4. Обновляем базу данных одним коммитом
            updated_count = 0
            for adset_id, insights in all_insights.items():
                if not insights:  # Пропускаем, если для адсета нет данных
                    continue
                
                try:
                    cursor.execute("""
                        UPDATE adsets SET 
                            cpc = ?, cpm = ?, spend = ?, updated_at = ?
                        WHERE adset_id = ? AND user_id = ?
                    """, (
                        float(insights.get("cpc", 0) or 0),
                        float(insights.get("cpm", 0) or 0),
                        float(insights.get("spend", 0) or 0),
                        datetime.now(),
                        adset_id,
                        user_id
                    ))
                    updated_count += 1
                except Exception as e:
                    logger.warning(f"Не удалось обновить метрики в БД для {adset_id}: {e}")

            conn.commit()
            logger.info(f"✅ Успешно обновлены метрики для {updated_count} из {total_adsets_to_update} адсетов.")
            return updated_count