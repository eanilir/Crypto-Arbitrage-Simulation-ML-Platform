from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    log_level: str = "INFO"
