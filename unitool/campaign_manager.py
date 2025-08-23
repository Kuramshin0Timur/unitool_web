import logging
import sys
import time
from datetime import datetime
from typing import Any, Optional

import pytz
import requests
from PySide2.QtCore import (QModelIndex, QSortFilterProxyModel, Qt, QThread,
                            QTimer)
from PySide2.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QProgressDialog,
                               QPushButton, QSpinBox, QSplitter, QTableView,
                               QTextEdit, QVBoxLayout, QWidget)

from unitool.adset_evaluator import evaluate_adset
from unitool.config import get_auto_refresh_adsets, get_auto_refresh_campaigns
from unitool.fb_api import refresh_session
from unitool.sheets_client import load_geo_config_from_sheet, safe_worksheet

from .auto_control import auto_control, send_telegram_message
from .config import LOG_FILE
from .fb_api import (_graph_request, get_adset_budget,
                     list_campaigns_with_spend, pause_adset, pause_campaign,
                     resume_adset, resume_campaign, update_adset_budget)
from .keitaro import fetch_keitaro_report, get_keitaro_api_key
from .logger import setup_logging
from .models import AdSetTableModel, CampaignTableModel
from .sheets_client import fetch_adsets, fetch_campaigns

logger = logging.getLogger(__name__)


class CampaignFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None,
                 status_filter=None, king_filter=None, king_column=0,
                 name_filter=None, name_column=1, status_column=2):
        super().__init__(parent)
        self.status_filter = status_filter
        self.king_filter = king_filter
        self.name_filter = name_filter
        self.king_column = king_column
        self.name_column = name_column
        self.status_column = status_column

        if status_filter:
            status_filter.currentTextChanged.connect(self.invalidateFilter)
        if king_filter:
            king_filter.currentTextChanged.connect(self.invalidateFilter)
        if name_filter:
            name_filter.textChanged.connect(self.invalidateFilter)

    def filterAcceptsRow(self, src_row, src_parent):
        model = self.sourceModel()
        if self.status_filter:
            st = self.status_filter.currentText()
            val = model.index(src_row, self.status_column).data() or ""
            if st == "Активные" and val != "ACTIVE":
                return False
            if st == "Пауза" and val != "PAUSED":
                return False
        if self.king_filter:
            sel = self.king_filter.currentText()
            if sel != "Все":
                king = model.index(src_row, self.king_column).data() or ""
                if king != sel:
                    return False
        if self.name_filter:
            txt = self.name_filter.text().lower().strip()
            if txt:
                name = model.index(src_row, self.name_column).data() or ""
                if txt not in name.lower():
                    return False
        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        lv, rv = left.data(), right.data()
        try:
            return float(str(lv).replace(",", ".")) < float(str(rv).replace(",", "."))
        except (TypeError, ValueError):
            return str(lv) < str(rv)


class GenericFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None,
                 status_filter=None, text_filter=None,
                 filter_column=None, status_column=2):
        super().__init__(parent)
        self.status_filter = status_filter
        self.text_filter = text_filter
        self.filter_column = filter_column
        self.status_column = status_column

        if status_filter:
            status_filter.currentTextChanged.connect(self.invalidateFilter)
        if text_filter:
            text_filter.textChanged.connect(self.invalidateFilter)

    def filterAcceptsRow(self, src_row, src_parent):
        model = self.sourceModel()
        if self.status_filter:
            st = self.status_filter.currentText()
            val = model.index(src_row, self.status_column).data() or ""
            if st == "Активные" and val != "ACTIVE":
                return False
            if st == "Пауза" and val != "PAUSED":
                return False
        if self.text_filter and self.filter_column is not None:
            txt = self.text_filter.text().lower().strip()
            if txt:
                cell = model.index(src_row, self.filter_column).data() or ""
                if txt not in cell.lower():
                    return False
        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        lv, rv = left.data(), right.data()
        try:
            return float(str(lv).replace(",", ".")) < float(str(rv).replace(",", "."))
        except (TypeError, ValueError):
            return str(lv) < str(rv)


class AutoControlWorker(QThread):
    def __init__(self, interval_minutes):
        super().__init__()
        self.interval = interval_minutes * 60
        self._running = True

    def run(self):
        while self._running:
            auto_control()
            for _ in range(int(self.interval / 5)):
                if not self._running:
                    break
                time.sleep(5)

    def stop(self):
        self._running = False


class CampaignManager(QWidget):
    def __init__(self):
        super().__init__()
        refresh_session()
        self.setWindowTitle("UNITOOL")
        self.resize(1200, 700)

        self.log_widget = QTextEdit(readOnly=True)
        self.log_widget.setMinimumHeight(150)
        setup_logging(LOG_FILE, ui_log_widget=self.log_widget)

        self.red_style = """ QPushButton { background-color: #d9534f; color:white; border-radius:5px; padding:5px 10px; }
                             QPushButton:hover { background-color: #c9302c; }
                             QPushButton:pressed { background-color: #ac2925; }"""
        self.green_style = """ QPushButton { background-color: #5cb85c; color:white; border-radius:5px; padding:5px 10px; }
                               QPushButton:hover { background-color: #4cae4c; }
                               QPushButton:pressed { background-color: #449d44; }"""
        self.blue_style = """ QPushButton { background-color: #0275d8; color:white; border-radius:5px; padding:5px 10px; }
                              QPushButton:hover { background-color: #025aa5; }
                              QPushButton:pressed { background-color: #014682; }"""

        self._setup_campaign_panel()
        self._setup_adset_panel()

        tables = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget();  left.setLayout(self.campaign_layout)
        right = QWidget(); right.setLayout(self.adset_layout)
        tables.addWidget(left); tables.addWidget(right)
        tables.setSizes([600, 600])

        main_split = QSplitter(Qt.Orientation.Vertical)
        main_split.addWidget(tables)
        main_split.addWidget(self.log_widget)
        main_split.setSizes([500, 150])

        # Часы автоконтроля
        self.minute1_spin = QSpinBox()
        self.minute1_spin.setRange(0, 59)
        self.minute1_spin.setValue(15)
        self.minute1_check = QCheckBox("вкл")
        self.minute1_check.setChecked(False)

        self.minute2_spin = QSpinBox()
        self.minute2_spin.setRange(0, 59)
        self.minute2_spin.setValue(45)
        self.minute2_check = QCheckBox("вкл")
        self.minute2_check.setChecked(False)

        self.btn_force_auto = QPushButton("Принудительный автоконтроль")
        self.btn_force_auto.setStyleSheet(self.blue_style)
        self.btn_force_auto.clicked.connect(self.force_auto_control)

        minute_row = QHBoxLayout()
        minute_row.addWidget(QLabel("Минуты автоконтроля:"))
        minute_row.addWidget(self.minute1_spin)
        minute_row.addWidget(self.minute1_check)
        minute_row.addWidget(self.minute2_spin)
        minute_row.addWidget(self.minute2_check)
        minute_row.addStretch()

        bottom = QHBoxLayout()
        bottom.addLayout(minute_row)
        bottom.addWidget(self.btn_force_auto)
        bottom.addStretch()

        root = QVBoxLayout(self)
        root.addWidget(main_split)
        root.addLayout(bottom)

        # Автоконтроль каждые 30 секунд — проверка расписания
        self.auto_control_timer = QTimer(self)
        self.auto_control_timer.timeout.connect(self._check_time_for_auto_control)
        self.auto_control_timer.start(30 * 1000)

        self._last_auto_control_minute = None
        self.worker = None
        self._last_refresh_minute = None
        self.refresh_check_timer = QTimer(self)
        self.refresh_check_timer.timeout.connect(self._check_time_for_refresh)
        self.refresh_check_timer.start(30 * 1000)  # каждые 30 секунд


        for btn in (
            self.btn_disable_campaign,
            self.btn_enable_campaign,
            self.btn_refresh_campaign,
            self.btn_disable_adset,
            self.btn_enable_adset,
            self.btn_refresh_adset,
            self.btn_set_budget
        ):
            text = btn.text()
            if "Отключить" in text:
                btn.setStyleSheet(self.red_style)
            elif "Включить" in text:
                btn.setStyleSheet(self.green_style)
            else:
                btn.setStyleSheet(self.blue_style)

        self.refresh_campaigns()
        self.refresh_adsets()


    def _setup_campaign_panel(self):
        self.campaign_model = CampaignTableModel()
        self.campaign_status_filter = QComboBox()
        self.campaign_status_filter.addItems(["Все", "Активные", "Пауза"])
        self.campaign_king_filter = QComboBox()
        self.campaign_king_filter.addItem("Все")
        self.campaign_name_search = QLineEdit()
        self.campaign_name_search.setPlaceholderText("Поиск по названию кампании")

        self.campaign_proxy = CampaignFilterProxyModel(
            status_filter=self.campaign_status_filter,
            king_filter=self.campaign_king_filter,
            king_column=0,
            name_filter=self.campaign_name_search,
            name_column=1,
            status_column=2
        )
        self.campaign_proxy.setSourceModel(self.campaign_model)

        self.campaign_table = QTableView()
        self.campaign_table.setModel(self.campaign_proxy)
        self.campaign_table.setSortingEnabled(True)
        self.campaign_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.campaign_table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

        for col in (2, 3, 5):  # скрыть Status, CampaignID, Token
            self.campaign_table.hideColumn(col)

        hdr = self.campaign_table.horizontalHeader()
        hdr.moveSection(hdr.visualIndex(4), 1)
        hdr.moveSection(hdr.visualIndex(1), 2)

        self.btn_disable_campaign = QPushButton("⏸ Отключить кампании")
        self.btn_enable_campaign = QPushButton("▶ Включить кампании")
        self.btn_refresh_campaign = QPushButton("↻ Обновить кампании")
        self.btn_disable_campaign.clicked.connect(self.disable_selected_campaigns)
        self.btn_enable_campaign.clicked.connect(self.enable_selected_campaigns)
        self.btn_refresh_campaign.clicked.connect(self.refresh_campaigns)

        fl = QHBoxLayout()
        fl.addWidget(QLabel("Статус:"))
        fl.addWidget(self.campaign_status_filter)
        fl.addWidget(QLabel("KING:"))
        fl.addWidget(self.campaign_king_filter)
        fl.addWidget(QLabel("Название:"))
        fl.addWidget(self.campaign_name_search)

        bl = QHBoxLayout()
        bl.addWidget(self.btn_disable_campaign)
        bl.addWidget(self.btn_enable_campaign)
        bl.addWidget(self.btn_refresh_campaign)

        self.campaign_layout = QVBoxLayout()
        self.campaign_layout.addLayout(fl)
        self.campaign_layout.addWidget(self.campaign_table)
        self.campaign_layout.addLayout(bl)


    def _setup_adset_panel(self):
        self.adset_model = AdSetTableModel()
        self.adset_status_filter = QComboBox()
        self.adset_status_filter.addItems(["Все", "Активные", "Пауза"])
        self.adset_search = QLineEdit()
        self.adset_search.setPlaceholderText("Поиск по названию AdSet")

        self.adset_proxy = GenericFilterProxyModel(
            status_filter=self.adset_status_filter,
            text_filter=self.adset_search,
            filter_column=0,     # AdSet Name
            status_column=5      # Status
        )
        self.adset_proxy.setSourceModel(self.adset_model)

        self.adset_table = QTableView()
        self.adset_table.setModel(self.adset_proxy)
        self.adset_table.setSortingEnabled(True)
        self.adset_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.adset_table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

        for col in (1, 5, 6, 7, 9, 10, 12, 11):
            self.adset_table.hideColumn(col)

        hdr = self.adset_table.horizontalHeader()
        hdr.moveSection(hdr.visualIndex(13), 9)

        self.adset_budget_spin = QDoubleSpinBox()
        self.adset_budget_spin.setRange(0.00, 100_000.00)
        self.adset_budget_spin.setDecimals(2)
        self.adset_budget_spin.setSingleStep(1.00)
        self.adset_budget_spin.setSuffix(" $")
        self.adset_budget_spin.setValue(10.00)

        self.btn_set_budget = QPushButton("Установить бюджет")
        self.btn_set_budget.clicked.connect(self.set_selected_adsets_budget)

        self.btn_disable_adset = QPushButton("⏸ Отключить адсеты")
        self.btn_enable_adset = QPushButton("▶ Включить адсеты")
        self.btn_refresh_adset = QPushButton("↻ Обновить адсеты")
        self.btn_disable_adset.clicked.connect(self.disable_selected_adsets)
        self.btn_enable_adset.clicked.connect(self.enable_selected_adsets)
        self.btn_refresh_adset.clicked.connect(self.refresh_adsets)

        fl = QHBoxLayout()
        fl.addWidget(QLabel("Статус:"))
        fl.addWidget(self.adset_status_filter)
        fl.addWidget(QLabel("Поиск:"))
        fl.addWidget(self.adset_search)
        fl.addWidget(QLabel("Бюджет:"))
        fl.addWidget(self.adset_budget_spin)

        bl = QHBoxLayout()
        bl.addWidget(self.btn_disable_adset)
        bl.addWidget(self.btn_enable_adset)
        bl.addWidget(self.btn_refresh_adset)
        bl.addWidget(self.btn_set_budget)

        self.adset_layout = QVBoxLayout()
        self.adset_layout.addLayout(fl)
        self.adset_layout.addWidget(self.adset_table)
        self.adset_layout.addLayout(bl)


    def _check_time_for_auto_control(self):
        now = datetime.now(pytz.timezone("Europe/Moscow"))
        minute = now.minute

        selected_minutes = []
        if self.minute1_check.isChecked():
            selected_minutes.append(self.minute1_spin.value())
        if self.minute2_check.isChecked():
            selected_minutes.append(self.minute2_spin.value())

        if minute in selected_minutes and minute != self._last_auto_control_minute:
            logger.info(f"🕒 Автоконтроль запущен по расписанию: {minute} мин")
            auto_control()
            self._last_auto_control_minute = minute
        elif minute not in selected_minutes:
            self._last_auto_control_minute = None


    def force_auto_control(self):
        logger.info("🕒 Принудительный запуск автоконтроля")
        auto_control()
        QMessageBox.information(self, "Автоконтроль", "Автоконтроль выполнен принудительно.")

    def refresh_campaigns(self):
        dlg = QProgressDialog("Загрузка кампаний из Facebook…", None, 0, 0, self)
        dlg.show()
        try:
            sheet_rows = fetch_campaigns()
            accounts: dict[str, str] = {}
            for row in sheet_rows:
                if len(row) >= 6 and row[4] and row[5]:
                    accounts[row[4]] = row[5]

            enriched = []
            for acc_id, token in accounts.items():
                fb_rows = list_campaigns_with_spend(
                    acc_id, token,
                    fields="id,name,status,effective_status,daily_budget",
                    effective_status=["ACTIVE", "PAUSED"],
                )
                for c in fb_rows:
                    enriched.append([
                        "",
                        c.get("name", ""),
                        c.get("id", ""),
                        c.get("status") or c.get("effective_status") or "",
                        acc_id,
                        token,
                        ""
                    ])

            self.campaign_model.update(enriched)
            self.campaign_proxy.invalidate()
            self.campaign_table.resizeColumnsToContents()
            logger.info("Данные кампаний аккаунта обновлены (через /campaigns)")

        except Exception as e:
            logger.error(f"Ошибка: {e}", exc_info=True)
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить кампании:\n{e}")
        finally:
            dlg.close()
    def _get_fb_adset_data_with_retry(self, account_id: str, token: str, retries: int = 3, delay: int = 3):
        """
        Загружает данные по адсетам из Facebook Marketing API с повторными попытками.
        """
        url = f"https://graph.facebook.com/v18.0/act_{account_id}/adsets"
        params = {
            "fields": "id,name,campaign_id,status,effective_status,daily_budget",
            "limit": 500,
            "access_token": token,
        }

        last_error = None
        for attempt in range(1, retries + 1):
            try:
                resp = requests.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                adsets_by_id = {}
                for adset in data.get("data", []):
                    adsets_by_id[adset["id"]] = adset

                return adsets_by_id

            except Exception as e:
                last_error = e
                logger.warning(f"[{attempt}/{retries}] Ошибка загрузки адсетов Facebook: {e}")
                time.sleep(delay)

        logger.error(f"Не удалось загрузить адсеты после {retries} попыток: {last_error}")
        return {}

    # -----------------------------
    # Обновление адсетов (Facebook + Keitaro)
    # -----------------------------
    def refresh_adsets(self):
        dlg = QProgressDialog("Загрузка адсетов…", None, 0, 0, self)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.show()

        try:
            # Загрузка GEOcfg для оценки CPA
            geo_sheet = safe_worksheet("GEOcfg")
            geo_config = load_geo_config_from_sheet(geo_sheet)  

            if not getattr(self.campaign_model, "_data", None):
                logger.warning("Кампании ещё не загружены.")
                rows_from_sheet = fetch_adsets()
                enriched = []
                for row in rows_from_sheet:
                    color = evaluate_adset(row, geo_config)
                    enriched.append([*row, color])
                self.adset_model.update(enriched)
                self.adset_proxy.invalidate()
                self.adset_table.resizeColumnsToContents()
                return

            campaigns_rows = self.campaign_model._data
            acc_map = {}
            for row in campaigns_rows:
                try:
                    campaign_id = str(row[2]).strip()
                    account_id = str(row[4]).strip()
                    token = str(row[5]).strip()

                    if (not campaign_id.isdigit()) and len(row) > 3 and str(row[3]).strip().isdigit():
                        logger.warning("⚠️ Обнаружен перепутанный порядок колонок (cid/status). Исправляю.")
                        campaign_id = str(row[3]).strip()
                except Exception:
                    continue

                if not (account_id and token and campaign_id):
                    continue

                bucket = acc_map.setdefault(account_id, {"token": token, "campaign_ids": set()})
                bucket["campaign_ids"].add(campaign_id)

            allowed_status = {"ACTIVE", "PAUSED", "DISAPPROVED", "PENDING_REVIEW"}

            collected_rows = []
            seen_adset_ids = set()

            for acc_id, bundle in acc_map.items():
                token = bundle["token"]
                cmp_ids = bundle["campaign_ids"]

                try:
                    adsets_by_id = self._get_fb_adset_data(acc_id, token, date_preset="today")
                except Exception as e:
                    logger.warning("Не удалось получить адсеты для аккаунта %s: %s", acc_id, e)
                    adsets_by_id = {}

                for a in adsets_by_id.values():
                    aid = (a.get("id") or "").strip()
                    if not aid or aid in seen_adset_ids:
                        continue
                    if a.get("campaign_id") not in cmp_ids:
                        continue

                    status_val = (a.get("status") or "").upper()
                    eff_val = (a.get("effective_status") or "").upper()

                    st_for_filter = eff_val or status_val
                    if st_for_filter not in allowed_status:
                        continue

                    seen_adset_ids.add(aid)

                    name = a.get("name") or ""
                    spend = a.get("spend", "")
                    daily = a.get("daily_budget")
                    budget_str = ""
                    if daily is not None:
                        try:
                            budget_str = f"{int(daily) / 100:.2f} $"
                        except Exception:
                            budget_str = ""

                    # Получаем uCPC и CPA из данных
                    uCPC = a.get("uCPC", "")
                    CPA = a.get("CPA", "")

                    # Форматируем значения для отображения
                    uCPC_str = f"{uCPC:.2f}" if isinstance(uCPC, (int, float)) else uCPC
                    CPA_str = f"{CPA:.2f}" if isinstance(CPA, (int, float)) else CPA

                    row = [
                        name,
                        aid,
                        uCPC_str,  # uCPC
                        spend,
                        CPA_str,   # CPA Leads
                        status_val,
                        str(acc_id),
                        bundle["token"],
                        "", "", "",
                        eff_val,
                        "",
                        budget_str,
                    ]
                    
                    # Оцениваем CPA и получаем цвет для подсветки
                    color = evaluate_adset(row, geo_config)
                    row.append(color)  # Добавляем цвет в конец строки

                    collected_rows.append(row)

            self.adset_model.update(collected_rows)
            self.adset_proxy.invalidate()
            self.adset_table.resizeColumnsToContents()
            logger.info("Список адсетов обновлён: %d шт.", len(collected_rows))

        except Exception as e:
            logger.error(f"Ошибка загрузки адсетов: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить адсеты:\n{e}")
        finally:
            dlg.close()
    def _get_fb_adset_data(self, account_id: str, token: str, date_preset: str = "today"):
        base_url = "https://graph.facebook.com/v23.0"
        fields = "id,name,campaign_id,status,effective_status,daily_budget,lifetime_budget"

        acc = str(account_id).strip()
        if not acc.startswith("act_"):
            acc = f"act_{acc}"

        import json as _json

        adsets_by_id = {}
        params = {
            "fields": fields,
            "effective_status": _json.dumps(["ACTIVE", "PAUSED", "DISAPPROVED", "PENDING_REVIEW"]),
            "access_token": token,
            "limit": 200,
        }
        url = f"{base_url}/{acc}/adsets"

        while True:
            resp = requests.get(url, params=params, timeout=20)
            try:
                resp.raise_for_status()
                payload = resp.json()
            except Exception as e:
                logger.warning("adsets page error: %s", e)
                break

            for a in payload.get("data", []) or []:
                aid = a.get("id")
                if aid:
                    adsets_by_id[aid] = a

            paging = payload.get("paging") or {}
            cursors = paging.get("cursors") or {}
            after = cursors.get("after")
            if not after:
                break
            params["after"] = after

        if not adsets_by_id:
            return {}

        # Загружаем insights с uCPC и CPA
        ins_params = {
            "level": "adset",
            "fields": "adset_id,spend,cpc,cost_per_conversion",
            "date_preset": date_preset,
            "time_increment": 1,
            "limit": 500,
            "access_token": token,
        }
        ins_url = f"{base_url}/{acc}/insights"

        while True:
            ins = requests.get(ins_url, params=ins_params, timeout=20)
            try:
                ins.raise_for_status()
                ip = ins.json()
            except Exception as e:
                logger.warning("insights page error: %s", e)
                break

            for row in (ip.get("data") or []):
                aid = row.get("adset_id")
                if aid in adsets_by_id:
                    # Добавляем spend если есть
                    if 'spend' in row:
                        adsets_by_id[aid]["spend"] = row['spend']
                    # Добавляем uCPC (используем cpc)
                    if 'cpc' in row:
                        adsets_by_id[aid]["uCPC"] = float(row['cpc'])
                    # Добавляем CPA Leads (используем cost_per_conversion)
                    if 'cost_per_conversion' in row:
                        adsets_by_id[aid]["CPA"] = float(row['cost_per_conversion'])

            paging = ip.get("paging") or {}
            cursors = paging.get("cursors") or {}
            after = cursors.get("after")
            if not after:
                break
            ins_params["after"] = after

        return adsets_by_id
    def set_selected_adsets_budget(self):
        rows = [
            self.adset_proxy.mapToSource(idx).row()
            for idx in self.adset_table.selectionModel().selectedRows()
        ]
        if not rows:
            QMessageBox.warning(self, "Внимание", "Не выбрано ни одного AdSet")
            return

        dollars = self.adset_budget_spin.value()
        budget = int(dollars * 100)
        cnt, errs = 0, []

        for r in rows:
            name, aid, *_ = self.adset_model._data[r]
            token = self.adset_model._data[r][7]
            res = update_adset_budget(aid, token, daily_budget=budget)

            if res.get("success") or res.get("id") == aid:
                logger.info(f"💰 Бюджет ${dollars:.2f} установлен для «{name}»")
                send_telegram_message(f"💰 Бюджет ${dollars:.2f} установлен для «{name}»")

                self.adset_model._data[r] = (
                    *self.adset_model._data[r][:-1],
                    f"{dollars:.2f} $"
                )

                cnt += 1
            else:
                err = res.get("error", res)
                logger.error(f"Ошибка установки бюджета для «{name}»: {err}")
                errs.append(f"{name}: {err}")

        self.adset_model.dataChanged.emit(
            self.adset_model.index(0, 0),
            self.adset_model.index(len(self.adset_model._data) - 1, self.adset_model.columnCount() - 1)
        )
        self.adset_proxy.invalidate()

        QMessageBox.information(self, "Результат", f"Успешно: {cnt}\nОшибок: {len(errs)}")


    def disable_selected_campaigns(self):
        rows = [
            self.campaign_proxy.mapToSource(idx).row()
            for idx in self.campaign_table.selectionModel().selectedRows()
        ]
        if not rows:
            QMessageBox.warning(self, "Внимание", "Нечего отключать")
            return
        cnt, errs = 0, []

        for r in rows:
            row = self.campaign_model._data[r]
            name = row[1]
            cid = row[2]
            token = row[5]

            res = pause_campaign(cid, token)
            if res.get("success") or res.get("id") == cid:
                logger.info(f"🔴 Кампания «{name}» отключена")
                send_telegram_message(f"🔴 Кампания «{name}» отключена")
                cnt += 1
                self.campaign_model._data[r][3] = "PAUSED"
            else:
                err = res.get("error", res)
                logger.error(f"Ошибка отключения кампании «{name}»: {err}")
                errs.append(f"{name}: {err}")

        self.campaign_proxy.invalidateFilter()
        self.campaign_table.clearSelection()
        QMessageBox.information(self, "Результат", f"Отключено: {cnt}\nОшибок: {len(errs)}")


    def enable_selected_campaigns(self):
        rows = [
            self.campaign_proxy.mapToSource(idx).row()
            for idx in self.campaign_table.selectionModel().selectedRows()
        ]
        if not rows:
            QMessageBox.warning(self, "Внимание", "Нечего включать")
            return
        cnt, errs = 0, []

        for r in rows:
            row = self.campaign_model._data[r]
            name = row[1]
            cid = row[2]
            token = row[5]

            res = resume_campaign(cid, token)
            if res.get("success") or res.get("id") == cid:
                logger.info(f"🟢 Кампания «{name}» включена")
                send_telegram_message(f"🟢 Кампания «{name}» включена")
                cnt += 1
                self.campaign_model._data[r][3] = "ACTIVE"
            else:
                err = res.get("error", res)
                logger.error(f"Ошибка включения кампании «{name}»: {err}")
                errs.append(f"{name}: {err}")

        self.campaign_proxy.invalidateFilter()
        self.campaign_table.clearSelection()
        QMessageBox.information(self, "Результат", f"Включено: {cnt}\nОшибок: {len(errs)}")


    def disable_selected_adsets(self):
        rows = [
            self.adset_proxy.mapToSource(idx).row()
            for idx in self.adset_table.selectionModel().selectedRows()
        ]
        if not rows:
            QMessageBox.warning(self, "Внимание", "Нечего отключать")
            return
        cnt, errs = 0, []
        for r in rows:
            name, aid, *_ = self.adset_model._data[r]
            token = self.adset_model._data[r][7]
            res = pause_adset(aid, token)
            if res.get("success") or res.get("id") == aid:
                logger.info(f"🔴 AdSet «{name}» отключён")
                send_telegram_message(f"🔴 AdSet «{name}» отключён")
                cnt += 1
                self.adset_model._data[r][5] = "PAUSED"
            else:
                err = res.get("error", res)
                logger.error(f"Ошибка отключения AdSet «{name}»: {err}")
                errs.append(f"{name}: {err}")
        self.adset_proxy.invalidateFilter()
        self.adset_table.clearSelection()
        QMessageBox.information(self, "Результат", f"Отключено: {cnt}\nОшибок: {len(errs)}")


    def enable_selected_adsets(self):
        rows = [
            self.adset_proxy.mapToSource(idx).row()
            for idx in self.adset_table.selectionModel().selectedRows()
        ]
        if not rows:
            QMessageBox.warning(self, "Внимание", "Нечего включать")
            return
        cnt, errs = 0, []
        for r in rows:
            name, aid, *_ = self.adset_model._data[r]
            token = self.adset_model._data[r][7]
            res = resume_adset(aid, token)
            if res.get("success") or res.get("id") == aid:
                logger.info(f"🟢 AdSet «{name}» включён")
                send_telegram_message(f"🟢 AdSet «{name}» включён")
                cnt += 1
                self.adset_model._data[r][5] = "ACTIVE"
            else:
                err = res.get("error", res)
                logger.error(f"Ошибка включения AdSet «{name}»: {err}")
                errs.append(f"{name}: {err}")
        self.adset_proxy.invalidateFilter()
        self.adset_table.clearSelection()
        QMessageBox.information(self, "Результат", f"Включено: {cnt}\nОшибок: {len(errs)}")


    def _check_time_for_refresh(self):
        now = datetime.now(pytz.timezone("Europe/Moscow"))
        minute = now.minute

        if minute in [10, 40] and minute != self._last_refresh_minute:
            logger.info(f"🔁 Автообновление: {minute} минута")

            if get_auto_refresh_campaigns():
                self.refresh_campaigns()

            if get_auto_refresh_adsets():
                self.refresh_adsets()

            self._last_refresh_minute = minute
        elif minute not in [10, 40]:
            self._last_refresh_minute = None


    def toggle_auto(self):
        if not self.worker or not self.worker.isRunning():
            self.worker = AutoControlWorker(self.spin.value())
            self.worker.start()
            self.status_lbl.setText(f"Автоконтроль: Запущен ({self.spin.value()} мин)")
            self.btn_toggle_auto.setText("Остановить автоконтроль")
            logger.info("Автоконтроль запущен")
        else:
            self.worker.stop()
            self.worker.wait()
            self.status_lbl.setText("Автоконтроль: Остановлен")
            self.btn_toggle_auto.setText("Запустить автоконтроль")
            logger.info("Автоконтроль остановлен")


    def _update_timer_interval(self, val):
        self.timer.start(val * 60 * 1000)


    def _auto_refresh(self):
        self.refresh_campaigns()
        self.refresh_adsets()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CampaignManager()
    window.show()
    sys.exit(app.exec())