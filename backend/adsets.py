
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
    Улучшенная функция обновления адсетов с обработкой ошибок.
    """
    logger.info(f"Обновление адсетов для аккаунта {account_id}, пользователь {user_id}")
    
    try:
        adsets = fetch_facebook_adsets(account_id, token)
        logger.info(f"Получено {len(adsets)} адсетов")
        
        if not adsets:
            logger.warning(f"Не получено адсетов для аккаунта {account_id}")
            return
        
        updated_count = 0
        for adset in adsets:
            try:
                adset_id = adset.get("id")
                if not adset_id:
                    continue
                    
                # Получаем метрики с обработкой ошибок
                insights = {}
                try:
                    insights = fetch_facebook_adset_insights(adset_id, token)
                except Exception as e:
                    logger.warning(f"Не удалось получить метрики для адсета {adset_id}: {e}")
                
                # Подготавливаем данные
                budget_cents = adset.get("daily_budget") or adset.get("lifetime_budget") or 0
                budget = float(budget_cents) / 100 if budget_cents else 0
                
                adset_data = {
                    "name": adset.get("name", ""),
                    "adset_id": adset_id,
                    "campaign_id": adset.get("campaign_id", ""),
                    "status": adset.get("status", "PAUSED"),
                    "account_id": account_id,
                    "token": token,
                    "budget": budget,
                    "geo": extract_geo_from_name(adset.get("name", "")),
                    "ucpc": 0,  # Будет обновлено из Keitaro
                    "cpc": float(insights.get("cpc", 0) or 0),
                    "cpm": float(insights.get("cpm", 0) or 0),
                    "spend": float(insights.get("spend", 0) or 0),
                    "king": "Facebook",
                    "effective_status": adset.get("effective_status", ""),
                    "ad_name": adset.get("name", ""),
                    "manual_pause": 0,
                    "updated_at": datetime.now()  # Добавляем время обновления
                }
                
                add_user_adset(user_id, adset_data)
                updated_count += 1
                
            except Exception as e:
                logger.error(f"Ошибка обработки адсета {adset.get('id')}: {e}")
                continue
        
        # Обновляем данные из Keitaro
        try:
            keitaro_updated = sync_keitaro(user_id)
            logger.info(f"Keitaro обновил {keitaro_updated} записей")
        except Exception as e:
            logger.error(f"Ошибка синхронизации с Keitaro: {e}")
        
        logger.info(f"Успешно обновлено {updated_count} адсетов")
        return updated_count
        
    except Exception as e:
        logger.error(f"Критическая ошибка при обновлении адсетов: {e}")
        raise

# Добавить функцию для быстрого обновления только метрик
def refresh_adsets_metrics_only(user_id: int):
    """
    Быстрое обновление только метрик без полной перезагрузки адсетов.
    Используется для автообновления таблицы.
    """
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Получаем актуальные адсеты для пользователя
            cursor.execute("SELECT adset_id, token FROM adsets WHERE user_id = ?", (user_id,))
            adsets = cursor.fetchall()
            
            updated = 0
            for adset in adsets:
                try:
                    insights = fetch_facebook_adset_insights(adset['adset_id'], adset['token'])
                    
                    cursor.execute("""
                        UPDATE adsets SET 
                            cpc = ?, cpm = ?, spend = ?, updated_at = ?
                        WHERE adset_id = ? AND user_id = ?
                    """, (
                        float(insights.get("cpc", 0) or 0),
                        float(insights.get("cpm", 0) or 0),
                        float(insights.get("spend", 0) or 0),
                        datetime.now(),
                        adset['adset_id'],
                        user_id
                    ))
                    
                    updated += 1
                    
                except Exception as e:
                    logger.warning(f"Не удалось обновить метрики для {adset['adset_id']}: {e}")
                    continue
            
            conn.commit()
            return updated