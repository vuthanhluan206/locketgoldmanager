from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    admin_token: str = Field(min_length=32)
    mongodb_uri: str = 'mongodb://localhost:27017'
    mongodb_database: str = 'locket_manager'
    nextdns_id: str = Field(default='', pattern=r'^([a-fA-F0-9]{6})?$')
    root_ca_path: str = ''

    @field_validator('admin_token')
    @classmethod
    def reject_example(cls, value: str) -> str:
        if value.startswith('replace-with-') or not value.isascii() or value.strip() != value:
            raise ValueError('ADMIN_TOKEN must be a new random ASCII secret')
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
