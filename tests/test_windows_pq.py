"""
Тесты для модуля графического интерфейса windows_pq.py.

Проверяет инициализацию UI, навигацию между страницами,
подключение сигналов и базовую логику MainWindow.
"""

import pytest
from PyQt6.QtWidgets import QLineEdit

from src.windows_pq import MainWindow


@pytest.fixture
def main_window(qtbot):
    """Создает экземпляр MainWindow для тестирования."""
    window = MainWindow()
    qtbot.addWidget(window)
    return window


class TestMainWindowInit:
    """Тесты инициализации главного окна."""

    def test_window_creation(self, main_window):
        """Проверяет, что окно создается с корректными базовыми параметрами."""
        assert main_window.windowTitle() == "ViewHub — Интеграция с API"
        assert main_window.width() == 1100
        assert main_window.height() == 750

    def test_zone1_initialized(self, main_window):
        """Проверяет инициализацию зоны 1 (боковая панель)."""
        assert main_window.zone1 is not None
        assert main_window.stack is not None

    def test_zone2_initialized(self, main_window):
        """Проверяет инициализацию зоны 2 (панель вывода данных)."""
        assert main_window.zone2 is not None
        assert main_window.result_display is not None

    def test_zone3_initialized(self, main_window):
        """Проверяет инициализацию зоны 3 (панель логирования)."""
        assert main_window.zone3 is not None
        assert main_window.log_display is not None
        assert main_window.log_display.isReadOnly()

    def test_menu_buttons_initialized(self, main_window):
        """Проверяет инициализацию кнопок меню."""
        assert main_window.btn_auth_menu is not None
        assert main_window.btn_request_menu is not None
        assert main_window.btn_scanning_menu is not None
        assert main_window.btn_parsing_menu is not None
        assert main_window.btn_settings_menu is not None

    def test_auth_page_initialized(self, main_window):
        """Проверяет инициализацию страницы авторизации."""
        assert main_window.page_auth is not None
        assert main_window.api_url_input is not None
        assert main_window.login_input is not None
        assert main_window.password_input is not None
        assert main_window.btn_toggle_pass is not None
        assert main_window.btn_send_auth is not None
        assert main_window.btn_back is not None

    def test_request_page_initialized(self, main_window):
        """Проверяет инициализацию страницы запроса."""
        assert main_window.page_request is not None
        assert main_window.api_request_url_input is not None
        assert main_window.btn_send_request is not None
        assert main_window.btn_back_request is not None

    def test_scanning_page_initialized(self, main_window):
        """Проверяет инициализацию страницы сканирования."""
        assert main_window.page_scanning is not None
        assert main_window.base_url_input is not None
        assert main_window.btn_send_scanning is not None
        assert main_window.btn_cancel_scanning is not None
        assert main_window.btn_back_scanning is not None

    def test_parsing_page_initialized(self, main_window):
        """Проверяет инициализацию страницы парсинга."""
        assert main_window.page_parsing is not None
        assert main_window.target_url_input is not None
        assert main_window.key_word_input is not None
        assert main_window.btn_send_parsing is not None
        assert main_window.btn_cancel_parsing is not None
        assert main_window.btn_export_parsing is not None
        assert main_window.btn_preview_parsing is not None
        assert main_window.btn_back_parsing is not None

    def test_settings_page_initialized(self, main_window):
        """Проверяет инициализацию страницы настроек."""
        assert main_window.page_settings is not None
        assert main_window.timeout_input is not None
        assert main_window.import_path_input is not None
        assert main_window.proxy_url is not None
        assert main_window.btn_save_settings is not None
        assert main_window.btn_back_settings is not None


class TestNavigation:
    """Тесты навигации между страницами."""

    def test_show_menu_page(self, main_window):
        """Проверяет переход на страницу меню."""
        main_window.show_menu_page()
        assert main_window.stack.currentIndex() == 0

    def test_show_auth_page(self, main_window):
        """Проверяет переход на страницу авторизации."""
        main_window.show_auth_page()
        assert main_window.stack.currentIndex() == 1

    def test_show_request_page(self, main_window):
        """Проверяет переход на страницу запроса."""
        main_window.show_request_page()
        assert main_window.stack.currentIndex() == 2

    def test_show_scanning_page(self, main_window):
        """Проверяет переход на страницу сканирования."""
        main_window.show_scanning_page()
        assert main_window.stack.currentIndex() == 3

    def test_show_parsing_page(self, main_window):
        """Проверяет переход на страницу парсинга."""
        main_window.show_parsing_page()
        assert main_window.stack.currentIndex() == 4

    def test_show_settings_page(self, main_window):
        """Проверяет переход на страницу настроек."""
        main_window.show_settings_page()
        assert main_window.stack.currentIndex() == 5

    def test_navigation_sequence(self, main_window):
        """Проверяет последовательную навигацию между страницами."""
        main_window.show_auth_page()
        assert main_window.stack.currentIndex() == 1

        main_window.show_menu_page()
        assert main_window.stack.currentIndex() == 0

        main_window.show_scanning_page()
        assert main_window.stack.currentIndex() == 3

        main_window.show_menu_page()
        assert main_window.stack.currentIndex() == 0

        main_window.show_parsing_page()
        assert main_window.stack.currentIndex() == 4


class TestPasswordToggle:
    """Тесты переключения видимости пароля."""

    def test_password_initially_hidden(self, main_window):
        """Проверяет, что пароль изначально скрыт (точками)."""
        assert main_window.password_input.echoMode() == QLineEdit.EchoMode.Password
        assert main_window.btn_toggle_pass.text() == "Показать"

    def test_toggle_password_to_visible(self, main_window):
        """Проверяет переключение пароля в видимый режим."""
        main_window.toggle_password_visibility()
        assert main_window.password_input.echoMode() == QLineEdit.EchoMode.Normal
        assert main_window.btn_toggle_pass.text() == "Скрыть"

    def test_toggle_password_back_to_hidden(self, main_window):
        """Проверяет переключение пароля обратно в скрытый режим."""
        main_window.toggle_password_visibility()
        main_window.toggle_password_visibility()
        assert main_window.password_input.echoMode() == QLineEdit.EchoMode.Password
        assert main_window.btn_toggle_pass.text() == "Показать"

    def test_multiple_password_toggles(self, main_window):
        """Проверяет многократное переключение видимости пароля."""
        for _ in range(5):
            main_window.toggle_password_visibility()

        # После нечетного количества переключений должен быть видимый
        assert main_window.password_input.echoMode() == QLineEdit.EchoMode.Normal
        assert main_window.btn_toggle_pass.text() == "Скрыть"


class TestSettingsSave:
    """Тесты сохранения настроек."""

    def test_save_settings_with_values(self, main_window):
        """Проверяет сохранение настроек с заполненными полями."""
        main_window.timeout_input.setText("30")
        main_window.import_path_input.setText("test_schema")

        main_window.on_save_settings_click()

        # Проверяем, что после сохранения вернулись на меню
        assert main_window.stack.currentIndex() == 0

    def test_save_settings_empty_fields(self, main_window):
        """Проверяет сохранение настроек с пустыми полями."""
        main_window.timeout_input.setText("")
        main_window.import_path_input.setText("")

        main_window.on_save_settings_click()

        # Проверяем, что после сохранения вернулись на меню
        assert main_window.stack.currentIndex() == 0


class TestInitialState:
    """Тесты начального состояния элементов."""

    def test_parsing_buttons_initially_disabled(self, main_window):
        """Проверяет, что кнопки управления парсингом изначально отключены."""
        assert not main_window.btn_cancel_parsing.isEnabled()
        assert not main_window.btn_preview_parsing.isEnabled()
        assert not main_window.btn_export_parsing.isEnabled()

    def test_target_url_readonly(self, main_window):
        """Проверяет, что поле целевого URL только для чтения."""
        assert main_window.target_url_input.isReadOnly()
        assert main_window.target_url_input.text() == "https://goldapple.ru/"

    def test_log_display_readonly(self, main_window):
        """Проверяет, что панель логов только для чтения."""
        assert main_window.log_display.isReadOnly()


class TestParsingPageGuard:
    """
    Защита от создания второго парсера поверх работающего.

    Пользователь может уйти в меню во время парсинга и вернуться. Новый
    парсер поверх живого создал бы два потока, пишущих в одну базу, а лог и
    кнопка «ОТМЕНИТЬ» достались бы новому объекту — старый стал бы
    неуправляемым.
    """

    def test_no_parser_created_while_thread_running(self, main_window, mocker):
        """При живом потоке парсер не пересоздаётся."""
        mock_prepare = mocker.patch("src.windows_pq.prepare_parsing")

        thread = mocker.MagicMock()
        thread.isRunning.return_value = True
        main_window.parser_thread = thread
        original_parser = main_window.parser

        main_window.show_parsing_page()

        # Пользователь попал на страницу парсинга
        assert main_window.stack.currentIndex() == 4
        # Новый парсер не создавался, старый объект на месте
        assert not mock_prepare.called
        assert main_window.parser is original_parser

    def test_guard_uses_append_not_settext(self, main_window, mocker):
        """Прогресс парсинга в панели вывода не затирается."""
        mocker.patch("src.windows_pq.prepare_parsing")
        main_window.result_display.setText("загрузка страницы 7")
        main_window.parser_thread = mocker.MagicMock()
        main_window.parser_thread.isRunning.return_value = True

        main_window.show_parsing_page()

        assert "загрузка страницы 7" in main_window.result_display.toPlainText()

    def test_parser_created_when_thread_idle(self, main_window, mocker):
        """Если поток не работает — парсер создаётся как обычно."""
        thread = mocker.MagicMock()
        thread.isRunning.return_value = False
        main_window.parser_thread = thread
        main_window.parser = None

        main_window.show_parsing_page()

        # Настоящий prepare_parsing отработал, парсер на месте
        assert main_window.parser is not None
        assert main_window.manager is not None
        assert main_window.stack.currentIndex() == 4

    def test_close_event_survives_deleted_thread(self, main_window, mocker):
        """Закрытие окна после удалённого потока не должно падать.

        QThread удаляется через deleteLater, но атрибут продолжает
        ссылаться на оболочку удалённого объекта C++. Обращение
        к нему бросает RuntimeError, который раньше уходил в
        критическую ошибку приложения.
        """
        deleted = mocker.MagicMock()
        deleted.isRunning.side_effect = RuntimeError("wrapped C/C++ object of type QThread has been deleted")
        main_window.parser_thread = deleted

        event = mocker.MagicMock()
        main_window.closeEvent(event)

        assert event.accept.called
        assert main_window.parser_thread is None

    def test_thread_is_alive_returns_false_on_deleted(self, main_window, mocker):
        """Проверка живости потока переживает удалённый объект."""
        deleted = mocker.MagicMock()
        deleted.isRunning.side_effect = RuntimeError("deleted")
        main_window.parser_thread = deleted

        assert main_window._thread_is_alive() is False
        assert main_window.parser_thread is None

    def test_thread_is_alive_without_attribute(self, main_window):
        """Без атрибута parser_thread поток считается незапущенным."""
        if hasattr(main_window, "parser_thread"):
            del main_window.parser_thread

        assert main_window._thread_is_alive() is False

    def test_close_event_stops_running_thread(self, main_window, mocker):
        """Закрытие окна во время парсинга останавливает поток."""
        worker = mocker.MagicMock()
        thread = mocker.MagicMock()
        thread.isRunning.return_value = True
        main_window.parser_worker = worker
        main_window.parser_thread = thread

        event = mocker.MagicMock()
        main_window.closeEvent(event)

        assert worker.stop.called
        assert thread.quit.called
        assert thread.wait.called
        assert event.accept.called


class TestStackWidgetPages:
    """Тесты страниц в стеке виджетов."""

    def test_stack_has_six_pages(self, main_window):
        """Проверяет, что в стеке 6 страниц."""
        assert main_window.stack.count() == 6

    def test_stack_pages_in_correct_order(self, main_window):
        """Проверяет порядок страниц в стеке."""
        assert main_window.stack.widget(0) == main_window.page_menu
        assert main_window.stack.widget(1) == main_window.page_auth
        assert main_window.stack.widget(2) == main_window.page_request
        assert main_window.stack.widget(3) == main_window.page_scanning
        assert main_window.stack.widget(4) == main_window.page_parsing
        assert main_window.stack.widget(5) == main_window.page_settings
