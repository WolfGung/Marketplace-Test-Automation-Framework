import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT_DIR / ".env"
ENVIRONMENTS_FILE = Path(__file__).with_name("environments.yaml")

BrowserName = Literal["chromium", "firefox", "webkit"]


class Settings(BaseSettings):
    """Centralized, environment-driven configuration."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="prod", validation_alias="TEST_ENV")
    base_url: str = "https://www.automationexercise.com"
    api_base_url: str = "https://www.automationexercise.com/api"
    headless: bool = True
    browser: BrowserName = "chromium"
    slow_mo_ms: int = 0
    default_timeout_ms: int = 15_000
    http_timeout_s: float = 20.0

    #: Record the browser run. Off by default: it costs disk on every run and is
    #: only wanted when a run is going to be published. The same switch turns on
    #: the Playwright trace, which is the same kind of artefact for the same
    #: reason -- a recording of the run, worth its disk only when it is going to
    #: be looked at.
    record_video: bool = False
    video_dir: str = "videos"
    trace_dir: str = "traces"

    def apply_named_environment(self) -> None:
        if not ENVIRONMENTS_FILE.exists():
            return
        payload = yaml.safe_load(ENVIRONMENTS_FILE.read_text(encoding="utf-8")) or {}
        named = payload.get(self.env) or {}
        if "BASE_URL" not in os.environ and "base_url" in named:
            self.base_url = named["base_url"]
        if "API_BASE_URL" not in os.environ and "api_base_url" in named:
            self.api_base_url = named["api_base_url"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.apply_named_environment()
    settings.base_url = settings.base_url.rstrip("/")
    settings.api_base_url = settings.api_base_url.rstrip("/")
    return settings
