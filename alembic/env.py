from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from alembic import context
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import Base
from app.core.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Import side-effects: registra todos los modelos sobre Base.metadata
import app.models  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _widen_version_table(connection) -> None:
    # Alembic crea alembic_version.version_num como VARCHAR(32) y aquí hay
    # revisiones de hasta 45 caracteres ("075_user_organization_memberships").
    # SQLite no aplica la longitud; PostgreSQL sí, y la cadena se paraba en la
    # 075. Se crea o ensancha la tabla antes de que Alembic la use.
    if connection.dialect.name == "sqlite":
        return
    connection.execute(text(
        "CREATE TABLE IF NOT EXISTS alembic_version ("
        "version_num VARCHAR(255) NOT NULL, "
        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    ))
    connection.execute(text(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    ))
    connection.commit()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _widen_version_table(connection)
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
