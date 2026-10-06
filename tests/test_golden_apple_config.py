"""
Тесты конфигурации парсера Золотого Яблока.

Настройки браузера объявлены в GoldenAppleConfig, а не в самом парсере,
чтобы они не распространялись на CitadelParser и GardarikaParser.
"""

from src.parsers_config.golden_apple_config import GoldenAppleConfig


def test_user_agent_is_spoofed_chrome_124():
    """
    Фиксирует результат эксперимента: подмена Chrome/124 обязательна.

    Раньше эта подмена была в коде парсера, я счёл её «устаревшим расхождением»
    и удалил — после чего headless перестал работать: сайт отвечал отказом.
    Тест не даёт удалить её снова.
    """
    assert "Chrome/124" in GoldenAppleConfig.HEADLESS_USER_AGENT
    assert "Headless" not in GoldenAppleConfig.HEADLESS_USER_AGENT


def test_gpu_disable_enabled_by_default():
    """Без --disable-gpu включается SwiftShader, который сайт отвергает."""
    assert GoldenAppleConfig.HEADLESS_DISABLE_GPU is True


def test_headless_is_default_mode():
    """Headless — режим по умолчанию: экономит ресурсы и не требует дисплея."""
    assert GoldenAppleConfig.DEFAULT_HEADLESS is True


def test_env_var_names_are_scoped_to_this_site():
    """
    Имена переменных окружения должны быть уникальными для этого парсера.

    Префикс GOLDAPPLE_ не даёт этим настройкам повлиять на другие парсеры.
    """
    env_vars = [
        GoldenAppleConfig.HEADLESS_ENV_VAR,
        GoldenAppleConfig.UA_ENV_VAR,
        GoldenAppleConfig.DISABLE_GPU_ENV_VAR,
        GoldenAppleConfig.STEALTH_OFF_ENV_VAR,
        GoldenAppleConfig.NO_CHANNEL_ENV_VAR,
        GoldenAppleConfig.PROXY_ENV_VAR,
    ]

    assert all(name.startswith("GOLDAPPLE_") for name in env_vars)
    assert len(set(env_vars)) == len(env_vars), "имена переменных не должны повторяться"


def test_base_config_knows_nothing_about_browser():
    """Базовый класс не должен знать о настройках браузера."""
    from src.core.base_classes import BaseDBParsingConfig

    leaked = [name for name in dir(BaseDBParsingConfig) if any(
        marker in name for marker in ("HEADLESS", "USER_AGENT", "GPU", "STEALTH")
    )]

    assert leaked == []
