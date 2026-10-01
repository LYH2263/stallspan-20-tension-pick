import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import models  # noqa: F401  (register tables on Base.metadata)


@pytest.fixture
def sess_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def _get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield factory
    app.dependency_overrides.clear()


@pytest.fixture
def client(sess_factory):
    # No context manager: do not run the lifespan that dials Postgres.
    return TestClient(app)


def seed(sf, width=30.0, pillars=(10.0, 20.0), vendors=()):
    db = sf()
    day = models.MarketDay(name="测试夜市", day=dt.date(2026, 10, 1))
    db.add(day); db.flush()
    seg = models.Segment(market_day_id=day.id, name="东街段", width_m=width)
    db.add(seg); db.flush()
    for pos in pillars:
        db.add(models.Pillar(segment_id=seg.id, position_m=pos, thickness_m=0.5, label="柱"))
    for name, w, pri in vendors:
        db.add(models.Vendor(market_day_id=day.id, name=name, stall_width_m=w, priority=pri))
    seg_id = seg.id
    db.commit(); db.close()
    return seg_id


STD_VENDORS = [
    ("阿强烧烤", 4.0, 1), ("林记糖水", 3.0, 1), ("大碗面", 6.0, 1),
    ("老周水果", 5.0, 2), ("小美饰品", 2.5, 2), ("手作皮具", 3.5, 3),
    ("巨型舞台车", 12.0, 9),
]


def counts(sf):
    db = sf()
    runs = db.scalar(select(func.count()).select_from(models.AllocationRun))
    placements = db.scalar(select(func.count()).select_from(models.Placement))
    db.close()
    return runs, placements


def get_span_key(client, seg_id, predicate):
    r = client.get(f"/api/allocate/tension?segment_id={seg_id}")
    assert r.status_code == 200
    return next(s["key"] for s in r.json()["spans"] if predicate(s))


def test_tension_is_read_only_even_when_refreshed(client, sess_factory):
    seg_id = seed(sess_factory, vendors=STD_VENDORS)
    assert counts(sess_factory) == (0, 0)

    r1 = client.get(f"/api/allocate/tension?segment_id={seg_id}")
    r2 = client.get(f"/api/allocate/tension?segment_id={seg_id}")
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["spans"] == r2.json()["spans"]
    # 连刷两次运行表不增行；预估数字绝不落成已入库放置。
    assert counts(sess_factory) == (0, 0)

    span0 = r2.json()["spans"][0]
    assert span0["fit_count"] == 3          # 4 + 3 + 2.5 fit in 0..9.75
    assert span0["rejected_count"] == 4
    assert span0["widest_rejected_m"] == 12.0  # 放不下最宽摊宽


def test_confirm_without_any_span_is_rejected_no_rows(client, sess_factory):
    seg_id = seed(sess_factory, vendors=STD_VENDORS)
    r = client.post("/api/allocate/confirm", json={"segment_id": seg_id, "span_keys": []})
    assert r.status_code == 400
    assert "未选中任何柱间空档" in r.text
    assert counts(sess_factory) == (0, 0)


def test_confirm_with_multiple_spans_is_rejected_with_distinct_message(client, sess_factory):
    seg_id = seed(sess_factory, vendors=STD_VENDORS)
    spans = client.get(f"/api/allocate/tension?segment_id={seg_id}").json()["spans"]
    r = client.post("/api/allocate/confirm",
                    json={"segment_id": seg_id, "span_keys": [spans[0]["key"], spans[1]["key"]]})
    assert r.status_code == 400
    assert "只能选中一个柱间空档" in r.text and "2" in r.text
    # 零选/多选文案必须可区分。
    assert "未选中任何柱间空档" not in r.text
    assert counts(sess_factory) == (0, 0)


def test_confirm_single_span_persists_run_and_placements_once(client, sess_factory):
    seg_id = seed(sess_factory, vendors=STD_VENDORS)
    key = get_span_key(client, seg_id, lambda s: s["start_m"] == 0.0)
    r = client.post("/api/allocate/confirm", json={"segment_id": seg_id, "span_keys": [key]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["placements"]) == 3
    assert counts(sess_factory) == (1, 3)
    # 原空档已变成 0.25m 碎片：再确认该碎片，剩余摊一个都放不下 → 空跑拒绝。
    residual = get_span_key(client, seg_id, lambda s: s["width_m"] < 1.0)
    r2 = client.post("/api/allocate/confirm", json={"segment_id": seg_id, "span_keys": [residual]})
    assert r2.status_code == 409 and "未生成运行记录" in r2.text
    assert counts(sess_factory) == (1, 3)


def test_confirm_uses_submission_moment_width_not_stale_preview(client, sess_factory):
    # 只有一个 3m 的摊；打开紧张度表时预估落点是 0..3。
    seg_id = seed(sess_factory, width=10.0, pillars=(),
                  vendors=[("改宽摊", 3.0, 1)])
    key = get_span_key(client, seg_id, lambda s: True)

    # 打开紧张度表之后、点确认之前，摊主把摊宽改成 5m。
    db = sess_factory()
    v = db.scalars(select(models.Vendor)).first()
    v.stall_width_m = 5.0
    db.commit(); db.close()

    r = client.post("/api/allocate/confirm", json={"segment_id": seg_id, "span_keys": [key]})
    assert r.status_code == 200, r.text
    p = r.json()["placements"][0]
    assert p["width_m"] == 5.0 and p["end_m"] == 5.0  # 跟新宽，不吃旧预估缓存


def test_empty_run_is_refused_not_recorded_as_success(client, sess_factory):
    # 空档只有 2m，待安置摊 5m：该空档无法形成任何有效放置。
    seg_id = seed(sess_factory, width=2.0, pillars=(), vendors=[("大块头", 5.0, 1)])
    key = get_span_key(client, seg_id, lambda s: True)
    r = client.post("/api/allocate/confirm", json={"segment_id": seg_id, "span_keys": [key]})
    assert r.status_code == 409
    assert "放不下" in r.text and "未生成运行记录" in r.text
    assert counts(sess_factory) == (0, 0)


def test_failed_confirm_keeps_existing_successful_runs(client, sess_factory):
    # 先成功一次（4m 摊落入 10m 空档）。
    seg_id = seed(sess_factory, width=10.0, pillars=(), vendors=[("甲", 4.0, 1)])
    key = get_span_key(client, seg_id, lambda s: True)
    ok = client.post("/api/allocate/confirm", json={"segment_id": seg_id, "span_keys": [key]})
    assert ok.status_code == 200
    assert counts(sess_factory) == (1, 1)

    # 再加一个 8m 新摊：占位后只剩 4..10 共 6m，该空档一个摊都放不下 → 空跑拒绝。
    db = sess_factory()
    seg = db.get(models.Segment, seg_id)
    db.add(models.Vendor(market_day_id=seg.market_day_id, name="乙", stall_width_m=8.0, priority=2))
    db.commit(); db.close()

    residual = get_span_key(client, seg_id, lambda s: True)
    r = client.post("/api/allocate/confirm", json={"segment_id": seg_id, "span_keys": [residual]})
    assert r.status_code == 409 and "未生成运行记录" in r.text
    # 既有成功运行与其放置原样保留。
    assert counts(sess_factory) == (1, 1)


def test_stale_span_key_after_pillar_change_is_rejected(client, sess_factory):
    seg_id = seed(sess_factory, width=10.0, pillars=(), vendors=[("甲", 3.0, 1)])
    key = get_span_key(client, seg_id, lambda s: True)
    # 确认前新增挡柱，旧空档坐标已不存在。
    db = sess_factory()
    db.add(models.Pillar(segment_id=seg_id, position_m=5.0, thickness_m=0.5))
    db.commit(); db.close()
    r = client.post("/api/allocate/confirm", json={"segment_id": seg_id, "span_keys": [key]})
    assert r.status_code == 409
    assert counts(sess_factory) == (0, 0)


def test_state_aligns_map_rejected_and_run_drawer(client, sess_factory):
    seg_id = seed(sess_factory, vendors=STD_VENDORS)
    key = get_span_key(client, seg_id, lambda s: s["start_m"] == 0.0)
    client.post("/api/allocate/confirm", json={"segment_id": seg_id, "span_keys": [key]})

    st = client.get(f"/api/allocate/state?segment_id={seg_id}").json()
    # 运行抽屉里的放置并集 == 主图已入库放置，名单完全一致。
    from_runs = sorted((p["vendor_id"] for run in st["runs"] for p in run["placements"]))
    from_map = sorted(p["vendor_id"] for p in st["placements"])
    assert from_runs == from_map == [1, 2, 5]  # 阿强4 / 林记3 / 小美2.5
    # 放不下名单只含仍待安置且所有空档都放不下的摊主（12m 舞台车）。
    rejected_ids = {r["vendor_id"] for r in st["rejected"]}
    assert rejected_ids == {7}
    # 已落库摊主不出现在放不下里。
    assert rejected_ids.isdisjoint(from_map)
