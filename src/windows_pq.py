"""
Главный модуль графического интерфейса пользователя (GUI) на PyQt6.

Данный модуль инициализирует приложение и отрисовывает главное окно,
состоящее из текстовых полей, кнопок управления и панелей вывода данных
с возможностью изменения размеров элементов через QSplitter.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QTextEdit, QLabel,
                             QFrame, QSplitter, QStackedWidget)

from src.core.logger import QTextEditHandler
from src.core.resources import load_app_icon
from src.core.styles import (GLOBAL_STYLE, SIDEBAR_STYLE, BACK_BUTTON_STYLE,
                             TOGGLE_PASS_BUTTON_STYLE, SUBMIT_BUTTON_STYLE, LOG_DISPLAY_STYLE)
from src.services import auth_on_click, request_on_click, scanning_on_click

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

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

        # Навигация сканирования
        self.btn_scanning_menu = None
        self.base_url_input = None
        self.btn_back_scanning = None
        self.page_scanning = None
        self.btn_send_scanning = None

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

        self.zone3 = None
        self.log_display = None

        self.init_ui()
        self.connect_signals()

        # Задаем токен и url для дальнейшей работы
        self.auth_token = None
        self.base_url = None

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

        lbl_title = QLabel("МЕНЮ ДЕЙСТВИЙ")
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

        self.btn_scanning_menu = QPushButton("📡  СКАНИРОВАНИЕ")
        self.btn_scanning_menu.setMinimumHeight(45)
        self.btn_scanning_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_layout.addWidget(self.btn_scanning_menu)

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
        self.btn_toggle_pass.setStyleSheet(TOGGLE_PASS_BUTTON_STYLE)

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
        # СТРАНИЦА 3: ОКНО НАСТРОЕК
        # ==========================================
        self.page_settings = QWidget()
        settings_layout = QVBoxLayout(self.page_settings)  # Исправлено: привязка к self.page_settings
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(10)

        self.btn_back_settings = QPushButton("←  Назад к меню")
        self.btn_back_settings.setStyleSheet(BACK_BUTTON_STYLE)
        settings_layout.addWidget(self.btn_back_settings)
        settings_layout.addSpacing(5)

        lbl_settings_title = QLabel("Предустановки системы")
        lbl_settings_title.setStyleSheet("font-weight: bold; font-size: 16px; color: #ffffff;")
        settings_layout.addWidget(lbl_settings_title)
        settings_layout.addSpacing(5)

        settings_layout.addWidget(QLabel("Таймаут запросов (сек):"))
        self.timeout_input = QLineEdit()
        self.timeout_input.setPlaceholderText("7")
        self.timeout_input.setText("7")
        self.timeout_input.setFixedHeight(35)  # Фиксируем высоту
        settings_layout.addWidget(self.timeout_input)

        settings_layout.addWidget(QLabel("Папка импорта данных:"))
        self.import_path_input = QLineEdit()
        self.import_path_input.setPlaceholderText("./logs")
        self.import_path_input.setFixedHeight(35)  # Фиксируем высоту
        settings_layout.addWidget(self.import_path_input)

        settings_layout.addSpacing(15)
        self.btn_save_settings = QPushButton("Сохранить конфигурацию")
        self.btn_save_settings.setMinimumHeight(42)
        self.btn_save_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_settings.setStyleSheet(SUBMIT_BUTTON_STYLE)
        settings_layout.addWidget(self.btn_save_settings)

        settings_layout.addStretch()
        self.stack.addWidget(self.page_settings)

        # ==========================================
        # СТРАНИЦА 4: ОКНО ЗАПРОСА
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
        # СТРАНИЦА 5: ОКНО СКАНИРОВАНИЯ
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
        scanning_layout.addWidget(self.btn_send_scanning)  # ИСПРАВЛЕНО: добавляем в request_layout!

        scanning_layout.addStretch()
        self.stack.addWidget(self.page_scanning)

        # =============== Зона 2: Результат ===============
        self.zone2 = QFrame()
        self.zone2.setStyleSheet("QFrame { background-color: #f8fafc; border-radius: 8px; }")
        z2_layout = QVBoxLayout(self.zone2)
        z2_layout.setContentsMargins(15, 15, 15, 15)

        lbl_data_title = QLabel("<b>📋 ПАНЕЛЬ ВЫВОДА ДАННЫХ</b>")
        lbl_data_title.setStyleSheet("color: #64748b; font-size: 12px; letter-spacing: 0.5px;")
        z2_layout.addWidget(lbl_data_title)

        self.result_display = QTextEdit()
        self.result_display.setPlaceholderText("Здесь будут отображаться структурированные ответы от Django API...")
        z2_layout.addWidget(self.result_display)

        top_splitter.addWidget(self.zone1)
        top_splitter.addWidget(self.zone2)
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 2)

        # --- СОЗДАЕМ ГЛАВНЫЙ ВЕРТИКАЛЬНЫЙ СПЛИТТЕР ---
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # =============== Зона 3: Логирование ===============
        self.zone3 = QFrame()
        self.zone3.setStyleSheet("QFrame { background-color: #f8fafc; border-radius: 8px; }")
        z3_layout = QVBoxLayout(self.zone3)
        z3_layout.setContentsMargins(15, 15, 15, 15)

        lbl_log_title = QLabel("<b>🛠️ СИСТЕМНЫЙ ЖУРНАЛ (ЛОГИ)</b>")
        lbl_log_title.setStyleSheet("color: #64748b; font-size: 12px; letter-spacing: 0.5px;")
        z3_layout.addWidget(lbl_log_title)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        # Применяем стиль для темной консоли
        self.log_display.setStyleSheet(LOG_DISPLAY_STYLE)
        z3_layout.addWidget(self.log_display)

        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(self.zone3)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)

        layout.addWidget(main_splitter)

        # Подключаем логгер для окна логов
        qt_handler = QTextEditHandler(self.log_display)
        qt_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s]: %(message)s", datefmt="%H:%M:%S"))
        qt_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(qt_handler)

    def show_settings_page(self):
        """Переключить стек на страницу настроек (Индекс 2)."""
        self.stack.setCurrentIndex(2)

    def on_save_settings_click(self):
        """
        Обработать сохранение предустановок приложения.
        """
        timeout_val = self.timeout_input.text().strip()
        path_val = self.import_path_input.text().strip()

        logger.info(f"Конфигурация обновлена: Таймаут={timeout_val}с, Путь импорта='{path_val}'")
        self.result_display.append(
            f"[⚙️ CONFIG] Успешно сохранены предустановки:\n- Network Timeout: {timeout_val} seconds\n- Data Directory: {path_val}")

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
        self.stack.setCurrentIndex(3) # Возвращаем на индекс запроса (3)

    def show_scanning_page(self):
        """Открыть страницу сканирования."""
        self.stack.setCurrentIndex(4) # Возвращаем на индекс сканирования (3)


    def connect_signals(self):
        """Подключение обработчиков (слотов) к сигналам виджетов."""
        # Логика переключения страниц
        # Авторизация
        self.btn_auth_menu.clicked.connect(self.show_auth_page)  # На форму авторизации
        self.btn_back.clicked.connect(self.show_menu_page)  # Назад в меню
        self.btn_toggle_pass.clicked.connect(self.toggle_password_visibility)  # На скрыть/показать пароль
        self.btn_send_auth.clicked.connect(lambda: auth_on_click(self)) # На аутентификацию

        # Запрос
        self.btn_request_menu.clicked.connect(self.show_request_page)  # На форму запроса
        self.btn_back_request.clicked.connect(self.show_menu_page)  # Назад в меню
        self.btn_send_request.clicked.connect(lambda: request_on_click(self)) #На запрос по API

        # Сканирование
        self.btn_scanning_menu.clicked.connect(self.show_scanning_page)  # На форму сканирования
        self.btn_back_scanning.clicked.connect(self.show_menu_page)  # Назад в меню
        self.btn_send_scanning.clicked.connect(lambda: scanning_on_click(self))  # На сканирование

        # Настройки
        self.btn_settings_menu.clicked.connect(self.show_settings_page) # На форму настроек
        self.btn_back_settings.clicked.connect(self.show_menu_page)
        self.btn_save_settings.clicked.connect(self.on_save_settings_click)
