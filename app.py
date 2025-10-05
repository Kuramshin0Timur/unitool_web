import json
import logging
import os
import re
import sqlite3
import threading
from functools import wraps
from logging.handlers import RotatingFileHandler

import requests
from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   session, url_for)
from fuzzywuzzy import fuzz, process

from backend.account import get_all_users, get_user_accounts_stats
from backend.adsets import (add_user_adset, fetch_facebook_adsets,
                            get_user_adsets, refresh_adsets_internal, update_adset_exclusion_status,
                            update_user_adset_status)
from backend.autocontrol import (auto_control, auto_refresh_lock,
                                 auto_refresh_timers, get_combined_auto_status,
                                 start_auto_control_and_refresh,
                                 stop_auto_control_and_refresh)
from backend.budget import get_adset_budget_settings
from backend.campaign import (add_user_campaign, fetch_facebook_campaigns,
                              get_user_campaigns, update_campaign_stats,
                              update_user_campaign_status)
from backend.geo_config import extract_geo_from_name, get_user_geo_rules
from backend.keitaro import fetch_keitaro_report, sync_keitaro
from backend.reserve_tokens import (add_account_to_reserve_token,
                                    add_reserve_token,
                                    delete_reserve_token_complete,
                                    get_reserve_token_accounts)
from backend.reserve_tokens import get_reserve_tokens
from backend.reserve_tokens import \
    get_reserve_tokens as get_reserve_tokens_full
from backend.reserve_tokens import (normalize_account_id, normalize_token,
                                    remove_account_from_reserve_token,
                                    replace_token_everywhere,
                                    update_reserve_token_king)
from backend.setting import get_user_settings, update_user_settings
from backend.telegram import send_telegram_message
from database import (authenticate_user, create_user, get_db_connection,
                      init_db, lock)

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
from typing import Any, Dict, List, Optional, Set, Tuple


def login_required(f):
    """Декоратор для проверки аутентификации пользователя"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function



@app.route('/api/adsets/update_geo', methods=['POST'])
@login_required
def update_adsets_geo():
    """Принудительно обновляет GEO для всех адсетов"""
    try:
        user_id = session['user_id']
        
        # Получаем правила GEO
        geo_rules = get_user_geo_rules(user_id)
        known_geos = list(geo_rules.keys()) if geo_rules else []
        
        # Добавляем стандартные GEO коды
        standard_geos = ['US', 'UK', 'CA', 'AU', 'DE', 'FR', 'ES', 'IT', 'RU', 
                        'JP', 'KR', 'CN', 'IN', 'MX', 'BR', 'AR', 'CO', 'PE',
                        'CL', 'ZA', 'NG', 'EG', 'SA', 'AE', 'TR', 'PL', 'NL',
                        'SE', 'NO', 'DK', 'FI', 'BE', 'CH', 'AT', 'MY', 'SG',
                        'VN', 'TH', 'PH', 'ID']
        
        known_geos = list(set(known_geos + standard_geos))
        
        # Получаем все адсеты
        adsets = get_user_adsets(user_id)
        updated_count = 0
        
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            for adset in adsets:
                adset_name = adset.get('name', '')
                adset_id = adset.get('adset_id', '')
                
                # Определяем GEO
                geo = extract_geo_from_name(adset_name, known_geos)
                
                # Обновляем в базе
                cursor.execute("""
                    UPDATE adsets SET geo = ? 
                    WHERE user_id = ? AND adset_id = ?
                """, (geo, user_id, adset_id))
                
                if cursor.rowcount > 0:
                    updated_count += 1
            
            conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Обновлено GEO для {updated_count} адсетов',
            'updated_count': updated_count
        })
        
    except Exception as e:
        logger.error(f"Ошибка обновления GEO адсетов: {e}")
        return jsonify({'success': False, 'error': str(e)})

import traceback


@app.route('/api/auto_renumber_kings', methods=['POST'])
@login_required
def auto_renumber_kings():
    """
    Перенумеровывает KING так, чтобы у пользователя
    они были уникальны (King_1, King_2, ...).
    Нормализует токены (\n, \r, пробелы).
    """
    user_id = session['user_id']
    logs = []

    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()

            # получаем уникальные нормализованные токены
            cursor.execute("""
                SELECT DISTINCT TRIM(REPLACE(REPLACE(token, char(10), ''), char(13), '')) as token_norm
                FROM reserve_tokens
                WHERE user_id = ?
                ORDER BY token_norm
            """, (user_id,))
            tokens = [row['token_norm'] for row in cursor.fetchall() if row['token_norm']]
            logs.append(f"Найдено {len(tokens)} токенов")

            if not tokens:
                return jsonify({'success': False, 'error': 'Нет токенов', 'logs': logs})

            counter = 1
            changes = []

            for token in tokens:
                new_king = f"King_{counter}"
                logs.append(f"→ Обновляем token={token} → {new_king}")

                for table in ["reserve_tokens", "reserve_token_accounts", "campaigns", "adsets"]:
                    cursor.execute(f"""
                        UPDATE {table}
                        SET king = ?
                        WHERE user_id = ?
                          AND TRIM(REPLACE(REPLACE(token, char(10), ''), char(13), '')) = ?
                    """, (new_king, user_id, token))
                    updated = cursor.rowcount
                    changes.append(f"{table}: {updated} строк обновлено")
                    logs.append(f"{table}: {updated} строк обновлено")

                counter += 1

            conn.commit()

            # финальный снимок
            cursor.execute("""
                SELECT king, token, account_id 
                FROM reserve_token_accounts
                WHERE user_id = ?
                ORDER BY king
            """, (user_id,))
            current_state = [dict(row) for row in cursor.fetchall()]

            return jsonify({
                'success': True,
                'message': 'KING перенумерованы',
                'details': changes,
                'logs': logs,
                'current_state': current_state
            })

    except Exception as e:
        tb = traceback.format_exc()
        logs.append(f"Ошибка авто-ренумерации: {e}")
        return jsonify({'success': False, 'error': str(e), 'traceback': tb, 'logs': logs}), 500

@app.route('/api/auto_populate_reserve_tokens', methods=['POST'])
@login_required
def auto_populate_reserve_tokens():
    user_id = session['user_id']
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
                account_id = normalize_account_id(account['account_id'])
                token = normalize_token(account['token'])
                king = auto_determine_king(token)
                # добавляем токен и аккаунт через backend функции
                add_reserve_token(user_id, king, token)
                if account_id:
                    add_account_to_reserve_token(user_id, king, token, account_id)
                    added_count += 1
            return jsonify({'success': True, 'message': f'Добавлено {added_count} резервных аккаунтов'})
    except Exception as e:
        logger.error(f"auto_populate_reserve_tokens error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/combined_tokens_table', methods=['GET'])
@login_required
def get_combined_tokens_data():
    """Возвращает совмещенные данные: основные аккаунты + резервные токены"""
    user_id = session['user_id']
    
    try:
        # Получаем основные аккаунты из campaigns
        main_accounts = []
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Основные аккаунты из campaigns с актуальным king
            cursor.execute("""
                SELECT DISTINCT c.account_id, c.token, c.king 
                FROM campaigns c
                WHERE c.user_id = ? AND c.account_id IS NOT NULL AND c.token IS NOT NULL
                AND c.account_id != '' AND c.token != ''
                AND c.king IS NOT NULL AND c.king != ''
            """, (user_id,))
            
            for row in cursor.fetchall():
                king = row['king']
                # Если king пустой, используем автоматическое определение
                if not king or king == 'N/A':
                    king = auto_determine_king(row['token'])
                
                # Проверяем лимиты для основного аккаунта
                limits_info = get_account_limits_info(row['account_id'], row['token'])
                
                main_accounts.append({
                    'king': king,
                    'token': row['token'],
                    'account_id': row['account_id'],
                    'type': 'main',
                    'source': 'campaigns',
                    'limits_info': limits_info
                })
        
        # Получаем резервные токены
        reserve_tokens = get_reserve_tokens_table(user_id)
        
        # Формируем совмещенную структуру
        combined_data = {}
        
        # Добавляем основные аккаунты
        for account in main_accounts:
            king = account['king']
            if not king:  # Защита от пустого king
                king = 'Facebook_Default'
                
            if king not in combined_data:
                combined_data[king] = {}
            
            token = account['token']
            if token not in combined_data[king]:
                combined_data[king][token] = {
                    'token': token,
                    'accounts': [],
                    'type': 'main',
                    'requests_limit': account['limits_info'].get('requests_limit', 100),
                    'requests_today': account['limits_info'].get('requests_today', 0),
                    'requests_usage_percent': account['limits_info'].get('requests_usage_percent', 0)
                }
            
            combined_data[king][token]['accounts'].append({
                'account_id': account['account_id'],
                'type': 'main',
                'name': account['limits_info'].get('name', 'N/A'),
                'status': account['limits_info'].get('status', 'UNKNOWN'),
                'spend_cap': account['limits_info'].get('spend_cap', 0),
                'amount_spent': account['limits_info'].get('spend', 0),
                'balance': account['limits_info'].get('balance', 0),
                'requests_limit': account['limits_info'].get('requests_limit', 100),
                'requests_today': account['limits_info'].get('requests_today', 0),
                'requests_usage_percent': account['limits_info'].get('requests_usage_percent', 0)
            })
        
        # Добавляем резервные токены
        for king, tokens in reserve_tokens.items():
            if not king:  # Защита от пустого king
                king = 'Facebook_Default'
                
            if king not in combined_data:
                combined_data[king] = {}
            
            for token_info in tokens:
                token = token_info['token']
                if token not in combined_data[king]:
                    combined_data[king][token] = {
                        'token': token,
                        'accounts': [],
                        'type': 'reserve',
                        'requests_limit': token_info.get('requests_limit', 100),
                        'requests_today': token_info.get('requests_today', 0),
                        'requests_usage_percent': token_info.get('requests_usage_percent', 0)
                    }
                
                # Добавляем аккаунты резервных токенов
                for account in token_info.get('accounts', []):
                    combined_data[king][token]['accounts'].append({
                        'account_id': account['account_id'],
                        'type': 'reserve',
                        'name': account.get('name', 'N/A'),
                        'status': account.get('status', 'UNKNOWN'),
                        'spend_cap': account.get('spend_cap', 0),
                        'amount_spent': account.get('amount_spent', 0),
                        'balance': account.get('balance', 0),
                        'requests_limit': account.get('requests_limit', 100),
                        'requests_today': account.get('requests_today', 0),
                        'requests_usage_percent': account.get('requests_usage_percent', 0)
                    })
        
        # Преобразуем в нужный формат
        result = {}
        for king, tokens in combined_data.items():
            result[king] = list(tokens.values())
        
        return jsonify({
            'success': True,
            'tokens': result
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения совмещенных токенов: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/replace_token', methods=['POST'])
@login_required
def replace_token():
    """Заменяет токен во всех таблицах (atomic): reserve_tokens, reserve_token_accounts, campaigns, adsets"""
    user_id = session['user_id']
    data = request.json or {}

    old_token = normalize_token(data.get('old_token') or data.get('oldToken'))
    new_token = normalize_token(data.get('new_token') or data.get('newToken') or '')
    king = data.get('king') or data.get('KING') or ''
    account_ids = data.get('account_ids', None)

    if not old_token or not king:
        return jsonify({'success': False, 'error': 'Не указаны старый токен или KING'})

    result = replace_token_everywhere(user_id, old_token, new_token, king, account_ids)
    if 'error' in result:
        return jsonify({'success': False, 'error': result['error']})

    return jsonify({'success': True, 'details': result})

@app.route('/api/update_king', methods=['POST'])
@login_required
def update_king():
    user_id = session['user_id']
    data = request.json or {}
    current_king = data.get('currentKing') or data.get('current_king')
    new_king = data.get('newKing') or data.get('new_king')
    token = normalize_token(data.get('token') or data.get('currentToken'))

    if not all([current_king, new_king, token]):
        return jsonify({'success': False, 'error': 'Не указаны все параметры'})

    try:
        ok = update_reserve_token_king(user_id, current_king, new_king, token)
        if ok:
            return jsonify({'success': True, 'message': f'KING обновлен с "{current_king}" на "{new_king}"'})
        else:
            return jsonify({'success': False, 'error': 'Ошибка при обновлении KING'})
    except Exception as e:
        logger.error(f"Ошибка update_king endpoint: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update_token', methods=['POST'])
@login_required
def update_token():
    """Обновляет токен в reserve_tokens и reserve_token_accounts (нормализует)"""
    user_id = session['user_id']
    data = request.json or {}

    king = data.get('king')
    current_token = normalize_token(data.get('currentToken') or data.get('current_token'))
    new_token = normalize_token(data.get('newToken') or data.get('new_token'))

    if not all([king, current_token, new_token]):
        return jsonify({'success': False, 'error': 'Не указаны все параметры'})

    try:
        # Используем функции из backend (add/update)
        from backend.reserve_tokens import replace_token_everywhere
        res = replace_token_everywhere(user_id, current_token, new_token, king, None)
        if 'error' in res:
            return jsonify({'success': False, 'error': res['error']})
        return jsonify({'success': True, 'message': 'Токен успешно обновлен', 'details': res})
    except Exception as e:
        logger.error(f"Ошибка update_token: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update_token_complete', methods=['POST'])
@login_required
def update_token_complete():
    """Полное обновление токена с изменением KING и обновлением основных таблиц"""
    user_id = session['user_id']
    data = request.json

    # Приводим все значения к строке
    old_king = str(data.get('oldKing')) if data.get('oldKing') is not None else None
    new_king = str(data.get('newKing')) if data.get('newKing') else None
    old_token = str(data.get('oldToken')) if data.get('oldToken') else None
    new_token = str(data.get('newToken')) if data.get('newToken') else None
    account_ids = data.get('account_ids', [])

    if not all([old_king, old_token]):
        return jsonify({'success': False, 'error': 'Не указаны обязательные параметры'})

    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()

            changes = []
            final_king = old_king
            final_token = old_token

            # --- 1. Смена KING ---
            if new_king and new_king != old_king:
                # Обновляем во всех таблицах
                tables_to_update = ["reserve_tokens", "reserve_token_accounts", "campaigns", "adsets"]
                for table in tables_to_update:
                    try:
                        cursor.execute(f"""
                            UPDATE {table}
                            SET king = ?
                            WHERE user_id = ? AND king = ? AND token = ?
                        """, (new_king, user_id, old_king, old_token))
                        updated_rows = cursor.rowcount
                        logger.info(f"Обновлено {updated_rows} строк в таблице {table}")
                    except Exception as e:
                        logger.error(f"Ошибка обновления таблицы {table}: {e}")
                        # Продолжаем выполнение для других таблиц

                changes.append(f'KING изменён на "{new_king}"')
                final_king = new_king

            # --- 2. Смена токена ---
            if new_token and new_token != old_token:
                # Обновляем во всех таблицах
                tables_to_update = ["reserve_tokens", "reserve_token_accounts", "campaigns", "adsets"]
                for table in tables_to_update:
                    try:
                        cursor.execute(f"""
                            UPDATE {table}
                            SET token = ?
                            WHERE user_id = ? AND king = ? AND token = ?
                        """, (new_token, user_id, final_king, old_token))
                        updated_rows = cursor.rowcount
                        logger.info(f"Обновлено {updated_rows} строк в таблице {table}")
                    except Exception as e:
                        logger.error(f"Ошибка обновления таблицы {table}: {e}")
                        # Продолжаем выполнение для других таблиц

                changes.append('токен изменён')
                final_token = new_token

            # --- 3. Смена аккаунтов ---
            if account_ids is not None:
                # Удаляем старые аккаунты для этого токена
                cursor.execute("""
                    DELETE FROM reserve_token_accounts 
                    WHERE user_id = ? AND king = ? AND token = ?
                """, (user_id, final_king, final_token))

                # Добавляем новые аккаунты
                added_count = 0
                for account_id in account_ids:
                    if account_id and account_id.strip():
                        clean_account_id = account_id.strip().replace('act_', '')
                        if clean_account_id:  # Проверяем, что не пустая строка
                            try:
                                cursor.execute("""
                                    INSERT OR IGNORE INTO reserve_token_accounts 
                                    (user_id, king, token, account_id) 
                                    VALUES (?, ?, ?, ?)
                                """, (user_id, final_king, final_token, clean_account_id))
                                if cursor.rowcount > 0:
                                    added_count += 1
                            except Exception as e:
                                logger.warning(f"Пропущен аккаунт {account_id}: {e}")
                                continue

                changes.append(f'аккаунтов: {added_count} добавлено')

            conn.commit()

            message = 'Данные сохранены' + (f' ({", ".join(changes)})' if changes else '')
            return jsonify({'success': True, 'message': message})

    except Exception as e:
        logger.error(f"Ошибка полного обновления токена: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/user/reserve_tokens/bulk', methods=['POST'])
@login_required
def add_bulk_reserve_tokens():
    """Добавляет несколько токенов с одним KING"""
    user_id = session['user_id']
    data = request.json
    
    king = data.get('king')
    tokens = data.get('tokens', [])
    account_ids = data.get('account_ids', [])
    
    if not king or not tokens:
        return jsonify({'success': False, 'error': 'Не указан KING или токены'})
    
    try:
        added_count = 0
        error_count = 0
        error_messages = []
        
        for token in tokens:
            token = token.strip()
            if not token:
                continue
                
            # Проверяем, не существует ли уже токен
            if check_reserve_token_exists(user_id, king, token):
                error_count += 1
                error_messages.append(f'Токен уже существует: {token[:20]}...')
                continue
            
            if add_reserve_token(user_id, king, token):
                # Добавляем аккаунты если они указаны
                for account_id in account_ids:
                    if account_id:
                        add_account_to_reserve_token(user_id, king, token, account_id)
                added_count += 1
            else:
                error_count += 1
        
        message = f'Добавлено {added_count} токенов'
        if error_count > 0:
            message += f', ошибок: {error_count}'
        
        return jsonify({
            'success': True,
            'message': message,
            'added_count': added_count,
            'error_count': error_count,
            'errors': error_messages[:5]  # Первые 5 ошибок
        })
        
    except Exception as e:
        logger.error(f"Ошибка массового добавления токенов: {e}")
        return jsonify({'success': False, 'error': str(e)})
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
        total_balance = sum(acc.get("balance", 0) for acc in checked_accounts)

        return jsonify({
            'success': True,
            'users_count': len(users),
            'raw_accounts_count': len(all_accounts_data),
            'valid_accounts_count': len(checked_accounts),
            'total_balance': total_balance,
            'users': users,
            'raw_accounts': all_accounts_data[:10],
            'valid_accounts': checked_accounts[:10]
        })

    except Exception as e:
        logger.error(f"Ошибка отладки аккаунтов: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reserve_tokens/check_account_limits', methods=['POST'])
@login_required
def check_reserve_token_account_limits():
    """Проверяет лимиты для конкретного аккаунта резервного токена"""
    user_id = session['user_id']
    data = request.json
    
    king = data.get('king')
    token = data.get('token')
    account_id = data.get('account_id')
    
    if not all([king, token, account_id]):
        return jsonify({'success': False, 'error': 'Не указан KING, токен или account_id'})
    
    try:
        # Проверяем лимиты через Facebook API
        limits_info = get_account_limits_info(account_id, token)
        
        if limits_info:
            # Обновляем информацию об аккаунте
            update_reserve_token_account_info(user_id, king, token, account_id, limits_info)
            
            return jsonify({
                'success': True,
                'message': f'Лимиты аккаунта {account_id} обновлены',
                'account_info': limits_info
            })
        else:
            return jsonify({'success': False, 'error': 'Не удалось получить информацию об аккаунте'})
        
    except Exception as e:
        logger.error(f"Ошибка проверки лимитов аккаунта: {e}")
        return jsonify({'success': False, 'error': str(e)})
def get_all_accounts_stats() -> List[Dict[str, Any]]:
    """Получает статистику по всем аккаунтам всех пользователей - исправленная версия"""
    try:
        users = get_all_users()
        all_accounts = []
        
        for user in users:
            user_id = user['id']
            try:
                # Получаем аккаунты пользователя из campaigns таблицы
                with get_db_connection(user_id) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT DISTINCT account_id, token 
                        FROM campaigns 
                        WHERE user_id = ? 
                        AND account_id IS NOT NULL 
                        AND account_id != 'N/A'
                        AND account_id != ''
                        AND token IS NOT NULL
                        AND token != 'N/A'
                        AND token != ''
                    """, (user_id,))
                    
                    accounts = cursor.fetchall()
                    
                    for account in accounts:
                        # Проверяем, что account_id начинается с 'act_' или состоит из цифр
                        account_id = account['account_id']
                        if not account_id.startswith('act_') and account_id.isdigit():
                            account_id = f"act_{account_id}"
                        
                        account_info = {
                            'user_id': user_id,
                            'username': user['username'],
                            'account_id': account_id,
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
def get_reserve_tokens(user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Получает резервные токены с аккаунтами - исправленная версия"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Проверяем существование таблицы reserve_tokens
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='reserve_tokens'
            """)
            table_exists = cursor.fetchone()
            
            if not table_exists:
                return {}
            
            # Получаем все токены с информацией о лимитах
            cursor.execute("""
                SELECT rt.king, rt.token, 
                       rta.account_id, rta.name, rta.status, rta.spend_cap, 
                       rta.amount_spent, rta.balance, rta.daily_limit, rta.remaining,
                       rta.requests_today, rta.requests_limit, rta.requests_usage_percent
                FROM reserve_tokens rt
                LEFT JOIN reserve_token_accounts rta ON rt.user_id = rta.user_id 
                    AND rt.king = rta.king AND rt.token = rta.token
                WHERE rt.user_id = ?
                ORDER BY rt.king, rt.token
            """, (user_id,))
            
            tokens_by_king = {}
            for row in cursor.fetchall():
                king = row['king']
                token = row['token']
                
                if king not in tokens_by_king:
                    tokens_by_king[king] = []
                
                # Находим токен в списке или создаем новый
                token_entry = None
                for entry in tokens_by_king[king]:
                    if entry['token'] == token:
                        token_entry = entry
                        break
                
                if not token_entry:
                    token_entry = {
                        'token': token,
                        'accounts': []
                    }
                    tokens_by_king[king].append(token_entry)
                
                # Добавляем аккаунт, если он есть
                if row['account_id']:
                    token_entry['accounts'].append({
                        'account_id': row['account_id'],
                        'name': row['name'],
                        'status': row['status'],
                        'spend_cap': row['spend_cap'],
                        'amount_spent': row['amount_spent'],
                        'balance': row['balance'],
                        'daily_limit': row['daily_limit'],
                        'remaining': row['remaining'],
                        'requests_today': row['requests_today'],
                        'requests_limit': row['requests_limit'],
                        'requests_usage_percent': row['requests_usage_percent']
                    })
            
            return tokens_by_king
            
    except Exception as e:
        logger.error(f"Ошибка получения резервных токенов: {e}")
        return {}
def get_reserve_tokens_table(user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Возвращает резервные токены в формате для таблицы - исправленная версия"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # ДЕБАГ 1: Проверяем данные в reserve_tokens
            cursor.execute("SELECT king, token, user_id FROM reserve_tokens")
            all_tokens = cursor.fetchall()
            logger.info(f"Все токены в таблице reserve_tokens: {[dict(t) for t in all_tokens]}")
            
            # ДЕБАГ 2: Токены текущего пользователя
            cursor.execute("SELECT king, token FROM reserve_tokens WHERE user_id = ?", (user_id,))
            user_tokens = cursor.fetchall()
            logger.info(f"Токены для user_id {user_id}: {[dict(t) for t in user_tokens]}")
            
            if not user_tokens:
                logger.info(f"Не найдено токенов для пользователя {user_id}")
                return {}
            
            # ДЕБАГ 3: Проверяем данные в reserve_token_accounts
            cursor.execute("SELECT king, token, account_id, user_id FROM reserve_token_accounts")
            all_accounts = cursor.fetchall()
            logger.info(f"Все аккаунты в таблице reserve_token_accounts: {[dict(a) for a in all_accounts]}")
            
            # ДЕБАГ 4: Выполняем JOIN запрос и проверяем результаты
            cursor.execute("""
                SELECT rt.king, rt.token, 
                       rta.account_id, rta.requests_limit, 
                       rta.requests_today, rta.requests_usage_percent
                FROM reserve_tokens rt
                LEFT JOIN reserve_token_accounts rta ON rt.user_id = rta.user_id 
                    AND rt.king = rta.king AND rt.token = rta.token
                WHERE rt.user_id = ?
                ORDER BY rt.king, rt.token
            """, (user_id,))
            
            rows = cursor.fetchall()
            logger.info(f"Результаты JOIN запроса для user_id {user_id}:")
            for row in rows:
                logger.info(f"  {dict(row)}")
            
            tokens_data = {}
            for row in rows:
                king = row['king']
                token = row['token']
                
                if king not in tokens_data:
                    tokens_data[king] = {}
                
                if token not in tokens_data[king]:
                    tokens_data[king][token] = {
                        'token': token,
                        'accounts': [],
                        'requests_limit': row['requests_limit'] or 100,
                        'requests_today': row['requests_today'] or 0,
                        'requests_usage_percent': row['requests_usage_percent'] or 0
                    }
                
                if row['account_id']:
                    tokens_data[king][token]['accounts'].append({
                        'account_id': row['account_id'],
                        'requests_limit': row['requests_limit'] or 100,
                        'requests_today': row['requests_today'] or 0,
                        'requests_usage_percent': row['requests_usage_percent'] or 0
                    })
            
            # Преобразуем в нужный формат
            result = {}
            for king, tokens in tokens_data.items():
                result[king] = list(tokens.values())
            
            logger.info(f"Финальный результат: {result}")
            return result
            
    except Exception as e:
        logger.error(f"Ошибка получения токенов для таблицы: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {}
def auto_determine_king(token: str) -> str:
    """Автоматически определяет KING на основе токена"""
    if not token or not isinstance(token, str):
        return "Facebook_Default"
    
    token_lower = token.lower()
    
    # Определяем платформу по характерным признакам токена
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
    elif len(token) > 100:  # Длинные токены обычно Facebook
        return "Facebook_Long"
    elif len(token) > 50:   # Средние токены
        return "Facebook_Medium"
    else:
        return "Facebook_Default"
    
def get_account_limits_info(account_id: str, access_token: str) -> Dict[str, Any]:
    """Получает информацию о лимитах аккаунта из Facebook API - исправленная версия"""
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
        
        # Сначала пробуем базовые поля, которые должны работать всегда
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
        
        # Пробуем получить daily limit отдельным запросом с обработкой ошибок
        daily_limit = 0
        try:
            # Пробуем разные поля для daily limit
            daily_limit_params = {
                'fields': '',
                'access_token': access_token
            }
            daily_response = requests.get(url, params=daily_limit_params, timeout=5)
            daily_data = daily_response.json()
            
            if 'error' not in daily_data:
                daily_spend_limit = float(daily_data.get('daily_spend_limit', 0)) / 100
                adtrust_dsl = float(daily_data.get('adtrust_dsl', 0)) / 100
                daily_limit = daily_spend_limit or adtrust_dsl or 0
                
        except (requests.exceptions.RequestException, KeyError, ValueError):
            # Игнорируем ошибки получения daily limit - это не критично
            pass
        
        # Получаем информацию о лимитах запросов из заголовков
        usage_info = response.headers.get('x-business-use-case-usage', '{}')
        calls_usage = 0
        calls_limit = 100
        
        try:
            usage_data = json.loads(usage_info)
            if usage_data and isinstance(usage_data, dict):
                for key in usage_data.keys():
                    call_count = usage_data[key][0].get('call_count', 0)
                    total_calls = usage_data[key][0].get('total_calls', 100)
                    calls_usage = max(calls_usage, call_count)
                    calls_limit = max(calls_limit, total_calls)
        except:
            pass
        
        amount_spent = float(data.get('amount_spent', 0)) / 100
        balance = float(data.get('balance', 0)) / 100
        spend_cap = float(data.get('spend_cap', 0)) / 100
        
        # Рассчитываем remaining amount (оставшийся лимит)
        remaining_amount = spend_cap - amount_spent if spend_cap > 0 else 0
        
        return {
            'account_id': clean_account_id,
            'name': data.get('name', 'N/A'),
            'status': data.get('account_status', 'UNKNOWN'),
            'spend': amount_spent,
            'balance': balance,
            'spend_cap': spend_cap,
            'remaining_amount': remaining_amount,  # Добавляем remaining amount
            'daily_limit': daily_limit,
            'requests_today': calls_usage,
            'requests_limit': calls_limit,
            'requests_usage_percent': round((calls_usage / calls_limit) * 100, 1) if calls_limit > 0 else 0
        }
    except requests.exceptions.RequestException as e:
        return {
            'account_id': account_id.replace('act_', ''),
            'name': 'Ошибка сети',
            'status': 'NETWORK_ERROR',
            'spend': 0,
            'balance': 0,
            'spend_cap': 0,
            'remaining_amount': 0,
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

@app.route('/api/reserve_tokens/delete', methods=['DELETE'])
@login_required
def delete_reserve_token_complete():
    """Полное удаление резервного токена и связанных данных"""
    user_id = session['user_id']
    data = request.json
    
    king = data.get('king')
    token = data.get('token')
    
    if not king or not token:
        return jsonify({'success': False, 'error': 'Не указан KING или токен'})
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # 1. Сначала получаем все account_id для этого токена
            cursor.execute("""
                SELECT account_id FROM reserve_token_accounts 
                WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            
            account_ids = [row['account_id'] for row in cursor.fetchall()]
            
            # 2. Удаляем аккаунты токена
            cursor.execute("""
                DELETE FROM reserve_token_accounts 
                WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            
            accounts_deleted = cursor.rowcount
            
            # 3. Удаляем сам токен
            cursor.execute("""
                DELETE FROM reserve_tokens 
                WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            
            token_deleted = cursor.rowcount
            
            # 4. Обновляем KING в основных таблицах для этого токена
            cursor.execute("""
                UPDATE campaigns 
                SET king = 'Facebook_Default'
                WHERE user_id = ? AND token = ? AND king = ?
            """, (user_id, token, king))
            
            campaigns_updated = cursor.rowcount
            
            cursor.execute("""
                UPDATE adsets 
                SET king = 'Facebook_Default'
                WHERE user_id = ? AND token = ? AND king = ?
            """, (user_id, token, king))
            
            adsets_updated = cursor.rowcount
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Токен удален: {token_deleted} токенов, {accounts_deleted} аккаунтов',
                'details': {
                    'token_deleted': token_deleted,
                    'accounts_deleted': accounts_deleted,
                    'campaigns_updated': campaigns_updated,
                    'adsets_updated': adsets_updated
                }
            })
            
    except Exception as e:
        logger.error(f"Ошибка удаления токена: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/reserve_tokens/accounts/manage', methods=['POST', 'DELETE'])
@login_required
def handle_reserve_token_accounts():
    """Управление аккаунтами резервных токенов (добавление/удаление отдельных аккаунтов)"""
    user_id = session['user_id']
    
    if request.method == 'POST':
        data = request.json
        king = data.get('king')
        token = data.get('token')
        account_id = data.get('account_id')
        
        if not all([king, token, account_id]):
            return jsonify({'success': False, 'error': 'Не указан KING, токен или account_id'})
        
        if add_account_to_reserve_token(user_id, king, token, account_id):
            return jsonify({'success': True, 'message': 'Аккаунт добавлен'})
        else:
            return jsonify({'success': False, 'error': 'Ошибка добавления аккаунта'})
    
    elif request.method == 'DELETE':
        data = request.json
        king = data.get('king')
        token = data.get('token')
        account_id = data.get('account_id')
        
        if not all([king, token, account_id]):
            return jsonify({'success': False, 'error': 'Не указан KING, токен или account_id'})
        
        if remove_account_from_reserve_token(user_id, king, token, account_id):
            return jsonify({'success': True, 'message': 'Аккаунт удален'})
        else:
            return jsonify({'success': False, 'error': 'Ошибка удаления аккаунта'})

@app.route('/api/reserve_tokens/<king>', methods=['GET'])
@login_required
def get_reserve_tokens_by_king(king):
    """Получает все токены для конкретного king"""
    user_id = session['user_id']
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT token 
                FROM reserve_tokens 
                WHERE user_id = ? AND king = ?
                ORDER BY created_at DESC
            """, (user_id, king))
            
            tokens = [row['token'] for row in cursor.fetchall()]
            
            return jsonify({
                'success': True,
                'tokens': tokens,
                'king': king
            })
            
    except Exception as e:
        logger.error(f"Ошибка получения токенов для king {king}: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/combined_tokens_table', methods=['GET'])
@login_required
def get_combined_tokens_table():
    """Возвращает совмещенные данные: основные аккаунты + резервные токены"""
    user_id = session['user_id']
    
    try:
        # Получаем основные аккаунты из campaigns
        main_accounts = []
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Основные аккаунты из campaigns
            cursor.execute("""
                SELECT DISTINCT account_id, token 
                FROM campaigns 
                WHERE user_id = ? AND account_id IS NOT NULL AND token IS NOT NULL
                AND account_id != '' AND token != ''
            """, (user_id,))
            
            for row in cursor.fetchall():
                king = auto_determine_king(row['token'])
                main_accounts.append({
                    'king': king,
                    'token': row['token'],
                    'account_id': row['account_id'],
                    'type': 'main',
                    'source': 'campaigns'
                })
        
        # Получаем резервные токены
        reserve_tokens = get_reserve_tokens_table(user_id)
        
        # Формируем совмещенную структуру
        combined_data = {}
        
        # Добавляем основные аккаунты
        for account in main_accounts:
            king = account['king']
            if king not in combined_data:
                combined_data[king] = {}
            
            token = account['token']
            if token not in combined_data[king]:
                combined_data[king][token] = {
                    'token': token,
                    'accounts': [],
                    'type': 'main',
                    'requests_limit': 100,
                    'requests_today': 0,
                    'requests_usage_percent': 0
                }
            
            combined_data[king][token]['accounts'].append({
                'account_id': account['account_id'],
                'type': 'main'
            })
        
        # Добавляем резервные токены
        for king, tokens in reserve_tokens.items():
            if king not in combined_data:
                combined_data[king] = {}
            
            for token_info in tokens:
                token = token_info['token']
                if token not in combined_data[king]:
                    combined_data[king][token] = {
                        'token': token,
                        'accounts': [],
                        'type': 'reserve',
                        'requests_limit': token_info.get('requests_limit', 100),
                        'requests_today': token_info.get('requests_today', 0),
                        'requests_usage_percent': token_info.get('requests_usage_percent', 0)
                    }
                
                # Добавляем аккаунты резервных токенов
                for account in token_info.get('accounts', []):
                    combined_data[king][token]['accounts'].append({
                        'account_id': account['account_id'],
                        'type': 'reserve',
                        'requests_limit': account.get('requests_limit', 100),
                        'requests_today': account.get('requests_today', 0),
                        'requests_usage_percent': account.get('requests_usage_percent', 0)
                    })
        
        # Преобразуем в нужный формат
        result = {}
        for king, tokens in combined_data.items():
            result[king] = list(tokens.values())
        
        return jsonify({
            'success': True,
            'tokens': result
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения совмещенных токенов: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/reserve_tokens/check_limits', methods=['POST'])
@login_required
def check_reserve_token_limits():
    """Проверяет лимиты для конкретного токена"""
    user_id = session['user_id']
    data = request.json
    
    king = data.get('king')
    token = data.get('token')
    
    if not king or not token:
        return jsonify({'success': False, 'error': 'Не указан KING или токен'})
    
    try:
        # Получаем аккаунты для этого токена
        accounts = get_reserve_token_accounts(user_id, king, token)
        checked_count = 0
        
        for account in accounts:
            account_id = account['account_id']
            # Проверяем лимиты через Facebook API
            limits_info = get_account_limits_info(account_id, token)
            
            if limits_info:
                # Обновляем информацию об аккаунте
                update_reserve_token_account_info(user_id, king, token, account_id, limits_info)
                checked_count += 1
        
        return jsonify({
            'success': True,
            'message': f'Проверено {checked_count} аккаунтов',
            'checked_accounts': checked_count
        })
        
    except Exception as e:
        logger.error(f"Ошибка проверки лимитов: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reserve_tokens/table', methods=['GET'])
@login_required
def get_reserve_tokens_table_route():
    """Возвращает резервные токены в формате для таблицы"""
    user_id = session['user_id']
    logger.info(f"Запрос токенов для user_id: {user_id}, username: {session.get('username')}")
    
    try:
        tokens = get_reserve_tokens_table(user_id)
        return jsonify({'success': True, 'tokens': tokens})
            
    except Exception as e:
        logger.error(f"Ошибка получения токенов для таблицы: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/reserve_tokens', methods=['POST'])
@login_required
def handle_reserve_tokens_post():
    user_id = session['user_id']
    data = request.json
    
    # Получаем параметры из data
    king = data.get('king')
    token = data.get('token')
    account_ids = data.get('account_ids', [])
    
    # Если king - это объект (из старого формата), извлекаем значение
    if isinstance(king, dict):
        king = king.get('king') or king.get('value') or ''
    
    if not token:
        return jsonify({'success': False, 'error': 'Не указан токен'})
    
    # Автоматически определяем KING если не указан или пустой
    if not king or str(king).strip() == '':
        king = auto_determine_king(token)
    
    if add_reserve_token(user_id, king, token):
        # Добавляем аккаунты если они указаны
        for account_id in account_ids:
            if account_id:
                add_account_to_reserve_token(user_id, king, token, account_id)
        
        return jsonify({
            'success': True, 
            'message': 'Токен добавлен', 
            'auto_determined_king': king
        })
    else:
        return jsonify({'success': False, 'error': 'Ошибка добавления токена'})
@app.route('/api/reserve_tokens/check_all_limits', methods=['POST'])
@login_required
def check_all_reserve_token_limits():
    """Проверяет лимиты для всех токенов"""
    user_id = session['user_id']
    
    try:
        reserve_tokens = get_reserve_tokens(user_id)
        total_checked = 0
        
        for king, tokens in reserve_tokens.items():
            for token_info in tokens:
                token = token_info['token']
                accounts = token_info['accounts']  # Теперь accounts уже в структуре
                
                for account in accounts:
                    account_id = account['account_id']
                    limits_info = get_account_limits_info(account_id, token)
                    
                    if limits_info:
                        update_reserve_token_account_info(user_id, king, token, account_id, limits_info)
                        total_checked += 1
        
        return jsonify({
            'success': True,
            'message': f'Проверено {total_checked} аккаунтов',
            'total_checked': total_checked
        })
        
    except Exception as e:
        logger.error(f"Ошибка проверки всех лимитов: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/reserve_tokens/check_account_limits_direct', methods=['POST'])
@login_required
def check_reserve_token_account_limits_direct():
    """Проверяет лимиты для аккаунта напрямую (без сохранения в БД)"""
    user_id = session['user_id']
    data = request.json
    
    account_id = data.get('account_id')
    token = data.get('token')
    
    if not all([account_id, token]):
        return jsonify({'success': False, 'error': 'Не указан account_id или token'})
    
    try:
        # Проверяем лимиты через Facebook API
        limits_info = get_account_limits_info(account_id, token)
        
        if limits_info:
            return jsonify({
                'success': True,
                'account_info': limits_info,
                'token': token
            })
        else:
            return jsonify({'success': False, 'error': 'Не удалось получить информацию об аккаунте'})
        
    except Exception as e:
        logger.error(f"Ошибка проверки лимитов аккаунта: {e}")
        return jsonify({'success': False, 'error': str(e)})

def add_account_to_reserve_token(user_id, king, token, account_id):
    """Добавляет аккаунт к резервному токену"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Создаем таблицу если не существует
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reserve_token_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    king TEXT NOT NULL,
                    token TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    name TEXT,
                    status TEXT,
                    spend_cap REAL DEFAULT 0,
                    amount_spent REAL DEFAULT 0,
                    balance REAL DEFAULT 0,
                    daily_limit REAL DEFAULT 0,
                    remaining REAL DEFAULT 0,
                    requests_today INTEGER DEFAULT 0,
                    requests_limit INTEGER DEFAULT 100,
                    requests_usage_percent REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(user_id, king, token, account_id)
                )
            """)
            
            cursor.execute(
                "INSERT OR IGNORE INTO reserve_token_accounts (user_id, king, token, account_id) VALUES (?, ?, ?, ?)",
                (user_id, king, token, account_id)
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка добавления аккаунта к токену: {e}")
        return False
def update_reserve_token_account_info(user_id, king, token, account_id, account_info):
    """Обновляет информацию об аккаунте резервного токена"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE reserve_token_accounts 
                SET name = ?, status = ?, spend_cap = ?, amount_spent = ?, 
                    balance = ?, daily_limit = ?, remaining = ?,
                    requests_today = ?, requests_limit = ?, requests_usage_percent = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND king = ? AND token = ? AND account_id = ?
            """, (
                account_info.get('name'),
                account_info.get('status'),
                account_info.get('spend_cap', 0),
                account_info.get('spend', 0),  # amount_spent = spend
                account_info.get('balance', 0),
                account_info.get('daily_limit', 0),
                account_info.get('remaining_limit', 0),
                account_info.get('requests_today', 0),
                account_info.get('requests_limit', 100),
                account_info.get('requests_usage_percent', 0),
                user_id, king, token, account_id
            ))
            
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления информации аккаунта: {e}")
        return False
def remove_account_from_reserve_token(user_id, account_id):
    """Удаляет аккаунт из резервного токена"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM reserve_token_accounts WHERE user_id = ? AND account_id = ?",
                (user_id, account_id)
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка удаления аккаунта: {e}")
        return False

@app.route('/account_limits')
@login_required
def account_limits():
    """Страница отображения лимитов аккаунтов"""
    return render_template('account_limits.html')

def get_reserve_tokens(user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Получает резервные токены с аккаунтами - исправленная версия"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT rt.king, rt.token, 
                       rta.account_id, rta.name, rta.status, rta.spend_cap, 
                       rta.amount_spent, rta.balance, rta.daily_limit, rta.remaining,
                       rta.requests_today, rta.requests_limit, rta.requests_usage_percent
                FROM reserve_tokens rt
                LEFT JOIN reserve_token_accounts rta ON rt.user_id = rta.user_id 
                    AND rt.king = rta.king AND rt.token = rta.token
                WHERE rt.user_id = ?
                ORDER BY rt.king, rt.token
            """, (user_id,))
            
            tokens_by_king = {}
            for row in cursor.fetchall():
                king = row['king']
                token = row['token']
                
                if king not in tokens_by_king:
                    tokens_by_king[king] = []
                
                # Находим токен в списке или создаем новый
                token_entry = None
                for entry in tokens_by_king[king]:
                    if entry['token'] == token:
                        token_entry = entry
                        break
                
                if not token_entry:
                    token_entry = {
                        'token': token,
                        'accounts': []
                    }
                    tokens_by_king[king].append(token_entry)
                
                # Добавляем аккаунт, если он есть
                if row['account_id']:
                    token_entry['accounts'].append({
                        'account_id': row['account_id'],
                        'name': row['name'],
                        'status': row['status'],
                        'spend_cap': row['spend_cap'],
                        'amount_spent': row['amount_spent'],
                        'balance': row['balance'],
                        'daily_limit': row['daily_limit'],
                        'remaining': row['remaining'],
                        'requests_today': row['requests_today'],
                        'requests_limit': row['requests_limit'],
                        'requests_usage_percent': row['requests_usage_percent']
                    })
            
            return tokens_by_king
            
    except Exception as e:
        logger.error(f"Ошибка получения резервных токенов: {e}")
        return {}

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

@app.route('/api/reserve_tokens/accounts', methods=['DELETE'])
@login_required
def handle_reserve_tokens_delete():
    """Удаляет резервный токен и обновляет основные таблицы"""
    user_id = session['user_id']
    data = request.json
    
    king = data.get('king')
    token = data.get('token')
    
    if not king or not token:
        return jsonify({'success': False, 'error': 'Не указан KING или токен'})
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # 1. Сначала получаем все account_id для этого токена
            cursor.execute("""
                SELECT account_id FROM reserve_token_accounts 
                WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            
            account_ids = [row['account_id'] for row in cursor.fetchall()]
            
            # 2. Удаляем аккаунты токена
            cursor.execute("""
                DELETE FROM reserve_token_accounts 
                WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            
            accounts_deleted = cursor.rowcount
            
            # 3. Удаляем сам токен
            cursor.execute("""
                DELETE FROM reserve_tokens 
                WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            
            token_deleted = cursor.rowcount
            
            # 4. Обновляем KING в основных таблицах для этого токена
            # Только если есть соответствующие записи
            cursor.execute("""
                UPDATE campaigns 
                SET king = 'Facebook_Default'
                WHERE user_id = ? AND token = ? AND king = ?
            """, (user_id, token, king))
            
            campaigns_updated = cursor.rowcount
            
            cursor.execute("""
                UPDATE adsets 
                SET king = 'Facebook_Default'
                WHERE user_id = ? AND token = ? AND king = ?
            """, (user_id, token, king))
            
            adsets_updated = cursor.rowcount
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Токен удален: {token_deleted} токенов, {accounts_deleted} аккаунтов',
                'details': {
                    'token_deleted': token_deleted,
                    'accounts_deleted': accounts_deleted,
                    'campaigns_updated': campaigns_updated,
                    'adsets_updated': adsets_updated
                }
            })
            
    except Exception as e:
        logger.error(f"Ошибка удаления токена: {e}")
        return jsonify({'success': False, 'error': str(e)})
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

@app.route('/api/account_limits', methods=['GET'])
@login_required
def get_account_limits():
    """Возвращает информацию о лимитах всех аккаунтов пользователя"""
    try:
        user_id = session['user_id']
        accounts = []
        total_spend = 0
        total_limit = 0
        
        # Получаем все аккаунты пользователя
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Получаем уникальные аккаунты
            cursor.execute("""
                SELECT DISTINCT account_id, token 
                FROM campaigns 
                WHERE user_id = ? AND account_id IS NOT NULL AND token IS NOT NULL
            """, (user_id,))
            
            account_data = cursor.fetchall()
            
            for account in account_data:
                account_id = account['account_id']
                token = account['token']
                
                # Получаем информацию о лимитах из Facebook API
                account_info = get_account_limits_info(account_id, token)
                
                if account_info:
                    accounts.append(account_info)
                    total_spend += account_info.get('spend', 0)
                    total_limit += account_info.get('spend_cap', 0)
        
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
            "fields": "adset_id,spend,cpc, cpm, cost_per_conversion,conversions",
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
                        'cpm': float(insight.get('cpm', 0)),
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
        cleanup_accounts = request.json.get('cleanup_accounts', [])
        

        # Получаем известные GEO коды
        geo_rules = get_user_geo_rules(user_id)
        known_geos = list(geo_rules.keys()) if geo_rules else []
        
        total_campaigns = 0
        total_adsets = 0
        cleaned_campaigns = 0
        cleaned_adsets = 0

        # Собираем все аккаунты из запроса для очистки
        imported_account_ids = []
        
        for account_data in accounts_data:
            account_id = account_data.get('account_id', '').strip()
            token = account_data.get('token', '').strip()
            
            # Очищаем account_id от префикса act_
            clean_account_id = account_id.replace('act_', '')
            imported_account_ids.append(clean_account_id)
            
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

 # 🔹 Очистка удаленных аккаунтов
        if cleanup_accounts is not None:
            clean_cleanup_accounts = [acc.replace('act_', '') for acc in cleanup_accounts if acc]

            with get_db_connection(user_id) as conn:
                cursor = conn.cursor()

                if clean_cleanup_accounts:
                    placeholders = ','.join('?' * len(clean_cleanup_accounts))

                    # Удаляем кампании вне переданного списка
                    cursor.execute(f"""
                        DELETE FROM campaigns 
                        WHERE user_id = ? AND account_id NOT IN ({placeholders})
                    """, [user_id] + clean_cleanup_accounts)
                    cleaned_campaigns = cursor.rowcount

                    # Удаляем адсеты вне переданного списка
                    cursor.execute(f"""
                        DELETE FROM adsets 
                        WHERE user_id = ? AND account_id NOT IN ({placeholders})
                    """, [user_id] + clean_cleanup_accounts)
                    cleaned_adsets = cursor.rowcount

                else:
                    # Если список пуст — удаляем все кампании и адсеты пользователя
                    cursor.execute("DELETE FROM campaigns WHERE user_id = ?", (user_id,))
                    cleaned_campaigns = cursor.rowcount

                    cursor.execute("DELETE FROM adsets WHERE user_id = ?", (user_id,))
                    cleaned_adsets = cursor.rowcount

                conn.commit()

                logger.info(
                    f"Очистка: удалено {cleaned_campaigns} кампаний и {cleaned_adsets} адсетов "
                    f"для аккаунтов вне списка: {clean_cleanup_accounts or 'все аккаунты'}"
                )

        return jsonify({
            'success': True,
            'message': f'Импортировано {total_campaigns} кампаний и {total_adsets} адсетов. Очищено {cleaned_campaigns} кампаний и {cleaned_adsets} адсетов',
            'total_campaigns': total_campaigns,
            'total_adsets': total_adsets,
            'cleaned_campaigns': cleaned_campaigns,
            'cleaned_adsets': cleaned_adsets
        })

    except Exception as e:
        logger.error(f"Ошибка bulk-импорта: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get_existing_accounts', methods=['GET'])
@login_required
def get_existing_accounts():
    """Получает уникальные аккаунты и токены из базы данных"""
    try:
        user_id = session['user_id']
        
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Получаем уникальные комбинации account_id и token из кампаний
            cursor.execute("""
                SELECT DISTINCT account_id, token 
                FROM campaigns 
                WHERE user_id = ? AND account_id != '' AND token != ''
                UNION
                SELECT DISTINCT account_id, token 
                FROM adsets 
                WHERE user_id = ? AND account_id != '' AND token != ''
            """, (user_id, user_id))
            
            accounts = cursor.fetchall()
            
            result = []
            for account in accounts:
                result.append({
                    'account_id': account['account_id'],
                    'token': account['token']
                })
            
            return jsonify({
                'success': True,
                'accounts': result
            })
            
    except Exception as e:
        logger.error(f"Ошибка получения аккаунтов: {e}")
        return jsonify({
            'success': False, 
            'error': str(e),
            'accounts': []
        })
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
            if settings.get('auto_refresh_interval', 60) > 0:
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

from backend.autocontrol import start_auto_control_and_refresh


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
def get_keitaro_performance_data(api_key, domain, campaign_id=None, interval="today"):
    """Альтернативный метод получения данных из Keitaro"""
    try:
        url = f"https://{domain}/admin_api/v1/report/build"
        headers = {
            "Api-Key": api_key, 
            "Content-Type": "application/json"
        }
        
        # Упрощенный payload с правильными метриками
        payload = {
            "range": {
                "interval": interval,
                "timezone": "Europe/Moscow"
            },
            "metrics": ["conversions", "cost", "revenue", "clicks"],
            "grouping": ["stream_id", "campaign_id"],
            "limit": 1000
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            all_rows = data.get('rows', [])
            
            # Фильтруем по campaign_id локально
            if campaign_id:
                filtered_rows = []
                for row in all_rows:
                    row_campaign_id = str(row.get('campaign_id') or row.get('sub_id_1') or '')
                    if row_campaign_id == str(campaign_id):
                        filtered_rows.append(row)
                return filtered_rows
            
            return all_rows
        
        return []
        
    except Exception as e:
        logger.error(f"Ошибка получения данных из Keitaro: {e}")
        return []
def analyze_stream_performance(api_key, domain, campaign_id=None, interval="today"):
    """Анализирует производительность потоков - исправленная версия"""
    try:
        url = f"https://{domain}/admin_api/v1/report/build"
        headers = {
            "Api-Key": api_key, 
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Используем только доступные метрики из ошибки
        payload = {
            "range": {
                "interval": interval,
                "timezone": "Europe/Moscow"
            },
            "metrics": ["conversions", "revenue", "cost", "roi", "epc", "clicks"],
            "grouping": ["stream_id"],
            "limit": 1000
        }
        
        # Добавляем фильтр по кампании если указана
        if campaign_id and campaign_id != 'all':
            payload["filters"] = [
                {
                    "name": "campaign_id", 
                    "operator": "EQUALS", 
                    "expression": str(campaign_id)
                }
            ]
        
        logger.info(f"Отправка запроса к Keitaro с правильными метриками")
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Keitaro API error: {response.status_code} - {response.text}")
            return []
        
        data = response.json()
        rows = data.get('rows', [])
        
        logger.info(f"Получено {len(rows)} записей из Keitaro")
        
        # Логируем первую запись для отладки
        if rows:
            logger.info(f"Пример данных: {json.dumps(rows[0], ensure_ascii=False)}")
        
        return rows
        
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
    """Возвращает список кампаний из Keitaro с поиском и пагинацией"""
    try:
        user_id = session['user_id']
        settings = get_user_settings(user_id)
        api_key = settings.get('keitaro_api_key')
        domain = settings.get('keitaro_domain')
        search_query = request.args.get('search', '')
        limit = int(request.args.get('limit', 50))
        
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
        
        # Фильтрация по поисковому запросу
        if search_query:
            search_lower = search_query.lower()
            campaigns = [camp for camp in campaigns 
                        if (search_lower in str(camp.get('name', '')).lower() 
                            or search_lower in str(camp.get('id', '')).lower())]
        
        # Ограничение количества
        campaigns = campaigns[:limit]
        
        # Форматируем ответ
        formatted_campaigns = []
        for campaign in campaigns:
            formatted_campaigns.append({
                'id': campaign.get('id'),
                'name': campaign.get('name', 'Unknown'),
                'status': campaign.get('status', 'active'),
                'cost': float(campaign.get('cost', 0)),
                'revenue': float(campaign.get('revenue', 0)),
                'traffic_source': campaign.get('traffic_source', ''),
                'group_id': campaign.get('group_id', '')
            })
        
        return jsonify({
            'success': True,
            'campaigns': formatted_campaigns,
            'total': len(formatted_campaigns),
            'search_query': search_query,
            'limit': limit
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения кампаний Keitaro: {e}")
        return jsonify({'success': False, 'error': str(e)})
def get_keitaro_stream_info(api_key, domain, stream_id):
    """Получает информацию о конкретном потоке"""
    try:
        url = f"https://{domain}/admin_api/v1/streams/{stream_id}"
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        return {
            'id': data.get('id'),
            'name': data.get('name', 'Unknown'),
            'weight': data.get('weight', 0),
            'is_active': data.get('is_active', False),
            'campaign_id': data.get('campaign_id'),
            'url': data.get('url', '')
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения информации о потоке {stream_id}: {e}")
        return {'id': stream_id, 'name': f'Stream {stream_id}', 'weight': 0, 'is_active': False}

def get_keitaro_campaign_info(api_key, domain, campaign_id):
    """Получает информацию о кампании"""
    try:
        url = f"https://{domain}/admin_api/v1/campaigns/{campaign_id}"
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        return {
            'id': data.get('id'),
            'name': data.get('name', 'Unknown'),
            'status': data.get('status', 'active'),
            'cost': data.get('cost', 0),
            'revenue': data.get('revenue', 0)
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения информации о кампании {campaign_id}: {e}")
        return {'id': campaign_id, 'name': f'Campaign {campaign_id}', 'status': 'unknown'}
@app.route('/api/debug/keitaro', methods=['GET'])
@login_required
def debug_keitaro():
    """Отладочная информация о подключении к Keitaro"""
    try:
        user_id = session['user_id']
        settings = get_user_settings(user_id)
        api_key = settings.get('keitaro_api_key')
        domain = settings.get('keitaro_domain')
        
        if not api_key:
            return jsonify({'success': False, 'error': 'Keitaro API key not configured'})
        
        # Тестовый запрос
        url = f"https://{domain}/admin_api/v1/campaigns"
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        
        response = requests.get(url, headers=headers, timeout=30)
        
        return jsonify({
            'success': True,
            'api_key_exists': bool(api_key),
            'domain': domain,
            'status_code': response.status_code,
            'response_sample': response.json()[:2] if response.status_code == 200 else None
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
def get_keitaro_campaign_streams(api_key, domain, campaign_id):
    """Получает все потоки конкретной кампании"""
    try:
        url = f"https://{domain}/admin_api/v1/campaigns/{campaign_id}/streams"
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        streams = []
        
        if isinstance(data, list):
            streams = data
        elif isinstance(data, dict) and 'streams' in data:
            streams = data.get('streams', [])
        elif isinstance(data, dict) and 'data' in data:
            streams = data.get('data', [])
        
        return streams
        
    except Exception as e:
        logger.error(f"Ошибка получения потоков кампании {campaign_id}: {e}")
        return []
@app.route('/api/headline_optimization/status', methods=['GET'])
@login_required
def get_headline_optimization_status():
    """Возвращает статус оптимизации заголовков для кампании"""
    try:
        user_id = session['user_id']
        campaign_id = request.args.get('campaign_id')
        
        if not campaign_id:
            return jsonify({'success': False, 'error': 'Не указан campaign_id'})
        
        settings = get_user_settings(user_id)
        api_key = settings.get('keitaro_api_key')
        domain = settings.get('keitaro_domain')
        
        if not api_key:
            return jsonify({'success': False, 'error': 'Keitaro API key not configured'})
        
        logger.info(f"Запрос статистики для кампании {campaign_id}")
        
        # Пробуем разные методы получения данных
        stream_stats = analyze_stream_performance(api_key, domain, campaign_id, "today")
        
        # Если не получилось, пробуем альтернативный метод
        if not stream_stats:
            logger.warning("Первый метод не дал результатов, пробуем альтернативный...")
            stream_stats = get_keitaro_performance_data(api_key, domain, campaign_id, "today")
        
        logger.info(f"Получено {len(stream_stats)} записей статистики")
        
        # Если все еще нет данных, пробуем получить потоки кампании
        if not stream_stats:
            logger.warning("Нет статистики, пробуем получить потоки кампании...")
            campaign_streams = get_keitaro_campaign_streams(api_key, domain, campaign_id)
            
            # Создаем пустые записи для каждого потока
            for stream in campaign_streams:
                stream_stats.append({
                    'stream_id': stream.get('id'),
                    'conversions': 0,
                    'cost': 0,
                    'revenue': 0,
                    'clicks': 0,
                    'campaign_id': campaign_id
                })
        
        stream_data = []
        total_conversions = 0
        total_cost = 0
        total_revenue = 0
        total_clicks = 0
        
        for stat in stream_stats:
            try:
                # Пробуем разные поля для stream_id
                stream_id = str(stat.get('stream_id') or stat.get('id') or 'unknown')
                if stream_id == 'unknown':
                    continue
                
                cost = float(stat.get('cost', 0)) if stat.get('cost') not in [None, ''] else 0
                conversions = int(stat.get('conversions', 0)) if stat.get('conversions') not in [None, ''] else 0
                revenue = float(stat.get('revenue', 0)) if stat.get('revenue') not in [None, ''] else 0
                clicks = int(stat.get('clicks', 0)) if stat.get('clicks') not in [None, ''] else 0
                
                # Рассчитываем метрики
                cpa = cost / conversions if conversions > 0 else 0
                roi = ((revenue - cost) / cost * 100) if cost > 0 else 0
                ctr = (conversions / clicks * 100) if clicks > 0 else 0
                
                # Получаем информацию о потоке
                stream_info = get_keitaro_stream_info(api_key, domain, stream_id)
                
                stream_data.append({
                    'id': stream_id,
                    'name': stream_info.get('name', f'Stream {stream_id}'),
                    'weight': stream_info.get('weight', 0),
                    'is_active': stream_info.get('is_active', False),
                    'conversions': conversions,
                    'cost': cost,
                    'revenue': revenue,
                    'clicks': clicks,
                    'cpa': cpa,
                    'roi': roi,
                    'ctr': ctr
                })
                
                total_conversions += conversions
                total_cost += cost
                total_revenue += revenue
                total_clicks += clicks
                
            except Exception as e:
                logger.error(f"Ошибка обработки статистики потока: {e}")
                continue
        
        campaign_info = get_keitaro_campaign_info(api_key, domain, campaign_id)
        
        response_data = {
            'success': True,
            'campaign_id': campaign_id,
            'campaign_name': campaign_info.get('name', f'Campaign {campaign_id}'),
            'streams': stream_data,
            'total_stats': {
                'conversions': total_conversions,
                'cost': total_cost,
                'revenue': total_revenue,
                'clicks': total_clicks,
                'cpa': total_cost / total_conversions if total_conversions > 0 else 0,
                'roi': ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0,
                'ctr': (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
            },
            'total_streams': len(stream_data),
            'active_streams': len([s for s in stream_data if s['is_active']])
        }
        
        logger.info(f"Отправка данных: {len(stream_data)} потоков")
        return jsonify(response_data)
        
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
    """Рассчитывает требуемый дневной бюджет - показывает все кампании, но считает только активные"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Берём ВСЕ адсеты, но считаем бюджет только для активных
            cursor.execute("""
                SELECT 
                    a.account_id,
                    c.token,
                    SUM(CASE WHEN UPPER(a.status) = 'ACTIVE' AND UPPER(a.effective_status) = 'ACTIVE' 
                            THEN a.budget ELSE 0 END) as total_active_budget,
                    SUM(a.budget) as total_all_budget,
                    COUNT(a.adset_id) as total_adsets,
                    SUM(CASE WHEN UPPER(a.status) = 'ACTIVE' AND UPPER(a.effective_status) = 'ACTIVE' 
                            THEN 1 ELSE 0 END) as active_adsets
                FROM adsets a
                LEFT JOIN campaigns c 
                    ON a.campaign_id = c.campaign_id AND a.user_id = c.user_id
                WHERE a.user_id = ? 
                  AND a.budget > 0
                  AND a.account_id IS NOT NULL
                  AND a.account_id != ''
                GROUP BY a.account_id, c.token
            """, (user_id,))
            
            requirements = []
            for row in cursor.fetchall():
                requirements.append({
                    'account_id': row['account_id'],
                    'token': row['token'],
                    'total_active_budget': float(row['total_active_budget'] or 0.0),
                    'total_all_budget': float(row['total_all_budget'] or 0.0),
                    'total_adsets': row['total_adsets'],
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
    """Проверяет достаточность лимита на аккаунтах - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    try:
        # Получаем требования по бюджетам с правильным подсчетом активных адсетов
        budget_requirements = calculate_daily_budget_requirements(user_id)
        
        warnings = []
        
        for req in budget_requirements:
            # Проверяем, что есть account_id и token
            if not req['account_id'] or not req['token']:
                continue
                
            # Получаем информацию об аккаунте
            account_info = get_account_limits_info(req['account_id'], req['token'])
            
            if account_info:
                remaining_amount = account_info.get('remaining_amount', 0)
                required = req['total_active_budget']  # Используем только активный бюджет для проверки
                
                # Определяем deficit
                deficit = max(0, required - remaining_amount) if remaining_amount < required else 0
                
                # Рассчитываем дни оставшиеся
                if required > 0:
                    days_remaining = remaining_amount / required
                else:
                    days_remaining = 999999  # большое число вместо infinity
                
                warning = {
                    'account_id': req['account_id'],
                    'account_name': account_info.get('name', 'Unknown'),
                    'balance': account_info.get('balance', 0),
                    'remaining_amount': remaining_amount,
                    'spend_cap': account_info.get('spend_cap', 0),
                    'spend': account_info.get('spend', 0),
                    'required_today': required,
                    'total_budget': req['total_all_budget'],  # Общий бюджет (все адсеты)
                    'deficit': deficit,
                    'days_remaining': days_remaining,
                    'active_adsets': req['active_adsets'],
                    'total_adsets': req['total_adsets'],  # Всего адсетов
                    'status': account_info.get('status', 'UNKNOWN')
                }
                
                warnings.append(warning)
        
        return warnings
        
    except Exception as e:
        logger.error(f"Ошибка проверки лимита: {e}")
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
from datetime import datetime  # Добавьте этот импорт в начале файла
@app.route('/api/adsets/data', methods=['GET'])
def get_adsets_data():
    """API endpoint для получения данных об адсетах из базы данных"""
    try:
        user_id = session.get('user_id', 1)
        status_filter = request.args.get('status', 'all')
        search_query = request.args.get('search', '')
        excluded_filter = request.args.get('excluded')  # Новый параметр
        
        with sqlite3.connect('unitool.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Базовый запрос
            query = """
                SELECT 
                    adset_id, name, status, effective_status, account_id, token,
                    budget, geo, ucpc, cpc, cpm, spend, cpa, leads, king,
                    manual_pause, auto_budget_increase, auto_budget_decrease,
                    max_budget, min_budget, budget_increase_step, budget_decrease_step,
                    created_at, updated_at,
                    exclude_from_autocontrol  -- Добавляем поле исключения
                FROM adsets 
                WHERE user_id = ?
            """

            params = [user_id]
            
            # Фильтр по исключенным адсетам
            if excluded_filter is not None:
                if excluded_filter.lower() == 'true':
                    query += " AND (exclude_from_autocontrol = 1 OR name LIKE '%#NOAUTO%' OR name LIKE '%#EXCLUDE%' OR name LIKE '%#ИСКЛ%')"
                elif excluded_filter.lower() == 'false':
                    query += " AND exclude_from_autocontrol = 0 AND name NOT LIKE '%#NOAUTO%' AND name NOT LIKE '%#EXCLUDE%' AND name NOT LIKE '%#ИСКЛ%'"
            
            # Добавляем остальные фильтры
            if status_filter != 'all':
                query += " AND status = ?"
                params.append(status_filter.upper())
            
            if search_query:
                query += " AND name LIKE ?"
                params.append(f'%{search_query}%')
            
            query += " ORDER BY updated_at DESC"
            
            cursor.execute(query, params)
            adsets = cursor.fetchall()
            
            # Преобразуем в словарь
            adsets_data = []
            for adset in adsets:
                adset_dict = dict(adset)
                
                # Форматируем числовые значения
                for field in ['budget', 'spend', 'ucpc', 'cpc', 'cpm', 'cpa']:
                    adset_dict[field] = float(adset_dict[field]) if adset_dict[field] else 0
                
                adset_dict['leads'] = int(adset_dict['leads']) if adset_dict['leads'] else 0
                
                # Определяем, исключен ли адсет (учитываем и поле, и маркеры в названии)
                exclude_from_autocontrol = bool(adset_dict.get('exclude_from_autocontrol', 0))
                name = adset_dict.get('name', '')
                has_exclude_marker = any(marker in name.upper() for marker in ['#NOAUTO', '#EXCLUDE', '#ИСКЛ'])
                
                adset_dict['is_excluded'] = exclude_from_autocontrol or has_exclude_marker
                
                adsets_data.append(adset_dict)
            
            return jsonify({
                'success': True,
                'data': adsets_data,
                'count': len(adsets_data),
                'filters': {
                    'status': status_filter,
                    'search': search_query,
                    'excluded': excluded_filter
                },
                'last_updated': datetime.now().isoformat()
            })
            
    except Exception as e:
        print(f"Ошибка загрузки адсетов: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'data': []
        }), 500     
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
                    from backend.geo_config import (extract_geo_from_name,
                                                    get_user_geo_rules)

                    stats = keitaro_data_by_name.get(ad_name, {})

                    budget = float(ad.get("daily_budget", 0)) / 100 if ad.get("daily_budget") else 0
                    geo = extract_geo_from_name(ad_name)
                    add_user_adset(user_id, {
                        "name": ad_name,
                        "adset_id": adset_id,
                        "campaign_id": camp_id,
                        "status": ad.get("status", "UNKNOWN"),             # сырой status
                        "effective_status": ad.get("effective_status", "UNKNOWN"),  # сырой effective_status
                        "account_id": account_id,
                        "token": token,
                        "budget": budget,
                        "spend": stats.get("spend", 0),
                        "leads": stats.get("leads", 0),
                        "cpa": stats.get("cpa", 0),
                        "ucpc": stats.get("ucpc", 0),
                        "cpm": stats.get("cpm", 0),
                        "cpc": stats.get("cpc", 0),
                        "king": "Facebook",
                        "ad_name": ad_name,
                        "manual_pause": 0,
                        "geo": geo
                    })

                    if stats:
                        keitaro_matched += 1

                    total_adsets += 1

                saved_accounts += 1
            
            except requests.exceptions.RequestException as e:
                logger.warning(f"Ошибка сети для аккаунта {account_id}: {e}")
                continue
        try:
            updated = sync_keitaro(user_id)
            logger.info(f"[save_and_sync] Keitaro обновил {updated} адсетов для пользователя {user_id}")
        except Exception as e:
            logger.error(f"[save_and_sync] Ошибка обновления Keitaro: {e}")

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
@app.route('/api/adsets/exclude_multiple', methods=['POST'])
def exclude_multiple_adsets():
    try:
        data = request.get_json()
        user_id = get_current_user_id()
        adset_ids = data.get('adset_ids', [])
        exclude = data.get('exclude', True)
        
        if not adset_ids:
            return jsonify({'success': False, 'error': 'adset_ids обязателен'})
        
        # Обновляем статус для каждого адсета
        for adset_id in adset_ids:
            update_adset_exclusion_status(user_id, adset_id, exclude)
        
        action = "исключены" if exclude else "включены"
        logger.info(f"{len(adset_ids)} адсетов {action} из автоконтроля для user_id {user_id}")
        
        return jsonify({
            'success': True, 
            'message': f'{len(adset_ids)} адсетов {action} из автоконтроля'
        })
        
    except Exception as e:
        logger.error(f"Ошибка массового обновления статуса исключения: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/adsets/exclude', methods=['POST'])
def toggle_adset_exclusion():
    try:
        # проверяем JSON
        if not request.is_json:
            logger.warning("Exclude: тело запроса не JSON, raw: %s", request.get_data(as_text=True))
            return jsonify({'success': False, 'error': 'Требуется JSON тело запроса'}), 400

        data = request.get_json(silent=True)
        if not data:
            logger.warning("Exclude: request.get_json() вернул None, raw: %s", request.get_data(as_text=True))
            return jsonify({'success': False, 'error': 'Невалидный JSON'}), 400

        # безопасно получаем user_id
        user_id = session.get('user_id')
        if not user_id:
            logger.info("Exclude: не аутентифицированный запрос (нет session['user_id']). Cookies: %s", dict(request.cookies))
            return jsonify({'success': False, 'error': 'Пользователь не аутентифицирован'}), 401

        adset_id = data.get('adset_id')
        # допускаем также список adset_ids на будущее
        adset_ids = data.get('adset_ids')

        if not adset_id and not adset_ids:
            return jsonify({'success': False, 'error': 'adset_id или adset_ids обязателен'}), 400

        exclude = data.get('exclude', True)

        # Поддержка одного и нескольких id
        ids = [adset_id] if adset_id else list(adset_ids)

        # Выполняем обновление в БД для каждого id — оборачиваем в try чтобы логировать конкретный id
        updated = []
        errors = []
        for aid in ids:
            try:
                update_adset_exclusion_status(user_id, aid, exclude)
                updated.append(aid)
                logger.info("Адсет %s %s автоконтроля для user_id=%s", aid, ("исключён" if exclude else "включён"), user_id)
            except Exception as ex:
                logger.exception("Ошибка при обновлении adset %s: %s", aid, ex)
                errors.append({'adset_id': aid, 'error': str(ex)})

        if errors:
            return jsonify({'success': False, 'message': 'Частично выполнено', 'updated': updated, 'errors': errors}), 207

        return jsonify({'success': True, 'message': f'Адсет{"ы" if len(updated)>1 else ""} обновлены', 'adset_ids': updated, 'excluded': exclude})

    except Exception as e:
        logger.exception("Ошибка обновления статуса исключения: %s", e)
        return jsonify({'success': False, 'error': 'Внутренняя ошибка сервера'}), 500

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
        # Возвращайте JSON даже при ошибках
        return jsonify({
            'success': False, 
            'error': str(e),
            'warnings': [],
            'count': 0
        })

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
    """Обрабатывает запуск, остановку и получение статуса системы автоконтроля."""
    try:
        data = request.get_json()
        action = data.get('action')
        user_id = session['user_id']

        if action == 'start':
            # Интервал больше не передается от фронтенда
            start_auto_control_and_refresh(user_id)
            settings = get_user_settings(user_id)
            interval = settings.get('auto_refresh_interval', 60)
            return jsonify({'success': True, 'message': f'Система автоконтроля запущена с интервалом из настроек ({interval} мин).'})

        elif action == 'stop':
            stop_auto_control_and_refresh(user_id)
            return jsonify({'success': True, 'message': 'Система автоконтроля остановлена.'})

        elif action == 'status':
            status = get_combined_auto_status(user_id)
            return jsonify({'success': True, 'status': status})

        else:
            return jsonify({'success': False, 'error': 'Неизвестное действие'}), 400

    except Exception as e:
        logger.error(f"Ошибка в handle_auto_refresh: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/balance_monitor')
@login_required
def balance_monitor():
    """Страница мониторинга баланса"""
    return render_template('balance_monitor.html')

def stop_auto_refresh(user_id):
    """Останавливает автообновление для пользователя"""
    with auto_refresh_lock:
        if user_id in auto_refresh_timers:
            auto_refresh_timers[user_id].cancel()
            del auto_refresh_timers[user_id]
            logger.info(f"Автообновление остановлено для пользователя {user_id}")




def get_auto_refresh_status(user_id):
    """Возвращает статус автообновления"""
    with auto_refresh_lock:
        is_running = user_id in auto_refresh_timers
        settings = get_user_settings(user_id)
        interval = settings.get('auto_refresh_interval', 60)
        
        return {
            'running': is_running,
            'interval': interval,
            'next_refresh': None  #
        }
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
            'total_balance': 0,  # Будет вычисляться
            'total_limit': 0,    # Тотал лимит - сумма всех лимитов
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
                total_stats['total_balance'] += account_info.get('balance', 0)  # ВЫЧИСЛЯЕМ БАЛАНС
                total_stats['total_limit'] += account_info.get('spend_cap', 0)
                total_stats['total_requests'] += account_info.get('requests_today', 0)
        
        logger.info(f"Обработано {len(accounts_info)} аккаунтов. Баланс: ${total_stats['total_balance']:.2f}")
        
        return jsonify({
            'success': True,
            'stats': total_stats,
            'accounts': accounts_info,
            'debug': {
                'total_raw_accounts': len(all_accounts_data),
                'total_processed_accounts': len(accounts_info),
                'computed_balance': total_stats['total_balance']  # Для отладки
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
# app.py - добавьте этот endpoint
@app.route('/api/replace_account_token', methods=['POST'])
@login_required
def replace_account_token():
    """Заменяет токен для конкретного аккаунта"""
    user_id = session['user_id']
    data = request.json
    
    account_id = data.get('account_id')
    old_token = data.get('old_token')
    new_token = data.get('new_token')
    new_king = data.get('new_king')
    
    if not all([account_id, old_token, new_token, new_king]):
        return jsonify({'success': False, 'error': 'Не указаны все необходимые параметры'})
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Обновляем токен в кампаниях
            cursor.execute("""
                UPDATE campaigns 
                SET token = ?, king = ?
                WHERE user_id = ? AND account_id = ? AND token = ?
            """, (new_token, new_king, user_id, account_id, old_token))
            
            campaigns_updated = cursor.rowcount
            
            # Обновляем токен в адсетах
            cursor.execute("""
                UPDATE adsets 
                SET token = ?, king = ?
                WHERE user_id = ? AND account_id = ? AND token = ?
            """, (new_token, new_king, user_id, account_id, old_token))
            
            adsets_updated = cursor.rowcount
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Токен заменен в {campaigns_updated} кампаниях и {adsets_updated} адсетах',
                'campaigns_updated': campaigns_updated,
                'adsets_updated': adsets_updated
            })
            
    except Exception as e:
        logger.error(f"Ошибка замены токена аккаунта: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/user/reserve_tokens', methods=['GET'])
@login_required
def get_user_reserve_tokens():
    """Получает резервные токены текущего пользователя"""
    user_id = session['user_id']
    
    try:
        tokens = get_reserve_tokens(user_id)
        return jsonify({'success': True, 'tokens': tokens})
            
    except Exception as e:
        logger.error(f"Ошибка получения резервных токенов пользователя {user_id}: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/user/reserve_tokens_table', methods=['GET'])
@login_required
def get_user_reserve_tokens_table():
    """Возвращает резервные токены в формате для таблицы для текущего пользователя"""
    user_id = session['user_id']
    
    try:
        tokens = get_reserve_tokens_table(user_id)
        return jsonify({'success': True, 'tokens': tokens})
            
    except Exception as e:
        logger.error(f"Ошибка получения токенов для таблицы пользователя {user_id}: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/user/reserve_tokens', methods=['POST'])
@login_required
def add_user_reserve_token():
    """Добавляет резервный токен для текущего пользователя"""
    user_id = session['user_id']
    data = request.json
    
    # Получаем параметры из data
    king = data.get('king')
    token = data.get('token')
    account_ids = data.get('account_ids', [])
    
    # Если king - это объект (из старого формата), извлекаем значение
    if isinstance(king, dict):
        king = king.get('king') or king.get('value') or ''
    
    if not token:
        return jsonify({'success': False, 'error': 'Не указан токен'})
    
    # Автоматически определяем KING если не указан или пустой
    if not king or str(king).strip() == '':
        king = auto_determine_king(token)
    
    # Проверяем, не существует ли уже такой токен
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM reserve_tokens 
                WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            
            if cursor.fetchone():
                return jsonify({
                    'success': False, 
                    'error': f'Токен уже существует в группе {king}'
                })
    except Exception as e:
        logger.error(f"Ошибка проверки существования токена: {e}")
    
    if add_reserve_token(user_id, king, token):
        # Добавляем аккаунты если они указаны
        added_accounts = 0
        for account_id in account_ids:
            if account_id:
                if add_account_to_reserve_token(user_id, king, token, account_id):
                    added_accounts += 1
        
        return jsonify({
            'success': True, 
            'message': f'Токен добавлен ({added_accounts} аккаунтов)', 
            'auto_determined_king': king
        })
    else:
        return jsonify({'success': False, 'error': 'Ошибка добавления токена'})
def check_reserve_token_exists(user_id, king, token):
    """Проверяет, существует ли уже такой токен"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM reserve_tokens 
                WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Ошибка проверки существования токена: {e}")
        return False
@app.route('/api/user/reserve_tokens', methods=['DELETE'])
@login_required
def delete_user_reserve_token():
    """Удаляет резервный токен для текущего пользователя"""
    user_id = session['user_id']
    data = request.json
    
    king = data.get('king')
    token = data.get('token')
    
    if not king or not token:
        return jsonify({'success': False, 'error': 'Не указан KING или токен'})
    
    if remove_reserve_token(user_id, king, token):
        return jsonify({'success': True, 'message': 'Токен удален'})
    else:
        return jsonify({'success': False, 'error': 'Ошибка удаления токена'})
@app.route('/api/user/reserve_tokens/<king>', methods=['GET'])
@login_required
def get_user_reserve_tokens_by_king(king):
    """Получает все токены для конкретного king текущего пользователя"""
    user_id = session['user_id']
    
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT token 
                FROM reserve_tokens 
                WHERE user_id = ? AND king = ?
                ORDER BY created_at DESC
            """, (user_id, king))
            
            tokens = [row['token'] for row in cursor.fetchall()]
            
            return jsonify({
                'success': True,
                'tokens': tokens,
                'king': king
            })
            
    except Exception as e:
        logger.error(f"Ошибка получения токенов для king {king} пользователя {user_id}: {e}")
        return jsonify({'success': False, 'error': str(e)})
def update_username(user_id: int, new_username: str) -> bool:
    """
    Обновляет имя пользователя по его ID.

    Args:
        user_id (int): ID пользователя
        new_username (str): новое имя пользователя

    Returns:
        bool: True, если обновление прошло успешно, иначе False
    """
    with lock:
        with get_db_connection(user_id) as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET username = ? WHERE id = ?",
                    (new_username, user_id)
                )
                conn.commit()
                return cursor.rowcount > 0
            except sqlite3.IntegrityError:
                print(f"Имя пользователя '{new_username}' уже занято.")
                return False
            except Exception as e:
                print(f"Ошибка при обновлении имени пользователя: {e}")
                return False
# Если telegram.py в папке backend
from backend.telegram import (
    TELEGRAM_BOT_TOKEN, BOT_USERNAME, get_bot_info, set_user_telegram_chat_id, 
    get_user_telegram_chat_id, disconnect_telegram, send_telegram_direct_message,
    init_telegram_bot, process_telegram_update, generate_connect_code, send_telegram_message
)
@app.route('/settings')
@login_required
def settings_page():
    """Страница настроек"""
    user_id = session['user_id']
    
    # Проверяем подключение Telegram
    telegram_connected = get_user_telegram_chat_id(user_id) is not None
    bot_info = get_bot_info()
    
    return render_template('settings.html', 
                         telegram_connected=telegram_connected,
                         telegram_bot_url=bot_info.get('bot_url', '#'))
@app.route('/api/telegram/connect', methods=['POST'])
@login_required
def connect_telegram():
    """Подключить Telegram аккаунт"""
    user_id = session['user_id']
    
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        
        if not chat_id:
            return jsonify({'success': False, 'error': 'Chat ID is required'})
        
        # Сохраняем связь user_id -> chat_id
        if set_user_telegram_chat_id(user_id, chat_id):
            # Отправляем приветственное сообщение
            send_telegram_direct_message(chat_id, 
                "✅ Ваш Telegram аккаунт успешно подключен к UniTool!\n\n"
                "Теперь вы будете получать уведомления о:\n"
                "• Автоматическом контроле рекламных кампаний\n"
                "• Изменениях статусов адсетов\n"
                "• Критических событиях и ошибках\n"
                "• Результатах оптимизации")
            
            return jsonify({'success': True, 'message': 'Telegram successfully connected'})
        else:
            return jsonify({'success': False, 'error': 'Failed to save Telegram connection'})
            
    except Exception as e:
        logger.error(f"Error connecting Telegram: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/telegram/disconnect', methods=['POST'])
@login_required
def disconnect_telegram_route():
    """Отключить Telegram уведомления"""
    user_id = session['user_id']
    
    try:
        if disconnect_telegram(user_id):
            return jsonify({'success': True, 'message': 'Telegram notifications disabled'})
        else:
            return jsonify({'success': False, 'error': 'Failed to disconnect Telegram'})
            
    except Exception as e:
        logger.error(f"Error disconnecting Telegram: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/telegram/status', methods=['GET'])
@login_required
def get_telegram_status():
    """Получить статус подключения Telegram"""
    user_id = session['user_id']
    
    try:
        chat_id = get_user_telegram_chat_id(user_id)
        connected = chat_id is not None
        
        return jsonify({
            'success': True,
            'connected': connected,
            'chat_id': chat_id
        })
        
    except Exception as e:
        logger.error(f"Error getting Telegram status: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/telegram/test', methods=['POST'])
@login_required
def test_telegram_notification():
    """Отправить тестовое уведомление"""
    user_id = session['user_id']
    
    try:
        test_message = "🔔 Тестовое уведомление от UniTool\n\nЭто сообщение подтверждает, что ваши Telegram уведомления настроены правильно!"
        
        # Используйте функцию send_telegram_message, которая уже импортирована
        if send_telegram_message(test_message, user_id=user_id):
            return jsonify({'success': True, 'message': 'Test notification sent'})
        else:
            return jsonify({'success': False, 'error': 'Failed to send test notification. Check if Telegram is connected.'})
            
    except Exception as e:
        logger.error(f"Error sending test Telegram notification: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/telegram/connect_link', methods=['GET'])
@login_required
def get_telegram_connect_link():
    """Получить уникальную ссылку для подключения Telegram"""
    user_id = session['user_id']
    
    try:
        bot_info = get_bot_info()
        if not bot_info.get('username'):
            return jsonify({'success': False, 'error': 'Bot username not configured'})
        
        # Создаем уникальный код для пользователя
        unique_code = generate_connect_code(user_id)
        
        connect_url = f"https://t.me/{bot_info['username']}?start={unique_code}"
        
        return jsonify({
            'success': True,
            'connect_url': connect_url,
            'bot_username': bot_info['username']
        })
        
    except Exception as e:
        logger.error(f"Error generating Telegram connect link: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Webhook для получения обновлений от Telegram"""
    try:
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            return jsonify({'status': 'error', 'message': 'Bot token not configured'})
        
        update = request.get_json()
        
        # Обрабатываем обновление (функция уже импортирована)
        process_telegram_update(update)
        
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Error in Telegram webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)})
def start_telegram_polling():
    """Запуск polling для Telegram бота (в отдельном потоке)"""
    import threading
    import time
    import requests
    
    def polling_worker():
        logger.info("🔄 Starting Telegram bot polling...")
        offset = 0
        
        while True:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                params = {
                    'offset': offset,
                    'timeout': 30,
                    'allowed_updates': ['message']
                }
                
                response = requests.get(url, params=params, timeout=35)
                data = response.json()
                
                if data.get('ok'):
                    for update in data['result']:
                        offset = update['update_id'] + 1
                        # Используйте функцию, импортированную в основном файле
                        process_telegram_update(update)
                
            except requests.exceptions.Timeout:
                continue
            except Exception as e:
                logger.error(f"Error in Telegram polling: {e}")
                time.sleep(5)
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
        polling_thread = threading.Thread(target=polling_worker, daemon=True)
        polling_thread.start()
        logger.info("✅ Telegram bot polling started")


if __name__ == '__main__':
    init_db()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Проверяем существование пользователя admin
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        admin_exists = cursor.fetchone()
    except Exception as e:
        print(f"Ошибка при инициализации тестового пользователя: {e}")
    start_telegram_polling() 
    # Запускаем приложение ОДИН раз
    app.run(host='0.0.0.0', debug=False, threaded=True)