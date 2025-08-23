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
                      create_user, get_db_connection, get_user_adsets,
                      get_user_campaigns, get_user_geo_config,
                      get_user_geo_rules, get_user_settings, init_db,
                      update_campaign_stats, update_user_adset_budget,
                      update_user_adset_status, update_user_campaign_status,
                      update_user_settings)

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
from typing import Dict, Optional

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
def fetch_keitaro_report(api_key, domain, interval="today", group_by="sub_id_9"):
    """
    Получает отчет из Keitaro с расчетом лидов по формуле Spend / CPA.
    """
    logger = logging.getLogger(__name__)
    url = f"https://{domain}/admin_api/v1/report/build"
    headers = {"Api-Key": api_key, "Content-Type": "application/json"}

    metrics = ["campaign_unique_clicks", "ucpc", "conversions", "sales", "cost", "cpa", "cpc"]
    limit = 250
    offset = 0
    all_rows = []

    try:
        while True:
            payload = {
                "range": {"interval": interval, "timezone": "Europe/Moscow"},
                "metrics": metrics,
                "columns": [],
                "grouping": [group_by],
                "filters": [],
                "sort": [{"name": "ucpc", "order": "desc"}],
                "limit": limit,
                "offset": offset
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            report = response.json()

            if not report or "rows" not in report:
                logger.warning("Пустой или некорректный ответ от Keitaro")
                break

            rows = report.get("rows", [])
            
            # Добавляем расчет лидов для каждой строки
            for row in rows:
                cost = float(row.get("cost", 0) or 0)
                cpa = float(row.get("cpa", 0) or 0)
                
                # Рассчитываем лиды по формуле Spend / CPA
                calculated_leads = 0
                if cpa > 0 and cost > 0:
                    calculated_leads = round(cost / cpa)
                
                row['calculated_leads'] = calculated_leads
                row['leads'] = calculated_leads  # Добавляем в основное поле
            
            all_rows.extend(rows)

            if len(rows) < limit:
                break
            offset += limit

        # Подсчёт итогов
        total_cost = total_profit = total_cpa = total_cpc = total_leads = 0.0
        cpa_count = cpc_count = 0

        for row in all_rows:
            cost = float(row.get("cost", 0) or 0)
            profit = float(row.get("profit_confirmed", 0) or 0)
            cpa = float(row.get("cpa", 0) or 0)
            cpc = float(row.get("cpc", 0) or 0)
            leads = row.get('calculated_leads', 0)

            total_cost += cost
            total_profit += profit
            total_leads += leads
            
            if cpa > 0:
                total_cpa += cpa
                cpa_count += 1
            
            if cpc > 0:
                total_cpc += cpc
                cpc_count += 1

        avg_cpa = total_cpa / cpa_count if cpa_count > 0 else 0
        avg_cpc = total_cpc / cpc_count if cpc_count > 0 else 0
        total_roi = (total_profit / total_cost * 100) if total_cost > 0 else 0

        return {
            "rows": all_rows,
            "totals": {
                "cost": total_cost,
                "profit": total_profit,
                "leads": total_leads,
                "average_cpa": avg_cpa,
                "average_cpc": avg_cpc,
                "total_roi": total_roi
            }
        }

    except requests.HTTPError as e:
        logger.error(f"HTTP ошибка Keitaro: {e.response.status_code} {e.response.text}")
    except requests.RequestException as e:
        logger.error(f"Ошибка запроса Keitaro: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")

    return {"rows": [], "totals": {}}
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
    with get_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        
        # Список администраторов - добавьте нужные username
        admin_users = ['admin', 'boss', 'administrator', 'root']
        return user and user['username'].lower() in admin_users
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


def get_reserve_tokens(user_id, king=None):
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

def get_keitaro_api_key(user_id: int) -> str:
    """Получает API ключ Keitaro из настроек пользователя"""
    try:
        settings = get_user_settings(user_id)
        return settings.get('keitaro_api_key', '')
    except Exception as e:
        logger.error(f"Ошибка получения Keitaro API key: {e}")
        return ""

def fetch_facebook_campaigns(account_id, access_token, fields=None):
    """Получает кампании из Facebook API с расширенными полями"""
    if fields is None:
        fields = "id,name,status,effective_status,daily_budget,objective,start_time,stop_time"
    
    try:
        # Убедимся, что account_id не содержит 'act_' префикс
        clean_account_id = account_id.replace('act_', '')
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}/campaigns"
        
        params = {
            "fields": fields,
            "access_token": access_token,
            "limit": 100
        }
        
        all_campaigns = []
        
        while url:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            campaigns = data.get('data', [])
            all_campaigns.extend(campaigns)
            
            # Обрабатываем пагинацию
            next_url = data.get('paging', {}).get('next')
            url = next_url
            # Очищаем params для последующих запросов
            params = {}
        
        logger.info(f"Получено {len(all_campaigns)} кампаний для аккаунта {clean_account_id}")
        return all_campaigns
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка получения кампаний: {e}")
        return []
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении кампаний: {e}")
        return []
def fetch_facebook_adsets(account_id, access_token, fields=None):
    """Получает адсеты из Facebook API"""
    if fields is None:
        fields = "id,name,campaign_id,daily_budget,status,effective_status"
    
    try:
        clean_account_id = account_id.replace('act_', '')
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}/adsets"
        
        params = {
            "fields": fields,
            "access_token": access_token,
            "limit": 100
        }
        
        all_adsets = []
        
        while url:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            adsets = data.get('data', [])
            all_adsets.extend(adsets)
            
            # Обрабатываем пагинацию
            next_url = data.get('paging', {}).get('next')
            url = next_url
            # Очищаем params для последующих запросов
            params = {}
        
        logger.info(f"Получено {len(all_adsets)} адсетов для аккаунта {clean_account_id}")
        return all_adsets
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка получения адсетов: {e}")
        return []
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении адсетов: {e}")
        return []
def fetch_facebook_adsets(account_id, access_token, fields=None):
    """Получает адсеты из Facebook API с актуальными статусами"""
    if fields is None:
        fields = "id,name,campaign_id,daily_budget,status,effective_status"
    
    try:
        clean_account_id = account_id.replace('act_', '')
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}/adsets"
        
        params = {
            "fields": fields,
            "access_token": access_token,
            "limit": 100,
        }
        
        all_adsets = []
        
        while url:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            adsets = data.get('data', [])
            all_adsets.extend(adsets)
            
            # Обрабатываем пагинацию
            next_url = data.get('paging', {}).get('next')
            url = next_url
            params = {}
        
        logger.info(f"Получено {len(all_adsets)} адсетов для аккаунта {clean_account_id}")
        return all_adsets
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка получения адсетов: {e}")
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
auto_control_threads = {}
auto_control_lock = threading.Lock()



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
# Добавьте этот код в app.py
# app.py - Update the geo_rules endpoint

@app.route('/admin/limits')
@login_required
def admin_limits():
    """Скрытая админ панель с лимитами аккаунтов"""
    # Проверяем права доступа
    if not is_admin_user(session['user_id']):
        return render_template('access_denied.html')
    
    return render_template('admin_panel.html')

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
        user_id = session['refresh_adsets_with_keitaro()']
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
        
        if result.get('success') or result.get('id') == adset_id:
            return True
        else:
            logger.error(f"Ошибка обновления бюджета: {result}")
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

@app.route('/api/adset/set_budget', methods=['POST'])
@login_required
def set_adset_budget_api():
    """Ручное установление бюджета адсета"""
    try:
        user_id = session['user_id']
        data = request.json
        
        adset_id = data.get('adset_id')
        name = data.get('name')
        token = data.get('token')
        new_budget = float(data.get('budget', 0))
        
        # Обновляем через Facebook API
        success = update_adset_budget_facebook(adset_id, new_budget, token)
        
        if success:
            # Обновляем в базе данных
            update_user_adset_budget(user_id, adset_id, new_budget)
            
            msg = f"💰 Бюджет установлен: {name} (${new_budget:.2f})"
            logger.info(msg)
            send_telegram_message(msg, user_id=user_id)
            
            return jsonify({'success': True, 'message': msg})
        else:
            return jsonify({'success': False, 'error': 'Ошибка установки бюджета'})
            
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
    """Получает insights для адсетов включая CPC из Facebook"""
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
                        'cpc': float(insight.get('cpc', 0)),  # CPC из Facebook
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
@app.route('/api/save_and_sync', methods=['POST'])
@login_required
def save_and_sync():
    try:
        logger.info("=== НАЧАЛО СИНХРОНИЗАЦИИ ===")
        user_id = session['user_id']
        accounts_data = request.json.get('accounts', [])
        if not accounts_data:
            return jsonify({'success': False, 'error': 'Нет данных для сохранения'})
        facebook_cpc_data = {}
        for account_data in accounts_data:
            account_id = account_data.get('account_id', '').replace('act_', '')
            token = account_data.get('token', '')
            
            if account_id and token:
                try:
                    cpc_data = fetch_facebook_cpc_data(account_id, token)
                    facebook_cpc_data[account_id] = cpc_data
                except Exception as e:
                    logger.error(f"Ошибка получения CPC для аккаунта {account_id}: {e}")

        # Получаем известные GEO коды
        geo_rules = get_user_geo_rules(user_id)
        known_geos = list(geo_rules.keys()) if geo_rules else []
        
        # Настройки Keitaro
        settings = get_user_settings(user_id)
        keitaro_api_key = settings.get('keitaro_api_key')
        keitaro_domain = settings.get('keitaro_domain', 'uniaffnu.com')

        # Загружаем данные из Keitaro (без CPC)
        keitaro_data = {}
        if keitaro_api_key:
            report = fetch_keitaro_report(keitaro_api_key, keitaro_domain)
            for row in report.get('rows', []):
                cost = float(row.get('cost', 0) or 0)
                cpa = float(row.get('cpa', 0) or 0)
                
                # Рассчитываем лиды по формуле Spend / CPA
                leads = 0
                if cpa > 0 and cost > 0:
                    leads = round(cost / cpa)
                
                record = {
                    'spend': cost,
                    'leads': leads,  # Используем рассчитанные лиды
                    'cpa': cpa,
                    'ucpc': float(row.get('ucpc', 0) or 0),
                }
                key_id = str(row.get('sub_id_9') or "").strip()
                key_name = str(row.get('campaign') or "").strip()
                if key_id:
                    keitaro_data[key_id] = record
                if key_name:
                    keitaro_data[key_name] = record
            logger.info(f"Обработано {len(keitaro_data)} записей из Keitaro")

        # Получаем CPC из Facebook для каждого аккаунта
        facebook_cpc_data = {}
        for account_data in accounts_data:
            account_id = account_data.get('account_id', '').replace('act_', '')
            token = account_data.get('token', '')
            
            if account_id and token:
                try:
                    insights = fetch_facebook_adsets_insights(account_id, token)
                    facebook_cpc_data[account_id] = insights
                    logger.info(f"Получено CPC данных для аккаунта {account_id}: {len(insights)} записей")
                except Exception as e:
                    logger.error(f"Ошибка получения CPC для аккаунта {account_id}: {e}")
        # Функция для разделения и очистки строки
        def split_clean(s: str) -> list[str]:
            """Разделяет строку на части и очищает их"""
            if not s:
                return []
            # Удаляем специальные символы и разделяем по пробелам, дефисам, подчеркиваниям
            clean_str = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(s))
            parts = re.split(r'[\s\-_]+', clean_str.lower())
            # Убираем пустые строки
            return [p for p in parts if p]

        # Функция поиска статистики
        def find_stats(fb_id=None, fb_name=None, fb_parent_name=None):
            """Поиск данных Keitaro с расчетом лидов"""
            weak_words = {"monah", "test", "copy", "vst"}

            def score_match(fb_parts, key_parts):
                common = set(fb_parts) & set(key_parts)
                if not common:
                    return 0, common
                # слабые слова не считаем
                strong_common = {w for w in common if w not in weak_words}
                return len(strong_common), common

            # 1. По ID
            if fb_id and fb_id in keitaro_data:
                logger.debug(f"[MATCH BY ID] FB {fb_id} → Keitaro {fb_id}")
                return keitaro_data[fb_id]

            # Составляем список кандидатов
            candidates = []
            fb_sources = [(fb_name, "ADSET"), (fb_parent_name, "CAMPAIGN")]
            for fb_source, label in fb_sources:
                if not fb_source:
                    continue
                fb_parts = split_clean(fb_source)
                for key, stats in keitaro_data.items():
                    key_parts = split_clean(key)
                    score, common = score_match(fb_parts, key_parts)
                    if score > 0:
                        candidates.append((score, key, stats, label, common))

            if not candidates:
                logger.debug(f"[NO MATCH] FB(id={fb_id}, name={fb_name}, parent={fb_parent_name})")
                return {'spend': 0, 'leads': 0, 'cpa': 0, 'ucpc': 0}

            # Берем лучший матч
            candidates.sort(key=lambda x: x[0], reverse=True)
            score, key, stats, label, common = candidates[0]

            if score >= 2:
                logger.debug(f"[STRONG MATCH by {label}] FB '{fb_name or fb_parent_name}' → Keitaro '{key}' (общие: {common})")
                return stats
            else:
                logger.debug(f"[WEAK MATCH IGNORED] FB '{fb_name or fb_parent_name}' → Keitaro '{key}' (общие: {common})")
                return {'spend': 0, 'leads': 0, 'cpa': 0, 'ucpc': 0}

        saved_accounts = total_campaigns = total_adsets = keitaro_updated = 0

        for acc in accounts_data:
            account_id = acc.get('account_id', '').replace('act_', '')
            token = acc.get('token', '')
            if not account_id or not token:
                continue

            # Проверка токена
            try:
                res = requests.get(
                    f"https://graph.facebook.com/v18.0/act_{account_id}",
                    params={'access_token': token, 'fields': 'id,name,account_status'}, 
                    timeout=30
                ).json()
                
                if 'error' in res:
                    logger.warning(f"Неверный токен для {account_id}: {res['error']['message']}")
                    continue

                # Кампании
                campaigns = fetch_facebook_campaigns(account_id, token)
                campaign_names = {c['id']: c['name'] for c in campaigns}
                
                for camp in campaigns:
                    stats = find_stats(fb_id=camp['id'], fb_name=camp.get('name'))
                    add_user_campaign(user_id, {
                        'king': 'Facebook',
                        'name': camp.get('name', ''),
                        'status': camp.get('status', 'PAUSED'),
                        'campaign_id': camp['id'],
                        'account_id': account_id,
                        'token': token
                    })
                    update_campaign_stats(user_id, camp['id'], **stats)
                    keitaro_updated += 1
                    total_campaigns += 1

                # Адсеты
                adsets = fetch_facebook_adsets(account_id, token)
                for ad in adsets:
                    camp_id = ad.get('campaign_id')
                    ad_name = ad.get('name', '')
                    
                    # Определяем GEO из названия адсета
                    geo = extract_geo_from_name(ad_name, known_geos)
                    
                    stats = find_stats(
                        fb_id=ad.get('id'),
                        fb_name=ad_name,
                        fb_parent_name=campaign_names.get(camp_id)
                    )
                    budget = float(ad.get('daily_budget', 0)) / 100 if ad.get('daily_budget') else 0
                    cpc_info = facebook_cpc_data.get(account_id, {}).get(ad.get('id', ''), {})
                    add_user_adset(user_id, {
                        'name': ad_name,
                        'adset_id': ad.get('id', ''),
                        'campaign_id': camp_id,
                        'status': ad.get('status', 'PAUSED'),
                        'account_id': account_id,
                        'token': token,
                        'budget': budget,
                        'geo': geo,
                        'ucpc': stats.get('ucpc', 0),
                        'cpc': cpc_info.get('cpc', 0),  # Добавьте CPC из Facebook insights если доступно
                        'spend': stats.get('spend', 0),
                        'cpa': stats.get('cpa', 0),
                        'leads': stats.get('leads', 0),
                        'king': 'Facebook',
                        'effective_status': ad.get('effective_status', ''),
                        'ad_name': ad_name,
                        'manual_pause': 0
                    })
                    total_adsets += 1

                saved_accounts += 1

            except requests.exceptions.RequestException as e:
                logger.warning(f"Ошибка сети для аккаунта {account_id}: {e}")
                continue

        return jsonify({
            'success': True,
            'saved_accounts': saved_accounts,
            'total_campaigns': total_campaigns,
            'total_adsets': total_adsets,
            'keitaro_updated': keitaro_updated,
            'keitaro_records': len(keitaro_data)
        })

    except Exception as e:
        logger.error(f"Критическая ошибка синхронизации: {e}")
        return jsonify({'success': False, 'error': str(e)})

def normalize_campaign_name(name):
    """Нормализует название кампании для поиска (без regex)"""
    if not name:
        return ""
    
    # Приводим к нижнему регистру
    normalized = name.lower()
    
    # Простая замена специальных символов на пробелы
    for char in '!@#$%^&*()_+-=[]{}|;:,.<>?/~`':
        normalized = normalized.replace(char, ' ')
    
    # Удаляем multiple spaces (простой способ)
    while '  ' in normalized:
        normalized = normalized.replace('  ', ' ')
    
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
        return jsonify({
            'success': True,
            'data': adsets
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

@app.route('/api/adset/budget', methods=['POST'])
@login_required
def set_adset_budget():
    data = request.json
    adset_id = data.get('adset_id')
    name = data.get('name')
    dollars = float(data.get('budget'))
    
    try:
        update_user_adset_budget(session['user_id'], adset_id, dollars)
        logger.info(f"💰 Бюджет ${dollars:.2f} установлен для «{name}»")
        send_telegram_message(f"💰 Бюджет ${dollars:.2f} установлен для «{name}»")
        return jsonify({'success': True, 'new_budget': f"{dollars:.2f} $"})
    except Exception as e:
        logger.error(f"Ошибка установки бюджета для «{name}»: {e}")
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


def apply_auto_budget_rules(user_id, adset):
    """Применяет правила авто-бюджета к адсету"""
    try:
        current_budget = float(adset.get('budget', 0))
        spend = float(adset.get('spend', 0))
        leads = int(adset.get('leads', 0))
        cpa = float(adset.get('cpa', 0))
        ucpc = float(adset.get('ucpc', 0))
        
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
        
    except Exception as e:
        logger.error(f"Ошибка применения авто-бюджета: {e}")
        return False
def apply_auto_budget_rules(user_id, adset):
    """Применяет правила авто-бюджета к адсету"""
    current_budget = float(adset.get('budget', 0))
    spend = float(adset.get('spend', 0))
    leads = int(adset.get('leads', 0))
    cpa = float(adset.get('cpa', 0))
    ucpc = float(adset.get('ucpc', 0))
    
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
# Добавьте эти функции в app.py


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
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)