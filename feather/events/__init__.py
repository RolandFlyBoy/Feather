"""
Event System
============

Pub/sub pattern for loose coupling between components in Feather applications.

Events allow different parts of your application to communicate without knowing
about each other. When something happens (like a user signing up), you dispatch
an event. Other parts of your app can listen for that event and react to it.

Why Use Events?
---------------
- **Loose coupling**: Services don't need to know about each other
- **Extensibility**: Add new behaviors without modifying existing code
- **Audit trails**: Events can be logged for debugging or analytics
- **Async processing**: Queue time-consuming tasks (like emails) for later

Quick Start
-----------
1. Define an event::

    from feather.events import Event

    class UserCreatedEvent(Event):
        def __init__(self, user_id: str, email: str):
            super().__init__(user_id=user_id)
            self.email = email

2. Register a listener::

    from feather import listen

    @listen(UserCreatedEvent)
    def send_welcome_email(event):
        print(f"Sending welcome email to {event.email}")

3. Dispatch the event (from a service)::

    from feather import dispatch

    class UserService(Service):
        def create(self, email: str, username: str) -> User:
            user = User(email=email, username=username)
            self.save(user)

            # Dispatch event after successful save
            dispatch(UserCreatedEvent(user_id=user.id, email=email))

            return user

Exports
-------
- **Event**: Base class for all events
- **dispatch**: Function to dispatch an event to all listeners
- **listen**: Decorator to register a function as an event listener
- **EventDispatcher**: The dispatcher class (for advanced use)

See Also
--------
- :mod:`feather.events.events`: Event base class documentation
- :mod:`feather.events.dispatcher`: Dispatcher implementation
"""

from feather.events.dispatcher import dispatch, listen, EventDispatcher
from feather.events.events import Event

__all__ = ["dispatch", "listen", "Event", "EventDispatcher"]
