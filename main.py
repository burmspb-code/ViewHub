"""Главный модуль запуска приложения."""
import logging
# СРАЗУ настраиваем базовый уровень для root логгера
from src.core.logger import setup_logger
setup_logger(name="", level=logging.INFO)

# Только ТЕПЕРЬ импортируем всё остальное.
# Все модули гарантированно увидят уже готовый root-логгер с нужным уровнем!
import sys # noqa: E402
import traceback # noqa: E402

from PyQt6.QtWidgets import QApplication # noqa: E402

from src.windows_pq import MainWindow # noqa: E402


def log_uncaught_exceptions(ex_cls, ex, tb):
    """Перехватывает любые ошибки PyQt и выводит их в консоль."""
    text = "".join(traceback.format_exception(ex_cls, ex, tb))
    print("!!! КРИТИЧЕСКАЯ ОШИБКА ПРИЛОЖЕНИЯ !!!\n", text)
    sys.exit(1)

# Регистрируем глобальный перехватчик ошибок
sys.excepthook = log_uncaught_exceptions

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
