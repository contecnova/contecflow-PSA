"""performance review questions + user team field

Revision ID: 070_perf_questions_team
Revises: 9b7c1d2e4f66
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa


revision = "070_perf_questions_team"
down_revision = "9b7c1d2e4f66"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Tabla review_questions (configuración de preguntas por ciclo)
    if "review_questions" not in insp.get_table_names():
        op.create_table(
            "review_questions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("cycle_id", sa.String(36),
                      sa.ForeignKey("review_cycles.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("key", sa.String(80), nullable=False),
            sa.Column("label", sa.String(300), nullable=False),
            sa.Column("hint", sa.String(500), nullable=True),
            sa.Column(
                "kind",
                sa.Enum(
                    "rating_5", "rating_10", "scale_likert",
                    "yes_no", "text_short", "text_long",
                    name="questionkind",
                ),
                nullable=False, server_default="rating_5",
            ),
            sa.Column("order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("required", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("scale_min", sa.Integer, nullable=True),
            sa.Column("scale_max", sa.Integer, nullable=True),
        )

    # 2. answers_json en performance_reviews
    cols = {c["name"] for c in insp.get_columns("performance_reviews")}
    if "answers_json" not in cols:
        op.add_column(
            "performance_reviews",
            sa.Column("answers_json", sa.JSON, nullable=True),
        )
        # Inicializa a dict vacío en filas existentes
        op.execute("UPDATE performance_reviews SET answers_json = '{}' WHERE answers_json IS NULL")

    # 3. team en users (sub-equipo dentro del departamento)
    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "team" not in user_cols:
        op.add_column("users", sa.Column("team", sa.String(120), nullable=True))
        op.create_index("ix_users_team", "users", ["team"])


def downgrade() -> None:
    op.drop_index("ix_users_team", table_name="users")
    op.drop_column("users", "team")
    op.drop_column("performance_reviews", "answers_json")
    op.drop_table("review_questions")
    sa.Enum(name="questionkind").drop(op.get_bind(), checkfirst=True)
