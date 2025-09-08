import logging
import time
from typing import Any, Dict, List

import requests

from backend.campaign import get_user_campaigns
from backend.geo_config import extract_geo_from_name, get_user_geo_rules
from backend.keitaro import sync_keitaro
from database import get_db_connection, lock

logger = logging.getLogger(__name__)

def get_user_adsets(user_id: int) -> List[Dict[str, Any]]:
   
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id, user_id, name, adset_id, campaign_id, 
                    COALESCE(effective_status, status, 'UNKNOWN') as status,
                    account_id, token, budget, geo, ucpc, cpc, spend, cpa, leads, 
                    king, effective_status, ad_name, manual_pause,
                    auto_budget_increase, auto_budget_decrease,
                    max_budget, min_budget, budget_increase_step, budget_decrease_step,
                    created_at, updated_at
                FROM adsets 
                WHERE user_id = ?
            """, (user_id,))
            
            adsets = []
            for row in cursor.fetchall():
                adset = dict(row)
               
                adset['status'] = str(adset.get('status', 'UNKNOWN')).strip()
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
        fields = "id,name,campaign_id,daily_budget,status,effective_status,budget_remaining,lifetime_budget"

    url = f"https://graph.facebook.com/v18.0/act_{account_id}/adsets"
    params = {
        "fields": fields,
        "access_token": access_token,
        "limit": 1000,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("data", [])
def refresh_adsets_internal(user_id, account_id, token):
    """
    Обновляет список адсетов и метрики из Facebook (CPM, Spend, CPC).
    После этого подтягивает CPA и Leads из Keitaro.
    """
    logger.info(f"Обновление адсетов для аккаунта {account_id}")

    adsets = fetch_facebook_adsets(account_id, token)
    logger.info(f"Получено {len(adsets)} адсетов для аккаунта {account_id}")

    for adset in adsets:
        adset_id = adset.get("id")
        adset_name = adset.get("name", "")
        budget_cents = adset.get("daily_budget") or adset.get("lifetime_budget") or 0
        budget = float(budget_cents) / 100 if budget_cents else 0
        geo = ""  # если где-то хранится geo — можно подтянуть

        # Подгружаем метрики через insights
        insights = fetch_facebook_adset_insights(adset_id, token)
        spend = float(insights.get("spend", 0) or 0)
        impressions = int(insights.get("impressions", 0) or 0)
        cpm = float(insights.get("cpm", 0) or 0)
        cpc = float(insights.get("cpc", 0) or 0)

        add_user_adset(user_id, {
            "name": adset_name,
            "adset_id": adset_id,
            "campaign_id": adset.get("campaign_id", ""),
            "status": adset.get("status", "PAUSED"),
            "account_id": account_id,
            "token": token,
            "budget": budget,
            "geo": geo,
            "ucpc": 0,   # подтянется из Keitaro
            "cpc": cpc,
            "cpm": cpm,
            "spend": spend,
            "king": "Facebook",
            "effective_status": adset.get("effective_status", ""),
            "ad_name": adset_name,
            "manual_pause": 0,
        })

    # 🔥 Обновляем метрики CPA/Leads из Keitaro
    try:
        updated = sync_keitaro(user_id)
        logger.info(f"Keitaro обновил {updated} адсетов для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении Keitaro для user_id={user_id}: {e}")

    """
    Обновляет список адсетов и метрики из Facebook (CPM, Spend, CPC).
    CPA и Leads не трогаем — они подтянутся из Keitaro.
    """
    logger.info(f"Обновление адсетов для аккаунта {account_id}")

    adsets = fetch_facebook_adsets(account_id, token)
    logger.info(f"Получено {len(adsets)} адсетов для аккаунта {account_id}")

    for adset in adsets:
        adset_id = adset.get("id")
        adset_name = adset.get("name", "")
        budget = adset.get("daily_budget") or adset.get("lifetime_budget") or 0
        geo = ""  # если где-то хранится geo — можно подтянуть

        # Подгружаем метрики через insights
        insights = fetch_facebook_adset_insights(adset_id, token)
        spend = float(insights.get("spend", 0) or 0)
        impressions = int(insights.get("impressions", 0) or 0)
        cpm = float(insights.get("cpm", 0) or 0)
        cpc = float(insights.get("cpc", 0) or 0)

        add_user_adset(user_id, {
            "name": adset_name,
            "adset_id": adset_id,
            "campaign_id": adset.get("campaign_id", ""),
            "status": adset.get("status", "PAUSED"),
            "account_id": account_id,
            "token": token,
            "budget": budget,
            "geo": geo,
            "ucpc": 0,   # из Keitaro
            "cpc": cpc,
            "cpm": cpm,
            "spend": spend,
            # ⚠️ CPA и Leads не затираем
            "king": "Facebook",
            "effective_status": adset.get("effective_status", ""),
            "ad_name": adset_name,
            "manual_pause": 0,
        })