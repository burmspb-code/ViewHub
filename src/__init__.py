import logging
from dotenv import load_dotenv
from src.core.logger import setup_logger

# Этот код сработает автоматически при первом импорте из папки src
load_dotenv()
setup_logger(name="", level=logging.INFO)
