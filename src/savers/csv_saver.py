"""Дочерний класс записи данных парсинга в формате CSV."""

import csv
import shutil
from pathlib import Path
from typing import Any, Dict, List


from core.base_classes import BaseSaver


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
