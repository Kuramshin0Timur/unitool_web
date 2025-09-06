import time
from typing import Any, Dict, List

import requests

from backend.campaign import get_user_campaigns
from backend.geo_config import extract_geo_from_name, get_user_geo_rules
from database import get_db_connection, lock

import logging
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



def fetch_facebook_adsets(account_id, access_token, fields=None):
    
    if fields is None:
        fields = "id,name,campaign_id,daily_budget,status,effective_status,budget_remaining,lifetime_budget"
    
    try:
        clean_account_id = account_id.replace('act_', '')
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}/adsets"
        
        params = {
            "fields": fields,
            "access_token": access_token,
            "limit": 1000  
        }
        
        all_adsets = []
        retry_count = 0
        max_retries = 3
        
        while url and retry_count < max_retries:
            try:
                response = requests.get(url, params=params, timeout=60)
                response.raise_for_status()
                
                data = response.json()
                adsets = data.get('data', [])
                all_adsets.extend(adsets)
                
                status_count = {}
                effective_status_count = {}
                for adset in adsets:
                    status = adset.get('status', 'UNKNOWN')
                    effective_status = adset.get('effective_status', 'UNKNOWN')
                    status_count[status] = status_count.get(status, 0) + 1
                    effective_status_count[effective_status] = effective_status_count.get(effective_status, 0) + 1
                
                logger.debug(f"Получено {len(adsets)} адсетов. Status: {status_count}, Effective Status: {effective_status_count}")
                
                next_url = data.get('paging', {}).get('next')
                if next_url == url: 
                    break
                    
                url = next_url
                params = {}
                retry_count = 0
                
            except requests.exceptions.RequestException as e:
                retry_count += 1
                logger.warning(f"Ошибка запроса адсетов (попытка {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    time.sleep(2 ** retry_count)  
                else:
                    raise
        
        filtered_adsets = [adset for adset in all_adsets 
                          if adset.get('effective_status') not in ['DELETED', 'ARCHIVED']]
        
        logger.info(f"Получено {len(all_adsets)} адсетов, после фильтрации: {len(filtered_adsets)} для аккаунта {clean_account_id}")
        return filtered_adsets
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка получения адсетов для аккаунта {account_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении адсетов: {e}")
        return []
    
def refresh_adsets_internal(user_id):
  
    try:
        campaigns = get_user_campaigns(user_id)
        accounts = {}
        
        geo_rules = get_user_geo_rules(user_id)
        known_geos = list(geo_rules.keys()) if geo_rules else []
        
        for campaign in campaigns:
            if campaign['account_id'] and campaign['token']:
                accounts[campaign['account_id']] = campaign['token']
        
        updated_count = 0
        for account_id, token in accounts.items():
            fb_adsets = fetch_facebook_adsets(account_id, token)
            for adset in fb_adsets:
                daily_budget = adset.get('daily_budget')
                budget = float(daily_budget) / 100 if daily_budget else 0
                
         
                adset_name = adset.get('name', '')
                geo = extract_geo_from_name(adset_name, known_geos)
                
                add_user_adset(user_id, {
                    'name': adset_name,
                    'adset_id': adset.get('id', ''),
                    'campaign_id': adset.get('campaign_id', ''),
                    'status': adset.get('status', 'PAUSED'),
                    'account_id': account_id,
                    'token': token,
                    'budget': budget,
                    'geo': geo,  
                    'ucpc': 0,
                    'spend': 0,
                    'cpa': 0,
                    'leads': 0,
                    'king': 'Facebook',
                    'effective_status': adset.get('effective_status', ''),
                    'ad_name': adset.get('name', ''),
                    'manual_pause': 0
                })
                updated_count += 1
                
        logger.info(f"Обновлено {updated_count} адсетов с определением GEO")
        return updated_count
                
    except Exception as e:
        logger.error(f"Ошибка обновления адсетов: {e}")
        return 0
