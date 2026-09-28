"""Модуль взаимодействия с SQLite."""

import re
import logging
import hashlib
import sqlite3
import uuid
import threading
from contextlib import closing
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.base_classes import BaseDBParsingConfig
from core.db_config import DBParsingConfig


logger = logging.getLogger(__name__)


class SQLiteSaver:
    """Класс для сохранения данных в SQLite. На вход получаем путь к базе данных для записи."""

    # Для SQLite лимит огромный (1 млн), но если мы хотим держать имена аккуратными
    # или совместимыми с PostgreSQL, оставляем 63 СИМВОЛА.
    MAX_IDENTIFIER_LENGTH = 63

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path: Path = DBParsingConfig.get_db_path(db_path)
        self.config: Optional[BaseDBParsingConfig] = None
        self.table_name: Optional[str] = None
        self.session_id: Optional[str] = None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Блокировка для потокобезопасности при конкурентных операциях с БД
        self._lock = threading.Lock()

    def _connect(self):
        """Устанавливает соединение с SQLite и включает WAL-режим логирования."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _make_table_name(self, config: BaseDBParsingConfig) -> str:
        """Формирует имя таблицы на основе URL и ключевого слова.
        Ориентировано на ограничение в символах (совместимо с SQLite).
        """
        domain = urlparse(config.target_url).netloc  # Получаем домен из URL
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", domain).strip("_")
        keyword = re.sub(r"[^a-zA-Z0-9а-яА-Я]+", "_", config.keyword or "").strip("_")

        # Для SQLite переводим в lower сразу. SQLite регистрозависим для кириллицы,
        # поэтому приведение к одному регистру спасет от дубликатов таблиц.
        table_name = f"{slug}_{keyword}".strip("_").lower() or "parsed_data"

        # В SQLite считаем СИМВОЛЫ, а не байты
        if len(table_name) > self.MAX_IDENTIFIER_LENGTH:
            # 20 символов хэша гарантируют уникальность
            hash_suffix = hashlib.md5(table_name.encode("utf-8")).hexdigest()[:20] # noqa: S324

            # Высчитываем доступное место под базовое имя в символах (63 - 20 - 1 = 42)
            max_base_len = self.MAX_IDENTIFIER_LENGTH - len(hash_suffix) - 1

            # Спокойно режем строку по символам, кириллица здесь не сломается
            base_name = table_name[:max_base_len].rstrip("_")
            table_name = f"{base_name}_{hash_suffix}"

        return table_name

    def _build_create_sql(self, config: BaseDBParsingConfig) -> str:
        """Построение sql запроса создания таблицы."""
        # Получаем полную схему (в ней уже есть id, created_at, session_id и бизнес-поля)
        schema = config.get_full_schema()
        if not isinstance(schema, dict):
            raise TypeError(f"Схема должна быть словарем, получено: {type(schema)}")

        # Собираем ограничения таблицы (constraints)
        raw_constraints = getattr(config, "TABLE_CONSTRAINTS", ()) or ()
        constraints = [str(c).strip() for c in raw_constraints if str(c).strip()]

        # Получаем имя колонки для дедупликации (например, "item_id")
        dedup_col = getattr(config, "DEDUP_COLUMN", None)

        parts = []

        # Перебираем ВСЕ колонки из схемы
        for col_name, col_type in schema.items():
            actual_type = col_type

            # Автоматическая защита: если это колонка дедупликации,
            # и в её типе ещё нет UNIQUE, и она не вынесена в TABLE_CONSTRAINTS — дописываем UNIQUE
            if col_name == dedup_col and "UNIQUE" not in col_type.upper():
                # Проверяем, не написан ли UNIQUE для этой колонки в constraints
                if not any(f"UNIQUE({col_name})" in c.replace(" ", "") for c in constraints):
                    actual_type = f"{col_type} UNIQUE"

            # Оборачиваем имя колонки в безопасные кавычки
            parts.append(f'"{col_name}" {actual_type}')

        # Добавляем "page_number", если его нет в схеме, но он нужен для парсинга
        if "page_number" not in schema:
            parts.append('"page_number" INTEGER')

        # Присоединяем ограничения таблицы строго в самый конец
        parts.extend(constraints)

        # Формируем финальный SQL
        cols_def = ",\n    ".join(parts)
        table_name = self._make_table_name(config)

        return f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n    {cols_def}\n)'

    def ensure_table(self, config: BaseDBParsingConfig) -> str:
        """Проверяет и обеспечивает существование таблицы в SQLite.
        Генерирует имя таблицы, валидирует схему и колонку дедупликации,
        после чего создает таблицу в БД, если она еще не существовала.
        Args:
            config (BaseDBParsingConfig): Конфигурация парсера со схемой и настройками.
        Returns:
            str: Итоговое имя созданной таблицы.
        """
        table_name = self._make_table_name(config)
        self.table_name = table_name

        # Отладка: что реально идет в SQL
        schema = config.get_full_schema()
        logger.debug(f"🔍 DEBUG: Таблица '{table_name}', Тип схемы: {type(schema).__name__}")

        if not isinstance(schema, dict):
            raise TypeError(f"Схема должна быть словарем, получено: {type(schema).__name__}")

        dedup_column = config.DEDUP_COLUMN

        if dedup_column not in schema and dedup_column != "id":
            raise ValueError(f"Колонка дедупликации '{dedup_column}' отсутствует в схеме.")

        create_sql = self._build_create_sql(config)

        with closing(self._connect()) as conn:
            try:
                conn.execute(create_sql)
                conn.commit()
            except Exception as e:
                logger.error(f"❌ Ошибка БД: {e}")
                raise

        logger.info(f"✅ Таблица '{table_name}' успешно создана.")
        return table_name

    def init_for_config(self, config: BaseDBParsingConfig) -> str:
        """Инициализирует сейвер под конкретную конфигурацию.
        Создает или проверяет таблицу, генерирует уникальный ID сессии
        и сохраняет настройки для последующей записи данных.
        Args:
            config (BaseDBParsingConfig): Конфигурация текущего парсера.
        Returns:
            str: Итоговое имя целевой таблицы.
        """
        # Импорты внутри метода (или перенесите их в самый верх файла)
        self.config = config
        self.table_name = self.ensure_table(config)
        self.session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        return self.table_name

    def save(self, items: List[Dict[str, Any]]) -> int:
        """Сохраняет пачку товаров в SQLite с обновлением дубликатов (UPSERT).
        Args:
            items (List[Dict[str, Any]]): Список словарей с данными товаров.
        Returns:
            int: Количество успешно сохраненных или обновленных записей.
        """
        if not self.config or not self.table_name or not self.session_id:
            raise RuntimeError("Сейвер не инициализирован.")

        from contextlib import closing
        from datetime import datetime

        # Получаем полную схему
        schema = self.config.get_full_schema()
        key_column = self.config.get_key_column()  # "id"
        dedup_column = getattr(self.config, "DEDUP_COLUMN", None)  # "item_id"

        # Формируем список колонок для вставки (исключая автоинкрементный id)
        # Так как page_number уже в схеме, cols_to_insert соберется автоматически!
        cols_to_insert = [c for c in schema if c != key_column]

        placeholders = ", ".join(["?"] * len(cols_to_insert))
        cols_str = ", ".join(f'"{c}"' for c in cols_to_insert)

        # Настраиваем логику обновления при конфликте
        update_cols = [c for c in cols_to_insert if c not in (dedup_column, "created_at")]
        update_set = ", ".join(f'"{c}" = excluded."{c}"' for c in update_cols)

        sql = (
            f'INSERT INTO "{self.table_name}" ({cols_str}) VALUES ({placeholders}) '  # noqa: S608
            f'ON CONFLICT("{dedup_column}") DO UPDATE SET {update_set}'
        )

        affected = 0
        current_time = datetime.now().isoformat()

        # Подготавливаем параметры (теперь тут супер-простой и быстрый цикл)
        params = []
        for item in items:
            row = []
            for c in cols_to_insert:
                if c == "created_at":
                    row.append(current_time)
                elif c == "session_id":
                    row.append(self.session_id)
                else:
                    row.append(item.get(c))  # page_number заберется отсюда автоматически!
            params.append(tuple(row))

        # Пакетная запись в БД с блокировкой для потокобезопасности
        if params:
            with self._lock:
                with closing(self._connect()) as conn:
                    conn.isolation_level = None
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute("PRAGMA synchronous = OFF;")
                        cursor.execute("PRAGMA journal_mode = WAL;")

                        cursor.executemany(sql, params)
                        affected += len(items)

        return affected

    def check_existing_items_with_pages(self, item_ids: list[str]) -> dict[str, int]:
        """Возвращает словарь {item_id: page_number} для товаров, которые уже есть в БД."""
        if not self.table_name or not item_ids:
            return {}

        placeholders = ", ".join(["?"] * len(item_ids))
        dedup_col = getattr(self.config, "DEDUP_COLUMN", "item_id")

        # Запрашиваем сразу две колонки: бизнес-ключ и номер страницы
        sql = f'SELECT "{dedup_col}", "page_number" FROM "{self.table_name}" WHERE "{dedup_col}" IN ({placeholders})'  # noqa: S608

        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, tuple(item_ids))

                # Собираем результат в словарь: { 'ID_товара': номер_страницы_в_БД }
                return {str(row[0]): row[1] for row in cursor.fetchall()}

    def get_last_page_number(self) -> int:
        """Возвращает последний сохраненный номер страницы из БД для возобновления парсинга."""
        if not self.table_name:
            return 1

        sql = f'SELECT MAX("page_number") FROM "{self.table_name}"'  # noqa: S608

        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                result = cursor.fetchone()

                if result and result[0] is not None:
                    return result[0]
                return 1
