"""Unit tests for pagination.

Tests the PaginatedResult class and its computed properties.
The paginate() function requires a database and is tested in integration tests.
"""

import pytest

pytestmark = pytest.mark.unit


class TestPaginatedResultBasic:
    """Test PaginatedResult basic functionality."""

    def test_stores_items(self):
        """PaginatedResult stores items list."""
        from feather.db.pagination import PaginatedResult

        items = [1, 2, 3]
        result = PaginatedResult(items=items, page=1, per_page=10, total=3)
        assert result.items == items

    def test_stores_page(self):
        """PaginatedResult stores current page."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=5, per_page=10, total=100)
        assert result.page == 5

    def test_stores_per_page(self):
        """PaginatedResult stores per_page."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=25, total=100)
        assert result.per_page == 25

    def test_stores_total(self):
        """PaginatedResult stores total count."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=10, total=156)
        assert result.total == 156


class TestPagesProperty:
    """Test the pages property calculation."""

    def test_exact_division(self):
        """100 items at 10 per page = 10 pages."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=10, total=100)
        assert result.pages == 10

    def test_with_remainder(self):
        """105 items at 10 per page = 11 pages."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=10, total=105)
        assert result.pages == 11

    def test_less_than_per_page(self):
        """5 items at 10 per page = 1 page."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=10, total=5)
        assert result.pages == 1

    def test_zero_total(self):
        """0 items = 0 pages."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=10, total=0)
        assert result.pages == 0

    def test_zero_per_page(self):
        """0 per_page = 0 pages (avoid division by zero)."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=0, total=100)
        assert result.pages == 0

    def test_single_item(self):
        """1 item at any per_page = 1 page."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=1)
        assert result.pages == 1


class TestHasNextProperty:
    """Test the has_next property."""

    def test_has_next_on_first_page(self):
        """First page of multi-page results has next."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=10, total=50)
        assert result.has_next is True

    def test_no_next_on_last_page(self):
        """Last page has no next."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=5, per_page=10, total=50)
        assert result.has_next is False

    def test_no_next_on_single_page(self):
        """Single page results have no next."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=10, total=5)
        assert result.has_next is False

    def test_no_next_on_empty(self):
        """Empty results have no next."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=10, total=0)
        assert result.has_next is False


class TestHasPrevProperty:
    """Test the has_prev property."""

    def test_no_prev_on_first_page(self):
        """First page has no previous."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=10, total=50)
        assert result.has_prev is False

    def test_has_prev_on_second_page(self):
        """Second page has previous."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=2, per_page=10, total=50)
        assert result.has_prev is True

    def test_has_prev_on_last_page(self):
        """Last page has previous."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=5, per_page=10, total=50)
        assert result.has_prev is True


class TestNextPageProperty:
    """Test the next_page property."""

    def test_next_page_number(self):
        """Returns next page number."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=2, per_page=10, total=50)
        assert result.next_page == 3

    def test_next_page_none_on_last(self):
        """Returns None on last page."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=5, per_page=10, total=50)
        assert result.next_page is None


class TestPrevPageProperty:
    """Test the prev_page property."""

    def test_prev_page_number(self):
        """Returns previous page number."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=3, per_page=10, total=50)
        assert result.prev_page == 2

    def test_prev_page_none_on_first(self):
        """Returns None on first page."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=10, total=50)
        assert result.prev_page is None


class TestStartEndIndex:
    """Test start_index and end_index properties."""

    def test_start_index_first_page(self):
        """Start index is 1 on first page."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=156)
        assert result.start_index == 1

    def test_start_index_second_page(self):
        """Start index is 21 on second page (20 per page)."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=2, per_page=20, total=156)
        assert result.start_index == 21

    def test_end_index_first_page(self):
        """End index is per_page on first page."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=156)
        assert result.end_index == 20

    def test_end_index_last_page_partial(self):
        """End index is total on partial last page."""
        from feather.db.pagination import PaginatedResult

        # 156 items, 20 per page, page 8 has items 141-156
        result = PaginatedResult(items=[], page=8, per_page=20, total=156)
        assert result.end_index == 156

    def test_start_index_empty(self):
        """Start index is 0 for empty results."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=0)
        assert result.start_index == 0

    def test_end_index_empty(self):
        """End index is 0 for empty results."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=0)
        assert result.end_index == 0


class TestToDict:
    """Test to_dict method."""

    def test_returns_dict(self):
        """to_dict returns a dictionary."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=156)
        assert isinstance(result.to_dict(), dict)

    def test_contains_page(self):
        """to_dict includes page."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=3, per_page=20, total=156)
        assert result.to_dict()["page"] == 3

    def test_contains_per_page_camel_case(self):
        """to_dict includes perPage (camelCase)."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=25, total=156)
        assert result.to_dict()["perPage"] == 25

    def test_contains_total(self):
        """to_dict includes total."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=156)
        assert result.to_dict()["total"] == 156

    def test_contains_pages(self):
        """to_dict includes pages count."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=156)
        assert result.to_dict()["pages"] == 8

    def test_contains_has_next_camel_case(self):
        """to_dict includes hasNext (camelCase)."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=156)
        assert result.to_dict()["hasNext"] is True

    def test_contains_has_prev_camel_case(self):
        """to_dict includes hasPrev (camelCase)."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=2, per_page=20, total=156)
        assert result.to_dict()["hasPrev"] is True

    def test_does_not_contain_items(self):
        """to_dict does NOT include items (they should be serialized separately)."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[1, 2, 3], page=1, per_page=20, total=3)
        assert "items" not in result.to_dict()

    def test_all_keys_present(self):
        """to_dict includes all expected keys."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=156)
        keys = set(result.to_dict().keys())
        expected = {"page", "perPage", "total", "pages", "hasNext", "hasPrev"}
        assert keys == expected


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_large_total(self):
        """Handles large total counts."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=1, per_page=20, total=1000000)
        assert result.pages == 50000
        assert result.has_next is True

    def test_large_page_number(self):
        """Handles large page numbers."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=50000, per_page=20, total=1000000)
        assert result.has_next is False
        assert result.has_prev is True

    def test_one_per_page(self):
        """Handles 1 item per page."""
        from feather.db.pagination import PaginatedResult

        result = PaginatedResult(items=[], page=5, per_page=1, total=10)
        assert result.pages == 10
        assert result.has_next is True
        assert result.has_prev is True
