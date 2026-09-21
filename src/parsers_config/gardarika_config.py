"""Конфигурация для парсинга сайта Гардарики."""

from typing import Any, Dict

from parser_classes import BaseConfig


class GardarikaConfig(BaseConfig):
    """Конфиг для сайта Гардарики."""

    def __init__(
        self, target_url: str, keyword: str = "", file_name: str = "", config: Dict[str, Any] | None = None
    ) -> None:

        # Если конфиг не передан, инициализируем его дефолтными значениями для Гардариков
        if config is None:
            config = {
                "table_selector": "div.products-table",  # Селектор таблицы с товарами
                "card_selector": "tr",                   # Селектор карточки (строки таблицы)

                # Исправлено на "code_keywords" для точной стыковки с вашим Extractor-ом
                "code_keywords": ["alt", "art", "articul", "sku", "number", "Арт"],

                "name": "_blank",                        # Поле наименования товара
                "product_link": "link",                  # Селектор ссылки на товар
                "quantity_package": "quantity",          # Поле количества в упаковке
                "price_keywords": ["price", "cost", "цена", "стоимость"], # Ключевые слова для поиска цены
            }

        # Явно вызываем конструктор базового класса
        super().__init__(target_url, keyword, file_name, config)
