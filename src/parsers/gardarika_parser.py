"""Класс парсинга для Сайта Гардарики."""

import requests

from typing import Any, Dict, Generator, List
from urllib.parse import urljoin, urlencode
from bs4 import BeautifulSoup
from parser_classes import BaseParser


class GardarikaParser(BaseParser):
    """Парсинг Сайта Гардарики."""

    def _build_url(self) -> str:
        """Строит URL для указанной страницы."""

        base_url = self.setup.target.rstrip("/") + "/"

        # Формируем параметры запроса. Ключ 'q' — это то, что сайт ждет в поиске
        params = {"q": self.setup.keyword}

        # Создаем поисковый хвост вида: '?q=%D0%B7%D0%B0%D0%BC%D0%BE%D0%BA+apecs'
        search_path = f"search/?{urlencode(params)}"

        # Безопасно склеиваем базовый URL и путь поиска
        full_search_url = urljoin(base_url, search_path)

        return full_search_url

    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """Возвращает страницу поиска с таблицей данных."""

        url = self._build_url()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            new_items = self.extractor.extract_data(soup)
            yield new_items

        except requests.exceptions.RequestException as e:
            # Перехватываем именно сетевые ошибки для детального логирования
            raise RuntimeError(f"❌ Ошибка сети при запросе к {url}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"❌ Критическая ошибка парсинга страницы: {e}") from e
