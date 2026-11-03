"""radiosync database: SQLite engine, Alembic migrations and consistent backups.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from .config import Project, backup_target

MIGRATIONS = Path(__file__).with_name("migrations")


def _enable_foreign_keys(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    def __init__(self, project: Project):
        self.project = project
        self.path = project.database
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.path}")
        event.listen(self.engine, "connect", _enable_foreign_keys)

    def alembic_config(self) -> Config:
        config = Config()
        config.set_main_option("script_location", str(MIGRATIONS))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.path}")
        return config

    def ensure_schema(self) -> None:
        config = self.alembic_config()
        head = ScriptDirectory.from_config(config).get_current_head()
        with self.engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        if current == head:
            return
        if current is not None:
            self.backup()
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def backup(self) -> Path | None:
        """Online-consistent copy of the database using the SQLite backup API."""
        if not self.path.exists():
            return None
        target = backup_target(self.project, self.path)
        source = sqlite3.connect(self.path)
        destination = sqlite3.connect(target)
        try:
            with destination:
                source.backup(destination)
        finally:
            destination.close()
            source.close()
        return target

    @contextmanager
    def session(self, write: bool = False):
        if write:
            self.backup()
        with Session(self.engine) as session:
            if write:
                with session.begin():
                    yield session
            else:
                yield session
