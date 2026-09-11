"""Модуль для фонового парсинга сайтов и автоматического анализа цен."""

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from PyQt6.QtCore import QThread, pyqtSignal


class ParserWorker(QThread):
    """Отдельный поток для парсинга, чтобы интерфейс приложения не зависал."""

    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, target_url: str, brand_keyword: str = ""):
        super().__init__()
        self.target_url = target_url.strip()
        if not self.target_url.endswith("/"):
            self.target_url += "/"
        self.brand_keyword = brand_keyword.strip().lower()
        self.output_file = "citadel_final.json"

    def is_category(self, href):
        """Категория: /catalog/zamki/ — один сегмент после /catalog/.
        Товар: /catalog/furnitura-raznaya-/allyur-seyf.../ — два и более."""
        path = href.split("?")[0]
        after_catalog = path.split("/catalog/", 1)
        if len(after_catalog) < 2:
            return True
        remainder = after_catalog[1]
        segments = [s for s in remainder.split("/") if s]
        return len(segments) <= 1

    def extract_data(self, soup, seen_hrefs):
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
            if self.is_category(href):
                continue
            if re.search(r"$\d+$", text):
                continue

            full_link = urljoin(self.target_url, href)
            if full_link in seen_hrefs:
                continue

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
            code_el = card.find(
                class_=lambda x: x and any(c in str(x).lower() for c in ["code", "art", "articul", "sku"])
            )
            if code_el:
                code = re.sub(
                    r"^(Арт\.|Код|Артикул):\s*", "", code_el.get_text(strip=True), flags=re.IGNORECASE
                ).strip()

            items.append({
                "name": name,
                "code": code,
                "price": price,
                "availability": availability,
                "link": full_link,
            })

        return items

    def run(self) -> None:
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
                        url = f"{self.target_url}catalog/?q={self.brand_keyword}"
                    else:
                        url = f"{self.target_url}catalog/?q={self.brand_keyword}&PAGEN_2={current_page}"

                    self.progress_signal.emit(f"📄 Страница №{current_page}")

                    page.goto(url, wait_until="networkidle", timeout=60000)

                    try:
                        page.wait_for_selector('a[href*="/catalog/"]', state="attached", timeout=30000)
                        page.wait_for_timeout(2000)
                    except PlaywrightTimeoutError:
                        self.progress_signal.emit("❌ Ссылки не появились.")
                        break
                    except Exception as e:
                        self.progress_signal.emit(f"❌ Ошибка ожидания: {e}")
                        break

                    html = page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    new_items = self.extract_data(soup, seen_hrefs)
                    all_items.extend(new_items)

                    self.progress_signal.emit(
                        f"📦 На странице: {len(new_items)} | Всего: {len(all_items)}"
                    )

                    if new_items:
                        no_items_streak = 0
                    else:
                        no_items_streak += 1
                        if no_items_streak >= 2:
                            self.progress_signal.emit("🛑 Две страницы без товаров. Конец.")
                            break

                    current_page += 1

                browser.close()

                if all_items:
                    with open(self.output_file, "w", encoding="utf-8") as f:
                        json.dump(all_items, f, ensure_ascii=False, indent=2)
                    self.progress_signal.emit(f"🎉 Готово! Товаров: {len(all_items)}")
                    self.finished_signal.emit(self.output_file)
                else:
                    self.error_signal.emit("⚠️ Товары не найдены.")

        except KeyboardInterrupt:
            self.error_signal.emit("⚠️ Остановлено.")
        except Exception as e:
            self.error_signal.emit(f"❌ Ошибка: {e}")
