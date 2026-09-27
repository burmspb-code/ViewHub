"""Главный модуль запуска приложения."""

import sys
import logging

# Импортируем пакет src. В этот момент автоматически загрузится .env
# и настроится логгер ДО того, как импортируется PyQt и MainWindow.
import src # noqa: F401
from PyQt6.QtWidgets import QApplication
from src.windows_pq import MainWindow


def log_uncaught_exceptions(ex_cls, ex, tb):
    """Перехватывает любые невыловленные ошибки и пишет их в логгер."""
    logging.critical("!!! КРИТИЧЕСКАЯ ОШИБКА ПРИЛОЖЕНИЯ !!!", exc_info=(ex_cls, ex, tb))
    sys.exit(1)


# Регистрируем глобальный перехватчик ошибок
sys.excepthook = log_uncaught_exceptions

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
