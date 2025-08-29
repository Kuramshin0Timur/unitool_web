import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

def get_session():
    """Создает и возвращает сессию requests с настройками"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    return session
def fetch_facebook_campaigns(account_id, access_token, fields=None):
    """Получает ВСЕ кампании из Facebook API (включая неактивные)"""
    if fields is None:
        fields = "id,name,status,effective_status,daily_budget,objective,start_time,stop_time"
    
    try:
        # Убедимся, что account_id не содержит 'act_' префикс
        clean_account_id = account_id.replace('act_', '')
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}/campaigns"
        
        params = {
            "fields": fields,
            "access_token": access_token,
            "limit": 1000  # Увеличиваем лимит
        }
        
        all_campaigns = []
        retry_count = 0
        max_retries = 3
        
        while url and retry_count < max_retries:
            try:
                response = requests.get(url, params=params, timeout=60)
                response.raise_for_status()
                
                data = response.json()
                campaigns = data.get('data', [])
                all_campaigns.extend(campaigns)
                
                # Логируем статусы для отладки
                status_count = {}
                effective_status_count = {}
                for campaign in campaigns:
                    status = campaign.get('status', 'UNKNOWN')
                    effective_status = campaign.get('effective_status', 'UNKNOWN')
                    status_count[status] = status_count.get(status, 0) + 1
                    effective_status_count[effective_status] = effective_status_count.get(effective_status, 0) + 1
                
                logger.debug(f"Получено {len(campaigns)} кампаний. Status: {status_count}, Effective Status: {effective_status_count}")
                
                # Обрабатываем пагинацию
                next_url = data.get('paging', {}).get('next')
                if next_url == url:  # Защита от бесконечного цикла
                    break
                    
                url = next_url
                # Очищаем params для последующих запросов
                params = {}
                retry_count = 0
                
            except requests.exceptions.RequestException as e:
                retry_count += 1
                logger.warning(f"Ошибка запроса кампаний (попытка {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    time.sleep(2 ** retry_count)  # Экспоненциальная задержка
                else:
                    raise
        
        # Фильтруем только нужные статусы если нужно (но лучше получить все)
        filtered_campaigns = [camp for camp in all_campaigns 
                             if camp.get('effective_status') not in ['DELETED', 'ARCHIVED']]
        
        logger.info(f"Получено {len(all_campaigns)} кампаний, после фильтрации: {len(filtered_campaigns)} для аккаунта {clean_account_id}")
        return filtered_campaigns
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка получения кампаний для аккаунта {account_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении кампаний: {e}")
        return []

def fetch_facebook_adsets(account_id, access_token, fields=None):
    """Получает ВСЕ адсеты из Facebook API (включая неактивные)"""
    if fields is None:
        fields = "id,name,campaign_id,daily_budget,status,effective_status,budget_remaining,lifetime_budget"
    
    try:
        clean_account_id = account_id.replace('act_', '')
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}/adsets"
        
        params = {
            "fields": fields,
            "access_token": access_token,
            "limit": 1000  # Увеличиваем лимит
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
                
                # Логируем статусы для отладки
                status_count = {}
                effective_status_count = {}
                for adset in adsets:
                    status = adset.get('status', 'UNKNOWN')
                    effective_status = adset.get('effective_status', 'UNKNOWN')
                    status_count[status] = status_count.get(status, 0) + 1
                    effective_status_count[effective_status] = effective_status_count.get(effective_status, 0) + 1
                
                logger.debug(f"Получено {len(adsets)} адсетов. Status: {status_count}, Effective Status: {effective_status_count}")
                
                # Обрабатываем пагинацию
                next_url = data.get('paging', {}).get('next')
                if next_url == url:  # Защита от бесконечного цикла
                    break
                    
                url = next_url
                # Очищаем params для последующих запросов
                params = {}
                retry_count = 0
                
            except requests.exceptions.RequestException as e:
                retry_count += 1
                logger.warning(f"Ошибка запроса адсетов (попытка {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    time.sleep(2 ** retry_count)  # Экспоненциальная задержка
                else:
                    raise
        
        # Фильтруем только нужные статусы
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

def fetch_adsets_insights(account_id, access_token):
    """Получает insights для адсетов (spend, CPC, CPA, conversions)"""
    try:
        url = f"https://graph.facebook.com/v18.0/act_{account_id}/insights"
        params = {
            "level": "adset",
            "fields": "adset_id,spend,cpc,cost_per_conversion,conversions",
            "date_preset": "today",
            "time_increment": 1,
            "access_token": access_token,
            "limit": 100
        }
        
        insights_by_adset = {}
        
        while url:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            insights = data.get('data', [])
            
            for insight in insights:
                adset_id = insight.get('adset_id')
                if adset_id:
                    insights_by_adset[adset_id] = {
                        'spend': float(insight.get('spend', 0)),
                        'cpc': float(insight.get('cpc', 0)),
                        'cost_per_conversion': float(insight.get('cost_per_conversion', 0)),
                        'conversions': int(insight.get('conversions', 0))
                    }
            
            # Обрабатываем пагинацию
            next_url = data.get('paging', {}).get('next')
            url = next_url
            params = {}
        
        logger.info(f"Получено insights для {len(insights_by_adset)} адсетов")
        return insights_by_adset
        
    except Exception as e:
        logger.error(f"Ошибка получения insights: {e}")
        return {}
def fetch_facebook_cpm_data(account_id, access_token):
    """Получает CPM данные из Facebook Insights"""
    try:
        url = f"https://graph.facebook.com/v18.0/act_{account_id}/insights"
        params = {
            "level": "adset",
            "fields": "adset_id,cpm,spend,impressions",
            "date_preset": "today",
            "time_increment": 1,
            "access_token": access_token,
            "limit": 100
        }
        
        cpm_data = {}
        
        while url:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            insights = data.get('data', [])
            
            for insight in insights:
                adset_id = insight.get('adset_id')
                if adset_id:
                    cpm_data[adset_id] = {
                        'cpm': float(insight.get('cpm', 0)),
                        'spend': float(insight.get('spend', 0)),
                        'impressions': int(insight.get('impressions', 0))
                    }
            
            # Обрабатываем пагинацию
            next_url = data.get('paging', {}).get('next')
            url = next_url
            params = {}
        
        logger.info(f"Получено CPM данных для {len(cpm_data)} адсетов")
        return cpm_data
        
    except Exception as e:
        logger.error(f"Ошибка получения CPM данных: {e}")
        return {}
def fetch_facebook_cpc_data(account_id, access_token):
    """Получает CPC данные из Facebook Insights"""
    try:
        url = f"https://graph.facebook.com/v18.0/act_{account_id}/insights"
        params = {
            "level": "adset",
            "fields": "adset_id,cpc,spend",
            "date_preset": "today",
            "time_increment": 1,
            "access_token": access_token,
            "limit": 100
        }
        
        cpc_data = {}
        
        while url:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            insights = data.get('data', [])
            
            for insight in insights:
                adset_id = insight.get('adset_id')
                if adset_id:
                    cpc_data[adset_id] = {
                        'cpc': float(insight.get('cpc', 0)),
                        'spend': float(insight.get('spend', 0))
                    }
            
            # Обрабатываем пагинацию
            next_url = data.get('paging', {}).get('next')
            url = next_url
            params = {}
        
        logger.info(f"Получено CPC данных для {len(cpc_data)} адсетов")
        return cpc_data
        
    except Exception as e:
        logger.error(f"Ошибка получения CPC данных: {e}")
        return {}
    
def get_account_limits_info(account_id, access_token):
    """Получает информацию о лимитах аккаунта из Facebook API"""
    try:
        clean_account_id = account_id.replace('act_', '')
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}"
        
        params = {
            'fields': 'id,name,account_status,amount_spent,balance,spend_cap,daily_spend_limit,'
                     'adtrust_dsl,min_daily_budget,min_campaign_group_spend_cap',
            'access_token': access_token
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if 'error' in data:
            return None
        
        # Получаем информацию о лимитах запросов из заголовков
        usage_info = response.headers.get('x-business-use-case-usage', '{}')
        calls_usage = 0
        calls_limit = 100
        
        try:
            usage_data = json.loads(usage_info)
            if usage_data and isinstance(usage_data, dict):
                for key in usage_data.keys():
                    call_count = usage_data[key][0].get('call_count', 0)
                    total_time = usage_data[key][0].get('total_time', 0)
                    calls_usage = max(calls_usage, call_count)
        except:
            pass
        
        return {
            'account_id': clean_account_id,
            'name': data.get('name', 'N/A'),
            'status': data.get('account_status', 'UNKNOWN'),
            'spend': float(data.get('amount_spent', 0)) / 100,
            'balance': float(data.get('balance', 0)) / 100,
            'spend_cap': float(data.get('spend_cap', data.get('daily_spend_limit', 0))) / 100,
            'daily_limit': float(data.get('daily_spend_limit', 0)) / 100,
            'min_daily_budget': float(data.get('min_daily_budget', 0)) / 100,
            'requests_today': calls_usage,
            'requests_limit': calls_limit,
            'requests_usage_percent': round((calls_usage / calls_limit) * 100, 1) if calls_limit > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения лимитов для аккаунта {account_id}: {e}")
        return None
