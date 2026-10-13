"""
Главный модуль графического интерфейса пользователя (GUI) на PyQt6.

Данный модуль инициализирует приложение и отрисовывает главное окно,
состоящее из текстовых полей, кнопок управления и панелей вывода данных
с возможностью изменения размеров элементов через QSplitter.
"""

import logging

from contextlib import suppress

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.logger import register_gui_handler
from src.core.resources import load_app_icon
from src.core.styles import (
    BACK_BUTTON_STYLE,
    GLOBAL_STYLE,
    LOG_DISPLAY_STYLE,
    SIDEBAR_STYLE,
    SUBMIT_BUTTON_STYLE,
    CANCEL_BUTTON_STYLE,
    TOGGLE_PWD_VISIBILITY_STYLE,
    EXPORT_BUTTON_STYLE,
    PREVIEW_BUTTON_STYLE,
)
from src.service_modules.auth_service import auth_on_click, request_on_click
from src.service_modules.parsing_service import parsing_on_click, parsing_cancel_on_click, prepare_parsing
from src.service_modules.scanning_service import scanning_on_click, scanning_cancel_on_click
from src.service_modules.export_service import parsing_export_on_click
from src.service_modules.db_viewer_service import parsing_preview_on_click


logger = logging.getLogger(__name__)


class MainWindow(QWidget):
    """
    Главное окно графического интерфейса приложения.

    Класс отвечает за инициализацию пользовательского интерфейса (UI),
    компоновку виджетов ввода/вывода, управление разделителями зон (QSplitter)
    и обработку сигналов от интерактивных элементов (кнопок, текстовых полей).

    Компоненты интерфейса:
        - Поля ввода (QLineEdit): Для настройки конфигурации подключения/путей.
        - Лог-панель (QTextEdit): Для отображения статуса операций и вывода данных.
        - Управление (QPushButton): Кнопки для запуска основных процессов приложения.
        - Контейнеры (QFrame, QSplitter): Для гибкого масштабирования рабочей области.

    Методы (Слоты):
        - init_ui(): Настройка и размещение всех PyQt6 виджетов в слоях.
        - connect_signals(): Привязка событий нажатия кнопок к обработчикам.
    """

    def __init__(self):
        super().__init__()

        self.import_path_input = None
        self.zone1 = None

        # Навигация авторизации
        self.btn_auth_menu = None  # кнопка Аторизация
        self.password_input = None
        self.login_input = None
        self.api_url_input = None
        self.api_request_url_input = None
        self.btn_toggle_pass = None
        self.btn_send_auth = None
        self.btn_back = None  # Кнопка возврата в меню
        self.page_auth = None

        # Навигация настроек
        self.btn_settings_menu = None
        self.btn_back_settings = None
        self.page_settings = None
        # Элементы полей настроек (для примера предустановок)
        self.timeout_input = None
        self.btn_save_settings = None
        self.proxy_url = None

        # Навигация сканирования
        self.btn_scanning_menu = None
        self.base_url_input = None
        self.btn_back_scanning = None
        self.page_scanning = None
        self.btn_send_scanning = None
        self.btn_cancel_scanning = None

        # Навигация парсинга
        self.page_parsing = None
        self.btn_back_parsing = None
        self.target_url_input = None
        self.btn_send_parsing = None
        self.btn_parsing_menu = None
        self.key_word_input = None
        self.btn_cancel_parsing = None
        self.btn_export_parsing = None
        self.btn_preview_parsing = None

        # Навигация запроса
        self.btn_request_menu = None
        self.page_request = None
        self.api_request_url_input = None
        self.btn_back_request = None
        self.btn_send_request = None
        self.btn_request = None  # кнопка Запрос

        self.stack = None
        self.page_menu = None

        self.result_display = None
        self.zone2 = None
        self.db_viewer = None  # Виджет для просмотра таблицы БД

        self.zone3 = None
        self.log_display = None

        # Задаем токен и url для дальнейшей работы
        self.auth_token = None
        self.base_url = None

        # Для экспорта данных парсинга
        self.parser = None
        self.manager = None

        # Инициализация графической оболочки (ОБЯЗАТЕЛЬНО ДО ЛОГГЕРА)
        self.init_ui()
        self.connect_signals()

    def init_ui(self):
        """Инициализация, стилизация и компоновка виджетов окна."""
        self.setWindowIcon(load_app_icon())  # Иконка приложения

        self.setWindowTitle("ViewHub — Интеграция с API")
        self.resize(1100, 750)

        # Применяем глобальный стиль ко всему окну
        self.setStyleSheet(GLOBAL_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # =========== Зона 1: Взаимодействие =============
        self.zone1 = QFrame()
        self.zone1.setStyleSheet(SIDEBAR_STYLE)

        z1_layout = QVBoxLayout(self.zone1)
        z1_layout.setContentsMargins(15, 20, 15, 20)
        z1_layout.setSpacing(15)

        self.stack = QStackedWidget()
        z1_layout.addWidget(self.stack)

        # ==========================================
        # СТРАНИЦА 1: Меню
        # ==========================================
        self.page_menu = QWidget()
        menu_layout = QVBoxLayout(self.page_menu)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(12)

        lbl_title = QLabel("МЕНЮ")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #94a3b8; letter-spacing: 1px;")
        menu_layout.addWidget(lbl_title)

        self.btn_auth_menu = QPushButton("🔐  АВТОРИЗАЦИЯ")
        self.btn_auth_menu.setMinimumHeight(45)
        self.btn_auth_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_layout.addWidget(self.btn_auth_menu)

        self.btn_request_menu = QPushButton("🌐  ЗАПРОС")
        self.btn_request_menu.setMinimumHeight(45)
        self.btn_request_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_layout.addWidget(self.btn_request_menu)

        self.btn_scanning_menu = QPushButton("💀  СКАНИРОВАНИЕ")
        self.btn_scanning_menu.setMinimumHeight(45)
        self.btn_scanning_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_layout.addWidget(self.btn_scanning_menu)

        self.btn_parsing_menu = QPushButton("👽 ПАРСИНГ")
        self.btn_parsing_menu.setMinimumHeight(45)
        self.btn_parsing_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_layout.addWidget(self.btn_parsing_menu)

        self.btn_settings_menu = QPushButton("⚙️  НАСТРОЙКИ")
        self.btn_settings_menu.setMinimumHeight(45)
        self.btn_settings_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_layout.addWidget(self.btn_settings_menu)

        menu_layout.addStretch()
        self.stack.addWidget(self.page_menu)

        # ==========================================
        # СТРАНИЦА 2: АВТОРИЗАЦИЯ
        # ==========================================
        self.page_auth = QWidget()
        auth_layout = QVBoxLayout(self.page_auth)
        auth_layout.setContentsMargins(0, 0, 0, 0)
        auth_layout.setSpacing(10)

        self.btn_back = QPushButton("←  Назад к меню")
        self.btn_back.setStyleSheet(BACK_BUTTON_STYLE)
        auth_layout.addWidget(self.btn_back)
        auth_layout.addSpacing(5)

        lbl_auth_title = QLabel("Авторизация API")
        lbl_auth_title.setStyleSheet("font-weight: bold; font-size: 16px; color: #ffffff;")
        auth_layout.addWidget(lbl_auth_title)

        auth_layout.addWidget(QLabel("Адрес API:"))
        self.api_url_input = QLineEdit()
        self.api_url_input.setPlaceholderText("https://your-vps-ip/api/v1")
        self.api_url_input.setFixedHeight(35)  # Фиксируем высоту
        auth_layout.addWidget(self.api_url_input)

        auth_layout.addWidget(QLabel("Логин:"))
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("Введите логин")
        self.login_input.setFixedHeight(35)  # Фиксируем высоту
        auth_layout.addWidget(self.login_input)

        auth_layout.addWidget(QLabel("Пароль:"))
        pass_layout = QHBoxLayout()
        pass_layout.setSpacing(8)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Введите пароль")
        self.password_input.setFixedHeight(35)  # Фиксируем высоту

        self.btn_toggle_pass = QPushButton("Показать")
        self.btn_toggle_pass.setFixedWidth(75)
        self.btn_toggle_pass.setFixedHeight(35)  # Выравниваем с полем ввода
        self.btn_toggle_pass.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_pass.setStyleSheet(TOGGLE_PWD_VISIBILITY_STYLE)

        pass_layout.addWidget(self.password_input)
        pass_layout.addWidget(self.btn_toggle_pass)
        auth_layout.addLayout(pass_layout)
        auth_layout.addSpacing(15)

        self.btn_send_auth = QPushButton("Войти в систему")
        self.btn_send_auth.setMinimumHeight(42)
        self.btn_send_auth.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send_auth.setStyleSheet(SUBMIT_BUTTON_STYLE)
        auth_layout.addWidget(self.btn_send_auth)

        auth_layout.addStretch()
        self.stack.addWidget(self.page_auth)

        # ==========================================
        # СТРАНИЦА 3: ОКНО ЗАПРОСА
        # ==========================================
        self.page_request = QWidget()
        request_layout = QVBoxLayout(self.page_request)  # ИСПРАВЛЕНО: теперь привязано к self.page_request!
        request_layout.setContentsMargins(0, 0, 0, 0)
        request_layout.setSpacing(10)

        self.btn_back_request = QPushButton("←  Назад к меню")
        self.btn_back_request.setStyleSheet(BACK_BUTTON_STYLE)
        request_layout.addWidget(self.btn_back_request)
        request_layout.addSpacing(5)

        request_layout.addWidget(QLabel("Адрес API:"))
        self.api_request_url_input = QLineEdit()
        self.api_request_url_input.setPlaceholderText("https://your-vps-ip/api/v1")
        self.api_request_url_input.setFixedHeight(35)  # Фиксируем высоту
        request_layout.addWidget(self.api_request_url_input)  # ИСПРАВЛЕНО: добавляем правильный инпут!
        request_layout.addSpacing(5)

        self.btn_send_request = QPushButton("Отправить")
        self.btn_send_request.setMinimumHeight(42)
        self.btn_send_request.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send_request.setStyleSheet(SUBMIT_BUTTON_STYLE)
        request_layout.addWidget(self.btn_send_request)  # ИСПРАВЛЕНО: добавляем в request_layout!

        request_layout.addStretch()
        self.stack.addWidget(self.page_request)

        # ==========================================
        # СТРАНИЦА 4: ОКНО СКАНИРОВАНИЯ
        # ==========================================
        self.page_scanning = QWidget()
        scanning_layout = QVBoxLayout(self.page_scanning)
        scanning_layout.setContentsMargins(0, 0, 0, 0)
        scanning_layout.setSpacing(5)

        self.btn_back_scanning = QPushButton("←  Назад к меню")
        self.btn_back_scanning.setStyleSheet(BACK_BUTTON_STYLE)
        scanning_layout.addWidget(self.btn_back_scanning)
        scanning_layout.addSpacing(5)

        scanning_layout.addWidget(QLabel("Базовый URL:"))
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://base-url")
        self.base_url_input.setFixedHeight(35)
        scanning_layout.addWidget(self.base_url_input)
        scanning_layout.addSpacing(5)

        self.btn_send_scanning = QPushButton("НАЧАТЬ")
        self.btn_send_scanning.setMinimumHeight(42)
        self.btn_send_scanning.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send_scanning.setStyleSheet(SUBMIT_BUTTON_STYLE)
        scanning_layout.addWidget(self.btn_send_scanning)

        self.btn_cancel_scanning = QPushButton("ОТМЕНИТЬ")
        self.btn_cancel_scanning.setMinimumHeight(42)
        self.btn_cancel_scanning.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel_scanning.setStyleSheet(CANCEL_BUTTON_STYLE)
        scanning_layout.addWidget(self.btn_cancel_scanning)

        scanning_layout.addStretch()
        self.stack.addWidget(self.page_scanning)

        # ==========================================
        # СТРАНИЦА 5: ОКНО ПАРСИНГА
        # ==========================================
        self.page_parsing = QWidget()
        parsing_layout = QVBoxLayout(self.page_parsing)
        parsing_layout.setContentsMargins(0, 0, 0, 0)
        parsing_layout.setSpacing(5)

        self.btn_back_parsing = QPushButton("←  Назад к меню")
        self.btn_back_parsing.setStyleSheet(BACK_BUTTON_STYLE)
        parsing_layout.addWidget(self.btn_back_parsing)
        parsing_layout.addSpacing(5)

        parsing_layout.addWidget(QLabel("Целевой URL:"))
        self.target_url_input = QLineEdit()
        # self.target_url_input.setPlaceholderText("https://target-url")
        # Предустанавливаем значение вместо плейсхолдера
        self.target_url_input.setText("https://goldapple.ru/")
        # Замораживаем ввод (пользователь сможет выделить и скопировать текст, но не изменить)
        self.target_url_input.setReadOnly(True)
        self.target_url_input.setFixedHeight(35)
        parsing_layout.addWidget(self.target_url_input)
        parsing_layout.addSpacing(5)

        parsing_layout.addWidget(QLabel("Ключевая фраза или раздел каталога:"))
        self.key_word_input = QLineEdit()
        self.key_word_input.setPlaceholderText("Key word")
        self.key_word_input.setFixedHeight(35)
        parsing_layout.addWidget(self.key_word_input)
        parsing_layout.addSpacing(5)

        self.btn_send_parsing = QPushButton("НАЧАТЬ")
        self.btn_send_parsing.setMinimumHeight(42)
        self.btn_send_parsing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send_parsing.setStyleSheet(SUBMIT_BUTTON_STYLE)
        parsing_layout.addWidget(self.btn_send_parsing)

        self.btn_cancel_parsing = QPushButton("ОТМЕНИТЬ")
        self.btn_cancel_parsing.setMinimumHeight(42)
        self.btn_cancel_parsing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel_parsing.setStyleSheet(CANCEL_BUTTON_STYLE)
        self.btn_cancel_parsing.setEnabled(False)  # Отключена по умолчанию
        parsing_layout.addWidget(self.btn_cancel_parsing)

        self.btn_preview_parsing = QPushButton("ПРОСМОТР")
        self.btn_preview_parsing.setMinimumHeight(42)
        self.btn_preview_parsing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview_parsing.setStyleSheet(PREVIEW_BUTTON_STYLE)
        self.btn_preview_parsing.setEnabled(False)  # Отключена по умолчанию
        parsing_layout.addWidget(self.btn_preview_parsing)

        self.btn_export_parsing = QPushButton("ЭКСПОРТ")
        self.btn_export_parsing.setMinimumHeight(42)
        self.btn_export_parsing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_parsing.setStyleSheet(EXPORT_BUTTON_STYLE)
        self.btn_export_parsing.setEnabled(False)  # Отключена по умолчанию
        parsing_layout.addWidget(self.btn_export_parsing)

        parsing_layout.addStretch()
        self.stack.addWidget(self.page_parsing)

        # ==========================================
        # СТРАНИЦА 6: ОКНО НАСТРОЕК
        # ==========================================
        self.page_settings = QWidget()
        settings_layout = QVBoxLayout(self.page_settings)  # Исправлено: привязка к self.page_settings
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(10)

        self.btn_back_settings = QPushButton("←  Назад к меню")
        self.btn_back_settings.setStyleSheet(BACK_BUTTON_STYLE)
        settings_layout.addWidget(self.btn_back_settings)
        settings_layout.addSpacing(5)

        lbl_settings_title = QLabel("Настройки системы")
        lbl_settings_title.setStyleSheet("font-weight: bold; font-size: 16px; color: #ffffff;")
        settings_layout.addWidget(lbl_settings_title)
        settings_layout.addSpacing(5)

        settings_layout.addWidget(QLabel("Таймаут запросов (сек):"))
        self.timeout_input = QLineEdit()
        self.timeout_input.setPlaceholderText("10")
        self.timeout_input.setText("")
        self.timeout_input.setFixedHeight(35)  # Фиксируем высоту
        settings_layout.addWidget(self.timeout_input)

        settings_layout.addWidget(QLabel("Загрузить базовую конфигурацию"))
        self.import_path_input = QLineEdit()
        self.import_path_input.setPlaceholderText("table_shema")
        self.import_path_input.setText("")
        self.import_path_input.setFixedHeight(35)  # Фиксируем высоту
        settings_layout.addWidget(self.import_path_input)

        settings_layout.addWidget(QLabel("Прокси адрес:"))
        self.proxy_url = QLineEdit()
        self.proxy_url.setPlaceholderText("176.15.164.69")
        self.proxy_url.setFixedHeight(35)  # Фиксируем высоту
        settings_layout.addWidget(self.proxy_url)

        settings_layout.addSpacing(15)
        self.btn_save_settings = QPushButton("Сохранить конфигурацию")
        self.btn_save_settings.setMinimumHeight(42)
        self.btn_save_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_settings.setStyleSheet(SUBMIT_BUTTON_STYLE)
        settings_layout.addWidget(self.btn_save_settings)

        settings_layout.addStretch()
        self.stack.addWidget(self.page_settings)

        # =============== Зона 2: Результат ===============
        self.zone2 = QFrame()
        self.zone2.setStyleSheet("QFrame { background-color: #f8fafc; border-radius: 8px; }")
        z2_layout = QVBoxLayout(self.zone2)
        z2_layout.setContentsMargins(15, 15, 15, 15)

        lbl_data_title = QLabel("<b>📋 ВЫВОД ДАННЫХ</b>")
        lbl_data_title.setStyleSheet("color: #64748b; font-size: 12px; letter-spacing: 0.5px;")
        z2_layout.addWidget(lbl_data_title)

        self.result_display = QTextEdit()
        self.result_display.setPlaceholderText("Здесь будет отображаться текущая справочная информация...")
        z2_layout.addWidget(self.result_display)

        top_splitter.addWidget(self.zone1)
        top_splitter.addWidget(self.zone2)
        top_splitter.setStretchFactor(0, 0)  # zone1 фиксированной ширины
        top_splitter.setStretchFactor(1, 1)  # zone2 занимает всё оставшееся пространство
        top_splitter.setSizes([350, 750])  # Фиксированная ширина zone1 = 350px

        # --- СОЗДАЕМ ГЛАВНЫЙ ВЕРТИКАЛЬНЫЙ СПЛИТТЕР ---
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # =============== Зона 3: Логирование ===============
        self.zone3 = QFrame()
        self.zone3.setStyleSheet("QFrame { background-color: #f8fafc; border-radius: 8px; }")
        z3_layout = QVBoxLayout(self.zone3)
        z3_layout.setContentsMargins(15, 15, 15, 15)

        lbl_log_title = QLabel("<b>🛠️ СИСТЕМНЫЙ ЖУРНАЛ</b>")
        lbl_log_title.setStyleSheet("color: #64748b; font-size: 12px; letter-spacing: 0.5px;")
        z3_layout.addWidget(lbl_log_title)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        # Применяем стиль для темной консоли
        self.log_display.setStyleSheet(LOG_DISPLAY_STYLE)
        z3_layout.addWidget(self.log_display)

        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(self.zone3)
        main_splitter.setStretchFactor(0, 65)
        main_splitter.setStretchFactor(1, 35)

        layout.addWidget(main_splitter)

        # Подключаем логгер для окна логов
        register_gui_handler(self.log_display, level=logging.INFO)

    def on_save_settings_click(self):
        """
        Обработать сохранение предустановок приложения.
        """
        timeout_val = self.timeout_input.text().strip()
        path_val = self.import_path_input.text().strip()

        logger.info(f"Конфигурация обновлена: Таймаут={timeout_val}с, Путь импорта='{path_val}'")
        self.result_display.append(
            f"[⚙️ CONFIG] Успешно сохранены предустановки:"
            f"\n- Network Timeout: {timeout_val} seconds\n- Data Directory: {path_val}"
        )

        # После сохранения красиво возвращаем пользователя в меню
        self.show_menu_page()

    def toggle_password_visibility(self):
        """Переключает видимость пароля между точками и обычным текстом."""
        if self.password_input.echoMode() == QLineEdit.EchoMode.Password:
            # Переключаем на отображение обычного текста
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_pass.setText("Скрыть")
        else:
            # Снова скрываем в точки
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_pass.setText("Показать")

    def show_auth_page(self):
        """Открыть страницу авторизации."""
        self.stack.setCurrentIndex(1)  # Переключаем на индекс формы (1)

    def show_menu_page(self):
        """Вернуться на главную страницу меню."""
        self.stack.setCurrentIndex(0)  # Возвращаем на индекс меню (0)

    def show_request_page(self):
        """Открыть страницу запроса."""
        self.stack.setCurrentIndex(2)  # Возвращаем на индекс запроса (2)

    def show_scanning_page(self):
        """Открыть страницу сканирования."""
        self.stack.setCurrentIndex(3)  # Возвращаем на индекс сканирования (3)

    def show_parsing_page(self):
        """Открытие меню парсинга."""
        # Парсер продолжает работать, пока пользователь ходит по другим
        # разделам. Создавать поверх него новый нельзя: старый поток продолжит
        # писать в ту же базу, а его воркер и лог окажутся заменены — отменять
        # и читать журнал было бы уже нечего. Кнопка «НАЧАТЬ» и так заблокирована
        # на время прогона, здесь нужно только не создавать дубль.
        if self._thread_is_alive():
            self.stack.setCurrentIndex(4)
            # append, а не setText: панель вывода жива, в ней идёт прогресс.
            self.result_display.append(
                "ℹ️ Парсинг уже идёт в фоне. Новый запуск станет доступен после "
                "его завершения или остановки кнопкой «ОТМЕНИТЬ»."
            )
            return

        try:
            # Запускаем функцию сборки парсера
            prepare_parsing(self)

            # ЕСЛИ ВСЁ ОК: только теперь перекидываем пользователя в меню парсинга (индекс 4)
            self.stack.setCurrentIndex(4)

            # Выводим готовое описание парсера на новый экран
            self.result_display.setText(f"🔔 ОПИСАНИЕ\n{self.parser.description}\n\n")

        except (ValueError, RuntimeError) as e:
            # Закрываем менеджер напрямую через self, если он успел создаться
            if getattr(self, "manager", None) is not None:
                with suppress(Exception):
                    self.manager.close()
            # Тотальное обнуление для чистоты системы
            self.manager = None
            self.parser = None
            self.result_display.setText(
                f"⚠️ Внимание\n❌ {e!s}\n\nПожалуйста, устраните проблему и нажмите кнопку 'Парсинг' еще раз."
            )

    def _thread_is_alive(self) -> bool:
        """Жив ли поток парсинга, с учётом того, что он мог быть удалён.

        После завершения прогона QThread удаляется через deleteLater,
        но атрибут self.parser_thread продолжает ссылаться на оболочку
        удалённого объекта C++. Обращение к такому объекту бросает
        RuntimeError, поэтому проверять isRunning на него нельзя.
        """
        thread = getattr(self, "parser_thread", None)
        if thread is None:
            return False
        try:
            return bool(thread.isRunning())
        except RuntimeError:
            # Объект C++ уже удалён: поток завершён, осталась только ссылка.
            self.parser_thread = None
            return False

    def closeEvent(self, event):
        """
        Корректно закрывает окно во время работающего парсинга.

        Без этого Qt уничтожает живой QThread и приложение падает с
        «QThread: Destroyed while thread is still running».
        """
        if self._thread_is_alive():
            logger.info("Закрытие окна во время парсинга: останавливаем поток.")

            with suppress(Exception):
                self.parser_worker.stop()

            with suppress(Exception):
                self.parser_thread.quit()
                # Ждём до 15 секунд: этого хватает, чтобы доехать до ближайшей
                # проверки флага отмены в цикле парсера.
                self.parser_thread.wait(15000)

        event.accept()

    def show_settings_page(self):
        """Переключить стек на страницу настроек (Индекс 2)."""
        self.stack.setCurrentIndex(5)  # Возвращаем на индекс парсинга (5)

    def connect_signals(self):
        """Подключение обработчиков (слотов) к сигналам виджетов."""
        # Логика переключения страниц
        # Авторизация
        self.btn_auth_menu.clicked.connect(self.show_auth_page)  # На форму авторизации
        self.btn_back.clicked.connect(self.show_menu_page)  # Назад в меню
        self.btn_toggle_pass.clicked.connect(self.toggle_password_visibility)  # На скрыть/показать пароль
        self.btn_send_auth.clicked.connect(lambda: auth_on_click(self))  # На аутентификацию

        # Запрос
        self.btn_request_menu.clicked.connect(self.show_request_page)  # На форму запроса
        self.btn_back_request.clicked.connect(self.show_menu_page)  # Назад в меню
        self.btn_send_request.clicked.connect(lambda: request_on_click(self))  # На запрос по API

        # Сканирование
        self.btn_scanning_menu.clicked.connect(self.show_scanning_page)  # На форму сканирования
        self.btn_back_scanning.clicked.connect(self.show_menu_page)  # Назад в меню
        self.btn_send_scanning.clicked.connect(lambda: scanning_on_click(self))  # На сканирование
        self.btn_cancel_scanning.clicked.connect(lambda: scanning_cancel_on_click(self))  # Отмена сканирования

        # Парсинг
        self.btn_parsing_menu.clicked.connect(self.show_parsing_page)  # На форму парсинга
        self.btn_back_parsing.clicked.connect(self.show_menu_page)  # Назад в меню
        self.btn_send_parsing.clicked.connect(lambda: parsing_on_click(self))  # На парсинг
        self.btn_cancel_parsing.clicked.connect(lambda: parsing_cancel_on_click(self))  # Отмена парсинга
        self.btn_export_parsing.clicked.connect(lambda: parsing_export_on_click(self))  # Экспорт парсинга
        self.btn_preview_parsing.clicked.connect(lambda: parsing_preview_on_click(self))  # Просмотр парсинга

        # Настройки
        self.btn_settings_menu.clicked.connect(self.show_settings_page)  # На форму настроек
        self.btn_back_settings.clicked.connect(self.show_menu_page)
        self.btn_save_settings.clicked.connect(self.on_save_settings_click)
