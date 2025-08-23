from PySide2.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide2.QtGui import QBrush, QColor


class CampaignTableModel(QAbstractTableModel):
    headers = ["KING", "Название", "Status", "Campaign ID", "Account ID", "Token"]

    def __init__(self, data=None):
        super().__init__()
        self._data = data or []
        self._colors = []  # Пока не используется, но оставлено для возможной подсветки

    def update(self, data, colors=None):
        self.beginResetModel()
        self._data = data or []
        self._colors = colors or [None] * len(self._data)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]

    def data(self, index, role):
        if not index.isValid():
            return None

        r, c = index.row(), index.column()
        val = self._data[r][c]

        if role == Qt.ItemDataRole.DisplayRole:
            return val

        # Подсветка колонки с CPA, если color передан (оставлено на будущее)
        if role == Qt.ItemDataRole.BackgroundRole and c == 4:
            color = self._colors[r]
            if color == "red":
                return QBrush(QColor("#D32F2F"))
            elif color == "orange":
                return QBrush(QColor("#F57C00"))
            elif color == "yellow":
                return QBrush(QColor("#FBC02D"))
            elif color == "green":
                return QBrush(QColor("#388E3C"))

        # Подсветка имени кампании по статусу
        if role == Qt.ItemDataRole.BackgroundRole and c == 1:
            status = self._data[r][2]
            if status == "ACTIVE":
                return QBrush(QColor("#388E3C"))
            elif status == "PAUSED":
                return QBrush(QColor("#D32F2F"))

        if role == Qt.ItemDataRole.ForegroundRole:
            return QBrush(QColor("#000000"))

        return None


class AdSetTableModel(QAbstractTableModel):
    headers = [
        "AdSet Name", "AdSet ID", "uCPC", "Spend", "CPA",
        "Status", "Account ID", "Token", "Leads",
        "ManualPause", "KING", "Effective Status", "Ad Name", "Budget"
    ]

    def __init__(self, data=None, colors=None):
        super().__init__()
        self._data = data or []
        self._colors = colors or []

    def update(self, data, colors=None):
        self.beginResetModel()
        self._data = data or []
        self._colors = colors or [None] * len(self._data)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]

    def data(self, index, role):
        if not index.isValid():
            return None

        r, c = index.row(), index.column()
        val = self._data[r][c]

        if role == Qt.ItemDataRole.DisplayRole:
            return val

        # 🔴 Подсветка CPA
        if role == Qt.ItemDataRole.BackgroundRole and c == 4:
            color = self._colors[r]
            if color == "red":
                return QBrush(QColor("#D32F2F"))
            elif color == "orange":
                return QBrush(QColor("#F57C00"))
            elif color == "yellow":
                return QBrush(QColor("#FBC02D"))
            elif color == "green":
                return QBrush(QColor("#388E3C"))

        # 🟣 Подсветка имени AdSet по EffectiveStatus и Status
        if role == Qt.ItemDataRole.BackgroundRole and c == 0:
            status = self._data[r][5]
            effective_status = self._data[r][11].upper()

            if status == "ACTIVE":
                if effective_status == "DISAPPROVED":
                    return QBrush(QColor("#9C27B0"))  # Фиолетовый
                elif effective_status == "PENDING_REVIEW":
                    return QBrush(QColor("#2196F3"))  # Синий
                else:
                    return QBrush(QColor("#388E3C"))  # Зелёный
            elif status == "PAUSED":
                return QBrush(QColor("#D32F2F"))  # Красный

        # Белый текст для читаемости
        if role == Qt.ItemDataRole.ForegroundRole:
            return QBrush(QColor("#000000"))

        return None
