import os
import re
import time
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def parse_category_clean(category_slug, max_pages=300):
    """
    Постраничный деликатный сбор каталога «Золотого Яблока».
    Учитывает пагинацию, проверяет наличие на складе и отсекает BNPL-рассрочки.
    """
    clean_slug = str(category_slug).strip().lstrip("/")
    output_filename = f"goldapple_{clean_slug.replace('/', '_')}.csv"

    # Изолированный профиль сессии реального пользователя для обхода 502/503 ошибок
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
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Переходим строго по страницам каталога маленькими порциями
        for current_page in range(1, max_pages + 1):
            # Исправлено: Слэш прописан жестко, чтобы избежать сетевых ошибок
            url = f"https://goldapple.ru/{clean_slug}?p={current_page}"
            print(f"  -> [Порция {current_page}] Подключение к: {url}")

            try:
                # Ожидание затихания сети для полной отрисовки интерфейса Next.js/Nuxt.js
                page.goto(url, wait_until="networkidle", timeout=90000)
                # Вежливая пауза для безопасности и стабилизации элементов
                time.sleep(4.0)
            except Exception as e:
                print(f"     [Предупреждение] Не удалось загрузить страницу {current_page}: {e}. Пропускаем.")
                continue

            # Снимаем слепок HTML разметки из живой памяти вкладки браузера
            html_content = page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Находим контейнеры карточек по нативному вертикальному классу витрины
            cards = soup.find_all("article", class_=lambda x: x and "_ga-product-card-vertical" in x)
            if not cards:
                cards = soup.find_all(attrs={"itemprop": "sku"})
                cards = [c.find_parent("article") or c.find_parent("div") for c in cards if c.find_parent()]
                cards = [c for c in list(set(cards)) if c]

            # КРИТИЧЕСКАЯ ПРОВЕРКА: Если товаров на странице вообще нет — завершаем подкатегорию
            if not cards:
                print(f"     [КОНЕЦ] Карточки на странице {current_page} отсутствуют. Сбор завершен.")
                break

            # Замеряем размер кэша ДО обработки текущей страницы
            cache_size_before = len(extracted_products)
            page_items_count = 0

            for card in cards:
                try:
                    # 1. Извлечение уникального item_id
                    inner_div = card.find("div", attrs={"data-scroll-id": True})
                    item_id = inner_div["data-scroll-id"].strip() if inner_div else ""
                    if not item_id:
                        meta_sku = card.find("meta", attrs={"itemprop": "sku"})
                        item_id = meta_sku["content"].strip() if meta_sku else ""

                    if not item_id:
                        continue  # Пропускаем баннеры и статьи

                    # 2. Формирование ссылки на товар
                    a_tag = card.find("a", href=True)
                    href = a_tag["href"].strip() if a_tag else ""
                    product_url = f"https://goldapple.ru{href}" if href else url

                    # 3. Извлечение БРЕНДА и НАЗВАНИЯ из нативных классов микроразметки
                    brand_tag = card.find(class_=lambda x: x and "product-card-name__brand" in x)
                    brand = brand_tag.text.strip() if brand_tag else "Не указан"

                    name_tag = card.find(class_=lambda x: x and "product-card-name__name" in x)
                    name = name_tag.text.strip() if name_tag else "Без названия"

                    # Извлекаем тип продукта
                    type_tag = card.find("div", class_=lambda x: x and "product-card-vertical__top" in x)
                    product_type = type_tag.text.strip() if type_tag else "Парфюмерия"

                    # 4. Извлечение цен и скидок по вашей логике (Прямая проверка имен классов)
                    current_price_rub = 0
                    old_price_rub = 0
                    discount_text = "0%"

                    all_prices = card.find_all(class_=lambda x: x and "_ga-price" in x)
                    for p_tag in all_prices:
                        class_str = " ".join(p_tag.get("class", []))

                        # Если это рассрочка (BNPL) — полностью игнорируем этот тег
                        if "bnpl" in class_str:
                            continue

                        digits = int(re.sub(r"\D", "", p_tag.text)) if re.sub(r"\D", "", p_tag.text) else 0
                        if digits == 0:
                            continue

                        # Если в классе есть маркер старой цены
                        if "old" in class_str or "discount" in class_str:
                            old_price_rub = digits
                        # Если чистый класс текущей цены
                        else:
                            current_price_rub = digits

                    if old_price_rub == 0:
                        old_price_rub = current_price_rub

                    if old_price_rub > current_price_rub and old_price_rub > 0:
                        calc_discount = int(round((1 - (current_price_rub / old_price_rub)) * 100))
                        discount_text = f"{calc_discount}%"

                    # 5. Определение наличия товара на складе (Динамическое, по вашему скриншоту)
                    in_stock = True
                    status_tag = card.find(
                        class_=lambda x: x and ("_ga-pdp-status" in x or "_ga-pdp-product__status" in x)
                    )

                    if status_tag:
                        status_text = status_tag.text.lower().strip()
                        if "нет в наличии" in status_text or "ожидается" in status_text:
                            in_stock = False
                    else:
                        # Резервная проверка по тексту всей карточки
                        card_text_lower = card.get_text(separator=" ").lower()
                        if "нет в наличии" in card_text_lower:
                            in_stock = False

                    # Формируем очищенный словарь параметров карточки по вашему ТЗ
                    product_data = {
                        "category": category_slug,
                        "item_id": item_id,
                        "brand": brand,
                        "name": name,
                        "product_type": product_type,
                        "old_price_rub": old_price_rub,
                        "current_price_rub": current_price_rub,
                        "discount": discount_text,
                        "in_stock": in_stock,
                        "url": product_url,
                    }

                    # Отправляем в функцию сохранения карточки
                    save_product_json(product_data, extracted_products, category_slug)
                    page_items_count += 1

                except Exception:
                    continue

            # Замеряем размер кэша ПОСЛЕ обработки страницы
            cache_size_after = len(extracted_products)

            # ПРЕДОХРАНИТЕЛЬ ОТ ЗАЦИКЛИВАНИЯ ПАГИНАЦИИ:
            # Если карточки на странице были, но НИ ОДНА из них не оказалась новой — категория закончилась!
            if page_items_count > 0 and cache_size_after == cache_size_before:
                print(f"     [СТОП] Порция {current_page} вернула только дубликаты. Фактический конец каталога.")
                break

            print(
                f"     [СТАТУС] Порция {current_page} обработана. Добавлено новых: {cache_size_after - cache_size_before}. Общий кэш: {len(extracted_products)} позиций."
            )

            # Сохранение в реальном времени (Защита данных от обрывов на VPS)
            if extracted_products:
                df_temp = pd.DataFrame(extracted_products)
                df_temp.to_csv(output_filename, index=False, encoding="utf-8-sig")

        context.close()

    print(f"[ЗАВЕРШЕНО] Подкатегория {category_slug} сохранена в файл: '{output_filename}'")
    return extracted_products


# Функция сохранения карточки в хранилище памяти
def save_product_json(prod, storage, category_slug):
    item_id = prod.get("item_id")
    if item_id and not any(p["item_id"] == item_id for p in storage):
        storage.append(prod)


if __name__ == "__main__":
    # Тестируем строго на одной подкатегории женской парфюмерии
    perfume_subcategories = ["parfjumerija/nabory"]

    print("[СТАРТ] Запуск локального порционного парсера для женских ароматов")
    global_start_time = time.time()
    total_all_products = 0

    for sub_slug in perfume_subcategories:
        print(f"\n=====================================================================")
        print(f" НАЧИНАЕМ ГЛУБОКИЙ СБОР ПОДКАТЕГОРИИ: {sub_slug}")
        print(f"=====================================================================")

        try:
            # Запускаем стабильную функцию парсинга HTML-порций
            # max_pages=300 гарантирует, что мы заберем категорию до самой последней страницы
            subcategory_results = parse_category_clean(category_slug=sub_slug, max_pages=300)
            total_all_products += len(subcategory_results)

        except Exception as e:
            print(f" [Критический сбой подраздела] Скрипт прерван на {sub_slug}: {e}")
            continue

    global_duration = time.time() - global_start_time
    print(f"\n=====================================================================")
    print(f" 🎉 ТЕСТОВЫЙ СБОР КАТЕГОРИИ УСПЕШНО ЗАВЕРШЕН!")
    print(f" ⏱️ Общее время работы скрипта: {global_duration / 60:.2f} мин.")
    print(f" 📦 Всего уникальных карточек сохранено в CSV: {total_all_products}")
    print(f"=====================================================================")
