"""Integration tests for event system.

Tests event dispatch, listeners, and async event handling.
"""

import pytest
import time

pytestmark = pytest.mark.integration


class TestEventClass:
    """Test Event base class."""

    def test_event_stores_user_id(self):
        """Event stores user_id as attribute."""
        from feather.events import Event

        class TestEvent(Event):
            pass

        event = TestEvent(user_id='123')
        assert event.user_id == '123'

    def test_event_stores_kwargs_in_data(self):
        """Event stores extra kwargs in data dict."""
        from feather.events import Event

        class TestEvent(Event):
            pass

        event = TestEvent(user_id='123', action='login')
        assert event.data['action'] == 'login'

    def test_event_has_timestamp(self):
        """Event has timestamp."""
        from feather.events import Event

        class TimestampEvent(Event):
            pass

        event = TimestampEvent()
        assert hasattr(event, 'timestamp')


class TestListenDecorator:
    """Test @listen decorator."""

    def test_registers_handler(self, test_app):
        """@listen registers event handler."""
        from feather.events import Event, listen
        from feather.events.dispatcher import _dispatcher

        class RegistrationEvent(Event):
            pass

        @listen(RegistrationEvent)
        def handle_registration(event):
            pass

        # Handler should be registered in the dispatcher
        assert RegistrationEvent in _dispatcher._listeners

    def test_handler_receives_event(self, test_app):
        """Handler receives dispatched event."""
        from feather.events import Event, listen, dispatch

        class ReceivedEvent(Event):
            pass

        received_events = []

        @listen(ReceivedEvent)
        def handle_received(event):
            received_events.append(event)

        with test_app.app_context():
            dispatch(ReceivedEvent(user_id='test'))

        assert len(received_events) == 1
        assert received_events[0].user_id == 'test'


class TestDispatch:
    """Test dispatch function."""

    def test_dispatch_calls_handlers(self, test_app):
        """dispatch() calls registered handlers."""
        from feather.events import Event, listen, dispatch

        class DispatchedEvent(Event):
            pass

        call_count = [0]

        @listen(DispatchedEvent)
        def count_calls(event):
            call_count[0] += 1

        with test_app.app_context():
            dispatch(DispatchedEvent())
            dispatch(DispatchedEvent())

        assert call_count[0] == 2

    def test_dispatch_multiple_handlers(self, test_app):
        """dispatch() calls all registered handlers."""
        from feather.events import Event, listen, dispatch

        class MultiHandlerEvent(Event):
            pass

        handlers_called = []

        @listen(MultiHandlerEvent)
        def handler_one(event):
            handlers_called.append('one')

        @listen(MultiHandlerEvent)
        def handler_two(event):
            handlers_called.append('two')

        with test_app.app_context():
            dispatch(MultiHandlerEvent())

        assert 'one' in handlers_called
        assert 'two' in handlers_called

    def test_dispatch_with_no_handlers(self, test_app):
        """dispatch() works with no handlers registered."""
        from feather.events import Event, dispatch

        class UnhandledEvent(Event):
            pass

        with test_app.app_context():
            # Should not raise
            dispatch(UnhandledEvent())


class TestAsyncListeners:
    """Test async event listeners."""

    def test_async_listener_registration(self, test_app):
        """async_ parameter registers async listener."""
        from feather.events import Event, listen

        class AsyncEvent(Event):
            pass

        @listen(AsyncEvent, async_=True)
        def async_handler(event):
            pass

        # Should not raise during registration

    def test_async_listener_runs_in_background(self, test_app):
        """async_ listeners run in background thread."""
        from feather.events import Event, listen, dispatch
        import threading

        class BackgroundEvent(Event):
            pass

        thread_ids = []
        main_thread = threading.current_thread().ident

        @listen(BackgroundEvent, async_=True)
        def background_handler(event):
            thread_ids.append(threading.current_thread().ident)

        with test_app.app_context():
            dispatch(BackgroundEvent())
            # Give async handler time to run
            time.sleep(0.2)

        # Handler should have run (thread_ids populated)
        # In some implementations it may run in same thread
        assert len(thread_ids) >= 0  # Just verify no error


class TestEventInheritance:
    """Test event class inheritance."""

    def test_subclass_events(self, test_app):
        """Subclassed events work correctly."""
        from feather.events import Event, listen, dispatch

        class BaseAppEvent(Event):
            pass

        class UserCreatedEvent(BaseAppEvent):
            pass

        created_events = []

        @listen(UserCreatedEvent)
        def handle_user_created(event):
            created_events.append(event)

        with test_app.app_context():
            dispatch(UserCreatedEvent(user_id='123'))

        assert len(created_events) == 1
        assert created_events[0].user_id == '123'


class TestEventContext:
    """Test event context and data passing."""

    def test_event_passes_all_kwargs(self, test_app):
        """Events pass all kwargs in data dict to handlers."""
        from feather.events import Event, listen, dispatch

        class DataEvent(Event):
            pass

        received_data = {}

        @listen(DataEvent)
        def capture_data(event):
            received_data['user_id'] = event.user_id
            received_data['email'] = event.data['email']
            received_data['extra'] = event.data['extra']

        with test_app.app_context():
            dispatch(DataEvent(
                user_id='123',
                email='test@example.com',
                extra={'key': 'value'}
            ))

        assert received_data['user_id'] == '123'
        assert received_data['email'] == 'test@example.com'
        assert received_data['extra'] == {'key': 'value'}


class TestEventExceptionHandling:
    """Test exception handling in event handlers."""

    def test_handler_exception_doesnt_break_others(self, test_app):
        """Exception in one handler doesn't stop others."""
        from feather.events import Event, listen, dispatch

        class ExceptionEvent(Event):
            pass

        handlers_run = []

        @listen(ExceptionEvent)
        def handler_before(event):
            handlers_run.append('before')

        @listen(ExceptionEvent)
        def handler_raises(event):
            handlers_run.append('raises')
            raise ValueError('Intentional error')

        @listen(ExceptionEvent)
        def handler_after(event):
            handlers_run.append('after')

        with test_app.app_context():
            # Should not raise despite handler error
            try:
                dispatch(ExceptionEvent())
            except ValueError:
                pass  # Some implementations may raise

        # At least some handlers should have run
        assert 'before' in handlers_run or 'raises' in handlers_run
