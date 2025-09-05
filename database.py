import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from venv import logger

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path("unitool.db")

lock = threading.Lock()

def get_db_connection(user_id: Optional[int] = None) -> sqlite3.Connection:
    """
    Создает и возвращает соединение с базой данных с обработкой ошибок
    
    Args:
        user_id: ID пользователя для установки application_id
        
    Returns:
        sqlite3.Connection: соединение с базой данных
        
    Raises:
        sqlite3.Error: если не удалось установить соединение
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Устанавливаем параметры соединения
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        
        if user_id:
            try:
                conn.execute(f"PRAGMA application_id = {user_id}")
            except sqlite3.Error as e:
                print(f"Warning: Could not set application_id: {e}")
                
        return conn
        
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        raise

def init_db():
    """Инициализирует базу данных с нужными таблицами"""
    with lock:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Сначала создаем таблицу users если не существует
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # Таблица настроек - ОБНОВЛЕННАЯ ВЕРСИЯ
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sync_api_key TEXT,
                proxy TEXT,
                use_proxy BOOLEAN DEFAULT TRUE,
                auto_refresh_campaigns BOOLEAN DEFAULT TRUE,
                auto_refresh_adsets BOOLEAN DEFAULT TRUE,
                auto_refresh_interval INTEGER DEFAULT 5,
                telegram_bot_token TEXT,
                telegram_chat_id TEXT,
                keitaro_api_key TEXT DEFAULT '',
                keitaro_domain TEXT DEFAULT 'uniaffnu.com',
                keitaro_range_days INTEGER DEFAULT 1,
                auto_headline_optimization BOOLEAN DEFAULT FALSE,
                headline_optimization_interval INTEGER DEFAULT 4,
                account_timezone TEXT DEFAULT '-7',  -- НОВОЕ ПОЛЕ
                balance_check_enabled BOOLEAN DEFAULT TRUE,  -- НОВОЕ ПОЛЕ
                warning_threshold REAL DEFAULT 50.0,  -- НОВОЕ ПОЛЕ
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id)
            )
            """)
            
            # Таблица кампаний
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                king TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                token TEXT,
                spend REAL DEFAULT 0,
                leads INTEGER DEFAULT 0,
                cpa REAL DEFAULT 0,
                ucpc REAL DEFAULT 0,
                cpc REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, campaign_id)
            )
            """)
            
            # Таблица адсетов - ОБНОВЛЕННАЯ ВЕРСИЯ
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS adsets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                adset_id TEXT NOT NULL,
                campaign_id TEXT,
                status TEXT DEFAULT 'PAUSED',
                account_id TEXT,
                token TEXT,
                budget REAL DEFAULT 0,
                geo TEXT DEFAULT 'N/A',
                ucpc REAL DEFAULT 0,
                cpc REAL DEFAULT 0,  
                cpm REAL DEFAULT 0,
                spend REAL DEFAULT 0,
                cpa REAL DEFAULT 0,
                leads INTEGER DEFAULT 0,
                king TEXT DEFAULT 'Facebook',
                effective_status TEXT DEFAULT '',
                ad_name TEXT DEFAULT '',
                manual_pause INTEGER DEFAULT 0,
                auto_budget_increase INTEGER DEFAULT 0,
                auto_budget_decrease INTEGER DEFAULT 0,
                max_budget REAL DEFAULT 0,
                min_budget REAL DEFAULT 0,
                budget_increase_step REAL DEFAULT 1.2,
                budget_decrease_step REAL DEFAULT 0.8,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, adset_id)
            )
            """)
            
            # Таблица GEO конфигурации
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS geo_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                geo_code TEXT NOT NULL,
                spend_zero_leads REAL NOT NULL,
                cpa_red REAL NOT NULL,
                cpa_green REAL NOT NULL,
                cpa_orange REAL NOT NULL,
                UNIQUE(user_id, geo_code)
            )
            """)
            
            # Таблица GEO правил
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
            
            # Таблица маппинга кампаний
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS campaign_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                facebook_campaign_id TEXT NOT NULL,
                keitaro_key TEXT NOT NULL,
                campaign_name TEXT,
                match_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, facebook_campaign_id, keitaro_key)
            )
            """)
            
            # Таблица резервных токенов
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
            # Таблица правил бюджета
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS budget_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                geo_code TEXT NOT NULL,
                increase_budget BOOLEAN DEFAULT 0,
                decrease_budget BOOLEAN DEFAULT 0,
                max_budget_multiplier REAL DEFAULT 2.0,
                min_budget REAL DEFAULT 5.0,
                increase_threshold_cpa REAL DEFAULT 0.7,
                decrease_threshold_cpa REAL DEFAULT 1.3,
                min_leads_for_increase INTEGER DEFAULT 3,
                budget_increase_step REAL DEFAULT 1.2,
                budget_decrease_step REAL DEFAULT 0.8,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, geo_code)
            )
            """)
            
            # Создаем индекс для улучшения производительности
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_adsets_user_status ON adsets (user_id, status)
            """)
            
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaigns_user_account ON campaigns (user_id, account_id)
            """)
            
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_settings_user ON settings (user_id)
            """)
            
            conn.commit()
            
            # Создаем тестового пользователя если не существует
            try:
                cursor.execute("SELECT id FROM users WHERE username = 'admin'")
                admin_exists = cursor.fetchone()
                
                if not admin_exists:
                    # Создаем пользователя admin с паролем 'admin'
                    password_hash = generate_password_hash('admin')
                    cursor.execute(
                        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        ('admin', password_hash)
                    )
                    
                    # Создаем настройки для пользователя
                    cursor.execute(
                        """INSERT INTO settings (
                            user_id, account_timezone, balance_check_enabled, warning_threshold
                        ) VALUES (?, ?, ?, ?)""",
                        (cursor.lastrowid, '-7', 1, 50.0)
                    )
                    
                    conn.commit()
                    print("Создан тестовый пользователь: admin/admin")
                    
            except Exception as e:
                print(f"Ошибка создания тестового пользователя: {e}")

def create_user(username: str, password: str) -> Optional[int]:
    """Создает нового пользователя и возвращает его ID"""
    with lock:
        with get_db_connection() as conn:
            try:
                password_hash = generate_password_hash(password)
                cursor = conn.cursor()
                
                # Сначала создаем пользователя
                cursor.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash)
                )
                user_id = cursor.lastrowid
                
                # Затем создаем настройки для пользователя
                cursor.execute("""
                INSERT INTO settings (
                    user_id, sync_api_key, proxy, use_proxy,
                    auto_refresh_campaigns, auto_refresh_adsets,
                    telegram_bot_token, telegram_chat_id,
                    keitaro_api_key, keitaro_domain, keitaro_range_days
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, '', '', 1, 1, 1, '', '', 
                    '', 'uniaffnu.com', 1  # Новые поля Keitaro
                ))
                
                conn.commit()
                return user_id
            except sqlite3.IntegrityError as e:
                logger.error(f"Ошибка создания пользователя: {e}")
                return None
def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Аутентифицирует пользователя и возвращает его данные"""
    with lock:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                return dict(user)
            return None


