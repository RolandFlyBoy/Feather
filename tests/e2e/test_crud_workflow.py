"""E2E tests for CRUD workflow.

Tests complete create, read, update, delete workflows through the stack.
"""

import pytest
from feather import Feather, inject, Service
from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin
from tests.conftest import make_csrf_client

pytestmark = pytest.mark.e2e


# Define model at module level to avoid SQLAlchemy redefinition warnings
class CrudItem(UUIDMixin, TimestampMixin, Model):
    """Test item model for CRUD tests."""
    __tablename__ = 'crud_items'
    __table_args__ = {'extend_existing': True}
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)


@pytest.fixture
def crud_app():
    """Create a test app with a CRUD model and routes."""
    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    # CSRF enabled to match production

    # Define service (references module-level model)
    class ItemService(Service):
        def list_all(self):
            return CrudItem.query.all()

        def get(self, item_id):
            return db.session.get(CrudItem, item_id)

        def create(self, name, description=None):
            item = CrudItem(name=name, description=description)
            self.save(item)
            return item

        def update(self, item_id, name=None, description=None, active=None):
            item = db.session.get(CrudItem, item_id)
            if not item:
                return None
            if name is not None:
                item.name = name
            if description is not None:
                item.description = description
            if active is not None:
                item.active = active
            db.session.commit()
            return item

        def delete(self, item_id):
            item = db.session.get(CrudItem, item_id)
            if item:
                db.session.delete(item)
                db.session.commit()
                return True
            return False

    # Define routes
    @app.route('/api/items', methods=['GET'])
    @inject(ItemService)
    def list_items(item_service):
        items = item_service.list_all()
        return {'items': [{'id': i.id, 'name': i.name, 'active': i.active} for i in items]}

    @app.route('/api/items/<item_id>', methods=['GET'])
    @inject(ItemService)
    def get_item(item_service, item_id):
        from feather import NotFoundError
        item = item_service.get(item_id)
        if not item:
            raise NotFoundError('Item', item_id)
        return {
            'id': item.id,
            'name': item.name,
            'description': item.description,
            'active': item.active,
        }

    @app.route('/api/items', methods=['POST'])
    @inject(ItemService)
    def create_item(item_service):
        from flask import request
        from feather import ValidationError
        data = request.get_json() or {}
        if not data.get('name'):
            raise ValidationError('Name is required', field='name')
        item = item_service.create(
            name=data['name'],
            description=data.get('description'),
        )
        return {'id': item.id, 'name': item.name}, 201

    @app.route('/api/items/<item_id>', methods=['PUT'])
    @inject(ItemService)
    def update_item(item_service, item_id):
        from flask import request
        from feather import NotFoundError
        data = request.get_json() or {}
        item = item_service.update(
            item_id,
            name=data.get('name'),
            description=data.get('description'),
            active=data.get('active'),
        )
        if not item:
            raise NotFoundError('Item', item_id)
        return {'id': item.id, 'name': item.name, 'active': item.active}

    @app.route('/api/items/<item_id>', methods=['DELETE'])
    @inject(ItemService)
    def delete_item(item_service, item_id):
        from feather import NotFoundError
        item = item_service.get(item_id)
        if not item:
            raise NotFoundError('Item', item_id)
        db.session.delete(item)
        db.session.commit()
        return '', 204

    # Setup: create tables
    with app.app_context():
        db.create_all()

    # Yield OUTSIDE app_context for proper CSRF isolation
    yield app

    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(crud_app):
    """Create a CSRF-aware test client."""
    return make_csrf_client(crud_app)


class TestCreateWorkflow:
    """Test create operations."""

    def test_create_item_success(self, client):
        """Successfully create an item."""
        response = client.post('/api/items', json={
            'name': 'Test Item',
            'description': 'A test item description',
        })

        assert response.status_code == 201
        data = response.get_json()
        assert data['name'] == 'Test Item'
        assert 'id' in data

    def test_create_item_validation_error(self, client):
        """Create without name returns validation error."""
        response = client.post('/api/items', json={
            'description': 'No name provided',
        })

        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'VALIDATION_ERROR'
        assert data['error']['field'] == 'name'

    def test_create_multiple_items(self, client):
        """Create multiple items."""
        for i in range(3):
            response = client.post('/api/items', json={'name': f'Item {i}'})
            assert response.status_code == 201

        # Verify all exist
        response = client.get('/api/items')
        data = response.get_json()
        assert len(data['items']) == 3


class TestReadWorkflow:
    """Test read operations."""

    def test_list_empty(self, client):
        """List returns empty array when no items."""
        response = client.get('/api/items')

        assert response.status_code == 200
        data = response.get_json()
        assert data['items'] == []

    def test_list_with_items(self, client):
        """List returns all items."""
        # Create items
        client.post('/api/items', json={'name': 'First'})
        client.post('/api/items', json={'name': 'Second'})

        response = client.get('/api/items')
        data = response.get_json()

        assert len(data['items']) == 2
        names = [item['name'] for item in data['items']]
        assert 'First' in names
        assert 'Second' in names

    def test_get_single_item(self, client):
        """Get a single item by ID."""
        # Create item
        create_response = client.post('/api/items', json={
            'name': 'Single Item',
            'description': 'Detailed description',
        })
        item_id = create_response.get_json()['id']

        # Get item
        response = client.get(f'/api/items/{item_id}')
        data = response.get_json()

        assert response.status_code == 200
        assert data['name'] == 'Single Item'
        assert data['description'] == 'Detailed description'
        assert data['active'] is True

    def test_get_nonexistent_item(self, client):
        """Get nonexistent item returns 404."""
        response = client.get('/api/items/nonexistent-id')

        assert response.status_code == 404
        data = response.get_json()
        assert data['error']['code'] == 'NOT_FOUND'


class TestUpdateWorkflow:
    """Test update operations."""

    def test_update_item_name(self, client):
        """Update item name."""
        # Create
        create_response = client.post('/api/items', json={'name': 'Original'})
        item_id = create_response.get_json()['id']

        # Update
        response = client.put(f'/api/items/{item_id}', json={'name': 'Updated'})
        data = response.get_json()

        assert response.status_code == 200
        assert data['name'] == 'Updated'

        # Verify change persisted
        get_response = client.get(f'/api/items/{item_id}')
        assert get_response.get_json()['name'] == 'Updated'

    def test_update_item_active_status(self, client):
        """Update item active status."""
        # Create
        create_response = client.post('/api/items', json={'name': 'Active Item'})
        item_id = create_response.get_json()['id']

        # Deactivate
        response = client.put(f'/api/items/{item_id}', json={'active': False})
        data = response.get_json()

        assert data['active'] is False

    def test_update_nonexistent_item(self, client):
        """Update nonexistent item returns 404."""
        response = client.put('/api/items/fake-id', json={'name': 'Updated'})

        assert response.status_code == 404

    def test_partial_update(self, client):
        """Partial update only changes specified fields."""
        # Create with description
        create_response = client.post('/api/items', json={
            'name': 'Original Name',
            'description': 'Original Description',
        })
        item_id = create_response.get_json()['id']

        # Update only name
        client.put(f'/api/items/{item_id}', json={'name': 'New Name'})

        # Verify description unchanged
        get_response = client.get(f'/api/items/{item_id}')
        data = get_response.get_json()
        assert data['name'] == 'New Name'
        assert data['description'] == 'Original Description'


class TestDeleteWorkflow:
    """Test delete operations."""

    def test_delete_item(self, client):
        """Delete an item."""
        # Create
        create_response = client.post('/api/items', json={'name': 'To Delete'})
        item_id = create_response.get_json()['id']

        # Delete
        response = client.delete(f'/api/items/{item_id}')
        assert response.status_code == 204

        # Verify deleted
        get_response = client.get(f'/api/items/{item_id}')
        assert get_response.status_code == 404

    def test_delete_nonexistent_item(self, client):
        """Delete nonexistent item returns 404."""
        response = client.delete('/api/items/fake-id')
        assert response.status_code == 404

    def test_delete_removes_from_list(self, client):
        """Deleted item no longer appears in list."""
        # Create two items
        resp1 = client.post('/api/items', json={'name': 'Keep'})
        resp2 = client.post('/api/items', json={'name': 'Delete'})
        delete_id = resp2.get_json()['id']

        # Delete one
        client.delete(f'/api/items/{delete_id}')

        # Verify list only has one
        list_response = client.get('/api/items')
        items = list_response.get_json()['items']
        assert len(items) == 1
        assert items[0]['name'] == 'Keep'


class TestFullCrudWorkflow:
    """Test complete CRUD cycle."""

    def test_complete_lifecycle(self, client):
        """Test complete create-read-update-delete lifecycle."""
        # CREATE
        create_response = client.post('/api/items', json={
            'name': 'Lifecycle Item',
            'description': 'Testing full lifecycle',
        })
        assert create_response.status_code == 201
        item_id = create_response.get_json()['id']

        # READ
        read_response = client.get(f'/api/items/{item_id}')
        assert read_response.status_code == 200
        assert read_response.get_json()['name'] == 'Lifecycle Item'

        # UPDATE
        update_response = client.put(f'/api/items/{item_id}', json={
            'name': 'Updated Lifecycle Item',
            'active': False,
        })
        assert update_response.status_code == 200
        assert update_response.get_json()['name'] == 'Updated Lifecycle Item'
        assert update_response.get_json()['active'] is False

        # Verify update persisted
        verify_response = client.get(f'/api/items/{item_id}')
        assert verify_response.get_json()['name'] == 'Updated Lifecycle Item'

        # DELETE
        delete_response = client.delete(f'/api/items/{item_id}')
        assert delete_response.status_code == 204

        # Verify deleted
        final_response = client.get(f'/api/items/{item_id}')
        assert final_response.status_code == 404

    def test_multiple_items_lifecycle(self, client):
        """Test managing multiple items."""
        # Create several items
        ids = []
        for i in range(5):
            resp = client.post('/api/items', json={'name': f'Item {i}'})
            ids.append(resp.get_json()['id'])

        # Verify all created
        list_resp = client.get('/api/items')
        assert len(list_resp.get_json()['items']) == 5

        # Update some
        client.put(f'/api/items/{ids[0]}', json={'active': False})
        client.put(f'/api/items/{ids[2]}', json={'name': 'Renamed'})

        # Delete some
        client.delete(f'/api/items/{ids[1]}')
        client.delete(f'/api/items/{ids[3]}')

        # Verify final state
        final_list = client.get('/api/items').get_json()['items']
        assert len(final_list) == 3

        # Check specific items
        item0 = client.get(f'/api/items/{ids[0]}').get_json()
        assert item0['active'] is False

        item2 = client.get(f'/api/items/{ids[2]}').get_json()
        assert item2['name'] == 'Renamed'
