from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Telegram
    bot_token: str

    # OpenAI / OpenRouter
    openai_api_key: str
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_chat_model: str = "openai/gpt-4o-mini"
    openai_document_model: str = "openai/gpt-4o"

    # Paths
    templates_dir: str = str(BASE_DIR / "templates")
    output_dir: str = str(BASE_DIR / "output")
    db_path: str = str(BASE_DIR / "data" / "teledocs.db")

    # Access control
    admin_ids: list[int] = []  # Telegram user IDs of admins
    whitelist_enabled: bool = True  # When False, all users can access the bot

    # Limits
    max_conversation_messages: int = 20

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
