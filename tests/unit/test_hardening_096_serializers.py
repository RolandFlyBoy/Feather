"""0.9.6 hardening: serializer auto-discovery skips secret-bearing columns."""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def account_model():
    """A model with the kind of columns that must never leak by default."""
    from tests.conftest import feather_app
    from feather.db import db

    with feather_app(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:") as app:
        class Account(db.Model):
            __tablename__ = "hardening_096_accounts"
            id = db.Column(db.Integer, primary_key=True)
            email = db.Column(db.String(255))
            password_hash = db.Column(db.String(255))
            google_refresh_token = db.Column(db.String(255))
            API_KEY = db.Column(db.String(255))
            client_secret = db.Column(db.String(255))
            private_key_pem = db.Column(db.Text)
            access_token_expires_at = db.Column(db.String(64))
            tokens_used = db.Column(db.Integer)  # matches *token* too, by design
            password_changed_at = db.Column(db.String(64))

        with app.app_context():
            db.create_all()
            account = Account(
                id=1,
                email="a@example.com",
                password_hash="hash",
                google_refresh_token="1//refresh",
                API_KEY="key",
                client_secret="shh",
                private_key_pem="-----BEGIN",
                access_token_expires_at="soon",
                tokens_used=3,
                password_changed_at="yesterday",
            )
            yield Account, account


class TestSensitiveColumnAutoDiscovery:
    def test_auto_discovery_skips_secret_columns(self, account_model):
        from feather.serializers import Serializer

        Account, account = account_model

        class AccountSerializer(Serializer):
            class Meta:
                model = Account
                camel_case = False

        data = AccountSerializer().serialize(account)

        assert data == {"id": 1, "email": "a@example.com"}
        for leaked in (
            "password_hash", "google_refresh_token", "API_KEY", "client_secret",
            "private_key_pem", "access_token_expires_at", "tokens_used",
            "password_changed_at",
        ):
            assert leaked not in data

    def test_explicit_fields_are_still_serialised(self, account_model):
        from feather.serializers import Serializer

        Account, account = account_model

        class TokenSerializer(Serializer):
            class Meta:
                model = Account
                fields = ["id", "google_refresh_token", "password_hash"]
                camel_case = False

        data = TokenSerializer().serialize(account)
        assert data == {"id": 1, "google_refresh_token": "1//refresh", "password_hash": "hash"}

    def test_patterns_can_be_extended_per_serializer(self, account_model):
        from feather.serializers import Serializer

        Account, account = account_model

        class StrictSerializer(Serializer):
            sensitive_field_patterns = Serializer.sensitive_field_patterns + ["email"]

            class Meta:
                model = Account
                camel_case = False

        assert StrictSerializer().serialize(account) == {"id": 1}

    def test_is_sensitive_field_helper(self):
        from feather.serializers import Serializer

        s = Serializer()
        for name in (
            "token", "TOKEN", "refresh_token", "google_refresh_token", "token_hash",
            "secret", "client_secret", "SECRET_KEY", "password", "password_hash",
            "api_key", "stripe_api_key", "private_key", "rsa_private_key_pem",
        ):
            assert s._is_sensitive_field(name), name
        for name in ("id", "email", "username", "created_at", "keyword", "display_name"):
            assert not s._is_sensitive_field(name), name
