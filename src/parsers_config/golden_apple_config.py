"""Конфигурация для парсинга сайта Золотое Яблоко."""

from typing import Dict, Tuple, ClassVar

from core.base_classes import BaseConfig


class GoldenAppleConfig(BaseConfig):
    """
    Конфигурация для парсинга интернет-магазина Золотое Яблоко.

    Формат схемы: колонки описываются голыми Python-типами.
    Маппер в SQLiteSaver превратит:
        str -> TEXT, float -> REAL, int -> INTEGER, bool -> INTEGER.
    NOT NULL задаётся через NOT_NULL_COLUMNS, ключи — через TABLE_CONSTRAINTS.
    """

    DEDUP_COLUMN = "item_id"

    COLUMNS: ClassVar[Dict[str, type]] = {
        "item_id": str,
        "category": str,
        "brand": str,
        "name": str,
        "product_type": str,
        "old_price_rub": float,
        "current_price_rub": float,
        "discount": float,
        "in_stock": int,          # SQLite хранит булевы значения как 0/1
        "rating": float,
        "url": str,
        "catalog_page_url": str,
        "description": str,
        "usage": str,
        "country_of_origin": str,
    }

    NOT_NULL_COLUMNS: Tuple[str, ...] = ("item_id", "name")

    # Первичный ключ задан явно — технический "id" сейвер не добавит
    TABLE_CONSTRAINTS: Tuple[str, ...] = (
        "PRIMARY KEY (item_id)",
    )

    def __init__(
        self,
        target_url: str,
        keyword: str = "",
        file_name: str = "",
    ) -> None:
        super().__init__(target_url, keyword, file_name)
