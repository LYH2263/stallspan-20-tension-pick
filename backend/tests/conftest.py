import os

# 必须在导入 app.* 之前：测试全程用内存 sqlite，不碰 Postgres
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SEED_ON_EMPTY"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import models  # noqa: F401  注册表
from app.services.seed import seed_if_empty


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    db = TestingSession()
    seed_if_empty(db)
    db.close()
    yield TestingSession


@pytest.fixture()
def client(db_session):
    def _override():
        db = db_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
