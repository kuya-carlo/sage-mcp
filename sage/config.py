from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "SAGE API"
    host: str = "0.0.0.0"
    port: int = 5463
    db_url: str
    notion_client_id: str
    notion_client_secret: str
    notion_redirect_uri: str
    fernet_key: str
    openrouter_api_key: str | None = None
    anthropic_api_key: str | None = None
    vultr_inference_key: str | None = None
    vultr_inference_url: str | None = None
    or_site_url: str | None = None
    or_app_name: str | None = None
    google_application_credentials: str | None = None
    google_credentials_base64: str | None = None
    google_cloud_project: str | None = None
    google_cloud_location: str | None = None
    document_ai_processor_id: str | None = None
    gaffa_api_key: str | None = None
    app_base_url: str | None = None
    admin_key: str | None = None
    fastmcp_allowed_origins: str | None = None
    notion_root_page_id: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # ty: ignore[missing-argument]
