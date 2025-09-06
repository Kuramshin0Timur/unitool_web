import logging

import requests


def fetch_keitaro_report(api_key, domain, interval="today"):
    
  
    logger = logging.getLogger(__name__)
    url = f"https://{domain}/admin_api/v1/report/build"
    headers = {"Api-Key": api_key, "Content-Type": "application/json"}

    metrics = ["ucpc", "cpc", "conversions", "cost", "cpa"]
    limit = 250
    offset = 0
    all_rows = []

    try:
        while True:
            payload = {
                "range": {"interval": interval, "timezone": "Europe/Moscow"},
                "metrics": metrics,
                "grouping": ["sub_id_9"],   # 🚨 только имя адсета
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
                cpa = float(row.get("cpa", 0) or 0)
                cpc = float(row.get("cpc", 0) or 0)

                leads = round(cost / cpa) if cpa > 0 and cost > 0 else 0
                row["leads"] = leads
                row["cpc"] = cpc

            all_rows.extend(rows)

            if len(rows) < limit:
                break
            offset += limit

        return {"rows": all_rows}

    except Exception as e:
        logger.error(f"Ошибка при запросе отчета Keitaro: {e}")
        return {"rows": []}
