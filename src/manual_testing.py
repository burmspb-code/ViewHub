"""Модуль предварительного ручного тестирования сайта для
исследования сетевого слоя, анализа разметки и проверки на защиту."""

import sys

import requests
from bs4 import BeautifulSoup

# Рабочая ссылка на страницу поиска
url = "https://gardarika-spb.ru/search/?q=apecs"

# Нужно посмотреть структуру страницы сайта CTRL + U,
# найти нужные селекторы и ключевые элементы для парсинга,
# например, /catalog/ или /product/, а так же
# проверить по F12 + Fetch/XHR какие идут запросы

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

response = requests.get(url, headers=headers, timeout=10)
soup = BeautifulSoup(response.text, "html.parser")

# Находим тело таблицы с товарами
# Пробуем посчитать все теги <tbody> на странице поиска
tbody_count = len(soup.find_all("tbody"))
if tbody_count == 0:
    print("Таблица с товаром не найдена")
    sys.exit()

print("Найдена таблица")

# Находим товары по тегу <tr>
trow = soup.find_all("tr")
print(f"Найдено строк всего: {len(trow)}")

# Находим ячейки по тегу <td>
tdata = trow[round(len(trow)/4)].find_all("td")
print(f"Количество ячеек (столбцов): {len(tdata)}")
