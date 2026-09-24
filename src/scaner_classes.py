"""
Модуль базовых абстрактных классов для создания гибкой системы сканирования.
Обеспечивает разделение бизнес-логики сетевых запросов, извлечения данных,
сохранения результатов и работы в фоновом потоке PyQt6.
"""

from abc import ABC, abstractmethod


class BaseScaner(ABC):
    """
    Абстрактный класс для управления сканированием.
    """
    def __init__(self, base_url: str):
        self.base_url = base_url

    @abstractmethod
    def run_scanning(self, worker) -> list:
        """
        Основной метод логики сканирования.
        Обязан регулярно проверять worker.is_stopped() для прерывания работы.
        """
        pass
