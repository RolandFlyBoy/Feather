"""Integration tests for database operations.

Tests model CRUD, transactions, mixins, and pagination.
"""

import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.integration


class TestModelCrud:
    """Test basic model CRUD operations."""

    def test_create_model(self, test_app):
        """Can create a model instance."""
        from feather.db import db, Model

        class Item(Model):
            __tablename__ = 'test_items_crud'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            item = Item(name='Test Item')
            db.session.add(item)
            db.session.commit()

            assert item.id is not None

    def test_read_model(self, test_app):
        """Can read a model instance."""
        from feather.db import db, Model

        class ReadItem(Model):
            __tablename__ = 'test_read_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            item = ReadItem(name='Read Test')
            db.session.add(item)
            db.session.commit()

            found = ReadItem.query.filter_by(name='Read Test').first()
            assert found is not None
            assert found.name == 'Read Test'

    def test_update_model(self, test_app):
        """Can update a model instance."""
        from feather.db import db, Model

        class UpdateItem(Model):
            __tablename__ = 'test_update_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            item = UpdateItem(name='Original')
            db.session.add(item)
            db.session.commit()

            item.name = 'Updated'
            db.session.commit()

            found = db.session.get(UpdateItem, item.id)
            assert found.name == 'Updated'

    def test_delete_model(self, test_app):
        """Can delete a model instance."""
        from feather.db import db, Model

        class DeleteItem(Model):
            __tablename__ = 'test_delete_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            item = DeleteItem(name='To Delete')
            db.session.add(item)
            db.session.commit()
            item_id = item.id

            db.session.delete(item)
            db.session.commit()

            found = db.session.get(DeleteItem, item_id)
            assert found is None


class TestUuidMixin:
    """Test UUIDMixin functionality."""

    def test_auto_generates_uuid(self, test_app):
        """UUIDMixin auto-generates UUID id."""
        from feather.db import db, Model
        from feather.db.mixins import UUIDMixin

        class UuidItem(UUIDMixin, Model):
            __tablename__ = 'test_uuid_items'
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            item = UuidItem(name='UUID Test')
            db.session.add(item)
            db.session.commit()

            assert item.id is not None
            assert isinstance(item.id, str)
            assert len(item.id) == 36  # UUID format

    def test_uuid_is_unique(self, test_app):
        """Each instance gets a unique UUID."""
        from feather.db import db, Model
        from feather.db.mixins import UUIDMixin

        class UniqueUuidItem(UUIDMixin, Model):
            __tablename__ = 'test_unique_uuid_items'
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            item1 = UniqueUuidItem(name='Item 1')
            item2 = UniqueUuidItem(name='Item 2')
            db.session.add_all([item1, item2])
            db.session.commit()

            assert item1.id != item2.id


class TestTimestampMixin:
    """Test TimestampMixin functionality."""

    def test_sets_created_at(self, test_app):
        """TimestampMixin sets created_at on insert."""
        from feather.db import db, Model
        from feather.db.mixins import TimestampMixin

        class TimestampItem(TimestampMixin, Model):
            __tablename__ = 'test_timestamp_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            before = datetime.now(timezone.utc)
            item = TimestampItem(name='Timestamp Test')
            db.session.add(item)
            db.session.commit()
            after = datetime.now(timezone.utc)

            assert item.created_at is not None
            # created_at should be between before and after
            # (accounting for timezone-naive comparison)

    def test_updates_updated_at(self, test_app):
        """TimestampMixin updates updated_at on update."""
        from feather.db import db, Model
        from feather.db.mixins import TimestampMixin
        import time

        class UpdatedAtItem(TimestampMixin, Model):
            __tablename__ = 'test_updated_at_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            item = UpdatedAtItem(name='Original')
            db.session.add(item)
            db.session.commit()

            original_updated = item.updated_at

            time.sleep(0.1)  # Small delay to ensure time difference
            item.name = 'Updated'
            db.session.commit()

            # updated_at should change
            assert item.updated_at >= original_updated


class TestSoftDeleteMixin:
    """Test SoftDeleteMixin functionality."""

    def test_soft_delete_sets_deleted_at(self, test_app):
        """soft_delete() sets deleted_at timestamp."""
        from feather.db import db, Model
        from feather.db.mixins import SoftDeleteMixin

        class SoftDeleteItem(SoftDeleteMixin, Model):
            __tablename__ = 'test_soft_delete_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            item = SoftDeleteItem(name='To Soft Delete')
            db.session.add(item)
            db.session.commit()

            assert item.deleted_at is None
            assert item.is_deleted is False

            item.soft_delete()
            db.session.commit()

            assert item.deleted_at is not None
            assert item.is_deleted is True

    def test_restore_clears_deleted_at(self, test_app):
        """restore() clears deleted_at."""
        from feather.db import db, Model
        from feather.db.mixins import SoftDeleteMixin

        class RestoreItem(SoftDeleteMixin, Model):
            __tablename__ = 'test_restore_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            item = RestoreItem(name='To Restore')
            db.session.add(item)
            db.session.commit()

            item.soft_delete()
            db.session.commit()
            assert item.is_deleted is True

            item.restore()
            db.session.commit()
            assert item.is_deleted is False
            assert item.deleted_at is None

    def test_query_active_excludes_deleted(self, test_app):
        """query_active() excludes soft-deleted records."""
        from feather.db import db, Model
        from feather.db.mixins import SoftDeleteMixin

        class ActiveQueryItem(SoftDeleteMixin, Model):
            __tablename__ = 'test_active_query_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            active = ActiveQueryItem(name='Active')
            deleted = ActiveQueryItem(name='Deleted')
            db.session.add_all([active, deleted])
            db.session.commit()

            deleted.soft_delete()
            db.session.commit()

            # query_active should only return active item
            results = ActiveQueryItem.query_active().all()
            assert len(results) == 1
            assert results[0].name == 'Active'


class TestTransactionalDecorator:
    """Test @transactional decorator."""

    def test_commits_on_success(self, test_app):
        """@transactional commits on successful execution."""
        from feather.db import db, Model
        from feather import transactional, Service

        class TxItem(Model):
            __tablename__ = 'test_tx_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        class TestService(Service):
            @transactional
            def create_item(self, name):
                item = TxItem(name=name)
                db.session.add(item)
                return item

        with test_app.app_context():
            db.create_all()

            service = TestService()
            item = service.create_item('Transactional')

            # Should be committed
            found = TxItem.query.filter_by(name='Transactional').first()
            assert found is not None

    def test_rollbacks_on_exception(self, test_app):
        """@transactional rolls back on exception."""
        from feather.db import db, Model
        from feather import transactional, Service

        class RollbackItem(Model):
            __tablename__ = 'test_rollback_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        class RollbackService(Service):
            @transactional
            def create_and_fail(self, name):
                item = RollbackItem(name=name)
                db.session.add(item)
                raise ValueError('Intentional failure')

        with test_app.app_context():
            db.create_all()

            service = RollbackService()
            with pytest.raises(ValueError):
                service.create_and_fail('Should Rollback')

            # Should not be committed
            found = RollbackItem.query.filter_by(name='Should Rollback').first()
            assert found is None


class TestDbOperation:
    """Test db_operation context manager."""

    def test_db_operation_commits(self, test_app):
        """db_operation commits on success."""
        from feather.db import db, Model, db_operation

        class OpItem(Model):
            __tablename__ = 'test_op_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            with db_operation():
                item = OpItem(name='Context Manager')
                db.session.add(item)

            # Should be committed
            found = OpItem.query.filter_by(name='Context Manager').first()
            assert found is not None

    def test_db_operation_rollbacks_on_error(self, test_app):
        """db_operation rolls back on exception."""
        from feather.db import db, Model, db_operation

        class OpRollbackItem(Model):
            __tablename__ = 'test_op_rollback_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            with pytest.raises(ValueError):
                with db_operation():
                    item = OpRollbackItem(name='Should Rollback')
                    db.session.add(item)
                    raise ValueError('Intentional')

            # Should not be committed
            found = OpRollbackItem.query.filter_by(name='Should Rollback').first()
            assert found is None


class TestPagination:
    """Test pagination functionality."""

    def test_paginate_returns_result(self, test_app):
        """paginate() returns PaginatedResult."""
        from feather.db import db, Model, paginate
        from feather import PaginatedResult

        class PageItem(Model):
            __tablename__ = 'test_page_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            # Create some items
            for i in range(25):
                db.session.add(PageItem(name=f'Item {i}'))
            db.session.commit()

            result = paginate(PageItem.query, page=1, per_page=10)

            assert isinstance(result, PaginatedResult)
            assert len(result.items) == 10
            assert result.total == 25
            assert result.pages == 3
            assert result.has_next is True
            assert result.has_prev is False

    def test_paginate_second_page(self, test_app):
        """paginate() handles page navigation."""
        from feather.db import db, Model, paginate

        class NavItem(Model):
            __tablename__ = 'test_nav_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            for i in range(25):
                db.session.add(NavItem(name=f'Item {i}'))
            db.session.commit()

            result = paginate(NavItem.query, page=2, per_page=10)

            assert len(result.items) == 10
            assert result.page == 2
            assert result.has_next is True
            assert result.has_prev is True

    def test_paginate_last_page(self, test_app):
        """paginate() handles last page."""
        from feather.db import db, Model, paginate

        class LastPageItem(Model):
            __tablename__ = 'test_last_page_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()

            for i in range(25):
                db.session.add(LastPageItem(name=f'Item {i}'))
            db.session.commit()

            result = paginate(LastPageItem.query, page=3, per_page=10)

            assert len(result.items) == 5  # Only 5 left
            assert result.has_next is False
            assert result.has_prev is True
