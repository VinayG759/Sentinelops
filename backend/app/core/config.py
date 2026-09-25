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
    # Workspace to file records in. Empty = the API key owner's own workspace. In a shared
    # (multi-team) account, records filed without it land in the default workspace, where
    # the key's agent may be unable to read or update them.
    freshservice_workspace_id: int | None = None
    # Vobiz phone alerts: call the on-call engineer when a fix needs approval.
    vobiz_auth_id: str = ""
    vobiz_auth_token: str = ""
    vobiz_from_number: str = ""
    oncall_phone: str = ""
    # Secret path segment on the Vobiz webhooks (Vobiz can't log in to our API).
    vobiz_webhook_secret: str = ""
    # Public https origin of THIS backend (e.g. a Cloudflare tunnel), for Vobiz callbacks.
    public_api_url: str = ""
    # ElevenLabs voice for the phone alert (empty key = the telephony provider's voice).
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # a standard ElevenLabs voice
    elevenlabs_model: str = "eleven_flash_v2_5"  # low latency: generated while ringing
    # Where people open SentinelOps; used for links written into Freshservice records.
    app_url: str = "http://localhost:5173"

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
