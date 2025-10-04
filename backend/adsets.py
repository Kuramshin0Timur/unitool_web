
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
                    status,
                    effective_status,
                    account_id, token, budget, geo, ucpc, cpc, cpm, spend, cpa, leads, 
                    king, ad_name, manual_pause,
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

                # Нормализуем строковые статусы
                adset['status'] = str(adset.get('status', 'UNKNOWN') or 'UNKNOWN').strip().upper()
                adset['effective_status'] = str(adset.get('effective_status', 'UNKNOWN') or 'UNKNOWN').strip().upper()

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

    def fetch_adsets(self, account_id: str, fields=None, limit=500, max_retries=5):
        """
        Получение всех адсетов аккаунта с пагинацией и обработкой лимитов.
        Берем только нужные поля.
        """
        if fields is None:
            fields = fields = "id,name,campaign_id,status,effective_status"


        url = f"{self.BASE_URL}/act_{account_id}/adsets"
        params = {
            "fields": fields,
            "access_token": self.access_token,
            "limit": limit,
        }

        all_adsets = []

        while url:
            attempt = 0
            while attempt < max_retries:
                resp = self.session.get(url, params=params, timeout=30)

                if resp.status_code == 200:
                    data = resp.json()
                    all_adsets.extend(data.get("data", []))

                    next_url = data.get("paging", {}).get("next")
                    if next_url:
                        # 🔑 гарантируем, что токен есть в next_url
                        if "access_token=" not in next_url:
                            sep = "&" if "?" in next_url else "?"
                            next_url = f"{next_url}{sep}access_token={self.access_token}"
                        url = next_url
                    else:
                        url = None

                    time.sleep(0.3)
                    break

                # --- Обработка ошибок ---
                try:
                    err = resp.json().get('error', {})
                except Exception:
                    err = {}

                # Распарсили err = resp.json().get("error", {})

                code = err.get("code")
                subcode = err.get("error_subcode")
                msg = err.get("message", "").lower()

                # ✅ Лимиты (code=17 — user request limit)
                if code == 17:
                    retry_after = resp.headers.get("Retry-After")
                    wait_time = int(retry_after) if retry_after else 2 ** attempt
                    logger.warning(
                        f"⚠️ Лимит API Facebook для аккаунта {account_id}. "
                        f"Попытка {attempt+1}/{max_retries}. Ждём {wait_time}с. "
                        f"(code={code}, subcode={subcode}, msg={err.get('message')})"
                    )
                    time.sleep(wait_time)
                    attempt += 1
                    continue

                elif resp.status_code in (429,):
                    # Общие лимиты
                    retry_after = resp.headers.get("Retry-After")
                    wait_time = int(retry_after) if retry_after else 2 ** attempt
                    logger.warning(
                        f"⚠️ Rate limit (429) для аккаунта {account_id}. "
                        f"Попытка {attempt+1}/{max_retries}. Ждём {wait_time}с"
                    )
                    time.sleep(wait_time)
                    attempt += 1
                    continue

                elif resp.status_code == 400:
                    logger.error(
                        f"❌ Ошибка параметров при получении адсетов {account_id}: "
                        f"code={code} subcode={subcode} msg={err.get('message')} resp={resp.text}"
                    )
                    url = None
                    break

                else:
                    # Другая ошибка
                    logger.error(f"Ошибка получения адсетов {account_id}: {resp.status_code} {resp.text}")
                    url = None
                    break

            else:
                logger.error(f"❌ Превышено число попыток получения адсетов для {account_id}")
                break

            # Важно! params не затираем
            # params = None  # эту строку убрали навсегда

        logger.info(f"✅ Получено {len(all_adsets)} адсетов из {account_id}")
        return all_adsets

    def fetch_adsets_insights_batch(self, adset_ids, fields=None, pause=1.0):
        """
        Получение метрик для группы адсетов через batch-запрос.
        Теперь берем только spend и clicks (для ucpc), а также leads (для cpa).
        """
        if fields is None:
            fields = "spend,clicks,actions"

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
                        data = body["data"][0]

                        spend = float(data.get("spend", 0) or 0)
                        clicks = float(data.get("clicks", 0) or 0)
                        leads = 0
                        for action in data.get("actions", []):
                            if action.get("action_type") == "lead":
                                leads += float(action.get("value", 0))

                        ucpc = spend / clicks if clicks > 0 else 0
                        cpa = spend / leads if leads > 0 else 0

                        results[adset_id] = {
                            "spend": spend,
                            "clicks": clicks,
                            "leads": leads,
                            "ucpc": ucpc,
                            "cpa": cpa
                        }
                    else:
                        results[adset_id] = {}
                except Exception as e:
                    logger.error(f"Ошибка парсинга batch-ответа {adset_id}: {e}")

        time.sleep(pause)
        return results
from backend.keitaro import fetch_keitaro_report
from backend.setting import get_user_settings

def refresh_adsets_internal(user_id, account_id, token):
    fb = FacebookAPI(token)
    try:
        adsets = fb.fetch_adsets(account_id)
    except Exception as e:
        logger.warning(f"⚠️ Не удалось получить адсеты из FB: {e}")
        return []

    # Загружаем Keitaro-данные
    settings = get_user_settings(user_id)
    keitaro_api_key = settings.get('keitaro_api_key')
    keitaro_domain = settings.get('keitaro_domain', 'uniaffnu.com')
    keitaro_data_by_name = {}

    if keitaro_api_key:
        report = fetch_keitaro_report(keitaro_api_key, keitaro_domain)
        for row in report.get("rows", []):
            adset_name = str(row.get("sub_id_9") or "").strip()
            if not adset_name:
                continue
            keitaro_data_by_name[adset_name] = {
                "spend": float(row.get("cost", 0) or 0),
                "leads": int(row.get("leads", 0) or 0),
                "cpa": float(row.get("cpa", 0) or 0),
                "ucpc": float(row.get("ucpc", 0) or 0),
                "cpc": float(row.get("cpc", 0) or 0),
                "cpm": float(row.get("cpm", 0) or 0),
            }

    # Сохраняем адсеты с Keitaro метриками
    for ad in adsets:
        ad_name = ad.get("name", "")
        adset_id = ad.get("id", "")
        camp_id = ad.get("campaign_id", "")
        budget = float(ad.get("daily_budget", 0)) / 100 if ad.get("daily_budget") else 0
        geo = extract_geo_from_name(ad_name)

        stats = keitaro_data_by_name.get(ad_name, {})

        add_user_adset(user_id, {
            "name": ad_name,
            "adset_id": adset_id,
            "campaign_id": camp_id,
            "status": ad.get("status", "PAUSED"),
            "account_id": account_id,
            "token": token,
            "budget": budget,
            "spend": stats.get("spend", 0),
            "leads": stats.get("leads", 0),
            "cpa": stats.get("cpa", 0),
            "ucpc": stats.get("ucpc", 0),
            "cpm": stats.get("cpm", 0),
            "cpc": stats.get("cpc", 0),
            "king": "Facebook",
            "effective_status": ad.get("effective_status", ""),
            "ad_name": ad_name,
            "manual_pause": 0,
            "geo": geo
        })

def refresh_adsets_metrics_only(user_id: int):
    """
    Быстрое обновление только ucpc и cpa.
    """
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT token, group_concat(adset_id) as adset_ids
                FROM adsets
                WHERE user_id = ? AND token != '' AND adset_id != '' AND status = 'ACTIVE'
                GROUP BY token
            """, (user_id,))
            
            adsets_by_token = cursor.fetchall()
            if not adsets_by_token:
                logger.info("Не найдено адсетов для обновления метрик.")
                return 0

            all_insights = {}
            for row in adsets_by_token:
                token = row['token']
                adset_ids = row['adset_ids'].split(',')
                fb_api = FacebookAPI(token)

                for i in range(0, len(adset_ids), 50):
                    batch_ids = adset_ids[i:i + 50]
                    try:
                        insights_batch = fb_api.fetch_adsets_insights_batch(batch_ids)
                        all_insights.update(insights_batch)
                    except Exception as e:
                        logger.error(f"Ошибка batch-запроса метрик: {e}")
                        continue
            
            updated_count = 0
            for adset_id, insights in all_insights.items():
                if not insights:
                    continue
                try:
                    cursor.execute("""
                        UPDATE adsets SET 
                            spend = ?, leads = ?, ucpc = ?, cpa = ?, updated_at = ?
                        WHERE adset_id = ? AND user_id = ?
                    """, (
                        insights.get("spend", 0),
                        insights.get("leads", 0),
                        insights.get("ucpc", 0),
                        insights.get("cpa", 0),
                        datetime.now(),
                        adset_id,
                        user_id
                    ))
                    updated_count += 1
                except Exception as e:
                    logger.warning(f"Не удалось обновить метрики в БД для {adset_id}: {e}")

            conn.commit()
            logger.info(f"✅ Обновлено {updated_count} адсетов с метриками ucpc и cpa")
            return updated_count
