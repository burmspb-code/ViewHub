"""Класс парсинга для Сайта Гардарики (цельная выгрузка таблицы)."""

from typing import Any, Dict, Generator, List
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from exceptions import ExceptionStopParser
from parser_classes import BaseParser


class GardarikaParser(BaseParser):
    """Парсинг Сайта Гардарики (для страниц без пагинации и скролла)."""

    def _build_url(self) -> str:
        """Строит URL для поискового запроса."""
        base_url = self.setup.target.rstrip("/") + "/"
        params = {"q": self.setup.keyword}

        # Создаем поисковый хвост вида: 'search/?q=замок+apecs'
        # Сайт поддерживает кодировку 'cp1251'
        search_path = f"search/?{urlencode(params, encoding='cp1251')}"

        # Безопасно склеиваем базовый URL и путь поиска
        full_search_url = urljoin(base_url, search_path)
        return full_search_url

    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """Возвращает всю таблицу данных одним чанком."""

        # Если пользователь нажал Стоп еще до начала запроса
        if not self._is_running:
            return

        url = self._build_url()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        try:
            # Делаем один запрос, так как Битрикс отдает таблицу целиком
            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code != 200:
                raise RuntimeError(f"❌ Сайт вернул статус код: {response.status_code}")

            soup = BeautifulSoup(response.text, "lxml")

            # Извлекаем данные (передаем объект soup в ваш GardarikiExtractor)
            new_items = self.extractor.extract_data(soup)

            if new_items:
                yield new_items  # Отдаем всю пачку товаров за один раз
            else:
                raise ExceptionStopParser("По вашему запросу ничего не найдено.")

        except ExceptionStopParser:
            # Пробрасываем ваше кастомное исключение наверх без изменений
            raise
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"❌ Ошибка сети при запросе к {url}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"❌ Критическая ошибка парсинга страницы: {e}") from e
