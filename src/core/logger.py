import logging
from logging import Logger
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

# Путь к файлу с логами
log_dir = Path.cwd() / "logs"
# parents=True — создаст все промежуточные папки, если их нет
# exist_ok=True — не выдаст ошибку, если папка уже существует
log_dir.mkdir(parents=True, exist_ok=True)
log_file_path = str(log_dir / "viewhub.log")


# Специальный мост-передатчик для потокобезопасности Qt
class LogSignals(QObject):
    """
    Контейнер сигналов Qt для потокобезопасной передачи логов.

    Используется как посредник (мост) между стандартным модулем logging
    и графическими виджетами PyQt6. Позволяет безопасно отправлять текстовые
    сообщения в UI-поток из фоновых потоков (например, при сетевых запросах),
    предотвращая падение графического ядра.

    Сигналы:
        append_log (pyqtSignal): Передает строку с текстом лога для добавления в виджет.
    """
    append_log = pyqtSignal(str)


class QTextEditHandler(logging.Handler):
    """
    Кастомный хэндлер, который перенаправляет логи в виджет QTextEdit.
    Использует сигналы Qt для безопасной работы из любых потоков.
    """
    def __init__(self, text_edit_widget=None):
        super().__init__()
        self.widget = text_edit_widget
        self.signals = LogSignals()
        # Подключаем сигнал к слоту добавления текста в виджет
        if text_edit_widget:
            self.signals.append_log.connect(self.widget.append)

    def emit(self, record):
        """
        Перехватить запись лога и отправить её в графический интерфейс.

        Форматирует объект записи (LogRecord) в текстовую строку в соответствии
        с заданными правилами логгера и генерирует потокобезопасный сигнал
        для отображения текста в виджете PyQt6.

        Args:
            record (logging.LogRecord): Объект, содержащий всю информацию о событии лога.
        """
        # Простая защита: отправляем лог в окно, только если виджет существует
        if self.widget:
            msg = self.format(record)
            self.signals.append_log.emit(msg)


def setup_logger(name: str) -> Logger:
    """Настройка логера для записи в файл и вывода в консоль."""

    logger = logging.getLogger(name)  # Создаем объект логера
    logger.setLevel(logging.DEBUG)  # Устанавливаем уровень логирования

    # Предотвращаем дублирование логов
    if not logger.handlers:
        # Настраиваем единый строковый формат
        formatter = logging.Formatter("%(asctime)s - [%(levelname)s] - %(message)s", datefmt="%H:%M:%S")

        # Файловый хэндлер (используем правильную переменную log_file_path)
        file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Консольный хэндлер (добавляем в текущий logger вместо несуществующего root)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
