from __future__ import annotations

import os
from enum import Enum
from json import JSONDecodeError
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import DirectoryPath, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.providers import env as env_source

# Load .env file - search in multiple locations
# 1. Repository root (when running from source)
# 2. Current working directory
# 3. Package directory
_possible_locations = [
    Path(__file__).parent.parent.parent.parent.parent / ".env",  # repo root from package
    Path.cwd() / ".env",  # current directory
    Path(__file__).parent.parent.parent / ".env",  # package root
]

_env_loaded = False
for _env_file in _possible_locations:
    if _env_file.exists():
        load_dotenv(_env_file)
        _env_loaded = True
        break

if not _env_loaded:
    # Last resort: try loading from current directory without checking existence
    load_dotenv()


class BridgeMode(str, Enum):
    mock = "mock"
    bridge = "bridge"


class _RawEnvSource(env_source.EnvSettingsSource):
    def decode_complex_value(self, field_name, field, value):
        try:
            return super().decode_complex_value(field_name, field, value)
        except JSONDecodeError:
            return value


class Config(BaseSettings):
    workspace_dir: Path = Field(...)
    allowed_directories: List[DirectoryPath] = Field(...)
    bridge_url: str | None = Field(default=None)
    mode: BridgeMode = Field(default=BridgeMode.mock)
    audit_log: Path = Field(default_factory=lambda: Path("audit.log"))
    log_level: str = Field("INFO")

    model_config = SettingsConfigDict(
        env_prefix="MCP_REVIT_",
        case_sensitive=False,
        extra="forbid",
    )

    @field_validator("allowed_directories", mode="before")
    def split_directories(cls, value):
        if isinstance(value, str):
            return [Path(p.strip()) for p in value.split(";") if p.strip()]
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        custom_env = _RawEnvSource(
            settings_cls,
            case_sensitive=env_settings.case_sensitive,
            env_prefix=env_settings.env_prefix,
            env_nested_delimiter=env_settings.env_nested_delimiter,
            env_nested_max_split=env_settings.env_nested_max_split,
            env_ignore_empty=env_settings.env_ignore_empty,
            env_parse_none_str=env_settings.env_parse_none_str,
            env_parse_enums=env_settings.env_parse_enums,
        )
        return init_settings, custom_env, dotenv_settings, file_secret_settings

    def workspace_allowed(self, path: Path) -> bool:
        path = path.resolve()
        return any(path.is_relative_to(allowed.resolve()) for allowed in self.allowed_directories)


config = Config()
