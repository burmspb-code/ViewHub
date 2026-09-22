"""Модуль управления бизнес-логикой проекта."""

import json
import logging
from contextlib import suppress

import httpx  # Изолированный и стабильный сетевой клиент вместо requests
from PyQt6.QtCore import QThread

from scaners.async_scan_ep import AsyncScanEndpoint
from src.auth.api_client import login_to_django
from src.extractors.gardarika_extractor import GardarikaExtractor
from src.parser_worker import ParserWorker
from src.parsers.gardarika_parser import GardarikaParser
from src.parsers_config.gardarika_config import GardarikaConfig
from src.savers import XLSXSaver
from src.scaner_worker import ScanerWorker

logger = logging.getLogger(__name__)

# ======================= Логика обработки пользовательских запросов ============================

def auth_on_click(obj) -> None:
    """
    Аутентификация через внешний API клиент.
    """
    url = obj.api_url_input.text().strip()
    username = obj.login_input.text().strip()
    password = obj.password_input.text()

    # Проверяем заполненность полей
    if not url or not username or not password:
        logger.warning("Заполните все поля для авторизации.")
        return

    # Информируем пользователя о начале процесса
    pas_mask = "*" * len(password)
    logger.info(f"Отправка запроса на {url}...")

    # Окно «Данные/Результат» обновляем напрямую
    obj.result_display.append(f"Запрос: POST {url}\nТело: username='{username}', password='{pas_mask}'")

    # Вызываем сетевую логику из нашего изолированного модуля
    result = login_to_django(url, username, password)

    # Обрабатываем стандартизированный ответ от модуля api_client
    if result["success"]:
        logger.info(f"УСПЕХ! {result['message']}")
        obj.result_display.append(f"Статус: Авторизован.\nТокен: {result['token']}")

        # Сохраняем токен и базовый url в класс главного окна
        obj.auth_token = result["token"]
        obj.base_url = url

        # Очищаем поля ввода
        # obj.api_url_input.clear()
        # obj.login_input.clear()
        # obj.password_input.clear()
    else:
        logger.error(f"{result['message']}")
        if "details" in result:
            obj.result_display.append(f"Детали ошибки:\n{result['details']}")
        else:
            obj.result_display.append("Статус: Доступ отклонен.")


def request_on_click(obj) -> None:
    """
    Отправляет GET-запрос на Django API по полному пути через httpx.

    Args:
        obj: объект главного окна (MainWindow)

    Returns:
        None
    """
    # Проверяем, авторизован ли пользователь
    base_url = getattr(obj, "base_url", None)
    token = getattr(obj, "auth_token", None)

    if not base_url or not token:
        logger.error("Ошибка: вы не авторизованы. Сначала выполните вход.")
        obj.result_display.append("Статус: Запрос отклонен. Требуется авторизация.")
        return

    # Достаем полный URL эндпоинта из правильного виджета
    full_url = obj.api_request_url_input.text().strip()

    if not full_url:
        logger.error("Ошибка: вы не ввели эндпоинт.")
        obj.result_display.append("Статус: Запрос отклонен. Требуется эндпоинт.")
        return

    # Передаем JWT-токен с правильным префиксом Bearer
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Передаем параметры фильтрации/поиска (Query Parameters)
    params = {
        "page": 1,
        "status": "active"
    }

    logger.info(f"Отправка GET-запроса на {full_url}...")
    obj.result_display.append(f"Запрос: GET {full_url}\nПараметры: {params}")

    try:
        # Использование httpx.Client с trust_env=False полностью изолирует
        # процесс от сетевого окружения Windows, прокси и VPN-маршрутов на 127.0.0.1
        with httpx.Client(trust_env=False) as client:
            response = client.get(full_url, headers=headers, params=params, timeout=10.0)

        # Проверяем HTTP статус-код (200 OK)
        if response.status_code == 200:
            tasks_data = response.json()  # Безопасно парсим полученный JSON от Django
            logger.info("Данные успешно получены через HTTPX!")

            # Преобразуем ответ в человекочитаемый текст
            pretty_json = json.dumps(tasks_data, indent=4, ensure_ascii=False)

            # Выводим результат в окно отчетности пользователя
            obj.result_display.append(f"Ответ сервера (200 OK):\n{pretty_json}")
        else:
            logger.error(f"Ошибка сервера: Код {response.status_code}")
            obj.result_display.append(f"Код: {response.status_code}\nДетали: {response.text}")

    # Перехватываем исключения исключительно из библиотеки httpx
    except httpx.HTTPError as e:
        logger.exception("Ошибка сети httpx при отправке запроса: %s", e)
        obj.result_display.append(f"Критическая ошибка сети: {e}")


def scanning_on_click(obj) -> None:
    """Запуск универсального асинхронного экспресс-сканирования."""

    # Считываем ссылку для сканирования
    base_url = obj.base_url_input.text().strip()
    # Устанавливаем нужный сканер
    scaner = AsyncScanEndpoint(base_url)

    # Если менеджер забыл ввести ссылку, подсвечиваем поле
    if not base_url:
        with suppress(Exception):
            obj.base_url_input.setStyleSheet("border: 1px solid #ef4444;")
        return

    # Сбрасываем красную рамку, если ссылка введена
    with suppress(Exception):
        obj.base_url_input.setStyleSheet("")

    # Блокируем элементы управления, чтобы избежать повторных кликов во время работы
    if obj.btn_send_scanning:
        obj.btn_send_scanning.setEnabled(False)

    if obj.btn_send_parsing:
        obj.btn_send_parsing.setEnabled(False)

    # Создаем чистый системный поток
    obj.scaner_thread = QThread()

    # Создаем рабочий объект
    obj.scaner_worker = ScanerWorker(scaner=scaner)

    # Перемещаем объект в фоновый поток
    obj.scaner_worker.moveToThread(obj.scaner_thread)

    # Связываем запуск потока с выполнением метода run()
    obj.scaner_thread.started.connect(obj.scaner_worker.run)

    # Цепочка очистки после остановки потока:
    # Закрываем поток после завершения работы воркера
    obj.scaner_worker.finished_signal.connect(obj.scaner_thread.quit)

    # Удаляем тред из памяти
    obj.scaner_thread.finished.connect(obj.scaner_thread.deleteLater)

    # Так же удаляем воркер из памяти
    obj.scaner_thread.finished.connect(obj.scaner_worker.deleteLater)

    # Подключаем сигналы воркера
    obj.scaner_worker.progress_signal.connect(
        lambda msg: _update_parsing_status(obj, msg)
    )
    obj.scaner_worker.finished_signal.connect(lambda obj_scan: _scanning_success_handler(obj, obj_scan))

    obj.result_display.append(f"⏳ Запуск сканера для сайта: {base_url}")
    logger.info(f"Старт сканера по адресу {base_url}")

    # Запускаем поток
    obj.scaner_thread.start()


def parsing_on_click(obj) -> None:
    """Запуск парсинга выбранного сайта в фоновом потоке."""
    # Считываем данные из текстовых полей переданного UI-объекта
    target_url = obj.target_url_input.text().strip()
    keyword = obj.key_word_input.text().strip()

    # Если менеджер забыл ввести ссылку, подсвечиваем поле
    if not target_url:
        with suppress(Exception):
            obj.target_url_input.setStyleSheet("border: 1px solid #ef4444;")
        return

    # Сбрасываем красную рамку, если ссылка введена
    with suppress(Exception):
        obj.target_url_input.setStyleSheet("")

    # Блокируем элементы управления, чтобы избежать повторных кликов во время работы
    if obj.btn_send_scanning:
        obj.btn_send_scanning.setEnabled(False)

    if obj.btn_send_parsing:
        obj.btn_send_parsing.setEnabled(False)

    obj.result_display.append(f"⏳ Запуск парсера для сайта: {target_url}, ключ: {keyword}")
    logger.info(f"Старт парсера по адресу {target_url}")

    #================ Конфигурируем парсер под конкретную задачу ========================
    # config = CitadelConfig(
    #     target_url,
    #     keyword,
    #     "citadel.xlsx"
    # )
    # extractor = CitadelExtractor(config)
    # saver = XLSXSaver()
    # parser = CitadelParser(
    #     config=config,
    #     extractor=extractor,
    #     saver=saver
    # )

    config = GardarikaConfig(
        target_url,
        keyword,
        "gardarika.xlsx"
    )
    extractor = GardarikaExtractor(config)
    saver = XLSXSaver(config.file_name)
    parser = GardarikaParser(
        config=config,
        extractor=extractor,
        saver=saver
    )

    #====================================================================================

    # Создаем чистый системный поток
    obj.parser_thread = QThread()

    # Создаем рабочий объект
    obj.parser_worker = ParserWorker(parser=parser)

    # Перемещаем объект в фоновый поток
    obj.parser_worker.moveToThread(obj.parser_thread)

    # Связываем запуск потока с выполнением метода run()
    obj.parser_thread.started.connect(obj.parser_worker.run)

    # АВТОМАТИЧЕСКАЯ ЦЕПОЧКА ОЧИСТКИ при завершении потока:
    # Когда воркер закончит работу -> даем команду потоку закрыться (выход из event loop)
    obj.parser_worker.finished_signal.connect(obj.parser_thread.quit)

    # Когда сам поток полностью остановится -> безопасно удаляем тред из памяти
    obj.parser_thread.finished.connect(obj.parser_thread.deleteLater)

    # Когда поток остановится -> также автоматически удаляем воркер из памяти
    obj.parser_thread.finished.connect(obj.parser_worker.deleteLater)

    # Подключаем сигналы воркера к функциям обновления UI (используем lambda для передачи obj)
    obj.parser_worker.progress_signal.connect(
        lambda msg: _update_parsing_status(obj, msg)
    )
    obj.parser_worker.finished_signal.connect(lambda path: _parsing_success_handler(obj, path))

    # Запускаем поток
    obj.parser_thread.start()


# --- Внутренние вспомогательные функции для обработки сигналов потока ---
def _update_parsing_status(obj, message: str) -> None:
    """Пишет служебные сообщения о парсинге в информационное окно."""
    obj.result_display.append(message)


def _parsing_success_handler(obj, output_file: str="") -> None:
    """Вызывается автоматически при успешном завершении парсинга."""
    # Разблокируем интерфейс обратно
    if obj.btn_send_scanning:
        obj.btn_send_scanning.setEnabled(True)

    if obj.btn_send_parsing:
        obj.btn_send_parsing.setEnabled(True)

    if output_file:
        # Показываем сообщение об успешном завершении
        obj.result_display.append("Успех")
        obj.result_display.append("📊 Парсинг сайта успешно завершен!")
        obj.result_display.append(f"Результат парсинга сохранен в файл: {output_file}\n\n")

    logger.info("Завершение работы парсера.")


def _scanning_success_handler(obj, obj_scan) -> None:
    """Вызывается автоматически при завершении сканирования."""
    # Сразу разблокируем интерфейс в любом случае (успех, отмена или ошибка)
    if obj.btn_send_scanning:
        obj.btn_send_scanning.setEnabled(True)

    if obj.btn_send_parsing:
        obj.btn_send_parsing.setEnabled(True)

    # Проверяем, получили ли мы валидный результат
    if obj_scan is None:
        obj.result_display.append("⚠️ Сканирование не выдало результатов (было прервано или произошло исключение).")
        logger.warning("Сканер завершил работу без данных (результат равен None).")
        return

    # Обрабатываем успешный результат (предполагаем, что obj_scan — это список или коллекция)
    obj.result_display.append("🔹 Успех")
    obj.result_display.append(f"🔹 Выявлено эндпоинтов: {len(obj_scan)}")
    obj.result_display.append("🎉 Сканирование сайта успешно завершено!")

    logger.info(f"Завершение работы сканера. Найдено эндпоинтов: {len(obj_scan)}")
