"""Класс извлечения данных из контента сайта Гардарики."""

from typing import Any, Dict, List

from bs4 import BeautifulSoup

from exceptions import ExceptionStopParser
from parser_classes import BaseConfig, BaseExtractor


class GardarikaExtractor(BaseExtractor):  # ИСПРАВЛЕНО: Переименовано в GardarikiExtractor
    """Extractor для сайта Гардарики."""

    def __init__(self, config: BaseConfig) -> None:
        self.config = config

    def extract_data(self, raw_content: Any) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        # ПОЛИМОРФИЗМ: Проверяем, что к нам пришло — готовый объект BeautifulSoup или сырая строка
        if isinstance(raw_content, BeautifulSoup):
            soup = raw_content
        else:
            soup = BeautifulSoup(str(raw_content), "lxml")

        # Извлекаем первую попавшуюся таблицу с товарами
        table_products = soup.select_one(f"{self.config.config['table_selector']}")

        if not table_products:
            raise ExceptionStopParser("Таблица с товарами не найдена")

        # Шаг 1. Извлекаем все карточки товара
        cards = table_products.select(f"tbody {self.config.config.get('card_selector', 'tr')}")

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
            availability = img.get("title") if (img := tds[0].find("img")) else "Много"

            # Упаковка (колонка 4, index 3)
            packaging = tds[3].get_text(strip=True)

            # Ссылка (ищем внутри колонки с наименованием)
            url = link.get("href") if (link := tds[2].find("a")) else None

            # Шаг 4. Составляем словарь
            product_data = {
                "product_name": name,
                "product_code": code,
                "product_availability": availability,
                "product_packaging": packaging,
                "product_url": url
            }

            # Шаг 5. Добавляем в итоговый список
            items.append(product_data)

        return items
