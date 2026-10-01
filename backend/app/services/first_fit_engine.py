"""1D First-Fit stall placement along a street segment.

Stalls occupy one contiguous free span between pillars and can never cross a
pillar. Existing placements carve room out of spans; all functions here are
pure calculations used both by read-only tension previews and by confirm.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass

EPS = 1e-9

@dataclass
class Placement:
    vendor_id: int
    vendor_name: str
    start_m: float
    end_m: float
    width_m: float

@dataclass
class Rejected:
    vendor_id: int
    vendor_name: str
    width_m: float
    reason: str

@dataclass
class Span:
    index: int
    start_m: float
    end_m: float

    @property
    def width_m(self) -> float:
        return self.end_m - self.start_m

@dataclass
class SpanTension:
    """Per free-span read-only preview. 放不下 means after fitting 可落 vendors
    first-fit into this span alone, these vendors still do not fit."""
    index: int
    start_m: float
    end_m: float
    width_m: float
    fit_count: int
    fit_vendor_ids: list[int]
    rejected: list[Rejected]

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    @property
    def widest_rejected_m(self) -> float | None:
        if not self.rejected:
            return None
        return max(r.width_m for r in self.rejected)

def pillar_blocked(width_m: float, pillars: list[dict]) -> list[list[float]]:
    """pillars: position_m, thickness_m — treated as blocked intervals."""
    blocked = []
    for p in pillars:
        half = p.get("thickness_m", 0.4) / 2.0
        lo = max(0.0, p["position_m"] - half)
        hi = min(width_m, p["position_m"] + half)
        if hi > lo:
            blocked.append([lo, hi])
    blocked.sort()
    merged: list[list[float]] = []
    for lo, hi in blocked:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    return merged

def free_spans(width_m: float, pillars: list[dict],
               placements: list[dict] | None = None) -> list[Span]:
    """Free spans after removing pillar intervals and already-placed stalls.

    placements: [{start_m, end_m}] — committed stalls that carve room out.
    Returns spans in left-to-right order with stable indices.
    """
    blocked = pillar_blocked(width_m, pillars)
    for pl in placements or []:
        lo = max(0.0, float(pl["start_m"]))
        hi = min(width_m, float(pl["end_m"]))
        if hi > lo:
            blocked.append([lo, hi])
    blocked.sort()
    merged: list[list[float]] = []
    for lo, hi in blocked:
        if not merged or lo > merged[-1][1] + EPS:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    spans: list[Span] = []
    cursor = 0.0
    for lo, hi in merged:
        if lo > cursor + EPS:
            spans.append(Span(len(spans), round(cursor, 3), round(lo, 3)))
        cursor = max(cursor, hi)
    if cursor < width_m - EPS:
        spans.append(Span(len(spans), round(cursor, 3), round(width_m, 3)))
    return spans

def order_vendors(vendors: list[dict]) -> list[dict]:
    return sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))

def simulate_span(span: Span, vendors: list[dict]) -> tuple[list[Placement], list[Rejected]]:
    """First-fit every considered vendor into THIS span alone, from its left
    edge. Vendors that do not fit are rejected for this span."""
    cursor = span.start_m
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in order_vendors(vendors):
        need = float(v["stall_width_m"])
        if need <= 0:
            rejected.append(Rejected(v["id"], v["name"], need, "摊宽必须大于 0"))
            continue
        if cursor + need <= span.end_m + EPS:
            placements.append(Placement(v["id"], v["name"], round(cursor, 3),
                                        round(cursor + need, 3), need))
            cursor += need
        else:
            rejected.append(Rejected(v["id"], v["name"], need, "该柱间空档放不下"))
    return placements, rejected

def span_tensions(width_m: float, vendors: list[dict], pillars: list[dict],
                  placements: list[dict] | None = None) -> list[SpanTension]:
    """Read-only tension table: for each current free span, how many of the
    still-unplaced vendors would fit first-fit, how many would not, and the
    widest stall among the not-fit."""
    spans = free_spans(width_m, pillars, placements)
    out: list[SpanTension] = []
    for sp in spans:
        pl, rej = simulate_span(sp, vendors)
        out.append(SpanTension(sp.index, sp.start_m, sp.end_m,
                               round(sp.width_m, 3), len(pl),
                               [p.vendor_id for p in pl], rej))
    return out

def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict]) -> "AllocResult":
    """Legacy whole-segment first fit (kept for engine unit tests)."""
    spans = free_spans(width_m, pillars)
    remain = [[s.start_m, s.end_m] for s in spans]
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in order_vendors(vendors):
        need = float(v["stall_width_m"])
        placed = False
        for cell in remain:
            if cell[1] - cell[0] + EPS >= need:
                start = cell[0]
                placements.append(Placement(v["id"], v["name"], round(start, 3),
                                            round(start + need, 3), need))
                cell[0] = start + need
                placed = True
                break
        if not placed:
            rejected.append(Rejected(v["id"], v["name"], need, "无连续空档可放下且不跨越挡柱"))
    free = [(round(c[0], 3), round(c[1], 3)) for c in remain if c[1] - c[0] > EPS]
    return AllocResult(placements, rejected, free)

@dataclass
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    free_spans: list[tuple[float, float]]

def tension_to_dict(t: SpanTension) -> dict:
    return {
        "index": t.index,
        "start_m": t.start_m,
        "end_m": t.end_m,
        "width_m": t.width_m,
        "fit_count": t.fit_count,
        "fit_vendor_ids": t.fit_vendor_ids,
        "rejected_count": t.rejected_count,
        "widest_rejected_m": t.widest_rejected_m,
        "rejected": [asdict(r) for r in t.rejected],
    }

def placement_to_dict(p: Placement) -> dict:
    return asdict(p)
