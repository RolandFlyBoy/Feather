"""
Pagination Helper
=================

Simple, efficient pagination utilities for SQLAlchemy queries.

This module provides a clean way to paginate database queries and return
results with metadata useful for building paginated UIs.

Quick Start
-----------
Paginate any SQLAlchemy query::

    from feather.db.pagination import paginate

    # In a service or route
    result = paginate(Post.query.order_by(Post.created_at.desc()), page=1, per_page=20)

    # Access results
    posts = result.items           # List of Post objects
    total = result.total           # Total number of posts
    pages = result.pages           # Total number of pages
    has_next = result.has_next     # Boolean: is there a next page?
    has_prev = result.has_prev     # Boolean: is there a previous page?

API Response
------------
Include pagination metadata in your API response::

    @api.get('/posts')
    def list_posts():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        result = paginate(Post.query_active(), page=page, per_page=per_page)

        return {
            'data': [post.to_dict() for post in result.items],
            'pagination': result.to_dict(),
        }

    # Response:
    # {
    #     "data": [...],
    #     "pagination": {
    #         "page": 1,
    #         "perPage": 20,
    #         "total": 156,
    #         "pages": 8,
    #         "hasNext": true,
    #         "hasPrev": false
    #     }
    # }
"""

from dataclasses import dataclass
from typing import TypeVar, Generic, List, Optional

T = TypeVar("T")


@dataclass
class PaginatedResult(Generic[T]):
    """Container for paginated query results.

    This class holds both the items for the current page and metadata
    about the pagination state.

    Attributes:
        items: List of model instances for the current page
        page: Current page number (1-indexed)
        per_page: Number of items per page
        total: Total number of items across all pages

    Properties:
        pages: Total number of pages
        has_next: True if there's a next page
        has_prev: True if there's a previous page
        next_page: Next page number (or None)
        prev_page: Previous page number (or None)

    Example::

        result = paginate(Post.query, page=2, per_page=10)

        print(f"Showing page {result.page} of {result.pages}")
        print(f"Total posts: {result.total}")

        if result.has_next:
            print(f"Next page: {result.next_page}")

        for post in result.items:
            print(post.title)
    """

    items: List[T]
    page: int
    per_page: int
    total: int

    @property
    def pages(self) -> int:
        """Total number of pages.

        Returns:
            Number of pages, or 0 if per_page is 0.
        """
        if self.per_page == 0:
            return 0
        return (self.total + self.per_page - 1) // self.per_page

    @property
    def has_next(self) -> bool:
        """Check if there's a next page.

        Returns:
            True if current page is less than total pages.
        """
        return self.page < self.pages

    @property
    def has_prev(self) -> bool:
        """Check if there's a previous page.

        Returns:
            True if current page is greater than 1.
        """
        return self.page > 1

    @property
    def next_page(self) -> Optional[int]:
        """Get the next page number.

        Returns:
            Next page number, or None if on last page.
        """
        return self.page + 1 if self.has_next else None

    @property
    def prev_page(self) -> Optional[int]:
        """Get the previous page number.

        Returns:
            Previous page number, or None if on first page.
        """
        return self.page - 1 if self.has_prev else None

    @property
    def start_index(self) -> int:
        """Get the 1-indexed position of the first item on this page.

        Useful for displaying "Showing 21-40 of 156 items".

        Returns:
            Start index (1-indexed), or 0 if no items.
        """
        if self.total == 0:
            return 0
        return (self.page - 1) * self.per_page + 1

    @property
    def end_index(self) -> int:
        """Get the 1-indexed position of the last item on this page.

        Useful for displaying "Showing 21-40 of 156 items".

        Returns:
            End index (1-indexed), or 0 if no items.
        """
        if self.total == 0:
            return 0
        return min(self.page * self.per_page, self.total)

    def to_dict(self) -> dict:
        """Convert pagination metadata to a dictionary.

        Returns a camelCase dictionary suitable for JSON API responses.
        Does NOT include the items themselves - serialize those separately.

        Returns:
            Dict with pagination metadata.

        Example::

            @api.get('/posts')
            def list_posts():
                result = paginate(Post.query, page=1, per_page=20)
                return {
                    'data': [p.to_dict() for p in result.items],
                    'pagination': result.to_dict(),
                }
        """
        return {
            "page": self.page,
            "perPage": self.per_page,
            "total": self.total,
            "pages": self.pages,
            "hasNext": self.has_next,
            "hasPrev": self.has_prev,
        }


def paginate(query, page: int = 1, per_page: int = 20, max_per_page: int = 100) -> PaginatedResult:
    """Paginate a SQLAlchemy query.

    Takes any SQLAlchemy query and returns a PaginatedResult with the
    items for the requested page plus pagination metadata.

    Args:
        query: SQLAlchemy query to paginate. Can be a Query object or
               a model class (e.g., Post.query or Post).
        page: Page number (1-indexed). Defaults to 1. Values less than 1
              are clamped to 1.
        per_page: Number of items per page. Defaults to 20. Clamped between
                  1 and max_per_page.
        max_per_page: Maximum allowed items per page. Defaults to 100.
                      Prevents clients from requesting too many items.

    Returns:
        PaginatedResult containing items and pagination metadata.

    Example::

        from feather.db.pagination import paginate

        # Basic usage
        result = paginate(Post.query, page=1, per_page=20)

        # With filters and ordering
        result = paginate(
            Post.query_active()
                .filter_by(user_id=user_id)
                .order_by(Post.created_at.desc()),
            page=page,
            per_page=per_page,
        )

        # Access results
        for post in result.items:
            print(post.title)

        # Check navigation
        if result.has_next:
            print(f"Load more: page {result.next_page}")

    Note:
        The function executes two queries: one COUNT query for the total,
        and one LIMIT/OFFSET query for the items. For very large tables,
        consider using cursor-based pagination instead.
    """
    # Ensure query is a Query object
    if hasattr(query, "query"):
        query = query.query

    # Clamp page to at least 1
    page = max(1, page)

    # Clamp per_page between 1 and max_per_page
    per_page = max(1, min(max_per_page, per_page))

    # Get total count
    total = query.count()

    # Calculate offset
    offset = (page - 1) * per_page

    # Get items for this page
    items = query.offset(offset).limit(per_page).all()

    return PaginatedResult(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
    )
