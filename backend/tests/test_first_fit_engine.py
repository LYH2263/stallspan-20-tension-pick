from app.services.first_fit_engine import allocate_first_fit, free_spans, span_tensions

def test_free_spans_with_pillars():
    spans = free_spans(30.0, [{"position_m": 10.0, "thickness_m": 0.5},
                              {"position_m": 20.0, "thickness_m": 0.5}])
    assert len(spans) == 3
    assert spans[0].start_m == 0.0
    assert spans[2].end_m == 30.0

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

def test_tension_preview_is_read_only_shape():
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "Huge", "stall_width_m": 12.0, "priority": 1},
    ]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}]
    rows = span_tensions(30.0, vendors, pillars)
    by0 = rows[0]
    # span 0 is 0..9.75m: 4m fits, 12m does not.
    assert by0.fit_count == 1
    assert by0.rejected_count == 1
    assert by0.widest_rejected_m == 12.0
