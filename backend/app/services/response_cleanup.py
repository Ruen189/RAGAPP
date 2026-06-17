import re

ROLE_PREFIX_RE = re.compile(r"^\s*(assistant|ассистент)\s*:\s*", re.IGNORECASE)
NEXT_TURN_RE = re.compile(r"\n\s*(user|пользователь|USER)\s*:\s*", re.IGNORECASE)
THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
THINK_OPEN_RE = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)
REASONING_MARKERS_RE = re.compile(
    r"^\s*(thinking process|analy[sz]e the request|drafting the response|review against constraints|final check)\s*:",
    re.IGNORECASE,
)
INSTRUCTION_ECHO_MARKERS = (
    "ответь только финальным сообщением",
    "не добавляй имена ролей",
    "не продолжай диалог за пользователя",
    "не выводи <think>",
    "thinking process",
    "анализ запроса или черновики",
    "не добавляй список использованных источников",
    "технические id документов",
    "/no_think",
)
ANSWER_PREFIX_RE = re.compile(r"^\s*Ответ:\s*", re.IGNORECASE)


def strip_instruction_echo(answer: str) -> str:
    text = ANSWER_PREFIX_RE.sub("", answer.strip())
    lowered = text.lower()
    cut_at = len(text)
    for marker in INSTRUCTION_ECHO_MARKERS:
        idx = lowered.find(marker)
        if idx != -1 and idx < cut_at:
            cut_at = idx
    return text[:cut_at].rstrip()


def clean_assistant_answer(answer: str) -> str:
    cleaned = THINK_BLOCK_RE.sub("", answer)
    open_match = THINK_OPEN_RE.search(cleaned)
    if open_match:
        cleaned = cleaned[: open_match.start()]
    cleaned = THINK_CLOSE_RE.sub("", cleaned)
    cleaned = ROLE_PREFIX_RE.sub("", cleaned.strip())
    cleaned = strip_instruction_echo(cleaned)
    if REASONING_MARKERS_RE.search(cleaned):
        return ""
    next_turn_match = NEXT_TURN_RE.search(cleaned)
    if next_turn_match:
        cleaned = cleaned[: next_turn_match.start()].rstrip()
    return cleaned
