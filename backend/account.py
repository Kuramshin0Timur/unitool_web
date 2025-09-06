from typing import Any, Dict, List
from venv import logger

from database import get_db_connection


def get_user_accounts_stats(user_id: int) -> List[Dict[str, Any]]:
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            
            cursor.execute("""
                SELECT DISTINCT account_id, token 
                FROM campaigns 
                WHERE user_id = ? 
                AND account_id IS NOT NULL
            """, (user_id,))
            
            accounts = []
            for row in cursor.fetchall():
                account_id = row['account_id']
                token = row['token']
                
          
                accounts.append({
                    'account_id': account_id or 'N/A',
                    'token': token or 'N/A'
                })
            
            logger.info(f"Найдено {len(accounts)} аккаунтов у пользователя {user_id}")
            return accounts
            
    except Exception as e:
        logger.error(f"Ошибка получения статистики аккаунтов пользователя {user_id}: {e}")
        return []


def get_all_users() -> List[Dict[str, Any]]:
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, created_at FROM users ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей: {e}")
        return []
def get_user_accounts_stats(user_id: int) -> List[Dict[str, Any]]:
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
        
            cursor.execute("""
                SELECT DISTINCT account_id, token 
                FROM campaigns 
                WHERE user_id = ? 
                AND account_id IS NOT NULL 
                AND account_id != 'N/A'
                AND token IS NOT NULL
                AND token != 'N/A'
            """, (user_id,))
            
            accounts = []
            for row in cursor.fetchall():
                accounts.append({
                    'account_id': row['account_id'],
                    'token': row['token']
                })
            
            logger.info(f"Найдено {len(accounts)} валидных аккаунтов у пользователя {user_id}")
            return accounts
            
    except Exception as e:
        logger.error(f"Ошибка получения статистики аккаунтов пользователя {user_id}: {e}")
        return []
def get_all_users():
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, created_at FROM users ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей: {e}")
        return []
def get_all_accounts_stats():
    
    users = get_all_users()
    all_accounts = []
    
    for user in users:
        user_id = user['id']
        accounts = get_user_accounts_stats(user_id)
        
        for account in accounts:
            account['user_id'] = user_id
            account['username'] = user['username']
            all_accounts.append(account)
    
    return all_accounts
