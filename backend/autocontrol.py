import logging
import threading
import time
from typing import Dict, List, Optional, Callable
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

# Глобальная сессия для повторного использования соединений
_session = None
_session_lock = threading.Lock()

def get_session():
    """Получить глобальную сессию с повторным использованием соединений"""
    global _session
    with _session_lock:
        if _session is None:
            _session = requests.Session()
            _session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            # Настройки для оптимизации производительности
            adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=100, max_retries=3)
            _session.mount('http://', adapter)
            _session.mount('https://', adapter)
        return _session

def auto_populate_reserve_tokens(user_id: int):
    """Автозаполнение резервных токенов"""
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
    """Определение платформы по токену"""
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
    """Получить статус системы с учётом флагов running"""
    with auto_control_lock:
        auto_control_running = False
        control_info = ""
        if user_id in auto_control_threads:
            thread_info = auto_control_threads[user_id]
            auto_control_running = thread_info.get('running', False)
            control_info = f" (running: {auto_control_running})"
        
    with auto_refresh_lock:
        auto_refresh_running = user_id in auto_refresh_timers
        refresh_info = ""
        if auto_refresh_running:
            refresh_info = " (timer active)"
    
    settings = get_user_settings(user_id)
    interval = settings.get('auto_refresh_interval', 60)
    
    running = auto_control_running or auto_refresh_running
    
    logger.info(
        f"📊 СТАТУС СИСТЕМЫ user_id={user_id}: "
        f"control={auto_control_running}{control_info}, "
        f"refresh={auto_refresh_running}{refresh_info}, "
        f"interval={interval}мин, overall={'RUNNING' if running else 'STOPPED'}"
    )
    
    return {
        'running': running,
        'auto_control_running': auto_control_running,
        'auto_refresh_running': auto_refresh_running,
        'interval': interval
    }

def stop_auto_control_and_refresh(user_id: int):
    """Ручная остановка автоконтроля и автообновления"""
    logger.info(f"🛑 РУЧНАЯ остановка системы для пользователя {user_id}")
    
    # Останавливаем автоконтроль
    with auto_control_lock:
        if user_id in auto_control_threads:
            auto_control_threads[user_id]['running'] = False
            # Ждем завершения потока
            time.sleep(2)
            # Удаляем из словаря
            if user_id in auto_control_threads:
                del auto_control_threads[user_id]
            logger.info(f"⏹️ Автоконтроль остановлен для пользователя {user_id}")
        else:
            logger.info(f"⚠️ Автоконтроль не был запущен для пользователя {user_id}")
    
    # Останавливаем автообновление
    with auto_refresh_lock:
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
            del auto_refresh_timers[user_id]
            logger.info(f"⏹️ Таймер автообновления остановлен для пользователя {user_id}")
        else:
            logger.info(f"⚠️ Автообновление не было запущено для пользователя {user_id}")
    
    # Уведомление об остановке
    send_telegram_message(
        f"🛑 Система автоконтроля остановлена\n"
        f"🆔 Пользователь: {user_id}",
        user_id=user_id
    )

def start_auto_refresh(user_id, interval_minutes):
    """Запуск автообновления с заданным интервалом"""
    with auto_refresh_lock:
        if user_id in auto_refresh_timers:
            logger.info(f"⚠️ Автообновление уже запущено для пользователя {user_id}")
            return

        # Используем переданный интервал, а не фиксированный
        interval_seconds = interval_minutes * 60

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
    """Загрузка всех токенов пользователя"""
    all_tokens = {}
    
    try:
        # Токены из кампаний
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
        
        # Резервные токены
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

def calculate_cpm(spend: float, impressions: int) -> float:
    """Расчет CPM из spend и impressions"""
    if impressions > 0 and spend > 0:
        return (spend / impressions) * 1000
    return 0.0

class AdsetControlResult:
    """Класс для отслеживания результатов контроля адсета"""
    def __init__(self):
        self.paused_count = 0
        self.resumed_count = 0
        self.errors_count = 0
        self.processed_adsets = []

def process_adset_control(user_id, adset, geo_rules, known_geos, reserve_tokens, session_obj, settings, result_tracker):
    """Обработка контроля одного адсета с отслеживанием изменений"""
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
    exclude_from_autocontrol = bool(adset.get('exclude_from_autocontrol', 0))
    
    # Проверка исключений
    if exclude_from_autocontrol:
        logger.info(f"⏭️ Адсет {adset_name} исключен из автоконтроля")
        return
        
    if any(marker in adset_name.upper() for marker in ['#NOAUTO', '#EXCLUDE', '#ИСКЛ']):
        logger.info(f"⏭️ Адсет {adset_name} исключен по маркеру в названии")
        return
        
    logger.debug(f"Обработка адсета: {adset_name} "
                 f"(ID: {adset_id}, статус: {status}, effective_status: {effective_status})")

    geo = extract_geo_from_name(adset_name, known_geos)

    if geo == 'N/A' or geo not in geo_rules:
        logger.info(f"⏭️ Пропускаем {adset_name} (неизвестное GEO: {geo})")
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

    # Загружаем правила GEO
    max_cpa = rule.get("max_cpa", 100)
    min_spend = rule.get("min_spend", 50)
    max_leads_threshold = rule.get("max_leads_threshold", 1)
    extended_spend_threshold = rule.get("extended_spend_threshold", min_spend)
    max_ucpc = rule.get("max_ucpc", 100)
    max_ucpc_spend = rule.get("max_ucpc_spend", min_spend)

    # 🔴 Логика выключения
    if status == "ACTIVE" and not manual_pause:
        logger.debug(f"Правила для GEO {geo}: max_cpa={max_cpa}, min_spend={min_spend}, "
                     f"extended_spend_threshold={extended_spend_threshold}")

        # 1) Есть лиды, но CPA выше нормы
        if leads > 0 and cpa > max_cpa and spend >= min_spend:
            should_pause = True
            pause_reason = f"CPA ${cpa:.2f} > Max CPA ${max_cpa:.2f}"
            logger.warning(f"🚨 ВЫКЛЮЧАЕМ {adset_name} - {pause_reason}")

        # 2) Нет лидов, но перерасход бюджета
        elif leads == 0 and spend >= extended_spend_threshold:
            should_pause = True
            pause_reason = (f"0 лидов, Spend ${spend:.2f} >= "
                            f"Extended Spend Threshold ${extended_spend_threshold:.2f}")
            logger.warning(f"🚨 ВЫКЛЮЧАЕМ {adset_name} - {pause_reason}")

    # 🟢 Логика возобновления
    elif status == "PAUSED" and not manual_pause:
        logger.debug(f"Проверка условий для возобновления {adset_name} (GEO {geo})")

        # 1) Если есть лиды и CPA снова в норме
        if leads > 0 and cpa <= max_cpa and spend >= min_spend:
            should_resume = True
            logger.info(f"🟢 ВОЗОБНОВЛЯЕМ {adset_name} - CPA ${cpa:.2f} <= Max CPA ${max_cpa:.2f}")

        # 2) Если лидов нет, но расходы упали ниже extended_spend_threshold
        elif leads == 0 and spend < extended_spend_threshold:
            should_resume = True
            logger.info(f"🟢 ВОЗОБНОВЛЯЕМ {adset_name} - 0 лидов, но Spend ${spend:.2f} < "
                        f"Extended Spend Threshold ${extended_spend_threshold:.2f}")

    # === Работа с токенами ===
    token_list = reserve_tokens.get(king, [])
    if token and token not in token_list:
        token_list = [token] + token_list

    if not token_list:
        logger.warning(f"Нет доступных токенов для KING={king}, адсет {adset_name}")
        return

    def execute_with_token_rotation(api_call_func: Callable) -> bool:
        """Выполнить API-вызов с ротацией токенов"""
        for idx, current_token in enumerate(token_list):
            try:
                result = api_call_func(current_token)
                if result:
                    return True
            except Exception as e:
                error_msg = str(e).lower()
                if any(limit_error in error_msg for limit_error in [
                    'request limit', 'rate limit', 'too many requests',
                    'application request limit', 'quota'
                ]):
                    if idx + 1 < len(token_list):
                        logger.warning(f"Токен {idx+1} исчерпан, пробуем следующий...")
                        continue
                    else:
                        raise Exception(f"❌ Все токены исчерпаны для KING={king}")
                else:
                    raise e
        return False

    # === Пауза ===
    if should_pause:
        def pause_adset(current_token: str) -> bool:
            """Функция паузы адсета"""
            url = f"https://graph.facebook.com/v18.0/{adset_id}"
            data = {"status": "PAUSED"}
            resp = session_obj.post(url, params={"access_token": current_token}, data=data, timeout=10).json()
            if resp.get("success") or resp.get("id") == adset_id:
                update_user_adset_status(user_id, adset_id, "PAUSED")
                result_tracker.paused_count += 1
                msg = (f"🔴 Отключен: {adset_name} "
                       f"(GEO={geo}, CPA={cpa:.2f}, Leads={leads}, Spend={spend:.2f}) "
                       f"— причина: {pause_reason}")
                logger.info(msg)
                send_telegram_message(msg, user_id=user_id)
                return True
            return False

        success = execute_with_token_rotation(pause_adset)
        if success:
            result_tracker.processed_adsets.append({
                'name': adset_name,
                'id': adset_id,
                'action': 'PAUSED',
                'reason': pause_reason
            })

    # === Возобновление ===
    elif should_resume:
        def resume_adset(current_token: str) -> bool:
            """Функция возобновления адсета"""
            url = f"https://graph.facebook.com/v18.0/{adset_id}"
            data = {"status": "ACTIVE"}
            resp = session_obj.post(url, params={"access_token": current_token}, data=data, timeout=10).json()
            if resp.get("success") or resp.get("id") == adset_id:
                update_user_adset_status(user_id, adset_id, "ACTIVE")
                result_tracker.resumed_count += 1
                msg = (f"🟢 Возобновлен: {adset_name} "
                       f"(GEO={geo}, CPA={cpa:.2f}, Leads={leads}, Spend={spend:.2f})")
                logger.info(msg)
                send_telegram_message(msg, user_id=user_id)
                return True
            return False

        success = execute_with_token_rotation(resume_adset)
        if success:
            result_tracker.processed_adsets.append({
                'name': adset_name,
                'id': adset_id,
                'action': 'RESUMED',
                'reason': 'Условия улучшились'
            })

def auto_control(user_id):
    """Основная функция автоконтроля с оптимизацией производительности"""
    try:
        logger.info(f"=== НАЧАЛО АВТОКОНТРОЛЯ ДЛЯ ПОЛЬЗОВАТЕЛЯ {user_id} ===")
        
        settings = get_user_settings(user_id)      
        session_obj = get_session()
        
        if settings.get('use_proxy') and settings.get('proxy'):
            session_obj.proxies = {
                'http': settings.get('proxy'),
                'https': settings.get('proxy'),
            }
        
        # Загрузка GEO правил
        geo_rules = get_user_geo_rules(user_id)
        if not geo_rules:
            geo_rules = get_user_geo_config(user_id)
            logger.info("Используются правила из старой таблицы geo_config")
        
        known_geos = list(geo_rules.keys()) if geo_rules else []
        reserve_tokens = load_all_tokens(user_id)
        
        # Получение всех адсетов
        all_adsets = get_user_adsets(user_id)
        
        # Фильтрация активных адсетов
        active_adsets = [
            adset for adset in all_adsets
            if not adset.get('manual_pause') and 
            not adset.get('exclude_from_autocontrol') and
            not any(marker in adset.get('name', '').upper() for marker in ['#NOAUTO', '#EXCLUDE', '#ИСКЛ'])
        ]
            
        logger.info(f"Найдено {len(all_adsets)} всего адсетов. В обработку взято {len(active_adsets)} активных.")
        
        # Инициализация трекера результатов
        result_tracker = AdsetControlResult()
        
        # Обработка адсетов
        for adset in active_adsets:
            try:
                process_adset_control(user_id, adset, geo_rules, known_geos, reserve_tokens, session_obj, settings, result_tracker)
            except Exception as e:
                logger.error(f"Ошибка обработки адсета {adset.get('name', 'unknown')}: {e}")
                result_tracker.errors_count += 1
                continue
        
        # Финальная проверка и пауза кампаний (только один раз в конце)
        check_and_pause_campaigns(user_id)
        
        # Детальное логирование результатов
        logger.info(f"📊 ИТОГИ АВТОКОНТРОЛЯ: "
                   f"Приостановлено: {result_tracker.paused_count}, "
                   f"Возобновлено: {result_tracker.resumed_count}, "
                   f"Ошибок: {result_tracker.errors_count}")
        
        # Итоговое уведомление (только при изменениях или ошибках)
        if result_tracker.paused_count > 0 or result_tracker.resumed_count > 0 or result_tracker.errors_count > 0:
            send_telegram_message(
                f"📊 Автоконтроль завершен\n"
                f"• Всего адсетов: {len(all_adsets)}\n"
                f"• Обработано: {len(active_adsets)}\n"
                f"• Приостановлено: {result_tracker.paused_count}\n"
                f"• Возобновлено: {result_tracker.resumed_count}\n"
                f"• Ошибок: {result_tracker.errors_count}",
                user_id=user_id
            )
        
        # Детальное уведомление о конкретных изменениях (если есть)
        if result_tracker.processed_adsets:
            detailed_message = "🔍 Изменения:\n"
            for adset_info in result_tracker.processed_adsets[:10]:  # Ограничиваем первые 10
                detailed_message += f"• {adset_info['name']} - {adset_info['action']}\n"
            
            if len(result_tracker.processed_adsets) > 10:
                detailed_message += f"• ... и еще {len(result_tracker.processed_adsets) - 10} изменений\n"
            
            send_telegram_message(detailed_message, user_id=user_id)
        
    except Exception as e:
        logger.error(f"Критическая ошибка автоконтроля для пользователя {user_id}: {e}")
        send_telegram_message(f"🚫 Ошибка автоконтроля: {e}", user_id=user_id)

def perform_auto_refresh(user_id, send_notifications=True):
    """Выполнить автообновление данных с оптимизацией"""
    try:
        logger.info(f"🔄 ВЫЗОВ perform_auto_refresh для user_id {user_id}")
        
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
            if send_notifications:
                send_telegram_message("✅ Обновление кампаний завершено", user_id=user_id)
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
            if send_notifications:
                send_telegram_message("✅ Обновление адсетов завершено", user_id=user_id)
        else:
            logger.info("⏭️ Обновление адсетов пропущено (отключено в настройках)")
        
        # 4. Синхронизация с Keitaro
        logger.info("🔗 Синхронизация с Keitaro...")
        sync_keitaro(user_id)
        logger.info("✅ Синхронизация с Keitaro завершена")
        if send_notifications:
            send_telegram_message("✅ Синхронизация с Keitaro завершена", user_id=user_id)
        
        logger.info(f"✅ АВТООБНОВЛЕНИЕ ДАННЫХ ЗАВЕРШЕНО для user_id {user_id}")
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА в автообновлении: {e}")
        logger.error(f"❌ Подробности ошибки: {traceback.format_exc()}")
        if send_notifications:
            send_telegram_message(f"❌ Критическая ошибка автообновления: {e}", user_id=user_id)
        raise

def run_auto_control_for_user(user_id):
    """Циклический автоконтроль с интегрированным автообновлением"""
    logger.info(f"🎯 Запуск цикла автоконтроля для user_id {user_id}")
    
    # Уведомление о начале работы цикла отправляется только один раз
    # при запуске системы, а не при каждом цикле
    
    cycle_count = 0
    
    while True:
        cycle_count += 1
        logger.info(f"🔄 Цикл автоконтроля #{cycle_count} для user_id {user_id}")
        
        # Проверяем, нужно ли продолжать
        with auto_control_lock:
            if user_id not in auto_control_threads:
                logger.info(f"🛑 Автоконтроль остановлен (поток удален) для user_id {user_id}")
                # Уведомление об остановке уже отправлено в stop_auto_control_and_refresh
                break
            if not auto_control_threads[user_id].get('running', True):
                logger.info(f"🛑 Автоконтроль остановлен (флаг running=False) для user_id {user_id}")
                # Уведомление об остановке уже отправлено в stop_auto_control_and_refresh
                break
        
        try:
            # 🔄 АВТООБНОВЛЕНИЕ ДАННЫХ ПЕРЕД КОНТРОЛЕМ (без уведомлений)
            logger.info(f"📊 === НАЧАЛО АВТООБНОВЛЕНИЯ ДАННЫХ (цикл #{cycle_count}) ===")
            perform_auto_refresh(user_id, send_notifications=False)
            logger.info(f"✅ === АВТООБНОВЛЕНИЕ ДАННЫХ ЗАВЕРШЕНО (цикл #{cycle_count}) ===")
            
            # 🎯 АВТОКОНТРОЛЬ
            logger.info(f"🎯 === НАЧАЛО АВТОКОНТРОЛЯ (цикл #{cycle_count}) ===")
            auto_control(user_id)
            logger.info(f"✅ === АВТОКОНТРОЛЬ ЗАВЕРШЕН (цикл #{cycle_count}) ===")
            
            logger.info(f"✅ Цикл #{cycle_count} завершен успешно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле автоконтроля #{cycle_count}: {e}")
            logger.error(f"❌ Подробности ошибки: {traceback.format_exc()}")
            
            send_telegram_message(
                f"❌ Ошибка в цикле автоконтроля #{cycle_count}:\n"
                f"{str(e)[:200]}...",
                user_id=user_id
            )
        
        # ⏰ Ожидание между циклами
        settings = get_user_settings(user_id)
        interval_minutes = settings.get('auto_refresh_interval', 30)
        interval_seconds = interval_minutes * 60
        
        logger.info(f"⏰ Ожидание {interval_minutes} минут до следующего цикла...")
        
        # Разбиваем ожидание для быстрой остановки
        check_interval = 10
        total_checks = interval_seconds // check_interval
        
        for i in range(total_checks):
            with auto_control_lock:
                if user_id not in auto_control_threads:
                    logger.info("🛑 Остановка: поток удален из словаря")
                    return
                if not auto_control_threads[user_id].get('running', True):
                    logger.info("🛑 Остановка: флаг running=False")
                    return
            time.sleep(check_interval)
            
        logger.info(f"⏰ Ожидание завершено, начинаем следующий цикл")

def start_auto_control_and_refresh(user_id: int, interval_minutes: int = None):
    """Запускает автоконтроль + автообновление (с защитой от дублирования)"""
    logger.info(f"🚀 ЗАПУСК СИСТЕМЫ для user_id {user_id}")
    
    # Проверяем, не запущена ли система уже
    with auto_control_lock:
        if user_id in auto_control_threads and auto_control_threads[user_id].get('running', False):
            logger.info(f"⚠️ Система уже запущена для пользователя {user_id}")
            send_telegram_message(
                f"⚠️ Система уже запущена\n"
                f"🆔 Пользователь: {user_id}",
                user_id=user_id
            )
            return False
    
    if interval_minutes is None:
        settings = get_user_settings(user_id)
        interval_minutes = settings.get('auto_refresh_interval', 30)
    
    # Уведомление о запуске системы
    send_telegram_message(
        f"🚀 Система автоконтроля запущена\n"
        f"⏰ Интервал: {interval_minutes} минут\n"
        f"🆔 Пользователь: {user_id}",
        user_id=user_id
    )
    
    # 🔄 НАЧАЛЬНАЯ СИНХРОНИЗАЦИЯ ДАННЫХ
    logger.info("🔄 Начальная синхронизация данных")
    try:
        perform_auto_refresh(user_id, send_notifications=True)
        logger.info("✅ Начальная синхронизация завершена")
        # Уведомление уже отправлено в perform_auto_refresh
    except Exception as e:
        logger.error(f"⚠️ Ошибка начальной синхронизации: {e}")
        send_telegram_message(f"❌ Ошибка начальной синхронизации: {e}", user_id=user_id)
    
    # 🎯 ЗАПУСК АВТОКОНТРОЛЯ
    with auto_control_lock:
        # Останавливаем предыдущий запуск, если есть (на всякий случай)
        if user_id in auto_control_threads:
            logger.info("⚠️ Останавливаем предыдущую версию автоконтроля")
            auto_control_threads[user_id]['running'] = False
            time.sleep(3)
        
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
            'start_time': time.time(),
            'interval': interval_minutes
        }
        logger.info(f"🎯 Автоконтроль запущен в потоке {control_thread.name}")
    
    logger.info("🚀 СИСТЕМА ПОЛНОСТЬЮ ЗАПУЩЕНА")
    logger.info(f"📊 Режим: автоконтроль (с автообновлением внутри цикла, интервал {interval_minutes} мин)")
    
    return True