"""Класс парсинга для Сайта Гардарики (цельная выгрузка таблицы)."""

import logging
from typing import Any, Dict, Generator, List
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from src.my_exceptions.exceptions import ExceptionStopParser
from src.core.base_classes import BaseParser

logger = logging.getLogger(__name__)

PARSER_DESCRIPTION = (
    "-" * 85 + "\n"
    "Парсер добавляет товары в БД из поисковых ответов сайта.\n"
    "Введите ключевое слово, например: 'apecs' или 'петля'.\n"
    "Важно: Если сайт не нашел товаров по такому запросу, то и парсер их не добавит!\n"
    "Экспорт данных из базы доступен в формате .xlsx или .csv.\n"
)


class GardarikaParser(BaseParser):
    """Парсинг Сайта Гардарики (для страниц без пагинации и скролла)."""

    def __init__(self, config: BaseDBParsingConfig, extractor: BaseExtractor, manager: DatabaseManager):
        super().__init__(config, extractor, manager)
        self.description = PARSER_DESCRIPTION

        # Сохраняем сессию для Keep-Alive, единых заголовков и сохранения Cookies
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    def _build_url(self) -> str:
        """Строит URL для поискового запроса."""
        base_url = self.config.target_url.rstrip("/") + "/"
        params = {"q": self.config.keyword}

        # Сайт поддерживает кодировку 'cp1251'
        search_path = f"search/?{urlencode(params, encoding='cp1251')}"
        return urljoin(base_url, search_path)

    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """Возвращает всю таблицу данных одним чанком."""
        url = self._build_url()

        try:
            # Делаем один чистый запрос через сессию (timeout на всякий случай оставляем)
            response = self.session.get(url, timeout=15)

            if response.status_code != 200:
                raise RuntimeError(f"❌ Сайт вернул статус код: {response.status_code}")

            # Сайт Гардарики отдаёт контент в cp1251 (windows-1251).
            # apparent_encoding иногда ошибается, ломая парсинг lxml.
            # Передаём байты и from_encoding — BeautifulSoup сам декодирует,
            # заменяя невалидные последовательности, и lxml не падает.
            response.encoding = "cp1251"
            html_bytes = response.content

            soup = BeautifulSoup(html_bytes, "lxml", from_encoding="cp1251")
            new_items = self.extractor.extract_data(soup)

            if new_items:
                self.manager.save(new_items) # Записываем в БД
                yield new_items  # Отдаем пачку воркеру, который сам проверит флаг "Стоп"
            else:
                raise ExceptionStopParser("По вашему запросу ничего не найдено.")

        except ExceptionStopParser:
            raise
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"❌ Ошибка сети при запросе к {url}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"❌ Критическая ошибка парсинга страницы: {e}") from e
        finally:
            # Закрываем сессию при уничтожении или выходе из генератора
            if hasattr(self, "session") and self.session:
                self.session.close()
