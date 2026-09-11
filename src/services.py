"""Модуль управления бизнес-логикой проекта."""

import json
import logging
from contextlib import suppress

import httpx  # Изолированный и стабильный сетевой клиент вместо requests
from PyQt6.QtWidgets import QMessageBox

# Убираем QApplication, так как вызовы processEvents() перегружали стек событий Qt
# и приводили к аппаратным сбоям C++ (0xC0000409).
from src.auth.api_client import login_to_django
from src.auto_blind_fuzzer import run_security_api_scan
from src.parser_worker import ParserWorker

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

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

        # 4. Проверяем HTTP статус-код (200 OK)
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
        logger.error(f"Ошибка сети httpx при отправке запроса: {e}")
        obj.result_display.append(f"Критическая ошибка сети: {e}")


def scanning_on_click(obj) -> None:
    """Запуск универсального асинхронного экспресс-сканирования."""
    run_security_api_scan(obj)


def parsing_on_click(obj) -> None:
    """Запуск парсинга выбранного сайта в фоновом потоке."""
    # Считываем данные из текстовых полей переданного UI-объекта
    target_url = obj.target_url_input.text().strip()
    brand_keyword = obj.key_word_input.text().strip()

    # Простая валидация: если менеджер забыл ввести ссылку, подсвечиваем поле
    if not target_url:
        with suppress(Exception):
            obj.target_url_input.setStyleSheet("border: 1px solid #ef4444;")
        return

    # Сбрасываем красную рамку, если ссылка введена
    with suppress(Exception):
        obj.target_url_input.setStyleSheet("")

    # Блокируем элементы управления, чтобы избежать повторных кликов во время работы
    if obj.btn_send_parsing:
        obj.btn_send_parsing.setEnabled(False)
        obj.btn_send_parsing.setText("⏳ Запуск...")

    if obj.btn_back_parsing:
        obj.btn_back_parsing.setEnabled(False)

    # Создаем экземпляр фонового потока
    # Сохраняем его внутри obj, чтобы Python не удалил поток из памяти в процессе работы
    obj.parser_thread = ParserWorker(
        target_url=target_url,
        brand_keyword=brand_keyword,
    )

    # Подключаем сигналы воркера к функциям обновления UI (используем lambda для передачи obj)
    obj.parser_thread.progress_signal.connect(
        lambda msg: _update_parsing_status(obj, msg)
    )
    obj.parser_thread.finished_signal.connect(
        lambda path: _parsing_success_handler(obj, path)
    )
    obj.parser_thread.error_signal.connect(
        lambda err: _parsing_failure_handler(obj, err)
    )

    # Запускаем поток (PyQt автоматически вызовет метод run() внутри ParserWorker)
    obj.parser_thread.start()


# --- Внутренние вспомогательные функции для обработки сигналов потока ---


def _update_parsing_status(obj, message: str) -> None:
    """Обновляет текст на кнопке в процессе парсинга."""
    if obj.btn_send_parsing:
        obj.btn_send_parsing.setText(message)


def _parsing_success_handler(obj, output_file: str) -> None:
    """Вызывается автоматически при успешном завершении парсинга."""
    # Разблокируем интерфейс обратно
    if obj.btn_send_parsing:
        obj.btn_send_parsing.setEnabled(True)
        obj.btn_send_parsing.setText("🤖 Запустить парсинг")

    if obj.btn_back_parsing:
        obj.btn_back_parsing.setEnabled(True)

    # Показываем менеджеру красивое всплывающее окно об успешном завершении
    msg_box = QMessageBox(obj.page_parsing if obj.page_parsing else None)
    msg_box.setIcon(QMessageBox.Icon.Information)
    msg_box.setWindowTitle("Успех")
    msg_box.setText("📊 Парсинг сайта успешно завершен!")
    msg_box.setInformativeText(f"Результат парсинга сохранен в файл:\n\n{output_file}")
    msg_box.exec()


def _parsing_failure_handler(obj, error_message: str) -> None:
    """Вызывается автоматически, если парсер столкнулся со сбоем."""
    # Возвращаем интерфейс в рабочее состояние, чтобы менеджер мог исправить данные
    if obj.btn_send_parsing:
        obj.btn_send_parsing.setEnabled(True)
        obj.btn_send_parsing.setText("❌ Сбой. Повторить?")

    if obj.btn_back_parsing:
        obj.btn_back_parsing.setEnabled(True)

    # Выводим всплывающее окно с ошибкой
    msg_box = QMessageBox(obj.page_parsing if obj.page_parsing else None)
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle("Ошибка парсинга")
    msg_box.setText("Не удалось собрать данные с сайта.")
    msg_box.setInformativeText(
        f"Детали ошибки:\n{error_message}\n\n"
        f"Проверьте интернет-соединение или корректность ссылки.")
    msg_box.exec()



