import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config.json")

# Значения по умолчанию
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "REPORT KLIM")
CAMPAIGN_SHEET = os.getenv("CAMPAIGN_SHEET", "CampaignControl")
DATA_SHEET_NAME = os.getenv("DATA_SHEET_NAME", "AdSetControl")
CONFIG_SHEET_NAME = os.getenv("CONFIG_SHEET_NAME", "Config")
RESERVE_API_SHEET_NAME = os.getenv("RESERVE_API_SHEET_NAME", "RESERV_API")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7434332656:AAFTQzifyHJJr__V1NMP3uArqyi4ew9mwlI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7941692968")

LOG_FILE = os.getenv("LOG_FILE", "adset_log.txt")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def load_config() -> dict:
    """
    Безопасная загрузка config.json.
    Возвращает словарь конфигурации, либо пустой словарь.
    """
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            logger.warning("⚠️ Файл config.json не найден")
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке config.json: {e}")
    return {}


def get_use_proxy() -> bool:
    """
    Возвращает актуальное значение use_proxy из config.json.
    По умолчанию — True.
    """
    config = load_config()
    return config.get("use_proxy", True)


# Для обратной совместимости:
USE_PROXY = get_use_proxy()

def get_auto_refresh_campaigns() -> bool:
    config = load_config()
    return config.get("auto_refresh_campaigns", True)

def get_auto_refresh_adsets() -> bool:
    config = load_config()
    return config.get("auto_refresh_adsets", True)

def save_config(data: dict):
    """Сохраняет словарь в config.json"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении config.json: {e}")
