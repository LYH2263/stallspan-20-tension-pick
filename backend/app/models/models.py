from datetime import date, datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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

class Placement(Base):
    """确认落库的放置：一档摊主在一个柱间空档内的一段连续区间。"""
    __tablename__ = "placements"
    __table_args__ = (UniqueConstraint("segment_id", "vendor_id", name="uq_placement_segment_vendor"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    vendor_name: Mapped[str] = mapped_column(String(64))
    start_m: Mapped[float] = mapped_column(Float)
    end_m: Mapped[float] = mapped_column(Float)
    width_m: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AllocationRun(Base):
    """成功确认一次 = 一条运行记录；拒绝/空跑绝不产生行。"""
    __tablename__ = "allocation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"))
    placement_id: Mapped[int | None] = mapped_column(ForeignKey("placements.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
