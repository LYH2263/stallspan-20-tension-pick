"""柱间紧张度（只读预估）与确认落库。

铁律：
- GET 接口一律只读，绝不产生 Placement / AllocationRun 行；
- 只有 POST /confirm 在"恰好选中一个空档且该空档此刻能形成有效放置"时才落库；
- 确认按 *提交瞬间* 的摊主与挡柱重算，不接受前端带来的任何预估数字，
  不存在"先预占再提交"的两段令牌。
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import AllocationRun, Pillar, Placement, Segment, Vendor
from app.services.first_fit_engine import (
    free_spans_from_pillars,
    gap_tensions,
    place_in_gap,
    simulate_first_fit,
)

router = APIRouter(prefix="/allocate", tags=["allocate"])


class ConfirmIn(BaseModel):
    segment_id: int = 1
    # 勾选粒度锁在柱间空档；确认时必须恰好一个，零选/多选一律拦下
    gap_indexes: list[int] = Field(default_factory=list)


def _load_snapshot(db: Session, segment_id: int):
    """提交瞬间的统一重算依据：街段、挡柱、摊主、已落库放置。每次现查，无缓存。"""
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == segment_id)
                                   .order_by(Pillar.position_m)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)
                                   .order_by(Vendor.priority, Vendor.id)).all()]
    placements = db.scalars(
        select(Placement).where(Placement.segment_id == segment_id).order_by(Placement.start_m, Placement.id)
    ).all()
    base_spans = free_spans_from_pillars(seg.width_m, pillars)
    occupied = [(p.start_m, p.end_m) for p in placements]
    placed_vendor_ids = {p.vendor_id for p in placements}
    pending_vendors = [v for v in vendors if v["id"] not in placed_vendor_ids]
    return seg, pillars, vendors, placements, base_spans, occupied, pending_vendors


def _state_payload(db: Session, seg, pillars, placements, base_spans, occupied, pending_vendors):
    tensions = gap_tensions(base_spans, occupied, pending_vendors)
    # 当前瞬时放不下名单：在已落库占用之上对未安置摊主只读模拟一遍
    sim = simulate_first_fit(base_spans, occupied, pending_vendors)
    runs = db.scalars(
        select(AllocationRun).where(AllocationRun.segment_id == seg.id).order_by(AllocationRun.id)
    ).all()
    return {
        "segment": {"id": seg.id, "name": seg.name, "width_m": seg.width_m},
        "pillars": pillars,
        "gaps": [
            {
                "index": t.index, "start_m": t.start_m, "end_m": t.end_m, "width_m": t.width_m,
                "fit_count": t.fit_count, "cant_fit_count": t.cant_fit_count,
                "widest_cant_fit_m": t.widest_cant_fit_m,
            }
            for t in tensions
        ],
        "placements": [
            {"id": p.id, "vendor_id": p.vendor_id, "vendor_name": p.vendor_name,
             "start_m": p.start_m, "end_m": p.end_m, "width_m": p.width_m}
            for p in placements
        ],
        "rejected": [
            {"vendor_id": r.vendor_id, "vendor_name": r.vendor_name,
             "width_m": r.width_m, "reason": r.reason}
            for r in sim.rejected
        ],
        "pending_fit_count": len(sim.placements),
        "runs": [
            {"id": r.id, "placement_id": r.placement_id, "created_at": r.created_at.isoformat()}
            for r in runs
        ],
    }


@router.get("/tension")
def tension(segment_id: int = 1, db: Session = Depends(get_db)):
    """柱间紧张度表：纯只读。连刷任意次都不增行，数字仅为预估，不是已入库放置。"""
    seg, pillars, _vendors, placements, base_spans, occupied, pending_vendors = _load_snapshot(db, segment_id)
    payload = _state_payload(db, seg, pillars, placements, base_spans, occupied, pending_vendors)
    return payload


@router.get("/state")
def state(segment_id: int = 1, db: Session = Depends(get_db)):
    """统一只读视图：主图 / 放不下 / 运行抽屉都以此为准，保证三处结论对齐。"""
    seg, pillars, _v, placements, base_spans, occupied, pending = _load_snapshot(db, segment_id)
    return _state_payload(db, seg, pillars, placements, base_spans, occupied, pending)


@router.post("/confirm")
def confirm(body: ConfirmIn, db: Session = Depends(get_db)):
    # --- 选择校验：必须恰好一个柱间空档，零选与多选文案可区分，都不增行 ---
    if len(body.gap_indexes) == 0:
        raise HTTPException(400, "未选中任何柱间空档：请先勾选一个空档再确认（本次未落库，无新增运行）")
    if len(body.gap_indexes) > 1:
        raise HTTPException(
            400,
            f"一次只能确认一个柱间空档，当前勾选了 {len(body.gap_indexes)} 个：请只保留一个空档（本次未落库，无新增运行）",
        )

    # --- 提交瞬间重算：摊主、挡柱、已落库放置全部现查，拒收一切旧预估缓存 ---
    seg, pillars, _vendors, placements, base_spans, occupied, pending_vendors = _load_snapshot(
        db, body.segment_id
    )
    gap_index = body.gap_indexes[0]
    placement, rejected = place_in_gap(base_spans, occupied, gap_index, pending_vendors)

    if placement is None:
        # 业务要求拒空跑：该空档此刻无法形成任何有效放置 → 明确拒绝，不增行，
        # 不记成功运行，也不冒充笼统的分配成功。
        raise HTTPException(
            409,
            f"确认被拒绝（拒空跑）：{rejected.reason}；该空档此刻无法形成任何有效放置"
            "（未写入任何放置，运行表无新增行）",
        )

    # --- 有效放置：Placement 与 AllocationRun 同一事务落库 ---
    row = Placement(
        segment_id=seg.id, vendor_id=placement.vendor_id, vendor_name=placement.vendor_name,
        start_m=placement.start_m, end_m=placement.end_m, width_m=placement.width_m,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()  # 取 placement.id
    snapshot = {
        "placement": {"vendor_id": row.vendor_id, "vendor_name": row.vendor_name,
                      "start_m": row.start_m, "end_m": row.end_m, "width_m": row.width_m},
        "gap_index": gap_index,
    }
    run = AllocationRun(segment_id=seg.id, placement_id=row.id, created_at=datetime.utcnow(),
                        result_json=json.dumps(snapshot, ensure_ascii=False))
    db.add(run)
    db.commit()
    db.refresh(row)
    db.refresh(run)

    seg2, p2, _v, placements2, spans2, occ2, pending2 = _load_snapshot(db, body.segment_id)
    return {"ok": True, "run_id": run.id,
            **_state_payload(db, seg2, p2, placements2, spans2, occ2, pending2)}
