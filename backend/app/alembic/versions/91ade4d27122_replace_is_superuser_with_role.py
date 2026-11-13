"""Replace is_superuser with role

Existing superusers become admins and everyone else becomes a member, so no
user gains or loses access. is_active is not touched. The whole upgrade runs
in one transaction: on any error the table stays as it was.

Downgrade grants is_superuser only to admins. Managers fall back to regular
users, so a downgrade can only narrow access, never widen it.

Revision ID: 91ade4d27122
Revises: fe56fa70289e
Create Date: 2026-11-13 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "91ade4d27122"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade():
    # A constant server default lets Postgres add the column without
    # rewriting the table; every existing row starts as 'member'.
    op.add_column(
        "user",
        sa.Column(
            "role", sa.String(length=20), nullable=False, server_default="member"
        ),
    )
    op.create_check_constraint(
        "ck_user_role", "user", "role IN ('admin', 'manager', 'member')"
    )
    op.execute("UPDATE \"user\" SET role = 'admin' WHERE is_superuser")
    op.drop_column("user", "is_superuser")


def downgrade():
    op.add_column(
        "user",
        sa.Column(
            "is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.execute("UPDATE \"user\" SET is_superuser = true WHERE role = 'admin'")
    # The original column had no server default.
    op.alter_column("user", "is_superuser", server_default=None)
    op.drop_constraint("ck_user_role", "user", type_="check")
    op.drop_column("user", "role")
