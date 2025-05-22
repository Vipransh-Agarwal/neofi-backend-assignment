"""add useful event indexes

Revision ID: 25ceaad7b4fb
Revises: f5f647bef18f
Create Date: 2025-05-22 19:40:09.209419

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25ceaad7b4fb'
down_revision: Union[str, None] = 'f5f647bef18f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
