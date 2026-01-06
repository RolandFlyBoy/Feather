"""
Service Layer
=============

Base class for business logic services in Feather applications.

Services are where you put your application's business logic. They sit between
your routes (which handle HTTP) and your models (which handle persistence).
This pattern keeps your code organized and testable.

The Rule
--------
**Routes should be thin controllers. Services contain the logic.**

Instead of::

    @api.post('/users')
    def create_user():
        data = request.get_json()
        if User.query.filter_by(email=data['email']).first():
            raise ValidationError('Email taken')
        user = User(**data)
        db.session.add(user)
        db.session.commit()
        send_welcome_email(user)  # Side effect
        return {'user': user.to_dict()}, 201

Do this::

    # services/user_service.py
    class UserService(Service):
        def create(self, email: str, username: str) -> User:
            if User.query.filter_by(email=email).first():
                raise ValidationError('Email taken')
            user = User(email=email, username=username)
            self.save(user)
            dispatch(UserCreatedEvent(user_id=user.id))
            return user

    # routes/api/users.py
    @api.post('/users')
    @inject(UserService)
    def create_user(user_service):
        data = request.get_json()
        user = user_service.create(**data)
        return {'user': user.to_dict()}, 201

Quick Start
-----------
Create a service in services/user_service.py::

    from feather import Service
    from feather.exceptions import ValidationError, NotFoundError
    from models import User

    class UserService(Service):
        def get_by_id(self, user_id: str) -> User:
            return self.get_or_404(User, user_id)

        def create(self, email: str, username: str) -> User:
            if User.query.filter_by(email=email).first():
                raise ValidationError('Email already taken', field='email')

            user = User(email=email, username=username)
            self.save(user)
            return user

        def update(self, user_id: str, **kwargs) -> User:
            user = self.get_or_404(User, user_id)
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            self.commit()
            return user

Use in routes with @inject::

    from feather import api, inject
    from services import UserService

    @api.get('/users/<user_id>')
    @inject(UserService)
    def get_user(user_id, user_service):
        user = user_service.get_by_id(user_id)
        return {'user': user.to_dict()}
"""

from typing import TypeVar, Generic, Type, Optional, Dict

from flask import current_app

from feather.db import db
from feather.exceptions import NotFoundError

#: Type variable for generic model types in service methods
T = TypeVar("T")


# =============================================================================
# Service Registry
# =============================================================================


class ServiceRegistry:
    """Registry for singleton service instances.

    By default, services are instantiated per-request via @inject. Use the
    registry when you need:

    - Expensive initialization (connection pools, caches)
    - Shared state across requests
    - Singleton pattern for services

    Example:
        Register a service as singleton::

            from feather.services import registry

            # Option 1: Manual registration
            registry.register(CacheService, CacheService())

            # Option 2: Use @singleton decorator
            @singleton
            class CacheService(Service):
                def __init__(self):
                    self.cache = {}  # Shared across requests

        Get registered service::

            cache_service = registry.get(CacheService)
            # Or use @inject - it checks registry first
            @inject(CacheService)
            def my_route(cache_service):
                pass
    """

    def __init__(self):
        self._services: Dict[Type, object] = {}

    def register(self, service_class: Type[T], instance: T) -> None:
        """Register a singleton service instance.

        Args:
            service_class: The service class.
            instance: The singleton instance.
        """
        self._services[service_class] = instance

    def get(self, service_class: Type[T]) -> Optional[T]:
        """Get a registered service instance.

        Args:
            service_class: The service class.

        Returns:
            The singleton instance, or None if not registered.
        """
        return self._services.get(service_class)

    def has(self, service_class: Type) -> bool:
        """Check if a service is registered.

        Args:
            service_class: The service class.

        Returns:
            True if registered, False otherwise.
        """
        return service_class in self._services

    def clear(self) -> None:
        """Clear all registered services (useful for testing)."""
        self._services.clear()


#: Global service registry
registry = ServiceRegistry()


def singleton(cls: Type[T]) -> Type[T]:
    """Decorator to register a service class as a singleton.

    The instance is created lazily on first access and reused thereafter.

    Example::

        from feather.services import singleton, Service

        @singleton
        class CacheService(Service):
            def __init__(self):
                super().__init__()
                self.cache = {}

            def get(self, key):
                return self.cache.get(key)

            def set(self, key, value):
                self.cache[key] = value

        # First access creates the instance
        # Subsequent accesses return the same instance
        @inject(CacheService)
        def my_route(cache_service):
            cache_service.set('key', 'value')
    """
    _instance = None

    class SingletonWrapper(cls):
        def __new__(cls_inner, *args, **kwargs):
            nonlocal _instance
            if _instance is None:
                _instance = super().__new__(cls_inner)
                cls.__init__(_instance, *args, **kwargs)
                registry.register(cls, _instance)
            return _instance

        def __init__(self, *args, **kwargs):
            # Skip __init__ after first creation
            pass

    SingletonWrapper.__name__ = cls.__name__
    SingletonWrapper.__qualname__ = cls.__qualname__
    return SingletonWrapper


class Service:
    """Base class for all services - inherit from this.

    Services contain your application's business logic. They provide:
    - Database access via self.db (the SQLAlchemy session)
    - Convenience methods: get_or_404(), save(), delete()
    - Transaction control: commit(), rollback()

    Example:
        Create a service::

            from feather import Service
            from feather.exceptions import ValidationError, NotFoundError
            from models import Post

            class PostService(Service):
                def get_by_id(self, post_id: str) -> Post:
                    '''Get post by ID or raise 404.'''
                    return self.get_or_404(Post, post_id)

                def create(self, user_id: str, title: str, content: str) -> Post:
                    '''Create a new post.'''
                    if not title:
                        raise ValidationError('Title is required', field='title')

                    post = Post(user_id=user_id, title=title, content=content)
                    self.save(post)
                    return post

                def delete(self, post_id: str, user_id: str) -> None:
                    '''Delete a post (only owner can delete).'''
                    post = self.get_or_404(Post, post_id)

                    if post.user_id != user_id:
                        raise AuthorizationError('Not your post')

                    super().delete(post)

        Use with @inject in routes::

            from feather import api, auth_required, inject
            from services import PostService

            @api.get('/posts/<post_id>')
            @inject(PostService)
            def get_post(post_id, post_service):
                post = post_service.get_by_id(post_id)
                return {'post': post.to_dict()}

            @api.delete('/posts/<post_id>')
            @auth_required
            @inject(PostService)
            def delete_post(post_id, post_service):
                post_service.delete(post_id, user_id=current_user.id)
                return '', 204

    Note:
        - Services are instantiated per-request by @inject (not singletons)
        - Use self.db for database operations (it's the SQLAlchemy session)
        - Raise exceptions for errors - they become JSON responses
    """

    def __init__(self, database=None):
        """Initialize the service.

        Args:
            database: Optional SQLAlchemy session. Defaults to db.session.
                This is mainly useful for testing with a mock session.

        Example:
            Normal usage (via @inject)::

                @api.get('/users')
                @inject(UserService)
                def list_users(user_service):
                    # user_service is created with default db.session
                    pass

            Testing with mock::

                mock_session = MagicMock()
                service = UserService(database=mock_session)
        """
        self._db = database
        self.on_init()

    def on_init(self) -> None:
        """Called when service is instantiated.

        Override to perform initialization like creating HTTP clients,
        opening connections, or loading configuration.

        Example::

            import httpx

            class ExternalApiService(Service):
                def on_init(self):
                    self.client = httpx.Client(timeout=30)

                def on_cleanup(self):
                    self.client.close()

                def fetch_data(self, endpoint: str) -> dict:
                    response = self.client.get(f"https://api.example.com/{endpoint}")
                    return response.json()

        Note:
            For singleton services (@singleton), on_init() is only called once.
            For per-request services (via @inject), on_init() is called each request.
        """
        pass

    def on_cleanup(self) -> None:
        """Called when service should release resources.

        Override to close connections, cleanup temporary files,
        or release other resources.

        The @inject decorator automatically calls on_cleanup() after the
        request completes for non-singleton services.

        Example::

            import httpx

            class ExternalApiService(Service):
                def on_init(self):
                    self.client = httpx.Client(timeout=30)

                def on_cleanup(self):
                    self.client.close()

        Note:
            - For singleton services, on_cleanup() is not automatically called
            - Singleton cleanup should be done via app shutdown hooks
            - Cleanup errors are logged but don't break the request
        """
        pass

    @property
    def db(self):
        """Get the database session.

        Returns:
            SQLAlchemy session for database operations.

        Example::

            class UserService(Service):
                def create(self, email: str, username: str) -> User:
                    user = User(email=email, username=username)
                    self.db.add(user)
                    self.db.commit()
                    return user

                def search(self, query: str) -> list[User]:
                    return self.db.query(User).filter(
                        User.username.ilike(f'%{query}%')
                    ).all()
        """
        if self._db is not None:
            return self._db
        return db.session

    def get_or_404(self, model: Type[T], id: str) -> T:
        """Get a model instance by ID or raise NotFoundError.

        This is the recommended way to fetch a single record by ID.
        Uses SQLAlchemy 2.0's Session.get() for optimal performance.

        Args:
            model: The model class to query (e.g., User, Post).
            id: The primary key value (usually a UUID string).

        Returns:
            The model instance.

        Raises:
            NotFoundError: If no record with this ID exists (becomes 404).

        Example::

            class PostService(Service):
                def get_by_id(self, post_id: str) -> Post:
                    return self.get_or_404(Post, post_id)

                def add_comment(self, post_id: str, content: str) -> Comment:
                    post = self.get_or_404(Post, post_id)
                    comment = Comment(post_id=post.id, content=content)
                    self.save(comment)
                    return comment
        """
        instance = self.db.get(model, id)
        if instance is None:
            raise NotFoundError(model.__name__, id)
        return instance

    def save(self, instance) -> None:
        """Save a model instance to the database.

        Adds the instance to the session and commits the transaction.
        Use this for both creating new records and updating existing ones.

        Args:
            instance: The model instance to save.

        Example::

            def create(self, email: str, username: str) -> User:
                user = User(email=email, username=username)
                self.save(user)  # INSERT and COMMIT
                return user

            def update(self, user_id: str, email: str) -> User:
                user = self.get_or_404(User, user_id)
                user.email = email
                self.save(user)  # UPDATE and COMMIT
                return user
        """
        self.db.add(instance)
        self.db.commit()

    def delete(self, instance) -> None:
        """Delete a model instance from the database.

        Removes the instance and commits the transaction.

        Args:
            instance: The model instance to delete.

        Example::

            def delete_post(self, post_id: str, user_id: str) -> None:
                post = self.get_or_404(Post, post_id)
                if post.user_id != user_id:
                    raise AuthorizationError('Not your post')
                self.delete(post)  # DELETE and COMMIT
        """
        self.db.delete(instance)
        self.db.commit()

    def commit(self) -> None:
        """Commit the current transaction.

        Use this when you've made multiple changes and want to commit
        them together, or when you've modified an object without calling
        save() (which auto-commits).

        Example::

            def bulk_update(self, user_ids: list, active: bool) -> None:
                for user_id in user_ids:
                    user = self.get_or_404(User, user_id)
                    user.active = active
                    self.db.add(user)  # Stage change
                self.commit()  # Commit all at once
        """
        self.db.commit()

    def rollback(self) -> None:
        """Rollback the current transaction.

        Undoes all uncommitted changes in the current transaction.
        Use this when an error occurs and you want to discard changes.

        Example::

            def transfer_funds(self, from_id: str, to_id: str, amount: float) -> None:
                try:
                    from_account = self.get_or_404(Account, from_id)
                    to_account = self.get_or_404(Account, to_id)

                    from_account.balance -= amount
                    to_account.balance += amount

                    self.commit()
                except Exception:
                    self.rollback()  # Undo both changes
                    raise
        """
        self.db.rollback()


# =============================================================================
# Transaction Decorator
# =============================================================================


def transactional(f):
    """Decorator to wrap a service method in a database transaction.

    Automatically commits on success and rolls back on any exception.
    This is useful for service methods that perform multiple database
    operations that should succeed or fail together.

    The decorated method should NOT call commit() or save() - the decorator
    handles the transaction lifecycle.

    Example::

        from feather import Service
        from feather.services import transactional

        class OrderService(Service):
            @transactional
            def create_order(self, user_id: str, items: list) -> Order:
                '''Create an order with line items - all or nothing.'''
                order = Order(user_id=user_id, status='pending')
                self.db.add(order)

                for item in items:
                    line = OrderLine(
                        order_id=order.id,
                        product_id=item['product_id'],
                        quantity=item['quantity'],
                    )
                    self.db.add(line)

                # Auto-commits on success
                return order

            @transactional
            def transfer_funds(self, from_id: str, to_id: str, amount: float):
                '''Transfer between accounts - atomic operation.'''
                from_account = self.get_or_404(Account, from_id)
                to_account = self.get_or_404(Account, to_id)

                if from_account.balance < amount:
                    raise ValidationError('Insufficient funds')

                from_account.balance -= amount
                to_account.balance += amount

                # Auto-commits on success, auto-rollback on error

    Note:
        - Only use on Service methods (requires self.db)
        - Don't call self.save() or self.commit() inside - it auto-commits
        - Any exception triggers a rollback and re-raises
        - The transaction boundary is the decorated method
    """
    from functools import wraps

    @wraps(f)
    def decorated(self, *args, **kwargs):
        try:
            result = f(self, *args, **kwargs)
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    return decorated
