from datetime import datetime

from sqlalchemy import String, Numeric, Integer, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # asset, liability
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_type: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    event_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="transfer")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    transfer_id: Mapped[str] = mapped_column(ForeignKey("transfers.id"), nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    direction: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=debit, -1=credit
    amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    previous_balance: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    current_balance: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transfer: Mapped["Transfer"] = relationship(back_populates="entries")
