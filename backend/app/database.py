from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def create_database(database_url: str):
    # FastAPI may handle successive requests on different threads.
    connect_args = {"check_same_thread": False} if make_url(database_url).get_backend_name() == "sqlite" else {}
    engine = create_engine(database_url, connect_args=connect_args)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, sessions
