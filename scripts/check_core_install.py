"""Fails unless the core modules import and no infrastructure library was installed."""

import importlib
import importlib.util

for module in ("gladys.domain", "gladys.ports", "gladys.config", "gladys.observability"):
    importlib.import_module(module)
leaked = [name for name in ("sqlalchemy", "asyncpg", "alembic") if importlib.util.find_spec(name) is not None]
assert not leaked, f"infrastructure libraries installed without extras: {leaked}"
print("core install OK")
