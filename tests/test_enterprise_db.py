"""Enterprise SQLAlchemy persistence tests."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.app.core.db as dbmod

    url = f"sqlite:///{tmp_path / 'enterprise.db'}"
    eng = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    sm = sessionmaker(bind=eng, autocommit=False, autoflush=False, future=True)
    monkeypatch.setattr(dbmod, "DATABASE_URL", url)
    monkeypatch.setattr(dbmod, "engine", eng)
    monkeypatch.setattr(dbmod, "SessionLocal", sm)
    dbmod.Base.metadata.create_all(bind=eng)
    yield


@pytest.mark.parametrize("name", ["M&A Pack", "Litigation", "IPO Due Diligence"])
def test_create_deal_room(name):
    from backend.app.core import enterprise_repo as repo

    out = repo.create_deal_room("u1", name)
    assert out["room_id"]
    rooms = repo.list_deal_rooms("u1")
    assert any(r["name"] == name for r in rooms)


def test_judge_stats_from_db():
    from backend.app.core import enterprise_repo as repo
    from backend.app.core.judgment_seed import seed_judgments_if_empty

    seed_judgments_if_empty()
    stats = repo.judge_disposition_stats("Khanna", "437")
    assert stats["sample_size"] >= 1


def test_deal_room_user_isolation():
    from backend.app.core import enterprise_repo as repo

    a = repo.create_deal_room("user_a", "Secret")
    assert repo.get_deal_room(a["room_id"], "user_b") is None
