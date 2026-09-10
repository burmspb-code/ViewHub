"""Модуль для фонового парсинга сайтов и автоматического анализа цен."""

import random
import time
from contextlib import suppress

import pandas as pd
import requests
from bs4 import BeautifulSoup
from PyQt6.QtCore import QThread, pyqtSignal


class ParserWorker(QThread):
    """Отдельный поток для парсинга, чтобы интерфейс приложения не зависал."""

    # Сигналы для безопасной передачи данных обратно в главный поток интерфейса
    progress_signal = pyqtSignal(str)  # Передает текст текущего статуса в UI
    finished_signal = pyqtSignal(str)  # Передает путь к созданному Excel-файлу
    error_signal = pyqtSignal(str)  # Передает текст ошибки в случае сбоя

    def __init__(self, target_url: str, internal_catalog_path: str, brand_keyword: str = ""):
        """Инициализация потока парсинга."""
        super().__init__()
        self.target_url = target_url.strip()
        self.internal_catalog_path = internal_catalog_path.strip()
        # Приводим к нижнему регистру для регистронезависимого поиска бренда
        self.brand_keyword = brand_keyword.strip().lower()

    def run(self) -> None:
        """Основной метод, который выполняется в фоновом потоке при вызове .start()."""
        try:
            self.progress_signal.emit("🤖 Шаг 1: Скачивание страницы конкурента...")

            # Заголовки для имитации реального браузера (защита от базовых блокировок)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            }

            # Отправляем сетевой запрос с таймаутом в 10 секунд
            response = requests.get(self.target_url, headers=headers, timeout=10)
            response.raise_for_status()

            self.progress_signal.emit("🔍 Шаг 2: Извлечение и фильтрация данных...")
            soup = BeautifulSoup(response.text, "html.parser")

            # Находим все карточки товаров на странице
            items = soup.find_all("div", class_="thumbnail")

            competitor_data = []
            for item in items:
                name_title = item.find("a", class_="title")
                price_text = item.find("h4", class_="price")

                if name_title and price_text:
                    name = name_title.get("title", name_title.text).strip()

                    # Фильтрация по бренду: если задан бренд и его нет в названии, пропускаем
                    if self.brand_keyword and (self.brand_keyword not in name.lower()):
                        continue

                    # Очищаем цену от лишних символов валют и пробелов
                    raw_price = price_text.text.replace("$", "").replace("€", "").replace("₽", "").strip()
                    price = float(raw_price)

                    competitor_data.append(
                        {
                            "Артикул/Модель": name,
                            "Цена Конкурента": price,
                            "Статус Конкурента": "В наличии"
                        }
                    )

            brand_info = f" по бренду '{self.brand_keyword}'" if self.brand_keyword else ""
            self.progress_signal.emit(f"📊 Найдено {len(competitor_data)} позиций{brand_info}. Сопоставляем прайсы...")

            # Небольшая пауза для плавности отображения статуса в UI
            time.sleep(0.5)

            if not competitor_data:
                msg = f"Товары{brand_info} не найдены на целевой странице."
                raise ValueError(msg)

            # Переходим к анализу данных с помощью pandas
            df_internal = pd.read_excel(self.internal_catalog_path)
            df_competitor = pd.DataFrame(competitor_data)

            # Объединяем внутренний каталог компании и собранные данные конкурента
            merged_df = pd.merge(df_internal, df_competitor, on="Артикул/Модель", how="left")

            # Маркируем товары, которых не оказалось у конкурента (потенциальный дефицит на рынке)
            merged_df["Цена Конкурента"] = merged_df["Цена Конкурента"].fillna(0)
            merged_df["Статус Конкурента"] = merged_df["Статус Конкурента"].fillna("Нет в наличии")

            # Рассчитываем разницу цен
            merged_df["Разница (Конкурент - Мы)"] = merged_df["Цена Конкурента"] - merged_df["Наша Цена"]

            # Выстраиваем интеллектуальную стратегию продаж для оптового менеджера
            def set_strategy(row: pd.Series) -> str:
                if row["Цена Конкурента"] == 0:
                    return "У конкурента нет. Можно поднять цену / Дефицит"
                if row["Разница (Конкурент - Мы)"] < 0:
                    return "ДЕМПИНГ! Конкурент дешевле. Нужна скидка"
                return "Наша цена выгоднее. Использовать в УТП"

            merged_df["Стратегия продаж"] = merged_df.apply(set_strategy, axis=1)

            # Имя финального файла отчета
            output_path = "Анализ_рынка_и_стратегия.xlsx"
            merged_df.to_excel(output_path, index=False)

            # Успешный финал: отправляем сигнал в UI и передаем путь к файлу
            self.finished_signal.emit(output_path)

        except Exception as e:
            # Безопасный перехват любых ошибок и передача их текста в интерфейс
            self.error_signal.emit(str(e))
