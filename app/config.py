import json
import re
from functools import lru_cache
from ipaddress import ip_network
from pydantic import Field, SecretStr, field_validator, model_validator
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
    root_ca_pem: str = Field(default='', max_length=65536, repr=False)
    admin_path: str = Field(default='/admin', pattern=r'^/[A-Za-z0-9_-]{1,64}$')
    allowed_hosts: list[str] = ['localhost', '127.0.0.1', '[::1]']
    vercel: str = ''
    vercel_url: str = ''
    vercel_project_production_url: str = ''
    vercel_branch_url: str = ''
    require_https: bool = False
    session_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    subscriber_api_token: SecretStr | None = None
    turnstile_site_key: str = Field(default='', pattern=r'^[A-Za-z0-9_-]*$', max_length=256)
    turnstile_secret_key: SecretStr = SecretStr('')
    turnstile_hostname: str = ''
    trusted_proxy_cidrs: list[str] = []
    dns_public_origin: str = Field(default='', max_length=256)

    @field_validator('admin_path')
    @classmethod
    def validate_admin_path(cls, value: str) -> str:
        if value in {'/proxy', '/api', '/v1', '/favicon', '/robots'}:
            raise ValueError('ADMIN_PATH conflicts with an application route')
        return value

    @model_validator(mode='after')
    def deployment_hosts(self):
        if self.vercel == '1':
            for host in (self.vercel_url, self.vercel_branch_url):
                if host:
                    if not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.vercel\.app', host):
                        raise ValueError('Vercel system URL must be an exact vercel.app hostname')
                    if host.lower() not in self.allowed_hosts:
                        self.allowed_hosts.append(host.lower())
            host = self.vercel_project_production_url.lower()
            if re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.vercel\.app', host) and host not in self.allowed_hosts:
                self.allowed_hosts.append(host)
        return self

    @field_validator('trusted_proxy_cidrs')
    @classmethod
    def validate_proxy_cidrs(cls, value: list[str]) -> list[str]:
        for network in value:
            ip_network(network)
        return value

    @field_validator('subscriber_api_token')
    @classmethod
    def validate_subscriber_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            raw = value.get_secret_value()
            if not 32 <= len(raw) <= 256 or not raw.isascii() or any(c.isspace() for c in raw):
                raise ValueError('SUBSCRIBER_API_TOKEN must be a random ASCII token of 32-256 characters')
        return value

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

    @field_validator('allowed_hosts', mode='before')
    @classmethod
    def validate_hosts(cls, value):
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith('['):
                hosts = json.loads(raw)
            else:
                hosts = [h.strip() for h in raw.split(',') if h.strip()]
        elif isinstance(value, list):
            hosts = [str(h).strip() for h in value if str(h).strip()]
        else:
            raise ValueError('ALLOWED_HOSTS must be a list of hostnames')
        if not hosts or any('*' in host or '://' in host or '/' in host for host in hosts):
            raise ValueError('ALLOWED_HOSTS must contain explicit hostnames and never wildcard (*)')
        return hosts


@lru_cache
def get_settings() -> Settings:
    return Settings()