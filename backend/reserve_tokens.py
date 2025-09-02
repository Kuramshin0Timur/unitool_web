from venv import logger

from database import get_db_connection


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
                    spend_cap REAL DEFAULT 0,
                    amount_spent REAL DEFAULT 0,
                    remaining REAL DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(user_id, king, token, account_id)
                )
            """)
            
            cursor.execute("""
                INSERT OR IGNORE INTO reserve_token_accounts 
                (user_id, king, token, account_id) 
                VALUES (?, ?, ?, ?)
            """, (user_id, king, token, account_id))
            
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка добавления аккаунта к токену: {e}")
        return False

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

def get_reserve_token_accounts(user_id, king, token):
    """Получает аккаунты для резервного токена"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT account_id, spend_cap, amount_spent, remaining, status 
                FROM reserve_token_accounts 
                WHERE user_id = ? AND king = ? AND token = ?
            """, (user_id, king, token))
            
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения аккаунтов токена: {e}")
        return []

def update_reserve_token_account_info(user_id, king, token, account_id, limits_info):
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
