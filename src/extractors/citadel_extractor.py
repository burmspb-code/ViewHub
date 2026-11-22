"""Класс извлечения данных из контента сайта Цитадель."""

import json
import logging
import re

from typing import Any, Dict, Iterator, List
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.core.base_classes import BaseExtractor, BaseDBParsingConfig

logger = logging.getLogger(__name__)

# Статусы, которые сайт показывает в карточке товара.
AVAILABILITY_MAP = {
    # Более конкретные статусы идут первыми: "нет в наличии" содержит "в наличии".
    "нет в наличии": "Нет в наличии",
    "ожидается поставка": "Ожидается поставка",
    "в наличии": "В наличии",
    "много": "Много",
    "под заказ": "Под заказ",
    "в пути": "В пути",
}

# Подписи-заглушки, которые сайт показывает вместо настоящего бренда в выдаче.
BRAND_PLACEHOLDERS = {"бренд", "brand", "-", "—", "/", ""}

# Префикс подписи артикула: на сайте встречается и "Арт:", и "Арт.:".
ARTICLE_PREFIX_RE = re.compile(r"^\s*(?:артикул|арт\.?)\s*[:：-]?\s*", re.IGNORECASE)


def _iter_jsonld_objects(data: Any) -> Iterator[Dict[str, Any]]:
    """Рекурсивно проходит JSON-LD, включая конструкцию @graph."""
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _iter_jsonld_objects(value)
    elif isinstance(data, list):
        for value in data:
            yield from _iter_jsonld_objects(value)


class CitadelExtractor(BaseExtractor):
    """Extractor для сайта Цитадель."""

    def __init__(self, config: BaseDBParsingConfig) -> None:
        self.config = config
        # Храним посещённые ссылки на уровне экземпляра экстрактора,
        # чтобы избегать дубликатов между разными страницами одного процесса.
        self.seen_hrefs: set[str] = set()

    def clear_seen(self) -> None:
        """Сброс кэша дубликатов при необходимости."""
        self.seen_hrefs.clear()

    @staticmethod
    def _normalize(text: str) -> str:
        """Сжимает пробелы в одну строку."""
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _parse_availability(text: str) -> str:
        """Приводит статус наличия сайта к читаемому значению."""
        normalized = CitadelExtractor._normalize(text).lower()
        if not normalized:
            return "Неизвестно"
        for key, value in AVAILABILITY_MAP.items():
            if key in normalized:
                return value
        return normalized.capitalize()

    @staticmethod
    def _parse_price(card: Any) -> float | None:
        """Достаёт цену, если сайт её показывает (обычно скрыта до авторизации)."""
        for element in card.find_all(class_=True):
            classes = " ".join(str(c) for c in element.get("class", [])).lower()
            if "price" not in classes:
                continue
            text = element.get_text(" ", strip=True)
            match = re.search(r"\d[\d\s.,]*", text)
            if match:
                raw = match.group(0).replace(" ", "").replace(",", ".")
                try:
                    return float(raw)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _item_id_from_url(url: str) -> str:
        """Использует последний сегмент URL в качестве идентификатора товара."""
        parts = [part for part in urlparse(url).path.split("/") if part]
        return parts[-1] if parts else url

    @staticmethod
    def _parse_code(soup: BeautifulSoup) -> str:
        """
        Достаёт код товара (артикул) со страницы товара.

        В выдаче поле пустое. На странице товара значение лежит в #number-field,
        но сайт может отдать и подпись целиком («Арт.: 24043») — префикс убираем.
        """
        for selector in ("#number-field", ".number-copy", ".number", ".product-brand-part"):
            element = soup.select_one(selector)
            if element is None:
                continue
            text = ARTICLE_PREFIX_RE.sub("", element.get_text(" ", strip=True))
            text = text.strip(" \t\r\n:-")
            if text:
                return text
        return ""

    @staticmethod
    def _parse_brand(soup: BeautifulSoup) -> str:
        """
        Достаёт настоящий бренд со страницы товара.

        Надёжный источник — JSON-LD объекта Product. В выдаче сайт показывает
        подпись «Бренд», поэтому такие заглушки отфильтровываются.
        """
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.get_text(strip=True))
            except (json.JSONDecodeError, TypeError):
                continue

            for obj in _iter_jsonld_objects(data):
                if not isinstance(obj, dict):
                    continue
                if "Product" not in str(obj.get("@type", "")):
                    continue
                brand = obj.get("brand")
                if isinstance(brand, dict):
                    brand = brand.get("name", "")
                if not isinstance(brand, str):
                    continue
                value = CitadelExtractor._normalize(brand)
                if value.lower() not in BRAND_PLACEHOLDERS:
                    return value

        # Резервный путь для авторизованной выдачи, где бренд реально выведен в DOM.
        for selector in (".product-brand-info .title", ".product-brand-info img[title]"):
            element = soup.select_one(selector)
            if element is None:
                continue
            value = CitadelExtractor._normalize(
                str(element.get("title") or element.get("alt") or element.get_text(" ", strip=True))
            )
            if value.lower() not in BRAND_PLACEHOLDERS:
                return value

        return ""

    def extract_detail_data(self, raw_content: Any) -> Dict[str, str]:
        """Извлекает поля, доступные только на странице отдельного товара."""
        soup = raw_content if isinstance(raw_content, BeautifulSoup) else BeautifulSoup(str(raw_content), "lxml")
        return {
            "code": self._parse_code(soup),
            "brand": self._parse_brand(soup),
        }

    def extract_data(self, raw_content: Any) -> List[Dict[str, Any]]:
        """Извлекает карточки товаров из HTML страницы каталога."""
        soup = raw_content if isinstance(raw_content, BeautifulSoup) else BeautifulSoup(str(raw_content), "lxml")

        # Реальный селектор карточки выдачи Citadel: .product-card.
        # Fallback на все ссылки недопустим: туда попадают категории каталога.
        cards = soup.select(".product-card")
        if not cards:
            return []

        items: List[Dict[str, Any]] = []
        for card in cards:
            title_link = card.select_one(".product-title a[href]")
            if title_link is None:
                continue

            href = str(title_link.get("href", "")).strip()
            if not href:
                continue

            full_link = urljoin(self.config.target_url, href)
            if full_link in self.seen_hrefs:
                continue

            name = self._normalize(str(title_link.get("title") or title_link.get_text(" ", strip=True)))
            if len(name) < 5:
                continue

            availability_element = card.select_one(".available-block")
            description_element = card.select_one(".product-card-info .text")

            # Ключи строго совпадают с CitadelConfig.BUSINESS_COLUMNS:
            # сейвер берёт значения из словаря именно по этим именам.
            # code и brand обогащаются отдельным проходом по карточке товара.
            items.append(
                {
                    "item_id": self._item_id_from_url(full_link),
                    "name": name,
                    "url": full_link,
                    "code": "",
                    "brand": self._parse_brand(card),
                    "availability": self._parse_availability(
                        availability_element.get_text(" ", strip=True) if availability_element else ""
                    ),
                    "description": self._normalize(description_element.get_text(" ", strip=True))
                    if description_element
                    else "",
                    "current_price": self._parse_price(card),
                }
            )
            self.seen_hrefs.add(full_link)

        return items
