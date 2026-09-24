import sys
import time
import pandas as pd
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


def parse_category_clean(category_slug, max_pages=3):
    url = "https://goldapple.ru/" + str(category_slug)
    extracted_products = []

    print(f"\n[ШАГ 1] Запуск Chromium браузера с нативной маскировкой...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        page = context.new_page()

        # Нативная маскировка webdriver
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("[ШАГ 2] Настройка сетевого перехватчика...")

        def handle_response(response):
            if "catalog/products" in response.url or "front/api/home/slots" in response.url:
                if response.status == 200:
                    try:
                        data = response.json()
                        products_list = data.get("products", []) if isinstance(data, dict) else []
                        for prod in products_list:
                            save_product_json(prod, extracted_products, category_slug)
                        slots = data.get("slots", []) if isinstance(data, dict) else []
                        for slot in slots:
                            slot_products = slot.get("products", [])
                            for prod in slot_products:
                                save_product_json(prod, extracted_products, category_slug)
                    except Exception:
                        pass

        page.on("response", handle_response)

        print(f"[ШАГ 3] Загрузка страницы раздела: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print("[ШАГ 4] Страница открыта. Ожидаем инициализацию UI...")
            time.sleep(5)
        except Exception as e:
            print(f"[КРИТИЧЕСКАЯ ОШИБКА] Не удалось открыть страницу: {e}")
            browser.close()
            return []

        print("[ШАГ 5] Запуск клавиатурной эмуляции прокрутки экрана...")
        page.mouse.click(960, 540)

        for i in range(1, max_pages + 1):
            print(f"  -> Прокрутка экрана вниз (Итерация {i} из {max_pages})...")
            try:
                for _ in range(5):
                    page.keyboard.press("PageDown")
                    time.sleep(0.4)
                time.sleep(4)
            except Exception as e:
                print(f"  [ПРЕДУПРЕЖДЕНИЕ] Контекст прерван: {e}. Сохраняем собранное.")
                break

        # =====================================================================
        # 🌟 УМНЫЙ СТРУКТУРНЫЙ ПАРСЕР DOM (ФИНАЛЬНАЯ НАСТРОЙКА) 🌟
        # =====================================================================
        if not extracted_products:
            print("[РЕЗЕРВНЫЙ ВАРИАНТ] Перехват сети пуст. Извлекаем данные напрямую из DOM-дерева HTML...")
            html_content = page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            product_links = soup.find_all("a", href=True)

            for link in product_links:
                href = link["href"]

                if href and any(char.isdigit() for char in href) and ("/p/" in href or "-" in href):
                    text_block = link.get_text(separator="\n")
                    lines = [l.strip() for l in text_block.split("\n") if l.strip()]

                    if len(lines) >= 3 and any("₽" in l for l in lines):
                        try:
                            # 1. Извлекаем самую первую (актуальную) цену со значком ₽
                            price = "0"
                            for line in lines:
                                if "₽" in line and "плат" not in line.lower():
                                    price = (
                                        line.replace("от", "")
                                        .replace("₽", "")
                                        .strip()
                                        .replace("\xa0", "")
                                        .replace(" ", "")
                                    )
                                    break

                            # 2. Фильтруем только текстовые строки (убираем объемы, рейтинги, проценты)
                            clean_strings = []
                            for l in lines:
                                if (
                                    l.replace(".", "", 1).isdigit()
                                    or "×" in l
                                    or l.endswith("%")
                                    or "₽" in l
                                    or l.lower() in ["от", "купить"]
                                ):
                                    continue
                                clean_strings.append(l)

                            # Убираем дубликаты строк, идущие подряд (особенность верстки маркетплейса)
                            final_strings = []
                            for s in clean_strings:
                                if not final_strings or s != final_strings[-1]:
                                    final_strings.append(s)

                            if len(final_strings) < 2:
                                continue

                            # 3. Распределяем Бренд, Название и Тип продукта
                            # Ищем строку, содержащую маркеры типа товара
                            type_idx = -1
                            product_type_text = "Парфюмерия"
                            for idx, s in enumerate(final_strings):
                                if any(k in s.lower() for k in ["вода", "духи", "одеколон", "спрей"]):
                                    type_idx = idx
                                    product_type_text = s
                                    break

                            # Если маркер типа продукта найден
                            if type_idx != -1 and type_idx + 1 < len(final_strings):
                                # Структура: [..., "Тип продукта", "Бренд Название"]
                                remainder = final_strings[type_idx + 1]
                                # Первое слово в связке — это Бренд (он на латинице)
                                parts = remainder.split(" ")
                                brand = parts[0]
                                name = " ".join(parts[1:]) if len(parts) > 1 else remainder
                            else:
                                # Если маркер типа не встал, распределяем по языковому признаку
                                # Первой строкой часто идет комбинация "Бренд Название"
                                candidate = final_strings[0]
                                parts = candidate.split(" ")
                                brand = parts[0]
                                name = " ".join(parts[1:]) if len(parts) > 1 else candidate

                            item_id = href.split("/")[-1].split("-")[0]
                            if not item_id or not item_id.isdigit():
                                item_id = str(abs(hash(name + price)))[:10]

                            if item_id and not any(p["item_id"] == item_id for p in extracted_products):
                                extracted_products.append(
                                    {
                                        "category": category_slug,
                                        "item_id": item_id,
                                        "brand": brand,
                                        "name": name,
                                        "product_type": product_type_text,
                                        "old_price_rub": price,
                                        "current_price_rub": price,
                                        "discount": "0%",
                                        "in_stock": True,
                                        "url": f"https://goldapple.ru{href}" if not href.startswith("http") else href,
                                    }
                                )
                        except Exception:
                            continue


        print("[ШАГ 6] Завершение сессии, закрытие процессов Chromium...")
        browser.close()

    return extracted_products


def save_product_json(prod, storage, category_slug):
    price_info = prod.get("price", {})
    regular_price = price_info.get("regular", {}).get("amount") or price_info.get("regular_price")
    discount_price = price_info.get("discount", {}).get("amount") or price_info.get("discount_price")
    current_price = discount_price if discount_price else regular_price
    discount_percent = price_info.get("viewOptions", {}).get("discountPercent", 0)

    item_id = prod.get("itemId") or prod.get("id")
    if item_id and not any(p["item_id"] == item_id for p in storage):
        storage.append(
            {
                "category": category_slug,
                "item_id": item_id,
                "brand": prod.get("brand") or prod.get("brandName"),
                "name": prod.get("name") or prod.get("title"),
                "product_type": prod.get("productType"),
                "old_price_rub": regular_price,
                "current_price_rub": current_price,
                "discount": f"{discount_percent}%" if discount_percent else "0%",
                "in_stock": prod.get("inStock"),
                "url": f"https://goldapple.ru{prod.get('url')}"
                if prod.get("url") and not str(prod.get("url")).startswith("http")
                else prod.get("url"),
            }
        )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        TARGET_CATEGORY = sys.argv[1]
    else:
        TARGET_CATEGORY = "parfjumerija"

    SCROLL_COUNT = 1

    print(f"=== ЗАПУСК ПАРСЕРА ДЛЯ ОТДЕЛЬНОЙ КАТЕГОРИИ: '{TARGET_CATEGORY.upper()}' ===")
    result = parse_category_clean(category_slug=TARGET_CATEGORY, max_pages=SCROLL_COUNT)

    if result:
        df = pd.DataFrame(result).drop_duplicates(subset=["item_id"])
        output_file = f"goldapple_{TARGET_CATEGORY}.csv"
        df.to_csv(output_file, index=False, encoding="utf-8-sig")
        print(f"\n[УСПЕХ] Сборка выборки завершена!")
        print(f"Успешно сохранено уникальных товаров: {len(df)} в файл '{output_file}'")
        print("\nПревью таблицы:")
        print(df[['brand', 'name', 'current_price_rub']].head(5).to_string())
    else:
        print(f"\n[ИТОГ] Не удалось собрать данные для раздела '{TARGET_CATEGORY}'.")
