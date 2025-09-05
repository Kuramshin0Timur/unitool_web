import re
from typing import Any, Dict
from venv import logger

from database import get_db_connection, lock


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
def extract_geo_from_name(name, known_geos=None):
    """
    Извлекает GEO код из названия адсета.
    Всегда пытается определить страну, даже если её нет в known_geos.
    """
    if not name:
        return 'N/A'
    
    # Словарь для сопоставления названий стран с кодами
    country_mapping = {
        # Азия
        'thailand': 'TH', 'thai': 'TH', 'тайланд': 'TH', 'тай': 'TH',
        'indonesia': 'ID', 'indo': 'ID', 'индонезия': 'ID', 'индо': 'ID',
        'malaysia': 'MY', 'malay': 'MY', 'малайзия': 'MY', 'малай': 'MY',
        'singapore': 'SG', 'sing': 'SG', 'сингапур': 'SG', 'синг': 'SG',
        'vietnam': 'VN', 'viet': 'VN', 'вьетнам': 'VN', 'вьет': 'VN',
        'philippines': 'PH', 'phil': 'PH', 'филиппины': 'PH', 'фил': 'PH',
        'taiwan': 'TW', 'тайвань': 'TW',
        'hong kong': 'HK', 'гонконг': 'HK',
        'japan': 'JP', 'japanese': 'JP', 'япония': 'JP', 'япон': 'JP',
        'korea': 'KR', 'korean': 'KR', 'корея': 'KR', 'корей': 'KR',
        'china': 'CN', 'chinese': 'CN', 'китай': 'CN', 'китайск': 'CN',
        'india': 'IN', 'indian': 'IN', 'индия': 'IN', 'индийск': 'IN',
        
        # Европа
        'germany': 'DE', 'german': 'DE', 'германия': 'DE', 'немец': 'DE',
        'france': 'FR', 'french': 'FR', 'франция': 'FR', 'франц': 'FR',
        'italy': 'IT', 'italian': 'IT', 'италия': 'IT', 'итальян': 'IT',
        'spain': 'ES', 'spanish': 'ES', 'испания': 'ES', 'испан': 'ES',
        'ukraine': 'UA', 'ukrainian': 'UA', 'украина': 'UA', 'украин': 'UA',
        'russia': 'RU', 'russian': 'RU', 'россия': 'RU', 'русск': 'RU',
        'poland': 'PL', 'polish': 'PL', 'польша': 'PL', 'польск': 'PL',
        'united kingdom': 'UK', 'uk': 'UK', 'британия': 'UK', 'англия': 'UK',
        'turkey': 'TR', 'turkish': 'TR', 'турция': 'TR', 'турецк': 'TR',
        'netherlands': 'NL', 'dutch': 'NL', 'нидерланды': 'NL', 'голландия': 'NL',
        
        # Америка
        'usa': 'US', 'united states': 'US', 'америка': 'US', 'сша': 'US',
        'canada': 'CA', 'canadian': 'CA', 'канада': 'CA', 'канад': 'CA',
        'brazil': 'BR', 'brazilian': 'BR', 'бразилия': 'BR', 'бразил': 'BR',
        'mexico': 'MX', 'mexican': 'MX', 'мексика': 'MX', 'мексик': 'MX',
        'argentina': 'AR', 'argentinian': 'AR', 'аргентина': 'AR', 'аргентин': 'AR',
        
        # Другие регионы
        'australia': 'AU', 'australian': 'AU', 'австралия': 'AU', 'австрал': 'AU',
        'new zealand': 'NZ', 'nz': 'NZ', 'новая зеландия': 'NZ',
        'south africa': 'ZA', 'sa': 'ZA', 'южная африка': 'ZA',
        'egypt': 'EG', 'egyptian': 'EG', 'египет': 'EG', 'египетск': 'EG',
        'nigeria': 'NG', 'nigerian': 'NG', 'нигерия': 'NG', 'нигерий': 'NG',
        'saudi arabia': 'SA', 'saudi': 'SA', 'саудовская аравия': 'SA',
        'uae': 'AE', 'united arab emirates': 'AE', 'оаэ': 'AE',
        
        # Дополнительные часто используемые коды
        'world': 'WW', 'global': 'WW', 'мир': 'WW', 'глобал': 'WW',
        'europe': 'EU', 'европа': 'EU',
        'asia': 'AS', 'азия': 'AS',
        'america': 'AM', 'америка': 'AM',
        'africa': 'AF', 'африка': 'AF',
    }
    
    # Приводим название к нижнему регистру для поиска
    name_lower = name.lower()
    
    # Сначала ищем совпадения по названиям стран
    for country_name, country_code in country_mapping.items():
        if country_name in name_lower:
            return country_code
    
    # Ищем паттерны с двухбуквенными кодами
    geo_patterns = [
        r'^([A-Z]{2})\b',       # код в начале названия
        r'\b([A-Z]{2})[-\s_]',  # код с разделителями
        r'[-\s_]([A-Z]{2})\b',  # код в конце
        r'\b([A-Z]{2})\d',      # код перед цифрами
    ]
    
    for pattern in geo_patterns:
        match = re.search(pattern, name.upper())
        if match:
            geo_code = match.group(1)
            if len(geo_code) == 2 and geo_code.isalpha():
                return geo_code
    
    # Ищем числовые коды стран (телефонные префиксы)
    phone_code_patterns = {
        '66': 'TH',  # Таиланд
        '62': 'ID',  # Индонезия
        '60': 'MY',  # Малайзия
        '65': 'SG',  # Сингапур
        '84': 'VN',  # Вьетнам
        '63': 'PH',  # Филиппины
        '1': 'US',   # США/Канада
        '7': 'RU',   # Россия/Казахстан
    }
    
    for code, country in phone_code_patterns.items():
        if code in name:
            return country
    
    # Потом проверяем known_geos (как fallback)
    if known_geos:
        for geo in known_geos:
            if geo.upper() in name.upper():
                return geo.upper()
    
    # Если ничего не найдено
    return 'N/A'
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
