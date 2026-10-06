import logging
from PyQt6.QtWidgets import QTextEdit
from unittest.mock import MagicMock

from src.core.logger import QTextEditHandler, register_gui_handler


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


def test_register_gui_handler_clears_old_handlers(qtbot):
    """Проверяет, что старые хэндлеры очищаются, а новый успешно регистрируется."""
    mock_widget = MagicMock(spec=QTextEdit)
    root_logger = logging.getLogger("")

    # 1. Принудительно добавляем мусорный хэндлер
    root_logger.addHandler(logging.StreamHandler())
    assert len(root_logger.handlers) > 0

    # 2. Вызываем регистрацию нашего GUI хэндлера
    register_gui_handler(mock_widget, level=logging.DEBUG)

    # 3. Проверяем результат: старый удален, наш добавлен
    assert len(root_logger.handlers) == 1
    assert isinstance(root_logger.handlers[0], QTextEditHandler)
    assert root_logger.level == logging.DEBUG

    # Очищаем за собой корневой логгер после теста
    root_logger.handlers.clear()
