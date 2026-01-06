"""feather generate - Code generation commands."""

import re
from pathlib import Path

import click


@click.group()
def generate():
    """Generate code (models, services, routes, serializers, islands)."""
    pass


@generate.command()
@click.argument("name")
@click.argument("fields", nargs=-1)
@click.option("--no-mixins", is_flag=True, help="Don't use any mixins (manual id/timestamps)")
@click.option("--soft-delete", is_flag=True, help="Add soft delete functionality")
@click.option("--ordered", is_flag=True, help="Add position-based ordering (OrderingMixin)")
def model(name: str, fields: tuple, no_mixins: bool, soft_delete: bool, ordered: bool):
    """Generate a new model.

    NAME is the model name (e.g., User, BlogPost)
    FIELDS are field definitions (e.g., name:string email:string age:integer)

    By default, models use UUIDMixin and TimestampMixin for common patterns.
    Use --no-mixins to define id and timestamps manually instead.

    \b
    Examples:
      feather generate model User name:string email:string
      feather generate model BlogPost title:string content:text
      feather generate model Post title:string --soft-delete
      feather generate model Card title:string column_id:uuid --ordered
      feather generate model SimpleItem name:string --no-mixins
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    # Convert name to proper case
    class_name = _to_pascal_case(name)
    file_name = _to_snake_case(name)
    table_name = _to_snake_case(name) + "s"

    # Parse fields
    field_definitions = []
    for field in fields:
        if ":" not in field:
            raise click.ClickException(f"Invalid field format: {field}. Use name:type format.")

        field_name, field_type = field.split(":", 1)
        sql_type = _python_type_to_sqlalchemy(field_type)
        field_definitions.append((field_name, sql_type))

    # Determine which mixins to use
    use_mixins = not no_mixins
    mixins = []
    if use_mixins:
        mixins.append("UUIDMixin")
        mixins.append("TimestampMixin")
    if soft_delete:
        mixins.append("SoftDeleteMixin")
    if ordered:
        mixins.append("OrderingMixin")

    # Build imports
    if use_mixins or soft_delete or ordered:
        mixin_imports = ", ".join(mixins)
        imports = f"""from feather.db import db, Model
from feather.db.mixins import {mixin_imports}"""
    else:
        imports = """import uuid
from datetime import datetime, timezone

from feather.db import db, Model"""

    # Build class inheritance
    if mixins:
        inheritance = ", ".join(mixins) + ", Model"
    else:
        inheritance = "Model"

    # Generate model code
    model_code = f'''"""{class_name} model."""

{imports}


class {class_name}({inheritance}):
    """{class_name} model."""

    __tablename__ = "{table_name}"

'''

    # Add manual id and timestamps if not using mixins
    if not use_mixins:
        model_code += "    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))\n"

    # Add custom fields
    for field_name, sql_type in field_definitions:
        model_code += f"    {field_name} = db.Column({sql_type})\n"

    # Add manual timestamps if not using mixins
    if not use_mixins:
        model_code += """    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))
"""

    model_code += f"""
    def __repr__(self):
        return f"<{class_name} {{self.id}}>"
"""

    # Write file
    model_path = Path("models") / f"{file_name}.py"
    model_path.write_text(model_code)

    click.echo(click.style(f"Created {model_path}", fg="green"))
    if mixins:
        click.echo(f"  Using mixins: {', '.join(mixins)}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Import in models/__init__.py: from models.{file_name} import {class_name}")
    click.echo("  2. Generate migration: feather db migrate")
    click.echo("  3. Apply migration: feather db upgrade")


@generate.command()
@click.argument("name")
def service(name: str):
    """Generate a new service.

    NAME is the service name (e.g., UserService, PostService)

    \b
    Example:
      feather generate service UserService
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    # Ensure name ends with Service
    if not name.endswith("Service"):
        name = name + "Service"

    class_name = _to_pascal_case(name)
    file_name = _to_snake_case(name)

    # Infer model name
    model_name = class_name.replace("Service", "")

    service_code = f'''"""{class_name} - Business logic for {model_name}."""

from feather import Service
from feather.exceptions import NotFoundError, ValidationError
from models import {model_name}


class {class_name}(Service):
    """{model_name} service."""

    def get_by_id(self, id: str) -> {model_name}:
        """Get {model_name.lower()} by ID or raise NotFoundError."""
        obj = {model_name}.query.get(id)
        if not obj:
            raise NotFoundError("{model_name}", id)
        return obj

    def create(self, **kwargs) -> {model_name}:
        """Create a new {model_name.lower()}."""
        obj = {model_name}(**kwargs)
        self.db.add(obj)
        self.db.commit()
        return obj

    def update(self, id: str, **kwargs) -> {model_name}:
        """Update a {model_name.lower()}."""
        obj = self.get_by_id(id)
        for key, value in kwargs.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        self.db.commit()
        return obj

    def delete(self, id: str) -> None:
        """Delete a {model_name.lower()}."""
        obj = self.get_by_id(id)
        self.db.delete(obj)
        self.db.commit()

    def list_all(self, limit: int = 20, offset: int = 0) -> list[{model_name}]:
        """List all {model_name.lower()}s with pagination."""
        return {model_name}.query\\
            .order_by({model_name}.created_at.desc())\\
            .offset(offset)\\
            .limit(limit)\\
            .all()
'''

    # Write file
    service_path = Path("services") / f"{file_name}.py"
    service_path.write_text(service_code)

    click.echo(click.style(f"Created {service_path}", fg="green"))
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  Import in services/__init__.py: from services.{file_name} import {class_name}")


@generate.command()
@click.argument("name")
def island(name: str):
    """Generate a new island (interactive JS component).

    NAME is the island name in kebab-case (e.g., like-button, audio-player)

    \b
    Example:
      feather generate island like-button
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    # Ensure kebab-case
    name = _to_kebab_case(name)

    island_code = f'''/**
 * {name} island - Interactive component
 */
island("{name}", {{
  state: {{
    // Define your state here
    active: false,
  }},

  init() {{
    // Initialize from data attributes or DOM
    // this.state.active = this.data.active === "true";
  }},

  actions: {{
    // Define actions triggered by data-action clicks
    toggle() {{
      this.state.active = !this.state.active;
    }},
  }},

  render(state) {{
    // Return an object mapping selectors to values
    // Only changed values update the DOM
    return {{
      ".status": state.active ? "Active" : "Inactive",
      "button": {{ class: {{ active: state.active }} }},
    }};
  }},
}});
'''

    # Write file
    island_path = Path("static/islands") / f"{name}.js"
    island_path.write_text(island_code)

    click.echo(click.style(f"Created {island_path}", fg="green"))
    click.echo()
    click.echo("Usage in templates:")
    click.echo(f'  <div data-island="{name}">')
    click.echo('    <span class="status">Inactive</span>')
    click.echo('    <button data-action="toggle">Toggle</button>')
    click.echo("  </div>")
    click.echo()
    click.echo(f'  <script src="{{{{ feather_asset(\'islands/{name}\') }}}}"></script>')


@generate.command()
@click.argument("name")
@click.option("--api", is_flag=True, help="Generate an API route (in routes/api/)")
@click.option("--page", is_flag=True, help="Generate a page route (in routes/pages/)")
@click.option("--model", help="Model name for CRUD operations")
def route(name: str, api: bool, page: bool, model: str):
    """Generate a new route file.

    NAME is the route name (e.g., users, posts, products)

    By default, generates an API route. Use --page for page routes.

    \b
    Examples:
      feather generate route users
      feather generate route users --model User
      feather generate route dashboard --page
      feather generate route products --api --model Product
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    # Default to API if neither specified
    if not api and not page:
        api = True

    file_name = _to_snake_case(name)

    if api:
        _generate_api_route(file_name, model)
    else:
        _generate_page_route(file_name)


def _generate_api_route(file_name: str, model: str = None):
    """Generate an API route file."""
    # Ensure routes/api directory exists
    api_dir = Path("routes/api")
    api_dir.mkdir(parents=True, exist_ok=True)

    if model:
        # Generate CRUD routes for a model
        model_class = _to_pascal_case(model)
        model_var = _to_snake_case(model)
        service_class = f"{model_class}Service"
        service_var = f"{model_var}_service"

        route_code = f'''"""{model_class} API routes."""

from flask import request
from feather import api, inject, auth_required
from feather.exceptions import ValidationError
from services import {service_class}


@api.get("/{file_name}")
@inject({service_class})
def list_{file_name}({service_var}):
    """List all {file_name}."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items = {service_var}.list_all(limit=per_page, offset=(page - 1) * per_page)
    return {{"items": [item.to_dict() for item in items]}}


@api.get("/{file_name}/<{model_var}_id>")
@inject({service_class})
def get_{model_var}({model_var}_id, {service_var}):
    """Get a single {model_var} by ID."""
    item = {service_var}.get_by_id({model_var}_id)
    return {{"item": item.to_dict()}}


@api.post("/{file_name}")
@auth_required
@inject({service_class})
def create_{model_var}({service_var}):
    """Create a new {model_var}."""
    data = request.get_json() or {{}}
    item = {service_var}.create(**data)
    return {{"item": item.to_dict()}}, 201


@api.put("/{file_name}/<{model_var}_id>")
@auth_required
@inject({service_class})
def update_{model_var}({model_var}_id, {service_var}):
    """Update a {model_var}."""
    data = request.get_json() or {{}}
    item = {service_var}.update({model_var}_id, **data)
    return {{"item": item.to_dict()}}


@api.delete("/{file_name}/<{model_var}_id>")
@auth_required
@inject({service_class})
def delete_{model_var}({model_var}_id, {service_var}):
    """Delete a {model_var}."""
    {service_var}.delete({model_var}_id)
    return {{"success": True}}
'''
    else:
        # Generate basic API route
        route_code = f'''"""{_to_pascal_case(file_name)} API routes."""

from flask import request
from feather import api, auth_required


@api.get("/{file_name}")
def list_{file_name}():
    """List {file_name}."""
    # TODO: Implement listing
    return {{"items": []}}


@api.get("/{file_name}/<item_id>")
def get_{file_name}_item(item_id):
    """Get a single item by ID."""
    # TODO: Implement get
    return {{"item": {{"id": item_id}}}}


@api.post("/{file_name}")
@auth_required
def create_{file_name}_item():
    """Create a new item."""
    data = request.get_json() or {{}}
    # TODO: Implement create
    return {{"item": data}}, 201
'''

    route_path = Path("routes/api") / f"{file_name}.py"
    route_path.write_text(route_code)

    click.echo(click.style(f"Created {route_path}", fg="green"))
    click.echo()
    click.echo("Routes available:")
    click.echo(f"  GET    /api/{file_name}")
    click.echo(f"  GET    /api/{file_name}/<id>")
    click.echo(f"  POST   /api/{file_name}")
    if model:
        click.echo(f"  PUT    /api/{file_name}/<id>")
        click.echo(f"  DELETE /api/{file_name}/<id>")


def _generate_page_route(file_name: str):
    """Generate a page route file."""
    # Ensure routes/pages directory exists
    pages_dir = Path("routes/pages")
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Ensure templates/pages directory exists
    templates_dir = Path("templates/pages")
    templates_dir.mkdir(parents=True, exist_ok=True)

    class_name = _to_pascal_case(file_name)

    route_code = f'''"""{class_name} page routes."""

from flask import render_template
from feather import page


@page.get("/{file_name}")
def {file_name}_page():
    """Render the {file_name} page."""
    return render_template("pages/{file_name}.html")
'''

    template_code = f'''{{% extends "base.html" %}}

{{% block title %}}{class_name}{{% endblock %}}

{{% block content %}}
<div class="max-w-4xl mx-auto py-8 px-4">
    <h1 class="text-3xl font-bold text-gray-900 mb-6">{class_name}</h1>

    <p class="text-gray-600">
        This is the {file_name} page. Edit templates/pages/{file_name}.html to customize.
    </p>
</div>
{{% endblock %}}
'''

    route_path = Path("routes/pages") / f"{file_name}.py"
    route_path.write_text(route_code)

    template_path = Path("templates/pages") / f"{file_name}.html"
    template_path.write_text(template_code)

    click.echo(click.style(f"Created {route_path}", fg="green"))
    click.echo(click.style(f"Created {template_path}", fg="green"))
    click.echo()
    click.echo("Route available:")
    click.echo(f"  GET /{file_name}")


@generate.command()
@click.argument("name")
@click.argument("fields", nargs=-1)
@click.option("--model", help="Model name (inferred from serializer name if not provided)")
def serializer(name: str, fields: tuple, model: str):
    """Generate a new serializer.

    NAME is the serializer name (e.g., UserSerializer, PostSerializer)
    FIELDS are field names to include (optional)

    \b
    Examples:
      feather generate serializer UserSerializer
      feather generate serializer PostSerializer id title content created_at
      feather generate serializer UserSerializer --model User
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    # Ensure name ends with Serializer
    if not name.endswith("Serializer"):
        name = name + "Serializer"

    class_name = _to_pascal_case(name)
    file_name = _to_snake_case(name)

    # Infer model name
    if not model:
        model = class_name.replace("Serializer", "")
    else:
        model = _to_pascal_case(model)

    # Ensure serializers directory exists
    serializers_dir = Path("serializers")
    serializers_dir.mkdir(parents=True, exist_ok=True)

    # Create __init__.py if it doesn't exist
    init_file = serializers_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text(f'"""Serializers for API responses."""\n\nfrom serializers.{file_name} import {class_name}\n')

    # Default fields if none provided
    if not fields:
        fields = ["id", "created_at", "updated_at"]

    fields_str = ", ".join(f"'{f}'" for f in fields)

    serializer_code = f'''"""{class_name} - Serialize {model} for API responses."""

from feather.serializers import Serializer
from models import {model}


class {class_name}(Serializer):
    """{model} serializer.

    Usage:
        serializer = {class_name}()
        data = serializer.serialize({model.lower()})
        items = serializer.serialize_many({model.lower()}s)
    """

    class Meta:
        model = {model}
        fields = [{fields_str}]
        camel_case = True

    # Add computed fields by defining get_<field_name> methods:
    #
    # def get_avatar_url(self, obj, **context):
    #     \"\"\"Compute avatar URL for the {model.lower()}.\"\"\"
    #     if obj.profile_image:
    #         return obj.profile_image
    #     return f"https://ui-avatars.com/api/?name={{obj.name}}"
'''

    serializer_path = serializers_dir / f"{file_name}.py"
    serializer_path.write_text(serializer_code)

    click.echo(click.style(f"Created {serializer_path}", fg="green"))
    click.echo()
    click.echo("Usage in routes:")
    click.echo(f"  from serializers import {class_name}")
    click.echo()
    click.echo(f"  serializer = {class_name}()")
    click.echo(f"  return {{'item': serializer.serialize({model.lower()})}}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Add fields to Meta.fields: {fields_str}")
    click.echo("  2. Add computed fields with get_<field_name> methods")


def _to_pascal_case(name: str) -> str:
    """Convert to PascalCase."""
    # Handle kebab-case and snake_case
    words = re.split(r"[-_]", name)
    return "".join(word.capitalize() for word in words)


def _to_snake_case(name: str) -> str:
    """Convert to snake_case."""
    # Handle PascalCase
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _to_kebab_case(name: str) -> str:
    """Convert to kebab-case."""
    return _to_snake_case(name).replace("_", "-")


def _python_type_to_sqlalchemy(python_type: str) -> str:
    """Convert Python type hint to SQLAlchemy column type."""
    type_map = {
        "string": "db.String(255)",
        "str": "db.String(255)",
        "text": "db.Text",
        "integer": "db.Integer",
        "int": "db.Integer",
        "float": "db.Float",
        "boolean": "db.Boolean",
        "bool": "db.Boolean",
        "datetime": "db.DateTime",
        "date": "db.Date",
        "time": "db.Time",
        "json": "db.JSON",
        "uuid": "db.String(36)",
    }
    return type_map.get(python_type.lower(), "db.String(255)")
