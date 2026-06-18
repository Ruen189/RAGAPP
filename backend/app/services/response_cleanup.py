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
MIN_REPEAT_PARAGRAPH_CHARS = 48
MIN_REPEAT_FINGERPRINT_CHARS = 160
MIN_REPEAT_FINGERPRINT_LEN = 180


def _normalize_for_repeat(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def truncate_repeated_blocks(text: str) -> str:
    """Cut answer when the same paragraph or long prefix starts repeating."""
    cleaned = text.strip()
    if not cleaned:
        return cleaned

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", cleaned) if part.strip()]
    if len(paragraphs) >= 2:
        seen: dict[str, int] = {}
        for index, paragraph in enumerate(paragraphs):
            if len(paragraph) < MIN_REPEAT_PARAGRAPH_CHARS:
                continue
            key = _normalize_for_repeat(paragraph)
            if key in seen:
                return "\n\n".join(paragraphs[:index]).strip()
            seen[key] = index

    if len(cleaned) >= MIN_REPEAT_FINGERPRINT_CHARS:
        fingerprint_len = min(MIN_REPEAT_FINGERPRINT_LEN, len(cleaned) // 3)
        fingerprint = cleaned[:fingerprint_len]
        second_pos = cleaned.find(fingerprint, fingerprint_len - 40)
        if second_pos != -1:
            return cleaned[:second_pos].rstrip()

    return cleaned


class RepetitionGuard:
    """Stops streaming once a repeated paragraph or long prefix is detected."""

    def __init__(self) -> None:
        self._buffer = ""
        self._emitted_len = 0
        self.stopped = False

    def feed(self, token: str) -> str:
        if self.stopped or not token:
            return ""
        self._buffer += token
        safe = truncate_repeated_blocks(self._buffer)
        if len(safe) < len(self._buffer.rstrip()):
            self._buffer = safe
            self.stopped = True
        emit_until = len(self._buffer)
        if self._emitted_len >= emit_until:
            return ""
        visible = self._buffer[self._emitted_len:emit_until]
        self._emitted_len = emit_until
        return visible

    def flush(self) -> str:
        if self.stopped:
            return ""
        tail = self._buffer[self._emitted_len :]
        self._emitted_len = len(self._buffer)
        return tail


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
    return truncate_repeated_blocks(cleaned)
