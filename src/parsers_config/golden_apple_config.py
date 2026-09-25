"""Конфигрурация для парсинга сайта Цитадель."""

from typing import Any, Dict
from parser_classes import BaseConfig


class GoldenAppleConfig(BaseConfig):
    """
    Конфигурация для парсинга интернет-магазина Золотое Яблоко.
    Управляет базовыми ссылками, категориями и именами файлов для PyQt6-воркера.
    """

    def __init__(
        self, target_url: str, keyword: str = "", file_name: str = "", config: Dict[str, Any] | None = None
    ) -> None:
        """
        Инициализация параметров конфигурации.

        :param target_url: Базовый URL сайта (например, 'https://goldapple.ru')
        :param keyword: Раздел/slug категории (например, 'parfjumerija/dlja-detej')
        :param file_name: Название файла для сохранения результата чанками
        :param config: Словарь дополнительных параметров (пока не используется, передаем пустым)
        """
        # Если словарь дополнительных настроек не передан, оставляем его пустым
        if config is None:
            config = {}

        # Явно передаем параметры в конструктор родительского класса BaseConfig
        super().__init__(target_url, keyword, file_name, config)