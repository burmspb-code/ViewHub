import logging

from contextlib import suppress
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from src.core.paths import app_root, ensure_writable

# Ограничение размера файлового лога. На сервере лог не должен расти
# бесконечно: при долгой работе он способен занять весь диск.
LOG_MAX_BYTES = 2 * 1024 * 1024  # 2 МБ на текущий файл
LOG_BACKUP_COUNT = 3  # плюс три предыдущие версии

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


def _resolve_log_dir() -> Path:
    """
    Каталог для файловых логов рядом с приложением.

    Если рядом с бинарником писать нельзя (read-only каталог на сервере),
    используем временный каталог, иначе логирование падало бы на старте.
    """
    return ensure_writable(app_root() / "logs")


def reset_log_file() -> bool:
    """
    Удаляет файловый лог вместе с ротациями.

    Вызывается в начале каждой сессии парсинга, поэтому лог всегда
    описывает только текущий запуск, а не историю предыдущих.

    Файл удаляется целиком, а не обрезается: обработчик открыт с
    delay=True и пересоздаст файл при первой же записи.

    Возвращает True, если лог был удалён.
    """
    root_logger = logging.getLogger("")
    removed = False

    for handler in root_logger.handlers:
        if not isinstance(handler, RotatingFileHandler):
            continue

        base_name = handler.baseFilename
        handler.close()

        candidates = [base_name]
        candidates.extend(f"{base_name}.{index}" for index in range(1, LOG_BACKUP_COUNT + 1))

        for candidate in candidates:
            with suppress(OSError):
                Path(candidate).unlink()
                removed = True

        # Обработчик остаётся подключённым: delay=True заставит его создать
        # новый файл при следующей записи.
        handler.stream = None

    return removed


def setup_logger(name: str = "", level: int = logging.INFO) -> Logger:
    """
    Инициализирует базовые параметры логгера.

    Для корневого логгера (name == "") дополнительно создаётся файловый
    обработчик. Раньше файловых логов не было вовсе, поэтому в собранном
    приложении падение парсера было невозможно диагностировать: всё уходило
    только в QTextEdit, а исключение внутри QThread не доходит до sys.excepthook.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Файловый обработчик добавляем только для корневого логгера и только один раз.
    if name == "" and not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        file_handler = RotatingFileHandler(
            str(_resolve_log_dir() / "viewhub.log"),
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(file_handler)

    return logger


def register_gui_handler(log_display_widget, level: int = logging.INFO):
    """
    Безопасно находит корневой логгер и жестко привязывает графическое окно.

    Удаляется ТОЛЬКО предыдущий QTextEditHandler. Раньше здесь вызывался
    handlers.clear(), который удалял и файловый обработчик — из-за чего
    логи в файл не попадали ни при каких настройках.
    """
    root_logger = logging.getLogger("")
    root_logger.setLevel(level)

    # Убираем только старые GUI-обработчики, файловый логгер сохраняем.
    for handler in root_logger.handlers:
        if isinstance(handler, QTextEditHandler):
            root_logger.removeHandler(handler)

    # Создаем и добавляем наш QTextEditHandler
    qt_handler = QTextEditHandler(log_display_widget)
    qt_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s]: %(message)s", datefmt="%H:%M:%S"))
    root_logger.addHandler(qt_handler)
