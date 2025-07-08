"""
Secret model for storing encrypted YouTube OAuth credentials
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Secret(Base):
    """Secret model for storing encrypted YouTube OAuth credentials."""
    
    __tablename__ = "secrets"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True
    )
    
    # User relationship
    user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # YouTube OAuth credentials (extracted from JSON)
    project_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    client_id_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    
    client_secret_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    
    # Additional OAuth configuration (stored as plain text)
    auth_uri: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="https://accounts.google.com/o/oauth2/auth"
    )
    
    token_uri: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="https://oauth2.googleapis.com/token"
    )
    
    auth_provider_x509_cert_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="https://www.googleapis.com/oauth2/v1/certs"
    )
    
    # Redirect URIs (JSON format as text)
    redirect_uris: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Status tracking
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    
    # Original filename for reference
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Relationships
    user = relationship("User", back_populates="secrets")

    def __repr__(self) -> str:
        return f"<Secret(id='{self.id}', user_id='{self.user_id}', project_id='{self.project_id}')>" 