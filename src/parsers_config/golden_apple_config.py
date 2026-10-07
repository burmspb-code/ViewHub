"""Конфигурация для парсинга интернет-магазина Золотое Яблоко."""

from typing import Dict, ClassVar
from src.core.base_classes import BaseDBParsingConfig


class GoldenAppleConfig(BaseDBParsingConfig):
    """
    Конфигурация для парсинга интернет-магазина Золотое Яблоко.
    Формат схемы: колонки описываются в нативном SQL-формате для SQLite.
    """

    # Схема бизнес-колонок: имя -> SQL-тип для SQLite
    BUSINESS_COLUMNS: ClassVar[Dict[str, str]] = {
        "item_id": "TEXT NOT NULL",  # Идентификатор товара (без UNIQUE, его добавит PRIMARY KEY)
        "category": "TEXT",
        "brand": "TEXT",
        "name": "TEXT NOT NULL",
        "product_type": "TEXT",
        "old_price_rub": "REAL",
        "current_price_rub": "REAL",
        "discount": "REAL",
        "in_stock": "INTEGER DEFAULT 0",  # В SQLite булевы значения хранятся как INTEGER (0 или 1)
        "rating": "REAL",
        "url": "TEXT",
        "catalog_page_url": "TEXT",
        "description": "TEXT",
        "usage": "TEXT",
        "country_of_origin": "TEXT",
        "page_number": "INTEGER",
    }

    # Ключ, по которому сейвер будет делать ON CONFLICT (UPSERT)
    DEDUP_COLUMN: str = "item_id"

    # =====================================================================
    # Настройки браузера — ТОЛЬКО для парсера Золотого Яблока.
    #
    # Эти параметры не имеют отношения к CitadelParser и GardarikaParser:
    # подмена User-Agent и отключение WebGL выведены из эксперимента именно
    # на этом сайте. Поэтому объявлены здесь, в конфигурации парсера, а не
    # как общие настройки приложения.
    # =====================================================================

    # Имя папки с упакованным браузером внутри сборки.
    #
    # Объявлено здесь, а не в src/core/paths.py: браузер нужен не всем
    # парсерам — например, работающим через API он не требуется вовсе.
    # Должно совпадать с BROWSERS_DEST в viewhub.spec.
    BROWSERS_DIR_NAME: ClassVar[str] = "pw-browsers"

    # Режим отрисовки по умолчанию. True — браузер без отрисовки страниц.
    # Требует подмены HEADLESS_USER_AGENT и добавления --disable-gpu.
    DEFAULT_HEADLESS: ClassVar[bool] = True

    # Имя переменной окружения для переключения режима отрисовки.
    # Это единственная переменная окружения парсера: она нужна, чтобы
    # заказчик мог переключить режим на конкретной машине, не пересобирая
    # программу. Все остальные настройки задаются только константами.
    HEADLESS_ENV_VAR: ClassVar[str] = "GOLDAPPLE_HEADLESS"

    # User-Agent для режима без отрисовки.
    #
    # ВАЖНО: подмена обязательна. С настоящей версией браузера (Chrome/153)
    # сайт отвечает отказом и парсер не может собрать каталог. Экспериментом
    # установлено, что именно эта версия проходит проверку. Не «исправлять».
    HEADLESS_USER_AGENT: ClassVar[str] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko)"
        " Chrome/124.0.0.0 Safari/537.36"
    )

    # Требуется ли отключение GPU в режиме без отрисовки.
    # Без этого флага включается программный рендеринг, который сайт отвергает.
    HEADLESS_DISABLE_GPU: ClassVar[bool] = True

    @classmethod
    def get_full_schema(cls) -> Dict[str, str]:
        """Схема ВСЕХ колонок таблицы: системные + специфичные для сайта."""
        return {**cls.SYSTEM_COLUMNS, **cls.BUSINESS_COLUMNS}
