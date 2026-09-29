from prometheus_client import CollectorRegistry


def create_registry() -> CollectorRegistry:
    """Return an isolated registry so tests and app instances never share collectors."""
    return CollectorRegistry(auto_describe=True)
