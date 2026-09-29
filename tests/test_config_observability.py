from gladys.config import ModelPrice, Settings
from gladys.observability import (
    bind_correlation_id,
    configure_logging,
    correlation_id,
    create_registry,
    reset_correlation_id,
)
from gladys.observability.logging import _add_correlation_id


def test_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm.generator_model == "claude-opus-5-5"
    assert settings.auth.require_distinct_approver
    assert settings.database.url.get_secret_value().startswith("postgresql+asyncpg")


def test_default_price_table_matches_published_opus_5_5_prices() -> None:
    prices = Settings(_env_file=None).llm.prices_per_million_tokens
    assert prices["claude-opus-5-5"] == ModelPrice(
        input=4.0, output=20.0, cache_read=0.20, cache_write_5m=5.0, cache_write_1h=8.0
    )


def test_every_default_model_has_a_price() -> None:
    settings = Settings(_env_file=None)
    assert {settings.llm.generator_model, settings.llm.reviewer_model} <= set(settings.llm.prices_per_million_tokens)


def test_correlation_context_and_registry() -> None:
    token = bind_correlation_id("request-1")
    assert correlation_id.get() == "request-1"
    reset_correlation_id(token)
    assert correlation_id.get() is None
    assert create_registry() is not create_registry()


def test_logging_adds_bound_correlation_id() -> None:
    configure_logging("warning")
    token = bind_correlation_id("request-2")
    assert _add_correlation_id(None, "info", {})["correlation_id"] == "request-2"
    reset_correlation_id(token)
    assert "correlation_id" not in _add_correlation_id(None, "info", {})
