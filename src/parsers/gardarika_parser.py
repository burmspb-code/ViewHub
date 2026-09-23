"""Класс парсинга для Сайта Гардарики (цельная выгрузка таблицы)."""

import logging
from typing import Any, Dict, Generator, List
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from exceptions import ExceptionStopParser
from parser_classes import BaseParser

logger = logging.getLogger(__name__)


class GardarikaParser(BaseParser):
    """Парсинг Сайта Гардарики (для страниц без пагинации и скролла)."""

    def __init__(self, *args, **kwargs):
        """Инициализация парсера с поддержкой сетевой сессии."""
        super().__init__(*args, **kwargs)
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

            # Автоматически чиним кодировку для правильного отображения кириллицы
            response.encoding = response.apparent_encoding

            soup = BeautifulSoup(response.text, "lxml")
            new_items = self.extractor.extract_data(soup)

            if new_items:
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
