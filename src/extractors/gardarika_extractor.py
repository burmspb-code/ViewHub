"""Класс извлечения данных из контента сайта Гардарики."""

import logging
import re

from typing import Any, Dict, List
from bs4 import BeautifulSoup

from src.my_exceptions.exceptions import ExceptionStopParser
from src.core.base_classes import BaseExtractor, BaseDBParsingConfig

logger = logging.getLogger(__name__)


class GardarikaExtractor(BaseExtractor):  # Переименовано в GardarikiExtractor
    """Extractor для сайта Гардарики."""

    def __init__(self, config: BaseDBParsingConfig) -> None:
        self.config = config

    def _parse_availability(self, text: str) -> int:
        """Преобразует строку наличия в 1/0."""
        text_lower = text.lower()
        # Наличие если написано "Много", "В наличии", есть картинка с title "В наличии" и т.д.
        if any(kw in text_lower for kw in ("много", "в наличии", "есть", "available", "in stock")):
            return 1
        return 0

    def _parse_price(self, text: str) -> float:
        """Извлекает числовую цену из строки."""
        # Удаляем всё кроме цифр, точки и запятой
        cleaned = re.sub(r"[^\d.,]", "", text)
        # Заменяем запятую на точку
        cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def extract_data(self, raw_content: Any) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        # ПОЛИМОРФИЗМ: Проверяем, что к нам пришло — готовый объект BeautifulSoup или сырая строка
        if isinstance(raw_content, BeautifulSoup):
            soup = raw_content
        else:
            soup = BeautifulSoup(str(raw_content), "lxml")

        # Извлекаем таблицу с товарами по слектору класса: products-table
        table_products = soup.select_one(".products-table")

        if not table_products:
            raise ExceptionStopParser("Таблица с товарами не найдена")

        # Шаг 1. Извлекаем все карточки товара по сектору - tr
        cards = table_products.select("table > tbody > tr")

        if not cards:
            raise ExceptionStopParser("Карточки отсутствуют в таблице")

        # Шаг 2. Находим карточки товара по условию — наличие пяти полей в карточке согласно верстке сайта
        # :scope - использует селектор дочерних элементов
        products_card = [card for card in cards if len(card.select(":scope > td")) == 5]

        if not products_card:
            raise ExceptionStopParser("Карточки с товарами не найдены")

        # Шаг 3. Считываем информационные поля из карточки
        for card in products_card:
            tds = card.select(":scope > td")

            # Наименование (колонка 3, индекс 2)
            name = tds[2].get_text(strip=True)

            # Код (колонка 2, index 1)
            code = tds[1].get_text(strip=True)

            # Наличие (колонка 1, index 0)
            img = tds[0].find("img")
            availability_text = img.get("title") if img else tds[0].get_text(strip=True)
            in_stock = self._parse_availability(availability_text)

            # Упаковка (колонка 4, index 3)
            packaging = tds[3].get_text(strip=True)

            # Цена (колонка 5, index 4)
            price_text = tds[4].get_text(strip=True)
            current_price = self._parse_price(price_text)

            # Ссылка (ищем внутри колонки с наименованием) + добавляем префикс для сайта Гардарики
            url_prefix = self.config.target_url.rstrip("/") if hasattr(self.config, "target_url") else ""
            url = url_prefix + link.get("href") if (link := tds[2].find("a")) else None

            # Шаг 4. Составляем словарь
            product_data = {
                "name": name,
                "item_id": code,
                "in_stock": in_stock,
                "package": packaging,
                "current_price": current_price,
                "url": url,
                "description": "",  # В таблице нет описания, оставляем пустым
            }

            # Шаг 5. Добавляем в итоговый список
            items.append(product_data)

        return items
