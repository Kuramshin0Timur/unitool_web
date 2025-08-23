import logging
from logging.handlers import RotatingFileHandler

def setup_logging(log_file: str, ui_log_widget=None):
    """
    Настраивает вывод в файл и (опционально) в QTextEdit.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Файловый логер с ротацией
    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(fh)

    # Qt-Handler для вывода в QTextEdit
    if ui_log_widget is not None:
        class QtHandler(logging.Handler):
            def __init__(self, widget):
                super().__init__()
                self.widget = widget
            def emit(self, record):
                msg = self.format(record)
                self.widget.append(msg)

        qh = QtHandler(ui_log_widget)
        qh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        logger.addHandler(qh)

    return logger
