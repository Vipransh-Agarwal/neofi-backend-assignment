"""add indexes for performance

Revision ID: 814ab053c6b4
Revises: 5608a0417b53
Create Date: 2025-05-22 17:26:34.928543

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '814ab053c6b4'
down_revision: Union[str, None] = '5608a0417b53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
