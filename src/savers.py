"""Модуль содержит классы для сохранения данных парсинга в различных форматах,
 а также классы конфигурации, извлечения и парсинга под кокретные целевые запросы."""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from openpyxl import Workbook, load_workbook

from parser_classes import BaseSaver


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
