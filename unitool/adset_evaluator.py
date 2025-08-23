import logging

logger = logging.getLogger(__name__)

def evaluate_adset(row, geo_config):
    try:
        adset_name = row[0].strip().upper()
        geo = adset_name[:2]  # первые 2 буквы AdSet Name — например, "TR"
        spend = float(row[3].replace(",", ".")) if row[3] else 0.0
        cpa = float(row[4].replace(",", ".")) if row[4] else 0.0
        leads = int(row[8]) if row[8].isdigit() else 0

        config = geo_config.get(geo)
        if not config:
            logging.warning(f"⚠️ GEO-конфигурация не найдена для кода: {geo}")
            return None

        # 🔴 Если есть трата, но нет лидов
        if leads == 0 and spend >= config["spend_zero_leads"]:
            return "red"

        # 🔴 CPA выше красного порога
        if cpa >= config["cpa_red"]:
            return "red"

        # 🟢 CPA ниже или равно зелёному порогу
        if cpa <= config["cpa_green"]:
            return "green"

        # 🟡 CPA ниже или равно оранжевому порогу
        if cpa <= config["cpa_orange"]:
            return "yellow"

        # 🟠 CPA между оранжевым и красным порогом — промежуточный "жёлтый"
        if config["cpa_orange"] < cpa < config["cpa_red"]:
            return "orange"

        return None  # не подсвечивать
    except Exception as e:
        logging.error(f"Ошибка в evaluate_adset: {e}")
        return None
