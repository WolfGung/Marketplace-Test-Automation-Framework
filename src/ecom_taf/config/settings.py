from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT_DIR / ".env"
ENVIRONMENTS_FILE = Path(__file__).with_name("environments.yaml")

#: The fields `environments.yaml` fills in per named target. Both are addresses
#: of the shop under test, and both are things a reader may want to point
#: somewhere else for one run -- a stand on another port, a review deployment --
#: without inventing a name for it in the YAML.
NAMED_FIELDS = ("base_url", "api_base_url")

BrowserName = Literal["chromium", "firefox", "webkit"]


class Settings(BaseSettings):
    """Centralized, environment-driven configuration."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="local", validation_alias="TEST_ENV")
    base_url: str = "http://127.0.0.1:8092"
    api_base_url: str = "http://127.0.0.1:8092/api"
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
        """Fill in the addresses `TEST_ENV` names, without overruling the user.

        `environments.yaml` holds a default per target, not an override. A value
        somebody actually set has to win, or `.env` -- the file the setup
        instructions tell a reader to copy -- is read and then silently thrown
        away, which is exactly what happened here: the old test was
        `"BASE_URL" not in os.environ`, and a dotenv value never reaches
        `os.environ`. pydantic-settings records every field one of its sources
        supplied -- the environment, the dotenv file, the constructor -- in
        `model_fields_set`, so that is the question to ask: not "where did this
        come from" but "did anyone set it at all".
        """
        if not ENVIRONMENTS_FILE.exists():
            return
        payload = yaml.safe_load(ENVIRONMENTS_FILE.read_text(encoding="utf-8")) or {}
        named = payload.get(self.env) or {}
        for field in NAMED_FIELDS:
            if field not in self.model_fields_set and field in named:
                setattr(self, field, named[field])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.apply_named_environment()
    settings.base_url = settings.base_url.rstrip("/")
    settings.api_base_url = settings.api_base_url.rstrip("/")
    return settings
