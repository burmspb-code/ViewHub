import pytest
import tinycss2
# Импортируем ваш модуль со стилями
import src.core.styles as styles


def validate_css_string(css_content: str) -> list[str]:
    """Вспомогательная функция для поиска ошибок в CSS-строке."""
    errors = []

    # Очищаем от лишних пробелов по краям
    css_content = css_content.strip()
    if not css_content:
        return errors

    # Шаг 1. Определяем тип контента
    if "{" in css_content:
        # Это полноценный CSS со структурами вида "селектор { свойства }"
        rules = tinycss2.parse_stylesheet(css_content, skip_comments=True)

        for rule in rules:
            if rule.type == "error":
                errors.append(f"Ошибка структуры: {rule.message}")
                continue

            if hasattr(rule, "content"):
                declarations = tinycss2.parse_declaration_list(rule.content, skip_comments=True)
                for decl in declarations:
                    if decl.type == "error":
                        errors.append(f"Ошибка в свойстве: {decl.message}")
    else:
        # Это инлайн-стиль вида "свойство: значение; свойство2: значение2;"
        declarations = tinycss2.parse_declaration_list(css_content, skip_comments=True)
        for decl in declarations:
            if decl.type == "error":
                errors.append(f"Ошибка в свойстве: {decl.message}")

    return errors


# НАСТРОЙКА АВТОМАТИЧЕСКОГО СБОРА СТИЛЕЙ:
# Находим все переменные в styles.py, которые содержат строки (пропускаем системные __)
style_variables = [
    (name, getattr(styles, name))
    for name in dir(styles)
    if not name.startswith("__") and isinstance(getattr(styles, name), str)
]


# ПЕРЕДАЕМ ПЕРЕМЕННУЮ style_variables В ДЕКОРАТОР
@pytest.mark.parametrize("style_name, style_content", style_variables)
def test_python_styles_have_no_syntax_errors(style_name, style_content):
    """Автоматически проверяет все строковые стили в styles.py на опечатки."""
    errors = validate_css_string(style_content)

    # Если ошибки есть, тест упадет и покажет, в какой именно переменной опечатка
    assert not errors, f"В стиле '{style_name}' обнаружены ошибки:\n" + "\n".join(errors)
