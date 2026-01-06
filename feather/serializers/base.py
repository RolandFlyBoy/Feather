"""
Serializer Base Class
=====================

Base class for converting models to JSON-friendly dictionaries.

Why Use Serializers?
--------------------
Serializers give you control over your API responses:

- **Select fields**: Only include what the client needs
- **camelCase conversion**: Convert snake_case to camelCase for JavaScript
- **Computed fields**: Add fields that aren't on the model (avatar URLs, etc.)
- **Security**: Exclude sensitive fields (password_hash, tokens, etc.)
- **Consistency**: Same format across all your API endpoints

Quick Example
-------------
::

    from feather.serializers import Serializer

    class UserSerializer(Serializer):
        class Meta:
            model = User
            fields = ['id', 'email', 'username', 'display_name', 'created_at']
            camel_case = True

        def get_avatar_url(self, user):
            '''Add a computed avatar_url field.'''
            if user.profile_image_url:
                return user.profile_image_url
            return f'https://ui-avatars.com/api/?name={user.display_name}'

    # Usage
    serializer = UserSerializer()
    data = serializer.serialize(user)
    # {
    #     'id': '...',
    #     'email': 'user@example.com',
    #     'username': 'johndoe',
    #     'displayName': 'John Doe',  # camelCase!
    #     'createdAt': '2024-01-15T10:30:00+00:00',  # ISO format
    #     'avatarUrl': 'https://...'  # computed field
    # }
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Type, Optional, Union


# =============================================================================
# Field Classes for Custom Serialization
# =============================================================================


class Field:
    """Base field class for custom serialization.

    Use Field subclasses to customize how specific fields are serialized.

    Example::

        class UserSerializer(Serializer):
            email = StringField()
            created_at = DateTimeField(format='%Y-%m-%d')
            profile = NestedField(ProfileSerializer)

            class Meta:
                fields = ['id', 'email', 'created_at', 'profile']
    """

    def __init__(self, source: str = None):
        """Initialize a field.

        Args:
            source: Attribute name on the object. Defaults to field name.
        """
        self.source = source

    def serialize(self, value: Any, obj: Any = None, context: dict = None) -> Any:
        """Serialize a value. Override in subclasses."""
        return value


class StringField(Field):
    """Field that ensures string output.

    Example::

        class UserSerializer(Serializer):
            username = StringField()
    """

    def __init__(self, source: str = None, allow_none: bool = True):
        super().__init__(source)
        self.allow_none = allow_none

    def serialize(self, value: Any, obj: Any = None, context: dict = None) -> Optional[str]:
        if value is None:
            return None if self.allow_none else ""
        return str(value)


class IntegerField(Field):
    """Field that ensures integer output.

    Example::

        class ProductSerializer(Serializer):
            quantity = IntegerField()
    """

    def serialize(self, value: Any, obj: Any = None, context: dict = None) -> Optional[int]:
        if value is None:
            return None
        return int(value)


class FloatField(Field):
    """Field that ensures float output with optional rounding.

    Example::

        class ProductSerializer(Serializer):
            price = FloatField(precision=2)
    """

    def __init__(self, source: str = None, precision: int = None):
        super().__init__(source)
        self.precision = precision

    def serialize(self, value: Any, obj: Any = None, context: dict = None) -> Optional[float]:
        if value is None:
            return None
        result = float(value)
        if self.precision is not None:
            result = round(result, self.precision)
        return result


class BooleanField(Field):
    """Field that ensures boolean output."""

    def serialize(self, value: Any, obj: Any = None, context: dict = None) -> Optional[bool]:
        if value is None:
            return None
        return bool(value)


class DateTimeField(Field):
    """Field for datetime serialization with custom formatting.

    Example::

        class EventSerializer(Serializer):
            starts_at = DateTimeField(format='%Y-%m-%d %H:%M')
    """

    def __init__(self, source: str = None, format: str = None):
        super().__init__(source)
        self.format = format  # None means ISO format

    def serialize(self, value: Any, obj: Any = None, context: dict = None) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if self.format:
                return value.strftime(self.format)
            return value.isoformat()
        return str(value)


class NestedField(Field):
    """Field for nested serialization using another serializer.

    Example::

        class PostSerializer(Serializer):
            author = NestedField(UserSerializer)
            comments = NestedField(CommentSerializer, many=True)

            class Meta:
                fields = ['id', 'title', 'author', 'comments']
    """

    def __init__(self, serializer_class: Type["Serializer"], source: str = None, many: bool = False):
        """Initialize a nested field.

        Args:
            serializer_class: The serializer class to use for the nested object.
            source: Attribute name on the object. Defaults to field name.
            many: If True, serializes a list of objects.
        """
        super().__init__(source)
        self.serializer_class = serializer_class
        self.many = many
        self._serializer_instance = None

    @property
    def serializer(self):
        """Lazy initialization of serializer instance."""
        if self._serializer_instance is None:
            self._serializer_instance = self.serializer_class()
        return self._serializer_instance

    def serialize(self, value: Any, obj: Any = None, context: dict = None) -> Any:
        if value is None:
            return [] if self.many else None
        context = context or {}
        if self.many:
            return self.serializer.serialize_many(value, **context)
        return self.serializer.serialize(value, **context)


class MethodField(Field):
    """Field that calls a method on the serializer.

    Example::

        class UserSerializer(Serializer):
            full_name = MethodField()

            def get_full_name(self, obj, **context):
                return f"{obj.first_name} {obj.last_name}"
    """

    def __init__(self, method_name: str = None):
        """Initialize a method field.

        Args:
            method_name: Name of the method to call. Defaults to 'get_<field_name>'.
        """
        super().__init__()
        self.method_name = method_name


class Serializer:
    """Base serializer - inherit from this to create your serializers.

    Serializers convert model instances to dictionaries suitable for JSON
    responses. They handle field selection, camelCase conversion, and
    custom transformations.

    Example:
        Basic serializer::

            class PostSerializer(Serializer):
                class Meta:
                    model = Post
                    fields = ['id', 'title', 'content', 'created_at']
                    camel_case = True

        With computed fields::

            class UserSerializer(Serializer):
                class Meta:
                    model = User
                    fields = ['id', 'username', 'avatar_url', 'post_count']
                    camel_case = True

                def get_avatar_url(self, user):
                    '''Computed field - generate avatar URL.'''
                    return user.profile_image_url or default_avatar(user)

                def get_post_count(self, user, **context):
                    '''Computed field using context.'''
                    counts = context.get('post_counts', {})
                    return counts.get(user.id, 0)

        Using in routes::

            @api.get('/users/<user_id>')
            def get_user(user_id):
                user = User.get_or_404(user_id)
                return {'user': UserSerializer().serialize(user)}

            @api.get('/users')
            def list_users():
                users = User.query.all()
                # Pass context for computed fields
                post_counts = get_post_counts(users)
                return {
                    'users': UserSerializer().serialize_many(
                        users, post_counts=post_counts
                    )
                }

    Attributes:
        Meta: Inner class with configuration options:
            - model: The SQLAlchemy model class
            - fields: List of field names to include
            - exclude: List of field names to exclude (if using model auto-discovery)
            - camel_case: Convert snake_case to camelCase (default: True)
    """

    class Meta:
        """Serializer configuration options.

        Override this in your subclass to configure the serializer.
        """

        #: The model class (optional - for auto-discovering fields)
        model = None

        #: List of field names to include. If empty and model is set,
        #: all model columns are included.
        fields: List[str] = []

        #: Fields to exclude (only used with model auto-discovery)
        exclude: List[str] = []

        #: Convert snake_case to camelCase in output keys
        camel_case: bool = True

    def serialize(self, obj, **context) -> Dict[str, Any]:
        """Serialize a single object to a dictionary.

        Args:
            obj: Model instance to serialize. If None, returns None.
            **context: Additional context passed to get_<field> methods.
                Use this to pass pre-computed data for efficiency.

        Returns:
            Dictionary with serialized data, ready for JSON.

        Example::

            serializer = UserSerializer()

            # Basic usage
            data = serializer.serialize(user)

            # With context for computed fields
            data = serializer.serialize(user, current_user_id='123')
        """
        if obj is None:
            return None

        result = {}
        fields = self._get_fields()

        for field in fields:
            value = self._get_field_value(obj, field, context)
            key = self._convert_key(field)
            result[key] = self._serialize_value(value)

        return result

    def serialize_many(self, objs, **context) -> List[Dict[str, Any]]:
        """Serialize a list of objects.

        Args:
            objs: Iterable of model instances.
            **context: Additional context passed to get_<field> methods.

        Returns:
            List of serialized dictionaries.

        Example::

            users = User.query.all()
            data = UserSerializer().serialize_many(users)

            # With pre-computed data for efficiency
            post_counts = {u.id: count for u, count in get_counts(users)}
            data = UserSerializer().serialize_many(users, post_counts=post_counts)
        """
        return [self.serialize(obj, **context) for obj in objs]

    def _get_fields(self) -> List[str]:
        """Get the list of fields to serialize.

        Returns fields from Meta.fields, or auto-discovers from model.
        """
        meta = getattr(self, "Meta", None)

        if meta and meta.fields:
            return meta.fields

        if meta and meta.model:
            # Auto-discover fields from model columns
            return [col.name for col in meta.model.__table__.columns]

        return []

    def _get_field_value(self, obj, field: str, context: dict) -> Any:
        """Get the value for a field.

        Checks in order:
        1. Field class defined on serializer (e.g., author = NestedField(...))
        2. Custom get_<field> method on the serializer
        3. Attribute on the object

        Args:
            obj: The model instance.
            field: Field name.
            context: Context dict passed to serialize().

        Returns:
            The field value, possibly transformed by a Field class.
        """
        # Check for Field class on serializer
        field_instance = getattr(self.__class__, field, None)
        if isinstance(field_instance, Field):
            # Get source attribute (defaults to field name)
            source = field_instance.source or field

            # Handle MethodField specially
            if isinstance(field_instance, MethodField):
                method_name = field_instance.method_name or f"get_{field}"
                if hasattr(self, method_name):
                    return getattr(self, method_name)(obj, **context)
                return None

            # Get raw value from object
            raw_value = getattr(obj, source, None)

            # Apply field serialization
            return field_instance.serialize(raw_value, obj=obj, context=context)

        # Check for custom getter method: get_avatar_url, get_post_count, etc.
        getter_name = f"get_{field}"
        if hasattr(self, getter_name):
            getter = getattr(self, getter_name)
            return getter(obj, **context)

        # Fall back to attribute on object
        return getattr(obj, field, None)

    def _convert_key(self, key: str) -> str:
        """Convert field name to output format.

        If camel_case is True, converts snake_case to camelCase.
        """
        meta = getattr(self, "Meta", None)

        if meta and meta.camel_case:
            return self._to_camel_case(key)

        return key

    def _to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case to camelCase.

        Examples:
            created_at → createdAt
            profile_image_url → profileImageUrl
            id → id
        """
        components = snake_str.split("_")
        return components[0] + "".join(x.title() for x in components[1:])

    def _serialize_value(self, value: Any) -> Any:
        """Serialize a single value to a JSON-compatible type.

        Handles:
        - None: returns None
        - datetime: returns ISO format string
        - objects with to_dict(): calls to_dict()
        - lists/tuples: recursively serializes each item
        - everything else: returns as-is
        """
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.isoformat()

        if hasattr(value, "to_dict"):
            return value.to_dict()

        if isinstance(value, (list, tuple)):
            return [self._serialize_value(v) for v in value]

        return value
