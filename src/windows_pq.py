"""
Главный модуль графического интерфейса пользователя (GUI) на PyQt6.

Данный модуль инициализирует приложение и отрисовывает главное окно,
состоящее из текстовых полей, кнопок управления и панелей вывода данных
с возможностью изменения размеров элементов через QSplitter.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QTextEdit, QLabel,
                             QFrame, QSplitter, QStackedWidget)

from src.auth.api_client import login_to_django
# Импорты из созданных вами пакетов
from src.core.logger import QTextEditHandler


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

        self.zone1 = None
        self.password_input = None
        self.login_input = None
        self.api_url_input = None
        self.btn_toggle_pass = None
        self.btn_send_auth = None

        self.stack = None
        self.page_menu = None
        self.page_auth = None
        self.btn_auth_menu = None  # кнопка Аторизация
        self.btn_request = None  # кнопка Запрос
        self.btn_back = None  # Кнопка возврата в меню

        self.result_display = None
        self.zone2 = None

        self.zone3 = None
        self.log_display = None

        self.init_ui()
        self.connect_signals()

    def init_ui(self):
        """Инициализация, стилизация и компоновка виджетов окна."""
        self.setWindowTitle("ViewHub (взаимодейстсвие по API-интерфейсу")
        self.resize(1000, 700)

        # Основной макет окна
        layout = QVBoxLayout(self)

        # --- СОЗДАЕМ ВЕРХНИЙ СПЛИТТЕР (для Зон 1 и 2) ---
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # =========== Зона 1: Взаимодействие =============
        self.zone1 = QFrame()
        self.zone1.setFrameShape(QFrame.Shape.StyledPanel)
        z1_layout = QVBoxLayout(self.zone1)

        # Создаем контейнер для переключения страниц
        self.stack = QStackedWidget()
        z1_layout.addWidget(self.stack)

        # ==========================================
        # СТРАНИЦА 1: ГЛАВНОЕ МЕНЮ ДЕЙСТВИЙ
        # ==========================================
        self.page_menu = QWidget()
        menu_layout = QVBoxLayout(self.page_menu)
        menu_layout.addWidget(QLabel("<b>Выберите действие:</b>"))

        # Кнопка АВТОРИЗАЦИЯ
        self.btn_auth_menu = QPushButton("АВТОРИЗАЦИЯ")
        menu_layout.addWidget(self.btn_auth_menu)

        self.btn_request = QPushButton("ЗАПРОС")
        menu_layout.addWidget(self.btn_request)

        # Сюда в будущем вы сможете добавить другие большие кнопки:
        # self.btn_import_csv = QPushButton("ИМПОРТ CSV")
        # menu_layout.addWidget(self.btn_import_csv)

        menu_layout.addStretch()
        self.stack.addWidget(self.page_menu)  # Индекс 0 в стопке

        # ==========================================
        # СТРАНИЦА 2: ФОРМА АВТОРИЗАЦИИ
        # ==========================================
        self.page_auth = QWidget()
        auth_layout = QVBoxLayout(self.page_auth)

        # Кнопка "Назад в меню"
        self.btn_back = QPushButton("← Назад")
        auth_layout.addWidget(self.btn_back)

        auth_layout.addWidget(QLabel("<b>Авторизация API</b>"))

        # Поле ввода API URL
        auth_layout.addWidget(QLabel("Адрес API:"))
        self.api_url_input = QLineEdit()
        self.api_url_input.setPlaceholderText("https://your-vps-ip/api/v1")
        auth_layout.addWidget(self.api_url_input)

        # Поле ввода Логина
        auth_layout.addWidget(QLabel("Логин:"))
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("Введите логин")
        auth_layout.addWidget(self.login_input)

        # Поле ввода Пароля + Кнопка (в горизонтальном слое)
        auth_layout.addWidget(QLabel("Пароль:"))
        pass_layout = QHBoxLayout()

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Введите пароль")

        self.btn_toggle_pass = QPushButton("Показать")
        self.btn_toggle_pass.setFixedWidth(70)

        pass_layout.addWidget(self.password_input)
        pass_layout.addWidget(self.btn_toggle_pass)
        auth_layout.addLayout(pass_layout)

        # Главная кнопка действия
        auth_layout.addSpacing(10)
        self.btn_send_auth = QPushButton("Отправить")
        auth_layout.addWidget(self.btn_send_auth)

        auth_layout.addStretch()
        self.stack.addWidget(self.page_auth)  # Индекс 1 в стопке

        # Показываем первую страницу по умолчанию (Меню)
        self.stack.setCurrentIndex(0)

        # =============== Зона 2: Результат ===============
        self.zone2 = QFrame()
        self.zone2.setFrameShape(QFrame.Shape.StyledPanel)
        z2_layout = QVBoxLayout(self.zone2)
        z2_layout.addWidget(QLabel("<b>Данные</b>"))
        self.result_display = QTextEdit()
        z2_layout.addWidget(self.result_display)

        # Добавляем зоны в горизонтальный сплиттер
        top_splitter.addWidget(self.zone1)
        top_splitter.addWidget(self.zone2)
        # Устанавливаем начальные пропорции (1:2)
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 2)

        # --- СОЗДАЕМ ГЛАВНЫЙ ВЕРТИКАЛЬНЫЙ СПЛИТТЕР ---
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # Зона 3: Логирование
        self.zone3 = QFrame()
        self.zone3.setFrameShape(QFrame.Shape.StyledPanel)
        z3_layout = QVBoxLayout(self.zone3)
        z3_layout.addWidget(QLabel("<b>Логирование</b>"))
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("background-color: #f0f0f0;")
        z3_layout.addWidget(self.log_display)

        # Собираем всё вместе
        main_splitter.addWidget(top_splitter)  # Добавляем верхний блок (1 и 2)
        main_splitter.addWidget(self.zone3)  # Добавляем низ (3)

        # Начальное распределение высоты (70% верх, 30% низ)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)

        # Добавляем главный сплиттер в основной макет окна
        layout.addWidget(main_splitter)

        # Подключаем логгер для окна логов
        qt_handler = QTextEditHandler(self.log_display)
        qt_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s]: %(message)s", datefmt="%H:%M:%S"))
        qt_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(qt_handler)

    def on_click(self):
        """
        Обработать нажатие кнопки отправки через внешний API клиент.
        """
        url = self.api_url_input.text().strip()
        username = self.login_input.text().strip()
        password = self.password_input.text()

        # Проверяем заполненность полей
        if not url or not username or not password:
            logger.warning("Заполните все поля для авторизации.")  # Само улетит и в файл, и в окно логов!
            return

        # Информируем пользователя о начале процесса
        pas_mask = "*" * len(password)
        logger.info(f"Отправка запроса на {url}...")  # Автоматически отобразится в логах как [🔄] или [INFO]

        # Окно «Данные/Результат» обновляем напрямую, так как это не лог, а отчет для пользователя
        self.result_display.append(f"Запрос: POST {url}\nТело: username='{username}', password='{pas_mask}'")
        QApplication.processEvents()

        # Вызываем сетевую логику из нашего изолированного модуля
        result = login_to_django(url, username, password)

        # Обрабатываем стандартизированный ответ от модуля api_client
        if result["success"]:
            logger.info(f"УСПЕХ! {result['message']}")
            self.result_display.append(f"Статус: Авторизован.\nТокен: {result['token']}")

            # Очищаем поля ввода
            self.api_url_input.clear()
            self.login_input.clear()
            self.password_input.clear()
        else:
            logger.error(f"{result['message']}")
            if "details" in result:
                self.result_display.append(f"Детали ошибки:\n{result['details']}")
            else:
                self.result_display.append("Статус: Доступ отклонен.")

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

    def connect_signals(self):
        """Подключение обработчиков (слотов) к сигналам виджетов."""
        # Логика переключения страниц
        self.btn_auth_menu.clicked.connect(self.show_auth_page)  # На форму авторизации
        self.btn_back.clicked.connect(self.show_menu_page)  # Назад в меню

        self.btn_send_auth.clicked.connect(self.on_click) # На аутентификацию
        self.btn_toggle_pass.clicked.connect(self.toggle_password_visibility) # На скрыть/показать пароль
