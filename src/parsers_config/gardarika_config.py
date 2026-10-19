"""Конфигурация для парсинга сайта Гардарики."""

from typing import Dict, ClassVar

from src.core.base_classes import BaseDBParsingConfig


class GardarikaConfig(BaseDBParsingConfig):
    """
    Конфигурация для парсинга сайта Гардарики.
    Формат схемы: колонки описываются в нативном SQL-формате для SQLite.
    """

    # Схема бизнес-колонок: имя -> SQL-тип для SQLite
    BUSINESS_COLUMNS: ClassVar[Dict[str, str]] = {
        "item_id": "TEXT NOT NULL",  # Идентификатор товара (без UNIQUE, его добавит PRIMARY KEY)
        "name": "TEXT NOT NULL",
        "in_stock": "INTEGER DEFAULT 0",  # В SQLite булевы значения хранятся как INTEGER (0 или 1)
        "package": "INTEGER",
        "current_price": "REAL",
        "url": "TEXT",
        "description": "TEXT",
    }

    # Ключ, по которому сейвер будет делать ON CONFLICT (UPSERT)
    DEDUP_COLUMN: str = "item_id"

    @classmethod
    def get_full_schema(cls) -> Dict[str, str]:
        """Схема ВСЕХ колонок таблицы: системные + специфичные для сайта."""
        return {**cls.SYSTEM_COLUMNS, **cls.BUSINESS_COLUMNS}
