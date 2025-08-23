import json
import os
from typing import Dict

from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFormLayout, QCheckBox
)

from unitool.fb_api import refresh_session  # для перезапуска сессии
from unitool.config import load_config, save_config

class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.config = load_config()

        # Основная форма
        form = QFormLayout()

        self.api_key_input = QLineEdit(self.config.get("sync_api_key", ""))
        self.proxy_input = QLineEdit(self.config.get("proxy", ""))
        self.fb_token_input = QLineEdit(self.config.get("fb_access_token", ""))

        self.use_proxy_checkbox = QCheckBox("Использовать прокси")
        self.use_proxy_checkbox.setChecked(self.config.get("use_proxy", True))

        self.auto_refresh_campaigns_checkbox = QCheckBox("Автообновление кампаний")
        self.auto_refresh_campaigns_checkbox.setChecked(self.config.get("auto_refresh_campaigns", True))

        self.auto_refresh_adsets_checkbox = QCheckBox("Автообновление адсетов")
        self.auto_refresh_adsets_checkbox.setChecked(self.config.get("auto_refresh_adsets", True))

        # Добавляем поля в форму
        form.addRow("Sync API Key:", self.api_key_input)
        form.addRow("SOCKS5 Proxy (ip:port:user:pass):", self.proxy_input)
        form.addRow(self.use_proxy_checkbox)
        form.addRow(self.auto_refresh_campaigns_checkbox)
        form.addRow(self.auto_refresh_adsets_checkbox)

        self.layout().addLayout(form)

        # Кнопка сохранения
        self.save_button = QPushButton("💾 Сохранить настройки")
        self.save_button.clicked.connect(self.save_config)
        self.layout().addWidget(self.save_button)

    def save_config(self):
        """Сохраняет настройки в config.json и перезапускает сессию."""
        config = {
            "sync_api_key": self.api_key_input.text().strip(),
            "proxy": self.proxy_input.text().strip(),
            "use_proxy": self.use_proxy_checkbox.isChecked(),
            "auto_refresh_campaigns": self.auto_refresh_campaigns_checkbox.isChecked(),
            "auto_refresh_adsets": self.auto_refresh_adsets_checkbox.isChecked()
        }

        try:
            save_config(config)
            refresh_session()
            QMessageBox.information(self, "Готово", "Настройки успешно сохранены.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить настройки:\n{e}")
