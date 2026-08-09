"""
Модуль централизованного управления стилями (QSS) приложения ViewHub.
"""

# Глобальные стили для всего приложения (окна, поля ввода, дефолтные кнопки)
GLOBAL_STYLE = """
    QWidget {
        font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
        font-size: 13px;
        color: #2c3e50;
    }
    /* Стилизация разделителей зон */
    QSplitter::handle {
        background-color: #dcdde1;
    }
    QSplitter::handle:horizontal {
        width: 4px;
    }
    QSplitter::handle:vertical {
        height: 4px;
    }
    /* Поля ввода */
    QLineEdit {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 8px 12px;
        selection-background-color: #3b82f6;
    }
    QLineEdit:focus {
        border: 1px solid #3b82f6;
    }
    /* Стандартные кнопки */
    QPushButton {
        background-color: #3b82f6;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 10px 16px;
        font-weight: 600;
    }
    QPushButton:hover {
        background-color: #2563eb;
    }
    QPushButton:pressed {
        background-color: #1d4ed8;
    }
    /* Текстовые поля вывода данных */
    QTextEdit {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 10px;
    }
"""

# Стиль для боковой панели (Зона 1)
SIDEBAR_STYLE = """
    QFrame {
        background-color: #1e293b;
        border-radius: 8px;
    }
    QLabel {
        color: #f8fafc;
    }
    QPushButton {
        background-color: #334155;
        color: #f8fafc;
    }
    QPushButton:hover {
        background-color: #475569;
    }
    QPushButton:pressed {
        background-color: #1e293b;
        border: 1px solid #475569;
    }
"""

# Стиль кнопки возврата "Назад"
BACK_BUTTON_STYLE = """
    QPushButton { 
        background-color: transparent; 
        color: #94a3b8; 
        border: none; 
        text-align: left; 
        padding: 5px 0px; 
    }
    QPushButton:hover { 
        color: #f8fafc; 
    }
"""

# Стиль компактной кнопки "Показать" пароль
TOGGLE_PASS_BUTTON_STYLE = "background-color: #475569; font-size: 11px; padding: 8px 5px;"

# Зеленая акцентная кнопка "Войти"
SUBMIT_BUTTON_STYLE = "background-color: #10b981; color: white;"

# Темный "хакерский" стиль для консоли логов (Зона 3)
LOG_DISPLAY_STYLE = """
    QTextEdit { 
        background-color: #0f172a; 
        color: #38bdf8; 
        font-family: 'Consolas', 'Courier New', monospace; 
        font-size: 12px;
        border: 1px solid #1e293b;
    }
"""
