import time
import logging
import gspread
from google.oauth2.service_account import Credentials
from .config import SCOPES, SPREADSHEET_NAME, CAMPAIGN_SHEET, DATA_SHEET_NAME

_creds = None
_gc = None
logger = logging.getLogger(__name__)


def init_client():
    global _creds, _gc
    _creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    _gc = gspread.authorize(_creds)


def safe_worksheet(sheet_name, max_retries=3, delay=2):
    for attempt in range(1, max_retries + 1):
        try:
            return _gc.open(SPREADSHEET_NAME).worksheet(sheet_name)
        except Exception as e:
            if attempt == max_retries:
                raise
            time.sleep(delay)
            delay *= 2
            init_client()


# инициализируем сразу
init_client()


def fetch_campaigns():
    sheet = safe_worksheet(CAMPAIGN_SHEET)
    rows = sheet.get_all_values()
    campaigns = []
    for row in rows[1:]:
        if len(row) >= 6:
            campaigns.append([
                row[0].strip(),        # KING
                row[1].strip(),        # Name
                row[3].strip().upper(),# Status
                row[2].strip(),        # ID
                row[4].strip(),        # AccountID
                row[5].strip()         # Token
            ])
    return campaigns


def fetch_adsets():
    sheet = safe_worksheet(DATA_SHEET_NAME)
    rows = sheet.get_all_values()
    adsets = []
    for row in rows[1:]:
        if len(row) >= 13:
            adsets.append([
                row[0].strip(),  # AdSet Name
                row[1].strip(),  # AdSet ID
                row[2].strip(),  # uCPC
                row[3].strip(),  # Spend
                row[4].strip(),  # CPA
                row[5].strip().upper(),  # Status
                row[6].strip(),  # Account ID (используем как GEO)
                row[7].strip(),  # Token
                row[8].strip(),  # Leads
                row[9].strip(),  # ManualPause
                row[10].strip(), # KING
                row[11].strip(), # Effective Status
                row[12].strip()  # Ad Name
            ])
    return adsets

def load_reserve_tokens():
    try:
        sheet = safe_worksheet("RESERV_API")
        rows = sheet.get_all_values()
        reserve_map = {}
        for row in rows[1:]:
            if not row or not row[0].strip():
                continue
            king = row[0].strip()
            tokens = [t.strip() for t in row[1:] if t.strip()]
            if tokens:
                reserve_map[king] = tokens
        return reserve_map
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка чтения RESERV_API: {e}")
        return {}

def load_geo_config_from_sheet(sheet):
    rows = sheet.get_all_values()
    geo_config = {}

    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue

        if len(row) < 5:
            logger.warning(f"Некорректная строка в GEOcfg: {row}")
            continue

        try:
            geo = row[0].strip().upper()
            geo_config[geo] = {
                "spend_zero_leads": float(row[1].replace(",", ".")),
                "cpa_red": float(row[2].replace(",", ".")),
                "cpa_green": float(row[3].replace(",", ".")),
                "cpa_orange": float(row[4].replace(",", "."))
            }
        except Exception as e:
            logger.error(f"Ошибка в строке GEOcfg {row}: {e}")
            continue

    return geo_config
