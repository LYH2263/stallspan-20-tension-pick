"""柱间紧张度 + 确认落库 的端到端验收（HTTP 层）。"""
from app.models.models import AllocationRun, Placement


def _counts(db_session):
    db = db_session()
    try:
        return db.query(Placement).count(), db.query(AllocationRun).count()
    finally:
        db.close()


def test_tension_read_only_double_refresh_adds_no_rows(client, db_session):
    assert _counts(db_session) == (0, 0)
    r1 = client.get("/api/allocate/tension?segment_id=1")
    r2 = client.get("/api/allocate/tension?segment_id=1")
    assert r1.status_code == r2.status_code == 200
    # 三列齐全：可落数 / 放不下数 / 放不下最宽摊宽
    g = r1.json()["gaps"][0]
    assert {"index", "width_m", "fit_count", "cant_fit_count", "widest_cant_fit_m"} <= set(g)
    # 连刷两次不增行；预估不得落成放置
    assert _counts(db_session) == (0, 0)


def test_state_aligned_with_tension(client):
    t = client.get("/api/allocate/tension?segment_id=1").json()
    s = client.get("/api/allocate/state?segment_id=1").json()
    assert t["gaps"] == s["gaps"]
    assert t["placements"] == s["placements"] == []
    assert t["rejected"] == s["rejected"]


def test_confirm_zero_selected_blocked_no_row(client, db_session):
    r = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": []})
    assert r.status_code == 400
    assert "未选中" in r.json()["detail"]
    assert _counts(db_session) == (0, 0)


def test_confirm_multi_selected_blocked_distinct_message_no_row(client, db_session):
    r = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": [0, 1]})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "一次只能确认一个" in detail and "2 个" in detail
    # 零选文案与多选文案必须可区分
    zero = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": []})
    assert zero.json()["detail"] != detail
    assert _counts(db_session) == (0, 0)


def test_confirm_success_writes_placement_and_run(client, db_session):
    r = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": [0]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert len(body["placements"]) == 1
    p = body["placements"][0]
    # 左端对齐 + 不跨挡柱（首空档 [0, 9.75]）
    assert p["start_m"] == 0.0 and p["end_m"] == p["width_m"]
    assert p["end_m"] <= 9.75 + 1e-6
    # 运行抽屉与落库各恰一行
    assert _counts(db_session) == (1, 1)
    assert len(body["runs"]) == 1 and body["runs"][0]["id"] == body["run_id"]


def test_confirm_recomputes_at_submit_time_ignores_stale_cache(client, db_session):
    # 打开紧张度表（产生"旧预估"），随后改摊宽，再确认必须跟新宽
    client.get("/api/allocate/tension?segment_id=1")
    vendors = client.get("/api/vendors").json()
    top = sorted(vendors, key=lambda v: (v["priority"], v["id"]))[0]
    new_w = 7.5
    pr = client.patch(f"/api/vendors/{top['id']}", json={"stall_width_m": new_w})
    assert pr.status_code == 200
    r = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": [0]})
    assert r.status_code == 200
    p = r.json()["placements"][0]
    assert p["vendor_id"] == top["id"] and p["width_m"] == new_w and p["end_m"] == new_w


def test_confirm_rejects_when_gap_cannot_fit_anything_no_row(client, db_session):
    # 把所有未安置摊主改成最宽也放不下：首空档 9.75，统一改成 25 m（跨挡柱）
    vendors = client.get("/api/vendors").json()
    for v in vendors:
        client.patch(f"/api/vendors/{v['id']}", json={"stall_width_m": 25.0})
    r = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": [0]})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "拒空跑" in detail and "无法形成任何有效放置" in detail
    # 不增行、不记成功运行、不冒充成功
    assert _counts(db_session) == (0, 0)


def test_confirm_failure_keeps_prior_successful_runs(client, db_session):
    ok = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": [0]})
    assert ok.status_code == 200
    assert _counts(db_session) == (1, 1)
    # 后续一次拒空跑失败：不得清掉已成功运行
    vendors = client.get("/api/vendors").json()
    for v in vendors:
        client.patch(f"/api/vendors/{v['id']}", json={"stall_width_m": 25.0})
    bad = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": [0]})
    assert bad.status_code == 409
    assert _counts(db_session) == (1, 1)
    # 恢复后再成功一次：2 放置 2 运行，历史都在
    # （挑一个 *尚未安置* 的最优先摊主改回小宽度）
    state = client.get("/api/allocate/state?segment_id=1").json()
    placed_ids = {p["vendor_id"] for p in state["placements"]}
    vendors = client.get("/api/vendors").json()
    target = next(v for v in sorted(vendors, key=lambda v: (v["priority"], v["id"]))
                  if v["id"] not in placed_ids)
    client.patch(f"/api/vendors/{target['id']}", json={"stall_width_m": 2.0})
    ok2 = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": [0]})
    assert ok2.status_code == 200
    assert _counts(db_session) == (2, 2)


def test_stale_gap_index_after_state_change_rejected_no_row(client, db_session):
    # 不存在的空档 index（等价于吃了打开表时的旧缓存、空档划分已变）
    r = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": [42]})
    assert r.status_code == 409
    assert "空档已不存在" in r.json()["detail"] or "无法形成任何有效放置" in r.json()["detail"]
    assert _counts(db_session) == (0, 0)


def test_map_rejected_runs_conclusions_align(client):
    # 两次成功确认后，主图 placements / 放不下 / 运行抽屉 必须同源对齐
    client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": [0]})
    state1 = client.get("/api/allocate/state?segment_id=1").json()
    # 在第二空档再确认一次
    ok2 = client.post("/api/allocate/confirm", json={"segment_id": 1, "gap_indexes": [1]})
    assert ok2.status_code == 200
    state = client.get("/api/allocate/state?segment_id=1").json()
    # 运行抽屉行数 == 放置行数，且每条 run 指向的 placement 都在主图名单
    assert len(state["runs"]) == len(state["placements"]) == 2
    pids = {p["vendor_id"] for p in state["placements"]}
    assert len(pids) == 2
    # 主图所有放置不跨挡柱：不得与任何挡柱区间相交
    width = state["segment"]["width_m"]
    blocked = [(pl["position_m"] - pl["thickness_m"] / 2, pl["position_m"] + pl["thickness_m"] / 2)
               for pl in state["pillars"]]
    for p in state["placements"]:
        assert 0 <= p["start_m"] < p["end_m"] <= width
        for lo, hi in blocked:
            assert p["end_m"] <= lo or p["start_m"] >= hi
    # 放不下名单与主图名单无交集（同源保证）
    assert {r["vendor_id"] for r in state["rejected"]}.isdisjoint(pids)
