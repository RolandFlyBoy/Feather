"""Unit tests for serializers.

Tests the serializer field types, camelCase conversion, and serialization logic.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.unit


class TestCamelCaseConversion:
    """Test snake_case to camelCase conversion."""

    def test_single_word(self):
        """Single word stays unchanged."""
        from feather.serializers import Serializer

        class TestSerializer(Serializer):
            class Meta:
                fields = ['id', 'email']
                camel_case = True

        s = TestSerializer()
        assert s._to_camel_case('id') == 'id'
        assert s._to_camel_case('email') == 'email'

    def test_two_words(self):
        """Two-word snake_case converts properly."""
        from feather.serializers import Serializer

        class TestSerializer(Serializer):
            class Meta:
                fields = []
                camel_case = True

        s = TestSerializer()
        assert s._to_camel_case('created_at') == 'createdAt'
        assert s._to_camel_case('user_id') == 'userId'

    def test_multiple_words(self):
        """Multiple-word snake_case converts properly."""
        from feather.serializers import Serializer

        class TestSerializer(Serializer):
            class Meta:
                fields = []
                camel_case = True

        s = TestSerializer()
        assert s._to_camel_case('profile_image_url') == 'profileImageUrl'
        assert s._to_camel_case('last_login_at') == 'lastLoginAt'

    def test_camel_case_disabled(self):
        """Keys stay snake_case when camel_case is False."""
        from feather.serializers import Serializer

        class TestSerializer(Serializer):
            class Meta:
                fields = ['created_at']
                camel_case = False

        obj = Mock(created_at=datetime(2024, 1, 15))
        result = TestSerializer().serialize(obj)
        assert 'created_at' in result
        assert 'createdAt' not in result


class TestStringField:
    """Test StringField serialization."""

    def test_string_value(self):
        """String values pass through."""
        from feather.serializers import StringField

        field = StringField()
        assert field.serialize('hello') == 'hello'

    def test_integer_to_string(self):
        """Integers are converted to strings."""
        from feather.serializers import StringField

        field = StringField()
        assert field.serialize(123) == '123'

    def test_none_allowed(self):
        """None is allowed by default."""
        from feather.serializers import StringField

        field = StringField(allow_none=True)
        assert field.serialize(None) is None

    def test_none_to_empty_string(self):
        """None converts to empty string when allow_none=False."""
        from feather.serializers import StringField

        field = StringField(allow_none=False)
        assert field.serialize(None) == ''


class TestIntegerField:
    """Test IntegerField serialization."""

    def test_integer_value(self):
        """Integer values pass through."""
        from feather.serializers import IntegerField

        field = IntegerField()
        assert field.serialize(42) == 42

    def test_string_to_integer(self):
        """Numeric strings are converted to integers."""
        from feather.serializers import IntegerField

        field = IntegerField()
        assert field.serialize('123') == 123

    def test_float_to_integer(self):
        """Floats are truncated to integers."""
        from feather.serializers import IntegerField

        field = IntegerField()
        assert field.serialize(3.9) == 3

    def test_none_value(self):
        """None returns None."""
        from feather.serializers import IntegerField

        field = IntegerField()
        assert field.serialize(None) is None


class TestFloatField:
    """Test FloatField serialization."""

    def test_float_value(self):
        """Float values pass through."""
        from feather.serializers import FloatField

        field = FloatField()
        assert field.serialize(3.14) == 3.14

    def test_integer_to_float(self):
        """Integers are converted to floats."""
        from feather.serializers import FloatField

        field = FloatField()
        assert field.serialize(42) == 42.0
        assert isinstance(field.serialize(42), float)

    def test_precision_rounding(self):
        """Values are rounded to specified precision."""
        from feather.serializers import FloatField

        field = FloatField(precision=2)
        assert field.serialize(3.14159) == 3.14

    def test_precision_zero_decimals(self):
        """Precision of 0 rounds to whole numbers."""
        from feather.serializers import FloatField

        field = FloatField(precision=0)
        assert field.serialize(3.7) == 4.0

    def test_none_value(self):
        """None returns None."""
        from feather.serializers import FloatField

        field = FloatField()
        assert field.serialize(None) is None


class TestBooleanField:
    """Test BooleanField serialization."""

    def test_true_value(self):
        """True passes through."""
        from feather.serializers import BooleanField

        field = BooleanField()
        assert field.serialize(True) is True

    def test_false_value(self):
        """False passes through."""
        from feather.serializers import BooleanField

        field = BooleanField()
        assert field.serialize(False) is False

    def test_truthy_to_true(self):
        """Truthy values convert to True."""
        from feather.serializers import BooleanField

        field = BooleanField()
        assert field.serialize(1) is True
        assert field.serialize('yes') is True
        assert field.serialize([1]) is True

    def test_falsy_to_false(self):
        """Falsy values convert to False."""
        from feather.serializers import BooleanField

        field = BooleanField()
        assert field.serialize(0) is False
        assert field.serialize('') is False
        assert field.serialize([]) is False

    def test_none_value(self):
        """None returns None."""
        from feather.serializers import BooleanField

        field = BooleanField()
        assert field.serialize(None) is None


class TestDateTimeField:
    """Test DateTimeField serialization."""

    def test_iso_format_default(self):
        """Default format is ISO 8601."""
        from feather.serializers import DateTimeField

        field = DateTimeField()
        dt = datetime(2024, 1, 15, 10, 30, 0)
        assert field.serialize(dt) == '2024-01-15T10:30:00'

    def test_custom_format(self):
        """Custom format is applied."""
        from feather.serializers import DateTimeField

        field = DateTimeField(format='%Y-%m-%d')
        dt = datetime(2024, 1, 15, 10, 30, 0)
        assert field.serialize(dt) == '2024-01-15'

    def test_time_format(self):
        """Time-only format works."""
        from feather.serializers import DateTimeField

        field = DateTimeField(format='%H:%M')
        dt = datetime(2024, 1, 15, 10, 30, 0)
        assert field.serialize(dt) == '10:30'

    def test_none_value(self):
        """None returns None."""
        from feather.serializers import DateTimeField

        field = DateTimeField()
        assert field.serialize(None) is None

    def test_non_datetime_to_string(self):
        """Non-datetime values are converted to strings."""
        from feather.serializers import DateTimeField

        field = DateTimeField()
        assert field.serialize('2024-01-15') == '2024-01-15'


class TestNestedField:
    """Test NestedField serialization."""

    def test_single_nested_object(self):
        """Single nested object is serialized."""
        from feather.serializers import Serializer, NestedField

        class AuthorSerializer(Serializer):
            class Meta:
                fields = ['id', 'name']
                camel_case = False

        class PostSerializer(Serializer):
            author = NestedField(AuthorSerializer)

            class Meta:
                fields = ['id', 'title', 'author']
                camel_case = False

        author = Mock(id='1')
        author.name = 'John'  # 'name' is reserved in Mock(), must set separately
        post = Mock(id='10', title='Hello', author=author)

        result = PostSerializer().serialize(post)
        assert result['author'] == {'id': '1', 'name': 'John'}

    def test_nested_list(self):
        """Nested list of objects is serialized."""
        from feather.serializers import Serializer, NestedField

        class CommentSerializer(Serializer):
            class Meta:
                fields = ['id', 'text']
                camel_case = False

        class PostSerializer(Serializer):
            comments = NestedField(CommentSerializer, many=True)

            class Meta:
                fields = ['id', 'comments']
                camel_case = False

        comments = [Mock(id='1', text='First'), Mock(id='2', text='Second')]
        post = Mock(id='10', comments=comments)

        result = PostSerializer().serialize(post)
        assert len(result['comments']) == 2
        assert result['comments'][0] == {'id': '1', 'text': 'First'}

    def test_none_single(self):
        """None for single nested returns None."""
        from feather.serializers import Serializer, NestedField

        class AuthorSerializer(Serializer):
            class Meta:
                fields = ['id']
                camel_case = False

        class PostSerializer(Serializer):
            author = NestedField(AuthorSerializer)

            class Meta:
                fields = ['id', 'author']
                camel_case = False

        post = Mock(id='10', author=None)
        result = PostSerializer().serialize(post)
        assert result['author'] is None

    def test_none_many(self):
        """None for many nested returns empty list."""
        from feather.serializers import Serializer, NestedField

        class CommentSerializer(Serializer):
            class Meta:
                fields = ['id']
                camel_case = False

        class PostSerializer(Serializer):
            comments = NestedField(CommentSerializer, many=True)

            class Meta:
                fields = ['id', 'comments']
                camel_case = False

        post = Mock(id='10', comments=None)
        result = PostSerializer().serialize(post)
        assert result['comments'] == []


class TestMethodField:
    """Test MethodField serialization."""

    def test_default_method_name(self):
        """Default method name is get_<field_name>."""
        from feather.serializers import Serializer, MethodField

        class UserSerializer(Serializer):
            full_name = MethodField()

            class Meta:
                fields = ['id', 'full_name']
                camel_case = False

            def get_full_name(self, obj, **context):
                return f"{obj.first_name} {obj.last_name}"

        user = Mock(id='1', first_name='John', last_name='Doe')
        result = UserSerializer().serialize(user)
        assert result['full_name'] == 'John Doe'

    def test_custom_method_name(self):
        """Custom method name can be specified."""
        from feather.serializers import Serializer, MethodField

        class UserSerializer(Serializer):
            display_name = MethodField(method_name='compute_display_name')

            class Meta:
                fields = ['display_name']
                camel_case = False

            def compute_display_name(self, obj, **context):
                return obj.username.upper()

        user = Mock(username='johndoe')
        result = UserSerializer().serialize(user)
        assert result['display_name'] == 'JOHNDOE'

    def test_method_receives_context(self):
        """Method receives context kwargs."""
        from feather.serializers import Serializer, MethodField

        class UserSerializer(Serializer):
            is_current = MethodField()

            class Meta:
                fields = ['id', 'is_current']
                camel_case = False

            def get_is_current(self, obj, current_user_id=None, **context):
                return obj.id == current_user_id

        user = Mock(id='123')
        result = UserSerializer().serialize(user, current_user_id='123')
        assert result['is_current'] is True

        result = UserSerializer().serialize(user, current_user_id='456')
        assert result['is_current'] is False


class TestSerializer:
    """Test base Serializer class."""

    def test_serialize_none(self):
        """Serializing None returns None."""
        from feather.serializers import Serializer

        class TestSerializer(Serializer):
            class Meta:
                fields = ['id']

        assert TestSerializer().serialize(None) is None

    def test_serialize_simple_object(self):
        """Simple object serialization."""
        from feather.serializers import Serializer

        class UserSerializer(Serializer):
            class Meta:
                fields = ['id', 'email', 'username']
                camel_case = False

        user = Mock(id='123', email='test@example.com', username='testuser')
        result = UserSerializer().serialize(user)

        assert result == {
            'id': '123',
            'email': 'test@example.com',
            'username': 'testuser'
        }

    def test_serialize_with_camel_case(self):
        """Serialization with camelCase conversion."""
        from feather.serializers import Serializer

        class UserSerializer(Serializer):
            class Meta:
                fields = ['id', 'email', 'created_at', 'last_login_at']
                camel_case = True

        user = Mock(
            id='123',
            email='test@example.com',
            created_at=datetime(2024, 1, 15),
            last_login_at=datetime(2024, 1, 20)
        )
        result = UserSerializer().serialize(user)

        assert 'id' in result
        assert 'email' in result
        assert 'createdAt' in result
        assert 'lastLoginAt' in result
        assert 'created_at' not in result

    def test_serialize_many(self):
        """Serializing multiple objects."""
        from feather.serializers import Serializer

        class UserSerializer(Serializer):
            class Meta:
                fields = ['id', 'email']
                camel_case = False

        users = [
            Mock(id='1', email='user1@example.com'),
            Mock(id='2', email='user2@example.com'),
        ]
        result = UserSerializer().serialize_many(users)

        assert len(result) == 2
        assert result[0] == {'id': '1', 'email': 'user1@example.com'}
        assert result[1] == {'id': '2', 'email': 'user2@example.com'}

    def test_datetime_auto_serialization(self):
        """Datetime fields are auto-serialized to ISO format."""
        from feather.serializers import Serializer

        class EventSerializer(Serializer):
            class Meta:
                fields = ['id', 'starts_at']
                camel_case = False

        event = Mock(id='1', starts_at=datetime(2024, 1, 15, 10, 30, 0))
        result = EventSerializer().serialize(event)

        assert result['starts_at'] == '2024-01-15T10:30:00'

    def test_custom_getter_method(self):
        """Custom get_<field> methods are called."""
        from feather.serializers import Serializer

        class UserSerializer(Serializer):
            class Meta:
                fields = ['id', 'avatar_url']
                camel_case = False

            def get_avatar_url(self, obj, **context):
                return f"https://avatars.com/{obj.id}"

        user = Mock(id='123')
        result = UserSerializer().serialize(user)

        assert result['avatar_url'] == 'https://avatars.com/123'

    def test_field_source_attribute(self):
        """Field source attribute allows different attribute names."""
        from feather.serializers import Serializer, StringField

        class UserSerializer(Serializer):
            name = StringField(source='display_name')

            class Meta:
                fields = ['id', 'name']
                camel_case = False

        user = Mock(id='1', display_name='John Doe')
        result = UserSerializer().serialize(user)

        assert result['name'] == 'John Doe'

    def test_context_passed_to_serialize_many(self):
        """Context is passed through serialize_many."""
        from feather.serializers import Serializer, MethodField

        class UserSerializer(Serializer):
            post_count = MethodField()

            class Meta:
                fields = ['id', 'post_count']
                camel_case = False

            def get_post_count(self, obj, counts=None, **context):
                return counts.get(obj.id, 0) if counts else 0

        users = [Mock(id='1'), Mock(id='2')]
        counts = {'1': 5, '2': 10}
        result = UserSerializer().serialize_many(users, counts=counts)

        assert result[0]['post_count'] == 5
        assert result[1]['post_count'] == 10

    def test_to_dict_method_called(self):
        """Objects with to_dict() have it called."""
        from feather.serializers import Serializer

        class TestSerializer(Serializer):
            class Meta:
                fields = ['id', 'profile']
                camel_case = False

        profile = Mock()
        profile.to_dict.return_value = {'bio': 'Hello', 'website': 'example.com'}
        user = Mock(id='1', profile=profile)

        result = TestSerializer().serialize(user)

        assert result['profile'] == {'bio': 'Hello', 'website': 'example.com'}
        profile.to_dict.assert_called_once()

    def test_list_values_serialized(self):
        """List values have each item serialized."""
        from feather.serializers import Serializer

        class TestSerializer(Serializer):
            class Meta:
                fields = ['id', 'timestamps']
                camel_case = False

        timestamps = [datetime(2024, 1, 1), datetime(2024, 1, 2)]
        obj = Mock(id='1', timestamps=timestamps)

        result = TestSerializer().serialize(obj)

        assert result['timestamps'] == ['2024-01-01T00:00:00', '2024-01-02T00:00:00']
