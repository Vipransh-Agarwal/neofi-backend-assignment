from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    events = relationship("Event", back_populates="creator")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    start_datetime = Column(DateTime, nullable=False, index=True)
    end_datetime = Column(DateTime, nullable=False, index=True)
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship back to the user who created it
    creator = relationship("User", back_populates="events")


class EventPermission(Base):
    __tablename__ = "event_permissions"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(
        Integer,
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    can_edit = Column(Boolean, nullable=False, default=False)
    granted_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships (optional, for convenience)
    event = relationship("Event", back_populates="permissions")
    user = relationship("User", foreign_keys=[user_id])
    granted_by = relationship("User", foreign_keys=[granted_by_id])


class EventVersion(Base):
    __tablename__ = "event_versions"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(
        Integer,
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False)  # store full event payload as JSON
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )

    event = relationship("Event", back_populates="versions")
    created_by = relationship("User", foreign_keys=[created_by_id])


class EventChange(Base):
    __tablename__ = "event_changes"

    id = Column(Integer, primary_key=True, index=True)
    event_version_id = Column(
        Integer,
        ForeignKey("event_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name = Column(String, nullable=False)
    old_value = Column(Text, nullable=True)  # JSON‐serialized text of the old value
    new_value = Column(Text, nullable=True)  # JSON‐serialized text of the new value
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    version = relationship("EventVersion", back_populates="changes")


# ─── Relationships in Event and EventVersion ───────────────────────────────

# In Event (add this above or below your existing class):
Event.permissions = relationship(
    "EventPermission", back_populates="event", cascade="all, delete-orphan"
)
Event.versions = relationship(
    "EventVersion", back_populates="event", cascade="all, delete-orphan"
)

# In EventVersion (add this below the class):
EventVersion.changes = relationship(
    "EventChange", back_populates="version", cascade="all, delete-orphan"
)