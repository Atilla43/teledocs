from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Telegram
    bot_token: str

    # OpenAI
    openai_api_key: str
    openai_chat_model: str = "gpt-4o-mini"
    openai_document_model: str = "gpt-4o"

    # Paths
    templates_dir: str = str(BASE_DIR / "templates")
    output_dir: str = str(BASE_DIR / "output")
    db_path: str = str(BASE_DIR / "data" / "teledocs.db")

    # Limits
    max_conversation_messages: int = 20

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
