import random
import sqlite3
from datetime import datetime, timedelta

from database import get_db_connection, init_db


def generate_test_data():
    """Генерирует тестовые данные для базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Очищаем таблицы
    cursor.execute("DELETE FROM campaigns")
    cursor.execute("DELETE FROM adsets")
    cursor.execute("DELETE FROM geo_config")
    cursor.execute("DELETE FROM settings")
    
    # Добавляем настройки
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
                telegram_bot_token TEXT,
                telegram_chat_id TEXT,
                keitaro_api_key TEXT,
                keitaro_domain TEXT DEFAULT 'uniaffnu.com',
                keitaro_range_days INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id)
            )
            """)
    # В функции init_db() добавьте:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS campaign_mapping (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        facebook_campaign_id TEXT NOT NULL,
        keitaro_sub_id TEXT NOT NULL,
        campaign_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        UNIQUE(user_id, facebook_campaign_id, keitaro_sub_id)
    )
    """)
    cursor.execute("""
    INSERT INTO users (username, password)
    VALUES (?, ?)
    """, ("admin", "admin"))
    user_id = cursor.lastrowid  # сохраняем ID

    # Добавляем GEO конфигурации
    geo_codes = ['US', 'RU', 'DE', 'FR', 'IT', 'TR', 'BR', 'IN', 'JP', 'CN']
    for geo in geo_codes:
        cursor.execute("""
        INSERT INTO geo_config (
            geo_code, spend_zero_leads, cpa_red, cpa_green, cpa_orange
        ) VALUES (?, ?, ?, ?, ?)
        
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
            king, name, status, campaign_id, account_id, token
        ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
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
            name, adset_id, ucpc, spend, cpa, status, geo, token, 
            leads, manual_pause, king, effective_status, ad_name, budget
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
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
    conn.close()

if __name__ == "__main__":
    print("Инициализация базы данных...")
    init_db()
    print("Генерация тестовых данных...")
    generate_test_data()
    print("Готово! База данных создана с тестовыми данными.")