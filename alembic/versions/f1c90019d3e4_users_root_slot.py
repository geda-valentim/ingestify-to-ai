"""users.root_slot: the installation's single root user (spec 0019).

Adds a nullable SMALLINT and a unique index on it; the root user has 1 and every
other user NULL, so the index allows at most one root. Both steps are skipped when
already present: on a fresh database Base.metadata.create_all creates them, and
existing databases may have been upgraded at boot by shared.database._add_missing_columns.
"""

from alembic import op
import sqlalchemy as sa

revision = "f1c90019d3e4"
down_revision = "d4e80018a2b6"
branch_labels = None
depends_on = None

INDEX = "uq_users_root_slot"


def _state():
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("users")}
    indexes = {i["name"] for i in inspector.get_indexes("users")}
    constraints = {u["name"] for u in inspector.get_unique_constraints("users")}
    return columns, indexes, constraints


def upgrade():
    columns, indexes, constraints = _state()
    if "root_slot" not in columns:
        op.add_column("users", sa.Column("root_slot", sa.SmallInteger(), nullable=True))
    if INDEX not in indexes | constraints:
        op.create_index(INDEX, "users", ["root_slot"], unique=True)


def downgrade():
    columns, indexes, constraints = _state()
    if op.get_bind().dialect.name == "sqlite":
        # SQLite cannot drop a column or an inline constraint in place: rebuild the table.
        # create_all makes the uniqueness an inline constraint; the upgrade, an index.
        with op.batch_alter_table("users", recreate="always") as batch:
            if INDEX in constraints:
                batch.drop_constraint(INDEX, type_="unique")
            elif INDEX in indexes:
                batch.drop_index(INDEX)
            if "root_slot" in columns:
                batch.drop_column("root_slot")
        return
    if INDEX in indexes | constraints:
        op.drop_index(INDEX, table_name="users")
    if "root_slot" in columns:
        op.drop_column("users", "root_slot")
