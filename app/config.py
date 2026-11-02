from functools import lru_cache
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from .passwords import validate_password_hash


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', hide_input_in_errors=True)
    superadmin_email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    superadmin_password_hash: SecretStr
    mongodb_uri: SecretStr
    mongodb_database: str = 'locket_manager'
    nextdns_id: str = Field(default='', pattern=r'^([a-fA-F0-9]{6})?$')
    root_ca_path: str = ''
    allowed_hosts: list[str] = ['localhost', '127.0.0.1', '[::1]']
    require_https: bool = False
    session_ttl_seconds: int = Field(default=3600, ge=300, le=86400)

    @field_validator('superadmin_password_hash')
    @classmethod
    def validate_hash(cls, value: SecretStr) -> SecretStr:
        validate_password_hash(value.get_secret_value())
        return value

    @field_validator('superadmin_email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator('mongodb_uri')
    @classmethod
    def validate_uri(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(('mongodb://', 'mongodb+srv://')):
            raise ValueError('MONGODB_URI must be a MongoDB connection URI')
        return value

    @field_validator('allowed_hosts')
    @classmethod
    def validate_hosts(cls, value: list[str]) -> list[str]:
        if not value or any(not host or '*' in host or '/' in host for host in value):
            raise ValueError('ALLOWED_HOSTS must contain explicit hostnames without wildcards')
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
