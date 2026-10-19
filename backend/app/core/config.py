from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from urllib.parse import unquote, urlsplit

from dotenv import dotenv_values
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    _placeholder_values: ClassVar[set[str]] = {
        'replace-me',
        'autotrader',
        'change-me',
        'changeme',
    }

    ENVIRONMENT: str = 'local'
    SECRET_KEY: str = 'replace-me'
    DATABASE_URL: str = 'postgresql+psycopg://autotrader:autotrader@127.0.0.1:5432/autotrader'
    POSTGRES_PASSWORD: str = 'autotrader'
    REDIS_BROKER_URL: str = 'redis://127.0.0.1:6379/0'
    REDIS_CACHE_URL: str = 'redis://127.0.0.1:6379/1'
    # Any S3-compatible store: SeaweedFS locally/CI, R2 or S3 in deployed environments.
    S3_ENDPOINT: str = '127.0.0.1:9000'
    S3_REGION: str = 'us-east-1'
    S3_ACCESS_KEY: str = 'replace-me'
    S3_SECRET_KEY: str = 'replace-me'
    S3_BUCKET: str = 'autotrader-uploads'
    S3_SECURE: bool = False
    TRUSTED_PROXY_CIDRS: str = '127.0.0.0/8,::1/128'
    ALLOWED_HOSTS: str = 'localhost,127.0.0.1,::1,testserver'
    FRONTEND_URL: str = 'http://127.0.0.1:3000'
    BACKEND_URL: str = 'http://127.0.0.1:8000'
    SENTRY_DSN: str = ''
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ''
    THREADPOOL_SIZE: int = 40
    # Server-side cap for every app query (Feature 01 §6). Set per connection rather than
    # relying on the login role's `ALTER ROLE ... SET`, which `SET ROLE` never applies.
    DB_STATEMENT_TIMEOUT_MS: int = 5000
    FLAG_VALUE_MY_CAR: str = 'off'

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / '.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    @model_validator(mode='after')
    def reject_placeholder_secrets_outside_local(self) -> Settings:
        if self.ENVIRONMENT == 'local':
            return self
        if self.ENVIRONMENT not in {'staging', 'production'}:
            raise ValueError('ENVIRONMENT must be local, staging, or production')

        credentials = unquote(urlsplit(self.DATABASE_URL).password or '')
        example_values = dotenv_values(REPO_ROOT / '.env.example')
        placeholder_values = {
            value.strip().lower()
            for key, value in example_values.items()
            if key
            in {
                'SECRET_KEY',
                'POSTGRES_PASSWORD',
                'S3_ACCESS_KEY',
                'S3_SECRET_KEY',
            }
            and value
        }
        placeholder_values.update(self._placeholder_values)
        secrets = {
            'SECRET_KEY': self.SECRET_KEY,
            'POSTGRES_PASSWORD': self.POSTGRES_PASSWORD,
            'S3_ACCESS_KEY': self.S3_ACCESS_KEY,
            'S3_SECRET_KEY': self.S3_SECRET_KEY,
            'DATABASE_URL password': credentials,
        }
        for name, value in secrets.items():
            normalized = value.strip().lower()
            if normalized in placeholder_values or any(
                marker in normalized
                for marker in ('change-me', 'changeme', 'replace-me', 'placeholder', 'local-only')
            ):
                raise ValueError(f'{name} still contains an .env.example placeholder')
        return self


settings = Settings()
