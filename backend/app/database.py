from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def begin_read_snapshot(session):
    if session.get_bind().dialect.name == "sqlite":
        session.connection().exec_driver_sql("BEGIN")
    elif session.get_bind().dialect.name == "postgresql":
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


def create_database(database_url: str):
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    # FastAPI may handle successive requests on different threads.
    connect_args = {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, sessions
