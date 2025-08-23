import datetime
import time
from typing import Dict, Optional
from venv import logger

import gspread
import requests


def get_keitaro_api_key() -> str:
    """Чтение Keitaro API key из Google Sheets (лист 'KEYS')."""
    try:
        gc = gspread.service_account(filename="credentials.json")  # твой json от Google API
        sh = gc.open("Копия REPORT KLIM")  # название таблицы
        ws = sh.worksheet("KEYS")

        records = ws.get_all_records()
        for row in records:
            if str(row.get("Key")).strip().lower() == "keitaro_api":
                return str(row.get("Value")).strip()

        raise ValueError("Keitaro API key не найден в таблице KEYS")

    except Exception as e:
        logger.error(f"Ошибка получения keitaro_api: {e}")
        return ""
