import sys
import re
import json
import os
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

BASE_URL = "https://citadel2000.ru/"
OUTPUT_FILE = "citadel_final.json"

print("=" * 70)
print("🚀 ПАРСЕР ЦИТАДЕЛЬ — ФИНАЛ")
print("=" * 70)

keyword = input("\n🔍 Введите ключевое слово: ").strip()
if not keyword:
    sys.exit(1)

def is_category(href):
    """Категория: /catalog/zamki/ — один сегмент после /catalog/.
    Товар: /catalog/furnitura-raznaya-/allyur-seyf.../ — два и более."""
    # Убираем query-параметры
    path = href.split("?")[0]
    # Считаем сегменты после /catalog/
    after_catalog = path.split("/catalog/", 1)
    if len(after_catalog) < 2:
        return True  # вообще нет /catalog/ — не товар
    remainder = after_catalog[1]
    segments = [s for s in remainder.split("/") if s]
    return len(segments) <= 1  # 1 сегмент = категория, 2+ = товар

def extract_data(soup, seen_hrefs):
    items = []
    all_links = soup.find_all("a", href=True)

    for link in all_links:
        href = link["href"]
        text = link.get_text(strip=True)

        if "/catalog/" not in href:
            continue
        if not text or len(text) < 10:
            continue
        if text.lower() in ["подробнее", "купить", "в корзину", "сравнить"]:
            continue
        # ГЛАВНЫЙ ФИЛЬТР: отбрасываем категории
        if is_category(href):
            continue
        # Доп. фильтр: если в тексте есть "(цифра)" — это категория со счётчиком
        if re.search(r"$\d+$", text):
            continue

        full_link = urljoin(BASE_URL, href)
        if full_link in seen_hrefs:
            continue

        # Поднимаемся к ближайшему div с <img>
        card = None
        parent = link.parent
        for _ in range(10):
            if parent is None:
                break
            if parent.name == "div" and parent.find("img"):
                card = parent
                break
            parent = parent.parent

        if card is None:
            continue

        seen_hrefs.add(full_link)
        name = text

        price = "Цена скрыта"
        for el in card.find_all(class_=lambda x: x and "price" in str(x).lower()):
            txt = el.get_text(strip=True)
            if txt and re.search(r"\d", txt):
                price = txt
                break

        availability = "Неизвестно"
        card_text = card.get_text(separator=" ", strip=True).lower()
        if "под заказ" in card_text:
            availability = "Под заказ"
        elif "в наличии" in card_text:
            availability = "В наличии"
        elif "в пути" in card_text:
            availability = "В пути"
        elif "нет в наличии" in card_text:
            availability = "Нет в наличии"

        code = ""
        code_el = card.find(class_=lambda x: x and any(c in str(x).lower() for c in ["code", "art", "articul", "sku"]))
        if code_el:
            code = re.sub(r"^(Арт\.|Код|Артикул):\s*", "", code_el.get_text(strip=True), flags=re.IGNORECASE).strip()

        items.append({
            "name": name,
            "code": code,
            "price": price,
            "availability": availability,
            "link": full_link,
        })

    return items

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        all_items = []
        seen_hrefs = set()
        current_page = 1
        max_pages = 25
        no_items_streak = 0

        while current_page <= max_pages:
            if current_page == 1:
                url = f"{BASE_URL}catalog/?q={keyword}"
            else:
                url = f"{BASE_URL}catalog/?q={keyword}&PAGEN_2={current_page}"

            print(f"\n{'─' * 50}")
            print(f"📄 СТРАНИЦА №{current_page}")
            print(f"{'─' * 50}")

            page.goto(url, wait_until="networkidle", timeout=60000)

            try:
                page.wait_for_selector('a[href*="/catalog/"]', state="attached", timeout=30000)
                page.wait_for_timeout(2000)
            except:
                print("❌ Ссылки не появились.")
                break

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            new_items = extract_data(soup, seen_hrefs)
            all_items.extend(new_items)

            print(f"📦 На странице: {len(new_items)}")
            print(f"📈 Всего: {len(all_items)}")

            if new_items:
                if current_page == 1:
                    for i, item in enumerate(new_items[:5], 1):
                        print(f"   {i}. {item['name'][:70]}")
                        print(f"      {item['availability']} | {item['price']}")
                no_items_streak = 0
            else:
                no_items_streak += 1
                if no_items_streak >= 2:
                    print("🛑 Две страницы без товаров. Конец.")
                    break

            current_page += 1

        browser.close()

        if all_items:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(all_items, f, ensure_ascii=False, indent=2)
            print(f"\n{'═' * 50}")
            print(f"🎉 Готово! Товаров: {len(all_items)}")
            print(f"💾 Файл: {os.path.abspath(OUTPUT_FILE)}")
            print(f"{'═' * 50}")

except KeyboardInterrupt:
    print("\n⚠️ Остановлено.")
except Exception as e:
    print(f"\n❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
