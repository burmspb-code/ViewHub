import os
import pytest
import json
import httpx
import sqlite3
import pandas as pd
import gc

from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QFileDialog, QWidget, QTableWidget, QPushButton
from PyQt6.QtCore import QThread

from src.services import (
    parsing_file_save,
    parsing_db_read,
    parsing_export_init,
    _update_parsing_status,
    _stop_handler,
    _parsing_success_handler,
    _scanning_success_handler,
    scanning_on_click,
    auth_on_click,
    scanning_cancel_on_click,
    request_on_click,
    parsing_cancel_on_click,
    parsing_export_on_click,
    parsing_on_click,
    parsing_preview_on_click,
    close_db_viewer,
    create_db_viewer
)


def test_parsing_export_init_with_config_name():
    """Проверяем, что берется имя из конфига и добавляется .xlsx, если расширения нет."""
    # Создаем фальшивый парсер с нужной структурой атрибутов
    mock_parser = MagicMock()
    mock_parser.config.file_name = "golden_apple_data"
    mock_parser.manager.table_name = "some_table"

    # Вызываем тестируемую функцию
    result = parsing_export_init(mock_parser)

    # Проверяем результат утверждением assert
    assert result == "golden_apple_data.xlsx"


def test_parsing_export_init_with_existing_extension():
    """Проверяем, что если расширение .csv уже есть, оно не дублируется."""
    mock_parser = MagicMock()
    mock_parser.config.file_name = "products.csv"

    result = parsing_export_init(mock_parser)

    assert result == "products.csv"


def test_parsing_export_init_fallback_to_table_name():
    """Проверяем, что если в конфиге пусто, имя берется из таблицы manager."""
    mock_parser = MagicMock()
    mock_parser.config.file_name = ""  # В конфиге пусто
    mock_parser.manager.table_name = "goods_table"

    result = parsing_export_init(mock_parser)

    assert result == "goods_table.xlsx"


@pytest.fixture
def setup_temporary_db(tmp_path):
    """Фикстура создает изолированную БД во временном файле и наполняет её."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT,
                price REAL
            )
        """)
        cursor.executemany(
            "INSERT INTO products (name, price) VALUES (?, ?)",
            [("Помада Golden Apple", 1200.50), ("Крем для лица", 2500.00)],
        )
        conn.commit()
    finally:
        conn.close()  # Гарантированно закрываем здесь!

    yield str(db_path)


def test_parsing_db_read_success(setup_temporary_db):
    """Проверяем успешное чтение таблицы из БД в DataFrame."""
    mock_parser = MagicMock()
    mock_parser.manager.db_path = setup_temporary_db
    mock_parser.manager.table_name = "products"
    mock_obj = MagicMock()

    df = parsing_db_read(mock_parser, mock_obj)

    assert df is not None
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    # Обращаемся к элементу через .iloc[0] для извлечения строки
    assert df.iloc[0]["name"] == "Помада Golden Apple"




@pytest.mark.filterwarnings("ignore:unclosed database:ResourceWarning")
def test_parsing_db_read_empty_table(setup_temporary_db):
    """Проверяем поведение функции, если таблица в БД оказалась пустой."""
    # Очищаем таблицу перед тестом и сразу закрываем соединение
    conn = sqlite3.connect(setup_temporary_db)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products")
        conn.commit()
    finally:
        conn.close()

    mock_parser = MagicMock()
    mock_parser.manager.db_path = setup_temporary_db
    mock_parser.manager.table_name = "products"

    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    # Запускаем чтение пустой таблицы
    df = parsing_db_read(mock_parser, mock_obj)

    # Базовые проверки логики функции
    assert df is None
    mock_obj.result_display.append.assert_called_once_with(
        "⚠️ База данных пуста, нечего экспортировать."
    )

    # === РЕШЕНИЕ ДЛЯ PYTHON 3.14: Принудительно очищаем скрытые ресурсы Pandas/SQLite ===
    del df  # Уничтожаем пустой DataFrame, освобождая ссылки
    gc.collect()  # Заставляем Python немедленно собрать мусор до завершения сессии теста


@pytest.fixture
def sample_dataframe():
    """Фикстура, создающая простой DataFrame для тестирования записи."""
    return pd.DataFrame({"Наименование": ["Товар 1", "Товар 2"], "Цена": [500, 1000]})


def test_parsing_file_save_excel_success(sample_dataframe, tmp_path):
    """Проверяем успешное сохранение данных в формат Excel."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    # Формируем безопасный путь к временному Excel-файлу
    test_file_path = str(tmp_path / "result.xlsx")

    # Подменяем вызов QFileDialog.getSaveFileName, как будто пользователь выбрал наш путь
    with patch.object(QFileDialog, "getSaveFileName", return_value=(test_file_path, "Excel Files (*.xlsx)")):
        # Вызываем тестируемую функцию
        parsing_file_save(sample_dataframe, "default_name.xlsx", mock_obj)

    # ПРОВЕРКИ:
    # 1. Файл физически создался на диске
    assert os.path.exists(test_file_path)
    # 2. В интерфейс вывелось сообщение об успешном сохранении (эмодзи 💾)
    mock_obj.result_display.append.assert_called_once_with(f"💾 Успешный экспорт: {test_file_path}")


def test_parsing_file_save_user_canceled(sample_dataframe):
    """Проверяем поведение, если пользователь нажал 'Отмена' в окне сохранения."""
    mock_obj = MagicMock()

    # Имитируем, что getSaveFileName вернул пустую строку (пользователь нажал Отмена)
    with patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
        parsing_file_save(sample_dataframe, "default_name.xlsx", mock_obj)

    # Проверяем, что метод append у result_display НЕ вызывался, так как запись не производилась
    if hasattr(mock_obj, "result_display"):
        mock_obj.result_display.append.assert_not_called()


def test_parsing_file_save_permission_error(sample_dataframe, tmp_path, monkeypatch):
    """Проверяем обработку ошибки PermissionError (файл открыт в Excel)."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    test_file_path = str(tmp_path / "locked.xlsx")

    # Подменяем выбор файла
    with patch.object(QFileDialog, "getSaveFileName", return_value=(test_file_path, "Excel Files (*.xlsx)")):
        # С помощью искусственной функции эмулируем сбой записи (PermissionError) в Pandas
        def mock_to_excel(*args, **kwargs):
            raise PermissionError("Permission denied")

        monkeypatch.setattr(pd.DataFrame, "to_excel", mock_to_excel)

        # Вызываем функцию сохранения
        parsing_file_save(sample_dataframe, "default_name.xlsx", mock_obj)

    # ПРОВЕРКА: функция отловила ошибку доступа и вывела понятный текст пользователю
    mock_obj.result_display.append.assert_called_once_with(
        "❌ Ошибка доступа: Файл занят другой программой (например, Excel). Закройте его и повторите попытку."
    )

def test_parsing_db_read_missing_db_path():
    """Проверяем поведение функции, если в парсере отсутствует путь к БД."""
    # Создаем мок-парсер, у которого db_path возвращает None или пустую строку
    mock_parser = MagicMock()
    mock_parser.manager.db_path = None
    mock_parser.manager.table_name = "products"

    # Мокаем UI
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    # Вызываем функцию
    df = parsing_db_read(mock_parser, mock_obj)

    # ПРОВЕРКИ:
    assert df is None
    # Проверяем, что в интерфейс вывелась правильная ошибка с крестиком ❌
    mock_obj.result_display.append.assert_called_once_with(
        "❌ Ошибка: не найден файл базы данных."
    )


def test_parsing_db_read_missing_table_name():
    """Проверяем поведение функции, если в парсере отсутствует имя таблицы."""
    mock_parser = MagicMock()
    mock_parser.manager.db_path = "valid_path.db"
    mock_parser.manager.table_name = None  # Имя таблицы не задано

    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    df = parsing_db_read(mock_parser, mock_obj)

    # ПРОВЕРКИ:
    assert df is None
    # Проверяем, что в интерфейс вывелось предупреждение с треугольником ⚠️
    mock_obj.result_display.append.assert_called_once_with(
        "⚠️ Ошибка: имя таблицы не задано."
    )

def test_parsing_db_read_exception_handling(setup_temporary_db, monkeypatch):
    """Проверяем перехват исключений и вывод ошибки в UI при сбое чтения БД."""
    mock_parser = MagicMock()
    mock_parser.manager.db_path = setup_temporary_db
    mock_parser.manager.table_name = "products"

    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    # Искусственно вызываем ошибку базы данных (например, OperationalError) при вызове read_sql_query
    def mock_read_sql(*args, **kwargs):
        raise sqlite3.OperationalError("Сбой чтения структуры таблицы или диск заблокирован")

    monkeypatch.setattr(pd, "read_sql_query", mock_read_sql)

    # Вызываем функцию
    df = parsing_db_read(mock_parser, mock_obj)

    # ПРОВЕРКИ:
    assert df is None
    # Проверяем, что первая строка ошибки корректно попала в UI
    mock_obj.result_display.append.assert_called_once_with(
        "❌ Ошибка чтения БД: Сбой чтения структуры таблицы или диск заблокирован"
    )

def test_update_parsing_status():
    """Проверяем, что сообщение корректно добавляется в result_display."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    # Вызываем тестируемую функцию
    _update_parsing_status(mock_obj, "Сканирование страницы 5...")

    # Проверяем, что метод append вызвался с нашей строкой
    mock_obj.result_display.append.assert_called_once_with("Сканирование страницы 5...")


def test_stop_handler_full_ui_unlock():
    """Проверяем, что обработчик остановки выводит логи и включает все кнопки."""
    # 1. Готовим мок-объект окна со всеми необходимыми кнопками и дисплеем
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    mock_obj.btn_send_scanning = MagicMock()
    mock_obj.btn_send_parsing = MagicMock()
    mock_obj.btn_cancel_parsing = MagicMock()
    mock_obj.btn_cancel_scanning = MagicMock()

    # 2. Вызываем обработчик остановки
    test_msg = "Парсер успешно завершил экстренное отключение."
    _stop_handler(mock_obj, test_msg)

    # ПРОВЕРКИ ВЫВОДА В ТЕКСТОВУЮ ПАНЕЛЬ:
    # Проверяем, что вывелся маркер остановки
    mock_obj.result_display.append.assert_any_call("🛑 Процесс остановлен!")
    # Проверяем, что вывелось кастомное системное сообщение
    mock_obj.result_display.append.assert_any_call(test_msg)

    # ПРОВЕРКИ АКТИВАЦИИ КНОПОК ИНТЕРФЕЙСА:
    mock_obj.btn_send_scanning.setEnabled.assert_called_once_with(True)
    mock_obj.btn_send_parsing.setEnabled.assert_called_once_with(True)
    mock_obj.btn_cancel_parsing.setEnabled.assert_called_once_with(False)  # Кнопка отмены парсинга отключается
    mock_obj.btn_cancel_scanning.setEnabled.assert_called_once_with(True)


def test_stop_handler_missing_buttons_safe():
    """Проверяем, что если кнопок нет в объекте (например, интерфейс еще не создан), код не падает."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    # Удаляем атрибуты кнопок, имитируя их отсутствие
    del mock_obj.btn_send_scanning
    del mock_obj.btn_send_parsing
    del mock_obj.btn_cancel_parsing
    del mock_obj.btn_cancel_scanning

    # Функция должна выполниться без AttributeError благодаря проверкам getattr
    _stop_handler(mock_obj, "Тест без кнопок")

    # Логи всё равно должны записаться
    mock_obj.result_display.append.assert_any_call("🛑 Процесс остановлен!")
    mock_obj.result_display.append.assert_any_call("Тест без кнопок")

def test_parsing_success_handler_with_file():
    """Проверяем успешный хэндлер, когда передан путь к файлу результатов."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()
    mock_obj.btn_send_scanning = MagicMock()
    mock_obj.btn_send_parsing = MagicMock()
    mock_obj.btn_cancel_parsing = MagicMock()

    test_file = "C:/exports/products.xlsx"

    # Вызываем функцию
    _parsing_success_handler(mock_obj, output_file=test_file)

    # ПРОВЕРКИ АКТИВАЦИИ КНОПОК:
    mock_obj.btn_send_scanning.setEnabled.assert_called_once_with(True)
    mock_obj.btn_send_parsing.setEnabled.assert_called_once_with(True)
    mock_obj.btn_cancel_parsing.setEnabled.assert_called_once_with(False)  # Кнопка отмены парсинга отключается

    # ПРОВЕРКИ ТЕКСТОВОГО ВЫВОДА (Порядок вызовов важен):
    mock_obj.result_display.append.assert_any_call("🎉 Успех!")
    mock_obj.result_display.append.assert_any_call("📊 Парсинг сайта успешно завершен!")
    mock_obj.result_display.append.assert_any_call(f"Результат парсинга сохранен в файл: {test_file}\n\n")


def test_parsing_success_handler_without_file():
    """Проверяем хэндлер, если файл не передан (пустая строка)."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()
    mock_obj.btn_send_scanning = MagicMock()
    mock_obj.btn_send_parsing = MagicMock()
    mock_obj.btn_cancel_parsing = MagicMock()

    # Вызываем без указания файла
    _parsing_success_handler(mock_obj, output_file="")

    # Кнопки всё равно обязаны включиться обратно
    mock_obj.btn_send_scanning.setEnabled.assert_called_once_with(True)
    mock_obj.btn_send_parsing.setEnabled.assert_called_once_with(True)
    mock_obj.btn_cancel_parsing.setEnabled.assert_called_once_with(False)  # Кнопка отмены парсинга отключается

    # Текстовые сообщения об успехе файла НЕ должны были вызываться
    mock_obj.result_display.append.assert_not_called()


def test_parsing_success_handler_missing_buttons_safe():
    """Проверяем, что код не падает, если кнопок в UI нет (защита через getattr)."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    # Удаляем кнопки из мока
    del mock_obj.btn_send_scanning
    del mock_obj.btn_send_parsing

    # Функция не должна упасть с AttributeError
    _parsing_success_handler(mock_obj, output_file="test.xlsx")

    # Текст успеха при этом всё равно выведется в консоль UI
    mock_obj.result_display.append.assert_any_call("🎉 Успех!")

def test_scanning_success_handler_none_result():
    """Проверяем поведение хэндлера, если результат сканирования равен None."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()
    mock_obj.btn_cancel_parsing = MagicMock()
    mock_obj.btn_cancel_scanning = MagicMock()

    # Вызываем функцию с результатом None
    _scanning_success_handler(mock_obj, obj_scan=None)

    # Кнопки отмены всё равно должны разблокироваться
    mock_obj.btn_cancel_parsing.setEnabled.assert_called_once_with(True)
    mock_obj.btn_cancel_scanning.setEnabled.assert_called_once_with(True)

    # Должно вывестись только предупреждение о пустом результате
    mock_obj.result_display.append.assert_called_once_with(
        "⚠️ Сканирование не выдало результатов (было прервано или произошло исключение)."
    )


def test_scanning_success_handler_with_data():
    """Проверяем успешный хэндлер, когда сканер нашел эндпоинты."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()
    mock_obj.btn_cancel_parsing = MagicMock()
    mock_obj.btn_cancel_scanning = MagicMock()

    # Имитируем список из 5 найденных эндпоинтов
    test_scan_data = ["url1", "url2", "url3", "url4", "url5"]

    # Вызываем функцию
    _scanning_success_handler(mock_obj, obj_scan=test_scan_data)

    # Кнопки отмены разблокированы
    mock_obj.btn_cancel_parsing.setEnabled.assert_called_once_with(True)
    mock_obj.btn_cancel_scanning.setEnabled.assert_called_once_with(True)

    # Проверяем вывод сообщений в UI
    mock_obj.result_display.append.assert_any_call("🔹 Успех")
    mock_obj.result_display.append.assert_any_call(f"🔹 Выявлено эндпоинтов: {len(test_scan_data)}")
    mock_obj.result_display.append.assert_any_call("🎉 Сканирование сайта успешно завершено!")


def test_scanning_success_handler_missing_buttons_safe():
    """Проверяем, что хэндлер не падает, если в UI отсутствуют кнопки отмены."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    # Удаляем кнопки из мока
    del mock_obj.btn_cancel_parsing
    del mock_obj.btn_cancel_scanning

    # Код должен выполниться без AttributeError
    _scanning_success_handler(mock_obj, obj_scan=["url1"])

    # Информационные сообщения при этом успешно добавляются в лог
    mock_obj.result_display.append.assert_any_call("🔹 Успех")





def test_auth_on_click_missing_fields():
    """Проверяем, что при пустых полях ввода авторизация прерывается."""
    mock_obj = MagicMock()
    # Имитируем ввод (одно из полей оставим пустым)
    mock_obj.api_url_input.text.return_value = "https://site.com"
    mock_obj.login_input.text.return_value = ""  # Пустой логин
    mock_obj.password_input.text.return_value = "secret123"

    with patch("src.services.login_to_django") as mock_login:
        auth_on_click(mock_obj)

        # Сетевой клиент не должен был вызываться
        mock_login.assert_not_called()


def test_auth_on_click_success():
    """Проверяем успешный сценарий авторизации и сохранение токена."""
    mock_obj = MagicMock()
    mock_obj.api_url_input.text.return_value = "https://site.com "  # С пробелом для проверки strip()
    mock_obj.login_input.text.return_value = "admin"
    mock_obj.password_input.text.return_value = "12345"
    mock_obj.result_display = MagicMock()

    # Имитируем успешный ответ от Django API
    fake_response = {"success": True, "message": "Сессия успешно создана.", "token": "JWT_TOKEN_XYZ_123"}

    with patch("src.services.login_to_django", return_value=fake_response) as mock_login:
        auth_on_click(mock_obj)

        # Проверяем, что сетевой клиент вызвался с очищенными от пробелов данными
        mock_login.assert_called_once_with("https://site.com", "admin", "12345")

        # Проверяем маскирование пароля в окне результатов
        mock_obj.result_display.append.assert_any_call(
            "Запрос: POST https://site.com\nТело: username='admin', password='*****'"
        )

        # Проверяем вывод токена в UI
        mock_obj.result_display.append.assert_any_call("Статус: Авторизован.\nТокен: JWT_TOKEN_XYZ_123")

        # Проверяем, что токен и адрес прописались в контекст главного окна
        assert mock_obj.auth_token == "JWT_TOKEN_XYZ_123"
        assert mock_obj.base_url == "https://site.com"


def test_auth_on_click_failed_with_details():
    """Проверяем обработку ошибки авторизации с выводом деталей."""
    mock_obj = MagicMock()
    mock_obj.api_url_input.text.return_value = "https://site.com"
    mock_obj.login_input.text.return_value = "wrong_user"
    mock_obj.password_input.text.return_value = "wrong_pass"
    mock_obj.result_display = MagicMock()

    # Ответ от сервера с ошибкой и детализацией
    fake_response = {
        "success": False,
        "message": "Неверные учетные данные.",
        "details": "Пользователь заблокирован за спам-попытки.",
    }

    with patch("src.services.login_to_django", return_value=fake_response):
        auth_on_click(mock_obj)

        # Проверяем, что детали ошибки отобразились на экране
        mock_obj.result_display.append.assert_any_call("Детали ошибки:\nПользователь заблокирован за спам-попытки.")


def test_auth_on_click_failed_generic_error():
    """Проверяем стандартную ошибку авторизации без деталей."""
    mock_obj = MagicMock()
    mock_obj.api_url_input.text.return_value = "https://site.com"
    mock_obj.login_input.text.return_value = "user"
    mock_obj.password_input.text.return_value = "pass"
    mock_obj.result_display = MagicMock()

    # В ответе нет ключа "details"
    fake_response = {"success": False, "message": "Ошибка 500."}

    with patch("src.services.login_to_django", return_value=fake_response):
        auth_on_click(mock_obj)

        # Проверяем стандартный фоллбек-текст
        mock_obj.result_display.append.assert_any_call("Статус: Доступ отклонен.")


def test_request_on_click_not_authorized():
    """Проверяем отмену запроса, если пользователь не авторизован."""
    mock_obj = MagicMock()
    # Имитируем отсутствие авторизации
    mock_obj.base_url = None
    mock_obj.auth_token = None
    mock_obj.result_display = MagicMock()

    with patch("httpx.Client") as mock_client:
        request_on_click(mock_obj)

        # Клиент httpx не должен создаваться
        mock_client.assert_not_called()
        # В UI должно уйти сообщение об ошибке
        mock_obj.result_display.append.assert_called_once_with("Статус: Запрос отклонен. Требуется авторизация.")


def test_request_on_click_missing_endpoint():
    """Проверяем отмену запроса, если поле эндпоинта пустое."""
    mock_obj = MagicMock()
    # Пользователь авторизован
    mock_obj.base_url = "https://site.com"
    mock_obj.auth_token = "valid_token_123"
    # Но эндпоинт пустой (с пробелами для проверки strip)
    mock_obj.api_request_url_input.text.return_value = "   "
    mock_obj.result_display = MagicMock()

    with patch("httpx.Client") as mock_client:
        request_on_click(mock_obj)

        mock_client.assert_not_called()
        mock_obj.result_display.append.assert_called_once_with("Статус: Запрос отклонен. Требуется эндпоинт.")


def test_request_on_click_success_200():
    """Проверяем успешный GET-запрос и вывод форматированного JSON."""
    mock_obj = MagicMock()
    mock_obj.base_url = "https://site.com"
    mock_obj.auth_token = "secret_jwt_token"
    mock_obj.api_request_url_input.text.return_value = "https://site.com/v1/tasks/"
    mock_obj.result_display = MagicMock()

    # 1. Готовим фальшивый ответ от сервера
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 1, "title": "Тестовая задача", "status": "active"}

    # 2. Настраиваем экземпляр клиента
    mock_client_instance = MagicMock()
    mock_client_instance.get.return_value = mock_response

    # РЕШЕНИЕ: Принудительно заставляем контекстный менеджер (with ... as client)
    # возвращать наш mock_client_instance
    with patch("httpx.Client") as mock_client_class:
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        # Вызываем боевую функцию
        request_on_click(mock_obj)

        # ПРОВЕРКИ:
        # Проверяем, что запрос ушел с правильными параметрами
        mock_client_instance.get.assert_called_once_with(
            "https://site.com/v1/tasks/",
            headers={"Authorization": "Bearer secret_jwt_token", "Content-Type": "application/json"},
            params={"page": 1, "status": "active"},
            timeout=10.0,
        )

        # Проверяем человекочитаемый вывод JSON в интерфейс
        # Исправлена опечатка в строке ответа (из боевого кода: 'Ответ сервера')
        expected_json = json.dumps(mock_response.json.return_value, indent=4, ensure_ascii=False)
        mock_obj.result_display.append.assert_any_call(f"Ответ сервера (200 OK):\n{expected_json}")


def test_request_on_click_server_error():
    """Проверяем обработку некорректных статус-кодов (например, 500 Internal Error)."""
    mock_obj = MagicMock()
    mock_obj.base_url = "https://site.com"
    mock_obj.auth_token = "token"
    mock_obj.api_request_url_input.text.return_value = "https://site.com/error/"
    mock_obj.result_display = MagicMock()

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error Details"

    mock_client_instance = MagicMock()
    mock_client_instance.get.return_value = mock_response

    with patch("httpx.Client") as mock_client_class:
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        request_on_click(mock_obj)

        # Должна сработать ветка else и вывести ошибку сервера в UI
        mock_obj.result_display.append.assert_any_call("Код: 500\nДетали: Internal Server Error Details")


def test_request_on_click_network_exception():
    """Проверяем перехват исключений httpx при критическом сбое сети."""
    mock_obj = MagicMock()
    mock_obj.base_url = "https://site.com"
    mock_obj.auth_token = "token"
    mock_obj.api_request_url_input.text.return_value = "https://site.com/timeout/"
    mock_obj.result_display = MagicMock()

    mock_client_instance = MagicMock()
    # Имитируем падение сети по таймауту через side_effect
    mock_client_instance.get.side_effect = httpx.ConnectTimeout("Connection timed out")

    with patch("httpx.Client") as mock_client_class:
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        request_on_click(mock_obj)

        # Блок except должен поймать ошибку и безопасно вывести её на экран
        mock_obj.result_display.append.assert_any_call("Критическая ошибка сети: Connection timed out")


def test_scanning_on_click_missing_url():
    """Проверяем, что при пустой ссылке поле подсвечивается красным и поток не создается."""
    mock_obj = MagicMock()
    # Имитируем пустое поле ввода
    mock_obj.base_url_input.text.return_value = "   "

    # Мокаем класс сканера, чтобы он не инициализировался реальным сетевым адресом
    with patch("src.services.AsyncScanEndpoint"), patch("src.services.QThread") as mock_thread_class:
        scanning_on_click(mock_obj)

        # Проверяем установку красной рамки
        mock_obj.base_url_input.setStyleSheet.assert_called_once_with("border: 1px solid #ef4444;")
        # Системный поток не должен был создаваться
        mock_thread_class.assert_not_called()


def test_scanning_on_click_success_thread_start():
    """Проверяем успешную инициализацию воркера, привязку сигналов и старт QThread."""
    mock_obj = MagicMock()
    mock_obj.base_url_input.text.return_value = "https://example.com"
    mock_obj.btn_send_scanning = MagicMock()
    mock_obj.btn_send_parsing = MagicMock()
    mock_obj.result_display = MagicMock()

    # Создаем моки для QThread и ScanerWorker
    mock_thread = MagicMock(spec=QThread)
    mock_worker = MagicMock()

    with (
        patch("src.services.AsyncScanEndpoint"),
        patch("src.services.QThread", return_value=mock_thread),
        patch("src.services.ScannerWorker", return_value=mock_worker),
    ):
        scanning_on_click(mock_obj)

        # 1. Проверяем очистку стилей рамки (сброс красного цвета)
        mock_obj.base_url_input.setStyleSheet.assert_called_once_with("")

        # 2. Элементы управления должны заблокироваться, защищая от спам-кликов
        mock_obj.btn_send_scanning.setEnabled.assert_called_once_with(False)
        mock_obj.btn_send_parsing.setEnabled.assert_called_once_with(False)

        # 3. Переменные треда и воркера успешно сохранились в объект окна
        assert mock_obj.scaner_thread == mock_thread
        assert mock_obj.scaner_worker == mock_worker

        # 4. Проверяем архитектурный перенос воркера в фоновый тред
        mock_worker.moveToThread.assert_called_once_with(mock_thread)

        # 5. Проверяем связывание QT-сигналов и цепочку очистки памяти
        mock_thread.started.connect.assert_called_once_with(mock_worker.run)
        mock_worker.finished_signal.connect.assert_any_call(mock_thread.quit)
        mock_thread.finished.connect.assert_any_call(mock_thread.deleteLater)
        mock_thread.finished.connect.assert_any_call(mock_worker.deleteLater)

        # 6. В лог вывелось сообщение о старте сканирования
        mock_obj.result_display.append.assert_called_once_with("⏳ Запуск сканера для сайта: https://example.com")

        # 7. Фоновый поток физически запущен
        mock_thread.start.assert_called_once()


def test_scanning_cancel_on_click_active():
    """Проверяем успешную отправку сигнала отмены, если поток сканера запущен."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()
    mock_obj.btn_cancel_scanning = MagicMock()
    mock_obj.scaner_worker = MagicMock()

    # Настраиваем мок потока так, будто он активен прямо сейчас
    mock_obj.scaner_thread = MagicMock()
    mock_obj.scaner_thread.isRunning.return_value = True

    # Вызываем тестируемую функцию отмены
    scanning_cancel_on_click(mock_obj)

    # ПРОВЕРКИ СЦЕНАРИЯ:
    # 1. Пользователю вывелось сообщение об остановке
    mock_obj.result_display.append.assert_called_once_with("🛑 Останавливаем сканирование, пожалуйста, подождите...")
    # 2. Кнопка отмены заблокирована для предотвращения спам-кликов
    mock_obj.btn_cancel_scanning.setEnabled.assert_called_once_with(False)
    # 3. Воркер получил команду на экстренную остановку асинхронного таска
    mock_obj.scaner_worker.stop.assert_called_once()


def test_scanning_cancel_on_click_not_running():
    """Проверяем поведение функции, если поток сканера не запущен."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()
    mock_obj.btn_cancel_scanning = MagicMock()
    mock_obj.scaner_worker = MagicMock()

    # Сценарий А: поток существует, но уже завершен (isRunning() -> False)
    mock_obj.scaner_thread = MagicMock()
    mock_obj.scaner_thread.isRunning.return_value = False

    with patch("src.services.logger") as mock_logger:
        scanning_cancel_on_click(mock_obj)

        # Проверяем, что никаких действий не произошло, кроме записи предупреждения
        mock_obj.result_display.append.assert_not_called()
        mock_obj.btn_cancel_scanning.setEnabled.assert_not_called()
        mock_obj.scaner_worker.stop.assert_not_called()
        mock_logger.warning.assert_called_once_with(
            "Невозможно отменить сканирование: процесс не запущен или уже завершен."
        )


def test_scanning_cancel_on_click_no_thread_attribute():
    """Проверяем поведение функции, если у объекта вообще нет атрибута scaner_thread."""
    mock_obj = MagicMock()
    # Удаляем атрибут потока, имитируя состояние до первого запуска сканера
    del mock_obj.scaner_thread
    mock_obj.result_display = MagicMock()
    mock_obj.btn_cancel_scanning = MagicMock()
    mock_obj.scaner_worker = MagicMock()

    with patch("src.services.logger") as mock_logger:
        scanning_cancel_on_click(mock_obj)

        # hasattr вернет False, код уйдет в безопасный ветку else
        mock_logger.warning.assert_called_once_with(
            "Невозможно отменить сканирование: процесс не запущен или уже завершен."
        )


def test_parsing_cancel_on_click_active():
    """Проверяем успешную отправку сигнала отмены, если поток парсера активен."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()
    mock_obj.btn_cancel_parsing = MagicMock()
    mock_obj.parser_worker = MagicMock()

    # Имитируем, что поток парсера запущен прямо сейчас
    mock_obj.parser_thread = MagicMock()
    mock_obj.parser_thread.isRunning.return_value = True

    # Вызываем функцию отмены
    parsing_cancel_on_click(mock_obj)

    # ПРОВЕРКИ:
    # 1. Текст статуса отправлен в окно логов
    mock_obj.result_display.append.assert_called_once_with("🛑 Останавливаем парсинг, пожалуйста, подождите...")
    # 2. Кнопка отмены заблокирована, чтобы пользователь не кликал повторно
    mock_obj.btn_cancel_parsing.setEnabled.assert_called_once_with(False)
    # 3. У воркера вызван метод стопа
    mock_obj.parser_worker.stop.assert_called_once()


def test_parsing_cancel_on_click_not_running():
    """Проверяем поведение функции, если поток парсера существует, но не запущен."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()
    mock_obj.btn_cancel_parsing = MagicMock()
    mock_obj.parser_worker = MagicMock()

    # Поток существует, но завершен (isRunning() -> False)
    mock_obj.parser_thread = MagicMock()
    mock_obj.parser_thread.isRunning.return_value = False

    with patch("src.services.logger") as mock_logger:
        parsing_cancel_on_click(mock_obj)

        # Никакие UI-действия не должны выполняться, пишется только предупреждение
        mock_obj.result_display.append.assert_not_called()
        mock_obj.btn_cancel_parsing.setEnabled.assert_not_called()
        mock_obj.parser_worker.stop.assert_not_called()
        mock_logger.warning.assert_called_once_with("Невозможно отменить парсинг: процесс не запущен или уже завершен.")


def test_parsing_cancel_on_click_no_thread_attribute():
    """Проверяем поведение функции, если у объекта вообще нет атрибута parser_thread."""
    mock_obj = MagicMock()
    # Имитируем состояние до первого старта парсера (атрибута нет в объекте окна)
    del mock_obj.parser_thread
    mock_obj.result_display = MagicMock()
    mock_obj.btn_cancel_parsing = MagicMock()
    mock_obj.parser_worker = MagicMock()

    with patch("src.services.logger") as mock_logger:
        parsing_cancel_on_click(mock_obj)

        # Код безопасно уходит в ветку else
        mock_logger.warning.assert_called_once_with("Невозможно отменить парсинг: процесс не запущен или уже завершен.")


def test_parsing_export_on_click_empty_path_name():
    """Проверяем ранний выход из функции, если имя файла не сформировалось."""
    mock_obj = MagicMock()
    mock_obj.btn_export_parsing = MagicMock()

    # Настраиваем фиктивный пустой возврат имени файла
    with patch("src.services.parsing_export_init", return_value=""):
        parsing_export_on_click(mock_obj)

        # Кнопка экспорта не должна блокироваться, так как выход произошел раньше
        mock_obj.btn_export_parsing.setEnabled.assert_not_called()


def test_parsing_export_on_click_empty_or_none_table():
    """Проверяем прерывание экспорта, если таблица из БД вернулась пустой или None."""
    mock_obj = MagicMock()
    mock_obj.btn_export_parsing = MagicMock()

    # Настраиваем успешное имя файла, но пустой DataFrame при чтении таблицы
    with (
        patch("src.services.parsing_export_init", return_value="valid_name.xlsx"),
        patch("src.services.parsing_db_read", return_value=pd.DataFrame()) as mock_read,
        patch("src.services.parsing_file_save") as mock_save,
    ):
        parsing_export_on_click(mock_obj)

        # Чтение таблицы было вызвано
        mock_read.assert_called_once_with(mock_obj.parser, mock_obj)
        # Сохранение файла НЕ должно вызываться, так как таблица пустая
        mock_save.assert_not_called()
        # Кнопка экспорта была сначала заблокирована, а затем разблокирована в finally
        mock_obj.btn_export_parsing.setEnabled.assert_any_call(False)
        mock_obj.btn_export_parsing.setEnabled.assert_called_with(True)


def test_parsing_on_click_missing_target_url():
    """Проверяем, что при пустой ссылке поле подсвечивается красным и функция прерывается."""
    mock_obj = MagicMock()
    mock_obj.target_url_input.text.return_value = "   "  # Пустая ссылка
    mock_obj.key_word_input.text.return_value = "косметика"

    with patch("src.services.GoldenAppleConfig"), patch("src.services.QThread") as mock_thread_class:
        parsing_on_click(mock_obj)

        # Проверяем установку красной рамки на поле ссылки
        mock_obj.target_url_input.setStyleSheet.assert_called_once_with("border: 1px solid #ef4444;")
        # Системный поток парсинга не должен создаваться
        mock_thread_class.assert_not_called()


def test_parsing_on_click_missing_keyword():
    """Проверяем, что при пустом ключевом слове подсвечивается поле ключа."""
    mock_obj = MagicMock()
    mock_obj.target_url_input.text.return_value = "https://goldapple.ru"
    mock_obj.key_word_input.text.return_value = ""  # Пустой ключ

    with patch("src.services.GoldenAppleConfig"), patch("src.services.QThread") as mock_thread_class:
        parsing_on_click(mock_obj)

        # Должно подсветиться именно поле ключевого слова
        mock_obj.key_word_input.setStyleSheet.assert_called_once_with("border: 1px solid #ef4444;")
        mock_thread_class.assert_not_called()


def test_parsing_on_click_db_initialization_error():
    """Проверяем перехват исключения БД и генерацию RuntimeError."""
    mock_obj = MagicMock()
    mock_obj.target_url_input.text.return_value = "https://goldapple.ru"
    mock_obj.key_word_input.text.return_value = "крем"

    # Имитируем падение метода init_for_config в DatabaseManager
    mock_manager = MagicMock()
    mock_manager.init_for_config.side_effect = Exception("Disk I/O Error")

    with (
        patch("src.services.GoldenAppleConfig"),
        patch("src.services.GoldenAppleExtractor"),
        patch("src.services.DatabaseManager", return_value=mock_manager),
        patch("src.services.QThread") as mock_thread_class,
    ):
        # Функция должна выбросить RuntimeError, защищая от запуска с битой БД
        with pytest.raises(RuntimeError, match="Не удалось подготовить базу данных"):
            parsing_on_click(mock_obj)

        # Поток выполнения не должен инициализироваться
        mock_thread_class.assert_not_called()


def test_parsing_on_click_success_thread_start():
    """Проверяем успешную сборку конвейера потока, привязку сигналов и старт парсера."""
    mock_obj = MagicMock()
    mock_obj.target_url_input.text.return_value = "https://goldapple.ru"
    mock_obj.key_word_input.text.return_value = "помада"
    mock_obj.btn_send_scanning = MagicMock()
    mock_obj.btn_send_parsing = MagicMock()
    mock_obj.btn_cancel_parsing = MagicMock()
    mock_obj.result_display = MagicMock()

    # Создаем изолированные моки для треда и воркера
    mock_thread = MagicMock(spec=QThread)
    mock_worker = MagicMock()
    mock_parser = MagicMock()

    with (
        patch("src.services.GoldenAppleConfig"),
        patch("src.services.GoldenAppleExtractor"),
        patch("src.services.DatabaseManager"),
        patch("src.services.GoldenAppleParser", return_value=mock_parser),
        patch("src.services.QThread", return_value=mock_thread),
        patch("src.services.ParserWorker", return_value=mock_worker),
    ):
        parsing_on_click(mock_obj)

        # 1. Проверяем сброс красных рамок с UI-компонентов
        mock_obj.target_url_input.setStyleSheet.assert_called_once_with("")
        mock_obj.key_word_input.setStyleSheet.assert_called_once_with("")

        # 2. Кнопки запуска блокируются, предотвращая спам-клики во время работы
        mock_obj.btn_send_scanning.setEnabled.assert_called_once_with(False)
        mock_obj.btn_send_parsing.setEnabled.assert_called_once_with(False)

        # 3. Кнопка отмены парсинга включается при запуске
        mock_obj.btn_cancel_parsing.setEnabled.assert_called_once_with(True)

        # 4. Объект парсера успешно прописался в контекст главного окна
        assert mock_obj.parser == mock_parser

        # 5. Проверяем перенос воркера в фоновый тред и установку callback прогресса
        mock_worker.moveToThread.assert_called_once_with(mock_thread)
        assert mock_parser.progress_callback == mock_worker.progress_signal.emit

        # 6. Проверяем связывание QT-сигналов и логику автоматической очистки памяти
        mock_thread.started.connect.assert_called_once_with(mock_worker.run)
        mock_worker.finished_signal.connect.assert_any_call(mock_thread.quit)
        mock_worker.stop_signal.connect.assert_any_call(mock_thread.quit)
        mock_thread.finished.connect.assert_any_call(mock_thread.deleteLater)
        mock_thread.finished.connect.assert_any_call(mock_worker.deleteLater)

        # 7. В лог панели вывелась информация о запуске
        mock_obj.result_display.append.assert_called_once_with(
            "⏳ Запуск парсера для сайта: https://goldapple.ru, ключ: помада"
        )

        # 7. Фоновый поток выполнения Playwright физически запущен
        mock_thread.start.assert_called_once()


def test_parsing_preview_on_click_already_open():
    """Проверяем, что если таблица уже открыта, функция делает ранний выход."""
    mock_obj = MagicMock()
    # Имитируем, что viewer уже создан и активен
    mock_obj.db_viewer = MagicMock()

    with patch("src.services.logger") as mock_logger, patch("src.services.create_db_viewer") as mock_create:
        parsing_preview_on_click(mock_obj)

        # Должно записаться предупреждение, а создание виджета не должно вызываться
        mock_logger.warning.assert_called_once_with("Таблица уже открыта. Сначала закройте текущую таблицу.")
        mock_create.assert_not_called()


def test_parsing_preview_on_click_missing_parser():
    """Проверяем прерывание функции, если парсер не инициализирован."""
    mock_obj = MagicMock()
    mock_obj.db_viewer = None
    del mock_obj.parser  # Парсер отсутствует

    with patch("src.services.logger") as mock_logger:
        parsing_preview_on_click(mock_obj)

        mock_logger.warning.assert_called_once_with(
            "Ошибка экспорта. Парсер не инициализирован. Сначала запустите парсинг."
        )


def test_parsing_preview_on_click_missing_db_or_table():
    """Проверяем прерывание, если в парсере нет пути к БД или имени таблицы."""
    mock_obj = MagicMock()
    mock_obj.db_viewer = None
    mock_obj.parser.manager.db_path = None  # Путь пустой
    mock_obj.parser.manager.table_name = "products"

    with patch("src.services.logger") as mock_logger:
        parsing_preview_on_click(mock_obj)

        mock_logger.warning.assert_called_once_with("Ошибка экспорта. Не найден путь к БД или имя таблицы.")


def test_parsing_preview_on_click_success_mount():
    """Проверяем успешное создание viewer, скрытие логов и монтирование в интерфейс."""
    mock_obj = MagicMock()
    mock_obj.db_viewer = None
    mock_obj.parser.manager.db_path = "storage/viewhub_parsing.db"
    mock_obj.parser.manager.table_name = "golden_apple"

    mock_obj.btn_preview_parsing = MagicMock()
    mock_obj.result_display = MagicMock()

    # Имитируем layout у zone2
    mock_layout = MagicMock()
    mock_obj.zone2.layout.return_value = mock_layout

    # Создаем фальшивый виджет таблицы
    mock_viewer = MagicMock()

    with patch("src.services.create_db_viewer", return_value=mock_viewer) as mock_create:
        parsing_preview_on_click(mock_obj)

        # 1. Проверяем, что конструктор viewer вызвался с правильными параметрами
        mock_create.assert_called_once_with("storage/viewhub_parsing.db", "golden_apple", mock_obj)

        # 2. Кнопка предпросмотра заблокировалась, и ссылка на виджет сохранилась в obj
        mock_obj.btn_preview_parsing.setEnabled.assert_any_call(False)
        assert mock_obj.db_viewer == mock_viewer

        # 3. Предыдущее текстовое окно скрылось, а новая таблица вмонтировалась в layout
        mock_obj.result_display.hide.assert_called_once()
        mock_layout.addWidget.assert_called_once_with(mock_viewer)
        mock_viewer.show.assert_called_once()

        # 4. ВАЖНО: В блоке finally кнопка НЕ должна была включиться обратно,
        # так как viewer успешно создан (условие в finally не выполнилось)
        # Проверяем, что последний вызов setEnabled НЕ был True
        assert mock_obj.btn_preview_parsing.setEnabled.call_args_list[-1][0][0] is False


def test_parsing_preview_on_click_finally_fallback_unblock():
    """Проверяем, что если viewer не создался (вернул None), кнопка разблокируется."""
    mock_obj = MagicMock()
    mock_obj.db_viewer = None
    mock_obj.parser.manager.db_path = "data/viewhub.db"
    mock_obj.parser.manager.table_name = "golden_apple"
    mock_obj.btn_preview_parsing = MagicMock()

    # Имитируем, что функция создания виджета вернула None (например, сбой SQLite)
    with patch("src.services.create_db_viewer", return_value=None):
        parsing_preview_on_click(mock_obj)

        # Ссылка в obj осталась None
        assert mock_obj.db_viewer is None
        # Блок finally увидел, что viewer нет, и разблокировал кнопку для повторной попытки
        mock_obj.btn_preview_parsing.setEnabled.assert_any_call(False)
        mock_obj.btn_preview_parsing.setEnabled.assert_called_with(True)


def test_close_db_viewer_success():
    """Проверяем успешный демонтаж виджета таблицы, очистку памяти и восстановление UI."""
    mock_obj = MagicMock()
    mock_obj.btn_preview_parsing = MagicMock()
    mock_obj.result_display = MagicMock()

    # Имитируем активный виджет таблицы
    mock_viewer = MagicMock()
    mock_obj.db_viewer = mock_viewer

    # Имитируем layout у zone2
    mock_layout = MagicMock()
    mock_obj.zone2.layout.return_value = mock_layout

    # Вызываем тестируемую функцию закрытия
    close_db_viewer(mock_obj)

    # ПРОВЕРКИ:
    # 1. Виджет таблицы удален из компоновщика zone2
    mock_layout.removeWidget.assert_called_once_with(mock_viewer)

    # 2. Вызван метод безопасного удаления объекта из памяти Qt
    mock_viewer.deleteLater.assert_called_once()

    # 3. Ссылка на виджет внутри главного окна очищена
    assert mock_obj.db_viewer is None

    # 4. Текстовое окно логов вернулось на экран, а кнопка предпросмотра снова активна
    mock_obj.result_display.show.assert_called_once()
    mock_obj.btn_preview_parsing.setEnabled.assert_called_once_with(True)


def test_close_db_viewer_already_closed():
    """Проверяем, что если виджет таблицы не существует, функция ничего не делает."""
    mock_obj = MagicMock()
    mock_obj.db_viewer = None  # Таблица уже закрыта
    mock_obj.btn_preview_parsing = MagicMock()
    mock_obj.result_display = MagicMock()

    mock_layout = MagicMock()
    mock_obj.zone2.layout.return_value = mock_layout

    close_db_viewer(mock_obj)

    # Никакие методы удаления и переключения UI не должны вызываться
    mock_layout.removeWidget.assert_not_called()
    mock_obj.result_display.show.assert_not_called()
    mock_obj.btn_preview_parsing.setEnabled.assert_not_called()

def test_create_db_viewer_empty_table(monkeypatch, qtbot, tmp_path):
    """Проверяем, что если таблица в БД пуста, функция возвращает None и пишет в UI."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()

    # Создаем путь во временной папке pytest (он удалится автоматически)
    temp_db_file = str(tmp_path / "test_products.db")

    # Имитируем возврат пустого DataFrame из pandas
    monkeypatch.setattr(pd, "read_sql_query", lambda *args, **kwargs: pd.DataFrame())

    # Передаем временный путь
    viewer = create_db_viewer(temp_db_file, "products", mock_obj)

    assert viewer is None
    mock_obj.result_display.append.assert_called_once_with("⚠️ Таблица пуста")


def test_create_db_viewer_success(monkeypatch, qtbot, tmp_path):
    """Проверяем успешную сборку виджета, таблицы и заполнение её ячеек данными."""
    mock_obj = MagicMock()

    # Готовим тестовые данные (2 строки, 2 колонки)
    test_df = pd.DataFrame({
        "ID": [1,2],
        "Название": ["Товар А", "Товар Б"]
    })

    # Создаем путь во временной папке pytest (он удалится автоматически)
    temp_db_file = str(tmp_path / "test_products.db")

    monkeypatch.setattr(pd, "read_sql_query", lambda *args, **kwargs: test_df)

    # Вызываем функцию
    viewer = create_db_viewer(temp_db_file, "products", mock_obj)

    # РЕШЕНИЕ: Регистрируем виджет в контексте qtbot, чтобы избежать ошибки 0xC0000409
    qtbot.addWidget(viewer)

    # ПРОВЕРКИ:
    assert viewer is not None
    assert isinstance(viewer, QWidget)

    layout = viewer.layout()
    assert layout is not None
    assert layout.count() == 2

    button = layout.itemAt(0).widget()
    table = layout.itemAt(1).widget()

    assert isinstance(button, QPushButton)
    assert isinstance(table, QTableWidget)
    assert table.rowCount() == 2
    assert table.columnCount() == 2

    assert table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers

    assert table.item(0, 0).text() == "1"
    assert table.item(0, 1).text() == "Товар А"


def test_create_db_viewer_button_click(monkeypatch, qtbot, tmp_path):
    """Проверяем, что клик по кнопке закрытия вызывает функцию close_db_viewer."""
    mock_obj = MagicMock()
    test_df = pd.DataFrame({"col": [1]})
    temp_db_file = str(tmp_path / "test_products.db")
    monkeypatch.setattr(pd, "read_sql_query", lambda *args, **kwargs: test_df)

    with patch("src.services.close_db_viewer") as mock_close:
        viewer = create_db_viewer(temp_db_file, "products", mock_obj)
        qtbot.addWidget(viewer)

        # Находим кнопку в макете и эмулируем клик пользователя
        button = viewer.layout().itemAt(0).widget()
        button.click()

        mock_close.assert_called_once_with(mock_obj)


def test_create_db_viewer_exception_handling(monkeypatch, qtbot, tmp_path):
    """Проверяем перехват критических исключений при падении запроса к БД."""
    mock_obj = MagicMock()
    mock_obj.result_display = MagicMock()
    temp_db_file = str(tmp_path / "test_products.db")

    # Имитируем жесткое падение библиотеки pandas/sqlite3
    def mock_crash(*args, **kwargs):
        raise sqlite3.DatabaseError("Database file is encrypted or corrupted")

    monkeypatch.setattr(pd, "read_sql_query", mock_crash)

    # Вызываем функцию
    viewer = create_db_viewer(temp_db_file, "products", mock_obj)

    # Так как viewer вернет None при исключении, регистрировать его в qtbot не нужно
    assert viewer is None
    mock_obj.result_display.append.assert_called_once_with(
        "❌ Ошибка при создании viewer: Database file is encrypted or corrupted"
    )
