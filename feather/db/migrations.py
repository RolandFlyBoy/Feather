"""Alembic helpers for the migrations Feather generates.

Wired into every scaffolded ``migrations/env.py``::

    from feather.db.migrations import process_revision_directives

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        process_revision_directives=process_revision_directives,
    )
"""

from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint


def defer_circular_foreign_keys(context, revision, directives) -> None:
    """Create ``use_alter`` foreign keys after the tables, not inside them.

    Two tables that point at each other (the scaffold's ``users`` and
    ``accounts``) mark one side ``use_alter=True``: the key has to be added
    once both tables exist. ``metadata.create_all`` honours that, but
    autogenerate renders the key inside ``op.create_table``, and SQLAlchemy
    leaves a ``use_alter`` key out of CREATE TABLE. The first migration
    therefore created neither key, and the next ``feather db migrate``
    "found" both and added them, inside whatever unrelated change it was
    written for.

    This moves each such key into an ``op.create_foreign_key`` after every
    table is created, and drops it first on the way down, so a table that
    another still points at can be dropped. SQLite, which cannot add a
    constraint to an existing table, is left as it was.
    """
    if not directives:
        return
    # SQLite cannot add a constraint to an existing table, so there the key
    # stays where autogenerate put it (SQLite does not enforce it by default).
    dialect = getattr(getattr(context, "dialect", None), "name", None)
    if dialect == "sqlite":
        return

    from alembic.operations import ops

    script = directives[0]
    for upgrade_ops, downgrade_ops in zip(script.upgrade_ops_list, script.downgrade_ops_list):
        deferred = []
        for op in upgrade_ops.ops:
            if not isinstance(op, ops.CreateTableOp):
                continue
            kept = []
            for item in op.columns:
                if isinstance(item, ForeignKeyConstraint) and item.use_alter:
                    deferred.append(item)
                else:
                    kept.append(item)
            op.columns = kept
        if not deferred:
            continue
        upgrade_ops.ops.extend(ops.CreateForeignKeyOp.from_constraint(fk) for fk in deferred)
        downgrade_ops.ops[:0] = [ops.DropConstraintOp.from_constraint(fk) for fk in deferred]


#: What a scaffolded env.py passes to ``context.configure``. A single name so
#: later fixes to generated migrations reach apps without editing env.py.
process_revision_directives = defer_circular_foreign_keys

__all__ = ["defer_circular_foreign_keys", "process_revision_directives"]
