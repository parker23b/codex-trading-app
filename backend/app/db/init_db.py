from app.db.migrations import ensure_database_schema_current
from app.db.session import engine


def initialize_database() -> None:
    ensure_database_schema_current(engine)
