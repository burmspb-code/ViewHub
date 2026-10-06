"""Сервисный слой для экспорта данных."""

import logging
import sqlite3

import pandas as pd

from PyQt6.QtWidgets import QFileDialog

logger = logging.getLogger(__name__)


def parsing_export_on_click(obj):
    """Экспорт таблицы из БД."""
    # Получаем парсер, если он был создан при запуске парсинга
    parser = getattr(obj, "parser", None)
    if not parser:
        logger.warning("Ошибка экспорта. Парсер не инициализирован. Сначала запустите парсинг.")
        return

    # Формируем дефолтное имя файла
    path_name = parsing_export_init(parser)

    # Если имя нигде не зафиксировано, возврат
    if not path_name:
        logger.warning("Ошибка экспорта. Возможно нечего сохранять.")
        return

    # Делаем кнопку экспорта временно неактивной, чтобы избежать спам-кликов
    if hasattr(obj, "btn_export_parsing"):
        obj.btn_export_parsing.setEnabled(False)

    try:
        # Читаем таблицу из БД (передаем parser и obj для логов в UI)
        table = parsing_db_read(parser, obj)

        # Если таблица пустая или была ошибка чтения — прерываем экспорт
        if table is None or table.empty:
            return

        # Открываем окно и сохраняем таблицу в файл (передаем table, path_name и obj)
        parsing_file_save(table, path_name, obj)

    finally:
        # Разблокируем кнопку экспорта при любом исходе (даже при ошибках)
        if hasattr(obj, "btn_export_parsing"):
            obj.btn_export_parsing.setEnabled(True)


def parsing_export_init(parser) -> str:
    """Формируем имя файла для экспорта."""
    # Задаем базовое имя файла на основе конфига или имени таблицы
    base_name = getattr(parser.config, "file_name", "")
    if not base_name:
        base_name = getattr(parser.manager, "table_name", "")

    if not base_name:
        return ""

    # Добавляем расширение по умолчанию, если его нет в имени таблицы/конфига
    if not base_name.endswith((".xlsx", ".csv")):
        path_name = f"{base_name}.xlsx"
    else:
        path_name = base_name

    return path_name


def parsing_db_read(parser, obj) -> pd.DataFrame | None:
    """Чтение таблицы из БД."""
    try:
        # Получаем путь к БД
        db_path = getattr(parser.manager, "db_path", None)
        if not db_path:
            logger.error("Не удалось найти путь к базе данных SQLite в parser.manager!")
            if hasattr(obj, "result_display"):
                obj.result_display.append("❌ Ошибка: не найден файл базы данных.")
            return None

        # Получаем имя таблицы
        table_name = getattr(parser.manager, "table_name", None)
        if not table_name:
            logger.warning("Не удалось найти таблицу для экспорта.")
            if hasattr(obj, "result_display"):
                obj.result_display.append("⚠️ Ошибка: имя таблицы не задано.")
            return None

        # Читаем данные через pandas с явным управлением соединением
        conn = sqlite3.connect(db_path)
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)  # noqa: S608
        finally:
            conn.close()
            # Удаляем ссылку для гарантии освобождения ресурсов
            del conn

        if df.empty:
            logger.warning("Экспорт отменен: таблица в базе данных пуста.")
            if hasattr(obj, "result_display"):
                obj.result_display.append("⚠️ База данных пуста, нечего экспортировать.")
            return None

        return df

    except Exception as e:
        error_msg = str(e).splitlines()[0] if str(e) else "Unknown database error"
        logger.error(f"Ошибка при импорте из БД: {error_msg}")
        if hasattr(obj, "result_display"):
            obj.result_display.append(f"❌ Ошибка чтения БД: {error_msg}")
        return None


def parsing_file_save(df, path_name, obj) -> None:
    """Сохранение данных в файл."""
    # Открываем диалоговое окно сохранения
    file_path, _ = QFileDialog.getSaveFileName(
        obj, "Сохранить файл", path_name, "Excel Files (*.xlsx);;CSV Files (*.csv)"
    )

    # Если пользователь закрыл окно или нажал "Отмена"
    if not file_path:
        logger.info("Экспорт отменен пользователем.")
        return

    try:
        if file_path.endswith(".xlsx"):
            # index=False убирает системную колонку с номерами строк от pandas
            df.to_excel(file_path, index=False, engine="openpyxl")
        elif file_path.endswith(".csv"):
            # utf-8-sig чтобы Excel корректно читал кириллицу в CSV
            df.to_csv(file_path, index=False, encoding="utf-8-sig")

        # Если запись прошла успешно
        logger.info(f"Данные успешно сохранены в файл: {file_path}")
        if hasattr(obj, "result_display"):
            obj.result_display.append(f"💾 Успешный экспорт: {file_path}")

    except PermissionError:
        # Отдельно обрабатываем частую ошибку, когда файл уже открыт в Excel
        error_msg = "Файл занят другой программой (например, Excel). Закройте его и повторите попытку."
        logger.error(f"Ошибка доступа к файлу: {file_path} заблокирован.")
        if hasattr(obj, "result_display"):
            obj.result_display.append(f"❌ Ошибка доступа: {error_msg}")

    except Exception as e:
        # Перехватываем любые другие ошибки диска (нет места, некорректные символы в пути и т.д.)
        error_msg = str(e).splitlines()[0] if str(e) else "Unknown file write error"
        logger.error(f"Ошибка при записи файла: {error_msg}")
        if hasattr(obj, "result_display"):
            obj.result_display.append(f"❌ Ошибка записи файла: {error_msg}")
