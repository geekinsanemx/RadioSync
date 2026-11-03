"""radiosync Alembic environment.

Changelog:
- 0.1.9 (2026-11-01): default URL is the radiosync storage database.
- 0.1.0 (2026-11-01): initial version.
"""

from alembic import context
from sqlalchemy import engine_from_config, pool

from radiosync.config import load_project
from radiosync.models import Base

config = context.config
target_metadata = Base.metadata
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", f"sqlite:///{load_project().database}")


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = engine_from_config(config.get_section(config.config_ini_section, {}),
                                prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
