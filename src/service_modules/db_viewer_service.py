"""Сервисный слой для просмотра базы данных."""

import logging
import sqlite3

import pandas as pd

from PyQt6.QtWidgets import QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


def parsing_preview_on_click(obj):
    """Открытие виджета с таблицей из БД в zone2."""
    # Проверяем, не открыта ли уже таблица
    if hasattr(obj, "db_viewer") and obj.db_viewer is not None:
        logger.warning("Таблица уже открыта. Сначала закройте текущую таблицу.")
        return

    # Получаем парсер, если он был создан при запуске парсинга
    parser = getattr(obj, "parser", None)
    if not parser:
        logger.warning("Ошибка экспорта. Парсер не инициализирован. Сначала запустите парсинг.")
        return

    # Получаем путь к БД и имя таблицы
    db_path = getattr(parser.manager, "db_path", None)
    table_name = getattr(parser.manager, "table_name", None)

    if not db_path or not table_name:
        logger.warning("Ошибка экспорта. Не найден путь к БД или имя таблицы.")
        return

    # Делаем кнопку временно неактивной, чтобы избежать спам-кликов
    if hasattr(obj, "btn_preview_parsing"):
        obj.btn_preview_parsing.setEnabled(False)

    try:
        # Создаем виджет с таблицей
        viewer = create_db_viewer(db_path, table_name, obj)
        if viewer:
            # Сохраняем ссылку на виджет
            obj.db_viewer = viewer
            # Добавляем виджет в zone2
            if hasattr(obj, "zone2"):
                layout = obj.zone2.layout()
                # Скрываем result_display
                if hasattr(obj, "result_display"):
                    obj.result_display.hide()
                # Добавляем viewer
                layout.addWidget(viewer)
                viewer.show()

    finally:
        # Разблокируем кнопку только если viewer не был создан
        if not (hasattr(obj, "db_viewer") and obj.db_viewer is not None):
            if hasattr(obj, "btn_preview_parsing"):
                obj.btn_preview_parsing.setEnabled(True)


def close_db_viewer(obj):
    """Закрытие виджета с таблицей и возврат к result_display."""
    if hasattr(obj, "db_viewer") and obj.db_viewer:
        layout = obj.zone2.layout()
        layout.removeWidget(obj.db_viewer)
        obj.db_viewer.deleteLater()
        obj.db_viewer = None
        # Показываем result_display
        if hasattr(obj, "result_display"):
            obj.result_display.show()
        # Разблокируем кнопку просмотра
        if hasattr(obj, "btn_preview_parsing"):
            obj.btn_preview_parsing.setEnabled(True)


def create_db_viewer(db_path: str, table_name: str, obj) -> QWidget:
    """Создает виджет для просмотра таблицы SQLite через pandas + QTableWidget."""
    widget = QWidget()
    layout = QVBoxLayout(widget)

    try:
        # Читаем данные через pandas (потокобезопасно)
        conn = sqlite3.connect(db_path)
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)  # noqa: S608
        finally:
            conn.close()

        if df.empty:
            if hasattr(obj, "result_display"):
                obj.result_display.append("⚠️ Таблица пуста")
            return None

        # Создаем кнопку закрытия
        close_btn = QPushButton("✕ Закрыть")
        close_btn.clicked.connect(lambda: close_db_viewer(obj))
        close_btn.setMaximumHeight(40)
        layout.addWidget(close_btn)

        # Создаем QTableWidget
        table = QTableWidget()
        table.setRowCount(len(df))
        table.setColumnCount(len(df.columns))
        table.setHorizontalHeaderLabels(df.columns)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)  # Отключаем редактирование

        # Заполняем таблицу данными
        for row_idx, row_data in df.iterrows():
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                table.setItem(row_idx, col_idx, item)

        # Автоматическое растягивание колонок
        table.resizeColumnsToContents()

        layout.addWidget(table)
        return widget

    except Exception as e:
        logger.exception("Ошибка при создании viewer: %s", e)
        if hasattr(obj, "result_display"):
            obj.result_display.append(f"❌ Ошибка при создании viewer: {e}")
        return None
