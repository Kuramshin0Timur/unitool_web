import logging
import threading
import time
from typing import Dict, List
import traceback
from urllib import request
import requests
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
    """Получить статус системы с подробным логированием"""
    with auto_control_lock:
        auto_control_running = user_id in auto_control_threads
        control_info = ""
        if auto_control_running:
            control_info = f" (running: {auto_control_threads[user_id].get('running', 'unknown')})"
        
    with auto_refresh_lock:
        auto_refresh_running = user_id in auto_refresh_timers
        refresh_info = ""
        if auto_refresh_running:
            refresh_info = " (timer active)"
    
    settings = get_user_settings(user_id)
    interval = settings.get('auto_refresh_interval', 60)
    
    running = auto_control_running or auto_refresh_running
    
    logger.info(f"📊 СТАТУС СИСТЕМЫ user_id={user_id}: "
                f"control={auto_control_running}{control_info}, "
                f"refresh={auto_refresh_running}{refresh_info}, "
                f"interval={interval}мин, overall={'RUNNING' if running else 'STOPPED'}")
    
    return {
        'running': running,
        'auto_control_running': auto_control_running,
        'auto_refresh_running': auto_refresh_running,
        'interval': interval
    }
def stop_auto_control_and_refresh(user_id):
    """Полная остановка системы"""
    logger.info(f"🛑 Остановка системы для пользователя {user_id}")
    
    # Останавливаем автообновление
    with auto_refresh_lock:
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
            del auto_refresh_timers[user_id]
            logger.info(f"⏹️ Автообновление остановлено для пользователя {user_id}")
    
    # Останавливаем автоконтроль
    with auto_control_lock:
        if user_id in auto_control_threads:
            auto_control_threads[user_id]['running'] = False
            del auto_control_threads[user_id]
            logger.info(f"⏹️ Автоконтроль остановлен для пользователя {user_id}")
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

        interval_seconds = 30 * 60

        def run_refresh():
            # Проверяем, не остановлена ли система
            with auto_refresh_lock:
                if user_id not in auto_refresh_timers:
                    return  # остановлено
            
            try:
                logger.info(f"🔄 Запуск автообновления для пользователя {user_id}")
                auto_refresh_user_data(user_id, interval_minutes)
            except Exception as e:
                logger.error(f"Ошибка автообновления: {e}")
            
            # Планируем следующее обновление только если система еще работает
            with auto_refresh_lock:
                if user_id in auto_refresh_timers:
                    start_auto_refresh(user_id, interval_minutes)

        timer = threading.Timer(interval_seconds, run_refresh)
        timer.daemon = True
        timer.start()
        auto_refresh_timers[user_id] = timer

        logger.info(f"⏱️ Автообновление запущено для {user_id}, интервал {interval_minutes} мин")
        
def auto_refresh_user_data(user_id, interval_minutes):
    """Однократное обновление данных пользователя"""
    try:
        logger.info(f"🔄 Автообновление данных для пользователя {user_id}")

        # Автозаполнение резервных токенов
        auto_populate_reserve_tokens(user_id)
        settings = get_user_settings(user_id)

        # Обновление кампаний
        if settings.get('auto_refresh_campaigns', True):
            logger.info("📊 Обновление кампаний...")
            refresh_campaigns_internal(user_id)

        # Обновление адсетов
        if settings.get('auto_refresh_adsets', True):
            logger.info("🎯 Обновление адсетов...")
            from backend.campaign import get_user_campaigns
            campaigns = get_user_campaigns(user_id)
            accounts = {
                c['account_id']: c['token']
                for c in campaigns
                if c['account_id'] and c['token']
            }
            for account_id, token in accounts.items():
                try:
                    refresh_adsets_internal(user_id, account_id, token)
                except Exception as e:
                    logger.error(f"Ошибка обновления адсетов {account_id}: {e}")

        # Синхронизация с Keitaro
        logger.info("🔗 Синхронизация с Keitaro...")
        sync_keitaro(user_id)
        
        logger.info(f"✅ Автообновление завершено для пользователя {user_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка автообновления для пользователя {user_id}: {e}")
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
    effective_status = adset.get('effective_status', '').strip().upper()
    account_id = adset.get('account_id', '')
    token = adset.get('token', '')
    leads = int(adset.get('leads', 0))
    manual_pause = bool(adset.get('manual_pause', 0))
    king = adset.get('king', '').strip()

    logger.debug(f"Обработка адсета: {adset_name} (ID: {adset_id}, статус: {status}, effective_status: {effective_status})")

    geo = extract_geo_from_name(adset_name, known_geos)

    if geo == 'N/A' or geo not in geo_rules:
        msg = f"⏭️ Пропускаем (GEO нет в таблице правил: {geo}) {adset_name}"
        logger.info(msg)
        return

    rule = geo_rules[geo]
    should_pause = False
    should_resume = False
    pause_reason = ""

    # 🟣 Если отклонён модерацией
    if effective_status == "DISAPPROVED":
        update_user_adset_status(user_id, adset_id, "DISAPPROVED")
        msg = (f"🟣 AdSet отклонен: {adset_name} "
               f"(GEO={geo}, CPA={cpa:.2f}, uCPC={ucpc:.2f}, Leads={leads}, Spend={spend:.2f})")
        logger.info(msg)
        send_telegram_message(msg, user_id=user_id)
        return

    max_cpa = rule.get("max_cpa", 0)
    min_spend = rule.get("min_spend", 0)

    # ⚡ УПРОЩЕННАЯ ЛОГИКА - ВЫКЛЮЧЕНИЕ ТОЛЬКО ПО CPA ИЗ ТАБЛИЦЫ
    if status == "ACTIVE" and not manual_pause:
        logger.debug(f"Правила для GEO {geo} из таблицы: max_cpa={max_cpa}, min_spend={min_spend}")

        # 🔴 ЕДИНСТВЕННОЕ УСЛОВИЕ ДЛЯ ВЫКЛЮЧЕНИЯ: CPA выше Max CPA из таблицы
        if max_cpa > 0 and cpa > max_cpa and spend >= min_spend and leads > 0:
            should_pause = True
            pause_reason = f"CPA ${cpa:.2f} > Max CPA ${max_cpa:.2f} (из таблицы)"
            logger.warning(f"🚨 ВЫКЛЮЧАЕМ {adset_name} - {pause_reason}")

        # Логируем информацию о метриках
        elif max_cpa > 0:
            if cpa <= max_cpa:
                logger.info(f"✅ ОСТАВЛЯЕМ {adset_name} - CPA ${cpa:.2f} <= Max CPA ${max_cpa:.2f} (из таблицы)")
            else:
                logger.info(f"💡 {adset_name} - CPA ${cpa:.2f} > ${max_cpa:.2f}, но недостаточно данных (spend=${spend:.2f}, leads={leads})")

    elif status == "PAUSED" and not manual_pause:
        logger.debug(f"Проверка условий для возобновления (GEO {geo})")

        # 🟢 условие возобновления: CPA снова в норме
        if max_cpa > 0 and cpa <= max_cpa and spend >= min_spend and leads > 0:
            should_resume = True
            logger.info(f"🟢 ВОЗОБНОВЛЯЕМ {adset_name} - CPA ${cpa:.2f} <= ${max_cpa:.2f} (из таблицы)")

    # === Работа с токенами ===
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

    # === Пауза ===
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
                       f"(GEO={geo}, CPA={cpa:.2f}, Max CPA={max_cpa:.2f}, Leads={leads}, Spend={spend:.2f}) — причина: {pause_reason}")
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
                       f"(GEO={geo}, CPA={cpa:.2f}, Max CPA={max_cpa:.2f}, Leads={leads}, Spend={spend:.2f})")
                logger.info(msg)
                send_telegram_message(msg, user_id=user_id)
                return True
            return False

        execute_with_token_rotation(resume_adset)
    adset_name = adset.get('name', '')
    adset_id = adset.get('adset_id', '')
    ucpc = float(adset.get('ucpc', 0))
    spend = float(adset.get('spend', 0))
    cpa = float(adset.get('cpa', 0))
    status = adset.get('status', '').strip().upper()
    effective_status = adset.get('effective_status', '').strip().upper()
    account_id = adset.get('account_id', '')
    token = adset.get('token', '')
    leads = int(adset.get('leads', 0))
    manual_pause = bool(adset.get('manual_pause', 0))
    king = adset.get('king', '').strip()

    logger.debug(f"Обработка адсета: {adset_name} (ID: {adset_id}, статус: {status}, effective_status: {effective_status})")

    geo = extract_geo_from_name(adset_name, known_geos)

    if geo == 'N/A' or geo not in geo_rules:
        msg = f"⏭️ Пропускаем (неизвестное GEO: {geo}) {adset_name}"
        logger.info(msg)
        return

    rule = geo_rules[geo]
    should_pause = False
    should_resume = False
    pause_reason = ""

    # 🟣 Если отклонён модерацией
    if effective_status == "DISAPPROVED":
        update_user_adset_status(user_id, adset_id, "DISAPPROVED")
        msg = (f"🟣 AdSet отклонен: {adset_name} "
               f"(GEO={geo}, CPA={cpa:.2f}, uCPC={ucpc:.2f}, Leads={leads}, Spend={spend:.2f})")
        logger.info(msg)
        send_telegram_message(msg, user_id=user_id)
        return

    max_cpa = rule.get("max_cpa", 100)
    min_spend = rule.get("min_spend", 50)
    max_leads_threshold = rule.get("max_leads_threshold", 1)
    extended_spend_threshold = rule.get("extended_spend_threshold", min_spend)
    max_ucpc = rule.get("max_ucpc", 100)
    max_ucpc_spend = rule.get("max_ucpc_spend", min_spend)

    # ⚡ УПРОЩЕННАЯ ЛОГИКА - ВЫКЛЮЧЕНИЕ ТОЛЬКО ПО CPA ⚡
    if status == "ACTIVE" and not manual_pause:
        logger.debug(f"Правила для GEO {geo}: max_cpa={max_cpa}, min_spend={min_spend}, "
                     f"extended_spend_threshold={extended_spend_threshold}, "
                     f"max_ucpc={max_ucpc}, max_ucpc_spend={max_ucpc_spend}")

        # 🔴 ЕДИНСТВЕННОЕ УСЛОВИЕ ДЛЯ ВЫКЛЮЧЕНИЯ: CPA выше лимита
        if leads > 0 and cpa > max_cpa and spend >= min_spend:
            should_pause = True
            pause_reason = f"CPA ${cpa:.2f} > Max CPA ${max_cpa:.2f}"
            logger.warning(f"🚨 ВЫКЛЮЧАЕМ {adset_name} - {pause_reason}")

        # Остальные метрики только для логов (НЕ ВЫКЛЮЧАЮТ)
        else:
            # Логируем информацию о других метриках
            if leads == 0 and ucpc > max_ucpc and spend >= max_ucpc_spend:
                logger.info(f"💡 Инфо {adset_name} - uCPC ${ucpc:.2f} > Max uCPC ${max_ucpc:.2f} (не выключаем)")
            elif leads == 0 and spend >= extended_spend_threshold:
                logger.info(f"💡 Инфо {adset_name} - Zero Leads, Spend ${spend:.2f} (не выключаем)")
            elif spend >= min_spend and leads < max_leads_threshold:
                logger.info(f"💡 Инфо {adset_name} - Low Leads: {leads} (не выключаем)")
            elif spend >= min_spend and leads > max_leads_threshold:
                logger.info(f"💡 Инфо {adset_name} - Too Many Leads: {leads} (не выключаем)")
            else:
                logger.info(f"✅ ОСТАВЛЯЕМ {adset_name} - CPA ${cpa:.2f}/{max_cpa:.2f}, Spend ${spend:.2f}, Leads {leads}")

    elif status == "PAUSED" and not manual_pause:
        logger.debug(f"Проверка условий для возобновления (GEO {geo})")

        # 🟢 условие возобновления: CPA снова в норме
        if (leads > 0 
            and leads <= max_leads_threshold
            and cpa <= max_cpa 
            and ucpc <= max_ucpc 
            and spend >= min_spend):
            should_resume = True
            logger.info(f"🟢 ВОЗОБНОВЛЯЕМ {adset_name} - CPA ${cpa:.2f} <= ${max_cpa:.2f}")

    # === Работа с токенами ===
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

    # === Пауза ===
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

    # === Возобновление ===
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
            }
        
        check_and_pause_campaigns(user_id)
        
        geo_rules = get_user_geo_rules(user_id)
        
        if not geo_rules:
            geo_rules = get_user_geo_config(user_id)
            logger.info("Используются правила из старой таблицы geo_config")
        
        known_geos = list(geo_rules.keys()) if geo_rules else []
        reserve_tokens = load_all_tokens(user_id)
        
        # 1. Получаем ВСЕ адсеты, как и раньше
        all_adsets = get_user_adsets(user_id)
        
        # 🔥 2. КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Фильтруем список, оставляя только активные адсеты
        active_adsets = [
            adset for adset in all_adsets
            if adset.get('status') == 'ACTIVE' and not adset.get('manual_pause')
        ]
        
        logger.info(f"Найдено {len(all_adsets)} всего адсетов. В обработку взято {len(active_adsets)} активных.")
        
        # 3. Теперь цикл работает с коротким списком `active_adsets`
        for adset in active_adsets:
            try:
                process_adset_control(user_id, adset, geo_rules, known_geos, reserve_tokens, session_obj, settings)
                
            except Exception as e:
                logger.error(f"Ошибка обработки адсета {adset.get('name', 'unknown')}: {e}")
                continue
                
        check_and_pause_campaigns(user_id)
        
    except Exception as e:
        logger.error(f"Критическая ошибка автоконтроля для пользователя {user_id}: {e}")
        send_telegram_message(f"🚫 Ошибка автоконтроля: {e}", user_id=user_id)
def perform_auto_refresh(user_id):
    """Выполнить автообновление данных"""
    try:
        logger.info(f"🔄 ВЫЗОВ perform_auto_refresh для user_id {user_id}")
        logger.info(f"📊 Начало автообновления данных для user_id {user_id}")
        
        settings = get_user_settings(user_id)
        logger.info(f"⚙️ Настройки автообновления: campaigns={settings.get('auto_refresh_campaigns', True)}, adsets={settings.get('auto_refresh_adsets', True)}")
        
        # 1. Автозаполнение резервных токенов
        logger.info("🔑 Автозаполнение резервных токенов...")
        auto_populate_reserve_tokens(user_id)
        logger.info("✅ Автозаполнение резервных токенов завершено")
        
        # 2. Обновление кампаний (если включено в настройках)
        if settings.get('auto_refresh_campaigns', True):
            logger.info("🔄 Обновление кампаний...")
            refresh_campaigns_internal(user_id)
            logger.info("✅ Обновление кампаний завершено")
        else:
            logger.info("⏭️ Обновление кампаний пропущено (отключено в настройках)")
        
        # 3. Обновление адсетов (если включено в настройках)
        if settings.get('auto_refresh_adsets', True):
            logger.info("🎯 Обновление адсетов...")
            from backend.campaign import get_user_campaigns
            campaigns = get_user_campaigns(user_id)
            accounts = {
                c['account_id']: c['token']
                for c in campaigns
                if c['account_id'] and c['token']
            }
            logger.info(f"📋 Найдено {len(accounts)} аккаунтов для обновления адсетов")
            
            for account_id, token in accounts.items():
                try:
                    logger.info(f"🔄 Обновление адсетов для аккаунта {account_id}")
                    refresh_adsets_internal(user_id, account_id, token)
                    logger.info(f"✅ Адсеты для аккаунта {account_id} обновлены")
                except Exception as e:
                    logger.error(f"❌ Ошибка обновления адсетов {account_id}: {e}")
                    logger.error(f"❌ Подробности ошибки: {traceback.format_exc()}")
                    
            logger.info("✅ Обновление адсетов завершено")
        else:
            logger.info("⏭️ Обновление адсетов пропущено (отключено в настройках)")
        
        # 4. Синхронизация с Keitaro
        logger.info("🔗 Синхронизация с Keitaro...")
        sync_keitaro(user_id)
        logger.info("✅ Синхронизация с Keitaro завершена")
        
        logger.info(f"✅ АВТООБНОВЛЕНИЕ ДАННЫХ ЗАВЕРШЕНО для user_id {user_id}")
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА в автообновлении: {e}")
        logger.error(f"❌ Подробности ошибки: {traceback.format_exc()}")
        raise  # Пробрасываем исключение дальше
def run_auto_control_for_user(user_id):
    """Циклический автоконтроль с интегрированным автообновлением"""
    logger.info(f"🎯 Запуск цикла автоконтроля для user_id {user_id}")
    
    # Счетчик циклов для отладки
    cycle_count = 0
    
    while True:
        cycle_count += 1
        logger.info(f"🔄 Цикл автоконтроля #{cycle_count} для user_id {user_id}")
        
        # Проверяем, нужно ли продолжать
        with auto_control_lock:
            if user_id not in auto_control_threads:
                logger.info(f"🛑 Автоконтроль остановлен (поток удален) для user_id {user_id}")
                break
            if not auto_control_threads[user_id].get('running', True):
                logger.info(f"🛑 Автоконтроль остановлен (флаг running=False) для user_id {user_id}")
                break
        
        try:
            # 🔄 ВЫПОЛНЯЕМ АВТООБНОВЛЕНИЕ ДАННЫХ ПЕРЕД КОНТРОЛЕМ
            logger.info(f"📊 === НАЧАЛО АВТООБНОВЛЕНИЯ ДАННЫХ (цикл #{cycle_count}) ===")
            perform_auto_refresh(user_id)
            logger.info(f"✅ === АВТООБНОВЛЕНИЕ ДАННЫХ ЗАВЕРШЕНО (цикл #{cycle_count}) ===")
            
            # 🎯 ВЫПОЛНЯЕМ АВТОКОНТРОЛЬ
            logger.info(f"🎯 === НАЧАЛО АВТОКОНТРОЛЯ (цикл #{cycle_count}) ===")
            auto_control(user_id)
            logger.info(f"✅ === АВТОКОНТРОЛЬ ЗАВЕРШЕН (цикл #{cycle_count}) ===")
            
            logger.info(f"✅ Цикл #{cycle_count} завершен успешно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле автоконтроля #{cycle_count}: {e}")
            logger.error(f"❌ Подробности ошибки: {traceback.format_exc()}")
        
        # ⏰ Ждем указанный интервал между циклами
        settings = get_user_settings(user_id)
        interval_minutes = 30
        interval_seconds = interval_minutes * 60
        
        logger.info(f"⏰ Ожидание {interval_minutes} минут до следующего цикла...")
        
        # Разбиваем ожидание на короткие интервалы для быстрой остановки
        check_interval = 10  # Проверяем каждые 10 секунд
        total_checks = interval_seconds // check_interval
        
        for i in range(total_checks):
            # Проверяем флаг остановки каждые 10 секунд
            with auto_control_lock:
                if user_id not in auto_control_threads:
                    logger.info("🛑 Остановка: поток удален из словаря")
                    return
                if not auto_control_threads[user_id].get('running', True):
                    logger.info("🛑 Остановка: флаг running=False")
                    return
            
            # Ждем 10 секунд
            time.sleep(check_interval)
            
        logger.info(f"⏰ Ожидание завершено, начинаем следующий цикл")
def start_auto_control_and_refresh(user_id: int, interval_minutes: int = None):
    """Запускает автоконтроль + автообновление (без лишнего таймера)"""
    logger.info(f"🚀 ЗАПУСК СИСТЕМЫ для user_id {user_id}")
    
    if interval_minutes is None:
        settings = get_user_settings(user_id)
        interval_minutes = 30
    
    # 🔄 СНАЧАЛА ВЫПОЛНЯЕМ РАЗОВОЕ ОБНОВЛЕНИЕ ДАННЫХ
    logger.info("🔄 Начальная синхронизация данных")
    try:
        perform_auto_refresh(user_id)
        logger.info("✅ Начальная синхронизация завершена")
    except Exception as e:
        logger.error(f"⚠️ Ошибка начальной синхронизации: {e}")
    
    # 🎯 ЗАПУСКАЕМ АВТОКОНТРОЛЬ (он внутри себя делает обновление перед каждым циклом)
    with auto_control_lock:
        if user_id in auto_control_threads:
            logger.info("⚠️ Автоконтроль уже запущен, останавливаем старую версию")
            auto_control_threads[user_id]['running'] = False
            # Даем время потоку остановиться
            time.sleep(2)
        
        # Создаем новый поток
        control_thread = threading.Thread(
            target=run_auto_control_for_user,
            args=(user_id,),
            daemon=True,
            name=f"AutoControl-{user_id}"
        )
        control_thread.start()
        auto_control_threads[user_id] = {
            'thread': control_thread, 
            'running': True,
            'start_time': time.time()
        }
        logger.info(f"🎯 Автоконтроль запущен в потоке {control_thread.name}")
    
    logger.info("🚀 СИСТЕМА ПОЛНОСТЬЮ ЗАПУЩЕНА")
    logger.info(f"📊 Режим: автоконтроль (с автообновлением внутри цикла, интервал {interval_minutes} мин)")
    
    return True
