"""Сервисный слой для парсинга."""

import logging

from contextlib import suppress

from PyQt6.QtCore import QThread

from src.extractors.golden_apple_extractor import GoldenAppleExtractor
from src.parsers.golden_apple_parser import GoldenAppleParser
from src.parsers_config.golden_apple_config import GoldenAppleConfig
from src.database.sqlite_manager import DatabaseManager
from src.workers.parser_worker import ParserWorker

from .ui_helpers import _update_parsing_status, _stop_handler, _parsing_success_handler

logger = logging.getLogger(__name__)


def parsing_on_click(obj) -> None:
    """Запуск парсинга выбранного сайта в фоновом потоке."""

    # Достаем ссылку и ключ напрямую из пролей ввода
    target_url = obj.target_url_input.text().strip()
    keyword = obj.key_word_input.text().strip()

    # Проверка на пустые поля (подсвечиваем красным, если менеджер забыл ввести данные)
    if not target_url or not keyword:
        if not target_url:
            obj.target_url_input.setStyleSheet("border: 1px solid #ef4444;")
        if not keyword:
            obj.key_word_input.setStyleSheet("border: 1px solid #ef4444;")
        # Выбрасываем понятную ошибку, чтобы её поймал внешний try-except в меню
        raise ValueError("Поля 'Ссылка' и 'Ключевое слово' не должны быть пустыми!")

    # Сбрасываем красные рамки, если данные введены корректно
    obj.target_url_input.setStyleSheet("")
    obj.key_word_input.setStyleSheet("")

    # Записываем введенные данные в кофиг парсера
    obj.parser.config.target_url = target_url
    obj.parser.config.keyword = keyword

    try:
        # Инициализируем таблицы базы данных (Слой Данных)
        table_name = obj.manager.init_for_config(obj.parser.config)
        logger.info(f"Инициализация БД. Таблица: {table_name}, файл: {obj.manager.db_path}")

    except Exception as e:
        error_msg = f"❌ Критическая ошибка инициализации базы данных: {e}"
        logger.error(error_msg, exc_info=True)

        # Освобождаем ресурсы базы данных
        if getattr(obj, "manager", None) is not None:
            with suppress(Exception):
                obj.manager.close()

        # Полностью очищаем битые объекты
        obj.manager = None
        obj.parser = None
        raise RuntimeError(f"Не удалось подготовить базу данных: {e}") from e

    # Блокируем элементы управления, чтобы избежать повторных кликов во время работы
    if hasattr(obj, "btn_send_scanning"):
        obj.btn_send_scanning.setEnabled(False)

    if hasattr(obj, "btn_send_parsing"):
        obj.btn_send_parsing.setEnabled(False)

    # Включаем кнопку отмены
    if hasattr(obj, "btn_cancel_parsing"):
        obj.btn_cancel_parsing.setEnabled(True)

    # Выводим информацию о старте в окно логов (используем уже извлеченные переменные)
    obj.result_display.append(f"⏳ Запуск парсера для сайта: {target_url}, ключ: {keyword}")
    logger.info(f"Старт парсера по адресу {target_url}")

    # Включаем кнопки просмотра и экспорта результатов
    if hasattr(obj, "btn_preview_parsing"):
        obj.btn_preview_parsing.setEnabled(True)

    if hasattr(obj, "btn_export_parsing"):
        obj.btn_export_parsing.setEnabled(True)

    # Сначала создаем чистый системный поток QThread
    obj.parser_thread = QThread()

    # Затем создаем рабочий объект (Воркер) и передаем ему готовый парсер из объекта окна
    obj.parser_worker = ParserWorker(parser=obj.parser)

    # ИСПРАВЛЕНО: Прикрепляем колбэк прогресса к ПРАВИЛЬНОМУ объекту парсера через obj.
    obj.parser.progress_callback = obj.parser_worker.progress_signal.emit

    # Перемещаем воркер в фоновый поток
    obj.parser_worker.moveToThread(obj.parser_thread)

    # Связываем запуск потока с выполнением метода run() воркера
    obj.parser_thread.started.connect(obj.parser_worker.run)

    # АВТОМАТИЧЕСКАЯ ЦЕПОЧКА ОЧИСТКИ при завершении потока:
    obj.parser_worker.finished_signal.connect(obj.parser_thread.quit)
    obj.parser_worker.stop_signal.connect(obj.parser_thread.quit)

    # Безопасное удаление треда и воркера из памяти операционной системы
    obj.parser_thread.finished.connect(obj.parser_thread.deleteLater)
    obj.parser_thread.finished.connect(obj.parser_worker.deleteLater)

    # Подключаем сигналы воркера к функциям обновления UI вашего приложения
    obj.parser_worker.progress_signal.connect(lambda msg: _update_parsing_status(obj, msg))
    obj.parser_worker.finished_signal.connect(lambda path: _parsing_success_handler(obj, path))
    obj.parser_worker.stop_signal.connect(lambda msg: _stop_handler(obj, msg))

    # Запускаем фоновый поток выполнения Playwright
    obj.parser_thread.start()


def prepare_parsing(obj) -> None:
    """Сборка парсера."""
    config = GoldenAppleConfig()  # Конфиг по умолчанию
    extractor = GoldenAppleExtractor(config)
    obj.manager = DatabaseManager()
    obj.parser = GoldenAppleParser(config=config, extractor=extractor, manager=obj.manager)


def parsing_cancel_on_click(obj) -> None:
    """Обработчик нажатия на кнопку 'ОТМЕНИТЬ' во время парсинга."""
    # Проверяем, запущен ли поток парсера в данный момент
    if hasattr(obj, "parser_thread") and obj.parser_thread.isRunning():
        logger.info("Запрос на отмену сканирования отправлен пользователем...")

        # Выводим красивый статус пользователю в текстовую панель
        if hasattr(obj, "result_display"):
            obj.result_display.append("🛑 Останавливаем парсинг, пожалуйста, подождите...")

        # Делаем кнопку отмены временно неактивной, чтобы избежать спам-кликов
        if hasattr(obj, "btn_cancel_parsing"):
            obj.btn_cancel_parsing.setEnabled(False)

        # Поднимаем потокобезопасный флаг остановки внутри воркера.
        if hasattr(obj, "parser_worker"):
            obj.parser_worker.stop()
    else:
        logger.warning("Невозможно отменить парсинг: процесс не запущен или уже завершен.")
