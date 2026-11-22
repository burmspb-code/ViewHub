"""Конфигурация для парсинга сайта Цитадель."""

from typing import Dict, ClassVar

from src.core.base_classes import BaseDBParsingConfig


class CitadelConfig(BaseDBParsingConfig):
    """
    Конфигурация для парсинга сайта Цитадель.
    Формат схемы: колонки описываются в нативном SQL-формате для SQLite.
    """

    # Схема бизнес-колонок: имя -> SQL-тип для SQLite.
    # Ключи должны в точности совпадать с ключами словарей из CitadelExtractor.
    BUSINESS_COLUMNS: ClassVar[Dict[str, str]] = {
        "item_id": "TEXT NOT NULL",  # Идентификатор товара (без UNIQUE, его добавит PRIMARY KEY)
        "name": "TEXT NOT NULL",
        "code": "TEXT",  # Код товара (артикул) со страницы товара
        "url": "TEXT",
        "brand": "TEXT",
        "availability": "TEXT",
        "description": "TEXT",
        "current_price": "REAL",  # На сайте цена скрыта до авторизации, поэтому часто будет NULL
    }

    # Ключ, по которому сейвер будет делать ON CONFLICT (UPSERT)
    DEDUP_COLUMN: ClassVar[str] = "item_id"

    @classmethod
    def get_full_schema(cls) -> Dict[str, str]:
        """Схема ВСЕХ колонок таблицы: системные + специфичные для сайта."""
        return {**cls.SYSTEM_COLUMNS, **cls.BUSINESS_COLUMNS}
