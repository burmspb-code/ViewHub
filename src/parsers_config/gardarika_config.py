"""Конфигрурация для парсинга сайта Гардарики."""

from typing import Any, Dict

from parser_classes import BaseConfig


class CitadelConfig(BaseConfig):
    """Конфиг для сайта Гардарика."""

    def __init__(
        self, target_url: str, keyword: str = "", file_name: str = "", config: Dict[str, Any] | None = None
    ) -> None:

        # Если конфиг не передан, инициализируем его дефолтными значениями
        if config is None:
            config = {
                "card_selector": "div.product-title",
                "price_keywords": ["price", "cost", "sum", "val", "price-block"],
                "code": ["code", "art", "articul", "sku", "number", "Арт"],
            }

        # Явно вызываем конструктор базового класса
        super().__init__(target_url, keyword, file_name, config)
