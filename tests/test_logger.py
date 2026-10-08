import logging
import os
import sys

import pytest

from PyQt6.QtWidgets import QTextEdit
from unittest.mock import MagicMock

from src.core.logger import (
    LOG_BACKUP_COUNT,
    QTextEditHandler,
    register_gui_handler,
    reset_log_file,
    setup_logger,
)


@pytest.fixture
def isolated_log(tmp_path, monkeypatch):
    """Изолированный файловый лог во временном каталоге."""
    from src.core import logger as logger_module

    monkeypatch.setattr(logger_module, "_resolve_log_dir", lambda: tmp_path)

    root_logger = logging.getLogger("")
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    root_logger.handlers.clear()

    setup_logger(name="", level=logging.INFO)

    yield tmp_path / "viewhub.log"

    for handler in list(root_logger.handlers):
        handler.close()
    root_logger.handlers.clear()
    for handler in original_handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(original_level)


def test_reset_log_file_clears_previous_session(isolated_log):
    """Лог должен обнуляться на старте сеанса парсинга."""
    logging.getLogger("test").info("запись из прошлого сеанса")
    assert isolated_log.exists()

    assert reset_log_file() is True

    logging.getLogger("test").info("запись из текущего сеанса")
    content = isolated_log.read_text(encoding="utf-8")

    assert "прошлого сеанса" not in content
    assert "текущего сеанса" in content


def test_reset_log_file_keeps_handler_usable(isolated_log):
    """После обнуления логгер должен продолжать писать."""
    logging.getLogger("test").info("до обнуления")
    reset_log_file()
    logging.getLogger("test").info("после обнуления")

    content = isolated_log.read_text(encoding="utf-8")
    assert "после обнуления" in content


def test_log_is_rotated_not_grown_forever(tmp_path, monkeypatch):
    """Лог ограничен по размеру: иначе на сервере он съест диск."""
    from logging.handlers import RotatingFileHandler

    from src.core import logger as logger_module

    monkeypatch.setattr(logger_module, "_resolve_log_dir", lambda: tmp_path)

    root_logger = logging.getLogger("")
    original_handlers = list(root_logger.handlers)
    root_logger.handlers.clear()

    try:
        setup_logger(name="", level=logging.INFO)
        rotating = [h for h in root_logger.handlers if isinstance(h, RotatingFileHandler)]

        assert rotating, "должен быть обработчик с ротацией"
        assert rotating[0].maxBytes > 0
        assert rotating[0].backupCount == LOG_BACKUP_COUNT
    finally:
        for handler in list(root_logger.handlers):
            handler.close()
        root_logger.handlers.clear()
        for handler in original_handlers:
            root_logger.addHandler(handler)


def test_reset_returns_false_without_file_handlers():
    """Без файлового обработчика обнуление ничего не ломает."""
    root_logger = logging.getLogger("")
    original_handlers = list(root_logger.handlers)
    root_logger.handlers.clear()

    try:
        assert reset_log_file() is False
    finally:
        root_logger.handlers.clear()
        for handler in original_handlers:
            root_logger.addHandler(handler)


def test_qtextedit_handler_emits_signal(qtbot):
    """Проверяет, что при логировании хэндлер отправляет Qt-сигнал."""
    mock_widget = MagicMock(spec=QTextEdit)
    handler = QTextEditHandler(mock_widget)

    # Используем qtbot для перехвата сигнала append_log
    with qtbot.wait_signal(handler.signals.append_log) as blocker:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Тестовое сообщение лога",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

    # Проверяем, что сигнал был отправлен с правильным текстом
    assert blocker.args[0] == "Тестовое сообщение лога"


def test_qtextedit_handler_no_widget_does_not_crash():
    """Проверяет, что хэндлер работает без ошибок, если виджет не передан."""
    handler = QTextEditHandler(text_edit_widget=None)
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg="Тест без виджета", args=(), exc_info=None
    )
    # Метод должен выполниться без генерации AttributeError/NoneType ошибок
    handler.emit(record)


def test_register_gui_handler_keeps_file_handler(qtbot):
    """
    Проверяет, что GUI-обработчик НЕ стирает остальные хэндлеры.

    Раньше здесь был вызов handlers.clear(), который удалял и файловый логгер.
    Из-за этого в скомпилированном приложении не оставалось ни одного файлового
    лога: любая ошибка парсера на headless-сервере была невидима и выглядела
    как зависание программы.
    """
    mock_widget = MagicMock(spec=QTextEdit)
    root_logger = logging.getLogger("")

    file_handler = logging.FileHandler(os.devnull, encoding="utf-8")
    stream_handler = logging.StreamHandler()
    old_gui_handler = QTextEditHandler(MagicMock(spec=QTextEdit))

    for handler in (file_handler, stream_handler, old_gui_handler):
        root_logger.addHandler(handler)

    # Вызываем регистрацию нашего GUI хэндлера
    register_gui_handler(mock_widget, level=logging.DEBUG)

    # Старый GUI-обработчик удалён, чтобы в панели не было дублей
    assert old_gui_handler not in root_logger.handlers

    # Файловый и сторонние обработчики сохранены
    assert file_handler in root_logger.handlers
    assert stream_handler in root_logger.handlers

    # Новый GUI-обработчик зарегистрирован ровно один
    assert len([h for h in root_logger.handlers if isinstance(h, QTextEditHandler)]) == 1
    assert root_logger.level == logging.DEBUG

    # Убираем за собой корневой логгер
    for handler in (file_handler, stream_handler):
        root_logger.removeHandler(handler)
        handler.close()


def test_gui_handler_strips_traceback(qtbot):
    """
    В панель журнала GUI не должен попадать трейлбек.

    В логе на сервере ошибка загрузки карточки давала ~15 строк трейлбека
    Playwright прямо в окне журнала. Подробности нужны в файле, в интерфейсе
    достаточно строки о товаре.
    """
    handler = QTextEditHandler(MagicMock(spec=QTextEdit))
    handler.setFormatter(logging.Formatter("[%(levelname)s]: %(message)s"))

    try:
        raise TimeoutError("Timeout 60000ms exceeded")
    except TimeoutError:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Не удалось загрузить карточку ID %s",
            args=("99000037750",),
            exc_info=sys.exc_info(),
        )

    with qtbot.wait_signal(handler.signals.append_log) as blocker:
        handler.emit(record)

    text = blocker.args[0]
    assert "99000037750" in text
    assert "Traceback" not in text
    assert "TimeoutError" not in text
    assert "exc_info" not in text


def test_gui_handler_keeps_file_record_untouched(tmp_path, monkeypatch):
    """
    Обработчик GUI не должен портить запись для файлового логгера.

    LogRecord общий для всех обработчиков: если бы GUI присвоил exc_info=None
    напрямую, трейлбек исчез бы и из logs/viewhub.log.
    """
    from src.core import logger as logger_module

    monkeypatch.setattr(logger_module, "_resolve_log_dir", lambda: tmp_path)

    root_logger = logging.getLogger("")
    original_handlers = list(root_logger.handlers)
    root_logger.handlers.clear()

    try:
        setup_logger(name="", level=logging.INFO)
        gui_handler = QTextEditHandler(MagicMock(spec=QTextEdit))
        root_logger.addHandler(gui_handler)

        try:
            raise TimeoutError("Timeout 60000ms exceeded")
        except TimeoutError:
            logging.getLogger("test").exception("Не удалось загрузить карточку ID %s", "99000037750")

        content = (tmp_path / "viewhub.log").read_text(encoding="utf-8")
        assert "Traceback" in content
        assert "TimeoutError" in content
        assert gui_handler.widget is not None
    finally:
        for handler in list(root_logger.handlers):
            handler.close()
        root_logger.handlers.clear()
        for handler in original_handlers:
            root_logger.addHandler(handler)


def test_setup_logger_adds_file_handler_once():
    """Проверяет, что корневой логгер получает файловый обработчик ровно один раз."""
    root_logger = logging.getLogger("")

    setup_logger(name="", level=logging.INFO)
    file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]

    assert len(file_handlers) == 1

    # Повторный вызов не должен плодить дубликаты
    setup_logger(name="", level=logging.INFO)
    assert len([h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]) == 1
