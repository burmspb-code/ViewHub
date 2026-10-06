import pytest
from unittest.mock import MagicMock

from src.workers.scanner_worker import ScannerWorker


@pytest.fixture
def mock_scanner():
    """Фикстура базового сканера для подстановки в воркер."""
    scanner = MagicMock()
    # По умолчанию имитируем успешный возврат тестовых данных
    scanner.run_scanning.return_value = {"status": "success", "items_count": 42}
    return scanner


def test_scanner_worker_happy_path(qtbot, mock_scanner):
    """Проверяет успешный цикл работы воркера без прерываний."""
    worker = ScannerWorker(scaner=mock_scanner)

    # Подключаем qtbot к сигналу завершения и ждем передачи данных
    with qtbot.wait_signal(worker.finished_signal) as blocker:
        worker.run()

    # Проверяем контракт: сканер вызывался с аргументом worker
    mock_scanner.run_scanning.assert_called_once_with(worker=worker)

    # Проверяем, что в интерфейс улетели именно результаты сканирования
    assert blocker.args[0] == {"status": "success", "items_count": 42}


def test_scanner_worker_was_stopped(qtbot, mock_scanner):
    """Проверяет, что если воркер остановили, он возвращает None."""
    worker = ScannerWorker(scaner=mock_scanner)

    # Имитируем команду "Стоп" из интерфейса перед запуском или во время
    worker.stop()
    assert worker.is_stopped() is True

    with qtbot.wait_signal(worker.finished_signal) as blocker:
        worker.run()

    # В интерфейс должен вернуться строго None, сигнализируя об отмене
    assert blocker.args[0] is None


def test_scanner_worker_exception_handling(qtbot, mock_scanner, caplog):
    """Проверяет, что при краше сканера воркер не падает и тушит поток безопасно."""
    # Заставляем mock выкинуть критическую ошибку (например, ошибка сети при парсинге)
    mock_scanner.run_scanning.side_effect = RuntimeError("Ошибка прокси сервера")

    worker = ScannerWorker(scaner=mock_scanner)

    with qtbot.wait_signal(worker.finished_signal) as blocker:
        # Запуск не должен вызывать падение pytest, ошибка должна отловиться внутри try-except
        worker.run()

    # Кнопки в UI разблокируются, так как сигнал отмены всё равно ушел
    assert blocker.args[0] is None

    # Проверяем, что логгер зафиксировал traceback критической ошибки
    assert "Критическая ошибка в потоке" in caplog.text
