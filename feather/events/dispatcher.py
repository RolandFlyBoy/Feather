"""
Event Dispatcher
================

The pub/sub dispatcher that connects events to their listeners.

This module provides:

- **dispatch()**: Send an event to all registered listeners
- **@listen()**: Decorator to register a function as an event listener
- **EventDispatcher**: The underlying dispatcher class (for advanced use)

How It Works
------------
1. You define event classes that inherit from Event
2. You register listeners with @listen(EventClass)
3. You dispatch events with dispatch(event_instance)
4. All registered listeners are called with the event

Example Flow::

    # 1. Define event
    class UserCreatedEvent(Event):
        def __init__(self, user_id: str, email: str):
            super().__init__(user_id=user_id)
            self.email = email

    # 2. Register listener (can be anywhere, loaded at startup)
    @listen(UserCreatedEvent)
    def send_welcome_email(event):
        send_email(event.email, 'Welcome!')

    @listen(UserCreatedEvent)
    def track_signup(event):
        analytics.track('user_signup', user_id=event.user_id)

    # 3. Dispatch from service
    dispatch(UserCreatedEvent(user_id=user.id, email=user.email))

    # 4. Both listeners are called automatically

Async Listeners
---------------
Use ``async_=True`` to run listeners in a background thread::

    @listen(UserCreatedEvent, async_=True)
    def send_welcome_email(event):
        # This runs in a background thread
        send_email(event.email, 'Welcome!')

Error Handling
--------------
If a listener raises an exception, it's logged but doesn't prevent other
listeners from running. This ensures one failing listener doesn't break
the entire event chain.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Type

from flask import current_app, copy_current_request_context

from feather.events.events import Event

# Thread pool for async event handlers
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="feather_event_")
_logger = logging.getLogger(__name__)


class EventDispatcher:
    """The event dispatcher that manages listeners and dispatches events.

    You typically don't use this class directly - use dispatch() and @listen()
    instead. This class is exposed for advanced use cases like testing or
    creating isolated dispatchers.

    Example:
        Normal usage (via module functions)::

            from feather import dispatch, listen

            @listen(UserCreatedEvent)
            def handler(event):
                pass

            dispatch(UserCreatedEvent(user_id='123'))

        Advanced: Create isolated dispatcher for testing::

            dispatcher = EventDispatcher()
            dispatcher.listen(UserCreatedEvent, my_handler)
            dispatcher.dispatch(event)
    """

    def __init__(self):
        """Initialize an empty dispatcher with no listeners."""
        #: Synchronous listeners - called immediately when event is dispatched
        self._listeners: Dict[Type[Event], List[Callable]] = {}
        #: Async listeners - marked for background processing (not yet implemented)
        self._async_listeners: Dict[Type[Event], List[Callable]] = {}

    def listen(
        self,
        event_class: Type[Event],
        listener: Callable,
        async_: bool = False,
    ) -> None:
        """Register a listener for an event type.

        Args:
            event_class: The Event subclass to listen for.
            listener: Function to call when event is dispatched.
                Should accept one argument: the event instance.
            async_: If True, listener runs in a background thread pool.

        Example::

            def on_user_created(event):
                print(f"User {event.user_id} was created")

            dispatcher.listen(UserCreatedEvent, on_user_created)
        """
        listeners = self._async_listeners if async_ else self._listeners

        if event_class not in listeners:
            listeners[event_class] = []

        listeners[event_class].append(listener)

    def dispatch(self, event: Event) -> None:
        """Dispatch an event to all registered listeners.

        Calls each listener registered for this event type. If a listener
        raises an exception, it's logged but doesn't prevent other listeners
        from running.

        Args:
            event: The event instance to dispatch.

        Example::

            event = UserCreatedEvent(user_id='123', email='user@example.com')
            dispatcher.dispatch(event)
        """
        event_class = type(event)

        # Call synchronous listeners
        for listener in self._listeners.get(event_class, []):
            try:
                listener(event)
            except Exception as e:
                # Log error but continue with other listeners
                if current_app:
                    current_app.logger.error(
                        f"Error in event listener {listener.__name__}: {e}"
                    )
                else:
                    print(f"Error in event listener {listener.__name__}: {e}")

        # Call async listeners in background threads
        for listener in self._async_listeners.get(event_class, []):
            self._run_async(listener, event)

    def _run_async(self, listener: Callable, event: Event) -> None:
        """Run a listener in the background thread pool.

        Args:
            listener: The listener function to call.
            event: The event to pass to the listener.
        """
        def run_listener():
            try:
                listener(event)
            except Exception as e:
                _logger.error(f"Error in async event listener {listener.__name__}: {e}")

        _executor.submit(run_listener)


#: Global dispatcher instance used by dispatch() and @listen()
_dispatcher = EventDispatcher()


def dispatch(event: Event) -> None:
    """Dispatch an event to all registered listeners.

    This is the main function for sending events. Call it after a
    successful action in your service.

    Args:
        event: An Event instance to dispatch.

    Example::

        from feather import dispatch

        # In your service, after a successful action:
        class UserService(Service):
            def create(self, email: str, username: str) -> User:
                user = User(email=email, username=username)
                self.save(user)

                # Dispatch event AFTER successful save
                dispatch(UserCreatedEvent(user_id=user.id, email=email))

                return user

    Note:
        - Dispatch AFTER your database transaction succeeds
        - If listeners fail, exceptions are logged but don't affect your code
        - Multiple listeners for the same event all get called
    """
    _dispatcher.dispatch(event)


def listen(event_class: Type[Event], async_: bool = False) -> Callable:
    """Decorator to register a function as an event listener.

    Use this to react to events dispatched elsewhere in your application.
    Listeners are called in the order they were registered.

    Args:
        event_class: The Event subclass to listen for.
        async_: If True, marks for background processing (not yet implemented).

    Returns:
        Decorator that registers the function as a listener.

    Example:
        Basic listener::

            from feather import listen

            @listen(UserCreatedEvent)
            def on_user_created(event):
                print(f"User created: {event.user_id}")
                # Access custom attributes
                print(f"Email: {event.email}")

        Multiple listeners for same event::

            @listen(UserCreatedEvent)
            def send_welcome_email(event):
                send_email(event.email, 'Welcome!')

            @listen(UserCreatedEvent)
            def track_in_analytics(event):
                analytics.track('signup', user_id=event.user_id)

        Async listener (for future background processing)::

            @listen(UserCreatedEvent, async_=True)
            def send_welcome_email(event):
                # This will run in background when implemented
                send_email(event.email, 'Welcome!')

    Note:
        - Listeners should be defined at module level (not inside functions)
        - They're registered when the module is imported
        - Put listeners in a listeners.py file and import it at startup
    """

    def decorator(func: Callable) -> Callable:
        _dispatcher.listen(event_class, func, async_=async_)
        return func

    return decorator
