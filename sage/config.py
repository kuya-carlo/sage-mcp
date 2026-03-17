from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    project_name: str = "SAGE API"
    supabase_url: str
    supabase_key: str
    notion_client_id: str
    notion_client_secret: str
    notion_redirect_uri: str
    openrouter_api_key: str
    google_cloud_project: str
    fernet_key: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
