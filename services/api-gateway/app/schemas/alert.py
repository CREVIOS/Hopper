"""Schemas for per-user telemetry alert preferences."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_SEVERITIES = ("info", "warning", "critical")


class AlertPreferenceOut(BaseModel):
    email_enabled: bool = False
    email_address: str = ""
    telegram_enabled: bool = False
    telegram_number: str = ""
    min_severity: str = "warning"
    # Read-only: whether the platform has the Green API Telegram gateway
    # configured, so the UI can enable/disable the Telegram toggle accordingly.
    telegram_configured: bool = False


class AlertPreferenceUpdate(BaseModel):
    email_enabled: bool = False
    email_address: str = Field(default="", max_length=320)
    telegram_enabled: bool = False
    telegram_number: str = Field(default="", max_length=32)
    min_severity: str = "warning"

    @field_validator("min_severity")
    @classmethod
    def _valid_severity(cls, v: str) -> str:
        v = (v or "warning").lower().strip()
        if v not in _SEVERITIES:
            raise ValueError(f"min_severity must be one of {_SEVERITIES}")
        return v

    @field_validator("telegram_number")
    @classmethod
    def _norm_number(cls, v: str) -> str:
        return (v or "").strip()
