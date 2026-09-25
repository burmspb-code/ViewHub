import logging
import re
from typing import Any, List, Dict
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class GoldenAppleExtractor(BaseExtractor):
    """Extractor для сайта Цитадель (адаптирован под Золотое Яблоко)."""

    def __init__(self, config: BaseConfig) -> None:
        self.config = config

    def extract_deep_data(self, html_content: str) -> Dict[str, str]:
        """
        Извлечение детальных характеристик (Описание, Применение, Страна) 
        из HTML-кода карточки товара (PDP).
        """
        detail_soup = BeautifulSoup(html_content, "html.parser")

        # Дефолтные значения на случай, если бренд не заполнил вкладки характеристик
        description = "Описание отсутствует"
        usage = "Не указано"
        country_of_origin = "Не указана"

        # 1. ОПИСАНИЕ ТОВАРA (Ищем по строгому атрибуту itemprop="description")
        desc_container = detail_soup.find("div", attrs={"itemprop": "description"})
        if desc_container:
            description = desc_container.get_text(separator=" ", strip=True)
            description = description.strip("\"'")

        # 2. ПРИМЕНЕНИЕ (Ищем по уникальному атрибуту text="Применение")
        usage_container = detail_soup.find("div", attrs={"text": "Применение"})
        if usage_container:
            usage_tag = usage_container.find("div", class_=lambda x: x and "_ga-pdp-wysiwyg" in x)
            if usage_tag:
                usage = usage_tag.get_text(separator=" ", strip=True).strip("\"'")

        # 3. СТРАНА ПРОИСХОЖДЕНИЯ (Ищем по уникальному атрибуту text="Информация и документы")
        info_container = detail_soup.find("div", attrs={"text": "Информация и документы"})
        if info_container:
            info_tag = info_container.find("div", class_=lambda x: x and "_ga-pdp-wysiwyg" in x)
            if info_tag:
                paragraphs = info_tag.find_all("p")
                for p_node in paragraphs:
                    p_text = p_node.get_text(separator=" ", strip=True)
                    if "страна происхождения" in p_text.lower():
                        country_raw = p_text.lower().replace("страна происхождения", "")
                        country_clean = (
                            country_raw.replace("*", "").replace(":", "").replace('"', "").replace("'", "").strip()
                        )
                        if country_clean:
                            country_of_origin = country_clean.capitalize()
                            break

        return {
            "description": description, 
            "usage": usage, 
            "country_of_origin": country_of_origin
        }

    def _parse_single_card(self, card_soup: BeautifulSoup, category_slug: str) -> Dict[str, Any] | None:
        """Внутренний приватный метод для разбора одной конкретной карточки листинга."""
        try:
            # 1. Извлечение ITEM_ID
            inner_div = card_soup.find("div", attrs={"data-scroll-id": True})
            item_id = inner_div["data-scroll-id"].strip() if inner_div else ""
            if not item_id:
                meta_sku = card_soup.find("meta", attrs={"itemprop": "sku"})
                item_id = meta_sku["content"].strip() if meta_sku else ""

            # Пропускаем рекламные баннеры в сетке
            if not item_id:
                return None

            # 2. Склейка URL товара
            a_tag = card_soup.find("a", href=True)
            href = a_tag["href"].strip() if a_tag else ""

            if href.startswith("http"):
                product_url = href
            else:
                # Убираем ведущий слеш из href, если он есть, чтобы не дублировать
                clean_href = href.lstrip("/")
                product_url = f"https://goldapple.ru{clean_href}" if clean_href else ""

            # 3. Извлечение БРЕНДА и НАЗВАНИЯ товара
            brand_tag = card_soup.find(class_=lambda x: x and "product-card-name__brand" in x)
            brand = brand_tag.text.strip() if brand_tag else "Не указан"

            name_tag = card_soup.find(class_=lambda x: x and "product-card-name__name" in x)
            name = name_tag.text.strip() if name_tag else "Без названия"

            # 4. Извлечение ТИПА ПРОДУКТА
            type_tag = card_soup.find("div", class_=lambda x: x and "product-card-vertical__type" in x)
            product_type = type_tag.text.strip() if type_tag else "Нет категории"

            # 5. Парсинг ЦЕН И СКИДКИ
            current_price_rub = 0
            old_price_rub = 0
            discount_text = "0%"

            all_prices = card_soup.find_all(class_=lambda x: x and "_ga-price" in x)
            for p_tag in all_prices:
                class_str = " ".join(p_tag.get("class", []))
                if "bnpl" in class_str:
                    continue

                digits = int(re.sub(r"\D", "", p_tag.text)) if re.sub(r"\D", "", p_tag.text) else 0
                if digits == 0:
                    continue

                if "old" in class_str or "discount" in class_str:
                    old_price_rub = digits
                else:
                    current_price_rub = digits

            if old_price_rub == 0:
                old_price_rub = current_price_rub

            if old_price_rub > current_price_rub and old_price_rub > 0:
                calc_discount = int(round((1 - (current_price_rub / old_price_rub)) * 100))
                discount_text = f"{calc_discount}%"

            # 6. Определение НАЛИЧИЯ товара
            in_stock = True
            status_tag = card_soup.find(
                class_=lambda x: x and ("_ga-pdp-status" in x or "_ga-pdp-product__status" in x)
            )
            if status_tag and ("нет в наличии" in status_tag.text.lower() or "ожидается" in status_tag.text.lower()):
                in_stock = False
            elif "нет в наличии" in card_soup.get_text(separator=" ").lower():
                in_stock = False

            # 7. Извлечение РЕЙТИНГА товара
            rating = "0.0"
            rating_div = card_soup.find("div", class_=lambda x: x and "product-rating__rating-value" in x)
            if rating_div:
                rating = rating_div.text.strip()
            else:
                meta_rating = card_soup.find("meta", attrs={"itemprop": "ratingValue"})
                if meta_rating and meta_rating.has_attr("content"):
                    rating = meta_rating["content"].strip()

            return {
                "category": category_slug,
                "item_id": item_id,
                "brand": brand,
                "name": name,
                "product_type": product_type,
                "old_price_rub": old_price_rub,
                "current_price_rub": current_price_rub,
                "discount": discount_text,
                "in_stock": in_stock,
                "rating": rating,
                "url": product_url,
            }
        except Exception as e:
            logger.error(f"❌ Ошибка разбора одиночной карточки: {e}")
            return None

    def extract_data(self, product_cards: List[Any]) -> List[Dict[str, Any]]:
        """
        Пакетный метод. Принимает список всех карточек страницы,
        запускает внутренний цикл и возвращает готовый массив базовых данных.
        """
        # Динамически вырезаем категорию из целевого URL в конфиге для словаря
        # (Например, из "https://goldapple.ru/parfjumerija" получим "parfjumerija")
        category_slug = "Каталог"
        if hasattr(self.config, 'target_url') and self.config.target_url:
            category_slug = self.config.target_url.replace("https://goldapple.ru", "").strip("/")

        page_batch = []
        for card in product_cards:
            base_data = self._parse_single_card(card, category_slug)
            if base_data:
                page_batch.append(base_data)
                
        return page_batch