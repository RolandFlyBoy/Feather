"""Per-app backend registry (0.9.8).

Queue, cache, rate limiter, Vite manifest and (opt-in) event dispatcher live
in ``app.extensions["feather"]`` instead of module-level singletons, so two
apps in one process do not share state. Outside an app context the facades
fall back to a documented process-level default.
"""

import pytest

from feather.core.registry import feather_state, get_backend, reset_backends, set_backend

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def clean_process_defaults():
    reset_backends(app=None)
    yield
    reset_backends(app=None)


def _make_app(**config):
    from feather import Feather

    app = Feather(__name__)
    app.config["TESTING"] = True
    for key, value in config.items():
        app.config[key] = value
    return app


class TestRegistryPrimitives:
    def test_state_is_stored_under_app_extensions(self):
        app = _make_app()
        with app.app_context():
            state = feather_state()
        assert state is app.extensions["feather"]

    def test_state_outside_app_context_is_the_process_default(self):
        state = feather_state()
        assert isinstance(state, dict)
        set_backend("marker", 1)
        assert feather_state()["marker"] == 1

    def test_get_backend_calls_the_factory_once_per_app(self):
        calls = []

        def factory(app):
            calls.append(app)
            return object()

        app_a = _make_app()
        app_b = _make_app()

        with app_a.app_context():
            first = get_backend("thing", factory)
            again = get_backend("thing", factory)
        with app_b.app_context():
            other = get_backend("thing", factory)

        assert first is again
        assert other is not first
        assert len(calls) == 2

    def test_reset_backends_clears_one_app_only(self):
        app_a = _make_app()
        app_b = _make_app()
        with app_a.app_context():
            set_backend("thing", "a")
        with app_b.app_context():
            set_backend("thing", "b")

        reset_backends(app_a, "thing")

        assert "thing" not in app_a.extensions["feather"]
        assert app_b.extensions["feather"]["thing"] == "b"


class TestCacheIsolation:
    def test_two_apps_do_not_share_a_cache(self):
        from feather.cache import get_cache

        app_a = _make_app(CACHE_BACKEND="memory")
        app_b = _make_app(CACHE_BACKEND="memory")

        with app_a.app_context():
            cache_a = get_cache()
            cache_a.set("shared-key", "from-a")
        with app_b.app_context():
            cache_b = get_cache()
            assert cache_b is not cache_a
            assert cache_b.get("shared-key") is None

    def test_cache_still_works_without_an_app_context(self):
        from feather.cache import get_cache

        cache = get_cache()
        cache.set("no-app", 42)
        assert get_cache().get("no-app") == 42

    def test_init_cache_stores_on_the_app(self):
        from feather.cache import get_cache, init_cache

        app = _make_app(CACHE_BACKEND="memory")
        cache = init_cache(app)
        assert app.extensions["feather"]["cache"] is cache
        with app.app_context():
            assert get_cache() is cache

    def test_app_cache_config_is_honoured_per_app(self):
        from feather.cache import get_cache
        from feather.cache.memory import MemoryCache

        app_a = _make_app(CACHE_BACKEND="memory", CACHE_DEFAULT_TTL=11)
        app_b = _make_app(CACHE_BACKEND="memory", CACHE_DEFAULT_TTL=22)

        with app_a.app_context():
            cache_a = get_cache()
        with app_b.app_context():
            cache_b = get_cache()

        assert isinstance(cache_a, MemoryCache)
        assert cache_a._default_ttl == 11
        assert cache_b._default_ttl == 22


class TestQueueIsolation:
    def test_two_apps_do_not_share_a_queue(self):
        from feather.jobs import get_queue

        app_a = _make_app(JOB_BACKEND="sync")
        app_b = _make_app(JOB_BACKEND="sync")

        with app_a.app_context():
            queue_a = get_queue()
        with app_b.app_context():
            queue_b = get_queue()

        assert queue_a is not queue_b

    def test_backend_choice_is_per_app(self):
        from feather.jobs import get_queue
        from feather.jobs.sync import SyncQueue
        from feather.jobs.thread import ThreadPoolQueue

        app_sync = _make_app(JOB_BACKEND="sync")
        app_thread = _make_app(JOB_BACKEND="thread", JOB_MAX_WORKERS=1)

        with app_sync.app_context():
            assert isinstance(get_queue(), SyncQueue)
        with app_thread.app_context():
            queue = get_queue()
            assert isinstance(queue, ThreadPoolQueue)
        queue.shutdown(wait=False)

    def test_queue_still_works_without_an_app_context(self):
        from feather.jobs import get_queue
        from feather.jobs.base import JobQueue

        assert isinstance(get_queue(), JobQueue)

    def test_init_jobs_stores_on_the_app(self):
        from feather.jobs import init_jobs

        app = _make_app(JOB_BACKEND="sync")
        queue = init_jobs(app)
        assert app.extensions["feather"]["queue"] is queue


class TestRateLimiterIsolation:
    def test_two_apps_have_separate_rate_limit_counters(self):
        from feather.auth.decorators import get_rate_limiter

        app_a = _make_app()
        app_b = _make_app()

        with app_a.app_context():
            limiter_a = get_rate_limiter()
            limiter_a.is_allowed("key", 1, 60)
            assert limiter_a.is_allowed("key", 1, 60)[0] is False
        with app_b.app_context():
            limiter_b = get_rate_limiter()
            assert limiter_b is not limiter_a
            assert limiter_b.is_allowed("key", 1, 60)[0] is True

    def test_rate_limiter_works_without_an_app_context(self):
        from feather.auth.decorators import get_rate_limiter

        limiter = get_rate_limiter()
        assert limiter.is_allowed("outside", 1, 60)[0] is True


class TestManifestIsolation:
    def test_manifest_cache_is_per_app(self, tmp_path):
        import json

        from feather.core.helpers import _resolve_asset

        static_a = tmp_path / "a" / "static"
        static_b = tmp_path / "b" / "static"
        for folder, filename in ((static_a, "a.js"), (static_b, "b.js")):
            manifest_dir = folder / "dist" / ".vite"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "manifest.json").write_text(
                json.dumps({"static/js/feather.js": {"file": filename}})
            )

        app_a = _make_app()
        app_b = _make_app()
        app_a.static_folder = str(static_a)
        app_b.static_folder = str(static_b)

        assert _resolve_asset(app_a, "feather") == "/static/dist/a.js"
        assert _resolve_asset(app_b, "feather") == "/static/dist/b.js"
        # And again, from the cache this time.
        assert _resolve_asset(app_a, "feather") == "/static/dist/a.js"


class TestDispatcherFacade:
    def test_get_dispatcher_defaults_to_the_process_dispatcher(self):
        from feather.events import get_dispatcher
        from feather.events.dispatcher import _dispatcher

        app = _make_app()
        assert get_dispatcher() is _dispatcher
        with app.app_context():
            assert get_dispatcher() is _dispatcher

    def test_an_app_can_opt_into_its_own_dispatcher(self):
        from feather.events import EventDispatcher, dispatch, get_dispatcher
        from feather.events.events import Event

        class Ping(Event):
            pass

        app = _make_app()
        own = EventDispatcher()
        app.extensions.setdefault("feather", {})["dispatcher"] = own

        seen = []
        own.listen(Ping, lambda event: seen.append(event))

        with app.app_context():
            assert get_dispatcher() is own
            dispatch(Ping())

        assert len(seen) == 1


class TestFeatherAppSetsUpState:
    def test_feather_app_has_the_extension_key_from_the_start(self):
        app = _make_app()
        assert app.extensions["feather"] == {} or isinstance(app.extensions["feather"], dict)

    def test_plain_flask_app_still_works_through_the_facades(self):
        """A bare Flask app (no Feather) gets its state created on demand."""
        from flask import Flask

        from feather.cache import get_cache

        plain = Flask(__name__)
        with plain.app_context():
            cache = get_cache()
        assert plain.extensions["feather"]["cache"] is cache
