    
from typing import Any, Dict, List, Optional
from venv import logger

from database import get_db_connection, lock


def update_user_adset_budget(user_id: int, adset_id: str, budget: float):
    
  
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
def get_adset_budget_settings(user_id: int, adset_id: str) -> Optional[Dict[str, Any]]:
  
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

def get_adsets_for_auto_budget(user_id: int) -> List[Dict[str, Any]]:
    
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
