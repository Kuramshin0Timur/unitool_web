import fcntl
import time
from typing import Any, Dict, List

import requests

from backend.telegram import send_telegram_message
from database import get_db_connection, lock

import logging
logger = logging.getLogger(__name__)

def add_campaign_mapping(user_id: int, fb_campaign_id: str, keitaro_key: str, 
                        campaign_name: str = "", match_type: str = ""):
    
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO campaign_mapping 
            (user_id, facebook_campaign_id, keitaro_key, campaign_name, match_type)
            VALUES (?, ?, ?, ?, ?)
            """, (user_id, fb_campaign_id, keitaro_key, campaign_name, match_type))
            conn.commit()

def update_campaign_stats(user_id, campaign_id, spend=None, leads=None, cpa=None, cpc=None, ucpc=None):
  
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            updates = []
            params = {'user_id': user_id, 'campaign_id': campaign_id}
            
            if spend is not None:
                updates.append("spend = :spend")
                params['spend'] = spend
            
            if leads is not None:
                updates.append("leads = :leads")
                params['leads'] = leads
                
            if cpa is not None:
                updates.append("cpa = :cpa")
                params['cpa'] = cpa
                
            if cpc is not None:  # CPC из Facebook
                updates.append("cpc = :cpc")
                params['cpc'] = cpc
                
            if ucpc is not None:
                updates.append("ucpc = :ucpc")
                params['ucpc'] = ucpc
            
            if updates:
                query = f"""
                UPDATE campaigns SET
                    {', '.join(updates)}
                WHERE user_id = :user_id AND campaign_id = :campaign_id
                """
                cursor.execute(query, params)
                conn.commit()
                logger.info(f"Обновлена статистика кампании {campaign_id} с CPC из Facebook: {cpc}")

def add_user_campaign(user_id: int, data: Dict[str, Any]):
    
    required_fields = {
        'king': str,
        'name': str,
        'status': str,
        'campaign_id': str,
        'account_id': str
    }
    
   
    for field, field_type in required_fields.items():
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
        if not isinstance(data[field], field_type):
            raise ValueError(f"Invalid type for field {field}")
    
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            try:
                
                cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
                if not cursor.fetchone():
                    raise ValueError(f"User with ID {user_id} does not exist")
                
                cursor.execute("""
                INSERT OR REPLACE INTO campaigns (
                    user_id, king, name, status, campaign_id, account_id, token
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    data['king'],
                    data['name'],
                    data['status'],
                    data['campaign_id'],
                    data['account_id'],
                    data.get('token', '')
                ))
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error(f"Error adding campaign: {e}")
                raise ValueError(f"Database error: {str(e)}")


def get_user_campaigns(user_id: int) -> List[Dict[str, Any]]:
    
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns WHERE user_id = ?", (user_id,))
            return [dict(row) for row in cursor.fetchall()]

def fetch_facebook_campaigns(account_id, access_token, fields=None):
    
    if fields is None:
        fields = "id,name,status,effective_status,daily_budget,objective,start_time,stop_time"
    
    try:
        clean_account_id = account_id.replace('act_', '')
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}/campaigns"
        
        params = {
            "fields": fields,
            "access_token": access_token,
            "limit": 1000  
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
                
                status_count = {}
                effective_status_count = {}
                for campaign in campaigns:
                    status = campaign.get('status', 'UNKNOWN')
                    effective_status = campaign.get('effective_status', 'UNKNOWN')
                    status_count[status] = status_count.get(status, 0) + 1
                    effective_status_count[effective_status] = effective_status_count.get(effective_status, 0) + 1
                
                logger.debug(f"Получено {len(campaigns)} кампаний. Status: {status_count}, Effective Status: {effective_status_count}")
                
                next_url = data.get('paging', {}).get('next')
                if next_url == url:  
                    break
                    
                url = next_url
                params = {}
                retry_count = 0
                
            except requests.exceptions.RequestException as e:
                retry_count += 1
                logger.warning(f"Ошибка запроса кампаний (попытка {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    time.sleep(2 ** retry_count)  
                else:
                    raise
        
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


def refresh_campaigns_internal(user_id):
   
    try:
        campaigns = get_user_campaigns(user_id)
        accounts = {}
        
        for campaign in campaigns:
            if campaign['account_id'] and campaign['token']:
                accounts[campaign['account_id']] = campaign['token']
        
        for account_id, token in accounts.items():
            fb_campaigns = fetch_facebook_campaigns(account_id, token)
            for campaign in fb_campaigns:
                add_user_campaign(user_id, {
                    'king': 'Facebook',
                    'name': campaign.get('name', ''),
                    'status': campaign.get('status', 'PAUSED'),
                    'campaign_id': campaign.get('id', ''),
                    'account_id': account_id,
                    'token': token
                })
                
    except Exception as e:
        logger.error(f"Ошибка обновления кампаний: {e}")

def update_user_campaign_status(user_id: int, campaign_id: str, status: str):
  
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE campaigns SET status = ? 
            WHERE user_id = ? AND campaign_id = ?
            """, (status, user_id, campaign_id))
            conn.commit()

def check_and_pause_campaigns(user_id):
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
           
            cursor.execute("""
            SELECT c.campaign_id, c.name, c.token, c.account_id
            FROM campaigns c
            WHERE c.user_id = ? AND c.status = 'ACTIVE'
            AND NOT EXISTS (
                SELECT 1 FROM adsets a 
                WHERE a.campaign_id = c.campaign_id 
                AND a.user_id = c.user_id 
                AND a.status = 'ACTIVE'
            )
            """, (user_id,))
            
            campaigns_to_pause = cursor.fetchall()
            
            for campaign in campaigns_to_pause:
                campaign_id = campaign['campaign_id']
                name = campaign['name']
                token = campaign['token']
                account_id = campaign['account_id']
                
                update_user_campaign_status(user_id, campaign_id, 'PAUSED')
                
                try:
                    url = f"https://graph.facebook.com/v18.0/{campaign_id}"
                    response = requests.post(
                        url,
                        params={"access_token": token},
                        data={"status": "PAUSED"},
                        timeout=10
                    )
                    response.raise_for_status()
                    
                    logger.info(f"🔴 Кампания «{name}» отключена (все адсеты неактивны)")
                    send_telegram_message(f"🔴 Кампания «{name}» отключена (все адсеты неактивны)", user_id=user_id)
                    
                except Exception as e:
                    logger.error(f"Ошибка отключения кампании {campaign_id}: {e}")
                    
    except Exception as e:
        logger.error(f"Ошибка проверки кампаний: {e}")

def extract_king_from_name(name: str) -> str:
    """
    Извлекает KING из названия кампании
    """
    if not name:
        return 'UNKNOWN'
    
    # Поиск паттернов KING в названии
    import re
    
    king_patterns = [
        r'KING(\d+)',
        r'K-(\d+)', 
        r'king(\d+)',
        r'k-(\d+)'
    ]
    
    for pattern in king_patterns:
        match = re.search(pattern, name.upper())
        if match:
            return f"KING{match.group(1)}"
    
    return 'UNKNOWN'