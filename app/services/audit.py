from datetime import datetime

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings


class Base(DeclarativeBase):
    pass


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(100), index=True)
    actor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def write_audit_log(
    action: str,
    entity_type: str,
    entity_id: str,
    *,
    actor: str | None = None,
    details: dict | None = None,
    message: str | None = None,
) -> None:
    async with async_session_factory() as session:
        log = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            details=details,
            message=message,
        )
        session.add(log)
        await session.commit()


async def list_audit_logs(entity_id: str | None = None, limit: int = 50) -> list[dict]:
    async with async_session_factory() as session:
        stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
        if entity_id:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": row.id,
                "timestamp": row.timestamp.isoformat(),
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "actor": row.actor,
                "details": row.details,
                "message": row.message,
            }
            for row in rows
        ]
