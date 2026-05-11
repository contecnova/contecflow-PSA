"""360° performance review campaigns

Revision ID: 071_perf_360_campaigns
Revises: 070_perf_questions_team
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa


revision = "071_perf_360_campaigns"
down_revision = "070_perf_questions_team"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Tabla review_360_campaigns
    if "review_360_campaigns" not in insp.get_table_names():
        op.create_table(
            "review_360_campaigns",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("cycle_id", sa.String(36),
                      sa.ForeignKey("review_cycles.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("subject_id", sa.String(36),
                      sa.ForeignKey("users.id"),
                      nullable=False, index=True),
            sa.Column(
                "status",
                sa.Enum("draft", "active", "closed", name="review360campaignstatus"),
                nullable=False, server_default="draft",
            ),
            sa.Column("anonymity_threshold", sa.Integer, nullable=False, server_default="3"),
            sa.Column("created_by", sa.String(36),
                      sa.ForeignKey("users.id"),
                      nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        )

    # 2. campaign_id FK en performance_reviews
    cols = {c["name"] for c in insp.get_columns("performance_reviews")}
    if "campaign_id" not in cols:
        op.add_column(
            "performance_reviews",
            sa.Column("campaign_id", sa.String(36), nullable=True),
        )
        op.create_index("ix_performance_reviews_campaign_id",
                        "performance_reviews", ["campaign_id"])
        # SQLite no permite añadir FK con ALTER TABLE de forma estándar,
        # pero el campo es funcional sin la constraint física en dev.
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(
                "fk_perf_reviews_campaign_id",
                "performance_reviews", "review_360_campaigns",
                ["campaign_id"], ["id"], ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_perf_reviews_campaign_id",
                           "performance_reviews", type_="foreignkey")
    op.drop_index("ix_performance_reviews_campaign_id",
                  table_name="performance_reviews")
    op.drop_column("performance_reviews", "campaign_id")
    op.drop_table("review_360_campaigns")
    sa.Enum(name="review360campaignstatus").drop(op.get_bind(), checkfirst=True)
