from app.services.first_fit_engine import (
    allocate_first_fit,
    free_spans_from_pillars,
    gap_tensions,
    place_in_gap,
    remaining_spans,
)


def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(30.0, [{"position_m": 10.0, "thickness_m": 0.5},
                                           {"position_m": 20.0, "thickness_m": 0.5}])
    assert len(spans) == 3
    assert spans[0][0] == 0.0


def test_first_fit_no_cross_pillar():
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 12.0, "priority": 1},
    ]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert any(p.vendor_name == "A" for p in r.placements)
    assert len(r.placements) + len(r.rejected) == 2


def test_reject_oversized():
    vendors = [{"id": 1, "name": "Huge", "stall_width_m": 25.0, "priority": 1}]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"


def test_remaining_spans_subtracts_occupied_from_left():
    base = free_spans_from_pillars(30.0, [{"position_m": 10.0, "thickness_m": 0.5},
                                          {"position_m": 20.0, "thickness_m": 0.5}])
    # 首个柱间空档 [0, 9.75] 左端吃掉 4 m
    rem = remaining_spans(base, [(0.0, 4.0)])
    assert rem[0] == (4.0, 9.75)
    # 其余空档不变
    assert rem[1] == base[1] and rem[2] == base[2]


def test_gap_tension_fit_and_overflow_counts():
    base = free_spans_from_pillars(30.0, [{"position_m": 10.0, "thickness_m": 0.5},
                                          {"position_m": 20.0, "thickness_m": 0.5}])
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 5.0, "priority": 1},
        {"id": 3, "name": "Huge", "stall_width_m": 12.0, "priority": 9},
    ]
    t = gap_tensions(base, [], vendors)
    # 空档0 宽 9.75：A(4)+B(5)=9 落得下，Huge(12) 放不下 → 可落2 放不下1 最宽12
    g0 = t[0]
    assert g0.fit_count == 2
    assert g0.cant_fit_count == 1
    assert g0.widest_cant_fit_m == 12.0
    # 中间空档同样 9.75 宽，口径一致
    assert t[1].fit_count == 2 and t[1].widest_cant_fit_m == 12.0
    # 尾空档 [20.25,30] 宽 9.75 同理
    assert t[2].cant_fit_count == 1


def test_gap_tension_respects_existing_occupancy():
    base = free_spans_from_pillars(30.0, [{"position_m": 10.0, "thickness_m": 0.5}])
    # 空档0 已占 7 m，剩 2.75：4 m 的 A 也放不下
    t = gap_tensions(base, [(0.0, 7.0)], [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
    ])
    assert t[0].fit_count == 0
    assert t[0].cant_fit_count == 1
    assert t[0].widest_cant_fit_m == 4.0
    assert round(t[0].width_m, 3) == 2.75


def test_place_in_gap_left_aligned_by_priority():
    base = free_spans_from_pillars(30.0, [{"position_m": 10.0, "thickness_m": 0.5}])
    vendors = [
        {"id": 1, "name": "Low", "stall_width_m": 3.0, "priority": 2},
        {"id": 2, "name": "Hi", "stall_width_m": 4.0, "priority": 1},
    ]
    p, rej = place_in_gap(base, [], 0, vendors)
    assert rej is None
    assert p.vendor_name == "Hi" and p.start_m == 0.0 and p.end_m == 4.0
    # 第二次确认同一空档：Hi 已落库被调用方排除，只剩 Low，紧接上次占用左端对齐
    p2, _ = place_in_gap(base, [(0.0, 4.0)], 0,
                         [{"id": 1, "name": "Low", "stall_width_m": 3.0, "priority": 2}])
    assert p2.vendor_name == "Low" and p2.start_m == 4.0


def test_place_in_gap_none_fits_returns_rejected():
    base = free_spans_from_pillars(30.0, [{"position_m": 10.0, "thickness_m": 0.5}])
    p, rej = place_in_gap(base, [(0.0, 7.0)], 0,
                          [{"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1}])
    assert p is None and rej is not None
    assert "放不下" in rej.reason


def test_place_in_stale_gap_index_rejected():
    base = free_spans_from_pillars(30.0, [{"position_m": 10.0, "thickness_m": 0.5}])
    p, rej = place_in_gap(base, [], 9, [{"id": 1, "name": "A", "stall_width_m": 4.0}])
    assert p is None and "空档已不存在" in rej.reason
