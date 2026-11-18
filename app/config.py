from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_key: str = "dev-app-key"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    storage_backend: str = ""  # "memory" | "supabase"; empty → auto
    public_base_url: str = "http://localhost:8000"
    invite_ttl_days: int = 14

    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_bundle_id: str = "com.tidings.app"
    apns_private_key: str = ""
    apns_use_sandbox: bool = True

    @property
    def resolved_backend(self) -> str:
        if self.storage_backend:
            return self.storage_backend.lower()
        return "supabase" if self.supabase_url else "memory"


@lru_cache
def get_settings() -> Settings:
    return Settings()
