from typing import Any, Dict, List
from venv import logger

from database import get_db_connection


def add_reserve_token(user_id: int, king: str, token: str) -> bool:
    """Добавляет резервный токен в базу данных"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Создаем таблицу если не существует
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
            
            cursor.execute(
                "INSERT OR IGNORE INTO reserve_tokens (user_id, king, token) VALUES (?, ?, ?)",
                (user_id, king, token)
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка добавления резервного токена: {e}")
        return False

def remove_reserve_token(user_id: int, king: str, token: str) -> bool:
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

def get_all_reserve_tokens(user_id: int) -> List[Dict[str, Any]]:
    """Получает все резервные токены пользователя"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Проверяем существование таблицы
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='reserve_tokens'
            """)
            table_exists = cursor.fetchone()
            
            if not table_exists:
                return []
            
            cursor.execute("SELECT king, token FROM reserve_tokens WHERE user_id = ?", (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения резервных токенов: {e}")
        return []

def add_account_to_reserve_token(user_id, king, token, account_id):
    """Добавляет аккаунт к резервному токену (с проверкой на существование)"""
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
            
            # Проверяем, существует ли уже такая запись
            cursor.execute("""
                SELECT id FROM reserve_token_accounts 
                WHERE user_id = ? AND king = ? AND token = ? AND account_id = ?
            """, (user_id, king, token, account_id))
            
            existing_record = cursor.fetchone()
            
            if existing_record:
                # Запись уже существует, обновляем updated_at
                cursor.execute("""
                    UPDATE reserve_token_accounts 
                    SET updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (existing_record['id'],))
                return True
            else:
                # Добавляем новую запись
                cursor.execute("""
                    INSERT INTO reserve_token_accounts 
                    (user_id, king, token, account_id) 
                    VALUES (?, ?, ?, ?)
                """, (user_id, king, token, account_id))
                return True
                
    except Exception as e:
        logger.error(f"Ошибка добавления аккаунта к токену: {e}")
        return False
def get_reserve_token_accounts(user_id: int, king: str, token: str) -> List[Dict[str, Any]]:
    """Получает аккаунты для резервного токена"""
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
            
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения аккаунтов токена: {e}")
        return []

def update_reserve_token_account_info(user_id: int, king: str, token: str, account_id: str, limits_info: Dict[str, Any]) -> bool:
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
                limits_info.get('name'),
                limits_info.get('status'),
                limits_info.get('spend_cap', 0),
                limits_info.get('spend', 0),
                limits_info.get('balance', 0),
                limits_info.get('daily_limit', 0),
                limits_info.get('remaining_limit', 0),
                limits_info.get('requests_today', 0),
                limits_info.get('requests_limit', 100),
                limits_info.get('requests_usage_percent', 0),
                user_id, king, token, account_id
            ))
            
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления информации об аккаунте: {e}")
        return False
def get_reserve_tokens(user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Получает резервные токены с аккаунтами для конкретного пользователя"""
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
            
            # Получаем все токены с информацией о лимитах для конкретного пользователя
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
        logger.error(f"Ошибка получения резервных токенов для пользователя {user_id}: {e}")
        return {}

def get_reserve_tokens_table(user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Возвращает резервные токены в формате для таблицы для конкретного пользователя"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='reserve_tokens'
            """)
            table_exists = cursor.fetchone()
            
            if not table_exists:
                return {}
            
            # Получаем все токены с информацией о лимитах для конкретного пользователя
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
            
            tokens_data = {}
            for row in cursor.fetchall():
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
            
            return result
            
    except Exception as e:
        logger.error(f"Ошибка получения токенов для таблицы пользователя {user_id}: {e}")
        return {}
   