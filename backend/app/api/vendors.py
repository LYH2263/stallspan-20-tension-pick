from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Vendor
router = APIRouter(prefix="/vendors", tags=["vendors"])

class VendorPatch(BaseModel):
    stall_width_m: float | None = None
    priority: int | None = None

@router.get("")
def list_vendors(db: Session = Depends(get_db)):
    return [{"id": r.id, "market_day_id": r.market_day_id, "name": r.name,
             "stall_width_m": r.stall_width_m, "priority": r.priority}
            for r in db.scalars(select(Vendor).order_by(Vendor.priority, Vendor.id)).all()]

@router.patch("/{vendor_id}")
def patch_vendor(vendor_id: int, body: VendorPatch, db: Session = Depends(get_db)):
    """改摊宽/优先级：下一次紧张度与确认都按提交瞬间的新值重算。"""
    row = db.get(Vendor, vendor_id)
    if not row:
        raise HTTPException(404, "摊主不存在")
    if body.stall_width_m is not None:
        if body.stall_width_m <= 0:
            raise HTTPException(400, "摊位宽度必须为正数")
        row.stall_width_m = body.stall_width_m
    if body.priority is not None:
        row.priority = body.priority
    db.commit()
    return {"id": row.id, "market_day_id": row.market_day_id, "name": row.name,
            "stall_width_m": row.stall_width_m, "priority": row.priority}
