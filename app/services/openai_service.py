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
    def __init__(self, api_key: str, base_url: str | None = None, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
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

    async def generate_field_labels(self, variable_names: list[str]) -> dict:
        """Generate Russian labels and prompts for template variable names.

        Input: ["executor_inn", "contract_amount", ...]
        Output: {"executor_inn": {"label": "ИНН исполнителя", "prompt_ru": "Введите ИНН:", "type": "string"}, ...}
        """
        import json

        prompt = (
            "Тебе дан список имён переменных из шаблона документа (snake_case).\n"
            "Для каждой переменной придумай:\n"
            "- label: короткое название на русском (2-4 слова)\n"
            "- prompt_ru: вопрос для пользователя на русском\n"
            "- type: string | text | date\n"
            "Верни СТРОГО JSON без markdown: "
            '{\"var_name\": {\"label\": \"...\", \"prompt_ru\": \"...\", \"type\": \"...\"}, ...}\n'
        )

        vars_text = ", ".join(variable_names)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": vars_text},
            ],
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        return json.loads(raw)

    async def generate_target_queries(self, business_type: str, count: int = 20) -> str:
        """Generate target search queries for a business type.

        Returns a numbered list as plain text, e.g. "1. стоматология\\n2. ..."
        """
        prompt = (
            "Ты — SEO-специалист по продвижению организаций в Яндекс Картах и 2ГИС.\n"
            f"Составь {count} целевых поисковых запросов для продвижения "
            f"карточки организации типа «{business_type}».\n\n"
            "ВАЖНО — это запросы, по которым клиенты ИЩУТ ОРГАНИЗАЦИЮ в картах, "
            "а не гуглят информацию.\n\n"
            "СТРУКТУРА СПИСКА (по приоритету):\n"
            "1. Название сферы и синонимы (2-3 шт.)\n"
            "2. Конкретные коммерческие услуги этого бизнеса (10-12 шт.) — главная часть списка\n"
            "3. Запросы с «рядом» (1-2 шт.)\n"
            "4. Запросы с намерением: записаться, срочный (2-3 шт.)\n\n"
            "ЗАПРЕЩЕНО:\n"
            "- Симптомы и диагнозы (зубная боль, кариес, периодонтит — люди это гуглят, а не ищут в картах)\n"
            "- Общие понятия (гигиена полости рта)\n"
            "- Маркетинговые слова (лучший, качественный, профессиональный)\n"
            "- Названия городов, «[ваш город]» — геосервис привязывает к локации сам\n\n"
            "ПРИМЕР для стоматологии:\n"
            "1. стоматология\n2. стоматолог\n3. стоматологическая клиника\n"
            "4. лечение зубов\n5. лечение кариеса\n6. пломбирование зубов\n"
            "7. профессиональная чистка зубов\n8. отбеливание зубов\n"
            "9. лечение каналов\n10. удаление зуба\n...\n\n"
            "Верни ТОЛЬКО пронумерованный список, без заголовков и пояснений."
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": business_type},
            ],
        )

        return response.choices[0].message.content.strip()

    async def convert_business_type_genitive(self, business_type: str) -> str:
        """Convert business type to genitive case for document.

        'стоматология' -> 'стоматологической клиники'
        'автосервис' -> 'автосервиса'
        """
        prompt = (
            "Преобразуй тип бизнеса в родительный падеж для фразы "
            "'карточка [ТИП] Заказчика'. "
            "Верни ТОЛЬКО результат, без кавычек и пояснений.\n\n"
            "Примеры:\n"
            "стоматология → стоматологической клиники\n"
            "автосервис → автосервиса\n"
            "салон красоты → салона красоты\n"
            "ресторан → ресторана\n"
            "фитнес-клуб → фитнес-клуба"
        )
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": business_type},
            ],
        )
        return response.choices[0].message.content.strip()

    async def extract_requisites(self, document_text: str) -> dict:
        """Extract company requisites from a company card document.

        Returns a flat dict with keys like company_name, inn, kpp, etc.
        """
        from app.services.requisite_parser import REQUISITE_PROMPT

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": REQUISITE_PROMPT},
                {"role": "user", "content": document_text},
            ],
        )

        import json

        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        return json.loads(raw)

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
