"""
Главный модуль графического интерфейса пользователя (GUI) на PyQt6.

Данный модуль инициализирует приложение и отрисовывает главное окно,
состоящее из текстовых полей, кнопок управления и панелей вывода данных
с возможностью изменения размеров элементов через QSplitter.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLineEdit, QPushButton, QTextEdit, QLabel,
                             QFrame, QSplitter)


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
        self.log_display = None
        self.zone3 = None
        self.result_display = None
        self.zone2 = None
        self.btn = None
        self.input_field = None
        self.zone1 = None

        self.init_ui()
        self.connect_signals()


    def init_ui(self):
        """Инициализация, стилизация и компоновка виджетов окна."""
        self.setWindowTitle("Интерфейс с раздвижными зонами")
        self.resize(1000, 700)

        # Основной макет окна
        layout = QVBoxLayout(self)

        # --- СОЗДАЕМ ВЕРХНИЙ СПЛИТТЕР (для Зон 1 и 2) ---
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Зона 1: Взаимодействие
        self.zone1 = QFrame()
        self.zone1.setFrameShape(QFrame.Shape.StyledPanel)
        z1_layout = QVBoxLayout(self.zone1)
        z1_layout.addWidget(QLabel("<b>1 - Взаимодействие</b>"))
        self.input_field = QLineEdit()
        z1_layout.addWidget(self.input_field)
        self.btn = QPushButton("Обработать")
        z1_layout.addWidget(self.btn)
        z1_layout.addStretch()

        # Зона 2: Результат
        self.zone2 = QFrame()
        self.zone2.setFrameShape(QFrame.Shape.StyledPanel)
        z2_layout = QVBoxLayout(self.zone2)
        z2_layout.addWidget(QLabel("<b>2 - Результат</b>"))
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
        z3_layout.addWidget(QLabel("<b>3 - Логирование</b>"))
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("background-color: #f0f0f0;")
        z3_layout.addWidget(self.log_display)

        # Собираем всё вместе
        main_splitter.addWidget(top_splitter) # Добавляем верхний блок (1 и 2)
        main_splitter.addWidget(self.zone3)    # Добавляем низ (3)

        # Начальное распределение высоты (70% верх, 30% низ)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)

        # Добавляем главный сплиттер в основной макет окна
        layout.addWidget(main_splitter)

        # Логика кнопки
        self.btn.clicked.connect(self.on_click)

    def on_click(self):
        """
        Обработать нажатие кнопки для отправки введенного текста.

        Считывает строку из поля ввода, проверяет её на пустоту и,
        в случае успеха, выводит данные в панели результатов и логов,
        после чего очищает поле ввода.
        """
        txt = self.input_field.text()
        if txt:
            self.result_display.append(f"Вы ввели: {txt}")
            self.log_display.append(f"[OK] Данные приняты: {txt}")
            self.input_field.clear()

    def connect_signals(self):
        """Подключение обработчиков (слотов) к сигналам виджетов."""
        # self.button.clicked.connect(self.on_button_click)
        pass