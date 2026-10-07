"""Engine (0009) role grants converge into IAM bindings (spec 0018).

Adds the engines-family columns of iam_bindings, copies every access_role_grants
row into a binding with the same id (parents first), reconciles restrictively,
validates and records the marker `0018_engine_bindings`. The downgrade mirrors the
most restrictive state back into access_role_grants before dropping anything.
"""

from alembic import op
from shared.iam import migration

revision = "d4e80018a2b6"
down_revision = "03e70014b8c5"
branch_labels = None
depends_on = None


def upgrade():
    migration.upgrade_0018(op.get_bind())


def downgrade():
    migration.downgrade_0018(op.get_bind())
