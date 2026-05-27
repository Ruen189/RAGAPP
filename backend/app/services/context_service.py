from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Conversation, Message
from app.services.llama_client import LlamaClient
from app.services.prompt_templates import SUMMARIZATION_PROMPT
from app.services.summary_policy import merge_summaries, should_compress
from app.services.token_estimator import TokenEstimator


@dataclass
class ContextWindow:
    system_prompt: str
    summary_text: str | None
    raw_messages: list[Message]
    selected_messages: list[Message]
    total_tokens: int


class ContextService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llama = LlamaClient()

    async def maybe_compress(self, db: AsyncSession, conversation: Conversation) -> dict | None:
        if not self.settings.summary_enabled:
            return None

        rows = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
        )
        messages = rows.scalars().all()
        if not should_compress(len(messages), self.settings.raw_messages_size, self.settings.messages_summary_size):
            return None

        keep_tail = self.settings.raw_messages_size + max(self.settings.messages_summary_size - 1, 0)
        to_summarize = [msg for msg in messages[:-keep_tail] if not msg.summarized]
        if not to_summarize:
            return None

        serialized = "\n".join(f"{m.role.value}: {m.content}" for m in to_summarize)
        prompt = f"{SUMMARIZATION_PROMPT.strip()}\n\nТекущий summary:\n{conversation.summary_text or '-'}\n\nНовые сообщения:\n{serialized}"
        new_summary = await self.llama.generate(prompt, model=self.settings.effective_summary_model)

        input_chars = len(serialized)
        merged_summary = merge_summaries(conversation.summary_text, new_summary)
        merged_tokens = TokenEstimator.count(merged_summary)
        if merged_tokens > self.settings.summary_tokens_size:
            compress_prompt = (
                f"{SUMMARIZATION_PROMPT.strip()}\n\n"
                f"Сильно сократи этот summary до ключевых фактов без потери контекста:\n{merged_summary}"
            )
            merged_summary = await self.llama.generate(compress_prompt, model=self.settings.effective_summary_model)
            merged_tokens = TokenEstimator.count(merged_summary)

        conversation.summary_text = merged_summary
        conversation.summary_tokens = merged_tokens
        for msg in to_summarize:
            msg.summarized = True
        await db.commit()
        return {
            "strategy": "summary+state",
            "input_chars": input_chars,
            "output_chars": len(merged_summary),
            "summary_text": merged_summary,
        }

    async def build_context_window(
        self,
        db: AsyncSession,
        conversation_id: str,
        system_prompt: str,
    ) -> ContextWindow:
        conversation = await db.get(Conversation, conversation_id)
        raw_rows = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(self.settings.raw_messages_size)
        )
        raw_messages = list(reversed(raw_rows.scalars().all()))

        bridge_size = max(self.settings.messages_summary_size - 1, 0)
        selected_messages = raw_messages
        if bridge_size > 0:
            bridge_rows = await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id, Message.summarized.is_(False))
                .order_by(Message.created_at.desc())
                .offset(self.settings.raw_messages_size)
                .limit(bridge_size)
            )
            bridge_messages = list(reversed(bridge_rows.scalars().all()))
            selected_messages = bridge_messages + raw_messages

        total_tokens = TokenEstimator.count(system_prompt)
        total_tokens += TokenEstimator.count(conversation.summary_text or "")
        for msg in selected_messages:
            total_tokens += TokenEstimator.count(msg.content)

        return ContextWindow(
            system_prompt=system_prompt,
            summary_text=conversation.summary_text,
            raw_messages=raw_messages,
            selected_messages=selected_messages,
            total_tokens=total_tokens,
        )
