import pytest

from pathlib import Path
from PyQt6.QtGui import QIcon

from src.core.resources import load_app_icon

@pytest.mark.usefixtures("qapp")
def test_load_app_icon_success(monkeypatch, caplog):
    """Проверяет успешную загрузку иконки, если файл существует на диске."""
    caplog.set_level("INFO")

    monkeypatch.setattr(Path, "exists", lambda self: True)

    icon = load_app_icon()

    assert isinstance(icon, QIcon)
    # Проверяем, что в caplog.text попала нужная строка
    assert "Файл иконки успешно найден и загружен." in caplog.text

@pytest.mark.usefixtures("qapp")
def test_load_app_icon_not_found(monkeypatch, caplog):
    """Проверяет поведение функции, если файл иконки отсутствует на диске."""
    # 1. Заставляем caplog ловить сообщения уровня WARNING
    caplog.set_level("WARNING")

    # 2. Имитируем, что файла на диске нет
    monkeypatch.setattr(Path, "exists", lambda self: False)

    # 3. Вызываем функцию
    icon = load_app_icon()

    # 4. Проверяем защитную логику (должен вернуться пустой QIcon)
    assert isinstance(icon, QIcon)
    assert icon.isNull() is True  # isNull() вернет True, если иконка пустая

    # 5. Проверяем логи предупреждения
    assert "Файл иконки не найден по пути:" in caplog.text
    assert "Будет использована системная иконка по умолчанию." in caplog.text
