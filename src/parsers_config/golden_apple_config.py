"""Конфигурация для парсинга сайта Золотое Яблоко."""

from typing import Any, Dict
from parent_base_classes import BaseConfig


class GoldenAppleConfig(BaseConfig):
    """
    Конфигурация для парсинга интернет-магазина Золотое Яблоко.
    Управляет базовыми ссылками, категориями и именами файлов для PyQt6-воркера.
    """

    # Описание колонок таблицы: имя → SQL-тип.
    COLUMNS: Dict[str, str] = {
        "category": "TEXT",
        "item_id": "TEXT NOT NULL",
        "brand": "TEXT",
        "name": "TEXT",
        "product_type": "TEXT",
        "old_price_rub": "REAL",
        "current_price_rub": "REAL",
        "discount": "REAL",
        "in_stock": "INTEGER",
        "rating": "REAL",
        "url": "TEXT",
        "catalog_page_url": "TEXT NOT NULL",
        "description": "TEXT",
        "usage": "TEXT",
        "country_of_origin": "TEXT",
    }
    KEY_COLUMN: str = "item_id"
    PAGE_URL_COLUMN: str = "catalog_page_url"

    def __init__(
        self, target_url: str, keyword: str = "", file_name: str = "", config: Dict[str, Any] | None = None
    ) -> None:
        """Инициализация параметров конфигурации."""
        super().__init__(target_url, keyword, file_name, config)