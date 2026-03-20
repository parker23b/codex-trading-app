from collections.abc import Generator

from sqlmodel import Session, create_engine

from app.core.config import get_settings

settings = get_settings()
engine_kwargs: dict[str, object] = {"echo": False}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(settings.database_url, **engine_kwargs)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
