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


def extract_geo_from_name(name, known_geos=None):
    """
    Извлекает GEO код из названия адсета.
    Всегда пытается определить страну, даже если её нет в known_geos.
    """
    if not name:
        return 'N/A'

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
        
        'usa': 'US', 'united states': 'US', 'америка': 'US', 'сша': 'US',
        'canada': 'CA', 'canadian': 'CA', 'канада': 'CA', 'канад': 'CA',
        'brazil': 'BR', 'brazilian': 'BR', 'бразилия': 'BR', 'бразил': 'BR',
        'mexico': 'MX', 'mexican': 'MX', 'мексика': 'MX', 'мексик': 'MX',
        'argentina': 'AR', 'argentinian': 'AR', 'аргентина': 'AR', 'аргентин': 'AR',
        
        'australia': 'AU', 'australian': 'AU', 'австралия': 'AU', 'австрал': 'AU',
        'new zealand': 'NZ', 'nz': 'NZ', 'новая зеландия': 'NZ',
        'south africa': 'ZA', 'sa': 'ZA', 'южная африка': 'ZA',
        'egypt': 'EG', 'egyptian': 'EG', 'египет': 'EG', 'египетск': 'EG',
        'nigeria': 'NG', 'nigerian': 'NG', 'нигерия': 'NG', 'нигерий': 'NG',
        'saudi arabia': 'SA', 'saudi': 'SA', 'саудовская аравия': 'SA',
        'uae': 'AE', 'united arab emirates': 'AE', 'оаэ': 'AE',
        
        'world': 'WW', 'global': 'WW', 'мир': 'WW', 'глобал': 'WW',
        'europe': 'EU', 'европа': 'EU',
        'asia': 'AS', 'азия': 'AS',
        'america': 'AM', 'америка': 'AM',
        'africa': 'AF', 'африка': 'AF',
    }
    
    name_lower = name.lower()
    
    for country_name, country_code in country_mapping.items():
        if country_name in name_lower:
            return country_code
    
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
    
    if known_geos:
        for geo in known_geos:
            if geo.upper() in name.upper():
                return geo.upper()
    
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
    """
    Получает GEO правила напрямую из таблицы geo_rules (правила автоконтроля с сайта)
    Возвращает только актуальные правила для текущих GEO
    """
    geo_rules = {}
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Проверяем существование таблицы geo_rules
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
                    WHERE user_id = ? AND active = 1
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
                logger.info(f"Загружено {len(geo_rules)} GEO правил из таблицы geo_rules")
            else:
                logger.warning("Таблица geo_rules не найдена, используем старую конфигурацию")
                return get_user_geo_config(user_id)
    
    except Exception as e:
        logger.error(f"Ошибка получения GEO правил: {e}")
        # В случае ошибки возвращаем пустой словарь
    
    return geo_rules


def get_current_geos_from_adsets(user_id):
    """
    Получает список GEO из текущих активных адсетов
    (только те GEO, которые реально используются сейчас)
    """
    current_geos = set()
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
            # Получаем GEO из активных адсетов
            cursor.execute("""
                SELECT DISTINCT geo FROM adsets 
                WHERE user_id = ? AND status IN ('ACTIVE', 'PAUSED')
            """, (user_id,))
            
            for row in cursor.fetchall():
                if row['geo'] and row['geo'] != 'N/A':
                    current_geos.add(row['geo'])
            
            logger.info(f"Текущие GEO из адсетов: {list(current_geos)}")
    
    except Exception as e:
        logger.error(f"Ошибка получения текущих GEO: {e}")
    
    return list(current_geos)


def get_filtered_geo_rules(user_id):
    """
    Возвращает только те GEO правила, которые актуальны для текущих адсетов
    (не анализирует старые/неиспользуемые GEO)
    """
    # Получаем все правила из таблицы geo_rules
    all_rules = get_user_geo_rules(user_id)
    
    # Получаем GEO из текущих адсетов
    current_geos = get_current_geos_from_adsets(user_id)
    
    # Фильтруем правила только для актуальных GEO
    filtered_rules = {}
    for geo in current_geos:
        if geo in all_rules:
            filtered_rules[geo] = all_rules[geo]
        else:
            logger.warning(f"Нет правил для GEO: {geo} - адсеты будут пропущены")
    
    logger.info(f"Актуальные GEO правила: {len(filtered_rules)} из {len(all_rules)}")
    return filtered_rules


def should_analyze_adset(adset_data, geo_rules):
    """
    Определяет, нужно ли анализировать адсет
    Возвращает True только если есть правила для его GEO
    """
    geo = adset_data.get('geo', 'N/A')
    
    if geo == 'N/A' or geo not in geo_rules:
        logger.info(f"⏭️ Пропускаем (нет правил для GEO: {geo}) {adset_data.get('name', 'Unknown')}")
        return False
    
    # Дополнительные проверки для новых адсетов
    spend = adset_data.get('spend', 0)
    leads = adset_data.get('leads', 0)
    
    # Не анализировать адсеты с очень малыми данными
    if spend < 1.0:  # Меньше $1 трат
        logger.info(f"⏭️ Пропускаем (мало данных: spend=${spend}) {adset_data.get('name', 'Unknown')}")
        return False
    
    return True