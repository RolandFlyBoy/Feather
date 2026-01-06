"""
Database Layer
==============

SQLAlchemy database integration for Feather applications.

This module exports:

Core
----
- **db**: SQLAlchemy instance for defining models and querying
- **Model**: Base class for all your models with convenience methods
- **migrate**: Flask-Migrate instance for database migrations

Mixins
------
- **UUIDMixin**: Adds UUID primary key (id column)
- **TimestampMixin**: Adds created_at and updated_at columns
- **SoftDeleteMixin**: Adds soft delete functionality
- **OrderingMixin**: Adds position-based ordering

Pagination
----------
- **paginate**: Paginate SQLAlchemy queries
- **PaginatedResult**: Container for paginated results

Quick Start
-----------
Basic model::

    from feather.db import db, Model
    import uuid

    class User(Model):
        __tablename__ = 'users'
        id = db.Column(db.String(36), primary_key=True,
                       default=lambda: str(uuid.uuid4()))
        email = db.Column(db.String(255), unique=True)
        username = db.Column(db.String(50), unique=True)

Using mixins::

    from feather.db import db, Model
    from feather.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin

    class Post(UUIDMixin, TimestampMixin, SoftDeleteMixin, Model):
        __tablename__ = 'posts'
        title = db.Column(db.String(200), nullable=False)
        # id, created_at, updated_at, deleted_at provided by mixins

Pagination::

    from feather.db import paginate

    result = paginate(Post.query_active(), page=1, per_page=20)
    posts = result.items
    has_more = result.has_next

See :mod:`feather.db.base` for full documentation.
"""

from contextlib import contextmanager

from feather.db.base import db, Model, migrate
from feather.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin, OrderingMixin
from feather.db.pagination import paginate, PaginatedResult


@contextmanager
def db_operation():
    """Context manager for database operations that releases connection when done.

    Use this in background jobs to avoid holding database connections during
    external API calls. This pattern prevents connection pool exhaustion when
    jobs do long-running external operations.

    The context manager:
    - Yields the database session
    - Commits on successful exit
    - Rolls back on exception
    - Calls session.remove() to release connection back to pool

    Example::

        from feather.db import db_operation
        from feather.jobs import job

        @job
        def process_item(item_id):
            # Phase 1: Read from database
            with db_operation():
                item = Item.query.get(item_id)
                data = item.data
            # Connection released here

            # Phase 2: External API call (no connection held)
            result = external_api.process(data)

            # Phase 3: Write to database
            with db_operation():
                item = Item.query.get(item_id)
                item.result = result
            # Connection released again

    Without this pattern, a job that does::

        item = Item.query.get(item_id)  # Gets connection
        result = external_api.slow_call()  # Holds connection for minutes!
        item.status = result
        db.session.commit()

    ...holds a database connection for the entire duration of the API call,
    potentially exhausting the connection pool if many jobs run concurrently.

    Note:
        - Always use this in background jobs that make external calls
        - Don't use inside Flask request handlers (Flask manages sessions)
        - Calling db.session.commit() alone does NOT release the connection
        - session.remove() is required to return connection to pool
    """
    try:
        yield db.session
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        db.session.remove()


__all__ = [
    # Core
    "db",
    "Model",
    "migrate",
    # Mixins
    "UUIDMixin",
    "TimestampMixin",
    "SoftDeleteMixin",
    "OrderingMixin",
    # Pagination
    "paginate",
    "PaginatedResult",
    # Context managers
    "db_operation",
]
