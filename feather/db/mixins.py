"""
Database Mixins
===============

Reusable mixins for common model patterns. Apply only what you need.

These mixins provide common functionality that many models share, but you
can choose which ones to use. Simply add them to your model's inheritance.

Available Mixins
----------------

- **UUIDMixin**: Adds a UUID primary key (id column)
- **TimestampMixin**: Adds created_at and updated_at columns
- **TenantScopedMixin**: Adds tenant_id for multi-tenant isolation
- **SoftDeleteMixin**: Adds soft delete functionality (deleted_at column)
- **OrderingMixin**: Adds position-based ordering (position column)

Quick Start
-----------
Use all mixins together::

    from feather.db import db, Model
    from feather.db.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin

    class Post(UUIDMixin, TimestampMixin, SoftDeleteMixin, Model):
        __tablename__ = 'posts'

        title = db.Column(db.String(200), nullable=False)
        content = db.Column(db.Text)

Or pick only what you need::

    class Comment(UUIDMixin, TimestampMixin, Model):
        __tablename__ = 'comments'
        # ...

Note:
    Mixins must come BEFORE Model in the inheritance chain.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, TypeVar, Type

from sqlalchemy import Column, String, DateTime, Integer, Index
from sqlalchemy.orm import declared_attr

# Type variable for model classes
T = TypeVar("T")


class UUIDMixin:
    """Adds a UUID primary key column.

    Provides:
        id: String(36) primary key with auto-generated UUID

    Example::

        from feather.db import db, Model
        from feather.db.mixins import UUIDMixin

        class User(UUIDMixin, Model):
            __tablename__ = 'users'
            email = db.Column(db.String(255), unique=True)

        # The id field is automatically added
        user = User(email='user@example.com')
        user.save()
        print(user.id)  # '550e8400-e29b-41d4-a716-446655440000'
    """

    @declared_attr
    def id(cls):
        """UUID primary key, auto-generated on creation."""
        return Column(
            String(36),
            primary_key=True,
            default=lambda: str(uuid.uuid4()),
        )


class TimestampMixin:
    """Adds created_at and updated_at timestamp columns.

    Provides:
        created_at: DateTime, automatically set on creation
        updated_at: DateTime, automatically updated on every save

    Example::

        from feather.db import db, Model
        from feather.db.mixins import TimestampMixin

        class Post(TimestampMixin, Model):
            __tablename__ = 'posts'
            title = db.Column(db.String(200))

        post = Post(title='Hello')
        post.save()
        print(post.created_at)  # 2024-01-15 10:30:00+00:00
        print(post.updated_at)  # 2024-01-15 10:30:00+00:00

        post.title = 'Updated'
        post.save()
        print(post.updated_at)  # 2024-01-15 11:00:00+00:00

    Note:
        Timestamps are always stored in UTC timezone.
    """

    @declared_attr
    def created_at(cls):
        """Timestamp when the record was created (UTC)."""
        return Column(
            DateTime,
            default=lambda: datetime.now(timezone.utc),
            nullable=False,
        )

    @declared_attr
    def updated_at(cls):
        """Timestamp when the record was last updated (UTC)."""
        return Column(
            DateTime,
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
        )


class TenantScopedMixin:
    """Adds tenant isolation for multi-tenant applications.

    Provides a tenant_id column for scoping data to a specific tenant.
    Use the for_tenant() class method to query only records belonging
    to a specific tenant.

    Provides:
        tenant_id: String(36) column, indexed, non-nullable

    Class Methods:
        for_tenant(tenant_id): Returns query filtered to tenant

    Example::

        from feather.db import db, Model
        from feather.db.mixins import UUIDMixin, TenantScopedMixin

        class Project(UUIDMixin, TenantScopedMixin, Model):
            __tablename__ = 'projects'
            name = db.Column(db.String(100), nullable=False)

        # Query projects for a specific tenant
        projects = Project.for_tenant(tenant_id).all()

        # Create a project with tenant
        project = Project(name='My Project', tenant_id=current_tenant_id)
        project.save()

    Usage in Routes::

        from feather.auth import get_current_tenant_id

        @api.get('/projects')
        @auth_required
        def list_projects():
            tenant_id = get_current_tenant_id()
            projects = Project.for_tenant(tenant_id).all()
            return {'projects': projects}

    Note:
        Tenant isolation is enforced at the service layer. Always use
        for_tenant() or filter by tenant_id in your queries. The admin
        panel and platform admin routes may need special handling.
    """

    @declared_attr
    def tenant_id(cls):
        """Tenant ID for multi-tenant isolation."""
        return Column(
            String(36),
            nullable=False,
            index=True,
        )

    @classmethod
    def for_tenant(cls, tenant_id: str):
        """Return a query filtered to a specific tenant.

        Args:
            tenant_id: The tenant's UUID string.

        Returns:
            SQLAlchemy query filtered by tenant_id.

        Example::

            # Get all projects for the current tenant
            projects = Project.for_tenant(tenant_id).all()

            # Chain with other filters
            active = Project.for_tenant(tenant_id).filter_by(active=True).all()
        """
        return cls.query.filter_by(tenant_id=tenant_id)


class SoftDeleteMixin:
    """Adds soft delete functionality.

    Instead of permanently deleting records, marks them as deleted by setting
    a deleted_at timestamp. This allows you to recover deleted data and maintain
    referential integrity.

    Provides:
        deleted_at: DateTime, None if not deleted
        is_deleted: Property that returns True if soft deleted
        soft_delete(): Method to mark as deleted
        restore(): Method to restore a soft deleted record

    Class Methods:
        query_active(): Returns query filtered to non-deleted records
        query_deleted(): Returns query filtered to only deleted records

    Example::

        from feather.db import db, Model
        from feather.db.mixins import UUIDMixin, SoftDeleteMixin

        class Post(UUIDMixin, SoftDeleteMixin, Model):
            __tablename__ = 'posts'
            title = db.Column(db.String(200))

        # Create and soft delete
        post = Post(title='Hello')
        post.save()
        post.soft_delete()
        post.save()

        # Query only active posts
        active_posts = Post.query_active().all()

        # Restore a deleted post
        post.restore()
        post.save()

    Important:
        Remember to use query_active() in your queries to exclude deleted records.
        The regular .query will return all records including deleted ones.
    """

    @declared_attr
    def deleted_at(cls):
        """Timestamp when the record was soft deleted (None if active)."""
        return Column(DateTime, nullable=True, default=None)

    @property
    def is_deleted(self) -> bool:
        """Check if this record has been soft deleted.

        Returns:
            True if deleted_at is set, False otherwise.
        """
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark this record as deleted without removing from database.

        Sets deleted_at to the current UTC timestamp. You must call save()
        after this to persist the change.

        Example::

            post.soft_delete()
            post.save()  # Don't forget to save!
        """
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Restore a soft-deleted record.

        Clears the deleted_at timestamp. You must call save() after this
        to persist the change.

        Example::

            post.restore()
            post.save()  # Don't forget to save!
        """
        self.deleted_at = None

    @classmethod
    def query_active(cls):
        """Return a query filtered to only non-deleted records.

        This is the recommended way to query when you want to exclude
        soft-deleted records.

        Returns:
            SQLAlchemy query with deleted_at IS NULL filter.

        Example::

            # Get all active posts
            posts = Post.query_active().all()

            # Chain with other filters
            my_posts = Post.query_active().filter_by(user_id=user.id).all()

            # Paginate active posts
            paginated = paginate(Post.query_active(), page=1, per_page=20)
        """
        return cls.query.filter(cls.deleted_at.is_(None))

    @classmethod
    def query_deleted(cls):
        """Return a query filtered to only soft-deleted records.

        Useful for admin panels or data recovery features.

        Returns:
            SQLAlchemy query with deleted_at IS NOT NULL filter.

        Example::

            # Get all deleted posts (for recovery)
            deleted = Post.query_deleted().all()
        """
        return cls.query.filter(cls.deleted_at.isnot(None))

    @classmethod
    def get_active_or_404(cls: Type[T], id) -> T:
        """Get an active (non-deleted) record by ID or raise NotFoundError.

        Combines get_or_404() behavior with soft delete filtering.

        Args:
            id: The primary key value.

        Returns:
            The model instance if found and not deleted.

        Raises:
            NotFoundError: If no active instance with this ID exists.

        Example::

            @api.get('/posts/<post_id>')
            def get_post(post_id):
                post = Post.get_active_or_404(post_id)
                return {'post': post.to_dict()}
        """
        from feather.exceptions import NotFoundError
        from feather.db.base import db

        instance = db.session.get(cls, id)
        if instance is None or instance.is_deleted:
            raise NotFoundError(cls.__name__, id)
        return instance


class OrderingMixin:
    """Adds position-based ordering functionality.

    Provides a position column and methods to reorder items. Supports scoped
    ordering where items are ordered within a parent (e.g., cards within a column).

    Provides:
        position: Integer column for sort order (indexed)

    Class Attributes:
        __ordering_scope__: Optional list of column names to scope ordering.
            For example, ['column_id'] means positions are unique per column.

    Instance Methods:
        move_to(position): Move to a specific position
        move_above(item): Move directly above another item
        move_below(item): Move directly below another item
        insert_at_end(): Insert at end of list

    Class Methods:
        query_ordered(**scope): Returns query sorted by position
        reorder_all(**scope): Fix gaps in position values
        get_max_position(**scope): Get highest position value

    Example::

        from feather.db import db, Model
        from feather.db.mixins import UUIDMixin, TimestampMixin, OrderingMixin

        class Column(UUIDMixin, TimestampMixin, OrderingMixin, Model):
            __tablename__ = 'columns'
            title = db.Column(db.String(100), nullable=False)

        class Card(UUIDMixin, TimestampMixin, OrderingMixin, Model):
            __tablename__ = 'cards'
            __ordering_scope__ = ['column_id']  # Position scoped per column

            title = db.Column(db.String(200), nullable=False)
            column_id = db.Column(db.String(36), db.ForeignKey('columns.id'))

        # Create cards - position is auto-set at end
        card1 = Card(title='First', column_id=col.id)
        card1.insert_at_end()
        card1.save()

        card2 = Card(title='Second', column_id=col.id)
        card2.insert_at_end()
        card2.save()

        # Reorder
        card2.move_above(card1)
        card2.save()

        # Query in order
        cards = Card.query_ordered(column_id=col.id).all()

    Note:
        When using scoped ordering, always provide scope values to class methods
        (query_ordered, reorder_all, get_max_position).
    """

    __ordering_scope__: list = []

    @declared_attr
    def position(cls):
        """Position for ordering (lower values first)."""
        return Column(Integer, nullable=False, default=0, index=True)

    def _get_scope_filter(self):
        """Get filter dict for current scope values."""
        scope = {}
        for col in getattr(self.__class__, '__ordering_scope__', []):
            scope[col] = getattr(self, col)
        return scope

    def _get_siblings_query(self):
        """Get query for items in same scope."""
        query = self.__class__.query
        for col, val in self._get_scope_filter().items():
            query = query.filter(getattr(self.__class__, col) == val)
        return query

    def insert_at_end(self) -> None:
        """Set position to end of list.

        Call this before saving a new item to place it at the end.

        Example::

            card = Card(title='New Card', column_id=col.id)
            card.insert_at_end()
            card.save()
        """
        max_pos = self.__class__.get_max_position(**self._get_scope_filter())
        self.position = max_pos + 1

    def move_to(self, new_position: int) -> None:
        """Move item to a specific position.

        Shifts other items to make room. Position 0 is the first position.

        Args:
            new_position: The target position (0-indexed).

        Example::

            card.move_to(0)  # Move to top
            card.save()
        """
        from feather.db.base import db

        if new_position < 0:
            new_position = 0

        old_position = self.position
        if old_position == new_position:
            return

        siblings = self._get_siblings_query()

        if new_position < old_position:
            # Moving up: shift items between new and old position down
            siblings.filter(
                self.__class__.position >= new_position,
                self.__class__.position < old_position,
                self.__class__.id != self.id
            ).update({self.__class__.position: self.__class__.position + 1})
        else:
            # Moving down: shift items between old and new position up
            siblings.filter(
                self.__class__.position > old_position,
                self.__class__.position <= new_position,
                self.__class__.id != self.id
            ).update({self.__class__.position: self.__class__.position - 1})

        self.position = new_position

    def move_above(self, other) -> None:
        """Move this item directly above another item.

        Args:
            other: The item to move above.

        Example::

            card2.move_above(card1)  # card2 now appears before card1
            card2.save()
        """
        if other.position <= self.position:
            self.move_to(other.position)
        else:
            self.move_to(other.position - 1)

    def move_below(self, other) -> None:
        """Move this item directly below another item.

        Args:
            other: The item to move below.

        Example::

            card1.move_below(card2)  # card1 now appears after card2
            card1.save()
        """
        if other.position >= self.position:
            self.move_to(other.position)
        else:
            self.move_to(other.position + 1)

    @classmethod
    def query_ordered(cls, **scope):
        """Return query ordered by position.

        Args:
            **scope: Scope values to filter by (e.g., column_id='abc').

        Returns:
            SQLAlchemy query sorted by position ascending.

        Example::

            # Unscoped
            columns = Column.query_ordered().all()

            # Scoped
            cards = Card.query_ordered(column_id=col.id).all()
        """
        query = cls.query
        for col, val in scope.items():
            query = query.filter(getattr(cls, col) == val)
        return query.order_by(cls.position.asc())

    @classmethod
    def get_max_position(cls, **scope) -> int:
        """Get the highest position value in scope.

        Returns -1 if no items exist, so insert_at_end() sets position to 0.

        Args:
            **scope: Scope values to filter by.

        Returns:
            Maximum position value, or -1 if no items exist.

        Example::

            max_pos = Card.get_max_position(column_id=col.id)
        """
        from feather.db.base import db
        from sqlalchemy import func

        query = db.session.query(func.max(cls.position))
        for col, val in scope.items():
            query = query.filter(getattr(cls, col) == val)
        result = query.scalar()
        return result if result is not None else -1

    @classmethod
    def reorder_all(cls, **scope) -> None:
        """Fix gaps in position values after deletions.

        Reassigns positions sequentially (0, 1, 2, ...) while maintaining
        relative order. Call this periodically or after bulk deletions.

        Args:
            **scope: Scope values to filter by.

        Example::

            # After deleting some cards, fix gaps
            Card.reorder_all(column_id=col.id)
            db.session.commit()
        """
        from feather.db.base import db

        items = cls.query_ordered(**scope).all()
        for i, item in enumerate(items):
            if item.position != i:
                item.position = i
