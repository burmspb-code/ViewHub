import logging
from logging import Logger

from PyQt6.QtCore import QObject, pyqtSignal

# Отключаем DEBUG и INFO спам от сетевых библиотек и asyncio глобально
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.INFO)


class LogSignals(QObject):
    """
    Контейнер сигналов Qt для потокобезопасной передачи логов.
    """
    append_log = pyqtSignal(str)


class QTextEditHandler(logging.Handler):
    """
    Кастомный хэндлер, который перенаправляет логи в виджет QTextEdit.
    Оптимизирован для предотвращения зависаний при высокой интенсивности логов.
    """

    def __init__(self, text_edit_widget=None):
        super().__init__()
        self.widget = text_edit_widget
        self.signals = LogSignals()

        if text_edit_widget:
            self.signals.append_log.connect(self._safe_append_text)

    def _safe_append_text(self, text: str):
        """Быстрое и экономичное добавление текста в конец QTextEdit."""
        if not self.widget:
            return

        # Блокируем лишние сигналы перерисовки на время вставки текста
        self.widget.blockSignals(True)

        # Перемещаем курсор в самый конец и вставляем чистый текст с переносом строки
        cursor = self.widget.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.widget.setTextCursor(cursor)
        self.widget.insertPlainText(text + "\n")

        # Возвращаем сигналы обратно
        self.widget.blockSignals(False)

        # Автоматическая прокрутка вниз
        self.widget.ensureCursorVisible()

    def emit(self, record):
        if self.widget:
            msg = self.format(record)
            self.signals.append_log.emit(msg)


def setup_logger(name: str = "", level: int = logging.INFO) -> Logger:
    """Инициализирует базовые параметры логгера."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger


def register_gui_handler(log_display_widget, level: int = logging.INFO):
    """
    Безопасно находит корневой логгер, очищает старые хэндлеры
    и жестко привязывает графическое окно.
    """
    root_logger = logging.getLogger("")
    root_logger.setLevel(level)

    # Очищаем только старые хэндлеры, чтобы не было дублей
    if root_logger.handlers:
        root_logger.handlers.clear()

    # Создаем и добавляем наш QTextEditHandler
    qt_handler = QTextEditHandler(log_display_widget)
    qt_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s]: %(message)s", datefmt="%H:%M:%S"))
    root_logger.addHandler(qt_handler)