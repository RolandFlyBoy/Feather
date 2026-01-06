"""Integration tests for service layer.

Tests @inject decorator, @singleton, Service base class, and lifecycle hooks.
"""

import pytest

pytestmark = pytest.mark.integration


class TestServiceBaseClass:
    """Test Service base class."""

    def test_service_has_db_access(self, test_app):
        """Service has db attribute for database access."""
        from feather import Service

        class TestService(Service):
            def check_db(self):
                return self.db is not None

        with test_app.app_context():
            service = TestService()
            assert service.check_db()

    def test_service_save_method(self, test_app):
        """Service.save() adds and commits model."""
        from feather import Service
        from feather.db import db, Model

        class SaveItem(Model):
            __tablename__ = 'test_save_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        class SaveService(Service):
            def create(self, name):
                item = SaveItem(name=name)
                self.save(item)
                return item

        with test_app.app_context():
            db.create_all()

            service = SaveService()
            item = service.create('Test Item')

            assert item.id is not None
            found = db.session.get(SaveItem, item.id)
            assert found.name == 'Test Item'

    def test_service_delete_method(self, test_app):
        """Service.delete() removes model."""
        from feather import Service
        from feather.db import db, Model

        class DeleteServiceItem(Model):
            __tablename__ = 'test_delete_service_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        class DeleteService(Service):
            def remove(self, item):
                self.delete(item)

        with test_app.app_context():
            db.create_all()

            item = DeleteServiceItem(name='To Delete')
            db.session.add(item)
            db.session.commit()
            item_id = item.id

            service = DeleteService()
            service.remove(item)

            found = db.session.get(DeleteServiceItem, item_id)
            assert found is None


class TestInjectDecorator:
    """Test @inject decorator."""

    def test_inject_provides_service(self, test_app):
        """@inject provides service instance to route."""
        from feather import inject, Service

        class InjectedService(Service):
            def get_data(self):
                return 'injected data'

        @test_app.route('/test/injected')
        @inject(InjectedService)
        def injected_route(injected_service):
            return {'data': injected_service.get_data()}

        with test_app.test_client() as client:
            response = client.get('/test/injected')
            data = response.get_json()
            assert data['data'] == 'injected data'

    def test_inject_multiple_services(self, test_app):
        """@inject provides multiple services."""
        from feather import inject, Service

        class ServiceA(Service):
            def value(self):
                return 'A'

        class ServiceB(Service):
            def value(self):
                return 'B'

        @test_app.route('/test/multi-inject')
        @inject(ServiceA, ServiceB)
        def multi_inject(service_a, service_b):
            return {'a': service_a.value(), 'b': service_b.value()}

        with test_app.test_client() as client:
            response = client.get('/test/multi-inject')
            data = response.get_json()
            assert data['a'] == 'A'
            assert data['b'] == 'B'

    def test_inject_creates_new_instance(self, test_app):
        """@inject creates new service instance per request."""
        from feather import inject, Service

        instance_ids = []

        class PerRequestService(Service):
            def __init__(self):
                super().__init__()
                self.instance_id = id(self)

        @test_app.route('/test/per-request')
        @inject(PerRequestService)
        def per_request(per_request_service):  # Must match snake_case class name
            instance_ids.append(per_request_service.instance_id)
            return {'id': per_request_service.instance_id}

        with test_app.test_client() as client:
            client.get('/test/per-request')
            client.get('/test/per-request')

        # Each request should get new instance
        assert len(instance_ids) == 2
        assert instance_ids[0] != instance_ids[1]


class TestSingletonDecorator:
    """Test @singleton decorator."""

    def test_singleton_returns_same_instance(self, test_app):
        """@singleton returns same instance across requests."""
        from feather import inject, Service
        from feather.services import singleton

        @singleton
        class SingletonService(Service):
            def __init__(self):
                super().__init__()
                self.instance_id = id(self)

        instance_ids = []

        @test_app.route('/test/singleton')
        @inject(SingletonService)
        def singleton_route(singleton_service):  # Must match snake_case class name
            instance_ids.append(singleton_service.instance_id)
            return {'id': singleton_service.instance_id}

        with test_app.test_client() as client:
            client.get('/test/singleton')
            client.get('/test/singleton')

        # Both requests should get same instance
        assert len(instance_ids) == 2
        assert instance_ids[0] == instance_ids[1]

    def test_singleton_shares_state(self, test_app):
        """@singleton services share state across requests."""
        from feather import inject, Service
        from feather.services import singleton

        @singleton
        class StatefulService(Service):
            def __init__(self):
                super().__init__()
                self.counter = 0

            def increment(self):
                self.counter += 1
                return self.counter

        @test_app.route('/test/stateful')
        @inject(StatefulService)
        def stateful_route(stateful_service):  # Must match snake_case class name
            return {'count': stateful_service.increment()}

        with test_app.test_client() as client:
            r1 = client.get('/test/stateful')
            r2 = client.get('/test/stateful')
            r3 = client.get('/test/stateful')

        # Counter should increment across requests
        assert r1.get_json()['count'] == 1
        assert r2.get_json()['count'] == 2
        assert r3.get_json()['count'] == 3


class TestServiceLifecycle:
    """Test service lifecycle hooks."""

    def test_on_init_called(self, test_app):
        """on_init() is called during service initialization."""
        from feather import Service

        init_called = []

        class InitService(Service):
            def on_init(self):
                init_called.append(True)

        with test_app.app_context():
            service = InitService()

        assert len(init_called) == 1

    def test_on_cleanup_exists(self, test_app):
        """Service has on_cleanup method."""
        from feather import Service

        class CleanupService(Service):
            def on_cleanup(self):
                pass

        with test_app.app_context():
            service = CleanupService()
            # Should have on_cleanup method
            assert hasattr(service, 'on_cleanup')
            assert callable(service.on_cleanup)


class TestServiceDependencies:
    """Test service dependencies."""

    def test_service_can_use_other_services(self, test_app):
        """Services can compose other services."""
        from feather import Service
        from feather.db import db, Model

        class ComposedItem(Model):
            __tablename__ = 'test_composed_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        class LowerService(Service):
            def get_value(self):
                return 'lower value'

        class UpperService(Service):
            def __init__(self):
                super().__init__()
                self.lower = LowerService()

            def get_combined(self):
                return f'upper + {self.lower.get_value()}'

        with test_app.app_context():
            db.create_all()

            upper = UpperService()
            result = upper.get_combined()

            assert result == 'upper + lower value'


class TestServiceWithTransactions:
    """Test services with transactional behavior."""

    def test_transactional_service_method(self, test_app):
        """Service methods can be transactional."""
        from feather import Service, transactional
        from feather.db import db, Model

        class TxServiceItem(Model):
            __tablename__ = 'test_tx_service_items'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        class TxService(Service):
            @transactional
            def create_item(self, name):
                item = TxServiceItem(name=name)
                db.session.add(item)
                return item

        with test_app.app_context():
            db.create_all()

            service = TxService()
            item = service.create_item('Tx Item')

            # Should be committed
            found = TxServiceItem.query.filter_by(name='Tx Item').first()
            assert found is not None


class TestServiceErrorHandling:
    """Test service error handling patterns."""

    def test_service_raises_validation_error(self, test_app):
        """Services can raise ValidationError."""
        from feather import Service, ValidationError

        class ValidatingService(Service):
            def validate(self, email):
                if not email or '@' not in email:
                    raise ValidationError('Invalid email', field='email')
                return True

        with test_app.app_context():
            service = ValidatingService()

            with pytest.raises(ValidationError) as exc:
                service.validate('invalid')

            assert exc.value.field == 'email'

    def test_service_raises_not_found_error(self, test_app):
        """Services can raise NotFoundError."""
        from feather import Service, NotFoundError

        class FinderService(Service):
            def find(self, resource_id):
                raise NotFoundError('User', resource_id)

        with test_app.app_context():
            service = FinderService()

            with pytest.raises(NotFoundError) as exc:
                service.find('123')

            assert exc.value.resource_type == 'User'
            assert exc.value.resource_id == '123'
