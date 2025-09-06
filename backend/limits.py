
import json
import requests
import logging
logger = logging.getLogger(__name__)


def get_account_limits_info(account_id, access_token):
  
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
