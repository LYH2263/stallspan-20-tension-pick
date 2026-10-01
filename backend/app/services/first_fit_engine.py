"""1D First-Fit stall placement along a street segment; stalls cannot cross pillars.

紧张度（tension）与确认落库均为 *纯推导*：
- 柱间空档 = 挡柱区间切出的 free spans（只读几何事实）
- 剩余空档 = 柱间空档减去已落库放置占用的区间
- 紧张度数字只是对"按提交瞬间摊主清单能放进多少"的预估，不代表任何落库放置
"""
from __future__ import annotations
from dataclasses import asdict, dataclass

_EPS = 1e-6

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
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    free_spans: list[tuple[float, float]]

def free_spans_from_pillars(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """pillars: position_m, thickness_m — treated as blocked intervals."""
    blocked = []
    for p in pillars:
        half = p.get("thickness_m", 0.4) / 2.0
        lo = max(0.0, p["position_m"] - half)
        hi = min(width_m, p["position_m"] + half)
        if hi > lo:
            blocked.append((lo, hi))
    blocked.sort()
    merged = []
    for lo, hi in blocked:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    spans = []
    cursor = 0.0
    for lo, hi in merged:
        if lo > cursor:
            spans.append((cursor, lo))
        cursor = hi
    if cursor < width_m:
        spans.append((cursor, width_m))
    return [(round(a, 3), round(b, 3)) for a, b in spans if b - a > 1e-6]

def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict]) -> AllocResult:
    """vendors sorted by priority ascending then id; each needs stall_width_m contiguous in one free span (no pillar cross)."""
    spans = free_spans_from_pillars(width_m, pillars)
    # mutable remaining capacity per span
    remain = [[a, b] for a, b in spans]
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in ordered:
        need = float(v["stall_width_m"])
        placed = False
        for span in remain:
            avail = span[1] - span[0]
            if avail + 1e-9 >= need:
                start = span[0]
                end = start + need
                placements.append(Placement(v["id"], v["name"], round(start, 3), round(end, 3), need))
                span[0] = end
                placed = True
                break
        if not placed:
            rejected.append(Rejected(v["id"], v["name"], need, "无连续空档可放下且不跨越挡柱"))
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free)

def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
    }


# ---------------------------------------------------------------------------
# 剩余空档 / 紧张度 / 单空档确认落位 —— 全部纯函数，不读不写数据库
# ---------------------------------------------------------------------------

def remaining_spans(
    base_spans: list[tuple[float, float]],
    occupied: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """柱间空档 ``base_spans`` 减去已落库放置占用区间 ``occupied`` 后的剩余空档。

    每次成功确认都会在某个柱间空档左端吃掉一段，剩余空档仍是左端对齐的连续段。
    占用越界或跨越挡柱（落进空档间隙）时按交集裁剪，不改变柱间空档划分。
    """
    occ = sorted((max(0.0, a), b) for a, b in occupied if b - a > _EPS)
    out: list[tuple[float, float]] = []
    for lo, hi in base_spans:
        pieces = [[lo, hi]]
        for oa, ob in occ:
            nx: list[list[float]] = []
            for pa, pb in pieces:
                if ob <= pa + _EPS or oa >= pb - _EPS:
                    nx.append([pa, pb])
                    continue
                if oa > pa:
                    nx.append([pa, oa])
                if ob < pb:
                    nx.append([ob, pb])
            pieces = nx
        out.extend((round(a, 3), round(b, 3)) for a, b in pieces if b - a > _EPS)
    return out


@dataclass
class GapTension:
    index: int
    start_m: float
    end_m: float
    width_m: float
    fit_count: int          # 可落数：剩余空档内能放下的摊位数
    cant_fit_count: int     # 放不下数：轮到本空档仍放不下的摊位数
    widest_cant_fit_m: float | None  # 放不下最宽摊宽


def gap_tensions(
    base_spans: list[tuple[float, float]],
    occupied: list[tuple[float, float]],
    vendors: list[dict],
) -> list[GapTension]:
    """逐柱间剩余空档的紧张度预估。

    每个空档 *独立* 按摊主优先级队列做 first-fit 左端排布：
    能依次塞进本空档的计入可落数；塞不进的计入放不下数，
    放不下最宽摊宽 = 这些摊主里的最大需求宽。仅为预估，不产出任何放置。
    """
    spans = remaining_spans(base_spans, occupied)
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    out: list[GapTension] = []
    for i, (lo, hi) in enumerate(spans):
        cursor = lo
        fit = 0
        overflow: list[float] = []
        for v in ordered:
            need = float(v["stall_width_m"])
            if cursor + need <= hi + 1e-9:
                cursor += need
                fit += 1
            else:
                overflow.append(need)
        out.append(
            GapTension(
                index=i,
                start_m=lo,
                end_m=hi,
                width_m=round(hi - lo, 3),
                fit_count=fit,
                cant_fit_count=len(overflow),
                widest_cant_fit_m=(round(max(overflow), 3) if overflow else None),
            )
        )
    return out


def simulate_first_fit(
    base_spans: list[tuple[float, float]],
    occupied: list[tuple[float, float]],
    vendors: list[dict],
) -> AllocResult:
    """在柱间空档扣除已落库占用后，对给定摊主（未安置队列）再跑一遍 first-fit。

    只读预估：产出的 placements 表示"现在点确认还能依次落下谁"，
    rejected 即当前瞬时状态下仍放不下的名单。不产生任何副作用。
    """
    remain = [[a, b] for a, b in remaining_spans(base_spans, occupied)]
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in ordered:
        need = float(v["stall_width_m"])
        placed = False
        for span in remain:
            if span[1] - span[0] + 1e-9 >= need:
                start = span[0]
                placements.append(Placement(v["id"], v["name"], round(start, 3),
                                            round(start + need, 3), need))
                span[0] = start + need
                placed = True
                break
        if not placed:
            rejected.append(Rejected(v["id"], v["name"], need, "无连续空档可放下且不跨越挡柱"))
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > _EPS]
    return AllocResult(placements, rejected, free)


def place_in_gap(
    base_spans: list[tuple[float, float]],
    occupied: list[tuple[float, float]],
    gap_index: int,
    vendors: list[dict],
) -> tuple[Placement | None, Rejected | None]:
    """确认提交瞬间对 *恰好一个* 选中空档的落位重算。

    在该空档当前剩余空间内按 first-fit（优先级）挑第一个放得下的摊主，
    左端对齐落位。返回 (放置, 拒绝)；该空档无任何摊主能放下时放置为 None。
    """
    spans = remaining_spans(base_spans, occupied)
    if not 0 <= gap_index < len(spans):
        return None, Rejected(0, "", 0.0, "选中空档已不存在（挡柱或放置已变化）")
    start_m, end_m = spans[gap_index]
    avail = end_m - start_m
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    for v in ordered:
        need = float(v["stall_width_m"])
        if avail + 1e-9 >= need:
            return (
                Placement(v["id"], v["name"], round(start_m, 3), round(start_m + need, 3), need),
                None,
            )
    widest = max((float(v["stall_width_m"]) for v in ordered), default=0.0)
    return (
        None,
        Rejected(
            0, "", round(widest, 3),
            f"选中空档宽 {round(avail, 3)} m，最窄需求也放不下"
            if ordered else "本集日已无待安置摊主",
        ),
    )
