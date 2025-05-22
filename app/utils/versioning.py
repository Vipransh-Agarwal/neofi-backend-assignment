from datetime import datetime
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models import Event, EventVersion, EventChange


async def record_event_version(db: AsyncSession, event: Event, user_id: int):
    result = await db.execute(
        select(EventVersion)
        .where(EventVersion.event_id == event.id)
        .order_by(EventVersion.version_number.desc())
        .limit(1)
    )
    last_version = result.scalar_one_or_none()
    next_version_number = (last_version.version_number + 1) if last_version else 1

    new_snapshot: Dict[str, Any] = {
        "title": event.title,
        "description": event.description,
        "start_datetime": event.start_datetime.isoformat() if event.start_datetime else None,
        "end_datetime": event.end_datetime.isoformat() if event.end_datetime else None,
        "creator_id": event.creator_id,
        "created_at": event.updated_at.isoformat() if event.updated_at else datetime.utcnow().isoformat(),
    }

    version_row = EventVersion(
        event_id=event.id,
        version_number=next_version_number,
        snapshot=new_snapshot,
        created_at=datetime.utcnow(),
        created_by_id=user_id,
    )
    db.add(version_row)
    await db.flush()

    if last_version:
        old_snapshot = last_version.snapshot
        changes = []
        for key, new_val in new_snapshot.items():
            old_val = old_snapshot.get(key)
            if old_val != new_val:
                changes.append(
                    EventChange(
                        event_version_id=version_row.id,
                        field_name=key,
                        old_value=str(old_val) if old_val is not None else None,
                        new_value=str(new_val) if new_val is not None else None,
                        changed_at=datetime.utcnow(),
                    )
                )
        if changes:
            db.add_all(changes)

    return version_row
