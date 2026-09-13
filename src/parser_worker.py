"""Модуль для фонового парсинга сайтов и автоматического анализа цен."""

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from PyQt6.QtCore import QThread, pyqtSignal


class Extractor:
    """
    Класс-конфигурация для парсинга.
    Хранит все селекторы и правила извлечения данных.
    Позволяет легко переключаться между логикой для разных сайтов.
    """

    def __init__(self, config: dict):
        """
        config: словарь с настройками для конкретного сайта.
        Пример структуры:
        {
            "card_selector": "div.product-card", селектор карточки товара;
            "separating_insert: "catalog/", стуктурный разделитель;
            "link_selector": "a.product-link", селектор ссылки на товар;
            "price_keywords": ["price", "cost"], ключи для поиска цены товара;
            "code_keywords": ["code", "art", "articul"], ключи для поиска актикула товара;
            "is_table_layout": False, определяет, является ли сайт таблицей;
            ...
        }
        """
        self.config = config

    def extract(self, soup, seen_hrefs, base_url):
        """Извлечение данных."""
        return  self._extract_from_citadel(soup, seen_hrefs, base_url)


    def _extract_from_citadel(self, soup, seen_hrefs, base_url):
        """Логика для сайтов с карточками товаров (Цитадель)."""
        items = []
        # Получаем селектор карточки из конфига, если нет - ищем все ссылки
        card_selector = self.config.get("card_selector", "div")
        cards = soup.select(card_selector)

        # Если селектор карточки слишком общий, ищем ссылки напрямую
        if card_selector == "div" and len(cards) > 100:
            cards = soup.find_all("a", href=True)

        for card in cards:
            # Находим ссылку внутри карточки
            link_tag = card.find("a", href=True)
            if not link_tag:
                continue

            href = link_tag["href"]
            if "/catalog/" not in href:
                continue

            full_link = urljoin(base_url, href)
            if full_link in seen_hrefs:
                continue

            # Извлекаем название
            name = link_tag.get("title", "").strip()
            if not name or len(name) < 5:
                continue

            # Извлекаем цену
            price = "Цена скрыта"
            price_keywords = self.config.get("price_keywords", ["price", "cost"])

            def price_class_filter(x, pk=tuple(price_keywords)):
                return x and any(k in str(x).lower() for k in pk)

            for el in card.find_all(class_=price_class_filter):
                txt = el.get_text(strip=True)
                if txt and re.search(r"\d", txt):
                    price = txt
                    break

            # Извлекаем артикул
            code = ""

            # Сначала определяем дефолтный кортеж
            default_code_keywords = ("code", "art", "articul", "sku")

            # Получаем список из конфига или используем дефолтный
            code_keywords: list[str] = self.config.get("code_keywords", default_code_keywords)

            # Используем лямбду с аргументом по умолчанию для фиксации значения (устраняет B023)
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
            seen_hrefs.add(full_link)

        return items

    def _extract_from_table(self, soup, seen_hrefs, base_url):
        """Логика для сайтов с табличным выводом (Гардарика)."""
        items = []
        tables = soup.find_all("table")

        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue

                # Предполагаем структуру: [Код] [Название] [Шт] [Купить]
                code_cell = cols
                name_cell = cols

                code = code_cell.get_text(strip=True)
                name = name_cell.get_text(strip=True)

                if not name:
                    continue

                # Ищем ссылку (может быть в названии или в кнопке "Купить")
                link_tag = name_cell.find("a", href=True)
                if not link_tag and len(cols) > 3:
                    buy_btn = cols.find("a", href=True)
                    link_tag = buy_btn

                if not link_tag:
                    continue

                href = link_tag["href"]
                full_link = urljoin(base_url, href)

                if full_link in seen_hrefs:
                    continue

                # Для Гардарики цены нет в открытом доступе
                items.append(
                    {
                        "name": name,
                        "code": code,
                        "price": "Цена по запросу (B2B)",
                        "availability": "Уточняйте у менеджера",
                        "link": full_link,
                    }
                )
                seen_hrefs.add(full_link)

        return items

class ParserWorker(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)
    logging_signal = pyqtSignal(str)

    def __init__(self, target_url: str, brand_keyword: str = ""):
        super().__init__()
        self.target_url = target_url.strip()
        self.brand_keyword = brand_keyword
        if not self.target_url.endswith("/"):
            self.target_url += "/"
        self.full_url = f"{self.target_url}catalog/?q={self.brand_keyword}"
        self.output_file = "result.json"

        # Настройка для парсинга сайта Цитадель
        parsing_config = {
            # Точный класс карточки товара, который мы нашли в HTML
            "card_selector": "div.product-title",
            # Ключевые слова для поиска цены (нужно авторизовываться).
            "price_keywords": ["price", "cost", "sum", "val", "price-block"],
            # Ключевые слова для поиска артикула
            "code_keywords": ["code", "art", "articul", "sku", "number", "Арт"],
            "is_table_layout": False,
        }

        self.extractor = Extractor(parsing_config)

    def run(self) -> None:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                page = browser.new_page()

                all_items = []
                seen_hrefs = set()
                current_page = 1
                max_pages = 25
                no_items_streak = 0

                while current_page <= max_pages:
                    # Формируем URL. Логика пагинации может отличаться.
                    url = self.full_url
                    if current_page != 1:
                        url = f"{self.full_url}&PAGEN_2={current_page}"

                    self.progress_signal.emit(f"📄 Страница №{current_page}: {url}")
                    page.goto(url, wait_until="networkidle", timeout=60000)

                    try:
                        # Универсальный селектор ожидания. Можно тоже вынести в конфиг экстрактора
                        page.wait_for_selector('a[href*="/catalog/"]', state="attached", timeout=30000)
                        page.wait_for_timeout(2000)
                    except PlaywrightTimeoutError:
                        self.progress_signal.emit("❌ Ссылки не появились. Завершаем цикл.")
                        break
                    except Exception as e:
                        self.logging_signal.emit(f"❌ Ошибка ожидания: {e}")
                        break

                    html = page.content()
                    soup = BeautifulSoup(html, "html.parser")


                    # ВЫЗОВ ЭКСТРАКТОРА
                    new_items = self.extractor.extract(soup, seen_hrefs, self.target_url)

                    all_items.extend(new_items)

                    if new_items:
                        self.progress_signal.emit(f"📦 На странице: {len(new_items)} | Всего: {len(all_items)}")
                        no_items_streak = 0
                    else:
                        no_items_streak += 1
                        if no_items_streak >= 2:
                            self.progress_signal.emit("🛑 Конец по условию - две страницы без товаров.")
                            break

                    current_page += 1

                browser.close()

                if all_items:
                    with open(self.output_file, "w", encoding="utf-8") as f:
                        json.dump(all_items, f, ensure_ascii=False, indent=2)
                    self.progress_signal.emit(f"🎉 Готово! Товаров: {len(all_items)}")
                    self.finished_signal.emit(self.output_file)
                else:
                    self.progress_signal.emit("⚠️ Товары не найдены.")
                    self.finished_signal.emit("")

        except Exception as e:
            self.logging_signal.emit(f"❌ Критическая ошибка: {e}")
            self.finished_signal.emit("")
