"""Конфигурация для парсинга интернет-магазина Золотое Яблоко."""

from typing import Dict, ClassVar
from src.core.base_classes import BaseDBParsingConfig


class GoldenAppleConfig(BaseDBParsingConfig):
    """
    Конфигурация для парсинга интернет-магазина Золотое Яблоко.
    Формат схемы: колонки описываются в нативном SQL-формате для SQLite.
    """

    # Схема бизнес-колонок: имя -> SQL-тип для SQLite
    BUSINESS_COLUMNS: ClassVar[Dict[str, str]] = {
        "item_id": "TEXT NOT NULL",  # Идентификатор товара (без UNIQUE, его добавит PRIMARY KEY)
        "category": "TEXT",
        "brand": "TEXT",
        "name": "TEXT NOT NULL",
        "product_type": "TEXT",
        "old_price_rub": "REAL",
        "current_price_rub": "REAL",
        "discount": "REAL",
        "in_stock": "INTEGER DEFAULT 0",  # В SQLite булевы значения хранятся как INTEGER (0 или 1)
        "rating": "REAL",
        "url": "TEXT",
        "catalog_page_url": "TEXT",
        "description": "TEXT",
        "usage": "TEXT",
        "country_of_origin": "TEXT",
        "page_number": "INTEGER",
    }

    # Ключ, по которому сейвер будет делать ON CONFLICT (UPSERT)
    DEDUP_COLUMN: str = "item_id"

    @classmethod
    def get_full_schema(cls) -> Dict[str, str]:
        """Схема ВСЕХ колонок таблицы: системные + специфичные для сайта."""
        return {**cls.SYSTEM_COLUMNS, **cls.BUSINESS_COLUMNS}
