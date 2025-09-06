import logging

import requests

logger = logging.getLogger(__name__)
from backend.setting import get_user_settings
from database import get_db_connection, lock


def sync_keitaro(user_id: int):
    """Обновляет метрики адсетов из Keitaro"""
    try:
        settings = get_user_settings(user_id)
        api_key = settings.get("keitaro_api_key")
        domain = settings.get("keitaro_domain")

        if not api_key or not domain:
            return 0

        report = fetch_keitaro_report(api_key, domain, interval="today")
        rows = report.get("rows", [])
        if not rows:
            return 0

        updated_count = 0
        with lock:
            with get_db_connection(user_id) as conn:
                cursor = conn.cursor()
                for row in rows:
                    adset_id = row.get("sub_id_9")   # 🚨 должно совпадать с тем, что ты пишешь в Keitaro
                    if not adset_id:
                        continue

                    cpa = float(row.get("cpa", 0) or 0)
                    ucpc = float(row.get("ucpc", 0) or 0)
                    cpc = float(row.get("cpc", 0) or 0)
                    spend = float(row.get("cost", 0) or 0)
                    leads = int(row.get("leads", 0) or 0)

                    cursor.execute("""
                        UPDATE adsets
                        SET cpa = ?, ucpc = ?, cpc = ?, spend = ?, leads = ?
                        WHERE user_id = ? AND adset_id = ?
                    """, (cpa, ucpc, cpc, spend, leads, user_id, adset_id))
                    
                    if cursor.rowcount > 0:
                        updated_count += 1

                conn.commit()

        return updated_count

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Ошибка sync_keitaro для user_id {user_id}: {e}")
        return 0

def fetch_keitaro_report(api_key, domain, interval="today"):
    """
    Получает отчет из Keitaro для адсетов.
    Возвращает метрики: uCPC, CPC, CPA, Leads, Spend.
    """
    url = f"https://{domain}/admin_api/v1/report/build"
    headers = {"Api-Key": api_key, "Content-Type": "application/json"}

    metrics = ["ucpc", "cpc", "conversions", "cost"]  # ⚠️ CPA убрал, считаем сами
    limit = 250
    offset = 0
    all_rows = []

    try:
        while True:
            payload = {
                "range": {"interval": interval, "timezone": "Europe/Moscow"},
                "metrics": metrics,
                "grouping": ["sub_id_9"],   # sub_id_9 = adset_id
                "filters": [],
                "sort": [{"name": "ucpc", "order": "desc"}],
                "limit": limit,
                "offset": offset
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            report = response.json()

            rows = report.get("rows", [])
            if not rows:
                break

            for row in rows:
                cost = float(row.get("cost", 0) or 0)
                cpc = float(row.get("cpc", 0) or 0)
                ucpc = float(row.get("ucpc", 0) or 0)
                conversions = int(row.get("conversions", 0) or 0)

                leads = conversions
                cpa = (cost / conversions) if conversions > 0 else 0

                row["leads"] = leads
                row["cpa"] = round(cpa, 2)
                row["cpc"] = round(cpc, 2)
                row["ucpc"] = round(ucpc, 2)
                row["cost"] = round(cost, 2)

            all_rows.extend(rows)

            if len(rows) < limit:
                break
            offset += limit

        return {"rows": all_rows}

    except Exception as e:
        logger.error(f"Ошибка при запросе отчета Keitaro: {e}")
        return {"rows": []}