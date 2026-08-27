"""add trade.decision_id and trade.fee

Revision ID: 805d007cfb79
Revises: 65994f51f3a1
Create Date: 2026-08-26 22:27:47.094064

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '805d007cfb79'
down_revision: Union[str, Sequence[str], None] = '65994f51f3a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("trade") as batch_op:
        batch_op.add_column(sa.Column("decision_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("fee", sa.Float(), nullable=False, server_default="0"))
        batch_op.create_foreign_key("fk_trade_decision_id", "decision", ["decision_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("trade") as batch_op:
        batch_op.drop_constraint("fk_trade_decision_id", type_="foreignkey")
        batch_op.drop_column("fee")
        batch_op.drop_column("decision_id")
