"""Service layer base classes and utilities.

Services contain your application's business logic. They provide:

- Database access via self.db (the SQLAlchemy session)
- Convenience methods: get_or_404(), save(), delete()
- Transaction control: commit(), rollback()

Service Registry
----------------
For services that need singleton behavior (expensive initialization, shared state),
use the registry::

    from feather.services import singleton, Service

    @singleton
    class CacheService(Service):
        def __init__(self):
            super().__init__()
            self.cache = {}  # Shared across all requests

Or register manually::

    from feather.services import registry

    registry.register(MyService, MyService())
"""

from feather.services.base import Service, registry, singleton, ServiceRegistry
from feather.core.decorators import inject

__all__ = [
    "Service",
    "inject",
    "registry",
    "singleton",
    "ServiceRegistry",
]
