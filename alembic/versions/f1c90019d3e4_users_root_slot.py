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
    indexes |= {u["name"] for u in inspector.get_unique_constraints("users")}
    return columns, indexes


def upgrade():
    columns, indexes = _state()
    if "root_slot" not in columns:
        op.add_column("users", sa.Column("root_slot", sa.SmallInteger(), nullable=True))
    if INDEX not in indexes:
        op.create_index(INDEX, "users", ["root_slot"], unique=True)


def downgrade():
    columns, indexes = _state()
    if INDEX in indexes:
        op.drop_index(INDEX, table_name="users")
    if "root_slot" in columns:
        op.drop_column("users", "root_slot")
