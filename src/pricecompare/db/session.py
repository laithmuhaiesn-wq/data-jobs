import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def get_engine(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL", "sqlite:///pricecompare.db")
    for plain in ("postgres://", "postgresql://"):
        if url.startswith(plain):  # providers hand out plain URLs; we ship the psycopg 3 driver
            url = "postgresql+psycopg://" + url[len(plain):]
    return create_engine(url)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("offer")}
    if "image_url" not in cols:  # tables made before pictures existed
        with engine.begin() as c:
            c.execute(text("ALTER TABLE offer ADD COLUMN image_url VARCHAR(500)"))


def make_session(engine) -> Session:
    return sessionmaker(engine, expire_on_commit=False)()
