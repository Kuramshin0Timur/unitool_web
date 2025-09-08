import logging
import threading
from typing import Dict, List

import requests
from flask import app

from backend.adsets import (get_user_adsets, refresh_adsets_internal,
                            update_user_adset_status)
from backend.campaign import (check_and_pause_campaigns,
                              refresh_campaigns_internal)
from backend.geo_config import (extract_geo_from_name, get_user_geo_config,
                                get_user_geo_rules)
from backend.keitaro import sync_keitaro
from backend.reserve_tokens import get_reserve_tokens
from backend.setting import get_user_settings
from backend.telegram import send_telegram_message
from database import get_db_connection

logger = logging.getLogger(__name__)

auto_control_threads = {}
auto_control_lock = threading.Lock()
auto_refresh_timers = {}
auto_refresh_lock = threading.Lock()

def auto_populate_reserve_tokens(user_id: int):
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
           
            cursor.execute("""
                SELECT DISTINCT account_id, token 
                FROM campaigns 
                WHERE user_id = ? AND account_id IS NOT NULL AND token IS NOT NULL
                AND account_id != '' AND token != ''
            """, (user_id,))
            
            accounts = cursor.fetchall()
            
            added_count = 0
            for account in accounts:
                account_id = account['account_id']
                token = account['token']
                
               
                king = auto_determine_king(token)
                
                
                cursor.execute("""
                    INSERT OR IGNORE INTO reserve_tokens (user_id, king, token)
                    VALUES (?, ?, ?)
                """, (user_id, king, token))
                
                
                cursor.execute("""
                    INSERT OR IGNORE INTO reserve_token_accounts 
                    (user_id, king, token, account_id)
                    VALUES (?, ?, ?, ?)
                """, (user_id, king, token, account_id))
                
                if cursor.rowcount > 0:
                    added_count += 1
            
            conn.commit()
            if added_count > 0:
                logger.info(f"Автоматически добавлено {added_count} токенов в резерв для user_id {user_id}")
            
    except Exception as e:
        logger.error(f"Ошибка автоматического заполнения резервных токенов: {e}")

def auto_determine_king(token: str) -> str:
    
    if not token:
        return "Facebook_Default"
    
    token_lower = token.lower()
    
   
    if any(x in token_lower for x in ['ea', 'facebook', 'fb', 'act_']):
        return "Facebook"
    elif any(x in token_lower for x in ['ig', 'instagram']):
        return "Instagram" 
    elif any(x in token_lower for x in ['tt', 'tiktok']):
        return "TikTok"
    elif any(x in token_lower for x in ['gg', 'google', 'ga']):
        return "Google"
    elif any(x in token_lower for x in ['tw', 'twitter', 'x.com']):
        return "Twitter"
    elif len(token) > 100:  
        return "Facebook_Long"
    elif len(token) > 50:   
        return "Facebook_Medium"
    else:
        return "Facebook_Default"

def get_combined_auto_status(user_id):
    
    with auto_control_lock:
        auto_control_running = user_id in auto_control_threads
        
    with auto_refresh_lock:
        auto_refresh_running = user_id in auto_refresh_timers
        settings = get_user_settings(user_id)
        interval = settings.get('auto_refresh_interval', 5)
    
   
    running = auto_control_running or auto_refresh_running
    
    return {
        'running': running,
        'auto_control_running': auto_control_running,
        'auto_refresh_running': auto_refresh_running,
        'interval': interval
    }

def stop_auto_control_and_refresh(user_id):
    
    
    with auto_control_lock:
        if user_id in auto_control_threads:
            auto_control_threads[user_id]['running'] = False
            del auto_control_threads[user_id]
            logger.info(f"Автоконтроль остановлен для пользователя {user_id}")
    
    
    with auto_refresh_lock:
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
            del auto_refresh_timers[user_id]
            logger.info(f"Автообновление остановлено для пользователя {user_id}")

def get_session():
   
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    return session

def start_auto_refresh(user_id, interval_minutes):
    
    with auto_refresh_lock:
        
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
        
        
        interval_seconds = interval_minutes * 60
        timer = threading.Timer(interval_seconds, lambda: auto_refresh_user_data(user_id, interval_minutes))
        timer.daemon = True
        timer.start()
        
        auto_refresh_timers[user_id] = timer
        auto_control(user_id)
        logger.info(f"Автообновление запущено для пользователя {user_id}, интервал: {interval_minutes} мин")

def auto_refresh_user_data(user_id, interval_minutes):

    try:
        with app.app_context():
            logger.info(f"Автообновление данных для пользователя {user_id}")
            
          
            auto_populate_reserve_tokens(user_id)
            
        
            settings = get_user_settings(user_id)
            
           
            if settings.get('auto_refresh_campaigns', True):
                refresh_campaigns_internal(user_id)
            
        
            if settings.get('auto_refresh_adsets', True):
                refresh_adsets_internal(user_id)
            
          
            if settings.get('keitaro_api_key'):
                sync_keitaro(user_id)
            
            logger.info(f"Автообновление завершено для пользователя {user_id}")
            
    except Exception as e:
        logger.error(f"Ошибка автообновления для пользователя {user_id}: {e}")
    
    finally:
        
        start_auto_refresh(user_id, interval_minutes)

def load_all_tokens(user_id: int) -> Dict[str, List[str]]:
  
    all_tokens = {}
    
    try:
        
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
           
            cursor.execute("""
                SELECT DISTINCT account_id, token 
                FROM campaigns 
                WHERE user_id = ? AND account_id IS NOT NULL AND token IS NOT NULL
                AND account_id != '' AND token != ''
            """, (user_id,))
            
            for row in cursor.fetchall():
                king = auto_determine_king(row['token'])
                if king not in all_tokens:
                    all_tokens[king] = []
                if row['token'] not in all_tokens[king]:
                    all_tokens[king].append(row['token'])
        
   
        reserve_tokens = get_reserve_tokens(user_id)
        for king, tokens in reserve_tokens.items():
            if king not in all_tokens:
                all_tokens[king] = []
            for token_info in tokens:
                if token_info['token'] not in all_tokens[king]:
                    all_tokens[king].append(token_info['token'])
                    
    except Exception as e:
        logger.error(f"Ошибка загрузки всех токенов: {e}")
    
    return all_tokens
def process_adset_control(user_id, adset, geo_rules, known_geos, reserve_tokens, session_obj, settings):
   
    adset_name = adset.get('name', '')
    adset_id = adset.get('adset_id', '')
    ucpc = float(adset.get('ucpc', 0))
    spend = float(adset.get('spend', 0))
    cpa = float(adset.get('cpa', 0))
    status = adset.get('status', '').strip().upper()
    account_id = adset.get('account_id', '')
    token = adset.get('token', '')
    leads = int(adset.get('leads', 0))
    manual_pause = bool(adset.get('manual_pause', 0))
    king = adset.get('king', '').strip()
    
    logger.debug(f"Обработка адсета: {adset_name} (ID: {adset_id}, статус: {status})")
    

    geo = extract_geo_from_name(adset_name, known_geos)
    

    if geo == 'N/A' or geo not in geo_rules:
        msg = f"⏭️ Пропускаем (неизвестное GEO: {geo}) {adset_name}"
        logger.info(msg)
        return
    
    rule = geo_rules[geo]
    should_pause = False
    should_resume = False
    pause_reason = ""

    
    if status == "ACTIVE" and not manual_pause:
        max_cpa = rule.get("max_cpa", rule.get("cpa_red", 100))
        min_spend = rule.get("min_spend", rule.get("spend_zero_leads", 50))
        
        logger.debug(f"Правила для GEO {geo}: max_cpa={max_cpa}, min_spend={min_spend}")
        logger.debug(f"Показатели адсета: leads={leads}, ucpc={ucpc}, spend={spend}, cpa={cpa}")
        
        if leads == 0 and ucpc > max_cpa and spend >= min_spend:
            should_pause = True
            pause_reason = "uCPC"
            logger.info(f"Условие паузы 1: leads=0, ucpc={ucpc} > {max_cpa}, spend={spend} >= {min_spend}")
        elif leads > 0 and cpa > max_cpa and spend >= min_spend:
            should_pause = True
            pause_reason = "CPA"
            logger.info(f"Условие паузы 2: leads={leads}, cpa={cpa} > {max_cpa}, spend={spend} >= {min_spend}")
        elif spend >= min_spend and leads == 0:
            should_pause = True
            pause_reason = "Zero Leads"
            logger.info(f"Условие паузы 3: spend={spend} >= {min_spend}, leads=0")

    elif status == "PAUSED" and not manual_pause:
        cpa_green = rule.get("cpa_green", 20)
        cpa_orange = rule.get("cpa_orange", 50)
        min_spend_half = rule.get("min_spend", rule.get("spend_zero_leads", 50)) / 2
        
        logger.debug(f"Правила возобновления: cpa_green={cpa_green}, cpa_orange={cpa_orange}, min_spend_half={min_spend_half}")
        
        if (leads > 0 and cpa <= cpa_green and ucpc <= cpa_orange and spend >= min_spend_half):
            should_resume = True
            logger.info(f"Условие возобновления: leads={leads}, cpa={cpa} <= {cpa_green}, ucpc={ucpc} <= {cpa_orange}, spend={spend} >= {min_spend_half}")

   
    token_list = reserve_tokens.get(king, [])
    if token and token not in token_list:
        token_list = [token] + token_list  
    
    if not token_list:
        logger.warning(f"Нет доступных токенов для KING={king}, адсет {adset_name}")
        return

  
    def execute_with_token_rotation(api_call_func):
        for idx, current_token in enumerate(token_list):
            try:
                result = api_call_func(current_token)
                if result:
                    return result
                
            except Exception as e:
                error_msg = str(e).lower()
                
               
                if any(limit_error in error_msg for limit_error in [
                    'request limit', 'rate limit', 'too many requests', 
                    'application request limit', 'quota'
                ]):
                    logger.warning(f"⚠️ Токен №{idx+1} достиг лимита. Пробуем следующий...")
                    if idx + 1 < len(token_list):
                        continue
                    else:
                        raise Exception(f"❌ Все токены исчерпаны для KING={king}")
                else:
                    raise e
        
        return None

    
    if should_pause:
        logger.info(f"Попытка отключения адсета {adset_name} по причине: {pause_reason}")
        
        def pause_adset(token):
            url = f"https://graph.facebook.com/v18.0/{adset_id}"
            data = {"status": "PAUSED"}
            
            resp = session_obj.post(
                url,
                params={"access_token": token},
                data=data,
                timeout=10
            ).json()

            if resp.get("success") or resp.get("id") == adset_id:
                update_user_adset_status(user_id, adset_id, "PAUSED")
                
                msg = (f"🔴 Отключен: {adset_name} "
                       f"(GEO={geo}, CPA={cpa:.2f}, uCPC={ucpc:.2f}, Leads={leads}, Spend={spend:.2f}) — причина: {pause_reason}")
                logger.info(msg)
                send_telegram_message(msg, user_id=user_id)
                return True
            
            return False
        
        execute_with_token_rotation(pause_adset)

 
    elif should_resume:
        logger.info(f"Попытка включения адсета {adset_name}")
        
        def resume_adset(token):
            url = f"https://graph.facebook.com/v18.0/{adset_id}"
            data = {"status": "ACTIVE"}
            
            resp = session_obj.post(
                url,
                params={"access_token": token},
                data=data,
                timeout=10
            ).json()

            if resp.get("success") or resp.get("id") == adset_id:
                update_user_adset_status(user_id, adset_id, "ACTIVE")
                
                msg = (f"🟢 Включен: {adset_name} "
                       f"(GEO={geo}, CPA={cpa:.2f}, uCPC={ucpc:.2f}, Leads={leads}, Spend={spend:.2f})")
                logger.info(msg)
                send_telegram_message(msg, user_id=user_id)
                return True
            
            return False
        
        execute_with_token_rotation(resume_adset)
def auto_control(user_id):
    try:
        logger.info(f"=== НАЧАЛО АВТОКОНТРОЛЯ ДЛЯ ПОЛЬЗОВАТЕЛЯ {user_id} ===")
        
        settings = get_user_settings(user_id)        
        session_obj = get_session()
        if settings.get('use_proxy') and settings.get('proxy'):
            session_obj.proxies = {
                'http': settings.get('proxy'),
                'https': settings.get('proxy')
            }
        
    
        check_and_pause_campaigns(user_id)
        
      
        geo_rules = get_user_geo_rules(user_id)
        
   
        if not geo_rules:
            geo_rules = get_user_geo_config(user_id)
            logger.info("Используются правила из старой таблицы geo_config")
        
    
        known_geos = list(geo_rules.keys()) if geo_rules else []

        reserve_tokens = load_all_tokens(user_id)
        
       
        adsets = get_user_adsets(user_id)
        logger.info(f"Найдено {len(adsets)} адсетов для обработки")
        
        for adset in adsets:
            try:
                process_adset_control(user_id, adset, geo_rules, known_geos, reserve_tokens, session_obj, settings)
                
            except Exception as e:
                logger.error(f"Ошибка обработки адсета {adset.get('name', 'unknown')}: {e}")
                continue
        check_and_pause_campaigns(user_id)
    except Exception as e:
        logger.error(f"Критическая ошибка автоконтроля для пользователя {user_id}: {e}")
        send_telegram_message(f"🚫 Ошибка автоконтроля: {e}", user_id=user_id)

def run_auto_control_for_user(user_id):
    """Запускает автоконтроль для конкретного пользователя"""
    logger.info(f"Запуск автоконтроля для пользователя {user_id}")
    
    while True:
     
        with auto_control_lock:
            if user_id not in auto_control_threads or not auto_control_threads[user_id].get('running', False):
                logger.info(f"Автоконтроль остановлен для пользователя {user_id}")
                break
        
        try:
            logger.info(f"Выполнение автоконтроля для пользователя {user_id}")
            auto_control(user_id)
            logger.info(f"Автоконтроль завершен для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Ошибка автоконтроля для пользователя {user_id}: {e}")
        
     
        threading.Event().wait(300)

def start_auto_control_and_refresh(user_id):
    """Запускает и автоконтроль и автообновление вместе"""
    settings = get_user_settings(user_id)
    interval = settings.get('auto_refresh_interval', 5)
    
    
    with auto_control_lock:
        if user_id not in auto_control_threads:
            auto_control_threads[user_id] = {
                'running': True,
                'thread': threading.Thread(
                    target=run_auto_control_for_user,
                    args=(user_id,),
                    daemon=True
                )
            }
            auto_control_threads[user_id]['thread'].start()
            logger.info(f"Автоконтроль запущен для пользователя {user_id}")
    
 
    with auto_refresh_lock:
      
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
        
       
        interval_seconds = interval * 60
        timer = threading.Timer(interval_seconds, lambda: auto_refresh_user_data(user_id, interval))
        timer.daemon = True
        timer.start()
        
        auto_refresh_timers[user_id] = timer
        logger.info(f"Автообновление запущено для пользователя {user_id}, интервал: {interval} мин")
