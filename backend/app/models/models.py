from datetime import date, datetime
from sqlalchemy import (
    Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class MarketDay(Base):
    __tablename__ = "market_days"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    day: Mapped[date] = mapped_column(Date)

class Segment(Base):
    __tablename__ = "segments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_day_id: Mapped[int] = mapped_column(ForeignKey("market_days.id"))
    name: Mapped[str] = mapped_column(String(64))
    width_m: Mapped[float] = mapped_column(Float)

class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_day_id: Mapped[int] = mapped_column(ForeignKey("market_days.id"))
    name: Mapped[str] = mapped_column(String(64))
    stall_width_m: Mapped[float] = mapped_column(Float)
    priority: Mapped[int] = mapped_column(Integer, default=1)

class Pillar(Base):
    __tablename__ = "pillars"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"))
    position_m: Mapped[float] = mapped_column(Float)
    thickness_m: Mapped[float] = mapped_column(Float, default=0.4)
    label: Mapped[str] = mapped_column(String(32), default="挡柱")

class AllocationRun(Base):
    """一次成功确认：恰好选中一个柱间空档，且至少落了一个摊位。"""
    __tablename__ = "allocation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    span_index: Mapped[int] = mapped_column(Integer)
    span_start_m: Mapped[float] = mapped_column(Float)
    span_end_m: Mapped[float] = mapped_column(Float)
    result_json: Mapped[str] = mapped_column(Text, default="{}")

class Placement(Base):
    """已入库的成功放置。同一街段内一个摊主只允许落位一次。"""
    __tablename__ = "placements"
    __table_args__ = (UniqueConstraint("segment_id", "vendor_id", name="uq_placement_segment_vendor"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("allocation_runs.id"))
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    vendor_name: Mapped[str] = mapped_column(String(64))
    start_m: Mapped[float] = mapped_column(Float)
    end_m: Mapped[float] = mapped_column(Float)
    width_m: Mapped[float] = mapped_column(Float)
