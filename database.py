import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from venv import logger

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path("unitool.db")
lock = threading.Lock()
def add_user_adset(user_id: int, data: Dict[str, Any]):
    """Добавляет новый адсет для пользователя"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Убедимся, что все обязательные поля присутствуют
            required_fields = ['name', 'adset_id', 'campaign_id', 'account_id', 'token', 'king']
            for field in required_fields:
                if field not in data:
                    data[field] = '' if field != 'king' else 'Facebook'
            
            try:
                cursor.execute("""
                INSERT OR REPLACE INTO adsets (
                    user_id, name, adset_id, ucpc, spend, cpa, status, geo, token, 
                    leads, manual_pause, king, effective_status, ad_name, budget,
                    campaign_id, account_id, auto_budget_increase, auto_budget_decrease,
                    max_budget, min_budget, budget_increase_step, budget_decrease_step
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    data.get('name', ''),
                    data.get('adset_id', ''),
                    data.get('ucpc', 0),
                    data.get('spend', 0),
                    data.get('cpa', 0),
                    data.get('status', 'PAUSED'),
                    data.get('geo', 'N/A'),
                    data.get('token', ''),
                    data.get('leads', 0),
                    data.get('manual_pause', 0),
                    data.get('king', 'Facebook'),
                    data.get('effective_status', ''),
                    data.get('ad_name', ''),
                    data.get('budget', 0),
                    data.get('campaign_id', ''),
                    data.get('account_id', ''),
                    data.get('auto_budget_increase', 0),
                    data.get('auto_budget_decrease', 0),
                    data.get('max_budget', 0),
                    data.get('min_budget', 0),
                    data.get('budget_increase_step', 1.2),
                    data.get('budget_decrease_step', 0.8)
                ))

                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error(f"Error adding adset: {e}")
                raise ValueError(f"Database error: {str(e)}")
def get_db_connection(user_id=None):
    """Создает и возвращает соединение с базой данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Устанавливаем user_id для соединения (если нужно)
    if user_id:
        # PRAGMA не поддерживает параметризованные запросы, поэтому форматируем строку
        conn.execute(f"PRAGMA application_id = {user_id}")
    
    return conn
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path("unitool.db")
lock = threading.Lock()
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

def get_user_geo_rules(user_id):
    """Получает GEO правила из новой таблицы geo_rules"""
    geo_rules = {}
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Проверяем существование таблицы
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='geo_rules'
            """)
            table_exists = cursor.fetchone()
            
            if table_exists:
                cursor.execute("""
                    SELECT geo_code, max_cpa, min_spend, max_leads_threshold,
                           extended_spend_threshold, max_ucpc, max_ucpc_spend
                    FROM geo_rules 
                    WHERE user_id = ?
                """, (user_id,))
                
                for row in cursor.fetchall():
                    geo_rules[row['geo_code']] = {
                        'max_cpa': row['max_cpa'],
                        'min_spend': row['min_spend'],
                        'max_leads_threshold': row['max_leads_threshold'],
                        'extended_spend_threshold': row['extended_spend_threshold'],
                        'max_ucpc': row['max_ucpc'],
                        'max_ucpc_spend': row['max_ucpc_spend']
                    }
    
    except Exception as e:
        logger.error(f"Ошибка получения GEO правил: {e}")
    
    return geo_rules
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
            
            # Таблица настроек
           # В функции init_db() обновите таблицу settings:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sync_api_key TEXT,
                proxy TEXT,
                use_proxy BOOLEAN DEFAULT TRUE,
                auto_refresh_campaigns BOOLEAN DEFAULT TRUE,
                auto_refresh_adsets BOOLEAN DEFAULT TRUE,
                auto_refresh_interval INTEGER DEFAULT 5,  -- НОВОЕ ПОЛЕ: интервал в минутах
                telegram_bot_token TEXT,
                telegram_chat_id TEXT,
                keitaro_api_key TEXT DEFAULT '',
                keitaro_domain TEXT DEFAULT 'uniaffnu.com',
                keitaro_range_days INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id)
            )
            """)
            
            # Таблица кампаний - УДАЛЯЕМ ВНЕШНИЙ КЛЮЧ НА user_id
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
                cpc REAL DEFAULT 0,  -- ADD THIS COLUMN
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
                FOREIGN KEY (user_id) REFERENCES users (id)
                UNIQUE(user_id, adset_id)
            )
            """)
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
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS campaign_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                facebook_campaign_id TEXT NOT NULL,
                keitaro_key TEXT NOT NULL,  -- Изменили keitaro_sub_id на keitaro_key
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
                UNIQUE(user_id, king, token)
            )
            """)
            
    # Добавляем новые поля в таблицу adsets
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
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """)
            
         
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
            
            conn.commit()
# Добавьте эти функции в database.py

def get_adset_budget_settings(user_id: int, adset_id: str) -> Optional[Dict[str, Any]]:
    """Получает настройки авто-бюджета для адсета"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT auto_budget_increase, auto_budget_decrease, 
                       max_budget, min_budget, budget_increase_step, 
                       budget_decrease_step
                FROM adsets 
                WHERE user_id = ? AND adset_id = ?
            """, (user_id, adset_id))
            
            row = cursor.fetchone()
            if row:
                return {
                    'auto_budget_increase': bool(row['auto_budget_increase']),
                    'auto_budget_decrease': bool(row['auto_budget_decrease']),
                    'max_budget': float(row['max_budget'] or 0),
                    'min_budget': float(row['min_budget'] or 0),
                    'budget_increase_step': float(row['budget_increase_step'] or 1.2),
                    'budget_decrease_step': float(row['budget_decrease_step'] or 0.8)
                }
            return None
    except Exception as e:
        logger.error(f"Ошибка получения настроек бюджета: {e}")
        return None

def update_adset_budget_settings(user_id: int, adset_id: str, settings: Dict[str, Any]) -> bool:
    """Обновляет настройки авто-бюджета для адсета"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE adsets 
                SET auto_budget_increase = ?, auto_budget_decrease = ?,
                    max_budget = ?, min_budget = ?, budget_increase_step = ?,
                    budget_decrease_step = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND adset_id = ?
            """, (
                int(settings.get('auto_budget_increase', False)),
                int(settings.get('auto_budget_decrease', False)),
                float(settings.get('max_budget', 0)),
                float(settings.get('min_budget', 0)),
                float(settings.get('budget_increase_step', 1.2)),
                float(settings.get('budget_decrease_step', 0.8)),
                user_id, adset_id
            ))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления настроек бюджета: {e}")
        return False
# In database.py, update the function
def get_adsets_for_auto_budget(user_id: int) -> List[Dict[str, Any]]:
    """Получает адсеты для авто-бюджета с токенами"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*, c.token 
                FROM adsets a
                LEFT JOIN campaigns c ON a.campaign_id = c.campaign_id AND a.user_id = c.user_id
                WHERE a.user_id = ? AND a.status = 'ACTIVE'
                AND (a.auto_budget_increase = 1 OR a.auto_budget_decrease = 1)
            """, (user_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения адсетов для авто-бюджета: {e}")
        return []
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

def get_user_campaigns(user_id: int) -> List[Dict[str, Any]]:
    """Возвращает список кампаний пользователя"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns WHERE user_id = ?", (user_id,))
            return [dict(row) for row in cursor.fetchall()]

def get_user_adsets(user_id: int) -> List[Dict[str, Any]]:
    """Возвращает список адсетов пользователя с гарантированным наличием поля status"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id, user_id, name, adset_id, campaign_id, 
                    COALESCE(effective_status, status, 'UNKNOWN') as status,
                    account_id, token, budget, geo, ucpc, cpc, spend, cpa, leads, 
                    king, effective_status, ad_name, manual_pause,
                    auto_budget_increase, auto_budget_decrease,
                    max_budget, min_budget, budget_increase_step, budget_decrease_step,
                    created_at, updated_at
                FROM adsets 
                WHERE user_id = ?
            """, (user_id,))
            
            adsets = []
            for row in cursor.fetchall():
                adset = dict(row)
                # Гарантируем, что статус всегда есть и является строкой
                adset['status'] = str(adset.get('status', 'UNKNOWN')).strip()
                adsets.append(adset)
            
            return adsets

def get_user_geo_config(user_id: int) -> Dict[str, Dict[str, float]]:
    """Возвращает конфигурацию GEO пользователя"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM geo_config WHERE user_id = ?", (user_id,))
            return {row['geo_code']: {
                'spend_zero_leads': row['spend_zero_leads'],
                'cpa_red': row['cpa_red'],
                'cpa_green': row['cpa_green'],
                'cpa_orange': row['cpa_orange']
            } for row in cursor.fetchall()}
            
def get_user_settings(user_id: int) -> Dict[str, Any]:
    """Возвращает настройки пользователя"""
    default_settings = {
        'sync_api_key': '',
        'proxy': '',
        'use_proxy': True,
        'auto_refresh_campaigns': True,
        'auto_refresh_adsets': True,
        'auto_refresh_interval': 15,
        'telegram_bot_token': '',
        'telegram_chat_id': '',
        'keitaro_api_key': '',
        'keitaro_domain': 'uniaffnu.com',
        'keitaro_range_days': 1
    }
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            if row:
                user_settings = dict(row)
                # Убедимся, что все ключи присутствуют
                for key in default_settings.keys():
                    if key not in user_settings:
                        user_settings[key] = default_settings[key]
                return user_settings
            else:
                # Создаем запись настроек, если ее нет
                cursor.execute("""
                INSERT INTO settings (user_id, keitaro_api_key, keitaro_domain, keitaro_range_days)
                VALUES (?, ?, ?, ?)
                """, (user_id, '', 'uniaffnu.com', 1))
                conn.commit()
                return default_settings
                
    except Exception as e:
        logger.error(f"Ошибка получения настроек: {e}")
        return default_settings
def update_user_settings(user_id: int, data: Dict[str, Any]):
    """Обновляет настройки пользователя"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            query = """
            UPDATE settings SET 
                sync_api_key = :sync_api_key,
                proxy = :proxy,
                use_proxy = :use_proxy,
                auto_refresh_campaigns = :auto_refresh_campaigns,
                auto_refresh_adsets = :auto_refresh_adsets,
                auto_refresh_interval = :auto_refresh_interval,
                telegram_bot_token = :telegram_bot_token,
                telegram_chat_id = :telegram_chat_id,
                keitaro_api_key = :keitaro_api_key,
                keitaro_domain = :keitaro_domain,
                keitaro_range_days = :keitaro_range_days
            WHERE user_id = :user_id
            """
            
            data['user_id'] = user_id
            cursor.execute(query, data)
            conn.commit()
def add_user_campaign(user_id: int, data: Dict[str, Any]):
    """Добавляет кампанию с проверкой данных"""
    required_fields = {
        'king': str,
        'name': str,
        'status': str,
        'campaign_id': str,
        'account_id': str
    }
    
    # Проверяем обязательные поля
    for field, field_type in required_fields.items():
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
        if not isinstance(data[field], field_type):
            raise ValueError(f"Invalid type for field {field}")
    
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            try:
                # Сначала проверяем существование пользователя
                cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
                if not cursor.fetchone():
                    raise ValueError(f"User with ID {user_id} does not exist")
                
                cursor.execute("""
                INSERT OR REPLACE INTO campaigns (
                    user_id, king, name, status, campaign_id, account_id, token
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    data['king'],
                    data['name'],
                    data['status'],
                    data['campaign_id'],
                    data['account_id'],
                    data.get('token', '')
                ))
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error(f"Error adding campaign: {e}")
                raise ValueError(f"Database error: {str(e)}")

def update_campaign_stats(user_id, campaign_id, spend=None, leads=None, cpa=None, cpc=None, ucpc=None):
    """Обновляет статистику кампании с CPC из Facebook"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            updates = []
            params = {'user_id': user_id, 'campaign_id': campaign_id}
            
            if spend is not None:
                updates.append("spend = :spend")
                params['spend'] = spend
            
            if leads is not None:
                updates.append("leads = :leads")
                params['leads'] = leads
                
            if cpa is not None:
                updates.append("cpa = :cpa")
                params['cpa'] = cpa
                
            if cpc is not None:  # CPC из Facebook
                updates.append("cpc = :cpc")
                params['cpc'] = cpc
                
            if ucpc is not None:
                updates.append("ucpc = :ucpc")
                params['ucpc'] = ucpc
            
            if updates:
                query = f"""
                UPDATE campaigns SET
                    {', '.join(updates)}
                WHERE user_id = :user_id AND campaign_id = :campaign_id
                """
                cursor.execute(query, params)
                conn.commit()
                logger.info(f"Обновлена статистика кампании {campaign_id} с CPC из Facebook: {cpc}")

def update_user_campaign_status(user_id: int, campaign_id: str, status: str):
    """Обновляет статус кампании пользователя"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE campaigns SET status = ? 
            WHERE user_id = ? AND campaign_id = ?
            """, (status, user_id, campaign_id))
            conn.commit()
def add_user_adset(user_id: int, data: Dict[str, Any]):
    """Добавляет новый адсет для пользователя"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Убедимся, что все обязательные поля присутствуют
            required_fields = ['name', 'adset_id', 'campaign_id', 'account_id', 'token', 'king']
            for field in required_fields:
                if field not in data:
                    data[field] = '' if field != 'king' else 'Facebook'
            
            try:
                cursor.execute("""
                INSERT OR REPLACE INTO adsets (
                    user_id, name, adset_id, ucpc, cpc, spend, cpa, status, geo, token, 
                    leads, manual_pause, king, effective_status, ad_name, budget,
                    campaign_id, account_id, auto_budget_increase, auto_budget_decrease,
                    max_budget, min_budget, budget_increase_step, budget_decrease_step
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    data.get('name', ''),
                    data.get('adset_id', ''),
                    data.get('ucpc', 0),
                    data.get('cpc', 0),  # ADD CPC VALUE
                    data.get('spend', 0),
                    data.get('cpa', 0),
                    data.get('status', 'PAUSED'),
                    data.get('geo', 'N/A'),
                    data.get('token', ''),
                    data.get('leads', 0),
                    data.get('manual_pause', 0),
                    data.get('king', 'Facebook'),
                    data.get('effective_status', ''),
                    data.get('ad_name', ''),
                    data.get('budget', 0),
                    data.get('campaign_id', ''),
                    data.get('account_id', ''),
                    data.get('auto_budget_increase', 0),
                    data.get('auto_budget_decrease', 0),
                    data.get('max_budget', 0),
                    data.get('min_budget', 0),
                    data.get('budget_increase_step', 1.2),
                    data.get('budget_decrease_step', 0.8)
                ))

                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error(f"Error adding adset: {e}")
                raise ValueError(f"Database error: {str(e)}")
def update_user_adset_status(user_id: int, adset_id: str, status: str):
    """Обновляет статус адсета пользователя"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE adsets SET status = ? 
            WHERE user_id = ? AND adset_id = ?
            """, (status, user_id, adset_id))
            conn.commit()
# Добавьте эти функции в database.py

def get_all_users():
    """Получает список всех пользователей"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, created_at FROM users ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей: {e}")
        return []

def get_user_accounts_stats(user_id):
    """Получает статистику по аккаунтам пользователя"""
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Получаем уникальные аккаунты
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
            
            return accounts
    except Exception as e:
        logger.error(f"Ошибка получения статистики аккаунтов: {e}")
        return []

def get_all_accounts_stats():
    """Получает статистику по всем аккаунтам всех пользователей"""
    users = get_all_users()
    all_accounts = []
    
    for user in users:
        user_id = user['id']
        accounts = get_user_accounts_stats(user_id)
        
        for account in accounts:
            account['user_id'] = user_id
            account['username'] = user['username']
            all_accounts.append(account)
    
    return all_accounts

def get_account_limits_info(account_id, access_token):
    """Получает информацию о лимитах аккаунта из Facebook API"""
    try:
        clean_account_id = account_id.replace('act_', '')
        url = f"https://graph.facebook.com/v18.0/act_{clean_account_id}"
        
        params = {
            'fields': 'id,name,account_status,amount_spent,balance,spend_cap,daily_spend_limit,'
                     'adtrust_dsl,min_daily_budget,min_campaign_group_spend_cap',
            'access_token': access_token
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if 'error' in data:
            return None
        
        # Получаем информацию о лимитах запросов из заголовков
        usage_info = response.headers.get('x-business-use-case-usage', '{}')
        calls_usage = 0
        calls_limit = 100
        
        try:
            usage_data = json.loads(usage_info)
            if usage_data and isinstance(usage_data, dict):
                for key in usage_data.keys():
                    call_count = usage_data[key][0].get('call_count', 0)
                    total_time = usage_data[key][0].get('total_time', 0)
                    calls_usage = max(calls_usage, call_count)
        except:
            pass
        
        return {
            'account_id': clean_account_id,
            'name': data.get('name', 'N/A'),
            'status': data.get('account_status', 'UNKNOWN'),
            'spend': float(data.get('amount_spent', 0)) / 100,
            'balance': float(data.get('balance', 0)) / 100,
            'spend_cap': float(data.get('spend_cap', data.get('daily_spend_limit', 0))) / 100,
            'daily_limit': float(data.get('daily_spend_limit', 0)) / 100,
            'min_daily_budget': float(data.get('min_daily_budget', 0)) / 100,
            'requests_today': calls_usage,
            'requests_limit': calls_limit,
            'requests_usage_percent': round((calls_usage / calls_limit) * 100, 1) if calls_limit > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения лимитов для аккаунта {account_id}: {e}")
        return None
def update_user_adset_budget(user_id: int, adset_id: str, budget: float):
    """Обновляет бюджет адсета пользователя в базе данных"""
    with lock:
        try:
            with get_db_connection(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                UPDATE adsets SET budget = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE user_id = ? AND adset_id = ?
                """, (budget, user_id, adset_id))
                conn.commit()
                logger.info(f"Бюджет обновлен в БД: adset_id={adset_id}, budget=${budget:.2f}")
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления бюджета в БД: {e}")
            return False
def add_user_geo_config(user_id: int, data: Dict[str, Any]):
    """Добавляет или обновляет конфигурацию GEO пользователя"""
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            data['user_id'] = user_id
            
            cursor.execute("""
            SELECT id FROM geo_config 
            WHERE user_id = ? AND geo_code = ?
            """, (user_id, data['geo_code']))
            exists = cursor.fetchone()
            
            if exists:
                cursor.execute("""
                UPDATE geo_config SET 
                    spend_zero_leads = :spend_zero_leads,
                    cpa_red = :cpa_red,
                    cpa_green = :cpa_green,
                    cpa_orange = :cpa_orange
                WHERE user_id = :user_id AND geo_code = :geo_code
                """, data)
            else:
                cursor.execute("""
                INSERT INTO geo_config (
                    user_id, geo_code, spend_zero_leads, cpa_red, cpa_green, cpa_orange
                ) VALUES (
                    :user_id, :geo_code, :spend_zero_leads, :cpa_red, :cpa_green, :cpa_orange
                )
                """, data)
            
            conn.commit()

    """Генерирует тестовые данные для указанного пользователя"""
    import random
    
    with lock:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Очищаем данные пользователя
            cursor.execute("DELETE FROM campaigns WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM adsets WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM geo_config WHERE user_id = ?", (user_id,))
            
            # Добавляем GEO конфигурации
            geo_codes = ['US', 'RU', 'DE', 'FR', 'IT', 'TR', 'BR', 'IN', 'JP', 'CN']
            for geo in geo_codes:
                cursor.execute("""
                INSERT INTO geo_config (
                    user_id, geo_code, spend_zero_leads, cpa_red, cpa_green, cpa_orange
                ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    geo,
                    round(random.uniform(10, 50), 2),
                    round(random.uniform(20, 100), 2),
                    round(random.uniform(5, 20), 2),
                    round(random.uniform(15, 50), 2)
                ))
            
            # Добавляем кампании
            kings = ['KING1', 'KING2', 'KING3', 'KING4', 'KING5']
            statuses = ['ACTIVE', 'PAUSED']
            
            for i in range(1, 21):
                king = random.choice(kings)
                status = random.choice(statuses)
                cursor.execute("""
                INSERT INTO campaigns (
                    user_id, king, name, status, campaign_id, account_id, token
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    king,
                    f"Campaign {i} {king}",
                    status,
                    f"campaign_{i}",
                    f"account_{random.randint(1, 5)}",
                    f"token_{random.randint(1, 10)}"
                ))
            
            # Добавляем адсеты
            geos = ['US', 'RU', 'DE', 'FR', 'IT', 'TR', 'BR', 'IN', 'JP', 'CN']
            ad_names = ["Ad 1", "Ad 2", "Ad 3", "Ad 4", "Ad 5"]
            
            for i in range(1, 101):
                geo = random.choice(geos)
                king = random.choice(kings)
                status = random.choice(statuses)
                effective_status = random.choice(["ACTIVE", "PAUSED", "DISAPPROVED", "PENDING_REVIEW"])
                account_id = f"account_{random.randint(1, 5)}"
                cursor.execute("""
                INSERT INTO adsets (
                    user_id, name, adset_id, ucpc, spend, cpa, status, geo, token, 
                    leads, manual_pause, king, effective_status, ad_name, budget,campaign_id, account_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    f"AdSet {i} {geo}",
                    f"adset_{i}",
                    round(random.uniform(0.1, 5.0), 2),
                    round(random.uniform(10, 500), 2),
                    round(random.uniform(5, 100), 2),
                    status,
                    geo,
                    f"token_{random.randint(1, 10)}",
                    random.randint(0, 50),
                    random.choice([0, 1]),
                    king,
                    effective_status,
                    random.choice(ad_names),
                    round(random.uniform(5, 50), 2),
                    f"campaign_{random.randint(1, 20)}",  # campaign_id
                     account_id  # <-- теперь account_id есть
                ))
            
            conn.commit()
        finally:
            conn.close()
    """Генерирует тестовые данные для указанного пользователя"""
    import random
    
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Очищаем данные пользователя
            cursor.execute("DELETE FROM campaigns WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM adsets WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM geo_config WHERE user_id = ?", (user_id,))
            
            # Добавляем GEO конфигурации
            geo_codes = ['US', 'RU', 'DE', 'FR', 'IT', 'TR', 'BR', 'IN', 'JP', 'CN']
            for geo in geo_codes:
                cursor.execute("""
                INSERT INTO geo_config (
                    user_id, geo_code, spend_zero_leads, cpa_red, cpa_green, cpa_orange
                ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    geo,
                    random.uniform(10, 50),
                    random.uniform(20, 100),
                    random.uniform(5, 20),
                    random.uniform(15, 50)
                ))
            
            # Добавляем кампании
            kings = ['KING1', 'KING2', 'KING3', 'KING4', 'KING5']
            statuses = ['ACTIVE', 'PAUSED']
            
            for i in range(1, 21):
                king = random.choice(kings)
                status = random.choice(statuses)
                cursor.execute("""
                INSERT INTO campaigns (
                    user_id, king, name, status, campaign_id, account_id, token
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    king,
                    f"Campaign {i} {king}",
                    status,
                    f"campaign_{i}",
                    f"account_{random.randint(1, 5)}",
                    f"token_{random.randint(1, 10)}"
                ))
            
            # Добавляем адсеты
            geos = ['US', 'RU', 'DE', 'FR', 'IT', 'TR', 'BR', 'IN', 'JP', 'CN']
            ad_names = ["Ad 1", "Ad 2", "Ad 3", "Ad 4", "Ad 5"]
            
            for i in range(1, 101):
                geo = random.choice(geos)
                king = random.choice(kings)
                status = random.choice(statuses)
                effective_status = random.choice(["ACTIVE", "PAUSED", "DISAPPROVED", "PENDING_REVIEW"])
                
                cursor.execute("""
                INSERT INTO adsets (
                    user_id, name, adset_id, ucpc, spend, cpa, status, geo, token, 
                    leads, manual_pause, king, effective_status, ad_name, budget
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    f"AdSet {i} {geo}",
                    f"adset_{i}",
                    round(random.uniform(0.1, 5.0), 2),
                    round(random.uniform(10, 500), 2),
                    round(random.uniform(5, 100), 2),
                    status,
                    geo,
                    f"token_{random.randint(1, 10)}",
                    random.randint(0, 50),
                    random.choice([0, 1]),
                    king,
                    effective_status,
                    random.choice(ad_names),
                    round(random.uniform(5, 50), 2)
                ))
            
            conn.commit()