"""Validated application configuration; the only module that reads environment variables."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    url: SecretStr = SecretStr("postgresql+asyncpg://gladys:gladys@localhost:5432/gladys")
    pool_size: int = Field(5, ge=1)


class RedisSettings(BaseModel):
    url: SecretStr = SecretStr("redis://localhost:6379/0")


class LLMSettings(BaseModel):
    generator_model: str = "claude-opus-5-5"
    reviewer_model: str = "claude-opus-5-5"
    generator_effort: str = "high"
    api_key: SecretStr | None = None
    prices_per_million_tokens: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {"claude-opus-5-5": {"input": 5.0, "output": 25.0}}
    )


class AgentBudgetSettings(BaseModel):
    max_iterations: int = Field(12, ge=1)
    max_total_tokens: int = Field(100_000, ge=1)
    max_cost_usd: float = Field(10.0, gt=0)
    timeout_seconds: int = Field(600, ge=1)


class SandboxSettings(BaseModel):
    url: str = "http://sandbox:8001"
    timeout_seconds: int = Field(120, ge=1)
    max_output_bytes: int = Field(1_000_000, ge=1)


class AuthSettings(BaseModel):
    require_distinct_approver: bool = True
    static_api_keys: dict[str, SecretStr] = Field(default_factory=dict)


class ObservabilitySettings(BaseModel):
    log_level: str = "INFO"
    otlp_enabled: bool = False
    otlp_endpoint: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GLADYS_", env_nested_delimiter="__", env_file=".env", extra="ignore")
    environment: str = "development"
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    agent: AgentBudgetSettings = Field(default_factory=AgentBudgetSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
