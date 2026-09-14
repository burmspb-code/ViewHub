"""Связующая логика для работы парсинга."""

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Generator, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from openpyxl import Workbook, load_workbook
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from exceptions import ExceptionStopParser
from parser_classes import BaseConfig, BaseExtractor, BaseParser, BaseSaver


class CSVSaver(BaseSaver):
    """
    Дочерний класс записи данных парсинга в формате CSV.
    Поддерживает инкрементальную дозапись порций (чанков) данных на лету.
    """

    def initialize(self, file_name: str) -> None:
        """Очищает файл перед стартом."""
        file_path = Path.cwd() / file_name
        file_path = file_path.with_suffix(".csv")
        # Просто перезаписываем файл пустым
        with open(file_path, mode="w", encoding="utf-8-sig"):
            pass

    def save(self, data: List[Dict[str, Any]], file_name: str) -> bool:
        """
        Принимает порцию данных и дозаписывает её в файл.
        Автоматически создает заголовки при первом вызове.
        """
        if not data:
            return False

        # Формируем полный путь к файлу с расширением .csv
        file_path = Path.cwd() / file_name
        file_path = file_path.with_suffix(".csv")

        # Проверяем, существует ли файл до открытия (чтобы понять, нужен ли заголовок)
        file_exists = file_path.exists()

        # Берем заголовки из ключей первого словаря в текущей порции
        fieldnames = list(data[0].keys())

        try:
            # Открываем в режиме 'a' (append) для добавления данных, а не перезаписи
            with open(file_path, mode="a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                # Пишем заголовки только если файл создается впервые
                if not file_exists:
                    writer.writeheader()

                # Записываем текущую порцию данных
                writer.writerows(data)
                return True

        except Exception as e:
            raise IOError(f"Ошибка записи файла {file_path.name}\n{e}") from e


class JSONSaver(BaseSaver):
    """Сейвер для формата JSON."""

    def initialize(self, file_name: str) -> None:
        """Создает пустой массив в файле перед стартом."""
        file_path = Path.cwd() / file_name
        file_path = file_path.with_suffix(".json")
        with open(file_path, mode="w", encoding="utf-8") as f:
            json.dump([], f)

    def save(self, data: List[Dict[str, Any]], file_name: str) -> bool:
        if not data:
            return False
        file_path = (Path.cwd() / file_name).with_suffix(".json")

        try:
            # Читаем старые данные, если файл существует
            existing_data = []
            if file_path.exists() and file_path.stat().st_size > 0:
                with open(file_path, mode="r", encoding="utf-8") as f:
                    try:
                        existing_data = json.load(f)
                    except json.JSONDecodeError:
                        existing_data = []

            # Объединяем и перезаписываем файл целиком
            existing_data.extend(data)
            with open(file_path, mode="w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            raise IOError(f"Ошибка записи JSON:\n{e}") from e


class XLSXSaver(BaseSaver):
    """Сейвер для формата Excel (XLSX)."""

    def initialize(self, file_name: str) -> None:
        """Создает чистую книгу Excel с заголовками при старте не требуется,
        так как мы можем просто пересоздать файл."""
        file_path = Path.cwd() / file_name
        file_path = file_path.with_suffix(".xlsx")
        # Удаляем старый файл, если он был
        if file_path.exists():
            file_path.unlink()

    def save(self, data: List[Dict[str, Any]], file_name: str) -> bool:
        if not data:
            return False
        file_path = (Path.cwd() / file_name).with_suffix(".xlsx")
        fieldnames = list(data[0].keys())

        try:
            if not file_path.exists():
                wb = Workbook()
                ws = wb.active
                ws.title = "Parsing Result"
                ws.append(fieldnames)  # Пишем шапку
            else:
                wb = load_workbook(file_path)
                ws = wb.active

            # Дописываем строки чанка
            for item in data:
                ws.append([item.get(key, "") for key in fieldnames])

            wb.save(file_path)
            wb.close()
            return True
        except Exception as e:
            raise IOError(f"Ошибка записи XLSX:\n{e}") from e


class CitadelConfig(BaseConfig):
    """Класс конфигурации для парсинга."""

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


class CitadelExtractor(BaseExtractor):
    """Класс извлечения данных из контента сайта Цитадель."""

    def __init__(self, config: BaseConfig) -> None:
        self.setup = config
        # Храним посещенные ссылки на уровне экземпляра экстрактора,
        # чтобы избегать дубликатов между разными страницами одного процесса
        self.seen_hrefs: set[str] = set()

    def clear_seen(self) -> None:
        """Сброс кэша дубликатов при необходимости."""
        self.seen_hrefs.clear()

    def extract_data(self, raw_content: Any) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        # 1. Инициализируем BeautifulSoup из сырого HTML-контента
        soup = BeautifulSoup(raw_content, "lxml")

        # Базовый URL для сборки полных ссылок
        base_url = self.setup.target

        # Получаем селектор карточки из конфига, если нет - ищем div
        card_selector = self.setup.config.get("card_selector", "div")
        cards = soup.select(card_selector)

        # Если селектор карточки слишком общий, ищем ссылки напрямую
        if card_selector == "div" and len(cards) > 100:
            cards = soup.find_all("a", href=True)

        for card in cards:
            # 2. Безопасное извлечение тега ссылки (учитываем, что card сам может быть тегом 'a')
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
            # ИСПРАВЛЕНО: обращение через self.setup.config вместо self.config
            price_keywords = self.setup.config.get("price_keywords", ["price", "cost"])

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
            # ИСПРАВЛЕНО: приведение дефолта к общему типу (tuple)
            code_keywords = self.setup.config.get("code", default_code_keywords)

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


class CitadelParser(BaseParser):
    """Класс парсинга для Сайта Цитадель."""

    def _build_url(self, page: int = 1) -> str:
        """Строит URL для указанной страницы."""
        # ИСПРАВЛЕНО: target_url изменен на target в соответствии с BaseConfig
        base_url = self.setup.target.rstrip("/") + "/"
        url = f"{base_url}catalog/?q={self.setup.keyword}"
        if page > 1:
            url += f"&PAGEN_2={page}"
        return url

    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """Пошагово возвращает списки словарей с данными (постранично)."""
        current_page = 1
        max_pages = 50
        no_items_streak = 0

        # ИСПРАВЛЕНО: Инициализация Playwright внутри метода парсинга
        with sync_playwright() as p:
            # Запускаем браузер в фоновом (headless) режиме
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            while current_page <= max_pages:
                # Обязательная проверка флага остановки из интерфейса
                if not self._is_running:
                    break

                url = self._build_url(current_page)

                try:
                    # Переход по URL
                    page.goto(url, wait_until="networkidle", timeout=60000)

                    # Ожидание появления карточек товара
                    page.wait_for_selector('a[href*="/catalog/"]', state="attached", timeout=30000)
                    page.wait_for_timeout(2000)

                except PlaywrightTimeoutError as e:
                    # Если это первая страница — падаем, если последующие — возможно, каталог кончился
                    if current_page == 1:
                        raise RuntimeError(f"❌ Ссылки не появились на первой странице: {e}") from e
                    break
                except Exception as e:
                    raise RuntimeError(f"❌ Ошибка навигации на странице {current_page}: {e}") from e

                # Извлекаем данные из HTML текущей страницы
                html_content = page.content()
                new_items = self.extractor.extract_data(html_content)

                # Обработка пустых страниц (streak)
                if new_items:
                    no_items_streak = 0
                    # ИСПРАВЛЕНО: Возвращаем ТОЛЬКО новые элементы текущей страницы
                    yield new_items
                else:
                    no_items_streak += 1
                    if no_items_streak >= 2:
                        raise ExceptionStopParser("Превышен лимит пустых страниц.")

                current_page += 1

            # Чистим ресурсы
            context.close()
            browser.close()
