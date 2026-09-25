import os
import re
import time
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def extract_detail_fields(html_content: str) -> dict:
    """
    ЭТАП 1: Чистый парсинг детальной страницы товара (PDP).
    Извлекает Описание, Применение и Страну происхождения.
    """
    detail_soup = BeautifulSoup(html_content, "html.parser")

    description = "Описание отсутствует"
    usage = "Не указано"
    country_of_origin = "Не указана"

    # 1. ПОЛЕ №2: ОПИСАНИЕ ТОВАРA
    desc_tag = detail_soup.find(attrs={"itemprop": "description"})
    if desc_tag:
        description = desc_tag.get_text(separator=" ", strip=True)

    # 2. ПОЛЕ №3: ПРИМЕНЕНИЕ
    usage_container = detail_soup.find("div", attrs={"text": "Применение"})
    if usage_container:
        usage_tag = usage_container.find("div", class_=lambda x: x and "_ga-pdp-wysiwyg" in x)
        if usage_tag:
            usage = usage_tag.get_text(strip=True)

    # 3. ПОЛЕ №4: СТРАНА ПРОИСХОЖДЕНИЯ (ИСПРАВЛЕНО: Безотказный поиск по регулярному выражению)
    info_container = detail_soup.find("div", attrs={"text": "Информация и документы"})
    if info_container:
        # Получаем весь сплошной текст контейнера, очищая его от скрытых неразрывных пробелов \xa0
        info_text = info_container.get_text(separator=" ", strip=True).replace("\xa0", " ")

        # Регулярное выражение ищет фразу "страна происхождения", пропускает любые звездочки,
        # пробелы, двоеточия или переносы, и захватывает первое идущее следом слово из букв (название страны)
        match = re.search(r"страна\s+происхождения[\s\*:]+([А-Яа-яЁёА-Яа-яA-Za-z]+)", info_text, re.IGNORECASE)

        if match:
            # Извлекаем очищенную страну и делаем первую букву заглавной
            country_of_origin = match.group(1).strip().capitalize()

    return {"description": description, "usage": usage, "country_of_origin": country_of_origin}


def parse_category_clean(category_slug, max_pages=300):
    """
    ЭТАП 2: Постраничный сбор листинга. Извлекает базовые поля + Рейтинг,
    после чего вызывает функцию из ЭТАПа 1 для сбора глубоких полей.
    """
    clean_slug = str(category_slug).strip().lstrip("/")
    output_filename = f"goldapple_{clean_slug.replace('/', '_')}.csv"

    # Изолированный профиль сессии реального пользователя
    user_data_dir = os.path.join(os.getcwd(), "chrome_user_profile")
    extracted_products = []

    print(f"\n[ИНИЦИАЛИЗАЦИЯ] Запуск Chromium для подкатегории: {category_slug}")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,  # Обязательно False для прохождения TLS/Nginx проверок
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        # Вместо создания новой страницы, забираем ту, которую Playwright уже открыл сам
        page = context.pages[0] if context.pages else context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Вкладка №2 для быстрого и деликатного захода внутрь карточек товаров
        detail_page = context.new_page()
        detail_page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        for current_page in range(1, max_pages + 1):
            url = f"https://goldapple.ru/{clean_slug}?p={current_page}"
            print(f"\n[ПОРЦИЯ {current_page}] Подключение к каталогу: {url}")

            try:
                # Ожидание затихания сети для сборки интерфейса Next.js/Nuxt.js
                page.goto(url, wait_until="networkidle", timeout=90000)
                time.sleep(4.0)
            except Exception as e:
                print(f"     [Предупреждение] Не удалось загрузить страницу каталога {current_page}: {e}")
                continue

            html_content = page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Находим контейнеры карточек
            cards = soup.find_all("article", class_=lambda x: x and "_ga-product-card-vertical" in x)
            if not cards:
                cards = soup.find_all(attrs={"itemprop": "sku"})
                cards = [c.find_parent("article") or c.find_parent("div") for c in cards if c.find_parent()]
                cards = [c for c in list(set(cards)) if c]

            if not cards:
                print(f"     [КОНЕЦ] Карточки на странице {current_page} отсутствуют. Каталог пройден.")
                break

            cache_size_before = len(extracted_products)
            page_items_count = 0
            current_page_batch = []

            # 1. Собираем базовые параметры карточек с текущей страницы листинга
            for card in cards:
                try:
                    inner_div = card.find("div", attrs={"data-scroll-id": True})
                    item_id = inner_div["data-scroll-id"].strip() if inner_div else ""
                    if not item_id:
                        meta_sku = card.find("meta", attrs={"itemprop": "sku"})
                        item_id = meta_sku["content"].strip() if meta_sku else ""

                    if not item_id:
                        continue

                    a_tag = card.find("a", href=True)
                    href = a_tag["href"].strip() if a_tag else ""
                    product_url = f"https://goldapple.ru{href}" if href else url

                    brand_tag = card.find(class_=lambda x: x and "product-card-name__brand" in x)
                    brand = brand_tag.text.strip() if brand_tag else "Не указан"

                    name_tag = card.find(class_=lambda x: x and "product-card-name__name" in x)
                    name = name_tag.text.strip() if name_tag else "Без названия"

                    type_tag = card.find("div", class_=lambda x: x and "product-card-vertical__type" in x)
                    product_type = type_tag.text.strip() if type_tag else "Нет категории"

                    # ЦЕНЫ по вашей логике классов
                    current_price_rub = 0
                    old_price_rub = 0
                    discount_text = "0%"

                    all_prices = card.find_all(class_=lambda x: x and "_ga-price" in x)
                    for p_tag in all_prices:
                        class_str = " ".join(p_tag.get("class", []))
                        if "bnpl" in class_str:
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

                    # Определение НАЛИЧИЯ по вашему первому скану
                    in_stock = True
                    status_tag = card.find(
                        class_=lambda x: x and ("_ga-pdp-status" in x or "_ga-pdp-product__status" in x)
                    )
                    if status_tag and (
                        "нет в наличии" in status_tag.text.lower() or "ожидается" in status_tag.text.lower()
                    ):
                        in_stock = False
                    elif "нет в наличии" in card.get_text(separator=" ").lower():
                        in_stock = False

                    # ПОЛЕ №1: РЕЙТИНГ ПОЛЬЗОВАТЕЛЯ (Прямо из каталога по вашему скану)
                    rating = "0.0"
                    rating_div = card.find("div", class_=lambda x: x and "product-rating__rating-value" in x)
                    if rating_div:
                        rating = rating_div.text.strip()
                    else:
                        meta_rating = card.find("meta", attrs={"itemprop": "ratingValue"})
                        if meta_rating and meta_rating.has_attr("content"):
                            rating = meta_rating["content"].strip()

                    product_base = {
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
                    current_page_batch.append(product_base)
                except Exception:
                    continue

            # 2. Переходим по ссылкам товаров за глубокими характеристиками
            print(f"     [*] Углубленный сбор характеристик для {len(current_page_batch)} товаров порции...")
            for prod in current_page_batch:
                deep_fields = {
                    "description": "Описание отсутствует",
                    "usage": "Не указано",
                    "country_of_origin": "Не указана",
                }

                if prod["url"] and prod["url"] != url:
                    try:
                        # Деликатно заходим на детальную страницу товара
                        detail_page.goto(prod["url"], wait_until="networkidle", timeout=60000)
                        time.sleep(2.5)  # Короткая пауза для отрисовки аккордеонов

                        # Вызываем функцию из ЭТАПа 1
                        deep_fields = extract_detail_fields(detail_page.content())
                        print(
                            f"        [+] Извлечено глубоко: {prod['brand']} — {prod['name']} | Страна: {deep_fields['country_of_origin']}"
                        )
                    except Exception as e:
                        print(f"        [!] Ошибка перехода внутрь товара {prod['item_id']}: {e}")

                # Объединяем базовые и глубокие поля
                prod.update(deep_fields)

                # Финальное сохранение карточки в общий массив
                save_product_json(prod, extracted_products, category_slug)
                page_items_count += 1

            cache_size_after = len(extracted_products)

            # ПРЕДОХРАНИТЕЛЬ ОТ ЗАЦИКЛИВАНИЯ ПАГИНАЦИИ
            if page_items_count > 0 and cache_size_after == cache_size_before:
                print(f"     [СТОП] Порция {current_page} вернула только дубликаты. Категория пройдена.")
                break

            print(
                f"     [СТАТУС] Порция {current_page} обработана. Добавлено новых: {cache_size_after - cache_size_before}. Всего: {len(extracted_products)}."
            )

            # Запись файла в реальном времени после каждой страницы (Защита данных)
            if extracted_products:
                df_temp = pd.DataFrame(extracted_products)
                df_temp.to_csv(output_filename, index=False, encoding="utf-8-sig")

        context.close()

    return extracted_products


def save_product_json(prod, storage, category_slug):
    """
    ЭТАП 3: Контроль уникальности кэша в памяти.
    Добавляет товар в storage только если такого item_id еще нет.
    """
    item_id = prod.get("item_id")
    if item_id and not any(p["item_id"] == item_id for p in storage):
        storage.append(prod)


if __name__ == "__main__":
    # Тестовый контролируемый запуск на подразделе женских ароматов
    target_slug = "parfjumerija/dlja-detej"

    print(f"=== ЗАПУСК ГЛУБОКОГО ПАРСЕРА ДЛЯ: '{target_slug}' ===")

    # max_pages=5 — лимит для безопасного тестового прогона
    final_results = parse_category_clean(category_slug=target_slug, max_pages=5)

    print(f"\n=======================================================")
    print(f"ИТОГОВЫЙ ОТЧЕТ О ВЫПОЛНЕНИИ:")
    print(f"Всего уникальных товаров со всеми характеристиками: {len(final_results)}")

    if final_results:
        df = pd.DataFrame(final_results)
        print("\nПроверка структуры и новых полей (Превью первых 5 строк):")
        # Выводим в консоль часть полей, включая новые: рейтинг и страну происхождения
        print(df[["brand", "name", "current_price_rub", "rating", "country_of_origin"]].head(5))
    print(f"=======================================================")
