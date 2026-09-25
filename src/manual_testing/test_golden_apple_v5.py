"""Модуль отладочного тестирования для Golden Apple."""

import os
import re
import asyncio
import random
import csv

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# =====================================================================
# ГЛОБАЛЬНЫЕ КОНСТАНТЫ ПРОЕКТА
# =====================================================================
# Название подраздела для парсинга (slug)
CATEGORY_SLUG = "parfjumerija/dlja-detej"

# Количество одновременно открытых вкладок с детальным описанием товара (PDP)
MAX_CONCURRENT_DETAILS = 1

# Семафор для контроля параллельности глубокого сбора
detail_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DETAILS)


async def count_and_get_products_on_page(catalog_page):
    """
    Модуль 2: Определение количества товаров на странице.
    Считывает HTML открытой вкладки и находит все контейнеры карточек товаров.
    """
    print("[*] [Шаг Сбора] Чтение HTML-кода со страницы каталога...")
    try:
        # Извлекаем текущий HTML из оперативной памяти вкладки
        html_content = await catalog_page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        print("[*] [Шаг Поиска] Анализ структуры DOM-дерева в BeautifulSoup...")
        # Находим контейнеры карточек по вашей вчерашней логике тегов <article>
        cards = soup.find_all("article")

        # Страховочный вариант поиска, если структура тегов article пуста
        if not cards:
            print("[!] Предупреждение: Теги 'article' не найдены. Пробуем поиск по itemprop='sku'...")
            cards = soup.find_all(attrs={"itemprop": "sku"})
            cards = [c.find_parent("article") or c.find_parent("div") for c in cards if c.find_parent()]
            cards = [c for c in list(set(cards)) if c]

        total_cards = len(cards)
        print(f"[+] [Успех] Анализ страницы завершен. Физически обнаружено карточек товаров: {total_cards}")

        return cards

    except Exception as e:
        print(f"[-] [Ошибка] Не удалось определить количество товаров на странице: {e}")
        return []


def extract_deep_product_data(html_content: str) -> dict:
    """
    Модуль 6 (ЭТАП 2): Высокоточный парсинг детальной страницы товара (PDP).
    Извлекает Описание, Применение и Страну происхождения по уникальным
    атрибутам itemprop и text, полностью повторяя логику DevTools.
    """
    print("        [*] [Парсинг PDP] Хирургический разбор HTML-структуры карточки...")
    detail_soup = BeautifulSoup(html_content, "html.parser")

    # Дефолтные значения на случай, если бренд не заполнил вкладки характеристик
    description = "Описание отсутствует"
    usage = "Не указано"
    country_of_origin = "Не указана"

    # 1. ПОЛЕ №2: ОПИСАНИЕ ТОВАРA (Ищем по строгому атрибуту itemprop="description")
    desc_container = detail_soup.find("div", attrs={"itemprop": "description"})
    if desc_container:
        description = desc_container.get_text(separator=" ", strip=True)
        # Очищаем от лишних крайних кавычек, если они прилетели из верстки
        description = description.strip('"\'')
        print("        [+] [Парсинг PDP] Успешно извлечено поле: Описание товара.")

    # 2. ПОЛЕ №3: ПРИМЕНЕНИЕ (Ищем по уникальному атрибуту text="Применение")
    usage_container = detail_soup.find("div", attrs={"text": "Применение"})
    if usage_container:
        # Находим внутренний блок с контентом по частичному совпадению класса
        usage_tag = usage_container.find("div", class_=lambda x: x and "_ga-pdp-wysiwyg" in x)
        if usage_tag:
            usage = usage_tag.get_text(separator=" ", strip=True).strip('"\'')
            print("        [+] [Парсинг PDP] Успешно извлечено поле: Применение.")

    # 3. ПОЛЕ №4: СТРАНА ПРОИСХОЖДЕНИЯ (Ищем по уникальному атрибуту text="Информация и документы")
    info_container = detail_soup.find("div", attrs={"text": "Информация и документы"})
    if info_container:
        # Проваливаемся во внутренний текстовый контейнер аккордеона
        info_tag = info_container.find("div", class_=lambda x: x and "_ga-pdp-wysiwyg" in x)
        if info_tag:
            paragraphs = info_tag.find_all("p")
            for p_node in paragraphs:
                p_text = p_node.get_text(separator=" ", strip=True)
                if "страна происхождения" in p_text.lower():
                    # Вырезаем маркер "страна происхождения" и полностью очищаем результат
                    country_raw = p_text.lower().replace("страна происхождения", "")
                    # Убираем кавычки, двоеточия, звездочки и пробелы из DOM-дерева
                    country_clean = country_raw.replace("*", "").replace(":", "").replace('"', "").replace("'", "").strip()
                    if country_clean:
                        country_of_origin = country_clean.capitalize()
                        print(f"        [+] [Парсинг PDP] Успешно извлечено поле: Страна происхождения -> {country_of_origin}")
                        break

    return {
        "description": description,
        "usage": usage,
        "country_of_origin": country_of_origin
    }


def extract_base_product_data(card_soup, category_slug):
    """
    Модуль 4: Извлечение базовых параметров из одной карточки товара в каталоге.
    Парсит ID, Бренд, Название, Тип, Цены, Скидку, Наличие, Рейтинг и собирает полный URL.
    """
    try:
        # 1. Извлечение ITEM_ID
        inner_div = card_soup.find("div", attrs={"data-scroll-id": True})
        item_id = inner_div["data-scroll-id"].strip() if inner_div else ""
        if not item_id:
            meta_sku = card_soup.find("meta", attrs={"itemprop": "sku"})
            item_id = meta_sku["content"].strip() if meta_sku else ""

        # Если у карточки нет ID, это может быть рекламный баннер в сетке — пропускаем его
        if not item_id:
            return None

        print(f"\n[*] [Сбор Карточки] Начат разбор базовых полей для товара ID: {item_id}")

        # 2. Правильная склейка URL товара (Защита от дублирования домена)
        a_tag = card_soup.find("a", href=True)
        href = a_tag["href"].strip() if a_tag else ""

        if href.startswith("http"):
            product_url = href
        else:
            product_url = f"https://goldapple.ru{href}" if href else ""
        print(f"    [+] Ссылка на товар успешно собрана: {product_url}")

        # 3. Извлечение БРЕНДА и НАЗВАНИЯ товара
        brand_tag = card_soup.find(class_=lambda x: x and "product-card-name__brand" in x)
        brand = brand_tag.text.strip() if brand_tag else "Не указан"

        name_tag = card_soup.find(class_=lambda x: x and "product-card-name__name" in x)
        name = name_tag.text.strip() if name_tag else "Без названия"
        print(f"    [+] Товар определён как: {brand} — {name}")

        # 4. Извлечение ТИПА ПРОДУКТА
        type_tag = card_soup.find("div", class_=lambda x: x and "product-card-vertical__type" in x)
        product_type = type_tag.text.strip() if type_tag else "Нет категории"

        # 5. Парсинг ЦЕН И СКИДКИ по логике классов
        current_price_rub = 0
        old_price_rub = 0
        discount_text = "0%"

        all_prices = card_soup.find_all(class_=lambda x: x and "_ga-price" in x)
        for p_tag in all_prices:
            class_str = " ".join(p_tag.get("class", []))
            if "bnpl" in class_str:  # Пропускаем плашки Сплита/Долями
                continue

            digits = int(re.sub(r"\D", "", p_tag.text)) if re.sub(r"\D", "", p_tag.text) else 0
            if digits == 0:
                continue

            if "old" in class_str or "discount" in class_str:
                old_price_rub = digits
            else:
                current_price_rub = digits

        if old_price_rub == 0:
            old_price_rub = current_price_rub

        if old_price_rub > current_price_rub and old_price_rub > 0:
            calc_discount = int(round((1 - (current_price_rub / old_price_rub)) * 100))
            discount_text = f"{calc_discount}%"
        print(
            f"    [+] Цена актуальная: {current_price_rub} руб. | Старая: {old_price_rub} руб. | Скидка: {discount_text}"
        )

        # 6. Определение НАЛИЧИЯ товара
        in_stock = True
        status_tag = card_soup.find(class_=lambda x: x and ("_ga-pdp-status" in x or "_ga-pdp-product__status" in x))
        if status_tag and ("нет в наличии" in status_tag.text.lower() or "ожидается" in status_tag.text.lower()):
            in_stock = False
        elif "нет в наличии" in card_soup.get_text(separator=" ").lower():
            in_stock = False
        print(f"    [+] Статус наличия: {'В наличии' if in_stock else 'Нет в наличии'}")

        # 7. Извлечение РЕЙТИНГА товара
        rating = "0.0"
        rating_div = card_soup.find("div", class_=lambda x: x and "product-rating__rating-value" in x)
        if rating_div:
            rating = rating_div.text.strip()
        else:
            meta_rating = card_soup.find("meta", attrs={"itemprop": "ratingValue"})
            if meta_rating and meta_rating.has_attr("content"):
                rating = meta_rating["content"].strip()
        print(f"    [+] Рейтинг товара: {rating}")

        # Формируем итоговый базовый словарь параметров
        return {
            "category": category_slug,
            "item_id": item_id,
            "brand": brand,
            "name": name,
            "product_type": product_type,
            "old_price_rub": old_price_rub,
            "current_price_rub": current_price_rub,
            "discount": discount_text,
            "in_stock": in_stock,
            "rating": rating,
            "url": product_url,
        }

    except Exception as e:
        print(f"    [-] Ошибка извлечения полей из карточки: {e}")
        return None


async def run_deep_pdp_conveyor(context, base_products_batch):
    """
    Модуль 7 (ЭТАП 2): Асинхронный линейный конвейер глубокого сбора (PDP).
    Обходит собранные ссылки строго по одной, забирает сырой HTML-код из памяти
    вкладки и передает его в Модуль №6 для хирургического BS4-анализа.
    """
    total_items = len(base_products_batch)
    print(f"\n[*] [ЭТАП 2] Запуск конвейера глубокого парсинга для {total_items} товаров...")

    completed_products = []

    for idx, prod in enumerate(base_products_batch, start=1):
        product_id = prod.get("item_id", "Неизвестен")
        product_url = prod.get("url", "")

        print(f"\n[*] [Конвейер] Обработка товара [{idx}/{total_items}] | ID: {product_id}")

        if not product_url or product_url == "https://goldapple.ru":
            print(f"    [-] [Конвейер] Пропуск товара ID {product_id}: отсутствует валидный URL.")
            completed_products.append(prod)
            continue

        # Вызываем Модуль №3 для открытия фоновой вкладки товара
        detail_page = await load_product_detail_page(context, product_url, product_id)

        deep_data = {"description": "Описание отсутствует", "usage": "Не указано", "country_of_origin": "Не указана"}

        if detail_page:
            try:
                # Извлекаем сырой отрендеренный HTML-код из оперативной памяти вкладки
                html_content = await detail_page.content()

                # Передаем HTML в обновленный точечный Модуль №6
                deep_data = extract_deep_product_data(html_content)

            except Exception as e:
                print(f"        [-] [Конвейер] Ошибка при чтении HTML-данных товара {product_id}: {e}")
            finally:
                # Вкладку гарантированно закрываем через await, очищая ОЗУ
                await detail_page.close()
                print(f"        [*] [Конвейер] Фоновая вкладка товара ID {product_id} успешно закрыта.")
        else:
            print(
                f"        [-] [Конвейер] Не удалось получить доступ к вкладке для товара ID {product_id}. Поля останутся дефолтными."
            )

        # Склеиваем базу из листинга с глубокими характеристиками из карточки
        prod.update(deep_data)
        completed_products.append(prod)
        print(f"    [+] [Конвейer] Данные товара ID {product_id} успешно объединены в один объект.")

        # ЗАЩИТА WAF: Если товар в списке не последний, делаем случайную паузу человека
        if idx < total_items:
            jitter_pause = random.uniform(1.5, 3.0)
            print(
                f"    [*] [Защита WAF] Имитация поведения человека: пауза перед следующим кликом {jitter_pause:.2f} sec..."
            )
            await asyncio.sleep(jitter_pause)

    print(f"\n[+] [ЭТАП 2 ЗАВЕРШЕН] Конвейер успешно обработал всю порцию из {total_items} товаров.")
    return completed_products


async def collect_base_data_and_urls(product_cards, category_slug):
    """
        Модуль 5 (ЭТАП 1): Массовый сбор базовых данных и ссылок со страницы каталога.
        Пробегается по всем найденным карточкам листинга, извлекает базу и склеивает URL.
        Выполняется БЕЗ открытия детальных вкладок.
    Используйте код с осторожностью.python"""

    print(f"\n[*] [ЭТАП 1] Начат сбор базовых параметров и ссылок для {len(product_cards)} карточек...")
    page_batch = []

    # Импортируем Модуль №4 извлечения параметров (убедитесь, что он объявлен в файле)
    for idx, card in enumerate(product_cards, start=1):
        try:
            # Вызываем функцию извлечения базовых полей одной карточки
            base_data = extract_base_product_data(card, category_slug)

            # Если это была не рекламная плашка, а реальный товар — сохраняем его
            if base_data:
                page_batch.append(base_data)
                print(
                    f"    [+] [{idx}/{len(product_cards)}] Товар ID {base_data['item_id']} успешно добавлен в пакет листинга."
                )
            else:
                print(f"    [-] [{idx}/{len(product_cards)}] Пропущена пустая карточка или баннер.")

        except Exception as e:
            print(f"    [-] [Ошибка] Сбой разбора карточки №{idx}: {e}")
            continue

    print(f"\n[+] [ЭТАП 1 ЗАВЕРШЕН] Сбор страницы каталога окончен.")
    print(f"[+] Всего успешно обработано уникальных товаров в пакете: {len(page_batch)}")

    # Выводим красивый список всех собранных ссылок для визуального контроля
    print("\n=== КОНТРОЛЬНЫЙ СПИСОК ИЗВЛЕЧЕННЫХ ССЫЛОК ПРОЕКТА ===")
    for item in page_batch:
        print(f"ID: {item['item_id']} -> {item['url']}")
    print("=======================================================\n")

    # Возвращаем готовый пакет товаров со ссылками для ЭТАПА №2
    return page_batch


async def load_product_detail_page(context, product_url: str, product_id: str):
    """
    Модуль 3 (ЭТАП 2): Открытие фоновой вкладки товара.
    Терпеливо дожидается, пока лоадер сайта не сменится реальным текстом товара.
    """
    print(f"    [*] [Детальная Навигация] Запрос на открытие товара ID: {product_id}...")

    try:
        page = await context.new_page()

        # Переходим на страницу товара
        await page.goto(product_url, wait_until="domcontentloaded", timeout=40000)

        # Ждем появление главного заголовка страницы (название духов / бренд)
        print(f"    [*] [Детальное Ожидание] Ждем, пока исчезнет лоадер и прогрузится карточка ID {product_id}...")
        await page.locator("h1").first.wait_for(state="visible", timeout=60000)

        # Небольшая страховочная пауза для окончательного монтажа Vue-компонентов
        await page.wait_for_timeout(2000)

        print(f"    [+] [Детальный Успех] Карточка товара ID: {product_id} полностью готова!")
        return page

    except Exception as e:
        print(f"    [-] [Детальная Ошибка] Не удалось дождаться загрузки карточки ID {product_id}: {e}")
        await page.close()
        return None


async def load_catalog_page(context, category_slug, current_page):
    """
    Модуль 1: Загрузка конкретной страницы каталога.
    Открывает скрытую вкладку, дожидается отрисовки Nuxt-карточек и возвращает страницу.
    """
    print(f"[*] [Шаг Навигации] Создание новой вкладки для страницы листинга №{current_page}...")
    page = await context.new_page()

    # Скрытие автоматизации на уровне браузера
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    # Оптимизация сети: баним картинки и шрифты, оставляя стили ради верстки <p>
    await page.route(
        "**/*",
        lambda route, request: (
            route.abort() if request.resource_type in ["image", "font", "media", "image-set"] else route.continue_()
        ),
    )

    url = f"https://goldapple.ru/{category_slug}?p={current_page}"
    print(f"[*] [Шаг Навигации] Переход по URL: {url}")

    try:
        # Загружаем базовую структуру
        await page.goto(url, wait_until="domcontentloaded", timeout=0)

        # Жестко ждем, пока интернет физически не отрисует карточки товаров в DOM
        print(f"[*] [Шаг Ожидания] Ждем появление тегов 'article' на странице №{current_page}...")
        await page.locator("article").first.wait_for(state="visible", timeout=0)

        # Пауза для окончательного монтажа сетки товаров во Vue
        await asyncio.sleep(4.0)

        print(f"[+] [Успех] Страница №{current_page} полностью готова к сбору данных.")
        return page

    except Exception as e:
        print(f"[-] [Ошибка] Не удалось прогрузить страницу каталога №{current_page}: {e}")
        await page.close()
        return None


async def main():
    """
    Основное управляющее ядро проекта.
    Инициализирует скрытый браузер и координирует шаги.
    """
    print("=== ЗАПУСК НОВОГО МОДУЛЬНОГО АСИНХРОННОГО ПАРСЕРА ===")

    user_data_dir = os.path.join(os.getcwd(), "chrome_user_profile")
    print(f"[*] Инициализация persistent-профиля Хрома: {user_data_dir}")

    async with async_playwright() as p:
        print("[*] Запуск Chromium в скрытом режиме (headless=True)...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,  # Полностью невидимый интерфейс в памяти
            args=[
                "--disable-blink-features=AutomationControlled", # НАШ ВАЖНЕЙШИЙ МАСКИРОВОЧНЫЙ ФЛАГ (ОСТАВЛЯЕМ)
                "--blink-settings=imagesEnabled=false"           # НОВЫЙ ФЛАГ: ТАКТИЧЕСКОЕ ОТКЛЮЧЕНИЕ КАРТИНОК
            ],
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )

        # --- ТЕСТОВЫЙ ЗАПУСК МОДУЛЯ ЗАГРУЗКИ (СТРАНИЦА 1) ---
        catalog_page = await load_catalog_page(context, CATEGORY_SLUG, current_page=1)

        # Определяем количество карточек товара на странице
        product_cards = await count_and_get_products_on_page(catalog_page)

        if product_cards:
            # ВЫЗОВ НОВОГО МОДУЛЯ 5 (ЭТАП №1)
            # Собираем базу и все ссылки, не открывая фоновые вкладки
            current_page_batch = await collect_base_data_and_urls(product_cards, CATEGORY_SLUG)

            # Закрываем страницу каталога СРАЗУ ПОСЛЕ СБОРА ССЫЛОК, разгружая память
            await catalog_page.close()
            print("[*] Вкладка каталога успешно закрыта. Память разгружена.")

            # === ВЫЗОВ НОВОГО МОДУЛЯ 7 (ЭТАП №2) ===
            # Передаем массив из 20 ссылок в наш бережный линейный конвейер
            final_products_data = await run_deep_pdp_conveyor(context, current_page_batch)

            print(f"[*] Итоговый обогащенный массив из {len(final_products_data)} товаров собран в памяти.")

            # === ВЫЗОВ НОВОГО МОДУЛЯ 8 (ЭТАП №3) ===
            # Передаем готовый массив в функцию сохранения
            save_products_to_csv(final_products_data, CATEGORY_SLUG)

    print("=== РАБОТА СТАРТОВОГО МОДУЛЯ ЗАВЕРШЕНА ===")


def save_products_to_csv(products_list, category_slug):
    """
    Модуль 8 (ЭТАП 3): Финальное сохранение данных в формате CSV.
    Принимает обогащенный массив товаров, формирует имя файла по названию раздела
    и записывает таблицу с поддержкой кириллицы для Excel.
    """
    if not products_list:
        print("[-] [Шаг Экспорта] Ошибка: массив товаров пуст. Нечего сохранять.")
        return None

    # Формируем красивое имя файла на основе slug категории (н-р, goldapple_parfjumerija_dlja-detej.csv)
    clean_slug = str(category_slug).strip().lstrip("/").replace("/", "_")
    output_filename = f"goldapple_{clean_slug}.csv"

    print(f"\n[*] [Шаг Экспорта] Начата запись {len(products_list)} товаров в файл: {output_filename}...")

    try:
        # Извлекаем заголовки колонок из ключей первого товара в списке
        fieldnames = list(products_list[0].keys())

        # utf-8-sig добавляет BOM-маркер, чтобы Excel сразу распознавал русский текст
        with open(output_filename, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")

            # Пишем шапку таблицы
            writer.writeheader()
            print("    [+] Шапка таблицы успешно записана.")

            # Пишем строки с товарами
            writer.writerows(products_list)

        print(f"[+] [Экспорт Завершен] Все данные успешно сохранены на диск!")
        print(f"[+] Итоговый файл проекта: {os.path.abspath(output_filename)}")
        return output_filename

    except Exception as e:
        print(f"[-] [Ошибка] Не удалось сохранить данные в CSV: {e}")
        return None


if __name__ == "__main__":
    asyncio.run(main())
