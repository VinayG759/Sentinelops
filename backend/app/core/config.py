"""Settings, read once from the repo-root .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    supabase_db_url: str = ""

    anthropic_api_key: str = ""

    freshservice_domain: str = ""
    freshservice_api_key: str = ""

    prometheus_url: str = "http://localhost:9090"
    kubeconfig_path: str = "./sentinelops-agent.kubeconfig"
    k8s_namespace: str = "default"

    @property
    def kubeconfig_file(self) -> Path:
        path = Path(self.kubeconfig_path)
        return path if path.is_absolute() else REPO_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
