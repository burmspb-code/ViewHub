"""Модуль содержит классы для сохранения данных парсинга в различных форматах,
 а также классы конфигурации, извлечения и парсинга под кокретные целевые запросы."""

import csv
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

from openpyxl import Workbook, load_workbook

from parser_classes import BaseSaver


class CSVSaver(BaseSaver):
    """
    Дочерний класс записи данных парсинга в формате CSV.
    Поддерживает инкрементальную дозапись порций (чанков) с защитой бэкапом.
    """

    def __init__(self, file_name: str):
        # Вызываем конструктор базового класса для фиксации self.file_name
        super().__init__(file_name)
        # Привязываем пути строго к экземпляру класса
        self.file_path = (Path.cwd() / self.file_name).with_suffix(".csv")
        self.backup_path = (Path.cwd() / self.file_name).with_suffix(".csv.bak")
        self.is_file_init = False

    def save(self, data: List[Dict[str, Any]]) -> bool:
        """
        Принимает порцию данных и дозаписывает её в файл CSV.
        Автоматически создает заголовки при первом вызове сессии.
        """
        if not data:
            return False

        # --- ТРАНЗАКЦИОННАЯ ЗАЩИТА: Бэкап текущего состояния перед записью ---
        if self.file_path.exists():
            try:
                # Если прошлый временный кэш остался на диске — удаляем его
                self.backup_path.unlink(missing_ok=True)
                # Копируем текущее стабильное состояние файла в бэкап
                shutil.copy2(self.file_path, self.backup_path)

                # Если это самый первый чанк НОВОЙ сессии парсинга — очищаем старый файл
                if not self.is_file_init:
                    self.file_path.unlink()
            except PermissionError as e:
                raise IOError(
                    f"❌ Не удалось сделать бэкап файла {self.file_name}. "
                    f"Убедитесь, что он не открыт в сторонних программах (например, Excel)!"
                ) from e

        # Берем заголовки из ключей первого словаря в текущей порции
        fieldnames = list(data[0].keys())

        # Проверяем, существует ли файл ДО открытия в режиме 'a' (нужно ли писать шапку)
        file_exists = self.file_path.exists()

        try:
            # Открываем в режиме 'a' (append) для добавления данных, а не перезаписи.
            # Использование 'utf-8-sig' гарантирует корректное открытие кириллицы в Excel.
            with open(self.file_path, mode="a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                # Пишем заголовки, если файл создается с нуля в текущей сессии
                if not file_exists:
                    writer.writeheader()

                # Записываем текущую порцию данных
                writer.writerows(data)

            # --- УСПЕХ: Чанк успешно дозаписан, временный бэкап больше не нужен ---
            self.backup_path.unlink(missing_ok=True)
            self.is_file_init = True
            return True

        except Exception as e:
            # --- ОТКАТ: Запись чанка упала, мгновенно восстанавливаем файл из бэкапа ---
            if self.backup_path.exists():
                # Удаляем поврежденный/недописанный файл
                self.file_path.unlink(missing_ok=True)
                # Восстанавливаем точную копию файла, сделанную прямо перед этим чанком
                shutil.copy2(self.backup_path, self.file_path)
                self.backup_path.unlink(missing_ok=True)

            raise IOError(f"Ошибка записи CSV (данные восстановлены до состояния перед чанком):\n{e}") from e


class JSONSaver(BaseSaver):
    """Сейвер для формата JSON с транзакционным бэкапом текущего состояния."""

    def __init__(self, file_name: str):
        # Вызываем конструктор базового класса для фиксации self.file_name
        super().__init__(file_name)
        # Привязываем пути строго к экземпляру класса
        self.file_path = (Path.cwd() / self.file_name).with_suffix(".json")
        self.backup_path = (Path.cwd() / self.file_name).with_suffix(".json.bak")
        self.is_file_init = False

    def save(self, data: List[Dict[str, Any]]) -> bool:
        if not data:
            return False

        # --- ТРАНЗАКЦИОННАЯ ЗАЩИТА: Бэкап перед каждым изменением файла ---
        if self.file_path.exists():
            try:
                # Если прошлый временный кэш остался на диске — удаляем его
                self.backup_path.unlink(missing_ok=True)
                # Копируем текущее стабильное состояние файла в бэкап
                shutil.copy2(self.file_path, self.backup_path)

                # Если это самый первый чанк НОВОЙ сессии парсинга — очищаем старый файл
                if not self.is_file_init:
                    self.file_path.unlink()
            except PermissionError as e:
                raise IOError(
                    f"❌ Не удалось сделать бэкап файла {self.file_name}. "
                    f"Убедитесь, что файл не заблокирован другими программами!"
                ) from e

        try:
            existing_data = []

            # Если файл существует и мы находимся внутри текущей сессии (флаг True),
            # считываем из него ранее накопленные в этой сессии чанки
            if self.file_path.exists() and self.file_path.stat().st_size > 0:
                with open(self.file_path, mode="r", encoding="utf-8") as f:
                    try:
                        existing_data = json.load(f)
                    except json.JSONDecodeError:
                        existing_data = []
            else:
                # Если файла на диске нет (или мы только что стерли его при старте сессии),
                # инициализируем его как пустой массив
                existing_data = []

            # Объединяем старый массив текущей сессии с новой порцией (чанком)
            existing_data.extend(data)

            # Записываем обновленный массив целиком
            with open(self.file_path, mode="w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            # --- УСПЕХ: Чанк успешно записан на диск, временный бэкап больше не нужен ---
            self.backup_path.unlink(missing_ok=True)
            self.is_file_init = True
            return True

        except Exception as e:
            # --- ОТКАТ: Запись упала, мгновенно восстанавливаем файл из бэкапа ---
            if self.backup_path.exists():
                # Удаляем поврежденный при записи файл
                self.file_path.unlink(missing_ok=True)
                # Восстанавливаем точную копию файла, сделанную прямо перед этим чанком
                shutil.copy2(self.backup_path, self.file_path)
                self.backup_path.unlink(missing_ok=True)

            raise IOError(f"Ошибка записи JSON (данные восстановлены до состояния перед чанком):\n{e}") from e


class XLSXSaver(BaseSaver):
    """Сейвер для формата Excel (XLSX)."""

    def __init__(self, file_name: str):
        super().__init__(file_name)
        # Объявляем пути строго через self на уровне экземпляра класса
        self.file_path = (Path.cwd() / self.file_name).with_suffix(".xlsx")
        self.backup_path = (Path.cwd() / self.file_name).with_suffix(".xlsx.bak")
        self.is_file_init = False

    def save(self, data: List[Dict[str, Any]]) -> bool:
        if not data:
            return False

        # --- Делаем бэкап перед КАЖДОЙ записью чанка ---
        if self.file_path.exists():
            try:
                # Если прошлый бэкап остался, удаляем его
                self.backup_path.unlink(missing_ok=True)
                # Клонируем текущее состояние файла в бэкап
                shutil.copy2(self.file_path, self.backup_path)

                # Если это самый первый запуск НОВОЙ сессии — очищаем старый файл
                if not self.is_file_init:
                    self.file_path.unlink()
            except PermissionError as e:
                raise IOError(
                    f"❌ Не удалось сделать бэкап файла {self.file_name}. "
                    f"Убедитесь, что он закрыт в Excel перед запуском!"
                ) from e

        fieldnames = list(data[0].keys())

        try:
            if not self.file_path.exists():
                wb = Workbook()
                ws = wb.active
                ws.title = "Parsing Result"
                ws.append(fieldnames)  # Пишем шапку
            else:
                wb = load_workbook(self.file_path)
                ws = wb.active

            # Дописываем строки чанка
            for item in data:
                ws.append([item.get(key, "") for key in fieldnames])

            wb.save(self.file_path)
            wb.close()

            # --- УСПЕХ: Чанк записан, старый бэкап больше не нужен ---
            self.backup_path.unlink(missing_ok=True)
            self.is_file_init = True
            return True

        except Exception as e:
            # --- ОТКАТ: Запись чанка упала, восстанавливаем файл из бэкапа текущего шага ---
            if self.backup_path.exists():
                # Удаляем битый/недописанный файл
                self.file_path.unlink(missing_ok=True)
                # Возвращаем копию, сделанную прямо перед этим чанком
                shutil.copy2(self.backup_path, self.file_path)
                self.backup_path.unlink(missing_ok=True)

            raise IOError(f"Ошибка записи XLSX (данные восстановлены до состояния перед чанком):\n{e}") from e
