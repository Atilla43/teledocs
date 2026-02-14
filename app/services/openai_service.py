from openai import AsyncOpenAI

from config.settings import settings

SYSTEM_PROMPT = (
    "Ты — полезный ассистент бота для генерации документов. "
    "Ты помогаешь фрилансерам и малому бизнесу создавать договоры, "
    "счета и акты. Отвечай на русском языке. Будь кратким и профессиональным. "
    "Если пользователь спрашивает о создании документа, предложи использовать "
    "команду /newdoc."
)


class OpenAIService:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self._conversations: dict[int, list[dict]] = {}

    async def chat(self, user_id: int, user_message: str) -> str:
        history = self._get_or_create_history(user_id)
        history.append({"role": "user", "content": user_message})

        trimmed = self._trim_history(
            history, max_messages=settings.max_conversation_messages
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + trimmed,
        )

        assistant_msg = response.choices[0].message.content
        history.append({"role": "assistant", "content": assistant_msg})
        return assistant_msg

    def clear_history(self, user_id: int) -> None:
        self._conversations.pop(user_id, None)

    def _get_or_create_history(self, user_id: int) -> list[dict]:
        if user_id not in self._conversations:
            self._conversations[user_id] = []
        return self._conversations[user_id]

    @staticmethod
    def _trim_history(history: list[dict], max_messages: int = 20) -> list[dict]:
        if len(history) > max_messages:
            return history[-max_messages:]
        return history
