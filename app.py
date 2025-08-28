import json
import logging
import os
import re
import threading
from functools import wraps
from logging.handlers import RotatingFileHandler

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   session, url_for)
from fuzzywuzzy import fuzz, process

from database import (add_user_adset, add_user_campaign, authenticate_user,
                      create_user, get_adset_budget_settings,
                      get_db_connection, get_user_adsets, get_user_campaigns,
                      get_user_geo_config, get_user_geo_rules,
                      get_user_settings, init_db, update_campaign_stats,
                      update_user_adset_budget, update_user_adset_status,
                      update_user_campaign_status, update_user_settings)

lock = threading.Lock()

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('app.log', maxBytes=100000, backupCount=3),
        logging.StreamHandler()
    ]
)
app = Flask(__name__)
app.secret_key = 'your_very_secret_key_here'

# Настройка логироваcния
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import datetime
import json
import time
from typing import Dict, Optional, Set, Tuple

auto_control_threads = {}
auto_control_lock = threading.Lock()
auto_refresh_timers = {}
auto_refresh_lock = threading.Lock()

def login_required(f):
    """Декоратор для проверки аутентификации пользователя"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def start_auto_control_and_refresh(user_id):
    """Запускает и автоконтроль и автообновление вместе"""
    settings = get_user_settings(user_id)
    interval = settings.get('auto_refresh_interval', 5)
    
    # Запускаем автоконтроль
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
    
    # Запускаем автообновление
    with auto_refresh_lock:
        # Останавливаем предыдущий таймер, если есть
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
        
        # Создаем новый таймер
        interval_seconds = interval * 60
        timer = threading.Timer(interval_seconds, lambda: auto_refresh_user_data(user_id, interval))
        timer.daemon = True
        timer.start()
        
        auto_refresh_timers[user_id] = timer
        logger.info(f"Автообновление запущено для пользователя {user_id}, интервал: {interval} мин")

def stop_auto_control_and_refresh(user_id):
    """Останавливает и автоконтроль и автообновление вместе"""
    # Останавливаем автоконтроль
    with auto_control_lock:
        if user_id in auto_control_threads:
            auto_control_threads[user_id]['running'] = False
            del auto_control_threads[user_id]
            logger.info(f"Автоконтроль остановлен для пользователя {user_id}")
    
    # Останавливаем автообновление
    with auto_refresh_lock:
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
            del auto_refresh_timers[user_id]
            logger.info(f"Автообновление остановлено для пользователя {user_id}")

def get_combined_auto_status(user_id):
    """Возвращает комбинированный статус автоконтроля и автообновления"""
    with auto_control_lock:
        auto_control_running = user_id in auto_control_threads
        
    with auto_refresh_lock:
        auto_refresh_running = user_id in auto_refresh_timers
        settings = get_user_settings(user_id)
        interval = settings.get('auto_refresh_interval', 5)
    
    # Считаем, что система работает, если работает хотя бы один компонент
    running = auto_control_running or auto_refresh_running
    
    return {
        'running': running,
        'auto_control_running': auto_control_running,
        'auto_refresh_running': auto_refresh_running,
        'interval': interval
    }

def get_session():
    """Создает и возвращает сессию requests с настройками"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    return session
def fetch_keitaro_report(api_key, domain, interval="today"):
    """
    Получает отчет из Keitaro.
    Считает лиды по формуле Spend / CPA.
    Берёт CPC и UCPC из Keitaro.
    Группировка только по sub_id_9 (название адсета).
    """
    logger = logging.getLogger(__name__)
    url = f"https://{domain}/admin_api/v1/report/build"
    headers = {"Api-Key": api_key, "Content-Type": "application/json"}

    metrics = ["ucpc", "cpc", "conversions", "cost", "cpa"]
    limit = 250
    offset = 0
    all_rows = []

    try:
        while True:
            payload = {
                "range": {"interval": interval, "timezone": "Europe/Moscow"},
                "metrics": metrics,
                "grouping": ["sub_id_9"],   # 🚨 только имя адсета
                "filters": [],
                "sort": [{"name": "ucpc", "order": "desc"}],
                "limit": limit,
                "offset": offset
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            report = response.json()

            rows = report.get("rows", [])
            if not rows:
                break

            for row in rows:
                cost = float(row.get("cost", 0) or 0)
                cpa = float(row.get("cpa", 0) or 0)
                cpc = float(row.get("cpc", 0) or 0)

                leads = round(cost / cpa) if cpa > 0 and cost > 0 else 0
                row["leads"] = leads
                row["cpc"] = cpc

            all_rows.extend(rows)

            if len(rows) < limit:
                break
            offset += limit

        return {"rows": all_rows}

    except Exception as e:
        logger.error(f"Ошибка при запросе отчета Keitaro: {e}")
        return {"rows": []}

def send_telegram_message(message, chat_id=None, bot_token=None, user_id=None):
    """Безопасная отправка сообщения в Telegram"""
    try:
        # Если нет chat_id или bot_token — пробуем получить из настроек
        if user_id and (not chat_id or not bot_token):
            settings = get_user_settings(user_id)
            chat_id = chat_id or settings.get('telegram_chat_id')
            bot_token = bot_token or settings.get('telegram_bot_token')

        if not chat_id or not bot_token:
            logger.debug("Telegram не настроен — пропуск отправки")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }

        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True

    except Exception as e:
        logger.warning(f"Telegram сообщение не отправлено: {e}")
        return False
import json
from typing import Any, Dict, List

# Добавьте в начало файла с другими импортами
import requests


def get_all_users() -> List[Dict[str, Any]]:
    """Получает список всех пользователей"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, created_at FROM users ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей: {e}")
        return []
def get_user_accounts_stats(user_id: int) -> List[Dict[str, Any]]:
    """Получает статистику по аккаунтам пользователя с проверкой валидности"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Получаем ВСЕ аккаунты, включая невалидные
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
                
                # Добавляем даже невалидные аккаунты для отображения
                accounts.append({
                    'account_id': account_id or 'N/A',
                    'token': token or 'N/A'
                })
            
            logger.info(f"Найдено {len(accounts)} аккаунтов у пользователя {user_id}")
            return accounts
            
    except Exception as e:
        logger.error(f"Ошибка получения статистики аккаунтов пользователя {user_id}: {e}")
        return []
@app.route('/api/admin/test_tokens')
@login_required
def test_tokens():
    """Тестирует токены всех аккаунтов"""
    if not is_admin_user(session['user_id']):
        return jsonify({'success': False, 'error': 'Доступ запрещен'})
    
    try:
        all_accounts = get_all_accounts_stats()
        results = []
        
        for account in all_accounts:
            account_info = get_account_limits_info(account['account_id'], account['token'])
            
            result = {
                'user_id': account['user_id'],
                'username': account['username'],
                'account_id': account['account_id'],
                'token_valid': False,
                'error': None
            }
            
            if account_info:
                if 'error' in account_info:
                    result['error'] = account_info['error']
                else:
                    result['token_valid'] = True
                    result['account_name'] = account_info['name']
                    result['status'] = account_info['status']
            
            results.append(result)
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Ошибка тестирования токенов: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/admin/debug_accounts')
@login_required
def debug_accounts():
    """Отладочная информация об аккаунтах"""
    if not is_admin_user(session['user_id']):
        return jsonify({'success': False, 'error': 'Доступ запрещен'})
    
    try:
        # Получаем сырые данные
        users = get_all_users()
        all_accounts_data = get_all_accounts_stats()
        
        # Проверяем аккаунты
        checked_accounts = []
        for account_data in all_accounts_data:
            account_info = get_account_limits_info(account_data['account_id'], account_data['token'])
            if account_info:
                account_info.update(account_data)
                checked_accounts.append(account_info)
        
        return jsonify({
            'success': True,
            'users_count': len(users),
            'raw_accounts_count': len(all_accounts_data),
            'valid_accounts_count': len(checked_accounts),
            'users': users,
            'raw_accounts': all_accounts_data[:10],  # Первые 10 для отладки
            'valid_accounts': checked_accounts[:10]   # Первые 10 для отладки
        })
        
    except Exception as e:
        logger.error(f"Ошибка отладки аккаунтов: {e}")
        return jsonify({'success': False, 'error': str(e)})
def get_all_accounts_stats() -> List[Dict[str, Any]]:
    """Получает статистику по всем аккаунтам всех пользователей"""
    try:
        users = get_all_users()
        all_accounts = []
        
        for user in users:
            user_id = user['id']
            try:
                # Получаем аккаунты пользователя
                accounts = get_user_accounts_stats(user_id)
                
                for account in accounts:
                    account_info = {
                        'user_id': user_id,
                        'username': user['username'],
                        'account_id': account['account_id'],
                        'token': account['token']
                    }
                    all_accounts.append(account_info)
                    
            except Exception as e:
                logger.error(f"Ошибка получения аккаунтов пользователя {user_id}: {e}")
                continue
        
        logger.info(f"Найдено {len(all_accounts)} аккаунтов у {len(users)} пользователей")
        return all_accounts
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики всех аккаунтов: {e}")
        return []
def get_account_limits_info(account_id: str, access_token: str) -> Dict[str, Any]:
    """Получает информацию о лимитах аккаунта из Facebook API"""
    try:
        # Проверяем валидность входных данных
        if not account_id or account_id == 'N/A' or not access_token or access_token == 'N/A':
            return {
                'account_id': account_id or 'unknown',
                'name': 'Невалидные данные',
                'status': 'INVALID_DATA',
                'spend': 0,
                'balance': 0,
                'spend_cap': 0,
                'daily_limit': 0,
                'requests_today': 0,
                'requests_limit': 100,
                'requests_usage_percent': 0,
                'error': 'Невалидный account_id или token'
            }
        
        clean_account_id = account_id.replace('act_', '')
        
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}"
        
        # Упрощенные поля
        params = {
            'fields': 'id,name,account_status,amount_spent,balance,spend_cap',
            'access_token': access_token
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        # Проверяем наличие ошибок в ответе
        if 'error' in data:
            error_msg = data['error'].get('message', 'Unknown error')
            error_code = data['error'].get('code', 'Unknown')
            
            return {
                'account_id': clean_account_id,
                'name': f'Ошибка: {error_code}',
                'status': 'API_ERROR',
                'spend': 0,
                'balance': 0,
                'spend_cap': 0,
                'daily_limit': 0,
                'requests_today': 0,
                'requests_limit': 100,
                'requests_usage_percent': 0,
                'error': f"{error_code}: {error_msg}"
            }
        
        # Успешный ответ - конвертируем центы в доллары
        amount_spent = float(data.get('amount_spent', 0)) / 100
        balance = float(data.get('balance', 0)) / 100
        spend_cap = float(data.get('spend_cap', 0)) / 100
        
        return {
            'account_id': clean_account_id,
            'name': data.get('name', 'N/A'),
            'status': data.get('account_status', 'UNKNOWN'),
            'spend': amount_spent,
            'balance': balance,
            'spend_cap': spend_cap,
            'daily_limit': 0,
            'requests_today': 0,
            'requests_limit': 100,
            'requests_usage_percent': 0
        }
        
    except requests.exceptions.RequestException as e:
        return {
            'account_id': account_id.replace('act_', ''),
            'name': 'Ошибка сети',
            'status': 'NETWORK_ERROR',
            'spend': 0,
            'balance': 0,
            'spend_cap': 0,
            'daily_limit': 0,
            'requests_today': 0,
            'requests_limit': 100,
            'requests_usage_percent': 0,
            'error': f"Ошибка сети: {str(e)}"
        }
    except Exception as e:
        return {
            'account_id': account_id.replace('act_', ''),
            'name': 'Неизвестная ошибка',
            'status': 'ERROR',
            'spend': 0,
            'balance': 0,
            'spend_cap': 0,
            'daily_limit': 0,
            'requests_today': 0,
            'requests_limit': 100,
            'requests_usage_percent': 0,
            'error': f"Неизвестная ошибка: {str(e)}"
        }
def get_reserve_tokens(user_id: int, king: str = None) -> Dict[str, List[str]]:
    """Получает резервные токены для конкретного KING или все"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            if king:
                cursor.execute(
                    "SELECT token FROM reserve_tokens WHERE user_id = ? AND king = ?",
                    (user_id, king)
                )
            else:
                cursor.execute(
                    "SELECT king, token FROM reserve_tokens WHERE user_id = ?",
                    (user_id,)
                )
            
            tokens = {}
            for row in cursor.fetchall():
                if 'king' in row:
                    k = row['king']
                    token = row['token']
                else:
                    k = king
                    token = row['token']
                
                if k not in tokens:
                    tokens[k] = []
                tokens[k].append(token)
            
            return tokens
    except Exception as e:
        logger.error(f"Ошибка получения резервных токенов: {e}")
        return {}
def auto_control(user_id):
    """Функция автоконтроля для работы с базой данных и резервными токенами"""
    try:
        # Получаем настройки пользователя
        settings = get_user_settings(user_id)
        
        # Создаем сессию с прокси если нужно
        session_obj = get_session()
        if settings.get('use_proxy') and settings.get('proxy'):
            session_obj.proxies = {
                'http': settings.get('proxy'),
                'https': settings.get('proxy')
            }
        check_and_pause_campaigns(user_id)
    except Exception as e:
        msg = f"🚫 Сессия не создана: {e}"
        logger.error(msg)
    try:
        send_telegram_message("🔴 AdSet отключён", user_id=user_id)
    except Exception as e:
        logger.warning(f"Telegram сообщение не отправлено: {e}")
        return

    try:
        # Получаем правила GEO из новой таблицы geo_rules
        geo_rules = get_user_geo_rules(user_id)
        
        # Если нет правил в новой таблице, используем старую geo_config
        if not geo_rules:
            geo_rules = get_user_geo_config(user_id)
            logger.info("Используются правила из старой таблицы geo_config")
        
        # Получаем список известных GEO кодов для улучшенного распознавания
        known_geos = list(geo_rules.keys()) if geo_rules else []
        
        # Получаем резервные токены из отдельной таблицы
        reserve_tokens = load_reserve_tokens(user_id)
        
    except Exception as e:
        logger.error(f"Ошибка чтения конфигов: {e}")
        send_telegram_message(settings.get('telegram_chat_id'), f"Ошибка чтения конфигов: {e}", settings.get('telegram_bot_token'))
        return

    try:
        # Получаем все адсеты пользователя из базы данных
        adsets = get_user_adsets(user_id)
        
    except Exception as e:
        logger.error(f"Ошибка чтения адсетов: {e}")
        send_telegram_message(settings.get('telegram_chat_id'), f"Ошибка чтения адсетов: {e}", settings.get('telegram_bot_token'))
        return

    for adset in adsets:
        try:
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
            
            # Извлекаем GEO с улучшенной логикой
            geo = extract_geo_from_name(adset_name, known_geos)
            
            # Пропускаем если нет GEO
            if geo == 'N/A' or geo not in geo_rules:
                msg = f"⏭️ Пропускаем (неизвестное GEO: {geo}) {adset_name}"
                logger.info(msg)
                continue

            rule = geo_rules[geo]
            should_pause = False
            should_resume = False
            pause_reason = ""

            # Логика автоконтроля (адаптированная для новой структуры правил)
            if status == "ACTIVE" and not manual_pause:
                # Используем max_cpa вместо cpa_red
                max_cpa = rule.get("max_cpa", rule.get("cpa_red", 100))
                min_spend = rule.get("min_spend", rule.get("spend_zero_leads", 50))
                
                if leads == 0 and ucpc > max_cpa and spend >= min_spend:
                    should_pause = True
                    pause_reason = "uCPC"
                elif leads > 0 and cpa > max_cpa and spend >= min_spend:
                    should_pause = True
                    pause_reason = "CPA"
                elif spend >= min_spend and leads == 0:
                    should_pause = True
                    pause_reason = "Zero Leads"

            if status == "PAUSED" and not manual_pause:
                cpa_green = rule.get("cpa_green", 20)
                cpa_orange = rule.get("cpa_orange", 50)
                min_spend_half = rule.get("min_spend", rule.get("spend_zero_leads", 50)) / 2
                
                if (leads > 0 and cpa <= cpa_green
                    and ucpc <= cpa_orange
                    and spend >= min_spend_half):
                    should_resume = True

            url = f"https://graph.facebook.com/v18.0/{adset_id}"

            # --- Получаем токены: основной + резервные ---
            token_list = reserve_tokens.get(king, [])
            if token and token not in token_list:
                token_list = [token] + token_list  # основной токен первым

            # --- Отключение ---
            if should_pause:
                for idx, current_token in enumerate(token_list):
                    try:
                        resp = session_obj.post(
                            url,
                            params={"access_token": current_token},
                            data={"status": "PAUSED"},
                            timeout=10
                        ).json()

                        if resp.get("success") or resp.get("id") == adset_id:
                            # Обновляем статус в базе
                            update_user_adset_status(user_id, adset_id, "PAUSED")
                            
                            msg = (f"🔴 Отключен: {adset_name} "
                                   f"(GEO={geo}, CPA={cpa:.2f}, uCPC={ucpc:.2f}, Leads={leads}, Spend={spend:.2f}) — причина: {pause_reason}")
                            logger.info(msg)
                            send_telegram_message(settings.get('telegram_chat_id'), msg, settings.get('telegram_bot_token'))
                            break

                        if ("error" in resp and
                            "Application request limit" in resp["error"].get("message", "")):
                            if idx + 1 < len(token_list):
                                logger.warning(f"⚠️ Токен №{idx+1} достиг лимита. Пробуем следующий...")
                                continue
                            else:
                                raise Exception(f"❌ Все токены исчерпаны для KING={king}")
                        else:
                            raise Exception(resp)

                    except Exception as e:
                        msg = f"❌ Ошибка отключения {adset_name} (токен {idx+1}): {e}"
                        logger.error(msg)
                        send_telegram_message(settings.get('telegram_chat_id'), msg, settings.get('telegram_bot_token'))
                        break

            # --- Включение ---
            elif should_resume:
                for idx, current_token in enumerate(token_list):
                    try:
                        resp = session_obj.post(
                            url,
                            params={"access_token": current_token},
                            data={"status": "ACTIVE"},
                            timeout=10
                        ).json()

                        if resp.get("success") or resp.get("id") == adset_id:
                            # Обновляем статус в базе
                            update_user_adset_status(user_id, adset_id, "ACTIVE")
                            
                            msg = (f"🟢 Включен: {adset_name} "
                                   f"(GEO={geo}, CPA={cpa:.2f}, uCPC={ucpc:.2f}, Leads={leads}, Spend={spend:.2f})")
                            logger.info(msg)
                            send_telegram_message(settings.get('telegram_chat_id'), msg, settings.get('telegram_bot_token'))
                            break

                        if ("error" in resp and
                            "Application request limit" in resp["error"].get("message", "")):
                            if idx + 1 < len(token_list):
                                logger.warning(f"⚠️ Токен №{idx+1} достиг лимита. Пробуем следующий...")
                                continue
                            else:
                                raise Exception(f"❌ Все токены исчерпаны для KING={king}")
                        else:
                            raise Exception(resp)

                    except Exception as e:
                        msg = f"❌ Ошибка включения {adset_name} (токен {idx+1}): {e}"
                        logger.error(msg)
                        send_telegram_message(settings.get('telegram_chat_id'), msg, settings.get('telegram_bot_token'))
                        break

        except Exception as e:
            logger.error(f"Ошибка обработки адсета {adset.get('name', 'unknown')}: {e}")
            continue

def is_admin_user(user_id):
    """Проверяет, является ли пользователь администратором"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return False
            
            # Список администраторов - можно хранить в настройках или отдельной таблице
            admin_users = ['admin', 'administrator', 'root', 'boss', 'owner']
            return user['username'].lower() in admin_users
            
    except Exception as e:
        logger.error(f"Ошибка проверки прав администратора: {e}")
        return False
def get_facebook_account_limits(account_id, access_token):
    """Получает информацию о лимитах аккаунта из Facebook API"""
    try:
        clean_account_id = account_id.replace('act_', '')
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}"
        
        params = {
            'fields': 'id,name,account_status,amount_spent,balance,adtrust_dsl,spend_cap,daily_spend_limit',
            'access_token': access_token
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if 'error' in data:
            return None
        
        # Получаем информацию о лимитах запросов
        usage_url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}/adaccountusers"
        usage_params = {
            'fields': 'id',
            'access_token': access_token,
            'limit': 1
        }
        
        usage_response = requests.get(usage_url, params=usage_params, timeout=30)
        usage_headers = usage_response.headers
        
        # Извлекаем информацию о лимитах из заголовков
        calls_usage = int(usage_headers.get('x-business-use-case-usage', '{}').split('%')[0].split(':')[-1] or 0)
        calls_limit = 100  # Стандартный лимит Facebook
        
        return {
            'account_id': clean_account_id,
            'name': data.get('name'),
            'status': data.get('account_status'),
            'spend': float(data.get('amount_spent', 0)) / 100,
            'balance': float(data.get('balance', 0)) / 100,
            'limit': float(data.get('spend_cap', data.get('daily_spend_limit', 0))) / 100,
            'requests_today': calls_usage,
            'requests_limit': calls_limit
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения лимитов для аккаунта {account_id}: {e}")
        return None


@app.route('/api/admin/account_details/<account_id>')
@login_required
def get_account_details(account_id):
    """Возвращает детальную информацию об аккаунте"""
    if not is_admin_user(session['user_id']):
        return jsonify({'success': False, 'error': 'Доступ запрещен'})
    
    try:
        user_id = session['user_id']
        
        # Находим токен аккаунта
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT token FROM campaigns 
                WHERE user_id = ? AND account_id = ? 
                LIMIT 1
            """, (user_id, account_id))
            
            account = cursor.fetchone()
            if not account:
                return jsonify({'success': False, 'error': 'Аккаунт не найден'})
            
            # Получаем детальную информацию
            account_info = get_facebook_account_limits(account_id, account['token'])
            
            if account_info:
                return jsonify({
                    'success': True,
                    'account': account_info
                })
            else:
                return jsonify({'success': False, 'error': 'Не удалось получить данные'})
                
    except Exception as e:
        logger.error(f"Ошибка получения деталей аккаунта {account_id}: {e}")
        return jsonify({'success': False, 'error': str(e)})
def load_reserve_tokens(user_id):
    """Загружает резервные токены из отдельной таблицы базы данных"""
    reserve_tokens = {}
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Создаем таблицу для резервных токенов если ее нет
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS reserve_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                king TEXT NOT NULL,
                token TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, king, token)
            )
            """)
            
            # Получаем все резервные токены
            cursor.execute("SELECT king, token FROM reserve_tokens WHERE user_id = ?", (user_id,))
            
            for row in cursor.fetchall():
                king = row['king']
                token = row['token']
                
                if king not in reserve_tokens:
                    reserve_tokens[king] = []
                
                reserve_tokens[king].append(token)
                
    except Exception as e:
        logger.error(f"Ошибка загрузки резервных токенов: {e}")
    
    return reserve_tokens


def add_reserve_token(user_id, king, token):
    """Добавляет резервный токен в базу данных"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO reserve_tokens (user_id, king, token) VALUES (?, ?, ?)",
                (user_id, king, token)
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка добавления резервного токена: {e}")
        return False


def remove_reserve_token(user_id, king, token):
    """Удаляет резервный токен из базы данных"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM reserve_tokens WHERE user_id = ? AND king = ? AND token = ?",
                (user_id, king, token)
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка удаления резервного токена: {e}")
        return False


def get_keitaro_api_key(user_id: int) -> str:
    """Получает API ключ Keitaro из настроек пользователя"""
    try:
        settings = get_user_settings(user_id)
        return settings.get('keitaro_api_key', '')
    except Exception as e:
        logger.error(f"Ошибка получения Keitaro API key: {e}")
        return ""
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
def check_and_pause_campaigns(user_id):
    """Проверяет и отключает кампании, если все их адсеты отключены"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Находим кампании, где все адсеты отключены
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
                
                # Отключаем кампанию
                update_user_campaign_status(user_id, campaign_id, 'PAUSED')
                
                # Также отключаем через Facebook API
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
                    send_telegram_message(f"🔴 Кампания «{name}» отключена (все адсеты неактивны)")
                    
                except Exception as e:
                    logger.error(f"Ошибка отключения кампании {campaign_id}: {e}")
                    
    except Exception as e:
        logger.error(f"Ошибка проверки кампаний: {e}")
def extract_geo_from_name(name, known_geos=None):
    """Извлекает GEO код из названия с улучшенной логикой"""
    if not name:
        return 'N/A'
    
    # Нормализуем название
    clean_name = re.sub(r'[^A-Za-z\s]', ' ', name.upper())
    words = clean_name.split()
    
    # Если есть список известных GEO — ищем по нему
    if known_geos:
        # Сначала ищем точные совпадения
        for word in words:
            if word in known_geos:
                return word
        
        # Затем ищем частичные совпадения (для случаев типа "TH" в "THAI")
        for word in words:
            for known_geo in known_geos:
                if known_geo in word:
                    return known_geo
    
    # Ищем стандартные двухбуквенные коды стран
    country_codes = {
        'PH', 'TH', 'ID', 'MY', 'SG', 'VN', 'BR', 'US', 'UK', 'CA', 
        'AU', 'DE', 'FR', 'ES', 'IT', 'RU', 'JP', 'KR', 'CN', 'IN',
        'MX', 'AR', 'CO', 'PE', 'CL', 'ZA', 'NG', 'EG', 'SA', 'AE',
        'TR', 'PL', 'NL', 'SE', 'NO', 'DK', 'FI', 'BE', 'CH', 'AT'
    }
    
    for word in words:
        if len(word) == 2 and word.isalpha() and word in country_codes:
            return word
    
    # Дополнительные проверки для распространенных случаев
    geo_mappings = {
        'PHILIPPINES': 'PH', 'PHIL': 'PH', 'PHL': 'PH', 'PHILLIPINES': 'PH',
        'THAILAND': 'TH', 'THAI': 'TH', 'THA': 'TH',
        'INDONESIA': 'ID', 'INDO': 'ID', 'IDN': 'ID', 'INDON': 'ID',
        'MALAYSIA': 'MY', 'MALAY': 'MY', 'MYS': 'MY', 'MAL': 'MY',
        'SINGAPORE': 'SG', 'SGP': 'SG', 'SING': 'SG',
        'VIETNAM': 'VN', 'VIET': 'VN', 'VNM': 'VN', 'VIETNAMESE': 'VN',
        'BRAZIL': 'BR', 'BRA': 'BR', 'BRZ': 'BR', 'BRAZILIAN': 'BR',
        'USA': 'US', 'UNITED STATES': 'US', 'US': 'US', 'AMERICA': 'US',
        'UNITED KINGDOM': 'UK', 'UK': 'UK', 'GBR': 'UK', 'BRITAIN': 'UK',
        'CANADA': 'CA', 'CAN': 'CA', 'CAD': 'CA', 'CANADIAN': 'CA',
        'AUSTRALIA': 'AU', 'AUS': 'AU', 'AUST': 'AU', 'AUSTRALIAN': 'AU',
        'GERMANY': 'DE', 'DEU': 'DE', 'GER': 'DE', 'GERMAN': 'DE',
        'FRANCE': 'FR', 'FRA': 'FR', 'FRENCH': 'FR',
        'SPAIN': 'ES', 'ESP': 'ES', 'SPANISH': 'ES',
        'ITALY': 'IT', 'ITA': 'IT', 'ITALIAN': 'IT',
        'RUSSIA': 'RU', 'RUS': 'RU', 'RUSSIAN': 'RU',
        'JAPAN': 'JP', 'JPN': 'JP', 'JAPANESE': 'JP',
        'KOREA': 'KR', 'KOR': 'KR', 'KRN': 'KR', 'KOREAN': 'KR',
        'CHINA': 'CN', 'CHN': 'CN', 'CHINESE': 'CN',
        'INDIA': 'IN', 'IND': 'IN', 'INDIAN': 'IN',
        'MEXICO': 'MX', 'MEX': 'MX', 'MEXICAN': 'MX',
        'ARGENTINA': 'AR', 'ARG': 'AR', 'ARGENTINIAN': 'AR'
    }
    
    for word in words:
        if word in geo_mappings:
            return geo_mappings[word]
    
    # Ищем по первым буквам слов (например: "US Traffic" -> "US")
    for word in words:
        if len(word) > 2 and word[:2].isalpha() and word[:2] in country_codes:
            return word[:2]
    
    return 'N/A'
@app.route('/api/auto_control/logs', methods=['GET'])
@login_required
def get_auto_control_logs():
    """Возвращает логи автоконтроля"""
    try:
        user_id = session['user_id']
        
        # Читаем лог файл
        log_file = 'app.log'
        logs = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-100:]  # Последние 100 строк
                
                for line in lines:
                    # Парсим строку лога
                    if str(user_id) in line:
                        # Определяем уровень лога
                        level = 'info'
                        if 'ERROR' in line:
                            level = 'error'
                        elif 'WARNING' in line:
                            level = 'warning'
                        elif 'INFO' in line and ('✅' in line or '🟢' in line):
                            level = 'success'
                        
                        logs.append({
                            'message': line.strip(),
                            'level': level,
                            'timestamp': line.split(' - ')[0] if ' - ' in line else ''
                        })
        
        return jsonify({
            'success': True,
            'logs': logs[-50:]  # Возвращаем последние 50 записей
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения логов: {e}")
        return jsonify({'success': False, 'error': str(e)})

def run_auto_control_for_user(user_id):
    """Запускает автоконтроль для конкретного пользователя"""
    while True:
        # Проверяем, должен ли автоконтроль продолжать работать
        with auto_control_lock:
            if user_id not in auto_control_threads or not auto_control_threads[user_id].get('running', False):
                break
        
        try:
            auto_control(user_id)
        except Exception as e:
            logger.error(f"Ошибка автоконтроля для пользователя {user_id}: {e}")
        
        # Пауза между запусками (5 минут)
        threading.Event().wait(300)

@app.route('/api/manual_campaigns', methods=['POST'])
@login_required
def save_manual_campaigns():
    """Сохраняет кампании из ручного ввода"""
    try:
        user_id = session['user_id']
        data = request.json.get('campaigns', [])
        
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных для сохранения'})
        
        saved = 0
        for campaign in data:
            if campaign and len(campaign) >= 6:
                add_user_campaign(user_id, {
                    'king': campaign[0] or 'DEFAULT_KING',
                    'name': campaign[1] or f"Campaign {campaign[3]}",
                    'status': campaign[2] if campaign[2] in ['ACTIVE', 'PAUSED'] else 'PAUSED',
                    'campaign_id': campaign[3],
                    'account_id': campaign[4],
                    'token': campaign[5]
                })
                saved += 1
        
        return jsonify({
            'success': True,
            'message': f'Сохранено {saved} кампаний',
            'saved': saved
        })
        
    except Exception as e:
        logger.error(f"Error saving manual campaigns: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/check_access')
@login_required
def check_admin_access():
    """Проверяет права доступа к админ панели"""
    return jsonify({
        'success': True,
        'is_admin': is_admin_user(session['user_id'])
    })

@app.route('/api/admin/account_limits')
@login_required
def get_account_limits():
    """Возвращает информацию о лимитах всех аккаунтов"""
    if not is_admin_user(session['user_id']):
        return jsonify({'success': False, 'error': 'Доступ запрещен'})
    
    try:
        user_id = session['user_id']
        accounts = []
        total_spend = 0
        total_limit = 0
        
        # Получаем все аккаунты
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Получаем уникальные аккаунты
            cursor.execute("""
                SELECT DISTINCT account_id, token 
                FROM campaigns 
                WHERE user_id = ? AND account_id IS NOT NULL
            """, (user_id,))
            
            account_data = cursor.fetchall()
            
            for account in account_data:
                account_id = account['account_id']
                token = account['token']
                
                # Получаем информацию о лимитах из Facebook API
                account_info = get_facebook_account_limits(account_id, token)
                
                if account_info:
                    accounts.append(account_info)
                    total_spend += account_info.get('spend', 0)
                    total_limit += account_info.get('limit', 0)
        
        # Рассчитываем статистику
        limit_usage = (total_spend / total_limit * 100) if total_limit > 0 else 0
        
        return jsonify({
            'success': True,
            'stats': {
                'total_accounts': len(accounts),
                'active_accounts': len([acc for acc in accounts if acc.get('status') == 'ACTIVE']),
                'total_spend': total_spend,
                'total_limit': total_limit,
                'limit_usage': round(limit_usage, 1)
            },
            'accounts': accounts
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения лимитов: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/geo_rules', methods=['GET', 'POST'])
@login_required
def handle_geo_rules():
    """Управление GEO правилами автоконтроля"""
    user_id = session['user_id']
    
    if request.method == 'GET':
        try:
            # Сначала пробуем получить правила из новой таблицы
            with get_db_connection(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='geo_rules'
                """)
                geo_rules_table_exists = cursor.fetchone()
                
                if geo_rules_table_exists:
                    # Загрузка правил из новой таблицы
                    cursor.execute("""
                        SELECT geo_code, max_cpa, min_spend, max_leads_threshold, 
                               extended_spend_threshold, max_ucpc, max_ucpc_spend
                        FROM geo_rules 
                        WHERE user_id = ?
                        ORDER BY geo_code
                    """, (user_id,))
                    
                    rules = []
                    for row in cursor.fetchall():
                        rules.append({
                            'geo': row['geo_code'],
                            'max_cpa': row['max_cpa'],
                            'min_spend': row['min_spend'],
                            'max_leads_threshold': row['max_leads_threshold'],
                            'extended_spend_threshold': row['extended_spend_threshold'],
                            'max_ucpc': row['max_ucpc'],
                            'max_ucpc_spend': row['max_ucpc_spend']
                        })
                    
                    return jsonify({'success': True, 'rules': rules})
                else:
                    # Если новой таблицы нет, возвращаем пустой список
                    return jsonify({'success': True, 'rules': []})
                
        except Exception as e:
            logger.error(f"Ошибка загрузки GEO правил: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    elif request.method == 'POST':
        try:
            data = request.json
            rules = data.get('rules', [])
            
            with get_db_connection(user_id) as conn:
                cursor = conn.cursor()
                
                # Создаем таблицу если не существует
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS geo_rules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        geo_code TEXT NOT NULL,
                        max_cpa REAL DEFAULT 0,
                        min_spend REAL DEFAULT 0,
                        max_leads_threshold INTEGER DEFAULT 0,
                        extended_spend_threshold REAL DEFAULT 0,
                        max_ucpc REAL DEFAULT 0,
                        max_ucpc_spend REAL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id),
                        UNIQUE(user_id, geo_code)
                    )
                """)
                
                # Очищаем старые правила
                cursor.execute("DELETE FROM geo_rules WHERE user_id = ?", (user_id,))
                
                # Добавляем новые правила
                for rule in rules:
                    cursor.execute("""
                        INSERT INTO geo_rules (
                            user_id, geo_code, max_cpa, min_spend, max_leads_threshold,
                            extended_spend_threshold, max_ucpc, max_ucpc_spend
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        rule['geo'].upper(),
                        rule.get('max_cpa', 0),
                        rule.get('min_spend', 0),
                        rule.get('max_leads_threshold', 0),
                        rule.get('extended_spend_threshold', 0),
                        rule.get('max_ucpc', 0),
                        rule.get('max_ucpc_spend', 0)
                    ))
                
                conn.commit()
                return jsonify({'success': True, 'message': f'Сохранено {len(rules)} правил'})
                
        except Exception as e:
            logger.error(f"Ошибка сохранения GEO правил: {e}")
            return jsonify({'success': False, 'error': str(e)})
@app.route('/api/reserve_tokens', methods=['GET', 'POST', 'DELETE'])
@login_required
def handle_reserve_tokens():
    user_id = session['user_id']
    
    if request.method == 'GET':
        king = request.args.get('king')
        tokens = get_reserve_tokens(user_id, king)
        return jsonify({'success': True, 'tokens': tokens})
    
    elif request.method == 'POST':
        data = request.json
        king = data.get('king')
        token = data.get('token')
        
        if not king or not token:
            return jsonify({'success': False, 'error': 'Не указан KING или токен'})
        
        if add_reserve_token(user_id, king, token):
            return jsonify({'success': True, 'message': 'Токен добавлен'})
        else:
            return jsonify({'success': False, 'error': 'Ошибка добавления токена'})
    
    elif request.method == 'DELETE':
        data = request.json
        king = data.get('king')
        token = data.get('token')
        
        if not king or not token:
            return jsonify({'success': False, 'error': 'Не указан KING или токен'})
        
        if remove_reserve_token(user_id, king, token):
            return jsonify({'success': True, 'message': 'Токен удален'})
        else:
            return jsonify({'success': False, 'error': 'Ошибка удаления токена'})
@app.route('/auto_control')
@login_required
def auto_control_page():
    """Страница управления автоконтролем"""
    return render_template('auto_control.html')

@app.route('/reserve_tokens')
@login_required
def reserve_tokens():
    """Страница управления резервными токенами"""
    return render_template('reserve_tokens.html')

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

@app.route('/api/manual_import_bulk', methods=['POST'])
@login_required
def manual_import_bulk():
    try:
        user_id = session['user_id']
        accounts_data = request.json.get('accounts', [])
        
        if not accounts_data:
            return jsonify({'success': False, 'error': 'Нет аккаунтов для импорта'})

        # Получаем известные GEO коды
        geo_rules = get_user_geo_rules(user_id)
        known_geos = list(geo_rules.keys()) if geo_rules else []
        
        total_campaigns = 0
        total_adsets = 0

        for account_data in accounts_data:
            account_id = account_data.get('account_id', '').strip()
            token = account_data.get('token', '').strip()
            
            if not account_id or not token:
                continue

            # Очищаем account_id от префикса act_
            clean_account_id = account_id.replace('act_', '')
            
            # 🔹 Получаем кампании
            campaigns = fetch_facebook_campaigns(clean_account_id, token)
            for campaign in campaigns:
                try:
                    add_user_campaign(user_id, {
                        'king': 'Facebook',
                        'name': campaign.get('name', f"Campaign {campaign.get('id')}"),
                        'status': campaign.get('status', 'PAUSED'),
                        'campaign_id': campaign.get('id', ''),
                        'account_id': clean_account_id,
                        'token': token
                    })
                    total_campaigns += 1
                except Exception as e:
                    logger.error(f"Ошибка сохранения кампании {campaign.get('id')}: {e}")

            # 🔹 Получаем адсеты
            adsets = fetch_facebook_adsets(clean_account_id, token)
            for adset in adsets:
                try:
                    daily_budget = adset.get('daily_budget')
                    budget = float(daily_budget) / 100 if daily_budget else 0
                    
                    # Определяем GEO из названия адсета
                    adset_name = adset.get('name', '')
                    geo = extract_geo_from_name(adset_name, known_geos)
                    
                    add_user_adset(user_id, {
                        'name': adset_name,
                        'adset_id': adset.get('id', ''),
                        'campaign_id': adset.get('campaign_id', ''),
                        'status': adset.get('status', 'PAUSED'),
                        'account_id': clean_account_id,
                        'token': token,
                        'budget': budget,
                        'geo': geo,  # Сохраняем определенный GEO
                        'ucpc': 0,
                        'spend': 0,
                        'cpa': 0,
                        'leads': 0,
                        'king': 'Facebook',
                        'effective_status': adset.get('effective_status', ''),
                        'ad_name': adset.get('name', ''),
                        'manual_pause': 0
                    })
                    total_adsets += 1
                except Exception as e:
                    logger.error(f"Ошибка сохранения адсета {adset.get('id')}: {e}")

        return jsonify({
            'success': True,
            'message': f'Импортировано {total_campaigns} кампаний и {total_adsets} адсетов',
            'total_campaigns': total_campaigns,
            'total_adsets': total_adsets
        })

    except Exception as e:
        logger.error(f"Ошибка bulk-импорта: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/manual_adsets', methods=['POST'])
@login_required
def save_manual_adsets():
    """Сохраняет адсеты из ручного ввода"""
    try:
        user_id = session['user_id']
        data = request.json.get('adsets', [])
        
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных для сохранения'})
        
        saved = 0
        for adset in data:
            if adset and len(adset) >= 14:
                add_user_adset(user_id, {
                    'name': adset[0] or f"AdSet {adset[1]}",
                    'adset_id': adset[1],
                    'ucpc': float(adset[2] or 0),
                    'spend': float(adset[3] or 0),
                    'cpa': float(adset[4] or 0),
                    'status': adset[5] if adset[5] in ['ACTIVE', 'PAUSED'] else 'PAUSED',
                    'geo': adset[6] or 'N/A',
                    'token': adset[7] or '',
                    'leads': int(adset[8] or 0),
                    'manual_pause': 1 if adset[9] else 0,
                    'king': adset[10] or 'DEFAULT_KING',
                    'effective_status': adset[11] or 'PAUSED',
                    'ad_name': adset[12] or '',
                    'budget': float(adset[13] or 0)
                })
                saved += 1
        
        return jsonify({
            'success': True,
            'message': f'Сохранено {saved} адсетов',
            'saved': saved
        })
        
    except Exception as e:
        logger.error(f"Error saving manual adsets: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/refresh_campaigns', methods=['POST'])
@login_required
def refresh_campaigns():
    """Обновляет данные кампаний из Facebook API"""
    try:
        user_id = session['user_id']
        campaigns = get_user_campaigns(user_id)
        
        accounts = {}
        for campaign in campaigns:
            if campaign['account_id'] and campaign['token']:
                accounts[campaign['account_id']] = campaign['token']
        
        updated = 0
        for account_id, token in accounts.items():
            try:
                # Получаем кампании из Facebook
                fb_campaigns = fetch_facebook_campaigns(account_id, token)
                
                for fb_campaign in fb_campaigns:
                    # Обновляем или добавляем кампанию
                    add_user_campaign(user_id, {
                        'king': 'Facebook',
                        'name': fb_campaign.get('name', ''),
                        'status': fb_campaign.get('status', 'PAUSED'),
                        'campaign_id': fb_campaign.get('id', ''),
                        'account_id': account_id,
                        'token': token
                    })
                    updated += 1
                    
            except Exception as e:
                logger.error(f"Error updating campaigns for account {account_id}: {e}")
        
        return jsonify({
            'success': True,
            'message': f'Обновлено {updated} кампаний',
            'updated': updated
        })
        
    except Exception as e:
        logger.error(f"Error refreshing campaigns: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/refresh_adsets', methods=['POST'])
@login_required
def refresh_adsets():
    """Обновляет данные адсетов из Facebook API"""
    try:
        user_id = session['user_id']
        campaigns = get_user_campaigns(user_id)
        
        accounts = {}
        for campaign in campaigns:
            if campaign['account_id'] and campaign['token']:
                accounts[campaign['account_id']] = campaign['token']
        
        updated = 0
        for account_id, token in accounts.items():
            try:
                # Получаем адсеты из Facebook
                fb_adsets = fetch_facebook_adsets(account_id, token)
                
                for fb_adset in fb_adsets:
                    daily_budget = fb_adset.get('daily_budget')
                    budget = float(daily_budget) / 100 if daily_budget else 0
                    
                    # Обновляем или добавляем адсет
                    add_user_adset(user_id, {
                        'name': fb_adset.get('name', ''),
                        'adset_id': fb_adset.get('id', ''),
                        'campaign_id': fb_adset.get('campaign_id', ''),
                        'status': fb_adset.get('status', 'PAUSED'),
                        'account_id': account_id,
                        'token': token,
                        'budget': budget,
                        'geo': 'N/A',
                        'ucpc': 0,
                        'spend': 0,
                        'cpa': 0,
                        'leads': 0,
                        'king': 'Facebook',
                        'effective_status': fb_adset.get('effective_status', ''),
                        'ad_name': fb_adset.get('name', ''),
                        'manual_pause': 0
                    })
                    updated += 1
                    
            except Exception as e:
                logger.error(f"Error updating adsets for account {account_id}: {e}")
        
        return jsonify({
            'success': True,
            'message': f'Обновлено {updated} адсетов',
            'updated': updated
        })
        
    except Exception as e:
        logger.error(f"Error refreshing adsets: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/fetch_facebook_data', methods=['POST'])
@login_required
def fetch_facebook_data():
    """Получает данные из Facebook API по токену и account_id"""
    try:
        user_id = session['user_id']
        data = request.json
        
        account_id = data.get('account_id')
        access_token = data.get('access_token')
        
        if not account_id or not access_token:
            return jsonify({
                'success': False, 
                'error': 'Необходимо указать account_id и access_token'
            })
        
        # Сначала проверяем валидность токена
        test_url = f"https://graph.facebook.com/v18.0/act_{account_id}"
        test_params = {'access_token': access_token, 'fields': 'id'}
        
        test_response = requests.get(test_url, params=test_params, timeout=30)
        test_data = test_response.json()
        
        if 'error' in test_data:
            return jsonify({
                'success': False, 
                'error': f"Неверный токен или account_id: {test_data['error']['message']}"
            })
        
        # Получаем известные GEO коды
        geo_rules = get_user_geo_rules(user_id)
        known_geos = list(geo_rules.keys()) if geo_rules else []
        
        # Получаем кампании
        campaigns = fetch_facebook_campaigns(account_id, access_token)
        
        # Получаем адсеты
        adsets = fetch_facebook_adsets(account_id, access_token)
        
        # Сохраняем в базу данных
        saved_campaigns = 0
        for campaign in campaigns:
            try:
                add_user_campaign(user_id, {
                    'king': 'Facebook',
                    'name': campaign.get('name', f"Campaign {campaign.get('id')}"),
                    'status': campaign.get('status', 'PAUSED'),
                    'campaign_id': campaign.get('id', ''),
                    'account_id': account_id,
                    'token': access_token
                })
                saved_campaigns += 1
            except Exception as e:
                logger.error(f"Ошибка сохранения кампании {campaign.get('id')}: {e}")
        
        saved_adsets = 0
        for adset in adsets:
            try:
                daily_budget = adset.get('daily_budget')
                budget = float(daily_budget) / 100 if daily_budget else 0
                
                # Определяем GEO из названия адсета
                adset_name = adset.get('name', '')
                geo = extract_geo_from_name(adset_name, known_geos)
                
                add_user_adset(user_id, {
                    'name': adset_name,
                    'adset_id': adset.get('id', ''),
                    'campaign_id': adset.get('campaign_id', ''),
                    'status': adset.get('status', 'PAUSED'),
                    'account_id': account_id,
                    'token': access_token,
                    'budget': budget,
                    'geo': geo,  # Сохраняем определенный GEO
                    'ucpc': 0,
                    'spend': 0,
                    'cpa': 0,
                    'leads': 0,
                    'king': 'Facebook',
                    'effective_status': adset.get('effective_status', ''),
                    'ad_name': adset.get('name', ''),
                    'manual_pause': 0
                })
                saved_adsets += 1
            except Exception as e:
                logger.error(f"Ошибка сохранения адсета {adset.get('id')}: {e}")
        
        return jsonify({
            'success': True,
            'message': f'Сохранено {saved_campaigns} кампаний и {saved_adsets} адсетов',
            'campaigns_count': len(campaigns),
            'adsets_count': len(adsets),
            'saved_campaigns': saved_campaigns,
            'saved_adsets': saved_adsets
        })
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка сети при получении данных из Facebook: {e}")
        return jsonify({'success': False, 'error': f'Ошибка сети: {e}'})
    except Exception as e:
        logger.error(f"Ошибка получения данных из Facebook: {e}")
        return jsonify({'success': False, 'error': str(e)})

def reset_old_ucpc(user_id, days=7):
    """Сбрасывает uCPC у адсетов, которые не обновлялись более N дней"""
    try:
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE adsets
                SET ucpc = 0
                WHERE user_id = ?
                  AND (updated_at IS NULL OR updated_at < ?)
            """, (user_id, cutoff_date))
            conn.commit()
        logger.info(f"uCPC сброшен у адсетов старше {days} дней")
    except Exception as e:
        logger.error(f"Ошибка сброса старых uCPC: {e}")

@app.route('/api/test_facebook_connection', methods=['POST'])
@login_required
def test_facebook_connection():
    """Тестирует соединение с Facebook API"""
    try:
        data = request.json
        account_id = data.get('account_id')
        access_token = data.get('access_token')
        
        if not account_id or not access_token:
            return jsonify({
                'success': False, 
                'error': 'Необходимо указать account_id и access_token'
            })
        
        # Простой запрос для проверки токена - используем правильный формат версии
        url = f"https://graph.facebook.com/v18.0/act_{account_id}"
        params = {
            'access_token': access_token,
            'fields': 'id,name,account_status'
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        # Проверяем наличие ошибок в ответе
        if 'error' in result:
            return jsonify({
                'success': False, 
                'error': f"Facebook API error: {result['error']['message']}"
            })
        
        return jsonify({
            'success': True,
            'message': 'Соединение с Facebook API успешно установлено',
            'account_name': result.get('name', 'N/A'),
            'account_status': result.get('account_status', 'N/A')
        })
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка сети: {e}")
        return jsonify({'success': False, 'error': f'Ошибка сети: {e}'})
    except Exception as e:
        logger.error(f"Ошибка соединения: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/save_campaigns', methods=['POST'])
@login_required
def save_campaigns():
    try:
        user_id = session['user_id']
        data = request.json.get('campaigns', [])
        
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных для сохранения'})
        
        # Сохраняем кампании
        saved = 0
        for row in data:
            if len(row) >= 6 and row[3] and row[4] and row[5]:  # Проверяем обязательные поля
                add_user_campaign(user_id, {
                    'king': row[0] or 'DEFAULT_KING',
                    'name': row[1] or f"Campaign {row[3]}",
                    'status': row[2] if row[2] in ['ACTIVE', 'PAUSED'] else 'PAUSED',
                    'campaign_id': row[3],
                    'account_id': row[4],
                    'token': row[5]
                })
                saved += 1
        
        return jsonify({
            'success': True,
            'message': f'Сохранено {saved} кампаний',
            'saved': saved
        })
        
    except Exception as e:
        logger.error(f"Error saving campaigns: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/campaigns', methods=['GET', 'POST'])
@login_required
def api_campaigns():  # Изменили имя функции
    user_id = session['user_id']
    
    if request.method == 'GET':
        try:
            # Получаем данные из базы
            db_campaigns = get_user_campaigns(user_id)
            return jsonify({
                'success': True,
                'data': db_campaigns,
                'columns': [
                    {'name': 'KING', 'editable': True},
                    {'name': 'Название', 'editable': True},
                    {'name': 'Статус', 'editable': True, 'type': 'select', 'options': ['ACTIVE', 'PAUSED']},
                    {'name': 'ID кампании', 'editable': True},
                    {'name': 'ID аккаунта', 'editable': True},
                    {'name': 'Токен', 'editable': True}
                ]
            })
        except Exception as e:
            logger.error(f"Error getting campaigns: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            logger.debug(f"Received data: {data}")
            
            if isinstance(data, list):
                for row in data:
                    if row and row[0]:  # Проверяем, что строка не пустая
                        campaign_data = {
                            'king': row[0],
                            'name': row[1],
                            'status': row[2],
                            'campaign_id': row[3],
                            'account_id': row[4],
                            'token': row[5],
                            'user_id': user_id
                        }
                        add_user_campaign(user_id, campaign_data)
                return jsonify({'success': True, 'message': f'Добавлено {len(data)} кампаний'})
            return jsonify({'success': False, 'error': 'Invalid data format'})
        except Exception as e:
            logger.error(f"Error saving campaigns: {e}")
            return jsonify({'success': False, 'error': str(e)})

@app.route('/api/campaigns', methods=['GET'])
@login_required
def get_campaigns():
    try:
        campaigns = get_user_campaigns(session['user_id'])
        print(f"DEBUG: Found {len(campaigns)} campaigns")
        return jsonify({
            'success': True,
            'data': campaigns
        })
    except Exception as e:
        logger.error(f"Error getting campaigns: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/session', methods=['GET'])
@login_required
def get_session_info():
    """Возвращает информацию о текущей сессии"""
    return jsonify({
        'success': True,
        'user_id': session.get('user_id'),
        'username': session.get('username')
    })
# В app.py обновим функцию process_keitaro_data
def process_keitaro_data(report):
    """Обрабатывает данные из Keitaro без расчета CPC"""
    processed_data = []
    
    for row in report.get('rows', []):
        cost = float(row.get('cost', 0) or 0)
        cpa = float(row.get('cpa', 0) or 0)
        
        # Рассчитываем лиды по формуле Spend / CPA
        leads = 0
        if cpa > 0 and cost > 0:
            leads = round(cost / cpa)
        
        # CPC теперь будет получаться из Facebook, поэтому не используем из Keitaro
        processed_data.append({
            'campaign_id': row.get('sub_id_9', ''),
            'campaign_name': row.get('campaign', ''),
            'spend': cost,
            'cpa': cpa,
            'leads': leads,
            'ucpc': float(row.get('ucpc', 0) or 0),
            'conversions': int(row.get('conversions', 0) or 0)
        })
    
    return processed_data

@app.route('/api/sync/keitaro_only', methods=['POST'])
@login_required
def sync_keitaro_only():
    """Синхронизация только данных из Keitaro (без CPC)"""
    try:
        user_id = session['user_id']
        settings = get_user_settings(user_id)
        
        keitaro_api_key = settings.get('keitaro_api_key')
        keitaro_domain = settings.get('keitaro_domain', 'uniaffnu.com')
        keitaro_range_days = settings.get('keitaro_range_days', 1)
        
        logger.info(f"Синхронизация Keitaro: API_KEY={keitaro_api_key[:10] if keitaro_api_key else 'None'}..., domain={keitaro_domain}, days={keitaro_range_days}")
        
        if not keitaro_api_key:
            return jsonify({'success': False, 'error': 'Keitaro API key not configured'})
        
        # Получаем данные из Keitaro
        report = fetch_keitaro_report(keitaro_api_key, keitaro_domain)
        
        if not report:
            return jsonify({'success': False, 'error': 'Failed to fetch data from Keitaro'})
        
        # Обрабатываем данные (без CPC)
        processed_data = process_keitaro_data(report)
        
        if not processed_data:
            return jsonify({'success': False, 'error': 'No processable data from Keitaro'})
        
        # Обновляем статистику кампаний без CPC
        updated_count = 0
        for item in processed_data:
            try:
                campaign_id = item['campaign_id']
                
                # Проверяем, существует ли кампания
                with get_db_connection(user_id) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM campaigns WHERE user_id = ? AND campaign_id = ?", 
                                 (user_id, campaign_id))
                    campaign_exists = cursor.fetchone()
                
                if campaign_exists:
                    update_campaign_stats(
                        user_id,
                        campaign_id,
                        spend=item.get('spend'),
                        leads=item.get('leads'),
                        cpa=item.get('cpa'),
                        ucpc=item.get('ucpc')
                    )
                    updated_count += 1
                    logger.info(f"Обновлена кампания {campaign_id} из Keitaro")
                else:
                    logger.warning(f"Кампания {campaign_id} не найдена в базе для обновления из Keitaro")
                    
            except Exception as e:
                logger.error(f"Ошибка обновления кампании {item.get('campaign_id')}: {e}")
                continue
        
        return jsonify({
            'success': True, 
            'message': f'Обновлено {updated_count} кампаний из Keitaro',
            'updated_count': updated_count,
            'total_records': len(processed_data)
        })
        
    except Exception as e:
        logger.error(f"Ошибка синхронизации Keitaro: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/campaign/status', methods=['POST'])
@login_required
def update_campaign_status():
    """Обновляет статус кампании"""
    try:
        data = request.json
        campaign_id = data.get('campaign_id')
        name = data.get('name')
        token = data.get('token')
        new_status = data.get('status')  # 'ACTIVE' или 'PAUSED'
        
        if not all([campaign_id, name, token, new_status]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        if new_status not in ['ACTIVE', 'PAUSED']:
            return jsonify({'success': False, 'error': 'Invalid status'})
        
        # Обновляем через Facebook API
        url = f"https://graph.facebook.com/v18.0/{campaign_id}"
        response = requests.post(
            url,
            params={"access_token": token},
            data={"status": new_status},
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        
        if result.get('success') or result.get('id') == campaign_id:
            # Обновляем статус в базе данных
            update_user_campaign_status(session['user_id'], campaign_id, new_status)
            
            status_emoji = "🟢" if new_status == 'ACTIVE' else "🔴"
            logger.info(f"{status_emoji} Кампания «{name}» статус изменен на {new_status}")
            send_telegram_message(f"{status_emoji} Кампания «{name}» статус изменен на {new_status}")
            
            return jsonify({'success': True, 'new_status': new_status})
        else:
            error_msg = result.get('error', {}).get('message', 'Unknown error')
            raise Exception(f"Facebook API error: {error_msg}")
            
    except Exception as e:
        logger.error(f"Ошибка изменения статуса кампании «{data.get('name', 'unknown')}»: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/adset/status', methods=['POST'])
@login_required
def update_adset_status():
    """Обновляет статус адсета"""
    try:
        data = request.json
        adset_id = data.get('adset_id')
        name = data.get('name')
        token = data.get('token')
        new_status = data.get('status')  # 'ACTIVE' или 'PAUSED'
        
        if not all([adset_id, name, token, new_status]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        if new_status not in ['ACTIVE', 'PAUSED']:
            return jsonify({'success': False, 'error': 'Invalid status'})
        
        # Обновляем через Facebook API
        url = f"https://graph.facebook.com/v18.0/{adset_id}"
        response = requests.post(
            url,
            params={"access_token": token},
            data={"status": new_status},
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        
        if result.get('success') or result.get('id') == adset_id:
            # Обновляем статус в базе данных
            update_user_adset_status(session['user_id'], adset_id, new_status)
            
            status_emoji = "🟢" if new_status == 'ACTIVE' else "🔴"
            logger.info(f"{status_emoji} AdSet «{name}» статус изменен на {new_status}")
            send_telegram_message(f"{status_emoji} AdSet «{name}» статус изменен на {new_status}")
            
            return jsonify({'success': True, 'new_status': new_status})
        else:
            error_msg = result.get('error', {}).get('message', 'Unknown error')
            raise Exception(f"Facebook API error: {error_msg}")
            
    except Exception as e:
        logger.error(f"Ошибка изменения статуса AdSet «{data.get('name', 'unknown')}»: {e}")
        return jsonify({'success': False, 'error': str(e)})
def get_budget_rules(user_id):
    """Получает правила бюджета для пользователя"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT geo_code, increase_budget, decrease_budget, max_budget_multiplier,
                       min_budget, increase_threshold_cpa, decrease_threshold_cpa,
                       min_leads_for_increase, budget_increase_step, budget_decrease_step
                FROM budget_rules 
                WHERE user_id = ?
            """, (user_id,))
            
            rules = {}
            for row in cursor.fetchall():
                rules[row['geo_code']] = {
                    'increase_budget': bool(row['increase_budget']),
                    'decrease_budget': bool(row['decrease_budget']),
                    'max_budget_multiplier': row['max_budget_multiplier'],
                    'min_budget': row['min_budget'],
                    'increase_threshold_cpa': row['increase_threshold_cpa'],
                    'decrease_threshold_cpa': row['decrease_threshold_cpa'],
                    'min_leads_for_increase': row['min_leads_for_increase'],
                    'budget_increase_step': row['budget_increase_step'],
                    'budget_decrease_step': row['budget_decrease_step']
                }
            return rules
    except Exception as e:
        logger.error(f"Ошибка получения правил бюджета: {e}")
        return {}

def update_budget_rules(user_id, rules):
    """Обновляет правила бюджета"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Очищаем старые правила
            cursor.execute("DELETE FROM budget_rules WHERE user_id = ?", (user_id,))
            
            # Добавляем новые правила
            for geo_code, rule in rules.items():
                cursor.execute("""
                    INSERT INTO budget_rules (
                        user_id, geo_code, increase_budget, decrease_budget,
                        max_budget_multiplier, min_budget, increase_threshold_cpa,
                        decrease_threshold_cpa, min_leads_for_increase,
                        budget_increase_step, budget_decrease_step
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, geo_code.upper(),
                    int(rule.get('increase_budget', False)),
                    int(rule.get('decrease_budget', False)),
                    rule.get('max_budget_multiplier', 2.0),
                    rule.get('min_budget', 5.0),
                    rule.get('increase_threshold_cpa', 0.7),
                    rule.get('decrease_threshold_cpa', 1.3),
                    rule.get('min_leads_for_increase', 3),
                    rule.get('budget_increase_step', 1.2),
                    rule.get('budget_decrease_step', 0.8)
                ))
            
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления правил бюджета: {e}")
        return False

def update_adset_budget_facebook(adset_id, new_budget, access_token):
    """Обновляет бюджет адсета через Facebook API"""
    try:
        url = f"https://graph.facebook.com/v18.0/{adset_id}"
        
        # Конвертируем доллары в центы (Facebook API использует центы)
        budget_in_cents = int(new_budget * 100)
        
        params = {
            "access_token": access_token,
            "daily_budget": budget_in_cents
        }
        
        response = requests.post(url, params=params, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        logger.info(f"Facebook API response for budget update: {result}")
        
        if result.get('success') or result.get('id') == adset_id:
            return True
        else:
            error_msg = result.get('error', {}).get('message', 'Unknown error')
            logger.error(f"Facebook API error: {error_msg}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка обновления бюджета через Facebook API: {e}")
        return False
def update_user_adset_budget(user_id, adset_id, new_budget):
    """Обновляет бюджет адсета в базе данных"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE adsets 
                SET budget = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE user_id = ? AND adset_id = ?
            """, (new_budget, user_id, adset_id))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления бюджета в БД: {e}")
        return False
@app.route('/api/budget_rules', methods=['GET', 'POST'])
@login_required
def handle_budget_rules():
    """Управление правилами бюджета"""
    user_id = session['user_id']
    
    if request.method == 'GET':
        try:
            rules = get_budget_rules(user_id)
            return jsonify({'success': True, 'rules': rules})
        except Exception as e:
            logger.error(f"Ошибка загрузки правил бюджета: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    elif request.method == 'POST':
        try:
            data = request.json
            rules = data.get('rules', {})
            
            if update_budget_rules(user_id, rules):
                return jsonify({'success': True, 'message': 'Правила бюджета сохранены'})
            else:
                return jsonify({'success': False, 'error': 'Ошибка сохранения правил'})
                
        except Exception as e:
            logger.error(f"Ошибка сохранения правил бюджета: {e}")
            return jsonify({'success': False, 'error': str(e)})

@app.route('/api/adset/budget_settings', methods=['POST'])
@login_required
def update_adset_budget_settings():
    """Обновление настроек авто-бюджета для адсета"""
    try:
        user_id = session['user_id']
        data = request.json
        
        adset_id = data.get('adset_id')
        auto_increase = data.get('auto_budget_increase', False)
        auto_decrease = data.get('auto_budget_decrease', False)
        max_budget = data.get('max_budget', 0)
        min_budget = data.get('min_budget', 0)
        
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE adsets 
                SET auto_budget_increase = ?, auto_budget_decrease = ?,
                    max_budget = ?, min_budget = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND adset_id = ?
            """, (int(auto_increase), int(auto_decrease), max_budget, min_budget, user_id, adset_id))
            conn.commit()
        
        return jsonify({'success': True, 'message': 'Настройки бюджета обновлены'})
        
    except Exception as e:
        logger.error(f"Ошибка обновления настроек бюджета: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/adset/budget', methods=['POST'])
@login_required
def set_adset_budget_api():
    try:
        user_id = session['user_id']
        data = request.json
        
        adset_id = data.get('adset_id')
        name = data.get('name')
        token = data.get('token')
        new_budget = float(data.get('budget', 0))
        
        if not all([adset_id, name, token]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        # Обновляем через Facebook API
        success = update_adset_budget_facebook(adset_id, new_budget, token)
        
        if success:
            # Обновляем в базе данных
            update_user_adset_budget(user_id, adset_id, new_budget)
            
            msg = f"💰 Бюджет установлен: {name} (${new_budget:.2f})"
            logger.info(msg)
            send_telegram_message(msg, user_id=user_id)
            
            return jsonify({
                'success': True, 
                'message': msg,
                'new_budget': new_budget
            })
        else:
            return jsonify({'success': False, 'error': 'Ошибка установки бюджета через Facebook API'})
            
    except Exception as e:
        logger.error(f"Ошибка установки бюджета: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/')
def index():
    """Перенаправляет на страницу входа"""
    return redirect(url_for('login'))
@app.route('/api/campaign/<campaign_id>', methods=['DELETE'])
@login_required
def delete_campaign(campaign_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM campaigns WHERE user_id = ? AND campaign_id = ?",
            (session['user_id'], campaign_id)
        )
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = authenticate_user(username, password)
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Вы успешно вошли в систему', 'success')
            
            # Запускаем автоконтроль и автообновление вместе
            settings = get_user_settings(user['id'])
            if settings.get('auto_refresh_interval', 5) > 0:
                start_auto_control_and_refresh(user['id'])
            
            return redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user_id = create_user(username, password)
        if user_id:
            flash('Регистрация прошла успешно. Теперь вы можете войти.', 'success')
            
            # УБРАНО: генерация тестовых данных для нового пользователя
            # generate_test_data_for_user(user_id)
            
            return redirect(url_for('login'))
        else:
            flash('Это имя пользователя уже занято', 'danger')
    
    return render_template('register.html')

def get_campaign_name(api_key, domain, campaign_id):
    """Получает название кампании по ID"""
    try:
        url = f"https://{domain}/admin_api/v1/campaigns/{campaign_id}"
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                return data.get('name', 'Unknown')
    except Exception as e:
        logger.warning(f"Не удалось получить название кампании {campaign_id}: {e}")
    
    return 'Unknown'
import requests


def get_keitaro_streams(base_url, api_key, campaign_id):
    """
    Получение потоков Keitaro с автоподстановкой схемы и пути API.
    
    base_url: домен трекера (с https:// или без), например:
              "tracker.mydomain.com" или "https://tracker.mydomain.com/admin_api/v1"
    api_key: API key
    campaign_id: ID кампании или "all"
    """
    # Убираем пробелы и лишние слэши
    base_url = base_url.strip().rstrip("/")

    # Если нет схемы — добавляем https://
    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url

    # Если нет пути /admin_api/v1 — добавляем
    if "/admin_api/v1" not in base_url:
        base_url = base_url.rstrip("/") + "/admin_api/v1"

    headers = {
        "Api-Key": api_key,
        "Content-Type": "application/json"
    }

    try:
        if campaign_id == "all":
            # Получаем все кампании
            campaigns_url = f"{base_url}/campaigns"
            campaigns_resp = requests.get(campaigns_url, headers=headers)
            campaigns_resp.raise_for_status()
            campaigns = campaigns_resp.json()

            all_streams = {}
            return all_streams
        else:
            # Потоки по одной кампании
            streams_url = f"{base_url}/campaigns/{campaign_id}/streams"
            resp = requests.get(streams_url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except requests.HTTPError as e:
        if e.response.status_code == 404:
            print(f"Ошибка 404: Не найдено. Проверь, что ID кампании {campaign_id} существует и API-ключ имеет доступ.")
        else:
            print(f"HTTP ошибка: {e}")
        return None
    except requests.RequestException as e:
        print(f"Ошибка при запросе потоков Keitaro: {e}")
        return None

def update_keitaro_stream_weight(api_key, domain, stream_id, new_weight):
    """Обновляет вес потока в Keitaro - исправленная версия"""
    try:
        url = f"https://{domain}/admin_api/v1/streams/{stream_id}"
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        
        payload = {"weight": int(new_weight)}
        
        response = requests.put(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        return result
        
    except Exception as e:
        logger.error(f"Ошибка обновления веса потока {stream_id}: {e}")
        return None
def analyze_stream_performance(api_key, domain, campaign_id=None, interval="today"):
    """Анализирует производительность потоков кампании - исправленная версия"""
    try:
        url = f"https://{domain}/admin_api/v1/report/build"
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        
        # Базовый payload для анализа потоков
        payload = {
            "range": {"interval": interval, "timezone": "Europe/Moscow"},
            "metrics": ["conversions", "revenue", "cost", "roi", "epc", "clicks"],
            "grouping": ["stream_id", "campaign_id"],
            "limit": 1000
        }
        
        # Добавляем фильтр по кампании если указана
        if campaign_id and campaign_id != 'all':
            try:
                campaign_id_int = int(campaign_id)
                payload["filters"] = [{
                    "name": "campaign_id", 
                    "operator": "EQUALS", 
                    "expression": str(campaign_id_int)
                }]
            except ValueError:
                logger.error(f"Неверный ID кампании для фильтра: {campaign_id}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        report = response.json()
        return report.get('rows', [])
        
    except Exception as e:
        logger.error(f"Ошибка анализа производительности потоков: {e}")
        return []

def optimize_headlines_automation(user_id):
    """Автоматическая оптимизация заголовков на основе производительности - исправленная версия"""
    try:
        settings = get_user_settings(user_id)
        api_key = settings.get('keitaro_api_key')
        domain = settings.get('keitaro_domain')
        
        if not api_key:
            return
        
        # Получаем все кампании из Keitaro
        streams = get_keitaro_streams(domain, api_key)
        
        if not streams:
            logger.info("Не найдено потоков для оптимизации")
            return
        
        # Группируем потоки по кампаниям
        campaigns = {}
        for stream in streams:
            campaign_id = stream.get('campaign_id')
            if campaign_id not in campaigns:
                campaigns[campaign_id] = {
                    'name': stream.get('campaign_name', 'Unknown'),
                    'streams': []
                }
            campaigns[campaign_id]['streams'].append(stream)
        
        # Анализируем и оптимизируем каждую кампанию
        for campaign_id, campaign_data in campaigns.items():
            try:
                # Получаем статистику для этой кампании
                stream_stats = analyze_stream_performance(api_key, domain, campaign_id, "today")
                
                if not stream_stats:
                    continue
                
                # Создаем словарь для статистики
                stats_by_stream = {}
                for stat in stream_stats:
                    stream_id = stat.get('landing_id')
                    if stream_id:
                        cost = float(stat.get('cost', 0))
                        conversions = int(stat.get('conversions', 0))
                        revenue = float(stat.get('revenue', 0))
                        
                        cpa = cost / conversions if conversions > 0 else 0
                        roi = ((revenue - cost) / cost * 100) if cost > 0 else 0
                        
                        stats_by_stream[stream_id] = {
                            'conversions': conversions,
                            'cost': cost,
                            'revenue': revenue,
                            'cpa': cpa,
                            'roi': roi
                        }
                
                # Применяем оптимизацию
                optimize_campaign_streams(api_key, domain, campaign_data['streams'], stats_by_stream, user_id)
                
            except Exception as e:
                logger.error(f"Ошибка оптимизации кампании {campaign_id}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Ошибка оптимизации заголовков: {e}")

def optimize_campaign_streams(api_key, domain, streams, stats, user_id):
    """Оптимизирует потоки конкретной кампании"""
    performance_data = []
    
    for stream in streams:
        stream_id = stream.get('id')
        stat = stats.get(stream_id, {})
        
        conversions = stat.get('conversions', 0)
        cost = stat.get('cost', 0)
        revenue = stat.get('revenue', 0)
        cpa = stat.get('cpa', 0)
        roi = stat.get('roi', 0)
        
        # Минимальный порог для участия в оптимизации
        if cost < 5:  # Минимум $5 трат
            continue
            
        performance_data.append({
            'stream_id': stream_id,
            'stream_name': stream.get('name', 'Unknown'),
            'current_weight': stream.get('weight', 0),
            'conversions': conversions,
            'cost': cost,
            'revenue': revenue,
            'cpa': cpa,
            'roi': roi,
            'is_active': stream.get('is_active', False)
        })
    
    if not performance_data:
        return
    
    # Сортируем по ROI (лучшие сначала)
    performance_data.sort(key=lambda x: x['roi'], reverse=True)
    
    total_streams = len(performance_data)
    base_weight = 100 // max(total_streams, 1)
    
    for i, perf in enumerate(performance_data):
        stream_id = perf['stream_id']
        
        # Определяем новый вес на основе производительности
        if i == 0 and total_streams > 1:  # Лучший поток
            new_weight = min(base_weight * 2, 70)
        elif i == total_streams - 1 and total_streams > 1:  # Худший поток
            new_weight = max(base_weight // 2, 5)
        else:
            new_weight = base_weight
        
        # Обновляем вес только если изменился
        if abs(new_weight - perf['current_weight']) > 5: 
            update_result = update_keitaro_stream_weight(api_key, domain, stream_id, new_weight)
            
            if update_result:
                msg = (f"📊 Оптимизация: Кампания {streams[0].get('campaign_name', 'Unknown')} | "
                      f"Поток '{perf['stream_name']}' | Вес: {perf['current_weight']}% → {new_weight}% | "
                      f"ROI: {perf['roi']:.1f}% | Конверсии: {perf['conversions']}")
                
                logger.info(msg)
                send_telegram_message(msg, user_id=user_id)
@app.route('/api/keitaro/campaigns', methods=['GET'])
@login_required
def get_keitaro_campaigns():
    """Возвращает список всех кампаний из Keitaro"""
    try:
        user_id = session['user_id']
        settings = get_user_settings(user_id)
        api_key = settings.get('keitaro_api_key')
        domain = settings.get('keitaro_domain')
        
        if not api_key:
            return jsonify({'success': False, 'error': 'Keitaro API key not configured'})
        
        url = f"https://{domain}/admin_api/v1/campaigns"
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Обрабатываем разные форматы ответа
        if isinstance(data, list):
            campaigns = data
        elif isinstance(data, dict) and 'campaigns' in data:
            campaigns = data.get('campaigns', [])
        elif isinstance(data, dict) and 'data' in data:
            campaigns = data.get('data', [])
        else:
            campaigns = []
        
        # Форматируем ответ
        formatted_campaigns = []
        for campaign in campaigns:
            formatted_campaigns.append({
                'id': campaign.get('id'),
                'name': campaign.get('name', 'Unknown'),
                'status': campaign.get('status', 'active'),
                'group_id': campaign.get('group_id'),
                'cost': campaign.get('cost', 0),
                'revenue': campaign.get('revenue', 0)
            })
        
        return jsonify({
            'success': True,
            'campaigns': formatted_campaigns,
            'total': len(formatted_campaigns)
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения кампаний Keitaro: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/headline_optimization/status', methods=['GET'])
@login_required
def get_headline_optimization_status():
    """Возвращает статус оптимизации заголовков для кампании - исправленная версия"""
    try:
        user_id = session['user_id']
        campaign_id = request.args.get('campaign_id')
        
        settings = get_user_settings(user_id)
        api_key = settings.get('keitaro_api_key')
        domain = settings.get('keitaro_domain')
        
        if not api_key:
            return jsonify({'success': False, 'error': 'Keitaro API key not configured'})
        
        # Получаем текущие потоки
        streams = get_keitaro_streams(domain, api_key, campaign_id)
        if not streams:
            return jsonify({
                'success': True,
                'campaign_id': campaign_id,
                'streams': [],
                'message': 'No streams found'
            })
        
        # Получаем статистику потоков
        stream_stats = analyze_stream_performance(api_key, domain, campaign_id, "today")
        
        # Создаем словарь для быстрого поиска статистики по stream_id
        stats_by_stream = {}
        for stat in stream_stats:
            stream_id = stat.get('stream_id')
            if stream_id:
                cost = float(stat.get('cost', 0))
                conversions = int(stat.get('conversions', 0))
                revenue = float(stat.get('revenue', 0))
                clicks = int(stat.get('clicks', 0))
                
                cpa = cost / conversions if conversions > 0 else 0
                roi = ((revenue - cost) / cost * 100) if cost > 0 else 0
                ctr = (conversions / clicks * 100) if clicks > 0 else 0
                
                stats_by_stream[stream_id] = {
                    'conversions': conversions,
                    'cost': cost,
                    'revenue': revenue,
                    'clicks': clicks,
                    'cpa': cpa,
                    'roi': roi,
                    'ctr': ctr
                }
        
        # Формируем ответ с детальной информацией
        stream_data = []
        for stream in streams:
            stream_id = stream.get('id')
            stat = stats_by_stream.get(stream_id, {})
            
            stream_data.append({
                'id': stream_id,
                'name': stream.get('name', 'Unknown'),
                'campaign_id': stream.get('campaign_id'),
                'campaign_name': stream.get('campaign_name', 'Unknown'),
                'weight': stream.get('weight', 0),
                'is_active': stream.get('is_active', False),
                'url': stream.get('url', ''),
                'source': stream.get('source', ''),
                'conversions': stat.get('conversions', 0),
                'cost': stat.get('cost', 0),
                'revenue': stat.get('revenue', 0),
                'clicks': stat.get('clicks', 0),
                'cpa': stat.get('cpa', 0),
                'roi': stat.get('roi', 0),
                'ctr': stat.get('ctr', 0)
            })
        
        return jsonify({
            'success': True,
            'campaign_id': campaign_id,
            'streams': stream_data,
            'total_streams': len(stream_data),
            'active_streams': len([s for s in stream_data if s['is_active']])
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения статуса оптимизации: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/headline_optimization/run', methods=['POST'])
@login_required
def run_headline_optimization():
    """Запускает оптимизацию заголовков для кампании"""
    try:
        user_id = session['user_id']
        data = request.json
        campaign_id = data.get('campaign_id')
        
        if not campaign_id:
            return jsonify({'success': False, 'error': 'Campaign ID required'})
        
        # Запускаем оптимизацию
        optimize_headlines_automation(user_id)
        
        return jsonify({
            'success': True,
            'message': f'Оптимизация заголовков запущена для кампании {campaign_id}'
        })
        
    except Exception as e:
        logger.error(f"Ошибка запуска оптимизации: {e}")
        return jsonify({'success': False, 'error': str(e)})
def schedule_headline_optimization():
    """Планировщик для автоматической оптимизации заголовков"""
    try:
        users = get_all_users()
        
        for user in users:
            user_id = user['id']
            settings = get_user_settings(user_id)
            
            if settings.get('auto_headline_optimization', False):
                optimize_headlines_automation(user_id)
                
    except Exception as e:
        logger.error(f"Ошибка в планировщике оптимизации: {e}")

@app.route('/api/headline_optimization/update_weight', methods=['POST'])
@login_required
def update_stream_weight():
    """Ручное обновление веса потока"""
    try:
        user_id = session['user_id']
        data = request.json
        
        stream_id = data.get('stream_id')
        new_weight = data.get('new_weight')
        
        if not stream_id or new_weight is None:
            return jsonify({'success': False, 'error': 'Stream ID and weight required'})
        
        settings = get_user_settings(user_id)
        api_key = settings.get('keitaro_api_key')
        domain = settings.get('keitaro_domain')
        
        result = update_keitaro_stream_weight(api_key, domain, stream_id, new_weight)
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Вес потока обновлен до {new_weight}%'
            })
        else:
            return jsonify({'success': False, 'error': 'Ошибка обновления веса'})
            
    except Exception as e:
        logger.error(f"Ошибка обновления веса потока: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/headline_optimization')
@login_required
def headline_optimization():
    """Страница оптимизации заголовков"""
    return render_template('headline_optimization.html')
@app.route('/api/test_keitaro', methods=['POST'])
@login_required
def test_keitaro_connection():
    """Тестирует соединение с Keitaro API"""
    try:
        user_id = session['user_id']
        settings = get_user_settings(user_id)
        
        keitaro_api_key = settings.get('keitaro_api_key')
        keitaro_domain = settings.get('keitaro_domain', 'uniaffnu.com')
        
        if not keitaro_api_key:
            return jsonify({'success': False, 'error': 'Keitaro API key not configured'})
        
        logger.info(f"Тестирование Keitaro: API_KEY={keitaro_api_key[:10]}..., domain={keitaro_domain}")
        
        # Простой запрос для проверки подключения
        url = f"https://{keitaro_domain}/admin_api/v1/campaigns"
        headers = {
            "Api-Key": keitaro_api_key,
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                'success': True,
                'message': f'Соединение с Keitaro успешно. Найдено {len(data)} кампаний',
                'campaigns_count': len(data)
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Ошибка Keitaro: {response.status_code} - {response.text}'
            })
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка сети при подключении к Keitaro: {e}")
        return jsonify({'success': False, 'error': f'Ошибка сети: {e}'})
    except Exception as e:
        logger.error(f"Ошибка тестирования Keitaro: {e}")
        return jsonify({'success': False, 'error': str(e)})
# Обновите функцию выхода
@app.route('/logout')
@login_required
def logout():
    user_id = session['user_id']
    
    # Останавливаем и автоконтроль и автообновление
    stop_auto_control_and_refresh(user_id)
    
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))
@app.route('/dashboard')
@login_required
def dashboard():
    """Главная страница после входа"""
    return render_template('dashboard.html', username=session.get('username'))

@app.route('/campaigns')
@login_required
def campaigns():
    return render_template('campaigns.html')

@app.route('/adsets')
@login_required
def adsets():
    return render_template('adsets.html')

def split_clean(s: str) -> list[str]:
    """Разделяет строку на части и очищает их"""
    if not s:
        return []
    # Удаляем специальные символы и разделяем по пробелам, дефисам, подчеркиваниям
    clean_str = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(s))
    parts = re.split(r'[\s\-_]+', clean_str.lower())
    # Убираем пустые строки
    return [p for p in parts if p]
def fetch_facebook_adsets_insights(account_id, access_token):
    """Получает insights для адсетов включая CPC и CPM из Facebook"""
    try:
        url = f"https://graph.facebook.com/v18.0/act_{account_id}/insights"
        params = {
            "level": "adset",
            "fields": "adset_id,spend,cpc,cpm,cost_per_conversion,conversions,impressions",  # Добавлен cpm
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
                        'cpm': float(insight.get('cpm', 0)),  # ДОБАВЛЯЕМ CPM
                        'cost_per_conversion': float(insight.get('cost_per_conversion', 0)),
                        'conversions': int(insight.get('conversions', 0)),
                        'impressions': int(insight.get('impressions', 0))
                    }
            
            # Обрабатываем пагинацию
            next_url = data.get('paging', {}).get('next')
            url = next_url
            params = {}
        
        logger.info(f"Получено insights для {len(insights_by_adset)} адсетов (включая CPM)")
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

def calculate_daily_budget_requirements(user_id):
    """Рассчитывает требуемый дневной бюджет для всех активных кампаний"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Получаем сумму дневных бюджетов всех активных адсетов по аккаунтам
            cursor.execute("""
                SELECT 
                    a.account_id,
                    a.token,
                    SUM(a.budget) as total_daily_budget,
                    COUNT(a.adset_id) as active_adsets
                FROM adsets a
                WHERE a.user_id = ? 
                AND a.status = 'ACTIVE'
                AND a.budget > 0
                GROUP BY a.account_id, a.token
            """, (user_id,))
            
            requirements = []
            for row in cursor.fetchall():
                requirements.append({
                    'account_id': row['account_id'],
                    'token': row['token'],
                    'total_daily_budget': float(row['total_daily_budget']),
                    'active_adsets': row['active_adsets']
                })
            
            return requirements
            
    except Exception as e:
        logger.error(f"Ошибка расчета дневных бюджетов: {e}")
        return []
@app.route('/api/debug/balance', methods=['GET'])
@login_required
def debug_balance():
    """Отладочная информация о балансе"""
    try:
        user_id = session['user_id']
        
        # 1. Проверяем требования по бюджетам
        budget_req = calculate_daily_budget_requirements(user_id)
        
        # 2. Проверяем информацию об аккаунтах
        accounts_info = []
        for req in budget_req:
            account_info = get_account_limits_info(req['account_id'], req['token'])
            accounts_info.append({
                'requirement': req,
                'account_info': account_info
            })
        
        # 3. Полная проверка баланса
        warnings = check_account_balance_sufficiency(user_id)
        
        return jsonify({
            'success': True,
            'budget_requirements': budget_req,
            'accounts_info': accounts_info,
            'warnings': warnings,
            'warnings_count': len(warnings)
        })
        
    except Exception as e:
        logger.error(f"Ошибка отладки баланса: {e}")
        return jsonify({'success': False, 'error': str(e)})
def check_account_balance_sufficiency(user_id):
    """Проверяет достаточность баланса на аккаунтах"""
    try:
        # Получаем требования по бюджетам
        budget_requirements = calculate_daily_budget_requirements(user_id)
        
        warnings = []
        
        for req in budget_requirements:
            # Проверяем, что есть account_id и token
            if not req['account_id'] or not req['token']:
                continue
                
            # Получаем информацию об аккаунте
            account_info = get_account_limits_info(req['account_id'], req['token'])
            
            if account_info and 'balance' in account_info:
                balance = account_info['balance']
                required = req['total_daily_budget']
                
                # Проверяем, хватит ли баланса на сегодня
                if balance < required:
                    days_remaining = balance / required if required > 0 else 0
                    
                    warning = {
                        'account_id': req['account_id'],
                        'account_name': account_info.get('name', 'Unknown'),
                        'balance': balance,
                        'required_today': required,
                        'deficit': required - balance,
                        'days_remaining': days_remaining,
                        'active_adsets': req['active_adsets'],
                        'status': account_info.get('status', 'UNKNOWN')
                    }
                    
                    warnings.append(warning)
                else:
                    # Также возвращаем информацию об аккаунтах с достаточным балансом
                    warning = {
                        'account_id': req['account_id'],
                        'account_name': account_info.get('name', 'Unknown'),
                        'balance': balance,
                        'required_today': required,
                        'deficit': 0,
                        'days_remaining': float('inf'),
                        'active_adsets': req['active_adsets'],
                        'status': account_info.get('status', 'UNKNOWN')
                    }
                    warnings.append(warning)
        
        return warnings
        
    except Exception as e:
        logger.error(f"Ошибка проверки баланса: {e}")
        return []
def send_balance_warnings(user_id):
    """Отправляет уведомления о недостаточном балансе"""
    try:
        settings = get_user_settings(user_id)
        warnings = check_account_balance_sufficiency(user_id)
        
        if not warnings:
            return
        
        messages = []
        
        for warning in warnings:
            message = (
                f"⚠️ <b>НЕДОСТАТОЧНО СРЕДСТВ</b>\n"
                f"Аккаунт: {warning['account_name']}\n"
                f"Баланс: ${warning['balance']:.2f}\n"
                f"Требуется сегодня: ${warning['required_today']:.2f}\n"
                f"Дефицит: ${warning['deficit']:.2f}\n"
                f"Активных адсетов: {warning['active_adsets']}\n"
                f"Статус: {warning['status']}"
            )
            messages.append(message)
        
        # Отправляем все сообщения
        for msg in messages:
            send_telegram_message(msg, user_id=user_id)
            logger.warning(msg)
            
        return len(messages)
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомлений о балансе: {e}")
        return 0

def update_adset_stats_with_cpm(user_id, adset_id, stats):
    """Обновляет статистику адсета с CPM"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            updates = []
            params = {'user_id': user_id, 'adset_id': adset_id}
            
            if 'spend' in stats:
                updates.append("spend = :spend")
                params['spend'] = stats['spend']
            
            if 'leads' in stats:
                updates.append("leads = :leads")
                params['leads'] = stats['leads']
                
            if 'cpa' in stats:
                updates.append("cpa = :cpa")
                params['cpa'] = stats['cpa']
                
            if 'cpc' in stats:
                updates.append("cpc = :cpc")
                params['cpc'] = stats['cpc']
                
            if 'cpm' in stats:  # ДОБАВЛЯЕМ CPM
                updates.append("cpm = :cpm")
                params['cpm'] = stats['cpm']
                
            if 'ucpc' in stats:
                updates.append("ucpc = :ucpc")
                params['ucpc'] = stats['ucpc']
            
            if updates:
                query = f"""
                UPDATE adsets SET
                    {', '.join(updates)},
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND adset_id = :adset_id
                """
                cursor.execute(query, params)
                conn.commit()
                logger.info(f"Обновлена статистика адсета {adset_id} с CPM: {stats.get('cpm', 'N/A')}")
                
    except Exception as e:
        logger.error(f"Ошибка обновления статистики адсета {adset_id}: {e}")
@app.route('/api/sync/facebook_insights', methods=['POST'])
@login_required
def sync_facebook_insights():
    """Синхронизирует данные из Facebook Insights (включая CPM)"""
    try:
        user_id = session['user_id']
        accounts = get_user_accounts_stats(user_id)
        
        updated_count = 0
        for account in accounts:
            try:
                # Получаем insights из Facebook
                insights = fetch_facebook_adsets_insights(account['account_id'], account['token'])
                
                for adset_id, stats in insights.items():
                    # Обновляем статистику адсета
                    update_adset_stats_with_cpm(user_id, adset_id, stats)
                    updated_count += 1
                    
            except Exception as e:
                logger.error(f"Ошибка синхронизации insights для аккаунта {account['account_id']}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'message': f'Обновлено {updated_count} адсетов с данными Facebook Insights (включая CPM)',
            'updated_count': updated_count
        })
        
    except Exception as e:
        logger.error(f"Ошибка синхронизации Facebook Insights: {e}")
        return jsonify({'success': False, 'error': str(e)})
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

def build_keitaro_tree(keitaro_data: Dict[str, Dict]) -> Dict:
    """
    Улучшенное построение индекса Keitaro с дополнительными ключами
    """
    id_index: Dict[str, Dict] = {}
    name_index: Dict[str, Dict] = {}
    token_index: Dict[str, List[Dict]] = {}
    entries_by_key: Dict[str, Dict] = {}
    weak_words = {
    # GEO коды (чтобы они не доминировали в сопоставлении)
    "th", "id", "my", "sg", "vn", "ph", "br", "us", "uk", "ca", "au", "de", 
    "fr", "es", "it", "ru", "jp", "kr", "cn", "in", "mx", "ar", "co", "pe",
    "cl", "za", "ng", "eg", "sa", "ae", "tr", "pl", "nl", "se", "no", "dk",
    "fi", "be", "ch", "at",
    
    # Общие слова в названиях кампаний
    "monah", "test", "copy", "vst", "old", "archive", "arch", "backup", "bk",
    "final", "new", "beta", "visual", "lang", "gpt", "voltaren", "swype",
    "korotish", "yavis", "nepokupay", "olegneizd", "sereg", "podctast",
    "doposle", "legend", "voda", "duhi", "duh",
    
    # Технические термины и аббревиатуры
    "k", "y", "rr", "kk", "tt", "d", "dd", "sa", "am", "campaign", "adset",
    "ad", "fb", "facebook", "api",
    
    # Слова-модификаторы
    "ver", "version", "v", "var", "variant", "test", "testing", "temp",
    "temporary", "demo", "sample", "example",
    
    # Даты и числа (общие паттерны)
    "08", "07", "06", "05", "04", "03", "02", "01", "11", "12", "13", "14",
    "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26",
    "27", "28", "29", "30", "31", "2023", "2024", "2025",
    
    # Общие слова
    "the", "and", "or", "of", "in", "on", "at", "to", "for", "with", "by",
    "from", "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    
    # Размеры и позиции
    "big", "small", "large", "medium", "size", "pos", "position", "place",
    
    # Статусы
    "active", "paused", "deleted", "disabled", "enabled", "running", "stopped"
}
    def looks_like_id(k: str) -> bool:
        k0 = k.strip()
        # Более строгая проверка на ID
        return bool(re.fullmatch(r'\d{10,}', k0)) or bool(re.search(r'^\d+\.\d+$', k0))

    for key, stats in keitaro_data.items():
        if not key:  # Пропускаем пустые ключи
            continue
            
        tokens = set(split_clean(key))
        kind = 'id' if looks_like_id(key) else 'name'
        entry = {'key': key, 'stats': stats, 'tokens': tokens, 'kind': kind}
        entries_by_key[key] = entry

        if kind == 'id':
            id_index[key] = entry
        else:
            name_index[key] = entry

        # Индекс по токенам (только значимые слова)
        for t in tokens:
            if t not in weak_words and len(t) > 2:  # Исключаем слабые и короткие слова
                token_index.setdefault(t, []).append(entry)
                
        # Добавляем альтернативные ключи для лучшего поиска
        if kind == 'name':
            # Нормализованная версия
            normalized = normalize_campaign_name(key)
            if normalized and normalized != key and normalized not in entries_by_key:
                alt_entry = entry.copy()
                alt_entry['key'] = normalized
                name_index[normalized] = alt_entry
                entries_by_key[normalized] = alt_entry
                
            # Версия без дат
            no_dates = re.sub(r'\d{1,2}\.\d{1,2}', '', key).strip()
            if no_dates and no_dates != key and no_dates not in entries_by_key:
                alt_entry = entry.copy()
                alt_entry['key'] = no_dates
                name_index[no_dates] = alt_entry
                entries_by_key[no_dates] = alt_entry

    logger.info(f"[TREE] Улучшенный индекс Keitaro: id_index={len(id_index)}, name_index={len(name_index)}, "
                f"token_index(tokens)={len(token_index)}, entries={len(entries_by_key)}")
    return {
        'id_index': id_index,
        'name_index': name_index,
        'token_index': token_index,
        'entries_by_key': entries_by_key
    }
def find_in_tree(
    tree: Dict,
    used_keys: Set[str],
    fb_id: str = None,
    fb_name: str = None,
    fb_parent_name: str = None,
    fb_campaign_id: str = None,
    min_score: int = 5  # Увеличиваем порог для более точного сопоставления
) -> Dict:
    """
    Улучшенный поиск соответствия в Keitaro-дереве с проверкой релевантности
    """
    weak_words = {"monah", "test", "copy", "vst", "old", "archive", "arch", "backup", 
                 "bk", "final", "new", "beta", "th", "id", "my", "sg", "vn", "ph"}
    
    zeros = {'spend': 0, 'leads': 0, 'cpa': 0, 'ucpc': 0, 'cpc': 0}

    id_index = tree.get('id_index', {})
    name_index = tree.get('name_index', {})
    token_index = tree.get('token_index', {})

    # 1) По ID адсета (точное совпадение)
    if fb_id:
        e = id_index.get(fb_id)
        if e and e['key'] not in used_keys:
            used_keys.add(e['key'])
            logger.info(f"[MATCH] Прямой ID-матч по adset_id: {fb_id} -> {e['key']}")
            return e['stats']

    # 2) По ID кампании (точное совпадение)
    if fb_campaign_id:
        e = id_index.get(fb_campaign_id)
        if e and e['key'] not in used_keys:
            used_keys.add(e['key'])
            logger.info(f"[MATCH] Прямой ID-матч по campaign_id: {fb_campaign_id} -> {e['key']}")
            return e['stats']

    # 3) По точному имени
    if fb_name:
        e = name_index.get(fb_name)
        if e and e['key'] not in used_keys:
            used_keys.add(e['key'])
            logger.info(f"[MATCH] Прямой матч по имени: \"{fb_name}\" -> {e['key']}")
            return e['stats']

    # 4) Улучшенный частичный матч по токенам
    def _advanced_token_match(query_name: str, is_adset: bool = True) -> Dict:
        if not query_name:
            return None
            
        qtokens = split_clean(query_name)
        if not qtokens:
            return None

        # Фильтруем слабые слова
        strong_qtokens = [t for t in qtokens if t not in weak_words and len(t) > 2]
        if not strong_qtokens:
            return None

        candidates = {}
        
        # Ищем кандидатов по токенному индексу
        for token in strong_qtokens:
            for entry in token_index.get(token, []):
                if entry['key'] in used_keys:
                    continue
                    
                # Пропускаем записи без данных
                if entry['stats'].get('spend', 0) <= 0 and entry['stats'].get('leads', 0) <= 0:
                    continue
                
                # Сравниваем токены
                entry_tokens = entry['tokens']
                common_strong = len([t for t in strong_qtokens if t in entry_tokens and t not in weak_words])
                common_total = len(set(qtokens) & entry_tokens)
                
                if common_strong <= 0:
                    continue
                
                # Дополнительные проверки релевантности
                relevance_score = 0
                
                # Проверка на совпадение GEO кодов
                query_geo = extract_geo_from_name(query_name, [])
                entry_geo = extract_geo_from_name(entry['key'], [])
                if query_geo != 'N/A' and entry_geo != 'N/A' and query_geo == entry_geo:
                    relevance_score += 3
                
                # Проверка на совпадение числовых идентификаторов
                query_numbers = re.findall(r'\d+', query_name)
                entry_numbers = re.findall(r'\d+', entry['key'])
                common_numbers = set(query_numbers) & set(entry_numbers)
                if common_numbers:
                    relevance_score += len(common_numbers) * 2
                
                # Проверка на совпадение дат
                query_dates = re.findall(r'\d{1,2}\.\d{1,2}', query_name)
                entry_dates = re.findall(r'\d{1,2}\.\d{1,2}', entry['key'])
                common_dates = set(query_dates) & set(entry_dates)
                if common_dates:
                    relevance_score += len(common_dates) * 3
                
                total_score = common_strong + relevance_score
                
                if total_score >= min_score:
                    candidates[entry['key']] = {
                        'score': total_score,
                        'common_strong': common_strong,
                        'common_total': common_total,
                        'relevance': relevance_score,
                        'entry': entry
                    }
        
        if not candidates:
            return None
        
        # Выбираем лучшего кандидата
        best_candidate = max(candidates.values(), key=lambda x: (x['score'], x['relevance']))
        
        if best_candidate['score'] >= min_score:
            used_keys.add(best_candidate['entry']['key'])
            logger.info(f"[MATCH] Улучшенный матч: \"{query_name}\" -> {best_candidate['entry']['key']} "
                       f"(score={best_candidate['score']}, strong={best_candidate['common_strong']}, "
                       f"relevance={best_candidate['relevance']})")
            return best_candidate['entry']['stats']
        
        return None

    # 5) Поиск по имени адсета
    if fb_name:
        stats = _advanced_token_match(fb_name, is_adset=True)
        if stats:
            return stats

    # 6) Поиск по имени кампании (родителя)
    if fb_parent_name:
        stats = _advanced_token_match(fb_parent_name, is_adset=False)
        if stats:
            return stats

    logger.info(f"[MATCH] Не найдено релевантных совпадений для: "
                f"id={fb_id}, name={fb_name}, parent={fb_parent_name}, campaign_id={fb_campaign_id}")
    return zeros
@app.route('/api/save_and_sync', methods=['POST'])
@login_required
def save_and_sync():
    try:
        logger.info("=== НАЧАЛО СИНХРОНИЗАЦИИ ===")
        user_id = session['user_id']
        accounts_data = request.json.get('accounts', [])
        if not accounts_data:
            return jsonify({'success': False, 'error': 'Нет данных для сохранения'})

        # Настройки Keitaro
        settings = get_user_settings(user_id)
        keitaro_api_key = settings.get('keitaro_api_key')
        keitaro_domain = settings.get('keitaro_domain', 'uniaffnu.com')

        # Загружаем данные Keitaro
        keitaro_data_by_name = {}
        if keitaro_api_key:
            report = fetch_keitaro_report(keitaro_api_key, keitaro_domain)
            for row in report.get("rows", []):
                adset_name = str(row.get("sub_id_9") or "").strip()
                if not adset_name:
                    continue

                metrics = {
                    "spend": float(row.get("cost", 0) or 0),
                    "leads": int(row.get("leads", 0) or 0),
                    "cpa": float(row.get("cpa", 0) or 0),
                    "ucpc": float(row.get("ucpc", 0) or 0),
                    "cpc": float(row.get("cpc", 0) or 0)
                }
                keitaro_data_by_name[adset_name] = metrics

            logger.info(f"Обработано записей из Keitaro: {len(keitaro_data_by_name)} по имени")

        saved_accounts = total_campaigns = total_adsets = keitaro_matched = 0

        for acc in accounts_data:
            account_id = acc.get("account_id", "").replace("act_", "")
            token = acc.get("token", "")
            if not account_id or not token:
                continue

            try:
                # Проверяем токен
                res = requests.get(
                    f"https://graph.facebook.com/v18.0/act_{account_id}",
                    params={"access_token": token, "fields": "id,name,account_status"},
                    timeout=30
                ).json()
                if "error" in res:
                    logger.warning(f"Неверный токен для {account_id}: {res['error']['message']}")
                    continue

                # Кампании
                campaigns = fetch_facebook_campaigns(account_id, token)
                for camp in campaigns:
                    camp_id = camp["id"]
                    camp_name = camp.get("name", "")

                    add_user_campaign(user_id, {
                        "king": "Facebook",
                        "name": camp_name,
                        "status": camp.get("status", "PAUSED"),
                        "campaign_id": camp_id,
                        "account_id": account_id,
                        "token": token
                    })
                    total_campaigns += 1

                # Адсеты
                adsets = fetch_facebook_adsets(account_id, token)
                for ad in adsets:
                    ad_name = ad.get("name", "")
                    adset_id = ad.get("id", "")
                    camp_id = ad.get("campaign_id", "")

                    stats = keitaro_data_by_name.get(ad_name, {})

                    budget = float(ad.get("daily_budget", 0)) / 100 if ad.get("daily_budget") else 0

                    add_user_adset(user_id, {
                        "name": ad_name,
                        "adset_id": adset_id,
                        "campaign_id": camp_id,
                        "status": ad.get("status", "PAUSED"),
                        "account_id": account_id,
                        "token": token,
                        "budget": budget,
                        "spend": stats.get("spend", 0),
                        "leads": stats.get("leads", 0),
                        "cpa": stats.get("cpa", 0),
                        "ucpc": stats.get("ucpc", 0),
                        "cpc": stats.get("cpc", 0),
                        "king": "Facebook",
                        "effective_status": ad.get("effective_status", ""),
                        "ad_name": ad_name,
                        "manual_pause": 0
                    })

                    if stats:
                        keitaro_matched += 1

                    total_adsets += 1

                saved_accounts += 1

            except requests.exceptions.RequestException as e:
                logger.warning(f"Ошибка сети для аккаунта {account_id}: {e}")
                continue

        return jsonify({
            "success": True,
            "saved_accounts": saved_accounts,
            "total_campaigns": total_campaigns,
            "total_adsets": total_adsets,
            "keitaro_matched": keitaro_matched,
            "keitaro_records": len(keitaro_data_by_name)
        })

    except Exception as e:
        logger.error(f"Критическая ошибка синхронизации: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/adsets/sync_status', methods=['POST'])
@login_required
def sync_adsets_status():
    """Синхронизирует статусы адсетов с Facebook API"""
    try:
        user_id = session['user_id']
        adsets = get_user_adsets(user_id)
        
        updated_count = 0
        for adset in adsets:
            try:
                # Получаем актуальный статус из Facebook
                url = f"https://graph.facebook.com/v18.0/{adset['adset_id']}"
                params = {
                    'fields': 'status,effective_status',
                    'access_token': adset['token']
                }
                
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if 'error' not in data:
                    new_status = data.get('status') or data.get('effective_status')
                    if new_status and new_status != adset['status']:
                        # Обновляем статус в базе
                        update_user_adset_status(user_id, adset['adset_id'], new_status)
                        updated_count += 1
                        
            except Exception as e:
                logger.error(f"Ошибка синхронизации статуса для адсета {adset['adset_id']}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'message': f'Обновлено {updated_count} статусов адсетов',
            'updated_count': updated_count
        })
        
    except Exception as e:
        logger.error(f"Ошибка синхронизации статусов: {e}")
        return jsonify({'success': False, 'error': str(e)})
def normalize_campaign_name(name):
    """Улучшенная нормализация названия кампании"""
    if not name:
        return ""
    
    # Приводим к нижнему регистру
    normalized = name.lower()
    
    # Удаляем специальные символы, но сохраняем точки в датах
    normalized = re.sub(r'[^a-z0-9\s\.]', ' ', normalized)
    
    # Заменяем multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Удаляем leading/trailing spaces
    normalized = normalized.strip()
    
    return normalized
@app.route('/api/accounts', methods=['GET'])
@login_required
def get_accounts():
    """Возвращает список всех аккаунтов пользователя"""
    try:
        user_id = session['user_id']
        
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Получаем уникальные комбинации account_id + token
            cursor.execute("""
            SELECT DISTINCT account_id, token 
            FROM campaigns 
            WHERE user_id = ? AND account_id IS NOT NULL AND token IS NOT NULL
            """, (user_id,))
            
            accounts = []
            for row in cursor.fetchall():
                accounts.append({
                    'account_id': row['account_id'],
                    'token': row['token']
                })
            
            return jsonify({
                'success': True,
                'accounts': accounts,
                'count': len(accounts)
            })
            
    except Exception as e:
        logger.error(f"Ошибка получения аккаунтов: {e}")
        return jsonify({'success': False, 'error': str(e)})
def add_campaign_mapping(user_id: int, fb_campaign_id: str, keitaro_key: str, 
                        campaign_name: str = "", match_type: str = ""):
    """Добавляет соответствие между Facebook и Keitaro"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO campaign_mapping 
            (user_id, facebook_campaign_id, keitaro_key, campaign_name, match_type)
            VALUES (?, ?, ?, ?, ?)
            """, (user_id, fb_campaign_id, keitaro_key, campaign_name, match_type))
            conn.commit()
def get_keitaro_id_for_campaign(user_id: int, fb_campaign_id: str) -> Optional[str]:
    """Возвращает Keitaro key для Facebook campaign_id"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT keitaro_key FROM campaign_mapping 
            WHERE user_id = ? AND facebook_campaign_id = ?
            """, (user_id, fb_campaign_id))
            row = cursor.fetchone()
            return row['keitaro_key'] if row else None

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/add_campaign', methods=['GET', 'POST'])
@login_required
def add_campaign_page():
    if request.method == 'POST':
        data = {
            'king': request.form['king'],
            'name': request.form['name'],
            'status': request.form['status'],
            'campaign_id': request.form['campaign_id'],
            'account_id': request.form['account_id'],
            'token': request.form['token']
        }
        add_user_campaign(session['user_id'], data)
        flash('Кампания успешно добавлена', 'success')
        return redirect(url_for('campaigns'))
    return render_template('add_campaign.html')

@app.route('/add_adset', methods=['GET', 'POST'])
@login_required
def add_adset_page():
    if request.method == 'POST':
        data = {
            'name': request.form['name'],
            'adset_id': request.form['adset_id'],
            'ucpc': float(request.form['ucpc']),
            'spend': float(request.form['spend']),
            'cpa': float(request.form['cpa']),
            'status': request.form['status'],
            'geo': request.form['geo'],
            'token': request.form['token'],
            'leads': int(request.form['leads']),
            'manual_pause': 1 if request.form.get('manual_pause') == 'on' else 0,
            'king': request.form['king'],
            'effective_status': request.form['effective_status'],
            'ad_name': request.form['ad_name'],
            'budget': float(request.form['budget'])
        }
        add_user_adset(session['user_id'], data)
        flash('AdSet успешно добавлен', 'success')
        return redirect(url_for('adsets'))
    return render_template('add_adset.html')
@app.route('/api/adsets', methods=['GET'])
@login_required
def get_adsets():
    try:
        user_id = session['user_id']
        account_id = request.args.get('account_id')
        
        if account_id:
            adsets = get_account_adsets(user_id, account_id)
        else:
            adsets = get_user_adsets(user_id)
        
        return jsonify({
            'success': True,
            'data': adsets
        })
    except Exception as e:
        logger.error(f"Ошибка получения адсетов: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

def get_account_adsets(user_id, account_id):
    """Получает все адсеты для конкретного аккаунта, включая из выключенных кампаний"""
    with get_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT a.*
        FROM adsets a
        LEFT JOIN campaigns c ON a.campaign_id = c.campaign_id
        WHERE a.user_id = ? AND a.account_id = ?
        """, (user_id, account_id))
        return [dict(row) for row in cursor.fetchall()]

@app.route('/api/adsets', methods=['GET'])
@login_required
def get_adsets_api():
    try:
        adsets = get_user_adsets(session['user_id'])
        print(f"DEBUG: Found {len(adsets)} adsets")
        
        # Проверяем структуру данных
        if adsets and len(adsets) > 0:
            print(f"DEBUG: First adset structure: {adsets[0]}")
        
        return jsonify({
            'success': True,
            'data': adsets,
            'count': len(adsets)
        })
    except Exception as e:
        logger.error(f"Error getting adsets: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/refresh_adsets', methods=['POST'])
@login_required
def refresh_adsets_api():
    try:
        # Здесь будет логика обновления адсетов как в вашем коде
        # Пока просто возвращаем успех
        return jsonify({
            'success': True,
            'message': 'Adsets refresh initiated'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/campaign/pause', methods=['POST'])
@login_required
def pause_campaign_api():
    data = request.json
    campaign_id = data.get('campaign_id')
    name = data.get('name')
    
    try:
        update_user_campaign_status(session['user_id'], campaign_id, 'PAUSED')
        logger.info(f"🔴 Кампания «{name}» отключена")
        send_telegram_message(f"🔴 Кампания «{name}» отключена")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Ошибка отключения кампании «{name}»: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/campaign/resume', methods=['POST'])
@login_required
def resume_campaign_api():
    data = request.json
    campaign_id = data.get('campaign_id')
    name = data.get('name')
    
    try:
        update_user_campaign_status(session['user_id'], campaign_id, 'ACTIVE')
        logger.info(f"🟢 Кампания «{name}» включена")
        send_telegram_message(f"🟢 Кампания «{name}» включена")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Ошибка включения кампании «{name}»: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/adset/pause', methods=['POST'])
@login_required
def pause_adset_api():
    try:
        data = request.json
        adset_id = data.get('adset_id')
        name = data.get('name')
        token = data.get('token')
        
        if not all([adset_id, name, token]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        # Отключаем через Facebook API
        url = f"https://graph.facebook.com/v18.0/{adset_id}"
        response = requests.post(
            url,
            params={"access_token": token},
            data={"status": "PAUSED"},
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        
        if result.get('success') or result.get('id') == adset_id:
            update_user_adset_status(session['user_id'], adset_id, 'PAUSED')
            logger.info(f"🔴 AdSet «{name}» отключён")
            send_telegram_message(f"🔴 AdSet «{name}» отключён")
            return jsonify({'success': True})
        else:
            error_msg = result.get('error', {}).get('message', 'Unknown error')
            raise Exception(f"Facebook API error: {error_msg}")
            
    except Exception as e:
        logger.error(f"Ошибка отключения AdSet «{data.get('name', 'unknown')}»: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/adset/resume', methods=['POST'])
@login_required
def resume_adset_api():
    try:
        data = request.json
        adset_id = data.get('adset_id')
        name = data.get('name')
        token = data.get('token')
        
        if not all([adset_id, name, token]):
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        # Включаем через Facebook API
        url = f"https://graph.facebook.com/v18.0/{adset_id}"
        response = requests.post(
            url,
            params={"access_token": token},
            data={"status": "ACTIVE"},
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        
        if result.get('success') or result.get('id') == adset_id:
            update_user_adset_status(session['user_id'], adset_id, 'ACTIVE')
            logger.info(f"🟢 AdSet «{name}» включён")
            send_telegram_message(f"🟢 AdSet «{name}» включён")
            return jsonify({'success': True})
        else:
            error_msg = result.get('error', {}).get('message', 'Unknown error')
            raise Exception(f"Facebook API error: {error_msg}")
            
    except Exception as e:
        logger.error(f"Ошибка включения AdSet «{data.get('name', 'unknown')}»: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Добавляем API endpoint для ручной проверки
@app.route('/api/check_balance', methods=['GET'])
@login_required
def check_balance_api():
    """Проверка баланса аккаунтов"""
    try:
        user_id = session['user_id']
        warnings = check_account_balance_sufficiency(user_id)
        
        return jsonify({
            'success': True,
            'warnings': warnings,
            'count': len(warnings)
        })
        
    except Exception as e:
        logger.error(f"Ошибка проверки баланса: {e}")
        return jsonify({'success': False, 'error': str(e)})
# Добавляем функцию в планировщик для регулярной проверки
def schedule_balance_checks():
    """Планировщик для регулярной проверки баланса"""
    try:
        users = get_all_users()
        
        for user in users:
            user_id = user['id']
            settings = get_user_settings(user_id)
            
            # Проверяем баланс каждые 4 часа
            if settings.get('balance_check_enabled', True):
                send_balance_warnings(user_id)
                
    except Exception as e:
        logger.error(f"Ошибка в планировщике проверки баланса: {e}")

# Добавляем настройку в интерфейс
@app.route('/api/settings', methods=['POST'])
@login_required
def update_settings():
    """Обновление настроек с новой опцией"""
    try:
        user_id = session['user_id']
        data = request.json
        
        # Добавляем новую настройку
        if 'balance_check_enabled' not in data:
            data['balance_check_enabled'] = True
            
        update_user_settings(user_id, data)
        return jsonify({'success': True, 'message': 'Настройки сохранены'})
        
    except Exception as e:
        logger.error(f"Ошибка сохранения настроек: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto_refresh', methods=['POST'])
@login_required
def handle_auto_refresh():
    """Управление автообновлением и автоконтролем вместе"""
    try:
        user_id = session['user_id']
        data = request.json
        action = data.get('action')
        interval = data.get('interval')
        
        if action == 'start':
            # Запускаем и автоконтроль и автообновление
            if interval and isinstance(interval, int) and interval > 0:
                # Обновляем настройки
                settings = get_user_settings(user_id)
                settings['auto_refresh_interval'] = interval
                update_user_settings(user_id, settings)
                
                # Запускаем оба компонента
                start_auto_control_and_refresh(user_id)
                send_balance_warnings(user_id)
                return jsonify({
                    'success': True, 
                    'message': f'Автоконтроль и автообновление запущены (интервал: {interval} мин)'
                })
            else:
                return jsonify({'success': False, 'error': 'Неверный интервал'})
                
        elif action == 'stop':
            # Останавливаем и автоконтроль и автообновление
            stop_auto_control_and_refresh(user_id)
            return jsonify({
                'success': True, 
                'message': 'Автоконтроль и автообновление остановлены'
            })
            
        elif action == 'status':
            # Получаем комбинированный статус
            status = get_combined_auto_status(user_id)
            return jsonify({'success': True, 'status': status})
            
        else:
            return jsonify({'success': False, 'error': 'Неизвестное действие'})
            
    except Exception as e:
        logger.error(f"Ошибка управления автообновлением: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Глобальные переменные для управления автообновлением
auto_refresh_timers = {}
auto_refresh_lock = threading.Lock()
@app.route('/balance_monitor')
@login_required
def balance_monitor():
    """Страница мониторинга баланса"""
    return render_template('balance_monitor.html')
def start_auto_refresh(user_id, interval_minutes):
    """Запускает автообновление для пользователя"""
    with auto_refresh_lock:
        # Останавливаем предыдущий таймер, если есть
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
        
        # Создаем новый таймер
        interval_seconds = interval_minutes * 60
        timer = threading.Timer(interval_seconds, lambda: auto_refresh_user_data(user_id, interval_minutes))
        timer.daemon = True
        timer.start()
        
        auto_refresh_timers[user_id] = timer
        auto_control(user_id)
        logger.info(f"Автообновление запущено для пользователя {user_id}, интервал: {interval_minutes} мин")

def stop_auto_refresh(user_id):
    """Останавливает автообновление для пользователя"""
    with auto_refresh_lock:
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
            del auto_refresh_timers[user_id]
            logger.info(f"Автообновление остановлено для пользователя {user_id}")

def auto_refresh_user_data(user_id, interval_minutes):
    """Функция автообновления данных пользователя"""
    try:
        with app.app_context():
            logger.info(f"Автообновление данных для пользователя {user_id}")
            
            # Получаем настройки пользователя
            settings = get_user_settings(user_id)
            
            # Обновляем кампании, если включено
            if settings.get('auto_refresh_campaigns', True):
                refresh_campaigns_internal(user_id)
            
            # Обновляем адсеты, если включено
            if settings.get('auto_refresh_adsets', True):
                refresh_adsets_internal(user_id)
            
            # Синхронизируем с Keitaro, если настроено
            if settings.get('keitaro_api_key'):
                sync_keitaro_only_internal(user_id)
            
            logger.info(f"Автообновление завершено для пользователя {user_id}")
            
    except Exception as e:
        logger.error(f"Ошибка автообновления для пользователя {user_id}: {e}")
    
    finally:
        # Перезапускаем таймер
        start_auto_refresh(user_id, interval_minutes)

def refresh_campaigns_internal(user_id):
    """Внутренняя функция обновления кампаний"""
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
def refresh_adsets_internal(user_id):
    """Внутренняя функция обновления адсетов"""
    try:
        campaigns = get_user_campaigns(user_id)
        accounts = {}
        
        # Получаем известные GEO коды для улучшенного распознавания
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
                
                # Определяем GEO из названия адсета
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
                    'geo': geo,  # Сохраняем определенный GEO
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
def get_auto_refresh_status(user_id):
    """Возвращает статус автообновления"""
    with auto_refresh_lock:
        is_running = user_id in auto_refresh_timers
        settings = get_user_settings(user_id)
        interval = settings.get('auto_refresh_interval', 5)
        
        return {
            'running': is_running,
            'interval': interval,
            'next_refresh': None  # Можно добавить расчет времени следующего обновления
        }

# Добавьте эти функции в app.py

@app.route('/api/auto_budget/run', methods=['POST'])
@login_required
def run_auto_budget():
    """Запуск авто-бюджета для всех адсетов"""
    try:
        user_id = session['user_id']
        updated_count = 0
        
        # Получаем адсеты с включенным авто-бюджетом
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*, c.token 
                FROM adsets a
                LEFT JOIN campaigns c ON a.campaign_id = c.campaign_id AND a.user_id = c.user_id
                WHERE a.user_id = ? AND a.status = 'ACTIVE'
                AND (a.auto_budget_increase = 1 OR a.auto_budget_decrease = 1)
            """, (user_id,))
            
            adsets = [dict(row) for row in cursor.fetchall()]
        
        for adset in adsets:
            try:
                success = apply_auto_budget_rules(user_id, adset)
                if success:
                    updated_count += 1
            except Exception as e:
                logger.error(f"Ошибка авто-бюджета для адсета {adset['adset_id']}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'message': f'Авто-бюджет применен для {updated_count} адсетов',
            'updated_count': updated_count
        })
        
    except Exception as e:
        logger.error(f"Ошибка запуска авто-бюджета: {e}")
        return jsonify({'success': False, 'error': str(e)})

def apply_auto_budget_rules(user_id, adset):
    """Применяет правила авто-бюджета к адсету"""
    current_budget = float(adset.get('budget', 0))
    spend = float(adset.get('spend', 0))
    leads = int(adset.get('leads', 0))
    cpa = float(adset.get('cpa', 0))
    
    # Получаем настройки GEO правил
    geo_rules = get_user_geo_rules(user_id)
    geo = adset.get('geo', 'N/A')
    rule = geo_rules.get(geo, {})
    
    max_cpa = rule.get('max_cpa', 100)
    min_spend = rule.get('min_spend', 50)
    
    new_budget = current_budget
    action = None
    
    # Логика увеличения бюджета
    if (adset.get('auto_budget_increase') and 
        leads > 0 and cpa <= max_cpa * 0.7 and 
        spend >= min_spend / 2):
        
        increase_step = float(adset.get('budget_increase_step', 1.2))
        new_budget = current_budget * increase_step
        action = 'increase'
    
    # Логика уменьшения бюджета
    elif (adset.get('auto_budget_decrease') and 
          ((leads == 0 and spend >= min_spend) or 
           (leads > 0 and cpa > max_cpa * 1.3))):
        
        decrease_step = float(adset.get('budget_decrease_step', 0.8))
        new_budget = current_budget * decrease_step
        action = 'decrease'
    
    # Проверяем лимиты бюджета
    max_budget = float(adset.get('max_budget', 0))
    min_budget = float(adset.get('min_budget', 0))
    
    if max_budget > 0 and new_budget > max_budget:
        new_budget = max_budget
    if min_budget > 0 and new_budget < min_budget:
        new_budget = min_budget
    
    # Если бюджет изменился - применяем
    if action and abs(new_budget - current_budget) >= 0.01:
        success = update_adset_budget_facebook(
            adset['adset_id'], 
            new_budget, 
            adset['token']
        )
        
        if success:
            update_user_adset_budget(user_id, adset['adset_id'], new_budget)
            
            msg = (f"💰 Авто-бюджет: {adset['name']} "
                  f"({action}: ${current_budget:.2f} → ${new_budget:.2f}) "
                  f"CPA: ${cpa:.2f}, Leads: {leads}")
            
            logger.info(msg)
            send_telegram_message(msg, user_id=user_id)
            return True
    
    return False
@app.route('/api/adset/budget_settings', methods=['GET', 'POST'])
@login_required
def handle_adset_budget_settings():
    """Управление настройками авто-бюджета для адсета"""
    user_id = session['user_id']
    
    if request.method == 'GET':
        try:
            adset_id = request.args.get('adset_id')
            if not adset_id:
                return jsonify({'success': False, 'error': 'Не указан adset_id'})
            
            settings = get_adset_budget_settings(user_id, adset_id)
            if settings:
                return jsonify({'success': True, 'settings': settings})
            else:
                return jsonify({'success': False, 'error': 'AdSet не найден'})
                
        except Exception as e:
            logger.error(f"Ошибка получения настроек бюджета: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    elif request.method == 'POST':
        try:
            data = request.json
            adset_id = data.get('adset_id')
            
            if not adset_id:
                return jsonify({'success': False, 'error': 'Не указан adset_id'})
            
            if update_adset_budget_settings(user_id, adset_id, data):
                return jsonify({'success': True, 'message': 'Настройки бюджета обновлены'})
            else:
                return jsonify({'success': False, 'error': 'Ошибка сохранения настроек'})
                
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек бюджета: {e}")
            return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/limits')
@login_required
def admin_limits():
    """Админ панель с лимитами всех аккаунтов"""
    if not is_admin_user(session['user_id']):
        return render_template('access_denied.html')
    
    return render_template('admin_panel.html')
@app.route('/api/admin/all_accounts_limits')
@login_required
def get_all_accounts_limits():
    """Возвращает информацию о лимитах всех аккаунтов всех пользователей"""
    if not is_admin_user(session['user_id']):
        return jsonify({'success': False, 'error': 'Доступ запрещен'})
    
    try:
        all_accounts_data = get_all_accounts_stats()
        accounts_info = []
        total_stats = {
            'total_accounts': 0,
            'active_accounts': 0,
            'disabled_accounts': 0,
            'error_accounts': 0,
            'total_spend': 0,
            'total_balance': 0,
            'total_limit': 0,
            'total_requests': 0
        }
        
        for account_data in all_accounts_data:
            account_info = get_account_limits_info(account_data['account_id'], account_data['token'])
            
            if account_info:
                # Добавляем информацию о пользователе
                account_info['user_id'] = account_data['user_id']
                account_info['username'] = account_data['username']
                accounts_info.append(account_info)
                
                # Обновляем общую статистику
                total_stats['total_accounts'] += 1
                
                if account_info['status'] == 'ACTIVE':
                    total_stats['active_accounts'] += 1
                elif account_info['status'] in ['DISABLED', 'INVALID_DATA', 'API_ERROR', 'NETWORK_ERROR', 'ERROR']:
                    total_stats['error_accounts'] += 1
                else:
                    total_stats['disabled_accounts'] += 1
                
                total_stats['total_spend'] += account_info.get('spend', 0)
                total_stats['total_balance'] += account_info.get('balance', 0)
                total_stats['total_limit'] += account_info.get('spend_cap', 0)
                total_stats['total_requests'] += account_info.get('requests_today', 0)
        
        logger.info(f"Обработано {len(accounts_info)} аккаунтов из {len(all_accounts_data)}")
        
        return jsonify({
            'success': True,
            'stats': total_stats,
            'accounts': accounts_info,
            'debug': {
                'total_raw_accounts': len(all_accounts_data),
                'total_processed_accounts': len(accounts_info)
            }
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения лимитов всех аккаунтов: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/admin/users')
@login_required
def get_all_users_api():
    """Возвращает список всех пользователей (только для админов)"""
    if not is_admin_user(session['user_id']):
        return jsonify({'success': False, 'error': 'Доступ запрещен'})
    
    try:
        users = get_all_users()
        return jsonify({
            'success': True,
            'users': users
        })
    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/user/<int:user_id>/accounts')
@login_required
def get_user_accounts_api(user_id):
    """Возвращает аккаунты конкретного пользователя (только для админов)"""
    if not is_admin_user(session['user_id']):
        return jsonify({'success': False, 'error': 'Доступ запрещен'})
    
    try:
        accounts = get_user_accounts_stats(user_id)
        accounts_info = []
        
        for account in accounts:
            account_info = get_account_limits_info(account['account_id'], account['token'])
            if account_info:
                accounts_info.append(account_info)
        
        return jsonify({
            'success': True,
            'accounts': accounts_info
        })
    except Exception as e:
        logger.error(f"Ошибка получения аккаунтов пользователя {user_id}: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/reserve_tokens_stats')
@login_required
def get_reserve_tokens_stats():
    """Возвращает статистику по резервным токенам всех пользователей"""
    if not is_admin_user(session['user_id']):
        return jsonify({'success': False, 'error': 'Доступ запрещен'})
    
    try:
        users = get_all_users()
        tokens_stats = []
        
        for user in users:
            user_id = user['id']
            tokens = get_reserve_tokens(user_id)
            
            if tokens:
                total_tokens = sum(len(token_list) for token_list in tokens.values())
                kings_count = len(tokens)
                
                tokens_stats.append({
                    'user_id': user_id,
                    'username': user['username'],
                    'total_tokens': total_tokens,
                    'kings_count': kings_count,
                    'kings': list(tokens.keys())
                })
        
        return jsonify({
            'success': True,
            'stats': tokens_stats
        })
    except Exception as e:
        logger.error(f"Ошибка получения статистики резервных токенов: {e}")
        return jsonify({'success': False, 'error': str(e)})



@app.route('/api/auto_control', methods=['POST'])
@login_required
def run_auto_control_api():
    try:
        auto_control(session['user_id'])
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Ошибка автоконтроля: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/debug/campaigns')
@login_required
def debug_campaigns():
    campaigns = get_user_campaigns(session['user_id'])
    return jsonify(campaigns)
@app.route('/api/settings', methods=['GET', 'POST', 'OPTIONS'])
@login_required
def handle_settings():
    user_id = session['user_id']
    
    if request.method == 'GET':
        try:
            config = get_user_settings(user_id)
            return jsonify({'success': True, 'config': config})
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    elif request.method == 'POST':
        try:
            data = request.json
            update_user_settings(user_id, data)
            return jsonify({'success': True, 'message': 'Настройки сохранены'})
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    elif request.method == 'OPTIONS':
        return jsonify({'success': True})
@app.route('/manual_data', methods=['GET', 'POST'])
@login_required
def manual_data():
    """Страница для ручного ввода данных"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'No data provided'})
            
            # Логика сохранения данных
            logger.info(f"Received manual data: {json.dumps(data, ensure_ascii=False)}")
            return jsonify({'success': True, 'message': 'Data received successfully'})
        
        except Exception as e:
            logger.error(f"Error processing manual data: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})
    
    return render_template('manual_data.html')
@app.route('/api/settings/init', methods=['POST'])
@login_required
def init_settings():
    """Создает запись настроек если её нет"""
    try:
        user_id = session['user_id']
        
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Проверяем существование записи
            cursor.execute("SELECT id FROM settings WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                # Создаем запись с настройками по умолчанию
                cursor.execute("""
                INSERT INTO settings (
                    user_id, sync_api_key, proxy, use_proxy,
                    auto_refresh_campaigns, auto_refresh_adsets,
                    telegram_bot_token, telegram_chat_id,
                    keitaro_api_key, keitaro_domain, keitaro_range_days
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, '', '', 1, 1, 1, '', '', 
                    '', 'uniaffnu.com', 1
                ))
                conn.commit()
                return jsonify({'success': True, 'message': 'Настройки инициализированы'})
            else:
                return jsonify({'success': True, 'message': 'Настройки уже существуют'})
                
    except Exception as e:
        logger.error(f"Ошибка инициализации настроек: {e}")
        return jsonify({'success': False, 'error': str(e)})
if __name__ == '__main__':
    # Инициализируем базу данных
    init_db()
    
    # Создаем тестового пользователя, если его нет
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем существование пользователя admin
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        admin_exists = cursor.fetchone()
    except Exception as e:
        print(f"Ошибка при инициализации тестового пользователя: {e}")
    
    # Запускаем приложение ОДИН раз
    app.run(host='0.0.0.0', port=8001, debug=False, threaded=True)