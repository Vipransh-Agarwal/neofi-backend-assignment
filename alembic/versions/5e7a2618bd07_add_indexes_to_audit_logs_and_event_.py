"""add indexes to audit_logs and event_exceptions

Revision ID: 5e7a2618bd07
Revises: 25ceaad7b4fb
Create Date: 2025-05-22 19:40:34.363852

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e7a2618bd07'
down_revision: Union[str, None] = '25ceaad7b4fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
