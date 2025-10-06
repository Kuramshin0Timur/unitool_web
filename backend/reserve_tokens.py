# backend/reserve_tokens.py
import logging
import re
from typing import Any, Dict, List
from database import get_db_connection

logger = logging.getLogger(__name__)

# ----- Нормализаторы (единственный источник правды) -----
def normalize_token(token: str) -> str:
    """Убирает CR/LF, ведущие/хвостовые пробелы и лишние пробельные символы внутри."""
    if token is None:
        return ''
    t = str(token)
    # удаляем переносы строк и невидимые символы
    t = re.sub(r'[\r\n\t]+', '', t)
    # удаляем ведущие/концевые пробелы
    t = t.strip()
    # опционально: если в токене встречаются пробелы внутри — удаляем их тоже
    t = re.sub(r'\s+', '', t)
    return t

def normalize_account_id(account_id: str) -> str:
    """Возвращаем account_id в формате act_XXXXXXXXX."""
    if account_id is None:
        return ''
    s = str(account_id).strip()
    # Убираем act_ если есть
    if s.lower().startswith('act_'):
        s = s[4:]
    # Оставляем только цифры
    s = ''.join(ch for ch in s if ch.isdigit())
    # Возвращаем в формате act_XXXXXXXXX
    return f'act_{s}' if s else ''

# ----- CRUD-функции для резервных токенов -----

def add_reserve_token(user_id: int, king: str, token: str) -> bool:
    token = normalize_token(token)
    king = (king or '').strip()
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reserve_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    king TEXT NOT NULL,
                    token TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, king, token)
                )
            """)
            cursor.execute(
                "INSERT OR IGNORE INTO reserve_tokens (user_id, king, token) VALUES (?, ?, ?)",
                (user_id, king, token)
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка add_reserve_token: {e}")
        return False

def add_account_to_reserve_token(user_id: int, king: str, token: str, account_id: str) -> bool:
    token = normalize_token(token)
    king = (king or '').strip()
    account_clean = normalize_account_id(account_id)
    if not account_clean:
        logger.warning("Попытка добавить пустой account_id")
        return False
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            # создаём таблицу если нет
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
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, king, token, account_id)
                )
            """)
            cursor.execute("""
                INSERT OR IGNORE INTO reserve_token_accounts
                (user_id, king, token, account_id)
                VALUES (?, ?, ?, ?)
            """, (user_id, king, token, account_clean))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка add_account_to_reserve_token: {e}")
        return False

def remove_account_from_reserve_token(user_id: int, king: str, token: str, account_id: str) -> bool:
    token = normalize_token(token)
    account_clean = normalize_account_id(account_id)
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM reserve_token_accounts
                WHERE user_id = ? AND king = ? AND token = ? AND account_id = ?
            """, (user_id, king, token, account_clean))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка remove_account_from_reserve_token: {e}")
        return False

def get_reserve_token_accounts(user_id: int, king: str, token: str) -> List[Dict[str, Any]]:
    token = normalize_token(token)
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT account_id, name, status, spend_cap, amount_spent,
                       balance, daily_limit, remaining, requests_today,
                       requests_limit, requests_usage_percent
                FROM reserve_token_accounts
                WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Ошибка get_reserve_token_accounts: {e}")
        return []

def get_reserve_tokens(user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Возвращает структуру { king: [ { token:..., accounts:[...] }, ... ] }"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT rt.king, rt.token, rta.account_id, rta.name, rta.status,
                       rta.spend_cap, rta.amount_spent, rta.balance, rta.daily_limit,
                       rta.remaining, rta.requests_today, rta.requests_limit, rta.requests_usage_percent
                FROM reserve_tokens rt
                LEFT JOIN reserve_token_accounts rta ON rt.user_id = rta.user_id
                    AND rt.king = rta.king AND rt.token = rta.token
                WHERE rt.user_id = ?
                ORDER BY rt.king, rt.token
            """, (user_id,))
            rows = cursor.fetchall()
            tokens_by_king = {}
            for r in rows:
                king = r['king'] or 'Facebook_Default'
                token = r['token']
                if king not in tokens_by_king:
                    tokens_by_king[king] = []
                # find token entry
                entry = next((e for e in tokens_by_king[king] if e['token'] == token), None)
                if not entry:
                    entry = {'token': token, 'accounts': []}
                    tokens_by_king[king].append(entry)
                if r['account_id']:
                    entry['accounts'].append({
                        'account_id': r['account_id'],
                        'name': r['name'],
                        'status': r['status'],
                        'spend_cap': r['spend_cap'],
                        'amount_spent': r['amount_spent'],
                        'balance': r['balance'],
                        'daily_limit': r['daily_limit'],
                        'remaining': r['remaining'],
                        'requests_today': r['requests_today'],
                        'requests_limit': r['requests_limit'],
                        'requests_usage_percent': r['requests_usage_percent']
                    })
            return tokens_by_king
    except Exception as e:
        logger.error(f"Ошибка get_reserve_tokens: {e}")
        return {}

def update_reserve_token_king(user_id: int, old_king: str, new_king: str, token: str) -> bool:
    token = normalize_token(token)
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE reserve_tokens SET king = ?
                WHERE user_id = ? AND king = ? AND token = ?
            """, (new_king, user_id, old_king, token))
            cursor.execute("""
                UPDATE reserve_token_accounts SET king = ?
                WHERE user_id = ? AND king = ? AND token = ?
            """, (new_king, user_id, old_king, token))
            # update main tables as well
            cursor.execute("""
                UPDATE campaigns SET king = ?
                WHERE user_id = ? AND token = ? AND king = ?
            """, (new_king, user_id, token, old_king))
            cursor.execute("""
                UPDATE adsets SET king = ?
                WHERE user_id = ? AND token = ? AND king = ?
            """, (new_king, user_id, token, old_king))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка update_reserve_token_king: {e}")
        return False

def replace_token_everywhere(user_id: int, old_token: str, new_token: str, king: str, account_ids: List[str]=None) -> Dict[str,int]:
    """Замена токена везде (reserve_tokens, reserve_token_accounts, campaigns, adsets).
       Возвращает словарь с counts: campaigns_updated, adsets_updated, reserve_tokens_updated, reserve_accounts_updated"""
    old_token = normalize_token(old_token)
    new_token = normalize_token(new_token) if new_token else ''
    if not old_token:
        return {'error': 'old_token empty'}
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            campaigns_updated = adsets_updated = reserve_tokens_updated = reserve_accounts_updated = 0
            token_from = old_token
            token_to = new_token or old_token

            # 1) если new_token указан и отличается — обновляем reserve_tokens и reserve_token_accounts
            if new_token and new_token != old_token:
                cursor.execute("""
                    UPDATE reserve_tokens SET token = ?
                    WHERE user_id = ? AND token = ? AND king = ?
                """, (new_token, user_id, old_token, king))
                reserve_tokens_updated = cursor.rowcount

                cursor.execute("""
                    UPDATE reserve_token_accounts SET token = ?
                    WHERE user_id = ? AND token = ? AND king = ?
                """, (new_token, user_id, old_token, king))
                reserve_accounts_updated = cursor.rowcount

                cursor.execute("""
                    UPDATE campaigns SET token = ?
                    WHERE user_id = ? AND token = ? AND king = ?
                """, (new_token, user_id, old_token, king))
                campaigns_updated = cursor.rowcount

                cursor.execute("""
                    UPDATE adsets SET token = ?
                    WHERE user_id = ? AND token = ? AND king = ?
                """, (new_token, user_id, old_token, king))
                adsets_updated = cursor.rowcount

            # 2) если переданы account_ids — заменить их под token_to
            if account_ids is not None:
                # удаляем старые привязки для token_to (если есть)
                cursor.execute("""
                    DELETE FROM reserve_token_accounts
                    WHERE user_id = ? AND king = ? AND token = ?
                """, (user_id, king, token_to))
                # вставляем новые
                inserted = 0
                for acc in account_ids:
                    acc_clean = normalize_account_id(acc)
                    if not acc_clean:
                        continue
                    cursor.execute("""
                        INSERT OR IGNORE INTO reserve_token_accounts (user_id, king, token, account_id)
                        VALUES (?, ?, ?, ?)
                    """, (user_id, king, token_to, acc_clean))
                    if cursor.rowcount:
                        inserted += 1

            conn.commit()
            return {
                'campaigns_updated': campaigns_updated,
                'adsets_updated': adsets_updated,
                'reserve_tokens_updated': reserve_tokens_updated,
                'reserve_accounts_updated': reserve_accounts_updated
            }
    except Exception as e:
        logger.error(f"Ошибка replace_token_everywhere: {e}")
        return {'error': str(e)}

def delete_reserve_token_complete(user_id: int, king: str, token: str) -> bool:
    token = normalize_token(token)
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM reserve_token_accounts WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            cursor.execute("""
                DELETE FROM reserve_tokens WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            cursor.execute("""
                UPDATE campaigns SET king = 'Facebook_Default' WHERE user_id = ? AND token = ? AND king = ?
            """, (user_id, token, king))
            cursor.execute("""
                UPDATE adsets SET king = 'Facebook_Default' WHERE user_id = ? AND token = ? AND king = ?
            """, (user_id, token, king))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка delete_reserve_token_complete: {e}")
        return False

def get_reserve_tokens_table(user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Возвращает резервные токены в формате для таблицы"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT rt.king, rt.token, rta.account_id, rta.name, rta.status,
                       rta.spend_cap, rta.amount_spent, rta.balance, rta.daily_limit,
                       rta.remaining, rta.requests_today, rta.requests_limit, rta.requests_usage_percent
                FROM reserve_tokens rt
                LEFT JOIN reserve_token_accounts rta ON rt.user_id = rta.user_id
                    AND rt.king = rta.king AND rt.token = rta.token
                WHERE rt.user_id = ?
                ORDER BY rt.king, rt.token
            """, (user_id,))
            rows = cursor.fetchall()
            tokens_by_king = {}
            for r in rows:
                king = r['king'] or 'Facebook_Default'
                token = r['token']
                if king not in tokens_by_king:
                    tokens_by_king[king] = []
                # find token entry
                entry = next((e for e in tokens_by_king[king] if e['token'] == token), None)
                if not entry:
                    entry = {'token': token, 'accounts': []}
                    tokens_by_king[king].append(entry)
                if r['account_id']:
                    entry['accounts'].append({
                        'account_id': r['account_id'],
                        'name': r['name'],
                        'status': r['status'],
                        'spend_cap': r['spend_cap'],
                        'amount_spent': r['amount_spent'],
                        'balance': r['balance'],
                        'daily_limit': r['daily_limit'],
                        'remaining': r['remaining'],
                        'requests_today': r['requests_today'],
                        'requests_limit': r['requests_limit'],
                        'requests_usage_percent': r['requests_usage_percent']
                    })
            return tokens_by_king
    except Exception as e:
        logger.error(f"Ошибка get_reserve_tokens_table: {e}")
        return {}
