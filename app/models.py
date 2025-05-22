from enum import Enum
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
    Index,
    UniqueConstraint,
    Enum as SQLEnum
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class RoleType(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    role = Column(SQLEnum(RoleType), nullable=False, default=RoleType.VIEWER)

    # relationship to events the user created
    events = relationship("Event", back_populates="creator")

    # relationship for permissions, versions, etc. (if needed)
    permissions_given = relationship(
        "EventPermission",
        foreign_keys="EventPermission.granted_by_id",
        back_populates="granted_by",
        cascade="all, delete-orphan",
    )
    versions_created = relationship(
        "EventVersion",
        foreign_keys="EventVersion.created_by_id",
        back_populates="created_by",
        cascade="all, delete-orphan",
    )
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    start_datetime = Column(DateTime(timezone=True), nullable=False)
    end_datetime = Column(DateTime(timezone=True), nullable=False)

    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    creator = relationship("User", back_populates="events")

    version_number = Column(Integer, nullable=False, server_default="1")

    # Automatically set/refresh updated_at
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        onupdate=func.now(),
    )

    recurrence_rule = Column(Text(), nullable=True)
    recurrence_end = Column(DateTime(timezone=True), nullable=True)

    # relationships
    permissions = relationship(
        "EventPermission", back_populates="event", cascade="all, delete-orphan"
    )
    versions = relationship(
        "EventVersion", back_populates="event", cascade="all, delete-orphan"
    )
    exceptions = relationship(
        "EventException", back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # index on creator_id → speeds up “events created by user X”
        Index("ix_events_creator_id", "creator_id"),

        # index on start_datetime → for filtering/sorting by date
        Index("ix_events_start_datetime", "start_datetime"),

        # composite index on (start_datetime, end_datetime) if you query both together
        Index("ix_events_start_end", "start_datetime", "end_datetime"),

        # index on recurrence_end → for querying events that stop recurring by a certain date
        Index("ix_events_recurrence_end", "recurrence_end"),
    )


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

    # relationships
    event = relationship("Event", back_populates="permissions")
    user = relationship("User", foreign_keys=[user_id])
    granted_by = relationship("User", foreign_keys=[granted_by_id], back_populates="permissions_given")

    __table_args__ = (
        # unique constraint: no duplicate (event_id, user_id)
        UniqueConstraint("event_id", "user_id", name="ux_event_permissions_event_user"),

        # index on event_id → speeds up “who has permissions on this event?”
        Index("ix_event_permissions_event_id", "event_id"),

        # index on user_id → speeds up “list all events user X can access”
        Index("ix_event_permissions_user_id", "user_id"),
    )


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
    snapshot = Column(JSON, nullable=False)  # store the full event payload as JSON
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )

    # relationships
    event = relationship("Event", back_populates="versions")
    created_by = relationship("User", back_populates="versions_created", foreign_keys=[created_by_id])
    changes = relationship("EventChange", back_populates="version", cascade="all, delete-orphan")

    __table_args__ = (
        # unique on (event_id, version_number)
        UniqueConstraint("event_id", "version_number", name="ux_event_versions_event_version"),

        # index on event_id → for listing all versions of a single event
        Index("ix_event_versions_event_id", "event_id"),
    )


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
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    version = relationship("EventVersion", back_populates="changes")

    __table_args__ = (
        # index on event_version_id → for fetching all changes in a given version
        Index("ix_event_changes_event_version_id", "event_version_id"),
    )


class EventException(Base):
    __tablename__ = "event_exceptions"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(
        Integer,
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exception_date = Column(DateTime(timezone=True), nullable=False)
    override_data = Column(JSON(), nullable=True)

    event = relationship("Event", back_populates="exceptions")

    __table_args__ = (
        # index on event_id → for quickly retrieving exceptions for a given event
        Index("ix_event_exceptions_event_id", "event_id"),

        # index on exception_date → for date‐based queries on exceptions
        Index("ix_event_exceptions_exception_date", "exception_date"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String(512), nullable=False)       # e.g. "/api/events/3"
    method = Column(String(10), nullable=False)       # "GET", "POST"
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status_code = Column(Integer, nullable=False)
    ip_address = Column(String(45), nullable=True)    # IPv4 or IPv6
    request_body = Column(JSON, nullable=True)
    response_body = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        # index on user_id → for listing all logs by a particular user
        Index("ix_audit_logs_user_id", "user_id"),

        # index on timestamp → for date‐range filtering of audit entries
        Index("ix_audit_logs_timestamp", "timestamp"),
    )
