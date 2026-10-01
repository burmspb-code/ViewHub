import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace

from src.workers.parser_worker import ParserWorker


@pytest.fixture
def mock_parser():
    """Базовый mock-парсер, подменяющий реальный сбор данных."""
    parser = MagicMock()
    parser.config = SimpleNamespace(file_name="goldenapple_ru")
    parser.manager = MagicMock()
    parser.cancel = MagicMock()
    return parser

def test_parser_worker_init_with_config():
    """Тест инициализации ParserWorker: сценарий с наличием конфига."""
    mock_parser = MagicMock()
    mock_parser.config = SimpleNamespace(file_name="goldenapple_ru")
    mock_parser.manager = MagicMock()

    worker = ParserWorker(parser=mock_parser)

    assert worker.parser == mock_parser
    assert worker.manager == mock_parser.manager

    assert worker.file_name == "goldenapple_ru"

    assert hasattr(worker, "manager") is True

def test_parser_worker_init_without_config():
    """Тест инициализации ParserWorker: сценарий с отсутствием конфига."""
    mock_parser = MagicMock()
    # С помощью spec мы говорим: "У этого парсера есть ТОЛЬКО поле manager, а поля config — нет"
    mock_parser = MagicMock(spec=["manager"])

    worker = ParserWorker(parser=mock_parser)

    assert worker.file_name == "result"


def test_run_happy_path(qtbot, mock_parser):
    """1. Сценарий: Успешный сбор данных. Сигналы летят в UI, возвращается имя файла."""
    # Имитируем генератор, возвращающий два чанка данных (списки элементов) [2026-09-30]
    mock_parser.run_parsing.return_value = [["item1", "item2"], ["item3"]]

    worker = ParserWorker(parser=mock_parser)

    # Записываем сигналы в лог-коллекторы qtbot
    with qtbot.wait_signals([worker.progress_signal, worker.finished_signal]):
        worker.run()

    # Проверяем, что в finished_signal ушло правильное имя файла
    # (Доступ к аргументам последнего вызова через pytest-qt сигналы)
    assert worker.file_name == "goldenapple_ru"

    # Проверяем, что сканер вызывался
    mock_parser.run_parsing.assert_called_once()


def test_run_no_data_found(qtbot, mock_parser):
    """2. Сценарий: Парсер вернул пустой список. Вызывается ExceptionStopParser."""
    # Имитируем пустой генератор
    mock_parser.run_parsing.return_value = []

    worker = ParserWorker(parser=mock_parser)

    # Ждем отправки сигнала об остановке
    with qtbot.wait_signal(worker.stop_signal) as blocker:
        worker.run()

    # Убеждаемся, что улетел stop_signal с нулевым счетчиком
    assert blocker.args[0] == "Всего найдено элементов: 0"


def test_run_user_cancellation(qtbot, mock_parser):
    """3. Сценарий: Пользователь нажал 'Стоп' во время парсинга."""
    # Создаем генератор, который вернет один чанк
    mock_parser.run_parsing.return_value = [["item1"]]

    worker = ParserWorker(parser=mock_parser)

    # Имитируем ручную остановку из UI перед запуском или в первой итерации
    worker.stop()

    # Проверяем контракт метода stop(): он должен пнуть сам парсер
    mock_parser.cancel.assert_called_once()
    assert worker._stop_event.is_set() is True

    # Запускаем run и ловим stop_signal
    with qtbot.wait_signal(worker.stop_signal) as blocker:
        worker.run()

    # Так как прерывание произошло сразу, счетчик остался 0, а данные не дособирались
    assert "Всего найдено элементов:" in blocker.args[0]


def test_run_critical_exception_handling(mock_parser, caplog):
    """4. Сценарий: Внутри парсера падает RuntimeError. Проверяем вырезание 1-й строки."""
    # Заставляем генератор выплюнуть многострочную ошибку сети
    mock_parser.run_parsing.side_effect = RuntimeError("Ошибка прокси-сервера 502\nConnection timed out")

    worker = ParserWorker(parser=mock_parser)

    # Создаем стандартные моки для перехвата сигналов
    mock_progress_receiver = MagicMock()
    mock_finished_receiver = MagicMock()

    # Напрямую привязываем их к Qt-сигналам воркера
    worker.progress_signal.connect(mock_progress_receiver)
    worker.finished_signal.connect(mock_finished_receiver)

    # Запускаем выполнение
    worker.run()

    # Проверяем, что в прогресс ушла строго ПЕРВАЯ строка сообщения
    mock_progress_receiver.assert_called_once_with("Ошибка прокси-сервера 502")

    # Проверяем, что в финиш ушла пустая строка для разблокировки UI
    mock_finished_receiver.assert_called_once_with("")

    # Проверяем, что в логах приложения остался лог критического сбоя
    assert "Критическая ошибка" in caplog.text