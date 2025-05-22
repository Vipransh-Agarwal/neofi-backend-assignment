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
from sqlalchemy.sql import func
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
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    start_datetime = Column(DateTime(timezone=True), nullable=False)
    end_datetime = Column(DateTime(timezone=True), nullable=False)

    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    creator = relationship("User", back_populates="events")
    
    version_number = Column(Integer, nullable=False, server_default="1")

    # Optional: also update updated_at timestamp
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    recurrence_rule = Column(Text(), nullable=True)
    recurrence_end = Column(DateTime(timezone=True), nullable=True)


    # Relationship to permissions, versions, etc.
    permissions = relationship("EventPermission", back_populates="event", cascade="all, delete-orphan")
    versions = relationship("EventVersion", back_populates="event", cascade="all, delete-orphan")
    
    exceptions = relationship("EventException", back_populates="event", cascade="all, delete-orphan")


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

class EventException(Base):
    __tablename__ = "event_exceptions"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    exception_date = Column(DateTime(timezone=True), nullable=False)
    # Optionally: a JSON column to override certain fields for that date (title, start/end)
    override_data = Column(JSON(), nullable=True)

    event = relationship("Event", back_populates="exceptions")


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


# ─── AuditLog ───────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String(512), nullable=False)       # e.g. "/api/events/3"
    method = Column(String(10), nullable=False)       # "GET", "POST"
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status_code = Column(Integer, nullable=False)
    ip_address = Column(String(45), nullable=True)    # IPv4 or IPv6
    request_body = Column(JSON, nullable=True)        # store JSON body (optional)
    response_body = Column(JSON, nullable=True)       # store JSON response (optional)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User")