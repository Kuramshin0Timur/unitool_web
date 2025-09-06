

from database import get_db_connection

import logging
logger = logging.getLogger(__name__)

def update_user_settings(user_id, data):
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
           
            cursor.execute("SELECT id FROM settings WHERE user_id = ?", (user_id,))
            settings_exists = cursor.fetchone()
            
            if settings_exists:
            
                cursor.execute("""
                    UPDATE settings SET
                        sync_api_key = ?, proxy = ?, use_proxy = ?,
                        auto_refresh_campaigns = ?, auto_refresh_adsets = ?,
                        auto_refresh_interval = ?, telegram_bot_token = ?,
                        telegram_chat_id = ?, keitaro_api_key = ?,
                        keitaro_domain = ?, keitaro_range_days = ?,
                        auto_headline_optimization = ?, headline_optimization_interval = ?,
                        account_timezone = ?, balance_check_enabled = ?, warning_threshold = ?
                    WHERE user_id = ?
                """, (
                    data.get('sync_api_key', ''),
                    data.get('proxy', ''),
                    int(data.get('use_proxy', True)),
                    int(data.get('auto_refresh_campaigns', True)),
                    int(data.get('auto_refresh_adsets', True)),
                    int(data.get('auto_refresh_interval', 5)),
                    data.get('telegram_bot_token', ''),
                    data.get('telegram_chat_id', ''),
                    data.get('keitaro_api_key', ''),
                    data.get('keitaro_domain', 'uniaffnu.com'),
                    int(data.get('keitaro_range_days', 1)),
                    int(data.get('auto_headline_optimization', False)),
                    int(data.get('headline_optimization_interval', 4)),
                    data.get('account_timezone', '-7'),
                    int(data.get('balance_check_enabled', True)),
                    float(data.get('warning_threshold', 50.0)),
                    user_id
                ))
            else:
              
                cursor.execute("""
                    INSERT INTO settings (
                        user_id, sync_api_key, proxy, use_proxy,
                        auto_refresh_campaigns, auto_refresh_adsets, auto_refresh_interval,
                        telegram_bot_token, telegram_chat_id, keitaro_api_key,
                        keitaro_domain, keitaro_range_days, auto_headline_optimization,
                        headline_optimization_interval, account_timezone, balance_check_enabled, warning_threshold
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    data.get('sync_api_key', ''),
                    data.get('proxy', ''),
                    int(data.get('use_proxy', True)),
                    int(data.get('auto_refresh_campaigns', True)),
                    int(data.get('auto_refresh_adsets', True)),
                    int(data.get('auto_refresh_interval', 5)),
                    data.get('telegram_bot_token', ''),
                    data.get('telegram_chat_id', ''),
                    data.get('keitaro_api_key', ''),
                    data.get('keitaro_domain', 'uniaffnu.com'),
                    int(data.get('keitaro_range_days', 1)),
                    int(data.get('auto_headline_optimization', False)),
                    int(data.get('headline_optimization_interval', 4)),
                    data.get('account_timezone', '-7'),
                    int(data.get('balance_check_enabled', True)),
                    float(data.get('warning_threshold', 50.0))
                ))
            
            conn.commit()
            return True
            
    except Exception as e:
        logger.error(f"Ошибка сохранения настроек: {e}")
        return False

def get_default_settings():
    
    return {
        'sync_api_key': '',
        'proxy': '',
        'use_proxy': True,
        'auto_refresh_campaigns': True,
        'auto_refresh_adsets': True,
        'auto_refresh_interval': 5,
        'telegram_bot_token': '',
        'telegram_chat_id': '',
        'keitaro_api_key': '',
        'keitaro_domain': 'uniaffnu.com',
        'keitaro_range_days': 1,
        'auto_headline_optimization': False,
        'headline_optimization_interval': 4,
        'account_timezone': '-7',
        'balance_check_enabled': True,
        'warning_threshold': 50.0
    }

def get_user_settings(user_id):
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    sync_api_key, proxy, use_proxy, auto_refresh_campaigns, 
                    auto_refresh_adsets, auto_refresh_interval, telegram_bot_token, 
                    telegram_chat_id, keitaro_api_key, keitaro_domain, keitaro_range_days,
                    auto_headline_optimization, headline_optimization_interval,
                    account_timezone, balance_check_enabled, warning_threshold
                FROM settings WHERE user_id = ?
            """, (user_id,))
            
            row = cursor.fetchone()
            if row:
              
                row_dict = dict(row)
                return {
                    'sync_api_key': row_dict.get('sync_api_key', ''),
                    'proxy': row_dict.get('proxy', ''),
                    'use_proxy': bool(row_dict.get('use_proxy', True)),
                    'auto_refresh_campaigns': bool(row_dict.get('auto_refresh_campaigns', True)),
                    'auto_refresh_adsets': bool(row_dict.get('auto_refresh_adsets', True)),
                    'auto_refresh_interval': row_dict.get('auto_refresh_interval', 5),
                    'telegram_bot_token': row_dict.get('telegram_bot_token', ''),
                    'telegram_chat_id': row_dict.get('telegram_chat_id', ''),
                    'keitaro_api_key': row_dict.get('keitaro_api_key', ''),
                    'keitaro_domain': row_dict.get('keitaro_domain', 'uniaffnu.com'),
                    'keitaro_range_days': row_dict.get('keitaro_range_days', 1),
                    'auto_headline_optimization': bool(row_dict.get('auto_headline_optimization', False)),
                    'headline_optimization_interval': row_dict.get('headline_optimization_interval', 4),
                    'account_timezone': row_dict.get('account_timezone', '-7'),
                    'balance_check_enabled': bool(row_dict.get('balance_check_enabled', True)),
                    'warning_threshold': float(row_dict.get('warning_threshold', 50.0))
                }
            else:
              
                return get_default_settings()
                
    except Exception as e:
        logger.error(f"Ошибка получения настроек: {e}")
        return get_default_settings()
