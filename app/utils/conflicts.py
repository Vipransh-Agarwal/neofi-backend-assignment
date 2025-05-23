from datetime import datetime
from sqlalchemy import and_, or_
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..models import Event

async def detect_event_conflicts(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    user_id: int,
    exclude_event_id: int | None = None
) -> List[Event]:
    """
    Check for any conflicting events for a given time period.
    Args:
        db: AsyncSession
        start: Start datetime of the event to check
        end: End datetime of the event to check  
        user_id: User ID to check conflicts for
        exclude_event_id: Optional event ID to exclude (for updates)
    Returns:
        List of conflicting Event objects
    """
    query = select(Event).where(
        and_(
            Event.creator_id == user_id,
            or_(
                # New event starts during an existing event
                and_(Event.start_datetime <= start, Event.end_datetime > start),
                # New event ends during an existing event  
                and_(Event.start_datetime < end, Event.end_datetime >= end),
                # New event completely contains an existing event
                and_(Event.start_datetime >= start, Event.end_datetime <= end)
            )
        )
    )
    
    if exclude_event_id:
        query = query.where(Event.id != exclude_event_id)
        
    result = await db.execute(query)
    return result.scalars().all()