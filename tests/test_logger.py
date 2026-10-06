import logging
import os
from PyQt6.QtWidgets import QTextEdit
from unittest.mock import MagicMock

from src.core.logger import QTextEditHandler, register_gui_handler, setup_logger


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


def test_setup_logger_adds_file_handler_once():
    """Проверяет, что корневой логгер получает файловый обработчик ровно один раз."""
    root_logger = logging.getLogger("")

    setup_logger(name="", level=logging.INFO)
    file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]

    assert len(file_handlers) == 1

    # Повторный вызов не должен плодить дубликаты
    setup_logger(name="", level=logging.INFO)
    assert len([h for h in root_logger.handlers if isinstance(h, logging.FileHandler)]) == 1
