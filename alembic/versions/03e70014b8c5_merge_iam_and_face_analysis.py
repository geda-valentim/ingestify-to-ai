"""Merge the IAM bindings branch (spec 0014) with main's image/face analysis chain.

a1c40014e7b2 (IAM bindings) and 01b5000bd5d4 -> 02c6000ce6e5 (image full analysis,
faces) both descend from f0b40009c4d3. Keeping a1c40014e7b2's original parent and
joining the two heads here means a database already stamped a1c40014e7b2 still
runs 01b5000bd5d4 and 02c6000ce6e5 on the next ``alembic upgrade head``.
"""

revision = "03e70014b8c5"
down_revision = ("02c6000ce6e5", "a1c40014e7b2")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
