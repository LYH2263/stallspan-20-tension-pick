"""Allocation endpoints.

读路径（tension / state）零写入；唯一写路径是 POST /confirm，且必须恰好选中
一个柱间空档。所有计算都在请求瞬间从数据库重读摊主宽度、挡柱与已入库放置，
不使用任何打开紧张度表时的旧预估缓存。
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import AllocationRun, Pillar, Placement, Segment, Vendor
from app.services.first_fit_engine import (
    free_spans,
    placement_to_dict,
    simulate_span,
    span_tensions,
    tension_to_dict,
)
router = APIRouter(prefix="/allocate", tags=["allocate"])

NO_SPAN_MSG = "未选中任何柱间空档：请勾选一个柱间空档后再确认。"
MANY_SPAN_MSG = "只能选中一个柱间空档，请取消多余勾选后再确认（当前选中 {n} 个）。"
EMPTY_RUN_MSG = "该柱间空档当前放不下任何待安置摊位，已拒绝本次空跑（未生成运行记录）。"


class ConfirmIn(BaseModel):
    segment_id: int = 1
    # 前端勾选结果，键为柱间空档边界（start_m-end_m），粒度锁死在空档上。
    # 服务端强制恰好一个，零选/多选分别给可区分文案。
    span_keys: list[str]


def _snapshot(db: Session, segment_id: int) -> dict:
    """提交瞬间的权威输入：摊主、挡柱、已入库放置全部重读。"""
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = [{"id": p.id, "position_m": p.position_m, "thickness_m": p.thickness_m,
                "label": p.label}
               for p in db.scalars(
                   select(Pillar).where(Pillar.segment_id == segment_id)
                   .order_by(Pillar.position_m, Pillar.id)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m,
                "priority": v.priority}
               for v in db.scalars(
                   select(Vendor).where(Vendor.market_day_id == seg.market_day_id)
                   .order_by(Vendor.priority, Vendor.id)).all()]
    placed_rows = db.scalars(
        select(Placement).where(Placement.segment_id == segment_id)
        .order_by(Placement.start_m, Placement.id)).all()
    placements = [{"vendor_id": p.vendor_id, "vendor_name": p.vendor_name,
                   "start_m": p.start_m, "end_m": p.end_m, "width_m": p.width_m,
                   "run_id": p.run_id}
                  for p in placed_rows]
    placed_vendor_ids = {p.vendor_id for p in placed_rows}
    pending = [v for v in vendors if v["id"] not in placed_vendor_ids]
    return {"segment": seg, "pillars": pillars, "vendors": vendors,
            "placements": placements, "pending": pending}


def _segment_dict(seg: Segment) -> dict:
    return {"id": seg.id, "name": seg.name, "width_m": seg.width_m}


def span_key(start_m: float, end_m: float) -> str:
    """空档身份：坐标边界键。序号会随前序确认平移，坐标不会错位到别的空档。"""
    return f"{round(float(start_m), 3)}-{round(float(end_m), 3)}"


@router.get("/tension")
def tension(segment_id: int = 1, db: Session = Depends(get_db)):
    """柱间紧张度表（只读，绝不写库）：每个空档的可落数、放不下数、
    放不下最宽摊宽。连刷任意次都不会产生运行或放置行。"""
    snap = _snapshot(db, segment_id)
    rows = span_tensions(snap["segment"].width_m, snap["pending"],
                         snap["pillars"], snap["placements"])
    return {
        "segment": _segment_dict(snap["segment"]),
        "pillars": snap["pillars"],
        "vendors": snap["pending"],
        "spans": [{**tension_to_dict(t),
                   "key": span_key(t.start_m, t.end_m)} for t in rows],
    }


@router.get("/state")
def state(segment_id: int = 1, db: Session = Depends(get_db)):
    """主图 / 放不下 / 运行抽屉共用的唯一只读事实源，保证三处结论对齐。"""
    snap = _snapshot(db, segment_id)
    seg = snap["segment"]
    spans = free_spans(seg.width_m, snap["pillars"], snap["placements"])

    rejected: list[dict] = []
    for v in snap["pending"]:
        need = float(v["stall_width_m"])
        if need <= 0 or not any(sp.width_m + 1e-9 >= need for sp in spans):
            rejected.append({"vendor_id": v["id"], "vendor_name": v["name"],
                             "width_m": need,
                             "reason": "所有柱间空档都放不下且不跨越挡柱"})

    runs = []
    for run in db.scalars(
            select(AllocationRun).where(AllocationRun.segment_id == segment_id)
            .order_by(AllocationRun.id.desc())).all():
        row_pl = db.scalars(
            select(Placement).where(Placement.run_id == run.id)
            .order_by(Placement.start_m, Placement.id)).all()
        runs.append({
            "id": run.id,
            "created_at": run.created_at.isoformat(),
            "span_index": run.span_index,
            "span_start_m": run.span_start_m,
            "span_end_m": run.span_end_m,
            "placements": [{"vendor_id": p.vendor_id, "vendor_name": p.vendor_name,
                            "start_m": p.start_m, "end_m": p.end_m,
                            "width_m": p.width_m} for p in row_pl],
        })

    return {
        "segment": _segment_dict(seg),
        "pillars": snap["pillars"],
        "free_spans": [{"index": s.index, "key": span_key(s.start_m, s.end_m),
                        "start_m": s.start_m, "end_m": s.end_m,
                        "width_m": round(s.width_m, 3)} for s in spans],
        "placements": snap["placements"],
        "pending_vendors": snap["pending"],
        "rejected": rejected,
        "runs": runs,
    }


@router.post("/confirm")
def confirm(body: ConfirmIn, db: Session = Depends(get_db)):
    """确认落库：恰好选中一个柱间空档；按提交瞬间数据重算；只发一次请求，
    没有“先发再交”的两段令牌。零落位即拒空跑，不建行、不算成功。"""
    chosen = body.span_keys or []
    if len(chosen) == 0:
        raise HTTPException(400, NO_SPAN_MSG)
    if len(chosen) > 1:
        raise HTTPException(400, MANY_SPAN_MSG.format(n=len(chosen)))

    snap = _snapshot(db, body.segment_id)
    seg = snap["segment"]
    # 不接受打开紧张度表时缓存的旧空档：此刻重算后按边界坐标定位。
    spans = free_spans(seg.width_m, snap["pillars"], snap["placements"])
    wanted = chosen[0]
    target = next((s for s in spans if span_key(s.start_m, s.end_m) == wanted), None)
    if target is None:
        raise HTTPException(409, "所选柱间空档已变化，请刷新紧张度表后按当前空档重新勾选（本次未写入）。")

    new_placements, _ = simulate_span(target, snap["pending"])
    if not new_placements:
        # 业务要求拒空跑：明确拒绝、不增行、不得记成成功运行。
        raise HTTPException(409, EMPTY_RUN_MSG)

    run = AllocationRun(segment_id=seg.id, created_at=datetime.utcnow(),
                        span_index=target.index, span_start_m=target.start_m,
                        span_end_m=target.end_m,
                        result_json=json.dumps(
                            {"placements": [placement_to_dict(p) for p in new_placements]},
                            ensure_ascii=False))
    db.add(run)
    db.flush()  # 取 run.id；失败整体回滚，不清任何既有运行
    for p in new_placements:
        db.add(Placement(run_id=run.id, segment_id=seg.id, vendor_id=p.vendor_id,
                         vendor_name=p.vendor_name, start_m=p.start_m, end_m=p.end_m,
                         width_m=p.width_m))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "该空档中的摊主已在其它确认中落位，请刷新后重试（本次未写入）。")
    db.refresh(run)
    return {
        "run_id": run.id,
        "segment": _segment_dict(seg),
        "span_index": target.index,
        "span_start_m": target.start_m,
        "span_end_m": target.end_m,
        "placements": [placement_to_dict(p) for p in new_placements],
    }
