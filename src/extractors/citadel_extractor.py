"""Класс извлечения данных из контента сайта Цитадель."""

import re
from typing import Any, Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from parser_classes import BaseConfig, BaseExtractor


class CitadelExtractor(BaseExtractor):
    """Extractor для сайта Цитадель."""

    def __init__(self, config: BaseConfig) -> None:
        self.config = config
        # Храним посещенные ссылки на уровне экземпляра экстрактора,
        # чтобы избегать дубликатов между разными страницами одного процесса
        self.seen_hrefs: set[str] = set()

    def clear_seen(self) -> None:
        """Сброс кэша дубликатов при необходимости."""
        self.seen_hrefs.clear()

    def extract_data(self, raw_content: Any) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        # Инициализируем BeautifulSoup из сырого HTML-контента
        soup = BeautifulSoup(raw_content, "lxml")

        # Базовый URL для сборки полных ссылок
        base_url = self.config.target_url

        # Получаем селектор карточки из конфига, если нет - ищем div
        card_selector = self.config.config.get("card_selector", "div")
        cards = soup.select(card_selector)

        # Если селектор карточки слишком общий, ищем ссылки напрямую
        if card_selector == "div" and len(cards) > 100:
            cards = soup.find_all("a", href=True)

        for card in cards:
            # Безопасное извлечение тега ссылки (учитываем, что card сам может быть тегом 'a')
            if card.name == "a" and card.has_attr("href"):
                link_tag = card
            else:
                link_tag = card.find("a", href=True)

            if not link_tag:
                continue

            href = link_tag["href"]
            if "/catalog/" not in href:
                continue

            full_link = urljoin(base_url, href)
            if full_link in self.seen_hrefs:
                continue

            # Извлекаем название
            name = link_tag.get("title", "").strip()
            # Если в title пусто, пробуем забрать текст самой ссылки
            if not name:
                name = link_tag.get_text(strip=True)

            if not name or len(name) < 5:
                continue

            # Извлекаем цену
            price = "Цена скрыта"
            price_keywords = self.config.config.get("price_keywords", ["price", "cost"])

            def price_class_filter(x, pk=tuple(price_keywords)):
                return x and any(k in str(x).lower() for k in pk)

            for el in card.find_all(class_=price_class_filter):
                txt = el.get_text(strip=True)
                if txt and re.search(r"\d", txt):
                    price = txt
                    break

            # Извлекаем артикул
            code = ""
            default_code_keywords = ("code", "art", "articul", "sku")
            code_keywords = self.config.config.get("code", default_code_keywords)

            # Лямбда с аргументом по умолчанию (защита от B023)
            code_el = card.find(class_=lambda x, ck=tuple(code_keywords): x and any(c in str(x).lower() for c in ck))

            if code_el:
                code = re.sub(
                    r"^(Арт\.|Код|Артикул):\s*", "", code_el.get_text(strip=True), flags=re.IGNORECASE
                ).strip()

            # Извлекаем наличие
            availability = "Неизвестно"
            card_text = card.get_text(separator=" ", strip=True).lower()
            status_map = {
                "под заказ": "Под заказ",
                "в наличии": "В наличии",
                "в пути": "В пути",
                "нет в наличии": "Нет в наличии",
            }
            for key, val in status_map.items():
                if key in card_text:
                    availability = val
                    break

            items.append(
                {
                    "name": name,
                    "code": code,
                    "price": price,
                    "availability": availability,
                    "link": full_link,
                }
            )
            self.seen_hrefs.add(full_link)

        return items
