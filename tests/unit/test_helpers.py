"""Unit tests for helper functions.

Tests htmx_redirect, htmx_refresh, with_trigger, and related helpers.
These tests require a Flask app context for Response objects.
"""

import pytest
from flask import Flask

pytestmark = pytest.mark.unit


@pytest.fixture
def app():
    """Create a minimal Flask app for testing responses."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


class TestRedirectWithToast:
    """redirect_with_toast: one call for htmx and plain requests, toast kept."""

    @pytest.fixture
    def session_app(self, app):
        app.secret_key = "test"
        return app

    def test_htmx_request_gets_hx_redirect_and_the_toast(self, session_app):
        from flask import session

        from feather.core.helpers import redirect_with_toast

        with session_app.test_request_context('/x', headers={'HX-Request': 'true'}):
            response = redirect_with_toast('/done', 'Saved.')
            assert response.status_code == 200
            assert response.headers['HX-Redirect'] == '/done'
            assert session['_pending_toast'] == {'message': 'Saved.', 'type': 'success'}

    def test_plain_request_gets_a_302(self, session_app):
        from flask import session

        from feather.core.helpers import redirect_with_toast

        with session_app.test_request_context('/x'):
            response = redirect_with_toast('/done', 'Nope.', 'error')
            assert response.status_code == 302 and response.headers['Location'] == '/done'
            assert session['_pending_toast']['type'] == 'error'

    def test_exported_from_the_package(self):
        import feather

        assert feather.redirect_with_toast is not None and 'redirect_with_toast' in feather.__all__


class TestHtmxRedirect:
    """Test htmx_redirect helper."""

    def test_returns_response(self, app):
        """Returns a Flask Response object."""
        from feather.core.helpers import htmx_redirect

        with app.app_context():
            response = htmx_redirect('/dashboard')
            assert response is not None
            assert hasattr(response, 'headers')

    def test_sets_hx_redirect_header(self, app):
        """Sets HX-Redirect header with URL."""
        from feather.core.helpers import htmx_redirect

        with app.app_context():
            response = htmx_redirect('/dashboard')
            assert response.headers.get('HX-Redirect') == '/dashboard'

    def test_default_status_code_200(self, app):
        """Default status code is 200."""
        from feather.core.helpers import htmx_redirect

        with app.app_context():
            response = htmx_redirect('/dashboard')
            assert response.status_code == 200

    def test_custom_status_code(self, app):
        """Custom status code can be specified."""
        from feather.core.helpers import htmx_redirect

        with app.app_context():
            response = htmx_redirect('/dashboard', status_code=204)
            assert response.status_code == 204

    def test_empty_body(self, app):
        """Response body is empty."""
        from feather.core.helpers import htmx_redirect

        with app.app_context():
            response = htmx_redirect('/dashboard')
            assert response.get_data(as_text=True) == ''


class TestHtmxRefresh:
    """Test htmx_refresh helper."""

    def test_returns_response(self, app):
        """Returns a Flask Response object."""
        from feather.core.helpers import htmx_refresh

        with app.app_context():
            response = htmx_refresh()
            assert response is not None

    def test_sets_hx_refresh_header(self, app):
        """Sets HX-Refresh header to true."""
        from feather.core.helpers import htmx_refresh

        with app.app_context():
            response = htmx_refresh()
            assert response.headers.get('HX-Refresh') == 'true'

    def test_status_code_200(self, app):
        """Status code is 200."""
        from feather.core.helpers import htmx_refresh

        with app.app_context():
            response = htmx_refresh()
            assert response.status_code == 200


class TestWithTrigger:
    """Test with_trigger helper."""

    def test_returns_response(self, app):
        """Returns a Flask Response object."""
        from feather.core.helpers import with_trigger

        with app.app_context():
            response = with_trigger('<div>Updated</div>')
            assert response is not None

    def test_sets_hx_trigger_header(self, app):
        """Sets HX-Trigger header with event name."""
        from feather.core.helpers import with_trigger

        with app.app_context():
            response = with_trigger('<div>Updated</div>')
            assert response.headers.get('HX-Trigger') == 'dataUpdated'

    def test_custom_trigger_name(self, app):
        """Custom trigger name can be specified."""
        from feather.core.helpers import with_trigger

        with app.app_context():
            response = with_trigger('<div>Updated</div>', trigger='statsUpdated')
            assert response.headers.get('HX-Trigger') == 'statsUpdated'

    def test_preserves_content(self, app):
        """HTML content is preserved in response."""
        from feather.core.helpers import with_trigger

        with app.app_context():
            html = '<div class="item">Updated item</div>'
            response = with_trigger(html)
            assert response.get_data(as_text=True) == html


class TestFeatherIslandScripts:
    """Test feather_island_scripts helper."""

    def test_returns_markup(self, app):
        """Returns Markup object."""
        from feather.core.helpers import feather_island_scripts
        from markupsafe import Markup

        app.debug = True
        with app.app_context():
            result = feather_island_scripts('<div>No islands</div>')
            assert isinstance(result, Markup)

    def test_no_islands_returns_empty(self, app):
        """Returns empty string when no islands found."""
        from feather.core.helpers import feather_island_scripts

        app.debug = True
        with app.app_context():
            result = feather_island_scripts('<div>No islands here</div>')
            assert str(result) == ''

    def test_finds_single_island(self, app):
        """Finds single data-island attribute."""
        from feather.core.helpers import feather_island_scripts

        app.debug = True
        with app.app_context():
            html = '<div data-island="counter">Content</div>'
            result = feather_island_scripts(html)
            assert 'counter.js' in str(result)

    def test_finds_multiple_islands(self, app):
        """Finds multiple different islands."""
        from feather.core.helpers import feather_island_scripts

        app.debug = True
        with app.app_context():
            html = '''
            <div data-island="counter">Count</div>
            <div data-island="audio-player">Player</div>
            '''
            result = feather_island_scripts(html)
            assert 'counter.js' in str(result)
            assert 'audio-player.js' in str(result)

    def test_deduplicates_same_island(self, app):
        """Same island used multiple times only generates one script."""
        from feather.core.helpers import feather_island_scripts

        app.debug = True
        with app.app_context():
            html = '''
            <div data-island="counter">Count 1</div>
            <div data-island="counter">Count 2</div>
            '''
            result = feather_island_scripts(html)
            # Should only have one counter.js script
            assert str(result).count('counter.js') == 1

    def test_debug_mode_uses_vite_server(self, app):
        """In debug mode, uses Vite dev server URL."""
        from feather.core.helpers import feather_island_scripts

        app.debug = True
        with app.app_context():
            html = '<div data-island="test">Content</div>'
            result = feather_island_scripts(html)
            assert 'localhost:5173' in str(result)

    def test_production_mode_uses_static(self, app):
        """In production mode, uses static URL."""
        from feather.core.helpers import feather_island_scripts

        app.debug = False
        with app.app_context():
            html = '<div data-island="test">Content</div>'
            result = feather_island_scripts(html)
            assert 'localhost:5173' not in str(result)

    def test_generates_module_script_tags(self, app):
        """Generates script tags with type="module"."""
        from feather.core.helpers import feather_island_scripts

        app.debug = True
        with app.app_context():
            html = '<div data-island="counter">Content</div>'
            result = feather_island_scripts(html)
            assert 'type="module"' in str(result)
