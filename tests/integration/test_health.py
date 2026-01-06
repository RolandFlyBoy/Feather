"""Integration tests for health check endpoints.

Tests the /health, /health/live, and /health/ready endpoints used by
load balancers and Kubernetes probes.
"""

import pytest
from unittest.mock import patch, MagicMock
from feather import Feather


pytestmark = pytest.mark.integration


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def health_app():
    """Create a test app with health endpoints."""
    from feather.db import db

    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'

    with app.app_context():
        db.create_all()

    # Yield OUTSIDE app_context for proper CSRF isolation
    yield app

    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


# =============================================================================
# Test /health Endpoint
# =============================================================================

class TestHealthEndpoint:
    """Tests for the main /health endpoint."""

    def test_health_returns_200_when_healthy(self, health_app):
        """Health check returns 200 when all checks pass."""
        client = health_app.test_client()
        response = client.get('/health')

        assert response.status_code == 200

    def test_health_status_is_healthy(self, health_app):
        """Status field is 'healthy' when checks pass."""
        client = health_app.test_client()
        response = client.get('/health')

        data = response.get_json()
        assert data['status'] == 'healthy'

    def test_health_has_timestamp(self, health_app):
        """Health response includes ISO timestamp."""
        client = health_app.test_client()
        response = client.get('/health')

        data = response.get_json()
        assert 'timestamp' in data
        # ISO format contains 'T'
        assert 'T' in data['timestamp']

    def test_health_has_checks_object(self, health_app):
        """Health response includes checks object."""
        client = health_app.test_client()
        response = client.get('/health')

        data = response.get_json()
        assert 'checks' in data
        assert isinstance(data['checks'], dict)

    def test_health_includes_database_check(self, health_app):
        """Health response includes database check."""
        client = health_app.test_client()
        response = client.get('/health')

        data = response.get_json()
        assert 'database' in data['checks']
        assert data['checks']['database'] == 'ok'

    def test_health_returns_json_content_type(self, health_app):
        """Health endpoint returns JSON content type."""
        client = health_app.test_client()
        response = client.get('/health')

        assert 'application/json' in response.content_type


class TestHealthEndpointDatabaseDown:
    """Tests for /health when database is unavailable."""

    def test_health_returns_503_when_db_down(self, health_app):
        """Health check returns 503 when database check fails."""
        client = health_app.test_client()

        # Mock db.session.execute to raise an exception
        with patch('feather.db.db.session') as mock_session:
            mock_session.execute.side_effect = Exception('Connection refused')
            response = client.get('/health')

        assert response.status_code == 503

    def test_health_status_is_unhealthy_when_db_down(self, health_app):
        """Status field is 'unhealthy' when database check fails."""
        client = health_app.test_client()

        with patch('feather.db.db.session') as mock_session:
            mock_session.execute.side_effect = Exception('Connection refused')
            response = client.get('/health')

        data = response.get_json()
        assert data['status'] == 'unhealthy'

    def test_health_shows_db_error_message(self, health_app):
        """Database check shows error message when failed."""
        client = health_app.test_client()

        with patch('feather.db.db.session') as mock_session:
            mock_session.execute.side_effect = Exception('Connection refused')
            response = client.get('/health')

        data = response.get_json()
        assert 'error' in data['checks']['database']
        assert 'Connection refused' in data['checks']['database']


class TestHealthEndpointNoDatabase:
    """Tests for /health when no database is configured."""

    def test_health_returns_200_without_db(self, health_app):
        """Health check returns 200 when database config is empty."""
        client = health_app.test_client()

        # Temporarily remove the database URI
        with patch.dict(health_app.config, {'SQLALCHEMY_DATABASE_URI': None}):
            response = client.get('/health')

        assert response.status_code == 200

    def test_database_check_skipped_without_db(self, health_app):
        """Database check is skipped when no URI configured."""
        client = health_app.test_client()

        with patch.dict(health_app.config, {'SQLALCHEMY_DATABASE_URI': None}):
            response = client.get('/health')

        data = response.get_json()
        assert data['checks']['database'] == 'skipped'


# =============================================================================
# Test /health/live Endpoint
# =============================================================================

class TestLivenessEndpoint:
    """Tests for the /health/live liveness probe."""

    def test_live_always_returns_200(self, health_app):
        """Liveness probe always returns 200."""
        client = health_app.test_client()
        response = client.get('/health/live')

        assert response.status_code == 200

    def test_live_status_is_alive(self, health_app):
        """Liveness probe returns status: alive."""
        client = health_app.test_client()
        response = client.get('/health/live')

        data = response.get_json()
        assert data['status'] == 'alive'

    def test_live_does_not_check_database(self, health_app):
        """Liveness probe doesn't check database."""
        client = health_app.test_client()

        # Even if db check would fail, liveness should pass
        with patch('feather.db.db.session') as mock_session:
            mock_session.execute.side_effect = Exception('Connection refused')
            response = client.get('/health/live')

        assert response.status_code == 200

    def test_live_returns_200_without_db_config(self, health_app):
        """Liveness probe returns 200 even without database."""
        client = health_app.test_client()

        with patch.dict(health_app.config, {'SQLALCHEMY_DATABASE_URI': None}):
            response = client.get('/health/live')

        assert response.status_code == 200


# =============================================================================
# Test /health/ready Endpoint
# =============================================================================

class TestReadinessEndpoint:
    """Tests for the /health/ready readiness probe."""

    def test_ready_returns_200_when_healthy(self, health_app):
        """Readiness probe returns 200 when all checks pass."""
        client = health_app.test_client()
        response = client.get('/health/ready')

        assert response.status_code == 200

    def test_ready_returns_503_when_db_down(self, health_app):
        """Readiness probe returns 503 when database check fails."""
        client = health_app.test_client()

        with patch('feather.db.db.session') as mock_session:
            mock_session.execute.side_effect = Exception('Connection refused')
            response = client.get('/health/ready')

        assert response.status_code == 503

    def test_ready_has_same_format_as_health(self, health_app):
        """Readiness probe has same response format as /health."""
        client = health_app.test_client()
        response = client.get('/health/ready')

        data = response.get_json()
        assert 'status' in data
        assert 'timestamp' in data
        assert 'checks' in data

    def test_ready_checks_database(self, health_app):
        """Readiness probe checks database connectivity."""
        client = health_app.test_client()
        response = client.get('/health/ready')

        data = response.get_json()
        assert 'database' in data['checks']
        assert data['checks']['database'] == 'ok'


# =============================================================================
# Test Response Format Contract
# =============================================================================

class TestHealthResponseFormat:
    """Contract tests for health endpoint response format."""

    def test_response_is_json(self, health_app):
        """All health endpoints return JSON."""
        client = health_app.test_client()

        for endpoint in ['/health', '/health/live', '/health/ready']:
            response = client.get(endpoint)
            assert response.is_json, f"{endpoint} should return JSON"

    def test_timestamp_is_iso_format(self, health_app):
        """Timestamps are ISO 8601 format."""
        client = health_app.test_client()
        response = client.get('/health')

        data = response.get_json()
        timestamp = data['timestamp']

        # ISO format: YYYY-MM-DDTHH:MM:SS.ffffff+HH:MM or Z
        assert 'T' in timestamp
        assert timestamp.count('-') >= 2  # Date has at least 2 dashes
        assert ':' in timestamp  # Time has colons

    def test_status_is_string(self, health_app):
        """Status field is a string."""
        client = health_app.test_client()
        response = client.get('/health')

        data = response.get_json()
        assert isinstance(data['status'], str)

    def test_checks_values_are_strings(self, health_app):
        """Check values are strings."""
        client = health_app.test_client()
        response = client.get('/health')

        data = response.get_json()
        for check_name, check_value in data['checks'].items():
            assert isinstance(check_value, str), f"{check_name} should be string"
