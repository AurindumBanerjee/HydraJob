"""Phase 0 baseline migration.

Revision ID: 20261114_0001
Revises:
Create Date: 2026-11-14 00:00:00+00:00
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "20261114_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Baseline revision prior to Phase 1 domain tables."""


def downgrade() -> None:
    """Downgrade baseline revision."""
