"""Engine control (0007); legacy installs use the standalone migration."""
from alembic import op
revision='c7e10007a1f0'
down_revision='b5d10003a1f0'
branch_labels=None
depends_on=None

def upgrade():
    from shared.engine_control.migration import upgrade
    upgrade(op.get_bind())

def downgrade():
    from shared.engine_control.migration import downgrade
    downgrade(op.get_bind())
