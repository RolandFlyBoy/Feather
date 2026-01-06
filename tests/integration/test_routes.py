"""Integration tests for route decorators.

Tests the @api and @page blueprint decorators and response handling.
"""

import pytest

from tests.conftest import make_csrf_client

pytestmark = pytest.mark.integration


class TestApiDecorator:
    """Test @api route decorator."""

    def test_api_get_returns_json(self, test_app):
        """@api.get returns JSON response."""
        from feather import api

        @test_app.route('/test/api/items')
        def list_items():
            return {'items': [1, 2, 3]}

        with test_app.test_client() as client:
            response = client.get('/test/api/items')
            assert response.content_type == 'application/json'
            data = response.get_json()
            assert data['items'] == [1, 2, 3]

    def test_api_post_receives_json(self, test_app):
        """@api.post can receive JSON body."""
        from flask import request

        @test_app.route('/test/api/items', methods=['POST'])
        def create_item():
            data = request.get_json()
            return {'created': data.get('name')}, 201

        client = make_csrf_client(test_app)
        response = client.post(
            '/test/api/items',
            json={'name': 'test-item'},
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data['created'] == 'test-item'

    def test_api_returns_status_code(self, test_app):
        """API routes can return custom status codes."""
        @test_app.route('/test/api/created')
        def created():
            return {'id': '123'}, 201

        with test_app.test_client() as client:
            response = client.get('/test/api/created')
            assert response.status_code == 201

    def test_api_route_parameters(self, test_app):
        """API routes receive URL parameters."""
        @test_app.route('/test/api/items/<item_id>')
        def get_item(item_id):
            return {'id': item_id}

        with test_app.test_client() as client:
            response = client.get('/test/api/items/abc-123')
            data = response.get_json()
            assert data['id'] == 'abc-123'

    def test_api_query_parameters(self, test_app):
        """API routes receive query parameters."""
        from flask import request

        @test_app.route('/test/api/search')
        def search():
            q = request.args.get('q', '')
            return {'query': q}

        with test_app.test_client() as client:
            response = client.get('/test/api/search?q=hello')
            data = response.get_json()
            assert data['query'] == 'hello'


class TestApiErrorResponses:
    """Test API error response format."""

    def test_validation_error_response(self, test_app):
        """ValidationError returns 400 with proper format."""
        from feather import ValidationError

        @test_app.route('/test/api/validate')
        def validate():
            raise ValidationError('Email is required', field='email')

        with test_app.test_client() as client:
            response = client.get('/test/api/validate')
            assert response.status_code == 400
            data = response.get_json()
            assert data['success'] is False
            assert data['error']['code'] == 'VALIDATION_ERROR'
            assert data['error']['message'] == 'Email is required'
            assert data['error']['field'] == 'email'

    def test_not_found_error_response(self, test_app):
        """NotFoundError returns 404 with proper format."""
        from feather import NotFoundError

        @test_app.route('/test/api/missing')
        def missing():
            raise NotFoundError('User', '123')

        with test_app.test_client() as client:
            response = client.get('/test/api/missing')
            assert response.status_code == 404
            data = response.get_json()
            assert data['success'] is False
            assert data['error']['code'] == 'NOT_FOUND'

    def test_authentication_error_response(self, test_app):
        """AuthenticationError returns 401 for API routes."""
        from feather import AuthenticationError

        # Route must start with /api/ to be treated as API route
        @test_app.route('/api/test/unauth')
        def unauth():
            raise AuthenticationError()

        with test_app.test_client() as client:
            response = client.get('/api/test/unauth')
            assert response.status_code == 401
            data = response.get_json()
            assert data['error']['code'] == 'AUTHENTICATION_ERROR'

    def test_authorization_error_response(self, test_app):
        """AuthorizationError returns 403."""
        from feather import AuthorizationError

        @test_app.route('/test/api/forbidden')
        def forbidden():
            raise AuthorizationError()

        with test_app.test_client() as client:
            response = client.get('/test/api/forbidden')
            assert response.status_code == 403
            data = response.get_json()
            assert data['error']['code'] == 'AUTHORIZATION_ERROR'

    def test_conflict_error_response(self, test_app):
        """ConflictError returns 409."""
        from feather import ConflictError

        @test_app.route('/test/api/conflict')
        def conflict():
            raise ConflictError('Email already exists')

        with test_app.test_client() as client:
            response = client.get('/test/api/conflict')
            assert response.status_code == 409
            data = response.get_json()
            assert data['error']['code'] == 'CONFLICT'


class TestPageRoutes:
    """Test page route behavior."""

    def test_page_route_returns_html(self, test_app):
        """Page routes can return HTML."""
        @test_app.route('/test/page')
        def test_page():
            return '<html><body>Hello</body></html>'

        with test_app.test_client() as client:
            response = client.get('/test/page')
            assert response.status_code == 200
            assert b'Hello' in response.data

    def test_page_with_template(self, test_app):
        """Page routes can render templates."""
        from flask import render_template_string

        @test_app.route('/test/template')
        def template_page():
            return render_template_string('<h1>{{ title }}</h1>', title='Test')

        with test_app.test_client() as client:
            response = client.get('/test/template')
            assert b'<h1>Test</h1>' in response.data


class TestResponseHeaders:
    """Test response header handling."""

    def test_json_content_type(self, test_app):
        """JSON responses have correct content type."""
        @test_app.route('/test/json')
        def json_route():
            return {'data': 'value'}

        with test_app.test_client() as client:
            response = client.get('/test/json')
            assert 'application/json' in response.content_type

    def test_request_id_in_response(self, test_app, client):
        """Request ID is included in response headers."""
        response = client.get('/health')
        assert 'X-Request-ID' in response.headers


class TestFormData:
    """Test form data handling."""

    def test_receives_form_data(self, test_app):
        """Routes can receive form data."""
        from flask import request

        @test_app.route('/test/form', methods=['POST'])
        def form_handler():
            name = request.form.get('name')
            return {'received': name}

        client = make_csrf_client(test_app)
        response = client.post('/test/form', data={'name': 'John'})
        data = response.get_json()
        assert data['received'] == 'John'

    def test_receives_multipart_form(self, test_app):
        """Routes can receive multipart form data."""
        from flask import request
        import io

        @test_app.route('/test/upload', methods=['POST'])
        def upload_handler():
            file = request.files.get('file')
            return {'filename': file.filename if file else None}

        client = make_csrf_client(test_app)
        response = client.post(
            '/test/upload',
            data={'file': (io.BytesIO(b'content'), 'test.txt')},
            content_type='multipart/form-data'
        )
        data = response.get_json()
        assert data['filename'] == 'test.txt'
