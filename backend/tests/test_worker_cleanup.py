from app.services.response_cleanup import clean_assistant_answer, strip_instruction_echo


def test_strip_instruction_echo_removes_leaked_guard():
    leaked = (
        "Краткий ответ по Scrum.\n\n"
        "Ответь только финальным сообщением ассистента. Не добавляй имена ролей и не продолжай диалог за пользователя. Не выводи"
    )
    assert strip_instruction_echo(leaked) == "Краткий ответ по Scrum."


def test_strip_instruction_echo_removes_answer_prefix():
    assert strip_instruction_echo("Ответ: Scrum — итеративный фреймворк.") == "Scrum — итеративный фреймворк."


def test_clean_assistant_answer_drops_instruction_only_output():
    assert clean_assistant_answer("Ответь только финальным сообщением ассистента. Не добавляй имена ролей") == ""
