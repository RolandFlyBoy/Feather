"""
Database Layer
==============

SQLAlchemy database setup and base model class for Feather applications.

This module provides:

- **db**: The SQLAlchemy database instance
- **Model**: Base class for all your models with helpful methods
- **migrate**: Flask-Migrate instance for database migrations

Quick Start
-----------
Create a model in models/user.py::

    from feather.db import db, Model
    import uuid
    from datetime import datetime, timezone

    class User(Model):
        __tablename__ = 'users'

        id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
        email = db.Column(db.String(255), unique=True, nullable=False)
        username = db.Column(db.String(50), unique=True, nullable=False)
        created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

        def __repr__(self):
            return f'<User {self.username}>'

Use the model::

    # Create
    user = User(email='user@example.com', username='johndoe')
    user.save()

    # Read
    user = User.get_by_id('some-uuid')
    user = User.get_or_404('some-uuid')  # Raises NotFoundError if not found

    # Query (standard SQLAlchemy)
    users = User.query.filter_by(active=True).all()

    # Update
    user.email = 'new@example.com'
    user.save()

    # Delete
    user.delete()

Migrations
----------
Use the CLI to manage database migrations::

    feather db init      # Initialize migrations (first time only)
    feather db migrate   # Generate migration from model changes
    feather db upgrade   # Apply pending migrations
    feather db downgrade # Rollback the last migration

See Also
--------
- :class:`feather.Service`: Business logic layer that uses models
- :mod:`feather.exceptions`: Error handling (NotFoundError, etc.)
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy declarative base.

    This is an internal class used to configure SQLAlchemy 2.0's declarative base.
    You don't need to use this directly - inherit from Model instead.
    """

    # Allow classic Column() syntax without Mapped[] type annotations
    __allow_unmapped__ = True


#: The SQLAlchemy database instance.
#: Use db.Column, db.String, db.Integer, etc. to define model columns.
#: Access the session via db.session for queries.
db = SQLAlchemy(model_class=Base)

#: Flask-Migrate instance for database migrations.
#: Managed via CLI: feather db init/migrate/upgrade/downgrade
migrate = Migrate()


class Model(db.Model):
    """Base model class - inherit from this for all your models.

    Provides common functionality that all models need:
    - save() and delete() methods for easy persistence
    - get_by_id() and get_or_404() class methods for retrieval
    - to_dict() for basic serialization

    Example:
        Define a model::

            from feather.db import db, Model
            import uuid
            from datetime import datetime, timezone

            class Post(Model):
                __tablename__ = 'posts'

                # Always use UUID strings for primary keys
                id = db.Column(db.String(36), primary_key=True,
                               default=lambda: str(uuid.uuid4()))

                title = db.Column(db.String(200), nullable=False)
                content = db.Column(db.Text)
                user_id = db.Column(db.String(36), db.ForeignKey('users.id'))

                # Timestamps
                created_at = db.Column(db.DateTime,
                                       default=lambda: datetime.now(timezone.utc))
                updated_at = db.Column(db.DateTime,
                                       onupdate=lambda: datetime.now(timezone.utc))

                # Relationships
                user = db.relationship('User', backref='posts')

        Use the model::

            # Create and save
            post = Post(title='Hello', content='World', user_id=user.id)
            post.save()

            # Get by ID
            post = Post.get_or_404('some-uuid')  # Raises if not found

            # Query (standard SQLAlchemy)
            posts = Post.query.filter_by(user_id=user.id).all()

            # Delete
            post.delete()

    Note:
        - Always define __tablename__ explicitly
        - Use db.String(36) for UUID primary keys
        - Use lambda for datetime defaults (not datetime.now() directly)
        - Use db.relationship() for model relationships
    """

    # Mark as abstract so SQLAlchemy doesn't create a table for this class
    __abstract__ = True

    # Allow classic Column() syntax without Mapped[] type annotations
    __allow_unmapped__ = True

    def save(self):
        """Save this model instance to the database.

        Adds the instance to the session and commits. If the instance
        is new, it will be inserted. If it already exists, it will be updated.

        Example::

            user = User(email='user@example.com', username='johndoe')
            user.save()  # INSERT

            user.email = 'new@example.com'
            user.save()  # UPDATE
        """
        db.session.add(self)
        db.session.commit()

    def delete(self):
        """Delete this model instance from the database.

        Removes the instance from the session and commits.

        Example::

            user = User.get_or_404(user_id)
            user.delete()  # DELETE FROM users WHERE id = ...
        """
        db.session.delete(self)
        db.session.commit()

    @classmethod
    def get_by_id(cls, id):
        """Get a model instance by its primary key ID.

        Uses SQLAlchemy 2.0's Session.get() method which is more efficient
        than Query.get() as it checks the identity map first.

        Args:
            id: The primary key value (usually a UUID string).

        Returns:
            The model instance if found, None otherwise.

        Example::

            user = User.get_by_id('550e8400-e29b-41d4-a716-446655440000')
            if user:
                print(user.username)
        """
        return db.session.get(cls, id)

    @classmethod
    def get_or_404(cls, id):
        """Get a model instance by ID or raise NotFoundError.

        Same as get_by_id(), but raises NotFoundError if the instance
        is not found. This is the recommended method for API endpoints
        where a missing resource should return a 404 error.

        Args:
            id: The primary key value (usually a UUID string).

        Returns:
            The model instance.

        Raises:
            NotFoundError: If no instance with this ID exists (404).

        Example::

            # In an API route - will return 404 if user not found
            @api.get('/users/<user_id>')
            def get_user(user_id):
                user = User.get_or_404(user_id)
                return {'user': user.to_dict()}
        """
        from feather.exceptions import NotFoundError

        instance = db.session.get(cls, id)
        if instance is None:
            raise NotFoundError(cls.__name__, id)
        return instance

    def to_dict(self):
        """Convert this model instance to a dictionary.

        Returns a dict with all column values. Override this method in
        your model subclass for custom serialization (e.g., to exclude
        sensitive fields or include computed values).

        Returns:
            Dict mapping column names to their values.

        Example::

            user = User.get_by_id(user_id)
            data = user.to_dict()
            # {'id': '...', 'email': '...', 'username': '...', ...}

        Customization::

            class User(Model):
                # ... columns ...

                def to_dict(self):
                    '''Custom serialization excluding password.'''
                    return {
                        'id': self.id,
                        'email': self.email,
                        'username': self.username,
                        # Exclude password_hash for security
                    }
        """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
