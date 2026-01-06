"""
Event Base Class
================

Base class for all events in Feather applications.

Defining Events
---------------
Create custom events by inheriting from Event::

    from feather.events import Event

    class UserCreatedEvent(Event):
        '''Dispatched when a new user is created.'''

        def __init__(self, user_id: str, email: str):
            super().__init__(user_id=user_id)
            self.email = email

    class PostLikedEvent(Event):
        '''Dispatched when a user likes a post.'''

        def __init__(self, user_id: str, post_id: str, author_id: str):
            super().__init__(user_id=user_id)
            self.post_id = post_id
            self.author_id = author_id

Dispatching Events
------------------
Dispatch events from your services after successful actions::

    from feather import dispatch

    class UserService(Service):
        def create(self, email: str, username: str) -> User:
            user = User(email=email, username=username)
            self.save(user)

            # Dispatch AFTER successful save
            dispatch(UserCreatedEvent(user_id=user.id, email=email))

            return user

Event Properties
----------------
All events have these built-in properties:

- **timestamp**: When the event was created (UTC datetime)
- **user_id**: Optional user ID associated with the event
- **data**: Dict of any additional keyword arguments
- **event_type**: The class name (e.g., 'UserCreatedEvent')
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


class Event:
    """Base class for all events - inherit from this.

    Events represent something that happened in your application.
    They carry data about the occurrence and can be dispatched to
    trigger reactions from listeners.

    Example:
        Define a simple event::

            class UserCreatedEvent(Event):
                def __init__(self, user_id: str, email: str):
                    super().__init__(user_id=user_id)
                    self.email = email

        Define an event with more data::

            class PaymentReceivedEvent(Event):
                def __init__(self, user_id: str, amount: float, currency: str):
                    super().__init__(user_id=user_id, amount=amount, currency=currency)
                    # Access via event.data['amount'] or add as attributes:
                    self.amount = amount
                    self.currency = currency

        Dispatch the event::

            dispatch(UserCreatedEvent(user_id=user.id, email=user.email))

    Attributes:
        timestamp: When the event was created (timezone-aware UTC).
        user_id: Optional ID of the user who triggered the event.
        data: Dict containing any additional keyword arguments.

    Note:
        - Always call super().__init__() with user_id (if applicable)
        - Add custom attributes for easy access (e.g., self.email = email)
        - Events are immutable after creation
    """

    def __init__(self, user_id: Optional[str] = None, **kwargs):
        """Initialize the event.

        Args:
            user_id: Optional ID of the user associated with this event.
                This is common enough that it's a first-class parameter.
            **kwargs: Additional event data, stored in self.data dict.

        Example::

            # Simple event
            event = UserCreatedEvent(user_id='abc123', email='user@example.com')

            # The email is in event.data
            print(event.data['email'])  # 'user@example.com'

            # Better: also set as attribute in your __init__
            # self.email = email
            print(event.email)  # 'user@example.com'
        """
        self.timestamp = datetime.now(timezone.utc)
        self.user_id = user_id
        self.data = kwargs

    @property
    def event_type(self) -> str:
        """Get the event type name.

        Returns the class name, which is useful for logging and debugging.

        Returns:
            The event class name (e.g., 'UserCreatedEvent').
        """
        return self.__class__.__name__

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to a dictionary.

        Useful for logging, serialization, or audit trails.

        Returns:
            Dict with event_type, timestamp (ISO format), user_id, and data.

        Example::

            event = UserCreatedEvent(user_id='123', email='user@example.com')
            print(event.to_dict())
            # {
            #     'event_type': 'UserCreatedEvent',
            #     'timestamp': '2024-01-15T10:30:00+00:00',
            #     'user_id': '123',
            #     'data': {'email': 'user@example.com'}
            # }
        """
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "data": self.data,
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<{self.event_type} user_id={self.user_id} data={self.data}>"
