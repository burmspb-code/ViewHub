"""Тест дедупликации: проверка ключей и схемы под новый формат конфигов."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parsers_config.golden_apple_config import GoldenAppleConfig


def test_key_and_schema():
    #config = BaseConfig("url", "key", "file")
    config = GoldenAppleConfig("https://goldapple.ru", "духи", "test")

    schema = config.get_full_schema()
    assert isinstance(schema, dict), f"Схема не dict: {type(schema).__name__}"

    key_column = config.get_key_column()
    assert isinstance(key_column, str), f"Ключ не строка: {type(key_column).__name__}"
    assert key_column == "id", f"Ожидался item_id, получен: {key_column}"

    print(f"Технический ключ (PK): {key_column}")
    print(f"Тип PK: {type(key_column).__name__}")
    print(f"Полная схема колонок: {list(schema.keys())}")
    print("Тест пройден ✅")


if __name__ == "__main__":
    test_key_and_schema()
