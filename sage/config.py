from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    project_name: str = "SAGE API"
    supabase_url: str
    supabase_key: str
    supabase_db_url: str
    notion_client_id: str
    notion_client_secret: str
    notion_redirect_uri: str
    openrouter_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    vultr_inference_key: Optional[str] = None
    vultr_inference_url: Optional[str] = None
    or_site_url: Optional[str] = None
    or_app_name: Optional[str] = None
    google_application_credentials: Optional[str] = None
    google_credentials_base64: Optional[str] = None
    google_cloud_project: Optional[str] = None
    google_cloud_location: Optional[str] = None
    document_ai_processor_id: Optional[str] = None
    gaffa_api_key: Optional[str] = None
    app_base_url: Optional[str] = None
    admin_key: Optional[str] = None
    fernet_key: str
    fastmcp_allowed_origins: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
