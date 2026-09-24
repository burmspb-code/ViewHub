"""
Модуль предварительного ручного тестирования сайта-таблицы
Гардарика (https://gardarika-spb.ru), собранного на старом
движке Битрикс с выдачей всего товара по запросу на страницу
с бесконечным скроллом.
"""

import sys

import requests
from bs4 import BeautifulSoup

# Рабочая ссылка на страницу поиска
url = "https://gardarika-spb.ru/search/?q=apecs"

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

response = requests.get(url, headers=headers, timeout=10)
soup = BeautifulSoup(response.text, "lxml")

# Находим тело таблицы с товарами
# Пробуем посчитать все теги <tbody> на странице поиска
tbody_count = len(soup.find_all("tbody"))
if tbody_count == 0:
    print("Таблица с товаром не найдена")
    sys.exit()

print("Найдена таблица")

# Находим товары по тегу <tr>
trow_base = soup.find_all("tr")
print(f"Найдено строк всего: {len(trow_base)}")

# Находим все карточки, где ячеек 5 штук, что соответствует карточке ТОВАРА
product_count = 0
for trow in trow_base:
    td_row_count = len(trow.find_all("td", recursive=False))
    if td_row_count == 5:
        product_count +=1

# Выводим количество товаров на странице
print(f"Количество товаров на странице: {product_count}")
