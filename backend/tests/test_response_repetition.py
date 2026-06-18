from app.services.response_cleanup import RepetitionGuard, clean_assistant_answer, truncate_repeated_blocks


def test_truncate_repeated_blocks_cuts_repeated_paragraph():
    block = (
        "В базе знаний нет информации о содержании ГОСТ 7.32.\n\n"
        "Если вы уточните, какой именно аспект стандарта вас интересует, я смогу помочь.\n\n"
        "Для получения точной информации рекомендую обратиться к официальным источникам.\n\n"
        "Если у вас есть другие вопросы, я с радостью отвечу на них."
    )
    repeated = f"{block}\n\n{block}\n\nВ базе знаний нет информации о содержании ГОСТ 7.32."
    assert truncate_repeated_blocks(repeated) == block


def test_clean_assistant_answer_removes_loops():
    paragraph = (
        "В базе знаний нет информации о содержании ГОСТ 7.32 и связанных стандартах оформления."
    )
    answer = f"Ответ: {paragraph}\n\n{paragraph}\n\n{paragraph}"
    assert clean_assistant_answer(answer) == paragraph


def test_repetition_guard_stops_on_repeated_paragraph():
    guard = RepetitionGuard()
    paragraph = "В базе знаний нет информации о содержании ГОСТ 7.32 и связанных стандартах оформления."
    emitted = guard.feed(f"{paragraph}\n\n{paragraph}")
    assert guard.stopped
    assert emitted.strip() == paragraph
