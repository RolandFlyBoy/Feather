"""
Serialization Layer
===================

Convert models to JSON-friendly dictionaries with automatic camelCase conversion.

Serializers provide a clean way to convert your SQLAlchemy models into JSON
responses. They handle:

- Selecting which fields to include
- Converting snake_case to camelCase for JavaScript
- Custom field transformations (computed values, signed URLs, etc.)
- Nested object serialization
- Field-level type coercion

Quick Start
-----------
Define a serializer::

    from feather.serializers import Serializer
    from models import User

    class UserSerializer(Serializer):
        class Meta:
            model = User
            fields = ['id', 'email', 'username', 'display_name', 'created_at']
            camel_case = True  # email → email, display_name → displayName

        def get_avatar_url(self, user):
            '''Custom field - computed from model data.'''
            return user.profile_image_url or f'https://ui-avatars.com/api/?name={user.display_name}'

Nested Serializers
------------------
Serialize related objects::

    from feather.serializers import Serializer, NestedField

    class CommentSerializer(Serializer):
        class Meta:
            fields = ['id', 'content', 'created_at']

    class PostSerializer(Serializer):
        author = NestedField(UserSerializer)
        comments = NestedField(CommentSerializer, many=True)

        class Meta:
            fields = ['id', 'title', 'author', 'comments']

Field Types
-----------
Use Field classes for per-field customization::

    from feather.serializers import (
        Serializer, StringField, IntegerField, FloatField,
        DateTimeField, NestedField, MethodField
    )

    class ProductSerializer(Serializer):
        name = StringField()
        price = FloatField(precision=2)
        created_at = DateTimeField(format='%Y-%m-%d')

        class Meta:
            fields = ['id', 'name', 'price', 'created_at']

Use in routes::

    @api.get('/users/<user_id>')
    @inject(UserService)
    def get_user(user_id, user_service):
        user = user_service.get_by_id(user_id)
        return {'user': UserSerializer().serialize(user)}

    @api.get('/users')
    @inject(UserService)
    def list_users(user_service):
        users = user_service.list_all()
        return {'users': UserSerializer().serialize_many(users)}

See :class:`feather.serializers.Serializer` for full documentation.
"""

from feather.serializers.base import (
    Serializer,
    Field,
    StringField,
    IntegerField,
    FloatField,
    BooleanField,
    DateTimeField,
    NestedField,
    MethodField,
)

__all__ = [
    "Serializer",
    "Field",
    "StringField",
    "IntegerField",
    "FloatField",
    "BooleanField",
    "DateTimeField",
    "NestedField",
    "MethodField",
]
