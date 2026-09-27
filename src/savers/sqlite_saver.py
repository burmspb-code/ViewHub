import re
import uuid
import logging
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, ClassVar

import sqlite3

from core.base_classes import BaseConfig
from core.db_config import DBConfig


logger = logging.getLogger(__name__)


class SQLiteSaver:
    MAX_IDENTIFIER_LENGTH = 60

    TYPE_MAPPING: ClassVar[Dict[type, List[str]]] = {
        int: ["INTEGER"],
        float: ["REAL"],
        str: ["TEXT"],
        bool: ["INTEGER"],
        datetime: ["TEXT"],
        bytes: ["BLOB"],
    }

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path: Path = DBConfig.get_db_path(db_path)
        self.config: Optional[BaseConfig] = None
        self.table_name: Optional[str] = None
        self.session_id: Optional[str] = None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _make_table_name(self, config: BaseConfig) -> str:
        from urllib.parse import urlparse
        domain = urlparse(config.target_url).netloc
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", domain).strip("_")
        keyword = re.sub(r"[^a-zA-Z0-9а-яА-Я]+", "_", config.keyword or "").strip("_")
        table_name = f"{slug}_{keyword}".strip("_") or "parsed_data"
        if len(table_name) > self.MAX_IDENTIFIER_LENGTH:
            table_name = table_name[: self.MAX_IDENTIFIER_LENGTH]
        return table_name.lower()

    def _get_dedup_column(self, config: BaseConfig) -> str:
        dedup = getattr(config, "DEDUP_COLUMN", None)
        if dedup:
            return dedup
        if hasattr(config, "get_dedup_column") and callable(config.get_dedup_column):
            result = config.get_dedup_column()
            if result:
                return result
        for constraint in getattr(config, "TABLE_CONSTRAINTS", ()) or ():
            m = re.search(r'UNIQUE\s*$\s*"?(\w+)"?\s*$', str(constraint), re.IGNORECASE)
            if m:
                return m.group(1)
        raise ValueError("Не удалось определить колонку дедупликации.")

    def _build_create_sql(self, config: BaseConfig) -> str:
        not_null_columns = set(getattr(config, "NOT_NULL_COLUMNS", ()) or ())
        raw_constraints = getattr(config, "TABLE_CONSTRAINTS", ()) or ()
        constraints = [str(c).strip() for c in raw_constraints if str(c).strip()]
        has_pk = any("PRIMARY KEY" in c.upper() for c in constraints)

        schema = config.get_table_columns()
        if not isinstance(schema, dict):
            raise TypeError(f"Схема должна быть словарем, получено: {type(schema)}")

        parts = []

        # 1. Бизнес-колонки
        for col_name, col_type in schema.items():
            if col_type not in self.TYPE_MAPPING:
                raise ValueError(f"Неизвестный тип {col_type} для колонки '{col_name}'")
            frags = list(self.TYPE_MAPPING[col_type])
            if col_name in not_null_columns:
                frags.append("NOT NULL")
            parts.append(f'"{col_name}" {" ".join(frags)}')

        # 2. Технический ключ (если нет своего PK)
        if not has_pk:
            parts.append('"id" INTEGER PRIMARY KEY')

        # 3. Служебные колонки (ТЕПЕРЬ ТУТ: строго до ограничений таблицы!)
        parts.append('"created_at" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP')
        parts.append('"page_number" INTEGER')
        parts.append('"session_id" TEXT NOT NULL')

        # 4. Ограничения таблицы (ТЕПЕРЬ СТРОГО В КОНЦЕ)
        parts.extend(constraints)

        cols_def = ",\n    ".join(parts)
        return f'CREATE TABLE IF NOT EXISTS "{self.table_name}" (\n    {cols_def}\n)'


    def ensure_table(self, config: BaseConfig) -> str:
        table_name = self._make_table_name(config)
        self.table_name = table_name

        # Отладка: что реально идет в SQL
        schema = config.get_table_columns()
        logger.debug(f"🔍 DEBUG: Таблица '{table_name}', Тип схемы: {type(schema)}")

        if not isinstance(schema, dict):
            raise TypeError(f"Схема должна быть словарем, получено: {type(schema)}")

        dedup_column = self._get_dedup_column(config)
        if dedup_column not in schema and dedup_column != "id":
            raise ValueError(f"Колонка дедупликации '{dedup_column}' отсутствует в схеме.")

        create_sql = self._build_create_sql(config)

        # Выводим SQL ПЕРЕД выполнением, чтобы видеть именно то, что летит в БД
        logger.info(f"📜 EXECUTING SQL:\n{create_sql}")

        with closing(self._connect()) as conn:
            try:
                conn.execute(create_sql)
                conn.commit()
            except Exception as e:
                logger.error(f"❌ FAILED SQL EXECUTION: {e}")
                # Для отладки: распечатаем SQL еще раз, если ошибка
                print("--- FAILED SQL DUMP ---")
                print(create_sql)
                print("-----------------------")
                raise

        logger.info(f"✅ Таблица '{table_name}' успешно создана.")
        return table_name

    def init_for_config(self, config: BaseConfig) -> str:
        self.config = config
        self.table_name = self.ensure_table(config)
        self.session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        return self.table_name

    def save(self, items: List[Dict[str, Any]], page_number: int = 0) -> int:
        if not self.config or not self.table_name or not self.session_id:
            raise RuntimeError("Сейвер не инициализирован.")

        key_column = self.config.get_key_column()
        schema = self.config.get_table_columns()
        data_columns = [c for c in schema if c != key_column]

        cols_to_insert = [key_column, *data_columns, "created_at", "page_number", "session_id"]
        placeholders = ", ".join(["?"] * len(cols_to_insert))
        cols_str = ", ".join(f'"{c}"' for c in cols_to_insert)

        update_cols = [*data_columns, "page_number", "session_id"]
        update_set = ", ".join(f'"{c}" = excluded."{c}"' for c in update_cols)

        sql = (
            f'INSERT INTO "{self.table_name}" ({cols_str}) VALUES ({placeholders}) ' # noqa: S608
            f'ON CONFLICT("{key_column}") DO UPDATE SET {update_set}'
        )

        affected = 0
        # Предварительно вычисляем неизменяемые для этой пачки значения
        current_time = datetime.now().isoformat()

        # Подготавливаем данные в виде списка кортежей
        params = [
            (item.get(key_column), *(item.get(c) for c in data_columns), current_time, page_number, self.session_id)
            for item in items
        ]

        if params:
            with closing(self._connect()) as conn:
                # 1. Отключаем автоматический запуск транзакций (опционально для старых версий, но надежно)
                conn.isolation_level = None

                with conn:  # Контекстный менеджер транзакции (автоматический commit/rollback)
                    cursor = conn.cursor()

                    # 2. Включаем ускоряющие настройки (PRAGMA)
                    cursor.execute("PRAGMA synchronous = OFF;")
                    cursor.execute("PRAGMA journal_mode = WAL;")

                    # 3. Пакетная вставка
                    cursor.executemany(sql, params)
                    affected += len(items)

        return affected
