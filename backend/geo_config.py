import re
from typing import Any, Dict, List
from venv import logger

from database import get_db_connection, lock


def add_user_geo_config(user_id: int, data: Dict[str, Any]):

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

    
    import random
    
    with lock:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
           
            cursor.execute("DELETE FROM campaigns WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM adsets WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM geo_config WHERE user_id = ?", (user_id,))
            
            
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
    
    import random
    
    with lock:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
           
            cursor.execute("DELETE FROM campaigns WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM adsets WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM geo_config WHERE user_id = ?", (user_id,))
            
          
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
def extract_geo_from_name(name: str, known_geos: List[str] = None) -> str:
   
    if not name:
        return 'N/A'
    
    
    if known_geos is None:
        known_geos = []
    
  
    standard_geos = ['US', 'UK', 'CA', 'AU', 'DE', 'FR', 'ES', 'IT', 'RU', 
                    'JP', 'KR', 'CN', 'IN', 'MX', 'BR', 'AR', 'CO', 'PE',
                    'CL', 'ZA', 'NG', 'EG', 'SA', 'AE', 'TR', 'PL', 'NL',
                    'SE', 'NO', 'DK', 'FI', 'BE', 'CH', 'AT', 'MY', 'SG',
                    'VN', 'TH', 'PH', 'ID']
    
    
    all_geos = list(set(standard_geos + known_geos))
    
   
    name_upper = name.upper()
    
    
    for geo in all_geos:
        
        if re.search(r'\b' + re.escape(geo) + r'\b', name_upper):
            return geo
    
    
    for geo in all_geos:
        if geo in name_upper:
            
            geo_pattern = re.compile(r'(^|[^A-Z])' + re.escape(geo) + r'($|[^A-Z])')
            if geo_pattern.search(name_upper):
                return geo
    
    return 'N/A'
def get_user_geo_config(user_id: int) -> Dict[str, Dict[str, float]]:
   
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
  
    geo_rules = {}
    try:
        with get_db_connection(user_id) as conn:
            cursor = conn.cursor()
            
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
